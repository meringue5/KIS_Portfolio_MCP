from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb

from kis_portfolio.analytics.asset_overview import get_total_asset_daily_change
from kis_portfolio.application.valuation_change import (
    CanonicalValuationState,
    ValuationChangeEvaluator,
    ValuationComponentState,
    build_valuation_change_result,
    inspect_valuation_change_readiness,
)
from kis_portfolio.db.schema import init_schema
from kis_portfolio.platform.migrations import MigrationRunner


def _component(
    component_id: str,
    value: str,
    *,
    currency: str = "KRW",
    market: str = "KRX",
    symbol: str | None = None,
    is_cash: bool = False,
) -> ValuationComponentState:
    return ValuationComponentState(
        component_id=component_id,
        symbol=symbol or (None if is_cash else component_id),
        name=component_id,
        market=market,
        currency=currency,
        is_cash=is_cash,
        value_krw=Decimal(value),
        account_values={"ria": Decimal(value)},
        lineage_hash=f"lineage-{component_id}-{value}",
    )


def _state(
    *,
    day: int,
    total: str,
    components: list[ValuationComponentState],
    complete: bool = True,
    required: frozenset[str] = frozenset({"ria"}),
    observed: frozenset[str] = frozenset({"ria"}),
    blockers: tuple[str, ...] = (),
) -> CanonicalValuationState:
    return CanonicalValuationState(
        source_model="fixture",
        snapshot_ref=f"snapshot-{day}",
        evaluation_date=date(2026, 8, day),
        evaluation_slot="16:00",
        snapshot_at=datetime(2026, 8, day, 7, tzinfo=UTC),
        total_value_krw=Decimal(total),
        components={item.component_id: item for item in components},
        required_accounts=required,
        observed_accounts=observed,
        quality_status="pass" if complete else "degraded",
        is_complete=complete,
        blockers=blockers,
    )


def test_complete_result_reconciles_new_sold_cash_and_foreign_fx() -> None:
    prior = _state(day=27, total="1000", components=[
        _component("KRX:OLD", "200"),
        _component("NASD:AAPL", "300", currency="USD", market="NASD", symbol="AAPL"),
        _component("cash|KRW", "500", market="CASH", is_cash=True),
    ])
    current = _state(day=28, total="1100", components=[
        _component("NASD:AAPL", "400", currency="USD", market="NASD", symbol="AAPL"),
        _component("KRX:NEW", "300"),
        _component("cash|KRW", "400", market="CASH", is_cash=True),
    ])

    result = build_valuation_change_result(prior, current, include_account_breakdown=True)
    contributors = {item["instrument_id"]: item for item in result["contributors"]}

    assert result["status"] == "pass"
    assert result["totals"] == {
        "previous_total_asset_krw": 1000,
        "current_total_asset_krw": 1100,
        "total_asset_change_krw": 100,
        "holding_change_sum_krw": 200,
        "cash_change_krw": -100,
        "explained_change_sum_krw": 100,
        "unexplained_residual_krw": 0,
        "reconciliation_tolerance_krw": 1,
        "reconciliation_status": "pass",
    }
    assert contributors["KRX:OLD"]["is_fully_sold"] is True
    assert contributors["KRX:NEW"]["is_new_position"] is True
    assert contributors["NASD:AAPL"]["valuation_change_label"] == "KRW valuation change including FX"
    assert contributors["NASD:AAPL"]["share_of_total_change_pct"] == 100.0
    assert result["cash"]["valuation_change_krw"] == -100


def test_partial_account_coverage_suppresses_new_and_sold_inference() -> None:
    accounts = frozenset({"ria", "isa"})
    prior = _state(
        day=27, total="100", components=[_component("KRX:OLD", "100")],
        required=accounts, observed=accounts,
    )
    current = _state(
        day=28, total="100", components=[_component("KRX:NEW", "100")], complete=False,
        required=accounts, observed=frozenset({"ria"}), blockers=("required_account_snapshot_missing",),
    )

    result = build_valuation_change_result(prior, current)

    assert result["status"] == "degraded"
    assert result["quality"]["new_sold_inference"] == "suppressed"
    assert "current_required_account_coverage_mismatch" in result["quality"]["blockers"]
    assert all(item["is_new_position"] is None and item["is_fully_sold"] is None for item in result["contributors"])


