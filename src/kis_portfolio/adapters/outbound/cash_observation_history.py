"""Read-only observed cash history, deliberately separate from settled reconciliation.

Immutable normalized Bronze inputs preserve what was known, including legacy basis
limitations. Observation differences are never booked as deposits, RP flows or P&L.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
from zoneinfo import ZoneInfo

from kis_portfolio.services.cash_reconciliation import aware

DATASET_ID = "dataset.cash-observation-history"
SCOPES = [(a, "KRW") for a in ("ria", "isa", "brokerage", "irp", "pension")] + [("brokerage", "USD")]
SEOUL = ZoneInfo("Asia/Seoul")


def enabled() -> bool:
    return os.getenv("KIS_CASH_OBSERVATION_HISTORY_ENABLED", "false").lower() == "true"


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _number(value) -> Decimal | None:
    if isinstance(value, (float, bool)) or value is None:
        return None
    try:
        number = Decimal(str(value))
        if number.is_finite() and abs(number) < Decimal("1e20") and number.as_tuple().exponent >= -8:
            return number
    except (InvalidOperation, ValueError):
        pass
    return None


def _text(value):
    return format(value, "f") if value is not None else None


class CashObservationHistory:
    def __init__(self, connection, *, clock=lambda: datetime.now(UTC)):
        self.connection = connection
        self.clock = clock

    def read(self, *, cutoff=None, lookback_days=7, run_id=None, limit=50, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100 or type(lookback_days) is not int or not 1 <= lookback_days <= 31:
            raise ValueError("invalid_cash_history_bounds")
        now = aware(self.clock())
        anchor = aware(cutoff) if cutoff is not None else now
        offset = 0
        body = None
        if cursor:
            try:
                if len(cursor) > 2048:
                    raise ValueError
                body = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if set(body) != {"cutoff", "binding", "offset"}:
                    raise ValueError
                saved = aware(datetime.fromisoformat(body["cutoff"]))
                if cutoff is None:
                    anchor = saved
                if anchor != saved:
                    raise ValueError
                offset = body["offset"]
                if type(offset) is not int or not 0 < offset <= 10000:
                    raise ValueError
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise ValueError("invalid_cash_history_cursor") from None
        binding = _digest([DATASET_ID, anchor, lookback_days, run_id])
        if body and body["binding"] != binding:
            raise ValueError("invalid_cash_history_cursor")
        if anchor > now:
            raise ValueError("future_cash_history_cutoff")
        floor = anchor - timedelta(days=lookback_days)
        # The 31-day source cap includes predecessor context; no unbounded history scan.
        rows = self.connection.execute("""
            SELECT a.account_label, json_extract_string(b.payload,'$.currency'),
                   b.observed_at, greatest(b.fetched_at,b.created_at), b.payload,
                   b.observation_id,b.pipeline_run_id
            FROM bronze.source_observations b
            JOIN silver.accounts a ON a.account_id=json_extract_string(b.payload,'$.account_id')
            WHERE b.dataset_id='dataset.portfolio-position-observation'
              AND b.source_id='source.kis-open-api'
              AND json_exists(b.payload,'$.amount') AND json_exists(b.payload,'$.currency')
              AND b.observed_at BETWEEN ? AND ?
              AND greatest(b.fetched_at,b.created_at)<=?
            ORDER BY b.observed_at,b.observation_id LIMIT 10001
        """, [anchor-timedelta(days=31), anchor, anchor]).fetchall()
        if len(rows) > 10000:
            raise ValueError("cash_history_source_limit")
        grouped = defaultdict(list)
        for alias, currency, at, known, payload, identity, producer in rows:
            if (alias, currency) in SCOPES:
                grouped[(alias, currency, aware(at))].append((aware(known), json.loads(payload), identity, producer))
        series = defaultdict(list)
        for (alias, currency, at), versions in sorted(grouped.items()):
            # Conflicting source rows are visible ambiguity, never arbitrary balance selection.
            amounts = {_text(_number(v[1].get("amount"))) for v in versions}
            known, payload, identity, producer = max(versions, key=lambda v: (v[0], v[2]))
            amount = _number(payload.get("amount")) if len(amounts) == 1 else None
            warnings = ["not_certified_settled_cash", "source_zero_omissions_not_recoverable"]
            basis = "valuation_residual_provisional" if currency == "KRW" else "legacy_deposit_or_withdrawable"
            if currency != "KRW":
                warnings.append("deposit_withdrawable_fallback_unresolved")
            if amount is None:
                warnings.append("ambiguous_or_invalid_observation")
            if payload.get("quality_status") != "pass":
                warnings.append("source_quality_not_pass")
            series[(alias, currency)].append(dict(account_alias=alias, currency=currency,
                observed_at=at.isoformat(), observed_date=at.astimezone(SEOUL).date().isoformat(),
                known_at=known.isoformat(), amount=_text(amount), basis=basis,
                status="observed" if amount is not None else "unavailable",
                cause="unknown", performance_eligible=False, lineage_ref=_digest(identity), warnings=warnings,
                _amount=amount, _at=at, _producer=producer))
        latest = []
        history = []
        for scope in SCOPES:
            points = series[scope]
            selected = [p for p in points if run_id is None or p["_producer"] == run_id]
            if not selected:
                latest.append(dict(account_alias=scope[0], currency=scope[1], amount=None,
                    observed_at=None, age_seconds=None, status="unavailable", basis="unknown",
                    warnings=["cash_observation_missing_not_zero"], performance_eligible=False))
                continue
            last = selected[-1]
            latest.append({**{k: last[k] for k in ("account_alias", "currency", "amount", "observed_at", "basis", "warnings", "performance_eligible")},
                "status": "last_known" if last["amount"] is not None else "unavailable",
                "age_seconds": int((anchor-last["_at"]).total_seconds())})
            previous = None
            for point in points:
                change = None
                if previous and point["_amount"] is not None and previous["_amount"] is not None and point["basis"] == previous["basis"]:
                    with localcontext() as context:
                        context.prec = 40
                        change = point["_amount"]-previous["_amount"]
                if point["_at"] >= floor and (run_id is None or point["_producer"] == run_id):
                    item = {k: v for k, v in point.items() if not k.startswith("_")}
                    item.update(previous_at=previous["observed_at"] if previous else None,
                        change=_text(change), observation_gap_seconds=int((point["_at"]-previous["_at"]).total_seconds()) if previous else None,
                        trade_context=[], trade_context_status="not_assessed")
                    history.append(item)
                previous = point
        history.sort(key=lambda x: (x["observed_at"], x["account_alias"], x["currency"], x["lineage_ref"]), reverse=True)
        page = history[offset:offset+limit]
        for item in page:
            if item["previous_at"]:
                self._trade_context(item, anchor)
        more = len(history) > offset+len(page)
        next_cursor = base64.urlsafe_b64encode(json.dumps(dict(cutoff=anchor.isoformat(),binding=binding,
            offset=offset+len(page))).encode()).decode() if more else None
        data = dict(latest=latest, results=page, next_cursor=next_cursor)
        if len(json.dumps(data).encode()) > 250000:
            raise ValueError("cash_history_response_too_large")
        return {"as_of": anchor, "data": data}

    def _trade_context(self, item, anchor):
        # These are confirmed trade observations by execution interval, NOT posted cash effects.
        rows = self.connection.execute("""
            WITH visible AS (
                SELECT t.* FROM silver.trade_event_revisions t
                JOIN bronze.source_observations b ON b.observation_id=t.source_observation_id
                JOIN silver.accounts a USING(account_id)
                WHERE a.account_label=? AND t.currency=? AND t.knowledge_at<=?
                  AND greatest(b.fetched_at,b.created_at)<=?
                QUALIFY row_number() OVER(PARTITION BY t.source_trade_event_id
                    ORDER BY t.revision DESC,t.knowledge_at DESC,t.trade_event_revision_id DESC)=1
            )
            SELECT market,instrument_id,side,executed_at,quantity,price FROM visible
            WHERE executed_at>? AND executed_at<=? AND quality_status='pass'
            ORDER BY executed_at,trade_event_revision_id LIMIT 11
        """, [item["account_alias"],item["currency"],anchor,anchor,
              datetime.fromisoformat(item["previous_at"]),datetime.fromisoformat(item["observed_at"])]).fetchall()
        item["trade_context"] = [dict(market=m,instrument_ref=i,side=s,executed_at=aware(at).isoformat(),
            quantity=_text(q),price=_text(p)) for m,i,s,at,q,p in rows[:10]]
        item["trade_context_status"] = "execution_interval_only_truncated" if len(rows)>10 else "execution_interval_only_incomplete"
