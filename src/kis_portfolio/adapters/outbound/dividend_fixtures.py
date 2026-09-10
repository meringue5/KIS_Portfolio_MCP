"""Pure, redistribution-safe dividend fixture normalization with no network I/O."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_portfolio.modules.market.dividends import (
    DividendActionRevision,
    DividendEntitlementRevision,
)


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("dividend fixture date must be YYYYMMDD")
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("dividend fixture amount must be numeric") from exc


def normalize_action_fixture(
    row: dict[str, Any],
    *,
    source_id: str,
    jurisdiction: str,
    issuer_id: str,
    instrument_id: str,
    observed_at: datetime,
    fetched_at: datetime,
) -> DividendActionRevision:
    """Normalize an already-captured synthetic action fixture."""

    amount = _decimal(row.get("amount_per_share"))
    currency = str(row.get("currency") or "").upper() or None
    return DividendActionRevision(
        source_id=source_id,
        jurisdiction=jurisdiction,
        issuer_id=issuer_id,
        instrument_id=instrument_id,
        source_action_id=str(row.get("source_action_id") or "").strip(),
        action_type=str(row.get("action_type") or "cash").lower(),
        action_status=str(row.get("action_status") or "declared").lower(),
        certainty=str(row.get("certainty") or "declared").lower(),
        amount_per_share=amount,
        currency=currency,
        declaration_date=_date(row.get("declaration_date")),
        ex_date=_date(row.get("ex_date")),
        record_date=_date(row.get("record_date")),
        payable_date=_date(row.get("payable_date")),
        source_available_at=observed_at,
        observed_at=observed_at,
        fetched_at=fetched_at,
        knowledge_at=fetched_at,
        source_time_precision=str(row.get("source_time_precision") or "day"),
        filing_revision_id=row.get("filing_revision_id"),
        correction_target_revision_id=row.get("correction_target_revision_id"),
        quality_status=str(row.get("quality_status") or "pass"),
        provenance={"fixture": True, "parser_version": "1.0.0"},
    )


def normalize_entitlement_fixture(
    row: dict[str, Any],
    *,
    dividend_action_id: str,
    account_id: str,
    knowledge_at: datetime,
    source_observation_id: str | None = None,
) -> DividendEntitlementRevision:
    coverage = str(row.get("coverage_status") or "source_gap")
    uncovered = coverage in {"source_gap", "not_observed", "insufficient_history", "ambiguous_action"}
    monetary_keys = ("eligible_quantity", "rate_per_share", "expected_gross", "expected_tax", "expected_net")
    if uncovered and any(row.get(key) not in (None, "") for key in monetary_keys):
        raise ValueError("uncovered entitlement cannot invent quantity or amounts")
    return DividendEntitlementRevision(
        dividend_action_id=dividend_action_id,
        account_id=account_id,
        basis=str(row.get("basis") or "manual"),
        coverage_status=coverage,
        knowledge_at=knowledge_at,
        eligibility_date=_date(row.get("eligibility_date")),
        eligible_quantity=None if uncovered else _decimal(row.get("eligible_quantity")),
        rate_per_share=None if uncovered else _decimal(row.get("rate_per_share")),
        expected_gross=None if uncovered else _decimal(row.get("expected_gross")),
        expected_tax=None if uncovered else _decimal(row.get("expected_tax")),
        expected_net=None if uncovered else _decimal(row.get("expected_net")),
        currency=None if uncovered else (str(row.get("currency") or "").upper() or None),
        source_observation_id=source_observation_id,
        position_evidence_id=row.get("position_evidence_id"),
        quality_status=str(row.get("quality_status") or ("partial" if uncovered else "pass")),
        provenance={"fixture": True, "parser_version": "1.0.0"},
    )
