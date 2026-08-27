from __future__ import annotations

import pytest

from kis_portfolio.clients import kis


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
    sleeps = []

    async def no_queue(*args, **kwargs):
        waits.append((args, kwargs))
        return 0.0

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(kis, "wait_for_kis_slot", no_queue)
    monkeypatch.setattr(kis.asyncio, "sleep", fake_sleep)
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
    assert sleeps == [1.0]


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


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)
