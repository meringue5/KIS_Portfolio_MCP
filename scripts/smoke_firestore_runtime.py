#!/usr/bin/env python3
"""Redacted runtime smoke for the Firestore OAuth and KIS token paths."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess

import duckdb
from dotenv import load_dotenv
from google.cloud import firestore
from google.oauth2.credentials import Credentials

from kis_portfolio.adapters.outbound.firestore_state import FirestoreStateStore
from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.platform.state_runtime import configure_state_store_for_tests
from kis_portfolio.security.token_encryption import decrypt_token, ensure_token_encryption_ready


async def main_async() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="kis-portfolio-state")
    parser.add_argument("--use-gcloud-token", action="store_true")
    args = parser.parse_args()
    credentials = None
    if args.use_gcloud_token:
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True,
        ).stdout.strip()
        credentials = Credentials(token)
    client = firestore.Client(project=args.project, database=args.database, credentials=credentials)
    store = FirestoreStateStore(project=args.project, database=args.database, client=client)
    configure_state_store_for_tests(store)
    os.environ["KIS_STATE_BACKEND"] = "firestore"

    md_token = get_motherduck_token()
    if not md_token:
        raise RuntimeError("MOTHERDUCK_TOKEN is required for redacted lookup keys")
    con = duckdb.connect(f"md:{get_motherduck_database()}?motherduck_token={md_token}")
    try:
        client_id = con.execute("SELECT client_id FROM oauth_clients ORDER BY created_at LIMIT 1").fetchone()[0]
        cache_key = con.execute(
            "SELECT cache_key FROM kis_api_access_tokens WHERE expires_at > current_timestamp ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()

    from kis_portfolio.adapters.auth.provider import KisOAuthProvider
    provider = KisOAuthProvider(token_pepper=os.environ["KIS_AUTH_TOKEN_PEPPER"])
    if await provider.get_client(client_id) is None:
        raise RuntimeError("Firestore OAuth client runtime lookup failed")
    token_record = store.get("kis_token_cache", cache_key)
    if not token_record:
        raise RuntimeError("Firestore KIS token runtime lookup failed")
    ensure_token_encryption_ready()
    if not decrypt_token(token_record["token_ciphertext"]):
        raise RuntimeError("Firestore KIS token ciphertext could not be decrypted")
    print("Firestore runtime smoke passed: oauth_client=1 kis_token_cache=1 plaintext_logged=0")


if __name__ == "__main__":
    asyncio.run(main_async())
