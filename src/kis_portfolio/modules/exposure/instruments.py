"""Pure instrument identity and classification rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


ETF_GROUP_CODES = frozenset({"E", "EF", "FE"})
REIT_GROUP_CODES = frozenset({"R", "RT"})


@dataclass(frozen=True, slots=True)
class InstrumentClassification:
    asset_type: str
    economic_exposure: str
    source: str
    quality: str
    evidence: dict[str, Any]


def canonical_instrument_id(market: str, symbol: str) -> str:
    normalized_market = str(market or "").strip().upper()
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_market or not normalized_symbol or "|" in normalized_market or "|" in normalized_symbol:
        raise ValueError("canonical instrument identity requires safe market and symbol")
    return f"v1|{normalized_market}|{normalized_symbol}"


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _valid_override(override: dict[str, Any] | None, as_of: date | datetime | None) -> bool:
    if not override or not str(override.get("reason") or "").strip():
        return False
    cutoff = _as_date(as_of) or date.today()
    valid_from = _as_date(override.get("valid_from"))
    valid_to = _as_date(override.get("valid_to"))
    return (valid_from is None or valid_from <= cutoff) and (valid_to is None or cutoff < valid_to)


def resolve_instrument_classification(
    *,
    market: str,
    name: str | None,
    as_of: date | datetime | None = None,
    master: dict[str, Any] | None = None,
    override: dict[str, Any] | None = None,
    exact_route_profile_id: str | None = None,
) -> InstrumentClassification:
    """Resolve asset type without inventing economic exposure or issuer routing."""
    if _valid_override(override, as_of):
        asset_type = str(override.get("asset_subtype") or "unknown").strip().lower()
        if asset_type not in {"equity", "etf", "reit", "bond", "cash", "derivative", "unknown"}:
            asset_type = "unknown"
        return InstrumentClassification(
            asset_type=asset_type,
            economic_exposure=str(override.get("exposure_type") or "unknown"),
            source="owner_override",
            quality="owner_approved",
            evidence={"reason": override["reason"]},
        )

    group_code = str((master or {}).get("group_code") or "").strip().upper()
    if group_code in ETF_GROUP_CODES:
        return InstrumentClassification("etf", "unknown", "kis_instrument_master", "official_reference", {"group_code": group_code})
    if group_code in REIT_GROUP_CODES:
        return InstrumentClassification("reit", "unknown", "kis_instrument_master", "official_reference", {"group_code": group_code})
    if group_code:
        return InstrumentClassification("equity", "unknown", "kis_instrument_master", "official_reference", {"group_code": group_code})
    if exact_route_profile_id:
        return InstrumentClassification(
            "etf", "unknown", "exact_etf_route", "fixture_route",
            {"profile_id": exact_route_profile_id},
        )
    return InstrumentClassification(
        "unknown", "unknown", "unresolved", "unknown",
        {"market": str(market).upper(), "name_present": bool(str(name or "").strip())},
    )
