"""DEC-051 production-value Telegram release-candidate activation gates."""

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
    CANARY_RULE_VERSION,
    REAL_USE_RULE_VERSION,
    RULE_ID,
    RULE_VERSION,
    real_use_rule,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def activate_wi030_real_use(
    connection: duckdb.DuckDBPyConnection,
    *,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    """Activate a new immutable rich-message RC and revoke the transport-only canary."""
    now = decided_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("decided_at must be timezone-aware")
    MigrationRunner(connection).require("0013")

    canary = connection.execute(
        """
        SELECT revision,decision FROM control.alert_rule_approval_revisions
        WHERE rule_id=? AND rule_version=? ORDER BY revision DESC LIMIT 1
        """,
        [RULE_ID, CANARY_RULE_VERSION],
    ).fetchone()
    sent_count = int(connection.execute(
        """
        SELECT count(*) FROM control.alert_delivery_attempts a
        JOIN control.alert_dispatch_claims d USING(dispatch_id)
        JOIN gold.alert_candidates c USING(candidate_id)
        WHERE c.rule_id=? AND c.rule_version=? AND d.channel='telegram' AND a.outcome='sent'
        """,
        [RULE_ID, CANARY_RULE_VERSION],
    ).fetchone()[0])
    if canary is None or str(canary[1]) not in {"approved", "revoked"} or sent_count <= 0:
        raise RuntimeError("DEC-051 requires successful immutable transport-canary evidence")

    calibration = connection.execute(
        "SELECT calibration_run_id,run_status FROM control.alert_calibration_runs WHERE report_hash=?",
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
        raise RuntimeError("DEC-051 requires governed replay and shadow evidence")
    if int(shadow[2]) <= 0 or int(shadow[3]) != 0 or int(shadow[4]) != 0:
        raise RuntimeError("DEC-051 requires clean shadow evidence and zero shadow external sends")

    rule = real_use_rule()
    if not (rule.valid_from <= now < rule.valid_to):
        raise RuntimeError("production-value release candidate is outside its bounded validity")
    evidence = {
        "decision_ref": "DEC-051",
        "prior_canary_version": CANARY_RULE_VERSION,
        "prior_canary_sent_count": sent_count,
        "presentation_version": "production-value-v1",
        "explicit_unavailable_metrics": ["episode_drawdown", "valuation_change_contribution"],
        "rule_version": REAL_USE_RULE_VERSION,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat(),
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
            [RULE_ID, REAL_USE_RULE_VERSION],
        ).fetchone()
        if existing is None:
            warehouse.append_owner_canary_approval(
                rule_id=RULE_ID,
                rule_version=REAL_USE_RULE_VERSION,
                actor_type="owner",
                calibration_run_id=str(calibration[0]),
                shadow_window_id=str(shadow[0]),
                evidence_hash=evidence_hash,
                decided_at=now,
                expected_prior_revision=0,
                rationale_code="OWNER_APPROVED_PRODUCTION_VALUE_RC",
            )
            activation_status = "activated"
        elif str(existing[1]) == "approved" and str(existing[2]) == evidence_hash:
            activation_status = "already_active"
        else:
            raise RuntimeError("production-value release candidate has a different owner decision")

        if str(canary[1]) == "approved":
            revoke_evidence = hashlib.sha256(_canonical({
                "decision_ref": "DEC-051",
                "rule_version": CANARY_RULE_VERSION,
                "replacement": REAL_USE_RULE_VERSION,
                "preserve_history": True,
            }).encode()).hexdigest()
            warehouse.append_owner_decision(
                rule_id=RULE_ID,
                rule_version=CANARY_RULE_VERSION,
                decision="revoked",
                actor_type="owner",
                calibration_run_id=None,
                shadow_window_id=None,
                evidence_hash=revoke_evidence,
                rationale_code="REPLACED_BY_PRODUCTION_VALUE_RC",
                decided_at=now,
                expected_prior_revision=int(canary[0]),
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {"status": activation_status, **evidence, "evidence_hash": evidence_hash}
