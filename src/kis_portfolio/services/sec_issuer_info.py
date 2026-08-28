"""Bounded SEC submissions metadata lookup and conservative issuer classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from kis_portfolio.services.overseas_instrument_info import OverseasInstrumentInfo


SEC_SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_REIT_SIC = "6798"
CIK_PATTERN = re.compile(r"^[0-9]{10}$")


class SecIssuerInfoError(RuntimeError):
    """Raised when SEC issuer metadata is unavailable or ambiguous."""


@dataclass(frozen=True, slots=True)
class SecIssuerInfo:
    cik: str
    name: str
    sic: str
    sic_description: str
    tickers: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OfficialInstrumentClassification:
    asset_type: str
    issuer_id: str
    source: str
    quality: str
    evidence: dict[str, Any]


async def fetch_sec_issuer_info(
    *,
    cik: str,
    user_agent: str,
    client: httpx.AsyncClient | None = None,
) -> SecIssuerInfo:
    """Fetch one SEC submissions header under the fair-access identity contract."""
    normalized_cik = str(cik).strip().zfill(10)
    normalized_user_agent = str(user_agent).strip()
    if not CIK_PATTERN.fullmatch(normalized_cik):
        raise ValueError("SEC CIK must be a ten-digit identifier")
    if "@" not in normalized_user_agent or len(normalized_user_agent) > 200:
        raise ValueError("SEC user agent must contain a bounded contact email")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await http_client.get(
            f"{SEC_SUBMISSIONS_BASE_URL}/CIK{normalized_cik}.json",
            headers={"User-Agent": normalized_user_agent, "Accept-Encoding": "gzip, deflate"},
        )
    finally:
        if owns_client:
            await http_client.aclose()
    if response.status_code != 200:
        raise SecIssuerInfoError(f"SEC submissions lookup failed: status={response.status_code}")
    body = response.json()
    returned_cik = str(body.get("cik") or "").zfill(10)
    if returned_cik != normalized_cik:
        raise SecIssuerInfoError("SEC submissions response CIK mismatch")
    tickers = tuple(sorted({str(item).strip().upper() for item in body.get("tickers", []) if item}))
    name = str(body.get("name") or "").strip()
    sic = str(body.get("sic") or "").strip()
    if not name or not sic:
        raise SecIssuerInfoError("SEC submissions response lacks issuer classification")
    return SecIssuerInfo(
        cik=normalized_cik,
        name=name,
        sic=sic,
        sic_description=str(body.get("sicDescription") or "").strip(),
        tickers=tickers,
        raw=dict(body),
    )


async def fetch_sec_ticker_ciks(
    *,
    symbols: tuple[str, ...],
    user_agent: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """Resolve a bounded exact ticker set through the SEC's published ticker file."""
    normalized = tuple(sorted({str(item).strip().upper() for item in symbols if str(item).strip()}))
    if not normalized or len(normalized) > 8:
        raise ValueError("SEC ticker lookup requires one to eight unique symbols")
    normalized_user_agent = str(user_agent).strip()
    if "@" not in normalized_user_agent or len(normalized_user_agent) > 200:
        raise ValueError("SEC user agent must contain a bounded contact email")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await http_client.get(
            SEC_COMPANY_TICKERS_URL,
            headers={"User-Agent": normalized_user_agent, "Accept-Encoding": "gzip, deflate"},
        )
    finally:
        if owns_client:
            await http_client.aclose()
    if response.status_code != 200:
        raise SecIssuerInfoError(f"SEC ticker mapping lookup failed: status={response.status_code}")
    wanted = set(normalized)
    matches: dict[str, set[str]] = {symbol: set() for symbol in normalized}
    body = response.json()
    for item in body.values() if isinstance(body, dict) else []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker in wanted:
            matches[ticker].add(str(item.get("cik_str") or "").zfill(10))
    ambiguous = sorted(symbol for symbol, ciks in matches.items() if len(ciks) != 1)
    if ambiguous:
        raise SecIssuerInfoError("SEC ticker mapping is missing or ambiguous for requested scope")
    return {symbol: next(iter(matches[symbol])) for symbol in normalized}


def classify_overseas_issuer(
    *,
    symbol: str,
    kis: OverseasInstrumentInfo,
    sec: SecIssuerInfo,
) -> OfficialInstrumentClassification:
    """Classify only evidence combinations that are exact enough to fail closed."""
    normalized_symbol = str(symbol).strip().upper()
    if not normalized_symbol or normalized_symbol != kis.symbol or normalized_symbol not in sec.tickers:
        raise ValueError("KIS symbol and SEC issuer ticker must match exactly")
    if kis.product_class_code != "101210" or kis.overseas_stock_division_code != "01":
        return OfficialInstrumentClassification(
            asset_type="unknown",
            issuer_id=f"sec-cik:{sec.cik}",
            source="kis_product_info+sec_edgar",
            quality="unresolved_official_evidence",
            evidence={
                "kis_product_class_code": kis.product_class_code,
                "kis_stock_division_code": kis.overseas_stock_division_code,
                "sec_sic": sec.sic,
            },
        )
    asset_type = "reit" if sec.sic == SEC_REIT_SIC else "equity"
    return OfficialInstrumentClassification(
        asset_type=asset_type,
        issuer_id=f"sec-cik:{sec.cik}",
        source="kis_product_info+sec_edgar",
        quality="official_reference",
        evidence={
            "kis_product_class_code": kis.product_class_code,
            "kis_stock_division_code": kis.overseas_stock_division_code,
            "sec_sic": sec.sic,
            "sec_sic_description": sec.sic_description,
        },
    )
