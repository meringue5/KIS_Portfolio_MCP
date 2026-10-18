from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services import wi064_release as release
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup
from test_deploy_cloud_run import deploy_cloud_run


@pytest.mark.parametrize('fail_phase', [None, 'pre', 'post'])
def test_protected_release_restore_and_failure_boundaries(tmp_path, monkeypatch, fail_phase):
    path = tmp_path/'source.duckdb'
    con = duckdb.connect(str(path))
    MigrationRunner(con).apply(through='0021')
    con.execute("INSERT INTO silver.trade_events VALUES ('base','acct','inst','buy',current_timestamp,1,10,'KRW','order',1,'obs','pass')")
    before = release._data_fingerprints(con)
    con.close()
    monkeypatch.setenv('KIS_DB_MODE','motherduck')
    monkeypatch.setenv('KIS_RELEASE_GIT_SHA','a'*40)
    monkeypatch.setenv('KIS_RELEASE_IMAGE_DIGEST','sha256:'+'b'*64)
    def backup(*, connection, store, root, label):
        if label == fail_phase:
            raise RuntimeError('injected backup failure')
        directory = root/label
        manifest = export_v2_backup(connection, directory, database='fixture')
        restored = root/f'{label}.duckdb'
        restore_v2_backup(directory, restored)
        return manifest, dict(byte_size=1,index_sha256='synthetic',object_count=80), restored
    monkeypatch.setattr(release,'_backup_round_trip',backup)
    run = lambda: release.run_wi064_release(release.WI064ReleaseConfig('project','bucket'),
        connection_factory=lambda: duckdb.connect(str(path)), store_factory=lambda _: object())
    if fail_phase:
        with pytest.raises(RuntimeError,match='injected'):
            run()
    else:
        result=run()
        assert result['status']=='verified' and result['applied_migrations']==['0022']
        assert run()['applied_migrations']==[]
    with duckdb.connect(str(path)) as check:
        assert release._data_fingerprints(check)==before
        assert ('0022' in MigrationRunner(check).applied()) == (fail_phase != 'pre')
        # Post failure retains migration history but restores the prior view definition.
        if fail_phase=='post':
            view=check.execute("SELECT sql FROM duckdb_views() WHERE schema_name='silver' AND view_name='trade_events_current'").fetchone()[0]
            assert 'trade_event_identity_aliases' not in view


@pytest.mark.parametrize('failure', [None, 'migration', 'second-image'])
def test_release_deploys_only_migration_and_existing_job_images(monkeypatch, failure):
    commands=[]
    args=argparse.Namespace(region='asia-northeast3',dry_run=False,secret_mode='secret-manager',job=None)
    monkeypatch.setenv('GITHUB_SHA','a'*40)
    monkeypatch.setattr(deploy_cloud_run,'_build_release_image',lambda *_a,**_k:'image@sha256:'+'b'*64)
    monkeypatch.setattr(deploy_cloud_run,'_split_runtime_env',lambda **_k: ({'KIS_DB_MODE':'motherduck'},{}))
    monkeypatch.setattr(deploy_cloud_run,'_run_capture',lambda cmd,**_k:SimpleNamespace(returncode=0,stdout=(
        'apiVersion: run.googleapis.com/v1\nkind: Job\n' if '--format=export' in cmd else json.dumps({'image':'prior@sha256:'+'c'*64}))))
    def run(command, **_kwargs):
        commands.append(command)
        if failure=='migration' and command[2:4]==['jobs','execute']:
            return 1
        if failure=='second-image' and command[2:5]==['jobs','update','kis-portfolio-trade-incremental-overseas']:
            return 1
        return 0
    monkeypatch.setattr(deploy_cloud_run,'_run',run)
    result=deploy_cloud_run._deploy_wi064(args,env={'KIS_DB_MODE':'motherduck',
        'MOTHERDUCK_DATABASE':'kis_portfolio','KIS_GCS_BUCKET':'private'},project='project')
    assert result == (0 if failure is None else 1)
    assert not any('services' in c or 'scheduler' in c or 'iam-policy-binding' in c for c in commands)
    if failure=='migration':
        assert not any(c[2:4]==['jobs','update'] for c in commands)
    elif failure=='second-image':
        assert sum(c[2:4]==['jobs','replace'] for c in commands)==2
    else:
        assert sum(c[2:4]==['jobs','update'] for c in commands)==2
    workflow=Path('.github/workflows/deploy-cloud-run.yml').read_text()
    assert "github.event.inputs.target == 'wi064'" in workflow
    assert 'scripts/deploy_cloud_run.py wi064' in workflow
