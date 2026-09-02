"""Pure alert identity, redaction and deterministic state-transition contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping


ALLOWED_SLOTS = frozenset({"kr-1000", "kr-1430", "kr-1600", "us-close"})
SEVERITY_RANK = {"normal": 0, "watch": 1, "warning": 2, "critical": 3}
PUBLIC_CONTEXT_KEYS = frozenset({
    "presentation_version", "subject_label", "market_label", "asset_type_label", "summary",
    "reason_codes", "change_percent", "sma20_relation", "sma50_relation", "sma120_relation",
    "volume_ratio20", "rsi14", "bollinger_state", "episode_drawdown_percent",
    "portfolio_impact_percent", "unavailable_codes", "source_at", "metric_refs", "quality_status",
})
_SENSITIVE_KEY = re.compile(r"account|cano|token|secret|chat.?id|total.?asset|total.?value", re.I)
_SENSITIVE_TEXT = re.compile(r"account.?number|cano|token|secret|chat.?id", re.I)
_ACCOUNT_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_.:-]{1,79}$")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


class AlertContractError(ValueError):
    """Raised when an alert candidate violates a governed contract."""


@dataclass(frozen=True, slots=True)
class AlertRuleVersion:
    rule_id: str
    version: str
    status: str
    minimum_delivery_severity: str
    delivery_mode: str
    valid_from: datetime
    valid_to: datetime | None
    document: Mapping[str, object]
    definition_hash: str

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "AlertRuleVersion":
        rule_id = str(document["id"])
        version = str(document["version"])
        status = str(document["status"])
        minimum = str(document["minimum_delivery_severity"])
        mode = str(document["delivery_mode"])
        valid_from = document["valid_from"]
        valid_to = document.get("valid_to")
        if not isinstance(valid_from, datetime) or (
            valid_to is not None and not isinstance(valid_to, datetime)
        ):
            raise AlertContractError("rule validity values must be datetime objects")
        _aware(valid_from, "valid_from")
        if valid_to is not None:
            _aware(valid_to, "valid_to")
        if status not in {"approved", "active"}:
            raise AlertContractError("alert rule must be approved or active")
        if minimum not in {"watch", "warning", "critical"}:
            raise AlertContractError("delivery floor must be watch, warning or critical")
        if mode not in {"off", "shadow", "external"}:
            raise AlertContractError("unknown delivery mode")
        if valid_to is not None and valid_to <= valid_from:
            raise AlertContractError("rule valid_to must advance valid_from")
        canonical = {
            **dict(document),
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if valid_to is not None else None,
        }
        return cls(
            rule_id=rule_id,
            version=version,
            status=status,
            minimum_delivery_severity=minimum,
            delivery_mode=mode,
            valid_from=valid_from,
            valid_to=valid_to,
            document=dict(document),
            definition_hash=hashlib.sha256(_json(canonical).encode()).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class AlertEvaluation:
    subject_type: str
    subject_id: str
    evaluation_date: date
    evaluation_slot: str
    session_key: str
    evaluation_at: datetime
    signal_state: str
    severity: str
    state_key: str
    quality_status: str
    input_lineage_hash: str
    public_context: Mapping[str, object]
    evaluation_run_id: str


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    candidate_id: str
    alert_identity: str
    rule: AlertRuleVersion
    evaluation: AlertEvaluation
    state_fingerprint: str

    @classmethod
    def build(cls, rule: AlertRuleVersion, evaluation: AlertEvaluation) -> "AlertCandidate":
        _aware(evaluation.evaluation_at, "evaluation_at")
        if evaluation.evaluation_slot not in ALLOWED_SLOTS:
            raise AlertContractError("evaluation slot is not governed")
        if not evaluation.session_key.strip() or not evaluation.input_lineage_hash.strip():
            raise AlertContractError("session key and input lineage are required")
        if evaluation.signal_state not in {"normal", "active"}:
            raise AlertContractError("signal state must be normal or active")
        if evaluation.severity not in SEVERITY_RANK:
            raise AlertContractError("unknown severity")
        if evaluation.signal_state == "normal" and evaluation.severity != "normal":
            raise AlertContractError("normal state must have normal severity")
        if evaluation.signal_state == "active" and evaluation.severity == "normal":
            raise AlertContractError("active state must have non-normal severity")
        if not (rule.valid_from <= evaluation.evaluation_at):
            raise AlertContractError("rule is not yet valid at evaluation time")
        if rule.valid_to is not None and evaluation.evaluation_at >= rule.valid_to:
            raise AlertContractError("rule is no longer valid at evaluation time")
        cls._validate_public_context(evaluation.public_context)
        alert_identity = _hash(
            "alert-identity-v1", rule.rule_id, rule.version,
            evaluation.subject_type, evaluation.subject_id,
        )
        candidate_id = _hash(
            "alert-candidate-v1", alert_identity, evaluation.session_key, evaluation.evaluation_slot
        )
        state_fingerprint = _hash(
            "alert-state-v1", rule.definition_hash, evaluation.signal_state,
            evaluation.severity, evaluation.state_key,
        )
        return cls(candidate_id, alert_identity, rule, evaluation, state_fingerprint)

    @staticmethod
    def _validate_public_context(context: Mapping[str, object]) -> None:
        unexpected = sorted(set(context) - PUBLIC_CONTEXT_KEYS)
        if unexpected:
            raise AlertContractError(f"public context contains non-allowlisted keys: {unexpected}")
        for key, value in context.items():
            if _SENSITIVE_KEY.search(key):
                raise AlertContractError("public context contains a sensitive key")
            rendered = _json(value)
            if _ACCOUNT_NUMBER.search(rendered) or _SENSITIVE_TEXT.search(rendered):
                raise AlertContractError("public context contains sensitive content")


@dataclass(frozen=True, slots=True)
class CurrentAlertState:
    revision: int
    episode: int
    current_state: str
    current_severity: str
    state_fingerprint: str
    knowledge_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AlertTransition:
    transition_type: str | None
    revision: int
    episode: int
    prior_state: str | None
    current_state: str
    prior_severity: str | None
    current_severity: str
    delivery_required: bool
    delivery_severity: str


def decide_alert_transition(
    candidate: AlertCandidate,
    current: CurrentAlertState | None,
) -> AlertTransition | None:
    evaluation = candidate.evaluation
    if evaluation.quality_status != "pass":
        return None
    floor = SEVERITY_RANK[candidate.rule.minimum_delivery_severity]
    if current is None:
        active = evaluation.signal_state == "active"
        return AlertTransition(
            "entered" if active else "initial_normal", 1, 1 if active else 0,
            None, evaluation.signal_state, None, evaluation.severity,
            active and SEVERITY_RANK[evaluation.severity] >= floor,
            evaluation.severity,
        )
    if (
        current.current_state == evaluation.signal_state
        and current.current_severity == evaluation.severity
        and current.state_fingerprint == candidate.state_fingerprint
    ):
        return None
    revision = current.revision + 1
    episode = current.episode
    delivery = False
    delivery_severity = evaluation.severity
    if current.current_state == "normal" and evaluation.signal_state == "active":
        transition = "reentered" if current.revision > 0 else "entered"
        episode += 1
        delivery = SEVERITY_RANK[evaluation.severity] >= floor
    elif current.current_state == "active" and evaluation.signal_state == "normal":
        transition = "recovered"
        delivery_severity = current.current_severity
        delivery = SEVERITY_RANK[current.current_severity] >= floor
    elif current.current_state == "active" and evaluation.signal_state == "active":
        old_rank = SEVERITY_RANK[current.current_severity]
        new_rank = SEVERITY_RANK[evaluation.severity]
        if new_rank > old_rank:
            transition = "escalated"
            delivery = new_rank >= floor
        elif new_rank < old_rank:
            transition = "deescalated"
        else:
            transition = "updated"
            delivery = new_rank >= floor
    else:
        transition = "initial_normal"
    return AlertTransition(
        transition, revision, episode, current.current_state, evaluation.signal_state,
        current.current_severity, evaluation.severity, delivery, delivery_severity,
    )


def validate_opaque_code(value: str, field: str) -> None:
    if not _SAFE_CODE.fullmatch(value) or _ACCOUNT_NUMBER.search(value):
        raise AlertContractError(f"{field} must be an opaque bounded code")
