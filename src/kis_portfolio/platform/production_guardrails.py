"""Fail-closed production inventory, cost, and release cleanup guardrails.

The module is deliberately side-effect free.  It validates already captured metadata
and produces review artifacts; it never calls Google Cloud or applies cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping
import re


INVENTORY_SCHEMA = "kis-portfolio.resource-inventory/v1"
COST_SNAPSHOT_SCHEMA = "kis-portfolio.cost-snapshot/v1"
RELEASE_MANIFEST_SCHEMA = "kis-portfolio.release-manifest/v1"
CLEANUP_PLAN_SCHEMA = "kis-portfolio.cleanup-plan/v1"

EARLY_WARNING_KRW = 7_500
GUARD_KRW = 35_000
APPROVAL_KRW = 42_500
CEILING_KRW = 50_000
DEFAULT_MAX_COST_EVIDENCE_AGE_DAYS = 40

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ACTIVE_KINDS = {"cloud_run_service", "cloud_run_job"}
_RESOURCE_KINDS = {
    "cloud_run_service",
    "cloud_run_job",
    "scheduler_job",
    "service_account",
    "secret",
    "gcs_bucket",
    "firestore_database",
    "artifact_repository",
}
_SEMANTIC_KEEP_TAGS = {"prod-current", "prod-previous"}


class GuardrailValidationError(ValueError):
    """Raised when a review artifact violates its versioned contract."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


def _parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be an RFC3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an RFC3339 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed.astimezone(UTC)


def _require_exact_keys(
    value: Mapping[str, Any], allowed: set[str], field: str, errors: list[str]
) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        errors.append(f"{field} has unsupported fields: {', '.join(extras)}")


