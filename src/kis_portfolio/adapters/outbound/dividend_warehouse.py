"""Append-only dividend repository implementing ADR-026 without source I/O."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.market.dividends import (
    CashAmountComponentRevision,
    DividendActionRevision,
    DividendEntitlementRevision,
    DividendReceiptLinkRevision,
    validate_action,
    validate_component,
    validate_entitlement,
    validate_receipt_link,
)
from kis_portfolio.ports.object_store import StoredObject


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _digest(prefix: str, value: Any) -> str:
    return hashlib.sha256(f"{prefix}|{_json(value)}".encode()).hexdigest()


def _content(value: Any, excluded: set[str]) -> dict[str, Any]:
    return {key: item for key, item in asdict(value).items() if key not in excluded}


def _has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"api_key", "authorization", "cookie", "access_token", "secret"}:
                return True
            if _has_forbidden_key(nested):
                return True
    if isinstance(value, (list, tuple)):
        return any(_has_forbidden_key(item) for item in value)
    return False


class DividendWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def _observation(self, observation_id: str, *, source_id: str | None = None) -> tuple[Any, ...]:
        row = self.connection.execute(
            """
            SELECT dataset_id,source_id,source_record_id,content_hash,fetched_at,pipeline_run_id
            FROM bronze.source_observations WHERE observation_id=?
            """,
            [observation_id],
        ).fetchone()
        if not row or row[0] not in {"dataset.dividend-source-observation", "dataset.cash-transaction-event"}:
            raise ValueError("dividend record requires governed source evidence")
        if source_id is not None and row[1] != source_id:
            raise ValueError("dividend source evidence does not match the record source")
        return row

    def record_source_manifest(
        self,
        *,
        observation_id: str,
        stored: StoredObject,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        observation = self._observation(observation_id)
        if observation[0] != "dataset.dividend-source-observation":
            raise ValueError("dividend source manifest requires dividend evidence")
        if not stored.uri.startswith(("gs://", "fixture-private://")):
            raise ValueError("dividend source objects require a private URI")
        if stored.content_hash != observation[3]:
            raise ValueError("dividend source object hash does not match its observation")
        if stored.media_type not in {"application/json", "application/pdf", "text/csv"}:
            raise ValueError("dividend source object media type is not allowlisted")
        if stored.byte_size < 0 or stored.byte_size > 50 * 1024 * 1024:
            raise ValueError("dividend source object exceeds the 50 MiB limit")
        if _has_forbidden_key(metadata or {}):
            raise ValueError("dividend source metadata contains forbidden credential fields")
        existing = self.connection.execute(
            """SELECT dataset_id,source_id,private_uri,media_type,byte_size
               FROM bronze.raw_object_manifest WHERE content_hash=?""",
            [stored.content_hash],
        ).fetchone()
        expected = (observation[0], observation[1], stored.uri, stored.media_type, stored.byte_size)
        if existing is not None and tuple(existing) != expected:
            raise ValueError("dividend source hash replay conflicts with its immutable manifest")
        self.connection.execute(
            """
            INSERT INTO bronze.raw_object_manifest(
                content_hash,dataset_id,source_id,private_uri,media_type,byte_size,
                rights_class,sensitivity,source_url,source_published_at,ingested_at,metadata
            ) VALUES (?,?,?,?,?,?,'owner-private','restricted',NULL,NULL,?,?)
            ON CONFLICT(content_hash) DO NOTHING
            """,
            [stored.content_hash, observation[0], observation[1], stored.uri,
             stored.media_type, stored.byte_size, observation[4],
             _json((metadata or {}) | {"source_observation_id": observation_id})],
        )
        return stored.content_hash

    def _require_manifest(self, observation_id: str, content_hash: str) -> None:
        if not self.connection.execute(
            """SELECT 1 FROM bronze.raw_object_manifest
               WHERE content_hash=? AND dataset_id='dataset.dividend-source-observation'
                 AND json_extract_string(metadata,'$.source_observation_id')=?""",
            [content_hash, observation_id],
        ).fetchone():
            raise ValueError("dividend Silver publish requires a verified private raw object")

    def record_action(self, value: DividendActionRevision, *, observation_id: str) -> tuple[str, str]:
        validate_action(value)
        observation = self._observation(observation_id, source_id=value.source_id)
        if observation[0] != "dataset.dividend-source-observation":
            raise ValueError("dividend action requires dividend source evidence")
        if observation[2] != value.source_action_id:
            raise ValueError("dividend action source identity does not match its observation")
        self._require_manifest(observation_id, observation[3])
        instrument = self.connection.execute(
            "SELECT issuer_id FROM silver.instruments WHERE instrument_id=?",
            [value.instrument_id],
        ).fetchone()
        if not instrument or instrument[0] != value.issuer_id:
            raise ValueError("dividend action requires an exact governed issuer and instrument")
        action_identity = {
            "source_id": value.source_id,
            "jurisdiction": value.jurisdiction,
            "issuer_id": value.issuer_id,
            "instrument_id": value.instrument_id,
            "source_action_id": value.source_action_id,
        }
        action_id = _digest("dividend-action", action_identity)
        existing_identity = self.connection.execute(
            """
            SELECT issuer_id,instrument_id FROM silver.dividend_actions
            WHERE dividend_action_id=?
            """,
            [action_id],
        ).fetchone()
        if existing_identity is not None and existing_identity != (value.issuer_id, value.instrument_id):
            raise ValueError("dividend action identity replay conflicts")
        content = _content(value, {"knowledge_at", "observed_at", "fetched_at", "provenance"})
        revision_hash = _digest("dividend-action-content", content)
        duplicate = self.connection.execute(
            """SELECT dividend_action_revision_id FROM silver.dividend_action_revisions
               WHERE dividend_action_id=? AND revision_hash=?""",
            [action_id, revision_hash],
        ).fetchone()
        if duplicate:
            return action_id, duplicate[0]
        latest = self.connection.execute(
            """SELECT revision,knowledge_at FROM silver.dividend_action_revisions
               WHERE dividend_action_id=? ORDER BY revision DESC LIMIT 1""",
            [action_id],
        ).fetchone()
        if latest and value.knowledge_at < latest[1]:
            raise ValueError("dividend action knowledge_at cannot move backwards")
        if value.correction_target_revision_id:
            target = self.connection.execute(
                """SELECT 1 FROM silver.dividend_action_revisions
                   WHERE dividend_action_revision_id=? AND dividend_action_id=?""",
                [value.correction_target_revision_id, action_id],
            ).fetchone()
            if not target:
                raise ValueError("dividend action correction target is not a known same-action revision")
        revision = 1 if latest is None else latest[0] + 1
        revision_id = _digest("dividend-action-revision", {
            "action_id": action_id, "revision": revision, "hash": revision_hash,
        })
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """
                INSERT INTO silver.dividend_actions(
                    dividend_action_id,source_id,jurisdiction,issuer_id,instrument_id,
                    source_action_id,first_source_observation_id,first_known_at
                ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(dividend_action_id) DO NOTHING
                """,
                [action_id, value.source_id, value.jurisdiction, value.issuer_id,
                 value.instrument_id, value.source_action_id, observation_id, value.knowledge_at],
            )
            self.connection.execute(
                """
                INSERT INTO silver.dividend_action_revisions(
                    dividend_action_revision_id,dividend_action_id,revision,revision_hash,
                    action_type,action_status,certainty,amount_per_share,currency,
                    declaration_date,ex_date,record_date,payable_date,cancellation_date,
                    source_available_at,source_time_precision,observed_at,fetched_at,knowledge_at,
                    source_observation_id,filing_revision_id,correction_target_revision_id,
                    quality_status,provenance
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                [revision_id, action_id, revision, revision_hash, value.action_type,
                 value.action_status, value.certainty, value.amount_per_share, value.currency,
                 value.declaration_date, value.ex_date, value.record_date, value.payable_date,
                 value.cancellation_date, value.source_available_at, value.source_time_precision,
                 value.observed_at, value.fetched_at, value.knowledge_at, observation_id,
                 value.filing_revision_id, value.correction_target_revision_id,
                 value.quality_status, _json(value.provenance or {})],
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return action_id, revision_id

    def record_entitlement(self, value: DividendEntitlementRevision) -> tuple[str, str]:
        validate_entitlement(value)
        if not self.connection.execute(
            "SELECT 1 FROM silver.dividend_actions WHERE dividend_action_id=?",
            [value.dividend_action_id],
        ).fetchone():
            raise ValueError("entitlement requires a known dividend action")
        if not self.connection.execute(
            "SELECT 1 FROM silver.accounts WHERE account_id=?", [value.account_id]
        ).fetchone():
            raise ValueError("entitlement requires a governed account")
        if value.source_observation_id:
            observation = self._observation(value.source_observation_id)
            if observation[0] != "dataset.dividend-source-observation":
                raise ValueError("entitlement source evidence must be a dividend observation")
            self._require_manifest(value.source_observation_id, observation[3])
        identity = {"action": value.dividend_action_id, "account": value.account_id}
        entitlement_id = _digest("dividend-entitlement", identity)
        content = _content(value, {"knowledge_at", "provenance"})
        revision_hash = _digest("dividend-entitlement-content", content)
        duplicate = self.connection.execute(
            """SELECT dividend_entitlement_revision_id FROM silver.dividend_entitlement_revisions
               WHERE dividend_entitlement_id=? AND revision_hash=?""",
            [entitlement_id, revision_hash],
        ).fetchone()
        if duplicate:
            return entitlement_id, duplicate[0]
        latest = self.connection.execute(
            """SELECT revision,knowledge_at FROM silver.dividend_entitlement_revisions
               WHERE dividend_entitlement_id=? ORDER BY revision DESC LIMIT 1""",
            [entitlement_id],
        ).fetchone()
        if latest and value.knowledge_at < latest[1]:
            raise ValueError("dividend entitlement knowledge_at cannot move backwards")
        if value.correction_target_revision_id and not self.connection.execute(
            """SELECT 1 FROM silver.dividend_entitlement_revisions
               WHERE dividend_entitlement_revision_id=? AND dividend_entitlement_id=?""",
            [value.correction_target_revision_id, entitlement_id],
        ).fetchone():
            raise ValueError("entitlement correction target is not a known same-entitlement revision")
        revision = 1 if latest is None else latest[0] + 1
        revision_id = _digest("dividend-entitlement-revision", {
            "entitlement_id": entitlement_id, "revision": revision, "hash": revision_hash,
        })
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """INSERT INTO silver.dividend_entitlements VALUES (?,?,?,?,current_timestamp)
                   ON CONFLICT(dividend_entitlement_id) DO NOTHING""",
                [entitlement_id, value.dividend_action_id, value.account_id, value.knowledge_at],
            )
            self.connection.execute(
                """
                INSERT INTO silver.dividend_entitlement_revisions VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,current_timestamp
                )
                """,
                [revision_id, entitlement_id, revision, revision_hash, value.basis,
                 value.eligibility_date, value.eligible_quantity, value.rate_per_share,
                 value.expected_gross, value.expected_tax, value.expected_net, value.currency,
                 value.coverage_status, value.source_observation_id, value.position_evidence_id,
                 value.corporate_action_revision_id, value.knowledge_at,
                 value.correction_target_revision_id, value.quality_status,
                 _json(value.provenance or {})],
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return entitlement_id, revision_id

    def record_receipt_link(self, value: DividendReceiptLinkRevision) -> tuple[str, str]:
        validate_receipt_link(value)
        if not self.connection.execute(
            "SELECT 1 FROM silver.dividend_actions WHERE dividend_action_id=?",
            [value.dividend_action_id],
        ).fetchone():
            raise ValueError("receipt link requires a known dividend action")
        if value.dividend_entitlement_id:
            entitlement = self.connection.execute(
                """SELECT dividend_action_id FROM silver.dividend_entitlements
                   WHERE dividend_entitlement_id=?""",
                [value.dividend_entitlement_id],
            ).fetchone()
            if not entitlement or entitlement[0] != value.dividend_action_id:
                raise ValueError("receipt link entitlement does not belong to the action")
        cash = None
        if value.cash_flow_event_id:
            cash = self.connection.execute(
                """SELECT account_id,amount,currency FROM silver.cash_flow_events
                   WHERE cash_flow_event_id=? AND knowledge_at<=?""",
                [value.cash_flow_event_id, value.knowledge_at],
            ).fetchone()
            classified = self.connection.execute(
                """SELECT event_type FROM silver.cash_flow_event_revisions
                   WHERE cash_flow_event_id=? AND knowledge_at<=?
                   ORDER BY knowledge_at DESC,revision DESC LIMIT 1""",
                [value.cash_flow_event_id, value.knowledge_at],
            ).fetchone()
            if not cash or not classified or classified[0] != "dividend":
                raise ValueError("receipt link requires a dividend-classified cash event at cutoff")
            if value.currency and value.currency != cash[2]:
                raise ValueError("receipt allocation currency must match the cash monetary fact")
            if value.dividend_entitlement_id:
                account = self.connection.execute(
                    """SELECT account_id FROM silver.dividend_entitlements
                       WHERE dividend_entitlement_id=?""",
                    [value.dividend_entitlement_id],
                ).fetchone()
                if account[0] != cash[0]:
                    raise ValueError("receipt cash and entitlement account must match")
        link_id = _digest("dividend-receipt-link", {
            "action": value.dividend_action_id, "relation_key": value.relation_key,
        })
        content = _content(value, {"knowledge_at", "provenance"})
        revision_hash = _digest("dividend-receipt-link-content", content)
        duplicate = self.connection.execute(
            """SELECT dividend_receipt_link_revision_id FROM silver.dividend_receipt_link_revisions
               WHERE dividend_receipt_link_id=? AND revision_hash=?""",
            [link_id, revision_hash],
        ).fetchone()
        if duplicate:
            return link_id, duplicate[0]
        latest = self.connection.execute(
            """SELECT revision,knowledge_at FROM silver.dividend_receipt_link_revisions
               WHERE dividend_receipt_link_id=? ORDER BY revision DESC LIMIT 1""",
            [link_id],
        ).fetchone()
        if latest and value.knowledge_at < latest[1]:
            raise ValueError("dividend receipt-link knowledge_at cannot move backwards")
        if value.correction_target_revision_id and not self.connection.execute(
            """SELECT 1 FROM silver.dividend_receipt_link_revisions
               WHERE dividend_receipt_link_revision_id=? AND dividend_receipt_link_id=?""",
            [value.correction_target_revision_id, link_id],
        ).fetchone():
            raise ValueError("receipt-link correction target is not a known same-link revision")
        if cash and value.link_status in {"exact", "reconciled", "partial"}:
            allocation = value.allocated_receipt_amount
            if allocation is None:
                other = self.connection.execute(
                    """SELECT count(*) FROM silver.dividend_receipt_links identities
                       JOIN silver.dividend_receipt_links_current current USING (dividend_receipt_link_id)
                       WHERE identities.cash_flow_event_id=? AND identities.dividend_receipt_link_id<>?
                         AND current.link_status IN ('exact','reconciled','partial')""",
                    [value.cash_flow_event_id, link_id],
                ).fetchone()[0]
                if other:
                    raise ValueError("many-to-many receipt links require explicit allocation")
            else:
                unallocated = self.connection.execute(
                    """SELECT count(*) FROM silver.dividend_receipt_links identities
                       JOIN silver.dividend_receipt_links_current current USING (dividend_receipt_link_id)
                       WHERE identities.cash_flow_event_id=? AND identities.dividend_receipt_link_id<>?
                         AND current.link_status IN ('exact','reconciled','partial')
                         AND current.allocated_receipt_amount IS NULL""",
                    [value.cash_flow_event_id, link_id],
                ).fetchone()[0]
                if unallocated:
                    raise ValueError("many-to-many receipt links require explicit allocation")
                allocated = self.connection.execute(
                    """SELECT coalesce(sum(abs(current.allocated_receipt_amount)),0)
                       FROM silver.dividend_receipt_links identities
                       JOIN silver.dividend_receipt_links_current current USING (dividend_receipt_link_id)
                       WHERE identities.cash_flow_event_id=? AND identities.dividend_receipt_link_id<>?
                         AND current.link_status IN ('exact','reconciled','partial')""",
                    [value.cash_flow_event_id, link_id],
                ).fetchone()[0]
                if Decimal(str(allocated)) + abs(allocation) > abs(Decimal(str(cash[1]))):
                    raise ValueError("receipt-link allocations exceed the cash monetary fact")
        revision = 1 if latest is None else latest[0] + 1
        revision_id = _digest("dividend-receipt-link-revision", {
            "link_id": link_id, "revision": revision, "hash": revision_hash,
        })
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(
                """INSERT INTO silver.dividend_receipt_links VALUES (?,?,?,?,?,?,current_timestamp)
                   ON CONFLICT(dividend_receipt_link_id) DO NOTHING""",
                [link_id, value.dividend_action_id, value.dividend_entitlement_id,
                 value.cash_flow_event_id, value.relation_key, value.knowledge_at],
            )
            self.connection.execute(
                """INSERT INTO silver.dividend_receipt_link_revisions(
                    dividend_receipt_link_revision_id,dividend_receipt_link_id,revision,
                    revision_hash,link_status,allocated_receipt_amount,currency,reason,
                    rule_version,knowledge_at,correction_target_revision_id,quality_status,provenance
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [revision_id, link_id, revision, revision_hash, value.link_status,
                 value.allocated_receipt_amount, value.currency, value.reason,
                 value.rule_version, value.knowledge_at, value.correction_target_revision_id,
                 value.quality_status, _json(value.provenance or {})],
            )
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return link_id, revision_id

    def record_cash_component(self, value: CashAmountComponentRevision) -> str:
        validate_component(value)
        observation = self._observation(value.source_observation_id, source_id=value.source_id)
        cash = self.connection.execute(
            "SELECT currency FROM silver.cash_flow_events WHERE cash_flow_event_id=?",
            [value.cash_flow_event_id],
        ).fetchone()
        if not cash or cash[0] != value.currency:
            raise ValueError("cash component must match an existing monetary fact currency")
        latest = self.connection.execute(
            """SELECT revision,knowledge_at,amount,source_id,source_observation_id,correction_target_revision_id
               FROM silver.cash_flow_event_amount_components
               WHERE cash_flow_event_id=? AND component_type=? ORDER BY revision DESC LIMIT 1""",
            [value.cash_flow_event_id, value.component_type],
        ).fetchone()
        if latest and value.knowledge_at < latest[1]:
            raise ValueError("cash component knowledge_at cannot move backwards")
        if latest and (
            Decimal(str(latest[2])), latest[3], latest[4], latest[5]
        ) == (
            value.amount, value.source_id, value.source_observation_id,
            value.correction_target_revision_id,
        ):
            return self.connection.execute(
                """SELECT cash_amount_component_revision_id FROM silver.cash_flow_event_amount_components
                   WHERE cash_flow_event_id=? AND component_type=? AND revision=?""",
                [value.cash_flow_event_id, value.component_type, latest[0]],
            ).fetchone()[0]
        revision = 1 if latest is None else latest[0] + 1
        revision_id = _digest("cash-amount-component", {
            "event": value.cash_flow_event_id, "type": value.component_type,
            "revision": revision, "amount": value.amount, "source_record": observation[2],
        })
        self.connection.execute(
            """INSERT INTO silver.cash_flow_event_amount_components VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,current_timestamp
            )""",
            [revision_id, value.cash_flow_event_id, value.component_type, revision,
             value.amount, value.currency, value.source_id, value.source_observation_id,
             value.knowledge_at, value.correction_target_revision_id, value.quality_status,
             _json(value.provenance or {})],
        )
        return revision_id

    def actions_as_of(self, *, instrument_id: str, cutoff_at: datetime) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT identities.dividend_action_id,identities.issuer_id,identities.instrument_id,
                   revisions.revision,revisions.action_type,revisions.action_status,
                   revisions.amount_per_share,revisions.currency,revisions.payable_date,
                   revisions.knowledge_at,revisions.quality_status
            FROM silver.dividend_actions identities
            JOIN silver.dividend_action_revisions revisions USING (dividend_action_id)
            WHERE identities.instrument_id=? AND revisions.knowledge_at<=?
            QUALIFY row_number() OVER (
                PARTITION BY identities.dividend_action_id
                ORDER BY revisions.knowledge_at DESC,revisions.revision DESC
            )=1 ORDER BY revisions.knowledge_at,identities.dividend_action_id
            """,
            [instrument_id, cutoff_at],
        )

    def receipt_links_as_of(self, *, cutoff_at: datetime) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT identities.dividend_receipt_link_id,identities.dividend_action_id,
                   identities.dividend_entitlement_id,identities.cash_flow_event_id,
                   revisions.revision,revisions.link_status,revisions.allocated_receipt_amount,
                   revisions.currency,revisions.knowledge_at,revisions.quality_status
            FROM silver.dividend_receipt_links identities
            JOIN silver.dividend_receipt_link_revisions revisions USING (dividend_receipt_link_id)
            WHERE revisions.knowledge_at<=?
            QUALIFY row_number() OVER (
                PARTITION BY identities.dividend_receipt_link_id
                ORDER BY revisions.knowledge_at DESC,revisions.revision DESC
            )=1 ORDER BY identities.dividend_receipt_link_id
            """,
            [cutoff_at],
        )

    def monthly_native_as_of(self, *, cutoff_at: datetime) -> list[dict[str, Any]]:
        rows = self._rows(
            """
            WITH links AS (
                SELECT * EXCLUDE (rn) FROM (
                    SELECT revisions.*,row_number() OVER (
                        PARTITION BY dividend_receipt_link_id
                        ORDER BY knowledge_at DESC,revision DESC
                    ) rn
                    FROM silver.dividend_receipt_link_revisions revisions
                    WHERE knowledge_at<=?
                ) WHERE rn=1
            ), cash_classifications AS (
                SELECT * EXCLUDE (rn) FROM (
                    SELECT revisions.*,row_number() OVER (
                        PARTITION BY cash_flow_event_id
                        ORDER BY knowledge_at DESC,revision DESC
                    ) rn
                    FROM silver.cash_flow_event_revisions revisions
                    WHERE knowledge_at<=?
                ) WHERE rn=1
            ), components AS (
                SELECT * EXCLUDE (rn) FROM (
                    SELECT values.*,row_number() OVER (
                        PARTITION BY cash_flow_event_id,component_type
                        ORDER BY knowledge_at DESC,revision DESC
                    ) rn
                    FROM silver.cash_flow_event_amount_components values
                    WHERE knowledge_at<=?
                ) WHERE rn=1
            ), component_pivot AS (
                SELECT cash_flow_event_id,
                       max(amount) FILTER (WHERE component_type='gross') gross_amount,
                       max(amount) FILTER (WHERE component_type='tax') tax_amount,
                       max(amount) FILTER (WHERE component_type='net') net_amount,
                       count(DISTINCT component_type) component_count
                FROM components GROUP BY cash_flow_event_id
            )
            SELECT date_trunc('month', cash.effective_at)::DATE received_month,
                   cash.account_id,actions.instrument_id,cash.currency,
                   sum(coalesce(links.allocated_receipt_amount,cash.amount)) received_cash_amount,
                   sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN component_pivot.gross_amount
                            ELSE component_pivot.gross_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) sourced_gross_amount,
                   sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN component_pivot.tax_amount
                            ELSE component_pivot.tax_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) sourced_tax_amount,
                   sum(CASE WHEN links.allocated_receipt_amount IS NULL THEN component_pivot.net_amount
                            ELSE component_pivot.net_amount*abs(links.allocated_receipt_amount)/nullif(abs(cash.amount),0) END) sourced_net_amount,
                   count(DISTINCT cash.cash_flow_event_id) received_count,
                   CASE WHEN min(coalesce(component_count,0))=3 THEN 'complete' ELSE 'partial' END component_coverage,
                   CASE WHEN bool_and(links.link_status IN ('exact','reconciled')) THEN 'complete' ELSE 'partial' END reconciliation_coverage
            FROM silver.dividend_receipt_links identities
            JOIN links USING (dividend_receipt_link_id)
            JOIN silver.dividend_actions actions USING (dividend_action_id)
            JOIN silver.cash_flow_events cash ON cash.cash_flow_event_id=identities.cash_flow_event_id
            JOIN cash_classifications classifications
              ON classifications.cash_flow_event_id=cash.cash_flow_event_id
            LEFT JOIN component_pivot
              ON component_pivot.cash_flow_event_id=cash.cash_flow_event_id
            WHERE links.link_status IN ('exact','reconciled','partial')
              AND classifications.event_type='dividend' AND cash.knowledge_at<=?
            GROUP BY received_month,cash.account_id,actions.instrument_id,cash.currency
            ORDER BY received_month,cash.account_id,actions.instrument_id,cash.currency
            """,
            [cutoff_at, cutoff_at, cutoff_at, cutoff_at],
        )
        history: dict[tuple[Any, ...], dict[Any, Decimal]] = {}
        for row in rows:
            key = (row["account_id"], row["instrument_id"], row["currency"])
            history.setdefault(key, {})[row["received_month"]] = Decimal(str(row["received_cash_amount"]))
        for row in rows:
            month = row["received_month"]
            prior_month = (month.replace(day=1) - timedelta(days=1)).replace(day=1)
            prior_year = month.replace(year=month.year - 1)
            amounts = history[(row["account_id"], row["instrument_id"], row["currency"])]
            current = Decimal(str(row["received_cash_amount"]))
            row["prior_month_change"] = current - amounts[prior_month] if prior_month in amounts else None
            row["prior_year_change"] = current - amounts[prior_year] if prior_year in amounts else None
            row["evaluation_at"] = cutoff_at
            row["producer_version"] = "1.0.0"
        return rows

    def _rows(self, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, parameters)
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
