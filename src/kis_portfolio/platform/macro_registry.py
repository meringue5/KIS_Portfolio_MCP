"""Exact macro_profile_v1 registry projected from the canonical DGH manifests."""

from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import date
from pathlib import Path

import duckdb

from kis_portfolio.modules.market.macro import MacroSeriesDefinition, validate_definition


PROFILE_COLLECTION_ID = "collection.macro-profile-v1"
PROFILE_COLLECTION_VERSION = "2.0.0"


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _hash_contract(contract: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class MacroSeriesRegistry:
    def __init__(self, definitions: tuple[MacroSeriesDefinition, ...]) -> None:
        self.definitions = definitions
        self._by_key = {
            (item.series_contract_id, item.version): item for item in definitions
        }
        if len(self._by_key) != len(definitions):
            raise ValueError("duplicate macro series contract identity")
        provider_keys = {(item.source_id, item.provider_series_id) for item in definitions}
        if len(provider_keys) != len(definitions):
            raise ValueError("duplicate macro provider identity")

    def get(self, series_contract_id: str, version: str = "1.0.0") -> MacroSeriesDefinition:
        try:
            return self._by_key[(series_contract_id, version)]
        except KeyError as exc:
            raise ValueError("macro series is not in the exact profile registry") from exc

    @property
    def definition_set_hash(self) -> str:
        value = "|".join(sorted(item.definition_hash for item in self.definitions))
        return hashlib.sha256(value.encode()).hexdigest()

    def project(self, connection: duckdb.DuckDBPyConnection) -> int:
        for item in self.definitions:
            prior = connection.execute(
                """
                SELECT definition_hash FROM control.macro_series_definitions
                WHERE series_contract_id=? AND version=?
                """,
                [item.series_contract_id, item.version],
            ).fetchone()
            if prior is not None and prior[0] != item.definition_hash:
                raise ValueError("macro definition replay conflicts with the immutable projection")
            connection.execute(
                """
                INSERT INTO control.macro_series_definitions(
                    series_contract_id,version,definition_hash,source_id,provider_series_id,
                    source_owner,source_license_class,region,concept,native_frequency,
                    native_unit,seasonal_adjustment,vintage_capability,publication_cadence,
                    expected_lag,history_start,rights_note,attribution,permitted_consumers,
                    transform_policy,activation_state,valid_from
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(series_contract_id,version) DO NOTHING
                """,
                [
                    item.series_contract_id, item.version, item.definition_hash,
                    item.source_id, item.provider_series_id, item.source_owner,
                    item.source_license_class, item.region, item.concept,
                    item.native_frequency, item.native_unit, item.seasonal_adjustment,
                    item.vintage_capability, item.publication_cadence, item.expected_lag,
                    item.history_start, item.rights_note, item.attribution,
                    json.dumps(item.permitted_consumers, ensure_ascii=False),
                    item.transform_policy, item.activation_state, item.valid_from,
                ],
            )
        return len(self.definitions)


def load_macro_series_registry(
    *,
    macro_path: Path | None = None,
    collections_path: Path | None = None,
) -> MacroSeriesRegistry:
    macro_path = macro_path or _root() / "governance/catalog/macro-series.toml"
    collections_path = collections_path or _root() / "governance/catalog/collections.toml"
    macro_document = tomllib.loads(macro_path.read_text(encoding="utf-8"))
    collection_document = tomllib.loads(collections_path.read_text(encoding="utf-8"))
    collection = next(
        (
            item for item in collection_document.get("contracts", [])
            if item.get("id") == PROFILE_COLLECTION_ID
            and item.get("version") == PROFILE_COLLECTION_VERSION
        ),
        None,
    )
    if collection is None or collection.get("status") != "approved":
        raise ValueError("approved macro profile collection contract is unavailable")
    expected_ids = tuple(collection.get("macro_series_ids") or ())
    contracts = {item.get("id"): item for item in macro_document.get("contracts", [])}
    if len(expected_ids) != 17 or len(set(expected_ids)) != 17:
        raise ValueError("macro_profile_v1 must contain exactly 17 unique series")
    definitions: list[MacroSeriesDefinition] = []
    for contract_id in expected_ids:
        contract = contracts.get(contract_id)
        if contract is None or contract.get("status") != "approved":
            raise ValueError("macro profile references an unapproved series")
        if contract.get("activation_state") != "inactive":
            raise ValueError("isolated macro implementation requires every series to remain inactive")
        definition = MacroSeriesDefinition(
            series_contract_id=str(contract["id"]),
            version=str(contract["version"]),
            definition_hash=_hash_contract(contract),
            source_id=str(contract["source_id"]),
            provider_series_id=str(contract["provider_series_id"]),
            source_owner=str(contract["source_owner"]),
            source_license_class=str(contract["source_license_class"]),
            region=str(contract["region"]),
            concept=str(contract["concept"]),
            native_frequency=str(contract["native_frequency"]),
            native_unit=str(contract["native_unit"]),
            seasonal_adjustment=str(contract["seasonal_adjustment"]),
            vintage_capability=str(contract["vintage_capability"]),
            publication_cadence=str(contract["publication_cadence"]),
            expected_lag=str(contract["expected_lag"]),
            history_start=str(contract["history_start"]),
            rights_note=str(contract["rights_note"]),
            attribution=str(contract["attribution"]),
            permitted_consumers=tuple(str(value) for value in contract["permitted_consumers"]),
            transform_policy=str(contract["transform_policy"]),
            activation_state=str(contract["activation_state"]),
            valid_from=date.fromisoformat(str(contract["valid_from"])),
        )
        validate_definition(definition)
        definitions.append(definition)
    return MacroSeriesRegistry(tuple(definitions))
