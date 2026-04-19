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
