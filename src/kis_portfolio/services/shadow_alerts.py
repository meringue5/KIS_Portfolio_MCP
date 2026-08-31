"""DB-only production shadow evaluation composed after governed portfolio collection."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.application.signal_replay import load_price_replay_observations
from kis_portfolio.modules.monitoring import (
    AlertCandidate,
    AlertEvaluation,
    AlertRuleVersion,
    SignalObservation,
    ThresholdProfile,
    evaluate_bootstrap_signal,
)
from kis_portfolio.platform.migrations import MigrationRunner


SEOUL = ZoneInfo("Asia/Seoul")
RULE_ID = "rule-set.owned-portfolio-monitoring"
RULE_VERSION = "bootstrap-1.0.0"
CANARY_RULE_VERSION = "canary-2026-09-01.1"
CANARY_VALID_FROM = datetime(2026, 9, 1, 0, 0, tzinfo=SEOUL).astimezone(UTC)
CANARY_VALID_TO = datetime(2026, 9, 8, 0, 0, tzinfo=SEOUL).astimezone(UTC)
CALIBRATION_REPORT_HASH = "a9048d06d758d5923899f15f2a6a034e9bb5f2b7e9efc2844706df6ebf13dc8d"
THRESHOLD_MULTIPLIER = Decimal("0.75")
US_MARKETS = frozenset({"NAS", "NYS", "AMS"})
KR_SLOTS = frozenset({"kr-1000", "kr-1430", "kr-1600"})


def _rule() -> AlertRuleVersion:
    return AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": RULE_VERSION,
        "status": "approved",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "shadow",
        "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
        "valid_to": None,
        "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
        "thresholds": {
            "profile": "bootstrap-package-d",
            "absolute_boundary_multiplier": str(THRESHOLD_MULTIPLIER),
            "calibration_report_hash": CALIBRATION_REPORT_HASH,
        },
        "limitations": ["ETF constituent exposure unavailable", "shadow only"],
    })


def canary_rule() -> AlertRuleVersion:
    """Return the immutable DEC-050 bounded external rule."""
    return AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": CANARY_RULE_VERSION,
        "status": "active",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "external",
        "valid_from": CANARY_VALID_FROM,
        "valid_to": CANARY_VALID_TO,
        "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
        "thresholds": {
            "profile": "bootstrap-package-d",
            "absolute_boundary_multiplier": str(THRESHOLD_MULTIPLIER),
            "calibration_report_hash": CALIBRATION_REPORT_HASH,
        },
        "limitations": [
            "experimental bounded canary",
            "ETF constituent exposure unavailable",
            "no automatic promotion",
        ],
    })


def _fixed_slot_time(logical_date: date, slot: str) -> datetime:
    wall = {
        "kr-1000": time(10, 0),
        "kr-1430": time(14, 30),
        "kr-1600": time(16, 0),
        "us-close": time(10, 0),
    }[slot]
    return datetime.combine(logical_date, wall, tzinfo=SEOUL).astimezone(UTC)


def _asset_class(value: object) -> str:
    return {
        "equity": "stock",
        "stock": "stock",
        "etf": "etf",
        "reit": "reit",
        "leveraged": "leveraged",
        "leveraged_etf": "leveraged",
        "inverse": "inverse",
        "inverse_etf": "inverse",
    }.get(str(value or "unknown").strip().lower(), "unknown")


def _held_instruments(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
    evaluation_slot: str,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT DISTINCT p.instrument_id,i.asset_type,i.market
        FROM gold.portfolio_daily_state p
        JOIN silver.instruments_current i USING(instrument_id)
        WHERE p.evaluation_date=? AND p.evaluation_slot=?
          AND p.aggregate_level='position' AND p.quantity>0
        ORDER BY p.instrument_id
        """,
        [logical_date, source_slot],
    ).fetchall()
    wanted_us = evaluation_slot == "us-close"
    return {
        str(instrument_id): _asset_class(asset_type)
        for instrument_id, asset_type, market in rows
        if (str(market) in US_MARKETS) == wanted_us
    }


