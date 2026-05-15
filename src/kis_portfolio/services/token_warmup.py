"""Operational helpers for observing or warming KIS access-token cache."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import httpx

from kis_portfolio.account_registry import get_account, load_account_registry, scoped_account_env
from kis_portfolio.auth import get_access_token, get_token_status
from kis_portfolio.clients.kis import DOMAIN
from kis_portfolio.observability import log_event, new_operation_id, operation_context

import logging


logger = logging.getLogger("kis-portfolio-token-warmup")
SEOUL_TZ = ZoneInfo("Asia/Seoul")


def parse_valid_through(value: str, *, now: datetime | None = None) -> datetime:
    try:
        hour_text, minute_text = value.split(":", 1)
        valid_time = time(hour=int(hour_text), minute=int(minute_text))
    except Exception as exc:
        raise ValueError("--valid-through must use HH:MM format, for example 16:30") from exc
    current = now or datetime.now(SEOUL_TZ).replace(tzinfo=None)
    return datetime.combine(current.date(), valid_time)


def _select_accounts(account_label: str):
    normalized = (account_label or "all").strip().lower()
    if normalized == "all":
        return load_account_registry()
    return [get_account(normalized)]


def _needs_refresh_for_valid_through(status: dict, valid_through_at: datetime) -> bool:
    refresh_after = status.get("refresh_after")
    if not refresh_after:
        return True
    try:
        refresh_after_dt = datetime.fromisoformat(str(refresh_after))
    except ValueError:
        return True
    return refresh_after_dt <= valid_through_at


async def warm_token_cache(
    *,
    account_label: str = "all",
    valid_through: str = "16:30",
    dry_run: bool = True,
) -> dict:
    operation_id = new_operation_id("batch")
    valid_through_at = parse_valid_through(valid_through)
    accounts = _select_accounts(account_label)
    rows = []
    with operation_context(operation_id):
        log_event(
            logger,
            "warm_token_cache_start",
            operation_id=operation_id,
            account_label=account_label,
            valid_through=valid_through_at,
            dry_run=dry_run,
            count=len(accounts),
        )
        for account in accounts:
            with scoped_account_env(account):
                before = get_token_status()
                needs_refresh = _needs_refresh_for_valid_through(before, valid_through_at)
                row = {
                    "account": account.public_dict(),
                    "before": before,
                    "valid_through": valid_through_at.isoformat(),
                    "needs_refresh": needs_refresh,
                    "dry_run": dry_run,
                    "refresh_status": "not_needed",
                }
                if needs_refresh:
                    row["refresh_status"] = "would_refresh" if dry_run else "pending"
                log_event(
                    logger,
                    "warm_token_cache_account_checked",
                    operation_id=operation_id,
                    account_label=account.label,
                    masked_cano=account.masked_cano,
                    valid_through=valid_through_at,
                    needs_refresh=needs_refresh,
                    dry_run=dry_run,
                )
                if needs_refresh and not dry_run:
                    try:
                        async with httpx.AsyncClient() as client:
                            await get_access_token(client, DOMAIN, force_refresh=True)
                        after = get_token_status()
                    except Exception as exc:
                        row["refresh_status"] = "error"
                        row["error"] = str(exc)
                        log_event(
                            logger,
                            "warm_token_cache_account_failed",
                            level=logging.WARNING,
                            operation_id=operation_id,
                            account_label=account.label,
                            masked_cano=account.masked_cano,
                            error_type=type(exc).__name__,
                        )
                    else:
                        row["refresh_status"] = "refreshed"
                        row["after"] = after
                        log_event(
                            logger,
                            "warm_token_cache_account_refreshed",
                            operation_id=operation_id,
                            account_label=account.label,
                            masked_cano=account.masked_cano,
                            storage=after.get("storage"),
                            expires_at=after.get("expires_at"),
                        )
                rows.append(row)

    error_count = sum(1 for row in rows if row["refresh_status"] == "error")
    refresh_count = sum(1 for row in rows if row["refresh_status"] == "refreshed")
    would_refresh_count = sum(1 for row in rows if row["refresh_status"] == "would_refresh")
    status = "ok" if error_count == 0 else "partial_error"
    return {
        "source": "token_cache",
        "operation": "warm-token-cache",
        "status": status,
        "dry_run": dry_run,
        "valid_through": valid_through_at.isoformat(),
        "count": len(rows),
        "needs_refresh_count": sum(1 for row in rows if row["needs_refresh"]),
        "would_refresh_count": would_refresh_count,
        "refresh_count": refresh_count,
        "error_count": error_count,
        "accounts": rows,
        "diagnostics": {"operation_id": operation_id},
    }
