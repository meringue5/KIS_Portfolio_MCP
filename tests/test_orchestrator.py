import asyncio
import json
import os

from kis_mcp_server import orchestrator


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


def test_orchestrator_mcp_name():
    assert orchestrator.mcp.name == "KIS Portfolio Orchestrator"


def test_get_configured_accounts_masks_account_numbers(monkeypatch):
    apply_account_env(monkeypatch)

    result = asyncio.run(orchestrator.get_configured_accounts())
    payload = json.dumps(result, ensure_ascii=False)

    assert result["count"] == 5
    assert [row["label"] for row in result["accounts"]] == [
        "ria",
        "isa",
        "brokerage",
        "irp",
        "pension",
    ]
    assert "11111111" not in payload
    assert "secret-RIA" not in payload
    assert result["accounts"][0]["masked_cano"] == "11****11"


def test_get_all_token_statuses_never_returns_token_value(monkeypatch):
    apply_account_env(monkeypatch)

    def fake_status():
        return {
            "status": "valid",
            "token": "raw-token-value",
            "token_file": "token_11111111.json",
        }

    monkeypatch.setattr(orchestrator, "inspect_token_status", fake_status)

    result = asyncio.run(orchestrator.get_all_token_statuses())
    payload = json.dumps(result, ensure_ascii=False)

    assert result["count"] == 5
    assert "raw-token-value" not in payload
    assert all("token" not in row["token_status"] for row in result["accounts"])


def test_refresh_all_account_snapshots_runs_sequentially_and_reports_account_errors(monkeypatch):
    apply_account_env(monkeypatch)
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "previous")
    calls = []

    async def fake_fetch_balance_snapshot(save_snapshot=True):
        label = os.environ["KIS_ACCOUNT_LABEL"]
        calls.append(label)
        if label == "irp":
            raise RuntimeError("boom")
        return {"label": label, "saved": save_snapshot}

    monkeypatch.setattr(orchestrator, "fetch_balance_snapshot", fake_fetch_balance_snapshot)

    result = asyncio.run(orchestrator.refresh_all_account_snapshots())

    assert calls == ["ria", "isa", "brokerage", "irp", "pension"]
    assert result["count"] == 5
    assert result["success_count"] == 4
    assert result["error_count"] == 1
    assert result["accounts"][3]["account"]["label"] == "irp"
    assert result["accounts"][3]["status"] == "error"
    assert os.environ["KIS_ACCOUNT_LABEL"] == "previous"


def test_get_account_balance_uses_requested_account(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_fetch_balance_snapshot(save_snapshot=True):
        return {
            "label": os.environ["KIS_ACCOUNT_LABEL"],
            "cano": os.environ["KIS_CANO"],
            "saved": save_snapshot,
        }

    monkeypatch.setattr(orchestrator, "fetch_balance_snapshot", fake_fetch_balance_snapshot)

    result = asyncio.run(orchestrator.get_account_balance("isa"))

    assert result["status"] == "ok"
    assert result["account"]["label"] == "isa"
    assert result["account"]["masked_cano"] == "22****22"
    assert result["data"] == {"label": "isa", "cano": "22222222", "saved": True}
