"""Provider-neutral macro series, observation and metric contracts for ADR-027."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


MACRO_SOURCES = frozenset({"source.bok-ecos", "source.fred-alfred"})
REVISION_KINDS = frozenset({"provider_vintage", "observed_content"})
QUALITY_STATUSES = frozenset({"pass", "partial", "missing", "stale", "rights_blocked", "failed"})
RIGHTS_STATUSES = frozenset({"allowed", "blocked"})
QUERY_MODES = frozenset({"system_as_of", "retrospective_source_as_of"})


@dataclass(frozen=True, slots=True)
class MacroSeriesDefinition:
    series_contract_id: str
    version: str
    definition_hash: str
    source_id: str
    provider_series_id: str
    source_owner: str
    source_license_class: str
    region: str
    concept: str
    native_frequency: str
    native_unit: str
    seasonal_adjustment: str
    vintage_capability: str
    publication_cadence: str
    expected_lag: str
    history_start: str
    rights_note: str
    attribution: str
    permitted_consumers: tuple[str, ...]
    transform_policy: str
    activation_state: str
    valid_from: date


@dataclass(frozen=True, slots=True)
class MacroObservationRevision:
    series_contract_id: str
    series_contract_version: str
    definition_hash: str
    observation_period: str
    revision_kind: str
    revision_key: str
    native_value: Decimal | None
    missing_reason: str | None
    native_unit: str
    native_frequency: str
    seasonal_adjustment: str
    knowledge_at: datetime
    fetched_at: datetime
    request_id: str
    partition_key: str
    content_hash: str
    rights_status: str = "allowed"
    quality_status: str = "pass"
    source_realtime_start: date | None = None
    source_realtime_end: date | None = None
    source_available_at: datetime | None = None
    source_time_precision: str | None = None
    pipeline_run_id: str | None = None
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MacroMetricResult:
    metric_id: str
    metric_version: str
    quality_status: str
    value: Decimal | None = None
    label: str | None = None
    unknown_reason: str | None = None
    input_revision_ids: tuple[str, ...] = ()


def validate_definition(value: MacroSeriesDefinition) -> None:
    if value.source_id not in MACRO_SOURCES:
        raise ValueError("macro definition requires an approved profile source")
    if value.vintage_capability not in {"provider-vintage", "observed-content"}:
        raise ValueError("unsupported macro vintage capability")
    if value.activation_state not in {"inactive", "production"}:
        raise ValueError("unsupported macro activation state")
    required = (
        value.series_contract_id, value.version, value.definition_hash,
        value.provider_series_id, value.source_owner, value.native_frequency,
        value.native_unit, value.attribution, value.rights_note,
    )
    if not all(item.strip() for item in required):
        raise ValueError("macro definition identity, metadata and rights are required")
    if len(value.definition_hash) != 64:
        raise ValueError("macro definition hash must be SHA-256")
    if not value.permitted_consumers:
        raise ValueError("macro definition requires a bounded consumer allowlist")


def validate_observation(
    value: MacroObservationRevision,
    definition: MacroSeriesDefinition,
) -> None:
    validate_definition(definition)
    if value.series_contract_id != definition.series_contract_id:
        raise ValueError("macro observation series contract does not match its definition")
    if value.series_contract_version != definition.version or value.definition_hash != definition.definition_hash:
        raise ValueError("macro observation definition version or hash mismatch")
    if value.revision_kind not in REVISION_KINDS:
        raise ValueError("unsupported macro revision kind")
    expected_kind = (
        "provider_vintage" if definition.vintage_capability == "provider-vintage"
        else "observed_content"
    )
    if value.revision_kind != expected_kind:
        raise ValueError("macro revision kind does not match its source contract")
    if value.native_unit != definition.native_unit:
        raise ValueError("macro observation native unit differs from the exact registry")
    if value.native_frequency != definition.native_frequency:
        raise ValueError("macro observation frequency differs from the exact registry")
    if value.seasonal_adjustment != definition.seasonal_adjustment:
        raise ValueError("macro observation seasonal adjustment differs from the exact registry")
    if value.quality_status not in QUALITY_STATUSES or value.rights_status not in RIGHTS_STATUSES:
        raise ValueError("unsupported macro quality or rights state")
    if not value.observation_period.strip() or not value.revision_key.strip():
        raise ValueError("macro observation period and revision key are required")
    if (value.native_value is None) == (value.missing_reason is None):
        raise ValueError("macro observation requires exactly one native value or missing marker")
    if value.rights_status == "blocked" and value.quality_status != "rights_blocked":
        raise ValueError("blocked macro rights must fail closed as rights_blocked")
    if value.quality_status == "pass" and value.native_value is None:
        raise ValueError("passing macro observation requires a native value")
    if value.knowledge_at.tzinfo is None or value.fetched_at.tzinfo is None:
        raise ValueError("macro observation timestamps must be timezone-aware")
    if value.source_available_at is not None and value.source_available_at.tzinfo is None:
        raise ValueError("macro source availability must be timezone-aware")
    if value.knowledge_at > value.fetched_at:
        raise ValueError("macro knowledge_at cannot follow fetched_at")
    if value.revision_kind == "provider_vintage":
        if value.source_realtime_start is None or value.source_realtime_end is None:
            raise ValueError("provider-vintage observation requires its provider realtime interval")
        if value.source_realtime_end < value.source_realtime_start:
            raise ValueError("macro provider realtime interval must be ordered")
    elif value.source_realtime_start is not None or value.source_realtime_end is not None:
        raise ValueError("ECOS observed-content must not fabricate a provider realtime interval")
    if len(value.content_hash) != 64:
        raise ValueError("macro observation content hash must be SHA-256")
