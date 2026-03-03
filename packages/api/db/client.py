"""Supabase client helpers."""

from typing import Any

from supabase import acreate_client

from config import settings


async def get_supabase_client() -> Any:
    """Create an async Supabase client instance."""
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
