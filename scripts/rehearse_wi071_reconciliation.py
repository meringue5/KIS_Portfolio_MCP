#!/usr/bin/env python3
"""Immediate synthetic evaluator -> revisions -> internal read, without source/persistence I/O."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

from kis_portfolio.application.cash_reconciliation_preview import PreviewQuery, read_preview
from kis_portfolio.services.cash_reconciliation import (
    CashEffect, CashObservation, Coverage, EvaluationHistory, OpeningPending,
    ReconciliationInput, RoundingRule, money, reconcile,
)


def main() -> None:
    start = datetime(2026, 10, 12, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    cutoff = end + timedelta(hours=1)
    opening = CashObservation("ria", "KRW", start, start, money("100.00"), "settled", "fixture-only",
                              "synthetic-opening", True, True)
    closing = replace(opening, observed_at=end, known_at=end, amount=money("150.00"))
    credit = CashEffect("synthetic-credit", "ria", "KRW", "trade", 1, end, money("20.00"),
                        start + timedelta(hours=1), "synthetic-posting", True, True)
    inputs = ReconciliationInput(
        closing, opening, cutoff, effects=(credit,),
        coverage=tuple(Coverage("ria", "KRW", name, start, end, end, True, True, "synthetic-proof", True)
                       for name in ("trade", "charges")),
        opening_pending=OpeningPending("ria", "KRW", start, start, True, "synthetic-opening-proof"),
        rounding=RoundingRule("KRW", 2, "half_even", "aggregate", "synthetic-rule", "fixture-only", start),
    )
    history = EvaluationHistory()
    revision = history.append(reconcile(inputs))
    query = PreviewQuery("ria", "KRW", start, end, cutoff)
    positive = read_preview(history, query)["data"][0]
    assert (positive["outcome"], positive["expected"], positive["delta"]) == (
        "unexplained_movement", "120.00", "30.00")
    assert history.append(reconcile(inputs)) is revision
    later = cutoff + timedelta(hours=1)
    history.append(reconcile(replace(inputs, knowledge_cutoff=later,
                                     closing=replace(closing, basis="valuation_residual"))))
    partial = read_preview(history, replace(query, knowledge_cutoff=later))["data"][0]
    assert partial["outcome"] == "deferred" and partial["delta"] is None
    assert read_preview(history, query)["data"][0] == positive
    try:
        read_preview(history, replace(query, limit=101))
    except ValueError as exc:
        assert str(exc) == "invalid_preview_limit"
    else:
        raise AssertionError("invalid query accepted")
    assert all(r["external_flow_coverage"] == "not_assessed" and not r["performance_eligible"]
               for r in (positive, partial))
    print(json.dumps({"work_item": "WI-071", "evidence_kind": "synthetic-internal-end-to-end",
                      "fixture_only": True, "positive": "pass", "partial": "pass", "error": "pass",
                      "replay_no_op": True, "old_cutoff_preserved": True,
                      "cash_flow_coverage_promoted": False, "broker_calls": 0,
                      "production_writes": 0, "public_mcp_acceptance": "not run; inactive"}))


if __name__ == "__main__":
    main()
