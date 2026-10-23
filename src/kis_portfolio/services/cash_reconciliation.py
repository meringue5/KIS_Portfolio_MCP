"""WI-071 isolated diagnostic evaluator. No DB, network, cash writer or MCP imports.

Attestations are supplied by a reviewed input adapter, never inferred from amounts.
Production stored-input adapters currently attest no numeric-ready scope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
import hashlib
import json
import re


FORMULA_VERSION = "cash-reconciliation-0.1.0"
ACCOUNTS = frozenset({"ria", "isa", "brokerage", "irp", "pension"})
ROUNDING_MODES = {"half_even": ROUND_HALF_EVEN, "half_up": ROUND_HALF_UP, "down": ROUND_DOWN}


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


def money(value: str | Decimal) -> Decimal:
    """Strict native DECIMAL(28,8) input; unknown is None at the caller, never zero."""
    if not isinstance(value, (str, Decimal)) or (
        isinstance(value, str) and not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value)
    ):
        raise ValueError("invalid_decimal")
    number = Decimal(value)
    if not number.is_finite() or number.as_tuple().exponent < -8 or number.copy_abs() >= Decimal("1e20"):
        raise ValueError("decimal_out_of_range")
    return number


def _scope(account: str, currency: str) -> None:
    if account not in ACCOUNTS or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("invalid_scope")


def _hash(value: object) -> str:
    def encode(item):
        if isinstance(item, datetime):
            return aware(item).isoformat()
        if isinstance(item, Decimal):
            return format(item, "f")
        raise TypeError("unsupported_hash_input")
    return hashlib.sha256(json.dumps(value, default=encode, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class CashObservation:
    account_alias: str
    currency: str
    observed_at: datetime
    known_at: datetime
    amount: Decimal | None = field(repr=False)
    basis: str = "unknown"
    basis_version: str = "unknown"
    evidence_ref: str = field(default="", repr=False)
    verified: bool = False
    fresh: bool | None = None


@dataclass(frozen=True)
class CashEffect:
    canonical_id: str = field(repr=False)
    account_alias: str
    currency: str
    source: str
    revision: int
    known_at: datetime
    amount: Decimal = field(repr=False)
    posted_at: datetime | None = None
    # None is uncertain posting, even when settlement date is known. No midnight synthesis.
    evidence_ref: str = field(default="", repr=False)
    identity_verified: bool = False
    amount_verified: bool = False
    # Includes any embedded fee/tax effect ids; separate effects may not consume them again.
    included_effect_ids: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class Coverage:
    account_alias: str
    currency: str
    source: str
    start: datetime
    end: datetime
    known_at: datetime
    complete: bool
    pagination_complete: bool
    evidence_ref: str = field(repr=False)
    # Separate from successful source-date collection or WI-063 execution coverage.
    posting_complete: bool = False


@dataclass(frozen=True)
class OpeningPending:
    account_alias: str
    currency: str
    as_of: datetime
    known_at: datetime
    complete: bool
    evidence_ref: str = field(repr=False)


@dataclass(frozen=True)
class RoundingRule:
    currency: str
    scale: int
    mode: str
    stage: str  # aggregate or per_effect, source-confirmed; never guessed by currency
    evidence_ref: str = field(repr=False)
    basis_version: str = ""
    known_at: datetime | None = None


@dataclass(frozen=True)
class ReconciliationInput:
    closing: CashObservation
    opening: CashObservation | None
    knowledge_cutoff: datetime
    effects: tuple[CashEffect, ...] = ()
    coverage: tuple[Coverage, ...] = ()
    opening_pending: OpeningPending | None = None
    rounding: RoundingRule | None = None
    required_sources: tuple[str, ...] = ("trade", "charges")


@dataclass(frozen=True)
class ReconciliationResult:
    account_alias: str
    currency: str
    t0: datetime | None
    t1: datetime
    knowledge_cutoff: datetime
    outcome: str
    reasons: tuple[str, ...]
    observed: Decimal | None = field(repr=False)
    expected: Decimal | None = field(repr=False)
    delta: Decimal | None = field(repr=False)
    explained_count: int
    pending_count: int
    input_hash: str
    formula_version: str = FORMULA_VERSION


def _covered(proofs: tuple[Coverage, ...], source: str, start: datetime, end: datetime,
             account: str, currency: str, cutoff: datetime) -> bool:
    intervals = sorted((aware(p.start), aware(p.end)) for p in proofs
                       if (p.account_alias, p.currency, p.source) == (account, currency, source)
                       and aware(p.known_at) <= cutoff and p.complete is True
                       and p.pagination_complete is True and p.posting_complete is True
                       and p.evidence_ref and aware(p.start) <= aware(p.end) <= aware(p.known_at))
    cursor = start
    for lower, upper in intervals:
        if lower > cursor:
            break
        cursor = max(cursor, upper)
        if cursor >= end:
            return True
    return False


def reconcile(inputs: ReconciliationInput) -> ReconciliationResult:
    end, start = inputs.closing, inputs.opening
    _scope(end.account_alias, end.currency)
    cutoff, t1 = aware(inputs.knowledge_cutoff), aware(end.observed_at)
    t0 = aware(start.observed_at) if start else None
    if t1 > cutoff or (start and (start.account_alias, start.currency) != (end.account_alias, end.currency)):
        raise ValueError("invalid_observation_interval")
    if t0 is not None and not t0 < t1 <= t0 + timedelta(days=31):
        raise ValueError("invalid_observation_interval")
    if (not {"trade", "charges"}.issubset(inputs.required_sources)
            or len(set(inputs.required_sources)) != len(inputs.required_sources)):
        raise ValueError("required_sources_missing_or_duplicated")
    if len(inputs.effects) > 10000 or len(inputs.coverage) > 10000:
        raise ValueError("input_budget_exceeded")
    # Order-independent identity: unordered row retrieval must not create new revisions.
    content = asdict(inputs)
    content["effects"] = [asdict(e) for e in inputs.effects if aware(e.known_at) <= cutoff]
    content["coverage"] = [asdict(p) for p in inputs.coverage if aware(p.known_at) <= cutoff]
    if inputs.opening_pending and aware(inputs.opening_pending.known_at) > cutoff:
        content["opening_pending"] = None
    if inputs.rounding and (inputs.rounding.known_at is None or aware(inputs.rounding.known_at) > cutoff):
        content["rounding"] = None
    for name in ("effects", "coverage"):
        unique = {_hash(item): item for item in content[name]}
        content[name] = [unique[key] for key in sorted(unique)]
    fingerprint = _hash({"formula": FORMULA_VERSION, "inputs": content})

    def result(outcome, reasons=(), observed=None, expected=None, delta=None, count=0, pending=0):
        return ReconciliationResult(end.account_alias, end.currency, t0, t1, cutoff, outcome,
                                    tuple(sorted(set(reasons))), observed, expected, delta, count, pending, fingerprint)

    gaps = []
    for observation in (start, end):
        if observation is None:
            continue
        if observation.amount is None:
            gaps.append("cash_missing")
        else:
            money(observation.amount)
        if observation.basis != "settled" or observation.verified is not True or not observation.evidence_ref:
            gaps.append("settled_basis_unverified")
        if observation.basis == "unsupported":
            gaps.append("account_currency_unsupported")
        if not observation.basis_version or observation.basis_version == "unknown":
            gaps.append("cash_basis_unversioned")
        if observation.fresh is False:
            gaps.append("cash_stale")
        elif observation.fresh is not True:
            gaps.append("cash_freshness_unverified")
        if aware(observation.known_at) > cutoff:
            gaps.append("cash_not_known_at_cutoff")
        if aware(observation.known_at) < aware(observation.observed_at):
            gaps.append("cash_time_inconsistent")
    if gaps:
        return result("deferred", gaps)
    if start is None:
        return result("baseline_only", ("compatible_opening_missing",))
    if start.basis_version != end.basis_version or not end.basis_version or end.basis_version == "unknown":
        return result("deferred", ("cash_basis_changed",))

    for source in inputs.required_sources:
        if not _covered(inputs.coverage, source, t0, t1, end.account_alias, end.currency, cutoff):
            gaps.append("required_source_coverage_gap")
    pending_proof = inputs.opening_pending
    if not (pending_proof and pending_proof.complete is True and pending_proof.evidence_ref
            and (pending_proof.account_alias, pending_proof.currency) == (end.account_alias, end.currency)
            and aware(pending_proof.as_of) == t0 <= aware(pending_proof.known_at) <= cutoff):
        gaps.append("opening_pending_unverified")
    rule = inputs.rounding
    if not (rule and rule.evidence_ref and rule.currency == end.currency
            and rule.basis_version == end.basis_version and rule.known_at is not None
            and aware(rule.known_at) <= cutoff
            and type(rule.scale) is int and 0 <= rule.scale <= 8
            and rule.mode in ROUNDING_MODES and rule.stage in {"aggregate", "per_effect"}):
        gaps.append("rounding_unverified")

    selected: dict[str, CashEffect] = {}
    revisions: dict[tuple[str, int], CashEffect] = {}
    for effect in inputs.effects:
        if (effect.account_alias, effect.currency) != (end.account_alias, end.currency):
            raise ValueError("effect_scope_mismatch")
        if aware(effect.known_at) > cutoff:
            continue
        money(effect.amount)
        if type(effect.revision) is not int or effect.revision < 1 or not effect.canonical_id:
            raise ValueError("invalid_effect_revision")
        revision_key = (effect.canonical_id, effect.revision)
        if revision_key in revisions and effect != revisions[revision_key]:
            gaps.append("conflicting_effect_revision")
        revisions[revision_key] = effect
        previous = selected.get(effect.canonical_id)
        if previous is None or effect.revision > previous.revision:
            selected[effect.canonical_id] = effect

    posted = []
    pending = 0
    used: set[str] = set()
    for effect in selected.values():
        if effect.identity_verified is not True or effect.amount_verified is not True or not effect.evidence_ref:
            gaps.append("cash_effect_unverified")
        if effect.posted_at is None:
            pending += 1
            continue
        if aware(effect.posted_at) > aware(effect.known_at):
            gaps.append("posting_evidence_inconsistent")
        if not t0 < aware(effect.posted_at) <= t1:
            continue
        identities = set(effect.included_effect_ids) | {effect.canonical_id}
        if used & identities:
            gaps.append("cash_effect_double_count")
        used.update(identities)
        posted.append(effect)
    if gaps:
        return result("deferred", gaps, pending=pending)
    if pending:
        return result("pending_settlement", ("posting_time_unknown",), pending=pending)
    # Precision is local, not inherited from an ambient caller's Decimal context.
    with localcontext(Context(prec=80)):
        quantum = Decimal(1).scaleb(-rule.scale)
        rounding = ROUNDING_MODES[rule.mode]
        if any(o.amount != o.amount.quantize(quantum, rounding=rounding) for o in (start, end)):
            return result("deferred", ("cash_precision_mismatch",))
        amounts = [p.amount.quantize(quantum, rounding=rounding) if rule.stage == "per_effect" else p.amount
                   for p in posted]
        expected = (start.amount + sum(amounts, Decimal(0))).quantize(quantum, rounding=rounding)
        delta = end.amount - expected
        if abs(expected) >= Decimal("1e20") or abs(delta) >= Decimal("1e20"):
            return result("deferred", ("calculation_overflow",))
    return result("reconciled" if delta == 0 else "unexplained_movement",
                  observed=end.amount, expected=expected, delta=delta, count=len(posted))


@dataclass(frozen=True)
class EvaluationRevision:
    revision: int
    result: ReconciliationResult


class EvaluationHistory:
    """Ephemeral isolated evidence only; no monetary writer or production persistence."""

    def __init__(self):
        self._rows: list[EvaluationRevision] = []

    def append(self, result: ReconciliationResult) -> EvaluationRevision:
        interval = (result.account_alias, result.currency, result.t0, result.t1)
        matching = [r for r in self._rows if (r.result.account_alias, r.result.currency,
                                              r.result.t0, r.result.t1) == interval]
        for row in matching:
            if row.result.input_hash == result.input_hash:
                return row
        row = EvaluationRevision(len(matching) + 1, result)
        self._rows.append(row)
        return row

    @property
    def rows(self) -> tuple[EvaluationRevision, ...]:
        return tuple(self._rows)
