"""Pure ECOS and FRED/ALFRED fixture normalization with no network I/O."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_portfolio.modules.market.macro import (
    MacroObservationRevision,
    MacroSeriesDefinition,
    validate_observation,
)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _date(value: Any) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("macro fixture date must be ISO YYYY-MM-DD") from exc


def _decimal(value: Any) -> tuple[Decimal | None, str | None]:
    text = str(value if value is not None else "").strip()
    if text in {"", ".", "NA", "N/A"}:
        return None, "provider_missing"
    try:
        return Decimal(text.replace(",", "")), None
    except InvalidOperation as exc:
        raise ValueError("macro fixture value is not a Decimal or typed missing marker") from exc


def _require_metadata(row: dict[str, Any], definition: MacroSeriesDefinition) -> None:
    expected = {
        "unit": definition.native_unit,
        "frequency": definition.native_frequency,
        "seasonal_adjustment": definition.seasonal_adjustment,
    }
    for key, value in expected.items():
        if str(row.get(key) or "") != value:
            raise ValueError(f"macro fixture {key} differs from the exact registry")


def normalize_fred_fixture(
    row: dict[str, Any],
    *,
    definition: MacroSeriesDefinition,
    fetched_at: datetime,
    knowledge_at: datetime,
    request_id: str,
    partition_key: str,
    pipeline_run_id: str | None = None,
) -> MacroObservationRevision:
    if definition.source_id != "source.fred-alfred":
        raise ValueError("FRED fixture requires a FRED/ALFRED definition")
    if str(row.get("series_id") or "") != definition.provider_series_id:
        raise ValueError("FRED fixture series ID differs from the exact registry")
    _require_metadata(row, definition)
    realtime_start = _date(row.get("realtime_start"))
    realtime_end = _date(row.get("realtime_end"))
    native_value, missing_reason = _decimal(row.get("value"))
    content_hash = _hash(row)
    source_available_at = datetime.combine(realtime_start, time.min, tzinfo=UTC)
    value = MacroObservationRevision(
        series_contract_id=definition.series_contract_id,
        series_contract_version=definition.version,
        definition_hash=definition.definition_hash,
        observation_period=str(row.get("date") or "").strip(),
        revision_kind="provider_vintage",
        revision_key=f"{realtime_start.isoformat()}:{realtime_end.isoformat()}:{content_hash}",
        native_value=native_value,
        missing_reason=missing_reason,
        native_unit=definition.native_unit,
        native_frequency=definition.native_frequency,
        seasonal_adjustment=definition.seasonal_adjustment,
        source_realtime_start=realtime_start,
        source_realtime_end=realtime_end,
        source_available_at=source_available_at,
        source_time_precision="day",
        knowledge_at=knowledge_at,
        fetched_at=fetched_at,
        request_id=request_id,
        pipeline_run_id=pipeline_run_id,
        partition_key=partition_key,
        content_hash=content_hash,
        quality_status="missing" if native_value is None else "pass",
        provenance={"fixture": True, "provider": "FRED/ALFRED"},
    )
    validate_observation(value, definition)
    return value


def normalize_ecos_fixture(
    row: dict[str, Any],
    *,
    definition: MacroSeriesDefinition,
    fetched_at: datetime,
    request_id: str,
    partition_key: str,
    pipeline_run_id: str | None = None,
) -> MacroObservationRevision:
    if definition.source_id != "source.bok-ecos":
        raise ValueError("ECOS fixture requires an ECOS definition")
    expected_parts = definition.provider_series_id.split("/")
    actual_parts = [str(row.get("STAT_CODE") or ""), str(row.get("CYCLE") or "")]
    actual_parts.extend(str(row.get(f"ITEM_CODE{index}") or "") for index in range(1, len(expected_parts) - 1))
    if actual_parts != expected_parts:
        raise ValueError("ECOS fixture identity differs from the exact registry")
    _require_metadata(row, definition)
    native_value, missing_reason = _decimal(row.get("DATA_VALUE"))
    content_hash = _hash(row)
    value = MacroObservationRevision(
        series_contract_id=definition.series_contract_id,
        series_contract_version=definition.version,
        definition_hash=definition.definition_hash,
        observation_period=str(row.get("TIME") or "").strip(),
        revision_kind="observed_content",
        revision_key=f"observed-content:{content_hash}",
        native_value=native_value,
        missing_reason=missing_reason,
        native_unit=definition.native_unit,
        native_frequency=definition.native_frequency,
        seasonal_adjustment=definition.seasonal_adjustment,
        source_available_at=None,
        source_time_precision=None,
        knowledge_at=fetched_at,
        fetched_at=fetched_at,
        request_id=request_id,
        pipeline_run_id=pipeline_run_id,
        partition_key=partition_key,
        content_hash=content_hash,
        quality_status="missing" if native_value is None else "pass",
        provenance={"fixture": True, "provider": "Bank of Korea ECOS"},
    )
    validate_observation(value, definition)
    return value
