from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from kis_portfolio.platform.production_guardrails import GuardrailValidationError
from kis_portfolio.platform.runtime_cleanup import (
    execute_runtime_cleanup,
    job_configuration_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


def _job(name: str, digest: str) -> dict:
    return {
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "taskCount": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "image": "region/pkg/image@" + digest,
                                    "command": ["kis-portfolio-batch"],
                                    "args": ["one-time"],
                                }
                            ],
                            "serviceAccountName": "pipeline@example.iam.gserviceaccount.com",
                            "timeoutSeconds": "1800",
                            "maxRetries": 0,
                        }
                    },
                }
            }
        },
    }


def _evidence() -> tuple[dict, dict, dict]:
    digest = "sha256:" + "a" * 64
    name = "kis-portfolio-one-time"
    job = _job(name, digest)
    manifest = {
        "schema_version": "kis-portfolio.runtime-cleanup-manifest/v1",
        "generated_at": "2026-09-14T00:00:00Z",
        "project_id": "project-1",
        "region": "asia-northeast3",
        "mode": "dry_run",
        "apply_allowed": False,
        "owner_approved": False,
        "destructive_controls": {
            "data_deletion_allowed": False,
            "backup_deletion_allowed": False,
            "iam_changes_allowed": False,
            "secret_changes_allowed": False,
            "scheduler_changes_allowed": False,
        },
        "protected_data": [
            {"dataset": "main.asset_overview_snapshots", "row_count": 1, "reason": "history"}
        ],
        "protected_resources": [
            {"kind": "cloud_run_job", "name": "kis-portfolio-v2", "reason": "active"}
        ],
        "candidates": [
            {
                "kind": "cloud_run_job",
                "name": name,
                "region": "asia-northeast3",
                "image_digest": digest,
                "configuration_sha256": job_configuration_sha256(job),
                "last_execution": name + "-run",
                "last_completed_at": "2026-09-13T00:00:00Z",
                "last_execution_status": "SUCCEEDED",
                "scheduler_refs": [],
                "deployment_ref": "github-run:1",
                "recovery_ref": "git:example",
            }
        ],
        "recovery_evidence": {
            "backup_index_uri": "gs://private/index",
            "backup_index_sha256": "b" * 64,
            "backup_verified_at": "2026-09-13T00:00:00Z",
            "backup_result": "pass",
            "source_git_sha": "c" * 40,
            "workflow_reference": "github-run:1",
        },
    }
    approval = {
        "schema_version": "kis-portfolio.runtime-cleanup-approval/v1",
        "approved_at": "2026-09-14",
        "approved_by": "owner",
        "manifest_reference": "manifest.json",
        "approved_targets": [name],
        "excluded_resource_families": [
            "artifact_images", "backups", "data", "iam", "schedulers", "secrets", "services"
        ],
    }
    return manifest, approval, job


def test_repository_approval_exactly_matches_frozen_candidates():
    manifest = json.loads(
        (ROOT / "governance/project/evidence/wi049/runtime-cleanup-readiness-2026-09-13.json")
        .read_text(encoding="utf-8")
    )
    approval = json.loads(
        (ROOT / "governance/project/evidence/wi049/runtime-cleanup-approval-2026-09-14.json")
        .read_text(encoding="utf-8")
    )

    assert set(approval["approved_targets"]) == {
        item["name"] for item in manifest["candidates"]
    }


def test_cleanup_dry_run_revalidates_without_deleting():
    manifest, approval, job = _evidence()
    deletes = []

    def load_json(command):
        if command[1:4] == ["scheduler", "jobs", "list"]:
            return []
        if command[1:3] == ["storage", "objects"]:
            return {"name": "recovery/index"}
        return job

    result = execute_runtime_cleanup(
        manifest,
        approval,
        apply=False,
        github_actions=False,
        github_ref="",
        load_json=load_json,
        delete=lambda command: deletes.append(command),
    )

    assert result.status == "dry_run_pass"
    assert deletes == []


def test_cleanup_apply_requires_master_actions_and_deletes_exact_name():
    manifest, approval, job = _evidence()
    deletes = []

    def load_json(command):
        if command[1:4] == ["scheduler", "jobs", "list"]:
            return [{"name": "kis-portfolio-schedule"}]
        if command[1:4] == ["run", "jobs", "list"]:
            return [{"metadata": {"name": "kis-portfolio-v2"}}]
        if command[1:3] == ["storage", "objects"]:
            return {"name": "recovery/index"}
        return job

    result = execute_runtime_cleanup(
        manifest,
        approval,
        apply=True,
        github_actions=True,
        github_ref="refs/heads/master",
        load_json=load_json,
        delete=lambda command: deletes.append(command),
    )

    assert result.status == "applied"
    assert deletes == [[
        "gcloud", "run", "jobs", "delete", "kis-portfolio-one-time", "--quiet",
        "--project", "project-1", "--region", "asia-northeast3",
    ]]


def test_cleanup_apply_is_blocked_outside_master_actions():
    manifest, approval, _job_payload = _evidence()

    with pytest.raises(GuardrailValidationError, match="GitHub Actions"):
        execute_runtime_cleanup(
            manifest,
            approval,
            apply=True,
            github_actions=False,
            github_ref="refs/heads/master",
        )


@pytest.mark.parametrize("failure", ["scheduler", "configuration", "approval"])
def test_cleanup_preflight_fails_closed(failure):
    manifest, approval, job = _evidence()
    if failure == "configuration":
        job = deepcopy(job)
        job["spec"]["template"]["spec"]["template"]["spec"]["maxRetries"] = 1
    if failure == "approval":
        approval["approved_targets"].append("not-in-manifest")

    def load_json(command):
        if command[1:4] == ["scheduler", "jobs", "list"]:
            if failure == "scheduler":
                return [{"httpTarget": {"uri": "https://run/jobs/kis-portfolio-one-time:run"}}]
            return []
        if command[1:3] == ["storage", "objects"]:
            return {"name": "recovery/index"}
        return job

    with pytest.raises(GuardrailValidationError):
        execute_runtime_cleanup(
            manifest,
            approval,
            apply=False,
            github_actions=False,
            github_ref="",
            load_json=load_json,
        )
