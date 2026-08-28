"""Conservative normalization for official KIS corporate-action rows.

This adapter performs no HTTP call. It maps already-landed KIS rows and refuses to
invent ratio semantics that the official field contract does not define precisely.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_portfolio.modules.exposure.instruments import canonical_instrument_id


OVERSEAS_ACTION_TYPES = {
    "11": "merger",
    "14": "split",
    "15": "reverse_split",
    "76": "symbol_change",
}


def _date(value: Any) -> date | None:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return None
    if len(text) != 8 or not text.isdigit():
        raise ValueError("KIS corporate action date must be YYYYMMDD")
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def _effective_at(value: date | None, knowledge_at: datetime) -> datetime:
    if value is None:
        return knowledge_at
    return datetime.combine(value, time.min, tzinfo=UTC)


def _decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("KIS corporate action numeric field is invalid") from exc


def _source_record_id(endpoint: str, fields: dict[str, Any]) -> str:
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str)
    return f"{endpoint}|{hashlib.sha256(payload.encode()).hexdigest()}"


def normalize_domestic_face_value(
    row: dict[str, Any],
    *,
    knowledge_at: datetime,
    market: str = "KRX",
    source_confirmed: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Map KSD face-value replacement without reversing the stock-unit ratio."""

    symbol = str(row.get("sht_cd") or "").strip()
    record_date = _date(row.get("record_date"))
    listing_date = _date(row.get("list_dt"))
    before_face = _decimal(row.get("inter_bf_face_amt"))
    after_face = _decimal(row.get("inter_af_face_amt"))
    action_type = "unknown"
    terms_status = "unknown"
    pre_units = post_units = None
    if before_face is not None and after_face is not None and before_face > 0 and after_face > 0:
        multiplier = before_face / after_face
        if multiplier > 1:
            action_type = "split"
            terms_status = "complete"
        elif multiplier < 1:
            action_type = "reverse_split"
            terms_status = "complete"
        if terms_status == "complete":
            pre_units = Decimal(1)
            post_units = multiplier
    source_record_id = _source_record_id("domestic.ksdinfo.rev-split", {
        "symbol": symbol,
        "record_date": record_date,
        "listing_date": listing_date,
    })
    status = "confirmed" if source_confirmed else "provisional"
    return source_record_id, {
        "market": market,
        "action_type": action_type,
        "action_status": status,
        "source_instrument_id": canonical_instrument_id(market, symbol),
        "effective_at": _effective_at(listing_date or record_date, knowledge_at),
        "knowledge_at": knowledge_at,
        "record_date": record_date,
        "listing_date": listing_date,
        "pre_action_units": pre_units,
        "post_action_units": post_units,
        "terms_status": terms_status,
        "quality_status": "pass" if source_confirmed and terms_status == "complete" else "provisional",
        "provenance": {
            "endpoint": "/uapi/domestic-stock/v1/ksdinfo/rev-split",
            "tr_id": "HHKDB669105C0",
            "before_face_value": str(before_face) if before_face is not None else None,
            "after_face_value": str(after_face) if after_face is not None else None,
            "source_confirmation": source_confirmed,
        },
    }


def normalize_domestic_merger_split(
    row: dict[str, Any],
    *,
    knowledge_at: datetime,
    market: str = "KRX",
) -> tuple[str, dict[str, Any]]:
    """Preserve domestic free-form merger/split terms as unresolved evidence."""

    symbol = str(row.get("sht_cd") or "").strip()
    record_date = _date(row.get("record_date"))
    listing_date = _date(row.get("list_dt"))
    reason = str(row.get("merge_type") or "").strip()
    if "인적분할" in reason or "spin" in reason.lower():
        action_type = "spin_off"
    elif "분할" in reason:
        action_type = "split"
    elif "합병" in reason:
        action_type = "merger"
    else:
        action_type = "unknown"
    source_record_id = _source_record_id("domestic.ksdinfo.merger-split", {
        "symbol": symbol,
        "record_date": record_date,
        "listing_date": listing_date,
        "sequence": row.get("seq"),
        "opposite_company": row.get("opp_cust_cd"),
    })
    return source_record_id, {
        "market": market,
        "action_type": action_type,
        "action_status": "provisional",
        "source_instrument_id": canonical_instrument_id(market, symbol),
        "effective_at": _effective_at(listing_date or record_date, knowledge_at),
        "knowledge_at": knowledge_at,
        "record_date": record_date,
        "listing_date": listing_date,
        "terms_status": "unknown",
        "quality_status": "unresolved",
        "provenance": {
            "endpoint": "/uapi/domestic-stock/v1/ksdinfo/merger-split",
            "tr_id": "HHKDB669104C0",
            "merge_type": reason,
            "vendor_merge_rate": row.get("merge_rate"),
            "raw_result_company_code": row.get("cust_cd"),
        },
    }


def normalize_overseas_period_right(
    row: dict[str, Any],
    *,
    knowledge_at: datetime,
    market: str,
) -> tuple[str, dict[str, Any]]:
    """Map supported overseas action types while leaving allocation units unresolved."""

    symbol = str(row.get("pdno") or "").strip().upper()
    action_code = str(row.get("rght_type_cd") or "").strip()
    record_date = _date(row.get("acpl_bass_dt") or row.get("bass_dt"))
    source_record_id = _source_record_id("overseas.period-rights", {
        "market": market,
        "symbol": symbol,
        "action_code": action_code,
        "record_date": record_date,
        "product_type": row.get("prdt_type_cd"),
    })
    confirmation = str(row.get("dfnt_yn") or "").strip().upper()
    confirmed = confirmation in {"Y", "1", "확정"}
    return source_record_id, {
        "market": market,
        "action_type": OVERSEAS_ACTION_TYPES.get(action_code, "unknown"),
        "action_status": "confirmed" if confirmed else "provisional",
        "source_instrument_id": canonical_instrument_id(market, symbol),
        "effective_at": _effective_at(record_date, knowledge_at),
        "knowledge_at": knowledge_at,
        "record_date": record_date,
        "terms_status": "unknown",
        "quality_status": "unresolved",
        "provenance": {
            "endpoint": "/uapi/overseas-price/v1/quotations/period-rights",
            "tr_id": "CTRGT011R",
            "right_type_code": action_code,
            "vendor_stock_allocation_ratio": row.get("stck_alct_rt"),
            "vendor_confirmation": row.get("dfnt_yn"),
        },
    }
