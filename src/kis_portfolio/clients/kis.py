"""Shared KIS API constants and resilient request helpers."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

import httpx

from kis_portfolio.observability import current_or_new_operation_id, log_event

from .kis_resilience import (
    DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS,
    DEFAULT_REAL_MIN_INTERVAL_SECONDS,
    DEFAULT_TOKEN_MIN_INTERVAL_SECONDS,
    DEFAULT_VIRTUAL_MIN_INTERVAL_SECONDS,
    KISApiError,
    KISBulkheadRejectedError,
    KISCircuitOpenError,
    KISDeadlineExceeded,
    KISRateLimitError,
    KISRequestPolicy,
    KISTransientError,
    allow_circuit_request,
    bulkhead_slot,
    circuit_scope,
    clear_kis_resilience_state,
    full_jitter_delay,
    impose_rate_limit_cooldown,
    min_interval_seconds,
    positive_float_env,
    record_circuit_failure,
    record_circuit_success,
    record_rate_limit_success,
    release_circuit_probe,
    request_policy,
    wait_for_slot,
)

DOMAIN = "https://openapi.koreainvestment.com:9443"
VIRTUAL_DOMAIN = "https://openapivts.koreainvestment.com:29443"
CONTENT_TYPE = "application/json"
AUTH_TYPE = "Bearer"
KIS_RATE_LIMIT_CODES = frozenset({"EGW00201", "EGW00215"})
KIS_RATE_LIMIT_MESSAGE_MARKERS = (
    "초당 거래건수",
    "지정 시간 내 api 호출",
    "지정시간 내 api 호출",
)
TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
logger = logging.getLogger("kis-portfolio-client")


def clear_kis_rate_limiters() -> None:
    """Backward-compatible test hook that clears all resilience state."""
    clear_kis_resilience_state()


def _positive_float_env(name: str, default: float) -> float:
    """Backward-compatible alias retained for existing callers and tests."""
    return positive_float_env(name, default)


def kis_min_interval_seconds(domain: str, *, request_kind: str = "rest") -> float:
    return min_interval_seconds(
        domain,
        VIRTUAL_DOMAIN,
        request_kind=request_kind,
    )


async def wait_for_kis_slot(domain: str, *, request_kind: str = "rest") -> float:
    return await wait_for_slot(
        domain,
        VIRTUAL_DOMAIN,
        request_kind=request_kind,
    )


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


def _retry_after_seconds(response: httpx.Response) -> float | None:
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _endpoint_label(url: str) -> str:
    return urlsplit(url).path or "/"


async def _sleep_with_deadline(delay: float, deadline: float) -> None:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0 or delay >= remaining:
        raise KISDeadlineExceeded("KIS request deadline exhausted before retry.")
    await asyncio.sleep(delay)


async def request_kis(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    domain: str | None = None,
    policy: str | KISRequestPolicy | None = None,
    retry_safe: bool | None = None,
    rate_limit_retries: int = 1,
    **kwargs: Any,
) -> httpx.Response:
    """Issue a paced, bounded and observable KIS REST request.

    Only idempotent methods are retried by default. Callers must explicitly set
    retry_safe=True for a safe POST such as hash-key generation. Live order
    POSTs must never opt in.
    """
    domain = domain or (VIRTUAL_DOMAIN if url.startswith(VIRTUAL_DOMAIN) else DOMAIN)
    selected_policy = request_policy(policy)
    request_method_name = method.upper()
    request_method = getattr(client, request_method_name.lower())
    may_retry = retry_safe if retry_safe is not None else request_method_name in IDEMPOTENT_METHODS
    max_attempts = max(selected_policy.max_attempts, rate_limit_retries + 1)
    operation_id = current_or_new_operation_id("kis")
    endpoint = _endpoint_label(url)
    breaker_scope = circuit_scope(domain, VIRTUAL_DOMAIN, url)
    loop = asyncio.get_running_loop()
    started = perf_counter()
    deadline = loop.time() + selected_policy.total_timeout_seconds
    rate_rejections = 0
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise KISDeadlineExceeded(
                f"KIS {selected_policy.name} request exceeded its total deadline."
            ) from last_error

        try:
            allow_circuit_request(breaker_scope)
        except KISCircuitOpenError:
            log_event(
                logger,
                "kis_circuit_rejected",
                level=logging.WARNING,
                operation_id=operation_id,
                endpoint=endpoint,
                policy=selected_policy.name,
            )
            raise

        queue_timeout = min(selected_policy.queue_timeout_seconds, remaining)
        try:
            async with bulkhead_slot(
                domain,
                VIRTUAL_DOMAIN,
                queue_timeout_seconds=queue_timeout,
            ) as permit:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise KISDeadlineExceeded(
                        "KIS request deadline exhausted while queued."
                    )
                try:
                    async with asyncio.timeout(remaining):
                        queued_seconds = await wait_for_kis_slot(domain)
                except TimeoutError as exc:
                    raise KISDeadlineExceeded(
                        "KIS request deadline exhausted during rate-limit cooldown."
                    ) from exc

                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise KISDeadlineExceeded(
                        "KIS request deadline exhausted before transport."
                    )
                attempt_timeout = min(
                    selected_policy.attempt_timeout_seconds,
                    remaining,
                )
                try:
                    async with asyncio.timeout(attempt_timeout):
                        response = await request_method(url, **kwargs)
                except (TimeoutError, httpx.TransportError) as exc:
                    last_error = exc
                    opened = record_circuit_failure(breaker_scope)
                    will_retry = may_retry and attempt + 1 < max_attempts
                    log_event(
                        logger,
                        "kis_transport_failed",
                        level=logging.WARNING,
                        operation_id=operation_id,
                        endpoint=endpoint,
                        policy=selected_policy.name,
                        attempt=attempt + 1,
                        elapsed_ms=round((perf_counter() - started) * 1000, 1),
                        queued_ms=round((permit.waited_seconds + queued_seconds) * 1000, 1),
                        queue_depth=permit.queue_depth_at_entry,
                        error_type=type(exc).__name__,
                        circuit_opened=opened,
                        retried=will_retry,
                    )
                    if not will_retry:
                        raise KISTransientError(
                            f"KIS transport failed after {attempt + 1} attempt(s): "
                            f"{type(exc).__name__}"
                        ) from exc
                    await _sleep_with_deadline(
                        full_jitter_delay(selected_policy, attempt),
                        deadline,
                    )
                    continue
        except KISBulkheadRejectedError:
            release_circuit_probe(breaker_scope)
            log_event(
                logger,
                "kis_bulkhead_rejected",
                level=logging.WARNING,
                operation_id=operation_id,
                endpoint=endpoint,
                policy=selected_policy.name,
            )
            raise
        except KISDeadlineExceeded:
            release_circuit_probe(breaker_scope)
            raise

        if is_kis_rate_limit_response(response):
            record_circuit_success(breaker_scope)
            fields = _response_fields(response)
            fields.pop("kis_msg1", None)
            rate_rejections += 1
            cooldown = await impose_rate_limit_cooldown(
                domain,
                VIRTUAL_DOMAIN,
                retry_after_seconds=_retry_after_seconds(response),
            )
            will_retry = (
                may_retry
                and rate_rejections <= rate_limit_retries
                and attempt + 1 < max_attempts
            )
            log_event(
                logger,
                "kis_rate_limit_rejected",
                level=logging.WARNING,
                operation_id=operation_id,
                endpoint=endpoint,
                policy=selected_policy.name,
                attempt=attempt + 1,
                queued_ms=round((permit.waited_seconds + queued_seconds) * 1000, 1),
                bulkhead_wait_ms=round(permit.waited_seconds * 1000, 1),
                rate_wait_ms=round(queued_seconds * 1000, 1),
                queue_depth=permit.queue_depth_at_entry,
                cooldown_ms=round(cooldown * 1000, 1),
                retried=will_retry,
                **fields,
            )
            if will_retry:
                continue
            raise KISRateLimitError(
                "KIS API rate limit persisted after retry: "
                f"http_status={fields.get('http_status')} "
                f"msg_cd={fields.get('kis_msg_cd')}"
            )

        record_rate_limit_success(domain, VIRTUAL_DOMAIN)

        if response.status_code in TRANSIENT_HTTP_STATUSES:
            fields = _response_fields(response)
            fields.pop("kis_msg1", None)
            opened = record_circuit_failure(breaker_scope)
            will_retry = may_retry and attempt + 1 < max_attempts
            log_event(
                logger,
                "kis_upstream_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                endpoint=endpoint,
                policy=selected_policy.name,
                attempt=attempt + 1,
                elapsed_ms=round((perf_counter() - started) * 1000, 1),
                queued_ms=round((permit.waited_seconds + queued_seconds) * 1000, 1),
                queue_depth=permit.queue_depth_at_entry,
                circuit_opened=opened,
                retried=will_retry,
                **fields,
            )
            if will_retry:
                await _sleep_with_deadline(
                    full_jitter_delay(selected_policy, attempt),
                    deadline,
                )
                continue
            raise KISTransientError(
                f"KIS upstream returned HTTP {response.status_code} "
                f"after {attempt + 1} attempt(s)."
            )

        record_circuit_success(breaker_scope)
        log_event(
            logger,
            "kis_request_complete",
            operation_id=operation_id,
            endpoint=endpoint,
            policy=selected_policy.name,
            method=request_method_name,
            attempt_count=attempt + 1,
            queued_ms=round((permit.waited_seconds + queued_seconds) * 1000, 1),
            bulkhead_wait_ms=round(permit.waited_seconds * 1000, 1),
            rate_wait_ms=round(queued_seconds * 1000, 1),
            queue_depth=permit.queue_depth_at_entry,
            elapsed_ms=round((perf_counter() - started) * 1000, 1),
            http_status=response.status_code,
            kis_msg_cd=_response_fields(response).get("kis_msg_cd"),
        )
        return response

    raise KISTransientError("KIS request exhausted its retry budget.")

