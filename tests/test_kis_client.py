from __future__ import annotations

import asyncio
import ast
import time
from pathlib import Path

import httpx
import pytest

from kis_portfolio.clients import kis
from kis_portfolio.clients import kis_resilience


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clear_limiters():
    kis.clear_kis_rate_limiters()
    yield
    kis.clear_kis_rate_limiters()


def test_default_intervals_follow_official_real_virtual_and_token_limits(monkeypatch):
    monkeypatch.delenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("KIS_TOKEN_MIN_INTERVAL_SECONDS", raising=False)

    assert kis.kis_min_interval_seconds(kis.DOMAIN) == 0.15
    assert kis.kis_min_interval_seconds(kis.VIRTUAL_DOMAIN) == 1.0
    assert kis.kis_min_interval_seconds(kis.DOMAIN, request_kind="token") == 1.0


def test_kis_services_do_not_bypass_resilient_request_helper():
    root = Path(__file__).resolve().parents[1]
    service_files = [
        root / "src/kis_portfolio/services/account.py",
        root / "src/kis_portfolio/services/kis_api.py",
        root / "src/kis_portfolio/services/order_history.py",
        root / "src/kis_portfolio/services/overseas_history.py",
    ]
    bypasses = []
    for path in service_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
                continue
            function = node.value.func
            if (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "client"
                and function.attr in {"get", "post", "put", "patch", "delete", "request"}
            ):
                bypasses.append(f"{path.name}:{node.lineno}:{function.attr}")

    assert bypasses == []


@pytest.mark.parametrize("msg_cd", ["EGW00201", "EGW00215"])
def test_rate_limit_response_recognizes_documented_and_observed_codes(msg_cd):
    response = FakeResponse(
        {"rt_cd": "1", "msg_cd": msg_cd, "msg1": "초당 거래건수 초과"}
    )

    assert kis.is_kis_rate_limit_response(response)


@pytest.mark.anyio
async def test_wait_for_slot_spaces_process_wide_request_starts(monkeypatch):
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.01")

    first_delay = await kis.wait_for_kis_slot(kis.DOMAIN)
    second_delay = await kis.wait_for_kis_slot(kis.DOMAIN)

    assert first_delay == 0.0
    assert second_delay > 0.0


@pytest.mark.anyio
async def test_request_kis_retries_rate_limit_once(monkeypatch):
    waits = []
    cooldowns = []

    async def no_queue(*args, **kwargs):
        waits.append((args, kwargs))
        return 0.0

    async def fake_cooldown(*args, **kwargs):
        cooldowns.append((args, kwargs))
        return 1.0

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    monkeypatch.setattr(kis, "impose_rate_limit_cooldown", fake_cooldown)
    client = FakeClient([
        FakeResponse({"rt_cd": "1", "msg_cd": "EGW00215", "msg1": "초당 거래건수 초과"}),
        FakeResponse({"rt_cd": "0", "output": {"ok": True}}),
    ])

    response = await kis.request_kis(
        client,
        "GET",
        f"{kis.DOMAIN}/uapi/test",
        params={"value": "1"},
    )

    assert response.json()["rt_cd"] == "0"
    assert client.calls == 2
    assert len(waits) == 2
    assert len(cooldowns) == 1


@pytest.mark.anyio
async def test_request_kis_raises_after_bounded_retry(monkeypatch):
    async def no_queue(*args, **kwargs):
        return 0.0

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    monkeypatch.setattr(kis.asyncio, "sleep", no_sleep)
    client = FakeClient([
        FakeResponse({"rt_cd": "1", "msg_cd": "EGW00215", "msg1": "초당 거래건수 초과"}),
        FakeResponse({"rt_cd": "1", "msg_cd": "EGW00215", "msg1": "초당 거래건수 초과"}),
    ])

    with pytest.raises(kis.KISRateLimitError, match="EGW00215"):
        await kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/test")

    assert client.calls == 2


@pytest.mark.anyio
async def test_rate_limit_feedback_pauses_other_callers(monkeypatch):
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.001")
    await kis_resilience.impose_rate_limit_cooldown(
        kis.DOMAIN,
        kis.VIRTUAL_DOMAIN,
        retry_after_seconds=0.02,
    )

    started = time.perf_counter()
    delay = await kis.wait_for_kis_slot(kis.DOMAIN)

    assert delay >= 0.01
    assert time.perf_counter() - started >= 0.01


@pytest.mark.anyio
async def test_get_retries_transient_transport_failure(monkeypatch):
    async def no_queue(*args, **kwargs):
        return 0.0

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    monkeypatch.setattr(kis.asyncio, "sleep", no_sleep)
    client = FakeClient([
        httpx.ConnectError("temporary"),
        FakeResponse({"rt_cd": "0", "output": {"ok": True}}),
    ])

    response = await kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/retry")

    assert response.json()["output"]["ok"] is True
    assert client.calls == 2


