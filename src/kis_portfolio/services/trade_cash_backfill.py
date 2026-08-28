"""Pure planning for bounded trade and cash-history backfill partitions.

This module deliberately performs no KIS request and no database write.  It
turns public account capabilities and a date window into stable source
partitions so later Work Items can add call-budget enforcement and resumable
execution without changing partition identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable


PLAN_ID = "plan.trade-cash-history-v2"
PLAN_VERSION = "1.0.0"
DEFAULT_PARTITION_DAYS = 60
MAX_PARTITION_DAYS = 90
DOMESTIC_RECENT_DAYS = 90
SOURCE_PAGE_CAP = 10

DATASET_TRADE_EVENT = "dataset.trade-event"
DATASET_CASH_EVENT = "dataset.cash-transaction-event"

DOMESTIC_ORDER_HISTORY = "domestic-order-history"
DOMESTIC_CASH_HISTORY = "domestic-cash-history"
OVERSEAS_ORDER_HISTORY = "overseas-order-history"
OVERSEAS_TRANSACTION_HISTORY = "overseas-transaction-history"

CALLABLE = "callable"
KNOWN_GAP = "known_gap"


@dataclass(frozen=True, slots=True)
class BackfillAccountScope:
    """Non-secret account capabilities used by the planner."""

    label: str
    product_code: str
    account_type: str = "REAL"
    overseas_exchanges: tuple[str, ...] = ()

    def normalized(self) -> BackfillAccountScope:
        label = self.label.strip().lower()
        product_code = self.product_code.strip()
        account_type = self.account_type.strip().upper()
        exchanges = tuple(sorted({item.strip().upper() for item in self.overseas_exchanges if item.strip()}))
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", label):
            raise ValueError(f"invalid account label: {label or '<empty>'}")
        if not re.fullmatch(r"[A-Za-z0-9]{1,8}", product_code):
            raise ValueError(f"invalid account product code for {label}: {product_code or '<empty>'}")
        if account_type not in {"REAL", "VIRTUAL"}:
            raise ValueError(f"unsupported account type for {label}: {account_type}")
        invalid_exchanges = [item for item in exchanges if not re.fullmatch(r"[A-Z0-9]{2,8}", item)]
        if invalid_exchanges:
            raise ValueError(f"invalid overseas exchange for {label}: {invalid_exchanges[0]}")
        return BackfillAccountScope(label, product_code, account_type, exchanges)


@dataclass(frozen=True, slots=True)
class BackfillPartition:
    """One stable, bounded source request or one explicit unavailable range."""

    key: str
    source_operation: str
    source_route: str
    account_label: str
    account_product_code: str
    account_type: str
    market: str
    exchange: str | None
    start_date: date
    end_date: date
    output_dataset_ids: tuple[str, ...]
    disposition: str
    gap_reason: str | None = None
    source_page_cap: int = SOURCE_PAGE_CAP

    @property
    def calendar_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def public_dict(self) -> dict[str, Any]:
        return {
            "partition_key": self.key,
            "source_operation": self.source_operation,
            "source_route": self.source_route,
            "account_label": self.account_label,
            "account_product_code": self.account_product_code,
            "account_type": self.account_type,
            "market": self.market,
            "exchange": self.exchange,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "calendar_days": self.calendar_days,
            "output_dataset_ids": list(self.output_dataset_ids),
            "disposition": self.disposition,
            "gap_reason": self.gap_reason,
            "source_page_cap": self.source_page_cap if self.disposition == CALLABLE else 0,
        }


@dataclass(frozen=True, slots=True)
class TradeCashBackfillPlan:
    plan_id: str
    plan_version: str
    plan_hash: str
    start_date: date
    end_date: date
    as_of_date: date
    partition_days: int
    partitions: tuple[BackfillPartition, ...]

    @property
    def callable_partitions(self) -> tuple[BackfillPartition, ...]:
        return tuple(item for item in self.partitions if item.disposition == CALLABLE)

    @property
    def known_gaps(self) -> tuple[BackfillPartition, ...]:
        return tuple(item for item in self.partitions if item.disposition == KNOWN_GAP)

    def public_dict(self, *, include_partitions: bool = True) -> dict[str, Any]:
        callable_items = self.callable_partitions
        result: dict[str, Any] = {
            "status": "planned",
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_hash": self.plan_hash,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "as_of_date": self.as_of_date.isoformat(),
            "partition_days": self.partition_days,
            "partition_count": len(self.partitions),
            "callable_partition_count": len(callable_items),
            "known_gap_count": len(self.known_gaps),
            "minimum_physical_calls": len(callable_items),
            "page_cap_projection": sum(item.source_page_cap for item in callable_items),
            "budget_enforced": False,
            "side_effects": "none",
        }
        if include_partitions:
            result["partitions"] = [item.public_dict() for item in self.partitions]
        return result


def three_year_start(end_date: date) -> date:
    """Return an exact three-calendar-year lower bound, clamping leap day."""

    try:
        return end_date.replace(year=end_date.year - 3)
    except ValueError:
        return end_date.replace(year=end_date.year - 3, day=28)


def account_scopes_from_registry(
    accounts: Iterable[Any],
    *,
    overseas_account_labels: Iterable[str] = ("brokerage",),
    overseas_exchanges: Iterable[str] = ("NAS",),
) -> tuple[BackfillAccountScope, ...]:
    """Project configured accounts into a deterministic, non-secret scope."""

    overseas_labels = {item.strip().lower() for item in overseas_account_labels if item.strip()}
    exchanges = tuple(sorted({item.strip().upper() for item in overseas_exchanges if item.strip()}))
    if overseas_labels and not exchanges:
        raise ValueError("at least one overseas exchange is required")

    scopes = []
    observed_labels = set()
    for account in accounts:
        label = str(account.label).strip().lower()
        observed_labels.add(label)
        scopes.append(
            BackfillAccountScope(
                label=label,
                product_code=str(account.acnt_prdt_cd),
                account_type=str(account.account_type),
                overseas_exchanges=exchanges if label in overseas_labels else (),
            ).normalized()
        )
    missing = sorted(overseas_labels - observed_labels)
    if missing:
        raise ValueError(f"unknown overseas account labels: {', '.join(missing)}")
    return tuple(sorted(scopes, key=lambda item: item.label))


def _shards(start_date: date, end_date: date, partition_days: int) -> list[tuple[date, date]]:
    shards = []
    cursor = start_date
    while cursor <= end_date:
        shard_end = min(end_date, cursor + timedelta(days=partition_days - 1))
        shards.append((cursor, shard_end))
        cursor = shard_end + timedelta(days=1)
    return shards


def _partition_key(
    source_operation: str,
    account_label: str,
    account_product_code: str,
    account_type: str,
    source_route: str,
    start_date: date,
    end_date: date,
    *,
    exchange: str | None = None,
) -> str:
    market_key = exchange or "KRX"
    return (
        f"{PLAN_VERSION}|{source_operation}|{account_label}|{account_product_code}|"
        f"{account_type}|{market_key}|{source_route}|{start_date.isoformat()}|{end_date.isoformat()}"
    )


def _partition(
    *,
    scope: BackfillAccountScope,
    source_operation: str,
    source_route: str,
    market: str,
    exchange: str | None,
    start_date: date,
    end_date: date,
    output_dataset_ids: tuple[str, ...],
    disposition: str = CALLABLE,
    gap_reason: str | None = None,
) -> BackfillPartition:
    return BackfillPartition(
        key=_partition_key(
            source_operation,
            scope.label,
            scope.product_code,
            scope.account_type,
            source_route,
            start_date,
            end_date,
            exchange=exchange,
        ),
        source_operation=source_operation,
        source_route=source_route,
        account_label=scope.label,
        account_product_code=scope.product_code,
        account_type=scope.account_type,
        market=market,
        exchange=exchange,
        start_date=start_date,
        end_date=end_date,
        output_dataset_ids=output_dataset_ids,
        disposition=disposition,
        gap_reason=gap_reason,
    )


def _domestic_partitions(
    scope: BackfillAccountScope,
    *,
    start_date: date,
    end_date: date,
    as_of_date: date,
    partition_days: int,
) -> list[BackfillPartition]:
    cutoff = as_of_date - timedelta(days=DOMESTIC_RECENT_DAYS)
    items: list[BackfillPartition] = []
    route_ranges = []
    if start_date < cutoff:
        route_ranges.append(("old", start_date, min(end_date, cutoff - timedelta(days=1))))
    if end_date >= cutoff:
        route_ranges.append(("recent", max(start_date, cutoff), end_date))

    for route, route_start, route_end in route_ranges:
        if route_start > route_end:
            continue
        if route == "recent" and scope.product_code == "29":
            items.append(
                _partition(
                    scope=scope,
                    source_operation=DOMESTIC_ORDER_HISTORY,
                    source_route=route,
                    market="KRX",
                    exchange=None,
                    start_date=route_start,
                    end_date=route_end,
                    output_dataset_ids=(DATASET_TRADE_EVENT,),
                    disposition=KNOWN_GAP,
                    gap_reason="irp_recent_history_endpoint_unavailable",
                )
            )
            continue
        for shard_start, shard_end in _shards(route_start, route_end, partition_days):
            items.append(
                _partition(
                    scope=scope,
                    source_operation=DOMESTIC_ORDER_HISTORY,
                    source_route=route,
                    market="KRX",
                    exchange=None,
                    start_date=shard_start,
                    end_date=shard_end,
                    output_dataset_ids=(DATASET_TRADE_EVENT,),
                )
            )

    items.append(
        _partition(
            scope=scope,
            source_operation=DOMESTIC_CASH_HISTORY,
            source_route="unavailable",
            market="KRX",
            exchange=None,
            start_date=start_date,
            end_date=end_date,
            output_dataset_ids=(DATASET_CASH_EVENT,),
            disposition=KNOWN_GAP,
            gap_reason="no_selected_domestic_cash_transaction_history_source",
        )
    )
    return items


def _overseas_partitions(
    scope: BackfillAccountScope,
    *,
    start_date: date,
    end_date: date,
    partition_days: int,
) -> list[BackfillPartition]:
    items: list[BackfillPartition] = []
    for exchange in scope.overseas_exchanges:
        for shard_start, shard_end in _shards(start_date, end_date, partition_days):
            items.append(
                _partition(
                    scope=scope,
                    source_operation=OVERSEAS_ORDER_HISTORY,
                    source_route="order-aggregate",
                    market="US",
                    exchange=exchange,
                    start_date=shard_start,
                    end_date=shard_end,
                    output_dataset_ids=(DATASET_TRADE_EVENT,),
                )
            )
            if scope.account_type == "VIRTUAL":
                items.append(
                    _partition(
                        scope=scope,
                        source_operation=OVERSEAS_TRANSACTION_HISTORY,
                        source_route="period-transaction",
                        market="US",
                        exchange=exchange,
                        start_date=shard_start,
                        end_date=shard_end,
                        output_dataset_ids=(DATASET_TRADE_EVENT, DATASET_CASH_EVENT),
                        disposition=KNOWN_GAP,
                        gap_reason="overseas_period_transaction_virtual_support_unverified",
                    )
                )
            else:
                items.append(
                    _partition(
                        scope=scope,
                        source_operation=OVERSEAS_TRANSACTION_HISTORY,
                        source_route="period-transaction",
                        market="US",
                        exchange=exchange,
                        start_date=shard_start,
                        end_date=shard_end,
                        output_dataset_ids=(DATASET_TRADE_EVENT, DATASET_CASH_EVENT),
                    )
                )
    return items


def plan_trade_cash_backfill(
    account_scopes: Iterable[BackfillAccountScope],
    *,
    end_date: date,
    as_of_date: date,
    start_date: date | None = None,
    partition_days: int = DEFAULT_PARTITION_DAYS,
) -> TradeCashBackfillPlan:
    """Build a stable three-year source plan without performing any side effect."""

    resolved_start = start_date or three_year_start(end_date)
    if resolved_start > end_date:
        raise ValueError("start_date must not be after end_date")
    if end_date > as_of_date:
        raise ValueError("end_date must not be after as_of_date")
    if resolved_start < three_year_start(end_date):
        raise ValueError("backfill window must not exceed three calendar years")
    if not 1 <= partition_days <= MAX_PARTITION_DAYS:
        raise ValueError(f"partition_days must be between 1 and {MAX_PARTITION_DAYS}")

    normalized = [scope.normalized() for scope in account_scopes]
    labels = [scope.label for scope in normalized]
    if len(labels) != len(set(labels)):
        raise ValueError("account labels must be unique")
    if not normalized:
        raise ValueError("at least one account scope is required")

    partitions: list[BackfillPartition] = []
    for scope in sorted(normalized, key=lambda item: item.label):
        partitions.extend(
            _domestic_partitions(
                scope,
                start_date=resolved_start,
                end_date=end_date,
                as_of_date=as_of_date,
                partition_days=partition_days,
            )
        )
        partitions.extend(
            _overseas_partitions(
                scope,
                start_date=resolved_start,
                end_date=end_date,
                partition_days=partition_days,
            )
        )

    ordered = tuple(sorted(partitions, key=lambda item: item.key))
    public_partitions = [item.public_dict() for item in ordered]
    digest_input = {
        "plan_id": PLAN_ID,
        "plan_version": PLAN_VERSION,
        "start_date": resolved_start.isoformat(),
        "end_date": end_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "partition_days": partition_days,
        "partitions": public_partitions,
    }
    canonical = json.dumps(digest_input, sort_keys=True, separators=(",", ":"))
    return TradeCashBackfillPlan(
        plan_id=PLAN_ID,
        plan_version=PLAN_VERSION,
        plan_hash=hashlib.sha256(canonical.encode()).hexdigest()[:16],
        start_date=resolved_start,
        end_date=end_date,
        as_of_date=as_of_date,
        partition_days=partition_days,
        partitions=ordered,
    )
