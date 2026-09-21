from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import PipelineExecutionError
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
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

    async def fake_collect(slot, *_args, **_kwargs):
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
        ("dataset.fx-rate-daily", "usd-krw-valuation-rate-coverage", "partial", "0", "1"),
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

    async def fake_collect(slot, *_args, **_kwargs):
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


def test_managed_collection_lands_and_normalizes_returned_fx_without_extra_call(monkeypatch):
    """The existing morning FX API response must enter governed Silver, not only V1 cache."""
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("INSERT INTO control.market_calendar(market,trade_date,is_open,note) VALUES ('krx','2026-08-28',true,NULL)")
    observed = datetime(2026, 8, 28, 1, tzinfo=UTC)

    async def fake_collect(slot, *_args, **_kwargs):
        assert slot == "kr-1000"
        return {
            "domestic": [{"account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                          "observed_at": observed,
                          "raw": {"output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "1"}],
                                  "output2": [{"tot_evlu_amt": "2"}]}}],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 2,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
            "price_observations": [{
                "market": "KRX", "symbol": "005930", "adjusted": False,
                "fetched_at": observed,
                "raw": {"output2": [{"stck_bsop_date": "20260828", "stck_clpr": "1"}]},
            }],
            "fx_observations": [{
                "base_currency": "USD", "quote_currency": "KRW", "fetched_at": observed,
                "raw": {"output2": [{"xymd": "20260828", "clos": "1300.25"}]},
            }],
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])
    result = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1000", object_store=FakeObjectStore(),
    )

    assert result["status"] == "succeeded" and result["source_calls"] == 2
    assert con.execute(
        "SELECT rate_date,rate,quality_status FROM silver.fx_rates_daily "
        "WHERE base_currency='USD' AND quote_currency='KRW' AND rate_type='close'"
    ).fetchall() == [(date(2026, 8, 28), 1300.25, "pass")]
    assert con.execute(
        "SELECT count(*) FROM bronze.source_observations WHERE dataset_id='dataset.fx-rate-daily'"
    ).fetchone()[0] == 1
    con.close()


def test_managed_collection_uses_typed_fallback_only_after_cross_source_gate(monkeypatch):
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute(
        "INSERT INTO control.market_calendar(market,trade_date,is_open,note) "
        "VALUES ('krx','2026-08-27',true,NULL),('krx','2026-08-28',true,NULL)"
    )
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)
    repository = V2WarehouseRepository(con)
    reference_id = repository.record_observation(
        "dataset.fx-rate-daily",
        SourceEnvelope(
            source_id="source.kis-open-api",
            source_record_id="fixture:usd:20260827",
            observed_at=observed,
            fetched_at=observed,
            payload={"rate": "1300"},
            content_hash="fixture-kis-fx",
        ),
    )
    repository.upsert_fx_rate({
        "base_currency": "USD", "quote_currency": "KRW",
        "rate_date": date(2026, 8, 27), "rate_type": "close",
        "rate": Decimal("1300"), "quality_status": "pass",
    }, reference_id)

    async def fake_collect(slot, *_args, **_kwargs):
        assert slot == "kr-1430"
        return {
            "domestic": [{
                "account_label": "ria", "account_type": "REAL", "snapshot_id": "s",
                "observed_at": observed,
                "raw": {
                    "output1": [{"pdno": "005930", "hldg_qty": "1", "evlu_amt": "1"}],
                    "output2": [{"tot_evlu_amt": "2"}],
                },
            }],
            "overseas": {}, "overseas_deposit": {}, "source_calls": 2,
            "domestic_symbols": ["005930"], "overseas_symbols": [],
            "price_observations": [{
                "market": "KRX", "symbol": "005930", "adjusted": False,
                "fetched_at": observed,
                "raw": {"output2": [{"stck_bsop_date": "20260828", "stck_clpr": "1"}]},
            }],
            "fx_observations": [],
            "fx_fallback_observation": {
                "status": "pass", "provider": "korea-eximbank",
                "requested_date": date(2026, 8, 28), "rate_date": date(2026, 8, 28),
                "fetched_at": observed, "base_currency": "USD", "quote_currency": "KRW",
                "native_rate_field": "deal_bas_r", "rate": Decimal("1305"),
            },
        }

    monkeypatch.setattr(v2_collection, "_collect_sources", fake_collect)
    monkeypatch.setattr(v2_collection, "load_account_registry", lambda: [FakeAccount("ria")])

    result = v2_collection.run_owned_portfolio_pipeline(
        con, logical_date=date(2026, 8, 28), slot="kr-1430", object_store=FakeObjectStore(),
    )

    assert result["status"] == "succeeded"
    assert con.execute(
        "SELECT rate,quality_status FROM silver.fx_rates_daily "
        "WHERE rate_date='2026-08-28' AND rate_type='deal_bas_r'"
    ).fetchall() == [(Decimal("1305.0000000000"), "pass")]
    assert con.execute(
        "SELECT status FROM control.quality_results "
        "WHERE rule_id='usd-krw-valuation-rate-coverage'"
    ).fetchone()[0] == "pass"
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

    async def fake_collect(slot, *_args, **_kwargs):
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

    async def fake_collect(slot, *_args, **_kwargs):
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
