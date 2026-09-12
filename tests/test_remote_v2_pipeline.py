from __future__ import annotations

from datetime import date

import pytest

from kis_portfolio.adapters.outbound.remote_v2_pipeline import (
    CloudRunManagedPipelineCommands,
    WarehouseManagedRunLookup,
)
from kis_portfolio.services.remote_commands import ManagedRunCommand


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Session:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.status_code)


class _RunLookup:
    def __init__(self, status: str | None = None) -> None:
        self.status = status
        self.keys = []

    def status_for(self, logical_key: str) -> str | None:
        self.keys.append(logical_key)
        return self.status


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self.row


def _command(**overrides) -> ManagedRunCommand:
    values = {
        "run_id": "remote-run-1",
        "pipeline_id": "pipeline.owned-portfolio-core-v2",
        "pipeline_version": "1.0.0",
        "job_name": "kis-portfolio-owned-core-v2-1000",
        "logical_date": date(2026, 9, 11),
        "slot": "kr-1000",
        "actor_id": "owner",
        "client_id": "client",
        "request_id": "request-1",
        "idempotency_key": "owner-request-1",
    }
    values.update(overrides)
    return ManagedRunCommand(**values)


def test_warehouse_run_lookup_uses_only_the_logical_idempotency_key():
    connection = _Connection(("succeeded",))

    assert WarehouseManagedRunLookup(connection).status_for("logical-key") == "succeeded"
    assert connection.calls[0][1] == ["logical-key"]


@pytest.mark.anyio
async def test_managed_pipeline_adapter_invokes_only_current_date_fixed_job_without_overrides():
    session = _Session()
    lookup = _RunLookup()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", run_lookup=lookup, session=session,
        today=lambda: date(2026, 9, 11),
    )

    assert await adapter.enqueue(_command()) == "accepted"

    url, kwargs = session.calls[0]
    assert url.endswith("/jobs/kis-portfolio-owned-core-v2-1000:run")
    assert kwargs["json"] == {}
    assert kwargs["timeout"] == 30.0
    assert lookup.keys == ["remote-run-1"]


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["running", "succeeded"])
async def test_managed_pipeline_adapter_reuses_existing_logical_run_without_dispatch(status):
    session = _Session()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", run_lookup=_RunLookup(status),
        session=session, today=lambda: date(2026, 9, 12),
    )

    assert await adapter.enqueue(_command()) == "reused"
    assert session.calls == []


@pytest.mark.anyio
async def test_managed_pipeline_adapter_rejects_missing_historical_run_without_dispatch():
    session = _Session()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", run_lookup=_RunLookup(),
        session=session, today=lambda: date(2026, 9, 12),
    )

    with pytest.raises(RuntimeError, match="managed_historical_run_not_reusable"):
        await adapter.enqueue(_command())

    assert session.calls == []


@pytest.mark.anyio
async def test_managed_pipeline_adapter_rejects_job_slot_mismatch_before_network():
    session = _Session()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", run_lookup=_RunLookup(), session=session,
        today=lambda: date(2026, 9, 11),
    )

    with pytest.raises(ValueError, match="not allowlisted"):
        await adapter.enqueue(_command(job_name="kis-portfolio-owned-core-v2-1430"))

    assert session.calls == []


@pytest.mark.anyio
async def test_managed_pipeline_adapter_fails_closed_on_cloud_run_error():
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", run_lookup=_RunLookup(),
        session=_Session(503), today=lambda: date(2026, 9, 11),
    )

    with pytest.raises(RuntimeError, match="managed_job_enqueue_failed:503"):
        await adapter.enqueue(_command())
