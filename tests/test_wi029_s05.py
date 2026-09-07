from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb
import pytest

from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.adapters.outbound.alert_calibration_warehouse import AlertCalibrationWarehouse
from kis_portfolio.modules.monitoring import AlertCandidate, AlertEvaluation, AlertRuleVersion
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import RULE_ID, RULE_VERSION
from kis_portfolio.services.wi029_s05 import (
    expected_shadow_slot_keys,
    refresh_wi029_s05_evidence,
)


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute("""
        CREATE TABLE main.market_calendar(
            market VARCHAR NOT NULL,
            trade_date DATE NOT NULL,
            is_open BOOLEAN NOT NULL,
            open_time_local VARCHAR,
            close_time_local VARCHAR,
            timezone VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            PRIMARY KEY(market, trade_date)
        )
    """)
    for day, is_open in (
        (date(2026, 8, 28), True),
        (date(2026, 8, 29), False),
        (date(2026, 8, 30), False),
        (date(2026, 8, 31), True),
    ):
        connection.execute(
            """
            INSERT INTO main.market_calendar(
                market,trade_date,is_open,open_time_local,close_time_local,timezone,source
            ) VALUES ('krx',?,?,?,?,?,?)
            """,
            [day, is_open, "09:00" if is_open else None, "15:30" if is_open else None,
             "Asia/Seoul", "fixture"],
        )
    return connection


def _rule() -> AlertRuleVersion:
    return AlertRuleVersion.from_document({
        "id": RULE_ID,
        "version": RULE_VERSION,
        "status": "approved",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "shadow",
        "valid_from": datetime(2023, 1, 1, tzinfo=UTC),
        "valid_to": None,
    })


def _write_candidate(connection: duckdb.DuckDBPyConnection, *, evaluated: date, slot: str) -> None:
    alerts = AlertWarehouseRepository(connection)
    rule = _rule()
    alerts.register_rule(rule)
    alerts.apply_candidate(AlertCandidate.build(rule, AlertEvaluation(
        subject_type="instrument",
        subject_id=f"opaque-{evaluated}-{slot}",
        evaluation_date=evaluated,
        evaluation_slot=slot,
        session_key=(
            f"us-close:{(evaluated if slot != 'us-close' else date(2026, 8, 27)).isoformat()}"
            if slot == "us-close" else f"krx:{evaluated.isoformat()}"
        ),
        evaluation_at=datetime.combine(evaluated, datetime.min.time(), tzinfo=UTC),
        signal_state="normal",
        severity="normal",
        state_key="normal",
        quality_status="missing_current_price",
        input_lineage_hash="a" * 64,
        public_context={"summary": "fixture"},
        evaluation_run_id=f"fixture-{evaluated}-{slot}",
    )))


def test_expected_slots_use_calendar_and_only_due_schedule_times() -> None:
    connection = _connection()
    expected = expected_shadow_slot_keys(
        connection,
        window_start=date(2026, 8, 28),
        window_end=date(2026, 9, 10),
        observed_at=datetime(2026, 8, 31, 1, 5, tzinfo=UTC),
    )
    assert expected == (
        "evaluation:2026-08-28|kr-1000",
        "evaluation:2026-08-28|us-close",
        "evaluation:2026-08-28|kr-1430",
        "evaluation:2026-08-28|kr-1600",
        "evaluation:2026-08-31|kr-1000",
        "evaluation:2026-08-31|us-close",
    )
    connection.close()


def test_refresh_detects_missing_slot_independently_of_candidate_session_key() -> None:
    connection = _connection()
    for slot in ("kr-1000", "us-close", "kr-1430"):
        _write_candidate(connection, evaluated=date(2026, 8, 28), slot=slot)

    result = refresh_wi029_s05_evidence(
        connection, recorded_at=datetime(2026, 8, 28, 8, tzinfo=UTC),
        window_start=date(2026, 8, 28), window_end=date(2026, 8, 28),
    )

    assert result["status"] == "collecting"
    assert result["expected_due_slot_count"] == 4
    assert result["observed_slot_count"] == 3
    assert result["missing_slot_keys"] == ["evaluation:2026-08-28|kr-1600"]
    assert result["external_send_count"] == 0
    connection.close()


def test_shadow_slot_requires_terminal_delivery_claim() -> None:
    connection = _connection()
    alerts = AlertWarehouseRepository(connection)
    rule = _rule()
    alerts.register_rule(rule)
    candidate = AlertCandidate.build(rule, AlertEvaluation(
        subject_type="instrument", subject_id="opaque-dangling",
        evaluation_date=date(2026, 8, 28), evaluation_slot="kr-1600",
        session_key="krx:2026-08-28", evaluation_at=datetime(2026, 8, 28, 7, tzinfo=UTC),
        signal_state="active", severity="warning", state_key="warning",
        quality_status="pass", input_lineage_hash="b" * 64,
        public_context={"summary": "fixture"}, evaluation_run_id="fixture-dangling",
    ))
    alerts.apply_candidate(candidate)
    alerts.claim_dispatch(
        candidate_id=candidate.candidate_id, channel="shadow",
        destination_ref="shadow.owner", claimant_id="fixture",
        lease_token="lease", claimed_at=datetime(2026, 8, 28, 7, tzinfo=UTC),
    )

    evidence = AlertCalibrationWarehouse(connection).build_shadow_evidence(
        rule_set_id=RULE_ID, rule_set_version=RULE_VERSION,
        window_start=date(2026, 8, 28), window_end=date(2026, 8, 28),
        expected_session_keys=["evaluation:2026-08-28|kr-1600"],
        owner_review_complete=False,
    )

    assert evidence.observed_session_keys == ()
    assert evidence.summary["incomplete_session_keys"] == ["evaluation:2026-08-28|kr-1600"]
    assert evidence.summary["dangling_shadow_claim_count"] == 1
    connection.close()


def test_completion_marker_proves_zero_candidate_slot_after_cutover() -> None:
    connection = _connection()
    connection.execute(
        """
        INSERT INTO control.quality_results VALUES (
          'marker','run','dataset.alert-calibration-evidence','shadow-slot-terminal-v1',
          'pass','0','terminal',
          '{"logical_date":"2026-08-28","source_slot":"kr-1430"}',
          '2026-08-28T05:30:00+00:00'
        )
        """
    )
    evidence = AlertCalibrationWarehouse(connection).build_shadow_evidence(
        rule_set_id=RULE_ID, rule_set_version=RULE_VERSION,
        window_start=date(2026, 8, 28), window_end=date(2026, 8, 28),
        expected_session_keys=["evaluation:2026-08-28|kr-1430"],
        owner_review_complete=False,
        completion_marker_required_from=date(2026, 8, 28),
    )
    assert evidence.observed_session_keys == ("evaluation:2026-08-28|kr-1430",)
    connection.close()


def test_expected_slots_fail_closed_when_calendar_coverage_is_missing() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    with pytest.raises(RuntimeError, match="complete KRX calendar"):
        expected_shadow_slot_keys(
            connection,
            window_start=date(2026, 8, 28),
            window_end=date(2026, 9, 10),
            observed_at=datetime(2026, 8, 28, 8, tzinfo=UTC),
        )
    connection.close()
