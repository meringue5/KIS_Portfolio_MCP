#!/usr/bin/env python3
"""Dry-run or apply current-held instrument classification and exact ETF route projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

import duckdb
from dotenv import load_dotenv

from kis_portfolio.adapters.outbound.instrument_warehouse import InstrumentWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.modules.exposure import resolve_instrument_classification
from kis_portfolio.platform.etf_source_profiles import load_etf_instrument_routes, production_network_profiles
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


HELD_SQL = """
WITH latest AS (
    SELECT account_id, max(as_of) AS as_of FROM silver.position_snapshots GROUP BY account_id
), held AS (
    SELECT DISTINCT position.instrument_id
    FROM silver.position_snapshots position
    JOIN latest USING(account_id, as_of)
    WHERE position.quantity > 0
)
SELECT instrument.instrument_id,instrument.market,instrument.symbol,instrument.name,instrument.currency,
       master.group_code,master.standard_code,
       override.exposure_type,override.exposure_region,override.asset_subtype,override.reason
FROM held
JOIN silver.instruments instrument USING(instrument_id)
LEFT JOIN main.instrument_master master
  ON instrument.market='KRX' AND master.market='KRX' AND master.symbol=instrument.symbol
LEFT JOIN main.instrument_classification_overrides override
  ON instrument.market='KRX' AND override.market='KRX' AND override.symbol=instrument.symbol
ORDER BY instrument.instrument_id
"""


def _rows(connection: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = connection.execute(HELD_SQL).fetchall()
    columns = [item[0] for item in connection.description]
    return [dict(zip(columns, row)) for row in rows]


def inspect(connection: duckdb.DuckDBPyConnection) -> dict:
    routes = load_etf_instrument_routes()
    counts: Counter[str] = Counter()
    routed = 0
    resolved: list[tuple[dict, object]] = []
    for row in _rows(connection):
        route = routes.get(row["instrument_id"])
        classification = resolve_instrument_classification(
            market=row["market"], name=row["name"], as_of=datetime.now(UTC),
            master={"group_code": row["group_code"], "standard_code": row["standard_code"]},
            override={
                "exposure_type": row["exposure_type"], "exposure_region": row["exposure_region"],
                "asset_subtype": row["asset_subtype"], "reason": row["reason"],
            } if row["reason"] else None,
            exact_route_profile_id=route.profile_id if route else None,
        )
        counts[classification.asset_type] += 1
        routed += int(route is not None)
        resolved.append((row, classification))
    return {
        "held_instruments": len(resolved), "classification_counts": dict(sorted(counts.items())),
        "exact_routes_for_held": routed, "registered_routes": len(routes),
        "production_network_profiles": len(production_network_profiles()),
        "instrument_version_rows": connection.execute("SELECT count(*) FROM silver.instrument_versions").fetchone()[0],
        "route_rows": connection.execute("SELECT count(*) FROM control.etf_instrument_routes").fetchone()[0],
        "classification_observation_rows": connection.execute("""
            SELECT count(*) FROM bronze.source_observations
            WHERE pipeline_run_id='wi017-held-classification'
        """).fetchone()[0],
    }


def apply(connection: duckdb.DuckDBPyConnection) -> dict:
    now = datetime.now(UTC)
    routes = load_etf_instrument_routes()
    instruments = InstrumentWarehouseRepository(connection)
    observations = V2WarehouseRepository(connection)
    for route in routes.values():
        instruments.sync_route(route, knowledge_at=now)
    for row in _rows(connection):
        route = routes.get(row["instrument_id"])
        classification = resolve_instrument_classification(
            market=row["market"], name=row["name"], as_of=now,
            master={"group_code": row["group_code"], "standard_code": row["standard_code"]},
            override={
                "exposure_type": row["exposure_type"], "exposure_region": row["exposure_region"],
                "asset_subtype": row["asset_subtype"], "reason": row["reason"],
            } if row["reason"] else None,
            exact_route_profile_id=route.profile_id if route else None,
        )
        payload = {
            "instrument_id": row["instrument_id"], "market": row["market"], "symbol": row["symbol"],
            "name": row["name"], "currency": row["currency"], "asset_type": classification.asset_type,
            "economic_exposure": classification.economic_exposure, "classification_source": classification.source,
            "classification_quality": classification.quality, "valid_from": now, "knowledge_at": now,
            "metadata": classification.evidence,
        }
        latest = connection.execute("""
            SELECT name,asset_type,economic_exposure,currency,issuer_id,classification_source,classification_quality
            FROM silver.instruments_current WHERE instrument_id=?
        """, [row["instrument_id"]]).fetchone()
        comparison = (
            payload.get("name"), payload["asset_type"], payload["economic_exposure"], payload["currency"],
            payload.get("issuer_id"), payload["classification_source"], payload["classification_quality"],
        )
        if latest != comparison:
            document = json.dumps(payload, sort_keys=True, default=str)
            envelope = SourceEnvelope(
                "source.portfolio-owner", f"wi017:{row['instrument_id']}", now, now, payload,
                hashlib.sha256(document.encode()).hexdigest(),
                "pass" if classification.asset_type != "unknown" else "partial",
            )
            observation_id = observations.record_observation(
                "dataset.instrument-master", envelope, "wi017-held-classification"
            )
            instruments.record_version(payload, observation_id)
        connection.execute("""
            UPDATE silver.instruments SET asset_type=?,classification_quality=?
            WHERE instrument_id=?
        """, [classification.asset_type, classification.quality, row["instrument_id"]])
    return inspect(connection)


def main() -> None:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--motherduck", action="store_true")
    target.add_argument("--database")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    if args.motherduck:
        token = get_motherduck_token()
        if not token:
            raise RuntimeError("MOTHERDUCK_TOKEN required")
        connection_string = f"md:{get_motherduck_database()}?motherduck_token={token}"
        target_label = f"md:{get_motherduck_database()}"
    else:
        connection_string = args.database
        target_label = args.database
    connection = duckdb.connect(connection_string)
    try:
        MigrationRunner(connection).require("0007")
        result = apply(connection) if args.apply else inspect(connection)
        print(json.dumps({"status": "applied" if args.apply else "dry_run", "target": target_label, **result}, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
