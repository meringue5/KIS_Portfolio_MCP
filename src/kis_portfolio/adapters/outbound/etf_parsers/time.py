from __future__ import annotations

import re
import zipfile
from datetime import date
from io import BytesIO
from xml.etree import ElementTree

from kis_portfolio.modules.exposure.etf import ParsedComposition, normalize_constituent


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xlsx_rows(payload: bytes) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall(f"{NS}si")]
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("TIME fixture is not a supported XLSX") from exc
    rows: list[list[str]] = []
    for row in root.findall(f".//{NS}row"):
        values: dict[int, str] = {}
        for cell in row.findall(f"{NS}c"):
            reference = cell.attrib.get("r", "A1")
            letters = re.match(r"[A-Z]+", reference)
            column = 0
            for char in (letters.group(0) if letters else "A"):
                column = column * 26 + ord(char) - 64
            value_node = cell.find(f"{NS}v")
            value = value_node.text if value_node is not None and value_node.text is not None else ""
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            values[column - 1] = value
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])
    return rows


def parse_time_xlsx(payload: bytes) -> ParsedComposition:
    rows = _xlsx_rows(payload)
    if len(rows) < 3 or len(rows[0]) < 2 or rows[0][0].lower() != "source_date":
        raise ValueError("TIME fixture requires a source_date row")
    source_date = date.fromisoformat(rows[0][1])
    header = [item.lower() for item in rows[1]]
    required = {"code", "name", "type", "weight", "currency"}
    if not required.issubset(header):
        raise ValueError("TIME fixture schema is incomplete")
    return ParsedComposition(
        source_date,
        tuple(normalize_constituent(dict(zip(header, row))) for row in rows[2:]),
    )
