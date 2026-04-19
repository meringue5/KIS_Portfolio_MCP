"""Account helpers for KIS account routing and snapshot metadata."""

from typing import Any


KNOWN_ACCOUNT_TYPES = {
    "44299692": "ria",
    "43786274": "isa",
    "43416048": "brokerage",
    "43362670": "irp",
    "43286118": "pension",
}

PRODUCT_CODE_ACCOUNT_TYPES = {
    "01": "brokerage",
    "22": "pension",
    "29": "irp",
}


def is_irp_account(acnt_prdt_cd: str) -> bool:
    """Only IRP (29) uses the KIS pension balance API."""
    return acnt_prdt_cd == "29"


def infer_account_type(cano: str, acnt_prdt_cd: str) -> str:
    """Infer logical account type from CANO first, then product code."""
    return KNOWN_ACCOUNT_TYPES.get(
        cano,
        PRODUCT_CODE_ACCOUNT_TYPES.get(acnt_prdt_cd, "unknown"),
    )


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
