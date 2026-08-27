"""KIS balance service shared by legacy and orchestrator MCP tools."""

from __future__ import annotations

import logging
import os

import httpx

from kis_portfolio import db as kisdb
from kis_portfolio.accounts import extract_total_eval_amt, infer_account_type, is_irp_account
from kis_portfolio.auth import get_access_token, is_kis_expired_token_response
from kis_portfolio.clients.kis import (
    AUTH_TYPE,
    CONTENT_TYPE,
    DOMAIN,
    VIRTUAL_DOMAIN,
    request_kis,
)


logger = logging.getLogger(__name__)

BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
PENSION_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/pension/inquire-balance"

REAL_TR_IDS = {
    "balance": "TTTC8434R",
    "pension_balance": "TTTC2208R",
}

VIRTUAL_TR_IDS = {
    "balance": "VTTC8434R",
    "pension_balance": "TTTC2208R",
}


def get_balance_tr_id(operation: str) -> str:
    is_real_account = os.environ.get("KIS_ACCOUNT_TYPE", "REAL").upper() == "REAL"
    tr_ids = REAL_TR_IDS if is_real_account else VIRTUAL_TR_IDS
    return tr_ids[operation]


def get_balance_domain() -> str:
    is_real_account = os.environ.get("KIS_ACCOUNT_TYPE", "REAL").upper() == "REAL"
    return DOMAIN if is_real_account else VIRTUAL_DOMAIN


async def fetch_balance_snapshot(
    save_snapshot: bool = True,
    return_metadata: bool = False,
) -> dict:
    """
    Fetch current domestic/pension balance for the active account environment.

    IRP (ACNT_PRDT_CD=29) uses the pension balance API. Pension savings
    (ACNT_PRDT_CD=22) uses the standard balance API.
    """
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    cano = os.environ["KIS_CANO"]

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)

        async def request_balance(access_token: str):
            if is_irp_account(acnt_prdt_cd):
                request_data = {
                    "CANO": cano,
                    "ACNT_PRDT_CD": acnt_prdt_cd,
                    "ACCA_DVSN_CD": "00",
                    "INQR_DVSN": "00",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                }
                return await request_kis(
                    client,
                    "GET",
                    f"{DOMAIN}{PENSION_BALANCE_PATH}",
                    domain=DOMAIN,
                    headers={
                        "content-type": CONTENT_TYPE,
                        "authorization": f"{AUTH_TYPE} {access_token}",
                        "appkey": os.environ["KIS_APP_KEY"],
                        "appsecret": os.environ["KIS_APP_SECRET"],
                        "tr_id": get_balance_tr_id("pension_balance"),
                    },
                    params=request_data,
                )

            request_data = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "INQR_DVSN": "01",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "OFL_YN": "",
            }
            balance_domain = get_balance_domain()
            return await request_kis(
                client,
                "GET",
                f"{balance_domain}{BALANCE_PATH}",
                domain=balance_domain,
                headers={
                    "content-type": CONTENT_TYPE,
                    "authorization": f"{AUTH_TYPE} {access_token}",
                    "appkey": os.environ["KIS_APP_KEY"],
                    "appsecret": os.environ["KIS_APP_SECRET"],
                    "tr_id": get_balance_tr_id("balance"),
                },
                params=request_data,
            )

        response = await request_balance(token)
        if is_kis_expired_token_response(response):
            token = await get_access_token(client, DOMAIN, force_refresh=True)
            response = await request_balance(token)

    if response.status_code != 200:
        raise Exception(f"Failed to get balance: {response.text}")

    data = response.json()
    saved_snapshot_id = None
    if save_snapshot:
        saved_snapshot_id = save_balance_snapshot(data)
    if return_metadata:
        return {"raw": data, "saved_snapshot_id": saved_snapshot_id}
    return data


def save_balance_snapshot(data: dict) -> str | None:
    try:
        cano = os.environ.get("KIS_CANO", "unknown")
        acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
        acct_type = infer_account_type(cano, acnt_prdt_cd)
        total = extract_total_eval_amt(data)
        return kisdb.insert_portfolio_snapshot(cano, acct_type, data, total)
    except Exception as e:
        logger.warning(f"DB snapshot save failed (non-critical): {e}")
        return None
