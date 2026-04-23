import asyncio
import os

from kis_portfolio.adapters.mcp import server as portfolio_mcp
from kis_portfolio.services import order_history as order_history_service


def apply_account_env(monkeypatch):
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    for suffix, cano, prdt in [
        ("RIA", "11111111", "01"),
        ("ISA", "22222222", "01"),
        ("BROKERAGE", "33333333", "01"),
        ("IRP", "44444444", "29"),
        ("PENSION", "55555555", "22"),
    ]:
        monkeypatch.setenv(f"KIS_APP_KEY_{suffix}", f"key-{suffix}")
        monkeypatch.setenv(f"KIS_APP_SECRET_{suffix}", f"secret-{suffix}")
        monkeypatch.setenv(f"KIS_CANO_{suffix}", cano)
        monkeypatch.setenv(f"KIS_ACNT_PRDT_CD_{suffix}", prdt)


def test_get_domestic_order_history_prefers_latest_db_snapshot(monkeypatch):
    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "brokerage")
    monkeypatch.setattr(
        order_history_service.kisdb,
        "get_latest_order_history_snapshot",
        lambda *args: {
            "id": "snapshot-1",
            "account_product_code": "01",
            "fetched_at": "2026-04-23T15:35:10",
            "data": {
                "output1": [
                    {
                        "odno": "A-1",
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "ord_dt": "20260423",
                        "ord_qty": "10",
                        "ord_unpr": "60000",
                        "tot_ccld_qty": "10",
                    },
                    {
                        "odno": "A-2",
                        "pdno": "000660",
                        "prdt_name": "SK하이닉스",
                        "ord_dt": "20260423",
                        "ord_qty": "5",
                        "ord_unpr": "120000",
                        "tot_ccld_qty": "2",
                    },
                ]
            },
        },
    )
    monkeypatch.setattr(
        order_history_service.kisdb,
        "get_domestic_orders",
        lambda *args, **kwargs: [
            {
                "order_no": "A-1",
                "order_branch_no": "",
                "symbol": "005930",
                "symbol_name": "삼성전자",
                "order_date": "2026-04-23",
                "order_time": "153001",
                "side_code": "02",
                "side_name": "매수",
                "order_qty": 10,
                "total_order_qty": 10,
                "order_price": 60000,
                "filled_qty": 10,
                "filled_amount": 600000,
                "pending_qty": 0,
                "first_seen_at": "2026-04-23T15:31:00",
                "last_seen_at": "2026-04-23T15:35:10",
                "last_source": "batch",
                "last_order_history_id": "snapshot-1",
                "raw_data": {"odno": "A-1", "pdno": "005930"},
            }
        ],
    )

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("KIS API should not be called when DB cache exists")

    monkeypatch.setattr(order_history_service.kis_api, "inquery_order_list", fail_fetch)

    result = asyncio.run(
        order_history_service.get_domestic_order_history(
            "20260423",
            "20260423",
            symbol="005930",
            source="auto",
        )
    )

    assert result["source"] == "domestic_orders_db"
    assert result["snapshot_status"] == "cached"
    assert result["snapshot_id"] == "snapshot-1"
    assert result["row_count"] == 1
    assert result["rows"][0]["symbol"] == "005930"
    assert result["rows"][0]["last_order_history_id"] == "snapshot-1"
    assert result["fetched_at"] == "2026-04-23T15:35:10"


def test_get_domestic_order_history_falls_back_to_kis_and_saves(monkeypatch):
    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "brokerage")
    monkeypatch.setattr(
        order_history_service.kisdb,
        "get_latest_order_history_snapshot",
        lambda *args: None,
    )
    calls = []
    saved_rows = {}

    def fake_upsert_domestic_orders(rows):
        saved_rows["rows"] = rows
        return len(rows)

    monkeypatch.setattr(order_history_service.kisdb, "upsert_domestic_orders", fake_upsert_domestic_orders)
    monkeypatch.setattr(
        order_history_service.kisdb,
        "get_domestic_orders",
        lambda *args, **kwargs: [
            {
                "order_no": "A-3",
                "order_branch_no": "",
                "symbol": "005930",
                "symbol_name": "삼성전자",
                "order_date": "2026-04-23",
                "order_time": "103000",
                "side_code": "02",
                "side_name": "매수",
                "order_qty": 3,
                "total_order_qty": 3,
                "order_price": 61000,
                "filled_qty": 3,
                "filled_amount": 183000,
                "pending_qty": 0,
                "first_seen_at": "2026-04-23T10:30:00",
                "last_seen_at": "2026-04-23T10:30:00",
                "last_source": "kis_api",
                "last_order_history_id": "saved-1",
                "raw_data": {"odno": "A-3", "pdno": "005930"},
            }
        ],
    )

    async def fake_fetch(start_date, end_date, save_history=False, return_metadata=False):
        calls.append((start_date, end_date, save_history, return_metadata))
        payload = {
            "raw": {
                "output1": [
                    {
                        "odno": "A-3",
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "ord_dt": "20260423",
                        "ord_qty": "3",
                        "ord_unpr": "61000",
                        "tot_ccld_qty": "3",
                    }
                ]
            },
            "saved_order_history_id": "saved-1",
        }
        return payload

    monkeypatch.setattr(order_history_service.kis_api, "inquery_order_list", fake_fetch)

    result = asyncio.run(
        order_history_service.get_domestic_order_history(
            "20260423",
            "20260423",
            source="auto",
        )
    )

    assert calls == [("20260423", "20260423", True, True)]
    assert result["source"] == "kis_api"
    assert result["snapshot_status"] == "saved"
    assert result["saved_order_history_id"] == "saved-1"
    assert result["canonical_write_count"] == 1
    assert result["row_count"] == 1
    assert result["rows"][0]["symbol"] == "005930"
    assert saved_rows["rows"][0]["account_product_code"] == "01"
    assert saved_rows["rows"][0]["order_no"] == "A-3"


def test_get_domestic_order_history_db_mode_reports_cache_miss(monkeypatch):
    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setattr(
        order_history_service.kisdb,
        "get_latest_order_history_snapshot",
        lambda *args: None,
    )

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("KIS API should not be called for source=db cache miss")

    monkeypatch.setattr(order_history_service.kis_api, "inquery_order_list", fail_fetch)

    result = asyncio.run(
        order_history_service.get_domestic_order_history(
            "20260423",
            "20260423",
            source="db",
        )
    )

    assert result["source"] == "domestic_orders_db"
    assert result["status"] == "cache_miss"
    assert result["row_count"] == 0


def test_get_order_list_tool_wraps_account_and_passes_symbol_source(monkeypatch):
    apply_account_env(monkeypatch)
    seen = {}

    async def fake_query(start_date, end_date, *, symbol="", source="auto", save_history=True):
        seen["env_label"] = os.environ["KIS_ACCOUNT_LABEL"]
        seen["args"] = (start_date, end_date, symbol, source, save_history)
        return {
            "source": "domestic_orders_db",
            "status": "ok",
            "market_type": "domestic",
            "canonical_store": "domestic_orders",
            "row_count": 0,
            "rows": [],
            "raw": {"output1": []},
        }

    monkeypatch.setattr(portfolio_mcp, "get_domestic_order_history", fake_query)

    result = asyncio.run(
        portfolio_mcp.get_order_list(
            "20260423",
            "20260423",
            symbol="005930",
            source="db",
            account_label="isa",
        )
    )

    assert seen["env_label"] == "isa"
    assert seen["args"] == ("20260423", "20260423", "005930", "db", True)
    assert result["account"]["label"] == "isa"
