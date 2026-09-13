from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = (
    ROOT
    / "governance"
    / "project"
    / "evidence"
    / "wi049"
    / "artifact-cleanup-spec-2026-09-14.json"
)
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def _targets(groups: dict[str, list[str]]) -> set[tuple[str, str]]:
    return {
        (package, digest)
        for package, digests in groups.items()
        for digest in digests
    }


def test_artifact_cleanup_spec_is_review_only_and_exact() -> None:
    spec = _spec()
    assert spec["schema_version"] == "kis-portfolio.artifact-cleanup-spec/v1"
    assert spec["mode"] == "dry_run"
    assert spec["apply_allowed"] is False
    assert spec["owner_approved"] is False
    assert spec["excluded_mutations"] == [
        "cloud_run_jobs",
        "cloud_run_services",
        "schedulers",
        "data",
        "backups",
        "buckets",
        "firestore",
        "iam",
        "secrets",
        "tags",
    ]

    retained = _targets(spec["retain_targets"])
    removable = _targets(spec["removal_targets"])
    assert len(retained) == spec["inventory"]["retain_versions"] == 49
    assert len(removable) == spec["inventory"]["removal_candidate_versions"] == 59
    assert len(retained | removable) == spec["inventory"]["versions"] == 108
    assert retained.isdisjoint(removable)
    assert all(DIGEST_RE.fullmatch(digest) for _, digest in retained | removable)
    assert all("*" not in package for package, _ in removable)


def test_artifact_cleanup_spec_protects_every_live_reference() -> None:
    spec = _spec()
    retained = _targets(spec["retain_targets"])
    removable = _targets(spec["removal_targets"])
    for reference in spec["protected_references"]:
        key = (f"{reference['repository']}/{reference['package']}", reference["digest"])
        assert key in retained
        assert key not in removable


def test_artifact_cleanup_spec_keeps_canonical_repository_whole() -> None:
    spec = _spec()
    assert len(spec["retain_targets"]["kis-portfolio/kis-portfolio"]) == 33
    assert "kis-portfolio/kis-portfolio" not in spec["removal_targets"]
    assert sum(len(items) for items in spec["removal_targets"].values()) == 17 + 10 + 4 + 25 + 3
