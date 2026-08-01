"""Canonical total-asset overview aggregation and classification helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.services.classification import classify_domestic_holding


EXCHANGE_CURRENCY = {
    "NASD": "USD",
    "NYSE": "USD",
    "AMEX": "USD",
    "SEHK": "HKD",
    "SHAA": "CNY",
    "SZAA": "CNY",
    "TKSE": "JPY",
    "HASE": "VND",
    "VNSE": "VND",
}


def overseas_holding_currencies(overseas_balance: dict) -> list[str]:
    """Return currencies that need KRW conversion for positive holdings."""
    currencies: set[str] = set()
    for exchange, payload in (overseas_balance.items() if isinstance(overseas_balance, dict) else []):
        if not isinstance(payload, dict):
            continue
        for row in payload.get("output1") or []:
            if not isinstance(row, dict):
                continue
            value = _first_number(row, ["ovrs_stck_evlu_amt", "frcr_evlu_amt2"])
            if value is not None and value > 0:
                currencies.add(row.get("tr_crcy_cd") or EXCHANGE_CURRENCY.get(str(exchange), "USD"))
    return sorted(currencies)


def build_cached_fx_fallback(
    currencies: list[str],
    latest_rate_getter,
    *,
    valuation_date: date | None = None,
    stale_after_days: int = 7,
) -> dict[str, dict]:
    """Build provenance-rich fallback rates from the exchange-rate cache."""
    valuation_date = valuation_date or date.today()
    fallback: dict[str, dict] = {}
    for currency in currencies:
        row = latest_rate_getter(currency, on_or_before=valuation_date, period="D")
        if not row:
            continue
        rate_date = row.get("date")
        if isinstance(rate_date, str):
            rate_date = datetime.fromisoformat(rate_date).date()
        age_days = (valuation_date - rate_date).days if rate_date else None
        fallback[currency] = {
            "rate": parse_number(row.get("rate")),
            "source": "db_cache",
            "rate_date": rate_date.isoformat() if rate_date else None,
            "age_days": age_days,
            "stale": age_days is None or age_days > stale_after_days,
        }
    return fallback


def parse_number(value: Any) -> float | None:
    """Parse KIS numeric strings without raising."""
    if value in (None, "", "-"):
        return None
    try:
        text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
        return float(text)
    except Exception:
        return None


def parse_int(value: Any) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def pct(value: float | int | None, total: float | int | None) -> float | None:
    if value is None or not total:
        return None
    return round(float(value) / float(total) * 100, 2)


def _first_number(row: dict, keys: list[str]) -> float | None:
    for key in keys:
        number = parse_number(row.get(key))
        if number is not None:
            return number
    return None


def build_fx_rates(
    overseas_deposit: dict,
    fallback_fx_rates: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Extract KRW FX rates, preferring the KIS deposit response over cache."""
    rates: dict[str, dict] = {
        currency.upper(): {
            "currency": currency.upper(),
            "quote": "KRW",
            **value,
            "source": value.get("source", "db_cache"),
        }
        for currency, value in (fallback_fx_rates or {}).items()
        if isinstance(value, dict) and parse_number(value.get("rate")) is not None
    }
    raw_rates = overseas_deposit.get("적용환율") or {}
    if isinstance(raw_rates, dict):
        for pair, raw_value in raw_rates.items():
            if not isinstance(pair, str) or "/" not in pair:
                continue
            currency, quote = pair.split("/", 1)
            if quote != "KRW":
                continue
            rate = parse_number(raw_value)
            if rate is not None:
                rates[currency] = {
                    "currency": currency,
                    "quote": "KRW",
                    "rate": rate,
                    "source": "kis_deposit_summary",
                    "stale": False,
                }

    for row in overseas_deposit.get("통화별_잔고") or []:
        if not isinstance(row, dict):
            continue
        currency = row.get("crcy_cd")
        rate = parse_number(row.get("frst_bltn_exrt"))
        if currency and rate is not None:
            rates[currency] = {
                "currency": currency,
                "quote": "KRW",
                "rate": rate,
                "source": "kis_deposit_currency_balance",
                "stale": False,
            }
    return rates


