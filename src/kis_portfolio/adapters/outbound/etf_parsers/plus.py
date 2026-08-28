from __future__ import annotations

import json
from datetime import date

from kis_portfolio.modules.exposure.etf import ParsedComposition, normalize_constituent


def parse_plus_json(payload: bytes) -> ParsedComposition:
    data = json.loads(payload)
    if int(data.get("page", 0)) != 1 or int(data.get("totalPages", 0)) != 1:
        raise ValueError("PLUS fixture pagination is incomplete")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("PLUS fixture requires non-empty items")
    return ParsedComposition(
        date.fromisoformat(data["sourceDate"]),
        tuple(normalize_constituent(item) for item in items),
    )
