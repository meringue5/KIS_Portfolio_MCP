"""Protected WI-064 view-only migration with private backup/restore evidence."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.wi066_release import MAX_BACKUP_BYTES, _backup_round_trip, _backup_summary


@dataclass(frozen=True, slots=True)
class WI064ReleaseConfig:
    project: str
    bucket: str


def _data_fingerprints(con):
    return {name: con.execute(f'SELECT count(*), bit_xor(hash(t)) FROM {name} t').fetchone()
            for name in v2_backup_table_names()}


def _projection(con):
    return dict(current_rows=con.execute('SELECT count(*) FROM silver.trade_events_current').fetchone()[0],
                aliases=con.execute('''SELECT count(*) FROM silver.trade_event_identity_aliases
                    WHERE source_trade_event_id<>canonical_source_trade_event_id''').fetchone()[0])


def run_wi064_release(config: WI064ReleaseConfig, *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(bucket, prefix='recovery/wi064'),
) -> dict:
    if get_db_mode() != 'motherduck':
        raise RuntimeError('WI-064 requires MotherDuck mode')
    image, git_sha = os.getenv('KIS_RELEASE_IMAGE_DIGEST', ''), os.getenv('KIS_RELEASE_GIT_SHA', '')
    if not image.startswith('sha256:') or len(git_sha) < 7:
        raise RuntimeError('WI-064 requires immutable release provenance')
    con = connection_factory()
    try:
        runner = MigrationRunner(con)
        runner.require('0021')
        if max(runner.applied()) not in {'0021', '0022'}:
            raise RuntimeError('WI-064 unsupported migration ceiling')
        if con.execute('''SELECT (SELECT count(*) FROM silver.purchase_lot_identities)+
                          (SELECT count(*) FROM silver.sell_allocation_sets)''').fetchone()[0]:
            raise RuntimeError('WI-064 requires reviewed reconciliation of existing reconstruction outputs')
        store = store_factory(config.bucket)
        with tempfile.TemporaryDirectory(prefix='kis-wi064-') as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            before = _data_fingerprints(con)
            pre, pre_upload, restored_path = _backup_round_trip(connection=con, store=store, root=root, label='pre')
            if pre_upload['byte_size'] > MAX_BACKUP_BYTES:
                raise RuntimeError('WI-064 backup bound exceeded')
            # Evaluate the migration against a fresh copy before ANY live DDL.
            with duckdb.connect(str(restored_path)) as restored:
                if _data_fingerprints(restored) != before:
                    raise RuntimeError('WI-064 pre restore differs from live state')
                old_count = restored.execute('SELECT count(*) FROM silver.trade_events_current').fetchone()[0]
                pending = MigrationRunner(restored).apply(through='0022')
                expected = _projection(restored)
                if pending and old_count - expected['current_rows'] != expected['aliases']:
                    raise RuntimeError('WI-064 source alias reconciliation failed')
                if _data_fingerprints(restored) != before:
                    raise RuntimeError('WI-064 rehearsal changed source tables')
            prior_views = dict(con.execute("""SELECT view_name,sql FROM duckdb_views()
                WHERE database_name=current_database() AND schema_name='silver'
                  AND view_name IN ('trade_events_current','purchase_lots_current')""").fetchall())
            applied = []
            try:
                applied = runner.apply(through='0022')
                if applied not in ([], ['0022']) or runner.apply(through='0022'):
                    raise RuntimeError('WI-064 unexpected migration/replay')
                if _projection(con) != expected or _data_fingerprints(con) != before:
                    raise RuntimeError('WI-064 live projection/source reconciliation failed')
                post, post_upload, post_path = _backup_round_trip(connection=con, store=store, root=root, label='post')
                if post_upload['byte_size'] > MAX_BACKUP_BYTES:
                    raise RuntimeError('WI-064 post backup bound exceeded')
                with duckdb.connect(str(post_path), read_only=True) as restored:
                    if _projection(restored) != expected or _data_fingerprints(restored) != before:
                        raise RuntimeError('WI-064 post restore reconciliation failed')
            except Exception:
                # Preserve the migration ledger and all data; restore only prior read projections.
                # A deliberately reviewed resume must reapply the pinned view SQL, not erase history.
                if applied:
                    con.execute('BEGIN')
                    try:
                        for sql in prior_views.values():
                            con.execute(sql.replace('CREATE VIEW ', 'CREATE OR REPLACE VIEW ', 1))
                        con.execute('COMMIT')
                    except Exception:
                        con.execute('ROLLBACK')
                        raise
                raise
            return dict(status='verified', work_item='WI-064', applied_migrations=applied,
                        projection=expected, preserved_data_tables=len(before),
                        source_history_preserved=True, pre_backup=_backup_summary(pre_upload),
                        post_backup=_backup_summary(post_upload), git_sha=git_sha, image_digest=image,
                        actual_oauth_acceptance='required after release; not established by this Job')
    finally:
        con.close()