def summarize_overseas_deposit(overseas_deposit: dict) -> dict:
    """Extract KRW overseas account totals and cash-like balances."""
    total = overseas_deposit.get("예수금_총계") or {}
    if not isinstance(total, dict):
        total = {}

    foreign_cash_krw = parse_int(total.get("외화사용가능금액"))
    krw_cash = parse_int(total.get("예수금액"))
    total_cash_krw = parse_int(total.get("총예수금액"))
    total_asset_krw = parse_int(total.get("총자산금액"))
    cash_from_fields = (
        total_cash_krw
        if total_cash_krw is not None
        else sum(value or 0 for value in [foreign_cash_krw, krw_cash])
    )

    by_currency = []
    for row in overseas_deposit.get("통화별_잔고") or []:
        if not isinstance(row, dict):
            continue
        by_currency.append({
            "currency": row.get("crcy_cd"),
            "cash_foreign": parse_number(row.get("frcr_dncl_amt_2")),
            "withdrawable_foreign": parse_number(row.get("frcr_drwg_psbl_amt_1")),
            "cash_krw": parse_int(row.get("frcr_evlu_amt2")),
            "fx_rate": parse_number(row.get("frst_bltn_exrt")),
        })

    return {
        "total_asset_amt_krw": total_asset_krw,
        "reported_account_total_asset_amt_krw": total_asset_krw,
        "reported_total_asset_amt_krw": total_asset_krw,
        "total_cash_amt_krw": total_cash_krw,
        "cash_from_fields_amt_krw": cash_from_fields,
        "usable_cash_amt_krw": foreign_cash_krw,
        "foreign_cash_amt_krw": foreign_cash_krw,
        "krw_cash_amt_krw": krw_cash,
        "cash_by_currency": by_currency,
        "cash_semantics": {
            "canonical_overseas_cash_field": "foreign_cash_amt_krw",
            "reported_total_asset_includes_securities": True,
            "total_cash_may_overlap_domestic_feeder": True,
        },
    }


