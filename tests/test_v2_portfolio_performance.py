from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

from kis_portfolio.adapters.outbound.metric_warehouse import MetricWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.application.portfolio_performance import (
    CONTRIBUTION_METRIC,
    DRAWDOWN_METRIC,
    METRIC_VERSION,
    RESIDUAL_METRIC,
    RETURN_METRIC,
    WEALTH_METRIC,
    PerformanceChainState,
    PortfolioPerformanceEvaluator,
    inspect_portfolio_performance_readiness,
    performance_account_scope_hash,
)
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


ROOT = Path(__file__).resolve().parents[1]
SLOT = "kr-1600"
ACCOUNT = "account-1"
INSTRUMENT = "instrument-a"


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    connection.execute("""
        CREATE TABLE main.market_calendar(
            market VARCHAR NOT NULL,
            trade_date DATE NOT NULL,
            is_open BOOLEAN NOT NULL,
            PRIMARY KEY(market, trade_date)
        )
    """)
    return connection


def _account(connection: duckdb.DuckDBPyConnection, valid_from: datetime) -> None:
    connection.execute(
        "INSERT INTO silver.accounts VALUES (?, 'owner-account', 'brokerage', 'KRW', ?, NULL, '{}')",
        [ACCOUNT, valid_from],
    )


def _calendar(connection: duckdb.DuckDBPyConnection, dates: list[date]) -> None:
    connection.executemany(
        "INSERT INTO main.market_calendar VALUES ('krx', ?, true)",
        [(item,) for item in dates],
    )


def _state(
    connection: duckdb.DuckDBPyConnection,
    *,
    day: date,
    as_of: datetime,
    position_value: str,
    cash_value: str,
    quality_status: str = "pass",
) -> None:
    rows = (
        (ACCOUNT, INSTRUMENT, "position", position_value, f"lineage-position-{day}"),
        (ACCOUNT, "cash|KRW", "cash", cash_value, f"lineage-cash-{day}"),
    )
    for account_id, instrument_id, level, value, lineage in rows:
        connection.execute("""
            INSERT INTO gold.portfolio_daily_state(
                evaluation_date, evaluation_slot, account_id, instrument_id, aggregate_level,
                quantity, value_krw, cost_krw, unrealized_pnl_krw, contribution_pct,
                allocation_pct, as_of, input_watermarks, quality_status, lineage_hash
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, '{}', ?, ?)
        """, [day, SLOT, account_id, instrument_id, level, value, as_of, quality_status, lineage])


def _coverage(
    connection: duckdb.DuckDBPyConnection,
    *,
    result_id: str,
    run_id: str,
    start_at: datetime,
    end_at: datetime,
    evaluated_at: datetime | None = None,
) -> None:
    details = {
        "coverage_start": start_at.isoformat(),
        "coverage_end": end_at.isoformat(),
        "account_count": 1,
        "account_scope_hash": performance_account_scope_hash(frozenset({ACCOUNT})),
    }
    connection.execute("""
        INSERT INTO control.quality_results(
            quality_result_id, run_id, dataset_id, rule_id, status,
            observed_value, expected_value, details, evaluated_at
        ) VALUES (?, ?, 'dataset.cash-transaction-event', 'external-cash-flow-coverage',
                  'pass', '1', '1', ?, ?)
    """, [result_id, run_id, json.dumps(details), evaluated_at or end_at - timedelta(minutes=1)])


def _cash_event(
    connection: duckdb.DuckDBPyConnection,
    *,
    event_type: str,
    amount: str,
    effective_at: datetime,
    knowledge_at: datetime,
    currency: str = "KRW",
) -> str:
    repository = V2WarehouseRepository(connection)
    record_id = f"cash-{event_type}-{effective_at.isoformat()}"
    observation_id = repository.record_observation(
        "dataset.cash-transaction-event",
        SourceEnvelope(
            "source.portfolio-owner", record_id, effective_at, knowledge_at,
            {"fixture": True}, f"hash-{record_id}", "pass",
        ),
        "cash-fixture-run",
    )
    return repository.record_cash_flow(
        {
            "account_id": ACCOUNT,
            "source_record_id": record_id,
            "event_type": event_type,
            "effective_at": effective_at,
            "knowledge_at": knowledge_at,
            "amount": amount,
            "currency": currency,
            "classification_source": "manual",
            "provenance": {"fixture": True},
        },
        observation_id,
    )


