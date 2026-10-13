"""DEC-061 permanent held-position Telegram signal activation gates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.alert_calibration_warehouse import AlertCalibrationWarehouse
from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import (
    CALIBRATION_REPORT_HASH,
    PERMANENT_REAL_USE_RULE_VERSION,
    REAL_USE_RULE_VERSION,
    RULE_ID,
    RULE_VERSION,
    permanent_real_use_rule,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def activate_wi070_permanent_signals(
    connection: duckdb.DuckDBPyConnection,
    *,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    """Approve the permanent successor and revoke the expired RC append-only."""
    now = decided_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("decided_at must be timezone-aware")
    MigrationRunner(connection).require("0013")

    prior_release = connection.execute(
        """
        SELECT revision,decision FROM control.alert_rule_approval_revisions
        WHERE rule_id=? AND rule_version=? ORDER BY revision DESC LIMIT 1
        """,
        [RULE_ID, REAL_USE_RULE_VERSION],
    ).fetchone()
    sent_count = int(connection.execute(
        """
        SELECT count(*) FROM control.alert_delivery_attempts a
        JOIN control.alert_dispatch_claims d USING(dispatch_id)
        JOIN gold.alert_candidates c USING(candidate_id)
        WHERE c.rule_id=? AND c.rule_version=? AND d.channel='telegram' AND a.outcome='sent'
        """,
        [RULE_ID, REAL_USE_RULE_VERSION],
    ).fetchone()[0])
    if (
        prior_release is None
        or str(prior_release[1]) not in {"approved", "revoked"}
        or sent_count <= 0
    ):
        raise RuntimeError("DEC-061 requires approved prior RC and successful owner delivery evidence")

    calibration = connection.execute(
        """
        SELECT calibration_run_id,run_status FROM control.alert_calibration_runs
        WHERE report_hash=?
        """,
        [CALIBRATION_REPORT_HASH],
    ).fetchone()
    shadow = connection.execute(
        """
        SELECT shadow_window_id,window_status,observed_session_count,
               sensitive_violation_count,external_send_count
        FROM control.alert_shadow_windows
        WHERE rule_set_id=? AND rule_set_version=? ORDER BY updated_at DESC LIMIT 1
        """,
        [RULE_ID, RULE_VERSION],
    ).fetchone()
    if calibration is None or shadow is None:
        raise RuntimeError("DEC-061 requires governed replay and current shadow evidence")

    rule = permanent_real_use_rule()
    if rule.valid_to is not None or now < rule.valid_from:
        raise RuntimeError("permanent signal rule is not yet effective or has an expiry")
    evidence = {
        "decision_ref": "DEC-061",
        "prior_rule_version": REAL_USE_RULE_VERSION,
        "prior_owner_sent_count": sent_count,
        "rule_version": PERMANENT_REAL_USE_RULE_VERSION,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": None,
        "scope": "held-positive-quantity-only",
        "initial_active_policy": "baseline_only",
        "historical_replay": False,
        "presentation_version": "production-value-v3",
        "shadow_sensitive_violation_count": int(shadow[3]),
        "shadow_external_send_count": int(shadow[4]),
    }
    evidence_hash = hashlib.sha256(_canonical(evidence).encode()).hexdigest()
    warehouse = AlertCalibrationWarehouse(connection)

    connection.execute("BEGIN TRANSACTION")
    try:
        AlertWarehouseRepository(connection).register_rule(rule)
        existing = connection.execute(
            """
            SELECT revision,decision,evidence_hash FROM control.alert_rule_approval_revisions
            WHERE rule_id=? AND rule_version=? ORDER BY revision DESC LIMIT 1
            """,
            [RULE_ID, PERMANENT_REAL_USE_RULE_VERSION],
        ).fetchone()
        if existing is None:
            warehouse.append_owner_permanent_approval(
                rule_id=RULE_ID,
                rule_version=PERMANENT_REAL_USE_RULE_VERSION,
                actor_type="owner",
                calibration_run_id=str(calibration[0]),
                shadow_window_id=str(shadow[0]),
                evidence_hash=evidence_hash,
                decided_at=now,
                expected_prior_revision=0,
            )
            activation_status = "activated"
        elif str(existing[1]) == "approved" and str(existing[2]) == evidence_hash:
            activation_status = "already_active"
        else:
            raise RuntimeError("permanent signal rule has a different owner decision")

        if str(prior_release[1]) == "approved":
            revoke_evidence = hashlib.sha256(_canonical({
                "decision_ref": "DEC-061",
                "rule_version": REAL_USE_RULE_VERSION,
                "replacement": PERMANENT_REAL_USE_RULE_VERSION,
                "preserve_history": True,
                "historical_replay": False,
            }).encode()).hexdigest()
            warehouse.append_owner_decision(
                rule_id=RULE_ID,
                rule_version=REAL_USE_RULE_VERSION,
                decision="revoked",
                actor_type="owner",
                calibration_run_id=None,
                shadow_window_id=None,
                evidence_hash=revoke_evidence,
                rationale_code="REPLACED_BY_PERMANENT_HELD_SIGNALS",
                decided_at=now,
                expected_prior_revision=int(prior_release[0]),
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {"status": activation_status, **evidence, "evidence_hash": evidence_hash}
