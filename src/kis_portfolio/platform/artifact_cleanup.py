"""Fail-closed validation and exact-digest execution for WI-049-S03."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from kis_portfolio.platform.production_guardrails import GuardrailValidationError


SPEC_SCHEMA = "kis-portfolio.artifact-cleanup-spec/v1"
APPROVAL_SCHEMA = "kis-portfolio.artifact-cleanup-approval/v1"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*")
_REQUIRED_EXCLUSIONS = (
    "cloud_run_jobs",
    "cloud_run_services",
    "schedulers",
    "data",
    "backups",
    "buckets",
    "firestore",
    "iam",
    "secrets",
    "tags",
)


@dataclass(frozen=True)
class ArtifactCleanupResult:
    status: str
    approved_target_count: int
    deleted_targets: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "approved_target_count": self.approved_target_count,
            "deleted_targets": list(self.deleted_targets),
        }


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _flatten(groups: Mapping[str, Sequence[str]]) -> set[tuple[str, str]]:
    return {(package, digest) for package, digests in groups.items() for digest in digests}


def validate_artifact_cleanup_spec(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "schema_version", "generated_at", "project_id", "region", "mode",
        "apply_allowed", "owner_approved", "inventory", "policy",
        "protected_references", "retain_targets", "removal_targets",
        "excluded_mutations", "approval_boundary",
    }
    if set(payload) != required:
        errors.append("spec fields do not exactly match the v1 contract")
    if payload.get("schema_version") != SPEC_SCHEMA:
        errors.append(f"schema_version must be {SPEC_SCHEMA}")
    if payload.get("mode") != "dry_run" or payload.get("apply_allowed") is not False:
        errors.append("spec must remain dry_run with apply_allowed=false")
    if payload.get("owner_approved") is not False:
        errors.append("owner approval must be a separate artifact")
    if tuple(payload.get("excluded_mutations") or ()) != _REQUIRED_EXCLUSIONS:
        errors.append("spec exclusions must exactly preserve all non-image and tag mutations")

    groups: dict[str, dict[str, Sequence[str]]] = {}
    for field in ("retain_targets", "removal_targets"):
        value = payload.get(field)
        groups[field] = value if isinstance(value, Mapping) else {}
        if not isinstance(value, Mapping) or not value:
            errors.append(f"{field} must be a non-empty package map")
            continue
        for package, digests in value.items():
            if not isinstance(package, str) or not _PACKAGE_RE.fullmatch(package):
                errors.append(f"invalid package identity in {field}: {package}")
            if not isinstance(digests, list) or not digests:
                errors.append(f"{field}.{package} must be a non-empty digest list")
                continue
            if len(digests) != len(set(digests)):
                errors.append(f"duplicate digest in {field}.{package}")
            if any(not isinstance(item, str) or not _DIGEST_RE.fullmatch(item) for item in digests):
                errors.append(f"invalid digest in {field}.{package}")

    retained = _flatten(groups["retain_targets"])
    removable = _flatten(groups["removal_targets"])
    inventory = payload.get("inventory") if isinstance(payload.get("inventory"), Mapping) else {}
    if len(retained) != inventory.get("retain_versions"):
        errors.append("retain count does not match inventory")
    if len(removable) != inventory.get("removal_candidate_versions"):
        errors.append("removal count does not match inventory")
    if len(retained | removable) != inventory.get("versions"):
        errors.append("retain/removal union does not match inventory")
    if retained & removable:
        errors.append("retain and removal targets overlap")

    references = payload.get("protected_references")
    if not isinstance(references, list) or not references:
        errors.append("protected_references must be non-empty")
        references = []
    for reference in references:
        if not isinstance(reference, Mapping):
            errors.append("protected reference must be an object")
            continue
        key = (f"{reference.get('repository')}/{reference.get('package')}", reference.get("digest"))
        if key not in retained or key in removable:
            errors.append(f"protected reference is not retained: {reference.get('target')}")
    if errors:
        raise GuardrailValidationError(errors)
    return dict(payload)


def validate_artifact_cleanup_approval(
    payload: Mapping[str, Any], *, spec: Mapping[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "schema_version", "approved_at", "approved_by", "spec_reference",
        "spec_canonical_sha256", "approved_scope", "approved_target_count",
        "excluded_mutations",
    }
    if set(payload) != required:
        errors.append("approval fields do not exactly match the v1 contract")
    if payload.get("schema_version") != APPROVAL_SCHEMA:
        errors.append(f"schema_version must be {APPROVAL_SCHEMA}")
    if payload.get("approved_by") != "owner":
        errors.append("approved_by must be owner")
    if payload.get("approved_scope") != "all_removal_targets":
        errors.append("approved_scope must be all_removal_targets")
    if payload.get("spec_canonical_sha256") != canonical_sha256(spec):
        errors.append("approval does not match the canonical specification hash")
    removal_count = len(_flatten(spec["removal_targets"]))
    if payload.get("approved_target_count") != removal_count:
        errors.append("approved target count does not match the specification")
    if tuple(payload.get("excluded_mutations") or ()) != _REQUIRED_EXCLUSIONS:
        errors.append("approval exclusions must exactly preserve all non-image and tag mutations")
    if errors:
        raise GuardrailValidationError(errors)
    return dict(payload)


def _run_json(command: Sequence[str]) -> Any:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _run_delete(command: Sequence[str]) -> None:
    subprocess.run(command, check=True, text=True)


def _inventory(
    spec: Mapping[str, Any], load_json: Callable[[Sequence[str]], Any]
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], list[str]]]:
    project = spec["project_id"]
    region = spec["region"]
    repositories = sorted({package.split("/", 1)[0] for package in spec["retain_targets"]})
    found: set[tuple[str, str]] = set()
    tags: dict[tuple[str, str], list[str]] = {}
    for repository in repositories:
        root = f"{region}-docker.pkg.dev/{project}/{repository}"
        rows = load_json([
            "gcloud", "artifacts", "docker", "images", "list", root,
            "--include-tags", "--format=json",
        ])
        for row in rows:
            package = f"{repository}/{str(row['package']).rsplit('/', 1)[-1]}"
            digest = row["version"]
            key = (package, digest)
            found.add(key)
            tags[key] = list(row.get("tags") or [])
    return found, tags


def _image_key(image: str, *, project: str) -> tuple[str, str] | None:
    if "@" not in image:
        return None
    path, digest = image.rsplit("@", 1)
    parts = path.split("/")
    if len(parts) < 4 or parts[1] != project or not _DIGEST_RE.fullmatch(digest):
        return None
    return (f"{parts[2]}/{parts[-1]}", digest)


def _live_image_references(
    spec: Mapping[str, Any], load_json: Callable[[Sequence[str]], Any]
) -> set[tuple[str, str]]:
    project = spec["project_id"]
    region = spec["region"]
    references: set[tuple[str, str]] = set()
    services = load_json([
        "gcloud", "run", "services", "list", "--project", project,
        "--region", region, "--format=json",
    ])
    for service in services:
        containers = (((service.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
        for container in containers:
            key = _image_key(container.get("image") or "", project=project)
            if key:
                references.add(key)
        for traffic in (service.get("status") or {}).get("traffic") or []:
            revision = traffic.get("revisionName")
            if not revision:
                continue
            row = load_json([
                "gcloud", "run", "revisions", "describe", revision,
                "--project", project, "--region", region, "--format=json",
            ])
            for container in (row.get("spec") or {}).get("containers") or []:
                key = _image_key(container.get("image") or "", project=project)
                if key:
                    references.add(key)
    jobs = load_json([
        "gcloud", "run", "jobs", "list", "--project", project,
        "--region", region, "--format=json",
    ])
    for job in jobs:
        task = (((((job.get("spec") or {}).get("template") or {}).get("spec") or {}).get("template") or {}).get("spec") or {})
        for container in task.get("containers") or []:
            key = _image_key(container.get("image") or "", project=project)
            if key:
                references.add(key)
    return references


def execute_artifact_cleanup(
    spec_payload: Mapping[str, Any],
    approval_payload: Mapping[str, Any],
    *,
    apply: bool,
    github_actions: bool,
    github_ref: str,
    load_json: Callable[[Sequence[str]], Any] = _run_json,
    delete: Callable[[Sequence[str]], None] = _run_delete,
) -> ArtifactCleanupResult:
    spec = validate_artifact_cleanup_spec(spec_payload)
    approval = validate_artifact_cleanup_approval(approval_payload, spec=spec)
    if apply and (not github_actions or github_ref != "refs/heads/master"):
        raise GuardrailValidationError(
            ("apply is allowed only from GitHub Actions on refs/heads/master",)
        )

    retained = _flatten(spec["retain_targets"])
    removable = _flatten(spec["removal_targets"])
    actual, tags = _inventory(spec, load_json)
    errors: list[str] = []
    if actual != retained | removable:
        errors.append("Artifact Registry inventory drifted from the approved specification")
    tagged_candidates = sorted(f"{package}@{digest}" for package, digest in removable if tags.get((package, digest)))
    if tagged_candidates:
        errors.append("removal candidates gained tags: " + ", ".join(tagged_candidates))
    live_references = _live_image_references(spec, load_json)
    unsafe = sorted(f"{package}@{digest}" for package, digest in live_references if (package, digest) not in retained)
    if unsafe:
        errors.append("live image reference is outside retain set: " + ", ".join(unsafe))
    if errors:
        raise GuardrailValidationError(errors)

    approved_targets = tuple(sorted(f"{package}@{digest}" for package, digest in removable))
    if not apply:
        return ArtifactCleanupResult("dry_run_pass", len(approved_targets), ())

    project = spec["project_id"]
    region = spec["region"]
    deleted: list[str] = []
    for target in approved_targets:
        repository_package, digest = target.rsplit("@", 1)
        repository, package = repository_package.split("/", 1)
        uri = f"{region}-docker.pkg.dev/{project}/{repository}/{package}@{digest}"
        delete(["gcloud", "artifacts", "docker", "images", "delete", uri, "--quiet", "--project", project])
        deleted.append(target)

    remaining, _ = _inventory(spec, load_json)
    still_present = sorted(f"{package}@{digest}" for package, digest in removable & remaining)
    missing_retained = sorted(f"{package}@{digest}" for package, digest in retained - remaining)
    if still_present or missing_retained:
        post_errors = []
        if still_present:
            post_errors.append("approved images still present: " + ", ".join(still_present))
        if missing_retained:
            post_errors.append("retained images missing: " + ", ".join(missing_retained))
        raise GuardrailValidationError(post_errors)
    return ArtifactCleanupResult("applied", approval["approved_target_count"], tuple(deleted))
