"""Point-in-time instrument version and exact ETF route repository."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from kis_portfolio.platform.etf_source_profiles import EtfInstrumentRoute


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class InstrumentWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_version(self, payload: dict[str, Any], source_observation_id: str) -> str:
        instrument_id = payload["instrument_id"]
        latest = self.connection.execute("""
            SELECT instrument_version_id, name, asset_type, economic_exposure, currency, issuer_id,
                   classification_source, classification_quality, valid_from
            FROM silver.instrument_versions
            WHERE instrument_id=?
            ORDER BY valid_from DESC, knowledge_at DESC LIMIT 1
        """, [instrument_id]).fetchone()
        comparison = (
            payload.get("name"), payload["asset_type"], payload.get("economic_exposure", "unknown"),
            payload["currency"], payload.get("issuer_id"), payload["classification_source"],
            payload["classification_quality"],
        )
        if latest and tuple(latest[1:8]) == comparison:
            return latest[0]
        valid_from = payload["valid_from"]
        if latest and valid_from <= latest[8]:
            raise ValueError("instrument version valid_from must advance for a changed classification")
        knowledge_at = payload.get("knowledge_at") or datetime.now(UTC)
        identity = _json({
            "instrument_id": instrument_id, "valid_from": valid_from, "classification": comparison,
        })
        version_id = hashlib.sha256(identity.encode()).hexdigest()
        self.connection.execute("""
            INSERT INTO silver.instrument_versions(
                instrument_version_id,instrument_id,market,symbol,name,asset_type,economic_exposure,
                currency,issuer_id,valid_from,knowledge_at,classification_source,classification_quality,
                source_observation_id,metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT DO NOTHING
        """, [version_id, instrument_id, payload["market"], payload["symbol"], payload.get("name"),
              payload["asset_type"], payload.get("economic_exposure", "unknown"), payload["currency"],
              payload.get("issuer_id"), valid_from, knowledge_at, payload["classification_source"],
              payload["classification_quality"], source_observation_id, _json(payload.get("metadata", {}))])
        return version_id

    def as_of(self, instrument_id: str, cutoff: datetime) -> dict[str, Any] | None:
        row = self.connection.execute("""
            SELECT * EXCLUDE(valid_to) FROM silver.instrument_versions_effective
            WHERE instrument_id=? AND valid_from<=? AND knowledge_at<=?
            ORDER BY valid_from DESC, knowledge_at DESC LIMIT 1
        """, [instrument_id, cutoff, cutoff]).fetchone()
        if not row:
            return None
        columns = [item[0] for item in self.connection.description]
        return dict(zip(columns, row))

    def sync_route(self, route: EtfInstrumentRoute, *, knowledge_at: datetime | None = None) -> None:
        self.connection.execute("""
            INSERT INTO control.etf_instrument_routes(
                route_id,instrument_id,market,symbol,profile_id,provider_product_key,product_key_kind,
                activation_state,valid_from,valid_to,knowledge_at,contract_version,metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?)
            ON CONFLICT(route_id) DO NOTHING
        """, [route.route_id, route.instrument_id, route.market, route.symbol, route.profile_id,
              route.provider_product_key, route.product_key_kind, route.activation_state, route.valid_from,
              knowledge_at or datetime.now(UTC), route.version, _json({"source": "governance catalog"})])
