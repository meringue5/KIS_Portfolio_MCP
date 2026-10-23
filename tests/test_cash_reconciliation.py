"""Independent literal oracles from WI-071 design. All monetary inputs are invented."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
import json

import duckdb
import pytest

from kis_portfolio.application.cash_reconciliation_preview import PreviewQuery, read_preview
from kis_portfolio.adapters.outbound.cash_reconciliation_shadow import inspect_stored_cash
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.cash_reconciliation import (
    CashEffect, CashObservation, Coverage, EvaluationHistory, OpeningPending, ReconciliationInput,
    RoundingRule, money, reconcile,
)


T0 = datetime(2026, 10, 12, 1, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
CUTOFF = T1 + timedelta(hours=1)


def inputs(*, opening="100.00", closing="100.00", effects=()):
    def obs(at, amount):
        return CashObservation("ria", "KRW", at, at, money(amount), "settled", "fixture-v1",
                               "independent-synthetic-statement", True, True)
    return ReconciliationInput(
        obs(T1, closing), obs(T0, opening), CUTOFF, effects=effects,
        coverage=tuple(Coverage("ria", "KRW", s, T0, T1, CUTOFF, True, True, "source-proof", True)
                       for s in ("trade", "charges")),
        opening_pending=OpeningPending("ria", "KRW", T0, T0, True, "opening-obligations"),
        rounding=RoundingRule("KRW", 2, "half_even", "aggregate", "synthetic-rounding-only", "fixture-v1", T0),
    )


def effect(amount="-20.25", *, identity="buy-net", revision=1, posted=T0 + timedelta(hours=2), known=T1):
    return CashEffect(identity, "ria", "KRW", "trade", revision, known, money(amount), posted,
                      "independent-posting", True, True, ("embedded-fee",))


@pytest.mark.parametrize("opening,closing,effects,expected,delta,outcome", [
    ("100.00", "100.00", (), "100.00", "0.00", "reconciled"),
    ("100.00", "79.75", (effect(),), "79.75", "0.00", "reconciled"),
    ("100.00", "119.75", (effect("19.75"),), "119.75", "0.00", "reconciled"),
    ("100.00", "150.00", (effect("20.00"),), "120.00", "30.00", "unexplained_movement"),
    ("0.00", "0.00", (), "0.00", "0.00", "reconciled"),
    ("-10.00", "-10.00", (), "-10.00", "0.00", "reconciled"),
    # Unobserved equal/opposite external flows cannot be discovered or certified by net zero.
    ("100.00", "100.00", (), "100.00", "0.00", "reconciled"),
])
def test_independent_literal_oracles(opening, closing, effects, expected, delta, outcome):
    data = inputs(opening=opening, closing=closing, effects=effects)
    result = reconcile(data)
    assert (result.expected, result.delta, result.outcome) == (Decimal(expected), Decimal(delta), outcome)
    history = EvaluationHistory()
    history.append(result)
    row = read_preview(history, query())["data"][0]
    assert row["performance_eligible"] is False
    assert row["external_flow_coverage"] == "not_assessed"
    assert "quality" not in row and "cash_flow_event" not in row


def query(**changes):
    return replace(PreviewQuery("ria", "KRW", T0, T1, CUTOFF), **changes)


@pytest.mark.parametrize("change,reason", [
    ({"opening_pending": None}, "opening_pending_unverified"),
    ({"coverage": ()}, "required_source_coverage_gap"),
    ({"rounding": None}, "rounding_unverified"),
    ({"rounding": RoundingRule("USD", 2, "half_even", "aggregate", "proof")}, "rounding_unverified"),
])
def test_required_evidence_never_falls_back(change, reason):
    result = reconcile(replace(inputs(), **change))
    assert result.outcome == "deferred" and reason in result.reasons
    assert (result.observed, result.expected, result.delta) == (None, None, None)


@pytest.mark.parametrize("change,reason", [
    ({"basis": "valuation_residual"}, "settled_basis_unverified"),
    ({"basis": "withdrawable"}, "settled_basis_unverified"),
    ({"verified": False}, "settled_basis_unverified"),
    ({"fresh": False}, "cash_stale"),
    ({"fresh": None}, "cash_freshness_unverified"),
    ({"amount": None}, "cash_missing"),
    ({"known_at": CUTOFF + timedelta(seconds=1)}, "cash_not_known_at_cutoff"),
    ({"basis_version": "new-version"}, "cash_basis_changed"),
])
def test_observation_gate_and_no_clipping(change, reason):
    data = inputs()
    result = reconcile(replace(data, closing=replace(data.closing, **change)))
    assert result.outcome == "deferred" and reason in result.reasons
    assert result.delta is None


def test_first_compatible_observation_only_and_pending_before_t0():
    data = inputs(closing="79.75", effects=(effect(),))
    assert reconcile(replace(data, opening=None)).outcome == "baseline_only"
    # No executed-at filter: an obligation from before t0 must still post inside (t0,t1].
    assert reconcile(data).expected == Decimal("79.75")
    # The same effect included at the opening boundary is never posted twice.
    assert reconcile(replace(data, effects=(effect(posted=T0),))).expected == Decimal("100.00")
    assert reconcile(replace(data, effects=(effect(posted=T1),))).expected == Decimal("79.75")
    after = effect(posted=T1 + timedelta(minutes=1), known=CUTOFF)
    assert reconcile(replace(data, effects=(after,))).expected == Decimal("100.00")


def test_date_only_holiday_or_unresolved_pending_never_becomes_midnight_posting():
    result = reconcile(inputs(effects=(effect(posted=None),)))
    assert result.outcome == "pending_settlement" and result.pending_count == 1
    assert result.expected is result.delta is None
    data = inputs(effects=(effect(known=T0, posted=T1),))
    assert "posting_evidence_inconsistent" in reconcile(data).reasons


def test_net_fee_double_count_is_rejected_not_subtracted_twice():
    standalone = replace(effect("-0.25", identity="embedded-fee"), source="charges", included_effect_ids=())
    result = reconcile(inputs(closing="79.75", effects=(effect(), standalone)))
    assert result.outcome == "deferred" and "cash_effect_double_count" in result.reasons
    assert result.expected is None


def test_alias_replay_distinct_orders_and_conflicting_revisions():
    same = effect()
    assert reconcile(inputs(closing="79.75", effects=(same, same))).expected == Decimal("79.75")
    assert reconcile(inputs(effects=(same, same))).input_hash == reconcile(inputs(effects=(same,))).input_hash
    separate = replace(same, canonical_id="independent-order", included_effect_ids=("independent-fee",))
    assert reconcile(inputs(effects=(same, separate))).expected == Decimal("59.50")
    ambiguous = replace(same, identity_verified=False)
    assert "cash_effect_unverified" in reconcile(inputs(effects=(ambiguous,))).reasons
    conflict = replace(same, amount=Decimal("-21.25"))
    newer = replace(same, revision=2)
    for sequence in ((same, conflict, newer), (newer, conflict, same)):
        assert "conflicting_effect_revision" in reconcile(inputs(effects=sequence)).reasons


def test_coverage_union_gap_wrong_scope_and_late_proof():
    data = inputs()
    split = T0 + timedelta(hours=12)
    left = replace(data.coverage[0], end=split)
    right = replace(left, start=split, end=T1)
    assert reconcile(replace(data, coverage=(left, right, data.coverage[1]))).outcome == "reconciled"
    for proof in (replace(right, start=split + timedelta(seconds=1)),
                  replace(right, currency="USD"), replace(right, pagination_complete=False),
                  replace(right, posting_complete=False),
                  replace(right, known_at=CUTOFF + timedelta(seconds=1))):
        assert "required_source_coverage_gap" in reconcile(replace(data, coverage=(left, proof, data.coverage[1]))).reasons
    with pytest.raises(ValueError, match="required_sources"):
        reconcile(replace(data, required_sources=("trade",)))


def test_late_source_correction_pit_replay_and_revision_history():
    base = inputs(closing="78.75", effects=(effect(),))
    late = replace(effect("-21.25", revision=2), known_at=CUTOFF + timedelta(hours=1))
    history = EvaluationHistory()
    old = history.append(reconcile(replace(base, effects=(late, effect()))))
    assert old.result.expected == Decimal("79.75")
    assert old.result.input_hash == reconcile(base).input_hash
    assert history.append(reconcile(replace(base, effects=(effect(), late)))) is old
    revised = history.append(reconcile(replace(base, effects=(effect(), late), knowledge_cutoff=late.known_at)))
    assert revised.revision == 2 and revised.result.expected == Decimal("78.75")
    assert read_preview(history, query())["data"][0]["expected"] == "79.75"
    assert read_preview(history, query(knowledge_cutoff=late.known_at))["data"][0]["expected"] == "78.75"
    assert old.result.expected == Decimal("79.75")
    partial = replace(base, effects=(late,), coverage=())
    assert reconcile(partial).expected is None


@pytest.mark.parametrize("stage,mode,amount,expected", [
    ("aggregate", "half_even", "-0.005", "99.99"),
    ("per_effect", "half_even", "-0.005", "100.00"),
    ("per_effect", "half_up", "-0.005", "99.98"),
    ("aggregate", "down", "-0.004", "99.99"),
])
def test_explicit_source_rounding_is_exact_and_context_independent(stage, mode, amount, expected):
    one = replace(effect(amount), included_effect_ids=())
    two = replace(one, canonical_id="second")
    data = inputs(effects=(one, two))
    data = replace(data, rounding=replace(data.rounding, stage=stage, mode=mode))
    with localcontext() as ctx:
        ctx.prec = 6
        result = reconcile(data)
    assert result.expected == Decimal(expected)
    assert result.delta == Decimal("100.00") - Decimal(expected)


@pytest.mark.parametrize("bad", ["", " 0", "NaN", "Infinity", "1e-3", "1.123456789", "100000000000000000000", 0.1])
def test_invalid_monetary_lexemes_rejected_without_values_in_errors(bad):
    with pytest.raises(ValueError, match="invalid_decimal|decimal_out_of_range"):
        money(bad)


def test_precision_overflow_and_read_range_errors():
    data = inputs(closing="100.001")
    assert "cash_precision_mismatch" in reconcile(data).reasons
    data = inputs(opening="99999999999999999999.00", effects=(effect("2.00"),))
    assert "calculation_overflow" in reconcile(data).reasons
    for q in (query(limit=101), query(start=T0 - timedelta(days=32)), query(currency="usd"),
              query(start=T0.replace(tzinfo=None)), query(cursor="private-raw-URI")):
        with pytest.raises(ValueError):
            read_preview(EvaluationHistory(), q)


def test_rounding_evidence_is_bound_to_basis_and_knowledge_cutoff():
    data = inputs()
    for rule in (replace(data.rounding, basis_version="different-basis"),
                 replace(data.rounding, known_at=CUTOFF + timedelta(seconds=1))):
        result = reconcile(replace(data, rounding=rule))
        assert result.expected is None and "rounding_unverified" in result.reasons


def test_native_currency_effects_cannot_be_mixed_or_converted():
    data = inputs(effects=(replace(effect(), currency="USD"),))
    with pytest.raises(ValueError, match="effect_scope_mismatch"):
        reconcile(data)
    usd = replace(inputs(closing="79.75", effects=(effect(),)),
                  closing=replace(inputs(closing="79.75").closing, currency="USD"),
                  opening=replace(inputs().opening, currency="USD"),
                  effects=(replace(effect(), currency="USD"),),
                  coverage=tuple(replace(p, currency="USD") for p in inputs().coverage),
                  opening_pending=replace(inputs().opening_pending, currency="USD"),
                  rounding=replace(inputs().rounding, currency="USD"))
    assert reconcile(usd).expected == Decimal("79.75")


def test_input_budget_and_invalid_revision_are_explicit_errors():
    with pytest.raises(ValueError, match="input_budget_exceeded"):
        reconcile(inputs(effects=(effect(),) * 10001))
    with pytest.raises(ValueError, match="invalid_effect_revision"):
        reconcile(inputs(effects=(replace(effect(), revision=0),)))


def test_bounded_projection_paging_binding_and_private_field_suppression():
    history = EvaluationHistory()
    data = inputs()
    first = reconcile(data)
    history.append(first)
    history.append(replace(first, t1=T1 + timedelta(minutes=1), input_hash="second-input"))
    q = query(end=CUTOFF, limit=1)
    page = read_preview(history, q)
    assert page["next_cursor"]
    second = read_preview(history, replace(q, cursor=page["next_cursor"]))
    assert second["next_cursor"] is None
    serialized = json.dumps(page)
    for private in ("independent-synthetic-statement", "source-proof", "opening-obligations", "raw_json", "account_id"):
        assert private not in serialized
    with pytest.raises(ValueError, match="cursor"):
        read_preview(history, replace(q, account_alias="isa", cursor=page["next_cursor"]))
    history.append(replace(first, input_hash="new-evaluation"))
    with pytest.raises(ValueError, match="cursor"):
        read_preview(history, replace(q, cursor=page["next_cursor"]))


def test_stored_reader_never_attests_numeric_cash_or_mutates_source():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("INSERT INTO silver.accounts VALUES ('private-account','ria','REAL','KRW',?,NULL,'{}')", [T0])
    for index, ts in enumerate((T0, T1)):
        con.execute("""INSERT INTO bronze.source_observations
            (observation_id,dataset_id,source_id,source_record_id,idempotency_key,observed_at,fetched_at,
             content_hash,quality_status,payload,created_at)
            VALUES (?, 'dataset.portfolio-position-observation','source.kis-open-api',?,?,?,?,'hash','pass','{}',?)
        """, [f"obs{index}", f"private-record{index}", f"key{index}", ts, ts, ts])
        con.execute("INSERT INTO silver.cash_snapshots VALUES ('private-account','KRW',?,100,?,'pass')",
                    [ts, f"obs{index}"])
    before = con.execute("SELECT count(*),bit_xor(hash(t)) FROM silver.cash_snapshots t").fetchone()
    class SelectOnly:
        def execute(self, sql, args):
            assert sql.strip().upper().startswith("SELECT")
            return con.execute(sql, args)
    result = inspect_stored_cash(SelectOnly(), "ria", "KRW", cutoff=CUTOFF).rows[0].result
    assert result.outcome == "deferred" and result.delta is result.observed is None
    assert "settled_basis_unverified" in result.reasons
    unsupported = inspect_stored_cash(con, "isa", "USD", cutoff=CUTOFF).rows[0].result
    assert unsupported.outcome == "deferred" and "account_currency_unsupported" in unsupported.reasons
    assert before == con.execute("SELECT count(*),bit_xor(hash(t)) FROM silver.cash_snapshots t").fetchone()
    con.execute("INSERT INTO silver.cash_snapshots VALUES ('private-account','JPY',?,100,'obs0','pass')", [T0])
    unexpected = inspect_stored_cash(con, "ria", "JPY", cutoff=CUTOFF).rows[0].result
    assert "account_currency_unsupported" in unexpected.reasons and unexpected.delta is None
    # A backdated observation imported after the PIT cutoff must not be visible.
    con.execute("UPDATE bronze.source_observations SET created_at=?", [CUTOFF + timedelta(days=1)])
    assert "cash_missing" in inspect_stored_cash(con, "ria", "KRW", cutoff=CUTOFF).rows[0].result.reasons
    con.close()
