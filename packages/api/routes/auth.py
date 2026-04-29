"""Authentication routes — OAuth login, callback, session, API key issuance.

Implements the full human signup flow:
1. ``GET /auth/login/{provider}`` — redirect to GitHub/Google consent screen
2. ``GET /auth/callback/{provider}`` — exchange code for token,
   create user + agent, redirect to dashboard
3. ``GET /auth/me`` — return current user profile + API key (requires session)
4. ``POST /auth/logout`` — clear session cookie

Session is a JWT stored in an httpOnly cookie.  The JWT contains user_id,
agent_id, and email — enough to hydrate the dashboard without a DB round-trip
on every page load.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt  # PyJWT
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from config import settings
from schemas.agent_identity import api_key_prefix, get_agent_identity_store
from schemas.user import (
    EMAIL_AUTH_PROVIDER,
    EMAIL_NO_TRIAL_CREDIT_POLICY,
    EMAIL_OTP_SIGNUP_METHOD,
    OAUTH_SIGNUP_METHOD,
    OAUTH_TRIAL_CREDIT_POLICY,
    UserSchema,
    build_email_provider_id,
    get_user_store,
    has_verified_email,
)
from services.billing_bootstrap import ensure_org_billing_bootstrap
from services.email_otp import (
    EmailOTPService,
    EmailOtpRequestResult,
    derive_request_ip,
    get_email_otp_service,
)
from services.error_envelope import RhumbError
from services.service_slugs import public_service_slug
from services.stripe_billing import confirm_checkout_session_detailed, create_checkout_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_CHECKOUT_AMOUNT_USD = 5.0
MAX_CHECKOUT_AMOUNT_USD = 5000.0


class DashboardCheckoutRequest(BaseModel):
    amount_usd: float = Field(..., description="Amount in USD to add to the org balance")


class DashboardCheckoutConfirmRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Stripe Checkout Session id")


class DashboardAutoReloadRequest(BaseModel):
    enabled: bool
    threshold_usd: float | None = None
    amount_usd: float | None = None


class DashboardCreateAgentKeyRequest(BaseModel):
    """Create a secondary governed API key (new agent) for the current org."""

    name: str = Field(..., min_length=1, max_length=64, description="Agent display name")
    description: str | None = Field(default=None, max_length=240)
    budget_usd: float = Field(
        ..., gt=0, le=MAX_CHECKOUT_AMOUNT_USD, description="Budget cap in USD"
    )
    period: str = Field(
        default="monthly",
        description="Budget reset period: daily | weekly | monthly | total",
    )
    hard_limit: bool = Field(default=True, description="Block calls when budget is exhausted")
    rate_limit_qpm: int = Field(default=20, ge=1, le=1000, description="Global QPM limit")


def _public_usage_service(service_slug: Any) -> str:
    canonical = public_service_slug(service_slug)
    if canonical is not None:
        return canonical
    return str(service_slug or "")


def _public_calls_by_service(summary_services: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_service, info in (summary_services or {}).items():
        service = _public_usage_service(raw_service)
        if not service:
            continue
        calls = int(info.get("calls") or 0) if isinstance(info, dict) else 0
        counts[service] = counts.get(service, 0) + calls
    return counts

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


def _public_auth_provider(provider: str) -> str:
    """Normalize public auth provider ids for routing and error messages."""
    return str(provider).strip().lower()


def _required_oauth_callback_text(value: str, field: str) -> str:
    """Validate OAuth callback query text before opening CSRF or provider state."""
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    return text


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


def _extract_request_ip(request: Request) -> str:
    """Best-effort client IP extraction for abuse controls."""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for", ""
    )
    if forwarded:
        return derive_request_ip(forwarded)
    if request.client and request.client.host:
        return derive_request_ip(request.client.host)
    return ""


async def _email_json_object_body(request: Request) -> dict[str, Any]:
    """Return a JSON object body or reject malformed body shapes before auth state opens."""
    try:
        payload = await request.json()
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid email auth request body.",
        detail="Provide a JSON object body.",
    )


def _session_claims_for_user(user: Any) -> Dict[str, Any]:
    """Build standard session JWT claims from a hydrated user object."""
    return {
        "sub": user.user_id,
        "email": user.email,
        "agent_id": user.default_agent_id,
        "org_id": user.organization_id,
    }


def _set_session_cookie(response: Response, session_token: str) -> None:
    """Attach the standard Rhumb session cookie to a response."""
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


def _default_agent_name(*, email: str, name_hint: str = "") -> str:
    """Build a stable default agent name for auth-created users."""
    base = (name_hint or email.split("@", 1)[0] or "Rhumb").strip()
    if base.lower().endswith("agent"):
        return base
    return f"{base} Agent"


async def _ensure_default_identity(
    user: UserSchema,
    *,
    name_hint: str = "",
) -> tuple[UserSchema, Optional[str]]:
    """Ensure a user has a default org + agent, creating them when missing."""
    user_store = get_user_store()
    identity_store = get_agent_identity_store()

    updates: Dict[str, Any] = {}
    api_key_plaintext: Optional[str] = None
    org_id = user.organization_id or f"org_{secrets.token_hex(8)}"
    if not user.organization_id:
        updates["organization_id"] = org_id

    agent_id = user.default_agent_id
    if agent_id:
        existing_agent = await identity_store.get_agent(agent_id)
        if existing_agent is None:
            agent_id = ""

    if not agent_id:
        agent_id, api_key_plaintext = await identity_store.register_agent(
            name=_default_agent_name(email=user.email, name_hint=name_hint or user.name),
            organization_id=org_id,
            description=f"Default agent for {user.email}",
        )
        updates["default_agent_id"] = agent_id

    if updates:
        updated = await user_store.update_user(user.user_id, **updates)
        if updated is not None:
            user = updated
        else:
            for key, value in updates.items():
                setattr(user, key, value)

    return user, api_key_plaintext


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/login/{provider}")
async def login(provider: str) -> RedirectResponse:
    """Initiate OAuth login — redirect to provider consent screen."""
    provider_key = _public_auth_provider(provider)
    if provider_key not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_key}")

    client_id, _ = _get_client_credentials(provider_key)
    config = _PROVIDERS[provider_key]

    # Generate CSRF state
    state = secrets.token_urlsafe(32)
    _csrf_states[state] = {"provider": provider_key, "created_at": time.time()}

    # Clean expired states
    now = time.time()
    expired = [k for k, v in _csrf_states.items() if now - v["created_at"] > _CSRF_TTL_SECONDS]
    for k in expired:
        del _csrf_states[k]

    # Build the callback URL — routes through the API
    callback_url = f"{settings.auth_api_url}/v1/auth/callback/{provider_key}"

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": config["scope"],
        "state": state,
        "response_type": "code",
    }

    # Google requires additional params
    if provider_key == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    authorize_url = f"{config['authorize_url']}?{urlencode(params)}"
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/callback/{provider}")
async def callback(provider: str, code: str, state: str) -> RedirectResponse:
    """Handle OAuth callback — exchange code, create user, redirect to dashboard."""
    provider_key = _public_auth_provider(provider)
    if provider_key not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_key}")

    code = _required_oauth_callback_text(code, "code")
    state = _required_oauth_callback_text(state, "state")

    # Verify CSRF state
    stored = _csrf_states.pop(state, None)
    if stored is None or stored["provider"] != provider_key:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    if time.time() - stored["created_at"] > _CSRF_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="State token expired")

    # Exchange code for access token
    client_id, client_secret = _get_client_credentials(provider_key)
    config = _PROVIDERS[provider_key]

    callback_url = f"{settings.auth_api_url}/v1/auth/callback/{provider_key}"

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
            profile = await _fetch_user_profile(client, provider_key, access_token, config)

    except httpx.HTTPError as e:
        logger.error("OAuth exchange failed for %s: %s", provider_key, e)
        return _error_redirect(f"Authentication failed: {e}")

    if not profile.get("email"):
        return _error_redirect("Could not retrieve email from provider")

    # Find or create user
    user_store = get_user_store()
    user = await user_store.find_by_provider(provider_key, str(profile["id"]))

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
            provider=provider_key,
            provider_id=str(profile["id"]),
            avatar_url=profile.get("avatar_url", ""),
            organization_id=org_id,
            default_agent_id=agent_id,
        )
        logger.info(
            "New user created: %s (%s via %s), agent: %s",
            user.user_id, user.email, provider_key, agent_id,
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

    if user.organization_id:
        try:
            await ensure_org_billing_bootstrap(
                user.organization_id,
                email=user.email,
                name=user.name or profile.get("name") or profile["email"],
                signup_method=getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
                credit_policy=getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
            )
        except Exception as exc:
            logger.warning(
                "Billing bootstrap ensure failed for org %s during auth callback: %s",
                user.organization_id,
                exc,
            )

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
    _set_session_cookie(response, session_token)
    return response


@router.post("/email/request-code")
async def email_request_code(request: Request) -> JSONResponse:
    """Request an email OTP code.

    Always returns a generic success payload for valid-looking email input so the
    API does not leak account existence or throttling state.
    """
    payload = await _email_json_object_body(request)

    try:
        email = EmailOTPService.normalize_email(str(payload.get("email", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client_ip = _extract_request_ip(request)
    client_subnet = EmailOTPService.derive_subnet(client_ip)
    user_store = get_user_store()
    existing_user = await user_store.find_by_email(email)
    service = get_email_otp_service()
    try:
        result = await service.request_code(
            email=email,
            request_ip=client_ip,
            request_subnet=client_subnet,
            user_id=existing_user.user_id if existing_user is not None else None,
        )
    except Exception:
        logger.exception(
            "Email OTP request failed before delivery for %s (ip=%s, subnet=%s)",
            email,
            client_ip,
            client_subnet,
        )
        result = EmailOtpRequestResult(accepted=False, reason="storage_error")

    if not result.accepted:
        logger.info(
            "Email OTP request accepted generically but not delivered for %s "
            "(reason=%s, ip=%s, subnet=%s)",
            email,
            result.reason,
            client_ip,
            client_subnet,
        )

    return JSONResponse({
        "data": {
            "status": "ok",
            "message": "If the address can receive a sign-in code, it should arrive shortly.",
        },
        "error": None,
    })


@router.post("/email/verify-code")
async def email_verify_code(request: Request) -> JSONResponse:
    """Verify an email OTP code and issue a standard Rhumb session."""
    payload = await _email_json_object_body(request)

    try:
        email = EmailOTPService.normalize_email(str(payload.get("email", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    code = str(payload.get("code", "")).strip()
    device_label = str(payload.get("device_label", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="Email and code are required")

    client_ip = _extract_request_ip(request)
    client_subnet = EmailOTPService.derive_subnet(client_ip)
    otp_service = get_email_otp_service()
    verify_result = await otp_service.verify_code(email=email, code=code)
    if not verify_result.verified:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    user_store = get_user_store()
    user = await user_store.find_by_email(email)
    api_key_plaintext: Optional[str] = None
    new_user = False
    now = datetime.now(tz=UTC)

    if user is None:
        new_user = True
        identity_store = get_agent_identity_store()
        org_id = f"org_{secrets.token_hex(8)}"
        agent_id, api_key_plaintext = await identity_store.register_agent(
            name=_default_agent_name(email=email, name_hint=device_label or email),
            organization_id=org_id,
            description=f"Default agent for {email}",
        )
        user = await user_store.create_user(
            email=email,
            name=device_label or email.split("@", 1)[0],
            provider=EMAIL_AUTH_PROVIDER,
            provider_id=build_email_provider_id(email),
            organization_id=org_id,
            default_agent_id=agent_id,
            signup_method=EMAIL_OTP_SIGNUP_METHOD,
            email_verified_at=now,
            signup_ip=client_ip,
            signup_subnet=client_subnet,
            credit_policy=EMAIL_NO_TRIAL_CREDIT_POLICY,
            risk_flags={},
        )
    else:
        updates: Dict[str, Any] = {}
        if not has_verified_email(user):
            updates["email_verified_at"] = now
        if device_label and not user.name:
            updates["name"] = device_label
        if user.provider == EMAIL_AUTH_PROVIDER:
            updates.setdefault("provider_id", build_email_provider_id(email))
            updates.setdefault("signup_method", EMAIL_OTP_SIGNUP_METHOD)
            updates.setdefault("credit_policy", EMAIL_NO_TRIAL_CREDIT_POLICY)
            if client_ip and not getattr(user, "signup_ip", ""):
                updates["signup_ip"] = client_ip
            if client_subnet and not getattr(user, "signup_subnet", ""):
                updates["signup_subnet"] = client_subnet
        if updates:
            maybe_updated = await user_store.update_user(user.user_id, **updates)
            if maybe_updated is not None:
                user = maybe_updated

        user, maybe_api_key = await _ensure_default_identity(
            user,
            name_hint=device_label or user.name or email,
        )
        api_key_plaintext = api_key_plaintext or maybe_api_key

    if verify_result.code_id:
        await otp_service.attach_verified_user(verify_result.code_id, user.user_id)

    if user.organization_id:
        bootstrap_kwargs = {
            "email": user.email,
            "name": user.name or device_label or user.email,
            "signup_method": getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
            "credit_policy": getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
        }
        if (
            getattr(user, "signup_method", "") == EMAIL_OTP_SIGNUP_METHOD
            or getattr(user, "credit_policy", "") == EMAIL_NO_TRIAL_CREDIT_POLICY
        ):
            bootstrap_kwargs["starter_credits_cents"] = 0

        try:
            await ensure_org_billing_bootstrap(user.organization_id, **bootstrap_kwargs)
        except Exception as exc:
            logger.warning(
                "Billing bootstrap ensure failed for org %s during email verify: %s",
                user.organization_id,
                exc,
            )

    session_token = _issue_jwt(_session_claims_for_user(user))
    response = JSONResponse({
        "data": {
            "session_token": session_token,
            "new_user": new_user,
            "api_key": api_key_plaintext,
            "api_key_prefix": api_key_prefix(api_key_plaintext) if api_key_plaintext else None,
            "user": {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "avatar_url": user.avatar_url,
                "provider": user.provider,
                "signup_method": getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
                "credit_policy": getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
                "email_verified_at": (
                    user.email_verified_at.isoformat()
                    if getattr(user, "email_verified_at", None)
                    else None
                ),
                "organization_id": user.organization_id,
                "agent_id": user.default_agent_id,
                "created_at": (
                    user.created_at.isoformat()
                    if isinstance(user.created_at, datetime)
                    else str(user.created_at)
                ),
            },
        },
        "error": None,
    })
    _set_session_cookie(response, session_token)
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

    if user.organization_id:
        try:
            await ensure_org_billing_bootstrap(
                user.organization_id,
                email=user.email,
                name=user.name or user.email,
                signup_method=getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
                credit_policy=getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
            )
        except Exception as exc:
            logger.warning(
                "Billing bootstrap ensure failed for org %s during /auth/me: %s",
                user.organization_id,
                exc,
            )

    # Get API key prefix
    identity_store = get_agent_identity_store()
    agent = await identity_store.get_agent(user.default_agent_id) if user.default_agent_id else None

    return JSONResponse({
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "provider": user.provider,
        "signup_method": getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
        "credit_policy": getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
        "email_verified_at": (
            user.email_verified_at.isoformat()
            if getattr(user, "email_verified_at", None)
            else None
        ),
        "organization_id": user.organization_id,
        "agent_id": user.default_agent_id,
        "api_key_prefix": agent.api_key_prefix if agent else None,
        "created_at": (
            user.created_at.isoformat()
            if isinstance(user.created_at, datetime)
            else str(user.created_at)
        ),
    })


@router.post("/rotate-key")
async def rotate_key(rhumb_session: Optional[str] = Cookie(default=None)) -> JSONResponse:
    """Rotate the user's API key.  Returns the new key (shown once)."""
    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not has_verified_email(user):
        raise HTTPException(
            status_code=403,
            detail="Verify your email before rotating an API key",
        )

    agent_id = claims.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="No agent associated with this user")

    identity_store = get_agent_identity_store()
    new_key = await identity_store.rotate_api_key(agent_id)
    if new_key is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return JSONResponse({"api_key": new_key, "message": "Save this key — it won't be shown again."})


