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
PRIOR_REAL_USE_RULE_VERSION = "rc-2026-09-03.1"
REAL_USE_RULE_VERSION = "rc-2026-09-03.2"
REAL_USE_VALID_FROM = datetime(2026, 9, 3, 0, 0, tzinfo=SEOUL).astimezone(UTC)
REAL_USE_VALID_TO = datetime(2026, 9, 10, 0, 0, tzinfo=SEOUL).astimezone(UTC)
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


def real_use_rule() -> AlertRuleVersion:
    """Return the immutable DEC-051 production-value release candidate."""
    return AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": REAL_USE_RULE_VERSION,
        "status": "active",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "external",
        "initial_active_policy": "baseline_only",
        "valid_from": REAL_USE_VALID_FROM,
        "valid_to": REAL_USE_VALID_TO,
        "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
        "thresholds": {
            "profile": "bootstrap-package-d",
            "absolute_boundary_multiplier": str(THRESHOLD_MULTIPLIER),
            "calibration_report_hash": CALIBRATION_REPORT_HASH,
        },
        "limitations": [
            "stabilized production-value release candidate",
            "initial active state is baseline-only and not a market event",
            "intraday KRX volume is unavailable until same-slot normalization exists",
            "episode drawdown unavailable until governed metric readiness passes",
            "KRW valuation-change contribution unavailable until comparable-state readiness passes",
            "ETF constituent exposure unavailable",
            "no automatic promotion",
        ],
    })


def prior_real_use_rule() -> AlertRuleVersion:
    """Return the preserved DEC-051 rule document used before stabilization."""
    return AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": PRIOR_REAL_USE_RULE_VERSION,
        "status": "active",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "external",
        "valid_from": REAL_USE_VALID_FROM,
        "valid_to": REAL_USE_VALID_TO,
        "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
        "thresholds": {
            "profile": "bootstrap-package-d",
            "absolute_boundary_multiplier": str(THRESHOLD_MULTIPLIER),
            "calibration_report_hash": CALIBRATION_REPORT_HASH,
        },
        "limitations": [
            "production-value release candidate",
            "episode drawdown unavailable until governed metric readiness passes",
            "KRW valuation-change contribution unavailable until comparable-state readiness passes",
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
) -> dict[str, tuple[str, str, str]]:
    rows = connection.execute(
        """
        SELECT DISTINCT p.instrument_id,i.asset_type,i.market,i.name
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
        str(instrument_id): (_asset_class(asset_type), str(name or ""), str(market))
        for instrument_id, asset_type, market, name in rows
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
    for instrument_id, metadata in held.items():
        asset_class, subject_label, market = metadata
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
                subject_label=subject_label,
                market=market,
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
            subject_label=subject_label,
            market=market,
            volume_ratio20=(
                None if evaluation_slot in {"kr-1000", "kr-1430"}
                else item.volume_ratio20
            ),
        ))
    return tuple(target)


_REASON_LABELS = {
    "price_shock_up": "당일 급등 기준을 넘었습니다",
    "price_shock_down": "당일 급락 기준을 넘었습니다",
    "portfolio_contribution": "포트폴리오 원화 기준 변화 기여가 큽니다",
    "episode_drawdown": "보유구간 고점 대비 낙폭 기준을 넘었습니다",
    "thread_stop_breach": "사용자가 정한 손절 기준을 이탈했습니다",
    "thread_risk_ratio": "계획손실 비율 기준을 넘었습니다",
    "sma20_downward_cross": "주가가 오늘 20일선을 하향 이탈했습니다",
    "bearish_sma20_regime": "주가가 20일선을 하회하는 약세 상태입니다",
    "bearish_sma50_drawdown": "중기 하락추세와 보유구간 낙폭이 함께 확인됐습니다",
    "volume_confirmation": "평균보다 많은 거래량이 가격 변화를 확인했습니다",
}
_MARKET_LABELS = {"KRX": "국내", "NAS": "미국 NASDAQ", "NYS": "미국 NYSE", "AMS": "미국 AMEX"}
_ASSET_LABELS = {
    "stock": "주식", "etf": "ETF", "reit": "REIT", "leveraged": "레버리지",
    "inverse": "인버스", "unknown": "분류 확인 필요",
}


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _percent_text(value: Decimal | None) -> str | None:
    return None if value is None else _decimal_text(value * Decimal("100"))


def _relation(close: Decimal | None, average: Decimal | None) -> str:
    if close is None or average is None:
        return "unavailable"
    if close < average:
        return "below"
    if close > average:
        return "above"
    return "equal"


def _production_value_context(observation: SignalObservation, decision: Any) -> dict[str, object]:
    reasons = list(decision.reason_codes) or ["state_change"]
    labels = [_REASON_LABELS.get(code, "유의미한 상태 변화가 감지됐습니다") for code in reasons]
    bollinger = "unavailable"
    if observation.bollinger_percent_b is not None:
        if observation.bollinger_percent_b <= 0:
            bollinger = "below_lower"
        elif observation.bollinger_percent_b >= 1:
            bollinger = "above_upper"
        else:
            bollinger = "inside"
    unavailable: list[str] = []
    if observation.episode_drawdown is None:
        unavailable.append("episode_drawdown_not_ready")
    if observation.portfolio_contribution is None:
        unavailable.append("valuation_contribution_not_ready")
    if observation.evaluation_slot in {"kr-1000", "kr-1430"}:
        unavailable.append("intraday_volume_not_comparable")
    source_at = observation.input_known_at or observation.evaluation_at
    return {
        "presentation_version": "production-value-v2",
        "subject_label": observation.subject_label or "식별정보 확인 필요",
        "market_label": _MARKET_LABELS.get(observation.market, observation.market or "시장 확인 필요"),
        "asset_type_label": _ASSET_LABELS.get(observation.asset_class, "분류 확인 필요"),
        "summary": " · ".join(dict.fromkeys(labels)),
        "reason_codes": reasons,
        "change_percent": _percent_text(observation.daily_return),
        "sma20_relation": _relation(observation.close, observation.sma20),
        "sma50_relation": _relation(observation.close, observation.sma50),
        "sma120_relation": _relation(observation.close, observation.sma120),
        "sma20_sma50_relation": _relation(observation.sma20, observation.sma50),
        "volume_ratio20": _decimal_text(observation.volume_ratio20),
        "rsi14": _decimal_text(observation.rsi14),
        "bollinger_state": bollinger,
        "episode_drawdown_percent": _percent_text(observation.episode_drawdown),
        "portfolio_impact_percent": _percent_text(observation.portfolio_contribution),
        "unavailable_codes": unavailable,
        "source_at": source_at.isoformat(),
        "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
        "quality_status": decision.quality_status,
    }


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
    if rule.version == REAL_USE_RULE_VERSION:
        public_context = _production_value_context(observation, decision)
    else:
        public_context = {
            "subject_label": "보유 종목",
            "summary": "가격·추세·거래량 기반 DB-only shadow 평가",
            "reason_codes": list(reasons),
            "change_percent": change_percent,
            "metric_refs": ["price-shock", "sma-volume", "rsi14", "bollinger20"],
            "quality_status": decision.quality_status,
        }
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
        public_context=public_context,
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


def run_external_real_use_signal_evaluation(
    connection: duckdb.DuckDBPyConnection,
    *,
    logical_date: date,
    source_slot: str,
) -> dict[str, Any]:
    """Create DEC-051 production-value release-candidate alerts."""
    rule = real_use_rule()
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
    result["transport"] = "telegram-production-value-rc-pending"
    return result
