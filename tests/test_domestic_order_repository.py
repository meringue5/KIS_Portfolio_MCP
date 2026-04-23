import importlib


def test_upsert_domestic_orders_deduplicates_by_kis_order_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_portfolio.db as kisdb

    kisdb = importlib.reload(kisdb)
    try:
        saved = kisdb.upsert_domestic_orders([
            {
                "account_id": "12345678",
                "account_product_code": "01",
                "account_type": "brokerage",
                "order_date": "20260423",
                "order_branch_no": "",
                "order_no": "A-100",
                "symbol": "005930",
                "symbol_name": "삼성전자",
                "side_code": "02",
                "side_name": "매수",
                "order_qty": 10,
                "total_order_qty": 10,
                "order_price": 60000,
                "filled_qty": 2,
                "filled_amount": 120000,
                "pending_qty": 8,
                "last_source": "kis_api",
                "last_order_history_id": "snapshot-1",
                "raw_data": {"odno": "A-100", "tot_ccld_qty": "2"},
            }
        ])
        assert saved == 1

        saved = kisdb.upsert_domestic_orders([
            {
                "account_id": "12345678",
                "account_product_code": "01",
                "account_type": "brokerage",
                "order_date": "20260423",
                "order_branch_no": "",
                "order_no": "A-100",
                "symbol": "005930",
                "symbol_name": "삼성전자",
                "side_code": "02",
                "side_name": "매수",
                "order_qty": 10,
                "total_order_qty": 10,
                "order_price": 60000,
                "filled_qty": 10,
                "filled_amount": 600000,
                "pending_qty": 0,
                "last_source": "batch",
                "last_order_history_id": "snapshot-2",
                "raw_data": {"odno": "A-100", "tot_ccld_qty": "10"},
            }
        ])
        assert saved == 1

        rows = kisdb.get_domestic_orders(
            "12345678",
            "01",
            "20260423",
            "20260423",
        )
    finally:
        kisdb.close_connection()

    assert len(rows) == 1
    assert rows[0]["order_no"] == "A-100"
    assert rows[0]["filled_qty"] == 10
    assert rows[0]["pending_qty"] == 0
    assert rows[0]["last_source"] == "batch"
    assert rows[0]["last_order_history_id"] == "snapshot-2"
    assert rows[0]["raw_data"]["tot_ccld_qty"] == "10"


def test_upsert_domestic_orders_separates_account_product_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_portfolio.db as kisdb

    kisdb = importlib.reload(kisdb)
    try:
        saved = kisdb.upsert_domestic_orders([
            {
                "account_id": "12345678",
                "account_product_code": "01",
                "account_type": "brokerage",
                "order_date": "20260423",
                "order_branch_no": "",
                "order_no": "A-100",
                "symbol": "005930",
                "raw_data": {"odno": "A-100"},
            },
            {
                "account_id": "12345678",
                "account_product_code": "29",
                "account_type": "irp",
                "order_date": "20260423",
                "order_branch_no": "",
                "order_no": "A-100",
                "symbol": "005930",
                "raw_data": {"odno": "A-100"},
            },
        ])
        assert saved == 2

        rows_01 = kisdb.get_domestic_orders("12345678", "01", "20260423", "20260423")
        rows_29 = kisdb.get_domestic_orders("12345678", "29", "20260423", "20260423")
    finally:
        kisdb.close_connection()

    assert len(rows_01) == 1
    assert len(rows_29) == 1
    assert rows_01[0]["account_type"] == "brokerage"
    assert rows_29[0]["account_type"] == "irp"
