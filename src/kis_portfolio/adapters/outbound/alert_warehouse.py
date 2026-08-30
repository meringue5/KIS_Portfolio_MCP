"""Persistence for immutable alert candidates, state and transport-neutral delivery claims."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb

from kis_portfolio.modules.monitoring.alerts import (
    AlertCandidate,
    AlertRuleVersion,
    AlertTransition,
    CurrentAlertState,
    decide_alert_transition,
    validate_opaque_code,
)


_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


class AlertWarehouseConflictError(RuntimeError):
    """Raised when immutable alert history would be rewritten."""


class AlertClaimError(RuntimeError):
    """Raised for invalid or stale delivery-claim operations."""


@dataclass(frozen=True, slots=True)
class CandidateWrite:
    candidate_id: str
    inserted: bool


@dataclass(frozen=True, slots=True)
class StateWrite:
    transition: AlertTransition | None
    inserted: bool


@dataclass(frozen=True, slots=True)
class DispatchClaim:
    dispatch_id: str
    acquired: bool
    status: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class TelegramDispatchCandidate:
    candidate_id: str
    rule_id: str
    rule_version: str
    evaluation_slot: str
    session_key: str
    evaluation_at: datetime
    delivery_severity: str
    transition_type: str
    public_context: dict[str, object]


class AlertWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def register_rule(self, rule: AlertRuleVersion) -> None:
        prior = self.connection.execute(
            "SELECT definition_hash FROM control.alert_rule_versions WHERE rule_id=? AND version=?",
            [rule.rule_id, rule.version],
        ).fetchone()
        if prior is not None and str(prior[0]) != rule.definition_hash:
            raise AlertWarehouseConflictError("alert rule version changed in place")
        document = {
            **dict(rule.document),
            "valid_from": rule.valid_from.isoformat(),
            "valid_to": rule.valid_to.isoformat() if rule.valid_to is not None else None,
        }
        self.connection.execute(
            """
            INSERT INTO control.alert_rule_versions(
                rule_id,version,contract_status,definition_hash,minimum_delivery_severity,
                delivery_mode,valid_from,valid_to,definition,minimum_delivery_rank
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(rule_id,version) DO NOTHING
            """,
            [
                rule.rule_id, rule.version, rule.status, rule.definition_hash,
                "warning" if rule.minimum_delivery_severity == "watch" else rule.minimum_delivery_severity,
                rule.delivery_mode, rule.valid_from, rule.valid_to, _json(document),
                {"watch": 1, "warning": 2, "critical": 3}[rule.minimum_delivery_severity],
            ],
        )

    @staticmethod
    def _candidate_document(candidate: AlertCandidate) -> tuple[object, ...]:
        item = candidate.evaluation
        return (
            candidate.alert_identity, candidate.rule.rule_id, candidate.rule.version,
            item.subject_type, item.subject_id, item.evaluation_date, item.evaluation_slot,
            item.session_key, item.evaluation_at, item.signal_state, item.severity,
            candidate.state_fingerprint, item.quality_status, item.input_lineage_hash,
            _json(dict(item.public_context)), item.evaluation_run_id,
        )

    def write_candidate(self, candidate: AlertCandidate) -> CandidateWrite:
        self.register_rule(candidate.rule)
        prior = self.connection.execute(
            """
            SELECT alert_identity,rule_id,rule_version,subject_type,subject_id,evaluation_date,
                   evaluation_slot,session_key,evaluation_at,signal_state,severity,state_fingerprint,
                   quality_status,input_lineage_hash,public_context,evaluation_run_id
            FROM gold.alert_candidates WHERE candidate_id=?
            """,
            [candidate.candidate_id],
        ).fetchone()
        expected = self._candidate_document(candidate)
        if prior is not None:
            normalized = (*prior[:14], str(prior[14]), prior[15])
            if normalized != expected:
                raise AlertWarehouseConflictError("alert candidate changed on replay")
            return CandidateWrite(candidate.candidate_id, False)
        try:
            self.connection.execute(
                """
                INSERT INTO gold.alert_candidates(
                    candidate_id,alert_identity,rule_id,rule_version,subject_type,subject_id,
                    evaluation_date,evaluation_slot,session_key,evaluation_at,signal_state,severity,
                    state_fingerprint,quality_status,input_lineage_hash,public_context,evaluation_run_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [candidate.candidate_id, *expected],
            )
        except duckdb.ConstraintException as exc:
            raise AlertWarehouseConflictError("alert logical evaluation key already has another candidate") from exc
        return CandidateWrite(candidate.candidate_id, True)

    def current_state(self, alert_identity: str) -> CurrentAlertState | None:
        row = self.connection.execute(
            """
            SELECT revision,episode,current_state,current_severity,state_fingerprint,knowledge_at
            FROM control.alert_states_current WHERE alert_identity=?
            """,
            [alert_identity],
        ).fetchone()
        if row is None:
            return None
        return CurrentAlertState(
            int(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4]), row[5]
        )

    def apply_candidate(self, candidate: AlertCandidate) -> StateWrite:
        self.write_candidate(candidate)
        processed = self.connection.execute(
            "SELECT outcome_type FROM control.alert_candidate_outcomes WHERE candidate_id=?",
            [candidate.candidate_id],
        ).fetchone()
        if processed is not None:
            return StateWrite(None, False)
        current = self.current_state(candidate.alert_identity)
        if (
            current is not None
            and current.knowledge_at is not None
            and candidate.evaluation.evaluation_at <= current.knowledge_at
        ):
            self.connection.execute(
                """
                INSERT INTO control.alert_candidate_outcomes(
                    candidate_id,outcome_type,state_revision_id,evaluated_against_revision,processed_at
                ) VALUES (?,'out_of_order',NULL,?,?)
                """,
                [candidate.candidate_id, current.revision, candidate.evaluation.evaluation_at],
            )
            return StateWrite(None, False)
        transition = decide_alert_transition(candidate, current)
        if transition is None:
            outcome = (
                "suppressed_quality"
                if candidate.evaluation.quality_status != "pass"
                else "no_change"
            )
            self.connection.execute(
                """
                INSERT INTO control.alert_candidate_outcomes(
                    candidate_id,outcome_type,state_revision_id,evaluated_against_revision,processed_at
                ) VALUES (?,?,NULL,?,?)
                """,
                [
                    candidate.candidate_id, outcome, 0 if current is None else current.revision,
                    candidate.evaluation.evaluation_at,
                ],
            )
            return StateWrite(None, False)
        revision_id = _hash(
            "alert-state-revision-v1", candidate.alert_identity, transition.revision,
            candidate.candidate_id, transition.transition_type,
        )
        actual = self.current_state(candidate.alert_identity)
        actual_revision = 0 if actual is None else actual.revision
        expected_revision = transition.revision - 1
        if actual_revision != expected_revision:
            raise AlertWarehouseConflictError(
                f"alert state revision changed: expected={expected_revision} actual={actual_revision}"
            )
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """
                INSERT INTO control.alert_state_revisions(
                    state_revision_id,alert_identity,revision,episode,transition_type,prior_state,
                    current_state,prior_severity,current_severity,state_fingerprint,candidate_id,
                    delivery_required,delivery_severity,knowledge_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    revision_id, candidate.alert_identity, transition.revision, transition.episode,
                    transition.transition_type, transition.prior_state, transition.current_state,
                    transition.prior_severity, transition.current_severity,
                    candidate.state_fingerprint, candidate.candidate_id,
                    transition.delivery_required, transition.delivery_severity,
                    candidate.evaluation.evaluation_at,
                ],
            )
            self.connection.execute(
                """
                INSERT INTO control.alert_candidate_outcomes(
                    candidate_id,outcome_type,state_revision_id,evaluated_against_revision,processed_at
                ) VALUES (?,'transition',?,?,?)
                """,
                [candidate.candidate_id, revision_id, expected_revision, candidate.evaluation.evaluation_at],
            )
            self.connection.execute("COMMIT")
        except duckdb.ConstraintException as exc:
            self.connection.execute("ROLLBACK")
            raise AlertWarehouseConflictError("concurrent alert state update lost optimistic claim") from exc
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return StateWrite(transition, True)

    def claim_dispatch(
        self,
        *,
        candidate_id: str,
        channel: str,
        destination_ref: str,
        claimant_id: str,
        lease_token: str,
        claimed_at: datetime,
        lease_seconds: int = 300,
    ) -> DispatchClaim:
        _aware(claimed_at, "claimed_at")
        validate_opaque_code(destination_ref, "destination_ref")
        validate_opaque_code(claimant_id, "claimant_id")
        if not lease_token or lease_seconds <= 0 or lease_seconds > 900:
            raise AlertClaimError("claim requires a token and a lease of at most 900 seconds")
        row = self.connection.execute(
            """
            SELECT r.delivery_mode,r.contract_status,s.delivery_required
            FROM gold.alert_candidates c
            JOIN control.alert_rule_versions r
              ON r.rule_id=c.rule_id AND r.version=c.rule_version
            JOIN control.alert_state_revisions s ON s.candidate_id=c.candidate_id
            WHERE c.candidate_id=?
            """,
            [candidate_id],
        ).fetchone()
        if row is None or not bool(row[2]):
            raise AlertClaimError("candidate is not eligible for delivery")
        delivery_mode = str(row[0])
        if channel not in {"shadow", "telegram"}:
            raise AlertClaimError("unsupported delivery channel")
        if channel == "telegram" and delivery_mode != "external":
            raise AlertClaimError("external delivery mode is not active")
        if channel == "telegram" and str(row[1]) != "active":
            raise AlertClaimError("external delivery rule is not active")
        if channel == "telegram":
            approval = self.connection.execute(
                """
                SELECT decision FROM control.alert_rule_approval_revisions
                WHERE rule_id=(SELECT rule_id FROM gold.alert_candidates WHERE candidate_id=?)
                  AND rule_version=(SELECT rule_version FROM gold.alert_candidates WHERE candidate_id=?)
                ORDER BY revision DESC,decided_at DESC,approval_revision_id DESC
                LIMIT 1
                """,
                [candidate_id, candidate_id],
            ).fetchone()
            if approval is None or str(approval[0]) != "approved":
                raise AlertClaimError("external delivery rule lacks current owner approval")
        if channel == "shadow" and delivery_mode == "off":
            raise AlertClaimError("shadow delivery mode is not active")
        dispatch_id = _hash("alert-dispatch-v1", candidate_id, channel, destination_ref)
        digest = hashlib.sha256(lease_token.encode()).hexdigest()
        expires_at = claimed_at + timedelta(seconds=lease_seconds)
        prior = self.connection.execute(
            """
            SELECT claim_status,lease_expires_at,attempt_count
            FROM control.alert_dispatch_claims WHERE dispatch_id=?
            """,
            [dispatch_id],
        ).fetchone()
        if prior is None:
            self.connection.execute(
                """
                INSERT INTO control.alert_dispatch_claims(
                    dispatch_id,candidate_id,channel,destination_ref,claim_status,claimant_id,
                    lease_token_digest,lease_expires_at,attempt_count,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,0,?)
                """,
                [
                    dispatch_id, candidate_id, channel, destination_ref, "claimed", claimant_id,
                    digest, expires_at, claimed_at,
                ],
            )
            return DispatchClaim(dispatch_id, True, "claimed", 0)
        status, prior_expiry, attempts = str(prior[0]), prior[1], int(prior[2])
        retryable = status == "retryable" or (
            channel != "telegram" and status == "claimed" and prior_expiry <= claimed_at
        )
        if not retryable:
            return DispatchClaim(dispatch_id, False, status, attempts)
        updated = self.connection.execute(
            """
            UPDATE control.alert_dispatch_claims
            SET claim_status='claimed',claimant_id=?,lease_token_digest=?,lease_expires_at=?,
                last_error_code=NULL,updated_at=?
            WHERE dispatch_id=? AND (
                claim_status='retryable' OR (claim_status='claimed' AND lease_expires_at<=?)
            )
            RETURNING attempt_count
            """,
            [claimant_id, digest, expires_at, claimed_at, dispatch_id, claimed_at],
        ).fetchone()
        return DispatchClaim(dispatch_id, updated is not None, "claimed" if updated else status, attempts)

    def eligible_telegram_dispatches(
        self,
        *,
        as_of: datetime,
        limit: int = 20,
    ) -> tuple[TelegramDispatchCandidate, ...]:
        """Return bounded owner-approved external candidates without destination data."""
        _aware(as_of, "as_of")
        if limit <= 0 or limit > 100:
            raise ValueError("telegram dispatch limit must be between 1 and 100")
        self.connection.execute(
            """
            UPDATE control.alert_dispatch_claims
            SET claim_status='unknown',last_error_code='CLAIM_EXPIRED_UNKNOWN',updated_at=?
            WHERE channel='telegram' AND claim_status='claimed' AND lease_expires_at<=?
            """,
            [as_of, as_of],
        )
        rows = self.connection.execute(
            """
            WITH latest_owner_decision AS (
                SELECT rule_id,rule_version,decision
                FROM control.alert_rule_approval_revisions
                QUALIFY row_number() OVER (
                    PARTITION BY rule_id,rule_version
                    ORDER BY revision DESC,decided_at DESC,approval_revision_id DESC
                ) = 1
            )
            SELECT c.candidate_id,c.rule_id,c.rule_version,c.evaluation_slot,c.session_key,
                   c.evaluation_at,s.delivery_severity,s.transition_type,c.public_context
            FROM gold.alert_candidates c
            JOIN control.alert_rule_versions r
              ON r.rule_id=c.rule_id AND r.version=c.rule_version
            JOIN control.alert_state_revisions s ON s.candidate_id=c.candidate_id
            JOIN latest_owner_decision a
              ON a.rule_id=c.rule_id AND a.rule_version=c.rule_version
            LEFT JOIN control.alert_dispatch_claims d
              ON d.candidate_id=c.candidate_id AND d.channel='telegram'
            WHERE r.contract_status='active'
              AND r.delivery_mode='external'
              AND a.decision='approved'
              AND s.delivery_required
              AND c.quality_status='pass'
              AND (
                  d.dispatch_id IS NULL OR d.claim_status='retryable'
              )
            ORDER BY c.evaluation_at,c.candidate_id
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return tuple(
            TelegramDispatchCandidate(
                candidate_id=str(row[0]),
                rule_id=str(row[1]),
                rule_version=str(row[2]),
                evaluation_slot=str(row[3]),
                session_key=str(row[4]),
                evaluation_at=row[5],
                delivery_severity=str(row[6]),
                transition_type=str(row[7]),
                public_context=json.loads(str(row[8])),
            )
            for row in rows
        )

    def record_attempt(
        self,
        *,
        dispatch_id: str,
        lease_token: str,
        outcome: str,
        started_at: datetime,
        completed_at: datetime,
        response_ref: str | None = None,
        error_code: str | None = None,
    ) -> str:
        _aware(started_at, "started_at")
        _aware(completed_at, "completed_at")
        if completed_at < started_at:
            raise AlertClaimError("delivery completion precedes start")
        statuses = {
            "sent": "completed",
            "retryable_failure": "retryable",
            "permanent_failure": "permanent_failure",
            "unknown": "unknown",
        }
        if outcome not in statuses:
            raise AlertClaimError("unknown delivery outcome")
        if error_code is not None and not _ERROR_CODE.fullmatch(error_code):
            raise AlertClaimError("delivery errors must use a bounded code")
        digest = hashlib.sha256(lease_token.encode()).hexdigest()
        claim = self.connection.execute(
            """
            SELECT claim_status,lease_token_digest,attempt_count
            FROM control.alert_dispatch_claims WHERE dispatch_id=?
            """,
            [dispatch_id],
        ).fetchone()
        if claim is None or str(claim[0]) != "claimed" or str(claim[1]) != digest:
            raise AlertClaimError("delivery claim is missing, terminal or owned by another lease")
        attempt_no = int(claim[2]) + 1
        attempt_id = _hash("alert-delivery-attempt-v1", dispatch_id, attempt_no)
        response_hash = hashlib.sha256(response_ref.encode()).hexdigest() if response_ref else None
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """
                INSERT INTO control.alert_delivery_attempts(
                    attempt_id,dispatch_id,attempt_no,outcome,started_at,completed_at,
                    response_ref_hash,error_code
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    attempt_id, dispatch_id, attempt_no, outcome, started_at, completed_at,
                    response_hash, error_code,
                ],
            )
            self.connection.execute(
                """
                UPDATE control.alert_dispatch_claims
                SET claim_status=?,attempt_count=?,last_error_code=?,updated_at=?
                WHERE dispatch_id=? AND claim_status='claimed' AND lease_token_digest=?
                """,
                [statuses[outcome], attempt_no, error_code, completed_at, dispatch_id, digest],
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return attempt_id
