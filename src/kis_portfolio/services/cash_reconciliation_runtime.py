"""Stored-input post-success diagnosis, independently feature-gated from portfolio publish."""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime

from kis_portfolio.adapters.outbound.cash_reconciliation_shadow import inspect_stored_cash
from kis_portfolio.adapters.outbound.cash_reconciliation_warehouse import CashReconciliationRepository
from kis_portfolio.services.cash_reconciliation import ACCOUNTS
from kis_portfolio.platform.pipeline import (ManagedPipelineRunner, PipelineDefinition, PipelineStage,
    StageResult, QualityEvidence, LineageEvidence)


def enabled() -> bool:
    return os.getenv('KIS_CASH_RECONCILIATION_ENABLED','false').strip().lower()=='true'


def evaluate_stored_cash(connection, *, run_id: str, cutoff: datetime) -> dict:
    repo=CashReconciliationRepository(connection)
    outcomes=Counter()
    created=0
    for alias in sorted(ACCOUNTS):
        for currency in (('KRW','USD') if alias=='brokerage' else ('KRW',)):
            for row in inspect_stored_cash(connection,alias,currency,cutoff=cutoff).rows:
                created+=int(repo.append(row.result,run_id))
                outcomes[row.result.outcome]+=1
    return dict(status='partial',created=created,evaluated=sum(outcomes.values()),outcomes=dict(outcomes),
                broker_calls=0,monetary_writes=0)


def after_success(connection, *, run_id: str) -> dict:
    if not enabled():
        return {'status':'disabled'}
    try:
        row=connection.execute('''SELECT finished_at,logical_date,slot FROM control.pipeline_runs
            WHERE run_id=? AND status='succeeded' AND pipeline_id='pipeline.owned-portfolio-core-v2' ''',
            [run_id]).fetchone()
        if row is None or row[0] is None:
            return {'status':'unavailable','reason':'successful_portfolio_run_missing'}
        def evaluate(context):
            try:
                summary = evaluate_stored_cash(connection,run_id=run_id,cutoff=row[0])
            except Exception:
                raise RuntimeError('cash_reconciliation_evaluation_failed') from None
            return StageResult(output_count=summary['evaluated'], evidence=summary,
                quality=(QualityEvidence('dataset.cash-balance-reconciliation', 'settled-cash-inputs',
                    'partial', details={'deferred_scopes':summary['evaluated']}),),
                lineage=(LineageEvidence(run_id,'control.cash_balance_reconciliations',
                    'stored-cash-reconciliation','1.0.0'),))
        definition=PipelineDefinition('pipeline.cash-balance-reconciliation-v1','1.0.0',
            (PipelineStage('evaluate-persist',evaluate),),source_call_budget=0)
        outcome=ManagedPipelineRunner(connection).run(definition,logical_date=row[1],slot=row[2],partition_key=run_id)
        return dict(status='partial',pipeline_run_id=outcome.run_id,reused=outcome.reused,
                    broker_calls=0,monetary_writes=0)
    except Exception:
        # Diagnostic failure never turns an already-published core/report into a failure.
        return {'status':'unavailable','reason':'cash_reconciliation_evaluation_failed'}
