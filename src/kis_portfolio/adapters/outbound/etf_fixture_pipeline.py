"""Offline-only ETF fixture adapter. No HTTP client is imported here."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb

from kis_portfolio.adapters.outbound.etf_parsers import (
    parse_koact_json,
    parse_plus_json,
    parse_rise_html,
    parse_time_xlsx,
)
from kis_portfolio.platform.etf_source_profiles import load_etf_instrument_routes, load_etf_source_profiles


PARSERS = {
    "time-xlsx": parse_time_xlsx,
    "koact-json": parse_koact_json,
    "rise-html": parse_rise_html,
    "plus-json": parse_plus_json,
}


def run_offline_etf_fixture(
    connection: duckdb.DuckDBPyConnection,
    *,
    profile_id: str,
    instrument_id: str,
    payload: bytes,
    media_type: str,
    expected_source_date: date | None = None,
) -> dict:
    profiles = load_etf_source_profiles()
    routes = load_etf_instrument_routes()
    profile = profiles[profile_id]
    route = routes.get(instrument_id)
    if not route or route.profile_id != profile_id or route.activation_state != "fixture_only":
        raise PermissionError("ETF fixture requires an exact fixture-only route")
    if media_type not in profile.media_types:
        raise ValueError("ETF fixture media type is not allowlisted")
    parsed = PARSERS[profile.parser_id](payload)
    if expected_source_date and parsed.source_date != expected_source_date:
        raise ValueError("ETF fixture source date mismatch")
    file_hash = hashlib.sha256(payload).hexdigest()
    existing = connection.execute("""
        SELECT distinct file_hash FROM silver.etf_constituent_snapshots
        WHERE etf_instrument_id=? AND source_date=?
    """, [instrument_id, parsed.source_date]).fetchall()
    if existing and any(row[0] != file_hash for row in existing):
        return {"status": "quarantined", "reason": "changed_hash_same_source_date", "source_calls": 0}
    total_weight = sum((item.weight_pct or Decimal(0)) for item in parsed.constituents)
    partial = any(item.weight_pct is None for item in parsed.constituents) or total_weight > Decimal("100.00000001")
    quality = "partial" if partial else "pass"
    connection.execute("""
        INSERT INTO bronze.raw_object_manifest(
            content_hash,dataset_id,source_id,private_uri,media_type,byte_size,rights_class,sensitivity,
            source_url,source_published_at,metadata
        ) VALUES (?, 'dataset.etf-constituent-snapshot', ?, ?, ?, ?, 'synthetic-fixture', 'internal',
                  NULL, NULL, ?)
        ON CONFLICT(content_hash) DO NOTHING
    """, [file_hash, profile.source_id, f"fixture://{file_hash}", media_type, len(payload),
          json.dumps({"profile_id": profile_id, "parser_version": profile.parser_version})])
    if partial:
        return {
            "status": "partial", "published_rows": 0, "source_calls": 0,
            "file_hash": file_hash, "unresolved_residual_pct": str(max(Decimal(0), Decimal(100) - total_weight)),
        }
    for ordinal, item in enumerate(parsed.constituents, 1):
        connection.execute("""
            INSERT INTO silver.etf_constituent_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT DO NOTHING
        """, [instrument_id, parsed.source_date, file_hash, ordinal, item.instrument_id, item.name,
              item.instrument_type, item.weight_pct, item.currency, quality])
    return {
        "status": "pass", "published_rows": len(parsed.constituents), "source_calls": 0,
        "file_hash": file_hash, "unresolved_residual_pct": str(max(Decimal(0), Decimal(100) - total_weight)),
        "evaluated_at": datetime.now(UTC).isoformat(),
    }
