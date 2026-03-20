"""Authentication routes — OAuth login, callback, session, API key issuance.

Implements the full human signup flow:
1. ``GET /auth/login/{provider}`` — redirect to GitHub/Google consent screen
2. ``GET /auth/callback/{provider}`` — exchange code for token, create user + agent, redirect to dashboard
3. ``GET /auth/me`` — return current user profile + API key (requires session)
4. ``POST /auth/logout`` — clear session cookie

Session is a JWT stored in an httpOnly cookie.  The JWT contains user_id,
agent_id, and email — enough to hydrate the dashboard without a DB round-trip
on every page load.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt  # PyJWT
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from config import settings
from schemas.agent_identity import get_agent_identity_store
from schemas.user import get_user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth Provider Config ────────────────────────────────────────────

_PROVIDERS: Dict[str, Dict[str, str]] = {
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "userinfo_email_url": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
    },
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
}

# In-memory CSRF state store (state_token → {provider, created_at})
# In production with multiple replicas, use Redis.  For single-replica
# Railway deployment this is fine.
_csrf_states: Dict[str, Dict[str, Any]] = {}
_CSRF_TTL_SECONDS = 600  # 10 minutes

# ── JWT Helpers ──────────────────────────────────────────────────────

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 168  # 7 days


def _jwt_secret() -> str:
    """Return the JWT signing secret."""
    secret = settings.auth_jwt_secret or settings.rhumb_admin_secret
    if not secret:
        raise RuntimeError("No JWT secret configured (set AUTH_JWT_SECRET or RHUMB_ADMIN_SECRET)")
    return secret


def _issue_jwt(payload: Dict[str, Any]) -> str:
    """Sign a JWT with standard claims."""
    now = time.time()
    payload.update({
        "iat": int(now),
        "exp": int(now + _JWT_EXPIRY_HOURS * 3600),
    })
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def _verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT.  Returns None on failure."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _get_client_credentials(provider: str) -> tuple[str, str]:
    """Return (client_id, client_secret) for a provider."""
    if provider == "github":
        cid = settings.github_client_id
        csecret = settings.github_client_secret
    elif provider == "google":
        cid = settings.google_client_id
        csecret = settings.google_client_secret
    else:
        raise ValueError(f"Unknown provider: {provider}")

    if not cid or not csecret:
        raise RuntimeError(f"OAuth credentials not configured for {provider}")
    return cid, csecret


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/login/{provider}")
async def login(provider: str) -> RedirectResponse:
    """Initiate OAuth login — redirect to provider consent screen."""
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    client_id, _ = _get_client_credentials(provider)
    config = _PROVIDERS[provider]

    # Generate CSRF state
    state = secrets.token_urlsafe(32)
    _csrf_states[state] = {"provider": provider, "created_at": time.time()}

    # Clean expired states
    now = time.time()
    expired = [k for k, v in _csrf_states.items() if now - v["created_at"] > _CSRF_TTL_SECONDS]
    for k in expired:
        del _csrf_states[k]

    # Build the callback URL — routes through the API
    callback_url = f"{settings.auth_api_url}/v1/auth/callback/{provider}"

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": config["scope"],
        "state": state,
        "response_type": "code",
    }

    # Google requires additional params
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    authorize_url = f"{config['authorize_url']}?{urlencode(params)}"
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/callback/{provider}")
async def callback(provider: str, code: str, state: str) -> RedirectResponse:
    """Handle OAuth callback — exchange code, create user, redirect to dashboard."""
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # Verify CSRF state
    stored = _csrf_states.pop(state, None)
    if stored is None or stored["provider"] != provider:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    if time.time() - stored["created_at"] > _CSRF_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="State token expired")

    # Exchange code for access token
    client_id, client_secret = _get_client_credentials(provider)
    config = _PROVIDERS[provider]

    callback_url = f"{settings.auth_api_url}/v1/auth/callback/{provider}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                config["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            token_data = token_response.json()

            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("No access_token in response: %s", token_data)
                return _error_redirect("Token exchange failed — no access token received")

            # Fetch user profile
            profile = await _fetch_user_profile(client, provider, access_token, config)

    except httpx.HTTPError as e:
        logger.error("OAuth exchange failed for %s: %s", provider, e)
        return _error_redirect(f"Authentication failed: {e}")

    if not profile.get("email"):
        return _error_redirect("Could not retrieve email from provider")

    # Find or create user
    user_store = get_user_store()
    user = await user_store.find_by_provider(provider, str(profile["id"]))

    api_key_plaintext: Optional[str] = None

    if user is None:
        # Also check by email (user may have signed up with a different provider)
        user = await user_store.find_by_email(profile["email"])

    if user is None:
        # New user — create user + org + agent
        identity_store = get_agent_identity_store()
        org_id = f"org_{secrets.token_hex(8)}"
        agent_id, api_key_plaintext = await identity_store.register_agent(
            name=f"{profile.get('name', profile['email'])}'s Agent",
            organization_id=org_id,
            description=f"Default agent for {profile['email']}",
        )

        user = await user_store.create_user(
            email=profile["email"],
            name=profile.get("name", ""),
            provider=provider,
            provider_id=str(profile["id"]),
            avatar_url=profile.get("avatar_url", ""),
            organization_id=org_id,
            default_agent_id=agent_id,
        )
        logger.info(
            "New user created: %s (%s via %s), agent: %s",
            user.user_id, user.email, provider, agent_id,
        )
    else:
        # Existing user — update profile if needed
        updates: Dict[str, Any] = {}
        if profile.get("name") and profile["name"] != user.name:
            updates["name"] = profile["name"]
        if profile.get("avatar_url") and profile["avatar_url"] != user.avatar_url:
            updates["avatar_url"] = profile["avatar_url"]
        if updates:
            await user_store.update_user(user.user_id, **updates)

    # Issue session JWT
    session_token = _issue_jwt({
        "sub": user.user_id,
        "email": user.email,
        "agent_id": user.default_agent_id,
        "org_id": user.organization_id,
    })

    # Redirect to dashboard
    # If this is a new signup, include a flag so the dashboard can show the API key
    redirect_params = {"session": session_token}
    if api_key_plaintext:
        # The API key is shown ONCE — encode it in the redirect URL fragment (not query)
        # so it doesn't get logged in server access logs
        redirect_url = f"{settings.auth_frontend_url}/dashboard?new=1#{api_key_plaintext}"
    else:
        redirect_url = f"{settings.auth_frontend_url}/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="rhumb_session",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_JWT_EXPIRY_HOURS * 3600,
        path="/",
        domain=".rhumb.dev",
    )
    return response


@router.get("/me")
async def me(rhumb_session: Optional[str] = Cookie(default=None)) -> JSONResponse:
    """Return current user profile.  Requires session cookie."""
    if not rhumb_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    claims = _verify_jwt(rhumb_session)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Get API key prefix
    identity_store = get_agent_identity_store()
    agent = await identity_store.get_agent(user.default_agent_id) if user.default_agent_id else None

    return JSONResponse({
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "provider": user.provider,
        "organization_id": user.organization_id,
        "agent_id": user.default_agent_id,
        "api_key_prefix": agent.api_key_prefix if agent else None,
        "created_at": user.created_at.isoformat() if isinstance(user.created_at, datetime) else str(user.created_at),
    })


@router.post("/rotate-key")
async def rotate_key(rhumb_session: Optional[str] = Cookie(default=None)) -> JSONResponse:
    """Rotate the user's API key.  Returns the new key (shown once)."""
    if not rhumb_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    claims = _verify_jwt(rhumb_session)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    agent_id = claims.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="No agent associated with this user")

    identity_store = get_agent_identity_store()
    new_key = await identity_store.rotate_api_key(agent_id)
    if new_key is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return JSONResponse({"api_key": new_key, "message": "Save this key — it won't be shown again."})


