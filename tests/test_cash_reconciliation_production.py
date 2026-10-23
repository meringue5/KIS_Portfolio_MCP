from dataclasses import replace
from datetime import UTC,datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from kis_portfolio.adapters.outbound.cash_reconciliation_warehouse import CashReconciliationRepository,TABLE
from kis_portfolio.adapters.outbound.remote_v2_warehouse import WarehouseReadQueryPort
from kis_portfolio.services.cash_reconciliation_runtime import after_success
from kis_portfolio.services import cash_reconciliation_runtime as runtime
from kis_portfolio.services.remote_read_surface import RemoteReadApplication,ReadActor,RemoteReadError
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import ManagedPipelineRunner,PipelineDefinition,PipelineStage,StageResult
from kis_portfolio.services.v2_recovery import export_v2_backup,restore_v2_backup
from test_cash_reconciliation import inputs,reconcile,CUTOFF


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def source_run(con):
    definition=PipelineDefinition('pipeline.owned-portfolio-core-v2','fixture',
        (PipelineStage('publish',lambda _:StageResult()),),0)
    return ManagedPipelineRunner(con).run(definition,logical_date=datetime.now(UTC).date(),slot='kr-1000').run_id


def test_production_bootstrap_persistence_replay_and_failure_isolation(monkeypatch):
    con=duckdb.connect(':memory:');MigrationRunner(con).apply();run_id=source_run(con)
    monkeypatch.setenv('KIS_CASH_RECONCILIATION_ENABLED','true')
    first=after_success(con,run_id=run_id)
    assert first['status']=='partial' and first['broker_calls']==first['monetary_writes']==0
    assert con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]==6
    second=after_success(con,run_id=run_id)
    assert second['reused'] and con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]==6
    assert con.execute("SELECT count(*) FROM silver.cash_flow_events").fetchone()[0]==0
    # A separately failed companion cannot change source core completion or leak raw exception text.
    monkeypatch.setattr(runtime,'evaluate_stored_cash',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('private-secret')))
    con.execute("DELETE FROM control.pipeline_runs WHERE pipeline_id='pipeline.cash-balance-reconciliation-v1'")
    con.execute("DELETE FROM control.pipeline_stage_runs WHERE run_id=?",[first['pipeline_run_id']])
    failure=after_success(con,run_id=run_id)
    assert failure['status']=='unavailable' and 'private-secret' not in json.dumps(failure)
    assert con.execute('SELECT status FROM control.pipeline_runs WHERE run_id=?',[run_id]).fetchone()[0]=='succeeded'
    assert 'private-secret' not in str(con.execute('SELECT error_message FROM control.pipeline_stage_runs').fetchall())
    monkeypatch.setenv('KIS_CASH_RECONCILIATION_ENABLED','false')
    assert after_success(None,run_id='irrelevant')=={'status':'disabled'}
    con.close()


def test_deferred_revision_pit_numeric_guard_and_backup_restore(tmp_path):
    con=duckdb.connect(':memory:');MigrationRunner(con).apply()
    at=CUTOFF+timedelta(hours=2)
    repo=CashReconciliationRepository(con,clock=lambda:at)
    partial=reconcile(replace(inputs(),coverage=()))
    assert repo.append(partial,'synthetic-run') and not repo.append(partial,'synthetic-run')
    later=replace(partial,input_hash='different-visible-input',knowledge_cutoff=at)
    assert repo.append(later,'synthetic-run')
    assert repo.read(cutoff=at)['data']['results'][0]['revision']==2
    # Recording clock prevents a late import from appearing in an earlier historical response.
    assert repo.read(cutoff=CUTOFF)['data']['results']==[]
    with pytest.raises(ValueError,match='numeric_reconciliation_not_approved'):
        repo.append(reconcile(inputs()),'synthetic-positive')
    with pytest.raises(duckdb.ConstraintException):
        con.execute(f"UPDATE {TABLE} SET delta=1")
    backup=tmp_path/'backup';export_v2_backup(con,backup,database='fixture')
    restore_v2_backup(backup,tmp_path/'restored.duckdb')
    with duckdb.connect(str(tmp_path/'restored.duckdb'),read_only=True) as check:
        assert check.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]==2
    con.close()


def test_concurrent_append_has_one_immutable_input(tmp_path):
    path=tmp_path/'concurrent.duckdb'
    with duckdb.connect(str(path)) as con:MigrationRunner(con).apply()
    result=reconcile(replace(inputs(),coverage=()))
    def worker(_):
        with duckdb.connect(str(path)) as con:return CashReconciliationRepository(con).append(result,'fixture')
    with ThreadPoolExecutor(2) as pool:assert sum(pool.map(worker,range(2)))==1
    with duckdb.connect(str(path)) as con:assert con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]==1


