"""Source-grounded legacy/current order identity regression fixtures (synthetic only)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.position_reconstruction_runtime import _trade_state


EXECUTED = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)


def observe(con, observation_id, payload, day):
    at = EXECUTED + timedelta(days=day)
    con.execute(
        """INSERT INTO bronze.source_observations
        (observation_id,dataset_id,source_id,source_record_id,idempotency_key,
         observed_at,fetched_at,content_hash,quality_status,payload)
        VALUES (?,'dataset.trade-event','source.kis-open-api',?,?,?,?,'fixture','pass',?)""",
        [observation_id, observation_id, observation_id, at, at, json.dumps(payload)],
    )


def seed(con, *, old_order='0001', new_order='0001', field=None, value=None):
    old = dict(order_no=old_order, order_branch_no='001', order_date='2026-08-25',
               order_time='100000', symbol='SYNTH', side_code='02', filled_qty='2', avg_price='100')
    new = dict(odno=new_order, ord_gno_brno='001', ord_dt='20260825', ord_tmd='100000',
               pdno='SYNTH', sll_buy_dvsn_cd='02', tot_ccld_qty='2', avg_prvs='100')
    if field:
        new[field] = value
    observe(con, 'v1-domestic-order-fixture', old, 1)
    observe(con, 'new-fixture', new, 2)
    repo = V2WarehouseRepository(con)
    common = dict(account_id='synthetic', market='KRX', account_product_code='01',
                  instrument_id='v1|KRX|SYNTH', executed_at=EXECUTED, side='buy',
                  quantity='2', price='100', currency='KRW', execution_sequence='aggregate')
    legacy, lot = repo.record_trade_with_lot(
        dict(common, broker_order_id=f'2026-08-25|001|{old_order}', correction_reason='v1_import_contract'),
        'v1-domestic-order-fixture',
    )
    new_payload = dict(common, broker_order_id=f'01|2026-08-25|KRX|001|{new_order}')
    collected = repo.record_trade(new_payload, 'new-fixture')
    return repo, legacy, collected, lot, new_payload


def db():
    con = duckdb.connect(':memory:')
    MigrationRunner(con).apply(through='0021')
    return con


def test_identity_repair_keeps_history_references_and_corrected_buy_projection(tmp_path):
    con = db()
    repo, legacy, collected, lot, payload = seed(con)
    thread = repo.create_thread(dict(thread_id='thread', account_id='synthetic',
                                    instrument_id='v1|KRX|SYNTH', opened_at=EXECUTED), lot)
    repo.append_journal(dict(journal_id='journal', revision=1, thread_id=thread,
                            trade_event_id=legacy, body='Synthetic', authored_at=EXECUTED))
    original_ids = con.execute('SELECT trade_event_revision_id FROM silver.trade_event_revisions ORDER BY 1').fetchall()
    assert con.execute('SELECT count(*) FROM silver.trade_events_current').fetchone() == (2,)
    assert MigrationRunner(con).apply() == ['0022']
    assert MigrationRunner(con).apply() == []
    assert con.execute('SELECT count(*) FROM silver.trade_events_current').fetchone() == (1,)
    assert con.execute('SELECT source_trade_event_id FROM silver.trade_events_current').fetchone() == (legacy,)
    assert con.execute('SELECT lot_id FROM silver.purchase_lots_current').fetchone() == (lot,)
    assert con.execute('SELECT trade_event_revision_id FROM silver.trade_event_revisions ORDER BY 1').fetchall() == original_ids
    assert con.execute('SELECT trade_event_id FROM silver.trade_journal_revisions').fetchone() == (legacy,)
    assert con.execute('SELECT lot_id FROM silver.trade_thread_lots').fetchone() == (lot,)
    assert con.execute('SELECT canonical_source_trade_event_id FROM silver.trade_event_identity_aliases WHERE source_trade_event_id=?', [collected]).fetchone() == (legacy,)
    trades = _trade_state(con, EXECUTED-timedelta(days=1), EXECUTED+timedelta(days=1))
    assert sum(len(rows) for rows in trades.values()) == 1
    # Replay stays idempotent, then an explicit source correction wins across the linked identities.
    assert repo.record_trade(payload, 'new-fixture') == collected
    assert con.execute('SELECT count(*) FROM silver.trade_event_revisions').fetchone() == (2,)
    observe(con, 'correction-fixture', {'correction': True}, 3)
    assert repo.record_trade(dict(payload, event_version=2, side='sell', quantity='3'), 'correction-fixture') == collected
    assert con.execute('SELECT side, quantity FROM silver.trade_events_current').fetchone() == ('sell', 3)
    assert con.execute('SELECT count(*) FROM silver.purchase_lots_current').fetchone() == (0,)
    assert con.execute('SELECT count(*) FROM silver.trade_event_identity_aliases WHERE source_trade_event_id<>canonical_source_trade_event_id').fetchone() == (1,)
    assert con.execute('SELECT count(*) FROM silver.purchase_lots').fetchone() == (1,)
    # All previously returned revision identifiers still resolve to immutable history.
    assert all(con.execute('SELECT count(*) FROM silver.trade_event_revisions WHERE trade_event_revision_id=?', row).fetchone() == (1,) for row in original_ids)
    con.close()


@pytest.mark.parametrize(('field','value'), [
    ('odno','0002'), ('ord_gno_brno','002'), ('ord_dt','20260824'), ('ord_tmd','100001'),
    ('pdno','OTHER'), ('sll_buy_dvsn_cd','01'), ('tot_ccld_qty','3'), ('avg_prvs','101'),
    ('odno',''), ('ord_gno_brno',None),
])
def test_equal_economics_without_full_source_proof_never_merge(field, value):
    con = db()
    seed(con, field=field, value=value)
    MigrationRunner(con).apply()
    assert con.execute('SELECT count(*) FROM silver.trade_events_current').fetchone() == (2,)
    con.close()


def test_distinct_orders_at_same_price_time_and_quantity_survive():
    con = db()
    seed(con, new_order='0002')
    MigrationRunner(con).apply()
    assert con.execute('SELECT count(*) FROM silver.trade_events_current').fetchone() == (2,)
    con.close()


def test_both_legacy_and_collected_lots_are_preserved_but_current_uses_legacy_anchor():
    con = db()
    repo, legacy, collected, lot, payload = seed(con)
    repo.record_trade_with_lot(payload, 'new-fixture')
    MigrationRunner(con).apply()
    assert con.execute('SELECT count(*) FROM silver.purchase_lots').fetchone() == (2,)
    assert con.execute('SELECT lot_id FROM silver.purchase_lots_current').fetchall() == [(lot,)]
    con.close()


def test_order_query_correction_and_late_replay_preserve_newest_aggregate():
    con = db()
    repo, legacy, collected, lot, payload = seed(con)
    MigrationRunner(con).apply()
    observe(con, 'later', {'tot_ccld_qty': '3'}, 3)
    assert repo.record_trade(dict(payload, quantity='3'), 'later') == collected
    assert con.execute('SELECT revision,quantity FROM silver.trade_events_current').fetchone() == (2, 3)
    assert repo.record_trade(dict(payload, quantity='3'), 'later') == collected
    assert repo.record_trade(payload, 'new-fixture') == collected
    assert con.execute('SELECT revision,quantity FROM silver.trade_events_current').fetchone() == (2, 3)
    with pytest.raises(ValueError, match='immutable history'):
        repo.record_trade(dict(payload, event_version=2, quantity='4'), 'later')
    with pytest.raises(ValueError, match='same knowledge time'):
        repo.record_trade(dict(payload, quantity='4'), 'later')
    # A later source reversion to the initial amount is still a new correction.
    observe(con, 'reversion', {'tot_ccld_qty': '2'}, 4)
    repo.record_trade(payload, 'reversion')
    assert con.execute('SELECT revision,quantity FROM silver.trade_events_current').fetchone() == (3, 2)
    assert con.execute('SELECT count(*) FROM silver.trade_event_revisions').fetchone() == (4,)
    con.close()
