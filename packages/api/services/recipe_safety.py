"""Recipe safety controls — content firewalls, idempotency, nesting depth,
fan-out rate limiting (WU-42.2).

Per Resolve spec §4 / Decision D11:
  - Content firewall at EVERY step transition (mandatory).
  - Idempotency key system for retry-safe execution.
  - Nesting depth limit (3) for sub-recipe invocations.
  - Fan-out rate limiting at runtime (distinct from compile-time DAG validation).

Spec principle: "Deploy with aggressive defaults, measure false positive rate,
tune down. Track blocked-but-legitimate content."
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import logging
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import unquote_plus

logger = logging.getLogger(__name__)


# ── Content Firewall ──────────────────────────────────────────────────


class ContentViolationType(str, Enum):
    """Classification of content firewall violations."""

    PROMPT_INJECTION = "prompt_injection"
    SHELL_INJECTION = "shell_injection"
    PATH_TRAVERSAL = "path_traversal"
    EXCESSIVE_LENGTH = "excessive_length"
    SUSPICIOUS_ENCODING = "suspicious_encoding"
    DISALLOWED_PATTERN = "disallowed_pattern"
    CONTROL_CHARACTER = "control_character"
    ENCODED_PAYLOAD = "encoded_payload"
    NESTING_DEPTH_EXCEEDED = "nesting_depth_exceeded"


@dataclass(frozen=True, slots=True)
class ContentViolation:
    """A detected content policy violation at a step transition."""

    violation_type: ContentViolationType
    field_path: str  # e.g., "outputs.result.text"
    description: str
    severity: str  # "block" | "warn"
    matched_pattern: str = ""


@dataclass(frozen=True, slots=True)
class FirewallResult:
    """Result of content firewall inspection."""

    passed: bool
    violations: tuple[ContentViolation, ...] = ()
    warnings: tuple[ContentViolation, ...] = ()
    inspected_fields: int = 0
    inspection_time_ms: float = 0.0


# Compile regex patterns once at module load
_PROMPT_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions?"), "ignore previous instructions"),
    (re.compile(r"(?i)you\s+are\s+now\s+a"), "role reassignment"),
    (re.compile(r"(?i)system\s*:\s*"), "system prompt injection"),
    (re.compile(r"(?i)(?:act|pretend|behave)\s+as\s+(?:if|though)?\s*(?:you\s+(?:are|were))?"), "behavioral override"),
    (re.compile(r"(?i)forget\s+(?:all|everything|your|the)"), "memory wipe"),
    (re.compile(r"(?i)(?:new|override|reset)\s+(?:system\s+)?prompt"), "prompt override"),
    (re.compile(r"(?i)(?:do\s+not|don't|never)\s+(?:follow|obey|listen)"), "instruction override"),
    (re.compile(r"(?i)\[SYSTEM\]"), "system tag injection"),
    (re.compile(r"(?i)<\|(?:system|endoftext|im_start|im_end)\|>"), "special token injection"),
    (re.compile(r"(?i)(?:jailbreak|DAN\s+mode|developer\s+mode)"), "explicit jailbreak"),
]

_SHELL_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[;&|`$]\s*(?:rm|curl|wget|nc|python|bash|sh|eval|exec)\b"), "shell command injection"),
    (re.compile(r"\$\(.*\)"), "command substitution"),
    (re.compile(r"`[^`]+`"), "backtick execution"),
]

_PATH_TRAVERSAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\.\./"), "path traversal"),
    (re.compile(r"(?i)(?:/etc/passwd|/etc/shadow|~/.ssh)"), "sensitive path"),
]

# Maximum field value length before triggering a warning
MAX_FIELD_LENGTH = 100_000  # 100KB per field
MAX_TOTAL_CONTENT_LENGTH = 1_000_000  # 1MB total across all fields


class ContentFirewall:
    """Inspects data flowing between recipe steps for safety violations.

    Called at every step transition:
    - Before step input resolution (inspect resolved parameters)
    - After step output capture (inspect outputs before downstream use)

    Aggressive by default (spec requirement). Tracks false positives
    for future tuning.
    """

    def __init__(
        self,
        *,
        block_on_injection: bool = True,
        max_field_length: int = MAX_FIELD_LENGTH,
        max_total_length: int = MAX_TOTAL_CONTENT_LENGTH,
        custom_disallowed: list[tuple[re.Pattern, str]] | None = None,
    ) -> None:
        self._block_on_injection = block_on_injection
        self._max_field_length = max_field_length
        self._max_total_length = max_total_length
        self._custom_disallowed = custom_disallowed or []
        self._blocked_count = 0
        self._warned_count = 0
        self._inspected_count = 0
        self._lock = threading.Lock()

    def inspect(
        self,
        data: dict[str, Any],
        context: str = "step_transition",
    ) -> FirewallResult:
        """Inspect a data payload for content safety violations.

        Args:
            data: The data dict to inspect (step outputs or resolved params)
            context: Human label for logging ("step_transition", "input", "output")

        Returns:
            FirewallResult with pass/fail + violation details
        """
        start = time.monotonic()
        violations: list[ContentViolation] = []
        warnings: list[ContentViolation] = []
        field_count = 0
        total_length = 0

        self._inspect_recursive(
            data, "", violations, warnings, field_count=0,
            total_length_ref=[0],
        )
        field_count = self._count_fields(data)

        elapsed_ms = (time.monotonic() - start) * 1000

        blocking = [v for v in violations if v.severity == "block"]
        warn_only = [v for v in violations if v.severity == "warn"] + warnings

        passed = len(blocking) == 0

        with self._lock:
            self._inspected_count += 1
            if not passed:
                self._blocked_count += 1
            if warn_only:
                self._warned_count += 1

        if not passed:
            logger.warning(
                "content_firewall_blocked context=%s violations=%d fields=%d",
                context,
                len(blocking),
                field_count,
            )

        return FirewallResult(
            passed=passed,
            violations=tuple(blocking),
            warnings=tuple(warn_only),
            inspected_fields=field_count,
            inspection_time_ms=round(elapsed_ms, 2),
        )

    def _count_fields(self, data: Any) -> int:
        """Count total scalar fields in a nested structure."""
        if isinstance(data, dict):
            return sum(self._count_fields(v) for v in data.values())
        if isinstance(data, (list, tuple)):
            return sum(self._count_fields(item) for item in data)
        return 1

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for pattern matching (AUD-2 hardening).

        1. NFKC normalization — collapses Unicode confusables
           (e.g., fullwidth 'ｉｇｎｏｒｅ' → 'ignore')
        2. Strip zero-width characters — defeats invisible insertion
           (U+200B, U+200C, U+200D, U+FEFF, U+2060, etc.)
        3. Strip combining marks used as visual noise
        """
        # NFKC normalizes compatibility decomposition + canonical composition
        normalized = unicodedata.normalize("NFKC", text)

        # Strip zero-width and invisible formatting characters
        _INVISIBLE_CHARS = frozenset([
            "\u200b",  # zero-width space
            "\u200c",  # zero-width non-joiner
            "\u200d",  # zero-width joiner
            "\u200e",  # left-to-right mark
            "\u200f",  # right-to-left mark
            "\u2060",  # word joiner
            "\u2061",  # function application
            "\u2062",  # invisible times
            "\u2063",  # invisible separator
            "\u2064",  # invisible plus
            "\ufeff",  # byte order mark / zero-width no-break space
            "\u00ad",  # soft hyphen
            "\u034f",  # combining grapheme joiner
            "\u061c",  # arabic letter mark
            "\u180e",  # mongolian vowel separator
        ])
        normalized = "".join(c for c in normalized if c not in _INVISIBLE_CHARS)

        return normalized

    @staticmethod
    def _detect_control_chars(text: str) -> list[str]:
        """Detect dangerous control characters beyond null bytes (AUD-2).

        Returns list of descriptions of found control chars.
        """
        found = []
        for i, ch in enumerate(text):
            cp = ord(ch)
            # C0 control chars (except \t, \n, \r which are normal)
            if cp < 0x20 and ch not in ("\t", "\n", "\r"):
                found.append(f"C0 control U+{cp:04X} at position {i}")
            # C1 control chars (0x80-0x9F)
            elif 0x80 <= cp <= 0x9F:
                found.append(f"C1 control U+{cp:04X} at position {i}")
            # Bidirectional override/embedding characters (text spoofing)
            elif cp in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069):
                found.append(f"bidi override U+{cp:04X} at position {i}")
        return found

    @staticmethod
    def _is_printable_text(text: str) -> bool:
        printable_ratio = sum(
            1 for c in text if c.isprintable() or c in ("\n", "\r", "\t")
        ) / max(len(text), 1)
        return printable_ratio > 0.5

    @classmethod
    def _try_decode_base64(cls, text: str) -> str | None:
        """Try to decode a base64-encoded string (AUD-2)."""
        stripped = text.strip()
        if len(stripped) < 20:
            return None
        if not re.match(r'^[A-Za-z0-9+/=\n\r]+$', stripped):
            return None
        try:
            decoded = base64.b64decode(stripped, validate=True)
            decoded_text = decoded.decode("utf-8")
            if cls._is_printable_text(decoded_text):
                return decoded_text
        except Exception:
            pass
        return None

    @classmethod
    def _try_decode_hex(cls, text: str) -> str | None:
        """Try to decode a hex-encoded UTF-8 payload (AUD-R1-06)."""
        stripped = re.sub(r"\s+", "", text.strip())
        if stripped.startswith(("0x", "0X")):
            stripped = stripped[2:]
        if len(stripped) < 20 or len(stripped) % 2 != 0:
            return None
        if not re.fullmatch(r"[0-9a-fA-F]+", stripped):
            return None
        try:
            decoded_text = bytes.fromhex(stripped).decode("utf-8")
            if cls._is_printable_text(decoded_text):
                return decoded_text
        except (ValueError, UnicodeDecodeError, binascii.Error):
            pass
        return None

    @classmethod
    def _decoded_payloads(cls, text: str) -> list[tuple[str, str]]:
        """Return encoded payload variants worth inspecting."""
        decoded_variants: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(label: str, decoded: str | None) -> None:
            if decoded is None:
                return
            key = (label, decoded)
            if key not in seen:
                seen.add(key)
                decoded_variants.append(key)

        add("base64", cls._try_decode_base64(text))
        add("hex", cls._try_decode_hex(text))

        if "%" in text or "+" in text:
            url_decoded = unquote_plus(text)
            if url_decoded != text and cls._is_printable_text(url_decoded):
                add("url", url_decoded)

        if "&" in text and ";" in text:
            html_decoded = html.unescape(text)
            if html_decoded != text and cls._is_printable_text(html_decoded):
                add("html", html_decoded)

        return decoded_variants

    def _inspect_string(
        self,
        data: str,
        path: str,
        violations: list[ContentViolation],
        warnings: list[ContentViolation],
        total_length_ref: list[int],
    ) -> None:
        """Inspect a single string field with full AUD-2 hardening."""
        total_length_ref[0] += len(data)

        # Length checks
        if len(data) > self._max_field_length:
            violations.append(ContentViolation(
                violation_type=ContentViolationType.EXCESSIVE_LENGTH,
                field_path=path,
                description=f"Field exceeds max length ({len(data)} > {self._max_field_length})",
                severity="block",
            ))
        if total_length_ref[0] > self._max_total_length:
            violations.append(ContentViolation(
                violation_type=ContentViolationType.EXCESSIVE_LENGTH,
                field_path=path,
                description=f"Total content exceeds max ({total_length_ref[0]} > {self._max_total_length})",
                severity="block",
            ))

        # Control character detection (AUD-2: beyond just null bytes)
        if "\x00" in data:
            violations.append(ContentViolation(
                violation_type=ContentViolationType.SUSPICIOUS_ENCODING,
                field_path=path,
                description="Null byte detected in string field",
                severity="block",
            ))

        control_chars = self._detect_control_chars(data)
        if control_chars:
            violations.append(ContentViolation(
                violation_type=ContentViolationType.CONTROL_CHARACTER,
                field_path=path,
                description=f"Dangerous control characters detected: {'; '.join(control_chars[:5])}",
                severity="block",
                matched_pattern="control_characters",
            ))

        # Normalize before pattern matching (AUD-2: NFKC + zero-width stripping)
        normalized = self._normalize_text(data)

        # Prompt injection (on normalized text)
        for pattern, label in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(normalized):
                severity = "block" if self._block_on_injection else "warn"
                violations.append(ContentViolation(
                    violation_type=ContentViolationType.PROMPT_INJECTION,
                    field_path=path,
                    description=f"Prompt injection pattern detected: {label}",
                    severity=severity,
                    matched_pattern=label,
                ))

        # Shell injection (on normalized text)
        for pattern, label in _SHELL_INJECTION_PATTERNS:
            if pattern.search(normalized):
                violations.append(ContentViolation(
                    violation_type=ContentViolationType.SHELL_INJECTION,
                    field_path=path,
                    description=f"Shell injection pattern: {label}",
                    severity="block",
                    matched_pattern=label,
                ))

        # Path traversal (on normalized text)
        for pattern, label in _PATH_TRAVERSAL_PATTERNS:
            if pattern.search(normalized):
                violations.append(ContentViolation(
                    violation_type=ContentViolationType.PATH_TRAVERSAL,
                    field_path=path,
                    description=f"Path traversal pattern: {label}",
                    severity="block",
                    matched_pattern=label,
                ))

        # Encoded payload inspection (AUD-2 / AUD-R1-06)
        for encoding, decoded_text in self._decoded_payloads(data):
            decoded_normalized = self._normalize_text(decoded_text)
            for pattern, label in _PROMPT_INJECTION_PATTERNS:
                if pattern.search(decoded_normalized):
                    violations.append(ContentViolation(
                        violation_type=ContentViolationType.ENCODED_PAYLOAD,
                        field_path=path,
                        description=f"Prompt injection in {encoding}-encoded content: {label}",
                        severity="block",
                        matched_pattern=f"{encoding}:{label}",
                    ))
            for pattern, label in _SHELL_INJECTION_PATTERNS:
                if pattern.search(decoded_normalized):
                    violations.append(ContentViolation(
                        violation_type=ContentViolationType.ENCODED_PAYLOAD,
                        field_path=path,
                        description=f"Shell injection in {encoding}-encoded content: {label}",
                        severity="block",
                        matched_pattern=f"{encoding}:{label}",
                    ))
            for pattern, label in _PATH_TRAVERSAL_PATTERNS:
                if pattern.search(decoded_normalized):
                    violations.append(ContentViolation(
                        violation_type=ContentViolationType.ENCODED_PAYLOAD,
                        field_path=path,
                        description=f"Path traversal in {encoding}-encoded content: {label}",
                        severity="block",
                        matched_pattern=f"{encoding}:{label}",
                    ))

        # Custom disallowed patterns (on normalized text)
        for pattern, label in self._custom_disallowed:
            if pattern.search(normalized):
                violations.append(ContentViolation(
                    violation_type=ContentViolationType.DISALLOWED_PATTERN,
                    field_path=path,
                    description=f"Disallowed pattern: {label}",
                    severity="block",
                    matched_pattern=label,
                ))

    def _inspect_recursive(
        self,
        data: Any,
        path: str,
        violations: list[ContentViolation],
        warnings: list[ContentViolation],
        *,
        field_count: int,
        total_length_ref: list[int],
        depth: int = 0,
    ) -> None:
        """Walk data structure, checking each string field.

        AUD-2 hardening: block on depth exceeded (instead of silent return),
        inspect dict keys (not just values).
        """
        if depth > 20:
            # AUD-2: block instead of silently stopping inspection
            violations.append(ContentViolation(
                violation_type=ContentViolationType.NESTING_DEPTH_EXCEEDED,
                field_path=path,
                description=f"Data nesting depth {depth} exceeds inspection limit of 20",
                severity="block",
                matched_pattern="max_inspection_depth",
            ))
            return

        if isinstance(data, str):
            self._inspect_string(data, path, violations, warnings, total_length_ref)

        elif isinstance(data, dict):
            for key, value in data.items():
                child_path = f"{path}.{key}" if path else key
                # AUD-2: inspect dict keys too (attackers can hide payloads in keys)
                if isinstance(key, str):
                    self._inspect_string(key, f"{path}[key:{key}]", violations, warnings, total_length_ref)
                self._inspect_recursive(
                    value, child_path, violations, warnings,
                    field_count=field_count, total_length_ref=total_length_ref,
                    depth=depth + 1,
                )

        elif isinstance(data, (list, tuple)):
            for i, item in enumerate(data):
                child_path = f"{path}[{i}]"
                self._inspect_recursive(
                    item, child_path, violations, warnings,
                    field_count=field_count, total_length_ref=total_length_ref,
                    depth=depth + 1,
                )

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "inspected": self._inspected_count,
                "blocked": self._blocked_count,
                "warned": self._warned_count,
            }


