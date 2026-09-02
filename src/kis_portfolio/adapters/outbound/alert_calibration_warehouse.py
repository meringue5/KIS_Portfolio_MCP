"""Persistence and evidence gates for replay calibration, shadow and owner approval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

import duckdb

from kis_portfolio.modules.monitoring.calibration import CalibrationResult


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


class CalibrationGateError(RuntimeError):
    """Raised when replay, shadow or owner evidence is insufficient."""


@dataclass(frozen=True, slots=True)
class CalibrationWrite:
    calibration_run_id: str
    inserted: bool


@dataclass(frozen=True, slots=True)
class ShadowEvidence:
    shadow_window_id: str
    rule_set_id: str
    rule_set_version: str
    window_start: date
    window_end: date
    expected_session_keys: tuple[str, ...]
    observed_session_keys: tuple[str, ...]
    candidate_count: int
    duplicate_suppressed_count: int
    quality_suppressed_count: int
    sensitive_violation_count: int
    external_send_count: int
    owner_review_complete: bool
    summary: Mapping[str, object]
    summary_hash: str

    @property
    def elapsed_days(self) -> int:
        return (self.window_end - self.window_start).days + 1

    @property
    def objectively_verifiable(self) -> bool:
        return (
            self.elapsed_days >= 14
            and set(self.observed_session_keys) == set(self.expected_session_keys)
            and self.sensitive_violation_count == 0
            and self.external_send_count == 0
            and self.owner_review_complete
        )


class AlertCalibrationWarehouse:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def write_calibration(self, result: CalibrationResult) -> CalibrationWrite:
        report = dict(result.report)
        start = date.fromisoformat(str(report["replay_start"]))
        end = date.fromisoformat(str(report["replay_end"]))
        run_id = _hash(
            "alert-calibration-run-v1", result.rule_set_id, result.rule_set_version,
            result.report_hash,
        )
        prior = self.connection.execute(
            "SELECT calibration_run_id FROM control.alert_calibration_runs WHERE report_hash=?",
            [result.report_hash],
        ).fetchone()
        if prior is not None:
            return CalibrationWrite(str(prior[0]), False)
        self.connection.execute(
            """
            INSERT INTO control.alert_calibration_runs(
                calibration_run_id,rule_set_id,rule_set_version,replay_start,replay_end,
                run_status,source_mode,observation_count,eligible_count,alert_count,
                report_hash,report
            ) VALUES (?,?,?,?,?,'draft',?,?,?,?,?,?)
            """,
            [
                run_id, result.rule_set_id, result.rule_set_version, start, end,
                report["source_mode"], report["observation_count"], report["eligible_count"],
                report["alert_count"], result.report_hash, _json(report),
            ],
        )
        return CalibrationWrite(run_id, True)

    def mark_calibration_reviewed(
        self,
        *,
        calibration_run_id: str,
        actor_type: str,
        owner_review_hash: str,
        reviewed_at: datetime,
    ) -> None:
        _aware(reviewed_at, "reviewed_at")
        if actor_type != "owner":
            raise CalibrationGateError("only owner may complete false-positive and miss review")
        if len(owner_review_hash) != 64:
            raise CalibrationGateError("owner review requires a SHA-256 evidence hash")
        row = self.connection.execute(
            "SELECT report,run_status FROM control.alert_calibration_runs WHERE calibration_run_id=?",
            [calibration_run_id],
        ).fetchone()
        if row is None:
            raise CalibrationGateError("calibration run does not exist")
        report = json.loads(str(row[0]))
        class_reports = report.get("asset_classes", {})
        if not report.get("three_year_span"):
            raise CalibrationGateError("calibration window is shorter than three years")
        if not report.get("global_alert_budget", {}).get("alert_budget_pass"):
            raise CalibrationGateError("combined alert budget did not pass")
        if not class_reports or not all(
            bool(item.get("alert_budget_pass")) and bool(item.get("three_year_coverage_ready"))
            for item in class_reports.values()
        ):
            raise CalibrationGateError("asset-class coverage or alert budget did not pass")
        self.connection.execute(
            """
            UPDATE control.alert_calibration_runs
            SET run_status='review_ready',owner_review_hash=?,owner_reviewed_at=?
            WHERE calibration_run_id=? AND run_status IN ('draft','review_ready')
            """,
            [owner_review_hash, reviewed_at, calibration_run_id],
        )

    def build_shadow_evidence(
        self,
        *,
        rule_set_id: str,
        rule_set_version: str,
        window_start: date,
        window_end: date,
        expected_session_keys: Iterable[str],
        owner_review_complete: bool,
        sensitive_violation_count: int = 0,
    ) -> ShadowEvidence:
        if window_end < window_start:
            raise ValueError("shadow window end precedes start")
        expected = tuple(sorted(set(expected_session_keys)))
        rows = self.connection.execute(
            """
            SELECT c.candidate_id,c.evaluation_date,c.evaluation_slot,c.quality_status,o.outcome_type
            FROM gold.alert_candidates c
            LEFT JOIN control.alert_candidate_outcomes o USING(candidate_id)
            WHERE c.rule_id=? AND c.rule_version=?
              AND c.evaluation_date BETWEEN ? AND ?
            ORDER BY c.evaluation_date,c.evaluation_slot,c.candidate_id
            """,
            [rule_set_id, rule_set_version, window_start, window_end],
        ).fetchall()
        # Coverage is the Korean evaluation opportunity. A morning U.S. close
        # can cite an earlier U.S. session, so its price session key is not the
        # scheduled coverage identity.
        observed = tuple(sorted({f"evaluation:{row[1].isoformat()}|{row[2]}" for row in rows}))
        duplicate_count = sum(row[4] == "no_change" for row in rows)
        quality_count = sum(row[4] == "suppressed_quality" for row in rows)
        external_send_count = int(self.connection.execute(
            """
            SELECT count(*)
            FROM control.alert_delivery_attempts a
            JOIN control.alert_dispatch_claims d USING(dispatch_id)
            JOIN gold.alert_candidates c USING(candidate_id)
            WHERE d.channel='telegram' AND c.rule_id=? AND c.rule_version=?
              AND c.evaluation_date BETWEEN ? AND ?
            """,
            [rule_set_id, rule_set_version, window_start, window_end],
        ).fetchone()[0])
        missing = sorted(set(expected) - set(observed))
        unexpected = sorted(set(observed) - set(expected))
        summary: dict[str, object] = {
            "summary_version": 2,
            "coverage_key_version": "evaluation-date-slot-v1",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "elapsed_days": (window_end - window_start).days + 1,
            "expected_session_count": len(expected),
            "observed_session_count": len(observed),
            "missing_session_keys": missing,
            "unexpected_session_keys": unexpected,
            "candidate_count": len(rows),
            "duplicate_suppressed_count": duplicate_count,
            "quality_suppressed_count": quality_count,
            "sensitive_violation_count": sensitive_violation_count,
            "external_send_count": external_send_count,
            "owner_review_complete": owner_review_complete,
        }
        summary_hash = hashlib.sha256(_json(summary).encode()).hexdigest()
        window_id = _hash(
            "alert-shadow-window-v1", rule_set_id, rule_set_version, window_start, window_end
        )
        return ShadowEvidence(
            window_id, rule_set_id, rule_set_version, window_start, window_end,
            expected, observed, len(rows), duplicate_count, quality_count,
            sensitive_violation_count, external_send_count, owner_review_complete,
            summary, summary_hash,
        )

    def write_shadow_evidence(self, evidence: ShadowEvidence, *, updated_at: datetime) -> str:
        _aware(updated_at, "updated_at")
        status = "review_ready" if evidence.objectively_verifiable else "collecting"
        self.connection.execute(
            """
            INSERT INTO control.alert_shadow_windows(
                shadow_window_id,rule_set_id,rule_set_version,window_start,window_end,
                window_status,expected_session_count,observed_session_count,candidate_count,
                duplicate_suppressed_count,quality_suppressed_count,sensitive_violation_count,
                external_send_count,owner_review_complete,summary_hash,summary,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(shadow_window_id) DO UPDATE SET
                window_status=excluded.window_status,
                expected_session_count=excluded.expected_session_count,
                observed_session_count=excluded.observed_session_count,
                candidate_count=excluded.candidate_count,
                duplicate_suppressed_count=excluded.duplicate_suppressed_count,
                quality_suppressed_count=excluded.quality_suppressed_count,
                sensitive_violation_count=excluded.sensitive_violation_count,
                external_send_count=excluded.external_send_count,
                owner_review_complete=excluded.owner_review_complete,
                summary_hash=excluded.summary_hash,summary=excluded.summary,
                updated_at=excluded.updated_at
            """,
            [
                evidence.shadow_window_id, evidence.rule_set_id, evidence.rule_set_version,
                evidence.window_start, evidence.window_end, status,
                len(evidence.expected_session_keys), len(evidence.observed_session_keys),
                evidence.candidate_count, evidence.duplicate_suppressed_count,
                evidence.quality_suppressed_count, evidence.sensitive_violation_count,
                evidence.external_send_count, evidence.owner_review_complete,
                evidence.summary_hash, _json(dict(evidence.summary)), updated_at,
            ],
        )
        return status

    def verify_shadow(self, *, shadow_window_id: str, actor_type: str, verified_at: datetime) -> None:
        _aware(verified_at, "verified_at")
        if actor_type != "owner":
            raise CalibrationGateError("only owner may verify shadow evidence")
        row = self.connection.execute(
            """
            SELECT window_start,window_end,expected_session_count,observed_session_count,
                   sensitive_violation_count,external_send_count,owner_review_complete,summary
            FROM control.alert_shadow_windows WHERE shadow_window_id=?
            """,
            [shadow_window_id],
        ).fetchone()
        if row is None:
            raise CalibrationGateError("shadow window does not exist")
        elapsed = (row[1] - row[0]).days + 1
        summary = json.loads(str(row[7]))
        if not (
            elapsed >= 14 and row[2] == row[3] and row[4] == 0 and row[5] == 0 and bool(row[6])
            and not summary.get("missing_session_keys")
            and not summary.get("unexpected_session_keys")
        ):
            raise CalibrationGateError("shadow window has not passed elapsed coverage and zero-send gates")
        self.connection.execute(
            "UPDATE control.alert_shadow_windows SET window_status='verified',updated_at=? WHERE shadow_window_id=?",
            [verified_at, shadow_window_id],
        )

    def append_owner_decision(
        self,
        *,
        rule_id: str,
        rule_version: str,
        decision: str,
        actor_type: str,
        calibration_run_id: str | None,
        shadow_window_id: str | None,
        evidence_hash: str,
        rationale_code: str,
        decided_at: datetime,
        expected_prior_revision: int,
    ) -> str:
        _aware(decided_at, "decided_at")
        if actor_type != "owner":
            raise CalibrationGateError("only owner may decide an alert rule version")
        if decision not in {"approved", "rejected", "revoked"}:
            raise ValueError("unknown owner rule decision")
        if len(evidence_hash) != 64:
            raise CalibrationGateError("owner decision requires a SHA-256 evidence hash")
        latest = self.connection.execute(
            """
            SELECT coalesce(max(revision),0) FROM control.alert_rule_approval_revisions
            WHERE rule_id=? AND rule_version=?
            """,
            [rule_id, rule_version],
        ).fetchone()[0]
        if int(latest) != expected_prior_revision:
            raise CalibrationGateError("owner rule decision revision changed")
        if decision == "approved":
            calibration = self.connection.execute(
                "SELECT run_status FROM control.alert_calibration_runs WHERE calibration_run_id=?",
                [calibration_run_id],
            ).fetchone()
            shadow = self.connection.execute(
                "SELECT window_status FROM control.alert_shadow_windows WHERE shadow_window_id=?",
                [shadow_window_id],
            ).fetchone()
            if calibration is None or calibration[0] != "review_ready":
                raise CalibrationGateError("approved rule requires owner-reviewed calibration")
            if shadow is None or shadow[0] != "verified":
                raise CalibrationGateError("approved rule requires verified two-week shadow")
        revision = expected_prior_revision + 1
        revision_id = _hash(
            "alert-rule-owner-decision-v1", rule_id, rule_version, revision,
            decision, evidence_hash,
        )
        self.connection.execute(
            """
            INSERT INTO control.alert_rule_approval_revisions(
                approval_revision_id,rule_id,rule_version,revision,decision,actor_type,
                calibration_run_id,shadow_window_id,evidence_hash,rationale_code,decided_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                revision_id, rule_id, rule_version, revision, decision, actor_type,
                calibration_run_id, shadow_window_id, evidence_hash, rationale_code, decided_at,
            ],
        )
        if decision == "approved" and calibration_run_id is not None:
            self.connection.execute(
                "UPDATE control.alert_calibration_runs SET run_status='approved' WHERE calibration_run_id=?",
                [calibration_run_id],
            )
        return revision_id

    def append_owner_canary_approval(
        self,
        *,
        rule_id: str,
        rule_version: str,
        actor_type: str,
        calibration_run_id: str,
        shadow_window_id: str,
        evidence_hash: str,
        decided_at: datetime,
        expected_prior_revision: int,
        rationale_code: str = "OWNER_APPROVED_BOUNDED_CANARY",
    ) -> str:
        """Approve an exact owner-authorized bounded external exception."""
        _aware(decided_at, "decided_at")
        if actor_type != "owner":
            raise CalibrationGateError("only owner may approve a bounded canary")
        if len(evidence_hash) != 64:
            raise CalibrationGateError("canary approval requires a SHA-256 evidence hash")
        if rationale_code not in {
            "OWNER_APPROVED_BOUNDED_CANARY", "OWNER_APPROVED_PRODUCTION_VALUE_RC",
        }:
            raise CalibrationGateError("bounded external approval rationale is not allowlisted")
        rule = self.connection.execute(
            """
            SELECT contract_status,delivery_mode,minimum_delivery_rank,valid_from,valid_to
            FROM control.alert_rule_versions WHERE rule_id=? AND version=?
            """,
            [rule_id, rule_version],
        ).fetchone()
        if (
            rule is None
            or str(rule[0]) != "active"
            or str(rule[1]) != "external"
            or int(rule[2]) != 1
            or rule[4] is None
            or rule[4] - rule[3] > timedelta(days=7)
            or decided_at >= rule[4]
        ):
            raise CalibrationGateError("canary rule is not active, external, watch-floor and bounded")
        calibration = self.connection.execute(
            "SELECT run_status FROM control.alert_calibration_runs WHERE calibration_run_id=?",
            [calibration_run_id],
        ).fetchone()
        shadow = self.connection.execute(
            """
            SELECT window_status,observed_session_count,sensitive_violation_count,external_send_count
            FROM control.alert_shadow_windows WHERE shadow_window_id=?
            """,
            [shadow_window_id],
        ).fetchone()
        if calibration is None or str(calibration[0]) not in {"draft", "review_ready", "approved"}:
            raise CalibrationGateError("canary approval requires the governed replay evidence")
        if (
            shadow is None
            or str(shadow[0]) not in {"collecting", "review_ready", "verified"}
            or int(shadow[1]) <= 0
            or int(shadow[2]) != 0
            or int(shadow[3]) != 0
        ):
            raise CalibrationGateError("canary approval requires clean observed shadow evidence")
        latest = self.connection.execute(
            """
            SELECT coalesce(max(revision),0) FROM control.alert_rule_approval_revisions
            WHERE rule_id=? AND rule_version=?
            """,
            [rule_id, rule_version],
        ).fetchone()[0]
        if int(latest) != expected_prior_revision:
            raise CalibrationGateError("owner canary decision revision changed")
        revision = expected_prior_revision + 1
        revision_id = _hash(
            "alert-rule-owner-decision-v1", rule_id, rule_version, revision,
            "approved", evidence_hash,
        )
        self.connection.execute(
            """
            INSERT INTO control.alert_rule_approval_revisions(
                approval_revision_id,rule_id,rule_version,revision,decision,actor_type,
                calibration_run_id,shadow_window_id,evidence_hash,rationale_code,decided_at
            ) VALUES (?,?,?,?,?,'owner',?,?,?,?,?)
            """,
            [
                revision_id, rule_id, rule_version, revision, "approved",
                calibration_run_id, shadow_window_id, evidence_hash,
                rationale_code, decided_at,
            ],
        )
        return revision_id
