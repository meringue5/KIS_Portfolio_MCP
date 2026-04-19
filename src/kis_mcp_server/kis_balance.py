"""KIS balance service shared by legacy and orchestrator MCP tools."""

from __future__ import annotations

import logging
import os

import httpx

from kis_mcp_server import db as kisdb
from kis_mcp_server.accounts import extract_total_eval_amt, infer_account_type, is_irp_account
from kis_mcp_server.auth import AUTH_TYPE, CONTENT_TYPE, get_access_token


logger = logging.getLogger(__name__)

DOMAIN = "https://openapi.koreainvestment.com:9443"
VIRTUAL_DOMAIN = "https://openapivts.koreainvestment.com:29443"
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


async def fetch_balance_snapshot(save_snapshot: bool = True) -> dict:
    """
    Fetch current domestic/pension balance for the active account environment.

    IRP (ACNT_PRDT_CD=29) uses the pension balance API. Pension savings
    (ACNT_PRDT_CD=22) uses the standard balance API.
    """
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    cano = os.environ["KIS_CANO"]

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)

        if is_irp_account(acnt_prdt_cd):
            request_data = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "ACCA_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            }
            response = await client.get(
                f"{DOMAIN}{PENSION_BALANCE_PATH}",
                headers={
                    "content-type": CONTENT_TYPE,
                    "authorization": f"{AUTH_TYPE} {token}",
                    "appkey": os.environ["KIS_APP_KEY"],
                    "appsecret": os.environ["KIS_APP_SECRET"],
                    "tr_id": get_balance_tr_id("pension_balance"),
                },
                params=request_data,
            )
        else:
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
            response = await client.get(
                f"{get_balance_domain()}{BALANCE_PATH}",
                headers={
                    "content-type": CONTENT_TYPE,
                    "authorization": f"{AUTH_TYPE} {token}",
                    "appkey": os.environ["KIS_APP_KEY"],
                    "appsecret": os.environ["KIS_APP_SECRET"],
                    "tr_id": get_balance_tr_id("balance"),
                },
                params=request_data,
            )

    if response.status_code != 200:
        raise Exception(f"Failed to get balance: {response.text}")

    data = response.json()
    if save_snapshot:
        save_balance_snapshot(data)
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
