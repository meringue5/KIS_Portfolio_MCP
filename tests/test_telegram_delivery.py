from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import duckdb
import httpx
import pytest

from kis_portfolio.adapters.outbound.alert_warehouse import AlertClaimError, AlertWarehouseRepository
from kis_portfolio.adapters.outbound.telegram import (
    TelegramBotClient,
    TelegramSendResult,
    UnsafeTelegramPayload,
    render_telegram_alert,
)
from kis_portfolio.modules.monitoring import AlertCandidate, AlertEvaluation, AlertRuleVersion
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.telegram_delivery import TelegramDeliveryConfig, run_telegram_delivery


NOW = datetime(2026, 8, 30, 1, tzinfo=UTC)


class FakeTelegramClient:
    def __init__(self, result: TelegramSendResult) -> None:
        self.result = result
        self.calls = 0

    def send_message(self, *, bot_token: str, chat_id: str, text: str) -> TelegramSendResult:
        assert bot_token == "bot-secret" and chat_id == "private-chat"
        assert "private-chat" not in text and "bot-secret" not in text
        self.calls += 1
        return self.result


def _external_candidate() -> tuple[duckdb.DuckDBPyConnection, AlertWarehouseRepository, AlertCandidate]:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    repository = AlertWarehouseRepository(connection)
    rule = AlertRuleVersion.from_document({
        "id": "rule-set.owned-portfolio-monitoring",
        "version": "external-fixture-1.0.0",
        "status": "active",
        "minimum_delivery_severity": "watch",
        "delivery_mode": "external",
        "valid_from": NOW - timedelta(days=1),
        "valid_to": None,
        "metric_refs": ["price-shock"],
        "thresholds": {"profile": "fixture"},
    })
    candidate = AlertCandidate.build(rule, AlertEvaluation(
        subject_type="instrument",
        subject_id="instrument.opaque.samsung",
        evaluation_date=date(2026, 8, 30),
        evaluation_slot="kr-1000",
        session_key="krx:2026-08-30",
        evaluation_at=NOW,
        signal_state="active",
        severity="watch",
        state_key="price-shock-watch",
        quality_status="pass",
        input_lineage_hash="lineage-fixture",
        public_context={
            "subject_label": "삼성전자",
            "summary": "가격 충격과 거래량 증가가 함께 감지됨",
            "reason_codes": ["price-shock-watch", "volume-spike"],
            "change_percent": "-3.25",
            "metric_refs": ["price-shock"],
            "quality_status": "pass",
        },
        evaluation_run_id="run-fixture",
    ))
    repository.apply_candidate(candidate)
    connection.execute(
        """
        INSERT INTO control.alert_rule_approval_revisions(
            approval_revision_id,rule_id,rule_version,revision,decision,actor_type,
            calibration_run_id,shadow_window_id,evidence_hash,rationale_code,decided_at
        ) VALUES ('approval-fixture',?,?,1,'approved','owner','calibration-fixture',
                  'shadow-fixture',?,'OWNER_APPROVED',?)
        """,
        [rule.rule_id, rule.version, "a" * 64, NOW],
    )
    return connection, repository, candidate


def _config(**overrides: object) -> TelegramDeliveryConfig:
    values = {
        "enabled": True,
        "bot_token": "bot-secret",
        "chat_id": "private-chat",
        "destination_ref": "dest.owner.primary",
    }
    values.update(overrides)
    return TelegramDeliveryConfig(**values)


def test_disabled_delivery_creates_no_claim_or_network_request() -> None:
    connection, _, _ = _external_candidate()
    client = FakeTelegramClient(TelegramSendResult("sent", response_ref="telegram-message:1"))

    result = run_telegram_delivery(connection, config=_config(enabled=False), client=client, now=NOW)

    assert result == {
        "status": "disabled", "eligible_count": 0, "attempt_count": 0, "sent_count": 0,
        "unknown_count": 0, "retryable_failure_count": 0, "permanent_failure_count": 0,
    }
    assert client.calls == 0
    assert connection.execute("SELECT count(*) FROM control.alert_dispatch_claims").fetchone()[0] == 0