def validate_inventory(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a non-secret resource inventory."""

    errors: list[str] = []
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "observed_at",
            "project_id",
            "regions",
            "complete",
            "collection_errors",
            "resources",
            "artifact_versions",
        },
        "inventory",
        errors,
    )
    if payload.get("schema_version") != INVENTORY_SCHEMA:
        errors.append(f"schema_version must be {INVENTORY_SCHEMA}")
    observed_at = _parse_timestamp(payload.get("observed_at"), "observed_at", errors)
    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        errors.append("project_id must be a non-empty string")
    regions = payload.get("regions")
    if (
        not isinstance(regions, list)
        or not regions
        or any(not isinstance(item, str) or not item for item in regions)
    ):
        errors.append("regions must be a non-empty string list")
    complete = payload.get("complete")
    if not isinstance(complete, bool):
        errors.append("complete must be boolean")
    collection_errors = payload.get("collection_errors")
    if not isinstance(collection_errors, list) or any(
        not isinstance(item, str) or not item for item in collection_errors
    ):
        errors.append("collection_errors must be a string list")
        collection_errors = []
    if complete is True and collection_errors:
        errors.append("complete inventory cannot contain collection_errors")

    resources = payload.get("resources")
    normalized_resources: list[dict[str, Any]] = []
    resource_keys: set[tuple[str, str]] = set()
    if not isinstance(resources, list):
        errors.append("resources must be a list")
        resources = []
    for index, resource in enumerate(resources):
        field = f"resources[{index}]"
        if not isinstance(resource, Mapping):
            errors.append(f"{field} must be an object")
            continue
        _require_exact_keys(
            resource,
            {"kind", "name", "region", "state", "labels", "image_digest", "configuration_sha256"},
            field,
            errors,
        )
        kind = resource.get("kind")
        name = resource.get("name")
        if kind not in _RESOURCE_KINDS:
            errors.append(f"{field}.kind is unsupported")
        if not isinstance(name, str) or not name:
            errors.append(f"{field}.name must be non-empty")
        elif isinstance(kind, str):
            key = (kind, name)
            if key in resource_keys:
                errors.append(f"duplicate resource {kind}/{name}")
            resource_keys.add(key)
        labels = resource.get("labels")
        if not isinstance(labels, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in labels.items()
        ):
            errors.append(f"{field}.labels must be a string map")
        image_digest = resource.get("image_digest")
        if kind in _ACTIVE_KINDS and not (
            isinstance(image_digest, str) and _DIGEST_RE.fullmatch(image_digest)
        ):
            errors.append(f"{field}.image_digest must resolve to sha256 for active compute")
        if image_digest is not None and not (
            isinstance(image_digest, str) and _DIGEST_RE.fullmatch(image_digest)
        ):
            errors.append(f"{field}.image_digest is invalid")
        config_hash = resource.get("configuration_sha256")
        if not isinstance(config_hash, str) or not _HASH_RE.fullmatch(config_hash):
            errors.append(f"{field}.configuration_sha256 must be 64 lowercase hex characters")
        normalized_resources.append(dict(resource))

    versions = payload.get("artifact_versions")
    normalized_versions: list[dict[str, Any]] = []
    version_keys: set[tuple[str, str, str]] = set()
    if not isinstance(versions, list):
        errors.append("artifact_versions must be a list")
        versions = []
    for index, version in enumerate(versions):
        field = f"artifact_versions[{index}]"
        if not isinstance(version, Mapping):
            errors.append(f"{field} must be an object")
            continue
        _require_exact_keys(
            version, {"repository", "package", "digest", "tags", "created_at"}, field, errors
        )
        repository = version.get("repository")
        package = version.get("package")
        digest = version.get("digest")
        if not isinstance(repository, str) or not repository:
            errors.append(f"{field}.repository must be non-empty")
        if not isinstance(package, str) or not package:
            errors.append(f"{field}.package must be non-empty")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            errors.append(f"{field}.digest is invalid")
        if all(isinstance(item, str) for item in (repository, package, digest)):
            key = (repository, package, digest)
            if key in version_keys:
                errors.append(f"duplicate artifact version {'/'.join(key)}")
            version_keys.add(key)
        tags = version.get("tags")
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
            errors.append(f"{field}.tags must be a string list")
        _parse_timestamp(version.get("created_at"), f"{field}.created_at", errors)
        normalized_versions.append(dict(version))

    if errors:
        raise GuardrailValidationError(errors)
    return {
        **dict(payload),
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "project_id": project_id.strip(),
        "regions": sorted(set(regions)),
        "resources": sorted(normalized_resources, key=lambda item: (item["kind"], item["name"])),
        "artifact_versions": sorted(
            normalized_versions,
            key=lambda item: (item["repository"], item["package"], item["created_at"], item["digest"]),
        ),
    }


def validate_release_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a release manifest that explicitly names active and rollback digests."""

    errors: list[str] = []
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "release_id",
            "created_at",
            "git_sha",
            "active_targets",
            "rollback_targets",
            "cleanup_policy",
            "restore_evidence",
        },
        "release_manifest",
        errors,
    )
    if payload.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        errors.append(f"schema_version must be {RELEASE_MANIFEST_SCHEMA}")
    if not isinstance(payload.get("release_id"), str) or not payload.get("release_id"):
        errors.append("release_id must be non-empty")
    created_at = _parse_timestamp(payload.get("created_at"), "created_at", errors)
    if not isinstance(payload.get("git_sha"), str) or not _GIT_SHA_RE.fullmatch(payload["git_sha"]):
        errors.append("git_sha must be a 40-character lowercase Git SHA")

    normalized_targets: dict[str, list[dict[str, Any]]] = {}
    for group in ("active_targets", "rollback_targets"):
        targets = payload.get(group)
        normalized_targets[group] = []
        if not isinstance(targets, list) or not targets:
            errors.append(f"{group} must be a non-empty list")
            continue
        names: set[str] = set()
        for index, target in enumerate(targets):
            field = f"{group}[{index}]"
            if not isinstance(target, Mapping):
                errors.append(f"{field} must be an object")
                continue
            _require_exact_keys(target, {"target", "repository", "digest"}, field, errors)
            name = target.get("target")
            repository = target.get("repository")
            digest = target.get("digest")
            if not isinstance(name, str) or not name:
                errors.append(f"{field}.target must be non-empty")
            elif name in names:
                errors.append(f"duplicate {group} target {name}")
            else:
                names.add(name)
            if not isinstance(repository, str) or not repository:
                errors.append(f"{field}.repository must be non-empty")
            if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
                errors.append(f"{field}.digest is invalid")
            normalized_targets[group].append(dict(target))

    active_names = {item.get("target") for item in normalized_targets["active_targets"]}
    rollback_names = {item.get("target") for item in normalized_targets["rollback_targets"]}
    missing_rollback = sorted(name for name in active_names - rollback_names if isinstance(name, str))
    if missing_rollback:
        errors.append("rollback_targets missing active targets: " + ", ".join(missing_rollback))

    policy = payload.get("cleanup_policy")
    if not isinstance(policy, Mapping):
        errors.append("cleanup_policy must be an object")
        policy = {}
    else:
        _require_exact_keys(
            policy,
            {"minimum_recent_versions", "untagged_min_age_days", "rollback_retention_days"},
            "cleanup_policy",
            errors,
        )
    for key in ("minimum_recent_versions", "untagged_min_age_days", "rollback_retention_days"):
        value = policy.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"cleanup_policy.{key} must be a positive integer")

    evidence = payload.get("restore_evidence")
    if not isinstance(evidence, Mapping):
        errors.append("restore_evidence must be an object")
        evidence = {}
    else:
        _require_exact_keys(evidence, {"verified_at", "reference", "result"}, "restore_evidence", errors)
    _parse_timestamp(evidence.get("verified_at"), "restore_evidence.verified_at", errors)
    if not isinstance(evidence.get("reference"), str) or not evidence.get("reference"):
        errors.append("restore_evidence.reference must be non-empty")
    if evidence.get("result") != "pass":
        errors.append("restore_evidence.result must be pass")

    if errors:
        raise GuardrailValidationError(errors)
    return {
        **dict(payload),
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "active_targets": sorted(normalized_targets["active_targets"], key=lambda item: item["target"]),
        "rollback_targets": sorted(normalized_targets["rollback_targets"], key=lambda item: item["target"]),
    }


