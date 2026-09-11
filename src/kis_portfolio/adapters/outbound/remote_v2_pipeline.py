"""Production fixed-Job command adapter for Remote MCP V2."""

from __future__ import annotations

import asyncio
from typing import Any

from kis_portfolio.services.remote_commands import MANAGED_JOB_BY_SLOT, ManagedRunCommand


class CloudRunManagedPipelineCommands:
    """Start one allowlisted Cloud Run Job with normalized CLI overrides."""

    def __init__(
        self,
        *,
        project: str,
        region: str,
        session: Any | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not project or not region:
            raise ValueError("project and region are required")
        self.project = project
        self.region = region
        self._session = session
        self.timeout_seconds = timeout_seconds

    def _authorized_session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
        return self._session

    async def enqueue(self, command: ManagedRunCommand) -> None:
        expected_job = MANAGED_JOB_BY_SLOT.get(command.slot)
        if expected_job is None or command.job_name != expected_job:
            raise ValueError("managed job is not allowlisted for the requested slot")
        endpoint = (
            f"https://run.googleapis.com/v2/projects/{self.project}/locations/"
            f"{self.region}/jobs/{command.job_name}:run"
        )
        args = [
            "collect-owned-portfolio-v2",
            "--date",
            command.logical_date.strftime("%Y%m%d"),
            "--slot",
            command.slot,
            "--partition-key",
            "all-accounts",
            "--requested-run-id",
            command.run_id,
        ]
        response = await asyncio.to_thread(
            self._authorized_session().post,
            endpoint,
            json={"overrides": {"containerOverrides": [{"args": args}]}},
            timeout=self.timeout_seconds,
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"managed_job_enqueue_failed:{response.status_code}")
