"""Thread-safe in-memory TTL cache with LRU eviction."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """In-memory cache with TTL expiry and LRU eviction."""

    def __init__(
        self,
        *,
        default_ttl: float = 60.0,
        max_size: int = 1000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if default_ttl <= 0:
            raise ValueError("default_ttl must be positive")
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.default_ttl = default_ttl
        self.max_size = max_size
        self._clock = clock or time.monotonic
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def _expiry_for(self, ttl: float | None) -> float:
        resolved_ttl = self.default_ttl if ttl is None else ttl
        if resolved_ttl <= 0:
            raise ValueError("ttl must be positive")
        return self._clock() + resolved_ttl

    def _prune_expired_locked(self) -> None:
        now = self._clock()
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)

    def _evict_if_needed_locked(self) -> None:
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)

    def get(self, key: str) -> Any | None:
        """Return a cached value if present and unexpired."""
        with self._lock:
            self._prune_expired_locked()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value with an optional per-entry TTL."""
        with self._lock:
            self._prune_expired_locked()
            self._entries[key] = _CacheEntry(value=value, expires_at=self._expiry_for(ttl))
            self._entries.move_to_end(key)
            self._evict_if_needed_locked()

    def invalidate(self, key: str) -> None:
        """Remove a single cached key."""
        with self._lock:
            self._entries.pop(key, None)

    def invalidate_pattern(self, prefix: str) -> None:
        """Remove all keys starting with a prefix."""
        with self._lock:
            matching_keys = [key for key in self._entries if key.startswith(prefix)]
            for key in matching_keys:
                self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove all cache entries."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            self._prune_expired_locked()
            return len(self._entries)


def build_cache_key(table: str, query_params: str) -> str:
    """Build a stable cache key from a table name and query string."""
    return f"{table}:{query_params}"
