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


def assert_overview_totals_are_consistent(result: dict) -> None:
    totals = result["totals"]
    assert totals["total_eval_amt_krw"] == (
        totals["domestic_eval_amt_krw"] + totals["overseas_total_asset_amt_krw"]
    )
    assert totals["overseas_total_asset_amt_krw"] == (
        totals["overseas_stock_eval_amt_krw"] + totals["overseas_cash_amt_krw"]
    )


def test_orchestrator_mcp_name():
    assert portfolio_mcp.mcp.name == "KIS Portfolio Service"


def test_mcp_exposes_clean_tool_names_only():
    tool_names = set(portfolio_mcp.mcp._tool_manager._tools)

    assert "get-stock-price" in tool_names
    assert "get-total-asset-overview" in tool_names
    assert "get-total-asset-history" in tool_names
    assert "submit-stock-order" in tool_names
    assert "inquery-stock-price" not in tool_names
    assert "order-stock" not in tool_names


def test_mcp_tool_metadata_guides_chatgpt_discovery():
    stock_price = portfolio_mcp.mcp._tool_manager._tools["get-stock-price"]
    overview = portfolio_mcp.mcp._tool_manager._tools["get-total-asset-overview"]
    order_list = portfolio_mcp.mcp._tool_manager._tools["get-order-list"]
    order_stub = portfolio_mcp.mcp._tool_manager._tools["submit-stock-order"]

    assert stock_price.description.startswith("Use this when")
    assert stock_price.annotations.readOnlyHint is True
    assert stock_price.parameters["properties"]["symbol"]["description"] == (
        "Domestic KRX stock or ETF code, usually a 6-digit symbol."
    )

    assert overview.description.startswith("Use this when")
    assert overview.annotations.destructiveHint is False
    assert overview.annotations.openWorldHint is False
    assert overview.parameters["properties"]["top_n"]["minimum"] == 1
    assert overview.parameters["properties"]["top_n"]["maximum"] == 50

    assert order_list.description.startswith("Use this when")
    assert order_list.annotations.destructiveHint is False
    assert order_list.annotations.openWorldHint is False
    assert order_list.parameters["properties"]["symbol"]["description"] == (
        "Optional domestic KRX symbol filter. Leave empty to include all symbols in the date range."
    )
    assert "backend strategy" in order_list.parameters["properties"]["source"]["description"]

    assert order_stub.description.startswith("Use this only when")
    assert "disabled stub" in order_stub.description
    assert order_stub.annotations.destructiveHint is False
    assert order_stub.annotations.openWorldHint is False


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
    assert result["accounts"][0]["snapshot_status"] == "saved"
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
    assert result["snapshot_status"] == "saved"


