#!/usr/bin/env python3
"""Repeatable wallet-prefund dogfood harness for Rhumb.

This script proves the honest repeatable wallet rail that is live today:

1. Request a wallet auth challenge
2. Verify the challenge with a local EOA private key
3. Request a wallet top-up payment envelope
4. Sign a standard EIP-3009 authorization proof
5. Verify the top-up and credit org balance
6. Optionally execute a paid capability via ``X-Rhumb-Key``

Honest boundary:
- This harness is for EOAs / exportable private keys.
- It is *not* a workaround for wrapped / smart-wallet x402 interop issues.
- If you want to prove the public, repeatable dogfood rail today, use a funded
  Base EOA and this script.

Examples:
  export RHUMB_DOGFOOD_WALLET_PRIVATE_KEY=0x...
  python3 scripts/wallet_prefund_dogfood.py --json
  python3 scripts/wallet_prefund_dogfood.py --rotate-key-if-missing
  python3 scripts/wallet_prefund_dogfood.py --skip-execute --topup-cents 25
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

DEFAULT_BASE_URL = "https://api.rhumb.dev/v1"
DEFAULT_PRIVATE_KEY_ENV = "RHUMB_DOGFOOD_WALLET_PRIVATE_KEY"
DEFAULT_TIMEOUT = 30.0
DEFAULT_TOPUP_CENTS = 50
DEFAULT_EXECUTE_CAPABILITY = "search.query"
DEFAULT_EXECUTE_PROVIDER = "brave-search-api"
DEFAULT_EXECUTE_CREDENTIAL_MODE = "rhumb_managed"
DEFAULT_EXECUTE_PARAMS = {
    "query": "rhumb wallet prefund dogfood smoke test",
    "numResults": 3,
}
DEFAULT_EXECUTE_INTERFACE = "dogfood"

TRANSFER_WITH_AUTHORIZATION_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}

NETWORK_CONFIG = {
    "base": {
        "chainId": 8453,
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
    "base-sepolia": {
        "chainId": 84532,
        "usdc": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    },
}


class FlowError(RuntimeError):
    def __init__(self, message: str, state: dict[str, Any]):
        super().__init__(message)
        self.state = json.loads(json.dumps(state, default=str))


def _normalize_private_key(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("Private key is empty")
    return raw if raw.startswith("0x") else f"0x{raw}"


def _get_private_key(env_name: str) -> str:
    raw = os.environ.get(env_name, "")
    if not raw.strip():
        raise RuntimeError(
            f"Missing wallet private key. Set the {env_name} environment variable."
        )
    return _normalize_private_key(raw)


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    body_bytes = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "rhumb-wallet-prefund-dogfood/0.1",
    }
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(url, data=body_bytes, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            status = response.getcode()
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        text = exc.read().decode("utf-8") if exc.fp else ""
        status = exc.code
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc

    parsed: dict[str, Any] | list[Any] | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

    return {
        "url": url,
        "status": status,
        "json": parsed,
        "text": text,
        "headers": response_headers,
    }


def _extract_error_detail(response: dict[str, Any]) -> str:
    payload = response.get("json")
    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("detail", "error", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    text = (response.get("text") or "").strip()
    return text or f"HTTP {response.get('status')}"


def _expect_success(label: str, response: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if 200 <= int(response.get("status") or 0) < 300:
        return response
    detail = _extract_error_detail(response)
    state["last_error_response"] = {
        "label": label,
        "status": response.get("status"),
        "detail": detail,
        "url": response.get("url"),
    }
    raise FlowError(f"{label} failed: {detail}", state)


def _mask_secret(value: str | None, *, head: int = 10, tail: int = 4) -> str | None:
    if value is None:
        return None
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}…{value[-tail:]}"


def _sign_challenge_message(private_key: str, message: str) -> str:
    signed = Account.sign_message(encode_defunct(text=message), private_key=private_key)
    return "0x" + signed.signature.hex()


def build_signed_authorization(
    *,
    private_key: str,
    network: str,
    pay_to: str,
    amount_atomic: str | int,
    validity_seconds: int = 3600,
    valid_after: int = 0,
    nonce: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Build and sign a standard USDC EIP-3009 authorization proof."""
    if network not in NETWORK_CONFIG:
        raise ValueError(f"Unsupported network for dogfood harness: {network}")

    normalized_key = _normalize_private_key(private_key)
    account = Account.from_key(normalized_key)
    config = NETWORK_CONFIG[network]
    now = int(time.time())

    authorization = {
        "from": account.address,
        "to": pay_to,
        "value": str(amount_atomic),
        "validAfter": str(valid_after),
        "validBefore": str(now + validity_seconds),
        "nonce": nonce or ("0x" + secrets.token_hex(32)),
    }

    nonce_bytes = bytes.fromhex(authorization["nonce"].replace("0x", "").ljust(64, "0"))
    signable = encode_typed_data(
        domain_data={
            "name": "USD Coin",
            "version": "2",
            "chainId": config["chainId"],
            "verifyingContract": config["usdc"],
        },
        message_types=TRANSFER_WITH_AUTHORIZATION_TYPES,
        message_data={
            "from": authorization["from"],
            "to": authorization["to"],
            "value": int(str(authorization["value"]), 0),
            "validAfter": int(str(authorization["validAfter"]), 0),
            "validBefore": int(str(authorization["validBefore"]), 0),
            "nonce": nonce_bytes,
        },
    )
    signed = account.sign_message(signable)
    signature = "0x" + signed.signature.hex()
    return authorization, signature


