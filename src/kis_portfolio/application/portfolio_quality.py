"""Pure quality decisions shared by portfolio readers and presentations."""

from __future__ import annotations

from datetime import date


def fx_watermark_is_current(
    *, currency: str, raw_fx_date: object, evaluation_date: date, earliest_fx_date: date,
) -> bool:
    """A foreign KRW valuation requires a dated rate in the approved session window."""
    if currency.upper() == "KRW":
        return True
    try:
        fx_date = date.fromisoformat(str(raw_fx_date))
    except (TypeError, ValueError):
        return False
    return earliest_fx_date <= fx_date <= evaluation_date
