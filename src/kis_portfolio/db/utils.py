"""Database value conversion helpers."""

import json
from datetime import date, datetime
from typing import Any


def to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "")) if value else None
    except Exception:
        return None


def to_int(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", "")) if value else None
    except Exception:
        return None


def normalize_row(row: dict) -> dict:
    """Convert DuckDB result values into MCP JSON-safe values."""
    normalized = {}
    for key, value in row.items():
        if isinstance(value, (datetime, date)):
            normalized[key] = value.isoformat()
        elif key.endswith("_data") or key == "data":
            normalized[key] = json_loads(value)
        else:
            normalized[key] = value
    return normalized


def rows_to_dicts(cursor) -> list[dict]:
    cols = [desc[0] for desc in cursor.description]
    return [
        {key: json_safe(value) for key, value in zip(cols, row)}
        for row in cursor.fetchall()
    ]


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def json_loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value