def _select_exact_option(x402_body: dict[str, Any]) -> dict[str, Any]:
    accepts = x402_body.get("accepts") or []
    for option in accepts:
        if isinstance(option, dict) and option.get("scheme") == "exact":
            return option
    raise ValueError("No exact x402 payment option found in top-up response")


def _json_or_default(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if not raw.strip():
        return dict(fallback)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    private_key = _get_private_key(args.private_key_env)
    account = Account.from_key(private_key)
    execute_params = _json_or_default(args.execute_params_json, DEFAULT_EXECUTE_PARAMS)

    state: dict[str, Any] = {
        "base_url": base_url,
        "wallet": {
            "address": account.address,
            "private_key_env": args.private_key_env,
        },
        "topup_cents": args.topup_cents,
        "execute_requested": not args.skip_execute,
    }

    challenge_resp = _expect_success(
        "wallet challenge",
        _http_json(
            "POST",
            f"{base_url}/auth/wallet/request-challenge",
            payload={
                "chain": args.chain,
                "address": account.address,
                "purpose": "access",
            },
            timeout=args.timeout,
        ),
        state,
    )
    challenge_data = (challenge_resp.get("json") or {}).get("data") or {}
    state["challenge"] = {
        "challenge_id": challenge_data.get("challenge_id"),
        "chain": challenge_data.get("chain"),
        "expires_at": challenge_data.get("expires_at"),
    }

    verify_resp = _expect_success(
        "wallet verify",
        _http_json(
            "POST",
            f"{base_url}/auth/wallet/verify",
            payload={
                "challenge_id": challenge_data.get("challenge_id"),
                "signature": _sign_challenge_message(private_key, challenge_data.get("message", "")),
            },
            timeout=args.timeout,
        ),
        state,
    )
    verify_data = (verify_resp.get("json") or {}).get("data") or {}
    wallet_session_token = verify_data.get("wallet_session_token") or ""
    if not wallet_session_token:
        raise FlowError("wallet verify succeeded but did not return a wallet_session_token", state)

    state["wallet"].update(
        {
            "new_wallet_identity": bool(verify_data.get("new_wallet_identity")),
            "org_id": (verify_data.get("wallet") or {}).get("org_id"),
            "agent_id": (verify_data.get("wallet") or {}).get("agent_id"),
            "api_key_prefix": verify_data.get("api_key_prefix"),
            "wallet_session_token_preview": _mask_secret(wallet_session_token),
        }
    )

    wallet_headers = {"Authorization": f"Bearer {wallet_session_token}"}
    balance_before_resp = _expect_success(
        "wallet balance (before top-up)",
        _http_json("GET", f"{base_url}/auth/wallet/balance", headers=wallet_headers, timeout=args.timeout),
        state,
    )
    state["balance_before_topup"] = (balance_before_resp.get("json") or {}).get("data") or {}

    api_key_plaintext = verify_data.get("api_key")
    if not api_key_plaintext and args.rotate_key_if_missing and not args.skip_execute:
        rotate_resp = _expect_success(
            "wallet rotate-key",
            _http_json(
                "POST",
                f"{base_url}/auth/wallet/rotate-key",
                payload={},
                headers=wallet_headers,
                timeout=args.timeout,
            ),
            state,
        )
        rotate_data = (rotate_resp.get("json") or {}).get("data") or {}
        api_key_plaintext = rotate_data.get("api_key")
        state["wallet"]["api_key_rotated"] = bool(api_key_plaintext)
        state["wallet"]["api_key_prefix"] = _mask_secret(api_key_plaintext, head=12, tail=0) if api_key_plaintext else state["wallet"].get("api_key_prefix")
    else:
        state["wallet"]["api_key_rotated"] = False

    topup_request_resp = _expect_success(
        "top-up request",
        _http_json(
            "POST",
            f"{base_url}/auth/wallet/topup/request",
            payload={"amount_usd_cents": args.topup_cents},
            headers=wallet_headers,
            timeout=args.timeout,
        ),
        state,
    )
    topup_request_data = (topup_request_resp.get("json") or {}).get("data") or {}
    exact_option = _select_exact_option(topup_request_data.get("x402") or {})
    state["topup_request"] = {
        "payment_request_id": topup_request_data.get("payment_request_id"),
        "amount_usd_cents": topup_request_data.get("amount_usd_cents"),
        "amount_usd": topup_request_data.get("amount_usd"),
        "network": exact_option.get("network"),
        "pay_to": exact_option.get("payTo"),
        "amount_atomic": exact_option.get("maxAmountRequired") or exact_option.get("amount"),
    }

    authorization, proof_signature = build_signed_authorization(
        private_key=private_key,
        network=str(exact_option.get("network") or ""),
        pay_to=str(exact_option.get("payTo") or ""),
        amount_atomic=str(exact_option.get("maxAmountRequired") or exact_option.get("amount") or "0"),
        validity_seconds=args.validity_seconds,
        valid_after=args.valid_after,
    )
    state["proof"] = {
        "network": exact_option.get("network"),
        "payer": authorization.get("from"),
        "pay_to": authorization.get("to"),
        "value_atomic": authorization.get("value"),
        "valid_before": authorization.get("validBefore"),
        "nonce": authorization.get("nonce"),
        "signature_preview": _mask_secret(proof_signature, head=16, tail=6),
    }

    topup_verify_resp = _expect_success(
        "top-up verify",
        _http_json(
            "POST",
            f"{base_url}/auth/wallet/topup/verify",
            payload={
                "payment_request_id": topup_request_data.get("payment_request_id"),
                "x_payment": {
                    "x402Version": 1,
                    "scheme": "exact",
                    "network": exact_option.get("network"),
                    "payload": {
                        "authorization": authorization,
                        "signature": proof_signature,
                    },
                },
            },
            headers=wallet_headers,
            timeout=args.timeout,
        ),
        state,
    )
    state["topup_verify"] = (topup_verify_resp.get("json") or {}).get("data") or {}

    balance_after_topup_resp = _expect_success(
        "wallet balance (after top-up)",
        _http_json("GET", f"{base_url}/auth/wallet/balance", headers=wallet_headers, timeout=args.timeout),
        state,
    )
    state["balance_after_topup"] = (balance_after_topup_resp.get("json") or {}).get("data") or {}

    if args.skip_execute:
        state["execute"] = {"skipped": True, "reason": "--skip-execute"}
    elif not api_key_plaintext:
        state["execute"] = {
            "skipped": True,
            "reason": (
                "wallet verify did not return a plaintext API key. Rerun with "
                "--rotate-key-if-missing or use a newly created wallet identity."
            ),
        }
        raise FlowError(state["execute"]["reason"], state)
    else:
        estimate_url = (
            f"{base_url}/capabilities/{quote(args.execute_capability, safe='')}/execute/estimate"
            f"?provider={quote(args.execute_provider, safe='')}"
            f"&credential_mode={quote(args.execute_credential_mode, safe='')}"
        )
        estimate_resp = _http_json(
            "GET",
            estimate_url,
            headers={"X-Rhumb-Key": api_key_plaintext},
            timeout=args.timeout,
        )
        state["execute_estimate"] = {
            "status": estimate_resp.get("status"),
            "body": estimate_resp.get("json") or estimate_resp.get("text"),
        }

        execute_payload = {
            "provider": args.execute_provider,
            "credential_mode": args.execute_credential_mode,
            "params": execute_params,
            "interface": args.execute_interface,
        }
        execute_resp = _expect_success(
            "capability execute",
            _http_json(
                "POST",
                f"{base_url}/capabilities/{quote(args.execute_capability, safe='')}/execute",
                payload=execute_payload,
                headers={"X-Rhumb-Key": api_key_plaintext},
                timeout=args.timeout,
            ),
            state,
        )
        state["execute"] = {
            "skipped": False,
            "capability": args.execute_capability,
            "provider": args.execute_provider,
            "credential_mode": args.execute_credential_mode,
            "request": execute_payload,
            "response": (execute_resp.get("json") or {}).get("data") or execute_resp.get("json") or execute_resp.get("text"),
        }

        balance_after_execute_resp = _expect_success(
            "wallet balance (after execute)",
            _http_json("GET", f"{base_url}/auth/wallet/balance", headers=wallet_headers, timeout=args.timeout),
            state,
        )
        state["balance_after_execute"] = (balance_after_execute_resp.get("json") or {}).get("data") or {}

    summary_parts = [
        f"Authenticated {account.address}",
        f"credited ${args.topup_cents / 100:.2f}",
    ]
    execute_state = state.get("execute") or {}
    if execute_state.get("skipped"):
        summary_parts.append("execute skipped")
    else:
        execution_id = ((execute_state.get("response") or {}).get("execution_id") if isinstance(execute_state.get("response"), dict) else None)
        summary_parts.append(f"executed {args.execute_capability}")
        if execution_id:
            summary_parts.append(f"execution_id={execution_id}")
    state["ok"] = True
    state["summary"] = "; ".join(summary_parts)
    return state


def _print_human(payload: dict[str, Any]) -> None:
    print(payload.get("summary") or ("OK" if payload.get("ok") else "FAILED"))
    print()
    wallet = payload.get("wallet") or {}
    print("Wallet")
    print(f"- address: {wallet.get('address')}")
    print(f"- org_id: {wallet.get('org_id')}")
    print(f"- agent_id: {wallet.get('agent_id')}")
    print(f"- new_wallet_identity: {wallet.get('new_wallet_identity')}")
    print(f"- api_key_prefix: {wallet.get('api_key_prefix')}")
    print(f"- api_key_rotated: {wallet.get('api_key_rotated')}")

    challenge = payload.get("challenge") or {}
    if challenge:
        print()
        print("Challenge")
        print(f"- challenge_id: {challenge.get('challenge_id')}")
        print(f"- chain: {challenge.get('chain')}")
        print(f"- expires_at: {challenge.get('expires_at')}")

    topup_request = payload.get("topup_request") or {}
    if topup_request:
        print()
        print("Top-up request")
        print(f"- payment_request_id: {topup_request.get('payment_request_id')}")
        print(f"- amount_usd_cents: {topup_request.get('amount_usd_cents')}")
        print(f"- network: {topup_request.get('network')}")
        print(f"- pay_to: {topup_request.get('pay_to')}")
        print(f"- amount_atomic: {topup_request.get('amount_atomic')}")

    topup_verify = payload.get("topup_verify") or {}
    if topup_verify:
        print()
        print("Top-up verify")
        print(f"- status: {topup_verify.get('status')}")
        print(f"- transaction: {topup_verify.get('transaction')}")
        print(f"- receipt_id: {topup_verify.get('receipt_id')}")
        print(f"- balance_usd_cents: {topup_verify.get('balance_usd_cents')}")

    for label in ("balance_before_topup", "balance_after_topup", "balance_after_execute"):
        balance = payload.get(label)
        if balance:
            print()
            print(label.replace("_", " ").title())
            print(f"- balance_usd_cents: {balance.get('balance_usd_cents')}")
            print(f"- total_topped_up_usd_cents: {balance.get('total_topped_up_usd_cents')}")

    execute = payload.get("execute") or {}
    print()
    print("Execute")
    print(f"- skipped: {execute.get('skipped')}")
    if execute.get("reason"):
        print(f"- reason: {execute.get('reason')}")
    if not execute.get("skipped"):
        response = execute.get("response")
        if isinstance(response, dict):
            print(f"- execution_id: {response.get('execution_id')}")
            print(f"- org_credits_remaining_cents: {response.get('org_credits_remaining_cents')}")
        else:
            print(f"- response: {response}")

    if payload.get("last_error_response"):
        err = payload["last_error_response"]
        print()
        print("Last error response")
        print(f"- label: {err.get('label')}")
        print(f"- status: {err.get('status')}")
        print(f"- detail: {err.get('detail')}")
        print(f"- url: {err.get('url')}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Rhumb API base URL")
    parser.add_argument(
        "--private-key-env",
        default=DEFAULT_PRIVATE_KEY_ENV,
        help="Environment variable containing the funded wallet private key",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")
    parser.add_argument("--chain", default="base", help="Wallet auth chain for request-challenge")
    parser.add_argument("--topup-cents", type=int, default=DEFAULT_TOPUP_CENTS, help="Top-up amount in USD cents")
    parser.add_argument(
        "--validity-seconds",
        type=int,
        default=3600,
        help="Authorization validity window for EIP-3009 proof",
    )
    parser.add_argument(
        "--valid-after",
        type=int,
        default=0,
        help="validAfter unix timestamp for EIP-3009 proof (default: immediately valid)",
    )
    parser.add_argument("--skip-execute", action="store_true", help="Stop after proving top-up + credited balance")
    parser.add_argument(
        "--rotate-key-if-missing",
        action="store_true",
        help="Rotate the wallet API key if verify does not return a plaintext key",
    )
    parser.add_argument(
        "--execute-capability",
        default=DEFAULT_EXECUTE_CAPABILITY,
        help="Capability id to execute after top-up",
    )
    parser.add_argument(
        "--execute-provider",
        default=DEFAULT_EXECUTE_PROVIDER,
        help="Provider slug for the execute step",
    )
    parser.add_argument(
        "--execute-credential-mode",
        default=DEFAULT_EXECUTE_CREDENTIAL_MODE,
        help="Credential mode for the execute step",
    )
    parser.add_argument(
        "--execute-params-json",
        default=json.dumps(DEFAULT_EXECUTE_PARAMS),
        help="JSON object for the execute params payload",
    )
    parser.add_argument(
        "--execute-interface",
        default=DEFAULT_EXECUTE_INTERFACE,
        help="Interface label for the execute request",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--json-out", help="Write the result payload to a file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = run_flow(args)
        exit_code = 0
    except FlowError as exc:
        payload = {
            "ok": False,
            "summary": str(exc),
            **exc.state,
        }
        exit_code = 1
    except Exception as exc:  # pragma: no cover - defensive CLI fallback
        payload = {
            "ok": False,
            "summary": str(exc),
        }
        exit_code = 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
