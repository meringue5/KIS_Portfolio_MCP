#!/usr/bin/env python3
"""Run WI-060 capability degradation cases without network, clock, DB, or Telegram sends."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from kis_portfolio.application.portfolio_quality import (
    PortfolioQualityComponent,
    evaluate_portfolio_capabilities,
)


EVALUATION_DATE = date(2026, 9, 17)
EARLIEST_FX_DATE = date(2026, 9, 16)


def _row(
    *,
    account: str = "brokerage",
    market: str = "KRX",
    currency: str = "KRW",
    value: str = "100",
    quality: str = "pass",
    fx_date: object = None,
) -> PortfolioQualityComponent:
    return PortfolioQualityComponent(
        account_ref=account,
        aggregate_level="position",
        market=market,
        currency=currency,
        value_krw=Decimal(value),
        quality_status=quality,
        fx_date=fx_date,
    )


def _result(name: str, rows: list[PortfolioQualityComponent], expected: list[str]) -> dict[str, object]:
    outcome = evaluate_portfolio_capabilities(
        rows,
        expected_accounts=expected,
        evaluation_date=EVALUATION_DATE,
        earliest_fx_date=EARLIEST_FX_DATE,
    )
    return {
        "scenario": name,
        "complete_total_available": outcome.complete,
        "verified_krw_listed_positions_krw": str(outcome.verified_krw_listed_positions_krw),
        "verified_krw_listed_positions_count": outcome.verified_krw_listed_positions_count,
        "missing_reasons": list(outcome.missing_reasons),
    }


def run_cases() -> list[dict[str, object]]:
    cases = [
        _result("missing_prior_does_not_poison_current", [_row(value="250")], ["brokerage"]),
        _result(
            "stale_fx_preserves_krw_subset",
            [
                _row(value="250"),
                _row(market="NAS", currency="USD", value="300", fx_date="2026-09-11"),
            ],
            ["brokerage"],
        ),
        _result("missing_account_preserves_observed_subset", [_row(value="250")], ["brokerage", "isa"]),
        _result("degraded_row_is_not_verified", [_row(value="250", quality="degraded")], ["brokerage"]),
        _result("missing_current_is_unavailable", [], ["brokerage"]),
    ]
    by_name = {str(item["scenario"]): item for item in cases}
    assert by_name["missing_prior_does_not_poison_current"]["complete_total_available"] is True
    assert by_name["stale_fx_preserves_krw_subset"]["missing_reasons"] == ["fx_input_stale"]
    assert by_name["stale_fx_preserves_krw_subset"]["verified_krw_listed_positions_krw"] == "250"
    assert by_name["missing_account_preserves_observed_subset"]["missing_reasons"] == ["account_coverage_gap"]
    assert by_name["degraded_row_is_not_verified"]["verified_krw_listed_positions_count"] == 0
    assert by_name["missing_current_is_unavailable"]["missing_reasons"] == ["missing_current_state"]
    return cases


def main() -> int:
    print(json.dumps({"status": "pass", "cases": run_cases()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
