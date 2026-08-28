"""Append-only persistence boundary for deterministic position reconstruction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.portfolio.reconstruction import (
    AllocationStatus,
    EvidenceProvenance,
    ReconstructionStatus,
    reconstruction_partition_key,
)
from kis_portfolio.services.position_replay import (
    PositionReplayPlan,
    ReplayRequest,
    replay_projection_hash,
)


ZERO = Decimal("0")


class ReconstructionPersistenceError(RuntimeError):
    """Raised before commit when a plan cannot satisfy the ledger contract."""


@dataclass(frozen=True, slots=True)
class ReconstructionWriteResult:
    partition_key: str
    replay_hash: str
    outcome: str
    episode_identities_inserted: int = 0
    episode_revisions_inserted: int = 0
    lot_identities_inserted: int = 0
    lot_revisions_inserted: int = 0
    allocation_revisions_inserted: int = 0
    allocation_slices_inserted: int = 0
    exception_identities_inserted: int = 0
    exception_revisions_inserted: int = 0
    exceptions_resolved: int = 0

    @property
    def inserted_revision_count(self) -> int:
        return (
            self.episode_revisions_inserted
            + self.lot_revisions_inserted
            + self.allocation_revisions_inserted
            + self.exception_revisions_inserted
        )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(label: str, value: Any) -> str:
    return hashlib.sha256(f"{label}|{_json(value)}".encode()).hexdigest()


def _provenance(request: ReplayRequest, plan: PositionReplayPlan) -> dict[str, Any]:
    return {
        "pipeline_id": "pipeline.position-lot-reconstruction-v2",
        "pipeline_version": "1.0.0",
        "partition_key": plan.partition_key,
        "replay_hash": plan.replay_hash,
        "projection_hash": plan.projection_hash,
        "reconstruction_start_at": request.start_at.isoformat(),
        "reconstruction_cutoff_at": request.cutoff_at.isoformat(),
        "coverage_quality_result_id": plan.coverage_quality_result_id,
    }


class PositionReconstructionWarehouseRepository:
    """Publish one S03 plan atomically into the S02 append-only ledger."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def persist(
        self,
        *,
        request: ReplayRequest,
        plan: PositionReplayPlan,
        run_id: str,
        knowledge_at: datetime,
        created_by: str = "system",
    ) -> ReconstructionWriteResult:
        if not run_id.strip() or not created_by.strip():
            raise ReconstructionPersistenceError("run_id and created_by are required")
        if knowledge_at.tzinfo is None:
            raise ReconstructionPersistenceError("knowledge_at must be timezone-aware")
        if knowledge_at < request.cutoff_at:
            raise ReconstructionPersistenceError("knowledge_at cannot precede the reconstruction cutoff")
        self._validate_plan(request, plan)

        counts = {
            "episode_identities_inserted": 0,
            "episode_revisions_inserted": 0,
            "lot_identities_inserted": 0,
            "lot_revisions_inserted": 0,
            "allocation_revisions_inserted": 0,
            "allocation_slices_inserted": 0,
            "exception_identities_inserted": 0,
            "exception_revisions_inserted": 0,
            "exceptions_resolved": 0,
        }
        self.connection.execute("BEGIN TRANSACTION")
        try:
            if plan.assessment.eligible_for_reconciled_projection:
                self._persist_reconciled(
                    request=request,
                    plan=plan,
                    run_id=run_id,
                    knowledge_at=knowledge_at,
                    created_by=created_by,
                    counts=counts,
                )
                counts["exceptions_resolved"] = self._resolve_open_exceptions(
                    plan=plan,
                    run_id=run_id,
                    knowledge_at=knowledge_at,
                    counts=counts,
                )
                self._verify_current_projection(plan)
                outcome = "published" if sum(counts.values()) else "reused"
            else:
                self._persist_exception(
                    plan=plan,
                    run_id=run_id,
                    knowledge_at=knowledge_at,
                    counts=counts,
                )
                outcome = "exception_recorded" if sum(counts.values()) else "reused"
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return ReconstructionWriteResult(
            partition_key=plan.partition_key,
            replay_hash=plan.replay_hash,
            outcome=outcome,
            **counts,
        )

    def _validate_plan(self, request: ReplayRequest, plan: PositionReplayPlan) -> None:
        expected_partition = reconstruction_partition_key(
            request.account_id,
            request.target_instrument_id,
            request.start_at,
            request.cutoff_at,
        )
        if plan.partition_key != expected_partition:
            raise ReconstructionPersistenceError("plan partition does not match the request")
        if replay_projection_hash(plan) != plan.projection_hash:
            raise ReconstructionPersistenceError("plan projection hash does not match candidate facts")
        if plan.assessment.current_quantity != request.current_quantity:
            raise ReconstructionPersistenceError("plan current quantity does not match the request")
        if plan.side_effects != "none":
            raise ReconstructionPersistenceError("only a side-effect-free replay plan may be persisted")

        if not plan.assessment.eligible_for_reconciled_projection:
            if plan.episodes or plan.lots or plan.allocations:
                raise ReconstructionPersistenceError("a blocked plan cannot contain publishable facts")
            return
        if plan.assessment.status not in {
            ReconstructionStatus.RECONSTRUCTED,
            ReconstructionStatus.INFERRED_OPENING,
        }:
            raise ReconstructionPersistenceError("eligible plan has a non-publishable status")
        if plan.assessment.blockers:
            raise ReconstructionPersistenceError("eligible plan cannot carry blockers")

        episode_ids = [item.episode_id for item in plan.episodes]
        lot_ids = [item.lot_id for item in plan.lots]
        allocation_ids = [item.allocation_id for item in plan.allocations]
        if len(episode_ids) != len(set(episode_ids)):
            raise ReconstructionPersistenceError("duplicate episode identity in replay plan")
        if len(lot_ids) != len(set(lot_ids)):
            raise ReconstructionPersistenceError("duplicate lot identity in replay plan")
        if len(allocation_ids) != len(set(allocation_ids)):
            raise ReconstructionPersistenceError("duplicate allocation identity in replay plan")

        episodes = {item.episode_id: item for item in plan.episodes}
        lots = {item.lot_id: item for item in plan.lots}
        open_episodes = [item for item in plan.episodes if item.closed_at is None]
        if len(open_episodes) != (1 if request.current_quantity > ZERO else 0):
            raise ReconstructionPersistenceError("open episode count does not match current position")
        if open_episodes and open_episodes[0].instrument_id != request.target_instrument_id:
            raise ReconstructionPersistenceError("open episode does not match the target instrument")
        if sum((item.current_quantity for item in open_episodes), ZERO) != request.current_quantity:
            raise ReconstructionPersistenceError("open episode quantity does not match current position")

        for episode in plan.episodes:
            if episode.account_id != request.account_id:
                raise ReconstructionPersistenceError("episode crosses the account scope")
            episode_lots = [item for item in plan.lots if item.episode_id == episode.episode_id]
            if sum((item.remaining_quantity for item in episode_lots), ZERO) != episode.current_quantity:
                raise ReconstructionPersistenceError("episode and lot remaining quantities do not reconcile")
        for lot in plan.lots:
            episode = episodes.get(lot.episode_id)
            if episode is None or lot.account_id != request.account_id:
                raise ReconstructionPersistenceError("lot crosses the account or episode scope")
            if lot.effective_quantity <= ZERO or not ZERO <= lot.remaining_quantity <= lot.effective_quantity:
                raise ReconstructionPersistenceError("lot quantities violate the ledger contract")
            if lot.evidence_provenance is EvidenceProvenance.ACTUAL and not lot.opening_trade_event_id:
                raise ReconstructionPersistenceError("actual lot requires an opening trade")
            if (
                lot.evidence_provenance is EvidenceProvenance.INFERRED_OPENING
                and lot.effective_unit_cost is not None
            ):
                raise ReconstructionPersistenceError("inferred opening cannot have a fabricated cost")
            if lot.state_effective_at > request.cutoff_at:
                raise ReconstructionPersistenceError("lot state uses an event after the replay cutoff")

        sell_ids: set[str] = set()
        for allocation in plan.allocations:
            if allocation.sell_trade_event_id in sell_ids:
                raise ReconstructionPersistenceError("sell has more than one allocation candidate")
            sell_ids.add(allocation.sell_trade_event_id)
            if allocation.episode_id not in episodes:
                raise ReconstructionPersistenceError("allocation references an unknown episode")
            candidate = allocation.plan
            if (
                candidate.status is not AllocationStatus.COMPLETE
                or candidate.unallocated_quantity != ZERO
                or candidate.allocated_quantity != candidate.requested_quantity
            ):
                raise ReconstructionPersistenceError("only a complete sell allocation may publish")
            if sum((item.allocated_quantity for item in candidate.slices), ZERO) != candidate.allocated_quantity:
                raise ReconstructionPersistenceError("allocation slices do not reconcile with the header")
            for item in candidate.slices:
                lot = lots.get(item.lot_id)
                if lot is None or lot.episode_id != allocation.episode_id:
                    raise ReconstructionPersistenceError("allocation slice crosses the lot episode boundary")

    def _persist_reconciled(
        self,
        *,
        request: ReplayRequest,
        plan: PositionReplayPlan,
        run_id: str,
        knowledge_at: datetime,
        created_by: str,
        counts: dict[str, int],
    ) -> None:
        provenance = _provenance(request, plan)
        inferred_episode_ids = {
            lot.episode_id
            for lot in plan.lots
            if lot.evidence_provenance is EvidenceProvenance.INFERRED_OPENING
        }
        for episode in plan.episodes:
            identity_document = {
                "episode_id": episode.episode_id,
                "account_id": episode.account_id,
                "opening_instrument_id": episode.opening_instrument_id,
                "opened_at": episode.opened_at.isoformat(),
            }
            identity_hash = _hash("position-episode-identity", identity_document)
            if self._ensure_episode_identity(
                episode=episode,
                identity_hash=identity_hash,
                run_id=run_id,
            ):
                counts["episode_identities_inserted"] += 1
            revision_document = {
                "replay_hash": plan.replay_hash,
                "episode_id": episode.episode_id,
                "instrument_id": episode.instrument_id,
                "closed_at": episode.closed_at.isoformat() if episode.closed_at else None,
                "current_quantity": episode.current_quantity,
                "reconstruction_status": episode.reconstruction_status.value,
            }
            revision_id = _hash("position-episode-revision", revision_document)
            if self._insert_episode_revision(
                request=request,
                plan=plan,
                episode=episode,
                revision_id=revision_id,
                knowledge_at=knowledge_at,
                provenance=provenance,
                inferred=episode.episode_id in inferred_episode_ids,
            ):
                counts["episode_revisions_inserted"] += 1

        for lot in plan.lots:
            identity_document = {
                "lot_id": lot.lot_id,
                "episode_id": lot.episode_id,
                "account_id": lot.account_id,
                "opening_instrument_id": lot.opening_instrument_id,
                "opening_trade_event_id": lot.opening_trade_event_id,
                "opened_at": lot.opened_at.isoformat(),
                "evidence_provenance": lot.evidence_provenance.value,
            }
            identity_hash = _hash("purchase-lot-identity", identity_document)
            if self._ensure_lot_identity(lot=lot, identity_hash=identity_hash, run_id=run_id):
                counts["lot_identities_inserted"] += 1
            revision_document = {
                "replay_hash": plan.replay_hash,
                "lot_id": lot.lot_id,
                "effective_quantity": lot.effective_quantity,
                "remaining_quantity": lot.remaining_quantity,
                "effective_unit_cost": lot.effective_unit_cost,
                "currency": lot.currency,
                "state_effective_at": lot.state_effective_at.isoformat(),
                "cause_type": lot.cause_type,
                "cause_ref": lot.cause_ref,
                "reconstruction_status": next(
                    item.reconstruction_status.value
                    for item in plan.episodes
                    if item.episode_id == lot.episode_id
                ),
            }
            revision_hash = _hash("purchase-lot-revision-content", revision_document)
            if self._insert_lot_revision(
                lot=lot,
                revision_hash=revision_hash,
                reconstruction_status=revision_document["reconstruction_status"],
                knowledge_at=knowledge_at,
                provenance=provenance,
            ):
                counts["lot_revisions_inserted"] += 1

        for allocation in plan.allocations:
            candidate = allocation.plan
            revision_document = {
                "replay_hash": plan.replay_hash,
                "allocation_id": allocation.allocation_id,
                "sell_trade_event_id": allocation.sell_trade_event_id,
                "episode_id": allocation.episode_id,
                "instrument_id": allocation.instrument_id,
                "method": candidate.method.value,
                "requested_quantity": candidate.requested_quantity,
                "allocated_quantity": candidate.allocated_quantity,
                "unallocated_quantity": candidate.unallocated_quantity,
                "status": candidate.status.value,
                "slices": [
                    (item.lot_id, item.allocated_quantity)
                    for item in candidate.slices
                ],
            }
            revision_hash = _hash("sell-allocation-revision-content", revision_document)
            inserted, slice_count = self._insert_allocation_revision(
                request=request,
                allocation=allocation,
                revision_hash=revision_hash,
                knowledge_at=knowledge_at,
                created_by=created_by,
                provenance=provenance,
            )
            if inserted:
                counts["allocation_revisions_inserted"] += 1
                counts["allocation_slices_inserted"] += slice_count

    def _ensure_episode_identity(self, *, episode: Any, identity_hash: str, run_id: str) -> bool:
        existing = self.connection.execute(
            """
            SELECT account_id,opening_instrument_id,opened_at,identity_hash
            FROM silver.position_episodes WHERE episode_id=?
            """,
            [episode.episode_id],
        ).fetchone()
        expected = (episode.account_id, episode.opening_instrument_id, episode.opened_at, identity_hash)
        if existing:
            if existing != expected:
                raise ReconstructionPersistenceError("position episode identity is immutable")
            return False
        self.connection.execute(
            """
            INSERT INTO silver.position_episodes(
                episode_id,account_id,opening_instrument_id,opened_at,identity_hash,first_run_id
            ) VALUES (?,?,?,?,?,?)
            """,
            [episode.episode_id, episode.account_id, episode.opening_instrument_id,
             episode.opened_at, identity_hash, run_id],
        )
        return True

    def _insert_episode_revision(
        self,
        *,
        request: ReplayRequest,
        plan: PositionReplayPlan,
        episode: Any,
        revision_id: str,
        knowledge_at: datetime,
        provenance: dict[str, Any],
        inferred: bool,
    ) -> bool:
        if self.connection.execute(
            "SELECT 1 FROM silver.position_episode_revisions WHERE position_episode_revision_id=?",
            [revision_id],
        ).fetchone():
            return False
        revision = self._next_revision(
            table="silver.position_episode_revisions",
            identity_column="episode_id",
            identity=episode.episode_id,
            knowledge_at=knowledge_at,
        )
        self.connection.execute(
            """
            INSERT INTO silver.position_episode_revisions(
                position_episode_revision_id,episode_id,revision,instrument_id,episode_status,
                closed_at,reconstruction_start_at,reconstruction_cutoff_at,knowledge_at,
                current_quantity,replayed_quantity,inferred_opening_quantity,evidence_provenance,
                reconstruction_status,coverage_quality_result_id,blockers,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, episode.episode_id, revision, episode.instrument_id,
             "closed" if episode.closed_at else "open", episode.closed_at,
             request.start_at, request.cutoff_at, knowledge_at, episode.current_quantity,
             episode.current_quantity,
             plan.assessment.inferred_opening_quantity if inferred else None,
             EvidenceProvenance.INFERRED_OPENING.value if inferred else EvidenceProvenance.ACTUAL.value,
             episode.reconstruction_status.value, plan.coverage_quality_result_id, "[]",
             _json(provenance)],
        )
        return True

    def _ensure_lot_identity(self, *, lot: Any, identity_hash: str, run_id: str) -> bool:
        existing = self.connection.execute(
            """
            SELECT episode_id,account_id,opening_instrument_id,opening_trade_event_id,
                   opened_at,evidence_provenance,identity_hash
            FROM silver.purchase_lot_identities WHERE lot_id=?
            """,
            [lot.lot_id],
        ).fetchone()
        expected = (
            lot.episode_id, lot.account_id, lot.opening_instrument_id, lot.opening_trade_event_id,
            lot.opened_at, lot.evidence_provenance.value, identity_hash,
        )
        if existing:
            if existing != expected:
                raise ReconstructionPersistenceError("purchase lot identity is immutable")
            return False
        self.connection.execute(
            """
            INSERT INTO silver.purchase_lot_identities(
                lot_id,episode_id,account_id,opening_instrument_id,opening_trade_event_id,
                opened_at,evidence_provenance,identity_hash,first_run_id
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            [lot.lot_id, lot.episode_id, lot.account_id, lot.opening_instrument_id,
             lot.opening_trade_event_id, lot.opened_at, lot.evidence_provenance.value,
             identity_hash, run_id],
        )
        return True

    def _insert_lot_revision(
        self,
        *,
        lot: Any,
        revision_hash: str,
        reconstruction_status: str,
        knowledge_at: datetime,
        provenance: dict[str, Any],
    ) -> bool:
        if self.connection.execute(
            "SELECT 1 FROM silver.purchase_lot_revisions WHERE lot_id=? AND revision_hash=?",
            [lot.lot_id, revision_hash],
        ).fetchone():
            return False
        revision = self._next_revision(
            table="silver.purchase_lot_revisions",
            identity_column="lot_id",
            identity=lot.lot_id,
            knowledge_at=knowledge_at,
        )
        revision_id = _hash("purchase-lot-revision", {"lot_id": lot.lot_id, "hash": revision_hash})
        self.connection.execute(
            """
            INSERT INTO silver.purchase_lot_revisions(
                purchase_lot_revision_id,lot_id,revision,revision_hash,effective_quantity,
                remaining_quantity,effective_unit_cost,currency,reconstruction_status,
                effective_at,knowledge_at,cause_type,cause_ref,quality_status,blockers,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, lot.lot_id, revision, revision_hash, lot.effective_quantity,
             lot.remaining_quantity, lot.effective_unit_cost, lot.currency, reconstruction_status,
             lot.state_effective_at, knowledge_at, lot.cause_type, lot.cause_ref, "pass", "[]",
             _json(provenance)],
        )
        return True

    def _insert_allocation_revision(
        self,
        *,
        request: ReplayRequest,
        allocation: Any,
        revision_hash: str,
        knowledge_at: datetime,
        created_by: str,
        provenance: dict[str, Any],
    ) -> tuple[bool, int]:
        if self.connection.execute(
            "SELECT 1 FROM silver.sell_allocation_sets WHERE allocation_id=? AND revision_hash=?",
            [allocation.allocation_id, revision_hash],
        ).fetchone():
            return False, 0
        revision = self._next_revision(
            table="silver.sell_allocation_sets",
            identity_column="allocation_id",
            identity=allocation.allocation_id,
            knowledge_at=knowledge_at,
        )
        candidate = allocation.plan
        self.connection.execute(
            """
            INSERT INTO silver.sell_allocation_sets(
                allocation_id,revision,revision_hash,sell_trade_event_id,account_id,instrument_id,
                episode_id,allocation_method,requested_quantity,allocated_quantity,
                unallocated_quantity,allocation_status,knowledge_at,created_by,reason,blockers,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [allocation.allocation_id, revision, revision_hash, allocation.sell_trade_event_id,
             request.account_id, allocation.instrument_id, allocation.episode_id,
             candidate.method.value, candidate.requested_quantity, candidate.allocated_quantity,
             candidate.unallocated_quantity, candidate.status.value, knowledge_at, created_by,
             "deterministic replay allocation", _json(candidate.blockers), _json(provenance)],
        )
        for item in candidate.slices:
            self.connection.execute(
                """
                INSERT INTO silver.sell_allocation_revisions(
                    allocation_id,revision,sell_trade_event_id,lot_id,allocated_quantity,
                    allocation_method,quality_status,created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                [allocation.allocation_id, revision, allocation.sell_trade_event_id,
                 item.lot_id, item.allocated_quantity, candidate.method.value, "pass", knowledge_at],
            )
        return True, len(candidate.slices)

    def _persist_exception(
        self,
        *,
        plan: PositionReplayPlan,
        run_id: str,
        knowledge_at: datetime,
        counts: dict[str, int],
    ) -> None:
        exception_type = self._exception_type(plan)
        identity_document = {
            "partition_key": plan.partition_key,
            "episode_id": None,
            "exception_type": exception_type,
        }
        identity_hash = _hash("reconstruction-exception-identity", identity_document)
        exception_id = _hash("reconstruction-exception", identity_document)
        existing = self.connection.execute(
            """
            SELECT partition_key,episode_id,exception_type,identity_hash
            FROM control.reconstruction_exceptions WHERE exception_id=?
            """,
            [exception_id],
        ).fetchone()
        expected = (plan.partition_key, None, exception_type, identity_hash)
        if existing:
            if existing != expected:
                raise ReconstructionPersistenceError("reconstruction exception identity is immutable")
        else:
            self.connection.execute(
                """
                INSERT INTO control.reconstruction_exceptions(
                    exception_id,partition_key,episode_id,exception_type,identity_hash,
                    first_run_id,first_seen_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                [exception_id, plan.partition_key, None, exception_type, identity_hash,
                 run_id, knowledge_at],
            )
            counts["exception_identities_inserted"] += 1
        reason = ";".join(plan.assessment.blockers) or plan.assessment.status.value
        evidence_refs = [plan.replay_hash]
        if plan.coverage_quality_result_id:
            evidence_refs.append(plan.coverage_quality_result_id)
        revision_document = {
            "exception_id": exception_id,
            "replay_hash": plan.replay_hash,
            "status": "open",
            "reason": reason,
            "evidence_refs": evidence_refs,
        }
        revision_id = _hash("reconstruction-exception-revision", revision_document)
        if self.connection.execute(
            """
            SELECT 1 FROM control.reconstruction_exception_revisions
            WHERE reconstruction_exception_revision_id=?
            """,
            [revision_id],
        ).fetchone():
            return
        revision = self._next_revision(
            table="control.reconstruction_exception_revisions",
            identity_column="exception_id",
            identity=exception_id,
            knowledge_at=knowledge_at,
        )
        self.connection.execute(
            """
            INSERT INTO control.reconstruction_exception_revisions(
                reconstruction_exception_revision_id,exception_id,revision,exception_status,
                reason,evidence_refs,knowledge_at,resolution_ref,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, exception_id, revision, "open", reason, _json(evidence_refs),
             knowledge_at, None, _json({"run_id": run_id, "replay_hash": plan.replay_hash})],
        )
        counts["exception_revisions_inserted"] += 1

    def _resolve_open_exceptions(
        self,
        *,
        plan: PositionReplayPlan,
        run_id: str,
        knowledge_at: datetime,
        counts: dict[str, int],
    ) -> int:
        rows = self.connection.execute(
            """
            SELECT exception_id,reason
            FROM control.reconstruction_exceptions_current
            WHERE partition_key=? AND exception_status='open'
            ORDER BY exception_id
            """,
            [plan.partition_key],
        ).fetchall()
        resolved = 0
        for exception_id, prior_reason in rows:
            revision_document = {
                "exception_id": exception_id,
                "replay_hash": plan.replay_hash,
                "status": "resolved",
            }
            revision_id = _hash("reconstruction-exception-revision", revision_document)
            if self.connection.execute(
                """
                SELECT 1 FROM control.reconstruction_exception_revisions
                WHERE reconstruction_exception_revision_id=?
                """,
                [revision_id],
            ).fetchone():
                continue
            revision = self._next_revision(
                table="control.reconstruction_exception_revisions",
                identity_column="exception_id",
                identity=exception_id,
                knowledge_at=knowledge_at,
            )
            self.connection.execute(
                """
                INSERT INTO control.reconstruction_exception_revisions(
                    reconstruction_exception_revision_id,exception_id,revision,exception_status,
                    reason,evidence_refs,knowledge_at,resolution_ref,provenance
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [revision_id, exception_id, revision, "resolved",
                 f"resolved by reconciled replay; prior={prior_reason}", _json([plan.replay_hash]),
                 knowledge_at, plan.replay_hash, _json({"run_id": run_id})],
            )
            counts["exception_revisions_inserted"] += 1
            resolved += 1
        return resolved

    def _next_revision(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        knowledge_at: datetime,
    ) -> int:
        allowed = {
            ("silver.position_episode_revisions", "episode_id"),
            ("silver.purchase_lot_revisions", "lot_id"),
            ("silver.sell_allocation_sets", "allocation_id"),
            ("control.reconstruction_exception_revisions", "exception_id"),
        }
        if (table, identity_column) not in allowed:
            raise ReconstructionPersistenceError("unmanaged revision target")
        latest = self.connection.execute(
            f"SELECT revision,knowledge_at FROM {table} "
            f"WHERE {identity_column}=? ORDER BY revision DESC LIMIT 1",
            [identity],
        ).fetchone()
        if latest is None:
            return 1
        if knowledge_at <= latest[1]:
            raise ReconstructionPersistenceError("changed reconstruction knowledge_at must advance")
        return int(latest[0]) + 1

    def _verify_current_projection(self, plan: PositionReplayPlan) -> None:
        for episode in plan.episodes:
            row = self.connection.execute(
                """
                SELECT instrument_id,closed_at,current_quantity,reconstruction_status
                FROM silver.position_episodes_current WHERE episode_id=?
                """,
                [episode.episode_id],
            ).fetchone()
            expected = (
                episode.instrument_id,
                episode.closed_at,
                episode.current_quantity,
                episode.reconstruction_status.value,
            )
            if row != expected:
                raise ReconstructionPersistenceError("persisted episode projection does not reconcile")
        for lot in plan.lots:
            row = self.connection.execute(
                """
                SELECT effective_quantity,remaining_quantity,effective_unit_cost,currency,cause_type,cause_ref
                FROM silver.purchase_lot_states_current WHERE lot_id=?
                """,
                [lot.lot_id],
            ).fetchone()
            expected = (
                lot.effective_quantity,
                lot.remaining_quantity,
                lot.effective_unit_cost,
                lot.currency,
                lot.cause_type,
                lot.cause_ref,
            )
            if row != expected:
                raise ReconstructionPersistenceError("persisted lot projection does not reconcile")
        for allocation in plan.allocations:
            rows = self.connection.execute(
                """
                SELECT requested_quantity,allocated_quantity,unallocated_quantity,
                       allocation_status,lot_id,lot_allocated_quantity
                FROM silver.sell_allocations_current
                WHERE allocation_id=? ORDER BY lot_id
                """,
                [allocation.allocation_id],
            ).fetchall()
            expected_slices = sorted(
                (item.lot_id, item.allocated_quantity) for item in allocation.plan.slices
            )
            if len(rows) != len(expected_slices):
                raise ReconstructionPersistenceError("persisted allocation slice count does not reconcile")
            for row, expected_slice in zip(rows, expected_slices, strict=True):
                expected = (
                    allocation.plan.requested_quantity,
                    allocation.plan.allocated_quantity,
                    allocation.plan.unallocated_quantity,
                    allocation.plan.status.value,
                    expected_slice[0],
                    expected_slice[1],
                )
                if row != expected:
                    raise ReconstructionPersistenceError("persisted allocation does not reconcile")

    @staticmethod
    def _exception_type(plan: PositionReplayPlan) -> str:
        if plan.assessment.status is ReconstructionStatus.NOT_ASSESSED:
            return "corporate_action_coverage"
        if plan.assessment.status is ReconstructionStatus.PROVISIONAL:
            return "source_gap"
        return plan.assessment.blockers[0] if plan.assessment.blockers else "reconciliation"
