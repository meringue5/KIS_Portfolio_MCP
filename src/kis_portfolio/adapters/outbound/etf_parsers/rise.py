from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

from kis_portfolio.modules.exposure.etf import ParsedComposition, normalize_constituent


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.source_date: str | None = None
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table" and attributes.get("data-source-date"):
            self.source_date = attributes["data-source-date"]
        if tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []


def parse_rise_html(payload: bytes) -> ParsedComposition:
    parser = _TableParser()
    parser.feed(payload.decode("utf-8"))
    if not parser.source_date or len(parser.rows) < 2:
        raise ValueError("RISE fixture requires source date and table rows")
    header = [item.lower() for item in parser.rows[0]]
    required = {"code", "name", "type", "weight", "currency"}
    if not required.issubset(header):
        raise ValueError("RISE fixture schema is incomplete")
    normalized = []
    for row in parser.rows[1:]:
        item = dict(zip(header, row))
        normalized.append(normalize_constituent(item))
    return ParsedComposition(date.fromisoformat(parser.source_date), tuple(normalized))
