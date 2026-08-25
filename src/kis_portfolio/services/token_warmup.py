"""Operational helpers for observing or warming KIS access-token cache."""

from __future__ import annotations

import os
from datetime import datetime, time
from urllib.parse import urlsplit, urlunsplit
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


def _health_url_from_service_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


def _split_warmup_urls(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        item.strip()
        for chunk in value.split(",")
        for item in chunk.split()
        if item.strip()
    ]


def resolve_service_health_urls() -> list[str]:
    configured = _split_warmup_urls(os.environ.get("KIS_SERVICE_WARMUP_HEALTH_URLS"))
    if configured:
        return list(dict.fromkeys(configured))

    candidates = [
        _health_url_from_service_url(os.environ.get("KIS_AUTH_BASE_URL")),
        _health_url_from_service_url(os.environ.get("KIS_AUTH_ISSUER_URL")),
        _health_url_from_service_url(os.environ.get("KIS_RESOURCE_SERVER_URL")),
    ]
    return [url for url in dict.fromkeys(candidates) if url]


async def warm_service_health(
    urls: list[str] | None = None,
    *,
    timeout_seconds: float = 10.0,
) -> list[dict]:
    resolved_urls = urls if urls is not None else resolve_service_health_urls()
    rows = []
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        for url in resolved_urls:
            row = {"url": url, "status": "pending"}
            try:
                response = await client.get(url)
            except Exception as exc:
                row.update({
                    "status": "error",
                    "error_type": type(exc).__name__,
                })
                log_event(
                    logger,
                    "service_health_warmup_failed",
                    level=logging.WARNING,
                    url=url,
                    error_type=type(exc).__name__,
                )
            else:
                row.update({
                    "status": "ok" if 200 <= response.status_code < 300 else "unexpected_status",
                    "http_status": response.status_code,
                })
                log_event(
                    logger,
                    "service_health_warmup_complete",
                    url=url,
                    http_status=response.status_code,
                    status=row["status"],
                )
            rows.append(row)
    return rows


async def warm_token_cache(
    *,
    account_label: str = "all",
    valid_through: str = "16:30",
    dry_run: bool = True,
    warm_service_health_checks: bool = False,
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
    service_health_rows = []
    if warm_service_health_checks:
        service_health_rows = await warm_service_health()
    service_health_error_count = sum(
        1 for row in service_health_rows
        if row["status"] not in {"ok"}
    )
    # Health warming is best-effort: a cold service may exceed this short probe while
    # the token refresh itself succeeds. Keep the batch result tied to token safety.
    status = "ok" if error_count == 0 else "partial_error"
    return {
        "source": "token_cache",
        "operation": "warm-token-cache",
        "status": status,
        "dry_run": dry_run,
        "warm_service_health": warm_service_health_checks,
        "valid_through": valid_through_at.isoformat(),
        "count": len(rows),
        "needs_refresh_count": sum(1 for row in rows if row["needs_refresh"]),
        "would_refresh_count": would_refresh_count,
        "refresh_count": refresh_count,
        "error_count": error_count,
        "service_health_error_count": service_health_error_count,
        "service_health_status": "ok" if service_health_error_count == 0 else "partial_error",
        "service_health": service_health_rows,
        "accounts": rows,
        "diagnostics": {"operation_id": operation_id},
    }