def _normalize_budget_period(period: str) -> str:
    normalized = str(period or "").strip().lower()
    if normalized in {"daily", "weekly", "monthly", "total"}:
        return normalized
    raise HTTPException(
        status_code=400,
        detail="period must be one of: daily, weekly, monthly, total",
    )


@router.get("/me/agents")
async def me_agents(
    rhumb_session: Optional[str] = Cookie(default=None),
) -> JSONResponse:
    """List governed API keys (agents) for the logged-in user's org."""
    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this user")

    identity_store = get_agent_identity_store()
    agents = await identity_store.list_agents(organization_id=org_id)

    from routes._supabase import supabase_fetch

    results: list[dict[str, Any]] = []
    for agent in agents:
        budget_row = None
        rows = await supabase_fetch(
            f"agent_budgets?agent_id=eq.{agent.agent_id}&select=budget_usd,spent_usd,period,hard_limit,alert_threshold_pct,alert_fired&limit=1"
        )
        if isinstance(rows, list) and rows:
            budget_row = rows[0]

        budget_usd = float(budget_row["budget_usd"]) if budget_row and budget_row.get("budget_usd") is not None else None
        spent_usd = float(budget_row["spent_usd"]) if budget_row and budget_row.get("spent_usd") is not None else None
        remaining_usd = (budget_usd - spent_usd) if (budget_usd is not None and spent_usd is not None) else None

        results.append({
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "status": agent.status,
            "api_key_prefix": agent.api_key_prefix,
            "rate_limit_qpm": agent.rate_limit_qpm,
            "is_default": agent.agent_id == user.default_agent_id,
            "created_at": agent.created_at.isoformat() if hasattr(agent.created_at, "isoformat") else str(agent.created_at),
            "budget": (
                {
                    "budget_usd": budget_usd,
                    "spent_usd": spent_usd,
                    "remaining_usd": remaining_usd,
                    "period": budget_row.get("period") if budget_row else None,
                    "hard_limit": budget_row.get("hard_limit") if budget_row else None,
                    "alert_threshold_pct": budget_row.get("alert_threshold_pct") if budget_row else None,
                    "alert_fired": budget_row.get("alert_fired") if budget_row else None,
                }
                if budget_row
                else None
            ),
        })

    results.sort(key=lambda item: (not item.get("is_default", False), item.get("created_at") or ""))

    return JSONResponse({"agents": results})


