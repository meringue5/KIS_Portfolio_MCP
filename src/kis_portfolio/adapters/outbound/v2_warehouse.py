"""Schema-qualified V2 warehouse repository used by local rehearsals and future adapters."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.core import new_id
from kis_portfolio.ports.source import SourceEnvelope


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class V2WarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_observation(self, dataset_id: str, envelope: SourceEnvelope, run_id: str | None = None) -> str:
        key_source = f"{dataset_id}|{envelope.source_id}|{envelope.source_record_id}|{envelope.content_hash}"
        key = hashlib.sha256(key_source.encode()).hexdigest()
        observation_id = hashlib.sha256(f"observation|{key}".encode()).hexdigest()
        self.connection.execute("""
            INSERT INTO bronze.source_observations(
                observation_id, dataset_id, source_id, source_record_id, idempotency_key,
                effective_at, observed_at, fetched_at, content_hash, quality_status, payload, pipeline_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO NOTHING
        """, [
            observation_id, dataset_id, envelope.source_id, envelope.source_record_id, key,
            envelope.observed_at, envelope.observed_at, envelope.fetched_at, envelope.content_hash,
            envelope.quality_status, _json(envelope.payload), run_id,
        ])
        row = self.connection.execute(
            "SELECT observation_id FROM bronze.source_observations WHERE idempotency_key = ?", [key]
        ).fetchone()
        return row[0]

    def upsert_account(self, payload: dict[str, Any], observation_id: str) -> None:
        self.connection.execute("""
            INSERT INTO silver.accounts VALUES (?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                account_label = excluded.account_label,
                account_type = excluded.account_type,
                base_currency = excluded.base_currency,
                provenance = excluded.provenance
        """, [payload["account_id"], payload["account_label"], payload["account_type"],
              payload.get("base_currency", "KRW"), payload["as_of"], _json({"observation_id": observation_id})])

    def upsert_instrument(self, payload: dict[str, Any], observation_id: str) -> None:
        self.connection.execute("""
            INSERT INTO silver.instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(instrument_id) DO UPDATE SET
                name = excluded.name, asset_type = excluded.asset_type, currency = excluded.currency,
                issuer_id = excluded.issuer_id, classification_quality = excluded.classification_quality,
                provenance = excluded.provenance
        """, [payload["instrument_id"], payload["market"], payload["symbol"], payload.get("name"),
              payload["asset_type"], payload["currency"], payload.get("issuer_id"), payload["as_of"],
              payload.get("classification_quality", "source"), _json({"observation_id": observation_id})])

    def upsert_position(self, payload: dict[str, Any], observation_id: str) -> None:
        self.connection.execute("""
            INSERT INTO silver.position_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, instrument_id, as_of) DO UPDATE SET
                quantity = excluded.quantity, average_cost = excluded.average_cost,
                source_observation_id = excluded.source_observation_id, quality_status = excluded.quality_status
        """, [payload["account_id"], payload["instrument_id"], payload["as_of"], payload["quantity"],
              payload.get("average_cost"), payload.get("cost_currency", "KRW"), observation_id,
              payload.get("quality_status", "pass")])

    def upsert_cash(self, payload: dict[str, Any], observation_id: str) -> None:
        self.connection.execute("""
            INSERT INTO silver.cash_snapshots VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, currency, as_of) DO UPDATE SET
                amount = excluded.amount, source_observation_id = excluded.source_observation_id,
                quality_status = excluded.quality_status
        """, [payload["account_id"], payload["currency"], payload["as_of"], payload["amount"],
              observation_id, payload.get("quality_status", "pass")])

    def record_trade_with_lot(self, payload: dict[str, Any], observation_id: str) -> tuple[str, str | None]:
        identity = f"{payload['account_id']}|{payload['broker_order_id']}|{payload.get('event_version', 1)}"
        trade_id = hashlib.sha256(identity.encode()).hexdigest()
        self.connection.execute("""
            INSERT INTO silver.trade_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, broker_order_id, event_version) DO NOTHING
        """, [trade_id, payload["account_id"], payload["instrument_id"], payload["side"],
              payload["executed_at"], payload["quantity"], payload["price"], payload["currency"],
              payload["broker_order_id"], payload.get("event_version", 1), observation_id,
              payload.get("quality_status", "pass")])
        if payload["side"].lower() != "buy":
            return trade_id, None
        lot_id = hashlib.sha256(f"lot|{trade_id}".encode()).hexdigest()
        self.connection.execute("""
            INSERT INTO silver.purchase_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_event_id) DO NOTHING
        """, [lot_id, trade_id, payload["account_id"], payload["instrument_id"], payload["executed_at"],
              payload["quantity"], payload["quantity"], payload["price"], payload["currency"],
              payload.get("quality_status", "pass")])
        return trade_id, lot_id

    def create_thread(self, payload: dict[str, Any], lot_id: str | None = None) -> str:
        thread_id = payload.get("thread_id") or new_id()
        self.connection.execute("""
            INSERT INTO silver.trade_threads VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO NOTHING
        """, [thread_id, payload["account_id"], payload["instrument_id"], payload["opened_at"],
              payload.get("title"), payload.get("status", "open"), payload.get("revision", 1),
              _json(payload.get("provenance", {"source": "fixture"}))])
        if lot_id:
            self.connection.execute("""
                INSERT INTO silver.trade_thread_lots VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
            """, [thread_id, lot_id, 1, payload["opened_at"], payload.get("linkage_quality", "explicit")])
        return thread_id

    def append_journal(self, payload: dict[str, Any]) -> None:
        self.connection.execute("""
            INSERT INTO silver.trade_journal_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
        """, [payload["journal_id"], payload["revision"], payload.get("thread_id"),
              payload.get("trade_event_id"), payload["body"], payload.get("authored_by", "owner"),
              payload["authored_at"], payload.get("expected_prior_revision")])

    def upsert_price_bar(self, payload: dict[str, Any], observation_id: str) -> None:
        self.upsert_price_bars([payload], observation_id)

    def upsert_price_bars(self, payloads: list[dict[str, Any]], observation_id: str) -> None:
        """Write one landed page in two database round trips."""
        if not payloads:
            return
        fallback_knowledge_at = None
        if any(payload.get("knowledge_at") is None for payload in payloads):
            row = self.connection.execute(
                "SELECT fetched_at FROM bronze.source_observations WHERE observation_id=?", [observation_id]
            ).fetchone()
            if not row:
                raise ValueError("price revision requires a governed source observation")
            fallback_knowledge_at = row[0]
        revision_rows: list[list[Any]] = []
        current_rows: list[list[Any]] = []
        for payload in payloads:
            basis = str(payload.get("price_basis") or "").strip()
            if basis not in {"raw", "adjusted"}:
                raise ValueError("price_basis must be raw or adjusted")
            session_date = payload["session_date"]
            if isinstance(session_date, str):
                session_date = date.fromisoformat(session_date)
            effective_at = payload.get("effective_at") or datetime.combine(session_date, time.max, tzinfo=UTC)
            knowledge_at = payload.get("knowledge_at") or fallback_knowledge_at
            endpoint = str(payload.get("endpoint") or "fixture-or-legacy")
            request_option = str(payload.get("request_option") or basis)
            volume_basis = str(payload.get("volume_basis") or "vendor_reported")
            reconstruction_mode = str(payload.get("reconstruction_mode") or "operational_strict")
            quality_status = str(payload.get("quality_status") or "pass")
            revision_document = {
                "instrument_id": payload["instrument_id"],
                "session_date": session_date.isoformat(),
                "price_basis": basis,
                "open": str(payload.get("open")),
                "high": str(payload.get("high")),
                "low": str(payload.get("low")),
                "close": str(payload.get("close")),
                "volume": payload.get("volume"),
                "endpoint": endpoint,
                "request_option": request_option,
                "volume_basis": volume_basis,
                "quality_status": quality_status,
            }
            revision_hash = str(payload.get("revision_hash") or hashlib.sha256(
                _json(revision_document).encode()
            ).hexdigest())
            shared = [
                payload["instrument_id"], session_date, basis,
                payload.get("open"), payload.get("high"), payload.get("low"), payload.get("close"),
                payload.get("volume"), observation_id, quality_status, effective_at, knowledge_at,
                revision_hash, endpoint, request_option, volume_basis, reconstruction_mode,
            ]
            current_rows.append(shared)
            revision_rows.append(
                shared[:3] + [revision_hash] + shared[3:8] + shared[10:12]
                + [observation_id, endpoint, request_option, volume_basis, reconstruction_mode, quality_status,
                   _json(payload.get("metadata", {}))]
            )

        revision_values = ",".join(["(" + ",".join(["?"] * 18) + ")"] * len(revision_rows))
        self.connection.execute(f"""
            INSERT INTO silver.price_bar_revisions_daily(
                instrument_id, session_date, price_basis, revision_hash,
                open, high, low, close, volume, effective_at, knowledge_at,
                source_observation_id, endpoint, request_option, volume_basis,
                reconstruction_mode, quality_status, metadata
            ) VALUES {revision_values}
            ON CONFLICT DO NOTHING
        """, [value for row in revision_rows for value in row])
        current_values = ",".join(["(" + ",".join(["?"] * 17) + ")"] * len(current_rows))
        self.connection.execute(f"""
            INSERT INTO silver.price_bars_daily(
                instrument_id, session_date, price_basis, open, high, low, close, volume,
                source_observation_id, quality_status, effective_at, knowledge_at, revision_hash,
                endpoint, request_option, volume_basis, reconstruction_mode
            ) VALUES {current_values}
            ON CONFLICT(instrument_id, session_date, price_basis) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                volume=excluded.volume, source_observation_id=excluded.source_observation_id,
                quality_status=excluded.quality_status, effective_at=excluded.effective_at,
                knowledge_at=excluded.knowledge_at, revision_hash=excluded.revision_hash,
                endpoint=excluded.endpoint, request_option=excluded.request_option,
                volume_basis=excluded.volume_basis, reconstruction_mode=excluded.reconstruction_mode
            WHERE silver.price_bars_daily.knowledge_at IS NULL
               OR excluded.knowledge_at >= silver.price_bars_daily.knowledge_at
        """, [value for row in current_rows for value in row])

    def get_price_bars_as_of(
        self,
        *,
        instrument_id: str,
        start_date: date,
        end_date: date,
        price_basis: str,
        evaluation_at: datetime,
        replay_mode: str = "operational_strict",
    ) -> list[dict[str, Any]]:
        if price_basis not in {"raw", "adjusted"}:
            raise ValueError("price_basis must be raw or adjusted")
        if replay_mode not in {"operational_strict", "retrospective_reconstructed"}:
            raise ValueError("unsupported replay_mode")
        if evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        knowledge_clause = "AND knowledge_at <= ?" if replay_mode == "operational_strict" else ""
        params: list[Any] = [instrument_id, start_date, end_date, price_basis, evaluation_at]
        if replay_mode == "operational_strict":
            params.append(evaluation_at)
        rows = self.connection.execute(f"""
            SELECT session_date, open, high, low, close, volume, effective_at, knowledge_at,
                   revision_hash, source_observation_id, endpoint, request_option, volume_basis,
                   reconstruction_mode, quality_status
            FROM silver.price_bar_revisions_daily
            WHERE instrument_id=? AND session_date BETWEEN ? AND ? AND price_basis=?
              AND effective_at <= ? {knowledge_clause}
            QUALIFY row_number() OVER (
                PARTITION BY instrument_id, session_date, price_basis
                ORDER BY knowledge_at DESC, recorded_at DESC, revision_hash DESC
            ) = 1
            ORDER BY session_date
        """, params).fetchall()
        columns = [
            "session_date", "open", "high", "low", "close", "volume", "effective_at", "knowledge_at",
            "revision_hash", "source_observation_id", "endpoint", "request_option", "volume_basis",
            "reconstruction_mode", "quality_status",
        ]
        return [dict(zip(columns, row)) | {"replay_mode": replay_mode} for row in rows]

    def upsert_fx_rate(self, payload: dict[str, Any], observation_id: str) -> None:
        self.connection.execute("""
            INSERT INTO silver.fx_rates_daily VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(base_currency, quote_currency, rate_date, rate_type) DO UPDATE SET
                rate=excluded.rate, source_observation_id=excluded.source_observation_id,
                quality_status=excluded.quality_status
        """, [payload["base_currency"], payload["quote_currency"], payload["rate_date"],
              payload.get("rate_type", "close"), payload["rate"], observation_id,
              payload.get("quality_status", "pass")])

    def materialize_daily_state(self, *, evaluation_date: date, slot: str, as_of: datetime) -> int:
        self.connection.execute("""
            INSERT INTO gold.portfolio_daily_state
            WITH latest_positions AS (
                SELECT * FROM silver.position_snapshots
                WHERE CAST(as_of AS DATE) = ?
                QUALIFY row_number() OVER (
                    PARTITION BY account_id, instrument_id ORDER BY as_of DESC, source_observation_id DESC
                ) = 1
            ), latest_bars AS (
                SELECT * FROM silver.price_bars_daily WHERE session_date <= ? AND price_basis = 'raw'
                QUALIFY row_number() OVER (PARTITION BY instrument_id ORDER BY session_date DESC) = 1
            )
            SELECT
                ?, ?, p.account_id, p.instrument_id, 'position', p.quantity,
                round(p.quantity * b.close * CASE WHEN i.currency = 'KRW' THEN 1 ELSE coalesce(f.rate, 0) END, 2),
                round(p.quantity * p.average_cost * CASE WHEN i.currency = 'KRW' THEN 1 ELSE coalesce(f.rate, 0) END, 2),
                round(p.quantity * (b.close - p.average_cost) * CASE WHEN i.currency = 'KRW' THEN 1 ELSE coalesce(f.rate, 0) END, 2),
                NULL, NULL, ?,
                json_object('position_as_of', p.as_of, 'price_date', b.session_date, 'fx_date', f.rate_date),
                CASE WHEN p.quality_status = 'pass' AND b.quality_status = 'pass' THEN 'pass' ELSE 'degraded' END,
                sha256(concat(p.source_observation_id, '|', b.source_observation_id, '|', coalesce(f.source_observation_id, 'KRW')))
            FROM latest_positions p
            JOIN silver.instruments i ON i.instrument_id = p.instrument_id
            JOIN latest_bars b ON b.instrument_id = p.instrument_id
            LEFT JOIN (
                SELECT * FROM silver.fx_rates_daily WHERE rate_date <= ? AND rate_type='close'
                QUALIFY row_number() OVER (PARTITION BY base_currency, quote_currency ORDER BY rate_date DESC)=1
            ) f ON f.base_currency = i.currency AND f.quote_currency = 'KRW'
            ON CONFLICT DO NOTHING
        """, [evaluation_date, evaluation_date, evaluation_date, slot, as_of, evaluation_date])
        self.connection.execute("""
            INSERT INTO gold.portfolio_daily_state
            WITH latest_cash AS (
                SELECT * FROM silver.cash_snapshots
                WHERE CAST(as_of AS DATE) = ?
                QUALIFY row_number() OVER (
                    PARTITION BY account_id, currency ORDER BY as_of DESC, source_observation_id DESC
                ) = 1
            )
            SELECT ?, ?, account_id, 'cash|' || currency, 'cash', NULL,
                   round(amount * CASE WHEN currency='KRW' THEN 1 ELSE coalesce(f.rate, 0) END, 2),
                   NULL, NULL, NULL, NULL, ?,
                   json_object('cash_as_of', c.as_of, 'fx_date', f.rate_date),
                   CASE WHEN c.quality_status='pass' AND (currency='KRW' OR f.rate IS NOT NULL)
                        THEN 'pass' ELSE 'degraded' END,
                   sha256(c.source_observation_id || '|' || coalesce(f.source_observation_id, 'KRW'))
            FROM latest_cash c
            LEFT JOIN (
                SELECT * FROM silver.fx_rates_daily WHERE rate_date<=? AND rate_type='close'
                QUALIFY row_number() OVER (PARTITION BY base_currency, quote_currency ORDER BY rate_date DESC)=1
            ) f ON f.base_currency=c.currency AND f.quote_currency='KRW'
            ON CONFLICT DO NOTHING
        """, [evaluation_date, evaluation_date, slot, as_of, evaluation_date])
        return self.connection.execute(
            "SELECT count(*) FROM gold.portfolio_daily_state WHERE evaluation_date=? AND evaluation_slot=?",
            [evaluation_date, slot],
        ).fetchone()[0]

    def table_count(self, qualified_name: str) -> int:
        allowed = {
            "bronze.source_observations", "silver.accounts", "silver.instruments",
            "silver.position_snapshots", "silver.cash_snapshots", "silver.trade_events",
            "silver.purchase_lots", "silver.trade_threads", "silver.trade_journal_revisions",
            "silver.price_bars_daily", "silver.price_bar_revisions_daily", "silver.fx_rates_daily",
            "gold.portfolio_daily_state",
        }
        if qualified_name not in allowed:
            raise ValueError("table is not in the repository count allowlist")
        return self.connection.execute(f"SELECT count(*) FROM {qualified_name}").fetchone()[0]
