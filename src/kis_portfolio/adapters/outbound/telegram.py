"""Fail-closed outbound Telegram rendering and transport primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from zoneinfo import ZoneInfo

import httpx

from kis_portfolio.adapters.outbound.alert_warehouse import TelegramDispatchCandidate


TELEGRAM_API_ROOT = "https://api.telegram.org"
_ALLOWED_CONTEXT_KEYS = frozenset({
    "presentation_version", "subject_label", "market_label", "asset_type_label", "summary",
    "reason_codes", "change_percent", "sma20_relation", "sma50_relation", "sma120_relation",
    "sma20_sma50_relation",
    "volume_ratio20", "rsi14", "bollinger_state", "episode_drawdown_percent",
    "portfolio_impact_percent", "unavailable_codes", "source_at", "metric_refs", "quality_status",
})
_SENSITIVE_TEXT = re.compile(
    r"(?i)(account.?number|cano|token|secret|chat.?id|계좌.?번호|총.?자산|평가액|예수금|"
    r"\bkrw\b|\busd\b|₩|\$|달러|\d[\d,]*(?:\.\d+)?\s*원|\d{8,10}:[a-z0-9_-]{20,})"
)
_ACCOUNT_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_ABSOLUTE_NUMBER = re.compile(r"(?<![\d.])\d{4,}(?:,\d{3})*(?![\d.])")
_PERCENT = re.compile(r"^-?\d{1,3}(?:\.\d{1,2})?$")
_SAFE_REASON = re.compile(r"^[a-z0-9_.:-]{1,80}$")
_SAFE_DECIMAL = re.compile(r"^-?\d{1,3}(?:\.\d{1,2})?$")
_SEOUL = ZoneInfo("Asia/Seoul")


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


def _optional_decimal(context: Mapping[str, object], key: str) -> str | None:
    value = context.get(key)
    if value in (None, ""):
        return None
    text = str(value)
    if not _SAFE_DECIMAL.fullmatch(text):
        raise UnsafeTelegramPayload(f"{key} must be a bounded decimal")
    return text


def _production_value_message(candidate: TelegramDispatchCandidate, severity: str, transition: str) -> str:
    context = candidate.public_context
    subject = _safe_text(context.get("subject_label"), field="subject_label", maximum=80)
    market = _safe_text(context.get("market_label"), field="market_label", maximum=40)
    asset_type = _safe_text(context.get("asset_type_label"), field="asset_type_label", maximum=40)
    summary = _safe_text(context.get("summary"), field="summary", maximum=500, forbid_absolute=True)

    relation_labels = {"above": "위", "below": "아래", "equal": "같음", "unavailable": "계산 보류"}
    relations: list[str] = []
    for period in (20, 50, 120):
        relation = str(context.get(f"sma{period}_relation", ""))
        if relation not in relation_labels:
            raise UnsafeTelegramPayload("SMA relation is not allowlisted")
        relations.append(f"{period}일선 {relation_labels[relation]}")
    average_relation = str(context.get("sma20_sma50_relation", ""))
    if average_relation not in relation_labels:
        raise UnsafeTelegramPayload("moving-average relation is not allowlisted")

    volume = _optional_decimal(context, "volume_ratio20")
    rsi = _optional_decimal(context, "rsi14")
    bollinger = str(context.get("bollinger_state", ""))
    bollinger_labels = {
        "below_lower": "하단 이탈", "inside": "밴드 안", "above_upper": "상단 돌파",
        "unavailable": "계산 보류",
    }
    if bollinger not in bollinger_labels:
        raise UnsafeTelegramPayload("Bollinger state is not allowlisted")
    unavailable = context.get("unavailable_codes", [])
    if not isinstance(unavailable, list) or any(not _SAFE_REASON.fullmatch(str(code)) for code in unavailable):
        raise UnsafeTelegramPayload("unavailable_codes must be an allowlisted list")
    unavailable_set = {str(code) for code in unavailable}
    if volume is not None:
        volume_text = f"직전 20일 평균의 {volume}배"
    elif "intraday_volume_not_comparable" in unavailable_set:
        volume_text = "장중 거래량 비교 보류 (동시간대 기준 미구축)"
    else:
        volume_text = "거래량 계산 보류"
    momentum = volume_text + " · " + (f"RSI(14) {rsi}" if rsi is not None else "RSI 계산 보류")
    momentum += f" · 볼린저 {bollinger_labels[bollinger]}"

    drawdown = _optional_decimal(context, "episode_drawdown_percent")
    impact = _optional_decimal(context, "portfolio_impact_percent")
    if drawdown is None and "episode_drawdown_not_ready" not in unavailable_set:
        raise UnsafeTelegramPayload("missing episode drawdown requires an explicit unavailable reason")
    if impact is None and "valuation_contribution_not_ready" not in unavailable_set:
        raise UnsafeTelegramPayload("missing valuation contribution requires an explicit unavailable reason")
    drawdown_line = (
        f"보유구간 낙폭: {drawdown}%"
        if drawdown is not None else "보유구간 낙폭: 계산 보류 (포지션 이력 정합성 확인 중)"
    )
    impact_line = (
        f"포트폴리오 영향: {impact}%p (원화 기준 변화 기여, 해외 환율 포함)"
        if impact is not None else "포트폴리오 영향: 계산 보류 (비교 가능한 전일 상태 확인 중)"
    )
    deferred_scopes: list[str] = []
    if drawdown is None:
        deferred_scopes.append("보유구간")
    if impact is None:
        deferred_scopes.append("기여도")
    data_status = "가격·추세 정상"
    if deferred_scopes:
        data_status += f" · {'·'.join(deferred_scopes)} 계산 보류"

    change = _optional_decimal(context, "change_percent")
    source_text = _safe_text(context.get("source_at"), field="source_at", maximum=40)
    try:
        source_at = datetime.fromisoformat(source_text)
    except ValueError as exc:
        raise UnsafeTelegramPayload("source_at must be ISO-8601") from exc
    if source_at.tzinfo is None:
        raise UnsafeTelegramPayload("source_at must be timezone-aware")
    evaluation_at = candidate.evaluation_at.astimezone(_SEOUL)
    source_at = source_at.astimezone(_SEOUL)
    change_line = f"가격: 오늘 {change}%" if change is not None else "가격: 변화율 계산 보류"
    return (
        f"[{severity}] {subject} · {market} · {asset_type}\n"
        f"상태: {transition}\n"
        f"핵심: {summary}\n"
        f"{change_line}\n"
        f"가격 위치: {' · '.join(relations)}\n"
        f"이평선 구조: 20일선이 50일선 {relation_labels[average_relation]}\n"
        f"거래량/모멘텀: {momentum}\n"
        f"{drawdown_line}\n"
        f"{impact_line}\n"
        f"데이터: {data_status} · 기준 {source_at:%Y-%m-%d %H:%M KST}\n"
        f"평가: {evaluation_at:%Y-%m-%d %H:%M KST} / {candidate.evaluation_slot}\n"
        "다음 확인: KIS Portfolio에서 차트와 상세 근거를 확인하세요."
    )


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
        "entered": "주의 신호 신규 감지",
        "reentered": "주의 신호 재발생",
        "escalated": "심각도 상승",
        "updated": "상태 변화",
        "recovered": "정상화",
    }.get(candidate.transition_type, "상태 변화")
    if context.get("presentation_version") in {"production-value-v1", "production-value-v2"}:
        message = _production_value_message(candidate, severity, transition)
    else:
        subject = _safe_text(context.get("subject_label"), field="subject_label", maximum=80)
        summary = _safe_text(
            context.get("summary"), field="summary", maximum=500, forbid_absolute=True,
        )
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
