"""Deterministic lot-path, episode-path and owner-stop risk formulas."""

from __future__ import annotations

import inspect
import sys
from decimal import Decimal, ROUND_HALF_EVEN

from .metrics import MetricFormulaRegistry, MetricInput, MetricQualityError


QUANTUM = Decimal("0.0000000001")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def _values(inputs: tuple[MetricInput, ...], role: str) -> tuple[Decimal, ...]:
    prefix = f"role={role}|"
    return tuple(item.value for item in inputs if item.ref.startswith(prefix))


def _one(inputs: tuple[MetricInput, ...], role: str) -> Decimal:
    values = _values(inputs, role)
    if len(values) != 1:
        raise MetricQualityError(f"formula requires exactly one {role} input")
    return values[0]


def lot_mfe(inputs: tuple[MetricInput, ...]) -> Decimal:
    entry = _one(inputs, "entry_price")
    highs = _values(inputs, "path_high")
    if entry <= 0 or not highs:
        raise MetricQualityError("lot MFE requires positive entry and path highs")
    return _quantize(max(highs) / entry - Decimal("1"))


def lot_mae(inputs: tuple[MetricInput, ...]) -> Decimal:
    entry = _one(inputs, "entry_price")
    lows = _values(inputs, "path_low")
    if entry <= 0 or not lows:
        raise MetricQualityError("lot MAE requires positive entry and path lows")
    return _quantize(min(lows) / entry - Decimal("1"))


def episode_high(inputs: tuple[MetricInput, ...]) -> Decimal:
    highs = _values(inputs, "path_high")
    if not highs:
        raise MetricQualityError("episode high requires path highs")
    return _quantize(max(highs))


def episode_drawdown(inputs: tuple[MetricInput, ...]) -> Decimal:
    current = _one(inputs, "current_close")
    high = _one(inputs, "episode_high")
    if high <= 0:
        raise MetricQualityError("episode high denominator must be positive")
    return _quantize(current / high - Decimal("1"))


def planned_loss_krw(inputs: tuple[MetricInput, ...]) -> Decimal:
    quantity = sum(_values(inputs, "open_quantity"), Decimal("0"))
    reference = _one(inputs, "reference_price")
    stop = _one(inputs, "stop_price")
    fx = _one(inputs, "fx_rate")
    if quantity <= 0 or reference <= stop or stop <= 0 or fx <= 0:
        raise MetricQualityError("planned loss requires positive quantity, owner stop and FX")
    return _quantize(quantity * (reference - stop) * fx)


def risk_ratio(inputs: tuple[MetricInput, ...]) -> Decimal:
    planned_loss = _one(inputs, "planned_loss")
    total_assets = _one(inputs, "total_assets")
    if planned_loss < 0 or total_assets <= 0:
        raise MetricQualityError("risk ratio requires non-negative loss and positive total assets")
    return _quantize(planned_loss / total_assets)


def aggregate_planned_loss(inputs: tuple[MetricInput, ...]) -> Decimal:
    values = _values(inputs, "thread_planned_loss")
    if not values:
        raise MetricQualityError("instrument planned loss requires thread values")
    return _quantize(sum(values, Decimal("0")))


LOT_THREAD_RISK_FORMULAS = {
    "formula.lot-mfe-adjusted-price.v1": lot_mfe,
    "formula.lot-mae-adjusted-price.v1": lot_mae,
    "formula.position-episode-high-adjusted-price.v1": episode_high,
    "formula.position-episode-drawdown-adjusted-price.v1": episode_drawdown,
    "formula.thread-planned-loss-krw.v1": planned_loss_krw,
    "formula.thread-risk-ratio.v1": risk_ratio,
    "formula.instrument-planned-loss-krw.v1": aggregate_planned_loss,
    "formula.instrument-risk-ratio.v1": risk_ratio,
}


def register_lot_thread_risk_formulas(registry: MetricFormulaRegistry) -> None:
    material = inspect.getsource(sys.modules[__name__])
    for formula_ref, formula in LOT_THREAD_RISK_FORMULAS.items():
        registry.register(formula_ref, formula, implementation_material=material)
