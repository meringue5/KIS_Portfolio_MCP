from __future__ import annotations

import json
import zipfile
from datetime import date
from io import BytesIO

import duckdb
import pytest

from kis_portfolio.adapters.outbound.etf_parsers import (
    parse_koact_json,
    parse_plus_json,
    parse_rise_html,
    parse_time_xlsx,
)
from kis_portfolio.adapters.outbound.etf_fixture_pipeline import run_offline_etf_fixture
from kis_portfolio.platform.migrations import MigrationRunner


def _time_xlsx(weight="60") -> bytes:
    rows = [
        ["source_date", "2026-08-28"],
        ["code", "name", "type", "weight", "currency"],
        ["005930", "Synthetic Equity", "equity", weight, "KRW"],
        ["CASH", "Cash", "cash", "40", "KRW"],
    ]
    xml_rows = []
    for row_index, values in enumerate(rows, 1):
        cells = []
        for column_index, value in enumerate(values):
            column = chr(65 + column_index)
            cells.append(f'<c r="{column}{row_index}" t="str"><v>{value}</v></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + "".join(xml_rows) + '</sheetData></worksheet>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _json_fixture(**overrides) -> bytes:
    payload = {
        "sourceDate": "2026-08-28", "page": 1, "totalPages": 1,
        "items": [
            {"code": "005930", "name": "Synthetic Equity", "type": "equity", "weight": "70", "currency": "KRW"},
            {"code": "BOND", "name": "Bond", "type": "bond", "weight": "30", "currency": "KRW"},
        ],
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_four_provider_specific_synthetic_parsers_preserve_types():
    time = parse_time_xlsx(_time_xlsx())
    koact = parse_koact_json(_json_fixture())
    rise = parse_rise_html(b'''<table data-source-date="2026-08-28">
        <tr><th>code</th><th>name</th><th>type</th><th>weight</th><th>currency</th></tr>
        <tr><td>NESTED</td><td>Nested ETF</td><td>etf</td><td>100</td><td>KRW</td></tr></table>''')
    plus = parse_plus_json(_json_fixture())
    assert time.source_date == koact.source_date == rise.source_date == plus.source_date == date(2026, 8, 28)
    assert {item.instrument_type for item in time.constituents} == {"equity", "cash"}
    assert {item.instrument_type for item in koact.constituents} == {"equity", "bond"}
    assert rise.constituents[0].instrument_type == "etf"
    with pytest.raises(ValueError, match="pagination is incomplete"):
        parse_plus_json(_json_fixture(totalPages=2))


def test_offline_pipeline_has_zero_calls_blocks_partial_and_quarantines_changed_hash():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    first = run_offline_etf_fixture(
        con, profile_id="etf_profile.time-v1", instrument_id="v1|KRX|0019K0",
        payload=_time_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert first["status"] == "pass" and first["source_calls"] == 0 and first["published_rows"] == 2
    repeated = run_offline_etf_fixture(
        con, profile_id="etf_profile.time-v1", instrument_id="v1|KRX|0019K0",
        payload=_time_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert repeated["status"] == "pass"
    changed = run_offline_etf_fixture(
        con, profile_id="etf_profile.time-v1", instrument_id="v1|KRX|0019K0",
        payload=_time_xlsx("50"), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert changed == {"status": "quarantined", "reason": "changed_hash_same_source_date", "source_calls": 0}
    partial = run_offline_etf_fixture(
        con, profile_id="etf_profile.koact-v1", instrument_id="v1|KRX|0074K0",
        payload=_json_fixture(items=[{"code": "X", "name": "Unknown", "type": "other", "weight": ""}]),
        media_type="application/json",
    )
    assert partial["status"] == "partial" and partial["published_rows"] == 0
    assert con.execute("select count(*) from silver.etf_constituent_snapshots").fetchone()[0] == 2
    con.close()
