"""WI-063 independent interval oracles; successful rows never establish absence."""
from datetime import date

import duckdb
import pytest

from kis_portfolio.adapters.outbound.remote_v2_warehouse import WarehouseReadQueryPort
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.remote_read_surface import TradeLedgerRequest
from kis_portfolio.services.trade_incremental import run_trade_incremental
from test_trade_incremental import _account, FETCHED
from kis_portfolio.services.trade_cash_backfill_pipeline import BackfillSourcePage, FetchedBackfillPartition


def empty(partition, gate):
    gate.reserve(partition.key)
    key = 'output' if partition.source_operation == 'overseas-order-history' else 'output1'
    return FetchedBackfillPartition((BackfillSourcePage({key: []}, FETCHED),), True)


@pytest.fixture
def con():
    c = duckdb.connect(':memory:')
    MigrationRunner(c).apply()
    yield c
    c.close()


def collect(c, start='2026-09-24', end='2026-09-26', label='ria', scope='domestic'):
    return run_trade_incremental(c, [_account(label)], start_date=date.fromisoformat(start),
                                 end_date=date.fromisoformat(end), scope=scope, overseas_account_labels=('brokerage',) if label == 'brokerage' else (), fetch_partition=empty)


def read(c, start, end, account='ria'):
    return WarehouseReadQueryPort(c)._get_trade_ledger(TradeLedgerRequest(
        start_date=date.fromisoformat(start), end_date=date.fromisoformat(end), account_alias=account))


@pytest.mark.parametrize('start,end,expected', [
    ('2020-01-01', '2020-01-02', 'partial'),
    ('2026-09-23', '2026-09-24', 'partial'),
    ('2026-09-24', '2026-09-24', 'pass'),
    ('2026-09-24', '2026-09-26', 'pass'),
    ('2026-09-26', '2026-09-27', 'partial'),
    ('2026-10-17', '2026-10-18', 'partial'),
])
def test_lower_boundary_empty_and_upper_boundary(con, start, end, expected):
    collect(con)
    result = read(con, start, end)
    assert result['quality']['status'] == expected
    assert bool(result['missing_coverage']) == (expected != 'pass')
    assert result['data']['events'] == []


def test_watermark_alone_never_proves_interval(con):
    con.execute("insert into control.watermarks values ('pipeline.trade-incremental-v2', 'account:ria', 'trade_query_coverage_v1', '2026-10-16', 'missing', current_timestamp)")
    assert read(con, '2020-01-01', '2020-01-02')['quality']['status'] == 'partial'


def test_internal_gap_union_and_recollection(con):
    collect(con, end='2026-09-24')
    # Legacy or independently recovered islands can exist even when resume guards are intact.
    con.execute('delete from control.watermarks')
    collect(con, start='2026-09-26')
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'partial'
    assert read(con, '2026-09-26', '2026-09-26')['quality']['status'] == 'pass'
    collect(con, start='2026-09-25', end='2026-09-25')
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'pass'
    # Recollection is a no-op and cannot move resume upper bounds backwards.
    collect(con, start='2026-09-24', end='2026-09-24')
    assert con.execute("select distinct watermark_value from control.watermarks where watermark_type='trade_query_coverage_v1'").fetchall() == [('2026-09-26',)]


@pytest.mark.parametrize('damage', ['run_failed', 'publish_missing', 'publish_failed', 'quality_missing',
                                    'quality_failed', 'pagination_failed', 'wrong_partition', 'wrong_product',
                                    'wrong_source', 'missing_lineage', 'malformed_reconciliation', 'interval_mismatch'])
def test_evidence_must_be_complete_and_exact(con, damage):
    collect(con)
    sql = {
        'run_failed': "update control.pipeline_runs set status='failed'",
        'publish_missing': "delete from control.pipeline_stage_runs where stage_name='publish'",
        'publish_failed': "update control.pipeline_stage_runs set status='failed' where stage_name='publish'",
        'quality_missing': "delete from control.quality_results where rule_id='pagination-complete'",
        'quality_failed': "update control.quality_results set status='failed' where rule_id='pagination-complete'",
        'pagination_failed': "update control.pipeline_stage_runs set evidence=json_merge_patch(evidence,'{\"reconciliation\":{\"pagination_complete\":false}}') where stage_name='collect-land-normalize'",
        'wrong_partition': "update control.pipeline_runs set partition_key=replace(partition_key,'|ria|','|isa|')",
        'wrong_product': "update control.pipeline_runs set partition_key=replace(partition_key,'|01|','|29|')",
        'wrong_source': "update control.pipeline_runs set pipeline_id='unapproved-producer'",
        'missing_lineage': "delete from control.lineage_edges",
        'malformed_reconciliation': "update control.pipeline_stage_runs set evidence=json_merge_patch(evidence,'{\"reconciliation\":{\"classified_rows\":\"bad\"}}') where stage_name='collect-land-normalize'",
        'interval_mismatch': "update control.pipeline_stage_runs set evidence=json_merge_patch(evidence,'{\"coverage_interval\":{\"start_date\":\"2020-01-01\"}}') where stage_name='publish'",
    }[damage]
    con.execute(sql)
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'partial'