@router.post("/me/agents")
async def me_create_agent_key(
    body: DashboardCreateAgentKeyRequest,
    rhumb_session: Optional[str] = Cookie(default=None),
) -> JSONResponse:
    """Create a capped secondary governed key for the logged-in user's org."""
    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not has_verified_email(user):
        raise HTTPException(
            status_code=403,
            detail="Verify your email before creating additional agent keys",
        )

    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this user")

    identity_store = get_agent_identity_store()
    existing = await identity_store.list_agents(organization_id=org_id)
    if len(existing) >= 10:
        raise HTTPException(
            status_code=400,
            detail="Too many agent keys for this organization (limit 10).",
        )

    period = _normalize_budget_period(body.period)

    agent_id, api_key = await identity_store.register_agent(
        name=body.name.strip(),
        organization_id=org_id,
        rate_limit_qpm=body.rate_limit_qpm,
        description=(body.description.strip() if body.description else f"Secondary agent key created from dashboard for {user.email}"),
        tags=["secondary"],
    )

    from routes._supabase import supabase_insert_returning

    budget_row = await supabase_insert_returning(
        "agent_budgets",
        {
            "agent_id": agent_id,
            "budget_usd": float(body.budget_usd),
            "period": period,
            "hard_limit": bool(body.hard_limit),
            "alert_threshold_pct": 80,
        },
    )

    if not budget_row:
        # Fail closed: do not leave an uncapped key active.
        try:
            await identity_store.disable_agent(agent_id)
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail="Unable to persist agent budget. Please try again.",
        )

    return JSONResponse(
        {
            "agent_id": agent_id,
            "api_key": api_key,
            "api_key_prefix": api_key_prefix(api_key),
            "rate_limit_qpm": body.rate_limit_qpm,
            "budget": {
                "budget_usd": float(budget_row.get("budget_usd")) if budget_row.get("budget_usd") is not None else float(body.budget_usd),
                "spent_usd": float(budget_row.get("spent_usd")) if budget_row.get("spent_usd") is not None else 0.0,
                "period": budget_row.get("period") or period,
                "hard_limit": bool(budget_row.get("hard_limit")) if budget_row.get("hard_limit") is not None else bool(body.hard_limit),
            },
            "message": "Save this key — it won't be shown again.",
        }
    )


