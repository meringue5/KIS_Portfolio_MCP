from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from kis_portfolio.platform.production_guardrails import (
    GuardrailValidationError,
    evaluate_cost_snapshot,
    plan_artifact_cleanup,
    validate_inventory,
    validate_release_manifest,
)


FIXTURES = Path(__file__).parent / "fixtures" / "wi035"
AS_OF = datetime(2026, 9, 9, 12, tzinfo=UTC)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_inventory_and_release_manifest_fixtures_are_valid():
    inventory = validate_inventory(_fixture("resource-inventory-v1.json"))
    release = validate_release_manifest(_fixture("release-manifest-v1.json"))

    assert inventory["complete"] is True
    assert len(inventory["artifact_versions"]) == 4
    assert {item["target"] for item in release["rollback_targets"]} == {
        "kis-portfolio-remote",
        "kis-portfolio-owned-core-v2-1000",
    }


def test_inventory_rejects_unresolved_active_digest_and_secret_shaped_extra_fields():
    inventory = _fixture("resource-inventory-v1.json")
    inventory["resources"][0]["image_digest"] = None
    inventory["resources"][0]["environment"] = {"TOKEN": "must-not-be-here"}

    with pytest.raises(GuardrailValidationError) as raised:
        validate_inventory(inventory)

    assert "image_digest must resolve" in str(raised.value)
    assert "unsupported fields: environment" in str(raised.value)


def test_incomplete_inventory_cannot_claim_complete_collection():
    inventory = _fixture("resource-inventory-v1.json")
    inventory["collection_errors"] = ["jobs page 2 unavailable"]

    with pytest.raises(GuardrailValidationError, match="complete inventory cannot"):
        validate_inventory(inventory)


@pytest.mark.parametrize(
    ("amount", "state", "first_action"),
    [
        (3749, "normal", "continue_within_approved_limits"),
        (3750, "early_50", "inspect_retry_image_storage_growth_and_attribution"),
        (6750, "early_90", "inspect_retry_image_storage_growth_and_attribution"),
        (7500, "early_100", "inspect_retry_image_storage_growth_and_attribution"),
        (35000, "guard", "stop_new_backfill_and_optional_high_frequency_sources"),
        (42500, "approval", "stop_new_backfill_and_optional_high_frequency_sources"),
        (50000, "ceiling", "stop_new_backfill_and_optional_high_frequency_sources"),
    ],
)
def test_cost_threshold_boundaries_are_deterministic(amount, state, first_action):
    snapshot = _fixture("cost-snapshot-v1.json")
    snapshot["actual_krw"] = amount
    snapshot["forecast_krw"] = amount

    decision = evaluate_cost_snapshot(snapshot, as_of=AS_OF)

    assert decision.state == state
    assert decision.actions[0] == first_action


def test_cost_uses_higher_of_actual_and_forecast():
    snapshot = _fixture("cost-snapshot-v1.json")
    snapshot["actual_krw"] = 5100
    snapshot["forecast_krw"] = 43000

    decision = evaluate_cost_snapshot(snapshot, as_of=AS_OF)

    assert decision.state == "approval"
    assert decision.evaluated_krw == 43000


def test_stale_or_incomplete_cost_evidence_is_unknown_and_fail_closed():
    stale = _fixture("cost-snapshot-v1.json")
    stale["observed_at"] = "2026-06-01T00:00:00Z"
    incomplete = _fixture("cost-snapshot-v1.json")
    incomplete["attribution_complete"] = False

    for snapshot in (stale, incomplete):
        decision = evaluate_cost_snapshot(snapshot, as_of=AS_OF)
        assert decision.state == "unknown"
        assert decision.actions[0] == "block_new_cost_increasing_work"


def test_open_period_requires_forecast():
    snapshot = _fixture("cost-snapshot-v1.json")
    snapshot["forecast_krw"] = None

    with pytest.raises(GuardrailValidationError, match="forecast_krw is required"):
        evaluate_cost_snapshot(snapshot, as_of=AS_OF)


def test_cleanup_plan_never_selects_active_rollback_semantic_or_recent_floor():
    plan = plan_artifact_cleanup(
        _fixture("resource-inventory-v1.json"),
        _fixture("release-manifest-v1.json"),
        as_of=AS_OF,
    )
    entries = {item["digest"]: item for item in plan["entries"]}

    assert plan["complete"] is True
    assert plan["mode"] == "dry_run"
    assert plan["apply_allowed"] is False
    assert entries["sha256:" + "a" * 64]["action"] == "protect"
    assert "active_manifest" in entries["sha256:" + "a" * 64]["reasons"]
    assert entries["sha256:" + "b" * 64]["action"] == "protect"
    assert "rollback_manifest" in entries["sha256:" + "b" * 64]["reasons"]
    assert entries["sha256:" + "c" * 64]["action"] == "protect"
    assert "recent_version_floor" in entries["sha256:" + "c" * 64]["reasons"]
    assert entries["sha256:" + "d" * 64]["action"] == "candidate"


def test_cleanup_blocks_active_digest_mismatch():
    inventory = _fixture("resource-inventory-v1.json")
    inventory["resources"][0]["image_digest"] = "sha256:" + "e" * 64
    inventory["artifact_versions"].append(
        {
            "repository": "kis-portfolio",
            "package": "runtime",
            "digest": "sha256:" + "e" * 64,
            "tags": [],
            "created_at": "2026-09-09T00:00:00Z",
        }
    )

    plan = plan_artifact_cleanup(
        inventory, _fixture("release-manifest-v1.json"), as_of=AS_OF
    )

    assert plan["complete"] is False
    assert "active digest mismatch: kis-portfolio-remote" in plan["blockers"]
    assert plan["apply_allowed"] is False


def test_cleanup_blocks_missing_rollback_digest_inventory_evidence():
    inventory = _fixture("resource-inventory-v1.json")
    inventory["artifact_versions"] = [
        item
        for item in inventory["artifact_versions"]
        if item["digest"] != "sha256:" + "b" * 64
    ]

    plan = plan_artifact_cleanup(
        inventory, _fixture("release-manifest-v1.json"), as_of=AS_OF
    )

    assert plan["complete"] is False
    assert any("rollback_target digest absent" in item for item in plan["blockers"])


def test_cleanup_blocks_stale_restore_evidence():
    release = _fixture("release-manifest-v1.json")
    release["restore_evidence"]["verified_at"] = "2026-07-01T00:00:00Z"

    plan = plan_artifact_cleanup(
        _fixture("resource-inventory-v1.json"), release, as_of=AS_OF
    )

    assert plan["complete"] is False
    assert "restore evidence is older than rollback retention window" in plan["blockers"]
    assert plan["apply_allowed"] is False


def test_release_manifest_requires_restore_evidence_and_target_rollback():
    release = deepcopy(_fixture("release-manifest-v1.json"))
    release["rollback_targets"] = release["rollback_targets"][:1]
    release["restore_evidence"]["result"] = "unknown"

    with pytest.raises(GuardrailValidationError) as raised:
        validate_release_manifest(release)

    assert "rollback_targets missing active targets" in str(raised.value)
    assert "restore_evidence.result must be pass" in str(raised.value)
