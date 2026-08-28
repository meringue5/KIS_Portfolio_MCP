from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/migrate_v1_v2_trade_lots.py"
    spec = importlib.util.spec_from_file_location("migrate_v1_v2_trade_lots", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trade_lot_thread_migration_is_idempotent(tmp_path: Path) -> None:
    backup=tmp_path/"backup";backup.mkdir();c=duckdb.connect()
    for name in ("order_history","overseas_transaction_history","trade_profit_history"):
        c.execute(f"COPY (SELECT '{name}-1' id) TO '{backup/(name+'.parquet')}' (FORMAT PARQUET)")
    c.execute(f"COPY (SELECT 'tx1' transaction_hash,date '2026-01-02' transaction_date,timestamp '2026-01-03' last_seen_at) TO '{backup/'overseas_transactions.parquet'}' (FORMAT PARQUET)")
    c.execute(f"""COPY (SELECT * FROM (VALUES
      ('ria','01','02',date '2026-01-02','1','100','090000',timestamp '2026-01-03',10::BIGINT,1000::BIGINT,1000::BIGINT,'005930',''),
      ('ria','01','01',date '2026-01-02','1','101','090100',timestamp '2026-01-03',3::BIGINT,1100::BIGINT,1100::BIGINT,'005930',''),
      ('ria','01','99',date '2026-01-02','1','102','090200',timestamp '2026-01-03',2::BIGINT,1200::BIGINT,1200::BIGINT,'005930',''),
      ('ria','01','02',date '2026-01-02','1','103','090300',timestamp '2026-01-03',0::BIGINT,1000::BIGINT,1000::BIGINT,'005930','')
    ) t(account_type,account_product_code,side_code,order_date,order_branch_no,order_no,order_time,last_seen_at,filled_qty,avg_price,order_price,symbol,original_order_no)) TO '{backup/'domestic_orders.parquet'}' (FORMAT PARQUET)""");c.close()
    target=duckdb.connect(str(tmp_path/"target.duckdb"));MigrationRunner(target).apply()
    target.execute("INSERT INTO silver.accounts VALUES (sha256('v1-account|ria'),'ria','ria','KRW',current_timestamp,NULL,'{}')")
    target.execute("INSERT INTO silver.instruments VALUES ('v1|KRX|005930','KRX','005930',NULL,'equity','KRW',NULL,current_timestamp,NULL,'fixture','{}')")
    target.execute("INSERT INTO silver.position_snapshots VALUES (sha256('v1-account|ria'),'v1|KRX|005930',current_timestamp,10,NULL,'KRW','fixture','passed')")
    module=load_module();first=module.apply(target,backup,"test-trade");second=module.apply(target,backup,"test-trade")
    assert first==second
    assert first["source_orders"]=={"rows":4,"filled":3,"buy":1,"sell":1,"unknown_side":1,"deferred_unfilled":1,"corrections":0}
    assert first["target_rows"]=={"trade_events":2,"trade_event_revisions":2,"purchase_lots":1,"threads":1,"thread_links":1}
    assert first["position_coverage"]=={"account_instruments":1,"matched":1,"partial_history":0}
    assert target.execute("select side, count(*) from silver.trade_events_current group by side order by side").fetchall()==[("buy",1),("sell",1)]
    assert target.execute("select count(*) from silver.purchase_lots_current").fetchone()[0]==1
    target.close()
