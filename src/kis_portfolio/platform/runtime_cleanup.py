"""Fail-closed planning and execution for exact Cloud Run Job cleanup."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from kis_portfolio.platform.production_guardrails import (
    GuardrailValidationError,
    validate_runtime_cleanup_manifest,
)


RUNTIME_CLEANUP_APPROVAL_SCHEMA = "kis-portfolio.runtime-cleanup-approval/v1"


@dataclass(frozen=True)
class CleanupResult:
    status: str
    approved_names: tuple[str, ...]
    deleted_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "approved_names": list(self.approved_names),
            "deleted_names": list(self.deleted_names),
        }


def validate_cleanup_approval(
    payload: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate exact owner approval without widening the frozen candidate set."""

    errors: list[str] = []
    allowed = {
        "schema_version",
        "approved_at",
        "approved_by",
        "manifest_reference",
        "approved_targets",
        "excluded_resource_families",
    }
    extras = sorted(set(payload) - allowed)
    if extras:
        errors.append("approval has unsupported fields: " + ", ".join(extras))
    if payload.get("schema_version") != RUNTIME_CLEANUP_APPROVAL_SCHEMA:
        errors.append(f"schema_version must be {RUNTIME_CLEANUP_APPROVAL_SCHEMA}")
    if not isinstance(payload.get("approved_at"), str) or not payload.get("approved_at"):
        errors.append("approved_at must be non-empty")
    if payload.get("approved_by") != "owner":
        errors.append("approved_by must be owner")
    if not isinstance(payload.get("manifest_reference"), str) or not payload.get(
        "manifest_reference"
    ):
        errors.append("manifest_reference must be non-empty")

    targets = payload.get("approved_targets")
    if not isinstance(targets, list) or not targets or any(
        not isinstance(item, str) or not item for item in targets
    ):
        errors.append("approved_targets must be a non-empty string list")
        targets = []
    if len(targets) != len(set(targets)):
        errors.append("approved_targets must not contain duplicates")
    manifest_targets = {item["name"] for item in manifest["candidates"]}
    unknown = sorted(set(targets) - manifest_targets)
    if unknown:
        errors.append("approved_targets are outside the frozen manifest: " + ", ".join(unknown))
    missing = sorted(manifest_targets - set(targets))
    if missing:
        errors.append("approval does not cover the frozen target set: " + ", ".join(missing))

    exclusions = payload.get("excluded_resource_families")
    required_exclusions = {
        "artifact_images",
        "backups",
        "data",
        "iam",
        "schedulers",
        "secrets",
        "services",
    }
    if not isinstance(exclusions, list) or set(exclusions) != required_exclusions:
        errors.append("excluded_resource_families must exactly preserve the required exclusions")

    if errors:
        raise GuardrailValidationError(errors)
    return {**dict(payload), "approved_targets": sorted(targets)}


