import asyncio
import os

import pytest

from kis_portfolio.adapters.mcp import server as portfolio_mcp
from kis_portfolio.services import kis_api
from kis_portfolio.services import overseas_history as overseas_history_service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_inquery_overseas_order_ccnl_uses_tr_id_params_and_can_save(monkeypatch):
    calls = []
    saved = {}

    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "brokerage")
    monkeypatch.setattr(kis_api, "get_access_token", fake_token)
    monkeypatch.setattr(kis_api.httpx, "AsyncClient", lambda: FakeClient(calls, {"output": [{"odno": "O-1"}]}))

    def fake_insert_overseas_order_history(*args):
        saved["args"] = args
        return "overseas-order-history-id"

    monkeypatch.setattr(
        kis_api.kisdb,
        "insert_overseas_order_history",
        fake_insert_overseas_order_history,
    )

    result = await kis_api.inquery_overseas_order_ccnl(
        "20260423",
        "20260423",
        symbol="AAPL",
        exchange="NASD",
        save_history=True,
        return_metadata=True,
    )

    assert calls[0]["headers"]["tr_id"] == "TTTS3035R"
    assert calls[0]["params"]["PDNO"] == "AAPL"
    assert calls[0]["params"]["OVRS_EXCG_CD"] == "NASD"
    assert result["saved_order_history_id"] == "overseas-order-history-id"
    assert result["raw"]["output"] == [{"odno": "O-1"}]
    assert saved["args"][:8] == (
        "33333333",
        "01",
        "brokerage",
        "20260423",
        "20260423",
        "NASD",
        "AAPL",
        "00",
    )


def test_get_overseas_transaction_history_falls_back_to_kis_and_saves(monkeypatch):
    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "brokerage")
    monkeypatch.setattr(
        overseas_history_service.kisdb,
        "get_latest_overseas_transaction_history_snapshot",
        lambda *args: None,
    )
    saved_rows = {}

    def fake_upsert(rows):
        saved_rows["rows"] = rows
        return len(rows)

    monkeypatch.setattr(overseas_history_service.kisdb, "upsert_overseas_transactions", fake_upsert)
    monkeypatch.setattr(
        overseas_history_service.kisdb,
        "get_overseas_transactions",
        lambda *args, **kwargs: [
            {
                "transaction_hash": "hash-1",
                "transaction_date": "2026-04-23",
                "exchange_code": "NAS",
                "symbol": "AAPL",
                "symbol_name": "Apple Inc",
                "side_code": "02",
                "side_name": "매수",
                "quantity": 2.0,
                "price": 170.5,
                "amount": 341.0,
                "currency": "USD",
                "order_no": "O-1",
                "last_source": "kis_api",
                "last_transaction_history_id": "txn-history-1",
                "raw_data": {"pdno": "AAPL"},
            }
        ],
    )

    async def fake_fetch(*args, **kwargs):
        return {
            "raw": {
                "output1": [
                    {
                        "erlm_dt": "20260423",
                        "ovrs_excg_cd": "NAS",
                        "pdno": "AAPL",
                        "prdt_name": "Apple Inc",
                        "sll_buy_dvsn_cd": "02",
                        "tr_qty": "2",
                        "ft_ccld_unpr2": "170.5",
                        "tr_amt": "341",
                        "frcr_fee1": "1.25",
                        "dmst_frcr_fee1": "1800",
                        "erlm_exrt": "1430.5",
                        "sttl_dt": "20260425",
                        "crcy_cd": "USD",
                        "odno": "O-1",
                    }
                ]
            },
            "saved_transaction_history_id": "txn-history-1",
        }

    monkeypatch.setattr(overseas_history_service.kis_api, "inquery_overseas_period_trans", fake_fetch)

    result = asyncio.run(
        overseas_history_service.get_overseas_transaction_history(
            "20260423",
            "20260423",
            exchange="NAS",
            source="auto",
        )
    )

    assert result["source"] == "kis_api"
    assert result["snapshot_status"] == "saved"
    assert result["snapshot_id"] == "txn-history-1"
    assert result["canonical_write_count"] == 1
    assert result["row_count"] == 1
    assert result["rows"][0]["symbol"] == "AAPL"
    assert saved_rows["rows"][0]["account_product_code"] == "01"
    assert saved_rows["rows"][0]["last_transaction_history_id"] == "txn-history-1"
    assert saved_rows["rows"][0]["price"] == 170.5
    assert saved_rows["rows"][0]["fee"] == 1.25
    assert saved_rows["rows"][0]["domestic_fee"] == 1800.0
    assert saved_rows["rows"][0]["fx_rate"] == 1430.5
    assert saved_rows["rows"][0]["settlement_date"] == "20260425"


def test_get_overseas_order_history_db_mode_reports_cache_miss(monkeypatch):
    monkeypatch.setenv("KIS_CANO", "33333333")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setattr(
        overseas_history_service.kisdb,
        "get_latest_overseas_order_history_snapshot",
        lambda *args: None,
    )

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("KIS API should not be called for source=db cache miss")

    monkeypatch.setattr(overseas_history_service.kis_api, "inquery_overseas_order_ccnl", fail_fetch)

    result = asyncio.run(
        overseas_history_service.get_overseas_order_history(
            "20260423",
            "20260423",
            source="db",
        )
    )

    assert result["source"] == "overseas_orders_db"
    assert result["status"] == "cache_miss"
    assert result["row_count"] == 0


def test_get_overseas_transaction_history_tool_wraps_account(monkeypatch):
    apply_account_env(monkeypatch)
    seen = {}

    async def fake_query(start_date, end_date, **kwargs):
        seen["env_label"] = os.environ["KIS_ACCOUNT_LABEL"]
        seen["args"] = (start_date, end_date, kwargs)
        return {
            "source": "overseas_transactions_db",
            "status": "ok",
            "market_type": "overseas",
            "canonical_store": "overseas_transactions",
            "row_count": 0,
            "rows": [],
        }

    monkeypatch.setattr(portfolio_mcp, "get_overseas_transaction_history_service", fake_query)

    result = asyncio.run(
        portfolio_mcp.get_overseas_transaction_history(
            "20260423",
            "20260423",
            symbol="AAPL",
            exchange="NAS",
            source="db",
            account_label="brokerage",
        )
    )

    assert seen["env_label"] == "brokerage"
    assert seen["args"][0:2] == ("20260423", "20260423")
    assert seen["args"][2]["symbol"] == "AAPL"
    assert seen["args"][2]["source"] == "db"
    assert result["account"]["label"] == "brokerage"


async def fake_token(client, domain):
    return "token"


class FakeResponse:
    status_code = 200
    text = "ok"
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, calls, payload):
        self.calls = calls
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers, params):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return FakeResponse(self.payload)


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
