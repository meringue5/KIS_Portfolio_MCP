"""Governed application boundary for the inactive Remote MCP V2 commands.

The application accepts only the three approved commands.  Managed collection
is reduced to one fixed pipeline allowlist and owner writes use append-only,
optimistically-concurrent repository ports.  Production adapters are
intentionally not composed here.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Awaitable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kis_portfolio.ports.state import StateStorePort


COLLECT_SCOPE = "mcp:collect"
JOURNAL_WRITE_SCOPE = "mcp:journal.write"
V2_COMMAND_TOOL_NAMES = (
    "run-managed-pipeline",
    "upsert-trade-journal",
    "revise-trade-thread",
)
PIPELINE_ALIAS = "portfolio-refresh"
MANAGED_PIPELINE_ID = "pipeline.owned-portfolio-core-v2"
MANAGED_PIPELINE_VERSION = "1.0.0"
MANAGED_JOB_BY_SLOT = {
    "kr-1000": "kis-portfolio-owned-core-v2-1000",
    "kr-1430": "kis-portfolio-owned-core-v2-1430",
    "kr-1600": "kis-portfolio-owned-core-v2-1600",
}
IDEMPOTENCY_TTL = timedelta(days=7)


class RemoteCommandError(ValueError):
    """Stable fail-closed error safe to expose at the adapter boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RevisionConflictError(RuntimeError):
    """A repository revision changed after the caller read it."""


class IdempotencyConflictError(RuntimeError):
    """A repository received one key for two different commands."""


class _CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


