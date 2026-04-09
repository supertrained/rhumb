"""Human-readable summaries for GitHub Actions workflow-run capability executions."""

from __future__ import annotations


def summarize_actions_execution(capability_id: str, payload: dict) -> str:
    actions_ref = payload.get("actions_ref") or "unknown actions_ref"
    repository = payload.get("repository") or "unknown repository"

    if capability_id == "workflow_run.list":
        count = payload.get("run_count_returned", 0)
        return f"Listed {count} GitHub Actions workflow runs for {repository} via actions_ref {actions_ref}"

    if capability_id == "workflow_run.get":
        run_id = payload.get("run_id") or "unknown run"
        return f"Fetched GitHub Actions workflow run {run_id} for {repository} via actions_ref {actions_ref}"

    return f"Completed {capability_id} for {repository} via actions_ref {actions_ref}"
