# Firestore operational-state cutover and rollback

## Boundary

`KIS_STATE_BACKEND=firestore` moves OAuth user/client/grant/code/token state and encrypted KIS access-token cache
behind the named Firestore database `kis-portfolio-state`. OAuth bearer values are never stored, and KIS access
tokens remain encrypted with `KIS_TOKEN_ENCRYPTION_KEY`. MotherDuck state tables are preserved as a rollback snapshot;
the migration does not delete or update them.

Production runtime identities must not execute DDL. MotherDuck schema creation and V2 migration are explicit release
jobs; serving startup performs read-only required-table verification and fails closed when a migration is missing.

## Rehearsal and activation

1. Run `scripts/migrate_operational_state.py --dry-run` and review counts only.
2. Run the same script with `--use-gcloud-token`; source and verified counts must match.
3. Run `scripts/bootstrap_firestore_state.py --apply --use-gcloud-token` to verify transaction fencing.
4. Run `scripts/smoke_firestore_runtime.py --use-gcloud-token`; it checks one OAuth client and decrypts one KIS
   ciphertext without printing identifiers, digests, ciphertext or plaintext.
5. Deploy a non-serving revision with `KIS_STATE_BACKEND=firestore`, `KIS_GCP_PROJECT=grand-forge-279904`, and
   `KIS_FIRESTORE_DATABASE=kis-portfolio-state`. Use the normal build-once release workflow.
6. Reconnect the MCP client to mint a new code/token pair. Existing migrated active digests may remain valid, but a
   reconnect is the recovery contract and avoids relying on a partially completed rotation.

## Rollback

- Route traffic back to the last V1 revision and set `KIS_STATE_BACKEND=motherduck` there.
- Do not copy Firestore state back into MotherDuck and do not delete either store during incident response.
- Reconnect the MCP client; KIS tokens are safely reissued from the upstream API when the old cache is absent/expired.
- If OAuth pepper exposure is suspected, rotate `KIS_AUTH_TOKEN_PEPPER` in Secret Manager and force reconnect.
- If the KIS encryption key is suspected, rotate it through a separate key-migration Work Item; do not overwrite
  ciphertext until decrypt/re-encrypt reconciliation and rollback evidence exist.
