import pytest

from kis_portfolio.services import kis_api


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_inquery_stock_history_uses_period_chart_tr_id(monkeypatch):
    calls = []
    saved_rows = []

    monkeypatch.setenv("KIS_APP_KEY", "key")
    monkeypatch.setenv("KIS_APP_SECRET", "secret")
    monkeypatch.setenv("KIS_ACCOUNT_TYPE", "REAL")
    monkeypatch.setattr(kis_api, "get_access_token", fake_token)
    monkeypatch.setattr(kis_api.httpx, "AsyncClient", lambda: FakeClient(calls))
    monkeypatch.setattr(kis_api.kisdb, "upsert_price_history", lambda rows: saved_rows.extend(rows))

    result = await kis_api.inquery_stock_history("005930", "20260101", "20260131")

    assert calls[0]["url"].endswith("/quotations/inquire-daily-itemchartprice")
    assert calls[0]["headers"]["tr_id"] == "FHKST03010100"
    assert calls[0]["params"] == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_DATE_1": "20260101",
        "FID_INPUT_DATE_2": "20260131",
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    assert "FID_INPUT_HOUR_1" not in calls[0]["params"]
    assert result["output2"][0]["stck_bsop_date"] == "20260102"
    assert saved_rows == [{
        "symbol": "005930",
        "exchange": "KRX",
        "date": "20260102",
        "open": "70000",
        "high": "71000",
        "low": "69000",
        "close": "70500",
        "volume": "1000",
    }]


async def fake_token(client, domain):
    return "token"


class FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {
            "output1": {"hts_kor_isnm": "삼성전자"},
            "output2": [{
                "stck_bsop_date": "20260102",
                "stck_oprc": "70000",
                "stck_hgpr": "71000",
                "stck_lwpr": "69000",
                "stck_clpr": "70500",
                "acml_vol": "1000",
            }],
        }


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
