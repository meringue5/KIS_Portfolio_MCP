import json
from datetime import date, timedelta

import pytest

from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.adapters.batch import cli as batch_cli
from kis_portfolio.services.trade_cash_backfill import (
    CALLABLE,
    DOMESTIC_CASH_HISTORY,
    DOMESTIC_ORDER_HISTORY,
    KNOWN_GAP,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillAccountScope,
    BackfillBudgetError,
    BackfillBudgetExceeded,
    BackfillBudgetPolicy,
    BackfillCallBudget,
    account_scopes_from_registry,
    apply_call_budget,
    plan_trade_cash_backfill,
    run_budgeted_physical_call,
    three_year_start,
)


END = date(2026, 8, 28)
START = date(2023, 8, 28)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _ranges(partitions):
    return sorted((item.start_date, item.end_date) for item in partitions)


def _assert_exact_coverage(partitions, start_date=START, end_date=END):
    ranges = _ranges(partitions)
    assert ranges[0][0] == start_date
    assert ranges[-1][1] == end_date
    for (_, previous_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert next_start == previous_end + timedelta(days=1)


def test_three_year_planner_is_deterministic_bounded_and_complete():
    scopes = [
        BackfillAccountScope("brokerage", "01", overseas_exchanges=("NAS",)),
        BackfillAccountScope("ria", "01"),
    ]

    first = plan_trade_cash_backfill(scopes, start_date=START, end_date=END, as_of_date=END)
    second = plan_trade_cash_backfill(reversed(scopes), start_date=START, end_date=END, as_of_date=END)

    assert first.plan_hash == second.plan_hash
    assert first.partitions == second.partitions
    assert len({item.key for item in first.partitions}) == len(first.partitions)
    assert all(item.calendar_days <= 60 for item in first.callable_partitions)
    assert first.public_dict()["budget_enforced"] is False
    assert first.public_dict()["side_effects"] == "none"

    domestic = [
        item for item in first.callable_partitions
        if item.account_label == "brokerage" and item.source_operation == DOMESTIC_ORDER_HISTORY
    ]
    overseas_orders = [
        item for item in first.callable_partitions
        if item.source_operation == OVERSEAS_ORDER_HISTORY
    ]
    overseas_transactions = [
        item for item in first.callable_partitions
        if item.source_operation == OVERSEAS_TRANSACTION_HISTORY
    ]
    _assert_exact_coverage(domestic)
    _assert_exact_coverage(overseas_orders)
    _assert_exact_coverage(overseas_transactions)


def test_domestic_partitions_never_cross_old_recent_route_boundary():
    cutoff = END - timedelta(days=90)
    plan = plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=START,
        end_date=END,
        as_of_date=END,
    )
    orders = [item for item in plan.partitions if item.source_operation == DOMESTIC_ORDER_HISTORY]

    assert any(item.source_route == "old" for item in orders)
    assert any(item.source_route == "recent" for item in orders)
    assert all(item.end_date < cutoff for item in orders if item.source_route == "old")
    assert all(item.start_date >= cutoff for item in orders if item.source_route == "recent")
    _assert_exact_coverage(orders)


def test_irp_recent_and_domestic_cash_sources_are_explicit_known_gaps():
    cutoff = END - timedelta(days=90)
    plan = plan_trade_cash_backfill(
        [BackfillAccountScope("irp", "29")],
        start_date=START,
        end_date=END,
        as_of_date=END,
    )
    recent = [
        item for item in plan.known_gaps
        if item.source_operation == DOMESTIC_ORDER_HISTORY
    ]
    cash = [
        item for item in plan.known_gaps
        if item.source_operation == DOMESTIC_CASH_HISTORY
    ]

    assert len(recent) == 1
    assert recent[0].start_date == cutoff
    assert recent[0].end_date == END
    assert recent[0].gap_reason == "irp_recent_history_endpoint_unavailable"
    assert len(cash) == 1
    assert cash[0].start_date == START
    assert cash[0].end_date == END
    assert cash[0].gap_reason == "no_selected_domestic_cash_transaction_history_source"
    assert all(item.disposition == KNOWN_GAP for item in recent + cash)
    assert all(item.public_dict()["source_page_cap"] == 0 for item in recent + cash)


def test_registry_projection_drops_credentials_and_limits_overseas_scope():
    accounts = [
        AccountConfig("ria", "RIA", "RIA", "key-ria", "secret-ria", "12345678", "01"),
        AccountConfig(
            "brokerage", "BROKERAGE", "Brokerage", "key-b", "secret-b", "87654321", "01",
        ),
    ]
    scopes = account_scopes_from_registry(
        accounts,
        overseas_account_labels=("brokerage",),
        overseas_exchanges=("NYS", "NAS", "NAS"),
    )
    plan = plan_trade_cash_backfill(scopes, start_date=START, end_date=END, as_of_date=END)
    serialized = str(plan.public_dict())

    assert [scope.label for scope in scopes] == ["brokerage", "ria"]
    assert scopes[0].overseas_exchanges == ("NAS", "NYS")
    assert not scopes[1].overseas_exchanges
    assert "12345678" not in serialized
    assert "87654321" not in serialized
    assert "secret-ria" not in serialized
    assert "secret-b" not in serialized
    assert {
        item.account_label for item in plan.partitions
        if item.source_operation in {OVERSEAS_ORDER_HISTORY, OVERSEAS_TRANSACTION_HISTORY}
    } == {"brokerage"}


