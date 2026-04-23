"""Batch-safe order history collection services."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from kis_portfolio.account_registry import load_account_registry, scoped_account_env
from kis_portfolio.services.market_calendar import evaluate_krx_collection_gate
from kis_portfolio.services import kis_api


logger = logging.getLogger(__name__)
SEOUL_TZ = ZoneInfo("Asia/Seoul")


def resolve_yyyymmdd(value: str = "", *, now: datetime | None = None) -> str:
    """Resolve batch date tokens into YYYYMMDD using Asia/Seoul."""
    token = (value or "today").strip().lower()
    if token == "today":
        current = now.astimezone(SEOUL_TZ) if now else datetime.now(SEOUL_TZ)
        return current.strftime("%Y%m%d")
    return datetime.strptime(token, "%Y%m%d").strftime("%Y%m%d")


def _order_count(raw: dict) -> int:
    rows = raw.get("output1")
    return len(rows) if isinstance(rows, list) else 0


async def collect_domestic_order_history(
    date_yyyymmdd: str,
    *,
    now: datetime | None = None,
    close_grace_minutes: int = 5,
) -> dict:
    """Collect and store one-day domestic order history for every configured account."""
    trade_date = resolve_yyyymmdd(date_yyyymmdd)
    gate = evaluate_krx_collection_gate(
        trade_date,
        now=now,
        close_grace_minutes=close_grace_minutes,
    )
    if gate.status == "skipped":
        return {
            "source": "market_calendar",
            "status": "skipped",
            "market_type": "domestic",
            "date": trade_date,
            "count": 0,
            "success_count": 0,
            "error_count": 0,
            "accounts": [],
            "skipped_reason": gate.reason,
            "market_calendar": gate.calendar,
            "now_local": gate.now_local,
        }

    results = []

    for account in load_account_registry():
        try:
            with scoped_account_env(account):
                result = await kis_api.inquery_order_list(
                    trade_date,
                    trade_date,
                    save_history=True,
                    return_metadata=True,
                )
            raw = result["raw"]
            saved_order_history_id = result.get("saved_order_history_id")
            results.append({
                "status": "ok",
                "account": account.public_dict(),
                "order_count": _order_count(raw),
                "saved_order_history_id": saved_order_history_id,
                "history_status": "saved" if saved_order_history_id else "not_saved",
            })
        except Exception as exc:
            logger.warning("Domestic order history batch failed for %s: %s", account.label, exc)
            results.append({
                "status": "error",
                "account": account.public_dict(),
                "error": str(exc),
            })

    return {
        "source": "kis_api",
        "status": "ok",
        "market_type": "domestic",
        "date": trade_date,
        "count": len(results),
        "success_count": sum(1 for row in results if row["status"] == "ok"),
        "error_count": sum(1 for row in results if row["status"] == "error"),
        "accounts": results,
        "market_calendar": gate.calendar,
        "now_local": gate.now_local,
    }
