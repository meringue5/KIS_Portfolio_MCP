from __future__ import annotations

from datetime import date, datetime

from cryptography.fernet import Fernet

from kis_portfolio.common import values
from kis_portfolio.security import oauth_crypto, redaction, token_encryption


def test_mask_account_id_matches_existing_public_shape():
    assert redaction.mask_account_id("11111111") == "11****11"
    assert redaction.mask_account_id("1234") == "****"
    assert redaction.mask_account_id("") == ""


def test_redact_mapping_removes_known_secret_values():
    payload = {
        "authorization": "Bearer token",
        "appsecret": "secret",
        "symbol": "005930",
    }

    assert redaction.redact_mapping(payload) == {
        "authorization": "<redacted>",
        "appsecret": "<redacted>",
        "symbol": "005930",
    }


def test_common_values_preserve_json_safe_conversion():
    row = {
        "created_at": datetime(2026, 5, 3, 12, 30, 0),
        "trade_date": date(2026, 5, 3),
        "balance_data": '{"cash": 1000}',
        "plain": "not-json",
    }

    assert values.to_float("1,234.5") == 1234.5
    assert values.to_int("1,234") == 1234
    assert values.to_int("1234.0") is None
    assert values.normalize_row(row) == {
        "created_at": "2026-05-03T12:30:00",
        "trade_date": "2026-05-03",
        "balance_data": {"cash": 1000},
        "plain": "not-json",
    }
    assert values.json_safe('{"x": 1}') == {"x": 1}
    assert values.json_safe("plain") == "plain"


def test_canonical_token_encryption_helpers(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("KIS_TOKEN_ENCRYPTION_KEY", key)

    ciphertext = token_encryption.encrypt_token("raw-token")

    assert token_encryption.decrypt_token(ciphertext) == "raw-token"


def test_canonical_oauth_crypto_helpers():
    digest = oauth_crypto.digest_token("token", "pepper")

    assert digest == oauth_crypto.digest_token("token", "pepper")
    secret_hash = oauth_crypto.hash_client_secret("secret")
    assert oauth_crypto.verify_client_secret("secret", secret_hash)
    assert oauth_crypto.generate_token(8)