def _one_period_fixture() -> tuple[duckdb.DuckDBPyConnection, datetime, datetime]:
    connection = _connection()
    start_at = datetime(2026, 1, 1, 7, tzinfo=UTC)
    end_at = datetime(2026, 1, 2, 7, tzinfo=UTC)
    _account(connection, start_at - timedelta(days=1))
    _calendar(connection, [end_at.date()])
    _state(connection, day=start_at.date(), as_of=start_at, position_value="600", cash_value="400")
    _state(connection, day=end_at.date(), as_of=end_at, position_value="720", cash_value="480")
    _cash_event(
        connection,
        event_type="owner_deposit",
        amount="100",
        effective_at=start_at + timedelta(hours=12),
        knowledge_at=start_at + timedelta(hours=13),
    )
    _coverage(
        connection,
        result_id="coverage-1",
        run_id="coverage-run",
        start_at=start_at,
        end_at=end_at,
    )
    return connection, start_at, end_at


def test_modified_dietz_contribution_residual_and_repository_match_independent_sql() -> None:
    connection, start_at, end_at = _one_period_fixture()
    repository = MetricWarehouseRepository(connection)
    outcome = PortfolioPerformanceEvaluator(connection, repository).evaluate_period_and_store(
        prior_date=start_at.date(),
        current_date=end_at.date(),
        evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run",
        evaluation_run_id="performance-run",
    )
    assert outcome.quality_status == "pass"
    by_metric = {value.definition.metric_id: value for value in outcome.values if value.definition.metric_id != CONTRIBUTION_METRIC}
    contributions = {
        value.subject_id: value.value for value in outcome.values
        if value.definition.metric_id == CONTRIBUTION_METRIC
    }

    independent_return = connection.execute("""
        SELECT CAST(round(
            (CAST(1200 AS DECIMAL(38,10)) - 1000 - 100)
            / (CAST(1000 AS DECIMAL(38,10)) + 100 * CAST(0.5 AS DECIMAL(38,10))),
            10
        ) AS DECIMAL(38,10))
    """).fetchone()[0]
    assert by_metric[RETURN_METRIC].value == independent_return == Decimal("0.0952380952")
    assert contributions["position|instrument-a"] == Decimal("0.1142857143")
    assert contributions["cash|cash|KRW"] == Decimal("-0.0190476190")
    assert by_metric[RESIDUAL_METRIC].value == Decimal("-0.0000000001")
    assert by_metric[WEALTH_METRIC].value == Decimal("1.0952380952")
    assert by_metric[DRAWDOWN_METRIC].value == Decimal("0E-10")

    stored = repository.read_values(
        metric_id=RETURN_METRIC,
        metric_version=METRIC_VERSION,
        subject_type="portfolio",
    )
    assert len(stored) == 1
    assert stored[0]["value_decimal"] == independent_return
    assert stored[0]["metric_version"] == METRIC_VERSION

    # Identical replay is a no-op even when the audit run id differs.
    replay = PortfolioPerformanceEvaluator(connection, repository).evaluate_period_and_store(
        prior_date=start_at.date(),
        current_date=end_at.date(),
        evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run",
        evaluation_run_id="performance-replay",
    )
    assert [value.lineage_hash for value in replay.values] == [value.lineage_hash for value in outcome.values]
    assert repository.count_values() == 6
    connection.close()


