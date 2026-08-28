from __future__ import annotations

import httpx
import pytest

from kis_portfolio.services import overseas_instrument_info as service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_overseas_product_info_uses_official_route_and_preserves_raw(monkeypatch) -> None:
    monkeypatch.setenv("KIS_APP_KEY", "fixture-key")
    monkeypatch.setenv("KIS_APP_SECRET", "fixture-secret")
    monkeypatch.setattr(service, "get_access_token", _token)
    captured: dict[str, object] = {}

    async def fake_request(client, method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={
            "rt_cd": "0",
            "output": {
                "prdt_clsf_cd": "01",
                "prdt_clsf_name": "Common Stock",
                "ovrs_stck_dvsn_cd": "01",
                "ovrs_stck_prdt_grp_no": "01",
                "ovrs_stck_etf_risk_drtp_cd": "",
                "etp_chas_erng_rt_dbnb": "1",
                "std_pdno": "US0000000000",
            },
        })

    monkeypatch.setattr(service, "request_kis", fake_request)
    async with httpx.AsyncClient() as client:
        result = await service.fetch_overseas_instrument_info(
            market="NAS", symbol="GOOG", client=client
        )
    assert captured["url"] == f"{service.DOMAIN}{service.ENDPOINT}"
    assert captured["policy"] == "quote"
    assert captured["params"] == {"PRDT_TYPE_CD": "512", "PDNO": "GOOG"}
    assert captured["headers"]["tr_id"] == "CTPF1702R"  # type: ignore[index]
    assert result.product_class_name == "Common Stock"
    assert result.raw["std_pdno"] == "US0000000000"


async def _token(_client, _domain):
    return "fixture-token"


@pytest.mark.anyio
async def test_overseas_product_info_fails_closed_on_missing_or_ambiguous_output(monkeypatch) -> None:
    monkeypatch.setenv("KIS_APP_KEY", "fixture-key")
    monkeypatch.setenv("KIS_APP_SECRET", "fixture-secret")
    monkeypatch.setattr(service, "get_access_token", _token)

    async def missing(*_args, **_kwargs):
        return httpx.Response(200, json={"rt_cd": "0", "output": []})

    monkeypatch.setattr(service, "request_kis", missing)
    async with httpx.AsyncClient() as client:
        with pytest.raises(service.OverseasInstrumentInfoError, match="no row"):
            await service.fetch_overseas_instrument_info(
                market="NAS", symbol="GOOG", client=client
            )

    async def ambiguous(*_args, **_kwargs):
        return httpx.Response(200, json={"rt_cd": "0", "output": [{"a": 1}, {"a": 2}]})

    monkeypatch.setattr(service, "request_kis", ambiguous)
    async with httpx.AsyncClient() as client:
        with pytest.raises(service.OverseasInstrumentInfoError, match="exactly one"):
            await service.fetch_overseas_instrument_info(
                market="NAS", symbol="GOOG", client=client
            )
