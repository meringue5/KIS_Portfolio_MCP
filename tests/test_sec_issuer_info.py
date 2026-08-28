import httpx
import pytest

from kis_portfolio.services.overseas_instrument_info import OverseasInstrumentInfo
from kis_portfolio.services.sec_issuer_info import (
    SecIssuerInfo,
    SecIssuerInfoError,
    classify_overseas_issuer,
    fetch_sec_issuer_info,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _kis(symbol: str = "EXAMPLE", *, product_class: str = "101210") -> OverseasInstrumentInfo:
    return OverseasInstrumentInfo(
        market="NAS",
        symbol=symbol,
        product_type_code="512",
        product_class_code=product_class,
        product_class_name="Overseas stock",
        overseas_stock_division_code="01",
        overseas_stock_product_group="",
        etf_risk_indicator_code="",
        tracking_multiple="0",
        raw={"fixture": True},
    )


@pytest.mark.anyio
async def test_fetch_sec_issuer_info_requires_exact_identity_and_contact() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "KIS Portfolio mustafa@example.com"
        return httpx.Response(200, json={
            "cik": "1234567",
            "name": "Example REIT",
            "sic": "6798",
            "sicDescription": "Real Estate Investment Trusts",
            "tickers": ["EXAMPLE"],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_sec_issuer_info(
            cik="1234567", user_agent="KIS Portfolio mustafa@example.com", client=client
        )
    assert result.cik == "0001234567"
    assert result.sic == "6798"
    assert result.tickers == ("EXAMPLE",)

    with pytest.raises(ValueError, match="contact email"):
        await fetch_sec_issuer_info(cik="1234567", user_agent="anonymous", client=client)


@pytest.mark.anyio
async def test_fetch_sec_issuer_info_fails_closed_on_cik_mismatch() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={
        "cik": "7654321", "name": "Wrong issuer", "sic": "3674", "tickers": ["EXAMPLE"]
    }))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(SecIssuerInfoError, match="CIK mismatch"):
            await fetch_sec_issuer_info(
                cik="1234567", user_agent="KIS Portfolio mustafa@example.com", client=client
            )


def test_classification_uses_exact_kis_and_sec_evidence() -> None:
    reit = SecIssuerInfo(
        "0001234567", "Example REIT", "6798", "Real Estate Investment Trusts",
        ("EXAMPLE",), {},
    )
    result = classify_overseas_issuer(symbol="EXAMPLE", kis=_kis(), sec=reit)
    assert result.asset_type == "reit"
    assert result.issuer_id == "sec-cik:0001234567"
    assert result.quality == "official_reference"

    company = SecIssuerInfo(
        "0001234568", "Example Corp", "3674", "Semiconductors & Related Devices",
        ("EXAMPLE",), {},
    )
    assert classify_overseas_issuer(symbol="EXAMPLE", kis=_kis(), sec=company).asset_type == "equity"

    unresolved = classify_overseas_issuer(
        symbol="EXAMPLE", kis=_kis(product_class="unknown"), sec=company
    )
    assert unresolved.asset_type == "unknown"
    assert unresolved.quality == "unresolved_official_evidence"

    with pytest.raises(ValueError, match="match exactly"):
        classify_overseas_issuer(symbol="OTHER", kis=_kis(), sec=company)
