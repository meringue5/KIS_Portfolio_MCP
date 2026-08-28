"""Provider-neutral ETF composition values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


ALLOWED_TYPES = frozenset({"equity", "etf", "bond", "cash", "derivative", "reit", "other"})


@dataclass(frozen=True, slots=True)
class EtfConstituent:
    name: str
    instrument_type: str
    weight_pct: Decimal | None
    currency: str | None = None
    instrument_id: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedComposition:
    source_date: date
    constituents: tuple[EtfConstituent, ...]


def normalize_constituent(item: dict) -> EtfConstituent:
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("ETF constituent name is required")
    instrument_type = str(item.get("type") or "other").strip().lower()
    if instrument_type not in ALLOWED_TYPES:
        instrument_type = "other"
    raw_weight = item.get("weight")
    try:
        weight = None if raw_weight in (None, "") else Decimal(str(raw_weight).replace("%", "").strip())
    except InvalidOperation as exc:
        raise ValueError("ETF constituent weight must be numeric") from exc
    if weight is not None and weight < 0:
        raise ValueError("ETF constituent weight must be nonnegative")
    code = str(item.get("code") or "").strip() or None
    currency = str(item.get("currency") or "").strip().upper() or None
    return EtfConstituent(name, instrument_type, weight, currency, code)
