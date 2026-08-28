from __future__ import annotations

import asyncio
import os
from collections import Counter
from datetime import date

import pytest

from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.services import kis_api
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillAccountScope,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_source import KisTradeCashBackfillSource


DAY = date(2026, 8, 28)


class FakeGate:
    def __init__(self, limit: int = 2) -> None:
        self.limit = limit
        self.reservations: Counter[str] = Counter()

    def limit_for(self, _partition_key: str) -> int:
        return self.limit

    def reserve(self, partition_key: str):
        self.reservations[partition_key] += 1


def _account() -> AccountConfig:
    return AccountConfig(
        "brokerage", "BROKERAGE", "Brokerage", "fixture-key", "fixture-secret",
        "12345678", "01", "REAL",
    )


def _partitions():
    plan = plan_trade_cash_backfill(
        [BackfillAccountScope("brokerage", "01", "REAL", ("NAS",))],
        start_date=DAY,
        end_date=DAY,
        as_of_date=DAY,
    )
    return {item.source_operation: item for item in plan.callable_partitions}


@pytest.mark.parametrize(
    ("operation", "expected_tr_id", "expected_exchange"),
    [
        (DOMESTIC_ORDER_HISTORY, "TTTC0081R", None),
        (OVERSEAS_ORDER_HISTORY, "TTTS3035R", "NASD"),
        (OVERSEAS_TRANSACTION_HISTORY, "CTOS4001R", "NAS"),
    ],
)
def test_kis_source_reserves_each_page_and_uses_approved_route(
    monkeypatch, operation, expected_tr_id, expected_exchange,
) -> None:
    calls = []

    async def fake_paginated(path, tr_id, params, **kwargs):
        assert os.environ["KIS_CANO"] == "12345678"
        kwargs["before_request"](1)
        kwargs["before_request"](2)
        calls.append((path, tr_id, params.copy(), kwargs.copy()))
        row_key = "output" if operation == OVERSEAS_ORDER_HISTORY else "output1"
        return {
            "captured_pages": [{row_key: []}, {row_key: []}],
            "pagination": {"page_count": 2, "max_pages": kwargs["max_pages"]},
        }

    monkeypatch.setattr(kis_api, "_get_paginated_kis_json", fake_paginated)
    monkeypatch.setenv("KIS_CANO", "previous")
    source = KisTradeCashBackfillSource([_account()])
    partition = _partitions()[operation]
    gate = FakeGate()

    fetched = asyncio.run(source._fetch(partition, gate))

    assert len(fetched.pages) == 2
    assert fetched.complete is True
    assert gate.reservations == Counter({partition.key: 2})
    assert calls[0][1] == expected_tr_id
    assert calls[0][3]["max_pages"] == 2
    if expected_exchange:
        assert calls[0][2]["OVRS_EXCG_CD"] == expected_exchange
    assert os.environ["KIS_CANO"] == "previous"


def test_kis_source_surfaces_page_limit_continuation_as_incomplete(monkeypatch) -> None:
    async def fake_paginated(_path, _tr_id, _params, **kwargs):
        kwargs["before_request"](1)
        return {
            "captured_pages": [{"output1": []}],
            "pagination_warning": "max_pages 1 reached",
            "pagination": {"page_count": 1, "max_pages": 1},
        }

    monkeypatch.setattr(kis_api, "_get_paginated_kis_json", fake_paginated)
    source = KisTradeCashBackfillSource([_account()])
    partition = _partitions()[DOMESTIC_ORDER_HISTORY]
    gate = FakeGate(limit=1)

    fetched = asyncio.run(source._fetch(partition, gate))

    assert fetched.complete is False
    assert fetched.pagination_warning == "max_pages 1 reached"
    assert gate.reservations == Counter({partition.key: 1})
