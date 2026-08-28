"""Overseas account history services with DB-first read semantics."""

from __future__ import annotations

import logging
import os
from typing import Any

from kis_portfolio.account_registry import get_account, scoped_account_env
from kis_portfolio.accounts import infer_account_type
from kis_portfolio.common.values import to_float
from kis_portfolio.services import kis_api
from kis_portfolio.services.order_history import resolve_yyyymmdd
from kis_portfolio import db as kisdb


logger = logging.getLogger(__name__)
HISTORY_SOURCES = {"auto", "db", "kis_api"}


def _current_account() -> tuple[str, str, str]:
    account_id = kis_api._current_account_id()
    account_product_code = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    account_type = os.environ.get("KIS_ACCOUNT_LABEL") or infer_account_type(
        account_id,
        account_product_code,
    )
    return account_id, account_product_code, account_type


def _resolve_source(source: str = "") -> str:
    token = (source or "auto").strip().lower()
    if token not in HISTORY_SOURCES:
        raise ValueError(f"source must be one of {sorted(HISTORY_SOURCES)}")
    return token


def _compact_yyyymmdd(value: Any) -> str | None:
    if value in ("", None):
        return None
    return str(value).replace("-", "")


def _pick_value(row: dict, *candidates: str):
    for candidate in candidates:
        for key in (candidate, candidate.lower(), candidate.upper()):
            value = row.get(key)
            if value not in ("", None):
                return value
    return None


def _row_list(raw: dict, key: str) -> list[dict]:
    rows = raw.get(key)
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if isinstance(rows, dict) and rows:
        return [rows]
    return []


def _order_count(raw: dict) -> int:
    return len(_row_list(raw, "output"))


def _transaction_count(raw: dict) -> int:
    return len(_row_list(raw, "output1"))


def _normalize_side(value: str) -> str:
    token = (value or "00").strip()
    return token or "00"


def _normalize_exchange(value: str, *, default: str) -> str:
    token = (value or default).strip().upper()
    return token or default


def _normalize_overseas_orders(
    raw: dict,
    *,
    fallback_date: str,
    fallback_exchange: str,
    saved_order_history_id: str | None,
    source: str,
) -> list[dict]:
    account_id, account_product_code, account_type = _current_account()
    normalized = []

    for row in _row_list(raw, "output"):
        order_no = _pick_value(row, "odno", "ord_no", "ovrs_odno")
        order_date = _compact_yyyymmdd(
            _pick_value(row, "ord_dt", "order_date", "ord_date") or fallback_date
        )
        if not order_no or not order_date:
            logger.warning("Skipping overseas order row without order identity: %s", row)
            continue
        normalized.append({
            "account_id": account_id,
            "account_product_code": account_product_code,
            "account_type": account_type,
            "order_date": order_date,
            "exchange_code": (
                _pick_value(row, "ovrs_excg_cd", "ovrs_excg", "excg_cd")
                or (fallback_exchange if fallback_exchange != "%" else "")
            ),
            "order_branch_no": str(_pick_value(row, "ord_gno_brno", "ord_gno_brno_org") or ""),
            "order_no": str(order_no),
            "symbol": _pick_value(row, "pdno", "ovrs_pdno", "symb"),
            "symbol_name": _pick_value(row, "prdt_name", "ovrs_item_name", "item_name"),
            "side_code": _pick_value(row, "sll_buy_dvsn_cd", "sll_buy_dvsn"),
            "side_name": _pick_value(row, "sll_buy_dvsn_cd_name", "sll_buy_dvsn_name"),
            "order_type_code": _pick_value(row, "ord_dvsn", "ord_dvsn_cd"),
            "order_type_name": _pick_value(row, "ord_dvsn_name"),
            "order_time": _pick_value(row, "ord_tmd", "ord_time"),
            "order_qty": to_float(_pick_value(row, "ord_qty", "ft_ord_qty", "tot_ord_qty")),
            "order_price": to_float(_pick_value(row, "ovrs_ord_unpr", "ord_unpr", "ft_ord_unpr3")),
            "avg_price": to_float(_pick_value(row, "avg_prvs", "avg_pric", "ft_ccld_unpr3")),
            "filled_qty": to_float(_pick_value(row, "ft_ccld_qty", "tot_ccld_qty", "ccld_qty")),
            "filled_amount": to_float(_pick_value(row, "ft_ccld_amt3", "tot_ccld_amt", "ccld_amt")),
            "pending_qty": to_float(_pick_value(row, "nccs_qty", "rmn_qty")),
            "currency": _pick_value(row, "tr_crcy_cd", "crcy_cd", "ovrs_crcy_cd"),
            "last_source": source,
            "last_order_history_id": saved_order_history_id,
            "raw_data": row,
        })
    return normalized


