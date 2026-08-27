"""Process-local resilience primitives for Korea Investment Open API calls."""

from __future__ import annotations

import asyncio
import os
import random
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary


DEFAULT_REAL_MIN_INTERVAL_SECONDS = 0.15
DEFAULT_VIRTUAL_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_TOKEN_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS = 1.0
DEFAULT_RATE_LIMIT_MAX_COOLDOWN_SECONDS = 10.0
DEFAULT_REAL_MAX_IN_FLIGHT = 3
DEFAULT_VIRTUAL_MAX_IN_FLIGHT = 1
DEFAULT_MAX_QUEUE_SIZE = 50
DEFAULT_CIRCUIT_FAILURE_THRESHOLD = 5
DEFAULT_CIRCUIT_WINDOW_SECONDS = 30.0
DEFAULT_CIRCUIT_OPEN_SECONDS = 20.0


class KISApiError(RuntimeError):
    """Base class for classified KIS transport failures."""


class KISRateLimitError(KISApiError):
    """KIS continued to reject a request after its bounded retry budget."""


class KISTransientError(KISApiError):
    """A retryable transport or upstream failure exhausted its retry budget."""


class KISDeadlineExceeded(KISTransientError):
    """The request exhausted its total latency budget."""


class KISBulkheadRejectedError(KISTransientError):
    """The bounded KIS request queue was full or could not be entered in time."""


class KISCircuitOpenError(KISTransientError):
    """A failing KIS endpoint is temporarily blocked by its circuit breaker."""


@dataclass(frozen=True)
class KISRequestPolicy:
    """Latency and retry budget for one class of KIS request."""

    name: str
    max_attempts: int
    attempt_timeout_seconds: float
    total_timeout_seconds: float
    queue_timeout_seconds: float
    retry_base_seconds: float
    retry_cap_seconds: float


REQUEST_POLICIES = {
    "quote": KISRequestPolicy("quote", 2, 5.0, 8.0, 3.0, 0.25, 1.0),
    "account": KISRequestPolicy("account", 2, 10.0, 15.0, 5.0, 0.5, 2.0),
    "history": KISRequestPolicy("history", 3, 20.0, 60.0, 10.0, 0.5, 4.0),
    "batch": KISRequestPolicy("batch", 4, 30.0, 120.0, 20.0, 1.0, 8.0),
    "default": KISRequestPolicy("default", 2, 10.0, 15.0, 5.0, 0.5, 2.0),
}


@dataclass
class RateLimitState:
    lock: asyncio.Lock
    next_allowed_at: float = 0.0
    blocked_until: float = 0.0
    consecutive_rejections: int = 0


@dataclass
class BulkheadState:
    semaphore: asyncio.Semaphore
    max_waiters: int
    waiters: int = 0


@dataclass(frozen=True)
class BulkheadPermit:
    waited_seconds: float
    queue_depth_at_entry: int


@dataclass
class CircuitState:
    failures: deque[float] = field(default_factory=deque)
    open_until: float = 0.0
    half_open_probe_active: bool = False


@dataclass
class LoopResilienceState:
    rate_limiters: dict[str, RateLimitState] = field(default_factory=dict)
    bulkheads: dict[str, BulkheadState] = field(default_factory=dict)
    circuits: dict[str, CircuitState] = field(default_factory=dict)


_LOOP_STATES: WeakKeyDictionary = WeakKeyDictionary()


def clear_kis_resilience_state() -> None:
    """Clear process-local state for tests and controlled diagnostics."""
    _LOOP_STATES.clear()


def positive_float_env(name: str, default: float) -> float:
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


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer.")
    return value


def request_policy(policy: str | KISRequestPolicy | None) -> KISRequestPolicy:
    if isinstance(policy, KISRequestPolicy):
        return policy
    name = policy or "default"
    try:
        return REQUEST_POLICIES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown KIS request policy: {name}") from exc