@dataclass(frozen=True)
class CostDecision:
    state: str
    evaluated_krw: int | None
    actions: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "evaluated_krw": self.evaluated_krw,
            "actions": list(self.actions),
            "reasons": list(self.reasons),
        }


def evaluate_cost_snapshot(
    payload: Mapping[str, Any], *, as_of: datetime | None = None
) -> CostDecision:
    """Evaluate cost evidence against the approved KRW thresholds."""

    errors: list[str] = []
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "observed_at",
            "billing_period",
            "period_closed",
            "actual_krw",
            "forecast_krw",
            "attribution_complete",
            "source",
        },
        "cost_snapshot",
        errors,
    )
    if payload.get("schema_version") != COST_SNAPSHOT_SCHEMA:
        errors.append(f"schema_version must be {COST_SNAPSHOT_SCHEMA}")
    observed_at = _parse_timestamp(payload.get("observed_at"), "observed_at", errors)
    if not isinstance(payload.get("billing_period"), str) or not _PERIOD_RE.fullmatch(
        payload["billing_period"]
    ):
        errors.append("billing_period must be YYYY-MM")
    period_closed = payload.get("period_closed")
    if not isinstance(period_closed, bool):
        errors.append("period_closed must be boolean")
    values: list[int] = []
    for field in ("actual_krw", "forecast_krw"):
        value = payload.get(field)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            errors.append(f"{field} must be a non-negative integer or null")
        elif isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
    if payload.get("actual_krw") is None:
        errors.append("actual_krw is required")
    if period_closed is False and payload.get("forecast_krw") is None:
        errors.append("forecast_krw is required for an open billing period")
    if not isinstance(payload.get("attribution_complete"), bool):
        errors.append("attribution_complete must be boolean")
    if payload.get("source") not in {"billing_console_manual", "billing_export"}:
        errors.append("source must be billing_console_manual or billing_export")
    if errors:
        raise GuardrailValidationError(errors)

    reference_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    evidence_age_days = (reference_time - observed_at).total_seconds() / 86_400
    unknown_reasons: list[str] = []
    if evidence_age_days < 0:
        unknown_reasons.append("cost evidence is dated in the future")
    if evidence_age_days > DEFAULT_MAX_COST_EVIDENCE_AGE_DAYS:
        unknown_reasons.append("cost evidence is stale")
    if payload["attribution_complete"] is not True:
        unknown_reasons.append("cost attribution is incomplete")
    if unknown_reasons:
        return CostDecision(
            "unknown",
            max(values) if values else None,
            ("block_new_cost_increasing_work", "obtain_current_complete_cost_snapshot"),
            tuple(unknown_reasons),
        )

    evaluated = max(values)
    if evaluated >= CEILING_KRW:
        return CostDecision(
            "ceiling",
            evaluated,
            (
                "stop_new_backfill_and_optional_high_frequency_sources",
                "nominate_optional_pipeline_circuits_to_open",
                "preserve_auth_backup_and_recovery",
                "request_owner_priority",
            ),
            ("actual or forecast reached 50000 KRW",),
        )
    if evaluated >= APPROVAL_KRW:
        return CostDecision(
            "approval",
            evaluated,
            (
                "stop_new_backfill_and_optional_high_frequency_sources",
                "require_owner_approval_for_nonessential_pipelines",
            ),
            ("actual or forecast reached 42500 KRW",),
        )
    if evaluated >= GUARD_KRW:
        return CostDecision(
            "guard",
            evaluated,
            ("stop_new_backfill_and_optional_high_frequency_sources", "inspect_cost_attribution"),
            ("actual or forecast reached 35000 KRW",),
        )
    if evaluated >= EARLY_WARNING_KRW:
        band = "early_100"
    elif evaluated >= int(EARLY_WARNING_KRW * 0.9):
        band = "early_90"
    elif evaluated >= int(EARLY_WARNING_KRW * 0.5):
        band = "early_50"
    else:
        band = "normal"
    actions = (
        ("inspect_retry_image_storage_growth_and_attribution",)
        if band != "normal"
        else ("continue_within_approved_limits",)
    )
    return CostDecision(band, evaluated, actions, ("evaluated against approved cost envelope",))


