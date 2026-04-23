"""Market calendar generation and gating helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

from kis_portfolio import db as kisdb


KOREA_TZ = ZoneInfo("Asia/Seoul")
KRX_MARKET = "krx"
KRX_OPEN_TIME = "09:00"
KRX_CLOSE_TIME = "15:30"


@dataclass(frozen=True)
class CalendarGate:
    status: str
    reason: str
    calendar: dict
    trade_date: str
    now_local: str


def _iter_year_dates(year: int) -> list[date]:
    current = date(year, 1, 1)
    end = date(year, 12, 31)
    rows = []
    while current <= end:
        rows.append(current)
        current += timedelta(days=1)
    return rows


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _business_day_before(value: date, closed_dates: set[date]) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in closed_dates:
        candidate -= timedelta(days=1)
    return candidate


def _year_end_closure_date(year: int, closed_dates: set[date]) -> date:
    candidate = date(year, 12, 31)
    if candidate.weekday() < 5 and candidate not in closed_dates:
        return candidate
    return _business_day_before(candidate, closed_dates)


def generate_krx_market_calendar_year(year: int) -> list[dict]:
    """Generate one KRX market calendar year from public-holiday and KRX rules."""
    public_holidays = holidays.country_holidays("KR", years=[year], language="ko")
    holiday_dates = set(public_holidays.keys())
    year_end_closure = _year_end_closure_date(year, holiday_dates)

    rows = []
    for trade_date in _iter_year_dates(year):
        is_weekend = trade_date.weekday() >= 5
        holiday_name = public_holidays.get(trade_date)
        is_labor_day = trade_date.month == 5 and trade_date.day == 1
        is_year_end_closure = trade_date == year_end_closure

        is_open = True
        note = None
        open_time_local = KRX_OPEN_TIME
        close_time_local = KRX_CLOSE_TIME

        if is_weekend:
            is_open = False
            note = "주말 휴장"
        elif holiday_name:
            is_open = False
            note = f"공휴일 휴장: {holiday_name}"
        elif is_labor_day:
            is_open = False
            note = "근로자의 날 휴장"
        elif is_year_end_closure:
            is_open = False
            note = "연말 휴장"

        if not is_open:
            open_time_local = None
            close_time_local = None

        rows.append({
            "market": KRX_MARKET,
            "trade_date": trade_date,
            "is_open": is_open,
            "open_time_local": open_time_local,
            "close_time_local": close_time_local,
            "timezone": "Asia/Seoul",
            "source": "generated:holidays.KR+krx_rules",
            "note": note,
            "raw_data": {
                "public_holiday_name": holiday_name,
                "is_weekend": is_weekend,
                "is_labor_day": is_labor_day,
                "is_year_end_closure": is_year_end_closure,
            },
        })
    return rows


def sync_krx_market_calendar_years(years: list[int]) -> dict:
    """Upsert generated KRX calendar rows for one or more years."""
    normalized = sorted({int(year) for year in years})
    total_saved = 0
    yearly = []
    for year in normalized:
        rows = generate_krx_market_calendar_year(year)
        saved = kisdb.upsert_market_calendar_rows(rows)
        total_saved += saved
        yearly.append({"year": year, "rows": saved})
    return {
        "market": KRX_MARKET,
        "years": normalized,
        "saved_rows": total_saved,
        "yearly": yearly,
    }


def ensure_krx_market_calendar_year(year: int) -> int:
    """Ensure a full KRX market calendar year exists in the DB."""
    existing = kisdb.count_market_calendar_rows(KRX_MARKET, year)
    expected = len(_iter_year_dates(year))
    if existing >= expected:
        return 0
    return kisdb.upsert_market_calendar_rows(generate_krx_market_calendar_year(year))


def get_krx_market_calendar_entry(trade_date: str) -> dict | None:
    """Load one persisted KRX market calendar row."""
    return kisdb.get_market_calendar_entry(KRX_MARKET, trade_date)


def evaluate_krx_collection_gate(
    trade_date: str,
    *,
    now: datetime | None = None,
    close_grace_minutes: int = 5,
) -> CalendarGate:
    """Decide whether KRX post-close collection should run for a date."""
    trade_day = datetime.strptime(trade_date, "%Y%m%d").date()
    current = now.astimezone(KOREA_TZ) if now else datetime.now(KOREA_TZ)

    ensure_krx_market_calendar_year(trade_day.year)
    calendar = get_krx_market_calendar_entry(trade_date)
    if not calendar:
        return CalendarGate(
            status="skipped",
            reason="calendar_missing",
            calendar={},
            trade_date=trade_date,
            now_local=current.isoformat(),
        )

    if not calendar["is_open"]:
        return CalendarGate(
            status="skipped",
            reason="market_closed",
            calendar=calendar,
            trade_date=trade_date,
            now_local=current.isoformat(),
        )

    if trade_day == current.date():
        close_time = _parse_hhmm(calendar["close_time_local"] or KRX_CLOSE_TIME)
        cutoff = datetime.combine(trade_day, close_time, tzinfo=KOREA_TZ) + timedelta(
            minutes=close_grace_minutes
        )
        if current < cutoff:
            return CalendarGate(
                status="skipped",
                reason="before_close_grace_window",
                calendar=calendar,
                trade_date=trade_date,
                now_local=current.isoformat(),
            )

    return CalendarGate(
        status="collect",
        reason="ready",
        calendar=calendar,
        trade_date=trade_date,
        now_local=current.isoformat(),
    )
