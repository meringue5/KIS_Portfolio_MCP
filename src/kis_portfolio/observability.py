"""Small observability helpers shared by adapters and services."""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator


_OPERATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "kis_operation_id",
    default=None,
)


def new_operation_id(prefix: str = "op") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def current_operation_id() -> str | None:
    return _OPERATION_ID.get()


def current_or_new_operation_id(prefix: str = "op") -> str:
    return current_operation_id() or new_operation_id(prefix)


@contextmanager
def operation_context(operation_id: str) -> Iterator[None]:
    token = _OPERATION_ID.set(operation_id)
    try:
        yield
    finally:
        _OPERATION_ID.reset(token)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        **{key: value for key, value in fields.items() if value is not None},
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=_json_default))
