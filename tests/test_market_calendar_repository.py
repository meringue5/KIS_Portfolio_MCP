import importlib


def test_upsert_market_calendar_rows_uses_one_statement(monkeypatch):
    from kis_portfolio.db import repository

    calls = []

    class Connection:
        def execute(self, query, parameters):
            calls.append((query, parameters))

    monkeypatch.setattr(repository, "get_connection", lambda: Connection())
    rows = [
        {"market": "krx", "trade_date": "20260810", "is_open": True, "raw_data": {"version": 1}},
        {"market": "krx", "trade_date": "20260811", "is_open": True, "raw_data": {"version": 1}},
    ]

    assert repository.upsert_market_calendar_rows(rows) == 2
    assert len(calls) == 1
    assert calls[0][0].count("(?, ?, ?, ?, ?, ?, ?, ?, ?)") == 2
    assert len(calls[0][1]) == 18

def test_upsert_market_calendar_rows_updates_existing_date(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_portfolio.db as kisdb

    kisdb = importlib.reload(kisdb)
    initial = {
        "market": "krx",
        "trade_date": "20260810",
        "is_open": True,
        "open_time_local": "09:00",
        "close_time_local": "15:30",
        "timezone": "Asia/Seoul",
        "source": "test",
        "note": None,
        "raw_data": {"version": 1},
    }
    updated = {
        **initial,
        "is_open": False,
        "open_time_local": None,
        "close_time_local": None,
        "note": "test closure",
        "raw_data": {"version": 2},
    }

    try:
        assert kisdb.upsert_market_calendar_rows([initial]) == 1
        assert kisdb.upsert_market_calendar_rows([updated]) == 1
        row = kisdb.get_market_calendar_entry("krx", "20260810")
    finally:
        kisdb.close_connection()

    assert row is not None
    assert row["is_open"] is False
    assert row["note"] == "test closure"
    assert row["raw_data"] == {"version": 2}
    assert row["updated_at"] is not None