def _dashboard_checkout_url(kind: str) -> str:
    frontend = (settings.auth_frontend_url or "https://rhumb.dev").rstrip("/")
    if kind == "success":
        return f"{frontend}/dashboard?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    return f"{frontend}/dashboard?checkout=cancel"


def _validate_dashboard_checkout_amount(amount_usd: float, *, suffix: str = "") -> None:
    if amount_usd < MIN_CHECKOUT_AMOUNT_USD or amount_usd > MAX_CHECKOUT_AMOUNT_USD:
        raise HTTPException(
            status_code=400,
            detail=(
                f"amount_usd must be between {MIN_CHECKOUT_AMOUNT_USD:.0f} "
                f"and {MAX_CHECKOUT_AMOUNT_USD:.0f}{suffix}"
            ),
        )


@router.post("/me/billing/checkout")
async def me_billing_checkout(
    body: DashboardCheckoutRequest,
    rhumb_session: Optional[str] = Cookie(default=None),
) -> JSONResponse:
    """Create a Stripe Checkout Session for the logged-in user's org."""
    _validate_dashboard_checkout_amount(body.amount_usd)

    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this user")

    amount_cents = int(round(body.amount_usd * 100))
    result = await create_checkout_session(
        org_id=org_id,
        amount_cents=amount_cents,
        success_url=_dashboard_checkout_url("success"),
        cancel_url=_dashboard_checkout_url("cancel"),
    )
    return JSONResponse(result)


