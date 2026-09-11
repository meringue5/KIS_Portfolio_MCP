"""Production append-only owner revision adapter for Remote MCP V2."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import duckdb

from kis_portfolio.services.remote_commands import (
    CommandActor,
    RevisionConflictError,
    RevisionWrite,
    ReviseTradeThreadRequest,
    UpsertTradeJournalRequest,
)


class WarehouseJournalRevisionCommands:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def append_journal(
        self,
        request: UpsertTradeJournalRequest,
        actor: CommandActor,
    ) -> RevisionWrite:
        row = self.connection.execute(
            "SELECT coalesce(max(revision), 0) FROM silver.trade_journal_revisions WHERE journal_id=?",
            [request.journal_id],
        ).fetchone()
        current = int(row[0])
        if current != request.expected_revision:
            raise RevisionConflictError("journal revision changed")
        revision = current + 1
        self.connection.execute(
            """
            INSERT INTO silver.trade_journal_revisions(
                journal_id, revision, thread_id, trade_event_id, body,
                authored_by, authored_at, expected_prior_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [request.journal_id, revision, request.thread_id, request.trade_event_id,
             request.body, actor.actor_id, request.authored_at, request.expected_revision],
        )
        return RevisionWrite(request.journal_id, revision, True)

    def append_thread_revision(
        self,
        request: ReviseTradeThreadRequest,
        actor: CommandActor,
    ) -> RevisionWrite:
        thread = self.connection.execute(
            "SELECT revision FROM silver.trade_threads WHERE thread_id=?", [request.thread_id]
        ).fetchone()
        if thread is None:
            raise RevisionConflictError("thread does not exist")
        ledger = self.connection.execute(
            "SELECT coalesce(max(revision), 0) FROM silver.trade_thread_command_revisions WHERE thread_id=?",
            [request.thread_id],
        ).fetchone()
        current = max(int(thread[0]), int(ledger[0]))
        if current != request.expected_revision:
            raise RevisionConflictError("thread revision changed")
        revision = current + 1
        change = request.change.model_dump(mode="json")
        key_hash = hashlib.sha256(request.idempotency_key.encode()).hexdigest()
        revision_id = hashlib.sha256(
            f"thread-command|{request.thread_id}|{revision}".encode()
        ).hexdigest()
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """
                INSERT INTO silver.trade_thread_command_revisions(
                    command_revision_id, thread_id, revision, change_kind, change_document,
                    authored_by, client_id, request_id, idempotency_key_hash, authored_at,
                    expected_prior_revision, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [revision_id, request.thread_id, revision, request.change.kind,
                 json.dumps(change, ensure_ascii=False, sort_keys=True), actor.actor_id,
                 actor.client_id, actor.request_id, key_hash, request.authored_at,
                 request.expected_revision, datetime.now(UTC)],
            )
            if request.change.kind == "thread":
                self.connection.execute(
                    """UPDATE silver.trade_threads
                       SET title=coalesce(?, title), status=coalesce(?, status),
                           closed_at=CASE WHEN ?='closed' THEN ? WHEN ?='open' THEN NULL ELSE closed_at END,
                           revision=? WHERE thread_id=? AND revision=?""",
                    [request.change.title, request.change.status, request.change.status,
                     request.authored_at, request.change.status, revision, request.thread_id, current],
                )
            elif request.change.kind == "lot":
                lot = self.connection.execute(
                    "SELECT account_id FROM silver.purchase_lot_identities WHERE lot_id=?",
                    [request.change.lot_id],
                ).fetchone()
                owner = self.connection.execute(
                    "SELECT account_id FROM silver.trade_threads WHERE thread_id=?",
                    [request.thread_id],
                ).fetchone()
                if lot is None or owner is None or lot[0] != owner[0]:
                    raise RevisionConflictError("lot is not owned by the thread account")
                self.connection.execute(
                    """INSERT INTO silver.trade_thread_lots(
                           thread_id, lot_id, allocation_revision, linked_at, linkage_quality
                       ) VALUES (?, ?, ?, ?, 'explicit')""",
                    [request.thread_id, request.change.lot_id, revision, request.authored_at],
                )
                self.connection.execute(
                    "UPDATE silver.trade_threads SET revision=? WHERE thread_id=? AND revision=?",
                    [revision, request.thread_id, current],
                )
            else:
                # The typed intent is the authoritative append-only fact. Allocation
                # quantities remain unchanged until a separately reconciled projection
                # can bind the named lots to the sell event without inference.
                self.connection.execute(
                    "UPDATE silver.trade_threads SET revision=? WHERE thread_id=? AND revision=?",
                    [revision, request.thread_id, current],
                )
            if self.connection.execute(
                "SELECT revision FROM silver.trade_threads WHERE thread_id=?", [request.thread_id]
            ).fetchone()[0] != revision:
                raise RevisionConflictError("thread revision update lost concurrency race")
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return RevisionWrite(request.thread_id, revision, True)
