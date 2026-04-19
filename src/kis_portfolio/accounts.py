"""Account helpers for KIS account routing and snapshot metadata."""

import os
from typing import Any


ACCOUNT_ENV_TYPES = {
    "KIS_CANO_RIA": "ria",
    "KIS_CANO_ISA": "isa",
    "KIS_CANO_BROKERAGE": "brokerage",
    "KIS_CANO_IRP": "irp",
    "KIS_CANO_PENSION": "pension",
}

VALID_ACCOUNT_TYPES = set(ACCOUNT_ENV_TYPES.values())

PRODUCT_CODE_ACCOUNT_TYPES = {
    "01": "brokerage",
    "22": "pension",
    "29": "irp",
}


def is_irp_account(acnt_prdt_cd: str) -> bool:
    """Only IRP (29) uses the KIS pension balance API."""
    return acnt_prdt_cd == "29"


def infer_account_type(cano: str, acnt_prdt_cd: str) -> str:
    """Infer logical account type from configured CANO first, then product code."""
    if cano and os.environ.get("KIS_CANO") == cano:
        account_label = os.environ.get("KIS_ACCOUNT_LABEL", "")
        if account_label in VALID_ACCOUNT_TYPES:
            return account_label

    for env_name, account_type in ACCOUNT_ENV_TYPES.items():
        if cano and os.environ.get(env_name) == cano:
            return account_type
    return PRODUCT_CODE_ACCOUNT_TYPES.get(acnt_prdt_cd, "unknown")


def to_int(value: Any) -> int | None:
    """Parse KIS numeric strings that may contain commas or arrive empty."""
    try:
        if value in (None, ""):
            return None
        return int(float(str(value).replace(",", "")))
    except Exception:
        return None


def extract_total_eval_amt(balance_response: dict) -> int | None:
    """Extract total evaluated amount from known KIS balance response fields."""
    output2 = balance_response.get("output2", {})
    if not isinstance(output2, dict):
        return None

    return to_int(
        output2.get("tot_evlu_amt")
        or output2.get("scts_evlu_amt")
        or output2.get("tot_asst_amt")
        or output2.get("dnca_tota")
    )