def test_readiness_report_is_aggregate_only_and_does_not_claim_empty_cash_is_covered() -> None:
    connection = _connection()
    at = datetime(2026, 1, 1, 7, tzinfo=UTC)
    _account(connection, at - timedelta(days=1))
    _state(connection, day=at.date(), as_of=at, position_value="600", cash_value="400")
    report = inspect_portfolio_performance_readiness(connection)
    assert report["status"] == "blocked"
    assert "insufficient_portfolio_state_history" in report["blockers"]
    assert "missing_external_cash_flow_coverage" in report["blockers"]
    assert report["side_effects"] == "none"
    serialized = json.dumps(report, sort_keys=True)
    assert ACCOUNT not in serialized
    assert INSTRUMENT not in serialized
    connection.close()


def test_future_cash_classification_is_excluded_and_unknown_fails_closed() -> None:
    connection = _connection()
    start_at = datetime(2026, 2, 2, 7, tzinfo=UTC)
    end_at = datetime(2026, 2, 3, 7, tzinfo=UTC)
    _account(connection, start_at - timedelta(days=1))
    _calendar(connection, [end_at.date()])
    _state(connection, day=start_at.date(), as_of=start_at, position_value="600", cash_value="400")
    _state(connection, day=end_at.date(), as_of=end_at, position_value="600", cash_value="500")
    event_id = _cash_event(
        connection,
        event_type="unknown",
        amount="100",
        effective_at=start_at + timedelta(hours=2),
        knowledge_at=start_at + timedelta(hours=3),
    )
    V2WarehouseRepository(connection).append_cash_flow_classification(
        event_id,
        {
            "event_type": "owner_deposit",
            "knowledge_at": end_at + timedelta(days=1),
            "classification_source": "manual",
            "correction_reason": "future-owner-review",
        },
    )
    _coverage(
        connection,
        result_id="coverage-future",
        run_id="coverage-run",
        start_at=start_at,
        end_at=end_at,
    )
    outcome = PortfolioPerformanceEvaluator(connection).evaluate_period_and_store(
        prior_date=start_at.date(),
        current_date=end_at.date(),
        evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run",
        evaluation_run_id="future-classification-run",
    )
    assert outcome.quality_status == "unclassified_cash_flow"
    assert all(value.value is None for value in outcome.values)
    assert {value.quality_status for value in outcome.values} == {"unclassified_cash_flow"}
    connection.close()


def test_missing_cash_coverage_and_non_krw_owner_flow_are_nullable_quality_outcomes() -> None:
    missing, start_at, end_at = _one_period_fixture()
    missing.execute("DELETE FROM control.quality_results")
    outcome = PortfolioPerformanceEvaluator(missing).evaluate_period_and_store(
        prior_date=start_at.date(), current_date=end_at.date(), evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run", evaluation_run_id="missing-coverage-run",
    )
    assert outcome.quality_status == "missing_cash_flow_coverage"
    assert all(value.value is None for value in outcome.values)
    missing.close()

    foreign = _connection()
    start_at = datetime(2026, 3, 2, 7, tzinfo=UTC)
    end_at = datetime(2026, 3, 3, 7, tzinfo=UTC)
    _account(foreign, start_at - timedelta(days=1))
    _calendar(foreign, [end_at.date()])
    _state(foreign, day=start_at.date(), as_of=start_at, position_value="600", cash_value="400")
    _state(foreign, day=end_at.date(), as_of=end_at, position_value="600", cash_value="500")
    _cash_event(
        foreign, event_type="owner_deposit", amount="100", currency="USD",
        effective_at=start_at + timedelta(hours=2), knowledge_at=start_at + timedelta(hours=3),
    )
    _coverage(
        foreign, result_id="coverage-foreign", run_id="coverage-run",
        start_at=start_at, end_at=end_at,
    )
    outcome = PortfolioPerformanceEvaluator(foreign).evaluate_period_and_store(
        prior_date=start_at.date(), current_date=end_at.date(), evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run", evaluation_run_id="foreign-flow-run",
    )
    assert outcome.quality_status == "unsupported_cash_flow_currency"
    assert all(value.value is None for value in outcome.values)
    foreign.close()


