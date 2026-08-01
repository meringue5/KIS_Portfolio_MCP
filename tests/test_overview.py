from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.services.overview import (
    build_cached_fx_fallback,
    build_total_asset_overview,
    build_fx_rates,
    summarize_overseas_deposit,
)
from datetime import date


def account(label, cano, display_name=None):
    return AccountConfig(
        label=label,
        suffix=label.upper(),
        display_name=display_name or label,
        app_key="key",
        app_secret="secret",
        cano=cano,
        acnt_prdt_cd="01",
    )


def test_build_fx_rates_extracts_deposit_rates():
    result = build_fx_rates({
        "적용환율": {"USD/KRW": "1,400.5", "HKD/KRW": "180.2"},
        "통화별_잔고": [{"crcy_cd": "JPY", "frst_bltn_exrt": "9.1"}],
    })

    assert result["USD"]["rate"] == 1400.5
    assert result["HKD"]["rate"] == 180.2
    assert result["JPY"]["rate"] == 9.1


def test_cached_fx_fallback_marks_stale_rates_with_provenance():
    result = build_cached_fx_fallback(
        ["USD"],
        lambda *args, **kwargs: {"currency": "USD", "date": "2026-07-20", "rate": 1400},
        valuation_date=date(2026, 7, 24),
        stale_after_days=3,
    )

    assert result["USD"] == {
        "rate": 1400.0,
        "source": "db_cache",
        "rate_date": "2026-07-20",
        "age_days": 4,
        "stale": True,
    }


def test_summarize_overseas_deposit_extracts_total_asset_and_cash():
    result = summarize_overseas_deposit({
        "예수금_총계": {
            "총자산금액": "180,000",
            "예수금액": "5,000",
            "총예수금액": "30,000",
            "외화사용가능금액": "25,000",
        },
        "통화별_잔고": [{
            "crcy_cd": "USD",
            "frcr_dncl_amt_2": "20.5",
            "frcr_drwg_psbl_amt_1": "20.5",
            "frcr_evlu_amt2": "30,000",
            "frst_bltn_exrt": "1000",
        }],
    })

    assert result["total_asset_amt_krw"] == 180_000
    assert result["reported_total_asset_amt_krw"] == 180_000
    assert result["cash_from_fields_amt_krw"] == 30_000
    assert result["usable_cash_amt_krw"] == 25_000
    assert result["total_cash_amt_krw"] == 30_000
    assert result["foreign_cash_amt_krw"] == 25_000
    assert result["krw_cash_amt_krw"] == 5_000
    assert result["cash_by_currency"][0]["cash_foreign"] == 20.5


def test_build_total_asset_overview_uses_foreign_cash_for_overseas_total():
    accounts = [account("brokerage", "11111111", "일반 위탁")]
    portfolio_summary = {
        "latest_snapshot_at": "2026-04-19T20:00:00",
        "accounts": [{
            "account_id": "11111111",
            "account_type": "brokerage",
            "snap_date": "2026-04-19",
            "snapshot_at": "2026-04-19T20:00:00",
            "total_eval_amt": 100_000,
        }],
    }
    overseas_balance = {
        "NASD": {
            "output1": [{
                "ovrs_pdno": "AAPL",
                "ovrs_item_name": "Apple",
                "tr_crcy_cd": "USD",
                "ovrs_stck_evlu_amt": "150",
            }]
        }
    }
    overseas_deposit = {
        "적용환율": {"USD/KRW": "1000"},
        "예수금_총계": {
            "예수금액": "5,000",
            "총예수금액": "30,000",
            "외화사용가능금액": "25,000",
        },
    }

    result = build_total_asset_overview(
        portfolio_summary,
        overseas_balance,
        overseas_deposit,
        accounts,
        accounts[0],
    )

    assert result["totals"]["overseas_stock_eval_amt_krw"] == 150_000
    assert result["totals"]["overseas_cash_amt_krw"] == 25_000
    assert result["totals"]["overseas_total_asset_amt_krw"] == 175_000
    assert result["totals"]["total_eval_amt_krw"] == 275_000
    assert result["overseas"]["total_asset_source"] == "stock_eval_plus_deposit_foreign_cash"


def test_build_total_asset_overview_does_not_report_domestic_only_as_complete_total():
    accounts = [account("brokerage", "11111111", "일반 위탁")]
    result = build_total_asset_overview(
        {
            "accounts": [{
                "account_id": "11111111",
                "account_type": "brokerage",
                "total_eval_amt": 100_000,
            }],
        },
        {"NASD": {"output1": [{
            "ovrs_pdno": "AAPL",
            "tr_crcy_cd": "USD",
            "ovrs_stck_evlu_amt": "100",
        }]}},
        {"예수금_총계": {"외화사용가능금액": "0"}},
        accounts,
        accounts[0],
    )

    assert result["status"] == "degraded"
    assert result["data_quality"]["is_complete"] is False
    assert result["totals"]["total_eval_amt_krw"] is None
    assert result["totals"]["known_total_eval_amt_krw"] == 100_000
    assert result["data_quality"]["flags"][0]["code"] == "fx_rate_missing"


def test_build_total_asset_overview_uses_fresh_db_fallback_with_explicit_warning():
    accounts = [account("brokerage", "11111111", "일반 위탁")]
    result = build_total_asset_overview(
        {"accounts": [{"account_id": "11111111", "total_eval_amt": 100_000}]},
        {"NASD": {"output1": [{
            "ovrs_pdno": "AAPL",
            "tr_crcy_cd": "USD",
            "ovrs_stck_evlu_amt": "100",
        }]}},
        {"예수금_총계": {"외화사용가능금액": "20000"}},
        accounts,
        accounts[0],
        fallback_fx_rates={
            "USD": {"rate": 1400, "source": "db_cache", "age_days": 1, "stale": False},
        },
    )

    assert result["status"] == "ok"
    assert result["data_quality"]["is_complete"] is True
    assert result["data_quality"]["flags"][0]["code"] == "fx_rate_db_fallback"
    assert result["totals"]["overseas_stock_eval_amt_krw"] == 140_000
    assert result["overseas"]["fx_rates"]["USD"]["source"] == "db_cache"