@router.post("/me/billing/checkout/confirm")
async def me_billing_checkout_confirm(
    body: DashboardCheckoutConfirmRequest,
    rhumb_session: Optional[str] = Cookie(default=None),
) -> JSONResponse:
    """Confirm a Stripe Checkout session and apply credits if webhooks are delayed.

    This provides a self-serve fallback path when webhook delivery is misconfigured
    or delayed. The session must belong to the caller's organization.
    """
    session_id = (body.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this user")

    result = await confirm_checkout_session_detailed(session_id, expected_org_id=org_id)
    return JSONResponse(result)


@router.put("/me/billing/auto-reload")
async def me_billing_auto_reload(
    body: DashboardAutoReloadRequest,
    rhumb_session: Optional[str] = Cookie(default=None),
) -> JSONResponse:
    """Update auto-reload settings for the logged-in user's org."""
    if body.enabled:
        if body.threshold_usd is None or body.threshold_usd <= 0:
            raise HTTPException(
                status_code=400,
                detail="threshold_usd must be > 0 when auto-reload is enabled",
            )
        if body.amount_usd is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"amount_usd must be between {MIN_CHECKOUT_AMOUNT_USD:.0f} "
                    f"and {MAX_CHECKOUT_AMOUNT_USD:.0f} when auto-reload is enabled"
                ),
            )
        _validate_dashboard_checkout_amount(
            body.amount_usd,
            suffix=" when auto-reload is enabled",
        )

    claims = await _require_session(rhumb_session)

    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    org_id = user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this user")

    if body.enabled:
        from routes._supabase import supabase_fetch

        rows = await supabase_fetch(
            f"org_credits?org_id=eq.{org_id}&select=stripe_payment_method_id&limit=1"
        )
        payment_method_id = rows[0].get("stripe_payment_method_id") if rows else None
        if not payment_method_id:
            raise HTTPException(
                status_code=400,
                detail="Auto-reload requires a saved payment method. Add funds once to save a card.",
            )

    from routes._supabase import supabase_patch

    payload: dict[str, Any] = {
        "auto_reload_enabled": body.enabled,
        "auto_reload_threshold_cents": (
            int(round(body.threshold_usd * 100)) if body.threshold_usd is not None else None
        ),
        "auto_reload_amount_cents": (
            int(round(body.amount_usd * 100)) if body.amount_usd is not None else None
        ),
    }

    result = await supabase_patch(f"org_credits?org_id=eq.{org_id}", payload)
    if not result:
        raise HTTPException(status_code=404, detail="Org credits not found")

    row = result[0] if isinstance(result, list) else result
    threshold_cents = row.get("auto_reload_threshold_cents")
    amount_cents = row.get("auto_reload_amount_cents")

    return JSONResponse({
        "auto_reload_enabled": bool(row.get("auto_reload_enabled", False)),
        "auto_reload_threshold_usd": (
            threshold_cents / 100 if threshold_cents is not None else None
        ),
        "auto_reload_amount_usd": (
            amount_cents / 100 if amount_cents is not None else None
        ),
    })


