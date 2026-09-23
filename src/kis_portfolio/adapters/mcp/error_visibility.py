"""Owner-only MCP error visibility without credential or account leakage."""

from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from kis_portfolio.security.redaction import mask_account_id


OWNER_DEBUG_VISIBILITY = "owner_debug"
MAX_ERROR_DETAIL_CHARS = 1_024
MAX_STACK_FRAMES = 12

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<prefix>[\"']?\b(?:authorization|appsecret|app_secret|client_secret|kis_app_secret|"
    r"motherduck_token|access_token|refresh_token|token|api[_-]?key|service[_-]?key)\b[\"']?"
    r"\s*[:=]\s*[\"']?)(?P<value>[^\s,;\"']+)"
)
_ACCOUNT_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<prefix>[\"']?\b(?:cano|account_id|account_no|account_number|acnt_no)\b[\"']?"
    r"\s*[:=]\s*[\"']?)(?P<value>[0-9-]{5,})"
)


def redact_error_detail(value: object) -> str:
    """Return one bounded diagnostic line with common secret/account forms removed."""
    text = " ".join(str(value).split())
    text = _BEARER_PATTERN.sub("Bearer <redacted>", text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}<redacted>", text,
    )
    text = _ACCOUNT_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{mask_account_id(match.group('value'))}", text,
    )
    if len(text) > MAX_ERROR_DETAIL_CHARS:
        return f"{text[: MAX_ERROR_DETAIL_CHARS - 3]}..."
    return text


def owner_debug_tool_error(
    exc: Exception,
    *,
    request_id: str,
    code: str | None = None,
    detail: str | None = None,
) -> ToolError:
    """Build the deliberate ToolError contract consumed by owner MCP clients."""
    resolved_code = code or getattr(exc, "code", None) or "internal_error"
    payload: dict[str, Any] = {
        "error": {
            "code": resolved_code,
            "detail": redact_error_detail(exc if detail is None else detail),
            "exception_type": type(exc).__name__,
            "request_id": request_id,
            "visibility": OWNER_DEBUG_VISIBILITY,
        }
    }
    return ToolError(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def validation_error_detail(exc: ValidationError) -> str:
    """Describe rejected fields without echoing their input values."""
    items = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        field = ".".join(str(part) for part in error["loc"]) or "request"
        items.append(f"{field}:{error['type']}:{error['msg']}")
    return "; ".join(items)


def log_unexpected_owner_error(
    logger: logging.Logger,
    *,
    tool_name: str,
    request_id: str,
    exc: Exception,
) -> None:
    """Log correlation and code locations without locals or an unredacted traceback."""
    frames = traceback.extract_tb(exc.__traceback__)[-MAX_STACK_FRAMES:]
    frame_text = " > ".join(
        f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames
    )
    logger.error(
        "owner_debug_tool_failure tool=%s request_id=%s exception_type=%s detail=%s frames=%s",
        tool_name,
        request_id,
        type(exc).__name__,
        redact_error_detail(exc),
        frame_text,
    )
