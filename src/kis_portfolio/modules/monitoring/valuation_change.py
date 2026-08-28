"""Deterministic point-to-point KRW valuation-change formula."""

from __future__ import annotations

import inspect
import sys
from decimal import Decimal, ROUND_HALF_EVEN

from .metrics import MetricFormulaRegistry, MetricInput, MetricQualityError


KRW_QUANTUM = Decimal("0.01")


def _one(inputs: tuple[MetricInput, ...], role: str) -> Decimal:
    prefix = f"role={role}|"
    values = tuple(item.value for item in inputs if item.ref.startswith(prefix))
    if len(values) != 1:
        raise MetricQualityError(f"valuation-change formula requires exactly one {role} input")
    return values[0]


def total_asset_valuation_change_krw(inputs: tuple[MetricInput, ...]) -> Decimal:
    previous = _one(inputs, "previous_value")
    current = _one(inputs, "current_value")
    return (current - previous).quantize(KRW_QUANTUM, rounding=ROUND_HALF_EVEN)


VALUATION_CHANGE_FORMULAS = {
    "formula.total-asset-valuation-change-contribution-krw.v1": total_asset_valuation_change_krw,
}


def register_valuation_change_formulas(registry: MetricFormulaRegistry) -> None:
    module_material = inspect.getsource(sys.modules[__name__])
    for formula_ref, formula in VALUATION_CHANGE_FORMULAS.items():
        registry.register(formula_ref, formula, implementation_material=module_material)
