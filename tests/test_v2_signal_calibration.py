from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.alert_calibration_warehouse import (
    AlertCalibrationWarehouse,
    CalibrationGateError,
)
from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.modules.monitoring import (
    AlertCandidate,
    AlertEvaluation,
    AlertRuleVersion,
    SignalObservation,
    ThresholdProfile,
    calibrate_replay,
    evaluate_bootstrap_signal,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE_TIME = datetime(2023, 1, 1, 1, tzinfo=UTC)


def _observation(**changes: object) -> SignalObservation:
    values: dict[str, object] = {
        "subject_id": "opaque-subject",
        "asset_class": "stock",
        "evaluation_at": BASE_TIME,
        "evaluation_slot": "kr-1600",
        "session_key": "krx:2023-01-01",
        "quality_status": "pass",
        "provenance_mode": "retrospective_reconstructed",
        "valid_bar_count": 120,
        "daily_return": Decimal("-0.031"),
        "vol20": Decimal("0.01"),
    }
    values.update(changes)
    return SignalObservation(**values)  # type: ignore[arg-type]


def _rule() -> AlertRuleVersion:
    return AlertRuleVersion.from_document({
        "id": "rule-set.owned-portfolio-monitoring",
        "version": "bootstrap-1.0.0",
        "status": "approved",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "shadow",
        "valid_from": BASE_TIME - timedelta(days=1),
        "valid_to": None,
    })


def _candidate(at: datetime) -> AlertCandidate:
    return AlertCandidate.build(_rule(), AlertEvaluation(
        subject_type="instrument",
        subject_id="opaque-subject",
        evaluation_date=at.date(),
        evaluation_slot="kr-1600",
        session_key=f"krx:{at.date().isoformat()}",
        evaluation_at=at,
        signal_state="normal",
        severity="normal",
        state_key="normal",
        quality_status="pass",
        input_lineage_hash=f"lineage-{at.date().isoformat()}",
        public_context={
            "subject_label": "fixture",
            "summary": "normal shadow fixture",
            "reason_codes": [],
            "quality_status": "pass",
        },
        evaluation_run_id=f"run-{at.date().isoformat()}",
    ))


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection


def test_bootstrap_boundaries_use_four_levels_and_context_is_not_a_signal() -> None:
    profile = ThresholdProfile("stock")
    assert evaluate_bootstrap_signal(_observation(), profile).severity == "watch"
    assert evaluate_bootstrap_signal(
        _observation(daily_return=Decimal("-0.06")), profile
    ).severity == "warning"
    assert evaluate_bootstrap_signal(
        _observation(daily_return=Decimal("-0.09")), profile
    ).severity == "critical"
    context_only = evaluate_bootstrap_signal(_observation(
        daily_return=Decimal("-0.001"), close=Decimal("89"), sma20=Decimal("90"),
        sma50=Decimal("95"), previous_close=Decimal("89"), previous_sma20=Decimal("90"),
        rsi14=Decimal("25"), bollinger_percent_b=Decimal("-0.1"),
    ), profile)
    assert context_only.severity == "watch"  # bearish SMA20+SMA50 transition confirms context
    assert context_only.reason_codes == ("bearish_sma20_regime",)
    downward_cross = evaluate_bootstrap_signal(_observation(
        daily_return=Decimal("-0.001"), close=Decimal("89"), sma20=Decimal("90"),
        sma50=Decimal("95"), previous_close=Decimal("96"), previous_sma20=Decimal("95"),
    ), profile)
    assert downward_cross.reason_codes == ("sma20_downward_cross",)
    rsi_bollinger_only = evaluate_bootstrap_signal(_observation(
        daily_return=None, close=None, sma20=None, sma50=None,
        rsi14=Decimal("25"), bollinger_percent_b=Decimal("-0.1"),
    ), profile)
    assert rsi_bollinger_only.severity == "normal"
    assert {"rsi14_below_30", "bollinger_below_lower"} <= set(rsi_bollinger_only.context_codes)


def test_volume_escalates_price_shock_but_not_unrelated_risk() -> None:
    profile = ThresholdProfile("stock")
    price = evaluate_bootstrap_signal(_observation(
        daily_return=Decimal("-0.031"), volume_ratio20=Decimal("1.6")
    ), profile)
    assert price.severity == "warning"
    risk = evaluate_bootstrap_signal(_observation(
        daily_return=None, risk_ratio=Decimal("0.0151"), volume_ratio20=Decimal("1.6")
    ), profile)
    assert risk.severity == "watch"


def test_short_history_uses_absolute_return_only_and_non_pass_is_suppressed() -> None:
    profile = ThresholdProfile("etf")
    short = evaluate_bootstrap_signal(_observation(
        asset_class="etf", valid_bar_count=10, vol20=None, daily_return=Decimal("0.031")
    ), profile)
    assert short.severity == "watch"
    assert "volatility_insufficient_history" in short.context_codes
    partial = evaluate_bootstrap_signal(_observation(
        asset_class="etf", quality_status="partial"
    ), profile)
    assert partial.severity == "normal"
    assert partial.delivery_eligible is False


def _three_year_observations() -> list[SignalObservation]:
    observations = []
    for offset in range(1096):
        at = BASE_TIME + timedelta(days=offset)
        observations.append(_observation(
            subject_id=f"stock-{offset % 3}",
            evaluation_at=at,
            session_key=f"krx:{at.date().isoformat()}",
            daily_return=Decimal("-0.031") if offset % 50 == 0 else Decimal("0.001"),
        ))
    return observations


def test_replay_report_is_deterministic_budgeted_and_provenance_labelled() -> None:
    observations = _three_year_observations()
    first = calibrate_replay(observations)
    second = calibrate_replay(reversed(observations))
    assert first.report_hash == second.report_hash
    assert first.report["three_year_span"] is True
    assert first.report["source_mode"] == "retrospective_reconstructed"
    stock = first.report["asset_classes"]["stock"]  # type: ignore[index]
    assert stock["three_year_coverage_ready"] is True
    assert stock["alert_budget_pass"] is True
    assert stock["active_observation_count"] == 22
    assert stock["alert_count"] == 44  # 22 entries plus 22 recoveries, not every unchanged active state
    assert first.report["global_alert_budget"]["alert_budget_pass"] is True  # type: ignore[index]
    assert stock["maximum_miss_proxy"]["definition"].endswith("not an owner-labelled miss")
    assert first.report["owner_label_review_complete"] is False


def test_calibration_shadow_and_owner_approval_gates(tmp_path: Path) -> None:
    connection = _connection()
    alerts = AlertWarehouseRepository(connection)
    calibration = AlertCalibrationWarehouse(connection)
    rule = _rule()
    alerts.register_rule(rule)
    stored_rule = connection.execute(
        "SELECT minimum_delivery_severity,minimum_delivery_rank FROM control.alert_rule_versions"
    ).fetchone()
    assert stored_rule == ("warning", 1)  # 0012 compatibility column plus exact 0013 rank

    result = calibrate_replay(_three_year_observations())
    write = calibration.write_calibration(result)
    assert write.inserted is True
    assert calibration.write_calibration(result).inserted is False
    with pytest.raises(CalibrationGateError, match="only owner"):
        calibration.mark_calibration_reviewed(
            calibration_run_id=write.calibration_run_id, actor_type="system",
            owner_review_hash="a" * 64, reviewed_at=BASE_TIME + timedelta(days=1096),
        )
    calibration.mark_calibration_reviewed(
        calibration_run_id=write.calibration_run_id, actor_type="owner",
        owner_review_hash="a" * 64, reviewed_at=BASE_TIME + timedelta(days=1096),
    )

    shadow_start = date(2026, 8, 1)
    expected = []
    for offset in range(14):
        at = datetime(2026, 8, 1 + offset, 7, tzinfo=UTC)
        candidate = _candidate(at)
        alerts.apply_candidate(candidate)
        expected.append(f"evaluation:{at.date().isoformat()}|kr-1600")
    evidence = calibration.build_shadow_evidence(
        rule_set_id=rule.rule_id, rule_set_version=rule.version,
        window_start=shadow_start, window_end=date(2026, 8, 14),
        expected_session_keys=expected, owner_review_complete=False,
    )
    assert evidence.elapsed_days == 14
    assert evidence.external_send_count == 0
    assert evidence.duplicate_suppressed_count == 13
    calibration.write_shadow_evidence(evidence, updated_at=datetime(2026, 8, 14, 8, tzinfo=UTC))
    with pytest.raises(CalibrationGateError, match="has not passed"):
        calibration.verify_shadow(
            shadow_window_id=evidence.shadow_window_id, actor_type="owner",
            verified_at=datetime(2026, 8, 14, 9, tzinfo=UTC),
        )
    reviewed = calibration.build_shadow_evidence(
        rule_set_id=rule.rule_id, rule_set_version=rule.version,
        window_start=shadow_start, window_end=date(2026, 8, 14),
        expected_session_keys=expected, owner_review_complete=True,
    )
    assert calibration.write_shadow_evidence(
        reviewed, updated_at=datetime(2026, 8, 14, 9, tzinfo=UTC)
    ) == "review_ready"
    calibration.verify_shadow(
        shadow_window_id=reviewed.shadow_window_id, actor_type="owner",
        verified_at=datetime(2026, 8, 14, 10, tzinfo=UTC),
    )
    decision_id = calibration.append_owner_decision(
        rule_id=rule.rule_id, rule_version=rule.version, decision="approved",
        actor_type="owner", calibration_run_id=write.calibration_run_id,
        shadow_window_id=reviewed.shadow_window_id,
        evidence_hash=hashlib.sha256(b"owner evidence").hexdigest(),
        rationale_code="OWNER_REVIEW_APPROVED", decided_at=datetime(2026, 8, 14, 11, tzinfo=UTC),
        expected_prior_revision=0,
    )
    assert len(decision_id) == 64

    expected_tables = {
        "control.alert_calibration_runs", "control.alert_shadow_windows",
        "control.alert_rule_approval_revisions",
    }
    assert expected_tables <= set(v2_backup_table_names())
    backup = tmp_path / "backup"
    manifest = export_v2_backup(connection, backup, database="fixture")
    connection.close()
    assert manifest["tables"]["control.alert_calibration_runs"]["rows"] == 1
    assert restore_v2_backup(backup, tmp_path / "restored.duckdb")["status"] == "verified"


def test_short_replay_cannot_be_marked_review_ready() -> None:
    connection = _connection()
    repository = AlertCalibrationWarehouse(connection)
    result = calibrate_replay([
        _observation(),
        _observation(evaluation_at=BASE_TIME + timedelta(days=30), session_key="krx:2023-01-31"),
    ])
    write = repository.write_calibration(result)
    with pytest.raises(CalibrationGateError, match="shorter than three years"):
        repository.mark_calibration_reviewed(
            calibration_run_id=write.calibration_run_id, actor_type="owner",
            owner_review_hash="b" * 64, reviewed_at=BASE_TIME + timedelta(days=31),
        )
    connection.close()
