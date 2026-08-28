"""Download and parse KRX instrument master files from official KIS sources."""

from __future__ import annotations

import tempfile
import urllib.request
import zipfile
from pathlib import Path

from kis_portfolio import db as kisdb


MARKET_SPECS = {
    "KOSPI": {
        "zip_url": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
        "filename": "kospi_code.mst",
        "market": "KRX",
        "tail_len": 228,
        "field_specs": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1,
            9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
        ],
        "field_names": [
            "group_code", "market_cap_scale", "idx_large_code", "idx_mid_code", "idx_small_code",
            "is_manufacturing", "is_low_liquidity", "is_governance", "is_kospi200_sector", "is_kospi100",
            "is_kospi50", "is_krx", "etp_code", "is_elw", "is_krx100", "is_krx_auto", "is_krx_semiconductor",
            "is_krx_bio", "is_krx_bank", "is_spac", "is_krx_energy_chemical", "is_krx_steel", "is_short_heat",
            "is_krx_media_telecom", "is_krx_construction", "non1", "is_krx_securities", "is_krx_ship",
            "is_krx_insurance", "is_krx_transport", "is_sri", "base_price", "trade_unit", "after_hours_unit",
            "is_halted", "is_cleanup_trade", "is_managed", "market_warning", "warning_notice", "is_unfaithful_disclosure",
            "is_backdoor_listing", "lock_code", "par_value_change_code", "capital_increase_code", "margin_rate",
            "is_credit_allowed", "credit_days", "prev_volume", "par_value", "listed_at", "listed_shares", "capital",
            "closing_month", "ipo_price", "preferred_stock", "is_short_sell_heat", "is_abnormal_surge", "is_krx300",
            "is_kospi", "sales", "operating_profit", "ordinary_profit", "net_profit", "roe", "base_year_month",
            "market_cap", "group_company_code", "is_credit_limit_exceeded", "is_collateral_loan_allowed", "is_stock_loan_allowed",
        ],
    },
    "KOSDAQ": {
        "zip_url": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
        "filename": "kosdaq_code.mst",
        "market": "KRX",
        "tail_len": 222,
        "field_specs": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1,
            1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8,
            9, 3, 1, 1, 1,
        ],
        "field_names": [
            "group_code", "market_cap_scale", "idx_large_code", "idx_mid_code", "idx_small_code",
            "is_venture", "is_low_liquidity", "is_krx", "etp_code", "is_krx100", "is_krx_auto",
            "is_krx_semiconductor", "is_krx_bio", "is_krx_bank", "is_spac", "is_krx_energy_chemical",
            "is_krx_steel", "is_short_heat", "is_krx_media_telecom", "is_krx_construction", "is_investment_caution",
            "is_krx_securities", "is_krx_ship", "is_krx_insurance", "is_krx_transport", "is_kosdaq150",
            "base_price", "trade_unit", "after_hours_unit", "is_halted", "is_cleanup_trade", "is_managed",
            "market_warning", "warning_notice", "is_unfaithful_disclosure", "is_backdoor_listing", "lock_code",
            "par_value_change_code", "capital_increase_code", "margin_rate", "is_credit_allowed", "credit_days",
            "prev_volume", "par_value", "listed_at", "listed_shares", "capital", "closing_month", "ipo_price",
            "preferred_stock", "is_short_sell_heat", "is_abnormal_surge", "is_krx300", "sales", "operating_profit",
            "ordinary_profit", "net_profit", "roe", "base_year_month", "market_cap", "group_company_code",
            "is_credit_limit_exceeded", "is_collateral_loan_allowed", "is_stock_loan_allowed",
        ],
    },
    "KONEX": {
        "zip_url": "https://new.real.download.dws.co.kr/common/master/konex_code.mst.zip",
        "filename": "konex_code.mst",
        "market": "KRX",
        "tail_len": 184,
        "field_specs": [
            2, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1,
            9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
        ],
        "field_names": [
            "group_code", "base_price", "trade_unit", "after_hours_unit", "is_halted", "is_cleanup_trade",
            "is_managed", "market_warning", "warning_notice", "is_unfaithful_disclosure", "is_backdoor_listing",
            "lock_code", "par_value_change_code", "capital_increase_code", "margin_rate", "is_credit_allowed",
            "credit_days", "prev_volume", "par_value", "listed_at", "listed_shares", "capital", "closing_month",
            "ipo_price", "preferred_stock", "is_short_sell_heat", "is_abnormal_surge", "is_krx300", "sales",
            "operating_profit", "ordinary_profit", "net_profit", "roe", "base_year_month", "market_cap",
            "is_credit_limit_exceeded", "is_collateral_loan_allowed", "is_stock_loan_allowed",
        ],
    },
}


def _download_zip(url: str, output_path: Path) -> None:
    urllib.request.urlretrieve(url, output_path)


def _split_fixed_width(text: str, widths: list[int]) -> list[str]:
    fields = []
    offset = 0
    for width in widths:
        fields.append(text[offset:offset + width].strip())
        offset += width
    return fields


def _split_fixed_width_bytes(blob: bytes, widths: list[int], encoding: str = "cp949") -> list[str]:
    fields = []
    offset = 0
    for width in widths:
        fields.append(blob[offset:offset + width].decode(encoding, errors="ignore").strip())
        offset += width
    return fields


def _parse_market_file(file_path: Path, spec: dict) -> list[dict]:
    rows: list[dict] = []
    with file_path.open("rb") as handle:
        for raw_line in handle:
            line = raw_line.rstrip(b"\r\n")
            head = line[: len(line) - spec["tail_len"]]
            tail = line[-spec["tail_len"]:]
            symbol = head[0:9].decode("cp949", errors="ignore").strip()
            if not symbol:
                continue
            standard_code = head[9:21].decode("cp949", errors="ignore").strip()
            name = head[21:].decode("cp949", errors="ignore").strip()
            values = _split_fixed_width_bytes(tail, spec["field_specs"])
            extra = dict(zip(spec["field_names"], values))
            rows.append({
                "symbol": symbol,
                "market": spec["market"],
                "standard_code": standard_code,
                "name": name,
                "group_code": extra.get("group_code"),
                "etp_code": extra.get("etp_code"),
                "idx_large_code": extra.get("idx_large_code"),
                "idx_mid_code": extra.get("idx_mid_code"),
                "idx_small_code": extra.get("idx_small_code"),
                **extra,
            })
    return rows


def sync_instrument_master(markets: tuple[str, ...] = ("KOSPI", "KOSDAQ", "KONEX")) -> dict:
    """Download official KIS master files and upsert minimal classification metadata."""
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        for market_name in markets:
            spec = MARKET_SPECS[market_name]
            zip_path = base / f"{market_name.lower()}.zip"
            _download_zip(spec["zip_url"], zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(base)
            rows = _parse_market_file(base / spec["filename"], spec)
            counts[market_name] = kisdb.upsert_instrument_master(rows)
    return counts