IdempotencyKey = Annotated[
    str,
    Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
OpaqueId = Annotated[str, Field(min_length=1, max_length=160)]


class ManagedPipelineRequest(_CommandRequest):
    pipeline: Literal["portfolio-refresh"] = PIPELINE_ALIAS
    logical_date: date
    slot: Literal["kr-1000", "kr-1430", "kr-1600"]
    idempotency_key: IdempotencyKey


class UpsertTradeJournalRequest(_CommandRequest):
    journal_id: OpaqueId
    thread_id: OpaqueId | None = None
    trade_event_id: OpaqueId | None = None
    body: str = Field(min_length=1, max_length=20_000)
    authored_at: datetime
    expected_revision: int = Field(ge=0)
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def validate_subject_and_time(self):
        if self.thread_id is None and self.trade_event_id is None:
            raise ValueError("thread_id or trade_event_id is required")
        if self.authored_at.tzinfo is None:
            raise ValueError("authored_at must be timezone-aware")
        return self


class ThreadMetadataChange(_CommandRequest):
    kind: Literal["thread"]
    title: str | None = Field(default=None, min_length=1, max_length=240)
    status: Literal["open", "closed"] | None = None

    @model_validator(mode="after")
    def validate_change(self):
        if self.title is None and self.status is None:
            raise ValueError("thread change requires title or status")
        return self


class LotLinkChange(_CommandRequest):
    kind: Literal["lot"]
    lot_id: OpaqueId
    linkage_quality: Literal["explicit"] = "explicit"


class SellAllocationChange(_CommandRequest):
    kind: Literal["sell_allocation"]
    allocation_id: OpaqueId
    allocation_method: Literal["explicit_lot", "explicit_thread_fifo"]
    lot_ids: list[OpaqueId] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_lots(self):
        if len(self.lot_ids) != len(set(self.lot_ids)):
            raise ValueError("lot_ids must be unique")
        return self


ThreadChange = Annotated[
    ThreadMetadataChange | LotLinkChange | SellAllocationChange,
    Field(discriminator="kind"),
]


class ReviseTradeThreadRequest(_CommandRequest):
    thread_id: OpaqueId
    change: ThreadChange
    authored_at: datetime
    expected_revision: int = Field(ge=0)
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def validate_time(self):
        if self.authored_at.tzinfo is None:
            raise ValueError("authored_at must be timezone-aware")
        return self


class CommandResponse(_CommandRequest):
    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: str = Field(min_length=1, max_length=128)
    command_id: str = Field(min_length=1, max_length=128)
    status: Literal["accepted", "reused"]
    run_id: str | None = Field(default=None, max_length=160)
    entity_id: str | None = Field(default=None, max_length=160)
    revision: int | None = Field(default=None, ge=1)


@dataclass(frozen=True, slots=True)
class CommandActor:
    actor_id: str
    client_id: str
    scopes: frozenset[str]
    resource: str | None
    request_id: str

    def authorize(self, required_scope: str, expected_resource: str | None) -> None:
        if required_scope not in self.scopes:
            raise RemoteCommandError("insufficient_scope")
        if not self.actor_id or not self.client_id or not self.request_id:
            raise RemoteCommandError("invalid_actor")
        if expected_resource and self.resource != expected_resource:
            raise RemoteCommandError("invalid_resource")


@dataclass(frozen=True, slots=True)
class ManagedRunCommand:
    run_id: str
    pipeline_id: str
    pipeline_version: str
    job_name: str
    logical_date: date
    slot: str
    actor_id: str
    client_id: str
    request_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RevisionWrite:
    entity_id: str
    revision: int
    inserted: bool


class ManagedPipelineCommandPort(Protocol):
    def enqueue(self, command: ManagedRunCommand) -> None | Awaitable[None]: ...


class JournalRevisionCommandPort(Protocol):
    def append_journal(
        self,
        request: UpsertTradeJournalRequest,
        actor: CommandActor,
    ) -> RevisionWrite | Awaitable[RevisionWrite]: ...

    def append_thread_revision(
        self,
        request: ReviseTradeThreadRequest,
        actor: CommandActor,
    ) -> RevisionWrite | Awaitable[RevisionWrite]: ...


class RemoteCommandApplication:
    """Authorize and dispatch the exact approved V2 command catalog."""

    def __init__(
        self,
        *,
        state: StateStorePort,
        managed_pipeline: ManagedPipelineCommandPort,
        revisions: JournalRevisionCommandPort,
        expected_resource: str | None,
    ) -> None:
        self.state = state
        self.managed_pipeline = managed_pipeline
        self.revisions = revisions
        self.expected_resource = expected_resource.rstrip("/") if expected_resource else None

    async def execute(
        self,
        tool_name: str,
        request: _CommandRequest | Mapping[str, Any],
        actor: CommandActor,
    ) -> dict[str, Any]:
        if tool_name == "run-managed-pipeline":
            actor.authorize(COLLECT_SCOPE, self.expected_resource)
            model = ManagedPipelineRequest.model_validate(request)
            return await self._execute_once(tool_name, model, actor, self._run_pipeline)
        if tool_name == "upsert-trade-journal":
            actor.authorize(JOURNAL_WRITE_SCOPE, self.expected_resource)
            model = UpsertTradeJournalRequest.model_validate(request)
            return await self._execute_once(tool_name, model, actor, self._append_journal)
        if tool_name == "revise-trade-thread":
            actor.authorize(JOURNAL_WRITE_SCOPE, self.expected_resource)
            model = ReviseTradeThreadRequest.model_validate(request)
            return await self._execute_once(tool_name, model, actor, self._append_thread_revision)
        raise RemoteCommandError("unknown_command_tool")

    async def _execute_once(self, tool_name, request, actor, operation) -> dict[str, Any]:
        document = request.model_dump(mode="json")
        fingerprint = _digest(tool_name, document)
        state_key = _digest("remote-command", actor.actor_id, actor.client_id, tool_name, request.idempotency_key)
        existing = self.state.get("run_requests", state_key)
        if existing is not None:
            return self._replay(existing, fingerprint, actor.request_id)
        claim_resource = f"remote-command:{state_key}"
        claim = self.state.claim(claim_resource, actor.request_id, IDEMPOTENCY_TTL)
        if not claim.acquired:
            existing = self.state.get("run_requests", state_key)
            if existing is not None:
                return self._replay(existing, fingerprint, actor.request_id)
            raise RemoteCommandError("command_in_progress")
        try:
            response = await operation(request, actor, fingerprint)
            accepted = CommandResponse.model_validate(response).model_dump(mode="json")
            self.state.put(
                "run_requests",
                state_key,
                {"request_hash": fingerprint, "response": accepted},
                expires_at=datetime.now(UTC) + IDEMPOTENCY_TTL,
            )
            return accepted
        except (RevisionConflictError, IdempotencyConflictError) as exc:
            code = "stale_revision" if isinstance(exc, RevisionConflictError) else "idempotency_conflict"
            raise RemoteCommandError(code) from exc
        finally:
            self.state.release(claim_resource, actor.request_id, claim.fencing_token)

    @staticmethod
    def _replay(existing: Mapping[str, Any], fingerprint: str, request_id: str) -> dict[str, Any]:
        if existing.get("request_hash") != fingerprint:
            raise RemoteCommandError("idempotency_conflict")
        response = dict(existing["response"])
        response.update(status="reused", request_id=request_id)
        return CommandResponse.model_validate(response).model_dump(mode="json")

    async def _run_pipeline(self, request, actor, fingerprint) -> CommandResponse:
        run_id = _digest("managed-run-v1", actor.actor_id, request.idempotency_key, fingerprint)
        command = ManagedRunCommand(
            run_id=run_id,
            pipeline_id=MANAGED_PIPELINE_ID,
            pipeline_version=MANAGED_PIPELINE_VERSION,
            job_name=MANAGED_JOB_BY_SLOT[request.slot],
            logical_date=request.logical_date,
            slot=request.slot,
            actor_id=actor.actor_id,
            client_id=actor.client_id,
            request_id=actor.request_id,
            idempotency_key=request.idempotency_key,
        )
        await _maybe_await(self.managed_pipeline.enqueue(command))
        return CommandResponse(
            request_id=actor.request_id,
            command_id=_digest("command-v1", "collect", fingerprint),
            status="accepted",
            run_id=run_id,
        )

    async def _append_journal(self, request, actor, fingerprint) -> CommandResponse:
        write = await _maybe_await(self.revisions.append_journal(request, actor))
        return CommandResponse(
            request_id=actor.request_id,
            command_id=_digest("command-v1", "journal", fingerprint),
            status="accepted" if write.inserted else "reused",
            entity_id=write.entity_id,
            revision=write.revision,
        )

    async def _append_thread_revision(self, request, actor, fingerprint) -> CommandResponse:
        write = await _maybe_await(self.revisions.append_thread_revision(request, actor))
        return CommandResponse(
            request_id=actor.request_id,
            command_id=_digest("command-v1", "thread", fingerprint),
            status="accepted" if write.inserted else "reused",
            entity_id=write.entity_id,
            revision=write.revision,
        )


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


def _digest(*parts: object) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()
