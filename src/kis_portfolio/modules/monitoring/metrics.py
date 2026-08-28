"""Infrastructure-free metric contracts and point-in-time evaluation."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable


class FutureMetricInputError(ValueError):
    """Raised when replay would use information unavailable at evaluation time."""


class MetricQualityError(ValueError):
    """Raised when inputs do not satisfy the metric publish gate."""


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    version: str
    status: str
    input_dataset_ids: tuple[str, ...]
    grain: str
    formula_ref: str
    unit: str
    point_in_time: bool
    quality_gate: str
    validation_policy: str
    consumer_ids: tuple[str, ...]
    document: dict[str, object]
    definition_hash: str

    @classmethod
    def from_document(cls, document: dict[str, object]) -> "MetricDefinition":
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return cls(
            metric_id=str(document["id"]),
            version=str(document["version"]),
            status=str(document["status"]),
            input_dataset_ids=tuple(str(item) for item in document["input_dataset_ids"]),
            grain=str(document["grain"]),
            formula_ref=str(document["formula_ref"]),
            unit=str(document["unit"]),
            point_in_time=bool(document["point_in_time"]),
            quality_gate=str(document["quality_gate"]),
            validation_policy=str(document["validation_policy"]),
            consumer_ids=tuple(str(item) for item in document["consumer_ids"]),
            document=dict(document),
            definition_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )


class MetricRegistry:
    def __init__(self, definitions: Iterable[MetricDefinition] = ()) -> None:
        self._definitions: dict[tuple[str, str], MetricDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: MetricDefinition) -> None:
        key = (definition.metric_id, definition.version)
        if definition.status not in {"approved", "active"}:
            raise ValueError(f"metric contract is not approved: {key}")
        if key in self._definitions:
            raise ValueError(f"metric contract already registered: {key}")
        self._definitions[key] = definition

    def get(self, metric_id: str, version: str) -> MetricDefinition:
        try:
            return self._definitions[(metric_id, version)]
        except KeyError as exc:
            raise LookupError(f"unknown metric contract: {(metric_id, version)}") from exc

    def definitions(self) -> tuple[MetricDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))


@dataclass(frozen=True, slots=True)
class MetricInput:
    ref: str
    value: Decimal
    effective_at: datetime
    knowledge_at: datetime
    quality_status: str
    lineage_hash: str

    def __post_init__(self) -> None:
        if not self.ref.strip() or not self.lineage_hash.strip():
            raise ValueError("metric input requires ref and lineage_hash")
        if self.effective_at.tzinfo is None or self.knowledge_at.tzinfo is None:
            raise ValueError("metric input timestamps must be timezone-aware")


MetricFormula = Callable[[tuple[MetricInput, ...]], Decimal]


@dataclass(frozen=True, slots=True)
class RegisteredMetricFormula:
    formula_ref: str
    evaluate: MetricFormula
    implementation_hash: str


class MetricFormulaRegistry:
    def __init__(self) -> None:
        self._formulas: dict[str, RegisteredMetricFormula] = {}

    def register(self, formula_ref: str, formula: MetricFormula) -> None:
        if formula_ref in self._formulas:
            raise ValueError(f"formula already registered: {formula_ref}")
        source = inspect.getsource(formula)
        self._formulas[formula_ref] = RegisteredMetricFormula(
            formula_ref=formula_ref,
            evaluate=formula,
            implementation_hash=hashlib.sha256(source.encode()).hexdigest(),
        )

    def get(self, formula_ref: str) -> RegisteredMetricFormula:
        try:
            return self._formulas[formula_ref]
        except KeyError as exc:
            raise LookupError(f"unknown metric formula: {formula_ref}") from exc


@dataclass(frozen=True, slots=True)
class MetricValue:
    definition: MetricDefinition
    subject_type: str
    subject_id: str
    evaluation_at: datetime
    evaluation_slot: str
    effective_at: datetime
    knowledge_cutoff_at: datetime
    value: Decimal | None
    quality_status: str
    inputs: tuple[MetricInput, ...]
    formula_hash: str
    lineage_hash: str
    evaluation_run_id: str


class PointInTimeMetricEngine:
    def __init__(self, definitions: MetricRegistry, formulas: MetricFormulaRegistry) -> None:
        self.definitions = definitions
        self.formulas = formulas

    def evaluate(
        self,
        *,
        metric_id: str,
        version: str,
        subject_type: str,
        subject_id: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        inputs: Iterable[MetricInput],
        evaluation_run_id: str,
    ) -> MetricValue:
        if evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        definition = self.definitions.get(metric_id, version)
        selected = tuple(inputs)
        if not selected:
            raise MetricQualityError("metric evaluation requires at least one input")
        self._validate_cutoff(definition, evaluation_at, selected)
        non_pass = sorted({item.quality_status for item in selected if item.quality_status != "pass"})
        if non_pass:
            raise MetricQualityError(f"metric input quality gate failed: {','.join(non_pass)}")
        formula = self.formulas.get(definition.formula_ref)
        value = formula.evaluate(selected)
        lineage_hash = self._lineage_hash(definition, formula, selected, "pass")
        return MetricValue(
            definition=definition,
            subject_type=subject_type,
            subject_id=subject_id,
            evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot,
            effective_at=max(item.effective_at for item in selected),
            knowledge_cutoff_at=evaluation_at,
            value=value,
            quality_status="pass",
            inputs=selected,
            formula_hash=formula.implementation_hash,
            lineage_hash=lineage_hash,
            evaluation_run_id=evaluation_run_id,
        )

    def unavailable(
        self,
        *,
        metric_id: str,
        version: str,
        subject_type: str,
        subject_id: str,
        evaluation_at: datetime,
        evaluation_slot: str,
        quality_status: str,
        inputs: Iterable[MetricInput] = (),
        evaluation_run_id: str,
    ) -> MetricValue:
        """Create a replayable evaluation outcome without inventing a numeric value."""
        if evaluation_at.tzinfo is None:
            raise ValueError("evaluation_at must be timezone-aware")
        if not quality_status.strip() or quality_status == "pass":
            raise ValueError("unavailable metric requires an explicit non-pass quality status")
        definition = self.definitions.get(metric_id, version)
        selected = tuple(inputs)
        self._validate_cutoff(definition, evaluation_at, selected)
        formula = self.formulas.get(definition.formula_ref)
        lineage_hash = self._lineage_hash(definition, formula, selected, quality_status)
        return MetricValue(
            definition=definition,
            subject_type=subject_type,
            subject_id=subject_id,
            evaluation_at=evaluation_at,
            evaluation_slot=evaluation_slot,
            effective_at=max((item.effective_at for item in selected), default=evaluation_at),
            knowledge_cutoff_at=evaluation_at,
            value=None,
            quality_status=quality_status,
            inputs=selected,
            formula_hash=formula.implementation_hash,
            lineage_hash=lineage_hash,
            evaluation_run_id=evaluation_run_id,
        )

    @staticmethod
    def _validate_cutoff(
        definition: MetricDefinition,
        evaluation_at: datetime,
        inputs: tuple[MetricInput, ...],
    ) -> None:
        for item in inputs:
            if definition.point_in_time and item.effective_at > evaluation_at:
                raise FutureMetricInputError(f"input effective_at exceeds evaluation cutoff: {item.ref}")
            if definition.point_in_time and item.knowledge_at > evaluation_at:
                raise FutureMetricInputError(f"input knowledge_at exceeds evaluation cutoff: {item.ref}")

    @staticmethod
    def _lineage_hash(
        definition: MetricDefinition,
        formula: RegisteredMetricFormula,
        inputs: tuple[MetricInput, ...],
        quality_status: str,
    ) -> str:
        lineage_payload = {
            "definition_hash": definition.definition_hash,
            "formula_hash": formula.implementation_hash,
            "quality_status": quality_status,
            "inputs": [
                {
                    "ref": item.ref,
                    "effective_at": item.effective_at.isoformat(),
                    "knowledge_at": item.knowledge_at.isoformat(),
                    "lineage_hash": item.lineage_hash,
                }
                for item in sorted(inputs, key=lambda candidate: candidate.ref)
            ],
        }
        return hashlib.sha256(
            json.dumps(lineage_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def sum_decimal_inputs(inputs: tuple[MetricInput, ...]) -> Decimal:
    return sum((item.value for item in inputs), start=Decimal("0"))