def test_zero_change_denominator_and_residual_failure_are_explicit() -> None:
    prior = _state(day=27, total="1000", components=[
        _component("KRX:A", "500"), _component("KRX:B", "500"),
    ])
    current = _state(day=28, total="1000", components=[
        _component("KRX:A", "600"), _component("KRX:B", "400"),
    ])
    zero_change = build_valuation_change_result(prior, current)
    assert zero_change["status"] == "pass"
    assert all(item["share_of_total_change_pct"] is None for item in zero_change["contributors"])
    assert all(
        item["share_of_total_change_unavailable_reason"] == "total_asset_change_zero"
        for item in zero_change["contributors"]
    )

    mismatched = _state(day=28, total="1200", components=[
        _component("KRX:A", "600"), _component("KRX:B", "400"),
    ])
    residual = build_valuation_change_result(prior, mismatched)
    assert residual["status"] == "degraded"
    assert residual["totals"]["unexplained_residual_krw"] == 200
    assert residual["totals"]["reconciliation_status"] == "failed"
    assert "valuation_change_reconciliation_failed" in residual["quality"]["blockers"]


def _insert_v1_snapshot(
    connection: duckdb.DuckDBPyConnection,
    *,
    snapshot_id: str,
    day: int,
    total: int,
    rows: list[tuple[str, str | None, str, str, int]],
    required: list[str] = ["ria", "isa"],
    observed: list[str] = ["ria", "isa"],
    complete: bool = True,
) -> None:
    quality = {
        "status": "pass" if complete else "degraded",
        "is_complete": complete,
        "flags": [] if complete else [{"code": "required_account_snapshot_missing"}],
        "required_account_labels": required,
        "observed_account_labels": observed,
    }
    connection.execute("""
        INSERT INTO asset_overview_snapshots(
            id,snapshot_at,total_eval_amt_krw,cash_amt_krw,allocation_data,classification_summary,
            quality_status,quality_flags,is_complete,overview_data
        ) VALUES (?, ?, ?, 0, '{}', '{}', ?, ?, ?, ?)
    """, [
        snapshot_id, datetime(2026, 8, day, 16), total, quality["status"],
        json.dumps(quality["flags"]), complete, json.dumps({"data_quality": quality}),
    ])
    for index, (account, symbol, market, currency, value) in enumerate(rows):
        is_cash = symbol is None
        connection.execute("""
            INSERT INTO asset_holding_snapshots(
                id,overview_snapshot_id,snapshot_at,account_label,account_type,symbol,name,market,
                basis_category,exposure_type,asset_subtype,value_krw,currency,raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
        """, [
            f"{snapshot_id}-{index}", snapshot_id, datetime(2026, 8, day, 16), account, account,
            symbol, symbol or "cash", market, "cash" if is_cash else "domestic_account",
            "cash" if is_cash else "domestic_direct", "cash" if is_cash else "equity", value, currency,
        ])


def test_v1_daily_change_is_additively_enriched_from_canonical_holdings() -> None:
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    _insert_v1_snapshot(
        connection, snapshot_id="prior", day=27, total=1000,
        rows=[("ria", "005930", "KRX", "KRW", 600), ("isa", None, "KRW", "KRW", 400)],
    )
    _insert_v1_snapshot(
        connection, snapshot_id="current", day=28, total=1100,
        rows=[("ria", "005930", "KRX", "KRW", 700), ("isa", None, "KRW", "KRW", 400)],
    )

    result = get_total_asset_daily_change(connection, days=2)

    assert result["latest"]["change_amt"] == 100
    assert result["valuation_change_contribution"]["status"] == "pass"
    assert result["valuation_change_contribution"]["contributors"][0]["valuation_change_krw"] == 100
    assert result["valuation_change_contribution"]["contributors"][0]["account_breakdown"][0]["account_label"] == "ria"


