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
        ) VALUES ('2026-09-11','kr-1000',?,?,?,NULL,?,NULL,NULL,NULL,NULL,?,'{}','pass',?)
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
    assert result["data"]["summary"]["quality_status"] == "pass"
    assert {row["account_label"] for row in result["data"]["positions"]} == {"alpha"}


@pytest.mark.anyio
async def test_pipeline_run_accepts_logical_run_handle_for_reused_run():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    logical_key = (
        "970077c2e85a0ca3e9cf7af0fe7c1be7876443c6e37926d47ce4865d11dc18d5"
    )
    connection.execute(
        """
        INSERT INTO control.pipeline_runs(
            run_id, pipeline_id, pipeline_version, logical_date, slot, partition_key,
            idempotency_key, status, source_calls, started_at, finished_at
        ) VALUES ('scheduler-run-1', 'pipeline.owned-portfolio-core-v2', '1.0.0',
                  '2026-09-11', 'kr-1600', 'all-accounts', ?, 'succeeded', 0, ?, ?)
        """,
        [logical_key, NOW, NOW],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    result = await application.execute(
        "get-pipeline-run", PipelineRunRequest(run_id=logical_key, as_of=NOW), ACTOR
    )

    assert result["data"]["runs"][0]["run_id"] == "scheduler-run-1"
    assert result["data"]["runs"][0]["status"] == "succeeded"


@pytest.mark.anyio
async def test_pipeline_run_accepts_public_portfolio_refresh_name():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        """
        INSERT INTO control.pipeline_runs(
            run_id, pipeline_id, pipeline_version, logical_date, slot, partition_key,
            idempotency_key, status, source_calls, started_at, finished_at
        ) VALUES ('run-1', 'pipeline.owned-portfolio-core-v2', '1.0.0',
                  '2026-09-11', 'kr-1600', 'all-accounts', 'logical-key',
                  'succeeded', 39, ?, ?)
        """,
        [NOW, NOW],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    result = await application.execute(
        "get-pipeline-run",
        PipelineRunRequest(pipeline_id="portfolio-refresh", as_of=NOW, lookback_days=1),
        ACTOR,
    )

    assert result["data"]["runs"][0]["pipeline_id"] == "pipeline.owned-portfolio-core-v2"
    assert result["source"]["dataset_id"] == "dataset.pipeline-run-evidence"


@pytest.mark.anyio
async def test_unknown_public_pipeline_name_fails_explicitly(application):
    with pytest.raises(RemoteReadError, match="unknown_pipeline_reference"):
        await application.execute(
            "get-pipeline-run",
            PipelineRunRequest(pipeline_id="not-a-pipeline", as_of=NOW),
            ACTOR,
        )


@pytest.mark.anyio
async def test_market_snapshot_resolves_public_kr_symbol_and_returns_raw_bar():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        """
        INSERT INTO silver.price_bars_daily(
            instrument_id, session_date, price_basis, close, source_observation_id,
            quality_status, effective_at, knowledge_at
        ) VALUES
            ('v1|KRX|000660', '2026-09-11', 'raw', 1812000, 'raw-1', 'pass', ?, ?),
            ('v1|KRX|000660', '2026-09-11', 'adjusted', 1811000, 'adj-1', 'pass', ?, ?)
        """,
        [NOW, NOW, NOW, NOW],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    for instrument_ref in ("000660", "KRX:000660", "v1|KRX|000660"):
        result = await application.execute(
            "get-market-snapshot",
            MarketSnapshotRequest(instrument_id=instrument_ref, market="KR"),
            ACTOR,
        )
        assert result["data"]["snapshot"]["instrument_id"] == "v1|KRX|000660"
        assert result["data"]["snapshot"]["price_basis"] == "raw"
        assert result["data"]["snapshot"]["close"] == "1812000.00000000"
        assert result["missing_coverage"] == []


@pytest.mark.anyio
async def test_market_snapshot_rejects_instrument_market_mismatch(application):
    with pytest.raises(RemoteReadError, match="instrument_market_mismatch"):
        await application.execute(
            "get-market-snapshot",
            MarketSnapshotRequest(instrument_id="US:AAPL", market="KR"),
            ACTOR,
        )


@pytest.mark.anyio
async def test_exposure_analysis_returns_direct_positions_and_explicit_optional_gaps():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        "INSERT INTO silver.accounts VALUES ('acct-a','ria','brokerage','KRW',?,NULL,'{}')",
        [NOW],
    )
    connection.execute(
        """
        INSERT INTO silver.instruments VALUES (
            'v1|KRX|000660','KRX','000660','SK hynix','equity','KRW','unknown',?,NULL,'fixture','{}'
        )
        """,
        [NOW],
    )
    connection.execute(
        """
        INSERT INTO gold.portfolio_daily_state(
            evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level,
            quantity, value_krw, cost_krw, unrealized_pnl_krw, contribution_pct,
            allocation_pct, as_of, input_watermarks, quality_status, lineage_hash
        ) VALUES ('2026-09-11','kr-1600','acct-a','v1|KRX|000660','position',
                  110,199320000,NULL,NULL,NULL,27.5,?,'{}','pass','lineage')
        """,
        [NOW],
    )
    application = RemoteReadApplication(
        WarehouseReadQueryPort(connection), expected_resource=RESOURCE
    )

    result = await application.execute(
        "get-exposure-analysis", ExposureAnalysisRequest(), ACTOR
    )

    assert result["data"]["direct"][0]["instrument_id"] == "v1|KRX|000660"
    assert result["data"]["direct"][0]["value_krw"] == "199320000.00"
    assert result["quality"]["status"] == "pass"
    assert result["missing_coverage"] == [
        {"dataset_id": "dataset.macro-profile-snapshot", "reason": "no_governed_rows"},
        {"dataset_id": "dataset.etf-constituent-snapshot", "reason": "unsupported_initial_v2"},
    ]


@pytest.mark.anyio
async def test_data_quality_distinguishes_missing_evidence_from_missing_dataset_rows(application):
    result = await application.execute(
        "get-data-quality",
        DataQualityRequest(
            dataset_id="dataset.price-bar-daily", as_of=NOW, lookback_days=1
        ),
        ACTOR,
    )

    assert result["data"]["results"] == []
    assert result["source"]["dataset_id"] == "dataset.data-quality-evidence"
    assert result["missing_coverage"] == [{
        "dataset_id": "dataset.price-bar-daily",
        "reason": "no_quality_evidence_in_window",
    }]


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
