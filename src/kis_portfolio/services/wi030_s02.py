"""DEC-050 bounded Telegram canary activation gates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.alert_calibration_warehouse import AlertCalibrationWarehouse
from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import (
    CALIBRATION_REPORT_HASH,
    CANARY_RULE_VERSION,
    RULE_ID,
    RULE_VERSION,
    canary_rule,
)


SMOKE_DATE = date(2026, 8, 31)
EXPECTED_PIPELINE_SLOTS = frozenset({"kr-1000", "kr-1430", "kr-1600"})
EXPECTED_EVALUATION_SLOTS = frozenset({"kr-1000", "us-close", "kr-1430", "kr-1600"})


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )


def activate_wi030_canary(
    connection: duckdb.DuckDBPyConnection,
    *,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    """Register and owner-approve the exact bounded canary after live smoke evidence."""
    now = decided_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("decided_at must be timezone-aware")
    MigrationRunner(connection).require("0013")

    runs = connection.execute(
        """
        SELECT r.slot,r.status,count(DISTINCT s.stage_name) AS stage_count,
               count(DISTINCT CASE WHEN s.status!='succeeded' THEN s.stage_name END) AS failed_stages,
               count(DISTINCT CASE WHEN q.status='pass' THEN q.quality_result_id END) AS pass_quality
        FROM control.pipeline_runs r
        LEFT JOIN control.pipeline_stage_runs s USING(run_id)
        LEFT JOIN control.quality_results q USING(run_id)
        WHERE r.pipeline_id='pipeline.owned-portfolio-core-v2' AND r.logical_date=?
        GROUP BY r.slot,r.status
        ORDER BY r.slot
        """,
        [SMOKE_DATE],
    ).fetchall()
    run_slots = {str(row[0]) for row in runs}
    if run_slots != EXPECTED_PIPELINE_SLOTS or any(
        str(row[1]) != "succeeded"
        or int(row[2]) != 4
        or int(row[3]) != 0
        or int(row[4]) < 1
        for row in runs
    ):
        raise RuntimeError("DEC-050 requires one complete pass-quality scheduled day")

    candidate_rows = connection.execute(
        """
        SELECT evaluation_slot,count(*) AS candidate_count,
               count_if(quality_status='pass') AS pass_count
        FROM gold.alert_candidates
        WHERE rule_id=? AND rule_version=? AND evaluation_date=?
        GROUP BY evaluation_slot
        ORDER BY evaluation_slot
        """,
        [RULE_ID, RULE_VERSION, SMOKE_DATE],
    ).fetchall()
    evaluation_slots = {str(row[0]) for row in candidate_rows}
    if evaluation_slots != EXPECTED_EVALUATION_SLOTS or any(
        int(row[1]) <= 0 or int(row[1]) != int(row[2]) for row in candidate_rows
    ):
        raise RuntimeError("DEC-050 requires all four pass-quality evaluation slots")

    calibration = connection.execute(
        "SELECT calibration_run_id,run_status FROM control.alert_calibration_runs WHERE report_hash=?",
        [CALIBRATION_REPORT_HASH],
    ).fetchone()
    shadow = connection.execute(
        """
        SELECT shadow_window_id,window_status,observed_session_count,
               sensitive_violation_count,external_send_count
        FROM control.alert_shadow_windows
        WHERE rule_set_id=? AND rule_set_version=?
        ORDER BY updated_at DESC LIMIT 1
        """,
        [RULE_ID, RULE_VERSION],
    ).fetchone()
    if calibration is None or shadow is None:
        raise RuntimeError("DEC-050 requires governed replay and shadow evidence")
    if int(shadow[2]) <= 0 or int(shadow[3]) != 0 or int(shadow[4]) != 0:
        raise RuntimeError("DEC-050 requires clean shadow evidence and zero external sends")

    rule = canary_rule()
    AlertWarehouseRepository(connection).register_rule(rule)
    evidence = {
        "decision_ref": "DEC-050",
        "smoke_date": SMOKE_DATE.isoformat(),
        "pipeline_slots": sorted(run_slots),
        "evaluation_slots": sorted(evaluation_slots),
        "pipeline_run_count": len(runs),
        "candidate_count": sum(int(row[1]) for row in candidate_rows),
        "all_candidate_quality_pass": True,
        "sensitive_violation_count": int(shadow[3]),
        "external_send_count": int(shadow[4]),
        "rule_version": CANARY_RULE_VERSION,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat() if rule.valid_to is not None else None,
    }
    evidence_hash = hashlib.sha256(_canonical(evidence).encode()).hexdigest()
    existing = connection.execute(
        """
        SELECT decision,evidence_hash FROM control.alert_rule_approval_revisions
        WHERE rule_id=? AND rule_version=? ORDER BY revision DESC LIMIT 1
        """,
        [RULE_ID, CANARY_RULE_VERSION],
    ).fetchone()
    if existing is not None:
        if str(existing[0]) == "approved" and str(existing[1]) == evidence_hash:
            return {"status": "already_active", **evidence, "evidence_hash": evidence_hash}
        raise RuntimeError("bounded canary already has a different owner decision")

    AlertCalibrationWarehouse(connection).append_owner_canary_approval(
        rule_id=RULE_ID,
        rule_version=CANARY_RULE_VERSION,
        actor_type="owner",
        calibration_run_id=str(calibration[0]),
        shadow_window_id=str(shadow[0]),
        evidence_hash=evidence_hash,
        decided_at=now,
        expected_prior_revision=0,
    )
    return {"status": "activated", **evidence, "evidence_hash": evidence_hash}