def test_calendar_and_required_account_coverage_fail_closed() -> None:
    calendar_gap, start_at, end_at = _one_period_fixture()
    calendar_gap.execute("DELETE FROM main.market_calendar")
    outcome = PortfolioPerformanceEvaluator(calendar_gap).evaluate_period_and_store(
        prior_date=start_at.date(), current_date=end_at.date(), evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run", evaluation_run_id="calendar-gap-run",
    )
    assert outcome.quality_status == "missing_market_calendar_coverage"
    assert all(value.value is None for value in outcome.values)
    calendar_gap.close()

    account_gap, start_at, end_at = _one_period_fixture()
    account_gap.execute(
        "INSERT INTO silver.accounts VALUES ('account-2', 'second', 'isa', 'KRW', ?, NULL, '{}')",
        [start_at - timedelta(days=1)],
    )
    outcome = PortfolioPerformanceEvaluator(account_gap).evaluate_period_and_store(
        prior_date=start_at.date(), current_date=end_at.date(), evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run", evaluation_run_id="account-gap-run",
    )
    assert outcome.quality_status == "prior_account_coverage_mismatch"
    assert all(value.value is None for value in outcome.values)
    account_gap.close()


def test_reversed_state_cutoff_is_a_nullable_quality_outcome() -> None:
    connection = _connection()
    prior_at = datetime(2026, 3, 10, 8, tzinfo=UTC)
    current_at = datetime(2026, 3, 10, 7, tzinfo=UTC)
    prior_date = date(2026, 3, 9)
    current_date = date(2026, 3, 10)
    _account(connection, prior_at - timedelta(days=2))
    _calendar(connection, [current_date])
    _state(connection, day=prior_date, as_of=prior_at, position_value="600", cash_value="400")
    _state(connection, day=current_date, as_of=current_at, position_value="660", cash_value="440")

    outcome = PortfolioPerformanceEvaluator(connection).evaluate_period_and_store(
        prior_date=prior_date,
        current_date=current_date,
        evaluation_slot=SLOT,
        cash_coverage_run_id="unused",
        evaluation_run_id="reversed-cutoff-run",
    )
    assert outcome.quality_status == "invalid_state_order"
    assert all(value.value is None for value in outcome.values)
    assert {value.evaluation_at for value in outcome.values} == {prior_at}
    connection.close()


def test_chain_linked_wealth_and_drawdown_do_not_use_absolute_asset_high() -> None:
    connection = _connection()
    first = datetime(2026, 4, 1, 7, tzinfo=UTC)
    second = first + timedelta(days=1)
    third = second + timedelta(days=1)
    _account(connection, first - timedelta(days=1))
    _calendar(connection, [second.date(), third.date()])
    _state(connection, day=first.date(), as_of=first, position_value="600", cash_value="400")
    _state(connection, day=second.date(), as_of=second, position_value="660", cash_value="440")
    _state(connection, day=third.date(), as_of=third, position_value="594", cash_value="396")
    _coverage(
        connection, result_id="coverage-chain-1", run_id="coverage-run",
        start_at=first, end_at=second,
    )
    _coverage(
        connection, result_id="coverage-chain-2", run_id="coverage-run",
        start_at=first, end_at=third,
    )

    outcomes = PortfolioPerformanceEvaluator(connection).evaluate_history_and_store(
        evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run",
        evaluation_run_id="chain-run",
    )
    assert len(outcomes) == 2
    second_values = {value.definition.metric_id: value.value for value in outcomes[0].values if value.subject_type == "portfolio"}
    third_values = {value.definition.metric_id: value.value for value in outcomes[1].values if value.subject_type == "portfolio"}
    assert second_values[RETURN_METRIC] == Decimal("0.1000000000")
    assert second_values[WEALTH_METRIC] == Decimal("1.1000000000")
    assert third_values[RETURN_METRIC] == Decimal("-0.1000000000")
    assert third_values[WEALTH_METRIC] == Decimal("0.9900000000")
    assert third_values[DRAWDOWN_METRIC] == Decimal("-0.1000000000")
    connection.close()


