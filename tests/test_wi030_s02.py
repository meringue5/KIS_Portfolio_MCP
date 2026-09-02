from __future__ import annotations

from datetime import UTC, datetime
from argparse import Namespace

import duckdb
import pytest

from kis_portfolio.adapters.batch import cli as batch_cli
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import (
    CALIBRATION_REPORT_HASH,
    CANARY_RULE_VERSION,
    REAL_USE_RULE_VERSION,
)
from kis_portfolio.services.wi030_s02 import activate_wi030_canary
from kis_portfolio.services.wi030_s03 import activate_wi030_real_use


NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _warehouse() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    for slot in ("kr-1000", "kr-1430", "kr-1600"):
        run_id = f"run-{slot}"
        connection.execute(
            """
            INSERT INTO control.pipeline_runs(
                run_id,pipeline_id,pipeline_version,logical_date,slot,partition_key,
                idempotency_key,status,source_calls,started_at,finished_at
            ) VALUES (?, 'pipeline.owned-portfolio-core-v2','1.0.0','2026-08-31',?,
                      'all-accounts',?,'succeeded',1,?,?)
            """,
            [run_id, slot, f"key-{slot}", NOW, NOW],
        )
        for order, stage in enumerate(("collect-land", "normalize", "quality", "publish")):
            connection.execute(
                """
                INSERT INTO control.pipeline_stage_runs(
                    run_id,stage_name,stage_order,status,attempt,input_count,output_count,
                    source_calls,started_at,finished_at
                ) VALUES (?,?,?,'succeeded',1,1,1,0,?,?)
                """,
                [run_id, stage, order, NOW, NOW],
            )
        connection.execute(
            """
            INSERT INTO control.quality_results VALUES (
                ?,?,'dataset.portfolio-daily-state','quality.fixture','pass','1','1','{}',?
            )
            """,
            [f"quality-{slot}", run_id, NOW],
        )
    for index, slot in enumerate(("kr-1000", "us-close", "kr-1430", "kr-1600")):
        connection.execute(
            """
            INSERT INTO gold.alert_candidates(
                candidate_id,alert_identity,rule_id,rule_version,subject_type,subject_id,
                evaluation_date,evaluation_slot,session_key,evaluation_at,signal_state,severity,
                state_fingerprint,quality_status,input_lineage_hash,public_context,evaluation_run_id
            ) VALUES (?,?, 'rule-set.owned-portfolio-monitoring','bootstrap-1.0.0',
                      'instrument',?,'2026-08-31',?,?,?,'normal','normal',?,'pass',?,'{}',?)
            """,
            [
                f"candidate-{index}", f"identity-{index}", f"instrument-{index}", slot,
                f"session-{slot}", NOW, f"state-{index}", f"lineage-{index}", f"eval-{index}",
            ],
        )
    connection.execute(
        """
        INSERT INTO control.alert_calibration_runs(
            calibration_run_id,rule_set_id,rule_set_version,replay_start,replay_end,
            run_status,source_mode,observation_count,eligible_count,alert_count,report_hash,report
        ) VALUES ('calibration-live','rule-set.owned-portfolio-monitoring','bootstrap-1.0.0',
                  '2023-08-28','2026-08-27','draft','retrospective_reconstructed',10,10,1,?, '{}')
        """,
        [CALIBRATION_REPORT_HASH],
    )
    connection.execute(
        """
        INSERT INTO control.alert_shadow_windows(
            shadow_window_id,rule_set_id,rule_set_version,window_start,window_end,window_status,
            expected_session_count,observed_session_count,candidate_count,
            duplicate_suppressed_count,quality_suppressed_count,sensitive_violation_count,
            external_send_count,owner_review_complete,summary_hash,summary,updated_at
        ) VALUES ('shadow-live','rule-set.owned-portfolio-monitoring','bootstrap-1.0.0',
                  '2026-08-28','2026-09-10','collecting',8,6,55,0,0,0,0,false,?, '{}',?)
        """,
        ["a" * 64, NOW],
    )
    return connection


def test_canary_activation_is_bounded_approved_and_idempotent() -> None:
    connection = _warehouse()

    first = activate_wi030_canary(connection, decided_at=NOW)
    second = activate_wi030_canary(connection, decided_at=NOW)

    assert first["status"] == "activated"
    assert second["status"] == "already_active"
    rule = connection.execute(
        """
        SELECT contract_status,delivery_mode,minimum_delivery_rank,valid_from,valid_to
        FROM control.alert_rule_versions WHERE version=?
        """,
        [CANARY_RULE_VERSION],
    ).fetchone()
    assert rule[:3] == ("active", "external", 1)
    assert (rule[4] - rule[3]).days == 7
    approval = connection.execute(
        """
        SELECT decision,actor_type,rationale_code,evidence_hash
        FROM control.alert_rule_approval_revisions WHERE rule_version=?
        """,
        [CANARY_RULE_VERSION],
    ).fetchone()
    assert approval[:3] == ("approved", "owner", "OWNER_APPROVED_BOUNDED_CANARY")
    assert approval[3] == first["evidence_hash"]
    connection.close()


