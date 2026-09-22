from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb

from kis_portfolio.clients.korea_exim import KoreaEximFxRate
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.services.fx_fallback import (
    assess_fx_fallback,
    latest_kis_usd_krw_reference,
    resolve_fx_preflight_date,
)


def candidate(rate: str = "1400") -> KoreaEximFxRate:
    return KoreaEximFxRate(
        requested_date=date(2026, 9, 22),
        rate_date=date(2026, 9, 22),
        fetched_at=datetime(2026, 9, 22, 2, tzinfo=UTC),
        base_currency="USD",
        quote_currency="KRW",
        native_rate_field="deal_bas_r",
        rate=Decimal(rate),
    )


def test_assessment_accepts_current_candidate_near_recent_primary() -> None:
    result = assess_fx_fallback(
        candidate(),
        logical_date=date(2026, 9, 22),
        reference_date=date(2026, 9, 21),
        reference_rate=Decimal("1390"),
    )

    assert result.eligible is True
    assert result.reason == "pass"


def test_assessment_quarantines_large_cross_source_disagreement() -> None:
    result = assess_fx_fallback(
        candidate("1500"),
        logical_date=date(2026, 9, 22),
        reference_date=date(2026, 9, 21),
        reference_rate=Decimal("1390"),
    )

    assert result.eligible is False
    assert result.reason == "cross_source_deviation_exceeded"


def test_reference_query_excludes_fallback_from_its_own_cross_check() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    now = datetime(2026, 9, 22, 2, tzinfo=UTC)
    for source_id, rate_type, rate in (
        ("source.kis-open-api", "close", Decimal("1390")),
        ("source.korea-eximbank-open-api", "deal_bas_r", Decimal("1400")),
    ):
        envelope = SourceEnvelope(
            source_id=source_id,
            source_record_id=f"{source_id}:{rate_type}",
            observed_at=now,
            fetched_at=now,
            payload={"rate": str(rate)},
            content_hash=f"hash-{rate_type}",
        )
        observation_id = repository.record_observation("dataset.fx-rate-daily", envelope)
        repository.upsert_fx_rate({
            "base_currency": "USD",
            "quote_currency": "KRW",
            "rate_date": date(2026, 9, 21),
            "rate_type": rate_type,
            "rate": rate,
            "quality_status": "pass",
        }, observation_id)

    assert latest_kis_usd_krw_reference(
        con, logical_date=date(2026, 9, 22),
    ) == (date(2026, 9, 21), Decimal("1390.0000000000"))
    assert resolve_fx_preflight_date(
        con,
        requested="latest-governed",
        today=date(2026, 9, 22),
    ) == date(2026, 9, 21)
    con.close()


def test_preflight_date_keeps_explicit_today_for_runtime_availability_checks() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()

    assert resolve_fx_preflight_date(
        con,
        requested="today",
        today=date(2026, 9, 22),
    ) == date(2026, 9, 22)
    con.close()


def test_preflight_date_fails_closed_without_governed_reference() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()

    try:
        resolve_fx_preflight_date(
            con,
            requested="latest-governed",
            today=date(2026, 9, 22),
        )
    except ValueError as exc:
        assert str(exc) == "no governed KIS USD/KRW reference is available"
    else:
        raise AssertionError("preflight must fail closed without a governed KIS reference")
    finally:
        con.close()