def summarize_overseas_holdings(
    overseas_balance: dict,
    overseas_deposit: dict,
    overseas_account: AccountConfig,
    top_n: int = 10,
    fallback_fx_rates: dict[str, dict] | None = None,
) -> dict:
    """Normalize overseas holdings and pre-compute KRW allocations."""
    top_n = max(1, min(int(top_n), 50))
    fx_rates = build_fx_rates(overseas_deposit, fallback_fx_rates)
    deposit = summarize_overseas_deposit(overseas_deposit)
    holdings: list[dict] = []
    missing_fx_currencies: set[str] = set()
    totals_by_currency: dict[str, dict] = defaultdict(
        lambda: {"currency": "", "value_foreign": 0.0, "value_krw": 0.0, "fx_rate": None}
    )

    exchange_items = overseas_balance.items() if isinstance(overseas_balance, dict) else []
    for exchange, payload in exchange_items:
        if not isinstance(payload, dict):
            continue
        output1 = payload.get("output1") or []
        if not isinstance(output1, list):
            continue
        for row in output1:
            if not isinstance(row, dict):
                continue
            currency = row.get("tr_crcy_cd") or EXCHANGE_CURRENCY.get(str(exchange), "USD")
            value_foreign = _first_number(row, ["ovrs_stck_evlu_amt", "frcr_evlu_amt2"])
            quantity = _first_number(row, ["ovrs_cblc_qty", "ord_psbl_qty"])
            if value_foreign is None or value_foreign <= 0:
                continue
            fx_rate = (fx_rates.get(currency) or {}).get("rate")
            value_krw = value_foreign * fx_rate if fx_rate else None
            if not fx_rate:
                missing_fx_currencies.add(currency)
            profit_foreign = parse_number(row.get("frcr_evlu_pfls_amt"))
            holding = {
                "account_label": overseas_account.label,
                "account_type": overseas_account.label,
                "symbol": row.get("ovrs_pdno"),
                "name": row.get("ovrs_item_name"),
                "market": exchange,
                "basis_category": "overseas_account",
                "exposure_type": "overseas_direct",
                "exposure_region": currency or "global",
                "asset_subtype": "equity",
                "confidence": "high",
                "exchange": exchange,
                "currency": currency,
                "quantity": quantity,
                "value_foreign": round(value_foreign, 2),
                "value_krw": parse_int(value_krw),
                "profit_foreign": round(profit_foreign, 2) if profit_foreign is not None else None,
                "profit_rate_pct": parse_number(row.get("evlu_pfls_rt")),
                "raw_data": row,
            }
            holdings.append(holding)

            bucket = totals_by_currency[currency]
            bucket["currency"] = currency
            bucket["value_foreign"] += value_foreign
            if fx_rate:
                bucket["fx_rate"] = fx_rate
                bucket["value_krw"] += value_foreign * fx_rate

    known_stock_krw = sum((row.get("value_krw") or 0) for row in holdings)
    stock_krw = None if missing_fx_currencies else known_stock_krw
    cash_krw = deposit.get("usable_cash_amt_krw")
    total_asset_source = "stock_eval_plus_deposit_foreign_cash"
    if cash_krw is None:
        cash_krw = deposit.get("cash_from_fields_amt_krw") or 0
        total_asset_source = "stock_eval_plus_deposit_cash_fields"
    total_asset_krw = stock_krw + cash_krw if stock_krw is not None else None
    if missing_fx_currencies:
        total_asset_source = "incomplete_missing_fx"

    stock_eval_by_currency = []
    for row in totals_by_currency.values():
        stock_eval_by_currency.append({
            "currency": row["currency"],
            "value_foreign": round(row["value_foreign"], 2),
            "fx_rate": row["fx_rate"],
            "value_krw": parse_int(row["value_krw"]) if row["value_krw"] else None,
        })

    holdings.sort(key=lambda row: row.get("value_krw") or 0, reverse=True)
    chart_holdings = []
    for row in holdings[:top_n]:
        chart_holdings.append({
            "label": row.get("symbol") or row.get("name") or "unknown",
            "value_krw": row.get("value_krw"),
            "value_foreign": row.get("value_foreign"),
            "currency": row.get("currency"),
            "pct_of_overseas_stock": pct(row.get("value_krw"), stock_krw),
            "pct_of_overseas_total": pct(row.get("value_krw"), total_asset_krw),
        })
    if len(holdings) > top_n:
        other_krw = sum((row.get("value_krw") or 0) for row in holdings[top_n:])
        chart_holdings.append({
            "label": "기타 해외주식",
            "value_krw": other_krw,
            "pct_of_overseas_stock": pct(other_krw, stock_krw),
            "pct_of_overseas_total": pct(other_krw, total_asset_krw),
        })

    return {
        "account": overseas_account.public_dict(),
        "holdings_count": len(holdings),
        "stock_eval_amt_krw": parse_int(stock_krw),
        "known_stock_eval_amt_krw": parse_int(known_stock_krw),
        "cash_amt_krw": parse_int(cash_krw),
        "total_asset_amt_krw": parse_int(total_asset_krw),
        "total_asset_source": total_asset_source,
        "deposit": deposit,
        "stock_eval_by_currency": sorted(stock_eval_by_currency, key=lambda row: row["currency"]),
        "fx_rates": fx_rates,
        "missing_fx_currencies": sorted(missing_fx_currencies),
        "holdings_top": holdings[:top_n],
        "chart_data": chart_holdings,
        "_normalized_holdings": holdings,
    }


def summarize_domestic_accounts(summary: dict, accounts: list[AccountConfig]) -> list[dict]:
    """Return masked domestic account rows from portfolio summary."""
    account_by_cano = {account.cano: account for account in accounts}
    rows = []
    for row in summary.get("accounts") or []:
        account = account_by_cano.get(row.get("account_id"))
        public = account.public_dict() if account else {
            "label": row.get("account_type") or "unknown",
            "display_name": row.get("account_type") or "unknown",
            "masked_cano": None,
        }
        rows.append({
            "account": public,
            "snap_date": row.get("snap_date"),
            "snapshot_at": row.get("snapshot_at"),
            "value_krw": row.get("total_eval_amt") or 0,
        })
    return rows