def canonical_job_configuration(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Select the non-secret fields used by the frozen configuration hash."""

    metadata = payload.get("metadata") or {}
    job_spec = (((payload.get("spec") or {}).get("template") or {}).get("spec") or {})
    task_spec = (((job_spec.get("template") or {}).get("spec") or {}))
    containers = task_spec.get("containers") or []
    container = containers[0] if containers else {}
    return {
        "name": metadata.get("name"),
        "image": container.get("image"),
        "command": container.get("command") or [],
        "args": container.get("args") or [],
        "serviceAccount": task_spec.get("serviceAccountName"),
        "taskCount": job_spec.get("taskCount"),
        "timeout": task_spec.get("timeoutSeconds"),
        "maxRetries": task_spec.get("maxRetries"),
    }


def job_configuration_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        canonical_job_configuration(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256((canonical + "\n").encode()).hexdigest()


def _run_json(command: Sequence[str]) -> Any:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _run_delete(command: Sequence[str]) -> None:
    subprocess.run(command, check=True, text=True)


def _scheduler_target_names(schedulers: Sequence[Mapping[str, Any]]) -> set[str]:
    targets: set[str] = set()
    marker = "/jobs/"
    for scheduler in schedulers:
        uri = ((scheduler.get("httpTarget") or {}).get("uri") or "")
        if marker in uri and uri.endswith(":run"):
            targets.add(uri.split(marker, 1)[1].removesuffix(":run"))
    return targets


def _resource_names(resources: Sequence[Mapping[str, Any]]) -> set[str]:
    names: set[str] = set()
    for resource in resources:
        raw = ((resource.get("metadata") or {}).get("name") or resource.get("name") or "")
        if raw:
            names.add(raw.rsplit("/", 1)[-1])
    return names


def execute_runtime_cleanup(
    manifest_payload: Mapping[str, Any],
    approval_payload: Mapping[str, Any],
    *,
    apply: bool,
    github_actions: bool,
    github_ref: str,
    load_json: Callable[[Sequence[str]], Any] = _run_json,
    delete: Callable[[Sequence[str]], None] = _run_delete,
) -> CleanupResult:
    """Revalidate every exact candidate, then optionally delete only those Jobs."""

    manifest = validate_runtime_cleanup_manifest(manifest_payload)
    approval = validate_cleanup_approval(approval_payload, manifest=manifest)
    if apply and (not github_actions or github_ref != "refs/heads/master"):
        raise GuardrailValidationError(
            ("apply is allowed only from GitHub Actions on refs/heads/master",)
        )

    project = manifest["project_id"]
    region = manifest["region"]
    schedulers = load_json(
        [
            "gcloud",
            "scheduler",
            "jobs",
            "list",
            "--project",
            project,
            "--location",
            region,
            "--format=json",
        ]
    )
    scheduled_names = _scheduler_target_names(schedulers)
    load_json(
        [
            "gcloud",
            "storage",
            "objects",
            "describe",
            manifest["recovery_evidence"]["backup_index_uri"],
            "--format=json",
        ]
    )
    errors: list[str] = []
    by_name = {item["name"]: item for item in manifest["candidates"]}
    for name in approval["approved_targets"]:
        expected = by_name[name]
        live = load_json(
            [
                "gcloud",
                "run",
                "jobs",
                "describe",
                name,
                "--project",
                project,
                "--region",
                region,
                "--format=json",
            ]
        )
        image = canonical_job_configuration(live)["image"] or ""
        live_digest = image.rsplit("@", 1)[-1] if "@" in image else ""
        if live_digest != expected["image_digest"]:
            errors.append(f"image digest mismatch: {name}")
        if job_configuration_sha256(live) != expected["configuration_sha256"]:
            errors.append(f"configuration hash mismatch: {name}")
        if name in scheduled_names:
            errors.append(f"scheduler still targets cleanup candidate: {name}")
    if errors:
        raise GuardrailValidationError(errors)

    if not apply:
        return CleanupResult("dry_run_pass", tuple(approval["approved_targets"]), ())

    deleted: list[str] = []
    for name in approval["approved_targets"]:
        delete(
            [
                "gcloud",
                "run",
                "jobs",
                "delete",
                name,
                "--quiet",
                "--project",
                project,
                "--region",
                region,
            ]
        )
        deleted.append(name)

    remaining_jobs = load_json(
        [
            "gcloud",
            "run",
            "jobs",
            "list",
            "--project",
            project,
            "--region",
            region,
            "--format=json",
        ]
    )
    remaining_job_names = _resource_names(remaining_jobs)
    still_present = sorted(set(approval["approved_targets"]) & remaining_job_names)
    protected_job_names = {
        item["name"]
        for item in manifest["protected_resources"]
        if item["kind"] == "cloud_run_job"
    }
    missing_protected_jobs = sorted(protected_job_names - remaining_job_names)

    remaining_schedulers = load_json(
        [
            "gcloud",
            "scheduler",
            "jobs",
            "list",
            "--project",
            project,
            "--location",
            region,
            "--format=json",
        ]
    )
    protected_scheduler_names = {
        item["name"]
        for item in manifest["protected_resources"]
        if item["kind"] == "scheduler_job"
    }
    missing_protected_schedulers = sorted(
        protected_scheduler_names - _resource_names(remaining_schedulers)
    )
    post_errors: list[str] = []
    if still_present:
        post_errors.append("approved Jobs still present: " + ", ".join(still_present))
    if missing_protected_jobs:
        post_errors.append("protected Jobs missing: " + ", ".join(missing_protected_jobs))
    if missing_protected_schedulers:
        post_errors.append(
            "protected Schedulers missing: " + ", ".join(missing_protected_schedulers)
        )
    if post_errors:
        raise GuardrailValidationError(post_errors)
    return CleanupResult("applied", tuple(approval["approved_targets"]), tuple(deleted))


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GuardrailValidationError((f"{path} must contain a JSON object",))
    return value