def _target_observations(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
    evaluation_slot: str,
) -> tuple[SignalObservation, ...]:
    held = _held_instruments(
        connection,
        logical_date=logical_date,
        source_slot=source_slot,
        evaluation_slot=evaluation_slot,
    )
    if not held:
        return ()
    history = load_price_replay_observations(
        connection,
        start_date=logical_date - timedelta(days=240),
        end_date=logical_date,
        price_basis="adjusted",
    )
    by_subject: dict[str, SignalObservation] = {}
    for item in history:
        if item.subject_id not in held:
            continue
        if evaluation_slot != "us-close" and item.evaluation_at.date() != logical_date:
            continue
        prior = by_subject.get(item.subject_id)
        if prior is None or item.evaluation_at > prior.evaluation_at:
            by_subject[item.subject_id] = item

    target: list[SignalObservation] = []
    fixed_at = _fixed_slot_time(logical_date, evaluation_slot)
    for instrument_id, asset_class in held.items():
        item = by_subject.get(instrument_id)
        if item is None:
            target.append(SignalObservation(
                subject_id=instrument_id,
                asset_class=asset_class,
                evaluation_at=fixed_at,
                evaluation_slot=evaluation_slot,
                session_key=(
                    f"us-close:missing:{logical_date.isoformat()}"
                    if evaluation_slot == "us-close" else f"krx:{logical_date.isoformat()}"
                ),
                quality_status="missing_current_price",
                provenance_mode="historical_live",
                valid_bar_count=0,
            ))
            continue
        quality = item.quality_status
        if item.provenance_mode != "historical_live":
            quality = "reconstructed_not_live"
        if asset_class == "unknown":
            quality = "unknown_asset_class"
        session_date = item.evaluation_at.date()
        known_at = item.input_known_at or fixed_at
        target.append(replace(
            item,
            asset_class=asset_class,
            evaluation_at=known_at,
            evaluation_slot=evaluation_slot,
            session_key=(
                f"us-close:{session_date.isoformat()}"
                if evaluation_slot == "us-close" else f"krx:{logical_date.isoformat()}"
            ),
            quality_status=quality,
        ))
    return tuple(target)


def _candidate(
    observation: SignalObservation,
    *,
    logical_date: date,
    run_id: str,
    rule: AlertRuleVersion,
) -> AlertCandidate:
    decision = evaluate_bootstrap_signal(
        observation,
        ThresholdProfile(observation.asset_class, THRESHOLD_MULTIPLIER),
    )
    active = decision.delivery_eligible
    reasons = decision.reason_codes or tuple(
        code for code in decision.context_codes if code.startswith("quality:")
    ) or ("normal",)
    state_key = ":".join(reasons)
    change_percent = (
        None
        if observation.daily_return is None
        else format((observation.daily_return * Decimal("100")).quantize(Decimal("0.01")), "f")
    )
    return AlertCandidate.build(rule, AlertEvaluation(
        subject_type="instrument",
        subject_id=observation.subject_id,
        evaluation_date=logical_date,
        evaluation_slot=observation.evaluation_slot,
        session_key=observation.session_key,
        evaluation_at=observation.evaluation_at,
        signal_state="active" if active else "normal",
        severity=decision.severity,
        state_key=state_key,
        quality_status=decision.quality_status,
        input_lineage_hash=observation.input_lineage_hash or hashlib.sha256(
            f"missing|{observation.subject_id}|{observation.session_key}".encode()
        ).hexdigest(),
        public_context={
            "subject_label": "보유 종목",
            "summary": "가격·추세·거래량 기반 DB-only shadow 평가",
            "reason_codes": list(reasons),
            "change_percent": change_percent,
            "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
            "quality_status": decision.quality_status,
        },
        evaluation_run_id=run_id,
    ))


