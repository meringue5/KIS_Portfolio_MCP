"""Persistence for owner-authoritative thread plans and review revisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb

from kis_portfolio.modules.portfolio.thread_risk import (
    ReviewStatus,
    ReviewType,
    ThreadRiskPlanDraft,
    review_identity,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class OwnerIntentAuthorizationError(PermissionError):
    """Raised when a non-owner attempts to create authoritative intent."""


class OwnerIntentConcurrencyError(RuntimeError):
    """Raised when optimistic revision state changed before an owner write."""


@dataclass(frozen=True, slots=True)
class RiskPlanWrite:
    risk_plan_id: str
    risk_plan_revision_id: str
    revision: int
    inserted: bool


class ThreadRiskReviewWarehouse:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def append_risk_plan(
        self,
        draft: ThreadRiskPlanDraft,
        *,
        expected_prior_revision: int,
        actor_type: str,
    ) -> RiskPlanWrite:
        if actor_type != "owner":
            raise OwnerIntentAuthorizationError("only owner may author a thread risk plan")
        if expected_prior_revision < 0:
            raise ValueError("expected_prior_revision cannot be negative")
        thread = self.connection.execute(
            "SELECT thread_id FROM silver.trade_threads WHERE thread_id=?",
            [draft.thread_id],
        ).fetchone()
        if thread is None:
            raise ValueError("thread risk plan target does not exist")
        risk_plan_id = _hash("thread-risk-plan-v1", draft.thread_id)
        document = {
            "thread_id": draft.thread_id,
            "reference_price": str(draft.reference_price),
            "stop_price": str(draft.stop_price),
            "currency": draft.currency,
            "risk_budget_ratio": str(draft.risk_budget_ratio),
            "effective_at": draft.effective_at.isoformat(),
            "knowledge_at": draft.knowledge_at.isoformat(),
            "authority_source": draft.authority_source.value,
            "advice_metadata": dict(draft.advice_metadata),
            "provenance": dict(draft.provenance),
        }
        revision_hash = hashlib.sha256(_json(document).encode()).hexdigest()
        duplicate = self.connection.execute(
            """
            SELECT risk_plan_revision_id,revision
            FROM silver.trade_thread_risk_plan_revisions
            WHERE risk_plan_id=? AND revision_hash=?
            """,
            [risk_plan_id, revision_hash],
        ).fetchone()
        if duplicate:
            self._resolve_matching_plan_review(
                draft.thread_id, str(duplicate[0]), draft.knowledge_at
            )
            return RiskPlanWrite(risk_plan_id, str(duplicate[0]), int(duplicate[1]), False)
        latest = self.connection.execute(
            """
            SELECT revision,knowledge_at
            FROM silver.trade_thread_risk_plan_revisions
            WHERE risk_plan_id=? ORDER BY revision DESC LIMIT 1
            """,
            [risk_plan_id],
        ).fetchone()
        actual_prior = 0 if latest is None else int(latest[0])
        if actual_prior != expected_prior_revision:
            raise OwnerIntentConcurrencyError(
                f"thread risk plan revision changed: expected={expected_prior_revision} actual={actual_prior}"
            )
        if latest is not None and draft.knowledge_at <= latest[1]:
            raise ValueError("changed risk plan knowledge_at must advance")
        revision = actual_prior + 1
        revision_id = _hash("thread-risk-plan-revision-v1", risk_plan_id, revision_hash)
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """
                INSERT INTO silver.trade_thread_risk_plan_revisions(
                    risk_plan_revision_id,risk_plan_id,thread_id,revision,revision_hash,
                    reference_price,stop_price,currency,risk_budget_ratio,effective_at,
                    knowledge_at,authored_by,authority_source,expected_prior_revision,
                    advice_metadata,provenance
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    revision_id, risk_plan_id, draft.thread_id, revision, revision_hash,
                    draft.reference_price, draft.stop_price, draft.currency,
                    draft.risk_budget_ratio, draft.effective_at, draft.knowledge_at,
                    "owner", draft.authority_source.value, expected_prior_revision,
                    _json(dict(draft.advice_metadata)), _json(dict(draft.provenance)),
                ],
            )
            self._resolve_matching_plan_review(
                draft.thread_id, revision_id, draft.knowledge_at
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return RiskPlanWrite(risk_plan_id, revision_id, revision, True)

    def risk_plan_as_of(
        self,
        *,
        thread_id: str,
        evaluation_at: datetime,
    ) -> dict[str, Any] | None:
        _aware(evaluation_at, "evaluation_at")
        cursor = self.connection.execute(
            """
            SELECT risk_plan_revision_id,risk_plan_id,thread_id,revision,reference_price,
                   stop_price,currency,risk_budget_ratio,effective_at,knowledge_at,
                   authored_by,authority_source,advice_metadata,provenance
            FROM silver.trade_thread_risk_plan_revisions
            WHERE thread_id=? AND effective_at<=? AND knowledge_at<=?
            ORDER BY knowledge_at DESC,revision DESC,risk_plan_revision_id DESC LIMIT 1
            """,
            [thread_id, evaluation_at, evaluation_at],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row, strict=True))

    def discover_review_items(self, *, knowledge_at: datetime) -> tuple[str, ...]:
        """Open stable missing-intent reviews without creating owner answers."""
        _aware(knowledge_at, "knowledge_at")
        candidates: list[tuple[ReviewType, str, str]] = []
        threads = self.connection.execute(
            "SELECT thread_id FROM silver.trade_threads WHERE status='open' ORDER BY thread_id"
        ).fetchall()
        for (thread_id,) in threads:
            plan = self.risk_plan_as_of(thread_id=str(thread_id), evaluation_at=knowledge_at)
            if plan is None:
                candidates.append((ReviewType.MISSING_THREAD_RISK_PLAN, "trade_thread", str(thread_id)))
            journal = self.connection.execute(
                """
                SELECT 1 FROM silver.trade_journal_revisions
                WHERE thread_id=? AND authored_at<=? LIMIT 1
                """,
                [thread_id, knowledge_at],
            ).fetchone()
            if journal is None:
                candidates.append((ReviewType.MISSING_TRADE_JOURNAL, "trade_thread", str(thread_id)))
        allocations = self.connection.execute(
            """
            WITH selected AS (
                SELECT allocation_id,allocation_method,allocation_status
                FROM silver.sell_allocation_sets
                WHERE knowledge_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY allocation_id
                    ORDER BY knowledge_at DESC,revision DESC,revision_hash DESC
                )=1
            )
            SELECT allocation_id,allocation_method,allocation_status
            FROM selected ORDER BY allocation_id
            """,
            [knowledge_at],
        ).fetchall()
        for allocation_id, method, status in allocations:
            review_type = (
                ReviewType.UNRESOLVED_SELL_ALLOCATION
                if status == "reconciliation_exception"
                else ReviewType.SELL_ALLOCATION_CONFIRMATION
                if method == "inferred_fifo"
                else None
            )
            if review_type is not None:
                candidates.append((review_type, "sell_allocation", str(allocation_id)))

        opened: list[str] = []
        self.connection.execute("BEGIN TRANSACTION")
        try:
            for review_type, subject_type, subject_id in candidates:
                review_id, inserted = self._ensure_open_review(
                    review_type=review_type,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    knowledge_at=knowledge_at,
                )
                if inserted:
                    opened.append(review_id)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return tuple(opened)

    def resolve_review_item(
        self,
        review_item_id: str,
        *,
        status: ReviewStatus,
        resolution_ref: str,
        knowledge_at: datetime,
        expected_prior_revision: int,
        actor_type: str,
        provenance: dict[str, Any] | None = None,
    ) -> int:
        if actor_type != "owner":
            raise OwnerIntentAuthorizationError("only owner may answer or dismiss a review item")
        if status is ReviewStatus.OPEN:
            raise ValueError("owner resolution status must be answered or dismissed")
        if not resolution_ref.strip():
            raise ValueError("resolution_ref is required")
        _aware(knowledge_at, "knowledge_at")
        return self._append_review_revision(
            review_item_id,
            status=status,
            resolution_ref=resolution_ref,
            knowledge_at=knowledge_at,
            expected_prior_revision=expected_prior_revision,
            actor_type="owner",
            provenance=provenance or {},
        )

    def reviews_as_of(
        self,
        *,
        evaluation_at: datetime,
        status: ReviewStatus | None = None,
    ) -> list[dict[str, Any]]:
        _aware(evaluation_at, "evaluation_at")
        params: list[object] = [evaluation_at]
        status_clause = ""
        if status is not None:
            status_clause = "WHERE review_status=?"
            params.append(status.value)
        cursor = self.connection.execute(
            f"""
            WITH selected AS (
                SELECT items.review_item_id,items.review_type,items.subject_type,items.subject_id,
                       revisions.revision,revisions.review_status,revisions.reason_code,
                       revisions.question,revisions.knowledge_at,revisions.actor_type,
                       revisions.resolution_ref
                FROM control.owner_review_items items
                JOIN control.owner_review_item_revisions revisions USING(review_item_id)
                WHERE revisions.knowledge_at<=?
                QUALIFY row_number() OVER (
                    PARTITION BY items.review_item_id
                    ORDER BY revisions.knowledge_at DESC,revisions.revision DESC,
                             revisions.review_item_revision_id DESC
                )=1
            )
            SELECT * FROM selected {status_clause}
            ORDER BY review_type,review_item_id
            """,
            params,
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def _ensure_open_review(
        self,
        *,
        review_type: ReviewType,
        subject_type: str,
        subject_id: str,
        knowledge_at: datetime,
    ) -> tuple[str, bool]:
        review_item_id, identity_hash = review_identity(review_type, subject_type, subject_id)
        existing = self.connection.execute(
            "SELECT review_item_id FROM control.owner_review_items WHERE review_item_id=?",
            [review_item_id],
        ).fetchone()
        if existing:
            return review_item_id, False
        question = {
            ReviewType.MISSING_THREAD_RISK_PLAN: "이 매수 thread의 기준가격과 손절가격을 확인해주세요.",
            ReviewType.MISSING_TRADE_JOURNAL: "이 매수 thread의 투자 이유와 계획을 기록해주세요.",
            ReviewType.SELL_ALLOCATION_CONFIRMATION: "추론된 FIFO 매도 배분이 실제 의도와 맞는지 확인해주세요.",
            ReviewType.UNRESOLVED_SELL_ALLOCATION: "미해결 매도수량의 lot/thread 배분을 확인해주세요.",
        }[review_type]
        self.connection.execute(
            """
            INSERT INTO control.owner_review_items(
                review_item_id,review_type,subject_type,subject_id,identity_hash,
                first_seen_at,provenance
            ) VALUES (?,?,?,?,?,?,?)
            """,
            [review_item_id, review_type.value, subject_type, subject_id, identity_hash,
             knowledge_at, _json({"discovery": "wi024-contract-v1"})],
        )
        revision_id = _hash("owner-review-revision-v1", review_item_id, 1, ReviewStatus.OPEN.value)
        self.connection.execute(
            """
            INSERT INTO control.owner_review_item_revisions(
                review_item_revision_id,review_item_id,revision,review_status,reason_code,
                question,knowledge_at,actor_type,expected_prior_revision,resolution_ref,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,NULL,?)
            """,
            [revision_id, review_item_id, 1, ReviewStatus.OPEN.value, review_type.value,
             question, knowledge_at, "system", 0, _json({"source": "review-discovery"})],
        )
        return review_item_id, True

    def _resolve_matching_plan_review(
        self,
        thread_id: str,
        risk_plan_revision_id: str,
        knowledge_at: datetime,
    ) -> None:
        review_item_id, _identity_hash = review_identity(
            ReviewType.MISSING_THREAD_RISK_PLAN, "trade_thread", thread_id
        )
        latest = self.connection.execute(
            """
            SELECT revision,review_status,knowledge_at
            FROM control.owner_review_item_revisions
            WHERE review_item_id=? ORDER BY revision DESC LIMIT 1
            """,
            [review_item_id],
        ).fetchone()
        if latest is None or latest[1] != ReviewStatus.OPEN.value:
            return
        resolution_at = max(knowledge_at, latest[2])
        self._append_review_revision(
            review_item_id,
            status=ReviewStatus.ANSWERED,
            resolution_ref=f"silver.trade_thread_risk_plan_revisions:{risk_plan_revision_id}",
            knowledge_at=resolution_at,
            expected_prior_revision=int(latest[0]),
            actor_type="owner",
            provenance={"source": "owner-risk-plan-write"},
        )

    def _append_review_revision(
        self,
        review_item_id: str,
        *,
        status: ReviewStatus,
        resolution_ref: str,
        knowledge_at: datetime,
        expected_prior_revision: int,
        actor_type: str,
        provenance: dict[str, Any],
    ) -> int:
        latest = self.connection.execute(
            """
            SELECT revision,review_status,reason_code,question,knowledge_at
            FROM control.owner_review_item_revisions
            WHERE review_item_id=? ORDER BY revision DESC LIMIT 1
            """,
            [review_item_id],
        ).fetchone()
        if latest is None:
            raise ValueError("review item does not exist")
        actual_prior = int(latest[0])
        if actual_prior != expected_prior_revision:
            raise OwnerIntentConcurrencyError(
                f"review revision changed: expected={expected_prior_revision} actual={actual_prior}"
            )
        if knowledge_at < latest[4]:
            raise ValueError("review knowledge_at cannot move backwards")
        revision = actual_prior + 1
        revision_id = _hash(
            "owner-review-revision-v1", review_item_id, revision, status.value,
            resolution_ref, knowledge_at.isoformat(),
        )
        self.connection.execute(
            """
            INSERT INTO control.owner_review_item_revisions(
                review_item_revision_id,review_item_id,revision,review_status,reason_code,
                question,knowledge_at,actor_type,expected_prior_revision,resolution_ref,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, review_item_id, revision, status.value, latest[2], latest[3],
             knowledge_at, actor_type, expected_prior_revision, resolution_ref,
             _json(provenance)],
        )
        return revision


def inspect_thread_review_readiness(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, object]:
    """Return aggregate-only WI-024 runtime readiness without writes or identities."""
    target_objects = {
        ("silver", "trade_thread_risk_plan_revisions"),
        ("silver", "trade_thread_risk_plans_current"),
        ("control", "owner_review_items"),
        ("control", "owner_review_item_revisions"),
        ("control", "owner_review_items_current"),
    }
    existing = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT table_schema,table_name FROM information_schema.tables
            WHERE table_catalog=current_database()
              AND table_schema IN ('silver','control')
            """
        ).fetchall()
    }
    missing = sorted(f"{schema}.{name}" for schema, name in target_objects - existing)
    migration_applied = connection.execute(
        "SELECT count(*) FROM control.schema_migrations WHERE version='0011'"
    ).fetchone()[0]
    threads = connection.execute(
        "SELECT count(*),coalesce(count_if(status='open'),0) FROM silver.trade_threads"
    ).fetchone()
    journals = connection.execute(
        "SELECT count(*),count(DISTINCT thread_id) FILTER (WHERE thread_id IS NOT NULL) "
        "FROM silver.trade_journal_revisions"
    ).fetchone()
    allocations = connection.execute(
        """
        WITH selected AS (
            SELECT allocation_id,allocation_method,allocation_status
            FROM silver.sell_allocation_sets
            QUALIFY row_number() OVER (
                PARTITION BY allocation_id
                ORDER BY knowledge_at DESC,revision DESC,revision_hash DESC
            )=1
        )
        SELECT count(*),coalesce(count_if(allocation_method='inferred_fifo'),0),
               coalesce(count_if(allocation_status='reconciliation_exception'),0)
        FROM selected
        """
    ).fetchone()
    open_exceptions = connection.execute(
        "SELECT count(*) FROM control.reconstruction_exceptions_current "
        "WHERE exception_status='open'"
    ).fetchone()[0]
    plan_rows = 0
    review_rows = 0
    if not missing:
        plan_rows = connection.execute(
            "SELECT count(*) FROM silver.trade_thread_risk_plan_revisions"
        ).fetchone()[0]
        review_rows = connection.execute(
            "SELECT count(*) FROM control.owner_review_item_revisions"
        ).fetchone()[0]
    blockers: list[str] = []
    if not migration_applied:
        blockers.append("migration_0011_not_applied")
    if missing:
        blockers.append("thread_review_objects_missing")
    return {
        "status": "ready" if not blockers else "blocked",
        "runtime_ready": not blockers,
        "blockers": blockers,
        "target_objects": {
            "expected": len(target_objects),
            "present": len(target_objects) - len(missing),
            "missing_count": len(missing),
        },
        "threads": {"rows": int(threads[0]), "open": int(threads[1])},
        "journals": {"revisions": int(journals[0]), "thread_targets": int(journals[1])},
        "sell_allocations": {
            "current_sets": int(allocations[0]),
            "inferred_fifo": int(allocations[1]),
            "reconciliation_exception": int(allocations[2]),
        },
        "known_gaps": {"open_reconstruction_exceptions": int(open_exceptions)},
        "new_ledger_rows": {
            "risk_plan_revisions": int(plan_rows),
            "review_item_revisions": int(review_rows),
        },
        "side_effects": "none",
    }
