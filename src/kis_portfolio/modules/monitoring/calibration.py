"""Deterministic bootstrap signal replay and asset-class calibration primitives."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Mapping


SEVERITY_RANK = {"normal": 0, "watch": 1, "warning": 2, "critical": 3}
RANK_SEVERITY = {rank: severity for severity, rank in SEVERITY_RANK.items()}
ASSET_CLASSES = frozenset({"stock", "etf", "reit", "leveraged", "inverse", "unknown"})
PROVENANCE_MODES = frozenset({"historical_live", "retrospective_reconstructed"})
PASS_QUALITY = "pass"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _opaque(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


@dataclass(frozen=True, slots=True)
class ThresholdProfile:
    asset_class: str
    absolute_boundary_multiplier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError("unsupported asset class")
        if self.absolute_boundary_multiplier <= 0:
            raise ValueError("threshold multiplier must be positive")


@dataclass(frozen=True, slots=True)
class SignalObservation:
    subject_id: str
    asset_class: str
    evaluation_at: datetime
    evaluation_slot: str
    session_key: str
    quality_status: str
    provenance_mode: str
    valid_bar_count: int
    daily_return: Decimal | None = None
    vol20: Decimal | None = None
    portfolio_contribution: Decimal | None = None
    episode_drawdown: Decimal | None = None
    volume_ratio20: Decimal | None = None
    close: Decimal | None = None
    sma20: Decimal | None = None
    sma50: Decimal | None = None
    sma120: Decimal | None = None
    rsi14: Decimal | None = None
    bollinger_percent_b: Decimal | None = None
    risk_ratio: Decimal | None = None
    stop_breached: bool = False
    input_lineage_hash: str = ""
    input_known_at: datetime | None = None
    subject_label: str = ""
    market: str = ""

    def __post_init__(self) -> None:
        if not self.subject_id.strip() or not self.session_key.strip():
            raise ValueError("signal observation requires opaque subject and session identity")
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError("unsupported asset class")
        if self.provenance_mode not in PROVENANCE_MODES:
            raise ValueError("unknown replay provenance")
        if self.evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        if self.input_known_at is not None and self.input_known_at.tzinfo is None:
            raise ValueError("input_known_at must be timezone-aware")
        if self.valid_bar_count < 0:
            raise ValueError("valid_bar_count cannot be negative")


@dataclass(frozen=True, slots=True)
class SignalDecision:
    severity: str
    reason_codes: tuple[str, ...]
    context_codes: tuple[str, ...]
    quality_status: str
    adverse_score: Decimal

    @property
    def delivery_eligible(self) -> bool:
        return self.quality_status == PASS_QUALITY and SEVERITY_RANK[self.severity] >= 1


def _severity_for_absolute(
    value: Decimal,
    *,
    watch: Decimal,
    warning: Decimal,
    critical: Decimal,
) -> int:
    absolute = abs(value)
    if absolute >= critical:
        return 3
    if absolute >= warning:
        return 2
    if absolute >= watch:
        return 1
    return 0


def evaluate_bootstrap_signal(
    observation: SignalObservation,
    profile: ThresholdProfile,
) -> SignalDecision:
    if observation.asset_class != profile.asset_class:
        raise ValueError("threshold profile does not match observation asset class")
    if observation.quality_status != PASS_QUALITY:
        return SignalDecision(
            "normal", (), (f"quality:{observation.quality_status}",),
            observation.quality_status, Decimal("0"),
        )
    multiplier = profile.absolute_boundary_multiplier
    rank = 0
    reasons: list[str] = []
    context: list[str] = []
    adverse_scores: list[Decimal] = [Decimal("0")]
    price_rank = 0

    if observation.daily_return is not None:
        volatility_ready = observation.valid_bar_count >= 20 and observation.vol20 is not None
        vol = observation.vol20 if volatility_ready else None
        watch = max(Decimal("0.03") * multiplier, Decimal("2") * vol) if vol is not None else Decimal("0.03") * multiplier
        warning = max(Decimal("0.05") * multiplier, Decimal("3") * vol) if vol is not None else Decimal("0.05") * multiplier
        critical = max(Decimal("0.08") * multiplier, Decimal("4") * vol) if vol is not None else Decimal("0.08") * multiplier
        price_rank = _severity_for_absolute(
            observation.daily_return, watch=watch, warning=warning, critical=critical
        )
        if price_rank:
            reasons.append(
                f"price_shock_{'up' if observation.daily_return > 0 else 'down'}"
            )
        rank = max(rank, price_rank)
        if observation.daily_return < 0:
            adverse_scores.append(abs(observation.daily_return) / watch)
        if not volatility_ready:
            context.append("volatility_insufficient_history")

    if observation.portfolio_contribution is not None:
        contribution_rank = _severity_for_absolute(
            observation.portfolio_contribution,
            watch=Decimal("0.0025") * multiplier,
            warning=Decimal("0.0075") * multiplier,
            critical=Decimal("0.015") * multiplier,
        )
        if contribution_rank:
            reasons.append("portfolio_contribution")
        rank = max(rank, contribution_rank)
        if observation.portfolio_contribution < 0:
            adverse_scores.append(
                abs(observation.portfolio_contribution) / (Decimal("0.0025") * multiplier)
            )

    drawdown_rank = 0
    if observation.episode_drawdown is not None and observation.episode_drawdown < 0:
        drawdown_rank = _severity_for_absolute(
            observation.episode_drawdown,
            watch=Decimal("0.08") * multiplier,
            warning=Decimal("0.12") * multiplier,
            critical=Decimal("0.20") * multiplier,
        )
        if drawdown_rank:
            reasons.append("episode_drawdown")
        rank = max(rank, drawdown_rank)
        adverse_scores.append(
            abs(observation.episode_drawdown) / (Decimal("0.08") * multiplier)
        )

    if observation.stop_breached:
        rank = 3
        reasons.append("thread_stop_breach")
        adverse_scores.append(Decimal("2"))
    elif observation.risk_ratio is not None:
        risk_rank = _severity_for_absolute(
            observation.risk_ratio,
            watch=Decimal("0.015"), warning=Decimal("0.020"), critical=Decimal("0.025"),
        )
        if risk_rank:
            reasons.append("thread_risk_ratio")
        rank = max(rank, risk_rank)
        adverse_scores.append(observation.risk_ratio / Decimal("0.015"))

    price_below_sma20 = (
        observation.close is not None
        and observation.sma20 is not None
        and observation.close < observation.sma20
    )
    bearish_cross = (
        observation.sma20 is not None
        and observation.sma50 is not None
        and observation.sma20 < observation.sma50
    )
    close_below_sma50 = (
        observation.close is not None
        and observation.sma50 is not None
        and observation.close < observation.sma50
    )
    volume_ready = observation.valid_bar_count >= 20 and observation.volume_ratio20 is not None
    high_volume = volume_ready and observation.volume_ratio20 >= Decimal("1.5")
    if high_volume:
        context.append("high_volume")
    if price_below_sma20:
        context.append("below_sma20")
        if rank >= 1 or high_volume or bearish_cross:
            rank = max(rank, 1)
            reasons.append("confirmed_sma20_break")
    if close_below_sma50 and bearish_cross and drawdown_rank >= 1:
        rank = max(rank, 2)
        reasons.append("bearish_sma50_drawdown")
    if price_rank >= 1 and high_volume:
        rank = min(3, rank + 1)
        reasons.append("volume_confirmation")
    if observation.sma120 is not None and observation.close is not None and observation.close < observation.sma120:
        context.append("below_sma120")
    if observation.rsi14 is not None:
        if observation.rsi14 <= 30:
            context.append("rsi14_below_30")
        elif observation.rsi14 >= 70:
            context.append("rsi14_above_70")
    if observation.bollinger_percent_b is not None:
        if observation.bollinger_percent_b <= 0:
            context.append("bollinger_below_lower")
        elif observation.bollinger_percent_b >= 1:
            context.append("bollinger_above_upper")

    return SignalDecision(
        RANK_SEVERITY[rank], tuple(sorted(set(reasons))), tuple(sorted(set(context))),
        PASS_QUALITY, max(adverse_scores),
    )


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    rule_set_id: str
    rule_set_version: str
    selected_profiles: Mapping[str, ThresholdProfile]
    report: Mapping[str, object]
    report_hash: str


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _delivery_transitions(
    decisions: list[tuple[SignalObservation, SignalDecision]],
) -> list[tuple[SignalObservation, SignalDecision, str, str]]:
    """Apply the WI-028 state semantics without persistence for replay budgeting."""
    current: dict[str, tuple[str, tuple[str, ...], bool]] = {}
    deliveries: list[tuple[SignalObservation, SignalDecision, str, str]] = []
    for item, decision in sorted(
        decisions, key=lambda pair: (pair[0].evaluation_at, pair[0].evaluation_slot, pair[0].subject_id)
    ):
        if decision.quality_status != PASS_QUALITY:
            continue
        active = decision.delivery_eligible
        prior = current.get(item.subject_id)
        if prior is None:
            if active:
                deliveries.append((item, decision, "entered", decision.severity))
            current[item.subject_id] = (decision.severity, decision.reason_codes, active)
            continue
        prior_severity, prior_reasons, prior_active = prior
        transition: str | None = None
        delivery_severity = decision.severity
        if prior_active and not active:
            transition = "recovered"
            delivery_severity = prior_severity
        elif not prior_active and active:
            transition = "reentered"
        elif prior_active and active:
            if SEVERITY_RANK[decision.severity] > SEVERITY_RANK[prior_severity]:
                transition = "escalated"
            elif decision.severity == prior_severity and decision.reason_codes != prior_reasons:
                transition = "updated"
        if transition is not None:
            deliveries.append((item, decision, transition, delivery_severity))
        current[item.subject_id] = (decision.severity, decision.reason_codes, active)
    return deliveries


def _profile_report(
    observations: tuple[SignalObservation, ...],
    profile: ThresholdProfile,
) -> dict[str, object]:
    decisions = [(item, evaluate_bootstrap_signal(item, profile)) for item in observations]
    eligible = [(item, decision) for item, decision in decisions if decision.quality_status == PASS_QUALITY]
    active_observations = [
        (item, decision) for item, decision in eligible if decision.delivery_eligible
    ]
    alerts = _delivery_transitions(decisions)
    counts: dict[tuple[str, str], int] = {
        (item.evaluation_at.date().isoformat(), item.evaluation_slot): 0
        for item, _decision in eligible
    }
    for item, _decision, _transition, _delivery_severity in alerts:
        key = (item.evaluation_at.date().isoformat(), item.evaluation_slot)
        counts[key] = counts.get(key, 0) + 1
    daily = list(counts.values())
    no_alert = [(item, decision) for item, decision in eligible if not decision.delivery_eligible]
    maximum_miss_proxy = max(no_alert, key=lambda pair: pair[1].adverse_score, default=None)
    by_severity = {
        severity: sum(decision.severity == severity for _item, decision in eligible)
        for severity in SEVERITY_RANK
    }
    observed_session_dates = {item.evaluation_at.date() for item, _decision in eligible}
    coverage_days = (
        max(observed_session_dates) - min(observed_session_dates)
    ).days if observed_session_dates else 0
    return {
        "asset_class": profile.asset_class,
        "absolute_boundary_multiplier": _decimal(profile.absolute_boundary_multiplier),
        "observation_count": len(observations),
        "eligible_count": len(eligible),
        "quality_suppressed_count": len(observations) - len(eligible),
        "observed_session_date_count": len(observed_session_dates),
        "calendar_coverage_days": coverage_days + 1 if observed_session_dates else 0,
        "three_year_coverage_ready": (
            profile.asset_class != "unknown"
            and coverage_days >= 1095
            and len(observed_session_dates) >= 600
        ),
        "active_observation_count": len(active_observations),
        "alert_count": len(alerts),
        "severity_counts": by_severity,
        "median_alerts_per_observed_slot": float(statistics.median(daily)) if daily else 0.0,
        "p95_alerts_per_observed_slot": _p95(daily),
        "alert_budget_pass": (float(statistics.median(daily)) if daily else 0.0) <= 2 and _p95(daily) <= 5,
        "maximum_miss_proxy": None if maximum_miss_proxy is None else {
            "subject_ref": _opaque(maximum_miss_proxy[0].subject_id),
            "session_key": maximum_miss_proxy[0].session_key,
            "adverse_score": _decimal(maximum_miss_proxy[1].adverse_score),
            "definition": "maximum adverse normalized observation below watch; not an owner-labelled miss",
        },
        "top_alert_review_refs": [
            {
                "subject_ref": _opaque(item.subject_id),
                "session_key": item.session_key,
                "severity": delivery_severity,
                "transition_type": transition,
                "reason_codes": list(decision.reason_codes),
            }
            for item, decision, transition, delivery_severity in sorted(
                alerts,
                key=lambda pair: (SEVERITY_RANK[pair[3]], pair[1].adverse_score),
                reverse=True,
            )[:20]
        ],
    }


def _budget_summary(
    observations: tuple[SignalObservation, ...],
    profiles: Mapping[str, ThresholdProfile],
) -> dict[str, object]:
    eligible = [item for item in observations if item.quality_status == PASS_QUALITY]
    counts: dict[tuple[str, str], int] = {
        (item.evaluation_at.date().isoformat(), item.evaluation_slot): 0 for item in eligible
    }
    alert_count = 0
    by_class: dict[str, int] = {asset_class: 0 for asset_class in profiles}
    decisions = [(item, evaluate_bootstrap_signal(item, profiles[item.asset_class])) for item in eligible]
    for item, _decision, _transition, _delivery_severity in _delivery_transitions(decisions):
        key = (item.evaluation_at.date().isoformat(), item.evaluation_slot)
        counts[key] += 1
        alert_count += 1
        by_class[item.asset_class] += 1
    daily = list(counts.values())
    median = float(statistics.median(daily)) if daily else 0.0
    p95 = _p95(daily)
    return {
        "alert_count": alert_count,
        "alerts_by_asset_class": by_class,
        "median_alerts_per_observed_slot": median,
        "p95_alerts_per_observed_slot": p95,
        "alert_budget_pass": median <= 2 and p95 <= 5,
    }


def calibrate_replay(
    observations: Iterable[SignalObservation],
    *,
    rule_set_id: str = "rule-set.owned-portfolio-monitoring",
    rule_set_version: str = "bootstrap-1.0.0",
    multiplier_grid: tuple[Decimal, ...] = (
        Decimal("0.75"), Decimal("1"), Decimal("1.25"), Decimal("1.5"), Decimal("2")
    ),
) -> CalibrationResult:
    selected = tuple(sorted(observations, key=lambda item: (
        item.evaluation_at, item.evaluation_slot, item.subject_id
    )))
    if not selected:
        raise ValueError("calibration requires observations")
    if not multiplier_grid or any(multiplier <= 0 for multiplier in multiplier_grid):
        raise ValueError("calibration requires a positive multiplier grid")
    by_class: dict[str, tuple[SignalObservation, ...]] = {
        asset_class: tuple(item for item in selected if item.asset_class == asset_class)
        for asset_class in sorted({item.asset_class for item in selected})
    }
    profiles: dict[str, ThresholdProfile] = {}
    class_reports: dict[str, dict[str, object]] = {}
    candidates_by_class: dict[str, list[dict[str, object]]] = {}
    selected_indexes: dict[str, int] = {}
    for asset_class, class_observations in by_class.items():
        candidates = [
            _profile_report(class_observations, ThresholdProfile(asset_class, multiplier))
            for multiplier in multiplier_grid
        ]
        index = next(
            (index for index, item in enumerate(candidates) if item["alert_budget_pass"]),
            len(candidates) - 1,
        )
        chosen = candidates[index]
        candidates_by_class[asset_class] = candidates
        selected_indexes[asset_class] = index
        profiles[asset_class] = ThresholdProfile(
            asset_class, Decimal(str(chosen["absolute_boundary_multiplier"]))
        )
    global_budget = _budget_summary(selected, profiles)
    while not global_budget["alert_budget_pass"]:
        expandable = [
            asset_class for asset_class, index in selected_indexes.items()
            if index + 1 < len(candidates_by_class[asset_class])
        ]
        if not expandable:
            break
        alert_counts = global_budget["alerts_by_asset_class"]
        target = max(expandable, key=lambda item: (alert_counts[item], item))
        selected_indexes[target] += 1
        chosen = candidates_by_class[target][selected_indexes[target]]
        profiles[target] = ThresholdProfile(
            target, Decimal(str(chosen["absolute_boundary_multiplier"]))
        )
        global_budget = _budget_summary(selected, profiles)
    for asset_class, candidates in candidates_by_class.items():
        class_reports[asset_class] = {
            **candidates[selected_indexes[asset_class]],
            "candidate_grid": candidates,
        }

    start = min(item.evaluation_at.date() for item in selected)
    end = max(item.evaluation_at.date() for item in selected)
    provenance = {item.provenance_mode for item in selected}
    source_mode = next(iter(provenance)) if len(provenance) == 1 else "mixed"
    eligible_count = sum(item.quality_status == PASS_QUALITY for item in selected)
    alert_count = int(global_budget["alert_count"])
    report: dict[str, object] = {
        "report_version": 1,
        "rule_set_id": rule_set_id,
        "rule_set_version": rule_set_version,
        "replay_start": start.isoformat(),
        "replay_end": end.isoformat(),
        "calendar_span_days": (end - start).days + 1,
        "three_year_span": (end - start).days >= 1095,
        "source_mode": source_mode,
        "observation_count": len(selected),
        "eligible_count": eligible_count,
        "alert_count": alert_count,
        "asset_classes": class_reports,
        "global_alert_budget": global_budget,
        "owner_label_review_complete": False,
        "limitations": [
            "retrospective_reconstructed observations are calibration evidence, not historical live alerts",
            "false-positive and miss labels require owner review; maximum_miss_proxy is not precision",
            "missing asset classes and windows shorter than three years cannot approve external delivery",
            "ETF constituent exposure is unavailable in initial V2",
            "unknown asset classification remains a calibration blocker and is never coerced to stock",
        ],
    }
    report_hash = hashlib.sha256(_canonical_json(report).encode()).hexdigest()
    return CalibrationResult(rule_set_id, rule_set_version, profiles, report, report_hash)