def test_get_account_balance_reports_snapshot_not_saved(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_fetch_balance_snapshot(save_snapshot=True, return_metadata=False):
        if return_metadata:
            return {"raw": {"label": os.environ["KIS_ACCOUNT_LABEL"]}, "saved_snapshot_id": None}
        return {"label": os.environ["KIS_ACCOUNT_LABEL"]}

    monkeypatch.setattr(portfolio_mcp, "fetch_balance_snapshot", fake_fetch_balance_snapshot)

    result = asyncio.run(portfolio_mcp.get_account_balance("ria"))

    assert result["status"] == "ok"
    assert result["snapshot_status"] == "not_saved"
    assert "saved_snapshot_id" not in result


def test_get_total_asset_overview_precomputes_allocation(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_refresh_all_account_snapshots():
        return {
            "count": 5,
            "success_count": 5,
            "error_count": 0,
            "accounts": [{"snapshot_status": "saved"} for _ in range(5)],
        }

    def fake_summary(con, account_id="", lookback_days=30):
        return {
            "latest_snapshot_at": "2026-04-19T20:00:00",
            "accounts": [
                {
                    "account_id": "33333333",
                    "account_type": "brokerage",
                    "snap_date": "2026-04-19",
                    "snapshot_at": "2026-04-19T20:00:00",
                    "total_eval_amt": 100_000,
                }
            ],
        }

    async def fake_overseas_balance(exchange="ALL"):
        return {
            "NASD": {
                "output1": [{
                    "ovrs_pdno": "AAPL",
                    "ovrs_item_name": "Apple",
                    "tr_crcy_cd": "USD",
                    "ovrs_stck_evlu_amt": "100",
                }]
            }
        }

    async def fake_overseas_deposit(wcrc_frcr_dvsn_cd="01", natn_cd="000"):
        return {
            "적용환율": {"USD/KRW": "1000"},
            "예수금_총계": {"총자산금액": "120000", "외화사용가능금액": "20000", "총예수금액": "0"},
        }

    monkeypatch.setattr(portfolio_mcp, "refresh_all_account_snapshots", fake_refresh_all_account_snapshots)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_connection", lambda: object())
    monkeypatch.setattr(portfolio_mcp, "analyze_latest_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_balance", fake_overseas_balance)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_deposit", fake_overseas_deposit)
    monkeypatch.setattr(
        portfolio_mcp.kisdb,
        "get_portfolio_snapshots",
        lambda *args, **kwargs: [{
            "account_id": "33333333",
            "account_type": "brokerage",
            "balance_data": {
                "output1": [
                    {
                        "pdno": "0015B0",
                        "prdt_name": "KoAct 미국나스닥성장기업액티브",
                        "evlu_amt": "100000",
                        "hldg_qty": "10",
                    }
                ]
            },
        }],
    )
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_instrument_master_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_classification_override_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_overseas_asset_snapshot", lambda *args, **kwargs: "ovs-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_overview_snapshot", lambda *args, **kwargs: "overview-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_holding_snapshots", lambda *args, **kwargs: 3)

    result = asyncio.run(portfolio_mcp.get_total_asset_overview())

    assert result["status"] == "ok"
    assert result["refresh"]["success_count"] == 5
    assert result["refresh"]["snapshot_status_counts"] == {"saved": 5, "not_saved": 0}
    assert result["totals"]["domestic_eval_amt_krw"] == 100_000
    assert result["totals"]["overseas_stock_eval_amt_krw"] == 100_000
    assert result["totals"]["overseas_cash_amt_krw"] == 20_000
    assert_overview_totals_are_consistent(result)
    assert result["overseas"]["total_asset_source"] == "overseas_deposit.예수금_총계.총자산금액"
    assert result["allocation"]["domestic_pct"] == 45.45
    assert result["chart_data"]["domestic_vs_overseas"][1]["pct"] == 54.55
    assert result["classification_summary"]["amounts"]["overseas_indirect"] == 100_000
    assert result["saved_snapshot_id"] == "overview-1"
    assert result["snapshot_status"] == "saved"
    assert "raw" not in result
    assert result["used_tools"] == [
        "refresh-all-account-snapshots",
        "get-latest-portfolio-summary",
        "get-overseas-balance",
        "get-overseas-deposit",
    ]


def test_get_total_asset_overview_saves_canonical_snapshots(monkeypatch, tmp_path):
    apply_account_env(monkeypatch)
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))
    portfolio_mcp.kisdb.close_connection()

    async def fake_refresh_all_account_snapshots():
        return {
            "count": 5,
            "success_count": 5,
            "error_count": 0,
            "accounts": [{"snapshot_status": "saved"} for _ in range(5)],
        }

    def fake_summary(con, account_id="", lookback_days=30):
        return {
            "latest_snapshot_at": "2026-04-19T20:00:00",
            "accounts": [
                {
                    "account_id": "33333333",
                    "account_type": "brokerage",
                    "snap_date": "2026-04-19",
                    "snapshot_at": "2026-04-19T20:00:00",
                    "total_eval_amt": 100_000,
                }
            ],
        }

    async def fake_overseas_balance(exchange="ALL"):
        return {
            "NASD": {
                "output1": [{
                    "ovrs_pdno": "AAPL",
                    "ovrs_item_name": "Apple",
                    "tr_crcy_cd": "USD",
                    "ovrs_stck_evlu_amt": "100",
                }]
            }
        }

    async def fake_overseas_deposit(wcrc_frcr_dvsn_cd="01", natn_cd="000"):
        return {
            "적용환율": {"USD/KRW": "1000"},
            "예수금_총계": {"총자산금액": "120000", "외화사용가능금액": "20000", "총예수금액": "0"},
        }

    monkeypatch.setattr(portfolio_mcp, "refresh_all_account_snapshots", fake_refresh_all_account_snapshots)
    monkeypatch.setattr(portfolio_mcp, "analyze_latest_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_balance", fake_overseas_balance)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_deposit", fake_overseas_deposit)
    monkeypatch.setattr(
        portfolio_mcp.kisdb,
        "get_portfolio_snapshots",
        lambda *args, **kwargs: [{
            "account_id": "33333333",
            "account_type": "brokerage",
            "balance_data": {
                "output1": [
                    {
                        "pdno": "0015B0",
                        "prdt_name": "KoAct 미국나스닥성장기업액티브",
                        "evlu_amt": "100000",
                        "hldg_qty": "10",
                    }
                ]
            },
        }],
    )
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_instrument_master_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_classification_override_map", lambda symbols: {})

    result = asyncio.run(portfolio_mcp.get_total_asset_overview())
    con = portfolio_mcp.kisdb.get_connection()
    counts = {
        "overseas_asset_snapshots": con.execute("select count(*) from overseas_asset_snapshots").fetchone()[0],
        "asset_overview_snapshots": con.execute("select count(*) from asset_overview_snapshots").fetchone()[0],
        "asset_holding_snapshots": con.execute("select count(*) from asset_holding_snapshots").fetchone()[0],
    }
    portfolio_mcp.kisdb.close_connection()

    assert result["snapshot_status"] == "saved"
    assert result["saved_snapshot_id"]
    assert counts["overseas_asset_snapshots"] == 1
    assert counts["asset_overview_snapshots"] == 1
    assert counts["asset_holding_snapshots"] >= 2


