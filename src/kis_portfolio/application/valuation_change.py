"""Governed KRW valuation-change contribution read model and metric persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any
from zoneinfo import ZoneInfo

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.modules.monitoring import (
    MetricFormulaRegistry,
    MetricInput,
    MetricValue,
    PointInTimeMetricEngine,
    register_valuation_change_formulas,
)
from kis_portfolio.platform.metric_contracts import load_metric_registry


METRIC_ID = "metric.total-asset-valuation-change-contribution-krw"
METRIC_VERSION = "1.0.0"
PERCENT_QUANTUM = Decimal("0.0001")
KRW_QUANTUM = Decimal("0.01")
SEOUL = ZoneInfo("Asia/Seoul")


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _decimal(value: object | None) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=SEOUL) if value.tzinfo is None else value


def _json(value: object) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return {}
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return {}


def _money(value: Decimal) -> int | float:
    quantized = value.quantize(KRW_QUANTUM, rounding=ROUND_HALF_EVEN)
    return int(quantized) if quantized == quantized.to_integral_value() else float(quantized)


def _percent(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return float((numerator / denominator * Decimal("100")).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_EVEN))


def _tolerance(*totals: Decimal) -> Decimal:
    scale = max((abs(item) for item in totals), default=Decimal("0"))
    return max(Decimal("1"), scale * Decimal("0.000001")).quantize(KRW_QUANTUM, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class ValuationComponentState:
    component_id: str
    symbol: str | None
    name: str | None
    market: str | None
    currency: str
    is_cash: bool
    value_krw: Decimal
    account_values: dict[str, Decimal]
    lineage_hash: str


@dataclass(frozen=True, slots=True)
class CanonicalValuationState:
    source_model: str
    snapshot_ref: str
    evaluation_date: date
    evaluation_slot: str
    snapshot_at: datetime
    total_value_krw: Decimal
    components: dict[str, ValuationComponentState]
    required_accounts: frozenset[str]
    observed_accounts: frozenset[str]
    quality_status: str
    is_complete: bool
    blockers: tuple[str, ...]


def _component(
    component_id: str,
    prior: CanonicalValuationState,
    current: CanonicalValuationState,
) -> tuple[ValuationComponentState | None, ValuationComponentState | None]:
    return prior.components.get(component_id), current.components.get(component_id)


def _component_value(item: ValuationComponentState | None) -> Decimal:
    return item.value_krw if item else Decimal("0")


def _component_lineage(item: ValuationComponentState | None, state: CanonicalValuationState, component_id: str) -> str:
    return item.lineage_hash if item else _hash("absent", state.snapshot_ref, component_id)


def _quality_blockers(prior: CanonicalValuationState, current: CanonicalValuationState) -> list[str]:
    blockers = [f"prior:{item}" for item in prior.blockers]
    blockers.extend(f"current:{item}" for item in current.blockers)
    if not prior.is_complete:
        blockers.append("prior_snapshot_incomplete")
    if not current.is_complete:
        blockers.append("current_snapshot_incomplete")
    if prior.required_accounts != current.required_accounts:
        blockers.append("required_account_coverage_changed")
    if prior.observed_accounts != prior.required_accounts:
        blockers.append("prior_required_account_coverage_mismatch")
    if current.observed_accounts != current.required_accounts:
        blockers.append("current_required_account_coverage_mismatch")
    return list(dict.fromkeys(blockers))


def build_valuation_change_result(
    prior: CanonicalValuationState,
    current: CanonicalValuationState,
    *,
    top_n: int = 5,
    include_account_breakdown: bool = False,
) -> dict[str, Any]:
    """Compare two canonical states without confusing KRW valuation change with return."""
    if current.snapshot_at <= prior.snapshot_at:
        raise ValueError("current canonical state must be later than prior state")
    top_n = max(1, min(int(top_n), 50))
    blockers = _quality_blockers(prior, current)
    total_change = current.total_value_krw - prior.total_value_krw
    previous_cash = sum((item.value_krw for item in prior.components.values() if item.is_cash), Decimal("0"))
    current_cash = sum((item.value_krw for item in current.components.values() if item.is_cash), Decimal("0"))
    cash_change = current_cash - previous_cash

    instrument_ids = sorted({
        component_id
        for component_id, item in {**prior.components, **current.components}.items()
        if not item.is_cash
    })
    contributors: list[dict[str, Any]] = []
    holding_change_sum = Decimal("0")
    for component_id in instrument_ids:
        before, after = _component(component_id, prior, current)
        metadata = after or before
        assert metadata is not None
        previous_value = _component_value(before)
        current_value = _component_value(after)
        change = current_value - previous_value
        holding_change_sum += change
        account_breakdown = []
        if include_account_breakdown:
            account_refs = sorted(set(before.account_values if before else {}) | set(after.account_values if after else {}))
            for account_ref in account_refs:
                account_previous = before.account_values.get(account_ref, Decimal("0")) if before else Decimal("0")
                account_current = after.account_values.get(account_ref, Decimal("0")) if after else Decimal("0")
                account_breakdown.append({
                    "account_label": account_ref,
                    "previous_value_krw": _money(account_previous),
                    "current_value_krw": _money(account_current),
                    "valuation_change_krw": _money(account_current - account_previous),
                })
        foreign = metadata.currency.upper() != "KRW" or str(metadata.market or "").upper() not in {"KRX", "KRW"}
        contributor = {
            "instrument_id": component_id,
            "symbol": metadata.symbol,
            "name": metadata.name,
            "market": metadata.market,
            "currency": metadata.currency,
            "previous_value_krw": _money(previous_value),
            "current_value_krw": _money(current_value),
            "valuation_change_krw": _money(change),
            "total_asset_impact_pct": _percent(change, prior.total_value_krw),
            "total_asset_impact_unavailable_reason": (
                "previous_total_asset_zero" if prior.total_value_krw == 0 else None
            ),
            "share_of_total_change_pct": _percent(change, total_change),
            "share_of_total_change_unavailable_reason": (
                "total_asset_change_zero" if total_change == 0 else None
            ),
            "is_new_position": None,
            "is_fully_sold": None,
            "inference_status": "suppressed",
            "valuation_change_label": (
                "KRW valuation change including FX" if foreign else "KRW valuation change"
            ),
        }
        if account_breakdown:
            contributor["account_breakdown"] = account_breakdown
        contributors.append(contributor)

    explained_change = holding_change_sum + cash_change
    residual = total_change - explained_change
    tolerance = _tolerance(prior.total_value_krw, current.total_value_krw)
    reconciliation_status = "pass" if abs(residual) <= tolerance else "failed"
    if reconciliation_status != "pass":
        blockers.append("valuation_change_reconciliation_failed")
    blockers = list(dict.fromkeys(blockers))
    comparable = not blockers
    if comparable:
        for contributor in contributors:
            contributor["is_new_position"] = (
                contributor["previous_value_krw"] == 0 and contributor["current_value_krw"] != 0
            )
            contributor["is_fully_sold"] = (
                contributor["previous_value_krw"] != 0 and contributor["current_value_krw"] == 0
            )
            contributor["inference_status"] = "evaluated"

    positives = sorted(
        (item for item in contributors if _decimal(item["valuation_change_krw"]) > 0),
        key=lambda item: _decimal(item["valuation_change_krw"]), reverse=True,
    )[:top_n]
    negatives = sorted(
        (item for item in contributors if _decimal(item["valuation_change_krw"]) < 0),
        key=lambda item: _decimal(item["valuation_change_krw"]),
    )[:top_n]
    return {
        "metric_id": METRIC_ID,
        "metric_version": METRIC_VERSION,
        "status": "pass" if comparable else "degraded",
        "label": "환율 효과를 포함한 원화 평가액 변화 기여도",
        "interpretation": "point-to-point KRW valuation change; not investment-return contribution",
        "source_model": current.source_model,
        "previous_snapshot": {
            "ref": prior.snapshot_ref,
            "date": prior.evaluation_date.isoformat(),
            "snapshot_at": prior.snapshot_at.isoformat(),
            "total_asset_krw": _money(prior.total_value_krw),
        },
        "current_snapshot": {
            "ref": current.snapshot_ref,
            "date": current.evaluation_date.isoformat(),
            "snapshot_at": current.snapshot_at.isoformat(),
            "total_asset_krw": _money(current.total_value_krw),
        },
        "quality": {
            "comparable": comparable,
            "status": "pass" if comparable else "degraded",
            "blockers": blockers,
            "new_sold_inference": "enabled" if comparable else "suppressed",
            "prior_required_account_count": len(prior.required_accounts),
            "prior_observed_account_count": len(prior.observed_accounts),
            "current_required_account_count": len(current.required_accounts),
            "current_observed_account_count": len(current.observed_accounts),
            "account_coverage_equal": prior.required_accounts == current.required_accounts,
        },
        "totals": {
            "previous_total_asset_krw": _money(prior.total_value_krw),
            "current_total_asset_krw": _money(current.total_value_krw),
            "total_asset_change_krw": _money(total_change),
            "holding_change_sum_krw": _money(holding_change_sum),
            "cash_change_krw": _money(cash_change),
            "explained_change_sum_krw": _money(explained_change),
            "unexplained_residual_krw": _money(residual),
            "reconciliation_tolerance_krw": _money(tolerance),
            "reconciliation_status": reconciliation_status,
        },
        "cash": {
            "previous_value_krw": _money(previous_cash),
            "current_value_krw": _money(current_cash),
            "valuation_change_krw": _money(cash_change),
            "total_asset_impact_pct": _percent(cash_change, prior.total_value_krw),
            "share_of_total_change_pct": _percent(cash_change, total_change),
            "share_of_total_change_unavailable_reason": (
                "total_asset_change_zero" if total_change == 0 else None
            ),
        },
        "contributors": contributors,
        "top_positive_contributors": positives,
        "top_negative_contributors": negatives,
        "fx_disclaimer": (
            "Foreign holdings are measured as KRW valuation change including FX; price and FX effects are not isolated."
        ),
    }


def _v1_component_id(*, is_cash: bool, market: object, symbol: object, currency: object) -> str:
    if is_cash:
        return f"cash|{str(currency or 'KRW').upper()}"
    return f"instrument|{str(market or 'UNKNOWN').upper()}|{str(symbol or 'UNKNOWN').upper()}"


def load_v1_canonical_states(connection: Any, *, limit: int = 2) -> tuple[CanonicalValuationState, ...]:
    rows = connection.execute("""
        SELECT id,snap_date,snapshot_at,total_eval_amt_krw,quality_status,quality_flags,is_complete,overview_data
        FROM asset_overview_daily_snapshots
        ORDER BY snap_date DESC LIMIT ?
    """, [max(1, int(limit))]).fetchall()
    states: list[CanonicalValuationState] = []
    for snapshot_id, evaluation_date, snapshot_at, total, quality, flags_raw, complete, overview_raw in reversed(rows):
        overview = _json(overview_raw)
        data_quality = overview.get("data_quality") if isinstance(overview, dict) else {}
        data_quality = data_quality if isinstance(data_quality, dict) else {}
        required = frozenset(str(item) for item in data_quality.get("required_account_labels", []) if item)
        observed = frozenset(str(item) for item in data_quality.get("observed_account_labels", []) if item)
        flags = _json(flags_raw)
        if not isinstance(flags, list):
            flags = []
        blockers = [str(item.get("code") if isinstance(item, dict) else item) for item in flags]
        holding_rows = connection.execute("""
            SELECT id,account_label,symbol,name,market,basis_category,exposure_type,asset_subtype,
                   value_krw,currency
            FROM asset_holding_snapshots WHERE overview_snapshot_id=? ORDER BY id
        """, [snapshot_id]).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row_id, account_label, symbol, name, market, basis, exposure, subtype, value, currency in holding_rows:
            is_cash = "cash" in {str(basis or "").lower(), str(exposure or "").lower(), str(subtype or "").lower()}
            component_id = _v1_component_id(is_cash=is_cash, market=market, symbol=symbol, currency=currency)
            bucket = grouped.setdefault(component_id, {
                "symbol": str(symbol) if symbol else None,
                "name": str(name) if name else None,
                "market": str(market) if market else None,
                "currency": str(currency or "KRW"),
                "is_cash": is_cash,
                "value": Decimal("0"),
                "accounts": {},
                "lineage": [],
            })
            amount = _decimal(value)
            bucket["value"] += amount
            account_ref = str(account_label or "unknown")
            bucket["accounts"][account_ref] = bucket["accounts"].get(account_ref, Decimal("0")) + amount
            bucket["lineage"].append(str(row_id))
        components = {
            component_id: ValuationComponentState(
                component_id, payload["symbol"], payload["name"], payload["market"], payload["currency"],
                payload["is_cash"], payload["value"], payload["accounts"],
                _hash("v1-holdings", snapshot_id, *payload["lineage"]),
            )
            for component_id, payload in grouped.items()
        }
        if not holding_rows:
            blockers.append("missing_holding_rows")
        holding_total = sum((item.value_krw for item in components.values()), Decimal("0"))
        total_decimal = _decimal(total)
        if abs(total_decimal - holding_total) > _tolerance(total_decimal):
            blockers.append("overview_holding_reconciliation_failed")
        states.append(CanonicalValuationState(
            "v1_canonical_overview",
            str(snapshot_id),
            evaluation_date,
            "daily-last",
            _aware(snapshot_at),
            total_decimal,
            components,
            required,
            observed,
            str(quality or "legacy_unassessed"),
            bool(complete) and str(quality) == "pass",
            tuple(dict.fromkeys(blockers)),
        ))
    return tuple(states)


def load_v2_canonical_state(
    connection: Any,
    *,
    evaluation_date: date,
    evaluation_slot: str,
) -> CanonicalValuationState | None:
    rows = connection.execute("""
        SELECT s.account_id,s.instrument_id,s.aggregate_level,s.value_krw,s.as_of,s.quality_status,s.lineage_hash,
               i.market,i.symbol,i.name,i.currency
        FROM gold.portfolio_daily_state s
        LEFT JOIN silver.instruments i ON i.instrument_id=s.instrument_id
        WHERE s.evaluation_date=? AND s.evaluation_slot=? AND s.aggregate_level IN ('position','cash')
        ORDER BY s.account_id,s.aggregate_level,s.instrument_id
    """, [evaluation_date, evaluation_slot]).fetchall()
    if not rows:
        return None
    grouped: dict[str, dict[str, Any]] = {}
    observed: set[str] = set()
    as_of_values: set[datetime] = set()
    blockers: list[str] = []
    for account_id, instrument_id, level, value, as_of, quality, lineage, market, symbol, name, currency in rows:
        observed.add(str(account_id))
        as_of_values.add(_aware(as_of))
        is_cash = str(level) == "cash"
        component_id = str(instrument_id)
        resolved_currency = str(currency or (component_id.split("|", 1)[1] if is_cash and "|" in component_id else "KRW"))
        bucket = grouped.setdefault(component_id, {
            "symbol": str(symbol) if symbol else (None if is_cash else component_id),
            "name": str(name) if name else (f"Cash {resolved_currency}" if is_cash else None),
            "market": str(market) if market else ("CASH" if is_cash else None),
            "currency": resolved_currency,
            "is_cash": is_cash,
            "value": Decimal("0"),
            "accounts": {},
            "lineage": [],
        })
        amount = _decimal(value)
        bucket["value"] += amount
        bucket["accounts"][str(account_id)] = bucket["accounts"].get(str(account_id), Decimal("0")) + amount
        bucket["lineage"].append(str(lineage))
        if str(quality) != "pass":
            blockers.append(f"input_quality_{quality}")
    if len(as_of_values) != 1:
        blockers.append("mixed_state_cutoff")
    snapshot_at = max(as_of_values)
    required = frozenset(str(row[0]) for row in connection.execute("""
        SELECT account_id FROM silver.accounts
        WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?) ORDER BY account_id
    """, [snapshot_at, snapshot_at]).fetchall())
    if not required:
        blockers.append("missing_required_account_registry")
    if frozenset(observed) != required:
        blockers.append("required_account_coverage_mismatch")
    components = {
        component_id: ValuationComponentState(
            component_id, payload["symbol"], payload["name"], payload["market"], payload["currency"],
            payload["is_cash"], payload["value"], payload["accounts"],
            _hash("v2-state", evaluation_date, evaluation_slot, component_id, *payload["lineage"]),
        )
        for component_id, payload in grouped.items()
    }
    total = sum((item.value_krw for item in components.values()), Decimal("0"))
    snapshot_ref = _hash("v2-daily-state", evaluation_date, evaluation_slot, *sorted(item.lineage_hash for item in components.values()))
    blockers = list(dict.fromkeys(blockers))
    return CanonicalValuationState(
        "v2_portfolio_daily_state", snapshot_ref, evaluation_date, evaluation_slot, snapshot_at, total,
        components, required, frozenset(observed), "pass" if not blockers else "degraded", not blockers, tuple(blockers),
    )


def read_latest_v1_valuation_change(
    connection: Any,
    *,
    top_n: int = 5,
    include_account_breakdown: bool = True,
) -> dict[str, Any]:
    states = load_v1_canonical_states(connection, limit=2)
    if len(states) < 2:
        return {
            "metric_id": METRIC_ID,
            "metric_version": METRIC_VERSION,
            "status": "unavailable",
            "quality": {"comparable": False, "blockers": ["insufficient_canonical_daily_states"]},
            "contributors": [],
            "message": "비교 가능한 총자산 일별 스냅샷이 2개 미만입니다.",
        }
    return build_valuation_change_result(
        states[-2], states[-1], top_n=top_n, include_account_breakdown=include_account_breakdown,
    )


def build_valuation_change_engine() -> PointInTimeMetricEngine:
    formulas = MetricFormulaRegistry()
    register_valuation_change_formulas(formulas)
    return PointInTimeMetricEngine(load_metric_registry(), formulas)


class ValuationChangeEvaluator:
    """Persist official V2 component deltas only when the shared read model passes."""

    def __init__(
        self,
        connection: Any,
        *,
        metric_repository: MetricWarehouseRepository | None = None,
        engine: PointInTimeMetricEngine | None = None,
    ) -> None:
        self.connection = connection
        self.repository = metric_repository or MetricWarehouseRepository(connection)
        self.engine = engine or build_valuation_change_engine()

    def evaluate_v2_period_and_store(
        self,
        *,
        prior_date: date,
        current_date: date,
        evaluation_slot: str,
        evaluation_run_id: str,
        top_n: int = 5,
    ) -> tuple[dict[str, Any], tuple[MetricValue, ...]]:
        prior = load_v2_canonical_state(self.connection, evaluation_date=prior_date, evaluation_slot=evaluation_slot)
        current = load_v2_canonical_state(self.connection, evaluation_date=current_date, evaluation_slot=evaluation_slot)
        if prior is None or current is None:
            raise ValueError("both V2 canonical daily states are required")
        result = build_valuation_change_result(prior, current, top_n=top_n, include_account_breakdown=False)
        component_ids = sorted(set(prior.components) | set(current.components))
        values: list[MetricValue] = []
        for component_id in component_ids:
            before, after = _component(component_id, prior, current)
            inputs = (
                MetricInput(
                    f"role=previous_value|{component_id}", _component_value(before), prior.snapshot_at,
                    prior.snapshot_at, prior.quality_status, _component_lineage(before, prior, component_id),
                ),
                MetricInput(
                    f"role=current_value|{component_id}", _component_value(after), current.snapshot_at,
                    current.snapshot_at, current.quality_status, _component_lineage(after, current, component_id),
                ),
            )
            kwargs = {
                "metric_id": METRIC_ID,
                "version": METRIC_VERSION,
                "subject_type": "portfolio_component",
                "subject_id": component_id,
                "evaluation_at": current.snapshot_at,
                "evaluation_slot": evaluation_slot,
                "inputs": inputs,
                "evaluation_run_id": evaluation_run_id,
            }
            if result["status"] == "pass":
                values.append(self.engine.evaluate(**kwargs))
            else:
                values.append(self.engine.unavailable(
                    **kwargs, quality_status=str(result["quality"]["blockers"][0]),
                ))
        self.connection.execute("BEGIN TRANSACTION")
        try:
            for value in values:
                self.repository.write_value(value)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return result, tuple(values)


def inspect_valuation_change_readiness(connection: Any) -> dict[str, Any]:
    """Return aggregate-only readiness evidence without values, account ids, writes or source calls."""
    view_columns = {
        str(row[0])
        for row in connection.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='asset_overview_daily_snapshots'
        """).fetchall()
    }
    quality_projection_ready = {"quality_status", "is_complete"}.issubset(view_columns)
    if quality_projection_ready:
        v1 = connection.execute("""
            WITH latest AS (
                SELECT id,quality_status,is_complete FROM asset_overview_daily_snapshots
                ORDER BY snap_date DESC LIMIT 2
            )
            SELECT count(*),coalesce(count_if(quality_status='pass' AND is_complete),0),
                   (SELECT count(*) FROM asset_holding_snapshots h JOIN latest l ON h.overview_snapshot_id=l.id)
            FROM latest
        """).fetchone()
    else:
        v1 = connection.execute("""
            WITH latest AS (
                SELECT id FROM asset_overview_daily_snapshots ORDER BY snap_date DESC LIMIT 2
            )
            SELECT count(*),0,
                   (SELECT count(*) FROM asset_holding_snapshots h JOIN latest l ON h.overview_snapshot_id=l.id)
            FROM latest
        """).fetchone()
    v2 = connection.execute("""
        SELECT count(*),count(DISTINCT evaluation_date),count(DISTINCT evaluation_slot),
               coalesce(count_if(quality_status='pass'),0),coalesce(count_if(quality_status<>'pass'),0)
        FROM gold.portfolio_daily_state
    """).fetchone()
    blockers: list[str] = []
    if not quality_projection_ready:
        blockers.append("v1_daily_view_missing_quality_projection")
    if int(v1[0]) < 2:
        blockers.append("v1_insufficient_daily_states")
    if int(v1[1]) < 2:
        blockers.append("v1_latest_pair_not_complete")
    if int(v1[2]) == 0:
        blockers.append("v1_latest_pair_missing_holdings")
    if int(v2[1]) < 2:
        blockers.append("v2_insufficient_daily_state_history")
    if int(v2[4]) > 0:
        blockers.append("v2_non_pass_state_rows")
    return {
        "status": "ready" if not blockers else "blocked",
        "publish_ready": not blockers,
        "blockers": blockers,
        "v1_latest_pair": {
            "states": int(v1[0]),
            "complete_pass_states": int(v1[1]),
            "holding_rows": int(v1[2]),
            "quality_projection_ready": quality_projection_ready,
        },
        "v2_daily_state": {
            "rows": int(v2[0]), "dates": int(v2[1]), "slots": int(v2[2]),
            "pass_rows": int(v2[3]), "non_pass_rows": int(v2[4]),
        },
        "side_effects": "none",
    }
