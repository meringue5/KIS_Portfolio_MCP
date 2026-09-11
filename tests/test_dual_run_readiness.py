from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from kis_portfolio.platform.dual_run_readiness import assess_dual_run_readiness
from kis_portfolio.platform.production_guardrails import GuardrailValidationError


ROOT = Path(__file__).parents[1]
WI035 = ROOT / "tests/fixtures/wi035"
WI045 = ROOT / "tests/fixtures/wi045"
AS_OF = datetime(2026, 9, 9, 12, tzinfo=UTC)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _inputs() -> tuple[dict, dict, dict]:
    return (
        _load(WI045 / "dual-run-fixture-v1.json"),
        _load(WI035 / "release-manifest-v1.json"),
        _load(WI035 / "cost-snapshot-v1.json"),
    )


def test_fixture_proves_contract_but_never_authorizes_cutover() -> None:
    decision = assess_dual_run_readiness(*_inputs(), as_of=AS_OF)
    output = decision.as_dict()

    assert decision.status == "blocked"
    assert decision.trading_days == 10
    assert decision.unexplained_differences == 0
    assert decision.explained_partial_gaps == 1
    assert output["production_cutover_allowed"] is False
    assert decision.blockers == ("fixture evidence cannot satisfy the production dual-run gate",)


def test_equivalent_production_observation_passes_all_numeric_gates() -> None:
    evidence, release, cost = _inputs()
    evidence["evidence_scope"] = "production_observation"

    decision = assess_dual_run_readiness(evidence, release, cost, as_of=AS_OF)

    assert decision.status == "pass"
    assert decision.blockers == ()
    assert decision.as_dict()["production_cutover_allowed"] is False


@pytest.mark.parametrize(
    ("mutation", "blocker"),
    [
        (lambda value: value["sessions"].pop(), "fewer than 10 unique trading days"),
        (lambda value: value["schedule"].update(successful_runs=19), "required schedule runs did not all succeed"),
        (lambda value: value["schedule"].update(duplicate_deliveries=1), "duplicate deliveries were observed"),
        (lambda value: value["restore"].update(rpo_minutes=1441), "restore RPO exceeded 24 hours"),
        (lambda value: value["restore"].update(rto_minutes=241), "restore RTO exceeded 4 hours"),
    ],
)
def test_operational_gaps_fail_closed(mutation, blocker) -> None:
    evidence, release, cost = _inputs()
    evidence["evidence_scope"] = "production_observation"
    mutation(evidence)

    decision = assess_dual_run_readiness(evidence, release, cost, as_of=AS_OF)

    assert decision.status == "blocked"
    assert blocker in decision.blockers


def test_value_outside_tolerance_is_unexplained_difference() -> None:
    evidence, release, cost = _inputs()
    evidence["evidence_scope"] = "production_observation"
    evidence["sessions"][0]["metrics"]["total_asset_krw"]["v2"] += 2

    decision = assess_dual_run_readiness(evidence, release, cost, as_of=AS_OF)

    assert decision.unexplained_differences == 1
    assert "unexplained V1/V2 differences: 1" in decision.blockers


def test_partial_requires_reason_and_explicit_missing_coverage() -> None:
    evidence, release, cost = _inputs()
    partial = evidence["sessions"][1]["metrics"]["signals"]
    partial["quality_reason"] = ""
    partial["missing_coverage"] = []

    with pytest.raises(GuardrailValidationError) as raised:
        assess_dual_run_readiness(evidence, release, cost, as_of=AS_OF)

    assert "quality_reason must be non-empty" in str(raised.value)
    assert "missing_coverage must be a non-empty string list" in str(raised.value)


def test_cost_target_and_manifest_contract_remain_fail_closed() -> None:
    evidence, release, cost = _inputs()
    evidence["evidence_scope"] = "production_observation"
    cost["forecast_krw"] = 7501

    decision = assess_dual_run_readiness(evidence, release, cost, as_of=AS_OF)
    assert "normal-month cost exceeded the 7500 KRW target" in decision.blockers

    invalid_release = deepcopy(release)
    invalid_release["rollback_targets"] = []
    with pytest.raises(GuardrailValidationError):
        assess_dual_run_readiness(evidence, invalid_release, cost, as_of=AS_OF)