def test_get_total_asset_overview_include_raw_supports_debug_invariants(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_refresh_all_account_snapshots():
        return {
            "count": 5,
            "success_count": 5,
            "error_count": 0,
            "accounts": [{"snapshot_status": "saved"} for _ in range(5)],
        }

    def fake_summary(con, account_id="", lookback_days=30):
        return {
            "latest_snapshot_at": "2026-04-23T09:00:00",
            "accounts": [
                {
                    "account_id": "33333333",
                    "account_type": "brokerage",
                    "snap_date": "2026-04-23",
                    "snapshot_at": "2026-04-23T09:00:00",
                    "total_eval_amt": 100_000,
                }
            ],
        }

    async def fake_overseas_balance(exchange="ALL"):
        return {
            "NASD": {
                "output1": [{
                    "ovrs_pdno": "AAPL",
                    "ovrs_item_name": "Apple",
                    "tr_crcy_cd": "USD",
                    "ovrs_stck_evlu_amt": "150",
                }]
            }
        }

    async def fake_overseas_deposit(wcrc_frcr_dvsn_cd="01", natn_cd="000"):
        return {
            "적용환율": {"USD/KRW": "1000"},
            "예수금_총계": {
                "예수금액": "5000",
                "총예수금액": "30000",
                "외화사용가능금액": "25000",
            },
            "통화별_잔고": [{
                "crcy_cd": "USD",
                "frcr_dncl_amt_2": "20.5",
                "frcr_drwg_psbl_amt_1": "20.5",
                "frcr_evlu_amt2": "30000",
                "frst_bltn_exrt": "1000",
            }],
        }

    monkeypatch.setattr(portfolio_mcp, "refresh_all_account_snapshots", fake_refresh_all_account_snapshots)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_connection", lambda: object())
    monkeypatch.setattr(portfolio_mcp, "analyze_latest_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_balance", fake_overseas_balance)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_deposit", fake_overseas_deposit)
    monkeypatch.setattr(
        portfolio_mcp.kisdb,
        "get_portfolio_snapshots",
        lambda *args, **kwargs: [{
            "account_id": "33333333",
            "account_type": "brokerage",
            "balance_data": {
                "output1": [
                    {
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "evlu_amt": "100000",
                        "hldg_qty": "5",
                    }
                ]
            },
        }],
    )
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_instrument_master_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_classification_override_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_overseas_asset_snapshot", lambda *args, **kwargs: "ovs-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_overview_snapshot", lambda *args, **kwargs: "overview-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_holding_snapshots", lambda *args, **kwargs: 3)

    result = asyncio.run(portfolio_mcp.get_total_asset_overview(include_raw=True))

    assert result["status"] == "ok"
    assert_overview_totals_are_consistent(result)
    assert result["overseas"]["total_asset_source"] == "stock_eval_plus_deposit_cash_fields"
    assert result["overseas"]["deposit"]["total_cash_amt_krw"] == 30_000
    assert result["totals"]["overseas_cash_amt_krw"] == 30_000
    assert result["raw"]["portfolio_summary"]["accounts"][0]["total_eval_amt"] == 100_000
    assert result["raw"]["overseas_deposit"]["예수금_총계"]["총예수금액"] == "30000"
    assert result["raw"]["overseas_balance"]["NASD"]["output1"][0]["ovrs_pdno"] == "AAPL"


def test_get_total_asset_overview_excludes_raw_by_default(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_refresh_all_account_snapshots():
        return {
            "count": 5,
            "success_count": 5,
            "error_count": 0,
            "accounts": [{"snapshot_status": "saved"} for _ in range(5)],
        }

    def fake_summary(con, account_id="", lookback_days=30):
        return {
            "latest_snapshot_at": "2026-04-23T09:00:00",
            "accounts": [{
                "account_id": "33333333",
                "account_type": "brokerage",
                "snap_date": "2026-04-23",
                "snapshot_at": "2026-04-23T09:00:00",
                "total_eval_amt": 100_000,
            }],
        }

    async def fake_overseas_balance(exchange="ALL"):
        return {
            "NASD": {
                "output1": [{
                    "ovrs_pdno": "AAPL",
                    "ovrs_item_name": "Apple",
                    "tr_crcy_cd": "USD",
                    "ovrs_stck_evlu_amt": "150",
                }]
            }
        }

    async def fake_overseas_deposit(wcrc_frcr_dvsn_cd="01", natn_cd="000"):
        return {
            "적용환율": {"USD/KRW": "1000"},
            "예수금_총계": {
                "예수금액": "5000",
                "총예수금액": "30000",
                "외화사용가능금액": "25000",
            },
        }

    monkeypatch.setattr(portfolio_mcp, "refresh_all_account_snapshots", fake_refresh_all_account_snapshots)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_connection", lambda: object())
    monkeypatch.setattr(portfolio_mcp, "analyze_latest_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_balance", fake_overseas_balance)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_deposit", fake_overseas_deposit)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_portfolio_snapshots", lambda *args, **kwargs: [])
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_instrument_master_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_classification_override_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_overseas_asset_snapshot", lambda *args, **kwargs: "ovs-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_overview_snapshot", lambda *args, **kwargs: "overview-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_holding_snapshots", lambda *args, **kwargs: 1)

    result = asyncio.run(portfolio_mcp.get_total_asset_overview())

    assert result["status"] == "ok"
    assert_overview_totals_are_consistent(result)
    assert "raw" not in result


def test_get_total_asset_overview_marks_partial_error_but_keeps_safe_totals(monkeypatch):
    apply_account_env(monkeypatch)

    async def fake_refresh_all_account_snapshots():
        return {
            "count": 5,
            "success_count": 5,
            "error_count": 0,
            "accounts": [{"snapshot_status": "saved"} for _ in range(5)],
        }

    def fake_summary(con, account_id="", lookback_days=30):
        return {
            "latest_snapshot_at": "2026-04-23T09:00:00",
            "accounts": [{
                "account_id": "33333333",
                "account_type": "brokerage",
                "snap_date": "2026-04-23",
                "snapshot_at": "2026-04-23T09:00:00",
                "total_eval_amt": 100_000,
            }],
        }

    async def fake_overseas_balance(exchange="ALL"):
        raise RuntimeError("balance unavailable")

    async def fake_overseas_deposit(wcrc_frcr_dvsn_cd="01", natn_cd="000"):
        return {
            "적용환율": {"USD/KRW": "1000"},
            "예수금_총계": {
                "예수금액": "5000",
                "총예수금액": "30000",
                "외화사용가능금액": "25000",
            },
        }

    monkeypatch.setattr(portfolio_mcp, "refresh_all_account_snapshots", fake_refresh_all_account_snapshots)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_connection", lambda: object())
    monkeypatch.setattr(portfolio_mcp, "analyze_latest_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_balance", fake_overseas_balance)
    monkeypatch.setattr(portfolio_mcp.kis_api, "inquery_overseas_deposit", fake_overseas_deposit)
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_portfolio_snapshots", lambda *args, **kwargs: [])
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_instrument_master_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "get_classification_override_map", lambda symbols: {})
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_overseas_asset_snapshot", lambda *args, **kwargs: "ovs-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_overview_snapshot", lambda *args, **kwargs: "overview-1")
    monkeypatch.setattr(portfolio_mcp.kisdb, "insert_asset_holding_snapshots", lambda *args, **kwargs: 1)

    result = asyncio.run(portfolio_mcp.get_total_asset_overview())

    assert result["status"] == "partial_error"
    assert result["errors"] == [{"tool": "get-overseas-balance", "error": "balance unavailable"}]
    assert result["overseas"]["total_asset_source"] == "stock_eval_plus_deposit_cash_fields"
    assert result["totals"]["overseas_stock_eval_amt_krw"] == 0
    assert result["totals"]["overseas_cash_amt_krw"] == 30_000
    assert result["totals"]["overseas_total_asset_amt_krw"] == 30_000
    assert result["totals"]["total_eval_amt_krw"] == 130_000
    assert_overview_totals_are_consistent(result)
