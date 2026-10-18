"""Whole-interval trade coverage from retained source/quality/publish evidence.

Upper watermarks are resume hints, never proof that preceding dates were queried.
No source I/O or warehouse mutation occurs here.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Iterable

import duckdb

from kis_portfolio.account_registry import ACCOUNT_SPECS


Interval = tuple[date, date]


# Approved held-account collection scope (pipeline.trade-incremental-v2).
PRODUCT_CODES = {label: '29' if label == 'irp' else '22' if label == 'pension' else '01'
                 for label, _, _ in ACCOUNT_SPECS}
DAY = timedelta(days=1)


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    merged = []
    for start, end in sorted(intervals):
        if merged and (start <= merged[-1][1] or (start - merged[-1][1]).days == 1):
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def interval_gaps(intervals: list[Interval], start: date, end: date) -> list[Interval]:
    gaps = []
    cursor = start
    for lower, upper in intervals:
        if upper < cursor:
            continue
        if lower > end:
            break
        if lower > cursor:
            gaps.append((cursor, lower - DAY))
        if upper >= end:
            return gaps
        cursor = max(cursor, upper + DAY)
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


def _document(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def published_trade_intervals(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Accept the existing v1 source key only with its full independent proof chain.

    Empty source responses have no Bronze rows. Their complete pagination and
    row reconciliation are established by stage and quality evidence, not by
    synthesizing a Bronze observation. Legacy keys remain usable without DDL.
    """
    rows = connection.execute("""
        SELECT r.run_id,r.partition_key,r.logical_date,c.evidence,p.evidence,r.finished_at
        FROM control.pipeline_runs r
        JOIN control.pipeline_definitions d ON d.pipeline_id=r.pipeline_id
          AND d.version=r.pipeline_version AND d.contract_status='approved'
        JOIN control.pipeline_stage_runs c ON c.run_id=r.run_id
          AND c.stage_name='collect-land-normalize' AND c.status='succeeded'
        JOIN control.pipeline_stage_runs q ON q.run_id=r.run_id
          AND q.stage_name='quality' AND q.status='succeeded'
        JOIN control.pipeline_stage_runs p ON p.run_id=r.run_id
          AND p.stage_name='publish' AND p.status='succeeded'
        WHERE r.pipeline_id IN ('pipeline.trade-cash-backfill-v2','pipeline.trade-incremental-v2')
          AND r.status='succeeded' AND r.finished_at IS NOT NULL AND c.source_calls>0
          AND (SELECT count(DISTINCT rule_id) FROM control.quality_results z
               WHERE z.run_id=r.run_id AND z.dataset_id='dataset.trade-event'
                 AND z.status='pass' AND z.rule_id IN ('source-row-reconciliation','pagination-complete'))=2
          AND NOT EXISTS (SELECT 1 FROM control.quality_results z
               WHERE z.run_id=r.run_id AND z.dataset_id='dataset.trade-event' AND z.status<>'pass')
          AND EXISTS (SELECT 1 FROM control.lineage_edges l WHERE l.run_id=r.run_id
               AND l.output_ref='dataset.trade-event' AND l.transform_id='trade-cash-backfill-normalize'
               AND l.input_ref='source.kis-open-api:' || split_part(r.partition_key,'|',2))
        ORDER BY r.partition_key,r.finished_at
    """).fetchall()
    result = []
    for run_id, key, logical_date, collected, published, finished in rows:
        parts = key.split('|')
        if len(parts) != 9 or parts[0] != '1.0.0':
            continue
        _, operation, account, product, account_type, market, route, lower, upper = parts
        if product != PRODUCT_CODES.get(account) or account_type != 'REAL':
            continue
        if market == 'KRX':
            valid_source = operation == 'domestic-order-history' and route in {'old', 'recent'}
        else:
            valid_source = market == 'NAS' and (operation, route) in {
                ('overseas-order-history', 'order-aggregate'),
                ('overseas-transaction-history', 'period-transaction')}
        if not valid_source:
            continue
        c, p = _document(collected), _document(published)
        reconciliation = c.get('reconciliation', {})
        if not isinstance(reconciliation, dict):
            continue
        counts = [reconciliation.get(name) for name in
                  ('page_count', 'raw_rows', 'classified_rows', 'deferred_rows')]
        if any(type(value) is not int or value < 0 for value in counts) or counts[0] == 0:
            continue
        expected_interval = dict(version=1, account_alias=account, market=market,
                                 source_operation=operation, source_route=route,
                                 start_date=lower, end_date=upper)
        if 'coverage_interval' in p and p['coverage_interval'] != expected_interval:
            continue
        if (c.get('partition_key') != key or p.get('partition_key') != key
                or not c.get('plan_hash') or not c.get('budget_hash')
                or reconciliation.get('status') != 'pass'
                or reconciliation.get('source_operation') != operation
                or reconciliation.get('pagination_complete') is not True
                or reconciliation.get('pagination_warning')
                or not reconciliation.get('page_count')
                or reconciliation.get('raw_rows') is None
                or reconciliation.get('raw_rows') != reconciliation.get('classified_rows', 0) + reconciliation.get('deferred_rows', 0)
                or p.get('watermark_type') != 'source_end_date_v1'):
            continue
        try:
            start, end = date.fromisoformat(lower), date.fromisoformat(upper)
            published_end = date.fromisoformat(p.get('watermark_value', ''))
        except (ValueError, TypeError):
            continue
        if start > end or end > logical_date or published_end < end:
            continue
        result.append(dict(account=account, market=market, operation=operation,
                           start=start, end=end, run_id=run_id, finished_at=finished))
    return result