@router.post("/logout")
async def logout() -> JSONResponse:
    """Clear session cookie."""
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(
        key="rhumb_session",
        path="/",
        domain=".rhumb.dev",
    )
    return response


# ── Profile Fetchers ─────────────────────────────────────────────────


async def _fetch_user_profile(
    client: httpx.AsyncClient,
    provider: str,
    access_token: str,
    config: Dict[str, str],
) -> Dict[str, Any]:
    """Fetch user profile from OAuth provider."""
    headers = {"Authorization": f"Bearer {access_token}"}

    if provider == "github":
        return await _fetch_github_profile(client, access_token, config)
    elif provider == "google":
        return await _fetch_google_profile(client, access_token, config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _fetch_github_profile(
    client: httpx.AsyncClient,
    access_token: str,
    config: Dict[str, str],
) -> Dict[str, Any]:
    """Fetch GitHub user profile + primary email."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    # Get profile
    resp = await client.get(config["userinfo_url"], headers=headers)
    resp.raise_for_status()
    profile = resp.json()

    # GitHub may not include email in profile — fetch from emails endpoint
    if not profile.get("email"):
        email_resp = await client.get(config["userinfo_email_url"], headers=headers)
        email_resp.raise_for_status()
        emails = email_resp.json()
        # Find primary verified email
        for e in emails:
            if e.get("primary") and e.get("verified"):
                profile["email"] = e["email"]
                break
        # Fallback: first verified email
        if not profile.get("email"):
            for e in emails:
                if e.get("verified"):
                    profile["email"] = e["email"]
                    break

    return {
        "id": str(profile.get("id", "")),
        "email": profile.get("email", ""),
        "name": profile.get("name") or profile.get("login", ""),
        "avatar_url": profile.get("avatar_url", ""),
    }


async def _fetch_google_profile(
    client: httpx.AsyncClient,
    access_token: str,
    config: Dict[str, str],
) -> Dict[str, Any]:
    """Fetch Google user profile."""
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = await client.get(config["userinfo_url"], headers=headers)
    resp.raise_for_status()
    profile = resp.json()

    return {
        "id": str(profile.get("id", "")),
        "email": profile.get("email", ""),
        "name": profile.get("name", ""),
        "avatar_url": profile.get("picture", ""),
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _error_redirect(message: str) -> RedirectResponse:
    """Redirect to frontend with an error message."""
    from urllib.parse import quote_plus
    return RedirectResponse(
        url=f"{settings.auth_frontend_url}/auth/login?error={quote_plus(message)}",
        status_code=302,
    )
