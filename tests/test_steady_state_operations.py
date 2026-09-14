from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest

from kis_portfolio.platform.production_guardrails import GuardrailValidationError
from kis_portfolio.platform.steady_state_operations import (
    assess_steady_state_review,
    verify_private_object_records,
)


ROOT = Path(__file__).resolve().parents[1]


def _evidence() -> dict:
    return json.loads((ROOT / "tests/fixtures/wi050/steady-state-review-v1.json").read_text())


def _cost() -> dict:
    return {
        "schema_version": "kis-portfolio.cost-snapshot/v1",
        "observed_at": "2026-09-11T09:54:11Z",
        "billing_period": "2026-09",
        "period_closed": False,
        "actual_krw": 434,
        "forecast_krw": 119,
        "attribution_complete": True,
        "source": "billing_console_manual",
    }


def _assess(evidence: dict | None = None):
    return assess_steady_state_review(
        evidence or _evidence(), _cost(), as_of=datetime.fromisoformat("2026-09-14T00:00:00+00:00")
    )


def test_baseline_review_passes_with_restricted_object_followup() -> None:
    result = _assess()
    assert result.status == "attention"
    assert result.blockers == ()
    assert result.rpo_minutes == 647
    assert "verify_private_restricted_object_recovery_separately" in result.actions
    assert result.as_dict()["production_change_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rpo_minutes", 1441, "restore RPO exceeded 24 hours"),
        ("rto_seconds", 14401, "restore RTO exceeded 4 hours"),
    ],
)
def test_recovery_slo_is_fail_closed(field: str, value: int, message: str) -> None:
    evidence = _evidence()
    evidence["recovery"][field] = value
    if field == "rpo_minutes":
        evidence["recovery"]["backup_created_at"] = "2026-09-12T23:59:00Z"
    assert message in _assess(evidence).blockers


def test_reported_rpo_must_match_backup_age() -> None:
    evidence = _evidence()
    evidence["recovery"]["rpo_minutes"] = 1
    with pytest.raises(GuardrailValidationError, match="conservative backup age"):
        _assess(evidence)


def test_runtime_and_source_drift_block_review() -> None:
    evidence = _evidence()
    evidence["capacity"]["actual_jobs"] = 5
    evidence["source_contracts"]["approved_unknown_rights_count"] = 1
    result = _assess(evidence)
    assert result.status == "blocked"
    assert "runtime jobs count drift: expected 6, actual 5" in result.blockers
    assert "approved source has unknown rights" in result.blockers


def test_access_review_never_accepts_secret_payload_or_mutation() -> None:
    evidence = _evidence()
    evidence["access_control"]["secret_payloads_read"] = True
    evidence["access_control"]["iam_mutated"] = True
    result = _assess(evidence)
    assert "secret payloads were read during metadata review" in result.blockers
    assert "access review mutated IAM or Secrets" in result.blockers


def test_capacity_growth_emits_actions_without_authorizing_cleanup() -> None:
    evidence = _evidence()
    evidence["capacity"]["database_size_mib"] = 170.0
    evidence["capacity"]["artifact_versions"] = 70
    result = _assess(evidence)
    assert result.status == "attention"
    assert "inspect_database_growth_at_or_above_25_percent" in result.actions
    assert "inspect_artifact_growth_above_20_versions" in result.actions


def test_exact_schema_rejects_unreviewed_extensions() -> None:
    evidence = deepcopy(_evidence())
    evidence["apply"] = True
    with pytest.raises(GuardrailValidationError, match="exactly match"):
        _assess(evidence)


def test_stale_cadence_evidence_blocks_reuse() -> None:
    result = assess_steady_state_review(
        _evidence(), _cost(), as_of=datetime.fromisoformat("2027-01-01T00:00:00+00:00")
    )
    assert "quarterly review evidence is stale" in result.blockers


def test_private_object_recovery_verifies_hash_and_size_without_identifiers() -> None:
    payload = b"private fixture"
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    result = verify_private_object_records(
        [{"content_hash": digest, "private_uri": "gs://private/object", "byte_size": len(payload)}],
        lambda _: payload,
    )
    assert result == {"status": "pass", "object_count": 1, "byte_size": len(payload)}


def test_private_object_recovery_fails_closed_on_hash_mismatch() -> None:
    with pytest.raises(GuardrailValidationError, match="SHA-256"):
        verify_private_object_records(
            [{"content_hash": "0" * 64, "private_uri": "gs://private/object", "byte_size": 3}],
            lambda _: b"bad",
        )
