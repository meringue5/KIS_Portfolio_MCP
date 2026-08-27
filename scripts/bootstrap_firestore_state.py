#!/usr/bin/env python3
"""Create or verify the non-secret Firestore state schema marker."""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime, timedelta

from google.cloud import firestore
from google.oauth2.credentials import Credentials

from kis_portfolio.adapters.outbound.firestore_state import ALLOWED_COLLECTIONS, FirestoreStateStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="kis-portfolio-state")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-gcloud-token", action="store_true")
    args = parser.parse_args()
    print(f"project={args.project} database={args.database}")
    print(f"allowed_collections={','.join(sorted(ALLOWED_COLLECTIONS))}")
    if not args.apply:
        print("dry-run: no Firestore document written")
        return
    credentials = None
    if args.use_gcloud_token:
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True
        ).stdout.strip()
        credentials = Credentials(token)
    client = firestore.Client(project=args.project, database=args.database, credentials=credentials)
    store = FirestoreStateStore(project=args.project, database=args.database, client=client)
    store.put("system_config", "state-schema-v1", {
        "schema_version": 1,
        "database": args.database,
        "allowed_collections": sorted(ALLOWED_COLLECTIONS),
        "ttl_managed_deletes_enabled": False,
        "pitr_enabled": False,
        "created_by": "scripts/bootstrap_firestore_state.py",
        "verified_at": datetime.now(UTC),
    })
    value = store.get("system_config", "state-schema-v1")
    if value is None or value.get("schema_version") != 1:
        raise RuntimeError("Firestore state schema marker verification failed")
    print("Firestore state schema marker verified")
    first = store.claim("smoke:state-schema-v1", "bootstrap", timedelta(seconds=30))
    second = store.claim("smoke:state-schema-v1", "contender", timedelta(seconds=30))
    if not first.acquired or second.acquired or second.fencing_token != first.fencing_token:
        raise RuntimeError("Firestore lease exclusivity verification failed")
    if not store.release("smoke:state-schema-v1", "bootstrap", first.fencing_token):
        raise RuntimeError("Firestore lease release verification failed")
    print(f"Firestore lease fencing verified: token={first.fencing_token}")


if __name__ == "__main__":
    main()
