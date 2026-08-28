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
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Iterable, Mapping, TypeVar


PLAN_ID = "plan.trade-cash-history-v2"
PLAN_VERSION = "1.0.0"
DEFAULT_PARTITION_DAYS = 60
MAX_PARTITION_DAYS = 90
DOMESTIC_RECENT_DAYS = 90
SOURCE_PAGE_CAP = 10
DEFAULT_MAX_PHYSICAL_CALLS = 400

DATASET_TRADE_EVENT = "dataset.trade-event"
DATASET_CASH_EVENT = "dataset.cash-transaction-event"

DOMESTIC_ORDER_HISTORY = "domestic-order-history"
DOMESTIC_CASH_HISTORY = "domestic-cash-history"
OVERSEAS_ORDER_HISTORY = "overseas-order-history"
OVERSEAS_TRANSACTION_HISTORY = "overseas-transaction-history"

CALLABLE = "callable"
KNOWN_GAP = "known_gap"

DEFAULT_PAGE_LIMITS = (
    (DOMESTIC_ORDER_HISTORY, 3),
    (OVERSEAS_ORDER_HISTORY, 3),
    (OVERSEAS_TRANSACTION_HISTORY, 2),
)
CALLABLE_SOURCE_OPERATIONS = frozenset(item[0] for item in DEFAULT_PAGE_LIMITS)


class BackfillBudgetError(RuntimeError):
    """Raised before a physical call when a budget contract cannot be honored."""


class BackfillBudgetExceeded(BackfillBudgetError):
    """Raised when the requested reservation exceeds a page or global ceiling."""


PhysicalCallResult = TypeVar("PhysicalCallResult")


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


