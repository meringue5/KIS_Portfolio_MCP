"""Typed application boundary for the inactive Remote MCP V2 read surface.

The public adapter owns protocol DTOs while this service owns authorization,
query delegation, response safety and the bounded versioned envelope.  Runtime
wiring is intentionally absent until the MS-003 production gate opens.
"""

from __future__ import annotations

import inspect
import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


READ_SCOPE = "mcp:read"
CONSUMER_SCOPE = "mcp-read"
MAX_RESPONSE_BYTES = 262_144
V2_READ_TOOL_NAMES = (
    "get-portfolio-overview",
    "get-position-analysis",
    "get-performance-history",
    "get-market-snapshot",
    "get-market-history",
    "get-trade-ledger",
    "get-trade-thread",
    "get-dividend-summary",
    "get-fundamental-outlook",
    "get-exposure-analysis",
    "get-signal-status",
    "get-data-catalog",
    "get-data-quality",
    "get-pipeline-run",
    "get-journal-review-queue",
)


class RemoteReadError(ValueError):
    """Stable fail-closed error safe to expose at the adapter boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _DateRangeRequest(_Request):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class PortfolioOverviewRequest(_Request):
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    as_of: datetime | None = None
    freshness_policy: Literal["stored", "cached", "bounded-live"] = "stored"
    include_holdings: bool = True


class PositionAnalysisRequest(_Request):
    instrument_id: str | None = Field(default=None, min_length=1, max_length=64)
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    as_of: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)


class PerformanceHistoryRequest(_DateRangeRequest):
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    grain: Literal["daily", "weekly", "monthly"] = "daily"
    limit: int = Field(default=250, ge=1, le=1_000)


class MarketSnapshotRequest(_Request):
    instrument_id: str = Field(min_length=1, max_length=64)
    market: Literal["KR", "US", "FX"]
    freshness_policy: Literal["stored", "cached", "bounded-live"] = "cached"


class MarketHistoryRequest(_DateRangeRequest):
    instrument_id: str = Field(min_length=1, max_length=64)
    market: Literal["KR", "US", "FX"]
    adjusted: bool = True
    limit: int = Field(default=250, ge=1, le=1_000)


class TradeLedgerRequest(_DateRangeRequest):
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    instrument_id: str | None = Field(default=None, min_length=1, max_length=64)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=100, ge=1, le=200)


class TradeThreadRequest(_Request):
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    instrument_id: str | None = Field(default=None, min_length=1, max_length=64)
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    as_of: datetime | None = None
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=50, ge=1, le=100)


class DividendSummaryRequest(_DateRangeRequest):
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    instrument_id: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class FundamentalOutlookRequest(_Request):
    instrument_id: str = Field(min_length=1, max_length=64)
    as_of: datetime | None = None
    scenario: Literal["bear", "base", "bull", "all"] = "all"


class ExposureAnalysisRequest(_Request):
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    as_of: datetime | None = None
    include_macro: bool = True


class SignalStatusRequest(_Request):
    signal_id: str | None = Field(default=None, min_length=1, max_length=128)
    instrument_id: str | None = Field(default=None, min_length=1, max_length=64)
    as_of: datetime | None = None
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=50, ge=1, le=100)


class DataCatalogRequest(_Request):
    kind: Literal["source", "dataset", "metric", "pipeline", "macro_series", "object"]
    item_id: str | None = Field(default=None, min_length=1, max_length=160)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=25, ge=1, le=50)


class DataQualityRequest(_Request):
    dataset_id: str = Field(min_length=1, max_length=160)
    run_id: str | None = Field(default=None, min_length=1, max_length=160)
    as_of: datetime | None = None
    lookback_days: int = Field(default=7, ge=1, le=31)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=50, ge=1, le=200)


class PipelineRunRequest(_Request):
    run_id: str | None = Field(default=None, min_length=1, max_length=160)
    pipeline_id: str | None = Field(default=None, min_length=1, max_length=160)
    as_of: datetime | None = None
    lookback_days: int = Field(default=7, ge=1, le=31)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_query_mode(self):
        if (self.run_id is None) == (self.pipeline_id is None):
            raise ValueError("exactly one of run_id or pipeline_id is required")
        return self


class JournalReviewQueueRequest(_Request):
    status: Literal["open", "answered", "all"] = "open"
    account_alias: str | None = Field(default=None, min_length=1, max_length=64)
    cursor: str | None = Field(default=None, max_length=2_048)
    limit: int = Field(default=25, ge=1, le=100)


REQUEST_MODELS: Mapping[str, type[_Request]] = {
    "get-portfolio-overview": PortfolioOverviewRequest,
    "get-position-analysis": PositionAnalysisRequest,
    "get-performance-history": PerformanceHistoryRequest,
    "get-market-snapshot": MarketSnapshotRequest,
    "get-market-history": MarketHistoryRequest,
    "get-trade-ledger": TradeLedgerRequest,
    "get-trade-thread": TradeThreadRequest,
    "get-dividend-summary": DividendSummaryRequest,
    "get-fundamental-outlook": FundamentalOutlookRequest,
    "get-exposure-analysis": ExposureAnalysisRequest,
    "get-signal-status": SignalStatusRequest,
    "get-data-catalog": DataCatalogRequest,
    "get-data-quality": DataQualityRequest,
    "get-pipeline-run": PipelineRunRequest,
    "get-journal-review-queue": JournalReviewQueueRequest,
}


class ReadResponseEnvelope(_Request):
    schema_version: str = Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")
    as_of: datetime
    source: dict[str, Any]
    freshness: dict[str, Any]
    quality: dict[str, Any]
    missing_coverage: list[dict[str, Any]]
    lineage_ref: str | None
    request_id: str = Field(min_length=1, max_length=128)
    data: dict[str, Any]


@dataclass(frozen=True)
class ReadActor:
    actor_id: str
    client_id: str
    scopes: frozenset[str]
    resource: str | None
    request_id: str

    def authorize(self, expected_resource: str | None) -> None:
        if READ_SCOPE not in self.scopes:
            raise RemoteReadError("insufficient_scope")
        if not self.actor_id or not self.client_id or not self.request_id:
            raise RemoteReadError("invalid_actor")
        if expected_resource and self.resource != expected_resource:
            raise RemoteReadError("invalid_resource")


class ReadQueryPort(Protocol):
    def capabilities(self) -> frozenset[str]: ...

    async def query(
        self,
        tool_name: str,
        request: _Request,
        actor: ReadActor,
    ) -> Mapping[str, Any]: ...


QueryHandler = Callable[[_Request, ReadActor], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]


class MappingReadQueryPort:
    """Explicit query-handler map used by application composition and fixtures."""

    def __init__(self, handlers: Mapping[str, QueryHandler]) -> None:
        names = frozenset(handlers)
        expected = frozenset(V2_READ_TOOL_NAMES)
        if names != expected:
            raise RemoteReadError("incomplete_query_port")
        self._handlers = dict(handlers)

    def capabilities(self) -> frozenset[str]:
        return frozenset(self._handlers)

    async def query(self, tool_name: str, request: _Request, actor: ReadActor) -> Mapping[str, Any]:
        result = self._handlers[tool_name](request, actor)
        if inspect.isawaitable(result):
            result = await result
        return result


class RemoteReadApplication:
    """Authorize, validate and dispatch the exact approved V2 read catalog."""

    def __init__(
        self,
        port: ReadQueryPort,
        *,
        expected_resource: str | None,
        deadline_seconds: float = 300.0,
    ) -> None:
        if port.capabilities() != frozenset(V2_READ_TOOL_NAMES):
            raise RemoteReadError("incomplete_query_port")
        if deadline_seconds <= 0 or deadline_seconds > 300:
            raise RemoteReadError("invalid_deadline")
        self.port = port
        self.expected_resource = expected_resource.rstrip("/") if expected_resource else None
        self.deadline_seconds = deadline_seconds

    async def execute(
        self,
        tool_name: str,
        request: _Request | Mapping[str, Any],
        actor: ReadActor,
    ) -> dict[str, Any]:
        actor.authorize(self.expected_resource)
        model_type = REQUEST_MODELS.get(tool_name)
        if model_type is None:
            raise RemoteReadError("unknown_read_tool")
        validated = request if isinstance(request, model_type) else model_type.model_validate(request)
        try:
            queried = await asyncio.wait_for(
                self.port.query(tool_name, validated, actor),
                timeout=self.deadline_seconds,
            )
        except TimeoutError as exc:
            raise RemoteReadError("query_deadline_exceeded") from exc
        result = dict(queried)
        result["request_id"] = actor.request_id
        envelope = ReadResponseEnvelope.model_validate(result)
        payload = envelope.model_dump(mode="json")
        _reject_sensitive_fields(payload)
        if len(_canonical_json(payload).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise RemoteReadError("response_too_large")
        return payload


_FORBIDDEN_RESPONSE_KEYS = {
    "raw",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "app_key",
    "app_secret",
    "cano",
    "account_number",
}


def _reject_sensitive_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_RESPONSE_KEYS:
                raise RemoteReadError("unsafe_response_field")
            _reject_sensitive_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive_fields(child)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
