"""Provider-neutral official filing contracts and fail-closed validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any


FILING_SOURCES = frozenset({"source.opendart", "source.sec-edgar"})
JURISDICTIONS = frozenset({"KR", "US"})
SOURCE_TIME_PRECISIONS = frozenset({"day", "second"})
RELATION_TYPES = frozenset({"none", "amends", "corrects", "withdraws"})
RELATION_QUALITIES = frozenset({"not_applicable", "candidate", "unresolved", "verified"})
ALIAS_QUALITIES = frozenset({"verified", "ambiguous", "missing", "superseded"})
QUALITY_STATUSES = frozenset({"pass", "partial", "quarantined", "failed"})
PERIOD_TYPES = frozenset({"instant", "duration"})
ALLOWED_MEDIA_TYPES = frozenset({
    "application/json",
    "application/xml",
    "application/zip",
    "text/html",
    "application/xhtml+xml",
})
MAX_OBJECT_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000


@dataclass(frozen=True, slots=True)
class IssuerAliasRevision:
    issuer_id: str
    source_id: str
    jurisdiction: str
    alias_type: str
    alias_value: str
    source_valid_from: datetime
    observed_at: datetime
    knowledge_at: datetime
    relation_quality: str
    market: str | None = None
    exchange_code: str | None = None
    source_valid_to: datetime | None = None
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FilingRevision:
    source_id: str
    jurisdiction: str
    source_filing_id: str
    issuer_id: str
    content_hash: str
    form_type: str
    source_url: str
    raw_object_hash: str
    source_available_at: datetime
    source_time_precision: str
    first_observed_at: datetime
    fetched_at: datetime
    knowledge_at: datetime
    parser_id: str
    parser_version: str
    relation_type: str = "none"
    relation_quality: str = "not_applicable"
    target_source_filing_id: str | None = None
    filing_title: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    statement_scope: str | None = None
    quality_status: str = "pass"
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FinancialFactRevision:
    taxonomy: str
    concept: str
    period_end: date
    period_type: str
    unit: str
    statement_scope: str
    dimension_hash: str
    raw_lexical_value: str
    source_available_at: datetime
    knowledge_at: datetime
    period_start: date | None = None
    typed_value: Decimal | None = None
    decimals_value: int | None = None
    scale_value: int | None = None
    quality_status: str = "partial"
    provenance: dict[str, Any] | None = None


def _require_aware(*values: datetime | None) -> None:
    if any(value is not None and value.tzinfo is None for value in values):
        raise ValueError("filing timestamps must be timezone-aware")


def validate_alias(value: IssuerAliasRevision) -> None:
    if value.source_id not in FILING_SOURCES:
        raise ValueError("issuer alias requires an approved filing source")
    if value.jurisdiction not in JURISDICTIONS:
        raise ValueError("unsupported filing jurisdiction")
    if value.relation_quality not in ALIAS_QUALITIES:
        raise ValueError("unsupported issuer alias quality")
    if not all((value.issuer_id.strip(), value.alias_type.strip(), value.alias_value.strip())):
        raise ValueError("issuer alias identity fields are required")
    _require_aware(
        value.source_valid_from,
        value.source_valid_to,
        value.observed_at,
        value.knowledge_at,
    )
    if value.source_valid_to is not None and value.source_valid_to <= value.source_valid_from:
        raise ValueError("issuer alias validity interval must advance")
    if value.knowledge_at < value.observed_at:
        raise ValueError("issuer alias knowledge_at cannot precede observation")
    if value.source_id == "source.opendart" and value.alias_type == "corp_code":
        if len(value.alias_value) != 8 or not value.alias_value.isdigit():
            raise ValueError("OpenDART corp_code must be eight digits")
    if value.source_id == "source.sec-edgar" and value.alias_type == "cik":
        if len(value.alias_value) != 10 or not value.alias_value.isdigit():
            raise ValueError("SEC CIK must be zero-padded to ten digits")


def validate_filing(value: FilingRevision) -> None:
    if value.source_id not in FILING_SOURCES:
        raise ValueError("filing requires an approved official source")
    if value.jurisdiction not in JURISDICTIONS:
        raise ValueError("unsupported filing jurisdiction")
    if value.source_time_precision not in SOURCE_TIME_PRECISIONS:
        raise ValueError("unsupported source timestamp precision")
    if value.relation_type not in RELATION_TYPES:
        raise ValueError("unsupported filing relation type")
    if value.relation_quality not in RELATION_QUALITIES:
        raise ValueError("unsupported filing relation quality")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported filing quality status")
    if not all((
        value.source_filing_id.strip(), value.issuer_id.strip(), value.content_hash.strip(),
        value.form_type.strip(), value.source_url.strip(), value.raw_object_hash.strip(),
        value.parser_id.strip(), value.parser_version.strip(),
    )):
        raise ValueError("filing identity, object, parser and source fields are required")
    if value.content_hash != value.raw_object_hash:
        raise ValueError("filing content hash must match the governed raw object")
    if value.relation_quality == "verified" and not value.target_source_filing_id:
        raise ValueError("verified filing relation requires an explicit target")
    if value.relation_type == "none" and value.target_source_filing_id:
        raise ValueError("unrelated filing cannot declare a correction target")
    _require_aware(
        value.source_available_at,
        value.first_observed_at,
        value.fetched_at,
        value.knowledge_at,
    )
    if value.knowledge_at < value.first_observed_at or value.fetched_at < value.first_observed_at:
        raise ValueError("filing knowledge and fetch times cannot precede first observation")


def validate_fact(value: FinancialFactRevision) -> None:
    if value.period_type not in PERIOD_TYPES:
        raise ValueError("financial fact period_type must be instant or duration")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported financial fact quality status")
    if not all((
        value.taxonomy.strip(), value.concept.strip(), value.unit.strip(),
        value.statement_scope.strip(), value.dimension_hash.strip(),
        value.raw_lexical_value.strip(),
    )):
        raise ValueError("financial fact source identity and lexical value are required")
    if value.period_type == "duration" and value.period_start is None:
        raise ValueError("duration fact requires period_start")
    if value.period_type == "instant" and value.period_start is not None:
        raise ValueError("instant fact must not declare period_start")
    if value.period_start is not None and value.period_start > value.period_end:
        raise ValueError("financial fact period must be ordered")
    _require_aware(value.source_available_at, value.knowledge_at)


def validate_artifact(
    *,
    media_type: str,
    byte_size: int,
    expanded_archive_bytes: int = 0,
    archive_members: int = 0,
    encrypted_archive: bool = False,
    archive_member_paths: tuple[str, ...] = (),
) -> None:
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError("filing artifact media type is not allowlisted")
    if byte_size < 0 or byte_size > MAX_OBJECT_BYTES:
        raise ValueError("filing artifact exceeds the 50 MiB object limit")
    if expanded_archive_bytes < 0 or expanded_archive_bytes > MAX_EXPANDED_ARCHIVE_BYTES:
        raise ValueError("filing archive exceeds the 200 MiB expanded limit")
    if archive_members < 0 or archive_members > MAX_ARCHIVE_MEMBERS:
        raise ValueError("filing archive exceeds the 2000 member limit")
    if archive_member_paths and archive_members not in {0, len(archive_member_paths)}:
        raise ValueError("filing archive member inventory count does not reconcile")
    for member in archive_member_paths:
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts or not member.strip():
            raise ValueError("filing archive contains an unsafe member path")
    if encrypted_archive:
        raise ValueError("encrypted filing archives are quarantined")
