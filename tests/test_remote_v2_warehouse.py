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
