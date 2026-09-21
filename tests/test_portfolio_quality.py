from datetime import date
from decimal import Decimal

from kis_portfolio.application.portfolio_quality import (
    PortfolioQualityComponent,
    evaluate_portfolio_capabilities,
)


def _component(
    instrument: str,
    *,
    market: str = "KRX",
    currency: str = "KRW",
    value: str = "100",
    quality: str = "pass",
    fx_date: object = None,
) -> PortfolioQualityComponent:
    return PortfolioQualityComponent(
        account_ref="brokerage",
        aggregate_level="position",
        market=market,
        currency=currency,
        value_krw=Decimal(value),
        quality_status=quality,
        fx_date=fx_date,
    )


def test_missing_prior_is_not_an_input_to_current_capability_quality() -> None:
    result = evaluate_portfolio_capabilities(
        [_component("005930")],
        expected_accounts=["brokerage"],
        evaluation_date=date(2026, 9, 17),
        earliest_fx_date=date(2026, 9, 16),
    )

    assert result.complete_total_krw == Decimal("100")
    assert result.verified_krw_listed_positions_krw == Decimal("100")
    assert result.missing_reasons == ()


def test_stale_foreign_fx_suppresses_complete_total_but_preserves_krw_subset() -> None:
    result = evaluate_portfolio_capabilities(
        [
            _component("005930", value="250"),
            _component("GOOG", market="NAS", currency="USD", value="300", fx_date="2026-09-11"),
        ],
        expected_accounts=["brokerage"],
        evaluation_date=date(2026, 9, 17),
        earliest_fx_date=date(2026, 9, 16),
    )

    assert result.complete_total_krw is None
    assert result.verified_krw_listed_positions_krw == Decimal("250")
    assert result.verified_krw_listed_positions_count == 1
    assert result.missing_reasons == ("fx_input_stale",)


def test_account_gap_and_degraded_row_do_not_create_false_complete_total() -> None:
    result = evaluate_portfolio_capabilities(
        [_component("005930", quality="degraded")],
        expected_accounts=["brokerage", "isa"],
        evaluation_date=date(2026, 9, 17),
        earliest_fx_date=date(2026, 9, 16),
    )

    assert result.complete_total_krw is None
    assert result.verified_krw_listed_positions_count == 0
    assert result.missing_reasons == ("degraded_components", "account_coverage_gap")
