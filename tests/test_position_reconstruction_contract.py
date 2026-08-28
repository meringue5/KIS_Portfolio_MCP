from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kis_portfolio.modules.portfolio.reconstruction import (
    AllocationContractError,
    AllocationMethod,
    AllocationStatus,
    CorporateActionCoverage,
    EvidenceProvenance,
    OpenLot,
    ReconstructionStatus,
    SellAllocationRequest,
    assess_reconstruction,
    plan_sell_allocation,
    reconstruction_partition_key,
)


NOW = datetime(2026, 8, 28, tzinfo=UTC)


def _lot(
    lot_id: str,
    days_ago: int,
    quantity: str,
    *,
    account_id: str = "account-a",
    instrument_id: str = "instrument-a",
    episode_id: str = "episode-a",
    thread_id: str | None = None,
) -> OpenLot:
    return OpenLot(
        lot_id,
        account_id,
        instrument_id,
        episode_id,
        NOW - timedelta(days=days_ago),
        Decimal(quantity),
        thread_id,
    )


def _request(quantity: str, **overrides) -> SellAllocationRequest:
    values = {
        "sell_trade_event_id": "sell-a",
        "account_id": "account-a",
        "instrument_id": "instrument-a",
        "episode_id": "episode-a",
        "quantity": Decimal(quantity),
    }
    values.update(overrides)
    return SellAllocationRequest(**values)


def test_partition_key_is_deterministic_and_hides_confidential_scope():
    first = reconstruction_partition_key("account-secret", "instrument-secret", NOW - timedelta(days=10), NOW)
    second = reconstruction_partition_key("account-secret", "instrument-secret", NOW - timedelta(days=10), NOW)

    assert first == second
    assert first.startswith("reconstruct-")
    assert "account-secret" not in first
    assert "instrument-secret" not in first


def test_exact_replay_is_reconstructed_actual_evidence():
    result = assess_reconstruction(
        current_quantity="12",
        replayed_quantity="12",
        corporate_action_coverage=CorporateActionCoverage.PASS,
    )

    assert result.status is ReconstructionStatus.RECONSTRUCTED
    assert result.evidence_provenance is EvidenceProvenance.ACTUAL
    assert result.eligible_for_reconciled_projection is True


def test_positive_residual_is_explicit_inferred_opening_only_after_coverage_passes():
    result = assess_reconstruction(
        current_quantity="12",
        replayed_quantity="7",
        corporate_action_coverage=CorporateActionCoverage.PASS,
    )

    assert result.status is ReconstructionStatus.INFERRED_OPENING
    assert result.inferred_opening_quantity == Decimal("5")
    assert result.evidence_provenance is EvidenceProvenance.INFERRED_OPENING
    assert result.eligible_for_reconciled_projection is True


def test_missing_action_coverage_and_source_gap_fail_closed_without_opening_lot():
    not_assessed = assess_reconstruction(
        current_quantity="12",
        replayed_quantity="7",
        corporate_action_coverage=CorporateActionCoverage.NOT_ASSESSED,
    )
    provisional = assess_reconstruction(
        current_quantity="12",
        replayed_quantity="7",
        corporate_action_coverage=CorporateActionCoverage.PASS,
        source_gap_reasons=("irp_recent_history_endpoint_unavailable",),
    )

    assert not_assessed.status is ReconstructionStatus.NOT_ASSESSED
    assert provisional.status is ReconstructionStatus.PROVISIONAL
    assert not_assessed.inferred_opening_quantity is None
    assert provisional.inferred_opening_quantity is None
    assert not not_assessed.eligible_for_reconciled_projection
    assert not provisional.eligible_for_reconciled_projection


@pytest.mark.parametrize(
    ("current", "replayed", "ambiguous", "blocker"),
    [
        ("5", "8", False, "replay_exceeds_current_position"),
        ("5", "5", True, "ambiguous_event_order"),
    ],
)
def test_negative_residual_or_ambiguous_order_is_an_exception(current, replayed, ambiguous, blocker):
    result = assess_reconstruction(
        current_quantity=current,
        replayed_quantity=replayed,
        corporate_action_coverage=CorporateActionCoverage.PASS,
        ambiguous_event_order=ambiguous,
    )

    assert result.status is ReconstructionStatus.RECONCILIATION_EXCEPTION
    assert blocker in result.blockers
    assert result.inferred_opening_quantity is None


def test_inferred_fifo_is_scoped_deterministic_and_reviewable():
    lots = [
        _lot("lot-new", 2, "4"),
        _lot("lot-other-account", 20, "100", account_id="account-b"),
        _lot("lot-old-b", 10, "3"),
        _lot("lot-old-a", 10, "5"),
    ]

    result = plan_sell_allocation(_request("7"), reversed(lots))

    assert result.method is AllocationMethod.INFERRED_FIFO
    assert result.status is AllocationStatus.COMPLETE
    assert [(item.lot_id, item.allocated_quantity) for item in result.slices] == [
        ("lot-old-a", Decimal("5")),
        ("lot-old-b", Decimal("2")),
    ]
    assert result.review_required is True


def test_explicit_lot_or_thread_never_falls_back_outside_declared_scope():
    lots = [
        _lot("lot-a", 10, "2", thread_id="thread-a"),
        _lot("lot-b", 5, "5", thread_id="thread-b"),
        _lot("lot-other-episode", 20, "100", episode_id="episode-b", thread_id="thread-a"),
    ]
    thread = plan_sell_allocation(
        _request("2", explicit_thread_id="thread-a"),
        lots,
    )

    assert thread.method is AllocationMethod.EXPLICIT_THREAD_FIFO
    assert [item.lot_id for item in thread.slices] == ["lot-a"]
    assert thread.review_required is False

    with pytest.raises(AllocationContractError, match="outside the sell scope"):
        plan_sell_allocation(
            _request("1", explicit_lot_ids=("lot-other-episode",)),
            lots,
        )


def test_insufficient_lot_quantity_is_partial_exception_never_a_synthetic_buy():
    result = plan_sell_allocation(
        _request("9"),
        [_lot("lot-a", 10, "2"), _lot("lot-b", 5, "3")],
    )

    assert result.status is AllocationStatus.RECONCILIATION_EXCEPTION
    assert result.allocated_quantity == Decimal("5")
    assert result.unallocated_quantity == Decimal("4")
    assert result.blockers == ("insufficient_open_lot_quantity",)
    assert result.review_required is True
