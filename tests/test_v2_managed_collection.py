from dataclasses import dataclass
from datetime import UTC, date, datetime

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import PipelineExecutionError
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
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx', '2026-08-28', true, NULL)")
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
            "price_observations": [{
                "market": "KRX", "symbol": "005930", "adjusted": False,
                "fetched_at": observed,
                "raw": {"output2": [{
                    "stck_bsop_date": "20260828", "stck_oprc": "70000",
                    "stck_hgpr": "73000", "stck_lwpr": "69000",
                    "stck_clpr": "72000", "acml_vol": "100",
                }, {
                    "stck_bsop_date": "20260827", "stck_oprc": "69000",
                    "stck_hgpr": "71000", "stck_lwpr": "68000",
                    "stck_clpr": "70000", "acml_vol": "90",
                }]},
            }],
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
    quality = con.execute(
        "select dataset_id, rule_id, status, observed_value, expected_value "
        "from control.quality_results order by dataset_id"
    ).fetchall()
    assert quality == [
        ("dataset.portfolio-position-observation", "configured-account-coverage", "pass", "1", "1"),
        ("dataset.price-bar-daily", "held-instrument-price-coverage", "pass", "1", "1"),
    ]
    assert con.execute("select count(*) from control.lineage_edges").fetchone()[0] == 3
    assert con.execute("select count(*) from control.watermarks").fetchone()[0] == 1
    assert con.execute("select count(*) from gold.portfolio_daily_state").fetchone()[0] == 2
    assert con.execute("select count(*) from silver.instrument_versions").fetchone()[0] == 1


def test_price_quality_rejects_one_uncovered_request_among_multirow_history(monkeypatch):
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx','2026-08-28',true,NULL)")
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)
    valid = {"stck_bsop_date": "20260828", "stck_oprc": "1", "stck_hgpr": "1",
             "stck_lwpr": "1", "stck_clpr": "1", "acml_vol": "1"}
    older = {**valid, "stck_bsop_date": "20260827"}
    future = {**valid, "stck_bsop_date": "20260829"}

    async def fake_collect(slot):
        return {
            "domestic": [{"account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                          "observed_at": observed,
                          "raw": {"output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "1"}],
                                  "output2": [{"tot_evlu_amt": "2"}]}}],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 2,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
            "price_observations": [
                {"market": "KRX", "symbol": "005930", "adjusted": False,
                 "fetched_at": observed, "raw": {"output2": [valid, older]}},
                {"market": "KRX", "symbol": "005930", "adjusted": True,
                 "fetched_at": observed, "raw": {"output2": [future]}},
            ],
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])
    with pytest.raises(PipelineExecutionError, match="price coverage failed: 1/2"):
        v2_collection.run_owned_portfolio_pipeline(
            con, logical_date=date(2026, 8, 28), slot="kr-1000", object_store=FakeObjectStore(),
        )
    con.close()


def test_managed_collection_skips_declared_closed_day():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx', '2026-08-29', false, 'weekend')")
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
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx','2026-08-28',true,NULL)")
    calls = {"count": 0}

    async def fake_collect(slot):
        calls["count"] += 1
        return {
            "domestic": [{"account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                "observed_at": datetime(2026, 8, 28, 7, tzinfo=UTC),
                "raw": {"output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "1"}],
                        "output2": [{"tot_evlu_amt": "2"}]} }],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 1,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
            "price_observations": [{
                "market": "KRX", "symbol": "005930", "adjusted": False,
                "fetched_at": datetime(2026, 8, 28, 7, tzinfo=UTC),
                "raw": {"output2": [{
                    "stck_bsop_date": "20260828", "stck_oprc": "1",
                    "stck_hgpr": "1", "stck_lwpr": "1",
                    "stck_clpr": "1", "acml_vol": "1",
                }]},
            }],
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


def test_operational_price_payload_is_landed_as_strict_and_beats_legacy_reconstruction(monkeypatch):
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx','2026-08-28',true,NULL)")
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)

    async def fake_collect(slot):
        assert slot == "kr-1600"
        return {
            "domestic": [{"account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                "observed_at": observed,
                "raw": {"output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "90"}],
                        "output2": [{"tot_evlu_amt": "100"}]}}],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 1,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
            "price_observations": [{
                "market": "KRX", "symbol": "005930", "adjusted": True,
                "fetched_at": observed,
                "raw": {"output2": [{"stck_bsop_date": "20260828", "stck_oprc": "100",
                    "stck_hgpr": "101", "stck_lwpr": "89", "stck_clpr": "90", "acml_vol": "3000"}]},
            }],
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])
    result = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1600", object_store=FakeObjectStore(),
    )
    assert result["status"] == "succeeded"
    rows = con.execute(
        """
        SELECT reconstruction_mode,close FROM silver.price_bar_revisions_daily
        WHERE instrument_id='v1|KRX|005930' AND session_date='2026-08-28' AND price_basis='adjusted'
        """
    ).fetchall()
    assert rows == [("operational_strict", 90)]
    con.close()
