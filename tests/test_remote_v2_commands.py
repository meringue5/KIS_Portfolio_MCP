import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from kis_portfolio.adapters.mcp import v2 as v2_adapter
from kis_portfolio.adapters.mcp.v2 import (
    COMMAND_TOOL_CONTRACTS,
    TOOL_CONTRACTS,
    build_v2_server,
)
from kis_portfolio.adapters.outbound.memory_commands import (
    InMemoryJournalRevisionCommands,
    InMemoryManagedPipelineCommands,
)
from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore
from kis_portfolio.services.remote_commands import (
    CommandActor,
    ManagedPipelineRequest,
    RemoteCommandApplication,
    RemoteCommandError,
    ReviseTradeThreadRequest,
    UpsertTradeJournalRequest,
    V2_COMMAND_TOOL_NAMES,
)
from kis_portfolio.services.remote_read_surface import (
    V2_READ_TOOL_NAMES,
    MappingReadQueryPort,
    ReadActor,
    RemoteReadApplication,
)


RESOURCE = "https://resource.example.com/mcp"
NOW = datetime(2026, 9, 11, 1, tzinfo=UTC)
COMMAND_ACTOR = CommandActor(
    actor_id="owner-subject",
    client_id="claude-client",
    scopes=frozenset({"mcp:collect", "mcp:journal.write"}),
    resource=RESOURCE,
    request_id="request-command-1",
)
READ_ACTOR = ReadActor(
    actor_id="owner-subject",
    client_id="claude-client",
    scopes=frozenset({"mcp:read"}),
    resource=RESOURCE,
    request_id="request-read-1",
)


def _read_application():
    def handler(_request, _actor):
        return {
            "schema_version": "1.0.0",
            "as_of": NOW,
            "source": {"kind": "fixture"},
            "freshness": {"status": "not_assessed"},
            "quality": {"status": "not_assessed"},
            "missing_coverage": [],
            "lineage_ref": None,
            "request_id": "replaced",
            "data": {},
        }

    return RemoteReadApplication(
        MappingReadQueryPort({name: handler for name in V2_READ_TOOL_NAMES}),
        expected_resource=RESOURCE,
    )


def _command_application():
    state = InMemoryStateStore()
    managed = InMemoryManagedPipelineCommands()
    revisions = InMemoryJournalRevisionCommands()
    application = RemoteCommandApplication(
        state=state,
        managed_pipeline=managed,
        revisions=revisions,
        expected_resource=RESOURCE,
    )
    return application, managed, revisions


def test_full_v2_catalog_is_exactly_fifteen_reads_and_three_commands():
    command, _managed, _revisions = _command_application()
    server = build_v2_server(
        _read_application(),
        command,
        read_actor_provider=lambda: READ_ACTOR,
        command_actor_provider=lambda: COMMAND_ACTOR,
    )
    tools = server._tool_manager.list_tools()
    names = tuple(tool.name for tool in tools)

    assert names == V2_READ_TOOL_NAMES + V2_COMMAND_TOOL_NAMES
    assert len(names) == 18
    assert tuple(item.name for item in TOOL_CONTRACTS) == V2_READ_TOOL_NAMES
    assert tuple(item.name for item in COMMAND_TOOL_CONTRACTS) == V2_COMMAND_TOOL_NAMES
    by_name = {tool.name: tool for tool in tools}
    assert by_name["run-managed-pipeline"].meta["kis/scope"] == "mcp:collect"
    assert by_name["upsert-trade-journal"].meta["kis/scope"] == "mcp:journal.write"
    assert by_name["revise-trade-thread"].meta["kis/scope"] == "mcp:journal.write"
    assert all(by_name[name].annotations.read_only_hint is False for name in V2_COMMAND_TOOL_NAMES)
    assert all(by_name[name].annotations.destructive_hint is False for name in V2_COMMAND_TOOL_NAMES)
    assert not any("order" in name for name in names)


@pytest.mark.parametrize(
    ("tool_name", "payload"),
    [
        (
            "run-managed-pipeline",
            {"logical_date": date(2026, 9, 11), "slot": "kr-1000", "idempotency_key": "collect-0001"},
        ),
        (
            "upsert-trade-journal",
            {
                "journal_id": "journal-1",
                "thread_id": "thread-1",
                "body": "Owner-authored fixture.",
                "authored_at": NOW,
                "expected_revision": 0,
                "idempotency_key": "journal-0001",
            },
        ),
    ],
)
def test_read_only_token_cannot_collect_or_write(tool_name, payload):
    application, _managed, _revisions = _command_application()
    actor = CommandActor(
        READ_ACTOR.actor_id,
        READ_ACTOR.client_id,
        READ_ACTOR.scopes,
        READ_ACTOR.resource,
        READ_ACTOR.request_id,
    )

    with pytest.raises(RemoteCommandError, match="insufficient_scope"):
        asyncio.run(application.execute(tool_name, payload, actor))


