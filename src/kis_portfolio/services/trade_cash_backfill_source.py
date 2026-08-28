"""Guarded physical KIS page adapter for trade/cash backfill partitions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from kis_portfolio.account_registry import AccountConfig, scoped_account_env
from kis_portfolio.clients.kis import DOMAIN
from kis_portfolio.services import kis_api
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillBudgetError,
    BackfillPartition,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import (
    BackfillSourcePage,
    FetchedBackfillPartition,
)
from kis_portfolio.services.trade_cash_backfill_runtime import CheckpointingCallBudget


ORDER_EXCHANGE_CODES = {"NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX"}


class KisTradeCashBackfillSource:
    """Fetch one approved partition while reserving every business API page."""

    def __init__(self, accounts: list[AccountConfig]) -> None:
        self._accounts = {account.label: account for account in accounts}

    def fetch(
        self,
        partition: BackfillPartition,
        gate: CheckpointingCallBudget,
    ) -> FetchedBackfillPartition:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._fetch(partition, gate))
        raise RuntimeError("KIS backfill source must run in a dedicated synchronous batch process")

    async def _fetch(
        self,
        partition: BackfillPartition,
        gate: CheckpointingCallBudget,
    ) -> FetchedBackfillPartition:
        account = self._accounts.get(partition.account_label)
        if account is None:
            raise BackfillBudgetError(
                f"partition account is not in the configured scope: {partition.account_label}"
            )
        if (
            account.acnt_prdt_cd != partition.account_product_code
            or account.account_type.upper() != partition.account_type
        ):
            raise BackfillBudgetError(
                f"partition account capability drifted: {partition.account_label}"
            )

        start = partition.start_date.strftime("%Y%m%d")
        end = partition.end_date.strftime("%Y%m%d")
        max_pages = gate.limit_for(partition.key)

        with scoped_account_env(account):
            if partition.source_operation == DOMESTIC_ORDER_HISTORY:
                tr_id = {
                    ("REAL", "recent"): "TTTC0081R",
                    ("REAL", "old"): "CTSC9215R",
                    ("VIRTUAL", "recent"): "VTTC0081R",
                    ("VIRTUAL", "old"): "VTSC9215R",
                }.get((partition.account_type, partition.source_route))
                if tr_id is None:
                    raise BackfillBudgetError(
                        f"unsupported domestic route: {partition.account_type}/{partition.source_route}"
                    )
                params = {
                    "CANO": account.cano,
                    "ACNT_PRDT_CD": account.acnt_prdt_cd,
                    "INQR_STRT_DT": start,
                    "INQR_END_DT": end,
                    "SLL_BUY_DVSN_CD": "00",
                    "INQR_DVSN": "00",
                    "PDNO": "",
                    "CCLD_DVSN": "00",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "INQR_DVSN_3": "00",
                    "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                }
                result = await kis_api._get_paginated_kis_json(
                    kis_api.ORDER_LIST_PATH,
                    tr_id,
                    params,
                    output_keys=("output1", "output2"),
                    domain=kis_api.TrIdManager.get_domain("order_list"),
                    context_size="100",
                    max_pages=max_pages,
                    before_request=lambda _page: gate.reserve(partition.key),
                    capture_pages=True,
                )
            elif partition.source_operation == OVERSEAS_ORDER_HISTORY:
                tr_id = "VTTS3035R" if partition.account_type == "VIRTUAL" else "TTTS3035R"
                exchange = ORDER_EXCHANGE_CODES.get(partition.exchange or "", partition.exchange or "%")
                params = {
                    "CANO": account.cano,
                    "ACNT_PRDT_CD": account.acnt_prdt_cd,
                    "PDNO": "",
                    "ORD_STRT_DT": start,
                    "ORD_END_DT": end,
                    "SLL_BUY_DVSN": "00",
                    "CCLD_NCCS_DVSN": "00",
                    "OVRS_EXCG_CD": exchange,
                    "SORT_SQN": "DS",
                    "ORD_DT": "",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "CTX_AREA_NK200": "",
                    "CTX_AREA_FK200": "",
                }
                result = await kis_api._get_paginated_kis_json(
                    kis_api.OVERSEAS_ORDER_CCNL_PATH,
                    tr_id,
                    params,
                    output_keys=("output",),
                    domain=kis_api.TrIdManager.get_domain("overseas_order_ccnl"),
                    context_size="200",
                    max_pages=max_pages,
                    before_request=lambda _page: gate.reserve(partition.key),
                    capture_pages=True,
                )
            elif partition.source_operation == OVERSEAS_TRANSACTION_HISTORY:
                if partition.account_type != "REAL":
                    raise BackfillBudgetError("overseas period transaction is not approved for virtual accounts")
                params = {
                    "CANO": account.cano,
                    "ACNT_PRDT_CD": account.acnt_prdt_cd,
                    "ERLM_STRT_DT": start,
                    "ERLM_END_DT": end,
                    "OVRS_EXCG_CD": partition.exchange or "NAS",
                    "PDNO": "",
                    "SLL_BUY_DVSN_CD": "00",
                    "LOAN_DVSN_CD": "",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                }
                result = await kis_api._get_paginated_kis_json(
                    kis_api.OVERSEAS_PERIOD_TRANS_PATH,
                    "CTOS4001R",
                    params,
                    output_keys=("output1", "output2"),
                    domain=DOMAIN,
                    context_size="100",
                    max_pages=max_pages,
                    before_request=lambda _page: gate.reserve(partition.key),
                    capture_pages=True,
                )
            else:
                raise BackfillBudgetError(
                    f"unsupported callable source operation: {partition.source_operation}"
                )

        fetched_at = datetime.now(UTC)
        pages = tuple(
            BackfillSourcePage(payload, fetched_at)
            for payload in result.get("captured_pages", ())
        )
        warning = result.get("pagination_warning")
        return FetchedBackfillPartition(
            pages=pages,
            complete=not bool(warning),
            pagination_warning=warning,
        )
