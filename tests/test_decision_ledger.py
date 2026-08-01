import duckdb
import pytest

from kis_portfolio.analytics.asset_overview import get_asset_return_history
from kis_portfolio.db import repository
from kis_portfolio.db.schema import init_schema


@pytest.fixture
def ledger_db(monkeypatch):
    con = duckdb.connect(":memory:")
    init_schema(con)
    monkeypatch.setattr(repository, "get_connection", lambda: con)
    return con


def test_cash_flow_upsert_is_idempotent_and_enforces_signs(ledger_db):
    row = {
        "idempotency_key": "deposit-20260801-brokerage",
        "event_date": "20260801",
        "account_label": "brokerage",
        "flow_type": "deposit",
        "amount_krw": 100_000,
        "note": "initial funding",
    }
    repository.upsert_cash_flow(row)
    repository.upsert_cash_flow({**row, "amount_krw": 120_000})

    assert ledger_db.execute("select count(*), max(amount_krw) from cash_flow").fetchone() == (1, 120_000)
    with pytest.raises(ValueError, match="withdrawal"):
        repository.upsert_cash_flow({
            **row,
            "idempotency_key": "bad-withdrawal",
            "flow_type": "withdrawal",
            "amount_krw": 10,
        })


def test_trade_journal_upsert_keeps_one_decision_record(ledger_db):
    row = {
        "idempotency_key": "decision-aapl-20260801-1",
        "trade_date": "20260801",
        "account_label": "brokerage",
        "symbol": "aapl",
        "side": "buy",
        "quantity": 2,
        "price": 210,
        "currency": "USD",
        "trigger_type": "price",
        "trigger_detail": "support held",
        "exit_plan": "stop below support",
        "principle_check": ["position_size_ok"],
    }
    first_id = repository.upsert_trade_journal(row)
    second_id = repository.upsert_trade_journal({**row, "trigger_detail": "support retest held"})

    assert first_id == second_id
    assert ledger_db.execute("select count(*) from trade_journal").fetchone()[0] == 1
    assert ledger_db.execute("select trigger_detail from trade_journal").fetchone()[0] == "support retest held"


def test_asset_return_view_separates_external_flow_from_performance(ledger_db):
    for days_ago, total in [(1, 1_000_000), (0, 1_200_000)]:
        ledger_db.execute("""
            INSERT INTO asset_overview_snapshots (
                snapshot_at, total_eval_amt_krw, quality_status, quality_flags,
                is_complete, overview_data
            )
            VALUES (current_date - (? * INTERVAL '1 day'), ?, 'ok', '[]', TRUE, '{}')
        """, [days_ago, total])
    repository.upsert_cash_flow({
        "idempotency_key": "deposit-today",
        "event_date": ledger_db.execute("select strftime(current_date, '%Y%m%d')").fetchone()[0],
        "account_label": "brokerage",
        "flow_type": "deposit",
        "amount_krw": 100_000,
    })

    result = get_asset_return_history(ledger_db, days=7)

    latest = result["data"][0]
    assert latest["balance_change_krw"] == 200_000
    assert latest["net_external_flow_krw"] == 100_000
    assert latest["flow_adjusted_change_krw"] == 100_000
    assert latest["daily_twr_return_pct"] == 10.0
    assert result["twr_return_pct"] == 10.0
