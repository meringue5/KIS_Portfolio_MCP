import pytest

from kis_portfolio.services import account as kis_balance


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_fetch_balance_snapshot_uses_pension_api_for_irp(monkeypatch):
    calls = []
    monkeypatch.setenv("KIS_CANO", "11111111")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "29")
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setattr(kis_balance, "get_access_token", fake_token)
    monkeypatch.setattr(kis_balance, "save_balance_snapshot", lambda data: "snapshot-id")
    monkeypatch.setattr(kis_balance.httpx, "AsyncClient", lambda: FakeClient(calls))

    result = await kis_balance.fetch_balance_snapshot()

    assert result == {"output2": {"tot_evlu_amt": "1000"}}
    assert calls[0]["url"].endswith("/trading/pension/inquire-balance")
    assert calls[0]["headers"]["tr_id"] == "TTTC2208R"


@pytest.mark.anyio
async def test_fetch_balance_snapshot_uses_standard_api_for_pension_savings(monkeypatch):
    calls = []
    monkeypatch.setenv("KIS_CANO", "22222222")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "22")
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setattr(kis_balance, "get_access_token", fake_token)
    monkeypatch.setattr(kis_balance, "save_balance_snapshot", lambda data: "snapshot-id")
    monkeypatch.setattr(kis_balance.httpx, "AsyncClient", lambda: FakeClient(calls))

    await kis_balance.fetch_balance_snapshot()

    assert calls[0]["url"].endswith("/trading/inquire-balance")
    assert calls[0]["headers"]["tr_id"] == "TTTC8434R"


@pytest.mark.anyio
async def test_fetch_balance_snapshot_refreshes_and_retries_expired_token(monkeypatch):
    calls = []
    token_calls = []
    monkeypatch.setenv("KIS_CANO", "22222222")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")

    async def token_provider(client, domain, *, force_refresh=False):
        token_calls.append(force_refresh)
        return "fresh-token" if force_refresh else "stale-token"

    monkeypatch.setattr(kis_balance, "get_access_token", token_provider)
    monkeypatch.setattr(kis_balance, "save_balance_snapshot", lambda data: "snapshot-id")
    monkeypatch.setattr(kis_balance.httpx, "AsyncClient", lambda: ExpiredThenValidClient(calls))

    result = await kis_balance.fetch_balance_snapshot()

    assert result == {"output2": {"tot_evlu_amt": "1000"}}
    assert token_calls == [False, True]
    assert [call["headers"]["authorization"] for call in calls] == [
        "Bearer stale-token",
        "Bearer fresh-token",
    ]


async def fake_token(client, domain):
    return "token"


class FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {"output2": {"tot_evlu_amt": "1000"}}


class FakeClient:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers, params):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return FakeResponse()


class ExpiredThenValidClient(FakeClient):
    async def get(self, url, headers, params):
        self.calls.append({"url": url, "headers": headers, "params": params})
        if len(self.calls) == 1:
            return ExpiredTokenResponse()
        return FakeResponse()


class ExpiredTokenResponse:
    status_code = 200
    text = "expired"

    def json(self):
        return {"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "expired token"}