def test_partition_identity_changes_with_public_source_capability():
    real = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "01", "REAL")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    pension = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "22", "REAL")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    virtual = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "01", "VIRTUAL")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )

    assert real.plan_hash != pension.plan_hash
    assert real.plan_hash != virtual.plan_hash
    assert real.partitions[0].key != pension.partitions[0].key
    assert real.partitions[0].key != virtual.partitions[0].key


def test_virtual_overseas_period_transactions_are_a_named_gap():
    plan = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "01", "VIRTUAL", ("NAS",))],
        start_date=date(2026, 8, 1),
        end_date=END,
        as_of_date=END,
    )
    transactions = [
        item for item in plan.partitions
        if item.source_operation == OVERSEAS_TRANSACTION_HISTORY
    ]

    assert transactions
    assert all(item.disposition == KNOWN_GAP for item in transactions)
    assert {item.gap_reason for item in transactions} == {
        "overseas_period_transaction_virtual_support_unverified"
    }
    assert all(item.disposition == CALLABLE for item in plan.partitions if item.source_operation == OVERSEAS_ORDER_HISTORY)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start_date": date(2026, 8, 29)}, "start_date"),
        ({"start_date": date(2023, 8, 27)}, "three calendar years"),
        ({"as_of_date": date(2026, 8, 27)}, "as_of_date"),
        ({"partition_days": 0}, "partition_days"),
        ({"partition_days": 91}, "partition_days"),
    ],
)
def test_planner_rejects_unbounded_or_invalid_windows(kwargs, message):
    arguments = {
        "start_date": START,
        "end_date": END,
        "as_of_date": END,
        **kwargs,
    }
    with pytest.raises(ValueError, match=message):
        plan_trade_cash_backfill([BackfillAccountScope("ria", "01")], **arguments)


@pytest.mark.parametrize(
    "scope",
    [
        BackfillAccountScope("bad|label", "01"),
        BackfillAccountScope("ria", ""),
        BackfillAccountScope("brokerage", "01", overseas_exchanges=("N|AS",)),
    ],
)
def test_planner_rejects_unsafe_partition_identity_tokens(scope):
    with pytest.raises(ValueError, match="invalid"):
        plan_trade_cash_backfill([scope], start_date=END, end_date=END, as_of_date=END)


def test_exact_three_year_default_clamps_leap_day():
    assert three_year_start(date(2024, 2, 29)) == date(2021, 2, 28)
    plan = plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        end_date=END,
        as_of_date=END,
    )
    assert plan.start_date == START


def test_batch_command_prints_public_read_only_plan(monkeypatch, capsys):
    account = AccountConfig(
        "brokerage", "BROKERAGE", "Brokerage", "app-key", "app-secret", "12345678", "01",
    )
    monkeypatch.setattr(batch_cli, "load_account_registry", lambda: [account])
    args = batch_cli.build_parser().parse_args([
        "plan-trade-cash-backfill-v2",
        "--start-date", "20230828",
        "--end-date", "20260828",
        "--as-of-date", "20260828",
    ])

    assert batch_cli._run_trade_cash_backfill_plan(args) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "budgeted"
    assert result["side_effects"] == "none"
    assert result["budget_enforced"] is True
    assert result["reserved_call_ceiling"] == 152
    assert result["call_headroom"] == 248
    assert "12345678" not in output
    assert "app-secret" not in output


def test_batch_command_fails_before_output_when_global_budget_is_too_small(monkeypatch, capsys):
    account = AccountConfig(
        "brokerage", "BROKERAGE", "Brokerage", "app-key", "app-secret", "12345678", "01",
    )
    monkeypatch.setattr(batch_cli, "load_account_registry", lambda: [account])
    args = batch_cli.build_parser().parse_args([
        "plan-trade-cash-backfill-v2",
        "--start-date", "20260828",
        "--end-date", "20260828",
        "--as-of-date", "20260828",
        "--max-physical-calls", "7",
    ])

    with pytest.raises(BackfillBudgetExceeded, match="8/7"):
        batch_cli._run_trade_cash_backfill_plan(args)
    assert capsys.readouterr().out == ""


def test_default_five_account_budget_reserves_under_global_ceiling():
    scopes = [
        BackfillAccountScope("ria", "01"),
        BackfillAccountScope("isa", "01"),
        BackfillAccountScope("brokerage", "01", overseas_exchanges=("NAS",)),
        BackfillAccountScope("irp", "29"),
        BackfillAccountScope("pension", "22"),
    ]
    source_plan = plan_trade_cash_backfill(
        scopes, start_date=START, end_date=END, as_of_date=END,
    )

    budgeted = apply_call_budget(source_plan)
    result = budgeted.public_dict()

    assert len(budgeted.reservations) == 131
    assert budgeted.reserved_call_ceiling == 374
    assert budgeted.call_headroom == 26
    assert result["budget_policy"]["max_physical_calls"] == 400
    assert result["budget_policy"]["page_limits"] == {
        DOMESTIC_ORDER_HISTORY: 3,
        OVERSEAS_ORDER_HISTORY: 3,
        OVERSEAS_TRANSACTION_HISTORY: 2,
    }
    assert sum(item["page_budget"] for item in result["partitions"]) == 374
    assert all(
        item["page_budget"] == 0
        for item in result["partitions"] if item["disposition"] == KNOWN_GAP
    )


