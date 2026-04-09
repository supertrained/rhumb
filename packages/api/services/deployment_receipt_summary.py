"""Human-readable summaries for deployment capability executions."""

from __future__ import annotations


def summarize_deployment_execution(capability_id: str, payload: dict) -> str:
    deployment_ref = payload.get("deployment_ref") or "unknown deployment_ref"

    if capability_id == "deployment.list":
        count = payload.get("deployment_count_returned", 0)
        project_id = payload.get("project_id") or "scoped projects"
        target = payload.get("target")
        target_suffix = f" on target {target}" if target else ""
        return f"Listed {count} Vercel deployments for {project_id}{target_suffix} via deployment_ref {deployment_ref}"

    if capability_id == "deployment.get":
        deployment_id = payload.get("deployment_id") or "unknown deployment"
        project_name = payload.get("project_name") or payload.get("project_id") or "unknown project"
        return f"Fetched Vercel deployment {deployment_id} for {project_name} via deployment_ref {deployment_ref}"

    return f"Completed {capability_id} via deployment_ref {deployment_ref}"
