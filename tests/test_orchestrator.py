import asyncio
import json
import os

from kis_portfolio.adapters.mcp import server as portfolio_mcp


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
    assert portfolio_mcp.mcp.name == "KIS Portfolio Service"


def test_mcp_exposes_clean_tool_names_only():
    tool_names = set(portfolio_mcp.mcp._tool_manager._tools)

    assert "get-stock-price" in tool_names
    assert "submit-stock-order" in tool_names
    assert "inquery-stock-price" not in tool_names
    assert "order-stock" not in tool_names


def test_get_configured_accounts_masks_account_numbers(monkeypatch):
    apply_account_env(monkeypatch)

    result = asyncio.run(portfolio_mcp.get_configured_accounts())
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

    monkeypatch.setattr(portfolio_mcp, "inspect_token_status", fake_status)

    result = asyncio.run(portfolio_mcp.get_all_token_statuses())
    payload = json.dumps(result, ensure_ascii=False)

    assert result["count"] == 5
    assert "raw-token-value" not in payload
    assert all("token" not in row["token_status"] for row in result["accounts"])


def test_refresh_all_account_snapshots_runs_sequentially_and_reports_account_errors(monkeypatch):
    apply_account_env(monkeypatch)
    monkeypatch.setenv("KIS_ACCOUNT_LABEL", "previous")
    calls = []

    async def fake_fetch_balance_snapshot(save_snapshot=True, return_metadata=False):
        label = os.environ["KIS_ACCOUNT_LABEL"]
        calls.append(label)
        if label == "irp":
            raise RuntimeError("boom")
        raw = {"label": label, "saved": save_snapshot}
        if return_metadata:
            return {"raw": raw, "saved_snapshot_id": f"snapshot-{label}"}
        return raw

    monkeypatch.setattr(portfolio_mcp, "fetch_balance_snapshot", fake_fetch_balance_snapshot)

    result = asyncio.run(portfolio_mcp.refresh_all_account_snapshots())

    assert calls == ["ria", "isa", "brokerage", "irp", "pension"]
    assert result["count"] == 5
    assert result["success_count"] == 4
    assert result["error_count"] == 1
    assert result["accounts"][3]["account"]["label"] == "irp"
    assert result["accounts"][3]["status"] == "error"
    assert os.environ["KIS_ACCOUNT_LABEL"] == "previous"


def test_get_account_balance_uses_requested_account(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_fetch_balance_snapshot(save_snapshot=True, return_metadata=False):
        raw = {
            "label": os.environ["KIS_ACCOUNT_LABEL"],
            "cano": os.environ["KIS_CANO"],
            "saved": save_snapshot,
        }
        if return_metadata:
            return {"raw": raw, "saved_snapshot_id": "snapshot-isa"}
        return raw

    monkeypatch.setattr(portfolio_mcp, "fetch_balance_snapshot", fake_fetch_balance_snapshot)

    result = asyncio.run(portfolio_mcp.get_account_balance("isa"))

    assert result["status"] == "ok"
    assert result["account"]["label"] == "isa"
    assert result["account"]["masked_cano"] == "22****22"
    assert result["raw"] == {"label": "isa", "cano": "22222222", "saved": True}
    assert result["saved_snapshot_id"] == "snapshot-isa"