def plan_artifact_cleanup(
    inventory_payload: Mapping[str, Any],
    manifest_payload: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Build a dry-run-only cleanup plan with explicit protected reasons."""

    inventory = validate_inventory(inventory_payload)
    manifest = validate_release_manifest(manifest_payload)
    blockers: list[str] = []
    reference_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    if inventory["complete"] is not True:
        blockers.append("resource inventory is incomplete")

    restore_verified_at = datetime.fromisoformat(
        manifest["restore_evidence"]["verified_at"].replace("Z", "+00:00")
    ).astimezone(UTC)
    restore_age_days = (reference_time - restore_verified_at).total_seconds() / 86_400
    if restore_age_days < 0:
        blockers.append("restore evidence is dated in the future")
    if restore_age_days > manifest["cleanup_policy"]["rollback_retention_days"]:
        blockers.append("restore evidence is older than rollback retention window")

    active_manifest = {item["target"]: item for item in manifest["active_targets"]}
    rollback_manifest = {item["target"]: item for item in manifest["rollback_targets"]}
    active_resources = [item for item in inventory["resources"] if item["kind"] in _ACTIVE_KINDS]
    for resource in active_resources:
        target = active_manifest.get(resource["name"])
        if target is None:
            blockers.append(f"active target missing from manifest: {resource['name']}")
        elif target["digest"] != resource["image_digest"]:
            blockers.append(f"active digest mismatch: {resource['name']}")
        if resource["name"] not in rollback_manifest:
            blockers.append(f"rollback target missing from manifest: {resource['name']}")

    known_versions = {
        (item["repository"], item["digest"]) for item in inventory["artifact_versions"]
    }
    for group in ("active_targets", "rollback_targets"):
        for target in manifest[group]:
            if (target["repository"], target["digest"]) not in known_versions:
                blockers.append(
                    f"{group[:-1]} digest absent from inventory: {target['target']} {target['digest']}"
                )

    protected_digests: dict[tuple[str, str], set[str]] = {}
    for group, reason in (("active_targets", "active_manifest"), ("rollback_targets", "rollback_manifest")):
        for target in manifest[group]:
            protected_digests.setdefault((target["repository"], target["digest"]), set()).add(reason)

    recent_floor = manifest["cleanup_policy"]["minimum_recent_versions"]
    by_package: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for version in inventory["artifact_versions"]:
        by_package.setdefault((version["repository"], version["package"]), []).append(version)
    recent_keys: set[tuple[str, str]] = set()
    for versions in by_package.values():
        newest = sorted(versions, key=lambda item: item["created_at"], reverse=True)[:recent_floor]
        recent_keys.update((item["repository"], item["digest"]) for item in newest)

    minimum_age = manifest["cleanup_policy"]["untagged_min_age_days"]
    entries: list[dict[str, Any]] = []
    for version in inventory["artifact_versions"]:
        key = (version["repository"], version["digest"])
        reasons = set(protected_digests.get(key, set()))
        tags = set(version["tags"])
        semantic_tags = sorted(
            tag for tag in tags if tag in _SEMANTIC_KEEP_TAGS or tag.startswith("rollback-")
        )
        if semantic_tags:
            reasons.add("semantic_keep_tag:" + ",".join(semantic_tags))
        if key in recent_keys:
            reasons.add("recent_version_floor")
        created_at = datetime.fromisoformat(version["created_at"].replace("Z", "+00:00"))
        age_days = int((reference_time - created_at.astimezone(UTC)).total_seconds() // 86_400)
        if age_days < 0:
            reasons.add("future_dated_version")
        if reasons:
            action = "protect"
        elif tags:
            action = "retain"
            reasons.add("non_cleanup_tag")
        elif age_days < minimum_age:
            action = "retain"
            reasons.add("minimum_age_not_met")
        else:
            action = "candidate"
            reasons.add("untagged_age_eligible")
        entries.append(
            {
                "repository": version["repository"],
                "package": version["package"],
                "digest": version["digest"],
                "age_days": age_days,
                "action": action,
                "reasons": sorted(reasons),
            }
        )

    return {
        "schema_version": CLEANUP_PLAN_SCHEMA,
        "generated_at": reference_time.isoformat().replace("+00:00", "Z"),
        "mode": "dry_run",
        "apply_allowed": False,
        "review_required": True,
        "complete": not blockers,
        "blockers": sorted(set(blockers)),
        "entries": sorted(entries, key=lambda item: (item["repository"], item["package"], item["digest"])),
    }
