"""Protected additive diagnostic migration, private recovery and source-preserving bootstrap."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.wi066_release import MAX_BACKUP_BYTES, _backup_round_trip, _backup_summary
from kis_portfolio.services.cash_reconciliation_runtime import after_success


@dataclass(frozen=True)
class WI071ReleaseConfig:
    project: str
    bucket: str


def preserved_fingerprints(con):
    allowed_mutations={'control.schema_migrations','control.pipeline_definitions','control.pipeline_runs',
        'control.pipeline_stage_runs','control.quality_results','control.lineage_edges',
        'control.cash_balance_reconciliations'}
    return {name:con.execute(f'SELECT count(*),bit_xor(hash(t)) FROM {name} t').fetchone()
            for name in v2_backup_table_names() if name not in allowed_mutations}


def bootstrap(con):
    latest=con.execute("""SELECT run_id FROM control.pipeline_runs WHERE
        pipeline_id='pipeline.owned-portfolio-core-v2' AND status='succeeded' AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1""").fetchone()
    if latest is None:
        raise RuntimeError('cash_reconciliation_source_run_missing')
    outcome=after_success(con,run_id=latest[0])
    if outcome['status']!='partial':
        raise RuntimeError('cash_reconciliation_bootstrap_failed')
    return outcome


def run_wi071_release(config, *, connection_factory=get_connection,
                      store_factory=lambda bucket:GCSObjectStore(bucket,prefix='recovery/wi071')):
    image=os.getenv('KIS_RELEASE_IMAGE_DIGEST','')
    sha=os.getenv('KIS_RELEASE_GIT_SHA','')
    if (get_db_mode()!='motherduck' or not image.startswith('sha256:') or len(sha)<7
            or os.getenv('KIS_CASH_RECONCILIATION_ENABLED','false')!='true'):
        raise RuntimeError('wi071_release_provenance_required')
    con=connection_factory()
    try:
        runner=MigrationRunner(con)
        runner.require('0022')
        if max(runner.applied()) not in {'0022','0023'}:
            raise RuntimeError('wi071_migration_ceiling_unsupported')
        if max(runner.applied())=='0022' and con.execute("""SELECT count(*) FROM information_schema.tables
            WHERE table_catalog=current_database() AND table_schema='control'
              AND table_name='cash_balance_reconciliations'""").fetchone()[0]:
            raise RuntimeError('wi071_unowned_table_drift')
        before=preserved_fingerprints(con)
        with tempfile.TemporaryDirectory(prefix='kis-wi071-') as tmp:
            root=Path(tmp);root.chmod(0o700)
            store=store_factory(config.bucket)
            pre,pre_upload,pre_path=_backup_round_trip(connection=con,store=store,root=root,label='pre')
            if pre_upload['byte_size']>MAX_BACKUP_BYTES:
                raise RuntimeError('wi071_backup_budget_exceeded')
            with duckdb.connect(str(pre_path)) as restored:
                MigrationRunner(restored).apply(through='0023')
                bootstrap(restored)
                if preserved_fingerprints(restored)!=before:
                    raise RuntimeError('wi071_rehearsal_changed_authoritative_inputs')
            applied=runner.apply(through='0023')
            if applied not in ([],['0023']) or runner.apply(through='0023'):
                raise RuntimeError('wi071_migration_replay_failed')
            result=bootstrap(con)
            if preserved_fingerprints(con)!=before:
                raise RuntimeError('wi071_source_fingerprints_changed')
            diag=con.execute('SELECT count(*),bit_xor(hash(t)) FROM control.cash_balance_reconciliations t').fetchone()
            post,post_upload,post_path=_backup_round_trip(connection=con,store=store,root=root,label='post')
            if post_upload['byte_size']>MAX_BACKUP_BYTES:
                raise RuntimeError('wi071_backup_budget_exceeded')
            with duckdb.connect(str(post_path),read_only=True) as restored:
                if (preserved_fingerprints(restored)!=before or diag!=restored.execute(
                    'SELECT count(*),bit_xor(hash(t)) FROM control.cash_balance_reconciliations t').fetchone()):
                    raise RuntimeError('wi071_post_restore_mismatch')
            return dict(status='verified',work_item='WI-071',applied_migrations=applied,
                authoritative_tables_preserved=len(before),diagnostic_rows=diag[0],
                pre_backup=_backup_summary(pre_upload),post_backup=_backup_summary(post_upload),
                bootstrap=result,image_digest=image,git_sha=sha,broker_calls=0,monetary_writes=0,
                actual_oauth_acceptance='required after release')
    finally:
        con.close()
