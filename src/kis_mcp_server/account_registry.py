"""Configured KIS account registry for orchestrator tools."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping


ACCOUNT_SPECS = [
    ("ria", "RIA", "위험자산 일임"),
    ("isa", "ISA", "ISA"),
    ("brokerage", "BROKERAGE", "일반 위탁"),
    ("irp", "IRP", "IRP 퇴직연금"),
    ("pension", "PENSION", "연금저축"),
]


class AccountRegistryError(ValueError):
    """Raised when account configuration is missing or invalid."""


@dataclass(frozen=True)
class AccountConfig:
    label: str
    suffix: str
    display_name: str
    app_key: str
    app_secret: str
    cano: str
    acnt_prdt_cd: str
    account_type: str = "REAL"

    @property
    def masked_cano(self) -> str:
        if len(self.cano) <= 4:
            return "*" * len(self.cano)
        return f"{self.cano[:2]}{'*' * max(len(self.cano) - 4, 0)}{self.cano[-2:]}"

    def runtime_env(self) -> dict[str, str]:
        return {
            "KIS_APP_KEY": self.app_key,
            "KIS_APP_SECRET": self.app_secret,
            "KIS_CANO": self.cano,
            "KIS_ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KIS_ACCOUNT_LABEL": self.label,
            "KIS_ACCOUNT_TYPE": self.account_type,
        }

    def public_dict(self) -> dict:
        return {
            "label": self.label,
            "display_name": self.display_name,
            "account_type": self.account_type,
            "acnt_prdt_cd": self.acnt_prdt_cd,
            "masked_cano": self.masked_cano,
        }


def load_account_registry(env: Mapping[str, str] | None = None) -> list[AccountConfig]:
    env = env or os.environ
    accounts: list[AccountConfig] = []
    missing: list[str] = []
    account_type = env.get("KIS_ACCOUNT_TYPE", "REAL")

    for label, suffix, display_name in ACCOUNT_SPECS:
        values = {
            "app_key": env.get(f"KIS_APP_KEY_{suffix}", ""),
            "app_secret": env.get(f"KIS_APP_SECRET_{suffix}", ""),
            "cano": env.get(f"KIS_CANO_{suffix}", ""),
            "acnt_prdt_cd": env.get(f"KIS_ACNT_PRDT_CD_{suffix}", ""),
        }
        for field_name, value in values.items():
            if not value:
                missing.append(f"KIS_{field_name.upper()}_{suffix}")
        if all(values.values()):
            accounts.append(
                AccountConfig(
                    label=label,
                    suffix=suffix,
                    display_name=display_name,
                    account_type=account_type,
                    **values,
                )
            )

    if missing:
        raise AccountRegistryError(
            "Missing account environment variables: " + ", ".join(sorted(missing))
        )

    return accounts


def get_account(label: str, accounts: list[AccountConfig] | None = None) -> AccountConfig:
    normalized = label.strip().lower()
    for account in accounts or load_account_registry():
        if account.label == normalized:
            return account
    raise AccountRegistryError(f"Unknown account_label: {label}")


@contextmanager
def scoped_account_env(account: AccountConfig) -> Iterator[None]:
    updates = account.runtime_env()
    old_values = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