def test_build_total_asset_overview_ignores_reported_overseas_total_that_duplicates_domestic_cash():
    accounts = [account("brokerage", "11111111", "일반 위탁")]
    portfolio_summary = {
        "latest_snapshot_at": "2026-05-14T12:32:00",
        "accounts": [{
            "account_id": "11111111",
            "account_type": "brokerage",
            "snap_date": "2026-05-14",
            "snapshot_at": "2026-05-14T12:32:00",
            "total_eval_amt": 93_613_410,
        }],
    }
    overseas_balance = {
        "NASD": {
            "output1": [{
                "ovrs_pdno": "AAPL",
                "ovrs_item_name": "Apple",
                "tr_crcy_cd": "USD",
                "ovrs_stck_evlu_amt": "200124",
            }]
        }
    }
    overseas_deposit = {
        "적용환율": {"USD/KRW": "1495"},
        "예수금_총계": {
            "총자산금액": "405,973,826",
            "총예수금액": "93,613,410",
            "외화사용가능금액": "13,155,325",
        },
    }

    result = build_total_asset_overview(
        portfolio_summary,
        overseas_balance,
        overseas_deposit,
        accounts,
        accounts[0],
    )

    assert result["totals"]["overseas_stock_eval_amt_krw"] == 299_185_380
    assert result["totals"]["overseas_cash_amt_krw"] == 13_155_325
    assert result["totals"]["overseas_total_asset_amt_krw"] == 312_340_705
    assert result["totals"]["total_eval_amt_krw"] == 405_954_115
    assert result["overseas"]["deposit"]["reported_total_asset_amt_krw"] == 405_973_826


def test_build_total_asset_overview_returns_chart_ready_allocations_without_raw_account_ids():
    accounts = [
        account("brokerage", "11111111", "일반 위탁"),
        account("isa", "22222222", "ISA"),
    ]
    portfolio_summary = {
        "total_eval_amt": 300_000,
        "latest_snapshot_at": "2026-04-19T20:00:00",
        "accounts": [
            {
                "account_id": "11111111",
                "account_type": "brokerage",
                "snap_date": "2026-04-19",
                "snapshot_at": "2026-04-19T20:00:00",
                "total_eval_amt": 100_000,
            },
            {
                "account_id": "22222222",
                "account_type": "isa",
                "snap_date": "2026-04-19",
                "snapshot_at": "2026-04-19T20:00:00",
                "total_eval_amt": 200_000,
            },
        ],
    }
    overseas_balance = {
        "NASD": {
            "output1": [
                {
                    "ovrs_pdno": "AAPL",
                    "ovrs_item_name": "Apple",
                    "tr_crcy_cd": "USD",
                    "ovrs_cblc_qty": "2",
                    "ovrs_stck_evlu_amt": "100",
                    "frcr_evlu_pfls_amt": "10",
                    "evlu_pfls_rt": "11.1",
                },
                {
                    "ovrs_pdno": "MSFT",
                    "ovrs_item_name": "Microsoft",
                    "tr_crcy_cd": "USD",
                    "ovrs_cblc_qty": "1",
                    "ovrs_stck_evlu_amt": "50",
                },
            ]
        }
    }
    overseas_deposit = {
        "적용환율": {"USD/KRW": "1000"},
        "예수금_총계": {
            "총자산금액": "180000",
            "예수금액": "5000",
            "총예수금액": "30000",
            "외화사용가능금액": "25000",
        },
    }

    result = build_total_asset_overview(
        portfolio_summary,
        overseas_balance,
        overseas_deposit,
        accounts,
        accounts[0],
        top_n=1,
        domestic_snapshot_rows=[
            {
                "account_label": "brokerage",
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
            },
            {
                "account_label": "isa",
                "balance_data": {
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "삼성전자",
                            "evlu_amt": "200000",
                            "hldg_qty": "5",
                        }
                    ]
                },
            },
        ],
    )

    assert result["totals"] == {
        "domestic_eval_amt_krw": 300_000,
        "overseas_stock_eval_amt_krw": 150_000,
        "overseas_cash_amt_krw": 25_000,
        "overseas_total_asset_amt_krw": 175_000,
        "total_eval_amt_krw": 475_000,
    }
    assert result["allocation"]["domestic_pct"] == 63.16
    assert result["allocation"]["overseas_pct"] == 36.84
    assert result["allocation"]["overseas_stock_pct"] == 31.58
    assert result["allocation"]["overseas_cash_pct"] == 5.26
    assert result["classification_summary"]["amounts"]["overseas_indirect"] == 100_000
    assert result["classification_summary"]["amounts"]["domestic_direct"] == 200_000
    assert result["chart_data"]["domestic_vs_overseas"][1]["pct"] == 36.84
    assert result["chart_data"]["overseas_stock_vs_cash"][1]["value_krw"] == 25_000
    assert result["chart_data"]["by_economic_exposure"][2]["value_krw"] == 100_000
    assert result["chart_data"]["overseas_holdings_top"][0]["label"] == "AAPL"
    assert result["chart_data"]["overseas_holdings_top"][1]["label"] == "기타 해외주식"
    assert result["domestic"]["accounts"][0]["account"]["masked_cano"] == "11****11"
    assert "raw" not in result