def test_missing_enabled_secrets_fails_before_claim() -> None:
    connection, _, _ = _external_candidate()

    with pytest.raises(RuntimeError, match="complete runtime secrets"):
        run_telegram_delivery(connection, config=_config(bot_token=""), now=NOW)

    assert connection.execute("SELECT count(*) FROM control.alert_dispatch_claims").fetchone()[0] == 0


def test_owner_approval_is_required_and_latest_revocation_wins() -> None:
    connection, repository, candidate = _external_candidate()
    connection.execute("DELETE FROM control.alert_rule_approval_revisions")
    assert repository.eligible_telegram_dispatches(as_of=NOW) == ()
    connection.execute(
        """
        INSERT INTO control.alert_rule_approval_revisions(
            approval_revision_id,rule_id,rule_version,revision,decision,actor_type,
            calibration_run_id,shadow_window_id,evidence_hash,rationale_code,decided_at
        ) VALUES ('approval-fixture-1',?,?,1,'approved','owner','calibration-fixture',
                  'shadow-fixture',?,'OWNER_APPROVED',?),
                 ('approval-fixture-2',?,?,2,'revoked','owner',NULL,NULL,?,'OWNER_REVOKED',?)
        """,
        [candidate.rule.rule_id, candidate.rule.version, "a" * 64, NOW,
         candidate.rule.rule_id, candidate.rule.version, "b" * 64, NOW + timedelta(seconds=1)],
    )
    assert repository.eligible_telegram_dispatches(as_of=NOW + timedelta(seconds=2)) == ()
    with pytest.raises(AlertClaimError, match="owner approval"):
        repository.claim_dispatch(
            candidate_id=candidate.candidate_id, channel="telegram",
            destination_ref="dest.owner.primary", claimant_id="worker.telegram.v1",
            lease_token="lease", claimed_at=NOW + timedelta(seconds=2),
        )


def test_renderer_is_plain_redacted_and_rejects_absolute_asset_text() -> None:
    _, repository, _ = _external_candidate()
    item = repository.eligible_telegram_dispatches(as_of=NOW)[0]

    message = render_telegram_alert(item)

    assert "[주의] 삼성전자" in message
    assert "변화율: -3.25%" in message
    assert "총자산" not in message and "계좌" not in message
    unsafe = item.__class__(
        **{**{field: getattr(item, field) for field in item.__dataclass_fields__},
           "public_context": {**item.public_context, "summary": "총자산 평가액이 변동함"}},
    )
    with pytest.raises(UnsafeTelegramPayload):
        render_telegram_alert(unsafe)
    numeric = item.__class__(
        **{**{field: getattr(item, field) for field in item.__dataclass_fields__},
           "public_context": {**item.public_context, "summary": "금액 변화 123456 감지"}},
    )
    with pytest.raises(UnsafeTelegramPayload):
        render_telegram_alert(numeric)
    currency = item.__class__(
        **{**{field: getattr(item, field) for field in item.__dataclass_fields__},
           "public_context": {**item.public_context, "summary": "가격 변화 500원 감지"}},
    )
    with pytest.raises(UnsafeTelegramPayload):
        render_telegram_alert(currency)


def test_success_is_hashed_in_ledger_and_never_persists_destination_secret() -> None:
    connection, _, _ = _external_candidate()
    client = FakeTelegramClient(TelegramSendResult("sent", response_ref="telegram-message:42"))

    result = run_telegram_delivery(connection, config=_config(), client=client, now=NOW)

    assert result["sent_count"] == 1 and client.calls == 1
    claim = connection.execute(
        "SELECT destination_ref,claim_status FROM control.alert_dispatch_claims WHERE channel='telegram'"
    ).fetchone()
    attempt = connection.execute(
        "SELECT outcome,response_ref_hash,error_code FROM control.alert_delivery_attempts"
    ).fetchone()
    assert claim == ("dest.owner.primary", "completed")
    assert attempt[0] == "sent" and len(attempt[1]) == 64 and attempt[2] is None
    dump = " ".join(str(value) for value in (*claim, *attempt))
    assert "private-chat" not in dump and "bot-secret" not in dump and "telegram-message:42" not in dump


