"""Bounded, fail-closed governance read models for the future Remote MCP adapter.

The service reads only packaged governance artifacts and existing Control
evidence.  It deliberately does not register public tools or interpret OAuth
tokens; the caller supplies an already validated consumer scope.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import duckdb

from kis_portfolio.db.catalog import V2_DATA_OBJECTS


MAX_RESPONSE_BYTES = 262_144
_CATALOG_KINDS = {
    "source": "sources.toml",
    "dataset": "datasets.toml",
    "metric": "metrics.toml",
    "pipeline": "pipelines.toml",
    "macro_series": "macro-series.toml",
}
_LIFECYCLES = {"approved", "active"}
_RUN_TERMINAL = {"succeeded", "failed"}
_STATUS_PRECEDENCE = {
    "pass": 0,
    "not_assessed": 1,
    "stale": 2,
    "partial": 3,
    "failed": 4,
    "unavailable": 5,
}
_KNOWN_ERROR_CODES = {"stage_failed", "build_failed", "timeout", "upstream_unavailable"}
_DATASET_OBJECT_LINKS = {
    "control.pipeline_runs": "dataset.pipeline-run-evidence",
    "control.pipeline_stage_runs": "dataset.pipeline-stage-evidence",
    "control.quality_results": "dataset.data-quality-evidence",
    "control.lineage_edges": "dataset.data-lineage-evidence",
    "control.watermarks": "dataset.pipeline-watermark-state",
    "control.pipeline_run_summary": "dataset.pipeline-run-summary-compat",
}


class ReadModelStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    PARTIAL = "partial"
    STALE = "stale"
    NOT_ASSESSED = "not_assessed"
    PASS = "pass"


class ReadModelRequestError(ValueError):
    """A stable, safe request validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReadModelEnvelope:
    """Immutable application DTO; adapters serialize it with :meth:`to_dict`."""

    schema_version: str
    as_of: datetime
    source: Mapping[str, Any]
    freshness: Mapping[str, Any]
    quality: Mapping[str, Any]
    missing_coverage: tuple[Mapping[str, Any], ...]
    lineage_ref: str | None
    request_id: str
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of,
            "source": dict(self.source),
            "freshness": dict(self.freshness),
            "quality": dict(self.quality),
            "missing_coverage": [dict(item) for item in self.missing_coverage],
            "lineage_ref": self.lineage_ref,
            "request_id": self.request_id,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class ConsumerPolicy:
    required_scope: str = "mcp-read"

    def authorize(self, consumer_scope: str) -> None:
        if consumer_scope != self.required_scope:
            raise ReadModelRequestError("forbidden")


@dataclass(frozen=True)
class EvidencePolicy:
    """Executable evidence rules for one exact pipeline definition.

    Manifest prose is never converted to executable policy.  Until every
    relevant field is provided, the aggregate cannot become ``pass``.
    """

    pipeline_id: str
    pipeline_version: str
    required_stages: tuple[str, ...]
    required_rules: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    required_watermark_types: tuple[str, ...] = ()
    freshness: timedelta | None = None
    dataset_wide_coverage: bool = False
    allowed_error_codes: frozenset[str] = frozenset(_KNOWN_ERROR_CODES)

    @property
    def complete(self) -> bool:
        return bool(
            self.required_stages
            and self.required_rules
            and self.required_watermark_types
            and self.freshness is not None
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime,)):
        return _utc(value).isoformat().replace("+00:00", "Z")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _opaque_ref(prefix: str, value: Any) -> str:
    return f"{prefix}:v1:{_hash(value)}"


def _encode_cursor(query: Mapping[str, Any], last: Sequence[Any]) -> str:
    payload = {"v": 1, "q": _hash(query), "last": list(last)}
    wrapped = {"p": payload, "d": _hash(payload)}
    return base64.urlsafe_b64encode(_canonical_json(wrapped).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, query: Mapping[str, Any], length: int) -> tuple[Any, ...]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        wrapped = json.loads(raw)
        payload = wrapped["p"]
        valid = (
            set(wrapped) == {"p", "d"}
            and wrapped["d"] == _hash(payload)
            and payload["v"] == 1
            and payload["q"] == _hash(query)
            and isinstance(payload["last"], list)
            and len(payload["last"]) == length
        )
        if not valid:
            raise ValueError
        return tuple(payload["last"])
    except Exception as exc:
        raise ReadModelRequestError("invalid_cursor") from exc