@pytest.mark.anyio
async def test_existing_oauth_read_shape_positive_partial_error_and_paging(monkeypatch):
    monkeypatch.setenv('KIS_CASH_RECONCILIATION_ENABLED','true')
    con=duckdb.connect(':memory:');MigrationRunner(con).apply();after_success(con,run_id=source_run(con))
    app=RemoteReadApplication(WarehouseReadQueryPort(con),expected_resource='https://fixture.test/mcp')
    actor=ReadActor('owner','client',frozenset({'mcp:read'}),'https://fixture.test/mcp','test-request')
    request=dict(dataset_id='dataset.cash-balance-reconciliation',limit=2)
    first=await app.execute('get-data-quality',request,actor)
    assert first['quality']['status']=='partial' and len(first['data']['results'])==2
    assert first['data']['next_cursor']
    second=await app.execute('get-data-quality',{**request,'cursor':first['data']['next_cursor']},actor)
    assert len(second['data']['results'])==2
    assert {r['account_alias'] for r in first['data']['results']}!={r['account_alias'] for r in second['data']['results']}
    assert all(r['delta'] is None and not r['performance_eligible'] for r in first['data']['results'])
    empty=await app.execute('get-data-quality',{**request,'run_id':'absent-run'},actor)
    assert empty['quality']['status']=='partial' and empty['data']['results']==[]
    with pytest.raises(RemoteReadError,match='invalid_reconciliation_bounds'):
        await app.execute('get-data-quality',{**request,'limit':101},actor)
    with pytest.raises(RemoteReadError,match='invalid_reconciliation_cursor'):
        await app.execute('get-data-quality',{**request,'cursor':'not-a-valid-cursor'},actor)
    with pytest.raises(RemoteReadError,match='insufficient_scope'):
        await app.execute('get-data-quality',request,replace(actor,scopes=frozenset()))
    con.close()


def test_deploy_target_updates_only_reviewed_jobs_and_reuses_same_digest(monkeypatch):
    path=Path(__file__).parents[1]/'scripts/deploy_cloud_run.py'
    spec=importlib.util.spec_from_file_location('wi071_deployer',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    commands=[];image='image@sha256:'+'a'*64
    monkeypatch.setattr(m,'_build_release_image',lambda *a,**k:image)
    monkeypatch.setattr(m,'_run',lambda cmd,**k:commands.append(cmd) or 0)
    remote=[];monkeypatch.setattr(m,'_deploy_wi065',lambda *a,**k:remote.append(k['release_image']) or 0)
    args=argparse.Namespace(target='wi071',region='asia-northeast3',job=None,secret_mode='env-file',dry_run=True)
    env=dict(KIS_DB_MODE='motherduck',MOTHERDUCK_DATABASE='fixture',MOTHERDUCK_TOKEN='synthetic',
        KIS_GCS_BUCKET='fixture',KIS_AUTH_BASE_URL='https://auth.test',KIS_RESOURCE_SERVER_URL='https://remote.test/mcp')
    assert m._deploy_wi071(args,env=env,project='fixture')==0 and remote==[image]
    updates=[c for c in commands if c[:4]==['gcloud','run','jobs','update']]
    assert len(updates)==3 and all(c[c.index('--image')+1]==image for c in updates)
    assert all('KIS_CASH_RECONCILIATION_ENABLED=true' in c for c in updates)
    executes=[c for c in commands if c[:4]==['gcloud','run','jobs','execute']]
    assert len(executes)==1 and executes[0][4]=='kis-portfolio-wi071'
    assert not any('scheduler' in c for c in commands)

@pytest.mark.parametrize('fail_phase',[None,'pre','post'])
def test_protected_transition_preserves_sources_and_verifies_restore(tmp_path,monkeypatch,fail_phase):
    from kis_portfolio.services import wi071_release as release
    path=tmp_path/'source.duckdb'
    with duckdb.connect(str(path)) as con:
        MigrationRunner(con).apply(through='0022');source_run(con)
        before=release.preserved_fingerprints(con)
    monkeypatch.setenv('KIS_DB_MODE','motherduck')
    monkeypatch.setenv('KIS_CASH_RECONCILIATION_ENABLED','true')
    monkeypatch.setenv('KIS_RELEASE_GIT_SHA','a'*40)
    monkeypatch.setenv('KIS_RELEASE_IMAGE_DIGEST','sha256:'+'b'*64)
    def backup(*,connection,store,root,label):
        if fail_phase==label:raise RuntimeError('injected_private_backup_failure')
        manifest=export_v2_backup(connection,root/label,database='fixture')
        restore_v2_backup(root/label,root/f'{label}.duckdb')
        return manifest,dict(byte_size=1,index_sha256='synthetic',object_count=80),root/f'{label}.duckdb'
    monkeypatch.setattr(release,'_backup_round_trip',backup)
    run=lambda:release.run_wi071_release(release.WI071ReleaseConfig('project','bucket'),
        connection_factory=lambda:duckdb.connect(str(path)),store_factory=lambda _:object())
    if fail_phase:
        with pytest.raises(RuntimeError,match='injected_private_backup_failure'):run()
    else:
        result=run();assert result['applied_migrations']==['0023'] and result['diagnostic_rows']==6
        assert run()['applied_migrations']==[]
    with duckdb.connect(str(path)) as con:
        assert release.preserved_fingerprints(con)==before
        assert ('0023' in MigrationRunner(con).applied())==(fail_phase!='pre')
