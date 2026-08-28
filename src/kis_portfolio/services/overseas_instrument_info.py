"""Bounded KIS overseas product metadata lookup for governed classification evidence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from kis_portfolio.auth import get_access_token
from kis_portfolio.clients.kis import AUTH_TYPE, CONTENT_TYPE, DOMAIN, request_kis


ENDPOINT = "/uapi/overseas-price/v1/quotations/search-info"
TR_ID = "CTPF1702R"
MARKET_PRODUCT_TYPES = {"NAS": "512", "NYS": "513", "NYSE": "513", "AMS": "529", "AMEX": "529"}


class OverseasInstrumentInfoError(RuntimeError):
    """Raised when official KIS product metadata is unavailable or ambiguous."""


@dataclass(frozen=True, slots=True)
class OverseasInstrumentInfo:
    market: str
    symbol: str
    product_type_code: str
    product_class_code: str
    product_class_name: str
    overseas_stock_division_code: str
    overseas_stock_product_group: str
    etf_risk_indicator_code: str
    tracking_multiple: str
    raw: dict[str, Any]


async def fetch_overseas_instrument_info(
    *,
    market: str,
    symbol: str,
    client: httpx.AsyncClient | None = None,
) -> OverseasInstrumentInfo:
    normalized_market = market.strip().upper()
    normalized_symbol = symbol.strip().upper()
    if normalized_market not in MARKET_PRODUCT_TYPES:
        raise ValueError("unsupported overseas product-info market")
    if not normalized_symbol or len(normalized_symbol) > 32:
        raise ValueError("invalid overseas symbol")
    headers = {
        "content-type": CONTENT_TYPE,
        "appkey": os.environ["KIS_APP_KEY"],
        "appsecret": os.environ["KIS_APP_SECRET"],
        "tr_id": TR_ID,
    }
    owns_client = client is None
    http_client = client or httpx.AsyncClient()
    try:
        token = await get_access_token(http_client, DOMAIN)
        headers["authorization"] = f"{AUTH_TYPE} {token}"
        response = await request_kis(
            http_client,
            "GET",
            f"{DOMAIN}{ENDPOINT}",
            policy="quote",
            headers=headers,
            params={
                "PRDT_TYPE_CD": MARKET_PRODUCT_TYPES[normalized_market],
                "PDNO": normalized_symbol,
            },
        )
    finally:
        if owns_client:
            await http_client.aclose()
    if response.status_code != 200:
        raise OverseasInstrumentInfoError(
            f"KIS overseas product info failed: market={normalized_market} status={response.status_code}"
        )
    body = response.json()
    if str(body.get("rt_cd", "0")) != "0":
        raise OverseasInstrumentInfoError(
            f"KIS overseas product info rejected: code={body.get('msg_cd', 'UNKNOWN')}"
        )
    output = body.get("output") or {}
    if isinstance(output, list):
        if len(output) != 1:
            raise OverseasInstrumentInfoError("KIS overseas product info must return exactly one row")
        output = output[0]
    if not isinstance(output, dict) or not output:
        raise OverseasInstrumentInfoError("KIS overseas product info returned no row")
    return OverseasInstrumentInfo(
        market=normalized_market,
        symbol=normalized_symbol,
        product_type_code=MARKET_PRODUCT_TYPES[normalized_market],
        product_class_code=str(output.get("prdt_clsf_cd") or ""),
        product_class_name=str(output.get("prdt_clsf_name") or ""),
        overseas_stock_division_code=str(output.get("ovrs_stck_dvsn_cd") or ""),
        overseas_stock_product_group=str(output.get("ovrs_stck_prdt_grp_no") or ""),
        etf_risk_indicator_code=str(output.get("ovrs_stck_etf_risk_drtp_cd") or ""),
        tracking_multiple=str(output.get("etp_chas_erng_rt_dbnb") or ""),
        raw=dict(output),
    )
