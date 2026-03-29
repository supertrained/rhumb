#!/usr/bin/env python3
"""Controlled restart helper for a wedged Awal / payments-mcp-server daemon.

Purpose:
- Turn the risky "kill the daemon and hope" move into a repeatable, inspect-first flow
- Preserve the read-only wallet-state evidence step before any restart
- Probe whether Awal CLI health actually recovers after reopening the companion window

By default this script is DRY-RUN ONLY. It will inspect local wallet state, locate the
`payments-mcp-server` PID, and show exactly what it would do. Pass `--execute` to send
SIGTERM to the detected daemon, wait for exit, reopen the companion window with
`npx awal show`, then run bounded health probes (`status`, `address`, `balance --json`).

Usage:
  python3 rhumb/scripts/restart_awal_payments_daemon.py
  python3 rhumb/scripts/restart_awal_payments_daemon.py --json
  python3 rhumb/scripts/restart_awal_payments_daemon.py --execute
  python3 rhumb/scripts/restart_awal_payments_daemon.py --execute --pid 6480
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
INSPECTOR_PATH = REPO_ROOT / "scripts" / "inspect_awal_wallet_state.py"
PROCESS_NAME = "payments-mcp-server"
DEFAULT_AWAL_SHOW_CMD = ["npx", "awal", "show"]
DEFAULT_PROBES = [
    ["npx", "awal", "status"],
    ["npx", "awal", "address"],
    ["npx", "awal", "balance", "--json"],
]


def _run_command(cmd: list[str], timeout: float) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "timed_out": False,
            "duration_seconds": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "cmd": cmd,
            "returncode": None,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "timed_out": True,
            "duration_seconds": round(time.time() - started, 3),
        }


def _ps_snapshot() -> list[dict[str, str]]:
    proc = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,etime=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    rows: list[dict[str, str]] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if PROCESS_NAME not in line and "Electron Helper" not in line and "awal" not in line.lower():
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, command = parts
        rows.append({"pid": pid, "ppid": ppid, "etime": etime, "command": command})
    return rows


def _detect_pid(snapshot: list[dict[str, str]]) -> int | None:
    for row in snapshot:
        if PROCESS_NAME in row["command"]:
            try:
                return int(row["pid"])
            except ValueError:
                return None
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int, wait_seconds: float) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pid": pid,
        "signal": "SIGTERM",
        "wait_seconds": wait_seconds,
        "sent": False,
        "exited": False,
        "error": None,
    }
    try:
        os.kill(pid, signal.SIGTERM)
        payload["sent"] = True
    except OSError as exc:
        payload["error"] = str(exc)
        return payload

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not _pid_alive(pid):
            payload["exited"] = True
            payload["exit_observed_after_seconds"] = round(wait_seconds - (deadline - time.time()), 3)
            return payload
        time.sleep(0.5)

    payload["exit_observed_after_seconds"] = round(wait_seconds, 3)
    return payload


def _wallet_state() -> dict[str, Any]:
    if not INSPECTOR_PATH.exists():
        return {"available": False, "summary": "Inspector script missing", "payload": None}

    result = _run_command([sys.executable, str(INSPECTOR_PATH), "--json"], timeout=12)
    payload: dict[str, Any] | None = None
    if not result.get("timed_out") and result.get("returncode") == 0 and result.get("stdout"):
        try:
            payload = json.loads(result["stdout"])
        except json.JSONDecodeError:
            payload = None

    return {
        "available": True,
        "summary": payload.get("summary") if payload else "Inspector did not return parseable JSON",
        "payload": payload,
        "command": result,
    }


def _build_summary(payload: dict[str, Any]) -> str:
    mode = "execute" if payload["execute"] else "dry-run"
    pid = payload.get("target_pid")
    pre = payload.get("pre_restart", {})
    pre_status = pre.get("status_probe", {})
    post = payload.get("post_restart", {})
    probes = post.get("probes", [])

    if mode == "dry-run":
        if pre_status.get("timed_out"):
            return (
                f"Dry run only: detected wedged Awal CLI (status timed out) with {PROCESS_NAME} PID {pid}. "
                "Wallet-state evidence is preserved; safe next step is executing a controlled restart, not wiping app data."
            )
        return (
            f"Dry run only: {PROCESS_NAME} PID {pid or 'not found'} is present and Awal CLI did not clearly time out. "
            "Manual review is safer than restarting blindly."
        )

    reopen = post.get("reopen_wallet_window", {})
    if not post.get("terminate", {}).get("exited"):
        return (
            f"Attempted controlled restart of {PROCESS_NAME} PID {pid}, but the process did not exit cleanly after SIGTERM. "
            "Do not escalate to wipes; inspect the process tree and decide whether a harder kill is justified."
        )

    if reopen.get("returncode") != 0 and not reopen.get("stdout"):
        return (
            f"Controlled restart terminated {PROCESS_NAME} PID {pid}, but reopening the wallet companion did not succeed cleanly. "
            "Further interactive recovery is still required."
        )

    if probes and any(not probe.get("timed_out") and probe.get("returncode") == 0 for probe in probes):
        return (
            "Controlled restart completed and at least one bounded Awal CLI probe recovered. "
            "Next step is verifying the funded wallet address before rerunning live x402."
        )

    return (
        "Controlled restart completed, but bounded Awal CLI probes still failed or timed out. "
        "The issue is narrowed to the local companion/runtime path, not wallet-state loss."
    )


def _print_human(payload: dict[str, Any]) -> None:
    print(f"Awal controlled restart helper ({'EXECUTE' if payload['execute'] else 'DRY RUN'})")
    print(f"Target process: {PROCESS_NAME}")
    print(f"Detected PID: {payload.get('target_pid') or 'not found'}")
    print()

    wallet_state = payload.get("wallet_state", {})
    print("Wallet-state preflight:")
    print(f"- available: {'yes' if wallet_state.get('available') else 'no'}")
    print(f"- summary: {wallet_state.get('summary')}")
    print()

    pre = payload.get("pre_restart", {})
    status_probe = pre.get("status_probe", {})
    print("Pre-restart probes:")
    print(
        f"- npx awal status: returncode={status_probe.get('returncode')} timed_out={status_probe.get('timed_out')} duration={status_probe.get('duration_seconds')}s"
    )
    if status_probe.get("stdout"):
        print(f"  stdout: {status_probe['stdout']}")
    if status_probe.get("stderr"):
        print(f"  stderr: {status_probe['stderr']}")
    print()

    if payload["execute"]:
        terminate = payload.get("post_restart", {}).get("terminate", {})
        reopen = payload.get("post_restart", {}).get("reopen_wallet_window", {})
        print("Restart actions:")
        print(
            f"- terminate: sent={terminate.get('sent')} exited={terminate.get('exited')} wait={terminate.get('wait_seconds')}s error={terminate.get('error')}"
        )
        print(
            f"- reopen wallet window: returncode={reopen.get('returncode')} timed_out={reopen.get('timed_out')} duration={reopen.get('duration_seconds')}s"
        )
        if reopen.get("stdout"):
            print(f"  stdout: {reopen['stdout']}")
        if reopen.get("stderr"):
            print(f"  stderr: {reopen['stderr']}")
        print()

        print("Post-restart probes:")
        for probe in payload.get("post_restart", {}).get("probes", []):
            cmd = " ".join(probe.get("cmd", []))
            print(
                f"- {cmd}: returncode={probe.get('returncode')} timed_out={probe.get('timed_out')} duration={probe.get('duration_seconds')}s"
            )
            if probe.get("stdout"):
                print(f"  stdout: {probe['stdout']}")
            if probe.get("stderr"):
                print(f"  stderr: {probe['stderr']}")
        print()
    else:
        print("Planned action:")
        print(f"- would send SIGTERM to PID {payload.get('target_pid') or '(not found)'}")
        print("- would reopen the companion with: npx awal show")
        print("- would run bounded probes: npx awal status / address / balance --json")
        print()

    print(f"Summary: {payload['summary']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled restart helper for a wedged Awal payments daemon")
    parser.add_argument("--execute", action="store_true", help="Actually send SIGTERM and attempt the restart")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--pid", type=int, help="Override detected payments-mcp-server PID")
    parser.add_argument("--term-wait-seconds", type=float, default=15.0, help="Seconds to wait for SIGTERM exit")
    parser.add_argument("--probe-timeout-seconds", type=float, default=12.0, help="Timeout per Awal probe")
    parser.add_argument("--settle-seconds", type=float, default=3.0, help="Pause after reopening the wallet window")
    args = parser.parse_args()

    snapshot = _ps_snapshot()
    target_pid = args.pid or _detect_pid(snapshot)
    wallet_state = _wallet_state()
    pre_status = _run_command(["npx", "awal", "status"], timeout=args.probe_timeout_seconds)

    payload: dict[str, Any] = {
        "execute": args.execute,
        "target_pid": target_pid,
        "process_snapshot": snapshot,
        "wallet_state": wallet_state,
        "pre_restart": {
            "status_probe": pre_status,
        },
        "post_restart": {},
    }

    if args.execute:
        if target_pid is None:
            payload["post_restart"] = {
                "terminate": {
                    "pid": None,
                    "signal": "SIGTERM",
                    "wait_seconds": args.term_wait_seconds,
                    "sent": False,
                    "exited": False,
                    "error": f"{PROCESS_NAME} not found",
                },
                "reopen_wallet_window": {"cmd": DEFAULT_AWAL_SHOW_CMD, "returncode": None, "stdout": "", "stderr": "", "timed_out": False, "duration_seconds": 0.0},
                "probes": [],
            }
        else:
            terminate = _terminate_pid(target_pid, wait_seconds=args.term_wait_seconds)
            reopen = _run_command(DEFAULT_AWAL_SHOW_CMD, timeout=20)
            if args.settle_seconds > 0:
                time.sleep(args.settle_seconds)
            probes = [_run_command(cmd, timeout=args.probe_timeout_seconds) for cmd in DEFAULT_PROBES]
            payload["post_restart"] = {
                "terminate": terminate,
                "reopen_wallet_window": reopen,
                "probes": probes,
            }

    payload["summary"] = _build_summary(payload)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