def _build_domestic_snapshot_index(domestic_snapshot_rows: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in domestic_snapshot_rows:
        account = row.get("account") or {}
        label = row.get("account_label") or account.get("label")
        if label:
            indexed[label] = row
    return indexed


def summarize_domestic_holdings(
    domestic_accounts: list[dict],
    domestic_snapshot_rows: list[dict],
    instrument_map: dict[str, dict] | None = None,
    override_map: dict[str, dict] | None = None,
) -> tuple[list[dict], dict, list[dict]]:
    """Normalize domestic holdings, economic exposure amounts, and warnings."""
    instrument_map = instrument_map or {}
    override_map = override_map or {}
    snapshot_index = _build_domestic_snapshot_index(domestic_snapshot_rows)
    normalized: list[dict] = []
    warnings: list[dict] = []
    exposure_amounts = {
        "domestic_direct": 0,
        "overseas_direct": 0,
        "overseas_indirect": 0,
        "cash": 0,
        "unknown": 0,
    }
    domestic_non_cash = 0

    for account_row in domestic_accounts:
        account = account_row["account"]
        account_label = account.get("label")
        snapshot = snapshot_index.get(account_label) or {}
        balance_data = snapshot.get("balance_data") or {}
        output1 = balance_data.get("output1") or []
        holdings_total = 0
        for row in output1:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("pdno") or "").strip()
            name = str(row.get("prdt_name") or "").strip()
            value_krw = parse_int(row.get("evlu_amt")) or 0
            quantity = parse_number(row.get("hldg_qty"))
            if not symbol or value_krw <= 0:
                continue
            classification = classify_domestic_holding(
                symbol,
                name,
                instrument_map.get(symbol),
                override_map.get(symbol),
            )
            holdings_total += value_krw
            domestic_non_cash += value_krw
            exposure_amounts[classification["exposure_type"]] += value_krw
            normalized.append({
                "account_label": account_label,
                "account_type": account.get("label"),
                "symbol": symbol,
                "name": name,
                "market": "KRX",
                "basis_category": "domestic_account",
                "exposure_type": classification["exposure_type"],
                "exposure_region": classification.get("exposure_region"),
                "asset_subtype": classification.get("asset_subtype"),
                "confidence": classification.get("confidence"),
                "quantity": quantity,
                "value_krw": value_krw,
                "value_foreign": None,
                "currency": "KRW",
                "raw_data": row,
            })
            if classification.get("warning"):
                warnings.append({
                    "account_label": account_label,
                    "symbol": symbol,
                    "name": name,
                    "reason": classification["warning"],
                    "confidence": classification.get("confidence"),
                    "source": classification.get("source"),
                })

        residual_cash = max((account_row.get("value_krw") or 0) - holdings_total, 0)
        if residual_cash:
            exposure_amounts["cash"] += residual_cash
            normalized.append({
                "account_label": account_label,
                "account_type": account.get("label"),
                "symbol": None,
                "name": "국내 예수금/현금성",
                "market": "KRW",
                "basis_category": "cash",
                "exposure_type": "cash",
                "exposure_region": "kr",
                "asset_subtype": "cash",
                "confidence": "high",
                "quantity": None,
                "value_krw": residual_cash,
                "value_foreign": None,
                "currency": "KRW",
                "raw_data": {"account_total": account_row.get("value_krw"), "holdings_total": holdings_total},
            })

    return normalized, {
        **exposure_amounts,
        "domestic_non_cash": domestic_non_cash,
    }, warnings