def _insert_v2_fixture(connection: duckdb.DuckDBPyConnection, *, current_quality: str = "pass") -> None:
    connection.execute(
        "INSERT INTO silver.accounts VALUES ('acct-1','owner','brokerage','KRW',?,NULL,'{}')",
        [datetime(2026, 8, 1, tzinfo=UTC)],
    )
    connection.execute("""
        INSERT INTO silver.instruments VALUES(
            'NASD:AAPL','NASD','AAPL','Apple','equity','USD',NULL,?,NULL,'source','{}'
        )
    """, [datetime(2026, 8, 1, tzinfo=UTC)])
    for day, value, cash, quality in ((27, "500", "500", "pass"), (28, "600", "500", current_quality)):
        as_of = datetime(2026, 8, day, 7, tzinfo=UTC)
        for instrument, level, amount in (("NASD:AAPL", "position", value), ("cash|KRW", "cash", cash)):
            connection.execute("""
                INSERT INTO gold.portfolio_daily_state(
                    evaluation_date,evaluation_slot,account_id,instrument_id,aggregate_level,quantity,
                    value_krw,cost_krw,unrealized_pnl_krw,contribution_pct,allocation_pct,as_of,
                    input_watermarks,quality_status,lineage_hash
                ) VALUES (?, '16:00','acct-1',?,?,NULL,?,NULL,NULL,NULL,NULL,?,'{}',?,?)
            """, [date(2026, 8, day), instrument, level, amount, as_of, quality, f"lineage-{day}-{instrument}"])


def test_v2_projection_persists_idempotent_point_in_time_metric() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    _insert_v2_fixture(connection)
    evaluator = ValuationChangeEvaluator(connection)

    result, values = evaluator.evaluate_v2_period_and_store(
        prior_date=date(2026, 8, 27), current_date=date(2026, 8, 28),
        evaluation_slot="16:00", evaluation_run_id="run-1",
    )
    replay, replay_values = evaluator.evaluate_v2_period_and_store(
        prior_date=date(2026, 8, 27), current_date=date(2026, 8, 28),
        evaluation_slot="16:00", evaluation_run_id="run-2",
    )

    assert result["status"] == replay["status"] == "pass"
    assert {item.subject_id: item.value for item in values} == {
        "NASD:AAPL": Decimal("100.00"), "cash|KRW": Decimal("0.00"),
    }
    assert all(item.quality_status == "pass" for item in replay_values)
    assert connection.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0] == 2
    assert connection.execute("SELECT count(*) FROM control.metric_definitions").fetchone()[0] == 1


def test_v2_degraded_state_stores_null_metric_and_suppresses_inference() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    _insert_v2_fixture(connection, current_quality="degraded")

    result, values = ValuationChangeEvaluator(connection).evaluate_v2_period_and_store(
        prior_date=date(2026, 8, 27), current_date=date(2026, 8, 28),
        evaluation_slot="16:00", evaluation_run_id="run-degraded",
    )

    assert result["status"] == "degraded"
    assert result["quality"]["new_sold_inference"] == "suppressed"
    assert all(item.value is None for item in values)
    assert connection.execute("SELECT count(*) FROM gold.metric_values WHERE value_decimal IS NULL").fetchone()[0] == 2


def test_readiness_reports_legacy_v1_view_drift_without_raising() -> None:
    connection = duckdb.connect(":memory:")
    init_schema(connection)
    MigrationRunner(connection).apply()
    connection.execute("DROP VIEW asset_overview_daily_snapshots")
    connection.execute("""
        CREATE VIEW asset_overview_daily_snapshots AS
        SELECT id,CAST(snapshot_at AS DATE) AS snap_date,snapshot_at
        FROM asset_overview_snapshots
    """)

    result = inspect_valuation_change_readiness(connection)

    assert result["status"] == "blocked"
    assert result["v1_latest_pair"]["quality_projection_ready"] is False
    assert "v1_daily_view_missing_quality_projection" in result["blockers"]
