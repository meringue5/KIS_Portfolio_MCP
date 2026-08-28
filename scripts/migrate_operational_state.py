#!/usr/bin/env python3
"""Copy active operational state from MotherDuck to the named Firestore DB.

The script is preservation-first: it never deletes or mutates MotherDuck rows,
never decrypts KIS tokens, and prints counts only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import duckdb
from dotenv import load_dotenv
from google.cloud import firestore
from google.oauth2.credentials import Credentials

from kis_portfolio.adapters.outbound.document_auth_repository import DocumentAuthRepository
from kis_portfolio.adapters.outbound.firestore_state import FirestoreStateStore
from kis_portfolio.config import (
    PROJECT_ROOT,
    get_firestore_database,
    get_gcp_project,
    get_motherduck_database,
    get_motherduck_token,
)


TABLES = {
    "auth_users": "SELECT * FROM auth_users",
    "auth_identities": "SELECT * FROM auth_identities",
    "oauth_clients": "SELECT * FROM oauth_clients",
    "oauth_grants": "SELECT * FROM oauth_grants",
    "oauth_codes": "SELECT * FROM oauth_authorization_codes WHERE expires_at > current_timestamp AND consumed_at IS NULL AND revoked_at IS NULL",
    "oauth_tokens": "SELECT * FROM oauth_tokens WHERE (expires_at IS NULL OR expires_at > current_timestamp) AND revoked_at IS NULL",
    "kis_token_cache": "SELECT * FROM kis_api_access_tokens WHERE expires_at > current_timestamp",
}
JSON_FIELDS = {"redirect_uris", "grant_types", "response_types", "profile_data", "metadata"}
SEOUL_TZ = ZoneInfo("Asia/Seoul")


def _normalize_value(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _rows(con: duckdb.DuckDBPyConnection, query: str) -> list[dict]:
    cursor = con.execute(query)
    columns = [item[0] for item in cursor.description]
    records = []
    for row in cursor.fetchall():
        record = {key: _normalize_value(value) for key, value in zip(columns, row)}
        for field in JSON_FIELDS & record.keys():
            if isinstance(record[field], str):
                record[field] = json.loads(record[field])
        records.append(record)
    return records


def migrate(con: duckdb.DuckDBPyConnection, store, *, dry_run: bool) -> dict:
    oauth = DocumentAuthRepository(store)
    counts: dict[str, int] = {}
    verified: dict[str, int] = {}
    for kind, query in TABLES.items():
        records = _rows(con, query)
        counts[kind] = len(records)
        if dry_run:
            verified[kind] = 0
            continue
        for record in records:
            if kind == "kis_token_cache":
                for field, value in list(record.items()):
                    if isinstance(value, datetime) and value.tzinfo is None:
                        record[field] = value.replace(tzinfo=SEOUL_TZ).astimezone(UTC)
                expires_at = record["expires_at"]
                store.put(kind, record["cache_key"], record, expires_at=expires_at)
            else:
                oauth.import_record(kind, record)
        if kind == "auth_users":
            verified[kind] = sum(bool(oauth.get_auth_user_by_id(str(r["id"]))) for r in records)
        elif kind == "oauth_clients":
            verified[kind] = sum(bool(oauth.get_oauth_client(r["client_id"])) for r in records)
        elif kind == "oauth_codes":
            verified[kind] = sum(bool(oauth.get_authorization_code(r["code_digest"])) for r in records)
        elif kind == "oauth_tokens":
            verified[kind] = sum(bool(oauth.get_oauth_token(r["token_digest"])) for r in records)
        elif kind == "kis_token_cache":
            verified[kind] = sum(bool(store.get(kind, r["cache_key"])) for r in records)
        else:
            verified[kind] = len(records)
    return {"source_counts": counts, "verified_counts": verified, "dry_run": dry_run}


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence")
    parser.add_argument("--use-gcloud-token", action="store_true")
    args = parser.parse_args()
    token = get_motherduck_token()
    project = get_gcp_project()
    if not token or not project:
        raise RuntimeError("MOTHERDUCK_TOKEN and KIS_GCP_PROJECT/GOOGLE_CLOUD_PROJECT are required")
    con = duckdb.connect(f"md:{get_motherduck_database()}?motherduck_token={token}")
    try:
        if args.dry_run:
            from kis_portfolio.adapters.outbound.memory_state import InMemoryStateStore
            store = InMemoryStateStore()
        else:
            credentials = None
            if args.use_gcloud_token:
                access_token = subprocess.run(
                    ["gcloud", "auth", "print-access-token"],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                credentials = Credentials(access_token)
            client = firestore.Client(
                project=project, database=get_firestore_database(), credentials=credentials,
            )
            store = FirestoreStateStore(
                project=project, database=get_firestore_database(), client=client,
            )
        result = migrate(con, store, dry_run=args.dry_run)
    finally:
        con.close()
    result.update({
        "source": f"md:{get_motherduck_database()}",
        "target": f"firestore:{project}/{get_firestore_database()}",
        "verified_at": datetime.now(UTC).isoformat(),
    })
    if not args.dry_run and result["source_counts"] != result["verified_counts"]:
        raise RuntimeError(f"Redacted state migration count mismatch: {result}")
    if args.evidence:
        from pathlib import Path
        Path(args.evidence).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
