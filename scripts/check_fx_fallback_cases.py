#!/usr/bin/env python3
"""Immediate no-network WI-060 FX fallback acceptance cases."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from kis_portfolio.clients.korea_exim import KoreaEximError, parse_usd_krw_deal_bas_rate
from kis_portfolio.services.fx_fallback import assess_fx_fallback


LOGICAL_DATE = date(2026, 9, 22)
FETCHED_AT = datetime(2026, 9, 22, 2, tzinfo=UTC)


def parsed(rate: str = "1,400.00"):
    return parse_usd_krw_deal_bas_rate(
        [{"result": 1, "cur_unit": "USD", "deal_bas_r": rate}],
        requested_date=LOGICAL_DATE,
        fetched_at=FETCHED_AT,
    )


def main() -> int:
    cases = []
    accepted = assess_fx_fallback(
        parsed(), logical_date=LOGICAL_DATE,
        reference_date=date(2026, 9, 21), reference_rate=Decimal("1390"),
    )
    cases.append({"scenario": "exact_date_within_threshold", "result": accepted.reason})

    divergent = assess_fx_fallback(
        parsed("1,500.00"), logical_date=LOGICAL_DATE,
        reference_date=date(2026, 9, 21), reference_rate=Decimal("1390"),
    )
    cases.append({"scenario": "cross_source_disagreement", "result": divergent.reason})

    stale_reference = assess_fx_fallback(
        parsed(), logical_date=LOGICAL_DATE,
        reference_date=date(2026, 9, 1), reference_rate=Decimal("1390"),
    )
    cases.append({"scenario": "stale_primary_reference", "result": stale_reference.reason})

    try:
        parse_usd_krw_deal_bas_rate(
            [], requested_date=LOGICAL_DATE, fetched_at=FETCHED_AT,
        )
    except KoreaEximError:
        cases.append({"scenario": "empty_provider_response", "result": "rejected"})

    expected = [
        "pass", "cross_source_deviation_exceeded", "reference_missing_or_stale", "rejected",
    ]
    status = "pass" if [item["result"] for item in cases] == expected else "failed"
    print(json.dumps({"status": status, "cases": cases}, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
