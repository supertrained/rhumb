"""Durable storage for the currently supported Resolve v2 account policy subset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from routes._supabase import supabase_fetch, supabase_insert_returning, supabase_patch

_POLICY_TABLE = "resolve_account_policies"


@dataclass
class StoredResolvePolicy:
    """Persisted organization-level Resolve policy subset."""

    org_id: str
    pin: str | None
    provider_preference: list[str]
    provider_deny: list[str]
    allow_only: list[str]
    max_cost_usd: float | None
    created_at: str | None = None
    updated_at: str | None = None


class ResolvePolicyStore:
    """Read/write the honest v2 policy subset keyed by organization."""

    async def get_policy(self, org_id: str) -> StoredResolvePolicy | None:
        rows = await supabase_fetch(
            f"{_POLICY_TABLE}?org_id=eq.{quote(org_id, safe='')}&select=*"
        )
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            return None
        return self._row_to_policy(row)

    async def put_policy(
        self,
        org_id: str,
        *,
        pin: str | None,
        provider_preference: list[str],
        provider_deny: list[str],
        allow_only: list[str],
        max_cost_usd: float | None,
    ) -> StoredResolvePolicy | None:
        payload = {
            "org_id": org_id,
            "pin": self._normalize_slug(pin),
            "provider_preference": self._normalize_slug_list(provider_preference),
            "provider_deny": self._normalize_slug_list(provider_deny),
            "allow_only": self._normalize_slug_list(allow_only),
            "max_cost_usd": float(max_cost_usd) if max_cost_usd is not None else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = await self.get_policy(org_id)
        if existing is None:
            row = await supabase_insert_returning(_POLICY_TABLE, payload)
            if not isinstance(row, dict):
                return None
            return self._row_to_policy(row)

        rows = await supabase_patch(
            f"{_POLICY_TABLE}?org_id=eq.{quote(org_id, safe='')}",
            payload,
        )
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return self._row_to_policy(rows[0])

        merged_row = {
            "org_id": org_id,
            "pin": payload["pin"],
            "provider_preference": payload["provider_preference"],
            "provider_deny": payload["provider_deny"],
            "allow_only": payload["allow_only"],
            "max_cost_usd": payload["max_cost_usd"],
            "created_at": existing.created_at,
            "updated_at": payload["updated_at"],
        }
        return self._row_to_policy(merged_row)

    @staticmethod
    def _normalize_slug(value: Any) -> str | None:
        if value is None:
            return None
        slug = str(value).strip().lower()
        return slug or None

    def _normalize_slug_list(self, values: list[Any] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            slug = self._normalize_slug(value)
            if not slug or slug in seen:
                continue
            normalized.append(slug)
            seen.add(slug)
        return normalized

    def _row_to_policy(self, row: dict[str, Any]) -> StoredResolvePolicy:
        return StoredResolvePolicy(
            org_id=str(row.get("org_id") or ""),
            pin=self._normalize_slug(row.get("pin")),
            provider_preference=self._normalize_slug_list(row.get("provider_preference")),
            provider_deny=self._normalize_slug_list(row.get("provider_deny")),
            allow_only=self._normalize_slug_list(row.get("allow_only")),
            max_cost_usd=(
                float(row["max_cost_usd"])
                if row.get("max_cost_usd") is not None
                else None
            ),
            created_at=(str(row.get("created_at")) if row.get("created_at") else None),
            updated_at=(str(row.get("updated_at")) if row.get("updated_at") else None),
        )


_resolve_policy_store: ResolvePolicyStore | None = None


def get_resolve_policy_store() -> ResolvePolicyStore:
    global _resolve_policy_store
    if _resolve_policy_store is None:
        _resolve_policy_store = ResolvePolicyStore()
    return _resolve_policy_store
