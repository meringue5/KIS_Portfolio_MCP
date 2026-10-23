"""Immutable diagnostic evidence; no monetary ledger writer or generic payload projection."""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
import time

import duckdb

from kis_portfolio.services.cash_reconciliation import ReconciliationResult, _hash, aware

DATASET_ID = 'dataset.cash-balance-reconciliation'
TABLE = 'control.cash_balance_reconciliations'


class CashReconciliationRepository:
    def __init__(self, connection, *, clock=lambda: datetime.now(UTC)):
        self.connection = connection
        self.clock = clock

    def append(self, result: ReconciliationResult, producer_run_id: str) -> bool:
        # A source-independent synthetic proof must never activate production numeric output.
        if (result.outcome != 'deferred' or any(x is not None for x in
                                              (result.observed, result.expected, result.delta))):
            raise ValueError('numeric_reconciliation_not_approved')
        if not producer_run_id or len(producer_run_id) > 160:
            raise ValueError('invalid_producer_run')
        interval = _hash([result.account_alias, result.currency, result.t0, result.t1])
        for attempt in range(3):
            self.connection.execute('BEGIN')
            try:
                if self.connection.execute(f'SELECT 1 FROM {TABLE} WHERE input_hash=?', [result.input_hash]).fetchone():
                    self.connection.execute('COMMIT')
                    return False
                revision = self.connection.execute(
                    f'SELECT coalesce(max(revision),0)+1 FROM {TABLE} WHERE interval_id=?', [interval]).fetchone()[0]
                self.connection.execute(f'INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
                    interval, revision, result.input_hash, result.account_alias, result.currency, result.t0,
                    result.t1, result.knowledge_cutoff, aware(self.clock()), producer_run_id, result.formula_version,
                    result.outcome, json.dumps(result.reasons), None, None, None,
                    result.explained_count, result.pending_count])
                self.connection.execute('COMMIT')
                return True
            except (duckdb.TransactionException, duckdb.ConstraintException):
                self._rollback()
                if attempt == 2:
                    raise RuntimeError('reconciliation_write_conflict') from None
                time.sleep(0.02 * (attempt + 1))
            except Exception:
                self._rollback()
                raise
        return False

    def _rollback(self):
        try:
            self.connection.execute('ROLLBACK')
        except duckdb.TransactionException as exc:
            if 'no transaction is active' not in str(exc).lower():
                raise RuntimeError('reconciliation_rollback_failed') from None

    def read(self, *, cutoff=None, lookback_days=7, run_id=None, limit=50, cursor=None) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100 or not 1 <= lookback_days <= 31:
            raise ValueError('invalid_reconciliation_bounds')
        now = aware(self.clock())
        anchor = aware(cutoff) if cutoff is not None else now
        offset = 0
        body = None
        if cursor:
            try:
                if len(cursor) > 2048:
                    raise ValueError
                body = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
                if set(body) != {'cutoff','scope','offset'}:
                    raise ValueError
                cursor_cutoff = aware(datetime.fromisoformat(body['cutoff']))
                if cutoff is None:
                    anchor = cursor_cutoff
                if anchor != cursor_cutoff:
                    raise ValueError
                offset = body['offset']
                if type(offset) is not int or not 0 < offset <= 10000:
                    raise ValueError
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise ValueError('invalid_reconciliation_cursor') from None
        if anchor > now:
            raise ValueError('future_reconciliation_cutoff')
        binding = _hash([DATASET_ID, anchor, lookback_days, run_id])
        if body and body['scope'] != binding:
            raise ValueError('invalid_reconciliation_cursor')
        rows = self.connection.execute(f'''
            WITH eligible AS (
              SELECT *, row_number() OVER (
                PARTITION BY interval_id ORDER BY knowledge_cutoff DESC,revision DESC) AS ranking
              FROM {TABLE}
              WHERE knowledge_cutoff<=? AND recorded_at<=? AND t1>=? AND t1<=?
                AND (? IS NULL OR producer_run_id=?)
            )
            SELECT account_alias,currency,t0,t1,knowledge_cutoff,outcome,reasons,
                   observed,expected,delta,explained_count,pending_count,revision,input_hash,formula_version
            FROM eligible WHERE ranking=1 ORDER BY t1 DESC,interval_id
            LIMIT ? OFFSET ?
        ''', [anchor,anchor,anchor-timedelta(days=lookback_days),anchor,run_id,run_id,limit+1,offset]).fetchall()
        more = len(rows)>limit
        items=[]
        for row in rows[:limit]:
            a,c,t0,t1,known,outcome,reasons,observed,expected,delta,count,pending,revision,digest,formula = row
            items.append(dict(account_alias=a,currency=c,t0=t0.isoformat() if t0 else None,t1=t1.isoformat(),
                knowledge_cutoff=known.isoformat(),outcome=outcome,reasons=json.loads(reasons),
                observed=format(observed,'f') if observed is not None else None,
                expected=format(expected,'f') if expected is not None else None,
                delta=format(delta,'f') if delta is not None else None,
                explained_count=count,pending_count=pending,revision=revision,lineage_ref=digest,
                formula_version=formula,external_flow_coverage='not_assessed',performance_eligible=False))
        next_cursor=base64.urlsafe_b64encode(json.dumps(dict(cutoff=anchor.isoformat(),scope=binding,
            offset=offset+len(items))).encode()).decode() if more else None
        response=dict(results=items,next_cursor=next_cursor)
        if len(json.dumps(response).encode())>250000:
            raise ValueError('reconciliation_response_too_large')
        return {'as_of':anchor,'data':response}