def environment_scope(domain: str, virtual_domain: str) -> str:
    return "virtual" if domain.startswith(virtual_domain) else "real"


def limiter_scope(domain: str, virtual_domain: str, request_kind: str) -> str:
    return f"{request_kind}:{environment_scope(domain, virtual_domain)}"


def circuit_scope(domain: str, virtual_domain: str, url: str) -> str:
    path = urlsplit(url).path or "/"
    return f"{environment_scope(domain, virtual_domain)}:{path}"


def _loop_state() -> LoopResilienceState:
    loop = asyncio.get_running_loop()
    state = _LOOP_STATES.get(loop)
    if state is None:
        state = LoopResilienceState()
        _LOOP_STATES[loop] = state
    return state


def min_interval_seconds(
    domain: str,
    virtual_domain: str,
    *,
    request_kind: str = "rest",
) -> float:
    if request_kind == "token":
        return positive_float_env(
            "KIS_TOKEN_MIN_INTERVAL_SECONDS",
            DEFAULT_TOKEN_MIN_INTERVAL_SECONDS,
        )
    if domain.startswith(virtual_domain):
        return positive_float_env(
            "KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS",
            DEFAULT_VIRTUAL_MIN_INTERVAL_SECONDS,
        )
    return positive_float_env(
        "KIS_REAL_API_MIN_INTERVAL_SECONDS",
        DEFAULT_REAL_MIN_INTERVAL_SECONDS,
    )


def _rate_limit_state(scope: str) -> RateLimitState:
    states = _loop_state().rate_limiters
    state = states.get(scope)
    if state is None:
        state = RateLimitState(lock=asyncio.Lock())
        states[scope] = state
    return state


async def wait_for_slot(
    domain: str,
    virtual_domain: str,
    *,
    request_kind: str = "rest",
) -> float:
    """Serialize starts and honor cooldown feedback shared by all callers."""
    loop = asyncio.get_running_loop()
    scope = limiter_scope(domain, virtual_domain, request_kind)
    state = _rate_limit_state(scope)
    interval = min_interval_seconds(domain, virtual_domain, request_kind=request_kind)
    async with state.lock:
        now = loop.time()
        allowed_at = max(state.next_allowed_at, state.blocked_until)
        delay = max(0.0, allowed_at - now)
        if delay:
            await asyncio.sleep(delay)
        state.next_allowed_at = loop.time() + interval
    return delay


async def impose_rate_limit_cooldown(
    domain: str,
    virtual_domain: str,
    *,
    retry_after_seconds: float | None = None,
) -> float:
    """Apply an adaptive cooldown to the whole REST environment scope."""
    loop = asyncio.get_running_loop()
    scope = limiter_scope(domain, virtual_domain, "rest")
    state = _rate_limit_state(scope)
    async with state.lock:
        state.consecutive_rejections += 1
        base = positive_float_env(
            "KIS_RATE_LIMIT_RETRY_DELAY_SECONDS",
            DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS,
        )
        maximum = positive_float_env(
            "KIS_RATE_LIMIT_MAX_COOLDOWN_SECONDS",
            DEFAULT_RATE_LIMIT_MAX_COOLDOWN_SECONDS,
        )
        adaptive = min(maximum, base * (2 ** (state.consecutive_rejections - 1)))
        cooldown = min(maximum, retry_after_seconds or adaptive)
        state.blocked_until = max(state.blocked_until, loop.time() + cooldown)
    return cooldown


def record_rate_limit_success(domain: str, virtual_domain: str) -> None:
    scope = limiter_scope(domain, virtual_domain, "rest")
    state = _loop_state().rate_limiters.get(scope)
    if state is not None:
        state.consecutive_rejections = 0