def build_total_asset_overview(
    portfolio_summary: dict,
    overseas_balance: dict,
    overseas_deposit: dict,
    accounts: list[AccountConfig],
    overseas_account: AccountConfig,
    top_n: int = 10,
    include_raw: bool = False,
    domestic_snapshot_rows: list[dict] | None = None,
    instrument_map: dict[str, dict] | None = None,
    override_map: dict[str, dict] | None = None,
    fallback_fx_rates: dict[str, dict] | None = None,
) -> dict:
    """Build token-efficient canonical total-asset overview response."""
    domestic_accounts = summarize_domestic_accounts(portfolio_summary, accounts)
    domestic_krw = sum(row["value_krw"] for row in domestic_accounts)
    overseas = summarize_overseas_holdings(
        overseas_balance,
        overseas_deposit,
        overseas_account,
        top_n,
        fallback_fx_rates,
    )
    overseas_stock_krw = overseas.get("stock_eval_amt_krw")
    overseas_cash_krw = overseas.get("cash_amt_krw") or 0
    overseas_total_krw = overseas.get("total_asset_amt_krw")
    total_krw = domestic_krw + overseas_total_krw if overseas_total_krw is not None else None
    known_total_krw = domestic_krw + (overseas.get("known_stock_eval_amt_krw") or 0) + overseas_cash_krw
    missing_fx_currencies = overseas.get("missing_fx_currencies") or []
    stale_fx_currencies = sorted(
        currency for currency, rate in overseas.get("fx_rates", {}).items()
        if rate.get("stale")
    )
    quality_flags = []
    if missing_fx_currencies:
        quality_flags.append({
            "code": "fx_rate_missing",
            "severity": "error",
            "currencies": missing_fx_currencies,
            "message": "해외 보유자산의 원화 환율이 없어 총자산을 완전하게 계산할 수 없습니다.",
        })
    if stale_fx_currencies:
        quality_flags.append({
            "code": "fx_rate_stale_fallback",
            "severity": "warning",
            "currencies": stale_fx_currencies,
            "message": "오래된 DB 환율 fallback으로 해외자산을 환산했습니다.",
        })
    fallback_currencies = sorted(
        currency for currency, rate in overseas.get("fx_rates", {}).items()
        if rate.get("source") == "db_cache"
    )
    if fallback_currencies:
        quality_flags.append({
            "code": "fx_rate_db_fallback",
            "severity": "warning",
            "currencies": fallback_currencies,
            "message": "KIS 예수금 응답에 환율이 없어 DB 캐시 환율을 사용했습니다.",
        })
    quality_status = "degraded" if missing_fx_currencies or stale_fx_currencies else "ok"
    is_complete = not missing_fx_currencies

    domestic_holdings, domestic_exposure, classification_warnings = summarize_domestic_holdings(
        domestic_accounts,
        domestic_snapshot_rows or [],
        instrument_map,
        override_map,
    )
    overseas_holdings = list(overseas.get("_normalized_holdings", []))
    classification_amounts = {
        "domestic_direct": domestic_exposure.get("domestic_direct", 0),
        "overseas_direct": domestic_exposure.get("overseas_direct", 0) + (overseas_stock_krw or 0),
        "overseas_indirect": domestic_exposure.get("overseas_indirect", 0),
        "cash": domestic_exposure.get("cash", 0) + overseas_cash_krw,
        "unknown": domestic_exposure.get("unknown", 0),
    }

    normalized_holdings = domestic_holdings + overseas_holdings
    if overseas_cash_krw:
        normalized_holdings.append({
            "account_label": overseas_account.label,
            "account_type": overseas_account.label,
            "symbol": None,
            "name": "해외 예수금/현금성",
            "market": "FX",
            "basis_category": "cash",
            "exposure_type": "cash",
            "exposure_region": "global",
            "asset_subtype": "cash",
            "confidence": "high",
            "quantity": None,
            "value_krw": overseas_cash_krw,
            "value_foreign": None,
            "currency": "KRW",
            "raw_data": overseas.get("deposit"),
        })

    for row in domestic_accounts:
        row["pct_of_total"] = pct(row.get("value_krw"), total_krw)
    for row in overseas["holdings_top"]:
        row["pct_of_total"] = pct(row.get("value_krw"), total_krw)

    domestic_vs_overseas = [
        {"label": "국내자산", "value_krw": domestic_krw, "pct": pct(domestic_krw, total_krw)},
        {"label": "해외자산", "value_krw": overseas_total_krw, "pct": pct(overseas_total_krw, total_krw)},
    ]
    overseas_stock_vs_cash = [
        {
            "label": "해외주식",
            "value_krw": overseas_stock_krw,
            "pct_of_overseas": pct(overseas_stock_krw, overseas_total_krw),
            "pct_of_total": pct(overseas_stock_krw, total_krw),
        },
        {
            "label": "해외 예수금/현금성",
            "value_krw": overseas_cash_krw,
            "pct_of_overseas": pct(overseas_cash_krw, overseas_total_krw),
            "pct_of_total": pct(overseas_cash_krw, total_krw),
        },
    ]

    by_account = [
        {
            "label": row["account"].get("display_name") or row["account"].get("label"),
            "account_label": row["account"].get("label"),
            "value_krw": row["value_krw"],
            "pct": row["pct_of_total"],
        }
        for row in domestic_accounts
    ]
    by_account.append({
        "label": "해외자산",
        "account_label": overseas_account.label,
        "value_krw": overseas_total_krw,
        "pct": pct(overseas_total_krw, total_krw),
    })

    by_account_basis = [
        {
            "label": "국내계좌 보유자산",
            "value_krw": domestic_exposure.get("domestic_non_cash", 0),
            "pct": pct(domestic_exposure.get("domestic_non_cash", 0), total_krw),
        },
        {
            "label": "해외계좌 보유자산",
            "value_krw": overseas_stock_krw,
            "pct": pct(overseas_stock_krw, total_krw),
        },
        {
            "label": "현금성",
            "value_krw": classification_amounts["cash"],
            "pct": pct(classification_amounts["cash"], total_krw),
        },
    ]

    by_economic_exposure = [
        {
            "label": "국내직접",
            "key": "domestic_direct",
            "value_krw": classification_amounts["domestic_direct"],
            "pct": pct(classification_amounts["domestic_direct"], total_krw),
        },
        {
            "label": "해외직접",
            "key": "overseas_direct",
            "value_krw": classification_amounts["overseas_direct"],
            "pct": pct(classification_amounts["overseas_direct"], total_krw),
        },
        {
            "label": "해외우회투자",
            "key": "overseas_indirect",
            "value_krw": classification_amounts["overseas_indirect"],
            "pct": pct(classification_amounts["overseas_indirect"], total_krw),
        },
        {
            "label": "현금성",
            "key": "cash",
            "value_krw": classification_amounts["cash"],
            "pct": pct(classification_amounts["cash"], total_krw),
        },
        {
            "label": "분류필요",
            "key": "unknown",
            "value_krw": classification_amounts["unknown"],
            "pct": pct(classification_amounts["unknown"], total_krw),
        },
    ]

    classification_summary = {
        "amounts": classification_amounts,
        "by_account_basis": by_account_basis,
        "by_economic_exposure": by_economic_exposure,
        "classification_warnings": classification_warnings,
    }

    result = {
        "source": "kis_portfolio_overview",
        "status": quality_status,
        "base_currency": "KRW",
        "data_quality": {
            "status": quality_status,
            "is_complete": is_complete,
            "flags": quality_flags,
            "warning_count": sum(flag.get("severity") == "warning" for flag in quality_flags),
            "error_count": sum(flag.get("severity") == "error" for flag in quality_flags),
        },
        "totals": {
            "domestic_eval_amt_krw": domestic_krw,
            "overseas_stock_eval_amt_krw": overseas_stock_krw,
            "overseas_cash_amt_krw": overseas_cash_krw,
            "overseas_total_asset_amt_krw": overseas_total_krw,
            "total_eval_amt_krw": total_krw,
        },
        "allocation": {
            "domestic_pct": pct(domestic_krw, total_krw),
            "overseas_pct": pct(overseas_total_krw, total_krw),
            "overseas_stock_pct": pct(overseas_stock_krw, total_krw),
            "overseas_cash_pct": pct(overseas_cash_krw, total_krw),
        },
        "classification_summary": classification_summary,
        "domestic": {
            "account_count": len(domestic_accounts),
            "latest_snapshot_at": portfolio_summary.get("latest_snapshot_at"),
            "accounts": domestic_accounts,
        },
        "overseas": {
            key: value
            for key, value in overseas.items()
            if not key.startswith("_")
        },
        "chart_data": {
            "domestic_vs_overseas": domestic_vs_overseas,
            "overseas_stock_vs_cash": overseas_stock_vs_cash,
            "by_account": by_account,
            "by_account_basis": by_account_basis,
            "by_economic_exposure": by_economic_exposure,
            "overseas_holdings_top": overseas["chart_data"],
        },
        "_normalized_holdings": normalized_holdings,
    }
    if not is_complete:
        result["totals"]["known_total_eval_amt_krw"] = known_total_krw
    if include_raw:
        result["raw"] = {
            "portfolio_summary": portfolio_summary,
            "overseas_balance": overseas_balance,
            "overseas_deposit": overseas_deposit,
            "domestic_snapshots": domestic_snapshot_rows or [],
        }
    return result
