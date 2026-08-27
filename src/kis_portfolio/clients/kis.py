"""Shared KIS API constants and rate-limited request helpers."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

import httpx

from kis_portfolio.observability import current_or_new_operation_id, log_event

DOMAIN = "https://openapi.koreainvestment.com:9443"
VIRTUAL_DOMAIN = "https://openapivts.koreainvestment.com:29443"
CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"
DEFAULT_REAL_MIN_INTERVAL_SECONDS = 0.15
DEFAULT_VIRTUAL_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_TOKEN_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS = 1.0
KIS_RATE_LIMIT_CODES = frozenset({"EGW00201", "EGW00215"})
KIS_RATE_LIMIT_MESSAGE_MARKERS = (
    "초당 거래건수",
    "지정 시간 내 api 호출",
    "지정시간 내 api 호출",
)
logger = logging.getLogger("kis-portfolio-client")


class KISApiError(RuntimeError):
    """Raised when a KIS API request fails."""


class KISRateLimitError(KISApiError):
    """Raised when KIS still rejects a request after the bounded retry."""


@dataclass
class _RateLimitState:
    lock: asyncio.Lock
    next_allowed_at: float = 0.0


_LOOP_LIMITERS: WeakKeyDictionary = WeakKeyDictionary()


def clear_kis_rate_limiters() -> None:
    """Clear process-local limiter state for tests and controlled diagnostics."""
    _LOOP_LIMITERS.clear()


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number.")
    return value


def kis_min_interval_seconds(domain: str, *, request_kind: str = "rest") -> float:
    """Resolve the minimum process-wide interval for a KIS request class."""
    if request_kind == "token":
        return _positive_float_env(
            "KIS_TOKEN_MIN_INTERVAL_SECONDS",
            DEFAULT_TOKEN_MIN_INTERVAL_SECONDS,
        )
    if domain.startswith(VIRTUAL_DOMAIN):
        return _positive_float_env(
            "KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS",
            DEFAULT_VIRTUAL_MIN_INTERVAL_SECONDS,
        )
    return _positive_float_env(
        "KIS_REAL_API_MIN_INTERVAL_SECONDS",
        DEFAULT_REAL_MIN_INTERVAL_SECONDS,
    )


def _limiter_scope(domain: str, request_kind: str) -> str:
    environment = "virtual" if domain.startswith(VIRTUAL_DOMAIN) else "real"
    return f"{request_kind}:{environment}"


async def wait_for_kis_slot(domain: str, *, request_kind: str = "rest") -> float:
    """Serialize request starts with a conservative process-wide interval."""
    loop = asyncio.get_running_loop()
    limiters = _LOOP_LIMITERS.setdefault(loop, {})
    scope = _limiter_scope(domain, request_kind)
    state = limiters.get(scope)
    if state is None:
        state = _RateLimitState(lock=asyncio.Lock())
        limiters[scope] = state

    interval = kis_min_interval_seconds(domain, request_kind=request_kind)
    async with state.lock:
        now = loop.time()
        delay = max(0.0, state.next_allowed_at - now)
        if delay:
            await asyncio.sleep(delay)
        state.next_allowed_at = loop.time() + interval
    return delay


def _response_fields(response: httpx.Response) -> dict[str, Any]:
    fields: dict[str, Any] = {"http_status": response.status_code}
    try:
        payload = response.json()
    except Exception:
        return fields
    if isinstance(payload, dict):
        fields.update({
            "kis_msg_cd": payload.get("msg_cd"),
            "kis_msg1": payload.get("msg1"),
            "rt_cd": payload.get("rt_cd"),
        })
    return fields


def is_kis_rate_limit_response(response: httpx.Response) -> bool:
    """Recognize documented and observed KIS REST rate-limit responses."""
    if response.status_code == 429:
        return True
    fields = _response_fields(response)
    if fields.get("kis_msg_cd") in KIS_RATE_LIMIT_CODES:
        return True
    message = str(fields.get("kis_msg1") or "").lower()
    return any(marker in message for marker in KIS_RATE_LIMIT_MESSAGE_MARKERS)


async def request_kis(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    domain: str | None = None,
    rate_limit_retries: int = 1,
    **kwargs: Any,
) -> httpx.Response:
    """Issue a throttled KIS REST request and retry a rate rejection once."""
    domain = domain or (VIRTUAL_DOMAIN if url.startswith(VIRTUAL_DOMAIN) else DOMAIN)
    request_method = getattr(client, method.lower())
    operation_id = current_or_new_operation_id("kis")
    for attempt in range(rate_limit_retries + 1):
        queued_seconds = await wait_for_kis_slot(domain)
        response = await request_method(url, **kwargs)
        if not is_kis_rate_limit_response(response):
            return response

        fields = _response_fields(response)
        will_retry = attempt < rate_limit_retries
        log_event(
            logger,
            "kis_rate_limit_rejected",
            level=logging.WARNING,
            operation_id=operation_id,
            attempt=attempt + 1,
            queued_ms=round(queued_seconds * 1000, 1),
            retried=will_retry,
            **fields,
        )
        if will_retry:
            retry_delay = _positive_float_env(
                "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS",
                DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(retry_delay)
            continue

        raise KISRateLimitError(
            "KIS API rate limit persisted after retry: "
            f"http_status={fields.get('http_status')} "
            f"msg_cd={fields.get('kis_msg_cd')}"
        )

    raise AssertionError("unreachable")
