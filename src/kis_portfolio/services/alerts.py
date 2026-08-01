"""Minimal secret-safe batch failure notification hook."""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx


def _build_alert_request(
    url: str,
    job: str,
    status: str,
    summary: str,
) -> tuple[str, dict, str]:
    """Build a provider-specific request without exposing credentials."""
    parsed = urlsplit(url)
    if parsed.hostname == "api.telegram.org" and parsed.path.endswith("/sendMessage"):
        chat_id = (parse_qs(parsed.query).get("chat_id") or [""])[0].strip()
        if not chat_id:
            raise ValueError("Telegram alert URL requires a chat_id query parameter")
        endpoint = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        text = (
            "🚨 KIS Portfolio batch alert\n"
            f"Job: {job[:100]}\n"
            f"Status: {status[:50]}\n"
            f"Summary: {summary[:500]}"
        )
        return endpoint, {"chat_id": chat_id, "text": text}, "telegram"

    return url, {
        "service": "kis-portfolio",
        "job": job[:100],
        "status": status[:50],
        "summary": summary[:500],
    }, "webhook"


async def notify_batch_failure(job: str, status: str, summary: str) -> dict:
    """POST a bounded, credential-free failure alert when a destination is configured."""
    url = os.environ.get("KIS_BATCH_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return {"status": "not_configured"}
    try:
        endpoint, payload, provider = _build_alert_request(url, job, status, summary)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        if provider == "telegram" and response.json().get("ok") is not True:
            return {"status": "failed", "error_type": "TelegramAPIError"}
        return {
            "status": "sent",
            "provider": provider,
            "http_status": response.status_code,
        }
    except Exception as error:
        return {"status": "failed", "error_type": type(error).__name__}
