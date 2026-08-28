from __future__ import annotations

import json
from datetime import date

from kis_portfolio.modules.exposure.etf import ParsedComposition, normalize_constituent


def parse_koact_json(payload: bytes) -> ParsedComposition:
    data = json.loads(payload)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("KoAct fixture requires non-empty items")
    return ParsedComposition(
        date.fromisoformat(data["sourceDate"]),
        tuple(normalize_constituent(item) for item in items),
    )
