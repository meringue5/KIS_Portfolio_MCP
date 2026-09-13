from __future__ import annotations

import json
from pathlib import Path

import pytest

from kis_portfolio.platform.artifact_cleanup import (
    canonical_sha256,
    execute_artifact_cleanup,
    validate_artifact_cleanup_approval,
)
from kis_portfolio.platform.production_guardrails import GuardrailValidationError


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "governance" / "project" / "evidence" / "wi049"


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text())


def _inventory_rows(spec: dict) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for field in ("retain_targets", "removal_targets"):
        for identity, digests in spec[field].items():
            repository, package = identity.split("/", 1)
            for digest in digests:
                rows.setdefault(repository, []).append(
                    {
                        "package": f"registry/project/{repository}/{package}",
                        "version": digest,
                        "tags": [],
                    }
                )
    return rows


class FakeCloud:
    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.rows = _inventory_rows(spec)
        self.deleted: list[list[str]] = []

    def load(self, command: list[str]):
        if command[:5] == ["gcloud", "artifacts", "docker", "images", "list"]:
            repository = command[5].rsplit("/", 1)[-1]
            return self.rows[repository]
        if command[:4] == ["gcloud", "run", "services", "list"]:
            digest = self.spec["protected_references"][0]["digest"]
            return [{"spec": {"template": {"spec": {"containers": [{"image": f"registry/project/kis-portfolio/kis-portfolio@{digest}"}]}}}, "status": {"traffic": []}}]
        if command[:4] == ["gcloud", "run", "jobs", "list"]:
            digest = self.spec["protected_references"][3]["digest"]
            return [{"spec": {"template": {"spec": {"template": {"spec": {"containers": [{"image": f"registry/project/cloud-run-source-deploy/kis-portfolio-domestic-order-history@{digest}"}]}}}}}}]
        raise AssertionError(command)

    def delete(self, command: list[str]) -> None:
        self.deleted.append(command)
        uri = command[5]
        path, digest = uri.rsplit("@", 1)
        repository = path.split("/")[2]
        package = path.rsplit("/", 1)[-1]
        self.rows[repository] = [
            row
            for row in self.rows[repository]
            if not (row["package"].endswith(f"/{package}") and row["version"] == digest)
        ]


def test_owner_approval_binds_the_exact_specification() -> None:
    spec = _load("artifact-cleanup-spec-2026-09-14.json")
    approval = _load("artifact-cleanup-approval-2026-09-14.json")
    assert approval["spec_canonical_sha256"] == canonical_sha256(spec)
    assert validate_artifact_cleanup_approval(approval, spec=spec)["approved_target_count"] == 59


def test_artifact_cleanup_dry_run_revalidates_without_delete() -> None:
    spec = _load("artifact-cleanup-spec-2026-09-14.json")
    cloud = FakeCloud(spec)
    result = execute_artifact_cleanup(
        spec,
        _load("artifact-cleanup-approval-2026-09-14.json"),
        apply=False,
        github_actions=False,
        github_ref="",
        load_json=cloud.load,
        delete=cloud.delete,
    )
    assert result.status == "dry_run_pass"
    assert result.approved_target_count == 59
    assert cloud.deleted == []


def test_artifact_cleanup_apply_is_master_github_actions_only() -> None:
    spec = _load("artifact-cleanup-spec-2026-09-14.json")
    with pytest.raises(GuardrailValidationError, match="GitHub Actions"):
        execute_artifact_cleanup(
            spec,
            _load("artifact-cleanup-approval-2026-09-14.json"),
            apply=True,
            github_actions=False,
            github_ref="refs/heads/master",
        )


def test_artifact_cleanup_fails_if_candidate_gains_tag() -> None:
    spec = _load("artifact-cleanup-spec-2026-09-14.json")
    cloud = FakeCloud(spec)
    first = next(iter(spec["removal_targets"].values()))[0]
    for rows in cloud.rows.values():
        for row in rows:
            if row["version"] == first:
                row["tags"] = ["new-reference"]
    with pytest.raises(GuardrailValidationError, match="gained tags"):
        execute_artifact_cleanup(
            spec,
            _load("artifact-cleanup-approval-2026-09-14.json"),
            apply=False,
            github_actions=False,
            github_ref="",
            load_json=cloud.load,
        )


def test_artifact_cleanup_deletes_only_exact_untagged_digests() -> None:
    spec = _load("artifact-cleanup-spec-2026-09-14.json")
    cloud = FakeCloud(spec)
    result = execute_artifact_cleanup(
        spec,
        _load("artifact-cleanup-approval-2026-09-14.json"),
        apply=True,
        github_actions=True,
        github_ref="refs/heads/master",
        load_json=cloud.load,
        delete=cloud.delete,
    )
    assert result.status == "applied"
    assert len(result.deleted_targets) == len(cloud.deleted) == 59
    assert all(command[:5] == ["gcloud", "artifacts", "docker", "images", "delete"] for command in cloud.deleted)
    assert all("--delete-tags" not in command and "*" not in command[5] for command in cloud.deleted)
