import asyncio
import json
import os
from datetime import datetime

import pytest

from kis_portfolio.adapters.batch import cli as batch_cli
from kis_portfolio.services import kis_api
from kis_portfolio.services import order_history as order_history_service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_inquery_order_list_uses_active_account_product_code_and_can_save(monkeypatch):
    calls = []
    saved = {}

    monkeypatch.setenv("KIS_CANO", "44444444")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "29")
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "irp")
    monkeypatch.setattr(kis_api, "get_access_token", fake_token)
    monkeypatch.setattr(kis_api.httpx, "AsyncClient", lambda: FakeClient(calls))

    def fake_insert_order_history(*args):
        saved["args"] = args
        return "order-history-id"

    monkeypatch.setattr(kis_api.kisdb, "insert_order_history", fake_insert_order_history)

    result = await kis_api.inquery_order_list(
        "20260423",
        "20260423",
        save_history=True,
        return_metadata=True,
    )

    assert calls[0]["params"]["ACNT_PRDT_CD"] == "29"
    assert result["saved_order_history_id"] == "order-history-id"
    assert saved["args"][:6] == ("44444444", "29", "irp", "domestic", "20260423", "20260423")


def test_collect_domestic_order_history_runs_all_accounts_and_reports_errors(monkeypatch):
    apply_account_env(monkeypatch)
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "previous")
    calls = []
    saved_rows = []

    async def fake_inquery_order_list(start_date, end_date, save_history=False, return_metadata=False):
        label = os.environ["KIS_ACCOUNT_LABEL"]
        calls.append((label, start_date, end_date, save_history, return_metadata))
        if label == "irp":
            raise RuntimeError("boom")
        payload = {
            "raw": {"output1": [{"odno": f"{label}-1"}]},
            "saved_order_history_id": f"order-{label}",
        }
        return payload if return_metadata else payload["raw"]

    monkeypatch.setattr(order_history_service.kis_api, "inquery_order_list", fake_inquery_order_list)
    monkeypatch.setattr(
        order_history_service.kisdb,
        "upsert_domestic_orders",
        lambda rows: saved_rows.append(rows) or len(rows),
    )
    monkeypatch.setattr(
        order_history_service,
        "evaluate_krx_collection_gate",
        lambda *args, **kwargs: FakeGate("collect"),
    )

    result = asyncio.run(
        order_history_service.collect_domestic_order_history(
            "20260423",
            now=datetime.fromisoformat("2026-04-23T15:35:30+09:00"),
        )
    )

    assert [label for label, *_ in calls] == ["ria", "isa", "brokerage", "irp", "pension"]
    assert result["date"] == "20260423"
    assert result["status"] == "ok"
    assert result["success_count"] == 4
    assert result["error_count"] == 1
    assert result["accounts"][0]["order_count"] == 1
    assert result["accounts"][0]["history_status"] == "saved"
    assert result["accounts"][0]["canonical_write_count"] == 1
    assert result["accounts"][3]["status"] == "error"
    assert os.environ["KIS_ACCOUNT_LABEL"] == "previous"
    assert saved_rows[0][0]["account_product_code"] == "01"
    assert saved_rows[3][0]["account_product_code"] == "22"


def test_collect_domestic_order_history_skips_when_market_closed(monkeypatch):
    apply_account_env(monkeypatch)
    monkeypatch.setattr(
        order_history_service,
        "evaluate_krx_collection_gate",
        lambda *args, **kwargs: FakeGate("skipped", reason="market_closed", is_open=False),
    )

    result = asyncio.run(order_history_service.collect_domestic_order_history("20260501"))

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "market_closed"
    assert result["count"] == 0
    assert result["accounts"] == []


def test_batch_cli_prints_json_summary(monkeypatch, capsys):
    async def fake_collect(date_yyyymmdd: str):
        return {
            "source": "kis_api",
            "status": "ok",
            "market_type": "domestic",
            "date": date_yyyymmdd,
            "count": 1,
            "success_count": 1,
            "error_count": 0,
            "accounts": [],
        }

    monkeypatch.setattr(batch_cli, "collect_domestic_order_history", fake_collect)
    monkeypatch.setattr(batch_cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(batch_cli, "resolve_yyyymmdd", lambda value: "20260423")
    monkeypatch.setattr(batch_cli.argparse.ArgumentParser, "parse_args", lambda self: argparse_namespace())

    with pytest.raises(SystemExit) as excinfo:
        batch_cli.main()

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["date"] == "20260423"


def test_batch_cli_sync_market_calendar_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        batch_cli,
        "sync_krx_market_calendar_years",
        lambda years: {"market": "krx", "years": years, "saved_rows": 365, "yearly": []},
    )
    monkeypatch.setattr(batch_cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        batch_cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"command": "sync-market-calendar", "years": [2026]})(),
    )

    with pytest.raises(SystemExit) as excinfo:
        batch_cli.main()

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["market"] == "krx"


def argparse_namespace():
    return type("Args", (), {"command": "collect-domestic-order-history", "date": "today"})()


class FakeGate:
    def __init__(self, status: str, reason: str = "ready", is_open: bool = True):
        self.status = status
        self.reason = reason
        self.calendar = {
            "market": "krx",
            "trade_date": "2026-04-23",
            "is_open": is_open,
            "open_time_local": "09:00" if is_open else None,
            "close_time_local": "15:30" if is_open else None,
            "timezone": "Asia/Seoul",
            "note": None,
        }
        self.trade_date = "20260423"
        self.now_local = "2026-04-23T15:35:30+09:00"


async def fake_token(client, domain):
    return "token"


class FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {"output1": [{"odno": "1"}]}


class FakeClient:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers, params):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return FakeResponse()


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
