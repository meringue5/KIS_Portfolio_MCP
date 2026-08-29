"""Governed, DB-only evidence refresh for the WI-029 shadow window."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from kis_portfolio.adapters.outbound.alert_calibration_warehouse import (
    AlertCalibrationWarehouse,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import RULE_ID, RULE_VERSION
from kis_portfolio.services.wi029_s04 import SHADOW_END, SHADOW_START


SEOUL = ZoneInfo("Asia/Seoul")
_SLOT_TIMES = (
    ("kr-1000", time(10, 0)),
    ("us-close", time(10, 0)),
    ("kr-1430", time(14, 30)),
    ("kr-1600", time(16, 0)),
)


def expected_shadow_slot_keys(
    connection: duckdb.DuckDBPyConnection,
    *,
    window_start: date,
    window_end: date,
    observed_at: datetime,
) -> tuple[str, ...]:
    """Return due KRX-open slots, independently of alert candidates."""
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    if window_end < window_start:
        raise ValueError("shadow window end precedes start")
    local_now = observed_at.astimezone(SEOUL)
    due_end = min(window_end, local_now.date())
    if due_end < window_start:
        return ()
    table_exists = connection.execute(
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema='main' AND table_name='market_calendar'
        """
    ).fetchone()[0]
    if not table_exists:
        raise RuntimeError("WI-029 shadow coverage requires complete KRX calendar rows")
    rows = connection.execute(
        """
        SELECT trade_date,is_open FROM main.market_calendar
        WHERE lower(market)='krx' AND trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        [window_start, due_end],
    ).fetchall()
    if len(rows) != (due_end - window_start).days + 1:
        raise RuntimeError("WI-029 shadow coverage requires complete KRX calendar rows")
    keys: list[str] = []
    for trade_date, is_open in rows:
        if not bool(is_open):
            continue
        for slot, due_time in _SLOT_TIMES:
            if trade_date == local_now.date() and local_now.timetz().replace(tzinfo=None) < due_time:
                continue
            keys.append(f"evaluation:{trade_date.isoformat()}|{slot}")
    return tuple(keys)


def refresh_wi029_s05_evidence(
    connection: duckdb.DuckDBPyConnection,
    *,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Recompute shadow coverage without provider or delivery calls."""
    now = recorded_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    MigrationRunner(connection).require("0013")
    repository = AlertCalibrationWarehouse(connection)
    expected = expected_shadow_slot_keys(
        connection,
        window_start=SHADOW_START,
        window_end=SHADOW_END,
        observed_at=now,
    )
    evidence = repository.build_shadow_evidence(
        rule_set_id=RULE_ID,
        rule_set_version=RULE_VERSION,
        window_start=SHADOW_START,
        window_end=SHADOW_END,
        expected_session_keys=expected,
        owner_review_complete=False,
    )
    status = repository.write_shadow_evidence(evidence, updated_at=now)
    return {
        "status": status,
        "shadow_window_id": evidence.shadow_window_id,
        "coverage_key_version": "evaluation-date-slot-v1",
        "expected_due_slot_count": len(evidence.expected_session_keys),
        "observed_slot_count": len(evidence.observed_session_keys),
        "missing_slot_keys": evidence.summary["missing_session_keys"],
        "unexpected_slot_keys": evidence.summary["unexpected_session_keys"],
        "candidate_count": evidence.candidate_count,
        "external_send_count": evidence.external_send_count,
    }
