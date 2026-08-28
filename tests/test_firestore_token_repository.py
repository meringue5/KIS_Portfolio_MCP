from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore
from kis_portfolio.db import kis_token_repository
from kis_portfolio.platform.state_runtime import configure_state_store_for_tests, reset_state_runtime


def test_kis_token_repository_uses_document_state(monkeypatch):
    store = InMemoryStateStore()
    configure_state_store_for_tests(store)
    monkeypatch.setattr(kis_token_repository, "get_state_backend", lambda: "firestore")
    # KIS expiry timestamps are intentionally stored as naive Asia/Seoul wall-clock values.
    issued = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    expires = issued + timedelta(hours=1)
    try:
        saved = kis_token_repository.upsert_kis_api_access_token(
            cache_key="cache", account_id="12345678", account_type="REAL",
            app_key_fingerprint="fingerprint", token_ciphertext="ciphertext-only",
            token_type="Bearer", issued_at=issued, expires_at=expires, expires_in=3600,
            response_expiry_raw=None, migrated_from_file=False,
        )
        loaded = kis_token_repository.get_kis_api_access_token("cache")
        assert loaded == saved
        assert loaded["token_ciphertext"] == "ciphertext-only"
    finally:
        reset_state_runtime()