# ── Dashboard Data Endpoints ─────────────────────────────────────────


async def _require_session(rhumb_session: Optional[str]) -> Dict[str, Any]:
    """Verify session cookie and return JWT claims.  Raises 401 on failure."""
    if not rhumb_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = _verify_jwt(rhumb_session)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return claims


@router.get("/me/usage")
async def me_usage(rhumb_session: Optional[str] = Cookie(default=None)) -> JSONResponse:
    """Return usage stats for the logged-in user's agent."""
    claims = await _require_session(rhumb_session)
    agent_id = claims.get("agent_id")

    if not agent_id:
        return JSONResponse({
            "total_calls": 0,
            "calls_this_month": 0,
            "calls_today": 0,
            "calls_by_service": {},
            "recent_calls": [],
        })

    try:
        from services.agent_usage_analytics import get_usage_analytics

        analytics = get_usage_analytics()

        # Get 30-day summary
        summary = await analytics.get_usage_summary(agent_id, days=30)

        # Get today's summary (1-day window)
        today_summary = await analytics.get_usage_summary(agent_id, days=1)

        # Get recent events
        recent_raw = await analytics.get_recent_events(agent_id, limit=10)
        recent_calls = [
            {
                "service": _public_usage_service(e.get("service")),
                "result": e.get("result", ""),
                "latency_ms": e.get("latency_ms", 0),
                "timestamp": e.get("created_at", ""),
            }
            for e in recent_raw
        ]

        # Build per-service call counts
        calls_by_service = _public_calls_by_service(summary.get("services"))

        return JSONResponse({
            "total_calls": summary.get("total_calls", 0),
            "calls_this_month": summary.get("total_calls", 0),
            "calls_today": today_summary.get("total_calls", 0),
            "calls_by_service": calls_by_service,
            "recent_calls": recent_calls,
        })
    except Exception as exc:
        logger.warning("Dashboard usage fetch failed: %s", exc)
        return JSONResponse({
            "total_calls": 0,
            "calls_this_month": 0,
            "calls_today": 0,
            "calls_by_service": {},
            "recent_calls": [],
        })