def _format_overseas_order(row: dict) -> dict:
    return {
        "order_no": row.get("order_no"),
        "order_branch_no": row.get("order_branch_no") or None,
        "exchange_code": row.get("exchange_code"),
        "symbol": row.get("symbol"),
        "symbol_name": row.get("symbol_name"),
        "order_date": _compact_yyyymmdd(row.get("order_date")),
        "order_time": row.get("order_time"),
        "side": row.get("side_name") or row.get("side_code"),
        "side_code": row.get("side_code"),
        "order_type": row.get("order_type_name") or row.get("order_type_code"),
        "order_type_code": row.get("order_type_code"),
        "order_qty": row.get("order_qty"),
        "order_price": row.get("order_price"),
        "avg_price": row.get("avg_price"),
        "filled_qty": row.get("filled_qty"),
        "filled_amount": row.get("filled_amount"),
        "pending_qty": row.get("pending_qty"),
        "currency": row.get("currency"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "last_source": row.get("last_source"),
        "last_order_history_id": row.get("last_order_history_id"),
        "raw": row.get("raw_data"),
    }


def _sync_overseas_orders(
    raw: dict,
    *,
    fallback_date: str,
    fallback_exchange: str,
    saved_order_history_id: str | None,
    source: str,
) -> int:
    return kisdb.upsert_overseas_orders(
        _normalize_overseas_orders(
            raw,
            fallback_date=fallback_date,
            fallback_exchange=fallback_exchange,
            saved_order_history_id=saved_order_history_id,
            source=source,
        )
    )


def _load_overseas_orders(
    start_date: str,
    end_date: str,
    *,
    exchange: str = "",
    symbol: str = "",
) -> list[dict]:
    account_id, account_product_code, _ = _current_account()
    rows = kisdb.get_overseas_orders(
        account_id,
        account_product_code,
        start_date,
        end_date,
        exchange_code=exchange,
        symbol=symbol,
    )
    return [_format_overseas_order(row) for row in rows]


def _normalize_overseas_transactions(
    raw: dict,
    *,
    fallback_date: str,
    fallback_exchange: str,
    saved_transaction_history_id: str | None,
    source: str,
) -> list[dict]:
    account_id, account_product_code, account_type = _current_account()
    normalized = []

    for row in _row_list(raw, "output1"):
        transaction_date = _compact_yyyymmdd(
            _pick_value(row, "erlm_dt", "trad_dt", "tr_dt", "ccld_dt", "ord_dt") or fallback_date
        )
        if not transaction_date:
            logger.warning("Skipping overseas transaction row without transaction date: %s", row)
            continue
        normalized.append({
            "account_id": account_id,
            "account_product_code": account_product_code,
            "account_type": account_type,
            "transaction_date": transaction_date,
            "exchange_code": fallback_exchange or _pick_value(row, "ovrs_excg_cd", "ovrs_excg", "excg_cd") or "",
            "symbol": _pick_value(row, "pdno", "ovrs_pdno", "symb"),
            "symbol_name": _pick_value(row, "prdt_name", "ovrs_item_name", "item_name"),
            "side_code": _pick_value(row, "sll_buy_dvsn_cd", "sll_buy_dvsn"),
            "side_name": _pick_value(row, "sll_buy_dvsn_cd_name", "sll_buy_dvsn_name"),
            "transaction_type_code": _pick_value(row, "trad_dvsn_cd", "tr_dvsn_cd"),
            "transaction_type_name": _pick_value(row, "trad_dvsn_name", "tr_dvsn_name"),
            "quantity": to_float(_pick_value(row, "tr_qty", "ccld_qty", "ft_ccld_qty", "qty")),
            "price": to_float(_pick_value(
                row, "ft_ccld_unpr2", "ovrs_stck_ccld_unpr", "tr_unpr", "ccld_unpr",
                "ft_ccld_unpr3", "unpr",
            )),
            "amount": to_float(_pick_value(row, "tr_amt", "ccld_amt", "frcr_ccld_amt", "ovrs_tr_amt")),
            "fee": to_float(_pick_value(row, "frcr_fee1", "fee", "ovrs_fee", "frcr_fee")),
            "tax": to_float(_pick_value(row, "tax", "tax_amt", "frcr_tax")),
            "currency": _pick_value(row, "tr_crcy_cd", "crcy_cd", "ovrs_crcy_cd"),
            "settlement_amount": to_float(_pick_value(row, "sttl_amt", "frcr_sttl_amt", "settlement_amount")),
            "fx_rate": to_float(_pick_value(row, "erlm_exrt", "exrt", "aply_exrt", "fx_rate")),
            "settlement_date": _compact_yyyymmdd(_pick_value(row, "sttl_dt")),
            "domestic_fee": to_float(_pick_value(row, "dmst_frcr_fee1")),
            "order_no": _pick_value(row, "odno", "ord_no", "ovrs_odno"),
            "last_source": source,
            "last_transaction_history_id": saved_transaction_history_id,
            "raw_data": row,
        })
    return normalized


def _format_overseas_transaction(row: dict) -> dict:
    raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
    return {
        "transaction_hash": row.get("transaction_hash"),
        "transaction_date": _compact_yyyymmdd(row.get("transaction_date")),
        "exchange_code": row.get("exchange_code"),
        "symbol": row.get("symbol"),
        "symbol_name": row.get("symbol_name"),
        "side": row.get("side_name") or row.get("side_code"),
        "side_code": row.get("side_code"),
        "transaction_type": row.get("transaction_type_name") or row.get("transaction_type_code"),
        "transaction_type_code": row.get("transaction_type_code"),
        "quantity": row.get("quantity"),
        "price": row.get("price"),
        "amount": row.get("amount"),
        "fee": row.get("fee"),
        "tax": row.get("tax"),
        "currency": row.get("currency"),
        "settlement_amount": row.get("settlement_amount"),
        "fx_rate": row.get("fx_rate"),
        "settlement_date": row.get("settlement_date") or _compact_yyyymmdd(_pick_value(raw, "sttl_dt")),
        "domestic_fee": row.get("domestic_fee") or to_float(_pick_value(raw, "dmst_frcr_fee1")),
        "order_no": row.get("order_no"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "last_source": row.get("last_source"),
        "last_transaction_history_id": row.get("last_transaction_history_id"),
        "raw": row.get("raw_data"),
    }


def _sync_overseas_transactions(
    raw: dict,
    *,
    fallback_date: str,
    fallback_exchange: str,
    saved_transaction_history_id: str | None,
    source: str,
) -> int:
    return kisdb.upsert_overseas_transactions(
        _normalize_overseas_transactions(
            raw,
            fallback_date=fallback_date,
            fallback_exchange=fallback_exchange,
            saved_transaction_history_id=saved_transaction_history_id,
            source=source,
        )
    )


def _load_overseas_transactions(
    start_date: str,
    end_date: str,
    *,
    exchange: str = "",
    symbol: str = "",
) -> list[dict]:
    account_id, account_product_code, _ = _current_account()
    rows = kisdb.get_overseas_transactions(
        account_id,
        account_product_code,
        start_date,
        end_date,
        exchange_code=exchange,
        symbol=symbol,
    )
    return [_format_overseas_transaction(row) for row in rows]


def _history_response(
    *,
    source: str,
    requested_source: str,
    market_type: str,
    canonical_store: str,
    query: dict,
    rows: list[dict],
    raw: dict | None = None,
    fetched_at: str | None = None,
    snapshot_id: str | None = None,
    snapshot_status: str | None = None,
    canonical_write_count: int | None = None,
) -> dict:
    payload = {
        "source": source,
        "status": "ok",
        "market_type": market_type,
        "canonical_store": canonical_store,
        "requested_source": requested_source,
        "query": query,
        "row_count": len(rows),
        "rows": rows,
    }
    if raw is not None:
        payload["raw"] = raw
    if fetched_at:
        payload["fetched_at"] = fetched_at
    if snapshot_id:
        payload["snapshot_id"] = snapshot_id
    if snapshot_status:
        payload["snapshot_status"] = snapshot_status
    if canonical_write_count is not None:
        payload["canonical_write_count"] = canonical_write_count
    return payload


async def get_overseas_order_history(
    start_date: str,
    end_date: str,
    *,
    symbol: str = "",
    exchange: str = "%",
    side: str = "00",
    fill_status: str = "00",
    source: str = "auto",
    save_history: bool = True,
) -> dict:
    """Get overseas order/execution history with DB-first cache semantics."""
    resolved_source = _resolve_source(source)
    exchange = _normalize_exchange(exchange, default="%")
    side = _normalize_side(side)
    fill_status = _normalize_side(fill_status)
    symbol = (symbol or "").strip().upper()
    account_id, account_product_code, _ = _current_account()
    query = {
        "start_date": start_date,
        "end_date": end_date,
        "exchange": exchange,
        "symbol": symbol or None,
        "side": side,
        "fill_status": fill_status,
    }

    if resolved_source in {"auto", "db"}:
        snapshot = kisdb.get_latest_overseas_order_history_snapshot(
            account_id,
            account_product_code,
            start_date,
            end_date,
            exchange,
            symbol,
            side,
            fill_status,
        )
        if snapshot:
            rows = _load_overseas_orders(start_date, end_date, exchange=exchange, symbol=symbol)
            if not rows and _order_count(snapshot["data"]) > 0:
                _sync_overseas_orders(
                    snapshot["data"],
                    fallback_date=start_date,
                    fallback_exchange=exchange,
                    saved_order_history_id=snapshot.get("id"),
                    source="overseas_order_history_backfill",
                )
                rows = _load_overseas_orders(start_date, end_date, exchange=exchange, symbol=symbol)
            return _history_response(
                source="overseas_orders_db",
                requested_source=resolved_source,
                market_type="overseas",
                canonical_store="overseas_orders",
                query=query,
                rows=rows,
                raw=snapshot["data"],
                fetched_at=snapshot.get("fetched_at"),
                snapshot_id=snapshot.get("id"),
                snapshot_status="cached",
            )
        if resolved_source == "db":
            return {
                "source": "overseas_orders_db",
                "status": "cache_miss",
                "market_type": "overseas",
                "canonical_store": "overseas_orders",
                "requested_source": resolved_source,
                "query": query,
                "row_count": 0,
                "rows": [],
                "message": "No saved overseas order history snapshot found for the requested account/date range.",
            }

    fetched = await kis_api.inquery_overseas_order_ccnl(
        start_date,
        end_date,
        symbol=symbol,
        exchange=exchange,
        side=side,
        fill_status=fill_status,
        save_history=save_history,
        return_metadata=True,
    )
    saved_order_history_id = fetched.get("saved_order_history_id")
    canonical_write_count = _sync_overseas_orders(
        fetched["raw"],
        fallback_date=start_date,
        fallback_exchange=exchange,
        saved_order_history_id=saved_order_history_id,
        source="kis_api",
    )
    return _history_response(
        source="kis_api",
        requested_source=resolved_source,
        market_type="overseas",
        canonical_store="overseas_orders",
        query=query,
        rows=_load_overseas_orders(start_date, end_date, exchange=exchange, symbol=symbol),
        raw=fetched["raw"],
        snapshot_id=saved_order_history_id,
        snapshot_status="saved" if saved_order_history_id else "not_saved",
        canonical_write_count=canonical_write_count,
    )


async def get_overseas_transaction_history(
    start_date: str,
    end_date: str,
    *,
    symbol: str = "",
    exchange: str = "NAS",
    side: str = "00",
    loan_dvsn_cd: str = "",
    source: str = "auto",
    save_history: bool = True,
) -> dict:
    """Get overseas daily transaction ledger with DB-first cache semantics."""
    resolved_source = _resolve_source(source)
    exchange = _normalize_exchange(exchange, default="NAS")
    side = _normalize_side(side)
    symbol = (symbol or "").strip().upper()
    loan_dvsn_cd = (loan_dvsn_cd or "").strip()
    account_id, account_product_code, _ = _current_account()
    query = {
        "start_date": start_date,
        "end_date": end_date,
        "exchange": exchange,
        "symbol": symbol or None,
        "side": side,
        "loan_dvsn_cd": loan_dvsn_cd or None,
    }

    if resolved_source in {"auto", "db"}:
        snapshot = kisdb.get_latest_overseas_transaction_history_snapshot(
            account_id,
            account_product_code,
            start_date,
            end_date,
            exchange,
            symbol,
            side,
            loan_dvsn_cd,
        )
        if snapshot:
            rows = _load_overseas_transactions(start_date, end_date, exchange=exchange, symbol=symbol)
            if not rows and _transaction_count(snapshot["data"]) > 0:
                _sync_overseas_transactions(
                    snapshot["data"],
                    fallback_date=start_date,
                    fallback_exchange=exchange,
                    saved_transaction_history_id=snapshot.get("id"),
                    source="overseas_transaction_history_backfill",
                )
                rows = _load_overseas_transactions(start_date, end_date, exchange=exchange, symbol=symbol)
            return _history_response(
                source="overseas_transactions_db",
                requested_source=resolved_source,
                market_type="overseas",
                canonical_store="overseas_transactions",
                query=query,
                rows=rows,
                raw=snapshot["data"],
                fetched_at=snapshot.get("fetched_at"),
                snapshot_id=snapshot.get("id"),
                snapshot_status="cached",
            )
        if resolved_source == "db":
            return {
                "source": "overseas_transactions_db",
                "status": "cache_miss",
                "market_type": "overseas",
                "canonical_store": "overseas_transactions",
                "requested_source": resolved_source,
                "query": query,
                "row_count": 0,
                "rows": [],
                "message": "No saved overseas transaction history snapshot found for the requested account/date range.",
            }

    fetched = await kis_api.inquery_overseas_period_trans(
        start_date,
        end_date,
        exchange=exchange,
        symbol=symbol,
        side=side,
        loan_dvsn_cd=loan_dvsn_cd,
        save_history=save_history,
        return_metadata=True,
    )
    saved_transaction_history_id = fetched.get("saved_transaction_history_id")
    canonical_write_count = _sync_overseas_transactions(
        fetched["raw"],
        fallback_date=start_date,
        fallback_exchange=exchange,
        saved_transaction_history_id=saved_transaction_history_id,
        source="kis_api",
    )
    return _history_response(
        source="kis_api",
        requested_source=resolved_source,
        market_type="overseas",
        canonical_store="overseas_transactions",
        query=query,
        rows=_load_overseas_transactions(start_date, end_date, exchange=exchange, symbol=symbol),
        raw=fetched["raw"],
        snapshot_id=saved_transaction_history_id,
        snapshot_status="saved" if saved_transaction_history_id else "not_saved",
        canonical_write_count=canonical_write_count,
    )


async def get_overseas_settlement_balance(
    base_date: str,
    *,
    wcrc_frcr_dvsn_cd: str = "01",
    inqr_dvsn_cd: str = "00",
    save_snapshot: bool = True,
) -> dict:
    """Fetch overseas settlement-basis balance and optionally save the raw snapshot."""
    result = await kis_api.inquery_overseas_paymt_stdr_balance(
        base_date,
        wcrc_frcr_dvsn_cd=wcrc_frcr_dvsn_cd,
        inqr_dvsn_cd=inqr_dvsn_cd,
        save_snapshot=save_snapshot,
        return_metadata=True,
    )
    return {
        "source": "kis_api",
        "status": "ok",
        "market_type": "overseas",
        "query": {
            "base_date": base_date,
            "wcrc_frcr_dvsn_cd": wcrc_frcr_dvsn_cd,
            "inqr_dvsn_cd": inqr_dvsn_cd,
        },
        "snapshot_status": "saved" if result.get("saved_snapshot_id") else "not_saved",
        "saved_snapshot_id": result.get("saved_snapshot_id"),
        "raw": result["raw"],
    }


async def collect_overseas_transaction_history(
    date_yyyymmdd: str,
    *,
    account_label: str = "brokerage",
    exchange: str = "NAS",
) -> dict:
    """Collect one-day overseas daily transaction history for one configured account."""
    trade_date = resolve_yyyymmdd(date_yyyymmdd)
    account = get_account(account_label)
    try:
        with scoped_account_env(account):
            result = await get_overseas_transaction_history(
                trade_date,
                trade_date,
                exchange=exchange,
                source="kis_api",
                save_history=True,
            )
        return {
            "source": "kis_api",
            "status": "ok",
            "market_type": "overseas",
            "date": trade_date,
            "account": account.public_dict(),
            "exchange": exchange,
            "transaction_count": result.get("row_count", 0),
            "snapshot_id": result.get("snapshot_id"),
            "snapshot_status": result.get("snapshot_status"),
            "canonical_store": result.get("canonical_store"),
            "canonical_write_count": result.get("canonical_write_count", 0),
        }
    except Exception as exc:
        logger.warning("Overseas transaction collection failed for %s: %s", account.label, exc)
        return {
            "source": "kis_api",
            "status": "error",
            "market_type": "overseas",
            "date": trade_date,
            "account": account.public_dict(),
            "exchange": exchange,
            "error": str(exc),
        }
