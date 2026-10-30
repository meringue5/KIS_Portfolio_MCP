from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json

import duckdb
import pytest

from kis_portfolio.adapters.outbound.cash_observation_history import CashObservationHistory
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.adapters.outbound.remote_v2_warehouse import WarehouseReadQueryPort
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_collection import _envelope
from kis_portfolio.services.remote_read_surface import RemoteReadApplication, ReadActor, RemoteReadError

AT = datetime(2026, 10, 30, 7, tzinfo=UTC)


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    MigrationRunner(c).apply()
    c.execute("INSERT INTO silver.accounts VALUES ('private-account','brokerage','REAL','KRW',current_timestamp,NULL,'{}')")
    yield c
    c.close()


def observation(con, amount, at, *, currency="USD", known=None, run="run", key=None):
    payload = dict(account_id="private-account", currency=currency, amount=amount,
        quality_status="pass", as_of=at.isoformat())
    obs = V2WarehouseRepository(con).record_observation("dataset.portfolio-position-observation",
        _envelope(key or f"fixture:{at}:{currency}:{amount}:cash", payload, at, fetched_at=known or at), run)
    con.execute("UPDATE bronze.source_observations SET created_at=? WHERE observation_id=?", [known or at, obs])
    return obs


def test_rp_like_movements_are_unknown_observed_changes_not_cash_flows(con):
    for days, amount in [(2, "100.00"), (1, "0.00"), (0, "100.00")]:
        observation(con, amount, AT-timedelta(days=days))
    data=CashObservationHistory(con,clock=lambda:AT).read()["data"]
    assert [r["change"] for r in data["results"]] == ["100.00", "-100.00", None]
    assert all(r["cause"]=="unknown" and not r["performance_eligible"] for r in data["results"])
    assert data["latest"][-1]["amount"]=="100.00"
    assert con.execute("SELECT count(*) FROM silver.cash_flow_events").fetchone()[0]==0
    assert con.execute("SELECT count(*) FROM control.cash_balance_reconciliations").fetchone()[0]==0


def test_missing_currency_never_becomes_zero_or_fabricated_movement(con):
    observation(con,"25",AT-timedelta(days=2))
    observation(con,"1000",AT,currency="KRW")
    data=CashObservationHistory(con,clock=lambda:AT).read()["data"]
    last=data["latest"][-1]
    assert last["amount"]=="25" and last["age_seconds"]==172800 and last["status"]=="last_known"
    assert len([r for r in data["results"] if r["currency"]=="USD"])==1
    assert data["latest"][0]["amount"] is None and data["latest"][0]["status"]=="unavailable"


def test_immutable_bronze_recording_cutoff_and_snapshot_paging(con):
    for days in [2,1,0]:observation(con,str(100+days),AT-timedelta(days=days))
    repo=CashObservationHistory(con,clock=lambda:AT)
    first=repo.read(limit=1)
    # An older late-arriving observation cannot change cursor pages or the old-cutoff read.
    observation(con,"999",AT-timedelta(hours=12),known=AT+timedelta(hours=1))
    second=repo.read(limit=1,cursor=first["data"]["next_cursor"])
    assert second["data"]["results"][0]["amount"]=="101"
    assert len(repo.read()["data"]["results"])==3
    with pytest.raises(ValueError,match="invalid_cash_history_cursor"):
        repo.read(lookback_days=1,cursor=first["data"]["next_cursor"])
    with pytest.raises(ValueError,match="invalid_cash_history_cursor"):
        repo.read(cursor="malformed")
    with pytest.raises(ValueError,match="invalid_cash_history_bounds"):
        repo.read(limit=101)


def test_conflicting_or_float_observation_does_not_invent_a_balance(con):
    observation(con,"12",AT,key="a")
    observation(con,"18",AT,key="b")
    result=CashObservationHistory(con,clock=lambda:AT).read()["data"]["results"][0]
    assert result["amount"] is None and result["change"] is None
    assert "ambiguous_or_invalid_observation" in result["warnings"]


@pytest.mark.parametrize("value",[1.2,True,"NaN","Infinity","0.000000001"])
def test_invalid_numeric_input_is_not_reported_as_zero(con,value):
    observation(con,value,AT)
    result=CashObservationHistory(con,clock=lambda:AT).read()["data"]["results"][0]
    assert result["amount"] is None and result["change"] is None


def test_negative_cash_and_small_changes_preserve_decimal_precision(con):
    observation(con,"-100.00000001",AT-timedelta(days=1))
    observation(con,"-100.00000002",AT)
    result=CashObservationHistory(con,clock=lambda:AT).read()["data"]["results"][0]
    assert result["amount"]=="-100.00000002" and result["change"]=="-0.00000001"
    absent=CashObservationHistory(con,clock=lambda:AT).read(run_id="absent")["data"]
    assert absent["results"]==[] and all(x["amount"] is None for x in absent["latest"])


def test_trade_context_does_not_claim_cash_posting_or_subtract_notional(con):
    observation(con,"100",AT-timedelta(days=1))
    obs=observation(con,"150",AT)
    con.execute("""INSERT INTO silver.trade_event_revisions
        (trade_event_revision_id,source_trade_event_id,account_id,market,product_code,instrument_id,
        broker_order_id,executed_at,execution_sequence,revision,side,quantity,price,currency,
        knowledge_at,source_observation_id,correction_reason,quality_status,metadata)
        VALUES ('r','t','private-account','NAS','01','NAS|ABC','private-order',?,'aggregate',1,
        'buy',2,10,'USD',?,?,'source_event','pass','{}')""", [AT-timedelta(hours=1),AT,obs])
    result=CashObservationHistory(con,clock=lambda:AT).read()["data"]["results"][0]
    assert result["change"]=="50" and result["cause"]=="unknown"
    assert len(result["trade_context"])==1
    assert result["trade_context_status"]=="execution_interval_only_incomplete"
    assert "private-order" not in json.dumps(result) and "private-account" not in json.dumps(result)


@pytest.mark.anyio
async def test_existing_read_transport_inactive_positive_partial_error(con,monkeypatch):
    app=RemoteReadApplication(WarehouseReadQueryPort(con),expected_resource="https://fixture.test/mcp")
    actor=ReadActor("owner","fixture",frozenset({"mcp:read"}),"https://fixture.test/mcp","test-request")
    request=dict(dataset_id="dataset.cash-observation-history",as_of=AT.isoformat())
    with pytest.raises(RemoteReadError,match="cash_observation_history_inactive"):
        await app.execute("get-data-quality",request,actor)
    monkeypatch.setenv("KIS_CASH_OBSERVATION_HISTORY_ENABLED","true")
    empty=await app.execute("get-data-quality",request,actor)
    assert empty["quality"]["status"]=="partial" and empty["data"]["results"]==[]
    observation(con,"10",AT)
    result=await app.execute("get-data-quality",request,actor)
    assert result["data"]["results"][0]["amount"]=="10"
    with pytest.raises(RemoteReadError,match="invalid_cash_history_cursor"):
        await app.execute("get-data-quality",{**request,"cursor":"bad"},actor)
    with pytest.raises(RemoteReadError,match="insufficient_scope"):
        await app.execute("get-data-quality",request,ReadActor("owner","fixture",frozenset(),"https://fixture.test/mcp","test-request"))


@pytest.fixture
def anyio_backend():
    return "asyncio"
