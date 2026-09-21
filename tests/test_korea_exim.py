import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from kis_portfolio.clients.korea_exim import (
    KOREA_EXIM_API_URL,
    KoreaEximError,
    fetch_usd_krw_deal_bas_rate,
    parse_usd_krw_deal_bas_rate,
)


FIXTURE = [
    {
        "result": 1,
        "cur_unit": "USD",
        "deal_bas_r": "1,407.50",
        "cur_nm": "미국 달러",
    }
]


def test_parser_preserves_requested_date_and_exact_native_field() -> None:
    fetched_at = datetime(2026, 9, 22, 1, 5, tzinfo=UTC)

    rate = parse_usd_krw_deal_bas_rate(
        FIXTURE,
        requested_date=date(2026, 9, 22),
        fetched_at=fetched_at,
    )

    assert rate.rate == Decimal("1407.50")
    assert rate.rate_date == date(2026, 9, 22)
    assert rate.native_rate_field == "deal_bas_r"
    assert rate.fetched_at == fetched_at


def test_client_uses_official_host_and_one_bounded_date_request() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=FIXTURE)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_usd_krw_deal_bas_rate(
                api_key="fixture-key",
                requested_date=date(2026, 9, 22),
                client=client,
            )

    rate = asyncio.run(run())

    assert rate.rate == Decimal("1407.50")
    assert len(requests) == 1
    assert str(requests[0].url).startswith(KOREA_EXIM_API_URL)
    assert requests[0].url.params["searchdate"] == "20260922"
    assert requests[0].url.params["data"] == "AP01"


def test_http_failure_discards_secret_bearing_request_cause() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_usd_krw_deal_bas_rate(
                api_key="must-not-appear-in-traceback",
                requested_date=date(2026, 9, 22),
                client=client,
            )

    with pytest.raises(KoreaEximError) as caught:
        asyncio.run(run())

    assert caught.value.__cause__ is None
    assert "must-not-appear" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [[], {}, [{"result": 1, "cur_unit": "EUR", "deal_bas_r": "1600"}],
     [{"result": 1, "cur_unit": "USD", "deal_bas_r": "not-a-number"}]],
)
def test_parser_fails_closed_on_empty_shape_drift_or_bad_rate(payload) -> None:
    with pytest.raises(KoreaEximError):
        parse_usd_krw_deal_bas_rate(
            payload,
            requested_date=date(2026, 9, 22),
            fetched_at=datetime.now(UTC),
        )
