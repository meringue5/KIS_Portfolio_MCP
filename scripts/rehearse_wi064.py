#!/usr/bin/env python3
"""WI-064: rehearse on a fresh LOCAL restore; never opens or mutates production."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


ROOT = Path(__file__).resolve().parents[1]


def fingerprints(con):
    return {name: con.execute(f'SELECT count(*), bit_xor(hash(t)) FROM {name} t').fetchone()
            for name in v2_backup_table_names() if name != 'control.schema_migrations'}


def count(con, table):
    return con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


def duplicates(con):
    return con.execute('''SELECT count(*) FROM (
        SELECT 1 FROM silver.trade_events_current
        GROUP BY account_id,market,instrument_id,executed_at,side,quantity,price,currency
        HAVING count(*)>1)''').fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--workspace', required=True, type=Path, help='new private local directory')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    target = root / 'restored.duckdb'
    restored = restore_v2_backup(args.backup, target)
    con = duckdb.connect(str(target))
    assert MigrationRunner(con).applied().keys() == {f'{n:04}' for n in range(1, 22)}
    before = fingerprints(con)
    old_views = dict(con.execute("""SELECT view_name, sql FROM duckdb_views()
        WHERE database_name=current_database() AND schema_name='silver'
        AND view_name IN ('trade_events_current','purchase_lots_current')""").fetchall())
    old_rows, old_duplicates = count(con, 'silver.trade_events_current'), duplicates(con)
    lots_before = count(con, 'silver.purchase_lots_current')
    cash_count = count(con, 'silver.cash_flow_events')
    cash_candidates = con.execute('''SELECT count(*) FROM (
        SELECT 1 FROM silver.cash_flow_events
        GROUP BY account_id,effective_at,event_type,amount,currency HAVING count(*)>1)''').fetchone()[0]
    cash_legacy = con.execute("""SELECT count(*) FROM silver.cash_flow_events c
        JOIN bronze.source_observations b ON b.observation_id=c.source_observation_id
        WHERE b.observation_id LIKE 'v1-%'""").fetchone()[0]
    refs = {name: count(con, name) for name in (
        'silver.purchase_lots','silver.trade_threads','silver.trade_thread_lots',
        'silver.trade_journal_revisions','silver.purchase_lot_identities',
        'silver.sell_allocation_sets','silver.sell_allocation_revisions')}
    applied = MigrationRunner(con).apply()
    assert applied == ['0022'] and MigrationRunner(con).apply() == []
    after = fingerprints(con)
    assert before == after, 'source/history/reference table changed'
    links = con.execute('''SELECT count(*) FROM silver.trade_event_identity_aliases
        WHERE source_trade_event_id<>canonical_source_trade_event_id''').fetchone()[0]
    new_rows, new_duplicates = count(con, 'silver.trade_events_current'), duplicates(con)
    assert old_rows-new_rows == links
    # Every historical source/revision id remains resolvable to one canonical source id.
    assert con.execute('''SELECT count(*) FROM silver.trade_event_revisions r
        LEFT JOIN silver.trade_event_identity_aliases a USING(source_trade_event_id)
        WHERE a.canonical_source_trade_event_id IS NULL''').fetchone()[0] == 0
    # Reversible view-only rollback rehearsed in a local transaction, no source mutation.
    con.execute('BEGIN')
    for sql in old_views.values():
        con.execute(sql.replace('CREATE VIEW ', 'CREATE OR REPLACE VIEW ', 1))
    assert count(con, 'silver.trade_events_current') == old_rows
    assert duplicates(con) == old_duplicates
    assert fingerprints(con) == before
    con.execute('ROLLBACK')
    assert count(con, 'silver.trade_events_current') == new_rows
    backup = root / 'post-backup'
    export_v2_backup(con, backup, database='wi064-local-rehearsal')
    con.close()
    post_restore = restore_v2_backup(backup, root / 'post-restored.duckdb')
    check = duckdb.connect(str(root / 'post-restored.duckdb'), read_only=True)
    assert fingerprints(check) == before
    assert count(check, 'silver.trade_events_current') == new_rows
    result = dict(
        work_item='WI-064', observed_at=datetime.now(UTC).isoformat(), production_mutations=0,
        evidence_kind='production-backup-fresh-local-restore', applied_migrations=applied,
        pre_restore_tables=restored['tables'], post_restore_tables=post_restore['tables'],
        unchanged_data_table_fingerprints=len(before), source_history_references_preserved=True,
        before_current_rows=old_rows, after_current_rows=new_rows,
        before_duplicate_candidate_groups=old_duplicates, after_duplicate_candidate_groups=new_duplicates,
        source_proven_alias_links=links, historical_ids_resolve=True,
        before_current_lots=lots_before, after_current_lots=count(check,'silver.purchase_lots_current'),
        preserved_reference_row_counts=refs,
        cash_rows=cash_count, cash_same_economics_candidates=cash_candidates,
        cash_linked_to_legacy_observations=cash_legacy,
        rollback_restored_prior_counts=True, rollback_changed_source_rows=False,
        real_client_acceptance='pending production approval; local replay is not OAuth acceptance',
        private_object_bytes='not included; table/view-only change does not alter object bytes',
    )
    check.close()
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
