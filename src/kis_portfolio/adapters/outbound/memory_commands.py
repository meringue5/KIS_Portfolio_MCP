"""Atomic local command ports for WI-043 fixtures and inactive verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock
from typing import Any

from kis_portfolio.services.remote_commands import (
    CommandActor,
    IdempotencyConflictError,
    ManagedRunCommand,
    RevisionConflictError,
    RevisionWrite,
    ReviseTradeThreadRequest,
    UpsertTradeJournalRequest,
)


@dataclass(frozen=True, slots=True)
class RecordedRevision:
    entity_id: str
    revision: int
    document: dict[str, Any]
    actor_id: str
    client_id: str
    request_id: str
    idempotency_key: str


class InMemoryManagedPipelineCommands:
    """Capture only already-normalized fixed Job requests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.commands: list[ManagedRunCommand] = []
        self._by_key: dict[str, ManagedRunCommand] = {}

    def enqueue(self, command: ManagedRunCommand) -> None:
        with self._lock:
            prior = self._by_key.get(command.idempotency_key)
            if prior is not None:
                if (
                    prior.run_id,
                    prior.pipeline_id,
                    prior.pipeline_version,
                    prior.job_name,
                    prior.logical_date,
                    prior.slot,
                    prior.actor_id,
                    prior.client_id,
                ) != (
                    command.run_id,
                    command.pipeline_id,
                    command.pipeline_version,
                    command.job_name,
                    command.logical_date,
                    command.slot,
                    command.actor_id,
                    command.client_id,
                ):
                    raise IdempotencyConflictError("managed run key was reused")
                return
            self._by_key[command.idempotency_key] = command
            self.commands.append(command)


class InMemoryJournalRevisionCommands:
    """Append-only owner revision fixture with optimistic concurrency."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.journals: dict[str, list[RecordedRevision]] = {}
        self.threads: dict[str, list[RecordedRevision]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, RevisionWrite]] = {}

    def append_journal(
        self,
        request: UpsertTradeJournalRequest,
        actor: CommandActor,
    ) -> RevisionWrite:
        document = request.model_dump(mode="json", exclude={"idempotency_key"})
        return self._append(
            kind="journal",
            identity=request.journal_id,
            expected=request.expected_revision,
            idempotency_key=request.idempotency_key,
            document=document,
            actor=actor,
            target=self.journals,
        )

    def append_thread_revision(
        self,
        request: ReviseTradeThreadRequest,
        actor: CommandActor,
    ) -> RevisionWrite:
        document = request.model_dump(mode="json", exclude={"idempotency_key"})
        return self._append(
            kind="thread",
            identity=request.thread_id,
            expected=request.expected_revision,
            idempotency_key=request.idempotency_key,
            document=document,
            actor=actor,
            target=self.threads,
        )

    def _append(
        self,
        *,
        kind: str,
        identity: str,
        expected: int,
        idempotency_key: str,
        document: dict[str, Any],
        actor: CommandActor,
        target: dict[str, list[RecordedRevision]],
    ) -> RevisionWrite:
        fingerprint = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        key = (kind, idempotency_key)
        with self._lock:
            prior = self._idempotency.get(key)
            if prior is not None:
                if prior[0] != fingerprint:
                    raise IdempotencyConflictError("revision key was reused")
                old = prior[1]
                return RevisionWrite(old.entity_id, old.revision, False)
            revisions = target.setdefault(identity, [])
            if len(revisions) != expected:
                raise RevisionConflictError(
                    f"revision changed: expected={expected} actual={len(revisions)}"
                )
            revision = expected + 1
            revisions.append(RecordedRevision(
                entity_id=identity,
                revision=revision,
                document=document,
                actor_id=actor.actor_id,
                client_id=actor.client_id,
                request_id=actor.request_id,
                idempotency_key=idempotency_key,
            ))
            result = RevisionWrite(identity, revision, True)
            self._idempotency[key] = (fingerprint, result)
            return result
