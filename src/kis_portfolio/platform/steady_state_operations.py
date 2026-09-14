"""Deterministic, non-authorizing assessment for steady-state operations reviews."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import math
from typing import Any, Mapping

from kis_portfolio.platform.production_guardrails import (
    CostDecision,
    GuardrailValidationError,
    evaluate_cost_snapshot,
)


EVIDENCE_SCHEMA = "kis-portfolio.steady-state-review-evidence/v1"
DECISION_SCHEMA = "kis-portfolio.steady-state-review-decision/v1"
RPO_LIMIT_MINUTES = 24 * 60
RTO_LIMIT_SECONDS = 4 * 60 * 60
RESTORE_REHEARSAL_MAX_AGE_DAYS = 100
DATABASE_GROWTH_ATTENTION_PERCENT = 25
ARTIFACT_GROWTH_ATTENTION_COUNT = 20
REVIEW_MAX_AGE_DAYS = {"monthly": 40, "quarterly": 100, "release": 7}


def verify_private_object_records(records, load_bytes) -> dict[str, Any]:
    """Verify private object bytes without returning identifiers or content."""

    seen: set[str] = set()
    total_bytes = 0
    for record in records:
        digest = record["content_hash"]
        uri = record["private_uri"]
        expected_size = record["byte_size"]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise GuardrailValidationError(("private object has an invalid content hash",))
        if not isinstance(uri, str) or not uri.startswith("gs://"):
            raise GuardrailValidationError(("private object has an invalid URI",))
        if digest in seen:
            raise GuardrailValidationError(("private object content hash is duplicated",))
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise GuardrailValidationError(("private object has an invalid byte size",))
        payload = load_bytes(uri)
        if len(payload) != expected_size:
            raise GuardrailValidationError(("private object byte size does not match metadata",))
        if hashlib.sha256(payload).hexdigest() != digest:
            raise GuardrailValidationError(("private object SHA-256 does not match metadata",))
        seen.add(digest)
        total_bytes += len(payload)
    return {"status": "pass", "object_count": len(seen), "byte_size": total_bytes}


@dataclass(frozen=True)
class SteadyStateDecision:
    status: str
    cadence: str
    blockers: tuple[str, ...]
    actions: tuple[str, ...]
    cost: CostDecision
    rpo_minutes: int
    rto_seconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "status": self.status,
            "cadence": self.cadence,
            "review_complete": self.status != "blocked",
            "production_change_authorized": False,
            "rpo_minutes": self.rpo_minutes,
            "rto_seconds": self.rto_seconds,
            "cost": self.cost.as_dict(),
            "blockers": list(self.blockers),
            "actions": list(self.actions),
        }


def _exact_keys(value: Any, expected: set[str], field: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{field} must be an object")
        return {}
    if set(value) != expected:
        errors.append(f"{field} fields do not exactly match the v1 contract")
    return value


def _non_negative_int(value: Any, field: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{field} must be a non-negative integer")
        return 0
    return value


def _positive_number(value: Any, field: str, errors: list[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        errors.append(f"{field} must be a positive number")
        return 0.0
    return float(value)


def _timestamp(value: Any, field: str, errors: list[str]) -> datetime:
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO timestamp")
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO timestamp")
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return datetime.min.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def assess_steady_state_review(
    evidence: Mapping[str, Any],
    cost_snapshot: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
) -> SteadyStateDecision:
    """Validate supplied review evidence and return actions without mutating any system."""

    errors: list[str] = []
    expected_top = {
        "schema_version", "observed_at", "evidence_scope", "cadence", "recovery",
        "capacity", "source_contracts", "access_control", "exceptions",
    }
    if set(evidence) != expected_top:
        errors.append("evidence fields do not exactly match the v1 contract")
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        errors.append(f"schema_version must be {EVIDENCE_SCHEMA}")
    if evidence.get("evidence_scope") not in {"fixture_only", "production_read_only"}:
        errors.append("evidence_scope must be fixture_only or production_read_only")
    cadence = evidence.get("cadence")
    if cadence not in {"monthly", "quarterly", "release"}:
        errors.append("cadence must be monthly, quarterly or release")
        cadence = "monthly"
    observed_at = _timestamp(evidence.get("observed_at"), "observed_at", errors)

    recovery = _exact_keys(evidence.get("recovery"), {
        "backup_created_at", "rehearsal_verified_at", "rpo_minutes", "rto_seconds",
        "result", "tables_restored", "through_migration", "object_count", "byte_size",
        "index_sha256", "restricted_object_bytes_included", "private_object_recovery_verified",
        "private_object_count", "private_object_byte_size",
    }, "recovery", errors)
    backup_created_at = _timestamp(recovery.get("backup_created_at"), "recovery.backup_created_at", errors)
    rehearsal_verified_at = _timestamp(
        recovery.get("rehearsal_verified_at"), "recovery.rehearsal_verified_at", errors
    )
    rpo = _non_negative_int(recovery.get("rpo_minutes"), "recovery.rpo_minutes", errors)
    rto = _non_negative_int(recovery.get("rto_seconds"), "recovery.rto_seconds", errors)
    tables_restored = _non_negative_int(
        recovery.get("tables_restored"), "recovery.tables_restored", errors
    )
    object_count = _non_negative_int(recovery.get("object_count"), "recovery.object_count", errors)
    byte_size = _non_negative_int(recovery.get("byte_size"), "recovery.byte_size", errors)
    if not tables_restored or not object_count or not byte_size:
        errors.append("recovery must restore non-empty tables and backup objects")
    if recovery.get("result") != "pass":
        errors.append("recovery.result must be pass")
    if not isinstance(recovery.get("through_migration"), str) or not recovery.get("through_migration"):
        errors.append("recovery.through_migration must be non-empty")
    digest = recovery.get("index_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        errors.append("recovery.index_sha256 must be a lowercase SHA-256")
    if not isinstance(recovery.get("restricted_object_bytes_included"), bool):
        errors.append("recovery.restricted_object_bytes_included must be boolean")
    if not isinstance(recovery.get("private_object_recovery_verified"), bool):
        errors.append("recovery.private_object_recovery_verified must be boolean")
    _non_negative_int(recovery.get("private_object_count"), "recovery.private_object_count", errors)
    _non_negative_int(
        recovery.get("private_object_byte_size"), "recovery.private_object_byte_size", errors
    )
    if rehearsal_verified_at < backup_created_at:
        errors.append("recovery rehearsal cannot predate the backup")
    expected_rpo = max(0, math.ceil((observed_at - backup_created_at).total_seconds() / 60))
    if rpo != expected_rpo:
        errors.append("recovery.rpo_minutes must equal the conservative backup age at observation")

    capacity = _exact_keys(evidence.get("capacity"), {
        "database_size_mib", "previous_database_size_mib", "artifact_versions",
        "previous_artifact_versions", "expected_services", "actual_services",
        "expected_jobs", "actual_jobs", "expected_schedulers", "actual_schedulers",
        "min_instances_zero", "explicit_max_instances", "review_reference",
    }, "capacity", errors)
    database_size = _positive_number(capacity.get("database_size_mib"), "capacity.database_size_mib", errors)
    previous_database_size = _positive_number(
        capacity.get("previous_database_size_mib"), "capacity.previous_database_size_mib", errors
    )
    artifact_versions = _non_negative_int(
        capacity.get("artifact_versions"), "capacity.artifact_versions", errors
    )
    previous_artifact_versions = _non_negative_int(
        capacity.get("previous_artifact_versions"), "capacity.previous_artifact_versions", errors
    )
    resource_pairs = []
    for name in ("services", "jobs", "schedulers"):
        expected = _non_negative_int(capacity.get(f"expected_{name}"), f"capacity.expected_{name}", errors)
        actual = _non_negative_int(capacity.get(f"actual_{name}"), f"capacity.actual_{name}", errors)
        resource_pairs.append((name, expected, actual))
    for field in ("min_instances_zero", "explicit_max_instances"):
        if not isinstance(capacity.get(field), bool):
            errors.append(f"capacity.{field} must be boolean")
    if not isinstance(capacity.get("review_reference"), str) or not capacity.get("review_reference"):
        errors.append("capacity.review_reference must be non-empty")

    sources = _exact_keys(evidence.get("source_contracts"), {
        "contract_count", "reviewed_contract_count", "approved_contract_count",
        "proposed_contract_count", "approved_unknown_rights_count",
        "approved_unknown_cost_count", "prohibited_collection_attempt_count",
        "terms_change_findings", "review_reference",
    }, "source_contracts", errors)
    source_counts = {
        field: _non_negative_int(sources.get(field), f"source_contracts.{field}", errors)
        for field in (
            "contract_count", "reviewed_contract_count", "approved_contract_count",
            "proposed_contract_count", "approved_unknown_rights_count",
            "approved_unknown_cost_count", "prohibited_collection_attempt_count",
            "terms_change_findings",
        )
    }
    if not isinstance(sources.get("review_reference"), str) or not sources.get("review_reference"):
        errors.append("source_contracts.review_reference must be non-empty")

    access = _exact_keys(evidence.get("access_control"), {
        "service_account_count", "secret_resource_count", "project_role_kind_count",
        "resource_policies_reviewed", "secret_payloads_read", "iam_mutated",
        "secret_mutated", "overbroad_finding_count", "review_reference",
    }, "access_control", errors)
    access_counts = {
        field: _non_negative_int(access.get(field), f"access_control.{field}", errors)
        for field in (
            "service_account_count", "secret_resource_count", "project_role_kind_count",
            "overbroad_finding_count",
        )
    }
    for field in ("resource_policies_reviewed", "secret_payloads_read", "iam_mutated", "secret_mutated"):
        if not isinstance(access.get(field), bool):
            errors.append(f"access_control.{field} must be boolean")
    if not isinstance(access.get("review_reference"), str) or not access.get("review_reference"):
        errors.append("access_control.review_reference must be non-empty")

    exceptions = _exact_keys(evidence.get("exceptions"), {
        "reconstruction_open_count", "owner_review_open_count",
        "governance_exception_count", "expired_governance_exception_count",
        "ownerless_governance_exception_count", "review_reference",
    }, "exceptions", errors)
    exception_counts = {
        field: _non_negative_int(exceptions.get(field), f"exceptions.{field}", errors)
        for field in (
            "reconstruction_open_count", "owner_review_open_count", "governance_exception_count",
            "expired_governance_exception_count", "ownerless_governance_exception_count",
        )
    }
    if not isinstance(exceptions.get("review_reference"), str) or not exceptions.get("review_reference"):
        errors.append("exceptions.review_reference must be non-empty")

    cost = evaluate_cost_snapshot(cost_snapshot, as_of=as_of)
    if errors:
        raise GuardrailValidationError(errors)

    reference_time = (as_of or datetime.now(UTC)).astimezone(UTC)
    blockers: list[str] = []
    actions: list[str] = list(cost.actions)
    if observed_at > reference_time:
        blockers.append("review evidence is dated in the future")
    review_age = (reference_time - observed_at).total_seconds() / 86_400
    if review_age > REVIEW_MAX_AGE_DAYS[cadence]:
        blockers.append(f"{cadence} review evidence is stale")
    if rpo > RPO_LIMIT_MINUTES:
        blockers.append("restore RPO exceeded 24 hours")
    if rto > RTO_LIMIT_SECONDS:
        blockers.append("restore RTO exceeded 4 hours")
    rehearsal_age = (reference_time - rehearsal_verified_at).total_seconds() / 86_400
    if rehearsal_age < 0:
        blockers.append("restore rehearsal is dated in the future")
    elif rehearsal_age > RESTORE_REHEARSAL_MAX_AGE_DAYS:
        blockers.append("restore rehearsal is older than the quarterly grace window")
    if not recovery["restricted_object_bytes_included"] and not recovery["private_object_recovery_verified"]:
        actions.append("verify_private_restricted_object_recovery_separately")

    for name, expected, actual in resource_pairs:
        if expected != actual:
            blockers.append(f"runtime {name} count drift: expected {expected}, actual {actual}")
    if not capacity["min_instances_zero"]:
        blockers.append("request-based services do not all use min-instances zero")
    if not capacity["explicit_max_instances"]:
        blockers.append("runtime targets do not all have explicit maximum instance caps")
    growth_percent = ((database_size - previous_database_size) / previous_database_size) * 100
    if growth_percent >= DATABASE_GROWTH_ATTENTION_PERCENT:
        actions.append("inspect_database_growth_at_or_above_25_percent")
    if artifact_versions - previous_artifact_versions > ARTIFACT_GROWTH_ATTENTION_COUNT:
        actions.append("inspect_artifact_growth_above_20_versions")

    if source_counts["reviewed_contract_count"] != source_counts["contract_count"]:
        blockers.append("not every source contract was reviewed")
    if source_counts["approved_contract_count"] + source_counts["proposed_contract_count"] != source_counts["contract_count"]:
        blockers.append("source lifecycle counts do not reconcile")
    if source_counts["approved_unknown_rights_count"]:
        blockers.append("approved source has unknown rights")
    if source_counts["approved_unknown_cost_count"]:
        blockers.append("approved source has unknown cost")
    if source_counts["prohibited_collection_attempt_count"]:
        blockers.append("a prohibited or proposed source was called")
    if source_counts["terms_change_findings"]:
        blockers.append("source terms changed and require contract review")

    if not access["resource_policies_reviewed"]:
        blockers.append("resource-scoped IAM policies were not reviewed")
    if access["secret_payloads_read"]:
        blockers.append("secret payloads were read during metadata review")
    if access["iam_mutated"] or access["secret_mutated"]:
        blockers.append("access review mutated IAM or Secrets")
    if access_counts["overbroad_finding_count"]:
        blockers.append("overbroad IAM findings require owner action")
    if exception_counts["expired_governance_exception_count"]:
        blockers.append("expired governance exceptions remain open")
    if exception_counts["ownerless_governance_exception_count"]:
        blockers.append("ownerless governance exceptions remain open")

    if cost.state in {"unknown", "ceiling"}:
        blockers.append(f"cost state is {cost.state}")
    elif cost.state != "normal":
        actions.append(f"apply_{cost.state}_cost_actions")
    if evidence["evidence_scope"] != "production_read_only":
        actions.append("replace_fixture_evidence_with_production_read_only_review")

    unique_actions = tuple(dict.fromkeys(actions))
    attention_actions = tuple(
        action for action in unique_actions if action != "continue_within_approved_limits"
    )
    status = "blocked" if blockers else ("attention" if attention_actions else "pass")
    return SteadyStateDecision(status, cadence, tuple(blockers), unique_actions, cost, rpo, rto)
