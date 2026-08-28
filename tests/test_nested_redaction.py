from kis_portfolio.security.redaction import redact_nested


def test_nested_redaction_removes_secrets_and_masks_accounts():
    value = {"outer": [{"access_token": "raw", "CANO": "12345678", "safe": "ok"}]}
    assert redact_nested(value) == {
        "outer": [{"access_token": "<redacted>", "CANO": "12****78", "safe": "ok"}]
    }
