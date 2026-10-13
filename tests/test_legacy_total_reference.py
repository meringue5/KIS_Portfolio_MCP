from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.remote_v2_warehouse import WarehouseReadQueryPort
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.legacy_total_reference import import_candidate, validate_candidate
from kis_portfolio.services.remote_read_surface import PerformanceHistoryRequest, RemoteReadError
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


def candidate():
    rows=[]
    for i in range(27):
        day=date(2026,4,19)+timedelta(days=i)
        kind='recorded_reference' if i<14 else 'estimated_reference' if i<25 else 'unavailable_total'
        rows.append(dict(date=day.isoformat(),recorded_total_krw='100',candidate_total_krw=None if i>=25 else '100',
            missing_foreign_valuation_added_krw='0',status=kind,canonical=False,snapshot_at_original=day.isoformat()+'T10:00:00',
            input_sha256=hashlib.sha256(str(i).encode()).hexdigest(),account_coverage_count=5,
            foreign_position_count=0 if i>=25 else 1,missing_krw_position_count=0,
            assumptions=[] if i<14 else ['missing_overseas_cash_assumed_zero_owner_2026-10-13'],
            flags=['legacy_noncanonical'],fx=None))
    # A same-day external FX estimate can have no missing-cash or stale-rate assumption.
    rows[14].update(candidate_total_krw='1400', missing_foreign_valuation_added_krw='1300',
        assumptions=[], missing_krw_position_count=1,
        fx=dict(provider='FRED / Federal Reserve Board',series_id='DEXKOUS',
                rate_type='new_york_noon_buying',base_currency='USD',quote_currency='KRW',rate='1300',
                requested_date=rows[14]['date'],rate_date=rows[14]['date'],age_days=0,
                fetched_at='2026-10-13T10:00:00+00:00',source_file_sha256='e'*64))
    return dict(work_item='WI-068',canonical=False,created_at='2026-10-13T11:44:32+00:00',rows=rows)


def write_candidate(tmp_path, data=None):
    payload=json.dumps(data or candidate()).encode()
    path=tmp_path/'candidate.json';path.write_bytes(payload)
    return path,hashlib.sha256(payload).hexdigest()


@pytest.fixture
def connection():
    con=duckdb.connect(':memory:');MigrationRunner(con).apply()
    yield con
    con.close()


def test_append_only_replay_conflict_and_restore(connection,tmp_path):
    path,digest=write_candidate(tmp_path)
    assert import_candidate(connection,path,expected_sha256=digest)['inserted']==27
    assert import_candidate(connection,path,expected_sha256=digest)['inserted']==0
    backup=tmp_path/'backup';manifest=export_v2_backup(connection,backup,database='fixture')
    assert 'silver.portfolio_legacy_total_reference' in manifest['tables']
    target=tmp_path/'restored.duckdb';restore_v2_backup(backup,target)
    with duckdb.connect(str(target)) as restored:
        assert import_candidate(restored,path,expected_sha256=digest)['inserted']==0
    connection.execute("UPDATE silver.portfolio_legacy_total_reference SET recorded_total_krw=101,reference_total_krw=101 WHERE observation_date='2026-04-19'")
    with pytest.raises(ValueError,match='existing_version_conflict'):
        import_candidate(connection,path,expected_sha256=digest)
    assert connection.execute('SELECT count(*) FROM silver.portfolio_legacy_total_reference').fetchone()[0]==27


def test_default_optin_partial_error_and_native_precedence(connection,tmp_path):
    path,digest=write_candidate(tmp_path);import_candidate(connection,path,expected_sha256=digest)
    port=WarehouseReadQueryPort(connection)
    params=dict(start_date=date(2026,4,19),end_date=date(2026,5,15))
    default=port._get_performance_history(PerformanceHistoryRequest(**params))
    assert 'reference_history' not in default['data']
    result=port._get_performance_history(PerformanceHistoryRequest(**params,include_legacy_reference=True))
    assert len(result['data']['reference_history'])==25
    assert result['quality']['status']=='partial'
    assert sum(r['reason']=='legacy_total_unavailable' for r in result['missing_coverage'])==2
    assert all(r['canonical'] is False for r in result['data']['reference_history'])
    assert 'source_object_hash' not in json.dumps(result,default=str)
    with pytest.raises(RemoteReadError,match='legacy_reference_total_only'):
        port._get_performance_history(PerformanceHistoryRequest(**params,include_legacy_reference=True,account_alias='alpha'))
    with pytest.raises(RemoteReadError,match='legacy_reference_range_exceeded'):
        port._get_performance_history(PerformanceHistoryRequest(start_date=date(2020,1,1),end_date=date(2026,1,1),include_legacy_reference=True))
    connection.execute("INSERT INTO silver.accounts VALUES ('acct','alpha','brokerage','KRW',current_timestamp,NULL,'{}')")
    connection.executemany("""INSERT INTO gold.portfolio_daily_state(evaluation_date,evaluation_slot,account_id,instrument_id,
        aggregate_level,value_krw,as_of,input_watermarks,quality_status,lineage_hash)
        VALUES (? ,?,'acct','cash|KRW','cash',200,current_timestamp,'{}','pass','fixture')""",
        [('2026-04-19','kr-1600'),('2026-04-20','v1-latest')])
    result=port._get_performance_history(PerformanceHistoryRequest(**params,include_legacy_reference=True))
    assert len(result['data']['reference_history'])==24
    assert result['data']['history'][0]['total_value_krw']==200
    assert result['data']['history'][1]['total_value_krw'] is None
    assert result['data']['history'][1]['quality_status']=='legacy_unassessed'
    assert port._get_performance_history(PerformanceHistoryRequest(**params))['data']['history']==result['data']['history']