def test_command_scopes_are_not_interchangeable_and_resource_fails_closed():
    application, _managed, _revisions = _command_application()
    collect_only = CommandActor("owner", "client", frozenset({"mcp:collect"}), RESOURCE, "request")
    wrong_resource = CommandActor(
        "owner", "client", frozenset({"mcp:collect"}), "https://other.example/mcp", "request"
    )
    journal = {
        "journal_id": "journal-1",
        "thread_id": "thread-1",
        "body": "Owner-authored fixture.",
        "authored_at": NOW,
        "expected_revision": 0,
        "idempotency_key": "journal-0001",
    }
    collect = {
        "logical_date": date(2026, 9, 11),
        "slot": "kr-1000",
        "idempotency_key": "collect-0001",
    }

    with pytest.raises(RemoteCommandError, match="insufficient_scope"):
        asyncio.run(application.execute("upsert-trade-journal", journal, collect_only))
    with pytest.raises(RemoteCommandError, match="invalid_resource"):
        asyncio.run(application.execute("run-managed-pipeline", collect, wrong_resource))


def test_managed_pipeline_accepts_only_fixed_alias_and_slots_and_returns_run_id():
    application, managed, _revisions = _command_application()
    request = ManagedPipelineRequest(
        logical_date=date(2026, 9, 11),
        slot="kr-1430",
        idempotency_key="collect-0001",
    )

    first = asyncio.run(application.execute("run-managed-pipeline", request, COMMAND_ACTOR))
    replay_actor = CommandActor(
        COMMAND_ACTOR.actor_id,
        COMMAND_ACTOR.client_id,
        COMMAND_ACTOR.scopes,
        COMMAND_ACTOR.resource,
        "request-command-2",
    )
    second = asyncio.run(application.execute("run-managed-pipeline", request, replay_actor))

    assert first["status"] == "accepted"
    assert second["status"] == "reused"
    assert first["run_id"] == second["run_id"]
    assert second["request_id"] == "request-command-2"
    assert len(managed.commands) == 1
    command = managed.commands[0]
    assert command.pipeline_id == "pipeline.owned-portfolio-core-v2"
    assert command.pipeline_version == "1.0.0"
    assert command.job_name == "kis-portfolio-owned-core-v2-1430"
    assert not hasattr(command, "args")
    assert not hasattr(command, "environment")
    assert not hasattr(command, "timeout")

    with pytest.raises(ValidationError):
        ManagedPipelineRequest(
            pipeline="arbitrary-job",
            logical_date=date(2026, 9, 11),
            slot="kr-1430",
            idempotency_key="collect-0002",
        )
    with pytest.raises(ValidationError):
        ManagedPipelineRequest.model_validate({
            "logical_date": "2026-09-11",
            "slot": "kr-1430",
            "idempotency_key": "collect-0003",
            "command": "DROP TABLE anything",
        })


def test_same_idempotency_key_with_changed_request_fails_without_second_job():
    application, managed, _revisions = _command_application()
    base = {
        "logical_date": date(2026, 9, 11),
        "slot": "kr-1000",
        "idempotency_key": "collect-0001",
    }
    asyncio.run(application.execute("run-managed-pipeline", base, COMMAND_ACTOR))

    with pytest.raises(RemoteCommandError, match="idempotency_conflict"):
        asyncio.run(application.execute(
            "run-managed-pipeline", {**base, "slot": "kr-1600"}, COMMAND_ACTOR
        ))
    assert len(managed.commands) == 1


def test_concurrent_replay_is_rejected_while_the_first_command_holds_its_claim():
    class BlockingManagedPort:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def enqueue(self, _command):
            self.calls += 1
            self.entered.set()
            await self.release.wait()

    async def scenario():
        managed = BlockingManagedPort()
        application = RemoteCommandApplication(
            state=InMemoryStateStore(),
            managed_pipeline=managed,
            revisions=InMemoryJournalRevisionCommands(),
            expected_resource=RESOURCE,
        )
        request = {
            "logical_date": date(2026, 9, 11),
            "slot": "kr-1000",
            "idempotency_key": "collect-concurrent-0001",
        }
        first = asyncio.create_task(
            application.execute("run-managed-pipeline", request, COMMAND_ACTOR)
        )
        await managed.entered.wait()
        contender = CommandActor(
            COMMAND_ACTOR.actor_id,
            COMMAND_ACTOR.client_id,
            COMMAND_ACTOR.scopes,
            COMMAND_ACTOR.resource,
            "request-command-contender",
        )
        with pytest.raises(RemoteCommandError, match="command_in_progress"):
            await application.execute("run-managed-pipeline", request, contender)
        managed.release.set()
        await first
        return managed.calls

    assert asyncio.run(scenario()) == 1


