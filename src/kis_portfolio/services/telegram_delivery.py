"""Governed Telegram delivery orchestration with an explicit disabled default."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Mapping

import duckdb

from kis_portfolio.adapters.outbound.alert_warehouse import AlertWarehouseRepository
from kis_portfolio.adapters.outbound.telegram import (
    TelegramBotClient,
    TelegramPhotoMessage,
    TelegramRichMessage,
    TelegramSendResult,
    UnsafeTelegramPayload,
    render_telegram_alert,
)
from kis_portfolio.adapters.outbound.portfolio_chart import render_photo_transport_smoke_chart
from kis_portfolio.modules.monitoring.alerts import validate_opaque_code


RICH_TRANSPORT_SMOKE_HTML = (
    "<h3>🟡 KIS Portfolio 리치 메시지 운영 점검</h3>"
    "<p><b>실제 금융 경보가 아닙니다.</b><br>"
    "Cloud Run 운영 경로에서 Telegram Rich Message 전송을 확인했습니다.</p>"
    "<table bordered striped compact><tbody>"
    "<tr><td>점검 대상</td><td>운영 전송 경로</td></tr>"
    "<tr><td>금융 데이터</td><td>포함하지 않음</td></tr>"
    "</tbody></table>"
    "<details><summary>안내</summary><p>이 메시지는 배포 차단형 전송 점검입니다.</p></details>"
    "<footer>KIS Portfolio · transport smoke</footer>"
)

PHOTO_TRANSPORT_SMOKE_CAPTION = (
    "<b>🟢 KIS Portfolio 이미지 전송 점검</b>\n"
    "실제 금융 데이터가 없는 배포 차단형 테스트입니다."
)


def run_telegram_rich_transport_smoke(
    *,
    config: TelegramDeliveryConfig | None = None,
    client: TelegramBotClient | None = None,
) -> TelegramSendResult:
    """Send one finance-free Rich Message and fail the caller unless Telegram confirms it."""
    config = config or TelegramDeliveryConfig.from_env()
    config.validate_for_send()
    if not config.enabled:
        raise RuntimeError("Telegram Rich Message smoke requires explicit delivery enablement")
    transport = client or TelegramBotClient(timeout_seconds=30.0)
    return transport.send_rich_message(
        bot_token=config.bot_token,
        chat_id=config.chat_id,
        message=TelegramRichMessage(RICH_TRANSPORT_SMOKE_HTML),
    )


def run_telegram_photo_transport_smoke(
    *,
    config: TelegramDeliveryConfig | None = None,
    client: TelegramBotClient | None = None,
) -> TelegramSendResult:
    """Send one finance-free PNG and fail the release unless Telegram confirms it."""
    config = config or TelegramDeliveryConfig.from_env()
    config.validate_for_send()
    if not config.enabled or config.destination_ref != "dest.owner.primary":
        raise RuntimeError("Telegram photo smoke requires the verified owner destination")
    transport = client or TelegramBotClient(timeout_seconds=30.0)
    return transport.send_photo_message(
        bot_token=config.bot_token,
        chat_id=config.chat_id,
        message=TelegramPhotoMessage(PHOTO_TRANSPORT_SMOKE_CAPTION, render_photo_transport_smoke_chart()),
    )


@dataclass(frozen=True, slots=True)
class TelegramDeliveryConfig:
    enabled: bool = False
    bot_token: str = field(default="", repr=False)
    chat_id: str = field(default="", repr=False)
    destination_ref: str = "dest.owner.primary"
    claimant_id: str = "worker.telegram.v1"
    max_dispatches: int = 20

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TelegramDeliveryConfig":
        values = os.environ if env is None else env
        enabled_value = values.get("KIS_TELEGRAM_DELIVERY_ENABLED", "false").strip().lower()
        if enabled_value not in {"true", "false"}:
            raise ValueError("KIS_TELEGRAM_DELIVERY_ENABLED must be true or false")
        return cls(
            enabled=enabled_value == "true",
            bot_token=values.get("KIS_TELEGRAM_BOT_TOKEN", ""),
            chat_id=values.get("KIS_TELEGRAM_CHAT_ID", ""),
            destination_ref=values.get("KIS_TELEGRAM_DESTINATION_REF", "dest.owner.primary"),
        )

    def validate_for_send(self) -> None:
        validate_opaque_code(self.destination_ref, "destination_ref")
        validate_opaque_code(self.claimant_id, "claimant_id")
        if self.max_dispatches <= 0 or self.max_dispatches > 100:
            raise ValueError("Telegram max_dispatches must be between 1 and 100")
        if self.enabled and (not self.bot_token or not self.chat_id):
            raise RuntimeError("Telegram delivery is enabled without complete runtime secrets")


def run_telegram_delivery(
    connection: duckdb.DuckDBPyConnection,
    *,
    config: TelegramDeliveryConfig | None = None,
    client: TelegramBotClient | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Send each eligible claim at most once; terminal unknown is never reacquired."""
    config = config or TelegramDeliveryConfig.from_env()
    if not config.enabled:
        return {
            "status": "disabled",
            "eligible_count": 0,
            "attempt_count": 0,
            "sent_count": 0,
            "unknown_count": 0,
            "retryable_failure_count": 0,
            "permanent_failure_count": 0,
        }
    config.validate_for_send()

    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("Telegram delivery time must be timezone-aware")
    repository = AlertWarehouseRepository(connection)
    candidates = repository.eligible_telegram_dispatches(
        as_of=timestamp,
        limit=config.max_dispatches,
    )
    transport = client or TelegramBotClient()
    counts = {
        "attempt_count": 0,
        "sent_count": 0,
        "unknown_count": 0,
        "retryable_failure_count": 0,
        "permanent_failure_count": 0,
    }
    for candidate in candidates:
        lease_token = secrets.token_urlsafe(32)
        claim = repository.claim_dispatch(
            candidate_id=candidate.candidate_id,
            channel="telegram",
            destination_ref=config.destination_ref,
            claimant_id=config.claimant_id,
            lease_token=lease_token,
            claimed_at=timestamp,
        )
        if not claim.acquired:
            continue
        try:
            message = render_telegram_alert(candidate)
        except UnsafeTelegramPayload:
            result = TelegramSendResult("permanent_failure", error_code="UNSAFE_PAYLOAD")
        else:
            try:
                result = transport.send_rich_message(
                    bot_token=config.bot_token,
                    chat_id=config.chat_id,
                    message=message,
                )
            except Exception:
                result = TelegramSendResult("unknown", error_code="TRANSPORT_EXCEPTION")
        repository.record_attempt(
            dispatch_id=claim.dispatch_id,
            lease_token=lease_token,
            outcome=result.outcome,
            started_at=timestamp,
            completed_at=datetime.now(UTC) if now is None else timestamp,
            response_ref=result.response_ref,
            error_code=result.error_code,
        )
        counts["attempt_count"] += 1
        counts[f"{result.outcome}_count"] += 1
    return {
        "status": "completed",
        "eligible_count": len(candidates),
        **counts,
    }
