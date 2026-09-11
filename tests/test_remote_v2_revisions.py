from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from kis_portfolio.adapters.outbound.remote_v2_revisions import WarehouseJournalRevisionCommands
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.remote_commands import (
    CommandActor,
    LotLinkChange,
    RevisionConflictError,
    ReviseTradeThreadRequest,
    SellAllocationChange,
    ThreadMetadataChange,
    UpsertTradeJournalRequest,
)


NOW = datetime(2026, 9, 11, 10, tzinfo=UTC)
ACTOR = CommandActor(
    "owner-subject", "client-1", frozenset({"mcp:journal.write"}),
    "https://portfolio.example.test", "request-1",
)


@pytest.fixture
def repository():
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute(
        """INSERT INTO silver.trade_threads(
               thread_id, account_id, instrument_id, opened_at, closed_at,
               title, status, revision, provenance
           ) VALUES ('thread-1','account-hash','KR:005930',?,NULL,'Initial','open',0,'{}')""",
        [NOW],
    )
    return connection, WarehouseJournalRevisionCommands(connection)


def test_journal_append_is_monotonic_and_rejects_stale_revision(repository):
    connection, adapter = repository
    request = UpsertTradeJournalRequest(
        journal_id="journal-1", thread_id="thread-1", body="owner note",
        authored_at=NOW, expected_revision=0, idempotency_key="journal-key-1",
    )

    written = adapter.append_journal(request, ACTOR)

    assert (written.entity_id, written.revision) == ("journal-1", 1)
    assert connection.execute(
        "SELECT authored_by, body FROM silver.trade_journal_revisions"
    ).fetchone() == ("owner-subject", "owner note")
    with pytest.raises(RevisionConflictError, match="journal revision changed"):
        adapter.append_journal(request, ACTOR)


def test_thread_metadata_appends_audit_revision_and_updates_projection(repository):
    connection, adapter = repository
    request = ReviseTradeThreadRequest(
        thread_id="thread-1", change=ThreadMetadataChange(kind="thread", title="Updated"),
        authored_at=NOW, expected_revision=0, idempotency_key="thread-key-1",
    )

    written = adapter.append_thread_revision(request, ACTOR)

    assert written.revision == 1
    assert connection.execute(
        "SELECT title, revision FROM silver.trade_threads WHERE thread_id='thread-1'"
    ).fetchone() == ("Updated", 1)
    assert connection.execute(
        "SELECT change_kind, authored_by, client_id, request_id FROM silver.trade_thread_command_revisions"
    ).fetchone() == ("thread", "owner-subject", "client-1", "request-1")


def test_explicit_lot_link_requires_same_account_and_is_append_only(repository):
    connection, adapter = repository
    connection.execute(
        """INSERT INTO silver.position_episodes VALUES (
               'episode-1','account-hash','KR:005930',?,'identity','run-1',?)""",
        [NOW, NOW],
    )
    connection.execute(
        """INSERT INTO silver.purchase_lot_identities VALUES (
               'lot-1','episode-1','account-hash','KR:005930','trade-1',?,
               'actual','lot-identity','run-1',?)""",
        [NOW, NOW],
    )
    request = ReviseTradeThreadRequest(
        thread_id="thread-1", change=LotLinkChange(kind="lot", lot_id="lot-1"),
        authored_at=NOW, expected_revision=0, idempotency_key="lot-link-key-1",
    )

    adapter.append_thread_revision(request, ACTOR)

    assert connection.execute(
        "SELECT lot_id, allocation_revision, linkage_quality FROM silver.trade_thread_lots"
    ).fetchone() == ("lot-1", 1, "explicit")


def test_sell_allocation_is_stored_as_typed_intent_without_inventing_quantities(repository):
    connection, adapter = repository
    request = ReviseTradeThreadRequest(
        thread_id="thread-1",
        change=SellAllocationChange(
            kind="sell_allocation", allocation_id="allocation-1",
            allocation_method="explicit_thread_fifo", lot_ids=["lot-1"], reason="owner intent",
        ),
        authored_at=NOW, expected_revision=0, idempotency_key="allocation-key-1",
    )

    adapter.append_thread_revision(request, ACTOR)

    change = connection.execute(
        "SELECT change_document FROM silver.trade_thread_command_revisions"
    ).fetchone()[0]
    assert '"allocation_id":"allocation-1"' in str(change).replace(" ", "")
    assert connection.execute("SELECT count(*) FROM silver.sell_allocation_sets").fetchone()[0] == 0