def test_journal_is_append_only_owner_audited_and_stale_revision_fails():
    application, _managed, revisions = _command_application()
    first = {
        "journal_id": "journal-1",
        "thread_id": "thread-1",
        "body": "Initial owner thesis.",
        "authored_at": NOW,
        "expected_revision": 0,
        "idempotency_key": "journal-0001",
    }
    result = asyncio.run(application.execute("upsert-trade-journal", first, COMMAND_ACTOR))
    second = {**first, "body": "Revised owner thesis.", "expected_revision": 1, "idempotency_key": "journal-0002"}
    revised = asyncio.run(application.execute("upsert-trade-journal", second, COMMAND_ACTOR))

    assert (result["revision"], revised["revision"]) == (1, 2)
    assert [item.document["body"] for item in revisions.journals["journal-1"]] == [
        "Initial owner thesis.",
        "Revised owner thesis.",
    ]
    assert all(item.actor_id == "owner-subject" for item in revisions.journals["journal-1"])
    assert all("token" not in item.document for item in revisions.journals["journal-1"])

    stale = {**second, "body": "Stale write.", "idempotency_key": "journal-0003"}
    with pytest.raises(RemoteCommandError, match="stale_revision"):
        asyncio.run(application.execute("upsert-trade-journal", stale, COMMAND_ACTOR))
    assert len(revisions.journals["journal-1"]) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "thread", "title": "Long-term core", "status": "open"},
        {"kind": "lot", "lot_id": "lot-1", "linkage_quality": "explicit"},
        {
            "kind": "sell_allocation",
            "allocation_id": "allocation-1",
            "allocation_method": "explicit_lot",
            "lot_ids": ["lot-1"],
            "reason": "Owner confirmed the lot.",
        },
    ],
)
def test_thread_lot_and_sell_allocation_changes_are_explicit_typed_revisions(change):
    application, _managed, revisions = _command_application()
    prior = len(revisions.threads.get("thread-1", []))
    request = ReviseTradeThreadRequest(
        thread_id="thread-1",
        change=change,
        authored_at=NOW,
        expected_revision=prior,
        idempotency_key=f"thread-{change['kind']}-0001",
    )

    response = asyncio.run(application.execute("revise-trade-thread", request, COMMAND_ACTOR))

    assert response["revision"] == prior + 1
    assert revisions.threads["thread-1"][-1].document["change"]["kind"] == change["kind"]


def test_invalid_thread_change_and_naive_owner_timestamp_fail_validation():
    with pytest.raises(ValidationError):
        ReviseTradeThreadRequest(
            thread_id="thread-1",
            change={"kind": "thread"},
            authored_at=NOW,
            expected_revision=0,
            idempotency_key="thread-0001",
        )
    with pytest.raises(ValidationError):
        UpsertTradeJournalRequest(
            journal_id="journal-1",
            thread_id="thread-1",
            body="Naive timestamp.",
            authored_at=datetime(2026, 9, 11, 1),
            expected_revision=0,
            idempotency_key="journal-0001",
        )


def test_command_actor_projection_drops_raw_bearer(monkeypatch):
    class Token:
        token = "must-never-leave-auth-context"
        subject = "owner-subject"
        client_id = "claude-client"
        scopes = ["mcp:collect", "mcp:journal.write"]
        resource = f"{RESOURCE}/"

    monkeypatch.setattr(v2_adapter, "get_access_token", lambda: Token())

    actor = v2_adapter.command_actor_from_auth_context()

    assert actor.actor_id == "owner-subject"
    assert actor.resource == RESOURCE
    assert not hasattr(actor, "token")


def test_command_actor_projection_requires_an_owner_subject(monkeypatch):
    class Token:
        token = "must-never-leave-auth-context"
        subject = None
        client_id = "machine-client"
        scopes = ["mcp:journal.write"]
        resource = RESOURCE

    monkeypatch.setattr(v2_adapter, "get_access_token", lambda: Token())
    application, _managed, _revisions = _command_application()
    actor = v2_adapter.command_actor_from_auth_context()

    with pytest.raises(RemoteCommandError, match="invalid_actor"):
        asyncio.run(application.execute(
            "upsert-trade-journal",
            {
                "journal_id": "journal-1",
                "thread_id": "thread-1",
                "body": "Machine clients cannot author owner intent.",
                "authored_at": NOW,
                "expected_revision": 0,
                "idempotency_key": "journal-0001",
            },
            actor,
        ))


def test_v2_command_catalog_remains_inactive_in_production_composition():
    remote_source = Path("src/kis_portfolio/remote.py").read_text(encoding="utf-8")

    assert "build_v2_server" not in remote_source
    assert "RemoteCommandApplication" not in remote_source
