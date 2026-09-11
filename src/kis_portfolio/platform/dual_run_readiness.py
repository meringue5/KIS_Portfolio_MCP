"""Fail-closed V1/V2 dual-run readiness assessment.

This module evaluates supplied evidence only.  It never reads production systems,
changes traffic, restores data, or applies a release/cleanup action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from kis_portfolio.platform.production_guardrails import (
    CostDecision,
    GuardrailValidationError,
    evaluate_cost_snapshot,
    validate_release_manifest,
)


DUAL_RUN_SCHEMA = "kis-portfolio.dual-run-evidence/v1"
READINESS_SCHEMA = "kis-portfolio.dual-run-readiness/v1"
REQUIRED_METRICS = (
    "total_asset_krw",
    "holding_quantity",
    "orders",
    "prices",
    "signals",
    "freshness",
)
MINIMUM_TRADING_DAYS = 10
RPO_LIMIT_MINUTES = 24 * 60
RTO_LIMIT_MINUTES = 4 * 60
NORMAL_MONTH_TARGET_KRW = 7_500


@dataclass(frozen=True)
class ReadinessDecision:
    status: str
    blockers: tuple[str, ...]
    evidence_scope: str
    trading_days: int
    unexplained_differences: int
    explained_partial_gaps: int
    cost: CostDecision

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": READINESS_SCHEMA,
            "status": self.status,
            "evidence_scope": self.evidence_scope,
            "production_cutover_allowed": False,
            "trading_days": self.trading_days,
            "unexplained_differences": self.unexplained_differences,
            "explained_partial_gaps": self.explained_partial_gaps,
            "cost": self.cost.as_dict(),
            "blockers": list(self.blockers),
        }


def _number(value: Any, field: str, errors: list[str]) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors.append(f"{field} must be numeric")
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        errors.append(f"{field} must be numeric")
        return None


def _positive_int(value: Any, field: str, errors: list[str]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{field} must be a non-negative integer")
        return None
    return value


def assess_dual_run_readiness(
    evidence: Mapping[str, Any],
    release_manifest: Mapping[str, Any],
    cost_snapshot: Mapping[str, Any],
    *,
    as_of=None,
) -> ReadinessDecision:
    """Validate captured evidence and return a non-authorizing readiness decision."""

    errors: list[str] = []
    allowed = {"schema_version", "evidence_scope", "sessions", "restore", "schedule"}
    extras = sorted(set(evidence) - allowed)
    if extras:
        errors.append("evidence has unsupported fields: " + ", ".join(extras))
    if evidence.get("schema_version") != DUAL_RUN_SCHEMA:
        errors.append(f"schema_version must be {DUAL_RUN_SCHEMA}")
    scope = evidence.get("evidence_scope")
    if scope not in {"fixture_only", "production_observation"}:
        errors.append("evidence_scope must be fixture_only or production_observation")

    sessions = evidence.get("sessions")
    if not isinstance(sessions, list):
        errors.append("sessions must be a list")
        sessions = []
    seen_dates: set[date] = set()
    unexplained = 0
    partial = 0
    for index, session in enumerate(sessions):
        field = f"sessions[{index}]"
        if not isinstance(session, Mapping):
            errors.append(f"{field} must be an object")
            continue
        if set(session) != {"trading_date", "metrics"}:
            errors.append(f"{field} must contain only trading_date and metrics")
        try:
            trading_date = date.fromisoformat(session.get("trading_date", ""))
        except (TypeError, ValueError):
            errors.append(f"{field}.trading_date must be ISO date")
            trading_date = None
        if trading_date is not None:
            if trading_date in seen_dates:
                errors.append(f"duplicate trading_date {trading_date.isoformat()}")
            seen_dates.add(trading_date)
        metrics = session.get("metrics")
        if not isinstance(metrics, Mapping):
            errors.append(f"{field}.metrics must be an object")
            continue
        if set(metrics) != set(REQUIRED_METRICS):
            errors.append(f"{field}.metrics must contain the exact required metric set")
        for metric in REQUIRED_METRICS:
            item = metrics.get(metric)
            metric_field = f"{field}.metrics.{metric}"
            if not isinstance(item, Mapping):
                errors.append(f"{metric_field} must be an object")
                continue
            status = item.get("status")
            if status == "match":
                if set(item) != {"status", "v1", "v2", "tolerance"}:
                    errors.append(f"{metric_field} match fields are invalid")
                    continue
                left = _number(item.get("v1"), f"{metric_field}.v1", errors)
                right = _number(item.get("v2"), f"{metric_field}.v2", errors)
                tolerance = _number(item.get("tolerance"), f"{metric_field}.tolerance", errors)
                if tolerance is not None and tolerance < 0:
                    errors.append(f"{metric_field}.tolerance must be non-negative")
                if None not in (left, right, tolerance) and abs(left - right) > tolerance:
                    unexplained += 1
            elif status == "partial":
                if set(item) != {"status", "quality_reason", "missing_coverage"}:
                    errors.append(f"{metric_field} partial fields are invalid")
                    continue
                reason = item.get("quality_reason")
                coverage = item.get("missing_coverage")
                if not isinstance(reason, str) or not reason.strip():
                    errors.append(f"{metric_field}.quality_reason must be non-empty")
                if not isinstance(coverage, list) or not coverage or any(
                    not isinstance(value, str) or not value for value in coverage
                ):
                    errors.append(f"{metric_field}.missing_coverage must be a non-empty string list")
                partial += 1
            elif status == "difference":
                if set(item) != {"status", "v1", "v2", "tolerance"}:
                    errors.append(f"{metric_field} difference fields are invalid")
                else:
                    _number(item.get("v1"), f"{metric_field}.v1", errors)
                    _number(item.get("v2"), f"{metric_field}.v2", errors)
                    _number(item.get("tolerance"), f"{metric_field}.tolerance", errors)
                unexplained += 1
            else:
                errors.append(f"{metric_field}.status is unsupported")

    schedule = evidence.get("schedule")
    if not isinstance(schedule, Mapping) or set(schedule) != {
        "required_runs", "successful_runs", "duplicate_deliveries"
    }:
        errors.append("schedule must contain exact run and duplicate counters")
        schedule = {}
    required_runs = _positive_int(schedule.get("required_runs"), "schedule.required_runs", errors)
    successful_runs = _positive_int(schedule.get("successful_runs"), "schedule.successful_runs", errors)
    duplicates = _positive_int(
        schedule.get("duplicate_deliveries"), "schedule.duplicate_deliveries", errors
    )

    restore = evidence.get("restore")
    if not isinstance(restore, Mapping) or set(restore) != {
        "result", "rpo_minutes", "rto_minutes", "reference"
    }:
        errors.append("restore must contain exact result, RPO, RTO and reference fields")
        restore = {}
    rpo = _positive_int(restore.get("rpo_minutes"), "restore.rpo_minutes", errors)
    rto = _positive_int(restore.get("rto_minutes"), "restore.rto_minutes", errors)
    if restore.get("result") != "pass":
        errors.append("restore.result must be pass")
    if not isinstance(restore.get("reference"), str) or not restore.get("reference"):
        errors.append("restore.reference must be non-empty")

    # These validators also prove target-specific immutable digests and current cost contract shape.
    validate_release_manifest(release_manifest)
    cost = evaluate_cost_snapshot(cost_snapshot, as_of=as_of)
    if errors:
        raise GuardrailValidationError(errors)

    blockers: list[str] = []
    if len(seen_dates) < MINIMUM_TRADING_DAYS:
        blockers.append("fewer than 10 unique trading days")
    if unexplained:
        blockers.append(f"unexplained V1/V2 differences: {unexplained}")
    if required_runs != successful_runs:
        blockers.append("required schedule runs did not all succeed")
    if duplicates:
        blockers.append("duplicate deliveries were observed")
    if rpo is not None and rpo > RPO_LIMIT_MINUTES:
        blockers.append("restore RPO exceeded 24 hours")
    if rto is not None and rto > RTO_LIMIT_MINUTES:
        blockers.append("restore RTO exceeded 4 hours")
    if cost.evaluated_krw is None or cost.evaluated_krw > NORMAL_MONTH_TARGET_KRW:
        blockers.append("normal-month cost exceeded the 7500 KRW target")
    if cost.state == "unknown":
        blockers.append("cost evidence is unknown")
    if scope != "production_observation":
        blockers.append("fixture evidence cannot satisfy the production dual-run gate")

    return ReadinessDecision(
        status="pass" if not blockers else "blocked",
        blockers=tuple(blockers),
        evidence_scope=scope,
        trading_days=len(seen_dates),
        unexplained_differences=unexplained,
        explained_partial_gaps=partial,
        cost=cost,
    )
