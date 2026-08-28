"""Load executable ETF source profiles and exact instrument routes."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from kis_portfolio.config import PROJECT_ROOT


RIGHT_FIELDS = (
    "automation_right", "cloud_processing_right", "raw_retention_right", "derived_use_right",
)


@dataclass(frozen=True, slots=True)
class EtfSourceProfile:
    profile_id: str
    version: str
    source_id: str
    parser_id: str
    parser_version: str
    allowed_hosts: tuple[str, ...]
    media_types: tuple[str, ...]
    product_key_kind: str
    activation_state: str
    rights: dict[str, str]

    @property
    def production_allowed(self) -> bool:
        return self.activation_state == "production" and all(
            self.rights.get(field) == "allowed" for field in RIGHT_FIELDS
        )

    def require_production_allowed(self) -> None:
        if not self.production_allowed:
            raise PermissionError(f"ETF profile {self.profile_id} is not approved for production network use")


@dataclass(frozen=True, slots=True)
class EtfInstrumentRoute:
    route_id: str
    version: str
    instrument_id: str
    market: str
    symbol: str
    profile_id: str
    provider_product_key: str
    product_key_kind: str
    activation_state: str
    valid_from: str


def _contracts(path: Path) -> list[dict]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported ETF contract schema: {path}")
    return list(data.get("contracts") or [])


def load_etf_source_profiles(root: Path = PROJECT_ROOT) -> dict[str, EtfSourceProfile]:
    result: dict[str, EtfSourceProfile] = {}
    for item in _contracts(root / "governance/catalog/etf-source-profiles.toml"):
        profile = EtfSourceProfile(
            profile_id=item["id"], version=item["version"], source_id=item["source_ids"][0],
            parser_id=item["parser_id"], parser_version=item["parser_version"],
            allowed_hosts=tuple(item["allowed_hosts"]), media_types=tuple(item["media_types"]),
            product_key_kind=item["product_key_kind"], activation_state=item["activation_state"],
            rights={field: item[field] for field in (*RIGHT_FIELDS, "redistribution_right")},
        )
        if profile.profile_id in result:
            raise ValueError(f"duplicate ETF profile: {profile.profile_id}")
        result[profile.profile_id] = profile
    return result


def load_etf_instrument_routes(root: Path = PROJECT_ROOT) -> dict[str, EtfInstrumentRoute]:
    profiles = load_etf_source_profiles(root)
    result: dict[str, EtfInstrumentRoute] = {}
    for item in _contracts(root / "governance/catalog/etf-instrument-routes.toml"):
        profile_id = item["profile_ids"][0]
        profile = profiles[profile_id]
        route = EtfInstrumentRoute(
            route_id=item["id"], version=item["version"], instrument_id=item["instrument_id"],
            market=item["market"], symbol=item["symbol"], profile_id=profile_id,
            provider_product_key=item["provider_product_key"], product_key_kind=item["product_key_kind"],
            activation_state=item["activation_state"], valid_from=item["valid_from"],
        )
        if route.instrument_id in result:
            raise ValueError(f"duplicate active ETF route: {route.instrument_id}")
        if route.product_key_kind != profile.product_key_kind:
            raise ValueError(f"ETF route/profile product-key mismatch: {route.route_id}")
        result[route.instrument_id] = route
    return result


def production_network_profiles(root: Path = PROJECT_ROOT) -> tuple[EtfSourceProfile, ...]:
    return tuple(profile for profile in load_etf_source_profiles(root).values() if profile.production_allowed)
