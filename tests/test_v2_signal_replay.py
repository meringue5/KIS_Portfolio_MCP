from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import duckdb
import pytest

from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.application import signal_replay
from kis_portfolio.application.signal_replay import (
    calibrate_price_history,
    load_price_replay_observations,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


def _fixture(*, asset_type: str = "etf", count: int = 21) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    warehouse = V2WarehouseRepository(connection)
    knowledge_at = datetime(2026, 8, 28, tzinfo=UTC)
    payload = {"fixture": "signal-replay", "count": count}
    observation_id = warehouse.record_observation(
        "dataset.price-bar-daily",
        SourceEnvelope(
            "source.kis-open-api", "signal-replay-page", knowledge_at, knowledge_at,
            payload, hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), "pass",
        ),
        "signal-replay-fixture",
    )
    InstrumentWarehouseRepository(connection).record_version({
        "instrument_id": "instrument-fixture",
        "market": "KRX",
        "symbol": "FIXTURE",
        "name": "Synthetic ETF",
        "asset_type": asset_type,
        "economic_exposure": "opaque_listed_security",
        "currency": "KRW",
        "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
        "knowledge_at": knowledge_at,
        "classification_source": "fixture",
        "classification_quality": "pass" if asset_type != "unknown" else "unknown",
    }, observation_id)
    start = date(2023, 1, 1)
    bars = []
    for index in range(count):
        session = start + timedelta(days=index)
        close = Decimal("100") + index
        bars.append({
            "instrument_id": "instrument-fixture",
            "session_date": session,
            "price_basis": "adjusted",
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "volume": 1000 + index,
            "effective_at": datetime.combine(session, datetime.min.time(), tzinfo=UTC),
            "knowledge_at": knowledge_at,
            "endpoint": "fixture.adjusted-history",
            "request_option": "adjusted",
            "volume_basis": "vendor_reported",
            "reconstruction_mode": "retrospective_reconstructed",
            "quality_status": "pass",
        })
    warehouse.upsert_price_bars(bars, observation_id)
    return connection


def test_price_replay_projects_only_rolling_history_and_preserves_reconstruction_label() -> None:
    connection = _fixture()
    observations = load_price_replay_observations(
        connection, start_date=date(2023, 1, 1), end_date=date(2023, 1, 21)
    )
    assert len(observations) == 21
    assert observations[0].daily_return is None
    assert observations[-1].valid_bar_count == 21
    assert observations[-1].vol20 is not None
    assert observations[-1].sma20 == Decimal("110.5")
    assert observations[-1].sma50 is None
    assert observations[-1].asset_class == "etf"
    assert observations[-1].provenance_mode == "retrospective_reconstructed"
    assert observations[-1].evaluation_slot == "kr-1600"
    connection.close()


def test_unknown_asset_class_is_not_coerced_and_blocks_three_year_readiness() -> None:
    connection = _fixture(asset_type="unknown", count=1096)
    result = calibrate_price_history(
        connection, start_date=date(2023, 1, 1), end_date=date(2026, 1, 1)
    )
    unknown = result.report["asset_classes"]["unknown"]  # type: ignore[index]
    assert unknown["observed_session_date_count"] == 1096
    assert unknown["three_year_coverage_ready"] is False
    assert any("never coerced" in item for item in result.report["limitations"])
    connection.close()


def test_price_replay_fails_before_reading_an_unbounded_window(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _fixture(count=3)
    monkeypatch.setattr(signal_replay, "MAX_REPLAY_ROWS", 2)
    with pytest.raises(RuntimeError, match="bounded row budget"):
        load_price_replay_observations(
            connection, start_date=date(2023, 1, 1), end_date=date(2023, 1, 3)
        )
    connection.close()
