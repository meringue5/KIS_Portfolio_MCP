from dataclasses import dataclass
from datetime import UTC, date, datetime

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services import v2_collection


@dataclass
class FakeAccount:
    label: str


class FakeObjectStore:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        import hashlib
        digest = hashlib.sha256(payload).hexdigest()
        self.objects[digest] = payload
        return StoredObject(f"gs://private/{digest}", digest, len(payload), media_type, True)

    def download(self, uri, destination, *, expected_sha256=None):
        digest = uri.rsplit("/", 1)[-1]
        assert expected_sha256 in (None, digest)
        destination.write_bytes(self.objects[digest])
        return destination


def test_managed_collection_is_calendar_gated_governed_and_idempotent(monkeypatch):
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("CREATE TABLE main.market_calendar(market VARCHAR, trade_date DATE, is_open BOOLEAN, note VARCHAR)")
    con.execute("CREATE TABLE main.price_history(exchange VARCHAR, symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, adjusted BOOLEAN, created_at TIMESTAMP)")
    con.execute("CREATE TABLE main.exchange_rate_history(currency VARCHAR, date DATE, rate DOUBLE)")
    con.execute("INSERT INTO main.market_calendar VALUES ('krx', '2026-08-28', true, NULL)")
    con.execute("INSERT INTO main.price_history VALUES ('KRX','005930','2026-08-28',70000,73000,69000,72000,100,false,'2026-08-28 07:00:00')")
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)

    async def fake_collect(slot):
        return {
            "domestic": [{
                "account_label": "ria", "account_type": "REAL", "snapshot_id": "snapshot-1",
                "observed_at": observed,
                "raw": {
                    "output1": [{
                        "pdno": "005930", "prdt_name": "Synthetic", "hldg_qty": "2",
                        "pchs_avg_pric": "70000", "evlu_amt": "144000",
                    }],
                    "output2": [{"tot_evlu_amt": "150000"}],
                },
            }],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 2,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])
    first = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1600", object_store=FakeObjectStore(),
    )
    second = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1600", object_store=FakeObjectStore(),
    )
    assert first["status"] == "succeeded" and first["source_calls"] == 2
    assert second["status"] == "succeeded" and second["reused"] is True
    assert con.execute("select count(*) from bronze.raw_object_manifest").fetchone()[0] == 1
    assert con.execute("select count(*) from control.quality_results").fetchone()[0] == 1
    assert con.execute("select count(*) from control.lineage_edges").fetchone()[0] == 3
    assert con.execute("select count(*) from control.watermarks").fetchone()[0] == 1
    assert con.execute("select count(*) from gold.portfolio_daily_state").fetchone()[0] == 2
    assert con.execute("select count(*) from silver.instrument_versions").fetchone()[0] == 1


def test_managed_collection_skips_declared_closed_day():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("CREATE TABLE main.market_calendar(market VARCHAR, trade_date DATE, is_open BOOLEAN, note VARCHAR)")
    con.execute("INSERT INTO main.market_calendar VALUES ('krx', '2026-08-29', false, 'weekend')")
    result = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 29), slot="kr-1000", object_store=FakeObjectStore(),
    )
    assert result == {
        "status": "skipped", "reason": "market_closed:weekend",
        "logical_date": "2026-08-29", "slot": "kr-1000",
    }


def test_managed_collection_resumes_from_landed_bundle_without_source_recall(monkeypatch):
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("CREATE TABLE main.market_calendar(market VARCHAR, trade_date DATE, is_open BOOLEAN, note VARCHAR)")
    con.execute("CREATE TABLE main.price_history(exchange VARCHAR, symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, adjusted BOOLEAN, created_at TIMESTAMP)")
    con.execute("CREATE TABLE main.exchange_rate_history(currency VARCHAR, date DATE, rate DOUBLE)")
    con.execute("INSERT INTO main.market_calendar VALUES ('krx','2026-08-28',true,NULL)")
    con.execute("INSERT INTO main.price_history VALUES ('KRX','005930','2026-08-28',1,1,1,1,1,false,'2026-08-28 07:00:00')")
    calls = {"count": 0}

    async def fake_collect(slot):
        calls["count"] += 1
        return {
            "domestic": [{"account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                "observed_at": datetime(2026, 8, 28, 7, tzinfo=UTC),
                "raw": {"output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "1"}],
                        "output2": [{"tot_evlu_amt": "2"}]} }],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 1, "domestic_symbols": ["005930"], "overseas_symbols": [],
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])
    store = FakeObjectStore()
    first = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1430", object_store=store,
    )
    con.execute("UPDATE control.pipeline_runs SET status='failed' WHERE run_id=?", [first["run_id"]])
    con.execute("UPDATE control.pipeline_stage_runs SET status='failed' WHERE run_id=? AND stage_name='normalize'", [first["run_id"]])
    resumed = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1430", object_store=store,
    )
    assert resumed["status"] == "succeeded"
    assert calls["count"] == 1
    assert con.execute(
        "select attempt from control.pipeline_stage_runs where run_id=? and stage_name='normalize'", [first["run_id"]]
    ).fetchone()[0] == 2