@router.get("/me/billing")
async def me_billing(rhumb_session: Optional[str] = Cookie(default=None)) -> JSONResponse:
    """Return billing status for the logged-in user's organization."""
    claims = await _require_session(rhumb_session)

    # Get user to find org_id
    user_store = get_user_store()
    user = await user_store.get_user(claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if user.organization_id:
        try:
            await ensure_org_billing_bootstrap(
                user.organization_id,
                email=user.email,
                name=user.name or user.email,
                signup_method=getattr(user, "signup_method", OAUTH_SIGNUP_METHOD),
                credit_policy=getattr(user, "credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
            )
        except Exception as exc:
            logger.warning(
                "Billing bootstrap ensure failed for org %s during /auth/me/billing: %s",
                user.organization_id,
                exc,
            )

    org_id = user.organization_id
    if not org_id:
        return JSONResponse({
            "balance_usd": 0.0,
            "plan": "free",
            "has_payment_method": False,
            "recent_transactions": [],
        })

    try:
        from routes._supabase import supabase_fetch

        # Fetch credit balance
        rows = await supabase_fetch(
            f"org_credits?org_id=eq.{org_id}"
            f"&select=balance_usd_cents,reserved_usd_cents,"
            f"auto_reload_enabled,auto_reload_threshold_cents,auto_reload_amount_cents,"
            f"stripe_payment_method_id"
            f"&limit=1"
        )

        if rows:
            row = rows[0]
            balance_cents = row.get("balance_usd_cents", 0)
            balance_usd = balance_cents / 100
            has_payment = bool(row.get("stripe_payment_method_id"))
            auto_reload_enabled = bool(row.get("auto_reload_enabled", False))
            auto_reload_threshold_cents = row.get("auto_reload_threshold_cents")
            auto_reload_amount_cents = row.get("auto_reload_amount_cents")
        else:
            balance_usd = 0.0
            has_payment = False
            auto_reload_enabled = False
            auto_reload_threshold_cents = None
            auto_reload_amount_cents = None

        # Determine plan
        plan = "prepaid" if balance_usd > 0 else "free"

        # Fetch recent ledger entries
        ledger_rows = await supabase_fetch(
            f"credit_ledger?org_id=eq.{org_id}"
            f"&select=event_type,amount_usd_cents,description,created_at"
            f"&order=created_at.desc&limit=5"
        )

        recent_transactions = [
            {
                "type": entry.get("event_type", "unknown"),
                "amount_usd": entry.get("amount_usd_cents", 0) / 100,
                "description": entry.get("description", ""),
                "timestamp": entry.get("created_at", ""),
            }
            for entry in (ledger_rows or [])
        ]

        return JSONResponse({
            "balance_usd": balance_usd,
            "plan": plan,
            "has_payment_method": has_payment,
            "auto_reload_enabled": auto_reload_enabled,
            "auto_reload_threshold_usd": (
                auto_reload_threshold_cents / 100
                if auto_reload_threshold_cents is not None
                else None
            ),
            "auto_reload_amount_usd": (
                auto_reload_amount_cents / 100
                if auto_reload_amount_cents is not None
                else None
            ),
            "recent_transactions": recent_transactions,
        })
    except Exception as exc:
        logger.warning("Dashboard billing fetch failed: %s", exc)
        return JSONResponse({
            "balance_usd": 0.0,
            "plan": "free",
            "has_payment_method": False,
            "auto_reload_enabled": False,
            "auto_reload_threshold_usd": None,
            "auto_reload_amount_usd": None,
            "recent_transactions": [],
        })


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