# ── Idempotency Key System ───────────────────────────────────────────


@dataclass(slots=True)
class IdempotencyRecord:
    """Stored result for a previous execution with this key."""

    key: str
    execution_id: str
    recipe_id: str
    status: str
    result_hash: str
    created_at: datetime
    expires_at: datetime


class IdempotencyStore:
    """In-memory idempotency key store for recipe executions.

    Ensures retry-safe execution: same key → same result.
    Keys expire after a configurable window (default 1 hour).

    Spec requirement: "Double-charge on retry" is a HIGH likelihood,
    HIGH impact risk. Idempotency keys are required.
    """

    def __init__(
        self,
        *,
        window_seconds: int = 3600,
        max_entries: int = 10_000,
    ) -> None:
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._store: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()
        self._clock = time.time

    def check(self, key: str) -> IdempotencyRecord | None:
        """Check if an idempotency key has a stored result.

        Returns the stored record if found and not expired, else None.
        """
        with self._lock:
            record = self._store.get(key)
            if record is None:
                return None
            if self._clock() > record.expires_at.timestamp():
                self._store.pop(key, None)
                return None
            return record

    def store(
        self,
        key: str,
        execution_id: str,
        recipe_id: str,
        status: str,
        result_hash: str,
    ) -> IdempotencyRecord:
        """Store an execution result for an idempotency key."""
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expires = now + timedelta(seconds=self._window_seconds)

        record = IdempotencyRecord(
            key=key,
            execution_id=execution_id,
            recipe_id=recipe_id,
            status=status,
            result_hash=result_hash,
            created_at=now,
            expires_at=expires,
        )

        with self._lock:
            self._store[key] = record
            # Evict expired entries if over capacity
            if len(self._store) > self._max_entries:
                self._prune_expired()
        return record

    def _prune_expired(self) -> None:
        """Remove expired entries (call under lock)."""
        now = self._clock()
        expired = [k for k, v in self._store.items() if now > v.expires_at.timestamp()]
        for k in expired:
            self._store.pop(k, None)

    @staticmethod
    def generate_key(
        recipe_id: str,
        inputs: dict[str, Any],
        agent_id: str = "",
    ) -> str:
        """Generate a deterministic idempotency key from recipe + inputs + agent."""
        import json
        payload = json.dumps(
            {"recipe_id": recipe_id, "inputs": inputs, "agent_id": agent_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"idem_{hashlib.sha256(payload.encode()).hexdigest()[:32]}"

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ── Nesting Depth Tracker ────────────────────────────────────────────

MAX_NESTING_DEPTH = 3


class NestingDepthError(Exception):
    """Raised when recipe nesting exceeds the limit."""

    pass


class NestingTracker:
    """Tracks recipe-within-recipe nesting depth.

    A recipe step can invoke a sub-recipe. This tracker enforces
    the max nesting depth (3 levels) per the Resolve spec.

    Thread-safe: uses a dict keyed by execution chain ID.
    """

    def __init__(self, max_depth: int = MAX_NESTING_DEPTH) -> None:
        self._max_depth = max_depth
        # execution_chain_id → current depth
        self._depths: dict[str, int] = {}
        self._lock = threading.Lock()

    def enter(self, chain_id: str) -> int:
        """Enter a nesting level. Returns the new depth.

        Raises NestingDepthError if exceeding max depth.
        """
        with self._lock:
            current = self._depths.get(chain_id, 0)
            new_depth = current + 1
            if new_depth > self._max_depth:
                raise NestingDepthError(
                    f"Recipe nesting depth {new_depth} exceeds maximum of {self._max_depth}"
                )
            self._depths[chain_id] = new_depth
            return new_depth

    def exit(self, chain_id: str) -> int:
        """Exit a nesting level. Returns the new depth."""
        with self._lock:
            current = self._depths.get(chain_id, 1)
            new_depth = max(0, current - 1)
            if new_depth == 0:
                self._depths.pop(chain_id, None)
            else:
                self._depths[chain_id] = new_depth
            return new_depth

    def depth(self, chain_id: str) -> int:
        """Current nesting depth for a chain."""
        with self._lock:
            return self._depths.get(chain_id, 0)


# ── Fan-out Rate Limiter ─────────────────────────────────────────────


@dataclass(slots=True)
class FanOutWindow:
    """Sliding window for fan-out rate tracking."""

    count: int
    window_start: float


class FanOutRateLimiter:
    """Runtime rate limiter for parallel fan-out execution.

    Distinct from compile-time DAG fan-out validation (MAX_FAN_OUT).
    This limits the RATE of parallel step launches to prevent
    cost amplification attacks.

    Spec reference §4.2: "1 request → 10,000 provider calls.
    Cost multiplier up to 10,000x."
    """

    def __init__(
        self,
        *,
        max_parallel_per_second: int = 20,
        max_parallel_per_recipe: int = 50,
        window_seconds: float = 1.0,
    ) -> None:
        self._max_per_second = max_parallel_per_second
        self._max_per_recipe = max_parallel_per_recipe
        self._window_seconds = window_seconds
        # recipe_execution_id → FanOutWindow
        self._windows: dict[str, FanOutWindow] = {}
        # recipe_execution_id → total count
        self._totals: dict[str, int] = {}
        self._lock = threading.Lock()
        self._clock = time.monotonic

    def check(self, execution_id: str) -> bool:
        """Check if a new step launch is permitted.

        Returns True if allowed, False if rate-limited.
        """
        now = self._clock()
        with self._lock:
            # Total per-recipe check
            total = self._totals.get(execution_id, 0)
            if total >= self._max_per_recipe:
                return False

            # Sliding window check
            window = self._windows.get(execution_id)
            if window is None:
                self._windows[execution_id] = FanOutWindow(count=1, window_start=now)
                self._totals[execution_id] = total + 1
                return True

            if now - window.window_start > self._window_seconds:
                # New window
                self._windows[execution_id] = FanOutWindow(count=1, window_start=now)
                self._totals[execution_id] = total + 1
                return True

            if window.count >= self._max_per_second:
                return False

            window = FanOutWindow(count=window.count + 1, window_start=window.window_start)
            self._windows[execution_id] = window
            self._totals[execution_id] = total + 1
            return True

    def release(self, execution_id: str) -> None:
        """Clean up tracking for a completed execution."""
        with self._lock:
            self._windows.pop(execution_id, None)
            self._totals.pop(execution_id, None)

    def stats(self, execution_id: str) -> dict[str, Any]:
        """Current rate limiter state for an execution."""
        with self._lock:
            window = self._windows.get(execution_id)
            return {
                "total_launched": self._totals.get(execution_id, 0),
                "max_per_recipe": self._max_per_recipe,
                "current_window_count": window.count if window else 0,
                "max_per_second": self._max_per_second,
            }


# ── Composite Safety Gate ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SafetyCheckResult:
    """Result of running all safety checks for a recipe execution."""

    passed: bool
    firewall_result: FirewallResult | None = None
    idempotency_hit: IdempotencyRecord | None = None
    nesting_depth: int = 0
    rate_limited: bool = False
    reason: str = ""


class RecipeSafetyGate:
    """Composite safety gate that runs all safety controls for a recipe execution.

    Integrates:
    1. Content firewall (step transitions)
    2. Optional legacy in-memory idempotency check (disabled by default)
    3. Nesting depth enforcement
    4. Fan-out rate limiting

    Use this as the single entry point for safety checks.
    """

    def __init__(
        self,
        *,
        firewall: ContentFirewall | None = None,
        idempotency: IdempotencyStore | None = None,
        nesting: NestingTracker | None = None,
        rate_limiter: FanOutRateLimiter | None = None,
    ) -> None:
        self.firewall = firewall or ContentFirewall()
        self.idempotency = idempotency
        self.nesting = nesting or NestingTracker()
        self.rate_limiter = rate_limiter or FanOutRateLimiter()

    def check_pre_execution(
        self,
        recipe_id: str,
        inputs: dict[str, Any],
        chain_id: str,
        execution_id: str,
        agent_id: str = "",
        idempotency_key: str | None = None,
    ) -> SafetyCheckResult:
        """Run all pre-execution safety checks.

        Returns a SafetyCheckResult. If passed=False, execution must not proceed.
        """
        # 1. Optional legacy in-memory idempotency check.
        # Live recipe execution now relies on route-level durable idempotency;
        # keep this only when a caller explicitly injects an in-memory store.
        if idempotency_key and self.idempotency is not None:
            existing = self.idempotency.check(idempotency_key)
            if existing is not None:
                return SafetyCheckResult(
                    passed=False,
                    idempotency_hit=existing,
                    reason=f"Idempotent replay: execution {existing.execution_id} already exists",
                )

        # 2. Nesting depth check
        try:
            depth = self.nesting.enter(chain_id)
        except NestingDepthError as e:
            return SafetyCheckResult(
                passed=False,
                reason=str(e),
            )

        # 3. Fan-out rate check
        if not self.rate_limiter.check(execution_id):
            self.nesting.exit(chain_id)  # Roll back nesting
            return SafetyCheckResult(
                passed=False,
                rate_limited=True,
                nesting_depth=depth,
                reason="Fan-out rate limit exceeded for this execution",
            )

        # 4. Content firewall on inputs
        fw_result = self.firewall.inspect(inputs, context="recipe_input")
        if not fw_result.passed:
            self.nesting.exit(chain_id)
            self.rate_limiter.release(execution_id)
            return SafetyCheckResult(
                passed=False,
                firewall_result=fw_result,
                nesting_depth=depth,
                reason="Content firewall blocked recipe inputs",
            )

        return SafetyCheckResult(
            passed=True,
            firewall_result=fw_result,
            nesting_depth=depth,
        )

    def check_step_transition(
        self,
        step_outputs: dict[str, Any],
        context: str = "step_transition",
    ) -> FirewallResult:
        """Run content firewall on step outputs before downstream use."""
        return self.firewall.inspect(step_outputs, context=context)

    def finalize_execution(
        self,
        chain_id: str,
        execution_id: str,
        idempotency_key: str | None,
        recipe_id: str,
        status: str,
        result_hash: str,
    ) -> None:
        """Clean up after execution completes."""
        self.nesting.exit(chain_id)
        self.rate_limiter.release(execution_id)

        if idempotency_key and self.idempotency is not None:
            self.idempotency.store(
                key=idempotency_key,
                execution_id=execution_id,
                recipe_id=recipe_id,
                status=status,
                result_hash=result_hash,
            )


# ── Module-level singletons ──────────────────────────────────────────

_safety_gate: RecipeSafetyGate | None = None


def get_safety_gate() -> RecipeSafetyGate:
    """Return the module-level safety gate singleton."""
    global _safety_gate
    if _safety_gate is None:
        _safety_gate = RecipeSafetyGate()
    return _safety_gate