def _bulkhead_state(domain: str, virtual_domain: str) -> BulkheadState:
    scope = environment_scope(domain, virtual_domain)
    states = _loop_state().bulkheads
    state = states.get(scope)
    if state is None:
        if scope == "virtual":
            maximum = positive_int_env(
                "KIS_VIRTUAL_API_MAX_IN_FLIGHT",
                DEFAULT_VIRTUAL_MAX_IN_FLIGHT,
            )
        else:
            maximum = positive_int_env(
                "KIS_REAL_API_MAX_IN_FLIGHT",
                DEFAULT_REAL_MAX_IN_FLIGHT,
            )
        state = BulkheadState(
            semaphore=asyncio.Semaphore(maximum),
            max_waiters=positive_int_env("KIS_API_MAX_QUEUE_SIZE", DEFAULT_MAX_QUEUE_SIZE),
        )
        states[scope] = state
    return state


@asynccontextmanager
async def bulkhead_slot(
    domain: str,
    virtual_domain: str,
    *,
    queue_timeout_seconds: float,
) -> AsyncIterator[BulkheadPermit]:
    """Bound both active requests and callers waiting to enter KIS."""
    state = _bulkhead_state(domain, virtual_domain)
    if state.waiters >= state.max_waiters:
        raise KISBulkheadRejectedError("KIS request queue is full.")
    loop = asyncio.get_running_loop()
    started = loop.time()
    queue_depth_at_entry = state.waiters
    state.waiters += 1
    acquired = False
    try:
        try:
            async with asyncio.timeout(queue_timeout_seconds):
                await state.semaphore.acquire()
                acquired = True
        except TimeoutError as exc:
            raise KISBulkheadRejectedError(
                "Timed out while waiting for KIS request capacity."
            ) from exc
        finally:
            state.waiters -= 1
        yield BulkheadPermit(
            waited_seconds=max(0.0, loop.time() - started),
            queue_depth_at_entry=queue_depth_at_entry,
        )
    finally:
        if acquired:
            state.semaphore.release()


def allow_circuit_request(scope: str) -> None:
    loop = asyncio.get_running_loop()
    state = _loop_state().circuits.setdefault(scope, CircuitState())
    now = loop.time()
    if state.open_until > now:
        raise KISCircuitOpenError("KIS endpoint circuit is open.")
    if state.open_until:
        if state.half_open_probe_active:
            raise KISCircuitOpenError("KIS endpoint circuit is half-open.")
        state.half_open_probe_active = True


def record_circuit_success(scope: str) -> None:
    state = _loop_state().circuits.setdefault(scope, CircuitState())
    state.failures.clear()
    state.open_until = 0.0
    state.half_open_probe_active = False


def release_circuit_probe(scope: str) -> None:
    """Release a half-open probe that never reached the upstream transport."""
    state = _loop_state().circuits.get(scope)
    if state is not None:
        state.half_open_probe_active = False


def record_circuit_failure(scope: str) -> bool:
    """Record a transient failure and return whether the circuit was opened."""
    loop = asyncio.get_running_loop()
    state = _loop_state().circuits.setdefault(scope, CircuitState())
    now = loop.time()
    threshold = positive_int_env(
        "KIS_CIRCUIT_FAILURE_THRESHOLD",
        DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
    )
    window = positive_float_env(
        "KIS_CIRCUIT_WINDOW_SECONDS",
        DEFAULT_CIRCUIT_WINDOW_SECONDS,
    )
    while state.failures and state.failures[0] < now - window:
        state.failures.popleft()
    was_half_open = state.half_open_probe_active
    state.half_open_probe_active = False
    state.failures.append(now)
    if was_half_open or len(state.failures) >= threshold:
        state.open_until = now + positive_float_env(
            "KIS_CIRCUIT_OPEN_SECONDS",
            DEFAULT_CIRCUIT_OPEN_SECONDS,
        )
        return True
    return False


def full_jitter_delay(policy: KISRequestPolicy, retry_number: int) -> float:
    cap = min(policy.retry_cap_seconds, policy.retry_base_seconds * (2 ** retry_number))
    return random.uniform(0.0, cap)
