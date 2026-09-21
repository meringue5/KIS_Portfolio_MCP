"""Bounded client for the official Korea Eximbank daily exchange-rate API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


KOREA_EXIM_API_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
KOREA_EXIM_DATA_CODE = "AP01"


class KoreaEximError(RuntimeError):
    """Raised when the official source cannot provide a safe typed observation."""


@dataclass(frozen=True, slots=True)
class KoreaEximFxRate:
    requested_date: date
    rate_date: date
    fetched_at: datetime
    base_currency: str
    quote_currency: str
    native_rate_field: str
    rate: Decimal
    provider: str = "korea-eximbank"


def parse_usd_krw_deal_bas_rate(
    payload: Any,
    *,
    requested_date: date,
    fetched_at: datetime,
) -> KoreaEximFxRate:
    """Parse only the explicitly approved USD `deal_bas_r` field."""
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    if not isinstance(payload, list) or not payload:
        raise KoreaEximError("official exchange-rate response is empty or malformed")
    usd = next(
        (
            row for row in payload
            if isinstance(row, dict) and str(row.get("cur_unit") or "").strip().upper() == "USD"
        ),
        None,
    )
    if usd is None:
        raise KoreaEximError("official exchange-rate response has no USD row")
    if str(usd.get("result") or "1") != "1":
        raise KoreaEximError("official exchange-rate response reported a non-success result")
    raw_rate = usd.get("deal_bas_r")
    try:
        rate = Decimal(str(raw_rate).replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise KoreaEximError("official USD deal_bas_r is not numeric") from exc
    if not rate.is_finite() or rate <= 0:
        raise KoreaEximError("official USD deal_bas_r must be positive and finite")
    return KoreaEximFxRate(
        requested_date=requested_date,
        rate_date=requested_date,
        fetched_at=fetched_at.astimezone(UTC),
        base_currency="USD",
        quote_currency="KRW",
        native_rate_field="deal_bas_r",
        rate=rate,
    )


async def fetch_usd_krw_deal_bas_rate(
    *,
    api_key: str,
    requested_date: date,
    client: httpx.AsyncClient | None = None,
) -> KoreaEximFxRate:
    """Fetch one requested business date once; callers own retry and fallback policy."""
    if not api_key.strip():
        raise KoreaEximError("Korea Eximbank API key is unavailable")
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        response = await active_client.get(
            KOREA_EXIM_API_URL,
            params={
                "authkey": api_key,
                "searchdate": requested_date.strftime("%Y%m%d"),
                "data": KOREA_EXIM_DATA_CODE,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            raise KoreaEximError("official exchange-rate response is not JSON") from None
        return parse_usd_krw_deal_bas_rate(
            payload,
            requested_date=requested_date,
            fetched_at=datetime.now(UTC),
        )
    except httpx.HTTPError:
        # httpx exceptions may embed the request URL, including the authkey query
        # parameter.  Deliberately discard the cause so an outer traceback cannot
        # leak the provider credential.
        raise KoreaEximError("official exchange-rate request failed") from None
    finally:
        if owns_client:
            await active_client.aclose()