@dataclass(frozen=True, slots=True)
class BackfillBudgetPolicy:
    """Versioned public budget limits; it never contains credentials."""

    policy_id: str = "budget.trade-cash-history-v2"
    policy_version: str = "1.0.0"
    max_physical_calls: int = DEFAULT_MAX_PHYSICAL_CALLS
    page_limits: tuple[tuple[str, int], ...] = DEFAULT_PAGE_LIMITS

    def normalized(self) -> BackfillBudgetPolicy:
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.policy_id):
            raise BackfillBudgetError(f"invalid budget policy id: {self.policy_id}")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.policy_version):
            raise BackfillBudgetError(f"invalid budget policy version: {self.policy_version}")
        if type(self.max_physical_calls) is not int or self.max_physical_calls < 1:
            raise BackfillBudgetError("max_physical_calls must be a positive integer")

        limits: dict[str, int] = {}
        for source_operation, page_limit in self.page_limits:
            if source_operation not in CALLABLE_SOURCE_OPERATIONS:
                raise BackfillBudgetError(f"unsupported budget source operation: {source_operation}")
            if source_operation in limits:
                raise BackfillBudgetError(f"duplicate page budget: {source_operation}")
            if type(page_limit) is not int or not 1 <= page_limit <= SOURCE_PAGE_CAP:
                raise BackfillBudgetError(
                    f"page budget for {source_operation} must be between 1 and {SOURCE_PAGE_CAP}"
                )
            limits[source_operation] = page_limit
        if not limits:
            raise BackfillBudgetError("at least one source page budget is required")
        return BackfillBudgetPolicy(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            max_physical_calls=self.max_physical_calls,
            page_limits=tuple(sorted(limits.items())),
        )

    def page_limit_for(self, source_operation: str) -> int:
        for operation, limit in self.page_limits:
            if operation == source_operation:
                return limit
        raise BackfillBudgetError(f"missing page budget for source operation: {source_operation}")

    @property
    def policy_hash(self) -> str:
        normalized = self.normalized()
        canonical = json.dumps(
            {
                "policy_id": normalized.policy_id,
                "policy_version": normalized.policy_version,
                "max_physical_calls": normalized.max_physical_calls,
                "page_limits": normalized.page_limits,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def public_dict(self) -> dict[str, Any]:
        normalized = self.normalized()
        return {
            "policy_id": normalized.policy_id,
            "policy_version": normalized.policy_version,
            "policy_hash": normalized.policy_hash,
            "max_physical_calls": normalized.max_physical_calls,
            "page_limits": dict(normalized.page_limits),
        }


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    partition_key: str
    source_operation: str
    page_limit: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "partition_key": self.partition_key,
            "source_operation": self.source_operation,
            "page_limit": self.page_limit,
        }


@dataclass(frozen=True, slots=True)
class BudgetedTradeCashBackfillPlan:
    source_plan: TradeCashBackfillPlan
    policy: BackfillBudgetPolicy
    budget_hash: str
    reservations: tuple[BudgetReservation, ...]

    @property
    def reserved_call_ceiling(self) -> int:
        return sum(item.page_limit for item in self.reservations)

    @property
    def call_headroom(self) -> int:
        return self.policy.max_physical_calls - self.reserved_call_ceiling

    def public_dict(self, *, include_partitions: bool = True) -> dict[str, Any]:
        result = self.source_plan.public_dict(include_partitions=include_partitions)
        result.update({
            "status": "budgeted",
            "budget_enforced": True,
            "budget_hash": self.budget_hash,
            "budget_policy": self.policy.public_dict(),
            "reserved_call_ceiling": self.reserved_call_ceiling,
            "call_headroom": self.call_headroom,
        })
        if include_partitions:
            limits = {item.partition_key: item.page_limit for item in self.reservations}
            for partition in result["partitions"]:
                partition["page_budget"] = limits.get(partition["partition_key"], 0)
        return result


@dataclass(frozen=True, slots=True)
class PhysicalCallReservation:
    partition_key: str
    page_number: int
    global_call_number: int
    partition_page_limit: int
    global_call_limit: int


class BackfillCallBudget:
    """Thread-safe, in-memory reservation gate called immediately before I/O."""

    def __init__(self, budgeted_plan: BudgetedTradeCashBackfillPlan):
        self._budgeted_plan = budgeted_plan
        self._limits = {
            item.partition_key: item.page_limit for item in budgeted_plan.reservations
        }
        self._used = {key: 0 for key in self._limits}
        self._total_used = 0
        self._lock = threading.Lock()

    @property
    def total_used(self) -> int:
        with self._lock:
            return self._total_used

    def restore(self, partition_pages_used: Mapping[str, int]) -> None:
        """Restore durable reservations once, failing closed on invalid state."""

        with self._lock:
            if self._total_used or any(self._used.values()):
                raise BackfillBudgetError("call budget can only be restored into an unused gate")
            restored = {key: 0 for key in self._limits}
            for partition_key, used in partition_pages_used.items():
                if partition_key not in self._limits:
                    raise BackfillBudgetError(
                        f"persisted usage references an unapproved partition: {partition_key}"
                    )
                if type(used) is not int or used < 0:
                    raise BackfillBudgetError(
                        f"persisted page usage must be a nonnegative integer: {partition_key}"
                    )
                limit = self._limits[partition_key]
                if used > limit:
                    raise BackfillBudgetExceeded(
                        f"persisted partition usage exceeds page budget: "
                        f"{partition_key} {used}/{limit}"
                    )
                restored[partition_key] = used
            total = sum(restored.values())
            global_limit = self._budgeted_plan.policy.max_physical_calls
            if total > global_limit:
                raise BackfillBudgetExceeded(
                    f"persisted usage exceeds global physical call budget: {total}/{global_limit}"
                )
            self._used = restored
            self._total_used = total

    def used_for(self, partition_key: str) -> int:
        with self._lock:
            if partition_key not in self._used:
                raise BackfillBudgetError(
                    f"partition is not callable in the approved budget: {partition_key}"
                )
            return self._used[partition_key]

    def reserve(self, partition_key: str) -> PhysicalCallReservation:
        """Reserve one physical call or raise before the caller performs I/O."""

        with self._lock:
            if partition_key not in self._limits:
                raise BackfillBudgetError(
                    f"partition is not callable in the approved budget: {partition_key}"
                )
            page_limit = self._limits[partition_key]
            used = self._used[partition_key]
            if used >= page_limit:
                raise BackfillBudgetExceeded(
                    f"partition page budget exhausted before physical call: "
                    f"{partition_key} {used}/{page_limit}"
                )
            global_limit = self._budgeted_plan.policy.max_physical_calls
            if self._total_used >= global_limit:
                raise BackfillBudgetExceeded(
                    f"global physical call budget exhausted before physical call: "
                    f"{self._total_used}/{global_limit}"
                )
            self._used[partition_key] = used + 1
            self._total_used += 1
            return PhysicalCallReservation(
                partition_key=partition_key,
                page_number=used + 1,
                global_call_number=self._total_used,
                partition_page_limit=page_limit,
                global_call_limit=global_limit,
            )

    def public_snapshot(self) -> dict[str, Any]:
        with self._lock:
            used_partitions = {
                key: used for key, used in sorted(self._used.items()) if used
            }
            return {
                "budget_hash": self._budgeted_plan.budget_hash,
                "total_used": self._total_used,
                "global_call_limit": self._budgeted_plan.policy.max_physical_calls,
                "partition_pages_used": used_partitions,
            }


async def run_budgeted_physical_call(
    gate: BackfillCallBudget,
    partition_key: str,
    physical_call: Callable[[], Awaitable[PhysicalCallResult]],
) -> tuple[PhysicalCallReservation, PhysicalCallResult]:
    """Reserve first, then invoke exactly one physical source call."""

    reservation = gate.reserve(partition_key)
    result = await physical_call()
    return reservation, result


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


def apply_call_budget(
    plan: TradeCashBackfillPlan,
    *,
    policy: BackfillBudgetPolicy | None = None,
) -> BudgetedTradeCashBackfillPlan:
    """Reserve worst-case page ceilings for every callable partition.

    This is a preflight-only operation.  It raises before an executor can be
    created when the complete plan does not fit within the global ceiling.
    """

    normalized = (policy or BackfillBudgetPolicy()).normalized()
    reservations = []
    for partition in plan.callable_partitions:
        page_limit = normalized.page_limit_for(partition.source_operation)
        if page_limit > partition.source_page_cap:
            raise BackfillBudgetError(
                f"page budget exceeds application source-helper cap for {partition.key}: "
                f"{page_limit}/{partition.source_page_cap}"
            )
        reservations.append(
            BudgetReservation(
                partition_key=partition.key,
                source_operation=partition.source_operation,
                page_limit=page_limit,
            )
        )

    ordered = tuple(sorted(reservations, key=lambda item: item.partition_key))
    reserved_call_ceiling = sum(item.page_limit for item in ordered)
    if len(ordered) > normalized.max_physical_calls:
        raise BackfillBudgetExceeded(
            "minimum one-call-per-partition reservation exceeds global budget: "
            f"{len(ordered)}/{normalized.max_physical_calls}"
        )
    if reserved_call_ceiling > normalized.max_physical_calls:
        raise BackfillBudgetExceeded(
            "preflight physical call reservation exceeds global budget: "
            f"{reserved_call_ceiling}/{normalized.max_physical_calls}"
        )

    canonical = json.dumps(
        {
            "source_plan_hash": plan.plan_hash,
            "policy_hash": normalized.policy_hash,
            "reservations": [item.public_dict() for item in ordered],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return BudgetedTradeCashBackfillPlan(
        source_plan=plan,
        policy=normalized,
        budget_hash=hashlib.sha256(canonical.encode()).hexdigest()[:16],
        reservations=ordered,
    )