def test_account_market_scope_intersection(con):
    collect(con, label='brokerage')
    assert read(con, '2026-09-24', '2026-09-26', 'brokerage')['quality']['status'] == 'partial'
    collect(con, label='brokerage', scope='overseas')
    assert read(con, '2026-09-24', '2026-09-26', 'brokerage')['quality']['status'] == 'pass'
    assert read(con, '2026-09-24', '2026-09-26', 'ria')['quality']['status'] == 'partial'
    assert read(con, '2026-09-24', '2026-09-26', None)['quality']['status'] == 'partial'
    # Candidate overseas transaction history cannot replace the execution source.
    con.execute("delete from control.pipeline_stage_runs where stage_name='publish' and run_id in (select run_id from control.pipeline_runs where partition_key like '%overseas-order-history%')")
    assert read(con, '2026-09-24', '2026-09-26', 'brokerage')['quality']['status'] == 'partial'


def test_published_source_window_populated_and_covered_empty(con):
    collect(con)
    con.execute("insert into silver.accounts values ('a','ria','REAL','KRW',current_timestamp,NULL,'{}')")
    con.execute("""insert into silver.trade_event_revisions values (
        'r','s','a','KRX','01','v1|KRX|005930','order','2026-09-24T07:00:00Z',
        '1',1,'buy',1,100,'KRW',current_timestamp,'observation','source_event','pass','{}')""")
    assert len(read(con, '2026-09-24', '2026-09-24')['data']['events']) == 1
    assert read(con, '2026-09-24', '2026-09-24')['quality']['status'] == 'pass'
    assert read(con, '2020-01-01', '2026-09-24')['quality']['status'] == 'partial'
    assert read(con, '2026-09-25', '2026-09-26')['data']['query']['result_status'] == 'no_events_in_query_window'


def test_global_scope_requires_all_five_accounts_and_both_overseas_sources(con):
    # A historical IRP old-route partition is callable; recent IRP is a named gap.
    # Use the approved backfill runner for the old-route source, not a fake IRP product.
    from kis_portfolio.services.trade_cash_backfill import (BackfillAccountScope,
        BackfillBudgetPolicy, apply_call_budget, plan_trade_cash_backfill)
    from kis_portfolio.services.trade_cash_backfill_runtime import execute_trade_cash_backfill
    from kis_portfolio.services.trade_cash_backfill_pipeline import build_trade_cash_partition_handler
    scopes = [BackfillAccountScope(label, product, 'REAL', ('NAS',) if label == 'brokerage' else ())
              for label, product in [('ria','01'),('isa','01'),('brokerage','01'),('irp','29'),('pension','22')]]
    plan = apply_call_budget(plan_trade_cash_backfill(scopes, start_date=date(2026,1,1),
        end_date=date(2026,1,2), as_of_date=date(2026,9,24)), policy=BackfillBudgetPolicy())
    execute_trade_cash_backfill(con, plan, build_trade_cash_partition_handler(con, empty))
    assert read(con, '2026-01-01', '2026-01-02', None)['quality']['status'] == 'pass'
    con.execute("update control.pipeline_runs set status='failed' where partition_key like '%|isa|%'")
    assert read(con, '2026-01-01', '2026-01-02', None)['quality']['status'] == 'partial'
    assert read(con, '2026-01-01', '2026-01-02', 'ria')['quality']['status'] == 'pass'


def test_new_publish_interval_matches_source_partition(con):
    import json
    collect(con)
    documents = con.execute("select evidence from control.pipeline_stage_runs where stage_name='publish'").fetchall()
    assert documents
    for (raw,) in documents:
        interval = json.loads(raw)['coverage_interval']
        assert interval == dict(version=1,account_alias='ria',market='KRX',source_operation='domestic-order-history',
                                source_route='recent',start_date='2026-09-24',end_date='2026-09-26')


def test_failed_extension_keeps_previously_proven_interval(con):
    from kis_portfolio.platform.pipeline import PipelineExecutionError
    collect(con)
    before = con.execute("select partition_key,watermark_value,run_id from control.watermarks order by 1").fetchall()
    def incomplete(partition, gate):
        gate.reserve(partition.key)
        return FetchedBackfillPartition((BackfillSourcePage({'output1': []}, FETCHED),), False)
    with pytest.raises(PipelineExecutionError, match='pagination incomplete'):
        run_trade_incremental(con, [_account('ria')], start_date=date(2026,9,27), end_date=date(2026,9,27),
                              scope='domestic', overseas_account_labels=(), fetch_partition=incomplete)
    assert con.execute("select partition_key,watermark_value,run_id from control.watermarks order by 1").fetchall() == before
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'pass'
    assert read(con, '2026-09-24', '2026-09-27')['quality']['status'] == 'partial'


def test_historical_publish_key_requires_same_proof_chain(con):
    collect(con)
    con.execute("update control.pipeline_stage_runs set evidence=json_merge_patch(evidence,'{\"coverage_interval\":null}') where stage_name='publish'")
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'pass'
    con.execute("delete from control.quality_results")
    assert read(con, '2026-09-24', '2026-09-26')['quality']['status'] == 'partial'