def _run_signal_evaluation(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
    rule: AlertRuleVersion,
    shadow_claims: bool,
) -> dict[str, Any]:
    """Evaluate one rule without performing an external network request."""
    if source_slot not in KR_SLOTS:
        raise ValueError("shadow source slot is not governed")
    MigrationRunner(connection).require("0013")
    repository = AlertWarehouseRepository(connection)
    repository.register_rule(rule)
    slots = (source_slot, "us-close") if source_slot == "kr-1000" else (source_slot,)
    run_id = hashlib.sha256(
        f"signal-evaluation-v1|{logical_date}|{source_slot}|{rule.version}".encode()
    ).hexdigest()
    totals = {
        "candidate_count": 0,
        "transition_count": 0,
        "shadow_claim_count": 0,
        "quality_suppressed_count": 0,
    }
    slot_counts: dict[str, int] = {}
    for evaluation_slot in slots:
        observations = _target_observations(
            connection,
            logical_date=logical_date,
            source_slot=source_slot,
            evaluation_slot=evaluation_slot,
        )
        slot_counts[evaluation_slot] = len(observations)
        for observation in observations:
            candidate = _candidate(observation, logical_date=logical_date, run_id=run_id, rule=rule)
            write = repository.apply_candidate(candidate)
            totals["candidate_count"] += 1
            if candidate.evaluation.quality_status != "pass":
                totals["quality_suppressed_count"] += 1
            if write.transition is None:
                continue
            totals["transition_count"] += 1
            if not write.transition.delivery_required or not shadow_claims:
                continue
            lease_token = hashlib.sha256(f"shadow-lease|{candidate.candidate_id}|{run_id}".encode()).hexdigest()
            claim = repository.claim_dispatch(
                candidate_id=candidate.candidate_id,
                channel="shadow",
                destination_ref="shadow.owner",
                claimant_id="worker.shadow.v1",
                lease_token=lease_token,
                claimed_at=candidate.evaluation.evaluation_at,
            )
            if not claim.acquired:
                continue
            repository.record_attempt(
                dispatch_id=claim.dispatch_id,
                lease_token=lease_token,
                outcome="sent",
                started_at=candidate.evaluation.evaluation_at,
                completed_at=candidate.evaluation.evaluation_at,
                response_ref="db-only-shadow",
            )
            totals["shadow_claim_count"] += 1
    return {
        "status": "succeeded",
        "logical_date": logical_date.isoformat(),
        "source_slot": source_slot,
        "evaluation_slots": list(slots),
        "slot_candidate_counts": slot_counts,
        **totals,
        "external_send_count": 0,
        "transport": "db-only-shadow",
        "rule_version": rule.version,
        "run_id": run_id,
    }


def run_shadow_signal_evaluation(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
) -> dict[str, Any]:
    """Evaluate the permanent DB-only shadow rule."""
    return _run_signal_evaluation(
        connection,
        logical_date=logical_date,
        source_slot=source_slot,
        rule=_rule(),
        shadow_claims=True,
    )


def run_external_canary_signal_evaluation(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
) -> dict[str, Any]:
    """Create bounded external candidates; Telegram delivery remains a later stage."""
    rule = canary_rule()
    slots = (source_slot, "us-close") if source_slot == "kr-1000" else (source_slot,)
    evaluation_times = tuple(_fixed_slot_time(logical_date, slot) for slot in slots)
    if all(value < rule.valid_from for value in evaluation_times):
        return {
            "status": "not_yet_valid",
            "logical_date": logical_date.isoformat(),
            "source_slot": source_slot,
            "rule_version": rule.version,
            "candidate_count": 0,
        }
    if all(rule.valid_to is not None and value >= rule.valid_to for value in evaluation_times):
        return {
            "status": "expired",
            "logical_date": logical_date.isoformat(),
            "source_slot": source_slot,
            "rule_version": rule.version,
            "candidate_count": 0,
        }
    result = _run_signal_evaluation(
        connection,
        logical_date=logical_date,
        source_slot=source_slot,
        rule=rule,
        shadow_claims=False,
    )
    result["transport"] = "telegram-canary-pending"
    return result
