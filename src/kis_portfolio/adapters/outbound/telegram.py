"""Fail-closed outbound Telegram rendering and transport primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

import httpx

from kis_portfolio.adapters.outbound.alert_warehouse import TelegramDispatchCandidate


TELEGRAM_API_ROOT = "https://api.telegram.org"
_ALLOWED_CONTEXT_KEYS = frozenset(
    {"subject_label", "summary", "reason_codes", "change_percent", "metric_refs", "quality_status"}
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(account.?number|cano|token|secret|chat.?id|계좌.?번호|총.?자산|평가액|예수금|"
    r"\bkrw\b|\busd\b|₩|\$|달러|\d[\d,]*(?:\.\d+)?\s*원|\d{8,10}:[a-z0-9_-]{20,})"
)
_ACCOUNT_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_ABSOLUTE_NUMBER = re.compile(r"(?<![\d.])\d{4,}(?:,\d{3})*(?![\d.])")
_PERCENT = re.compile(r"^-?\d{1,3}(?:\.\d{1,2})?$")
_SAFE_REASON = re.compile(r"^[a-z0-9_.:-]{1,80}$")


class UnsafeTelegramPayload(ValueError):
    """Raised before a request when a payload is not on the public allowlist."""


@dataclass(frozen=True, slots=True)
class TelegramSendResult:
    outcome: str
    error_code: str | None = None
    response_ref: str | None = None


def _safe_text(value: object, *, field: str, maximum: int, forbid_absolute: bool = False) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise UnsafeTelegramPayload(f"{field} is empty or exceeds its bounded length")
    if _SENSITIVE_TEXT.search(text) or _ACCOUNT_NUMBER.search(text):
        raise UnsafeTelegramPayload(f"{field} contains prohibited sensitive content")
    if forbid_absolute and _ABSOLUTE_NUMBER.search(text):
        raise UnsafeTelegramPayload(f"{field} contains a prohibited absolute value")
    return text


def render_telegram_alert(candidate: TelegramDispatchCandidate) -> str:
    """Render only allowlisted, non-absolute alert context as plain text."""
    context: Mapping[str, object] = candidate.public_context
    unexpected = sorted(set(context) - _ALLOWED_CONTEXT_KEYS)
    if unexpected:
        raise UnsafeTelegramPayload("public context contains non-allowlisted fields")
    if str(context.get("quality_status", "")) != "pass":
        raise UnsafeTelegramPayload("Telegram delivery requires pass quality")

    labels = {"watch": "주의", "warning": "경고", "critical": "긴급"}
    severity = labels.get(candidate.delivery_severity)
    if severity is None:
        raise UnsafeTelegramPayload("Telegram delivery requires watch or higher")
    subject = _safe_text(context.get("subject_label"), field="subject_label", maximum=80)
    summary = _safe_text(
        context.get("summary"), field="summary", maximum=500, forbid_absolute=True,
    )

    reasons_value = context.get("reason_codes", [])
    if not isinstance(reasons_value, list) or not reasons_value or len(reasons_value) > 8:
        raise UnsafeTelegramPayload("reason_codes must be a bounded non-empty list")
    reasons = [str(value) for value in reasons_value]
    if any(not _SAFE_REASON.fullmatch(value) for value in reasons):
        raise UnsafeTelegramPayload("reason_codes contain an unsafe value")

    change = context.get("change_percent")
    change_line = ""
    if change not in (None, ""):
        change_text = str(change)
        if not _PERCENT.fullmatch(change_text):
            raise UnsafeTelegramPayload("change_percent must be a bounded percentage")
        change_line = f"\n변화율: {change_text}%"

    transition = {
        "entered": "신규 감지",
        "reentered": "재진입",
        "escalated": "심각도 상승",
        "updated": "상태 변화",
        "recovered": "정상화",
    }.get(candidate.transition_type, "상태 변화")
    message = (
        f"[{severity}] {subject}\n"
        f"상태: {transition}\n"
        f"요약: {summary}{change_line}\n"
        f"근거: {', '.join(reasons)}\n"
        f"평가: {candidate.evaluation_at.isoformat()} / {candidate.evaluation_slot}\n"
        f"규칙: {candidate.rule_id}:{candidate.rule_version}\n"
        "다음 확인: KIS Portfolio에서 상세 품질과 근거를 확인하세요."
    )
    if len(message) > 3500 or _SENSITIVE_TEXT.search(message) or _ACCOUNT_NUMBER.search(message):
        raise UnsafeTelegramPayload("rendered Telegram payload is unsafe or too large")
    return message


class TelegramBotClient:
    """Minimal sendMessage client that never exposes provider bodies or request URLs."""

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Telegram timeout must be between 0 and 30 seconds")
        self._client = client or httpx.Client()
        self._timeout_seconds = timeout_seconds

    def send_message(self, *, bot_token: str, chat_id: str, text: str) -> TelegramSendResult:
        if not bot_token or not chat_id or not text:
            raise ValueError("Telegram credentials and text are required")
        try:
            response = self._client.post(
                f"{TELEGRAM_API_ROOT}/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            return TelegramSendResult("unknown", error_code="POST_SEND_TIMEOUT")
        except httpx.RequestError:
            return TelegramSendResult("unknown", error_code="TRANSPORT_UNKNOWN")

        if response.status_code == 429:
            return TelegramSendResult("retryable_failure", error_code="RATE_LIMITED")
        if response.status_code >= 500:
            return TelegramSendResult("retryable_failure", error_code="TELEGRAM_5XX")
        if response.status_code >= 400:
            return TelegramSendResult("permanent_failure", error_code="TELEGRAM_4XX")
        try:
            document = response.json()
            message_id = document["result"]["message_id"] if document.get("ok") is True else None
        except (KeyError, TypeError, ValueError):
            message_id = None
        if not isinstance(message_id, int):
            return TelegramSendResult("unknown", error_code="INVALID_RESPONSE")
        return TelegramSendResult("sent", response_ref=f"telegram-message:{message_id}")
