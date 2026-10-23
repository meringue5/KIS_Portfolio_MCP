"""Bounded INTERNAL WI-071 preview. No public registration or auth replacement."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from kis_portfolio.services.cash_reconciliation import EvaluationHistory, _hash, _scope, aware


@dataclass(frozen=True)
class PreviewQuery:
    account_alias: str
    currency: str
    start: datetime
    end: datetime
    knowledge_cutoff: datetime
    limit: int = 50
    cursor: str | None = None


def read_preview(history: EvaluationHistory, query: PreviewQuery) -> dict:
    _scope(query.account_alias, query.currency)
    start, end, cutoff = aware(query.start), aware(query.end), aware(query.knowledge_cutoff)
    if not start <= end <= cutoff or end - start > timedelta(days=31):
        raise ValueError("invalid_preview_range")
    if type(query.limit) is not int or not 1 <= query.limit <= 100:
        raise ValueError("invalid_preview_limit")
    # PIT choice per interval, independent of append order and future evaluation revisions.
    intervals = {}
    for row in history.rows:
        r = row.result
        if (r.account_alias, r.currency) != (query.account_alias, query.currency):
            continue
        if not start <= r.t1 <= end or r.knowledge_cutoff > cutoff:
            continue
        key = (r.t0, r.t1)
        prior = intervals.get(key)
        if prior is None or (r.knowledge_cutoff, row.revision) > (prior.result.knowledge_cutoff, prior.revision):
            intervals[key] = row
    rows = sorted(intervals.values(), key=lambda row: (row.result.t1, row.result.t0 or row.result.t1))
    binding = _hash([query.account_alias, query.currency, start, end, cutoff,
                     [(row.result.input_hash, row.revision) for row in rows]])
    offset = 0
    if query.cursor is not None:
        try:
            if not isinstance(query.cursor, str) or len(query.cursor) > 1024:
                raise ValueError
            body = json.loads(base64.b64decode(query.cursor, altchars=b"-_", validate=True))
            if (set(body) != {"snapshot", "offset"} or body["snapshot"] != binding
                    or type(body["offset"]) is not int or not 0 < body["offset"] < len(rows)):
                raise ValueError
            offset = body["offset"]
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("invalid_preview_cursor") from None
    selected = rows[offset:offset + query.limit]
    data = []
    for row in selected:
        r = row.result
        data.append({
            "account_alias": r.account_alias, "currency": r.currency,
            "t0": r.t0.isoformat() if r.t0 else None, "t1": r.t1.isoformat(),
            "knowledge_cutoff": r.knowledge_cutoff.isoformat(), "outcome": r.outcome,
            "reasons": list(r.reasons), "observed": format(r.observed, "f") if r.observed is not None else None,
            "expected": format(r.expected, "f") if r.expected is not None else None,
            "delta": format(r.delta, "f") if r.delta is not None else None,
            "explained_count": r.explained_count, "pending_count": r.pending_count,
            "revision": row.revision, "lineage_ref": r.input_hash, "formula_version": r.formula_version,
            "external_flow_coverage": "not_assessed", "performance_eligible": False,
        })
    next_offset = offset + len(selected)
    cursor = (base64.urlsafe_b64encode(json.dumps({"snapshot": binding, "offset": next_offset}).encode()).decode()
              if next_offset < len(rows) else None)
    response = {"schema_version": "0.1.0", "data": data, "next_cursor": cursor}
    if len(json.dumps(response, ensure_ascii=False).encode()) > 262144:
        raise ValueError("preview_response_too_large")
    return response
