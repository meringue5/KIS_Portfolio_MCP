from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

import duckdb

from kis_portfolio.adapters.outbound.thread_risk_review_warehouse import ThreadRiskReviewWarehouse
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.application.lot_thread_risk import (
    LotThreadRiskEvaluator,
    inspect_lot_thread_risk_readiness,
)
from kis_portfolio.modules.portfolio.thread_risk import (
    RiskPlanAuthority,
    ThreadRiskPlanDraft,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


EVALUATION_AT = datetime(2026, 8, 28, 7, tzinfo=UTC)
ACCOUNT_ID = "account-1"
INSTRUMENT_ID = "instrument-1"
QUANTUM = Decimal("0.0000000001")


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection


def _seed_account_and_state(
    connection: duckdb.DuckDBPyConnection,
    *,
    evaluation_at: datetime = EVALUATION_AT,
    slot: str = "kr-1600",
    quantity: str = "6",
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO silver.accounts(
            account_id,account_label,account_type,base_currency,valid_from,valid_to,provenance
        ) VALUES (?,?,?,'KRW',?,NULL,'{}')
        """,
        [ACCOUNT_ID, "fixture", "brokerage", evaluation_at - timedelta(days=365)],
    )
    connection.execute(
        """
        INSERT INTO gold.portfolio_daily_state(
            evaluation_date,evaluation_slot,account_id,instrument_id,aggregate_level,
            quantity,value_krw,cost_krw,unrealized_pnl_krw,contribution_pct,
            allocation_pct,as_of,input_watermarks,quality_status,lineage_hash
        ) VALUES
          (?,?,?,?, 'position',?,9000,6000,3000,NULL,NULL,?,'{}','pass',?),
          (?,?,?,'cash|KRW','cash',NULL,1000,NULL,NULL,NULL,NULL,?,'{}','pass',?)
        """,
        [
            evaluation_at.date(), slot, ACCOUNT_ID, INSTRUMENT_ID, quantity,
            evaluation_at, f"state-position-{evaluation_at.isoformat()}-{slot}",
            evaluation_at.date(), slot, ACCOUNT_ID, evaluation_at,
            f"state-cash-{evaluation_at.isoformat()}-{slot}",
        ],
    )


def _seed_episode(
    connection: duckdb.DuckDBPyConnection,
    *,
    episode_id: str,
    opened_at: datetime,
    quantity: str,
    closed_at: datetime | None = None,
    revision: int = 1,
    knowledge_at: datetime | None = None,
) -> None:
    knowledge_at = knowledge_at or EVALUATION_AT - timedelta(hours=2)
    connection.execute(
        """
        INSERT OR IGNORE INTO silver.position_episodes(
            episode_id,account_id,opening_instrument_id,opened_at,identity_hash,first_run_id
        ) VALUES (?,?,?,?,?,?)
        """,
        [episode_id, ACCOUNT_ID, INSTRUMENT_ID, opened_at, f"identity-{episode_id}", "fixture-run"],
    )
    connection.execute(
        """
        INSERT INTO silver.position_episode_revisions(
            position_episode_revision_id,episode_id,revision,instrument_id,episode_status,closed_at,
            reconstruction_start_at,reconstruction_cutoff_at,knowledge_at,current_quantity,
            replayed_quantity,inferred_opening_quantity,evidence_provenance,reconstruction_status,
            coverage_quality_result_id,blockers,provenance
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,'actual','reconstructed','coverage-pass','[]','{}')
        """,
        [
            f"{episode_id}-revision-{revision}", episode_id, revision, INSTRUMENT_ID,
            "closed" if closed_at else "open", closed_at, opened_at,
            knowledge_at - timedelta(minutes=1), knowledge_at, quantity, quantity,
        ],
    )


def _seed_lot(
    connection: duckdb.DuckDBPyConnection,
    *,
    lot_id: str,
    episode_id: str,
    opened_at: datetime,
    quantity: str,
    remaining: str,
    unit_cost: str,
    thread_id: str,
    revision: int = 1,
    knowledge_at: datetime | None = None,
) -> None:
    knowledge_at = knowledge_at or EVALUATION_AT - timedelta(hours=2)
    connection.execute(
        """
        INSERT OR IGNORE INTO silver.purchase_lot_identities(
            lot_id,episode_id,account_id,opening_instrument_id,opening_trade_event_id,
            opened_at,evidence_provenance,identity_hash,first_run_id
        ) VALUES (?,?,?,?,?,?, 'actual',?,?)
        """,
        [lot_id, episode_id, ACCOUNT_ID, INSTRUMENT_ID, f"buy-{lot_id}", opened_at,
         f"identity-{lot_id}", "fixture-run"],
    )
    connection.execute(
        """
        INSERT INTO silver.purchase_lot_revisions(
            purchase_lot_revision_id,lot_id,revision,revision_hash,effective_quantity,
            remaining_quantity,effective_unit_cost,currency,reconstruction_status,effective_at,
            knowledge_at,cause_type,cause_ref,quality_status,blockers,provenance
        ) VALUES (?,?,?,?,?,?,?,'KRW','reconstructed',?,?,'buy_trade',?,'pass','[]','{}')
        """,
        [f"{lot_id}-revision-{revision}", lot_id, revision, f"hash-{lot_id}-{revision}",
         quantity, remaining, unit_cost, knowledge_at, knowledge_at, f"buy-{lot_id}"],
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO silver.trade_threads(
            thread_id,account_id,instrument_id,opened_at,closed_at,title,status,revision,provenance
        ) VALUES (?,?,?,?,NULL,'fixture','open',1,'{}')
        """,
        [thread_id, ACCOUNT_ID, INSTRUMENT_ID, opened_at],
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO silver.trade_thread_lots(
            thread_id,lot_id,allocation_revision,linked_at,linkage_quality
        ) VALUES (?,?,1,?,'explicit')
        """,
        [thread_id, lot_id, opened_at],
    )


def _seed_prices(
    connection: duckdb.DuckDBPyConnection,
    bars: tuple[tuple[date, str, str, str], ...],
    *,
    knowledge_at: datetime | None = None,
) -> None:
    knowledge_at = knowledge_at or EVALUATION_AT - timedelta(hours=1)
    payload = {"fixture": "lot-thread-risk", "bars": bars}
    observation = SourceEnvelope(
        "source.kis-open-api", f"price-{hashlib.sha256(repr(bars).encode()).hexdigest()}",
        knowledge_at, knowledge_at, payload,
        hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest(),
        "pass",
    )
    warehouse = V2WarehouseRepository(connection)
    observation_id = warehouse.record_observation(
        "dataset.price-bar-daily", observation, "price-fixture-run"
    )
    warehouse.upsert_price_bars([
        {
            "instrument_id": INSTRUMENT_ID,
            "session_date": session_date,
            "price_basis": "adjusted",
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 100,
            "effective_at": datetime.combine(session_date, datetime.min.time(), tzinfo=UTC),
            "knowledge_at": knowledge_at,
            "endpoint": "fixture.adjusted-history",
            "request_option": "adjusted",
            "volume_basis": "vendor_reported",
            "reconstruction_mode": "operational_strict",
            "quality_status": "pass",
        }
        for session_date, high, low, close in bars
    ], observation_id)


def _seed_owner_plan(
    connection: duckdb.DuckDBPyConnection,
    *,
    thread_id: str = "thread-1",
    knowledge_at: datetime | None = None,
) -> None:
    knowledge_at = knowledge_at or EVALUATION_AT - timedelta(minutes=30)
    ThreadRiskReviewWarehouse(connection).append_risk_plan(
        ThreadRiskPlanDraft(
            thread_id=thread_id,
            reference_price=Decimal("120"),
            stop_price=Decimal("90"),
            currency="KRW",
            risk_budget_ratio=Decimal("0.02"),
            effective_at=EVALUATION_AT - timedelta(days=10),
            knowledge_at=knowledge_at,
            authority_source=RiskPlanAuthority.OWNER_CONFIRMED,
            advice_metadata={"atr_2n_suggested_stop": "88", "authoritative": False},
            provenance={"fixture": "owner-confirmed"},
        ),
        expected_prior_revision=0,
        actor_type="owner",
    )


def _seed_open_fixture(connection: duckdb.DuckDBPyConnection, *, owner_plan: bool = True) -> None:
    opened_at = EVALUATION_AT - timedelta(days=20)
    _seed_account_and_state(connection)
    _seed_episode(connection, episode_id="episode-1", opened_at=opened_at, quantity="6")
    _seed_lot(
        connection, lot_id="lot-1", episode_id="episode-1", opened_at=opened_at,
        quantity="4", remaining="4", unit_cost="100", thread_id="thread-1",
    )
    _seed_lot(
        connection, lot_id="lot-2", episode_id="episode-1", opened_at=opened_at,
        quantity="2", remaining="2", unit_cost="110", thread_id="thread-1",
    )
    _seed_prices(connection, (
        ((EVALUATION_AT - timedelta(days=19)).date(), "125", "95", "110"),
        ((EVALUATION_AT - timedelta(days=10)).date(), "130", "80", "100"),
        (EVALUATION_AT.date(), "120", "100", "115"),
    ))
    if owner_plan:
        _seed_owner_plan(connection)


def _evaluate(
    connection: duckdb.DuckDBPyConnection,
    *,
    evaluation_at: datetime = EVALUATION_AT,
    slot: str = "kr-1600",
    run_id: str = "risk-fixture-run",
):
    return LotThreadRiskEvaluator(connection).evaluate_and_store(
        evaluation_at=evaluation_at,
        evaluation_slot=slot,
        evaluation_run_id=run_id,
    )


def test_lot_episode_thread_and_instrument_metrics_match_sql_golden_and_replay() -> None:
    connection = _connection()
    _seed_open_fixture(connection)

    first = {(value.definition.metric_id, value.subject_id): value for value in _evaluate(connection)}
    assert len(first) == 10
    assert first[("metric.lot-mfe-adjusted-price", "lot-1")].value == Decimal("0.3000000000")
    assert first[("metric.lot-mae-adjusted-price", "lot-1")].value == Decimal("-0.2000000000")
    assert first[("metric.lot-mfe-adjusted-price", "lot-2")].value == (
        Decimal("130") / Decimal("110") - 1
    ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    assert first[("metric.position-episode-high-adjusted-price", "episode-1")].value == Decimal("130.0000000000")
    assert first[("metric.position-episode-drawdown-adjusted-price", "episode-1")].value == (
        Decimal("115") / Decimal("130") - 1
    ).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    assert first[("metric.thread-planned-loss-krw", "thread-1")].value == Decimal("180.0000000000")
    assert first[("metric.thread-risk-ratio", "thread-1")].value == Decimal("0.0180000000")
    assert first[("metric.instrument-planned-loss-krw", INSTRUMENT_ID)].value == Decimal("180.0000000000")

    sql_high, sql_drawdown, sql_loss = connection.execute(
        """
        WITH bars AS (
            SELECT max(high) high,max_by(close,session_date) closing_price
            FROM silver.price_bar_revisions_daily
            WHERE instrument_id=? AND price_basis='adjusted' AND knowledge_at<=?
        ), quantities AS (
            SELECT sum(remaining_quantity) quantity
            FROM silver.purchase_lot_states_current
        )
        SELECT high,closing_price/high-1,quantity*(120-90) FROM bars,quantities
        """,
        [INSTRUMENT_ID, EVALUATION_AT],
    ).fetchone()
    assert first[("metric.position-episode-high-adjusted-price", "episode-1")].value == Decimal(str(sql_high)).quantize(QUANTUM)
    assert first[("metric.position-episode-drawdown-adjusted-price", "episode-1")].value == Decimal(str(sql_drawdown)).quantize(QUANTUM)
    assert first[("metric.thread-planned-loss-krw", "thread-1")].value == Decimal(str(sql_loss)).quantize(QUANTUM)

    replay = _evaluate(connection, run_id="risk-fixture-replay")
    assert len(replay) == 10
    assert connection.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0] == 10
    connection.close()


def test_missing_or_future_owner_plan_keeps_risk_null_while_path_metrics_pass() -> None:
    for future_plan in (False, True):
        connection = _connection()
        _seed_open_fixture(connection, owner_plan=False)
        if future_plan:
            _seed_owner_plan(connection, knowledge_at=EVALUATION_AT + timedelta(minutes=1))
        values = {(item.definition.metric_id, item.subject_id): item for item in _evaluate(connection)}
        for metric_id in (
            "metric.thread-planned-loss-krw", "metric.thread-risk-ratio",
            "metric.instrument-planned-loss-krw", "metric.instrument-risk-ratio",
        ):
            item = values[(metric_id, "thread-1" if metric_id.startswith("metric.thread") else INSTRUMENT_ID)]
            assert item.value is None
            assert item.quality_status in {"missing_owner_risk_plan", "incomplete_thread_risk"}
        assert values[("metric.lot-mfe-adjusted-price", "lot-1")].quality_status == "pass"
        connection.close()


def test_partial_exit_changes_only_open_quantity_risk_deterministically() -> None:
    connection = _connection()
    _seed_open_fixture(connection)
    later = EVALUATION_AT + timedelta(days=1)
    connection.execute(
        """
        INSERT INTO silver.position_episode_revisions(
            position_episode_revision_id,episode_id,revision,instrument_id,episode_status,closed_at,
            reconstruction_start_at,reconstruction_cutoff_at,knowledge_at,current_quantity,
            replayed_quantity,inferred_opening_quantity,evidence_provenance,reconstruction_status,
            coverage_quality_result_id,blockers,provenance
        ) VALUES ('episode-1-revision-2','episode-1',2,?,'open',NULL,?,?,?,?,?,NULL,
                  'actual','reconstructed','coverage-pass','[]','{}')
        """,
        [INSTRUMENT_ID, EVALUATION_AT - timedelta(days=20), later - timedelta(hours=2),
         later - timedelta(hours=1), "5", "5"],
    )
    connection.execute(
        """
        INSERT INTO silver.purchase_lot_revisions(
            purchase_lot_revision_id,lot_id,revision,revision_hash,effective_quantity,
            remaining_quantity,effective_unit_cost,currency,reconstruction_status,effective_at,
            knowledge_at,cause_type,cause_ref,quality_status,blockers,provenance
        ) VALUES ('lot-1-revision-2','lot-1',2,'hash-lot-1-2',4,3,100,'KRW',
                  'reconstructed',?,?,'sell_allocation','allocation-1|1','pass','[]','{}')
        """,
        [later - timedelta(hours=2), later - timedelta(hours=1)],
    )
    _seed_account_and_state(connection, evaluation_at=later, slot="kr-1600", quantity="5")
    _seed_prices(connection, ((later.date(), "121", "101", "116"),), knowledge_at=later - timedelta(minutes=30))

    values = {(item.definition.metric_id, item.subject_id): item for item in _evaluate(
        connection, evaluation_at=later, run_id="partial-exit-run"
    )}
    assert values[("metric.thread-planned-loss-krw", "thread-1")].value == Decimal("150.0000000000")
    assert values[("metric.thread-risk-ratio", "thread-1")].value == Decimal("0.0150000000")
    connection.close()


def test_quantity_mismatch_fails_closed_and_later_episode_does_not_cross_old_boundary() -> None:
    mismatch = _connection()
    _seed_open_fixture(mismatch)
    mismatch.execute(
        "UPDATE gold.portfolio_daily_state SET quantity=7 WHERE aggregate_level='position'"
    )
    values = _evaluate(mismatch)
    assert values
    assert {item.quality_status for item in values} == {"canonical_position_quantity_mismatch"}
    assert all(item.value is None for item in values)
    mismatch.close()

    connection = _connection()
    first_open = EVALUATION_AT - timedelta(days=30)
    first_close = EVALUATION_AT - timedelta(days=10)
    second_open = EVALUATION_AT - timedelta(days=5)
    _seed_account_and_state(connection, quantity="2")
    _seed_episode(
        connection, episode_id="episode-old", opened_at=first_open, quantity="0", closed_at=first_close
    )
    _seed_lot(
        connection, lot_id="lot-old", episode_id="episode-old", opened_at=first_open,
        quantity="2", remaining="0", unit_cost="100", thread_id="thread-old",
    )
    _seed_episode(connection, episode_id="episode-new", opened_at=second_open, quantity="2")
    _seed_lot(
        connection, lot_id="lot-new", episode_id="episode-new", opened_at=second_open,
        quantity="2", remaining="2", unit_cost="200", thread_id="thread-new",
    )
    _seed_owner_plan(connection, thread_id="thread-new")
    _seed_prices(connection, (
        ((first_open + timedelta(days=1)).date(), "130", "90", "120"),
        (first_close.date(), "125", "100", "110"),
        (second_open.date(), "250", "180", "230"),
        (EVALUATION_AT.date(), "300", "200", "280"),
    ))
    evaluated = {(item.definition.metric_id, item.subject_id): item for item in _evaluate(connection)}
    assert evaluated[("metric.position-episode-high-adjusted-price", "episode-old")].value == Decimal("130.0000000000")
    assert evaluated[("metric.position-episode-high-adjusted-price", "episode-new")].value == Decimal("300.0000000000")
    connection.close()


def test_readiness_is_aggregate_only_and_has_no_side_effects() -> None:
    connection = _connection()
    _seed_open_fixture(connection)
    before = connection.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0]
    report = inspect_lot_thread_risk_readiness(connection)
    assert report["status"] == "ready"
    assert report["thread_links"] == {
        "open_lots": 2, "exactly_one": 2, "covered_threads": 1
    }
    assert report["owner_plans"] == {"current_rows": 1}
    assert report["side_effects"] == "none"
    serialized = str(report)
    assert ACCOUNT_ID not in serialized
    assert INSTRUMENT_ID not in serialized
    assert connection.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0] == before
    connection.close()


def test_lot_thread_metric_values_survive_complete_backup_restore(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    _seed_open_fixture(source)
    _evaluate(source)
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()

    assert manifest["tables"]["gold.metric_values"]["rows"] == 10
    assert manifest["tables"]["control.metric_definitions"]["rows"] == 8
    target = tmp_path / "restored.duckdb"
    result = restore_v2_backup(backup, target)
    assert result["status"] == "verified"
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        """
        SELECT value_decimal,quality_status FROM gold.metric_values
        WHERE metric_id='metric.thread-planned-loss-krw' AND subject_id='thread-1'
        """
    ).fetchone() == (Decimal("180.0000000000"), "pass")
    assert restored.execute(
        "SELECT count(*) FROM gold.metric_values WHERE value_decimal IS NULL"
    ).fetchone()[0] == 0
    restored.close()
