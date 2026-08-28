from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner


def _payload(valid_from, asset_type="etf"):
    return {
        "instrument_id": "v1|KRX|0019K0", "market": "KRX", "symbol": "0019K0",
        "name": "Synthetic ETF", "asset_type": asset_type, "economic_exposure": "unknown",
        "currency": "KRW", "valid_from": valid_from, "knowledge_at": valid_from,
        "classification_source": "kis_instrument_master", "classification_quality": "official_reference",
        "metadata": {"group_code": "E"},
    }


def test_instrument_versions_are_idempotent_and_point_in_time():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = InstrumentWarehouseRepository(con)
    first_at = datetime(2026, 8, 1, tzinfo=UTC)
    second_at = first_at + timedelta(days=10)
    first = repository.record_version(_payload(first_at), "obs-1")
    replay = repository.record_version(_payload(second_at), "obs-2")
    second = repository.record_version(_payload(second_at, "reit"), "obs-3")

    assert replay == first
    assert second != first
    assert repository.as_of("v1|KRX|0019K0", first_at + timedelta(days=1))["asset_type"] == "etf"
    assert repository.as_of("v1|KRX|0019K0", second_at + timedelta(days=1))["asset_type"] == "reit"
    assert con.execute("select count(*) from silver.instrument_versions").fetchone()[0] == 2
    assert con.execute("select asset_type from silver.instruments_current").fetchone()[0] == "reit"
    with pytest.raises(ValueError, match="valid_from must advance"):
        repository.record_version(_payload(first_at + timedelta(days=5), "bond"), "obs-4")
    con.close()
