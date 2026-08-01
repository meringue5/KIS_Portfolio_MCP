from kis_portfolio.services.alerts import _build_alert_request


def test_telegram_alert_url_builds_send_message_payload_without_query_secret():
    endpoint, payload, provider = _build_alert_request(
        "https://api.telegram.org/botsecret-token/sendMessage?chat_id=-123456",
        "collect-asset-overview-snapshot",
        "degraded",
        "FX rate is missing",
    )

    assert endpoint == "https://api.telegram.org/botsecret-token/sendMessage"
    assert payload == {
        "chat_id": "-123456",
        "text": (
            "🚨 KIS Portfolio batch alert\n"
            "Job: collect-asset-overview-snapshot\n"
            "Status: degraded\n"
            "Summary: FX rate is missing"
        ),
    }
    assert provider == "telegram"


def test_generic_webhook_keeps_structured_payload():
    endpoint, payload, provider = _build_alert_request(
        "https://alerts.example.invalid/hook",
        "snapshot-job",
        "error",
        "failed",
    )

    assert endpoint == "https://alerts.example.invalid/hook"
    assert payload == {
        "service": "kis-portfolio",
        "job": "snapshot-job",
        "status": "error",
        "summary": "failed",
    }
    assert provider == "webhook"