def test_unknown_is_terminal_and_is_not_automatically_reacquired() -> None:
    connection, _, _ = _external_candidate()
    client = FakeTelegramClient(TelegramSendResult("unknown", error_code="POST_SEND_TIMEOUT"))

    first = run_telegram_delivery(connection, config=_config(), client=client, now=NOW)
    second = run_telegram_delivery(
        connection, config=_config(), client=client, now=NOW + timedelta(minutes=10),
    )

    assert first["unknown_count"] == 1
    assert second["eligible_count"] == 0 and client.calls == 1


def test_expired_claim_is_sealed_unknown_instead_of_being_resent() -> None:
    connection, repository, candidate = _external_candidate()
    repository.claim_dispatch(
        candidate_id=candidate.candidate_id,
        channel="telegram",
        destination_ref="dest.owner.primary",
        claimant_id="worker.telegram.v1",
        lease_token="orphaned-lease",
        claimed_at=NOW,
        lease_seconds=60,
    )

    eligible = repository.eligible_telegram_dispatches(as_of=NOW + timedelta(minutes=2))
    claim = connection.execute(
        "SELECT claim_status,last_error_code FROM control.alert_dispatch_claims WHERE channel='telegram'"
    ).fetchone()

    assert eligible == ()
    assert claim == ("unknown", "CLAIM_EXPIRED_UNKNOWN")


def test_retryable_failure_is_only_retried_by_a_later_run() -> None:
    connection, _, _ = _external_candidate()
    failed = FakeTelegramClient(TelegramSendResult("retryable_failure", error_code="RATE_LIMITED"))
    sent = FakeTelegramClient(TelegramSendResult("sent", response_ref="telegram-message:43"))

    first = run_telegram_delivery(connection, config=_config(), client=failed, now=NOW)
    second = run_telegram_delivery(
        connection, config=_config(), client=sent, now=NOW + timedelta(minutes=10),
    )

    assert first["retryable_failure_count"] == 1 and failed.calls == 1
    assert second["sent_count"] == 1 and sent.calls == 1
    assert connection.execute("SELECT count(*) FROM control.alert_delivery_attempts").fetchone()[0] == 2


@pytest.mark.parametrize(
    ("status", "expected_outcome", "expected_code"),
    [(429, "retryable_failure", "RATE_LIMITED"), (503, "retryable_failure", "TELEGRAM_5XX"),
     (403, "permanent_failure", "TELEGRAM_4XX")],
)
def test_http_client_classifies_status_without_provider_body(
    status: int, expected_outcome: str, expected_code: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json={"description": "sensitive provider body"})
    )
    client = TelegramBotClient(client=httpx.Client(transport=transport))

    result = client.send_message(bot_token="bot-secret", chat_id="private-chat", text="safe")

    assert (result.outcome, result.error_code, result.response_ref) == (
        expected_outcome, expected_code, None,
    )
    assert "sensitive" not in repr(result) and "bot-secret" not in repr(result)


def test_http_timeout_is_terminal_unknown() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = TelegramBotClient(client=httpx.Client(transport=httpx.MockTransport(timeout)))

    result = client.send_message(bot_token="bot-secret", chat_id="private-chat", text="safe")

    assert result == TelegramSendResult("unknown", error_code="POST_SEND_TIMEOUT")


def test_config_repr_does_not_expose_runtime_secrets() -> None:
    representation = repr(_config())

    assert "bot-secret" not in representation and "private-chat" not in representation