def test_preflight_rejects_plan_that_does_not_fit_complete_reservation():
    scopes = [
        BackfillAccountScope("ria", "01"),
        BackfillAccountScope("isa", "01"),
        BackfillAccountScope("brokerage", "01", overseas_exchanges=("NAS",)),
        BackfillAccountScope("irp", "29"),
        BackfillAccountScope("pension", "22"),
    ]
    source_plan = plan_trade_cash_backfill(
        scopes, start_date=START, end_date=END, as_of_date=END,
    )

    with pytest.raises(BackfillBudgetExceeded, match="374/373"):
        apply_call_budget(
            source_plan,
            policy=BackfillBudgetPolicy(max_physical_calls=373),
        )
    with pytest.raises(BackfillBudgetExceeded, match="131/130"):
        apply_call_budget(
            source_plan,
            policy=BackfillBudgetPolicy(max_physical_calls=130),
        )


def test_physical_call_gate_fails_before_page_four_and_rejects_noncallable_keys():
    source_plan = plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    budgeted = apply_call_budget(source_plan)
    gate = BackfillCallBudget(budgeted)
    callable_key = source_plan.callable_partitions[0].key
    gap_key = source_plan.known_gaps[0].key

    receipts = [gate.reserve(callable_key) for _ in range(3)]
    assert [item.page_number for item in receipts] == [1, 2, 3]
    assert [item.global_call_number for item in receipts] == [1, 2, 3]
    with pytest.raises(BackfillBudgetExceeded, match="page budget exhausted before physical call"):
        gate.reserve(callable_key)
    with pytest.raises(BackfillBudgetError, match="not callable"):
        gate.reserve(gap_key)
    with pytest.raises(BackfillBudgetError, match="not callable"):
        gate.reserve("unknown-partition")
    assert gate.total_used == 3
    assert gate.public_snapshot()["partition_pages_used"] == {callable_key: 3}


@pytest.mark.parametrize(
    "policy",
    [
        BackfillBudgetPolicy(max_physical_calls=0),
        BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 0),)),
        BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 11),)),
        BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 1), (DOMESTIC_ORDER_HISTORY, 2))),
        BackfillBudgetPolicy(page_limits=((DOMESTIC_CASH_HISTORY, 1),)),
    ],
)
def test_invalid_budget_policy_fails_closed(policy):
    with pytest.raises(BackfillBudgetError):
        policy.normalized()


def test_missing_source_page_policy_fails_closed_and_hash_is_deterministic():
    source_plan = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "01", overseas_exchanges=("NAS",))],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    with pytest.raises(BackfillBudgetError, match="missing page budget"):
        apply_call_budget(
            source_plan,
            policy=BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 3),)),
        )

    default = apply_call_budget(source_plan)
    reordered = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(page_limits=tuple(reversed(BackfillBudgetPolicy().page_limits))),
    )
    assert default.budget_hash == reordered.budget_hash
    assert default.policy.policy_hash == reordered.policy.policy_hash


@pytest.mark.anyio
async def test_guard_reserves_before_call_and_never_invokes_after_exhaustion():
    source_plan = plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    budgeted = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 1),)),
    )
    gate = BackfillCallBudget(budgeted)
    key = source_plan.callable_partitions[0].key
    invoked = 0

    async def physical_call():
        nonlocal invoked
        invoked += 1
        return {"status": "fixture"}

    reservation, result = await run_budgeted_physical_call(gate, key, physical_call)
    assert reservation.page_number == 1
    assert result == {"status": "fixture"}
    with pytest.raises(BackfillBudgetExceeded, match="before physical call"):
        await run_budgeted_physical_call(gate, key, physical_call)
    assert invoked == 1


@pytest.mark.anyio
async def test_failed_physical_attempt_still_consumes_its_reservation():
    source_plan = plan_trade_cash_backfill(
        [BackfillAccountScope("ria", "01")],
        start_date=END,
        end_date=END,
        as_of_date=END,
    )
    budgeted = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(page_limits=((DOMESTIC_ORDER_HISTORY, 1),)),
    )
    gate = BackfillCallBudget(budgeted)
    key = source_plan.callable_partitions[0].key

    async def failed_call():
        raise RuntimeError("fixture upstream failure")

    with pytest.raises(RuntimeError, match="fixture upstream failure"):
        await run_budgeted_physical_call(gate, key, failed_call)
    assert gate.total_used == 1
    with pytest.raises(BackfillBudgetExceeded, match="before physical call"):
        await run_budgeted_physical_call(gate, key, failed_call)
