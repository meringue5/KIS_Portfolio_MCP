from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.fixture_source import FixtureSourceAdapter
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


FIXTURES = Path(__file__).with_name("fixtures") / "v2"


def test_fixture_adapter_and_canonical_ledger_are_idempotent(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "ledger.duckdb"))
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    source = FixtureSourceAdapter(FIXTURES / "kis_owned_portfolio.json")
    lot_id = None
    trade_id = None
    for envelope in source.collect({}):
        observation_id = repository.record_observation("dataset.portfolio-position-observation", envelope, "fixture-run")
        payload = envelope.payload
        if payload["type"] == "account":
            repository.upsert_account(payload, observation_id)
        elif payload["type"] == "instrument":
            repository.upsert_instrument(payload, observation_id)
        elif payload["type"] == "position":
            repository.upsert_position(payload, observation_id)
        elif payload["type"] == "trade":
            trade_id, lot_id = repository.record_trade_with_lot(payload, observation_id)
        elif payload["type"] == "price":
            repository.upsert_price_bar(payload, observation_id)

    thread_id = repository.create_thread({
        "thread_id": "fixture-thread",
        "account_id": "fixture-ria",
        "instrument_id": "KRX:005930",
        "opened_at": "2026-08-01T01:15:00+00:00",
        "title": "Synthetic thesis",
    }, lot_id)
    repository.append_journal({
        "journal_id": "fixture-journal",
        "revision": 1,
        "thread_id": thread_id,
        "trade_event_id": trade_id,
        "body": "Synthetic fixture only.",
        "authored_at": "2026-08-01T01:20:00+00:00",
    })
    count = repository.materialize_daily_state(
        evaluation_date=date(2026, 8, 28), slot="16:00", as_of=datetime(2026, 8, 28, 7, tzinfo=UTC)
    )
    assert count == 1
    assert con.execute("SELECT value_krw, unrealized_pnl_krw FROM gold.portfolio_daily_state").fetchone() == (730000, 30000)

    # Replaying the same bytes and canonical writes has no effect.
    for envelope in source.collect({}):
        repository.record_observation("dataset.portfolio-position-observation", envelope, "fixture-run-2")
    assert repository.table_count("bronze.source_observations") == 5
    assert repository.table_count("silver.trade_event_revisions") == 1
    assert repository.table_count("silver.trade_events_current") == 1
    assert repository.table_count("silver.purchase_lots") == 1
    assert repository.table_count("silver.purchase_lots_current") == 1
    assert repository.table_count("gold.portfolio_daily_state") == 1
    con.close()


def test_unknown_trade_side_fails_before_creating_event_or_lot(tmp_path: Path) -> None:
    con = duckdb.connect(str(tmp_path / "unknown-side.duckdb"))
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)
    envelope = SourceEnvelope(
        "source.kis-open-api", "unknown-side", observed, observed,
        {"type": "trade", "side": "unknown"}, "fixture-hash", "degraded",
    )
    observation_id = repository.record_observation("dataset.trade-event", envelope, "fixture-run")
    payload = {
        "account_id": "fixture-ria", "account_product_code": "01", "market": "KRX",
        "instrument_id": "KRX:005930", "side": "unknown", "executed_at": observed,
        "quantity": "1", "price": "70000", "currency": "KRW",
        "broker_order_id": "fixture-unknown", "execution_sequence": "aggregate",
    }

    with pytest.raises(ValueError, match="trade side"):
        repository.record_trade_with_lot(payload, observation_id)

    assert repository.table_count("silver.trade_events") == 0
    assert repository.table_count("silver.trade_event_revisions") == 0
    assert repository.table_count("silver.purchase_lots") == 0
    con.close()


@pytest.mark.parametrize(
    ("fx_date", "expected_quality"),
    [
        (date(2026, 9, 11), "degraded"),
        (date(2026, 9, 16), "pass"),
        (None, "degraded"),
    ],
)
def test_foreign_daily_state_requires_recent_governed_fx(
    fx_date: date | None, expected_quality: str,
) -> None:
    """A pass-marked USD position must not use a missing or week-old FX rate."""
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    observed = datetime(2026, 9, 17, 1, tzinfo=UTC)
    con.executemany(
        "INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('KRX',?,true,'')",
        [[date(2026, 9, 16)], [date(2026, 9, 17)]],
    )
    con.execute("INSERT INTO silver.accounts VALUES ('account','brokerage','REAL','KRW',?,NULL,'{}')", [observed])
    con.execute(
        "INSERT INTO silver.instruments VALUES ('v1|NAS|TEST','NAS','TEST','Synthetic','equity','USD',NULL,?,NULL,'source','{}')",
        [observed],
    )
    con.execute(
        "INSERT INTO silver.position_snapshots VALUES ('account','v1|NAS|TEST',?,1,10,'USD','position-observation','pass')",
        [observed],
    )
    con.execute(
        "INSERT INTO silver.price_bars_daily(instrument_id,session_date,price_basis,close,source_observation_id,quality_status) "
        "VALUES ('v1|NAS|TEST','2026-09-16','raw',12,'price-observation','pass')",
    )
    if fx_date is not None:
        con.execute(
            "INSERT INTO silver.fx_rates_daily VALUES ('USD','KRW',?,'close',1300,'fx-observation','pass')",
            [fx_date],
        )

    V2WarehouseRepository(con).materialize_daily_state(
        evaluation_date=date(2026, 9, 17), slot="kr-1000", as_of=observed,
    )

    quality, = con.execute(
        "SELECT quality_status FROM gold.portfolio_daily_state WHERE instrument_id='v1|NAS|TEST'"
    ).fetchone()
    assert quality == expected_quality
    con.close()
