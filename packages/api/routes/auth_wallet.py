"""Wallet authentication routes — challenge/verify for pseudonymous wallet identity.

Implements the wallet-linked identity flow (DF-16 / WU-W2):
1. ``POST /auth/wallet/request-challenge`` — generate a signable nonce message
2. ``POST /auth/wallet/verify`` — verify signature, create/load identity, issue session
3. ``GET /auth/wallet/me`` — return wallet identity + balance (requires wallet session)

Wallet sessions are distinct from human ``rhumb_session`` cookies:
- Issued as JWT with ``subject_type: wallet_identity``
- Passed via ``Authorization: Bearer <token>`` header
- Do NOT overload ``/auth/me`` or the dashboard session contract

On first verification, creates:
- ``wallet_identities`` row
- linked org (via ``ensure_org_billing_bootstrap`` with 0 starter credits)
- default agent (via ``AgentIdentityStore.register_agent``)
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import jwt as pyjwt
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from routes._supabase import supabase_fetch, supabase_insert, supabase_insert_returning, supabase_patch
from schemas.agent_identity import api_key_prefix, get_agent_identity_store
from services.billing_bootstrap import ensure_org_billing_bootstrap
from services.wallet_auth import (
    CHALLENGE_TTL_SECONDS,
    build_challenge_message,
    derive_subnet,
    get_challenge_throttle,
    normalize_address,
    validate_chain,
    verify_challenge_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/wallet", tags=["wallet-auth"])

# ── JWT Helpers (wallet-scoped) ──────────────────────────────────────

_JWT_ALGORITHM = "HS256"
_WALLET_JWT_EXPIRY_HOURS = 24  # shorter than human sessions (168h)


def _jwt_secret() -> str:
    secret = settings.auth_jwt_secret or settings.rhumb_admin_secret
    if not secret:
        raise RuntimeError("No JWT secret configured (set AUTH_JWT_SECRET or RHUMB_ADMIN_SECRET)")
    return secret


def _issue_wallet_jwt(claims: dict[str, Any]) -> str:
    """Sign a wallet-scoped JWT with standard claims."""
    now = time.time()
    claims.update({
        "subject_type": "wallet_identity",
        "iat": int(now),
        "exp": int(now + _WALLET_JWT_EXPIRY_HOURS * 3600),
    })
    return pyjwt.encode(claims, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def _verify_wallet_jwt(token: str) -> Optional[dict[str, Any]]:
    """Verify and decode a wallet-scoped JWT. Returns None on failure."""
    try:
        claims = pyjwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
        if claims.get("subject_type") != "wallet_identity":
            return None
        return claims
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None


def _extract_request_ip(request: Request) -> str:
    """Best-effort client IP extraction."""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for", ""
    )
    if forwarded:
        # Take the first IP from x-forwarded-for
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


async def _require_wallet_session(
    authorization: Optional[str],
) -> dict[str, Any]:
    """Verify wallet session from Authorization header. Raises 401 on failure."""
    normalized_authorization = str(authorization or "").strip()
    if not normalized_authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = normalized_authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format (expected: Bearer <token>)")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization format (expected: Bearer <token>)")
    claims = _verify_wallet_jwt(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired wallet session")
    return claims


# ── Routes ───────────────────────────────────────────────────────────


async def _json_object_body(request: Request) -> dict[str, Any]:
    """Return a JSON object body or reject before route state is opened."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON object body")
    return payload


def _required_text_field(payload: dict[str, Any], field: str) -> str:
    """Validate a required text field before lookup/auth state opens."""
    value = payload.get(field)
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="challenge_id and signature are required")
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="challenge_id and signature are required")
    return normalized


def _request_challenge_text_field(
    payload: dict[str, Any], field: str, *, default: str
) -> str:
    """Validate request-challenge scalar fields before throttle or writes open."""
    if field not in payload:
        return default
    value = payload.get(field)
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field} must be a string")
    return value.strip()


