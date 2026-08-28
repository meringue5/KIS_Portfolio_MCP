"""Deterministic adjusted-daily trend and volatility formulas."""

from __future__ import annotations

import inspect
import sys
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .metrics import MetricFormulaRegistry, MetricInput, MetricQualityError


METRIC_QUANTUM = Decimal("0.0000000001")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _require(inputs: tuple[MetricInput, ...], count: int) -> None:
    if len(inputs) != count:
        raise MetricQualityError(f"formula requires exactly {count} inputs")


def _sma(inputs: tuple[MetricInput, ...], period: int) -> Decimal:
    _require(inputs, period)
    return _quantize(sum((item.value for item in inputs), Decimal("0")) / Decimal(period))


def sma_adjusted_close_20(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _sma(inputs, 20)


def sma_adjusted_close_50(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _sma(inputs, 50)


def sma_adjusted_close_120(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _sma(inputs, 120)


def volume_sma_20(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _sma(inputs, 20)


def volume_ratio_20(inputs: tuple[MetricInput, ...]) -> Decimal:
    _require(inputs, 20)
    mean = sum((item.value for item in inputs), Decimal("0")) / Decimal("20")
    if mean == 0:
        raise MetricQualityError("volume SMA20 denominator is zero")
    return _quantize(inputs[-1].value / mean)


def rsi_14_wilder(inputs: tuple[MetricInput, ...]) -> Decimal:
    if not 15 <= len(inputs) <= 120:
        raise MetricQualityError("Wilder RSI14 requires 15 to 120 adjusted closes")
    changes = [inputs[index].value - inputs[index - 1].value for index in range(1, len(inputs))]
    gains = [max(change, Decimal("0")) for change in changes]
    losses = [max(-change, Decimal("0")) for change in changes]
    average_gain = sum(gains[:14], Decimal("0")) / Decimal("14")
    average_loss = sum(losses[:14], Decimal("0")) / Decimal("14")
    for gain, loss in zip(gains[14:], losses[14:], strict=True):
        average_gain = (average_gain * Decimal("13") + gain) / Decimal("14")
        average_loss = (average_loss * Decimal("13") + loss) / Decimal("14")
    if average_gain == 0 and average_loss == 0:
        return Decimal("50.0000000000")
    if average_loss == 0:
        return Decimal("100.0000000000")
    relative_strength = average_gain / average_loss
    return _quantize(Decimal("100") - Decimal("100") / (Decimal("1") + relative_strength))


def _bollinger(inputs: tuple[MetricInput, ...]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    _require(inputs, 20)
    mean = sum((item.value for item in inputs), Decimal("0")) / Decimal("20")
    variance = sum(((item.value - mean) ** 2 for item in inputs), Decimal("0")) / Decimal("20")
    with localcontext() as context:
        context.prec = 40
        standard_deviation = variance.sqrt()
    lower = mean - Decimal("2") * standard_deviation
    upper = mean + Decimal("2") * standard_deviation
    return mean, lower, upper, standard_deviation


def bollinger_lower_20_2(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _quantize(_bollinger(inputs)[1])


def bollinger_upper_20_2(inputs: tuple[MetricInput, ...]) -> Decimal:
    return _quantize(_bollinger(inputs)[2])


def bollinger_percent_b_20_2(inputs: tuple[MetricInput, ...]) -> Decimal:
    _, lower, upper, _ = _bollinger(inputs)
    width = upper - lower
    if width == 0:
        return Decimal("0.5000000000")
    return _quantize((inputs[-1].value - lower) / width)


def bollinger_bandwidth_20_2(inputs: tuple[MetricInput, ...]) -> Decimal:
    mean, lower, upper, _ = _bollinger(inputs)
    if mean == 0:
        raise MetricQualityError("Bollinger bandwidth denominator is zero")
    return _quantize((upper - lower) / mean)


def atr_20_wilder(inputs: tuple[MetricInput, ...]) -> Decimal:
    if len(inputs) % 3 != 0:
        raise MetricQualityError("ATR inputs must contain high, low and close for each session")
    bars = len(inputs) // 3
    if not 20 <= bars <= 120:
        raise MetricQualityError("Wilder ATR20 requires 20 to 120 adjusted OHLC bars")
    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for offset in range(0, len(inputs), 3):
        high, low, close = (item.value for item in inputs[offset:offset + 3])
        candidates = [high - low]
        if previous_close is not None:
            candidates.extend([abs(high - previous_close), abs(low - previous_close)])
        true_ranges.append(max(candidates))
        previous_close = close
    average_range = sum(true_ranges[:20], Decimal("0")) / Decimal("20")
    for true_range in true_ranges[20:]:
        average_range = (average_range * Decimal("19") + true_range) / Decimal("20")
    return _quantize(average_range)


TREND_FORMULAS = {
    "formula.sma-adjusted-close-20.v1": sma_adjusted_close_20,
    "formula.sma-adjusted-close-50.v1": sma_adjusted_close_50,
    "formula.sma-adjusted-close-120.v1": sma_adjusted_close_120,
    "formula.volume-sma-20.v1": volume_sma_20,
    "formula.volume-ratio-20.v1": volume_ratio_20,
    "formula.rsi-14-wilder.v1": rsi_14_wilder,
    "formula.bollinger-lower-20-2.v1": bollinger_lower_20_2,
    "formula.bollinger-upper-20-2.v1": bollinger_upper_20_2,
    "formula.bollinger-percent-b-20-2.v1": bollinger_percent_b_20_2,
    "formula.bollinger-bandwidth-20-2.v1": bollinger_bandwidth_20_2,
    "formula.atr-20-wilder.v1": atr_20_wilder,
}


def register_trend_formulas(registry: MetricFormulaRegistry) -> None:
    module_material = inspect.getsource(sys.modules[__name__])
    for formula_ref, formula in TREND_FORMULAS.items():
        registry.register(formula_ref, formula, implementation_material=module_material)