def test_canary_activation_fails_closed_when_a_smoke_slot_is_missing() -> None:
    connection = _warehouse()
    connection.execute("DELETE FROM gold.alert_candidates WHERE evaluation_slot='us-close'")

    with pytest.raises(RuntimeError, match="all four"):
        activate_wi030_canary(connection, decided_at=NOW)

    assert connection.execute(
        "SELECT count(*) FROM control.alert_rule_versions WHERE version=?",
        [CANARY_RULE_VERSION],
    ).fetchone()[0] == 0
    connection.close()


def _record_successful_canary_delivery(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO gold.alert_candidates(
            candidate_id,alert_identity,rule_id,rule_version,subject_type,subject_id,
            evaluation_date,evaluation_slot,session_key,evaluation_at,signal_state,severity,
            state_fingerprint,quality_status,input_lineage_hash,public_context,evaluation_run_id
        ) VALUES ('canary-candidate','canary-identity','rule-set.owned-portfolio-monitoring',?,
                  'instrument','instrument-safe','2026-09-01','kr-1000','session-canary',?,
                  'active','watch','canary-state','pass','canary-lineage','{}','canary-run')
        """,
        [CANARY_RULE_VERSION, datetime(2026, 9, 1, 1, tzinfo=UTC)],
    )
    connection.execute(
        """
        INSERT INTO control.alert_dispatch_claims(
            dispatch_id,candidate_id,channel,destination_ref,claim_status,claimant_id,
            lease_token_digest,lease_expires_at,attempt_count,created_at,updated_at
        ) VALUES ('dispatch-canary','canary-candidate','telegram','dest.owner.primary','completed',
                  'worker.telegram.v1','digest',?,1,?,?)
        """,
        [NOW, NOW, NOW],
    )
    connection.execute(
        """
        INSERT INTO control.alert_delivery_attempts(
            attempt_id,dispatch_id,attempt_no,outcome,started_at,completed_at,response_ref_hash,recorded_at
        ) VALUES ('attempt-canary','dispatch-canary',1,'sent',?,?,?,?)
        """,
        [NOW, NOW, "b" * 64, NOW],
    )


def test_real_use_activation_preserves_and_revokes_prior_canary_then_is_idempotent() -> None:
    connection = _warehouse()
    activate_wi030_canary(connection, decided_at=NOW)
    _record_successful_canary_delivery(connection)
    decided_at = datetime(2026, 9, 3, 3, tzinfo=UTC)

    first = activate_wi030_real_use(connection, decided_at=decided_at)
    second = activate_wi030_real_use(connection, decided_at=decided_at)

    assert first["status"] == "activated"
    assert second["status"] == "already_active"
    decisions = connection.execute(
        """
        SELECT rule_version,revision,decision,rationale_code
        FROM control.alert_rule_approval_revisions
        WHERE rule_version IN (?,?) ORDER BY rule_version,revision
        """,
        [CANARY_RULE_VERSION, REAL_USE_RULE_VERSION],
    ).fetchall()
    assert (CANARY_RULE_VERSION, 2, "revoked", "REPLACED_BY_PRODUCTION_VALUE_RC") in decisions
    assert (
        REAL_USE_RULE_VERSION, 1, "approved", "OWNER_APPROVED_PRODUCTION_VALUE_RC"
    ) in decisions
    connection.close()


def test_real_use_activation_requires_successful_transport_canary() -> None:
    connection = _warehouse()
    activate_wi030_canary(connection, decided_at=NOW)

    with pytest.raises(RuntimeError, match="successful immutable transport-canary"):
        activate_wi030_real_use(
            connection, decided_at=datetime(2026, 9, 3, 3, tzinfo=UTC)
        )
    assert connection.execute(
        "SELECT count(*) FROM control.alert_rule_versions WHERE version=?",
        [REAL_USE_RULE_VERSION],
    ).fetchone()[0] == 0
    connection.close()


def test_batch_rejects_simultaneous_canary_and_real_use_producers(monkeypatch) -> None:
    monkeypatch.setenv("KIS_TELEGRAM_CANARY_ENABLED", "true")
    monkeypatch.setenv("KIS_TELEGRAM_REAL_USE_ENABLED", "true")

    with pytest.raises(RuntimeError, match="mutually exclusive"):
        batch_cli._run_owned_portfolio_v2(Namespace(
            date="20260903", slot="kr-1000", partition_key="all-accounts",
        ))
