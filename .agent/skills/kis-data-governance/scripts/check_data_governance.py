#!/usr/bin/env python3
"""Validate repository-local Data Governance Harness contracts."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Any


GOVERNED_STATUSES = {"approved", "active", "deprecated", "retired"}


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    raise RuntimeError("Could not locate repo root")


def _load_toml(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"{path}: cannot read TOML: {exc}")
        return {}


def _require_text(path: Path, needles: list[str], errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing required file: {path}")
        return
    content = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in content:
            errors.append(f"{path}: missing governance integration {needle!r}")


def _validate_contract(
    kind: str,
    contract: dict[str, Any],
    common: dict[str, Any],
    type_schema: dict[str, Any],
    errors: list[str],
) -> None:
    identity = contract.get("id", f"{kind}[unknown]")
    label = f"{kind} contract {identity!r}"
    required = [*common.get("required", []), *type_schema.get("required", [])]
    for field in required:
        if field not in contract:
            errors.append(f"{label}: missing required field {field!r}")

    for field in required:
        value = contract.get(field)
        if isinstance(value, str) and not value.strip():
            errors.append(f"{label}: field {field!r} must not be blank")

    contract_id = contract.get("id")
    prefix = type_schema.get("id_prefix", "")
    if not isinstance(contract_id, str) or not contract_id.startswith(prefix):
        errors.append(f"{label}: id must start with {prefix!r}")
    elif not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+", contract_id):
        errors.append(f"{label}: id contains unsupported characters")

    version = contract.get("version")
    pattern = common.get("version_pattern", "")
    if not isinstance(version, str) or not re.fullmatch(pattern, version):
        errors.append(f"{label}: version must match {pattern!r}")

    status = contract.get("status")
    if status not in common.get("statuses", []):
        errors.append(f"{label}: invalid status {status!r}")

    list_fields = set(common.get("list_fields", [])) | set(type_schema.get("list_fields", []))
    for field in list_fields:
        if field in contract and not isinstance(contract[field], list):
            errors.append(f"{label}: field {field!r} must be a list")

    for field in type_schema.get("bool_fields", []):
        if field in contract and not isinstance(contract[field], bool):
            errors.append(f"{label}: field {field!r} must be a boolean")

    for field in type_schema.get("int_fields", []):
        if field in contract and (not isinstance(contract[field], int) or isinstance(contract[field], bool)):
            errors.append(f"{label}: field {field!r} must be an integer")

    for field in type_schema.get("scalar_reference_fields", []):
        if field in contract and not isinstance(contract[field], str):
            errors.append(f"{label}: field {field!r} must be a string reference")

    for field in type_schema.get("non_empty_list_fields", []):
        value = contract.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"{label}: field {field!r} must be a non-empty list")

    alternatives = type_schema.get("one_of_non_empty", [])
    source_less_control = (
        kind == "dataset"
        and contract.get("layer") == "control"
        and contract.get("control_origin") == "managed-pipeline-runtime"
    )
    if alternatives and not source_less_control and not any(
        isinstance(contract.get(field), list) and contract[field] for field in alternatives
    ):
        errors.append(f"{label}: at least one of {alternatives!r} must be non-empty")

    if kind == "dataset" and "control_origin" in contract and not source_less_control:
        errors.append(
            f"{label}: control_origin is allowed only for layer='control' "
            "and control_origin='managed-pipeline-runtime'"
        )

    for field, choices in type_schema.get("enums", {}).items():
        if field in contract and contract[field] not in choices:
            errors.append(f"{label}: field {field!r} must be one of {choices!r}")

    if status in GOVERNED_STATUSES:
        for field, forbidden in type_schema.get("forbidden_when_governed", {}).items():
            if contract.get(field) in forbidden:
                errors.append(
                    f"{label}: governed status {status!r} forbids {field}={contract.get(field)!r}"
                )

    decision_refs = contract.get("decision_refs")
    if status in GOVERNED_STATUSES and (not isinstance(decision_refs, list) or not decision_refs):
        errors.append(f"{label}: governed status {status!r} requires decision_refs")


def check(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    required_files = [
        "docs/governance/data-governance-harness.md",
        "governance/contract-schema.toml",
        ".agent/skills/kis-data-governance/SKILL.md",
        "scripts/check.sh",
        "AGENTS.md",
        "ARCHITECTURE.md",
        "SPEC.md",
        "docs/data-catalog.md",
        "docs/traceability.md",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")

    if errors:
        return errors

    _require_text(
        root / "scripts/check.sh",
        ["check_data_governance.py", "run_data_governance"],
        errors,
    )
    _require_text(
        root / "AGENTS.md",
        ["Data Governance Harness", "kis-data-governance/SKILL.md"],
        errors,
    )
    _require_text(
        root / "SPEC.md",
        ["ADR-023", "Data Governance Harness"],
        errors,
    )
    _require_text(
        root / "ARCHITECTURE.md",
        ["Data Governance Harness", "governance/catalog/"],
        errors,
    )
    _require_text(
        root / "docs/data-catalog.md",
        ["Data Governance Harness", "governance/catalog/datasets.toml"],
        errors,
    )
    _require_text(root / "docs/traceability.md", ["WI-003", "DGOV-010"], errors)

    schema = _load_toml(root / "governance/contract-schema.toml", errors)
    if schema.get("schema_version") != 1:
        errors.append("governance contract schema_version must be 1")
    common = schema.get("common")
    type_schemas = schema.get("types")
    if not isinstance(common, dict) or not isinstance(type_schemas, dict):
        errors.append("governance schema must define [common] and [types.*]")
        return errors

    contracts_by_kind: dict[str, list[dict[str, Any]]] = {}
    contracts_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    for kind, type_schema in type_schemas.items():
        if not isinstance(type_schema, dict):
            errors.append(f"schema type {kind!r} must be a table")
            continue
        relative = type_schema.get("file")
        if not isinstance(relative, str):
            errors.append(f"schema type {kind!r} missing file")
            continue
        catalog_path = root / relative
        if not catalog_path.is_file():
            errors.append(f"missing governance catalog: {relative}")
            continue
        catalog = _load_toml(catalog_path, errors)
        if catalog.get("schema_version") != schema.get("schema_version"):
            errors.append(f"{relative}: schema_version does not match contract schema")
        contracts = catalog.get("contracts", [])
        if not isinstance(contracts, list):
            errors.append(f"{relative}: contracts must be a list")
            continue
        contracts_by_kind[kind] = []
        for contract in contracts:
            if not isinstance(contract, dict):
                errors.append(f"{relative}: every contract must be a table")
                continue
            contracts_by_kind[kind].append(contract)
            _validate_contract(kind, contract, common, type_schema, errors)
            contract_id = contract.get("id")
            if isinstance(contract_id, str):
                if contract_id in contracts_by_id:
                    prior_kind = contracts_by_id[contract_id][0]
                    errors.append(f"duplicate governance contract id {contract_id!r}: {prior_kind}, {kind}")
                else:
                    contracts_by_id[contract_id] = (kind, contract)

    for kind, contracts in contracts_by_kind.items():
        type_schema = type_schemas[kind]
        for contract in contracts:
            contract_id = contract.get("id", f"{kind}[unknown]")
            status = contract.get("status")
            for field, expected_kind in type_schema.get("references", {}).items():
                value = contract.get(field, [])
                if field in type_schema.get("scalar_reference_fields", []):
                    references = [value] if isinstance(value, str) else []
                else:
                    references = value if isinstance(value, list) else []
                for reference in references:
                    target = contracts_by_id.get(reference)
                    if target is None:
                        errors.append(f"{contract_id!r}: field {field!r} references unknown id {reference!r}")
                        continue
                    actual_kind, target_contract = target
                    if actual_kind != expected_kind:
                        errors.append(
                            f"{contract_id!r}: field {field!r} expects {expected_kind}, got {actual_kind}"
                        )
                    target_status = target_contract.get("status")
                    if status in {"approved", "active"} and target_status in {"proposed", "retired"}:
                        errors.append(
                            f"{contract_id!r}: governed contract cannot reference {target_status} {reference!r}"
                        )

    provider_series_keys: set[tuple[str, str]] = set()
    for series in contracts_by_kind.get("macro_series", []):
        series_id = series.get("id", "macro_series[unknown]")
        key = (str(series.get("source_id")), str(series.get("provider_series_id")))
        if key in provider_series_keys:
            errors.append(f"{series_id!r}: duplicate macro provider identity {key!r}")
        provider_series_keys.add(key)
        source = contracts_by_id.get(series.get("source_id"))
        if series.get("activation_state") == "production":
            if series.get("status") != "active":
                errors.append(f"{series_id!r}: production macro series must have active lifecycle status")
            if source and source[1].get("status") != "active":
                errors.append(f"{series_id!r}: production macro series requires an active source")

    for kind in ("collection", "pipeline"):
        for contract in contracts_by_kind.get(kind, []):
            series_ids = contract.get("macro_series_ids", [])
            if not isinstance(series_ids, list):
                continue
            if len(series_ids) != len(set(series_ids)):
                errors.append(f"{contract.get('id')!r}: macro_series_ids contains duplicates")
            declared_sources = set(contract.get("source_ids", []))
            for series_id in series_ids:
                target = contracts_by_id.get(series_id)
                if target and target[1].get("source_id") not in declared_sources:
                    errors.append(
                        f"{contract.get('id')!r}: macro series {series_id!r} source is absent from source_ids"
                    )

    for read_model in contracts_by_kind.get("read_model", []):
        read_model_id = read_model.get("id", "read_model[unknown]")
        allowed = read_model.get("allowed_fields", [])
        suppressed = read_model.get("suppressed_fields", [])
        if isinstance(allowed, list) and isinstance(suppressed, list):
            overlap = sorted(set(allowed).intersection(suppressed))
            if overlap:
                errors.append(f"{read_model_id!r}: allowed_fields and suppressed_fields overlap: {overlap}")
        if not read_model.get("input_dataset_ids") and not read_model.get("registry_input_kinds"):
            errors.append(f"{read_model_id!r}: at least one governed input must be declared")
        max_response_bytes = read_model.get("max_response_bytes")
        if isinstance(max_response_bytes, int) and not isinstance(max_response_bytes, bool):
            if max_response_bytes <= 0 or max_response_bytes > 262_144:
                errors.append(f"{read_model_id!r}: max_response_bytes must be between 1 and 262144")
        max_page_size = read_model.get("max_page_size")
        if isinstance(max_page_size, int) and not isinstance(max_page_size, bool) and max_page_size <= 0:
            errors.append(f"{read_model_id!r}: max_page_size must be positive")
        max_lookback_days = read_model.get("max_lookback_days")
        if isinstance(max_lookback_days, int) and not isinstance(max_lookback_days, bool) and max_lookback_days < 0:
            errors.append(f"{read_model_id!r}: max_lookback_days must be nonnegative")
        if read_model.get("activation_state") == "production":
            if read_model.get("status") != "active":
                errors.append(f"{read_model_id!r}: production read model must have active lifecycle status")
            for dataset_id in read_model.get("input_dataset_ids", []):
                target = contracts_by_id.get(dataset_id)
                if target and target[1].get("status") != "active":
                    errors.append(f"{read_model_id!r}: production read model requires active input {dataset_id!r}")

    rights_fields = (
        "automation_right", "cloud_processing_right", "raw_retention_right", "derived_use_right",
    )
    for profile in contracts_by_kind.get("etf_profile", []):
        if profile.get("activation_state") == "production":
            denied = [field for field in rights_fields if profile.get(field) != "allowed"]
            if denied:
                errors.append(
                    f"{profile.get('id')!r}: production ETF profile requires allowed rights: {denied}"
                )

    route_keys: set[tuple[str, str]] = set()
    sensitive_route_fields = {"account_id", "account_label", "quantity", "amount", "valuation", "cano"}
    for route in contracts_by_kind.get("etf_route", []):
        route_id = route.get("id", "etf_route[unknown]")
        forbidden = sorted(sensitive_route_fields.intersection(route))
        if forbidden:
            errors.append(f"{route_id!r}: route contains prohibited holding fields {forbidden}")
        instrument_id = route.get("instrument_id")
        market = route.get("market")
        symbol = route.get("symbol")
        if instrument_id != f"v1|{market}|{symbol}":
            errors.append(f"{route_id!r}: instrument_id must equal v1|market|symbol")
        key = (str(instrument_id), str(route.get("valid_from")))
        if key in route_keys:
            errors.append(f"{route_id!r}: duplicate instrument route interval {key!r}")
        route_keys.add(key)
        for profile_id in route.get("profile_ids", []):
            target = contracts_by_id.get(profile_id)
            if target and route.get("product_key_kind") != target[1].get("product_key_kind"):
                errors.append(f"{route_id!r}: product_key_kind does not match {profile_id!r}")
            if target and route.get("activation_state") == "production" and target[1].get("activation_state") != "production":
                errors.append(f"{route_id!r}: production route requires a production profile")

    return errors


def main() -> int:
    root = repo_root()
    errors = check(root)
    if errors:
        print("Data governance contract check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    schema = tomllib.loads((root / "governance/contract-schema.toml").read_text(encoding="utf-8"))
    total = 0
    for type_schema in schema["types"].values():
        catalog = tomllib.loads((root / type_schema["file"]).read_text(encoding="utf-8"))
        total += len(catalog.get("contracts", []))
    print(f"Data governance contract check passed. registered_contracts={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
