"""Point-in-time corporate-action identity, revision and adjustment repository."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.market.corporate_actions import (
    CorporateActionRevision,
    validate_corporate_action,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _revision(payload: dict[str, Any]) -> CorporateActionRevision:
    return CorporateActionRevision(
        market=str(payload.get("market") or "").strip().upper(),
        action_type=str(payload.get("action_type") or "unknown").strip().lower(),
        action_status=str(payload.get("action_status") or "unknown").strip().lower(),
        source_instrument_id=str(payload.get("source_instrument_id") or "").strip(),
        result_instrument_id=str(payload.get("result_instrument_id") or "").strip() or None,
        effective_at=payload["effective_at"],
        knowledge_at=payload["knowledge_at"],
        record_date=_date(payload.get("record_date")),
        ex_date=_date(payload.get("ex_date")),
        listing_date=_date(payload.get("listing_date")),
        pre_action_units=_decimal(payload.get("pre_action_units")),
        post_action_units=_decimal(payload.get("post_action_units")),
        terms_status=str(payload.get("terms_status") or "unknown").strip().lower(),
        quality_status=str(payload.get("quality_status") or "unresolved").strip().lower(),
        provenance=dict(payload.get("provenance") or {}),
    )


def _content_document(value: CorporateActionRevision) -> dict[str, Any]:
    return {
        "market": value.market,
        "action_type": value.action_type,
        "action_status": value.action_status,
        "source_instrument_id": value.source_instrument_id,
        "result_instrument_id": value.result_instrument_id,
        "effective_at": value.effective_at.isoformat(),
        "record_date": value.record_date,
        "ex_date": value.ex_date,
        "listing_date": value.listing_date,
        "pre_action_units": value.pre_action_units,
        "post_action_units": value.post_action_units,
        "terms_status": value.terms_status,
        "quality_status": value.quality_status,
        "provenance": value.provenance or {},
    }


class CorporateActionWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_action(
        self,
        payload: dict[str, Any],
        source_observation_id: str,
    ) -> tuple[str, str]:
        observation = self.connection.execute(
            """
            SELECT dataset_id, source_id, source_record_id, fetched_at, pipeline_run_id
            FROM bronze.source_observations WHERE observation_id=?
            """,
            [source_observation_id],
        ).fetchone()
        if not observation or observation[0] != "dataset.corporate-action-event":
            raise ValueError("corporate action requires a governed corporate-action observation")
        _dataset_id, source_id, source_record_id, fetched_at, pipeline_run_id = observation
        value = _revision(payload | {"knowledge_at": payload.get("knowledge_at") or fetched_at})
        validate_corporate_action(value)
        action_id = hashlib.sha256(
            f"corporate-action|{source_id}|{source_record_id}".encode()
        ).hexdigest()
        existing_action = self.connection.execute(
            "SELECT market FROM silver.corporate_actions WHERE corporate_action_id=?",
            [action_id],
        ).fetchone()
        if existing_action and existing_action[0] != value.market:
            raise ValueError("corporate action source identity has immutable market")
        self.connection.execute(
            """
            INSERT INTO silver.corporate_actions(
                corporate_action_id,source_id,source_record_id,market,
                first_source_observation_id,first_known_at
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(corporate_action_id) DO NOTHING
            """,
            [action_id, source_id, source_record_id, value.market,
             source_observation_id, value.knowledge_at],
        )
        document = _content_document(value)
        revision_hash = hashlib.sha256(_json(document).encode()).hexdigest()
        duplicate = self.connection.execute(
            """
            SELECT corporate_action_revision_id
            FROM silver.corporate_action_revisions
            WHERE corporate_action_id=? AND revision_hash=?
            """,
            [action_id, revision_hash],
        ).fetchone()
        if duplicate:
            return action_id, duplicate[0]
        latest = self.connection.execute(
            """
            SELECT revision, knowledge_at
            FROM silver.corporate_action_revisions
            WHERE corporate_action_id=?
            ORDER BY knowledge_at DESC, revision DESC LIMIT 1
            """,
            [action_id],
        ).fetchone()
        if latest and value.knowledge_at <= latest[1]:
            raise ValueError("corporate action knowledge_at must advance for changed content")
        revision = 1 if latest is None else int(latest[0]) + 1
        revision_id = hashlib.sha256(
            f"corporate-action-revision|{action_id}|{revision_hash}".encode()
        ).hexdigest()
        self.connection.execute(
            """
            INSERT INTO silver.corporate_action_revisions(
                corporate_action_revision_id,corporate_action_id,revision,revision_hash,
                action_type,action_status,source_instrument_id,result_instrument_id,effective_at,
                record_date,ex_date,listing_date,pre_action_units,post_action_units,terms_status,
                knowledge_at,source_observation_id,quality_status,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [revision_id, action_id, revision, revision_hash, value.action_type,
             value.action_status, value.source_instrument_id, value.result_instrument_id,
             value.effective_at, value.record_date, value.ex_date, value.listing_date,
             value.pre_action_units, value.post_action_units, value.terms_status,
             value.knowledge_at, source_observation_id, value.quality_status,
             _json(value.provenance or {})],
        )
        self._record_safe_effects(revision_id, value, pipeline_run_id)
        return action_id, revision_id

    def _record_safe_effects(
        self,
        revision_id: str,
        value: CorporateActionRevision,
        pipeline_run_id: str | None,
    ) -> None:
        if value.action_status != "confirmed" or value.quality_status != "pass":
            return
        effects: list[tuple[str, str | None, Decimal | None, Decimal | None]] = []
        if value.action_type in {"split", "reverse_split"} and value.terms_status == "complete":
            effects.extend([
                ("quantity_multiplier", value.source_instrument_id,
                 value.post_action_units, value.pre_action_units),
                ("price_multiplier", value.source_instrument_id,
                 value.pre_action_units, value.post_action_units),
            ])
        elif (
            value.action_type == "symbol_change"
            and value.terms_status == "complete"
            and value.result_instrument_id
        ):
            effects.append(("instrument_successor", value.result_instrument_id, None, None))
        for effect_type, output_instrument_id, numerator, denominator in effects:
            effect_id = hashlib.sha256(
                f"corporate-action-effect|{revision_id}|{effect_type}|"
                f"{value.source_instrument_id}|{output_instrument_id or ''}".encode()
            ).hexdigest()
            self.connection.execute(
                """
                INSERT INTO silver.corporate_action_adjustment_effects(
                    corporate_action_effect_id,corporate_action_revision_id,effect_type,
                    input_instrument_id,output_instrument_id,factor_numerator,factor_denominator,
                    effective_at,knowledge_at,quality_status,provenance
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(corporate_action_effect_id) DO NOTHING
                """,
                [effect_id, revision_id, effect_type, value.source_instrument_id,
                 output_instrument_id, numerator, denominator, value.effective_at,
                 value.knowledge_at, "pass", _json({
                     "source": "corporate_action_revision",
                     "factor_contract": "output_units_per_input_unit" if effect_type == "quantity_multiplier"
                     else "input_price_basis_per_output_price_basis" if effect_type == "price_multiplier"
                     else "identity_successor",
                 })],
            )
            if pipeline_run_id:
                evidence_hash = hashlib.sha256(_json({
                    "revision_id": revision_id,
                    "effect_id": effect_id,
                    "effect_type": effect_type,
                    "numerator": numerator,
                    "denominator": denominator,
                }).encode()).hexdigest()
                lineage_id = hashlib.sha256(
                    f"corporate-action-lineage|{pipeline_run_id}|{effect_id}".encode()
                ).hexdigest()
                self.connection.execute(
                    """
                    INSERT INTO control.lineage_edges(
                        lineage_edge_id,run_id,input_ref,output_ref,transform_id,
                        transform_version,evidence_hash,created_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(lineage_edge_id) DO NOTHING
                    """,
                    [lineage_id, pipeline_run_id,
                     f"silver.corporate_action_revisions:{revision_id}",
                     f"silver.corporate_action_adjustment_effects:{effect_id}",
                     "corporate-action-safe-effect", "1.0.0", evidence_hash,
                     value.knowledge_at],
                )

    def actions_as_of(
        self,
        *,
        instrument_id: str,
        start_date: date,
        end_date: date,
        knowledge_cutoff_at: datetime,
    ) -> list[dict[str, Any]]:
        if knowledge_cutoff_at.tzinfo is None:
            raise ValueError("knowledge_cutoff_at must be timezone-aware")
        rows = self.connection.execute(
            """
            SELECT
                actions.corporate_action_id,actions.source_id,actions.source_record_id,actions.market,
                revisions.corporate_action_revision_id,revisions.revision,revisions.action_type,
                revisions.action_status,revisions.source_instrument_id,revisions.result_instrument_id,
                revisions.effective_at,revisions.pre_action_units,revisions.post_action_units,
                revisions.terms_status,revisions.knowledge_at,revisions.quality_status
            FROM silver.corporate_actions actions
            JOIN silver.corporate_action_revisions revisions USING(corporate_action_id)
            WHERE (revisions.source_instrument_id=? OR revisions.result_instrument_id=?)
              AND CAST(revisions.effective_at AS DATE) BETWEEN ? AND ?
              AND revisions.knowledge_at<=?
            QUALIFY row_number() OVER (
                PARTITION BY actions.corporate_action_id
                ORDER BY revisions.knowledge_at DESC,revisions.revision DESC,
                         revisions.corporate_action_revision_id DESC
            )=1
            ORDER BY revisions.effective_at,actions.corporate_action_id
            """,
            [instrument_id, instrument_id, start_date, end_date, knowledge_cutoff_at],
        ).fetchall()
        columns = [item[0] for item in self.connection.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def effects_for_revision(self, revision_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT corporate_action_effect_id,effect_type,input_instrument_id,output_instrument_id,
                   factor_numerator,factor_denominator,effective_at,knowledge_at,quality_status
            FROM silver.corporate_action_adjustment_effects
            WHERE corporate_action_revision_id=? ORDER BY effect_type
            """,
            [revision_id],
        ).fetchall()
        columns = [item[0] for item in self.connection.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def adjustment_readiness_as_of(
        self,
        *,
        instrument_id: str,
        start_date: date,
        end_date: date,
        knowledge_cutoff_at: datetime,
        coverage_quality_result_id: str | None = None,
    ) -> dict[str, Any]:
        actions = self.actions_as_of(
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        coverage = self._coverage_evidence(
            coverage_quality_result_id=coverage_quality_result_id,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        if not coverage:
            return {
                "status": "not_assessed",
                "can_compute_returns": False,
                "reason": "no_governed_corporate_action_coverage",
                "action_count": len(actions),
            }
        if not actions:
            return {
                "status": "pass",
                "can_compute_returns": True,
                "reason": "no_corporate_action_in_covered_period",
                "action_count": 0,
                "coverage_quality_result_id": coverage_quality_result_id,
                "blockers": [],
            }
        blockers: list[dict[str, str]] = []
        for action in actions:
            if action["action_status"] == "cancelled":
                continue
            expected = {
                "split": {"quantity_multiplier", "price_multiplier"},
                "reverse_split": {"quantity_multiplier", "price_multiplier"},
                "symbol_change": {"instrument_successor"},
            }.get(action["action_type"])
            effects = {
                item["effect_type"]
                for item in self.effects_for_revision(action["corporate_action_revision_id"])
                if item["quality_status"] == "pass"
            }
            if (
                action["action_status"] != "confirmed"
                or action["quality_status"] != "pass"
                or expected is None
                or not expected <= effects
            ):
                blockers.append({
                    "corporate_action_id": action["corporate_action_id"],
                    "reason": "unknown_or_unsupported_adjustment_terms",
                })
        return {
            "status": "pass" if not blockers else "blocked",
            "can_compute_returns": not blockers,
            "reason": None if not blockers else "corporate_action_adjustment_incomplete",
            "action_count": len(actions),
            "coverage_quality_result_id": coverage_quality_result_id,
            "blockers": blockers,
        }

    def _coverage_evidence(
        self,
        *,
        coverage_quality_result_id: str | None,
        instrument_id: str,
        start_date: date,
        end_date: date,
        knowledge_cutoff_at: datetime,
    ) -> bool:
        if not coverage_quality_result_id:
            return False
        row = self.connection.execute(
            """
            SELECT dataset_id,rule_id,status,details,evaluated_at
            FROM control.quality_results WHERE quality_result_id=?
            """,
            [coverage_quality_result_id],
        ).fetchone()
        if not row or row[0:3] != (
            "dataset.corporate-action-event",
            "held_instrument_date_range_coverage",
            "pass",
        ) or row[4] > knowledge_cutoff_at:
            return False
        details = json.loads(row[3]) if isinstance(row[3], str) else dict(row[3])
        try:
            covered_start = date.fromisoformat(str(details["start_date"]))
            covered_end = date.fromisoformat(str(details["end_date"]))
        except (KeyError, TypeError, ValueError):
            return False
        return (
            details.get("instrument_id") == instrument_id
            and covered_start <= start_date
            and covered_end >= end_date
        )
