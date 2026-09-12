"""Production fixed-Job command adapter for Remote MCP V2."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from kis_portfolio.services.remote_commands import MANAGED_JOB_BY_SLOT, ManagedRunCommand


class ManagedRunLookup(Protocol):
    def status_for(self, logical_key: str) -> str | None: ...


class WarehouseManagedRunLookup:
    """Read the existing logical run without granting Remote a write path."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def status_for(self, logical_key: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM control.pipeline_runs WHERE idempotency_key=? LIMIT 1",
            [logical_key],
        ).fetchone()
        return str(row[0]) if row is not None else None


class CloudRunManagedPipelineCommands:
    """Start one allowlisted Cloud Run Job with normalized CLI overrides."""

    def __init__(
        self,
        *,
        project: str,
        region: str,
        run_lookup: ManagedRunLookup,
        session: Any | None = None,
        timeout_seconds: float = 30.0,
        today: Callable[[], date] | None = None,
    ) -> None:
        if not project or not region:
            raise ValueError("project and region are required")
        self.project = project
        self.region = region
        self.run_lookup = run_lookup
        self._session = session
        self.timeout_seconds = timeout_seconds
        self._today = today or (lambda: datetime.now(ZoneInfo("Asia/Seoul")).date())

    def _authorized_session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
        return self._session

    async def enqueue(self, command: ManagedRunCommand) -> Literal["accepted", "reused"]:
        expected_job = MANAGED_JOB_BY_SLOT.get(command.slot)
        if expected_job is None or command.job_name != expected_job:
            raise ValueError("managed job is not allowlisted for the requested slot")
        existing_status = self.run_lookup.status_for(command.run_id)
        if existing_status in {"running", "succeeded"}:
            return "reused"
        if command.logical_date != self._today():
            raise RuntimeError("managed_historical_run_not_reusable")
        endpoint = (
            f"https://run.googleapis.com/v2/projects/{self.project}/locations/"
            f"{self.region}/jobs/{command.job_name}:run"
        )
        response = await asyncio.to_thread(
            self._authorized_session().post,
            endpoint,
            json={},
            timeout=self.timeout_seconds,
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"managed_job_enqueue_failed:{response.status_code}")
        return "accepted"