def trade_query_coverage(
    connection: duckdb.DuckDBPyConnection, *, account_alias: str | None,
    start_date: date, end_date: date,
) -> dict[str, Any]:
    evidence = published_trade_intervals(connection)
    accounts = [account_alias] if account_alias else list(PRODUCT_CODES)
    partitions = []
    missing = []
    ends = []
    updated = []
    for account in accounts:
        for market in (('KRX', 'NAS') if account == 'brokerage' else ('KRX',)):
            operations = (('domestic-order-history',) if market == 'KRX' else
                          ('overseas-order-history', 'overseas-transaction-history'))
            source_intervals = []
            for operation in operations:
                matching = [r for r in evidence if (r['account'], r['market'], r['operation']) ==
                            (account, market, operation)]
                source_intervals.append(merge_intervals([(r['start'], r['end']) for r in matching]))
                updated.extend(r['finished_at'] for r in matching)
            # Intersection of all required source operations, then union adjacent dates.
            intervals = source_intervals[0]
            for other in source_intervals[1:]:
                intervals = merge_intervals([(max(a, c), min(b, d)) for a, b in intervals
                                             for c, d in other if max(a, c) <= min(b, d)])
            gaps = interval_gaps(intervals, start_date, end_date)
            through = intervals[-1][1] if intervals else None
            ends.append(through)
            partitions.append(dict(account_alias=account, market=market,
                                   coverage_start=intervals[0][0] if intervals else None,
                                   coverage_through=through,
                                   uncovered_intervals=[dict(start_date=a, end_date=b) for a, b in gaps[:20]],
                                   uncovered_interval_count=len(gaps)))
            if gaps:
                reason = ('collection_watermark_missing' if not intervals else
                          'collection_watermark_before_query_end' if end_date > through else
                          'collection_coverage_before_start' if start_date < intervals[0][0] else
                          'collection_coverage_internal_gap')
                missing.append(dict(dataset_id='dataset.trade-event', reason=reason,
                                    account_alias=account, market=market))
    return dict(complete=not missing, partitions=partitions, missing=missing,
                coverage_through=min(ends) if ends and all(ends) else None,
                updated_at=max(updated, default=None))
