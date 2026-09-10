"""Pure OpenDART/SEC fixture normalization; this module performs no network I/O."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_portfolio.modules.market.filings import FilingRevision, FinancialFactRevision


KST = timezone(timedelta(hours=9))


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("filing fixture date must be YYYYMMDD")
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()
        if len(text) == 14 and text.isdigit():
            result = datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        else:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("filing fixture timestamp must include a timezone")
    return result


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def normalize_opendart_filing(
    row: dict[str, Any],
    *,
    corp_code: str,
    observed_at: datetime,
    fetched_at: datetime,
    raw_object_hash: str,
) -> FilingRevision:
    """Normalize a redistribution-safe OpenDART discovery fixture.

    OpenDART receipt dates are day-grain, so availability is conservatively the
    following KST midnight rather than an invented intraday timestamp.
    """

    receipt_date = _date(row.get("rcept_dt"))
    if receipt_date is None:
        raise ValueError("OpenDART filing requires rcept_dt")
    source_available_at = datetime.combine(
        receipt_date + timedelta(days=1), time.min, tzinfo=KST
    ).astimezone(UTC)
    filing_id = str(row.get("rcept_no") or "").strip()
    report_name = str(row.get("report_nm") or "").strip()
    candidate = "정정" in report_name
    return FilingRevision(
        source_id="source.opendart",
        jurisdiction="KR",
        source_filing_id=filing_id,
        issuer_id=f"KR:DART:{corp_code}",
        content_hash=raw_object_hash,
        form_type=str(row.get("reprt_code") or row.get("pblntf_ty") or "unknown"),
        filing_title=report_name or None,
        fiscal_year=int(row["bsns_year"]) if row.get("bsns_year") else None,
        fiscal_period=str(row.get("reprt_code") or "") or None,
        period_end=_date(row.get("period_end")),
        statement_scope=str(row.get("fs_div") or "") or None,
        source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing_id}",
        raw_object_hash=raw_object_hash,
        source_available_at=source_available_at,
        source_time_precision="day",
        first_observed_at=observed_at,
        fetched_at=fetched_at,
        knowledge_at=fetched_at,
        parser_id="opendart-filing-fixture",
        parser_version="1.0.0",
        relation_type="corrects" if candidate else "none",
        relation_quality="candidate" if candidate else "not_applicable",
        quality_status="partial" if candidate else "pass",
        provenance={"receipt_date": receipt_date.isoformat(), "fixture_hash": _hash(row)},
    )


def normalize_sec_filing(
    row: dict[str, Any],
    *,
    cik: str,
    observed_at: datetime,
    fetched_at: datetime,
    raw_object_hash: str,
    target_accession_number: str | None = None,
    verified_relation: bool = False,
) -> FilingRevision:
    accession = str(row.get("accessionNumber") or "").strip()
    accepted_at = _timestamp(row.get("acceptanceDateTime"))
    form_type = str(row.get("form") or "").strip()
    relation_type = "amends" if form_type.endswith("/A") else "none"
    relation_quality = "verified" if verified_relation else (
        "candidate" if relation_type != "none" else "not_applicable"
    )
    quality_status = "pass" if relation_quality in {"verified", "not_applicable"} else "partial"
    return FilingRevision(
        source_id="source.sec-edgar",
        jurisdiction="US",
        source_filing_id=accession,
        issuer_id=f"US:SEC:{cik}",
        content_hash=raw_object_hash,
        form_type=form_type,
        filing_title=str(row.get("primaryDocument") or "") or None,
        fiscal_year=int(row["fiscalYear"]) if row.get("fiscalYear") else None,
        fiscal_period=str(row.get("fiscalPeriod") or "") or None,
        period_start=_date(row.get("periodStart")),
        period_end=_date(row.get("reportDate")),
        statement_scope="consolidated",
        source_url=(
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{row.get('primaryDocument', '')}"
        ),
        raw_object_hash=raw_object_hash,
        source_available_at=accepted_at,
        source_time_precision="second",
        first_observed_at=observed_at,
        fetched_at=fetched_at,
        knowledge_at=fetched_at,
        parser_id="sec-submissions-fixture",
        parser_version="1.0.0",
        relation_type=relation_type,
        relation_quality=relation_quality,
        target_source_filing_id=target_accession_number,
        quality_status=quality_status,
        provenance={"fixture_hash": _hash(row)},
    )


def normalize_financial_fact(
    row: dict[str, Any],
    *,
    source_available_at: datetime,
    knowledge_at: datetime,
    statement_scope: str,
) -> FinancialFactRevision:
    dimensions = row.get("dimensions") or {}
    dimension_hash = _hash(dimensions)
    raw_value = str(row.get("value") if row.get("value") is not None else "").strip()
    period_start = _date(row.get("period_start"))
    period_end = _date(row.get("period_end"))
    if period_end is None:
        raise ValueError("financial fact fixture requires period_end")
    return FinancialFactRevision(
        taxonomy=str(row.get("taxonomy") or "").strip(),
        concept=str(row.get("concept") or "").strip(),
        period_start=period_start,
        period_end=period_end,
        period_type="duration" if period_start is not None else "instant",
        unit=str(row.get("unit") or "").strip(),
        statement_scope=statement_scope,
        dimension_hash=dimension_hash,
        raw_lexical_value=raw_value,
        typed_value=_decimal(raw_value),
        decimals_value=int(row["decimals"]) if row.get("decimals") not in (None, "") else None,
        scale_value=int(row["scale"]) if row.get("scale") not in (None, "") else None,
        source_available_at=source_available_at,
        knowledge_at=knowledge_at,
        quality_status="partial",
        provenance={"dimensions": dimensions, "fixture_hash": _hash(row)},
    )
