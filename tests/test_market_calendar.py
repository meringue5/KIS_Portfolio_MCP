from datetime import datetime

from kis_portfolio.services.market_calendar import (
    evaluate_krx_collection_gate,
    generate_krx_market_calendar_year,
)


def _find(rows: list[dict], trade_date: str) -> dict:
    for row in rows:
        if row["trade_date"].strftime("%Y%m%d") == trade_date:
            return row
    raise AssertionError(f"missing row for {trade_date}")


def test_generate_krx_market_calendar_marks_weekend_closed():
    rows = generate_krx_market_calendar_year(2026)

    saturday = _find(rows, "20260103")
    monday = _find(rows, "20260105")

    assert saturday["is_open"] is False
    assert saturday["note"] == "주말 휴장"
    assert monday["is_open"] is True
    assert monday["open_time_local"] == "09:00"
    assert monday["close_time_local"] == "15:30"


def test_generate_krx_market_calendar_marks_labor_day_closed():
    rows = generate_krx_market_calendar_year(2026)
    labor_day = _find(rows, "20260501")

    assert labor_day["is_open"] is False
    assert "근로자의 날" in (labor_day["note"] or "")


def test_generate_krx_market_calendar_marks_year_end_closure_closed():
    rows = generate_krx_market_calendar_year(2026)
    year_end = _find(rows, "20261231")

    assert year_end["is_open"] is False
    assert year_end["note"] == "연말 휴장"


def test_evaluate_krx_collection_gate_skips_before_close(monkeypatch):
    monkeypatch.setattr(
        "kis_portfolio.services.market_calendar.ensure_krx_market_calendar_year",
        lambda year: 0,
    )
    monkeypatch.setattr(
        "kis_portfolio.services.market_calendar.get_krx_market_calendar_entry",
        lambda trade_date: {
            "market": "krx",
            "trade_date": "2026-04-23",
            "is_open": True,
            "open_time_local": "09:00",
            "close_time_local": "15:30",
            "timezone": "Asia/Seoul",
            "note": None,
        },
    )

    gate = evaluate_krx_collection_gate(
        "20260423",
        now=datetime.fromisoformat("2026-04-23T15:34:00+09:00"),
    )

    assert gate.status == "skipped"
    assert gate.reason == "before_close_grace_window"


def test_evaluate_krx_collection_gate_skips_holiday(monkeypatch):
    monkeypatch.setattr(
        "kis_portfolio.services.market_calendar.ensure_krx_market_calendar_year",
        lambda year: 0,
    )
    monkeypatch.setattr(
        "kis_portfolio.services.market_calendar.get_krx_market_calendar_entry",
        lambda trade_date: {
            "market": "krx",
            "trade_date": "2026-05-01",
            "is_open": False,
            "open_time_local": None,
            "close_time_local": None,
            "timezone": "Asia/Seoul",
            "note": "근로자의 날 휴장",
        },
    )

    gate = evaluate_krx_collection_gate(
        "20260501",
        now=datetime.fromisoformat("2026-05-01T15:35:00+09:00"),
    )

    assert gate.status == "skipped"
    assert gate.reason == "market_closed"
