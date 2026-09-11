"""Inactive, parallel Remote MCP V2 read-only adapter for WI-042."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Callable, Literal
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from kis_portfolio.services.remote_read_surface import (
    MAX_RESPONSE_BYTES,
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
    ReadResponseEnvelope,
    RemoteReadApplication,
    SignalStatusRequest,
    TradeLedgerRequest,
    TradeThreadRequest,
)
from kis_portfolio.services.remote_commands import (
    CommandActor,
    CommandResponse,
    ManagedPipelineRequest,
    RemoteCommandApplication,
    ReviseTradeThreadRequest,
    ThreadChange,
    UpsertTradeJournalRequest,
    V2_COMMAND_TOOL_NAMES,
)


MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024
READ_ONLY_TOOL = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
NON_DESTRUCTIVE_WRITE_TOOL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
)
ActorProvider = Callable[[], ReadActor]
CommandActorProvider = Callable[[], CommandActor]
AccountAlias = Annotated[str, Field(min_length=1, max_length=64)]
InstrumentId = Annotated[str, Field(min_length=1, max_length=64)]
OpaqueId = Annotated[str, Field(min_length=1, max_length=160)]
Cursor = Annotated[str, Field(max_length=2_048)]
Limit50 = Annotated[int, Field(ge=1, le=50)]
Limit100 = Annotated[int, Field(ge=1, le=100)]
Limit200 = Annotated[int, Field(ge=1, le=200)]
Limit1000 = Annotated[int, Field(ge=1, le=1_000)]
LookbackDays = Annotated[int, Field(ge=1, le=31)]


@dataclass(frozen=True)
class ToolContract:
    name: str
    output_schema_ref: str
    sync_policy: str
    description: str

    @property
    def meta(self) -> dict[str, str]:
        return {
            "kis/scope": "mcp:read",
            "kis/outputSchemaRef": self.output_schema_ref,
            "kis/syncPolicy": self.sync_policy,
        }


TOOL_CONTRACTS = (
    ToolContract("get-portfolio-overview", "portfolio-overview.v2", "stored-or-bounded-read-through", "Return canonical total assets, allocation, holdings and valuation-change quality."),
    ToolContract("get-position-analysis", "position-analysis.v2", "stored", "Return bounded position, lot, thread, drawdown and risk analysis."),
    ToolContract("get-performance-history", "performance-history.v2", "stored", "Return cash-flow-adjusted performance and separately labelled KRW valuation-change contribution."),
    ToolContract("get-market-snapshot", "market-snapshot.v2", "cached-or-bounded-read-through", "Return a bounded current price, quote or FX snapshot with freshness."),
    ToolContract("get-market-history", "market-history.v2", "stored", "Return governed price or FX history with versioned technical context."),
    ToolContract("get-trade-ledger", "trade-ledger.v2", "stored", "Return canonical order, execution, transaction, settlement and cash-flow evidence."),
    ToolContract("get-trade-thread", "trade-thread.v2", "stored", "Return purchase-lot, trade-thread, sell-allocation and journal revisions."),
    ToolContract("get-dividend-summary", "dividend-summary.v2", "stored", "Return declared, entitled and received dividend reconciliation."),
    ToolContract("get-fundamental-outlook", "fundamental-outlook.v2", "stored", "Return actual, consensus, scenario and valuation outlook with point-in-time limits."),
    ToolContract("get-exposure-analysis", "exposure-analysis.v2", "stored", "Return direct and macro exposure; unsupported ETF look-through remains explicit."),
    ToolContract("get-signal-status", "signal-status.v2", "stored", "Return versioned signal state, inputs and quality."),
    ToolContract("get-data-catalog", "data-catalog.v1", "packaged", "Return the governed source, dataset, metric, pipeline or object catalog."),
    ToolContract("get-data-quality", "data-quality.v1", "control-read", "Return bounded freshness, completeness, reconciliation and known-gap evidence."),
    ToolContract("get-pipeline-run", "pipeline-run.v1", "control-read", "Return bounded pipeline run, stage, watermark and safe failure evidence."),
    ToolContract("get-journal-review-queue", "journal-review-queue.v2", "stored", "Return bounded owner-review questions without mutating journal state."),
)
_CONTRACT_BY_NAME = {item.name: item for item in TOOL_CONTRACTS}


@dataclass(frozen=True)
class CommandToolContract:
    name: str
    scope: str
    input_schema_ref: str
    output_schema_ref: str
    description: str

    @property
    def meta(self) -> dict[str, str]:
        return {
            "kis/scope": self.scope,
            "kis/inputSchemaRef": self.input_schema_ref,
            "kis/outputSchemaRef": self.output_schema_ref,
            "kis/syncPolicy": "async-run-id" if self.scope == "mcp:collect" else "append-only-revision",
        }


COMMAND_TOOL_CONTRACTS = (
    CommandToolContract(
        "run-managed-pipeline",
        "mcp:collect",
        "managed-pipeline-command.v1",
        "managed-command-result.v1",
        "Request the fixed portfolio-refresh pipeline and immediately return its run ID.",
    ),
    CommandToolContract(
        "upsert-trade-journal",
        "mcp:journal.write",
        "trade-journal-command.v1",
        "managed-command-result.v1",
        "Append an owner journal revision with optimistic concurrency and idempotency.",
    ),
    CommandToolContract(
        "revise-trade-thread",
        "mcp:journal.write",
        "trade-thread-command.v1",
        "managed-command-result.v1",
        "Append an explicit thread, lot link or sell-allocation revision.",
    ),
)
_COMMAND_CONTRACT_BY_NAME = {item.name: item for item in COMMAND_TOOL_CONTRACTS}


def actor_from_auth_context() -> ReadActor:
    """Project a validated MCP token without retaining its bearer value."""
    token = get_access_token()
    if token is None:
        return ReadActor("", "", frozenset(), None, uuid.uuid4().hex)
    return ReadActor(
        actor_id=token.subject or f"client:{token.client_id}",
        client_id=token.client_id,
        scopes=frozenset(token.scopes),
        resource=token.resource.rstrip("/") if token.resource else None,
        request_id=uuid.uuid4().hex,
    )


def command_actor_from_auth_context() -> CommandActor:
    """Project the same validated token into the command boundary."""
    token = get_access_token()
    if token is None:
        return CommandActor("", "", frozenset(), None, uuid.uuid4().hex)
    return CommandActor(
        actor_id=token.subject or "",
        client_id=token.client_id,
        scopes=frozenset(token.scopes),
        resource=token.resource.rstrip("/") if token.resource else None,
        request_id=uuid.uuid4().hex,
    )


def register_v2_read_tools(
    server: MCPServer,
    application: RemoteReadApplication,
    *,
    actor_provider: ActorProvider = actor_from_auth_context,
) -> None:
    async def invoke(name: str, request: object) -> ReadResponseEnvelope:
        result = await application.execute(name, request, actor_provider())
        return ReadResponseEnvelope.model_validate(result)

    def add(name: str, function: Callable) -> None:
        contract = _CONTRACT_BY_NAME[name]
        server.add_tool(
            function,
            name=name,
            description=contract.description,
            annotations=READ_ONLY_TOOL,
            meta=contract.meta,
            structured_output=True,
        )

    async def portfolio_overview(account_alias: AccountAlias | None = None, as_of: datetime | None = None, freshness_policy: Literal["stored", "cached", "bounded-live"] = "stored", include_holdings: bool = True) -> ReadResponseEnvelope:
        return await invoke("get-portfolio-overview", PortfolioOverviewRequest(account_alias=account_alias, as_of=as_of, freshness_policy=freshness_policy, include_holdings=include_holdings))

    async def position_analysis(instrument_id: InstrumentId | None = None, account_alias: AccountAlias | None = None, as_of: datetime | None = None, limit: Limit200 = 50) -> ReadResponseEnvelope:
        return await invoke("get-position-analysis", PositionAnalysisRequest(instrument_id=instrument_id, account_alias=account_alias, as_of=as_of, limit=limit))

    async def performance_history(start_date: date, end_date: date, account_alias: AccountAlias | None = None, grain: Literal["daily", "weekly", "monthly"] = "daily", limit: Limit1000 = 250) -> ReadResponseEnvelope:
        return await invoke("get-performance-history", PerformanceHistoryRequest(start_date=start_date, end_date=end_date, account_alias=account_alias, grain=grain, limit=limit))

    async def market_snapshot(instrument_id: InstrumentId, market: Literal["KR", "US", "FX"], freshness_policy: Literal["stored", "cached", "bounded-live"] = "cached") -> ReadResponseEnvelope:
        return await invoke("get-market-snapshot", MarketSnapshotRequest(instrument_id=instrument_id, market=market, freshness_policy=freshness_policy))

    async def market_history(instrument_id: InstrumentId, market: Literal["KR", "US", "FX"], start_date: date, end_date: date, adjusted: bool = True, limit: Limit1000 = 250) -> ReadResponseEnvelope:
        return await invoke("get-market-history", MarketHistoryRequest(instrument_id=instrument_id, market=market, start_date=start_date, end_date=end_date, adjusted=adjusted, limit=limit))

    async def trade_ledger(start_date: date, end_date: date, account_alias: AccountAlias | None = None, instrument_id: InstrumentId | None = None, cursor: Cursor | None = None, limit: Limit200 = 100) -> ReadResponseEnvelope:
        return await invoke("get-trade-ledger", TradeLedgerRequest(start_date=start_date, end_date=end_date, account_alias=account_alias, instrument_id=instrument_id, cursor=cursor, limit=limit))

    async def trade_thread(thread_id: OpaqueId | None = None, instrument_id: InstrumentId | None = None, account_alias: AccountAlias | None = None, as_of: datetime | None = None, cursor: Cursor | None = None, limit: Limit100 = 50) -> ReadResponseEnvelope:
        return await invoke("get-trade-thread", TradeThreadRequest(thread_id=thread_id, instrument_id=instrument_id, account_alias=account_alias, as_of=as_of, cursor=cursor, limit=limit))

    async def dividend_summary(start_date: date, end_date: date, account_alias: AccountAlias | None = None, instrument_id: InstrumentId | None = None, currency: Annotated[str, Field(min_length=3, max_length=3)] | None = None) -> ReadResponseEnvelope:
        return await invoke("get-dividend-summary", DividendSummaryRequest(start_date=start_date, end_date=end_date, account_alias=account_alias, instrument_id=instrument_id, currency=currency))

    async def fundamental_outlook(instrument_id: InstrumentId, as_of: datetime | None = None, scenario: Literal["bear", "base", "bull", "all"] = "all") -> ReadResponseEnvelope:
        return await invoke("get-fundamental-outlook", FundamentalOutlookRequest(instrument_id=instrument_id, as_of=as_of, scenario=scenario))

    async def exposure_analysis(account_alias: AccountAlias | None = None, as_of: datetime | None = None, include_macro: bool = True) -> ReadResponseEnvelope:
        return await invoke("get-exposure-analysis", ExposureAnalysisRequest(account_alias=account_alias, as_of=as_of, include_macro=include_macro))

    async def signal_status(signal_id: OpaqueId | None = None, instrument_id: InstrumentId | None = None, as_of: datetime | None = None, cursor: Cursor | None = None, limit: Limit100 = 50) -> ReadResponseEnvelope:
        return await invoke("get-signal-status", SignalStatusRequest(signal_id=signal_id, instrument_id=instrument_id, as_of=as_of, cursor=cursor, limit=limit))

    async def data_catalog(kind: Literal["source", "dataset", "metric", "pipeline", "macro_series", "object"], item_id: OpaqueId | None = None, cursor: Cursor | None = None, limit: Limit50 = 25) -> ReadResponseEnvelope:
        return await invoke("get-data-catalog", DataCatalogRequest(kind=kind, item_id=item_id, cursor=cursor, limit=limit))

    async def data_quality(dataset_id: OpaqueId, run_id: OpaqueId | None = None, as_of: datetime | None = None, lookback_days: LookbackDays = 7, cursor: Cursor | None = None, limit: Limit200 = 50) -> ReadResponseEnvelope:
        return await invoke("get-data-quality", DataQualityRequest(dataset_id=dataset_id, run_id=run_id, as_of=as_of, lookback_days=lookback_days, cursor=cursor, limit=limit))

    async def pipeline_run(run_id: OpaqueId | None = None, pipeline_id: OpaqueId | None = None, as_of: datetime | None = None, lookback_days: LookbackDays = 7, cursor: Cursor | None = None, limit: Limit50 = 20) -> ReadResponseEnvelope:
        return await invoke("get-pipeline-run", PipelineRunRequest(run_id=run_id, pipeline_id=pipeline_id, as_of=as_of, lookback_days=lookback_days, cursor=cursor, limit=limit))

    async def journal_review_queue(status: Literal["open", "answered", "all"] = "open", account_alias: AccountAlias | None = None, cursor: Cursor | None = None, limit: Limit100 = 25) -> ReadResponseEnvelope:
        return await invoke("get-journal-review-queue", JournalReviewQueueRequest(status=status, account_alias=account_alias, cursor=cursor, limit=limit))

    for name, function in (
        ("get-portfolio-overview", portfolio_overview),
        ("get-position-analysis", position_analysis),
        ("get-performance-history", performance_history),
        ("get-market-snapshot", market_snapshot),
        ("get-market-history", market_history),
        ("get-trade-ledger", trade_ledger),
        ("get-trade-thread", trade_thread),
        ("get-dividend-summary", dividend_summary),
        ("get-fundamental-outlook", fundamental_outlook),
        ("get-exposure-analysis", exposure_analysis),
        ("get-signal-status", signal_status),
        ("get-data-catalog", data_catalog),
        ("get-data-quality", data_quality),
        ("get-pipeline-run", pipeline_run),
        ("get-journal-review-queue", journal_review_queue),
    ):
        add(name, function)


def build_v2_read_server(
    application: RemoteReadApplication,
    *,
    actor_provider: ActorProvider = actor_from_auth_context,
) -> MCPServer:
    server = MCPServer("KIS Portfolio Service V2 Read", dependencies=[])
    register_v2_read_tools(server, application, actor_provider=actor_provider)
    return server


def register_v2_command_tools(
    server: MCPServer,
    application: RemoteCommandApplication,
    *,
    actor_provider: CommandActorProvider = command_actor_from_auth_context,
) -> None:
    async def invoke(name: str, request: object) -> CommandResponse:
        result = await application.execute(name, request, actor_provider())
        return CommandResponse.model_validate(result)

    def add(name: str, function: Callable) -> None:
        contract = _COMMAND_CONTRACT_BY_NAME[name]
        server.add_tool(
            function,
            name=name,
            description=contract.description,
            annotations=NON_DESTRUCTIVE_WRITE_TOOL,
            meta=contract.meta,
            structured_output=True,
        )

    async def run_managed_pipeline(
        logical_date: date,
        slot: Literal["kr-1000", "kr-1430", "kr-1600"],
        idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
        pipeline: Literal["portfolio-refresh"] = "portfolio-refresh",
    ) -> CommandResponse:
        return await invoke(
            "run-managed-pipeline",
            ManagedPipelineRequest(
                pipeline=pipeline,
                logical_date=logical_date,
                slot=slot,
                idempotency_key=idempotency_key,
            ),
        )

    async def upsert_trade_journal(
        journal_id: OpaqueId,
        body: Annotated[str, Field(min_length=1, max_length=20_000)],
        authored_at: datetime,
        expected_revision: Annotated[int, Field(ge=0)],
        idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
        thread_id: OpaqueId | None = None,
        trade_event_id: OpaqueId | None = None,
    ) -> CommandResponse:
        return await invoke(
            "upsert-trade-journal",
            UpsertTradeJournalRequest(
                journal_id=journal_id,
                thread_id=thread_id,
                trade_event_id=trade_event_id,
                body=body,
                authored_at=authored_at,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            ),
        )

    async def revise_trade_thread(
        thread_id: OpaqueId,
        change: ThreadChange,
        authored_at: datetime,
        expected_revision: Annotated[int, Field(ge=0)],
        idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
    ) -> CommandResponse:
        return await invoke(
            "revise-trade-thread",
            ReviseTradeThreadRequest(
                thread_id=thread_id,
                change=change,
                authored_at=authored_at,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            ),
        )

    for name, function in (
        ("run-managed-pipeline", run_managed_pipeline),
        ("upsert-trade-journal", upsert_trade_journal),
        ("revise-trade-thread", revise_trade_thread),
    ):
        add(name, function)


def build_v2_server(
    read_application: RemoteReadApplication,
    command_application: RemoteCommandApplication,
    *,
    read_actor_provider: ActorProvider = actor_from_auth_context,
    command_actor_provider: CommandActorProvider = command_actor_from_auth_context,
) -> MCPServer:
    """Build the exact inactive 18-tool V2 catalog without runtime wiring."""
    server = MCPServer("KIS Portfolio Service V2", dependencies=[])
    register_v2_read_tools(server, read_application, actor_provider=read_actor_provider)
    register_v2_command_tools(server, command_application, actor_provider=command_actor_provider)
    names = tuple(tool.name for tool in server._tool_manager.list_tools())
    if names != tuple(contract.name for contract in TOOL_CONTRACTS) + V2_COMMAND_TOOL_NAMES:
        raise RuntimeError("invalid V2 public tool catalog")
    return server


def create_v2_stateless_transport(
    application: RemoteReadApplication,
    *,
    resource_server_url: str,
    actor_provider: ActorProvider = actor_from_auth_context,
):
    """Build the official inactive transport; caller must add OAuth middleware."""
    resource = resource_server_url.rstrip("/")
    parts = urlsplit(resource)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[parts.netloc],
        allowed_origins=[
            f"{parts.scheme}://{parts.netloc}",
            "https://claude.ai",
            "https://claude.com",
        ],
    )
    server = build_v2_read_server(application, actor_provider=actor_provider)
    app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_REQUEST_BODY_BYTES,
        transport_security=security,
    )
    app.state.kis_max_response_bytes = MAX_RESPONSE_BYTES
    app.state.kis_public_activation = False
    return app
