from datetime import UTC, date, datetime, timedelta

import duckdb
import pytest

from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.price_history import (
    CallBudget,
    PriceHistoryError,
    PricePage,
    PricePartition,
    collect_price_partition,
    plan_held_price_backfill,
    run_held_price_backfill,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def domestic_row(day: date, close: int = 100) -> dict:
    return {
        "stck_bsop_date": day.strftime("%Y%m%d"),
        "stck_oprc": str(close), "stck_hgpr": str(close + 2),
        "stck_lwpr": str(close - 2), "stck_clpr": str(close), "acml_vol": "1000",
    }


def overseas_row(day: date, close: int = 100) -> dict:
    return {
        "xymd": day.strftime("%Y%m%d"), "open": str(close), "high": str(close + 2),
        "low": str(close - 2), "clos": str(close), "tvol": "1000",
    }


class FixtureFetcher:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def fetch_page(self, partition, *, cursor_end, continuation):
        self.calls.append((cursor_end, continuation, partition.request_option))
        return self.pages.pop(0)


@pytest.fixture
def repository():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    return con, V2WarehouseRepository(con)


@pytest.mark.anyio
async def test_domestic_100_row_boundary_moves_cursor_and_preserves_raw_page(repository):
    con, repo = repository
    end = date(2026, 8, 28)
    first_days = [end - timedelta(days=offset) for offset in range(100)]
    second_day = first_days[-1] - timedelta(days=1)
    fetcher = FixtureFetcher([
        PricePage({"output2": [domestic_row(day) for day in first_days]}),
        PricePage({"output2": [domestic_row(second_day)]}),
    ])
    partition = PricePartition("v1|KRX|005930", "KRX", "005930", second_day, end, "raw")

    result = await collect_price_partition(
        repo, partition, fetcher=fetcher, run_id="run-1", budget=CallBudget(10),
    )

    assert result["page_count"] == 2
    assert result["distinct_session_count"] == 101
    assert fetcher.calls == [(end, "", "1"), (second_day, "", "1")]
    assert con.execute("select count(*) from bronze.source_observations").fetchone()[0] == 2
    assert con.execute("select count(*) from silver.price_bar_revisions_daily").fetchone()[0] == 101


@pytest.mark.anyio
async def test_overseas_continuation_uses_n_and_adjusted_option(repository):
    _, repo = repository
    end = date(2026, 8, 28)
    oldest = end - timedelta(days=9)
    fetcher = FixtureFetcher([
        PricePage({"output2": [overseas_row(end), overseas_row(oldest)]}, "F"),
        PricePage({"output2": [overseas_row(oldest - timedelta(days=1))]}),
    ])
    partition = PricePartition(
        "v1|NAS|AAPL", "NAS", "AAPL", oldest - timedelta(days=1), end, "adjusted",
    )

    result = await collect_price_partition(
        repo, partition, fetcher=fetcher, run_id="run-2", budget=CallBudget(10),
    )

    assert result["page_count"] == 2
    assert fetcher.calls == [
        (end, "", "1"),
        (oldest - timedelta(days=1), "N", "1"),
    ]


@pytest.mark.anyio
async def test_cursor_stall_and_global_call_ceiling_fail_closed(repository):
    _, repo = repository
    end = date(2026, 8, 28)
    rows = [domestic_row(end) for _ in range(100)]
    partition = PricePartition("v1|KRX|005930", "KRX", "005930", end - timedelta(days=10), end, "raw")
    fetcher = FixtureFetcher([PricePage({"output2": rows}), PricePage({"output2": rows})])
    with pytest.raises(PriceHistoryError, match="did not move backward"):
        await collect_price_partition(
            repo, partition, fetcher=fetcher, run_id="run-3", budget=CallBudget(10),
        )

    with pytest.raises(PriceHistoryError, match="budget exhausted"):
        await collect_price_partition(
            repo, partition, fetcher=FixtureFetcher([PricePage({"output2": rows})]),
            run_id="run-4", budget=CallBudget(0),
        )


def test_planner_reserves_held_dual_basis_and_rejects_over_budget(repository):
    con, _ = repository
    observed = datetime(2026, 8, 28, tzinfo=UTC)
    con.execute("INSERT INTO silver.instruments VALUES ('v1|KRX|005930','KRX','005930','Synthetic','stock','KRW',NULL,?,NULL,'source','{}')", [observed])
    con.execute("INSERT INTO silver.position_snapshots VALUES ('a','v1|KRX|005930',?,1,1,'KRW','obs','pass')", [observed])
    partitions, plan = plan_held_price_backfill(
        con, start_date=date(2025, 8, 28), end_date=date(2026, 8, 28), max_physical_calls=10,
    )
    assert [item.price_basis for item in partitions] == ["raw", "adjusted"]
    assert plan["estimated_physical_calls"] == 6
    with pytest.raises(PriceHistoryError, match="planned physical call budget exceeded"):
        plan_held_price_backfill(
            con, start_date=date(2025, 8, 28), end_date=date(2026, 8, 28), max_physical_calls=5,
        )


def test_managed_backfill_records_run_quality_lineage_and_watermarks(repository):
    con, _ = repository
    observed = datetime(2026, 8, 28, tzinfo=UTC)
    con.execute("INSERT INTO silver.instruments VALUES ('v1|KRX|005930','KRX','005930','Synthetic','stock','KRW',NULL,?,NULL,'source','{}')", [observed])
    con.execute("INSERT INTO silver.position_snapshots VALUES ('a','v1|KRX|005930',?,1,1,'KRW','obs','pass')", [observed])
    fetcher = FixtureFetcher([
        PricePage({"output2": [domestic_row(date(2026, 8, 28))]}),
        PricePage({"output2": [domestic_row(date(2026, 8, 28), 99)]}),
    ])

    result = run_held_price_backfill(
        con,
        start_date=date(2026, 8, 28),
        end_date=date(2026, 8, 28),
        dry_run=False,
        fetcher=fetcher,
        max_physical_calls=2,
    )

    assert result["status"] == "succeeded"
    assert result["source_calls"] == 2
    assert con.execute("select count(*) from control.quality_results").fetchone()[0] == 1
    assert con.execute("select count(*) from control.lineage_edges").fetchone()[0] == 1
    assert con.execute("select count(*) from control.watermarks").fetchone()[0] == 2
    assert con.execute("select count(*) from silver.price_bar_revisions_daily").fetchone()[0] == 2