def _bounded_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).encode("utf-8")[:256].decode("utf-8", errors="ignore")


def _bounded_reviewed(value: Any) -> Any:
    if isinstance(value, str):
        return _bounded_text(value)
    if isinstance(value, list):
        return [_bounded_reviewed(item) for item in value]
    if isinstance(value, tuple):
        return [_bounded_reviewed(item) for item in value]
    return value


def _worst_status(statuses: Sequence[str]) -> str:
    if not statuses:
        return ReadModelStatus.NOT_ASSESSED
    return max(statuses, key=lambda item: _STATUS_PRECEDENCE.get(item, 1))


class GovernanceReadModelService:
    """Versioned catalog, quality and pipeline-run application projections."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        repo_root: Path,
        *,
        policies: Sequence[EvidencePolicy] = (),
        consumer_policy: ConsumerPolicy = ConsumerPolicy(),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        request_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        deadline_seconds: float = 5.0,
    ) -> None:
        self.connection = connection
        self.repo_root = repo_root.resolve()
        self.consumer_policy = consumer_policy
        self.now = now
        self.request_id = request_id
        self.deadline_seconds = deadline_seconds
        self.policies = {(item.pipeline_id, item.pipeline_version): item for item in policies}

    def data_catalog(
        self,
        *,
        consumer_scope: str,
        kind: str,
        item_id: str | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.consumer_policy.authorize(consumer_scope)
        if kind not in {*_CATALOG_KINDS, "object"}:
            raise ReadModelRequestError("invalid_kind")
        self._validate_limit(limit, maximum=50)
        query = {"model": "catalog.v1", "kind": kind, "id": item_id, "limit": limit}
        after = _decode_cursor(cursor, query, 3) if cursor else None
        try:
            records = self._catalog_records(kind)
        except Exception:
            return self._unavailable("packaged-governance", "catalog_load_failed")
        if item_id is not None:
            records = [item for item in records if item["id"] == item_id]
        records.sort(key=lambda item: (item["kind"], item["id"], item["version"]))
        if after:
            records = [item for item in records if (item["kind"], item["id"], item["version"]) > after]
        page = records[:limit]
        next_cursor = None
        if len(records) > limit:
            last = page[-1]
            next_cursor = _encode_cursor(query, (last["kind"], last["id"], last["version"]))
        gaps = [
            {"gap_code": "missing_contract_link", "gap_count": 1, "ref": item["id"]}
            for item in page if item.get("missing_contract_link")
        ]
        status = ReadModelStatus.PARTIAL if gaps else ReadModelStatus.PASS
        return self._envelope(
            source="packaged-governance",
            status=status,
            reason="catalog_projected" if status == ReadModelStatus.PASS else "contract_link_gap",
            missing_coverage=gaps,
            lineage_ref=_opaque_ref(
                "lineage", [(item["id"], item.get("contract_hash", _hash(item))) for item in page]
            ),
            data={"items": page, "next_cursor": next_cursor},
        )

    def data_quality(
        self,
        *,
        consumer_scope: str,
        dataset_id: str,
        run_id: str | None = None,
        as_of: datetime | None = None,
        lookback_days: int = 7,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.consumer_policy.authorize(consumer_scope)
        self._validate_lookback(lookback_days)
        self._validate_limit(limit, maximum=200)
        cutoff = _utc(as_of or self.now())
        query = {
            "model": "data-quality.v1", "dataset_id": dataset_id, "run_id": run_id,
            "as_of": cutoff.isoformat(), "lookback_days": lookback_days, "limit": limit,
        }
        after = _decode_cursor(cursor, query, 3) if cursor else None
        started = time.monotonic()
        try:
            sql = """
                SELECT q.run_id,q.rule_id,q.status,q.evaluated_at,r.pipeline_id,r.pipeline_version
                FROM control.quality_results q
                JOIN control.pipeline_runs r USING(run_id)
                WHERE q.dataset_id=? AND q.evaluated_at<=?
                  AND q.evaluated_at>=?
            """
            params: list[Any] = [dataset_id, cutoff, cutoff - timedelta(days=lookback_days)]
            if run_id is not None:
                sql += " AND q.run_id=?"
                params.append(run_id)
            if after:
                cursor_time = datetime.fromtimestamp(float(after[0]), tz=UTC)
                sql += """ AND (
                    q.evaluated_at<? OR
                    (q.evaluated_at=? AND (q.run_id>? OR (q.run_id=? AND q.rule_id>?)))
                )"""
                params.extend([cursor_time, cursor_time, str(after[1]), str(after[1]), str(after[2])])
            sql += " ORDER BY q.evaluated_at DESC,q.run_id,q.rule_id LIMIT ?"
            params.append(limit + 1)
            rows = self._rows(sql, params)
            self._check_deadline(started)
        except Exception:
            return self._unavailable("motherduck-control", "control_query_failed", as_of=cutoff)
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = []
        row_statuses = []
        for row in page_rows:
            policy = self.policies.get((row["pipeline_id"], row["pipeline_version"]))
            allowed = set(policy.required_rules.get(dataset_id, ())) if policy else set()
            known = row["rule_id"] in allowed
            normalized = row["status"] if row["status"] in {"pass", "failed"} else "not_assessed"
            if not known:
                normalized = "not_assessed" if normalized == "pass" else normalized
            row_statuses.append(normalized)
            items.append({
                "dataset_id": dataset_id,
                "run_id": row["run_id"],
                "rule_id": row["rule_id"] if known else "redacted",
                "status": normalized,
                "evaluated_at": _utc(row["evaluated_at"]),
                "safe_value_class": "none",
                "suppressed_detail": True,
            })
        next_cursor = None
        if has_more:
            last = page_rows[-1]
            next_cursor = _encode_cursor(
                query, (_utc(last["evaluated_at"]).timestamp(), last["run_id"], last["rule_id"]),
            )
        composed, gaps, lineage_ref = self._compose_quality(dataset_id, run_id, cutoff)
        status = _worst_status([composed, *row_statuses])
        return self._envelope(
            source="motherduck-control", status=status, reason="quality_evidence_composed",
            missing_coverage=gaps, lineage_ref=lineage_ref,
            data={"items": items, "next_cursor": next_cursor}, as_of=cutoff,
        )

    def pipeline_run(
        self,
        *,
        consumer_scope: str,
        run_id: str | None = None,
        pipeline_id: str | None = None,
        as_of: datetime | None = None,
        lookback_days: int = 7,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.consumer_policy.authorize(consumer_scope)
        if (run_id is None) == (pipeline_id is None):
            raise ReadModelRequestError("invalid_query_mode")
        self._validate_lookback(lookback_days)
        self._validate_limit(limit, maximum=50)
        cutoff = _utc(as_of or self.now())
        query = {
            "model": "pipeline-run.v1", "run_id": run_id, "pipeline_id": pipeline_id,
            "as_of": cutoff.isoformat(), "lookback_days": lookback_days, "limit": limit,
        }
        after = _decode_cursor(cursor, query, 2) if cursor else None
        started = time.monotonic()
        try:
            if run_id is not None:
                rows = self._rows("""
                    SELECT * FROM control.pipeline_runs WHERE run_id=? AND started_at<=?
                """, [run_id, cutoff])
            else:
                sql = """
                    SELECT * FROM control.pipeline_runs
                    WHERE pipeline_id=? AND started_at<=? AND started_at>=?
                """
                params = [pipeline_id, cutoff, cutoff - timedelta(days=lookback_days)]
                if after:
                    cursor_time = datetime.fromtimestamp(float(after[0]), tz=UTC)
                    sql += " AND (started_at<? OR (started_at=? AND run_id>?))"
                    params.extend([cursor_time, cursor_time, str(after[1])])
                sql += " ORDER BY started_at DESC,run_id LIMIT ?"
                params.append(limit + 1)
                rows = self._rows(sql, params)
            self._check_deadline(started)
        except Exception:
            return self._unavailable("motherduck-control", "control_query_failed", as_of=cutoff)
        has_more = run_id is None and len(rows) > limit
        selected = rows[:limit]
        items: list[dict[str, Any]] = []
        statuses: list[str] = []
        gaps: list[dict[str, Any]] = []
        lineage_values: list[str] = []
        try:
            for row in selected:
                item, status, item_gaps, lineage_ref = self._project_run(row, cutoff)
                items.append(item)
                statuses.append(status)
                gaps.extend(item_gaps)
                if lineage_ref:
                    lineage_values.append(lineage_ref)
            self._check_deadline(started)
        except Exception:
            return self._unavailable("motherduck-control", "control_query_failed", as_of=cutoff)
        next_cursor = None
        if has_more:
            last = selected[-1]
            next_cursor = _encode_cursor(query, (_utc(last["started_at"]).timestamp(), last["run_id"]))
        return self._envelope(
            source="motherduck-control", status=_worst_status(statuses), reason="pipeline_evidence_composed",
            missing_coverage=gaps, lineage_ref=_opaque_ref("lineage", lineage_values) if lineage_values else None,
            data={"items": items, "next_cursor": next_cursor}, as_of=cutoff,
        )

    def _catalog_records(self, kind: str) -> list[dict[str, Any]]:
        if kind == "object":
            return [self._project_object(item) for item in V2_DATA_OBJECTS]
        path = self.repo_root / "governance" / "catalog" / _CATALOG_KINDS[kind]
        raw_records = tomllib.loads(path.read_text(encoding="utf-8")).get("contracts", [])
        return [self._project_contract(kind, item) for item in raw_records if item.get("status") in _LIFECYCLES]

    def _project_contract(self, kind: str, record: Mapping[str, Any]) -> dict[str, Any]:
        sensitivity = str(record.get("sensitivity", "internal"))
        common = {
            "kind": kind,
            "id": str(record["id"]),
            "version": str(record["version"]),
            "lifecycle": str(record["status"]),
            "sensitivity": sensitivity,
            "contract_hash": _hash(record),
            "details_available": sensitivity != "restricted",
        }
        if sensitivity == "restricted":
            common.pop("contract_hash")
            return common
        common.update({"owner": record.get("owner"), "purpose": _bounded_text(record.get("purpose", record.get("description")))})
        if sensitivity == "confidential":
            return common
        fields = {
            "dataset": ("layer", "grain", "natural_key", "time_semantics", "freshness_slo", "quality_rules", "backup_policy"),
            "metric": ("grain", "formula_ref", "unit", "point_in_time", "quality_gate", "input_dataset_ids"),
            "pipeline": ("output_dataset_ids", "stages", "schedule_policy", "trigger_policy", "activation_state"),
            "macro_series": ("concept", "region", "provider_series_id", "native_frequency", "native_unit", "seasonal_adjustment", "vintage_capability", "source_owner", "rights_note", "attribution", "activation_state"),
            "source": ("region",),
        }[kind]
        for field_name in fields:
            if field_name in record:
                common[field_name] = _bounded_reviewed(record[field_name])
        return common

    def _project_object(self, item: Any) -> dict[str, Any]:
        linked = _DATASET_OBJECT_LINKS.get(item.qualified_name)
        result = {
            "kind": "object", "id": f"object.{item.qualified_name}", "version": "1.0.0",
            "lifecycle": "approved", "sensitivity": item.sensitivity,
            "contract_hash": _hash(item.__dict__), "details_available": item.sensitivity != "restricted",
        }
        if item.sensitivity == "restricted":
            result.pop("contract_hash")
            return result
        if item.sensitivity == "confidential":
            result.update({"purpose": _bounded_text(item.purpose)})
            return result
        result.update({
            "qualified_name": item.qualified_name, "object_type": item.object_type, "layer": item.layer,
            "grain": _bounded_text(item.grain), "key": _bounded_text(item.key),
            "backup_policy": item.backup_policy, "linked_dataset_id": linked,
            "missing_contract_link": linked is None,
        })
        return result

    def _compose_quality(self, dataset_id: str, run_id: str | None, cutoff: datetime) -> tuple[str, list[dict[str, Any]], str | None]:
        if run_id is None:
            return "not_assessed", [{"gap_code": "dataset_wide_coverage_unproven", "gap_count": 1}], None
        runs = self._rows("SELECT * FROM control.pipeline_runs WHERE run_id=?", [run_id])
        if not runs:
            return "not_assessed", [{"gap_code": "run_evidence_missing", "gap_count": 1}], None
        _, status, gaps, lineage_ref = self._project_run(runs[0], cutoff, dataset_id=dataset_id)
        return status, gaps, lineage_ref

    def _project_run(self, run: Mapping[str, Any], cutoff: datetime, *, dataset_id: str | None = None) -> tuple[dict[str, Any], str, list[dict[str, Any]], str | None]:
        run_id = run["run_id"]
        policy = self.policies.get((run["pipeline_id"], run["pipeline_version"]))
        stages = self._rows("""
            SELECT stage_name,status,stage_order FROM control.pipeline_stage_runs
            WHERE run_id=? ORDER BY stage_order,stage_name LIMIT 65
        """, [run_id])
        qualities = self._rows("""
            SELECT dataset_id,rule_id,status,evaluated_at FROM control.quality_results
            WHERE run_id=? ORDER BY dataset_id,rule_id LIMIT 201
        """, [run_id])
        watermarks = self._rows("""
            SELECT watermark_type,updated_at,run_id FROM control.watermarks
            WHERE pipeline_id=? AND partition_key=? ORDER BY watermark_type LIMIT 65
        """, [run["pipeline_id"], run["partition_key"]])
        lineage = self._rows("""
            SELECT transform_id,transform_version,evidence_hash FROM control.lineage_edges
            WHERE run_id=? ORDER BY transform_id,transform_version,evidence_hash LIMIT 201
        """, [run_id])
        definitions = self._rows("""
            SELECT definition_hash,definition FROM control.pipeline_definitions
            WHERE pipeline_id=? AND version=? LIMIT 2
        """, [run["pipeline_id"], run["pipeline_version"]])
        evidence_truncated = any((len(stages) > 64, len(qualities) > 200, len(watermarks) > 64, len(lineage) > 200))
        stages, qualities, watermarks, lineage = stages[:64], qualities[:200], watermarks[:64], lineage[:200]
        definition_hash = definitions[0]["definition_hash"] if definitions else None
        definition = json.loads(definitions[0]["definition"]) if definitions and isinstance(definitions[0]["definition"], str) else (definitions[0]["definition"] if definitions else {})
        source_budget = definition.get("source_call_budget") if isinstance(definition, dict) else None
        gaps: list[dict[str, Any]] = []
        status = "not_assessed"
        stage_names = {row["stage_name"] for row in stages}
        unknown_stage = policy is None or any(row["stage_name"] not in policy.required_stages for row in stages)
        expected_rule_pairs = (
            {(ds, rule) for ds, rules in policy.required_rules.items() for rule in rules}
            if policy else set()
        )
        observed_rule_pairs = {(row["dataset_id"], row["rule_id"]) for row in qualities}
        unknown_rule = policy is None or bool(observed_rule_pairs - expected_rule_pairs)
        unknown_watermark = policy is None or any(
            row["watermark_type"] not in policy.required_watermark_types for row in watermarks
        )
        failed = run["status"] == "failed" or any(row["status"] == "failed" for row in stages) or any(row["status"] == "failed" for row in qualities)
        if failed:
            status = "failed"
        elif (
            policy is None or not policy.complete or run["status"] not in _RUN_TERMINAL
            or unknown_stage or unknown_rule or unknown_watermark or not definition_hash
        ):
            status = "not_assessed"
            gaps.append({"gap_code": "executable_policy_or_terminal_evidence_missing", "gap_count": 1})
        elif evidence_truncated:
            status = "partial"
            gaps.append({"gap_code": "evidence_projection_truncated", "gap_count": 1})
        else:
            missing_stages = set(policy.required_stages) - stage_names
            incomplete_stages = {
                row["stage_name"] for row in stages
                if row["stage_name"] in policy.required_stages and row["status"] != "succeeded"
            }
            required_rules = policy.required_rules.get(dataset_id, ()) if dataset_id else tuple(rule for rules in policy.required_rules.values() for rule in rules)
            observed_rules = {(row["dataset_id"], row["rule_id"]) for row in qualities if row["status"] == "pass"}
            expected_rules = ({(dataset_id, rule) for rule in required_rules} if dataset_id else {(ds, rule) for ds, rules in policy.required_rules.items() for rule in rules})
            watermark_types = {row["watermark_type"] for row in watermarks if row["run_id"] == run_id}
            missing_watermarks = set(policy.required_watermark_types) - watermark_types
            if missing_stages or incomplete_stages or expected_rules - observed_rules or missing_watermarks:
                status = "partial"
                gaps.append({
                    "gap_code": "required_evidence_missing",
                    "gap_count": len(missing_stages) + len(incomplete_stages) + len(expected_rules - observed_rules) + len(missing_watermarks),
                })
            else:
                newest = min((_utc(row["updated_at"]) for row in watermarks), default=None)
                if newest is None:
                    status = "partial"
                    gaps.append({"gap_code": "watermark_missing", "gap_count": 1})
                elif cutoff - newest > policy.freshness:
                    status = "stale"
                elif dataset_id is not None or policy.dataset_wide_coverage:
                    status = "pass"
                else:
                    status = "not_assessed"
                    gaps.append({"gap_code": "dataset_wide_coverage_unproven", "gap_count": 1})
        error_code = run.get("error_code")
        allowed_error = error_code if policy and error_code in policy.allowed_error_codes else None
        if error_code and allowed_error is None and status == "pass":
            status = "not_assessed"
            gaps.append({"gap_code": "unknown_error_code", "gap_count": 1})
        visible_stages = []
        for row in stages:
            known = policy is not None and row["stage_name"] in policy.required_stages
            visible_stages.append({
                "stage_name": row["stage_name"] if known else "redacted",
                "stage_status": row["status"] if row["status"] in {"running", "succeeded", "failed"} else "not_assessed",
            })
        first_failed = next((item["stage_name"] for item in visible_stages if item["stage_status"] == "failed"), None)
        resumable = first_failed or next((item["stage_name"] for item in visible_stages if item["stage_status"] != "succeeded"), None)
        lineage_ref = _opaque_ref("lineage", lineage) if lineage else None
        item = {
            "run_id": run_id, "pipeline_id": run["pipeline_id"], "pipeline_version": run["pipeline_version"],
            "definition_hash": definition_hash, "logical_date": run["logical_date"], "slot": run["slot"],
            "partition_ref": _opaque_ref("partition", run["partition_key"]),
            "execution_state": run["status"] if run["status"] in {"running", "succeeded", "failed"} else "not_assessed",
            "overall_status": status, "source_calls_used": run["source_calls"],
            "source_call_budget": source_budget if isinstance(source_budget, int) else None,
            "stages": visible_stages, "first_failed_stage": first_failed, "resumable_stage": resumable,
            "watermarks": [{
                "watermark_type": row["watermark_type"]
                if policy and row["watermark_type"] in policy.required_watermark_types else "redacted",
                "watermark_status": "present",
            } for row in watermarks],
            "retry_eligible": status == "failed", "resume_eligible": resumable is not None,
            "error_code": allowed_error,
        }
        return item, status, gaps, lineage_ref

    def _rows(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, list(params))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _check_deadline(self, started: float) -> None:
        if time.monotonic() - started > self.deadline_seconds:
            raise TimeoutError("read model deadline exceeded")

    @staticmethod
    def _validate_limit(limit: int, *, maximum: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
            raise ReadModelRequestError("invalid_limit")

    @staticmethod
    def _validate_lookback(days: int) -> None:
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 31:
            raise ReadModelRequestError("invalid_lookback")

    def _unavailable(self, source: str, reason: str, *, as_of: datetime | None = None) -> dict[str, Any]:
        return self._envelope(
            source=source, status=ReadModelStatus.UNAVAILABLE, reason=reason,
            missing_coverage=[{"gap_code": reason, "gap_count": 1}], lineage_ref=None,
            data={"items": [], "next_cursor": None}, as_of=as_of,
        )

    def _envelope(
        self,
        *,
        source: str,
        status: str,
        reason: str,
        missing_coverage: list[dict[str, Any]],
        lineage_ref: str | None,
        data: dict[str, Any],
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        dto = ReadModelEnvelope(
            schema_version="1.0.0",
            as_of=_utc(as_of or self.now()),
            source={"kind": source, "available": status != ReadModelStatus.UNAVAILABLE},
            freshness={
                "status": status if status == ReadModelStatus.STALE else "not_assessed",
                "reason_code": reason,
            },
            quality={"status": str(status), "reason_code": reason},
            missing_coverage=tuple(missing_coverage),
            lineage_ref=lineage_ref,
            request_id=self.request_id(),
            data=data,
        )
        result = dto.to_dict()
        if len(_canonical_json(result).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ReadModelRequestError("response_too_large")
        return result
