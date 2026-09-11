from __future__ import annotations

from datetime import date

import pytest

from kis_portfolio.adapters.outbound.remote_v2_pipeline import CloudRunManagedPipelineCommands
from kis_portfolio.services.remote_commands import ManagedRunCommand


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


def test_managed_pipeline_adapter_posts_only_fixed_job_and_normalized_args():
    session = _Session()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", session=session
    )

    adapter.enqueue(_command())

    url, kwargs = session.calls[0]
    assert url.endswith("/jobs/kis-portfolio-owned-core-v2-1000:run")
    assert kwargs["json"] == {
        "overrides": {
            "containerOverrides": [{
                "args": [
                    "collect-owned-portfolio-v2", "--date", "20260911",
                    "--slot", "kr-1000", "--partition-key", "all-accounts",
                    "--requested-run-id", "remote-run-1",
                ]
            }]
        }
    }
    assert kwargs["timeout"] == 30.0


def test_managed_pipeline_adapter_rejects_job_slot_mismatch_before_network():
    session = _Session()
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", session=session
    )

    with pytest.raises(ValueError, match="not allowlisted"):
        adapter.enqueue(_command(job_name="kis-portfolio-owned-core-v2-1430"))

    assert session.calls == []


def test_managed_pipeline_adapter_fails_closed_on_cloud_run_error():
    adapter = CloudRunManagedPipelineCommands(
        project="project-1", region="asia-northeast3", session=_Session(503)
    )

    with pytest.raises(RuntimeError, match="managed_job_enqueue_failed:503"):
        adapter.enqueue(_command())
