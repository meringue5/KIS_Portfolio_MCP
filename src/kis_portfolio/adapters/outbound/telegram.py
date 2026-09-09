"""Fail-closed outbound Telegram rendering and transport primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import httpx

from kis_portfolio.adapters.outbound.alert_warehouse import TelegramDispatchCandidate
from kis_portfolio.adapters.outbound.portfolio_chart import ChartAllocation, render_portfolio_chart


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


@dataclass(frozen=True, slots=True)
class TelegramRichMessage:
    """A validated Telegram Rich Message document."""

    html: str


@dataclass(frozen=True, slots=True)
class TotalAssetDigestContributor:
    """One privacy-safe contributor shown in the scheduled total-asset digest."""

    label: str
    impact_percent_points: Decimal


@dataclass(frozen=True, slots=True)
class TotalAssetDigest:
    """Privacy-safe scheduled digest; absolute portfolio values are intentionally absent."""

    slot: str
    source_at: datetime
    quality_status: str
    total_change_percent: Decimal | None = None
    positive: Sequence[TotalAssetDigestContributor] = ()
    negative: Sequence[TotalAssetDigestContributor] = ()
    cash_impact_percent_points: Decimal | None = None
    reconciliation_status: str | None = None
    unavailable_codes: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class OwnerPortfolioReport:
    """Owner-only total-asset report with alias-only allocation dimensions."""

    slot: str
    source_at: datetime
    quality_status: str
    total_asset_krw: int | None = None
    total_change_krw: int | None = None
    total_change_percent: Decimal | None = None
    asset_allocations: Sequence[ChartAllocation] = ()
    account_allocations: Sequence[ChartAllocation] = ()
    positive: Sequence[TotalAssetDigestContributor] = ()
    negative: Sequence[TotalAssetDigestContributor] = ()
    unavailable_codes: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class TelegramPhotoMessage:
    """Validated single-operation Telegram photo and HTML caption."""

    caption_html: str
    png_bytes: bytes
    filename: str = "total-asset-report.png"


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


def _bounded_percent(value: Decimal, *, field: str) -> str:
    if not value.is_finite() or abs(value) > Decimal("1000"):
        raise UnsafeTelegramPayload(f"{field} must be a bounded percentage")
    return f"{value.quantize(Decimal('0.01')):.2f}"


def render_total_asset_digest(digest: TotalAssetDigest) -> TelegramRichMessage:
    """Render a scheduled total-asset digest without absolute assets or account data."""
    slot_labels = {"kr-1000": "오전 10시", "kr-1600": "오후 4시"}
    slot_label = slot_labels.get(digest.slot)
    if slot_label is None:
        raise UnsafeTelegramPayload("total-asset digest slot is not allowlisted")
    if digest.source_at.tzinfo is None:
        raise UnsafeTelegramPayload("total-asset digest source_at must be timezone-aware")
    source_at = digest.source_at.astimezone(_SEOUL)
    if digest.quality_status not in {"pass", "unavailable"}:
        raise UnsafeTelegramPayload("total-asset digest quality is not allowlisted")

    if digest.quality_status == "unavailable":
        if digest.total_change_percent is not None or digest.positive or digest.negative:
            raise UnsafeTelegramPayload("unavailable total-asset digest cannot contain calculated values")
        if not digest.unavailable_codes or any(
            not _SAFE_REASON.fullmatch(str(code)) for code in digest.unavailable_codes
        ):
            raise UnsafeTelegramPayload("unavailable total-asset digest requires bounded reason codes")
        reason_labels = {
            "missing_market_calendar": "전 거래일 확인 불가",
            "missing_prior_state": "이전 동일 시각 상태 없음",
            "missing_current_state": "현재 상태 없음",
            "state_quality_failed": "비교 상태 품질 미달",
            "reconciliation_failed": "합계 정합성 미달",
        }
        reasons = [reason_labels.get(str(code), "데이터 품질 확인 필요") for code in digest.unavailable_codes]
        html = (
            f"<h3>⚪ 총자산 현황 · {slot_label}</h3>"
            "<p><b>전 거래일 동일 시각 대비 계산 보류</b><br>"
            "불완전한 상태를 자산 변동으로 해석하지 않았습니다.</p>"
            "<details><summary>보류 사유</summary><p>"
            + escape(" · ".join(dict.fromkeys(reasons)))
            + "</p></details>"
            f"<footer>{source_at:%Y-%m-%d %H:%M} · KST</footer>"
        )
    else:
        if digest.total_change_percent is None or digest.reconciliation_status != "pass":
            raise UnsafeTelegramPayload("pass total-asset digest requires reconciled change")
        change = _bounded_percent(digest.total_change_percent, field="total_change_percent")
        rows: list[tuple[str, str]] = []
        for direction, contributors in (("상승", digest.positive), ("하락", digest.negative)):
            if len(contributors) > 3:
                raise UnsafeTelegramPayload("total-asset digest contributor count exceeds top three")
            for index, contributor in enumerate(contributors, start=1):
                label = _safe_text(
                    contributor.label, field="contributor_label", maximum=80,
                )
                impact = _bounded_percent(
                    contributor.impact_percent_points, field="impact_percent_points",
                )
                prefix = "+" if contributor.impact_percent_points > 0 else ""
                rows.append((f"{direction} {index}", f"{label} {prefix}{impact}%p"))
        if digest.cash_impact_percent_points is not None:
            cash = _bounded_percent(
                digest.cash_impact_percent_points, field="cash_impact_percent_points",
            )
            prefix = "+" if digest.cash_impact_percent_points > 0 else ""
            rows.append(("현금 영향", f"{prefix}{cash}%p"))
        rows.append(("합계 검증", "일치"))
        body = "".join(
            f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>" for label, value in rows
        )
        prefix = "+" if digest.total_change_percent > 0 else ""
        html = (
            f"<h3>📊 총자산 현황 · {slot_label}</h3>"
            f"<p><b>전 거래일 동일 시각 대비 {prefix}{change}%</b><br>"
            "보유 종목의 원화 평가액 변화 영향입니다.</p>"
            f"<table bordered striped compact><tbody>{body}</tbody></table>"
            "<details><summary>해석 기준</summary><p>"
            "해외 종목은 환율 효과를 포함하며 투자수익 기여도가 아닙니다."
            "</p></details>"
            f"<footer>{source_at:%Y-%m-%d %H:%M} · KST</footer>"
        )
    if len(html) > 3500 or _ACCOUNT_NUMBER.search(html):
        raise UnsafeTelegramPayload("rendered total-asset digest is unsafe or too large")
    return TelegramRichMessage(html=html)


_OWNER_ACCOUNT_ALIASES = frozenset({"ria", "isa", "brokerage", "irp", "pension"})
_ASSET_LABELS = frozenset({"DOMESTIC", "OVERSEAS", "CASH"})


def _format_krw(value: int, *, signed: bool = False) -> str:
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}₩{value:,}"


def _validate_allocations(
    allocations: Sequence[ChartAllocation], *, allowed: frozenset[str], field: str,
) -> tuple[ChartAllocation, ...]:
    if not allocations or len(allocations) > 5:
        raise UnsafeTelegramPayload(f"{field} must contain one to five rows")
    checked: list[ChartAllocation] = []
    for item in allocations:
        label = item.label.strip().lower() if field == "account_allocations" else item.label.strip().upper()
        if label not in allowed or item.value_krw < 0:
            raise UnsafeTelegramPayload(f"{field} contains an unsafe label or value")
        if not item.percent.is_finite() or item.percent < 0 or item.percent > Decimal("100"):
            raise UnsafeTelegramPayload(f"{field} contains an unsafe percentage")
        checked.append(ChartAllocation(label, int(item.value_krw), item.percent))
    return tuple(checked)


def render_owner_portfolio_report(report: OwnerPortfolioReport) -> TelegramRichMessage | TelegramPhotoMessage:
    """Render exact owner values only after complete state and alias-boundary validation."""
    slot_labels = {"kr-1000": "오전 10시", "kr-1600": "오후 4시"}
    slot_label = slot_labels.get(report.slot)
    if slot_label is None or report.source_at.tzinfo is None:
        raise UnsafeTelegramPayload("owner report slot and source_at must be valid")
    source_at = report.source_at.astimezone(_SEOUL)
    if report.quality_status == "unavailable":
        if any(value is not None for value in (
            report.total_asset_krw, report.total_change_krw, report.total_change_percent,
        )) or report.asset_allocations or report.account_allocations or report.positive or report.negative:
            raise UnsafeTelegramPayload("unavailable owner report cannot contain financial values")
        return render_total_asset_digest(TotalAssetDigest(
            report.slot, report.source_at, "unavailable", unavailable_codes=report.unavailable_codes,
        ))
    if report.quality_status != "pass":
        raise UnsafeTelegramPayload("owner report quality is not allowlisted")
    if report.total_asset_krw is None or report.total_asset_krw <= 0:
        raise UnsafeTelegramPayload("owner report requires a positive total")
    if report.total_change_krw is None or report.total_change_percent is None:
        raise UnsafeTelegramPayload("owner report requires exact change values")
    if not report.total_change_percent.is_finite() or abs(report.total_change_percent) > Decimal("1000"):
        raise UnsafeTelegramPayload("owner report change percentage is unsafe")
    assets = _validate_allocations(report.asset_allocations, allowed=_ASSET_LABELS, field="asset_allocations")
    accounts = _validate_allocations(
        report.account_allocations, allowed=_OWNER_ACCOUNT_ALIASES, field="account_allocations",
    )
    tolerance = max(1, round(report.total_asset_krw * 0.000001))
    if abs(sum(item.value_krw for item in assets) - report.total_asset_krw) > tolerance:
        raise UnsafeTelegramPayload("asset allocation does not reconcile to total")
    if abs(sum(item.value_krw for item in accounts) - report.total_asset_krw) > tolerance:
        raise UnsafeTelegramPayload("account allocation does not reconcile to total")
    for item in (*assets, *accounts):
        expected = Decimal(item.value_krw) / Decimal(report.total_asset_krw) * Decimal("100")
        if abs(item.percent - expected) > Decimal("0.02"):
            raise UnsafeTelegramPayload("allocation percentage does not reconcile to value")

    change_prefix = "+" if report.total_change_percent > 0 else ""
    lines = [
        f"<b>📊 총자산 현황 · {slot_label}</b>",
        f"<b>{_format_krw(report.total_asset_krw)}</b>",
        (
            "전 거래일 동일 시각 대비 "
            f"{_format_krw(report.total_change_krw, signed=True)} "
            f"({change_prefix}{report.total_change_percent.quantize(Decimal('0.01')):.2f}%)"
        ),
        "",
        "<b>계좌 구성</b>",
    ]
    lines.extend(
        f"• {escape(item.label.upper())}: {_format_krw(item.value_krw)} · {item.percent:.2f}%"
        for item in accounts
    )
    lines.extend(("", "<b>자산 구성</b>"))
    asset_names = {"DOMESTIC": "국내", "OVERSEAS": "해외", "CASH": "현금"}
    lines.extend(
        f"• {asset_names[item.label]}: {_format_krw(item.value_krw)} · {item.percent:.2f}%"
        for item in assets
    )
    if report.positive or report.negative:
        lines.extend(("", "<b>평가액 변화 기여</b>"))
    for marker, contributors in (("▲", report.positive), ("▼", report.negative)):
        for item in contributors[:3]:
            label = _safe_text(item.label, field="contributor_label", maximum=80)
            impact = _bounded_percent(item.impact_percent_points, field="impact_percent_points")
            prefix = "+" if item.impact_percent_points > 0 else ""
            lines.append(f"{marker} {escape(label)} {prefix}{impact}%p")
    lines.extend(("", "해외 자산은 환율 효과를 포함한 원화 평가액입니다.", f"{source_at:%Y-%m-%d %H:%M} · KST"))
    caption = "\n".join(lines)
    if len(caption) > 1000 or _ACCOUNT_NUMBER.search(caption):
        raise UnsafeTelegramPayload("owner report caption is unsafe or too large")
    png = render_portfolio_chart(
        total_asset_krw=report.total_asset_krw,
        change_krw=report.total_change_krw,
        change_percent=report.total_change_percent,
        asset_allocations=assets,
        account_allocations=accounts,
    )
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 10_000_000:
        raise UnsafeTelegramPayload("owner report chart is invalid or too large")
    return TelegramPhotoMessage(caption, png)


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

    drawdown = _optional_decimal(context, "episode_drawdown_percent")
    impact = _optional_decimal(context, "portfolio_impact_percent")
    if drawdown is None and "episode_drawdown_not_ready" not in unavailable_set:
        raise UnsafeTelegramPayload("missing episode drawdown requires an explicit unavailable reason")
    if impact is None and "valuation_contribution_not_ready" not in unavailable_set:
        raise UnsafeTelegramPayload("missing valuation contribution requires an explicit unavailable reason")
    change = _optional_decimal(context, "change_percent")
    source_text = _safe_text(context.get("source_at"), field="source_at", maximum=40)
    try:
        source_at = datetime.fromisoformat(source_text)
    except ValueError as exc:
        raise UnsafeTelegramPayload("source_at must be ISO-8601") from exc
    if source_at.tzinfo is None:
        raise UnsafeTelegramPayload("source_at must be timezone-aware")
    source_at = source_at.astimezone(_SEOUL)
    severity_icon = {"주의": "🟡", "경고": "🟠", "긴급": "🔴"}[severity]
    signal_labels = {
        "price_shock_up": "급등 신호", "price_shock_down": "급락 신호",
        "sma20_downward_cross": "20일선 하향 이탈", "bearish_sma20_regime": "20일선 하회",
        "bearish_sma50_drawdown": "중기 약세", "volume_confirmation": "거래량 확인",
        "portfolio_contribution": "포트폴리오 영향", "episode_drawdown": "보유구간 낙폭",
        "thread_stop_breach": "손절 기준 이탈", "thread_risk_ratio": "계획손실 경고",
    }
    reasons = [str(value) for value in context.get("reason_codes", [])]
    signal = signal_labels.get(reasons[0], "상태 변화")
    transition_suffix = {
        "주의 신호 신규 감지": "신규", "주의 신호 재발생": "재발생",
        "심각도 상승": "강도 상승", "상태 변화": "상태 변화", "정상화": "정상화",
    }[transition]
    headline_change = ""
    if change is not None:
        headline_change = f" {'+' if Decimal(change) > 0 else ''}{change}%"

    rows: list[tuple[str, str]] = []
    available_relations = [value for value in relations if not value.endswith("계산 보류")]
    if available_relations:
        rows.append(("가격 위치", " · ".join(available_relations)))
    if average_relation != "unavailable":
        rows.append(("이평선", f"20일선이 50일선 {relation_labels[average_relation]}"))
    if volume is not None:
        rows.append(("거래량", f"20일 평균 대비 {volume}배"))
    if rsi is not None:
        rows.append(("RSI(14)", rsi))
    if bollinger != "unavailable":
        rows.append(("볼린저", bollinger_labels[bollinger]))
    if drawdown is not None:
        rows.append(("보유구간 낙폭", f"{drawdown}%"))
    if impact is not None:
        rows.append(("포트폴리오 영향", f"{impact}%p (원화 평가액 변화)"))

    missing: list[str] = []
    missing.extend(
        f"{period}일선" for period, value in zip((20, 50, 120), relations, strict=True)
        if value.endswith("계산 보류")
    )
    if average_relation == "unavailable":
        missing.append("20·50일선 구조")
    if volume is None:
        missing.append("동시간대 거래량" if "intraday_volume_not_comparable" in unavailable_set else "거래량")
    if rsi is None:
        missing.append("RSI")
    if bollinger == "unavailable":
        missing.append("볼린저")
    if drawdown is None:
        missing.append("보유구간 낙폭")
    if impact is None:
        missing.append("포트폴리오 영향")

    table = ""
    if rows:
        body = "".join(
            f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>" for label, value in rows
        )
        table = f"<table bordered striped compact><tbody>{body}</tbody></table>"
    details = ""
    if missing:
        details = (
            "<details><summary>미산출 항목</summary><p>"
            + escape(" · ".join(dict.fromkeys(missing)))
            + "</p></details>"
        )
    return (
        f"<h3>{severity_icon} {escape(subject)}{escape(headline_change)}</h3>"
        f"<p><b>{escape(signal)} · {escape(transition_suffix)}</b><br>{escape(summary)}</p>"
        f"{table}{details}"
        f"<footer>{source_at:%Y-%m-%d %H:%M} · {escape(market)} {escape(asset_type)}</footer>"
    )


def render_telegram_alert(candidate: TelegramDispatchCandidate) -> TelegramRichMessage:
    """Render only allowlisted, non-absolute alert context as Telegram Rich HTML."""
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
    if context.get("presentation_version") in {
        "production-value-v1", "production-value-v2", "production-value-v3",
    }:
        message = _production_value_message(candidate, severity, transition)
    else:
        subject = _safe_text(context.get("subject_label"), field="subject_label", maximum=80)
        summary = _safe_text(
            context.get("summary"), field="summary", maximum=500, forbid_absolute=True,
        )
        message = (
            f"<h3>{escape({'주의': '🟡', '경고': '🟠', '긴급': '🔴'}[severity])} "
            f"{escape(subject)}{escape(change_line.replace(chr(10) + '변화율:', ''))}</h3>"
            f"<p><b>{escape(transition)}</b><br>{escape(summary)}</p>"
            f"<footer>{candidate.evaluation_at.astimezone(_SEOUL):%Y-%m-%d %H:%M}</footer>"
        )
    # Every dynamic string and numeric value is validated before interpolation.
    # Reapplying the broad input-keyword filter to trusted template text would
    # reject labels such as "원화 평가액 변화" once that governed metric is ready.
    if len(message) > 3500 or _ACCOUNT_NUMBER.search(message):
        raise UnsafeTelegramPayload("rendered Telegram payload is unsafe or too large")
    return TelegramRichMessage(html=message)


class TelegramBotClient:
    """Minimal sendRichMessage client that never exposes provider bodies or request URLs."""

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Telegram timeout must be between 0 and 30 seconds")
        self._client = client or httpx.Client()
        self._timeout_seconds = timeout_seconds

    def send_rich_message(
        self, *, bot_token: str, chat_id: str, message: TelegramRichMessage,
    ) -> TelegramSendResult:
        if not bot_token or not chat_id or not message.html:
            raise ValueError("Telegram credentials and Rich Message HTML are required")
        try:
            response = self._client.post(
                f"{TELEGRAM_API_ROOT}/bot{bot_token}/sendRichMessage",
                json={
                    "chat_id": chat_id,
                    "rich_message": {"html": message.html, "skip_entity_detection": True},
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

    def send_photo_message(
        self, *, bot_token: str, chat_id: str, message: TelegramPhotoMessage,
    ) -> TelegramSendResult:
        """Send one photo+caption operation without logging or retrying financial content."""
        if not bot_token or not chat_id or not message.caption_html or not message.png_bytes:
            raise ValueError("Telegram credentials and photo message are required")
        try:
            response = self._client.post(
                f"{TELEGRAM_API_ROOT}/bot{bot_token}/sendPhoto",
                data={"chat_id": chat_id, "caption": message.caption_html, "parse_mode": "HTML"},
                files={"photo": (message.filename, message.png_bytes, "image/png")},
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
