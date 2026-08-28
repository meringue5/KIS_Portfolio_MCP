"""Application service for strict point-in-time trend metric evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.modules.monitoring import (
    MetricFormulaRegistry,
    MetricInput,
    MetricValue,
    PointInTimeMetricEngine,
    register_trend_formulas,
)
from kis_portfolio.platform.metric_contracts import load_metric_registry


@dataclass(frozen=True, slots=True)
class TrendMetricSpec:
    metric_id: str
    minimum_bars: int
    maximum_bars: int
    fields: tuple[str, ...]


TREND_METRIC_SPECS = (
    TrendMetricSpec("metric.sma-adjusted-close-20", 20, 20, ("close",)),
    TrendMetricSpec("metric.sma-adjusted-close-50", 50, 50, ("close",)),
    TrendMetricSpec("metric.sma-adjusted-close-120", 120, 120, ("close",)),
    TrendMetricSpec("metric.volume-sma-20", 20, 20, ("volume",)),
    TrendMetricSpec("metric.volume-ratio-20", 20, 20, ("volume",)),
    TrendMetricSpec("metric.rsi-14-wilder", 15, 120, ("close",)),
    TrendMetricSpec("metric.bollinger-lower-20-2", 20, 20, ("close",)),
    TrendMetricSpec("metric.bollinger-upper-20-2", 20, 20, ("close",)),
    TrendMetricSpec("metric.bollinger-percent-b-20-2", 20, 20, ("close",)),
    TrendMetricSpec("metric.bollinger-bandwidth-20-2", 20, 20, ("close",)),
    TrendMetricSpec("metric.atr-20-wilder", 20, 120, ("high", "low", "close")),
)


def build_trend_metric_engine() -> PointInTimeMetricEngine:
    formulas = MetricFormulaRegistry()
    register_trend_formulas(formulas)
    return PointInTimeMetricEngine(load_metric_registry(), formulas)


class PriceTrendMetricEvaluator:
    def __init__(
        self,
        price_repository: V2WarehouseRepository,
        metric_repository: MetricWarehouseRepository,
        engine: PointInTimeMetricEngine | None = None,
    ) -> None:
        self.price_repository = price_repository
        self.metric_repository = metric_repository
        self.engine = engine or build_trend_metric_engine()

    @staticmethod
    def _inputs(
        instrument_id: str,
        bars: list[dict[str, Any]],
        fields: tuple[str, ...],
    ) -> tuple[MetricInput, ...]:
        inputs: list[MetricInput] = []
        for bar in bars:
            for field in fields:
                value = bar.get(field)
                if value is None:
                    continue
                inputs.append(MetricInput(
                    ref=(
                        f"silver.price_bar_revisions_daily:{instrument_id}:"
                        f"{bar['session_date'].isoformat()}:{bar['revision_hash']}:{field}"
                    ),
                    value=Decimal(str(value)),
                    effective_at=bar["effective_at"],
                    knowledge_at=bar["knowledge_at"],
                    quality_status=bar["quality_status"],
                    lineage_hash=bar["revision_hash"],
                ))
        return tuple(inputs)

    def evaluate_and_store(
        self,
        *,
        instrument_id: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        evaluation_run_id: str,
    ) -> tuple[MetricValue, ...]:
        if evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        bars = self.price_repository.get_price_bars_as_of(
            instrument_id=instrument_id,
            start_date=evaluation_at.date() - timedelta(days=800),
            end_date=evaluation_at.date(),
            price_basis="adjusted",
            evaluation_at=evaluation_at,
            replay_mode="operational_strict",
        )
        values: list[MetricValue] = []
        for spec in TREND_METRIC_SPECS:
            selected_bars = bars[-spec.maximum_bars:]
            inputs = self._inputs(instrument_id, selected_bars, spec.fields)
            quality_status: str | None = None
            if len(selected_bars) < spec.minimum_bars:
                quality_status = "insufficient_history"
            elif len(inputs) != len(selected_bars) * len(spec.fields):
                quality_status = "missing_price_field"
            elif any(bar["reconstruction_mode"] != "operational_strict" for bar in selected_bars):
                quality_status = "retrospective_reconstructed"
            else:
                non_pass = sorted({bar["quality_status"] for bar in selected_bars if bar["quality_status"] != "pass"})
                if non_pass:
                    quality_status = "input_quality_" + "_".join(non_pass)
                elif spec.metric_id == "metric.volume-ratio-20" and sum(
                    (item.value for item in inputs), Decimal("0")
                ) == 0:
                    quality_status = "zero_denominator"
                elif spec.metric_id == "metric.bollinger-bandwidth-20-2" and sum(
                    (item.value for item in inputs), Decimal("0")
                ) == 0:
                    quality_status = "zero_denominator"

            kwargs = {
                "metric_id": spec.metric_id,
                "version": "1.0.0",
                "subject_type": "instrument",
                "subject_id": instrument_id,
                "evaluation_at": evaluation_at,
                "evaluation_slot": evaluation_slot,
                "inputs": inputs,
                "evaluation_run_id": evaluation_run_id,
            }
            value = (
                self.engine.unavailable(quality_status=quality_status, **kwargs)
                if quality_status
                else self.engine.evaluate(**kwargs)
            )
            self.metric_repository.write_value(value)
            values.append(value)
        return tuple(values)
