from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN

import duckdb

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.application.trend_metrics import PriceTrendMetricEvaluator
from kis_portfolio.modules.monitoring import MetricInput
from kis_portfolio.modules.monitoring.trend_metrics import atr_20_wilder, rsi_14_wilder
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


INSTRUMENT_ID = "v1|KRX|005930"
QUANTUM = Decimal("0.0000000001")


def _load_bars(
    warehouse: V2WarehouseRepository,
    *,
    count: int,
    knowledge_at: datetime,
    reconstruction_mode: str = "operational_strict",
    close_offset: int = 0,
    zero_volume: bool = False,
) -> None:
    payload = {
        "fixture": "trend", "count": count, "close_offset": close_offset,
        "zero_volume": zero_volume,
    }
    observation_id = warehouse.record_observation(
        "dataset.price-bar-daily",
        SourceEnvelope(
            "source.kis-open-api",
            f"trend-page-{count}-{close_offset}-{reconstruction_mode}",
            knowledge_at,
            knowledge_at,
            payload,
            hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "pass",
        ),
        "trend-fixture-run",
    )
    start = date(2026, 1, 1)
    bars = []
    for index in range(1, count + 1):
        close = Decimal(index + close_offset)
        session_date = start + timedelta(days=index - 1)
        bars.append({
            "instrument_id": INSTRUMENT_ID,
            "session_date": session_date,
            "price_basis": "adjusted",
            "open": close - 1,
            "high": close + 2,
            "low": close - 1,
            "close": close,
            "volume": 0 if zero_volume else 100 + index,
            "effective_at": datetime.combine(session_date, datetime.min.time(), tzinfo=UTC),
            "knowledge_at": knowledge_at,
            "endpoint": "fixture.adjusted-history",
            "request_option": "adjusted",
            "volume_basis": "vendor_reported",
            "reconstruction_mode": reconstruction_mode,
            "quality_status": "pass",
        })
    warehouse.upsert_price_bars(bars, observation_id)


def _evaluate(con: duckdb.DuckDBPyConnection, evaluation_at: datetime):
    evaluator = PriceTrendMetricEvaluator(
        V2WarehouseRepository(con),
        MetricWarehouseRepository(con),
    )
    return evaluator.evaluate_and_store(
        instrument_id=INSTRUMENT_ID,
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        evaluation_run_id="trend-evaluation-fixture",
    )


def test_trend_metric_family_matches_independent_sql_golden() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    evaluation_at = datetime(2026, 6, 1, tzinfo=UTC)
    _load_bars(V2WarehouseRepository(con), count=120, knowledge_at=evaluation_at - timedelta(hours=1))

    values = {value.definition.metric_id: value.value for value in _evaluate(con, evaluation_at)}
    assert values["metric.sma-adjusted-close-20"] == Decimal("110.5000000000")
    assert values["metric.sma-adjusted-close-50"] == Decimal("95.5000000000")
    assert values["metric.sma-adjusted-close-120"] == Decimal("60.5000000000")
    assert values["metric.volume-sma-20"] == Decimal("210.5000000000")
    assert values["metric.volume-ratio-20"] == (Decimal("220") / Decimal("210.5")).quantize(
        QUANTUM, rounding=ROUND_HALF_EVEN
    )
    assert values["metric.rsi-14-wilder"] == Decimal("100.0000000000")
    assert values["metric.atr-20-wilder"] == Decimal("3.0000000000")

    lower, upper, percent_b, bandwidth = con.execute("""
        WITH stats AS (
            SELECT avg(i::DOUBLE) mean, stddev_pop(i::DOUBLE) sigma
            FROM range(101, 121) t(i)
        ), bands AS (
            SELECT mean, mean - 2 * sigma lower_band, mean + 2 * sigma upper_band FROM stats
        )
        SELECT round(lower_band, 10), round(upper_band, 10),
               round((120 - lower_band) / (upper_band - lower_band), 10),
               round((upper_band - lower_band) / mean, 10)
        FROM bands
    """).fetchone()
    assert values["metric.bollinger-lower-20-2"] == Decimal(str(lower)).quantize(QUANTUM)
    assert values["metric.bollinger-upper-20-2"] == Decimal(str(upper)).quantize(QUANTUM)
    assert values["metric.bollinger-percent-b-20-2"] == Decimal(str(percent_b)).quantize(QUANTUM)
    assert values["metric.bollinger-bandwidth-20-2"] == Decimal(str(bandwidth)).quantize(QUANTUM)
    assert con.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0] == 11
    assert con.execute("SELECT count(*) FROM control.metric_definitions").fetchone()[0] == 11
    con.close()