def test_chain_gap_does_not_restart_wealth_at_one() -> None:
    connection = _connection()
    first = datetime(2026, 5, 1, 7, tzinfo=UTC)
    second = first + timedelta(days=1)
    third = second + timedelta(days=1)
    _account(connection, first - timedelta(days=1))
    _calendar(connection, [second.date(), third.date()])
    _state(connection, day=first.date(), as_of=first, position_value="600", cash_value="400")
    _state(connection, day=second.date(), as_of=second, position_value="660", cash_value="440")
    _state(connection, day=third.date(), as_of=third, position_value="726", cash_value="484")
    _cash_event(
        connection, event_type="unknown", amount="1",
        effective_at=first + timedelta(hours=1), knowledge_at=first + timedelta(hours=2),
    )
    _coverage(
        connection, result_id="coverage-gap-1", run_id="coverage-run",
        start_at=first, end_at=second,
    )
    _coverage(
        connection, result_id="coverage-gap-2", run_id="coverage-run",
        start_at=first, end_at=third,
    )
    outcomes = PortfolioPerformanceEvaluator(connection).evaluate_history_and_store(
        evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run",
        evaluation_run_id="chain-gap-run",
    )
    assert outcomes[0].quality_status == "unclassified_cash_flow"
    assert outcomes[1].quality_status == "pass"
    later = {value.definition.metric_id: value for value in outcomes[1].values if value.subject_type == "portfolio"}
    assert later[RETURN_METRIC].value == Decimal("0.1000000000")
    assert later[WEALTH_METRIC].value is None
    assert later[WEALTH_METRIC].quality_status == "chain_gap"
    assert later[DRAWDOWN_METRIC].value is None
    connection.close()


def test_performance_metrics_survive_complete_backup_restore(tmp_path: Path) -> None:
    connection, start_at, end_at = _one_period_fixture()
    PortfolioPerformanceEvaluator(connection).evaluate_period_and_store(
        prior_date=start_at.date(), current_date=end_at.date(), evaluation_slot=SLOT,
        cash_coverage_run_id="coverage-run", evaluation_run_id="restore-run",
    )
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    manifest: dict[str, object] = {
        "manifest_version": 2,
        "tables": {},
        "object_bytes_included": False,
    }
    for qualified in v2_backup_table_names():
        schema, table = qualified.split(".", 1)
        directory = backup_dir / schema
        directory.mkdir(exist_ok=True)
        path = directory / f"{table}.parquet"
        quoted_path = "'" + str(path).replace("'", "''") + "'"
        connection.execute(f"COPY (SELECT * FROM {qualified}) TO {quoted_path} (FORMAT PARQUET)")
        manifest["tables"][qualified] = {
            "rows": connection.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0],
            "path": f"{schema}/{table}.parquet",
        }
    connection.close()
    (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restored.duckdb"
    completed = subprocess.run(
        [sys.executable, "scripts/restore_v2_backup.py", str(backup_dir), "--database", str(target)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"tables={len(v2_backup_table_names())}" in completed.stdout
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        "SELECT value_decimal FROM gold.metric_values WHERE metric_id=?",
        [RETURN_METRIC],
    ).fetchone()[0] == Decimal("0.0952380952")
    assert restored.execute(
        "SELECT count(*) FROM control.metric_definitions WHERE metric_id IN (?, ?, ?, ?, ?)",
        [RETURN_METRIC, CONTRIBUTION_METRIC, RESIDUAL_METRIC, WEALTH_METRIC, DRAWDOWN_METRIC],
    ).fetchone()[0] == 5
    restored.close()
