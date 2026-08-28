"""Deterministic cash-flow-adjusted portfolio performance formulas."""

from __future__ import annotations

import inspect
import sys
from decimal import Decimal, ROUND_HALF_EVEN

from .metrics import MetricFormulaRegistry, MetricInput, MetricQualityError


METRIC_QUANTUM = Decimal("0.0000000001")
RECONCILIATION_TOLERANCE = METRIC_QUANTUM


def quantize_metric(value: Decimal) -> Decimal:
    return value.quantize(METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _values(inputs: tuple[MetricInput, ...], role: str) -> tuple[Decimal, ...]:
    prefix = f"role={role}|"
    return tuple(item.value for item in inputs if item.ref.startswith(prefix))


def _one(inputs: tuple[MetricInput, ...], role: str) -> Decimal:
    values = _values(inputs, role)
    if len(values) != 1:
        raise MetricQualityError(f"formula requires exactly one {role} input")
    return values[0]


def modified_dietz_return(inputs: tuple[MetricInput, ...]) -> Decimal:
    beginning = _one(inputs, "beginning_value")
    ending = _one(inputs, "ending_value")
    external_flows = sum(_values(inputs, "external_flow"), Decimal("0"))
    weighted_flows = sum(_values(inputs, "weighted_external_flow"), Decimal("0"))
    denominator = beginning + weighted_flows
    if denominator == 0:
        raise MetricQualityError("Modified Dietz denominator is zero")
    return quantize_metric((ending - beginning - external_flows) / denominator)


def modified_dietz_component_contribution(inputs: tuple[MetricInput, ...]) -> Decimal:
    beginning = _one(inputs, "component_beginning_value")
    ending = _one(inputs, "component_ending_value")
    denominator = _one(inputs, "portfolio_denominator")
    external_flows = sum(_values(inputs, "component_external_flow"), Decimal("0"))
    if denominator == 0:
        raise MetricQualityError("component contribution denominator is zero")
    return quantize_metric((ending - beginning - external_flows) / denominator)


def contribution_residual(inputs: tuple[MetricInput, ...]) -> Decimal:
    portfolio_return = _one(inputs, "portfolio_return")
    contributions = sum(_values(inputs, "component_contribution"), Decimal("0"))
    return quantize_metric(portfolio_return - contributions)


def chain_linked_wealth(inputs: tuple[MetricInput, ...]) -> Decimal:
    prior_wealth = _one(inputs, "prior_wealth")
    period_return = _one(inputs, "period_return")
    return quantize_metric(prior_wealth * (Decimal("1") + period_return))


def wealth_drawdown(inputs: tuple[MetricInput, ...]) -> Decimal:
    wealth = _one(inputs, "wealth")
    high_water = _one(inputs, "high_water")
    if high_water <= 0:
        raise MetricQualityError("wealth high-water denominator must be positive")
    return quantize_metric(wealth / high_water - Decimal("1"))


PERFORMANCE_FORMULAS = {
    "formula.portfolio-return-modified-dietz.v1": modified_dietz_return,
    "formula.portfolio-component-contribution-modified-dietz.v1": modified_dietz_component_contribution,
    "formula.portfolio-contribution-residual.v1": contribution_residual,
    "formula.portfolio-wealth-index.v1": chain_linked_wealth,
    "formula.portfolio-drawdown.v1": wealth_drawdown,
}


def register_portfolio_performance_formulas(registry: MetricFormulaRegistry) -> None:
    module_material = inspect.getsource(sys.modules[__name__])
    for formula_ref, formula in PERFORMANCE_FORMULAS.items():
        registry.register(formula_ref, formula, implementation_material=module_material)