def test_insufficient_and_reconstructed_histories_are_null_quality_outcomes() -> None:
    insufficient = duckdb.connect(":memory:")
    MigrationRunner(insufficient).apply()
    evaluation_at = datetime(2026, 6, 1, tzinfo=UTC)
    _load_bars(V2WarehouseRepository(insufficient), count=10, knowledge_at=evaluation_at - timedelta(hours=1))
    values = _evaluate(insufficient, evaluation_at)
    assert {value.quality_status for value in values} == {"insufficient_history"}
    assert all(value.value is None for value in values)
    insufficient.close()

    reconstructed = duckdb.connect(":memory:")
    MigrationRunner(reconstructed).apply()
    _load_bars(
        V2WarehouseRepository(reconstructed),
        count=120,
        knowledge_at=evaluation_at - timedelta(hours=1),
        reconstruction_mode="retrospective_reconstructed",
    )
    values = _evaluate(reconstructed, evaluation_at)
    assert {value.quality_status for value in values} == {"retrospective_reconstructed"}
    assert all(value.value is None for value in values)
    reconstructed.close()


def test_future_price_revision_cannot_change_strict_historical_metric() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    evaluation_at = datetime(2026, 6, 1, tzinfo=UTC)
    warehouse = V2WarehouseRepository(con)
    _load_bars(warehouse, count=120, knowledge_at=evaluation_at - timedelta(hours=1))
    _load_bars(
        warehouse,
        count=120,
        knowledge_at=evaluation_at + timedelta(days=1),
        close_offset=1000,
    )

    values = {value.definition.metric_id: value for value in _evaluate(con, evaluation_at)}
    assert values["metric.sma-adjusted-close-20"].value == Decimal("110.5000000000")
    assert all(item.knowledge_at <= evaluation_at for item in values["metric.sma-adjusted-close-20"].inputs)
    con.close()


def test_zero_volume_ratio_is_unavailable_not_an_exception_or_zero() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    evaluation_at = datetime(2026, 6, 1, tzinfo=UTC)
    _load_bars(
        V2WarehouseRepository(con),
        count=20,
        knowledge_at=evaluation_at - timedelta(hours=1),
        zero_volume=True,
    )
    values = {value.definition.metric_id: value for value in _evaluate(con, evaluation_at)}
    assert values["metric.volume-sma-20"].value == Decimal("0E-10")
    assert values["metric.volume-ratio-20"].value is None
    assert values["metric.volume-ratio-20"].quality_status == "zero_denominator"
    con.close()


def test_wilder_formulas_match_independent_python_recurrence() -> None:
    closes = [
        Decimal(value) for value in (
            "54.8", "56.8", "57.85", "59.85", "60.57", "61.1", "62.17", "60.6",
            "62.35", "62.15", "62.35", "61.45", "62.8", "61.37", "62.5", "62.57",
            "60.8", "59.37", "60.35", "62.35",
        )
    ]
    at = datetime(2026, 1, 1, tzinfo=UTC)
    inputs = tuple(
        MetricInput(f"close-{index}", close, at, at, "pass", f"hash-{index}")
        for index, close in enumerate(closes)
    )
    changes = [current - prior for prior, current in zip(closes[:-1], closes[1:], strict=True)]
    gains = [change if change > 0 else Decimal("0") for change in changes]
    losses = [-change if change < 0 else Decimal("0") for change in changes]
    average_gain = sum(gains[:14], Decimal("0")) / Decimal("14")
    average_loss = sum(losses[:14], Decimal("0")) / Decimal("14")
    for gain, loss in zip(gains[14:], losses[14:], strict=True):
        average_gain = (average_gain * Decimal("13") + gain) / Decimal("14")
        average_loss = (average_loss * Decimal("13") + loss) / Decimal("14")
    independent_rsi = (
        Decimal("100") - Decimal("100") / (Decimal("1") + average_gain / average_loss)
    ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    assert rsi_14_wilder(inputs) == independent_rsi

    atr_inputs: list[MetricInput] = []
    true_ranges: list[Decimal] = []
    previous_close = None
    for index, close in enumerate(closes):
        high, low = close + Decimal(index % 3 + 1), close - Decimal(index % 2 + 1)
        for field, value in (("high", high), ("low", low), ("close", close)):
            atr_inputs.append(MetricInput(f"bar-{index}-{field}", value, at, at, "pass", f"h-{index}"))
        candidates = [high - low]
        if previous_close is not None:
            candidates.extend([abs(high - previous_close), abs(low - previous_close)])
        true_ranges.append(max(candidates))
        previous_close = close
    independent_atr = (sum(true_ranges, Decimal("0")) / Decimal("20")).quantize(QUANTUM)
    assert atr_20_wilder(tuple(atr_inputs)) == independent_atr