@pytest.mark.anyio
async def test_post_is_never_retried_without_explicit_opt_in(monkeypatch):
    async def no_queue(*args, **kwargs):
        return 0.0

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    client = FakeClient([
        httpx.ConnectError("ambiguous post outcome"),
        FakeResponse({"rt_cd": "0"}),
    ])

    with pytest.raises(kis.KISTransientError, match="ConnectError"):
        await kis.request_kis(client, "POST", f"{kis.DOMAIN}/uapi/order")

    assert client.calls == 1


@pytest.mark.anyio
async def test_bulkhead_limits_in_flight_requests(monkeypatch):
    monkeypatch.setenv("KIS_REAL_API_MAX_IN_FLIGHT", "1")
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.001")
    entered = asyncio.Event()
    release = asyncio.Event()
    client = BlockingFakeClient(entered, release)

    first = asyncio.create_task(
        kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/first")
    )
    await entered.wait()
    second = asyncio.create_task(
        kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/second")
    )
    await asyncio.sleep(0)

    assert client.active == 1
    assert client.maximum_active == 1

    release.set()
    await asyncio.gather(first, second)
    assert client.maximum_active == 1


@pytest.mark.anyio
async def test_bulkhead_rejects_requests_beyond_bounded_queue(monkeypatch):
    monkeypatch.setenv("KIS_REAL_API_MAX_IN_FLIGHT", "1")
    monkeypatch.setenv("KIS_API_MAX_QUEUE_SIZE", "1")
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.001")
    entered = asyncio.Event()
    release = asyncio.Event()
    client = BlockingFakeClient(entered, release)

    first = asyncio.create_task(
        kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/active")
    )
    await entered.wait()
    second = asyncio.create_task(
        kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/waiting")
    )
    await asyncio.sleep(0)

    with pytest.raises(kis.KISBulkheadRejectedError, match="queue is full"):
        await kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/rejected")

    release.set()
    await asyncio.gather(first, second)


@pytest.mark.anyio
async def test_total_deadline_includes_shared_cooldown(monkeypatch):
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.001")
    await kis_resilience.impose_rate_limit_cooldown(
        kis.DOMAIN,
        kis.VIRTUAL_DOMAIN,
        retry_after_seconds=0.05,
    )
    policy = kis.KISRequestPolicy("short", 1, 0.02, 0.01, 0.01, 0.001, 0.001)

    with pytest.raises(kis.KISDeadlineExceeded, match="cooldown"):
        await kis.request_kis(
            FakeClient([FakeResponse({"rt_cd": "0"})]),
            "GET",
            f"{kis.DOMAIN}/uapi/deadline",
            policy=policy,
            rate_limit_retries=0,
        )


@pytest.mark.anyio
async def test_get_retries_transient_503(monkeypatch):
    async def no_queue(*args, **kwargs):
        return 0.0

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    monkeypatch.setattr(kis.asyncio, "sleep", no_sleep)
    client = FakeClient([
        FakeResponse({"rt_cd": "1"}, status_code=503),
        FakeResponse({"rt_cd": "0", "output": {"ok": True}}),
    ])

    response = await kis.request_kis(client, "GET", f"{kis.DOMAIN}/uapi/503")

    assert response.status_code == 200
    assert client.calls == 2


@pytest.mark.anyio
async def test_circuit_opens_after_configured_transient_failure(monkeypatch):
    monkeypatch.setenv("KIS_CIRCUIT_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("KIS_REAL_API_MIN_INTERVAL_SECONDS", "0.001")
    policy = kis.KISRequestPolicy("single", 1, 1.0, 2.0, 1.0, 0.01, 0.01)
    client = FakeClient([httpx.ConnectError("down")])

    with pytest.raises(kis.KISTransientError):
        await kis.request_kis(
            client,
            "GET",
            f"{kis.DOMAIN}/uapi/circuit",
            policy=policy,
            rate_limit_retries=0,
        )

    with pytest.raises(kis.KISCircuitOpenError):
        await kis.request_kis(
            client,
            "GET",
            f"{kis.DOMAIN}/uapi/circuit",
            policy=policy,
            rate_limit_retries=0,
        )


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, url, **kwargs):
        return await self.get(url, **kwargs)


class BlockingFakeClient:
    def __init__(self, entered, release):
        self.entered = entered
        self.release = release
        self.active = 0
        self.maximum_active = 0

    async def get(self, url, **kwargs):
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.entered.set()
        await self.release.wait()
        self.active -= 1
        return FakeResponse({"rt_cd": "0", "output": {"ok": True}})

