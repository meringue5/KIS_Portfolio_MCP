"""Pinned, append-only import of owner-reviewed noncanonical total levels (WI-068)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

APPROVED_SHA256 = "c1b5a62d0146b1f72265519aed09a3952768329b1b5afa00f6802b622c23e95b"
RECOVERY_VERSION = "wi068-2026-10-13.1"
ASSUMPTIONS = frozenset({"last_available_fx_at_or_before_observation_date", "missing_overseas_cash_assumed_zero_owner_2026-10-13"})
FLAGS = frozenset({"external_fx_valuation", "legacy_noncanonical", "not_cash_flow_adjusted_return", "original_fetch_clock_not_repaired", "overseas_cash_unknown", "overseas_position_observation_absent", "retrospective_not_historical_pit"})
ROW_KEYS = frozenset({"date", "recorded_total_krw", "candidate_total_krw", "missing_foreign_valuation_added_krw", "status", "canonical", "snapshot_at_original", "input_sha256", "account_coverage_count", "foreign_position_count", "missing_krw_position_count", "assumptions", "flags", "fx"})


def _amount(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("reference_amount_type")
    result = Decimal(value)
    if not result.is_finite() or result < 0 or result != result.quantize(Decimal("0.01")):
        raise ValueError("reference_amount_invalid")
    return result


def validate_candidate(payload: bytes, *, expected_sha256: str = APPROVED_SHA256) -> tuple[dict, str]:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError("reference_input_hash_mismatch")
    candidate = json.loads(payload)
    if candidate.get("work_item") != "WI-068" or candidate.get("canonical") is not False:
        raise ValueError("reference_input_identity")
    knowledge = datetime.fromisoformat(candidate["created_at"])
    if knowledge.tzinfo is None:
        raise ValueError("reference_knowledge_timezone")
    dates = set()
    counts = {"recorded_reference": 0, "estimated_reference": 0, "unavailable_total": 0}
    for row in candidate["rows"]:
        if set(row) != ROW_KEYS or row["canonical"] is not False or row["account_coverage_count"] != 5:
            raise ValueError("reference_row_contract")
        day = date.fromisoformat(row["date"])
        if day in dates or not date(2026, 4, 19) <= day <= date(2026, 8, 27):
            raise ValueError("reference_dates")
        dates.add(day)
        if not re.fullmatch(r"[a-f0-9]{64}", row["input_sha256"]):
            raise ValueError("reference_source_hash")
        datetime.fromisoformat(row["snapshot_at_original"])
        if not set(row["assumptions"]) <= ASSUMPTIONS or not set(row["flags"]) <= FLAGS:
            raise ValueError("reference_unapproved_assumption")
        kind = row["status"]
        if kind not in counts:
            raise ValueError("reference_kind")
        counts[kind] += 1
        base, added = _amount(row["recorded_total_krw"]), _amount(row["missing_foreign_valuation_added_krw"])
        if kind == "unavailable_total":
            if row["candidate_total_krw"] is not None or row["foreign_position_count"] != 0 or added != 0:
                raise ValueError("reference_unavailable_total")
        elif _amount(row["candidate_total_krw"]) != base + added or row["foreign_position_count"] < 1:
            raise ValueError("reference_reconciliation")
        if kind == "recorded_reference" and (added or row["assumptions"] or row["fx"] is not None):
            raise ValueError("reference_recorded_assumptions")
        if kind == "estimated_reference" and not row["assumptions"]:
            raise ValueError("reference_estimate_assumptions_missing")
        fx = row["fx"]
        if added > 0 and (kind != "estimated_reference" or fx is None):
            raise ValueError("reference_fx_missing")
        if fx is not None:
            rate_day = date.fromisoformat(fx["rate_date"])
            age = (day - rate_day).days
            if (fx["series_id"] != "DEXKOUS" or fx["provider"] != "FRED / Federal Reserve Board"
                    or fx["rate_type"] != "new_york_noon_buying" or fx["base_currency"] != "USD"
                    or fx["quote_currency"] != "KRW" or fx["requested_date"] != row["date"]
                    or not 0 <= age <= 4 or fx["age_days"] != age or _amount(fx["rate"]) <= 0
                    or not re.fullmatch(r"[a-f0-9]{64}", fx["source_file_sha256"])):
                raise ValueError("reference_fx_contract")
    if counts != {"recorded_reference": 14, "estimated_reference": 11, "unavailable_total": 2}:
        raise ValueError("reference_reviewed_coverage")
    return candidate, digest


def import_candidate(connection: duckdb.DuckDBPyConnection, path: Path, *, expected_sha256: str = APPROVED_SHA256) -> dict[str, int | str]:
    candidate, digest = validate_candidate(path.read_bytes(), expected_sha256=expected_sha256)
    inserted = 0
    connection.execute("BEGIN TRANSACTION")
    try:
        for row in candidate["rows"]:
            values = [row["date"], RECOVERY_VERSION, row["input_sha256"], row["recorded_total_krw"],
                      row["candidate_total_krw"], row["missing_foreign_valuation_added_krw"], row["status"],
                      json.dumps(row["assumptions"], sort_keys=True), json.dumps(row["flags"], sort_keys=True),
                      row["snapshot_at_original"], json.dumps(row["fx"], sort_keys=True) if row["fx"] else None,
                      candidate["created_at"], digest]
            existing = connection.execute("""SELECT recorded_total_krw,reference_total_krw,added_foreign_value_krw,
                valuation_kind,assumptions,coverage_reasons,original_snapshot_at,fx_provenance,knowledge_at,source_object_hash
                FROM silver.portfolio_legacy_total_reference WHERE observation_date=? AND recovery_version=? AND input_content_hash=?""", values[:3]).fetchone()
            if existing is not None:
                expected = (_amount(values[3]), _amount(values[4]) if values[4] is not None else None,
                            _amount(values[5]), *values[6:11], datetime.fromisoformat(values[11]), digest)
                if existing != expected:
                    raise ValueError("reference_existing_version_conflict")
                continue
            connection.execute("""INSERT INTO silver.portfolio_legacy_total_reference
                (observation_date,recovery_version,input_content_hash,recorded_total_krw,reference_total_krw,
                 added_foreign_value_krw,valuation_kind,assumptions,coverage_reasons,original_snapshot_at,
                 fx_provenance,knowledge_at,source_object_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            inserted += 1
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {"inserted": inserted, "reviewed_rows": 27, "valued_rows": 25, "unavailable_rows": 2, "input_sha256": digest}
