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


@pytest.mark.anyio
async def test_domestic_order_history_splits_recent_old_routes_and_preserves_irp_gap(monkeypatch):
    calls = []
    monkeypatch.setenv("KIS_CANO", "44444444")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "29")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")

    async def fake_paginated(path, tr_id, params, **kwargs):
        calls.append((tr_id, params.copy(), kwargs))
        return {"output1": [{"odno": "old-1"}], "output2": [], "pagination": {"page_count": 2}}

    monkeypatch.setattr(kis_api, "_get_paginated_kis_json", fake_paginated)
    result = await kis_api.inquery_order_list(
        "20260101", "20260415", today=datetime(2026, 4, 20).date(),
    )

    assert [item[0] for item in calls] == ["CTSC9215R"]
    assert calls[0][1]["CTX_AREA_FK100"] == ""
    assert calls[0][2]["context_size"] == "100"
    assert result["output1"] == [{"odno": "old-1"}]
    assert result["segments"][1]["status"] == "provisional_source_gap"
    assert result["pagination"]["page_count"] == 2


@pytest.mark.anyio
async def test_domestic_order_history_uses_current_recent_route(monkeypatch):
    calls = []
    monkeypatch.setenv("KIS_CANO", "44444444")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")

    async def fake_paginated(path, tr_id, params, **kwargs):
        calls.append((path, tr_id, params.copy(), kwargs))
        return {"output1": [{"odno": "recent-1"}], "output2": [], "pagination": {"page_count": 1}}

    monkeypatch.setattr(kis_api, "_get_paginated_kis_json", fake_paginated)
    result = await kis_api.inquery_order_list(
        "20260415", "20260420", today=datetime(2026, 4, 20).date(),
    )

    assert len(calls) == 1
    assert calls[0][0] == kis_api.ORDER_LIST_PATH
    assert calls[0][1] == "TTTC0081R"
    assert calls[0][2]["CTX_AREA_FK100"] == ""
    assert calls[0][3]["context_size"] == "100"
    assert result["output1"] == [{"odno": "recent-1"}]
    assert result["segments"][0]["status"] == "collected"


@pytest.mark.anyio
async def test_paginated_kis_json_propagates_fk_nk_and_n_continuation(monkeypatch):
    calls = []
    responses = [
        PageResponse(
            {"output1": [{"odno": "1"}], "ctx_area_fk100": "fk-1", "ctx_area_nk100": "nk-1"},
            {"tr_cont": "F"},
        ),
        PageResponse({"output1": [{"odno": "2"}]}, {}),
    ]
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setattr(kis_api, "get_access_token", fake_token)
    monkeypatch.setattr(kis_api.httpx, "AsyncClient", lambda: PageClient(calls, responses))

    result = await kis_api._get_paginated_kis_json(
        kis_api.ORDER_LIST_PATH,
        "TTTC0081R",
        {"CTX_AREA_FK100": "", "CTX_AREA_NK100": ""},
        output_keys=("output1",),
        context_size="100",
    )

    assert result["output1"] == [{"odno": "1"}, {"odno": "2"}]
    assert result["pagination"]["page_count"] == 2
    assert calls[1]["headers"]["tr_cont"] == "N"
    assert calls[1]["params"]["CTX_AREA_FK100"] == "fk-1"
    assert calls[1]["params"]["CTX_AREA_NK100"] == "nk-1"


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


def test_batch_cli_warm_token_cache_prints_json(monkeypatch, capsys):
    async def fake_warm_token_cache(
        account_label: str,
        valid_through: str,
        dry_run: bool,
        warm_service_health_checks: bool,
    ):
        return {
            "source": "token_cache",
            "operation": "warm-token-cache",
            "status": "ok",
            "account_label": account_label,
            "valid_through": valid_through,
            "dry_run": dry_run,
            "warm_service_health": warm_service_health_checks,
            "error_count": 0,
            "accounts": [],
        }

    monkeypatch.setattr(batch_cli, "warm_token_cache", fake_warm_token_cache)
    monkeypatch.setattr(batch_cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        batch_cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "command": "warm-token-cache",
                "account_label": "all",
                "valid_through": "16:30",
                "dry_run": True,
                "warm_service_health": True,
            },
        )(),
    )

    with pytest.raises(SystemExit) as excinfo:
        batch_cli.main()

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "warm-token-cache"
    assert payload["dry_run"] is True
    assert payload["warm_service_health"] is True


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
    headers = {}

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


class PageResponse:
    status_code = 200
    text = "ok"

    def __init__(self, payload, headers):
        self.payload = payload
        self.headers = headers

    def json(self):
        return self.payload


class PageClient:
    def __init__(self, calls, responses):
        self.calls = calls
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers, params):
        self.calls.append({"url": url, "headers": headers.copy(), "params": params.copy()})
        return self.responses.pop(0)


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
