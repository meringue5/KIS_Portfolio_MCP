import os

import pytest

from kis_portfolio.account_registry import (
    AccountRegistryError,
    load_account_registry,
    scoped_account_env,
)


def make_env():
    env = {"KIS_ACCOUNT_TYPE": "REAL"}
    for suffix, cano, prdt in [
        ("RIA", "11111111", "01"),
        ("ISA", "22222222", "01"),
        ("BROKERAGE", "33333333", "01"),
        ("IRP", "44444444", "29"),
        ("PENSION", "55555555", "22"),
    ]:
        env[f"KIS_APP_KEY_{suffix}"] = f"key-{suffix}"
        env[f"KIS_APP_SECRET_{suffix}"] = f"secret-{suffix}"
        env[f"KIS_CANO_{suffix}"] = cano
        env[f"KIS_ACNT_PRDT_CD_{suffix}"] = prdt
    return env


def test_load_account_registry_reads_all_accounts():
    accounts = load_account_registry(make_env())

    assert [account.label for account in accounts] == ["ria", "isa", "brokerage", "irp", "pension"]
    assert accounts[0].masked_cano == "11****11"
    assert accounts[3].acnt_prdt_cd == "29"


def test_load_account_registry_reports_missing_values():
    env = make_env()
    del env["KIS_APP_SECRET_RIA"]

    with pytest.raises(AccountRegistryError, match="KIS_APP_SECRET_RIA"):
        load_account_registry(env)


def test_public_dict_does_not_expose_account_number_or_secret():
    account = load_account_registry(make_env())[0]

    public = account.public_dict()

    assert "cano" not in public
    assert "app_secret" not in public
    assert public["masked_cano"] == "11****11"


def test_scoped_account_env_restores_previous_values(monkeypatch):
    account = load_account_registry(make_env())[0]
    monkeypatch.setenv("KIS_CANO", "old-cano")
    monkeypatch.delenv("KIS_APP_KEY", raising=False)

    with scoped_account_env(account):
        assert os.environ["KIS_CANO"] == "11111111"
        assert os.environ["KIS_APP_KEY"] == "key-RIA"

    assert os.environ["KIS_CANO"] == "old-cano"
    assert "KIS_APP_KEY" not in os.environ
