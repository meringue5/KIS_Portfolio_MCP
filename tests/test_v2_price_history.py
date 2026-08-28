from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import duckdb

from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


def _observation(repository: V2WarehouseRepository, *, fetched_at: datetime, close: str) -> str:
    payload = {"page": 1, "close": close}
    content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return repository.record_observation(
        "dataset.price-bar-daily",
        SourceEnvelope(
            source_id="source.kis-open-api",
            source_record_id=f"KRX:005930:adjusted:{fetched_at.isoformat()}",
            observed_at=datetime(2026, 8, 27, 6, 30, tzinfo=UTC),
            fetched_at=fetched_at,
            payload=payload,
            content_hash=content_hash,
        ),
        "price-fixture-run",
    )


def _bar(close: str, knowledge_at: datetime) -> dict:
    return {
        "instrument_id": "v1|KRX|005930",
        "session_date": date(2026, 8, 27),
        "price_basis": "adjusted",
        "open": "100",
        "high": "120",
        "low": "90",
        "close": close,
        "volume": 1000,
        "effective_at": datetime(2026, 8, 27, 6, 30, tzinfo=UTC),
        "knowledge_at": knowledge_at,
        "endpoint": "domestic.inquire-daily-itemchartprice",
        "request_option": "0",
        "volume_basis": "vendor_reported",
        "reconstruction_mode": "retrospective_reconstructed",
        "quality_status": "pass",
    }


def test_price_revisions_are_content_idempotent_and_point_in_time() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    first_knowledge = datetime(2026, 8, 27, 7, tzinfo=UTC)
    later_knowledge = datetime(2026, 8, 28, 7, tzinfo=UTC)
    first_observation = _observation(repository, fetched_at=first_knowledge, close="110")
    repository.upsert_price_bar(_bar("110", first_knowledge), first_observation)

    duplicate_observation = _observation(repository, fetched_at=later_knowledge, close="110")
    repository.upsert_price_bar(_bar("110", later_knowledge), duplicate_observation)
    assert repository.table_count("silver.price_bar_revisions_daily") == 1

    changed_observation = _observation(repository, fetched_at=later_knowledge, close="111")
    repository.upsert_price_bar(_bar("111", later_knowledge), changed_observation)
    assert repository.table_count("silver.price_bar_revisions_daily") == 2
    assert con.execute("SELECT close FROM silver.price_bars_daily").fetchone()[0] == 111

    cutoff = datetime(2026, 8, 27, 8, tzinfo=UTC)
    strict = repository.get_price_bars_as_of(
        instrument_id="v1|KRX|005930",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 27),
        price_basis="adjusted",
        evaluation_at=cutoff,
    )
    assert [row["close"] for row in strict] == [110]

    reconstructed = repository.get_price_bars_as_of(
        instrument_id="v1|KRX|005930",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 27),
        price_basis="adjusted",
        evaluation_at=cutoff,
        replay_mode="retrospective_reconstructed",
    )
    assert [row["close"] for row in reconstructed] == [111]
    assert repository.get_price_bars_as_of(
        instrument_id="v1|KRX|005930",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 8, 27),
        price_basis="raw",
        evaluation_at=cutoff,
        replay_mode="retrospective_reconstructed",
    ) == []
    con.close()
