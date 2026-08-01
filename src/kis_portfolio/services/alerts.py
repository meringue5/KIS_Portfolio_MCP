"""Minimal secret-safe batch failure notification hook."""

from __future__ import annotations

import os

import httpx


async def notify_batch_failure(job: str, status: str, summary: str) -> dict:
    """POST a bounded, credential-free alert payload when a webhook is configured."""
    url = os.environ.get("KIS_BATCH_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return {"status": "not_configured"}
    payload = {
        "service": "kis-portfolio",
        "job": job,
        "status": status,
        "summary": summary[:500],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        return {"status": "sent", "http_status": response.status_code}
    except Exception as error:
        return {"status": "failed", "error_type": type(error).__name__}