def test_pinned_input_and_invalid_source_fact(tmp_path):
    path,digest=write_candidate(tmp_path)
    with pytest.raises(ValueError,match='input_hash_mismatch'):
        validate_candidate(path.read_bytes())
    data=candidate();data['rows'][0]['candidate_total_krw']='101'
    path,digest=write_candidate(tmp_path,data)
    with pytest.raises(ValueError,match='reconciliation'):
        validate_candidate(path.read_bytes(),expected_sha256=digest)
    data=candidate();data['rows'][25]['candidate_total_krw']='0'
    path,digest=write_candidate(tmp_path,data)
    with pytest.raises(ValueError,match='unavailable_total'):
        validate_candidate(path.read_bytes(),expected_sha256=digest)


def test_protected_release_backup_restore_and_replay(monkeypatch):
    from kis_portfolio.services import wi068_release
    from kis_portfolio.services import legacy_total_reference
    from kis_portfolio.services.wi068_release import WI068ReleaseConfig, run_wi068_release
    from kis_portfolio.ports.object_store import StoredObject

    payload=json.dumps(candidate()).encode();digest=hashlib.sha256(payload).hexdigest()
    class Store:
        def __init__(self): self.objects={}
        def _object_name(self,digest,dataset_id,partition): return f'{dataset_id}/{partition}/{digest}'
        def put_bytes(self,payload,*,dataset_id,partition,media_type):
            sha=hashlib.sha256(payload).hexdigest();uri='gs://private/'+self._object_name(sha,dataset_id,partition)
            self.objects[uri]=payload
            return StoredObject(uri,sha,len(payload),media_type,True)
        def put_file(self,path,**kwargs): return self.put_bytes(path.read_bytes(),**kwargs)
        def download(self,uri,destination,*,expected_sha256=None):
            value=self.objects[uri];assert hashlib.sha256(value).hexdigest()==expected_sha256
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(value);return destination
    store=Store();store.put_bytes(payload,dataset_id='backup.wi068-input',partition='approved-v1',media_type='application/json')
    monkeypatch.setattr(wi068_release,'APPROVED_SHA256',digest)
    original_validate=legacy_total_reference.validate_candidate
    monkeypatch.setattr(legacy_total_reference,'validate_candidate',lambda payload,**kwargs: original_validate(payload,expected_sha256=digest))
    monkeypatch.setattr(wi068_release,'get_db_mode',lambda:'motherduck')
    monkeypatch.setenv('KIS_RELEASE_GIT_SHA','b'*40);monkeypatch.setenv('KIS_RELEASE_IMAGE_DIGEST','sha256:'+'a'*64)
    con=duckdb.connect(':memory:');MigrationRunner(con).apply(through='0020')
    con.execute("INSERT INTO silver.accounts VALUES ('acct','alpha','brokerage','KRW',current_timestamp,NULL,'{}')")
    con.executemany("""INSERT INTO gold.portfolio_daily_state(evaluation_date,evaluation_slot,account_id,instrument_id,
        aggregate_level,value_krw,as_of,input_watermarks,quality_status,lineage_hash)
        VALUES (? ,?,'acct','cash|KRW','cash',200,current_timestamp,'{}','pass','fixture')""",
        [('2026-04-19','v1-latest'),('2026-10-13','kr-1600')])
    options=dict(connection_factory=lambda:con,store_factory=lambda _:store)
    first=run_wi068_release(WI068ReleaseConfig(project='fixture',bucket='private'),**options)
    second=run_wi068_release(WI068ReleaseConfig(project='fixture',bucket='private'),**options)
    assert first['applied_migrations']==['0021'] and second['applied_migrations']==[]
    assert first['import']['inserted']==27 and second['import']['inserted']==0
    assert first['state_before']==first['state_after']
    assert first['summary_evidence']['legacy_quarantined_groups']==1
    assert first['fresh_restore_verified'] is True
    assert first['source_calls']==first['original_rows_mutated']==first['deletions']==0
    assert 'gs://' not in json.dumps(first)
    con.close()


@pytest.mark.parametrize('rate_day,age', [('2026-05-04',-1), ('2026-04-28',5)])
def test_future_or_stale_fx_is_rejected(tmp_path,rate_day,age):
    data=candidate();data['rows'][14]['fx'].update(rate_date=rate_day,age_days=age)
    path,digest=write_candidate(tmp_path,data)
    with pytest.raises(ValueError,match='fx_contract'):
        validate_candidate(path.read_bytes(),expected_sha256=digest)
