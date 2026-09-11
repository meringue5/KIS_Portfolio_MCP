from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb
import pytest

from kis_portfolio.adapters.outbound.remote_v2_warehouse import WarehouseReadQueryPort
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.remote_read_surface import (
    V2_READ_TOOL_NAMES,
    DataCatalogRequest,
    DataQualityRequest,
    DividendSummaryRequest,
    ExposureAnalysisRequest,
    FundamentalOutlookRequest,
    JournalReviewQueueRequest,
    MarketHistoryRequest,
    MarketSnapshotRequest,
    PerformanceHistoryRequest,
    PipelineRunRequest,
    PortfolioOverviewRequest,
    PositionAnalysisRequest,
    ReadActor,
    RemoteReadApplication,
    RemoteReadError,
    SignalStatusRequest,
    TradeLedgerRequest,
    TradeThreadRequest,
)


RESOURCE = "https://portfolio.example.test"
ACTOR = ReadActor("owner", "client", frozenset({"mcp:read"}), RESOURCE, "request-1")
NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)


@pytest.fixture
def application() -> RemoteReadApplication:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return RemoteReadApplication(
        WarehouseReadQueryPort(connection),
        expected_resource=RESOURCE,
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


REQUESTS = {
    "get-portfolio-overview": PortfolioOverviewRequest(),
    "get-position-analysis": PositionAnalysisRequest(),
    "get-performance-history": PerformanceHistoryRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 11)
    ),
    "get-market-snapshot": MarketSnapshotRequest(instrument_id="KR:005930", market="KR"),
    "get-market-history": MarketHistoryRequest(
        instrument_id="KR:005930", market="KR", start_date=date(2026, 9, 1), end_date=date(2026, 9, 11)
    ),
    "get-trade-ledger": TradeLedgerRequest(start_date=date(2026, 9, 1), end_date=date(2026, 9, 11)),
    "get-trade-thread": TradeThreadRequest(),
    "get-dividend-summary": DividendSummaryRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 11)
    ),
    "get-fundamental-outlook": FundamentalOutlookRequest(instrument_id="US:AAPL"),
    "get-exposure-analysis": ExposureAnalysisRequest(),
    "get-signal-status": SignalStatusRequest(),
    "get-data-catalog": DataCatalogRequest(kind="object"),
    "get-data-quality": DataQualityRequest(dataset_id="dataset.portfolio-position-observation", as_of=NOW),
    "get-pipeline-run": PipelineRunRequest(pipeline_id="pipeline.owned-portfolio-core-v2", as_of=NOW),
    "get-journal-review-queue": JournalReviewQueueRequest(),
}


@pytest.mark.parametrize("tool_name", V2_READ_TOOL_NAMES)
@pytest.mark.anyio
async def test_production_warehouse_port_compiles_every_governed_query(application, tool_name):
    result = await application.execute(tool_name, REQUESTS[tool_name], ACTOR)

    assert result["schema_version"] == "2.0.0"
    assert result["request_id"] == "request-1"
    assert result["source"]["mode"] == "stored"
    assert result["quality"]["status"] in {"pass", "partial"}


def test_port_capabilities_are_exactly_the_approved_read_catalog():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()

    assert WarehouseReadQueryPort(connection).capabilities() == frozenset(V2_READ_TOOL_NAMES)


@pytest.mark.anyio
async def test_portfolio_overview_summary_respects_account_alias():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        "INSERT INTO silver.accounts VALUES "
        "('acct-a','alpha','brokerage','KRW',?,NULL,'{}'),"
        "('acct-b','beta','isa','KRW',?,NULL,'{}')",
        [NOW, NOW],
    )
    connection.executemany(
        """
        INSERT INTO gold.portfolio_daily_state(
            evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level,
            quantity, value_krw, cost_krw, unrealized_pnl_krw, contribution_pct,
            allocation_pct, as_of, input_watermarks, quality_status, lineage_hash
        ) VALUES ('2026-09-11','kr-1000',?,?,?,NULL,?,NULL,NULL,NULL,NULL,?,'{}','passed',?)
        """,
        [
            ("acct-a", "KR:AAA", "position", "100", NOW, "lineage-a-position"),
            ("acct-a", "cash|KRW", "cash", "25", NOW, "lineage-a-cash"),
            ("acct-b", "KR:BBB", "position", "900", NOW, "lineage-b-position"),
        ],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    result = await application.execute(
        "get-portfolio-overview", PortfolioOverviewRequest(account_alias="alpha"), ACTOR
    )

    assert result["data"]["summary"]["total_value_krw"] == "125.00"
    assert {row["account_label"] for row in result["data"]["positions"]} == {"alpha"}


@pytest.mark.anyio
async def test_performance_history_respects_account_alias():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        "INSERT INTO silver.accounts VALUES "
        "('acct-a','alpha','brokerage','KRW',?,NULL,'{}'),"
        "('acct-b','beta','isa','KRW',?,NULL,'{}')",
        [NOW, NOW],
    )
    connection.executemany(
        """
        INSERT INTO gold.portfolio_daily_state(
            evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level,
            quantity, value_krw, cost_krw, unrealized_pnl_krw, contribution_pct,
            allocation_pct, as_of, input_watermarks, quality_status, lineage_hash
        ) VALUES ('2026-09-11','kr-1000',?,?,'position',NULL,?,NULL,NULL,NULL,NULL,?,'{}','passed',?)
        """,
        [
            ("acct-a", "KR:AAA", "100", NOW, "lineage-a"),
            ("acct-b", "KR:BBB", "900", NOW, "lineage-b"),
        ],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    result = await application.execute(
        "get-performance-history",
        PerformanceHistoryRequest(
            start_date=date(2026, 9, 11), end_date=date(2026, 9, 11),
            account_alias="alpha",
        ),
        ACTOR,
    )

    assert result["data"]["history"][0]["total_value_krw"] == "100.00"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "request_model", "code"),
    [
        (
            "get-performance-history",
            PerformanceHistoryRequest(
                start_date=date(2026, 9, 1), end_date=date(2026, 9, 11), grain="weekly"
            ),
            "unsupported_performance_grain",
        ),
        (
            "get-trade-ledger",
            TradeLedgerRequest(
                start_date=date(2026, 9, 1), end_date=date(2026, 9, 11), cursor="opaque"
            ),
            "unsupported_cursor",
        ),
        (
            "get-journal-review-queue",
            JournalReviewQueueRequest(account_alias="alpha"),
            "unsupported_review_account_filter",
        ),
    ],
)
async def test_unimplemented_read_projections_fail_closed(
    application, tool_name, request_model, code
):
    with pytest.raises(RemoteReadError) as exc_info:
        await application.execute(tool_name, request_model, ACTOR)

    assert str(exc_info.value) == code