@router.post("/request-challenge")
async def request_challenge(request: Request) -> JSONResponse:
    """Generate a signable challenge for wallet authentication.

    Input:
        ``{"chain": "base", "address": "0x...", "purpose": "access"}``

    Returns a nonce message for the wallet to sign via ``personal_sign``.
    """
    payload = await _json_object_body(request)

    # Validate inputs
    raw_chain = _request_challenge_text_field(payload, "chain", default="base")
    raw_address = _request_challenge_text_field(payload, "address", default="")
    purpose = _request_challenge_text_field(payload, "purpose", default="access")

    if purpose not in ("access", "topup", "link", "rotate_key"):
        raise HTTPException(status_code=400, detail=f"Invalid purpose: {purpose}")

    try:
        chain = validate_chain(raw_chain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        address_normalized = normalize_address(raw_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Throttle
    client_ip = _extract_request_ip(request)
    throttle = get_challenge_throttle()
    if not throttle.check_and_record(address_normalized, client_ip):
        raise HTTPException(status_code=429, detail="Too many challenge requests. Try again later.")

    # Generate challenge
    nonce = secrets.token_hex(CHALLENGE_TTL_SECONDS // 10)  # ~32 bytes
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(seconds=CHALLENGE_TTL_SECONDS)

    message = build_challenge_message(
        chain=chain,
        address=raw_address,  # preserve original case in display message
        nonce=nonce,
        purpose=purpose,
        expires_at=expires_at,
    )

    client_subnet = derive_subnet(client_ip)

    # Store challenge
    challenge_row = {
        "chain": chain,
        "address": raw_address,
        "address_normalized": address_normalized,
        "purpose": purpose,
        "nonce": nonce,
        "message": message,
        "expires_at": expires_at.isoformat(),
        "request_ip": client_ip,
        "request_subnet": client_subnet,
    }

    stored = await supabase_insert_returning("wallet_auth_challenges", challenge_row)
    if stored is None:
        logger.error("Failed to store wallet auth challenge for %s", address_normalized)
        raise HTTPException(status_code=500, detail="Failed to create challenge")

    challenge_id = stored.get("id", "")

    return JSONResponse({
        "data": {
            "challenge_id": challenge_id,
            "chain": chain,
            "address": raw_address,
            "message": message,
            "expires_at": expires_at.isoformat(),
        },
        "error": None,
    })


@router.post("/verify")
async def verify(request: Request) -> JSONResponse:
    """Verify a signed challenge and issue a wallet session.

    Input:
        ``{"challenge_id": "...", "signature": "0x..."}``

    On first verification for a new wallet:
    - Creates wallet_identity + linked org + default agent
    - Returns the API key (shown once)

    On repeat verification:
    - Returns session token + api_key_prefix only
    """
    payload = await _json_object_body(request)

    challenge_id = _required_text_field(payload, "challenge_id")
    signature = _required_text_field(payload, "signature")

    # Load the challenge
    challenges = await supabase_fetch(
        f"wallet_auth_challenges?id=eq.{challenge_id}"
        f"&used_at=is.null"
        f"&select=*"
        f"&limit=1"
    )

    if not challenges:
        raise HTTPException(status_code=400, detail="Challenge not found or already used")

    challenge = challenges[0]

    # Check expiry
    expires_at_str = challenge.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Challenge has invalid expiry")

    if datetime.now(tz=UTC) >= expires_at:
        raise HTTPException(status_code=400, detail="Challenge expired")

    # Verify signature
    message = challenge["message"]
    expected_address = challenge["address_normalized"]
    result = verify_challenge_signature(message, signature, expected_address)

    if not result["valid"]:
        raise HTTPException(status_code=400, detail=f"Signature verification failed: {result['error']}")

    # Mark challenge as used
    await supabase_patch(
        f"wallet_auth_challenges?id=eq.{challenge_id}",
        {"used_at": datetime.now(tz=UTC).isoformat()},
    )

    chain = challenge["chain"]
    address = challenge["address"]
    address_normalized = challenge["address_normalized"]
    client_ip = _extract_request_ip(request)
    client_subnet = derive_subnet(client_ip)

    # Find or create wallet identity
    existing = await supabase_fetch(
        f"wallet_identities?chain=eq.{chain}"
        f"&address_normalized=eq.{address_normalized}"
        f"&select=*"
        f"&limit=1"
    )

    new_wallet_identity = False
    api_key_plaintext: Optional[str] = None

    if existing:
        # Existing wallet — refresh verification timestamps
        wallet = existing[0]
        await supabase_patch(
            f"wallet_identities?id=eq.{wallet['id']}",
            {
                "last_verified_at": datetime.now(tz=UTC).isoformat(),
                "last_verified_ip": client_ip,
                "last_verified_subnet": client_subnet,
            },
        )
        org_id = wallet["org_id"]
        agent_id = wallet["default_agent_id"]
        wallet_id = wallet["id"]
    else:
        # New wallet — create org + agent + wallet identity
        new_wallet_identity = True
        org_id = f"org_{secrets.token_hex(8)}"

        # Create agent
        identity_store = get_agent_identity_store()
        short_addr = address[:6] + "..." + address[-4:]
        agent_id, api_key_plaintext = await identity_store.register_agent(
            name=f"Wallet {short_addr} Agent",
            organization_id=org_id,
            description=f"Default agent for wallet {address} on {chain}",
        )

        # Bootstrap org + billing with ZERO starter credits
        try:
            await ensure_org_billing_bootstrap(
                org_id,
                name=f"Wallet {short_addr}",
                starter_credits_cents=0,
                signup_method="wallet_auth",
                credit_policy="wallet_no_trial",
            )
        except Exception as exc:
            logger.warning(
                "Billing bootstrap failed for wallet org %s: %s", org_id, exc
            )

        # Create wallet identity row
        wallet_row = {
            "chain": chain,
            "address": address,
            "address_normalized": address_normalized,
            "org_id": org_id,
            "default_agent_id": agent_id,
            "status": "active",
            "auth_method": "personal_sign",
            "last_verified_at": datetime.now(tz=UTC).isoformat(),
            "last_verified_ip": client_ip,
            "last_verified_subnet": client_subnet,
        }

        stored_wallet = await supabase_insert_returning("wallet_identities", wallet_row)
        if stored_wallet is None:
            logger.error("Failed to store wallet identity for %s", address_normalized)
            raise HTTPException(status_code=500, detail="Failed to create wallet identity")

        wallet_id = stored_wallet["id"]

    # Issue wallet-scoped session token
    session_token = _issue_wallet_jwt({
        "wallet_identity_id": wallet_id,
        "wallet_address": address_normalized,
        "chain": chain,
        "org_id": org_id,
        "agent_id": agent_id,
        "purpose": "wallet_access",
    })

    # Build response
    response_data: dict[str, Any] = {
        "wallet_session_token": session_token,
        "new_wallet_identity": new_wallet_identity,
        "wallet": {
            "chain": chain,
            "address": address,
            "org_id": org_id,
            "agent_id": agent_id,
        },
    }

    if api_key_plaintext:
        response_data["api_key"] = api_key_plaintext
        response_data["api_key_prefix"] = api_key_prefix(api_key_plaintext)
    else:
        # Return prefix for existing wallets
        identity_store = get_agent_identity_store()
        agent = await identity_store.get_agent(agent_id)
        response_data["api_key"] = None
        response_data["api_key_prefix"] = agent.api_key_prefix if agent else None

    return JSONResponse({
        "data": response_data,
        "error": None,
    })


@router.get("/me")
async def wallet_me(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Return wallet identity summary + balance. Requires wallet session."""
    claims = await _require_wallet_session(authorization)

    wallet_id = claims.get("wallet_identity_id")
    org_id = claims.get("org_id")
    agent_id = claims.get("agent_id")

    # Fetch wallet identity
    wallets = await supabase_fetch(
        f"wallet_identities?id=eq.{wallet_id}&select=*&limit=1"
    )
    wallet = wallets[0] if wallets else None

    # Fetch balance
    balance_usd_cents = 0
    credits = await supabase_fetch(
        f"org_credits?org_id=eq.{org_id}&select=balance_usd_cents&limit=1"
    )
    if credits:
        balance_usd_cents = credits[0].get("balance_usd_cents", 0)

    # Fetch API key prefix
    identity_store = get_agent_identity_store()
    agent = await identity_store.get_agent(agent_id) if agent_id else None

    return JSONResponse({
        "data": {
            "wallet_identity_id": wallet_id,
            "chain": claims.get("chain", "base"),
            "address": claims.get("wallet_address", ""),
            "org_id": org_id,
            "agent_id": agent_id,
            "status": wallet["status"] if wallet else "unknown",
            "linked_user_id": wallet.get("linked_user_id") if wallet else None,
            "balance_usd_cents": balance_usd_cents,
            "balance_usd": balance_usd_cents / 100,
            "api_key_prefix": agent.api_key_prefix if agent else None,
            "first_seen_at": wallet.get("first_seen_at") if wallet else None,
            "last_verified_at": wallet.get("last_verified_at") if wallet else None,
        },
        "error": None,
    })


@router.post("/rotate-key")
async def wallet_rotate_key(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Rotate the default agent's API key. Requires wallet session.

    Returns the new key (shown once).
    """
    claims = await _require_wallet_session(authorization)
    agent_id = claims.get("agent_id")

    if not agent_id:
        raise HTTPException(status_code=400, detail="No agent associated with this wallet")

    identity_store = get_agent_identity_store()
    new_key = await identity_store.rotate_api_key(agent_id)
    if new_key is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return JSONResponse({
        "data": {
            "api_key": new_key,
            "message": "Save this key — it won't be shown again.",
        },
        "error": None,
    })
