import asyncio
import json
import os

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
    assert saved["args"][:5] == ("44444444", "irp", "domestic", "20260423", "20260423")


def test_collect_domestic_order_history_runs_all_accounts_and_reports_errors(monkeypatch):
    apply_account_env(monkeypatch)
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "previous")
    calls = []

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

    result = asyncio.run(order_history_service.collect_domestic_order_history("20260423"))

    assert [label for label, *_ in calls] == ["ria", "isa", "brokerage", "irp", "pension"]
    assert result["date"] == "20260423"
    assert result["success_count"] == 4
    assert result["error_count"] == 1
    assert result["accounts"][0]["order_count"] == 1
    assert result["accounts"][0]["history_status"] == "saved"
    assert result["accounts"][3]["status"] == "error"
    assert os.environ["KIS_ACCOUNT_LABEL"] == "previous"


def test_batch_cli_prints_json_summary(monkeypatch, capsys):
    async def fake_collect(date_yyyymmdd: str):
        return {
            "source": "kis_api",
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


def argparse_namespace():
    return type("Args", (), {"command": "collect-domestic-order-history", "date": "today"})()


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
