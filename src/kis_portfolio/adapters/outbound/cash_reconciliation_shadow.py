"""Read-only stored-input WI-071 shadow, deliberately unable to attest settled cash.

Known gaps in current normalized cash cannot be repaired by assigning its amount
to a new basis. No current/latest cash-event view is treated as posting proof.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from kis_portfolio.services.cash_reconciliation import (
    CashObservation, EvaluationHistory, ReconciliationInput, _scope, aware, reconcile,
)


def inspect_stored_cash(connection, account_alias: str, currency: str, *, cutoff: datetime) -> EvaluationHistory:
    _scope(account_alias, currency)
    cutoff = aware(cutoff)
    supported_observation = currency == "KRW" or (account_alias == "brokerage" and currency == "USD")
    rows = connection.execute("""
        SELECT c.as_of, greatest(b.fetched_at,b.created_at), c.amount
        FROM silver.cash_snapshots c
        JOIN silver.accounts a USING(account_id)
        JOIN bronze.source_observations b ON b.observation_id=c.source_observation_id
        WHERE a.account_label=? AND c.currency=?
          AND c.as_of<=? AND c.as_of>=?
          AND greatest(b.fetched_at,b.created_at)<=?
        ORDER BY c.as_of DESC LIMIT 2
    """, [account_alias, currency, cutoff, cutoff - timedelta(days=31), cutoff]).fetchall()
    basis = ("unsupported" if not supported_observation else
             "valuation_residual" if currency == "KRW" else "mixed_deposit_withdrawable")
    observations = [CashObservation(account_alias, currency, aware(ts), aware(known), amount,
                                     basis=basis, basis_version="stored-unverified-v1")
                    for ts, known, amount in rows]
    history = EvaluationHistory()
    if not observations:
        observation = CashObservation(account_alias, currency, cutoff, cutoff, None,
                                       basis="unknown" if supported_observation else "unsupported")
        history.append(reconcile(ReconciliationInput(observation, None, cutoff)))
    else:
        history.append(reconcile(ReconciliationInput(observations[0], observations[1] if len(rows) > 1 else None,
                                                     cutoff)))
    return history
