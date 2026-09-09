# WI-055-S01 Owner Total-Asset Report Release and Rollback

## Scope and immutable baseline

- Corrective presentation: `pipeline.telegram-total-asset-report-v2` / `2.0.0`.
- Preserved baseline: legacy `pipeline.telegram-total-asset-digest-v1`, master `1025f4a`, and the 2026-09-09
  10:00/16:00 delivery ledgers remain immutable evidence.
- Existing three fixed-slot core Jobs and their Schedulers are reused. No database migration, source activation,
  service, Scheduler, IAM grant or secret is created by this release.
- Repository verification is side-effect free. Production execution requires the normal protected GitHub environment
  and an explicit `wi055-s01` deploy target invocation.

## Security and information boundary

- The only allowed destination alias is `dest.owner.primary`, whose pinned chat secret was previously verified as a
  one-to-one owner conversation. A second explicit `KIS_TELEGRAM_OWNER_DESTINATION_APPROVED=true` gate is required.
- The report may contain exact total assets, exact same-slot change, account-alias allocation and asset allocation.
- Account numbers, internal account IDs, bot token, raw chat ID and credential fingerprints are prohibited from the
  caption and PNG. Only `ria`, `isa`, `brokerage`, `irp`, and `pension` account aliases are accepted.
- Application output and Control evidence contain only hashes, outcome, presentation version, bounded row counts and
  quality status. Caption text and PNG bytes are not persisted in logs or the warehouse.
- Any missing account coverage, degraded canonical state or reconciliation failure suppresses both amounts and chart
  and sends the existing bounded `계산 보류` message.

## Cost and release guardrails

- Steady state remains at most two Telegram provider operations per applicable market day. `sendPhoto` replaces the
  legacy digest operation; it is not an additional recurring call.
- The deterministic 1200x800 RGB PNG is capped at 10 MB. The synthetic verification fixture is approximately 12 KB;
  actual size is data-independent apart from compressibility and remains bounded.
- The release builds one immutable image. Before any core Job revision changes, that same image must run one
  finance-free `sendPhoto` smoke from the existing pipeline service account with pinned Telegram secret versions.
- A timeout or malformed response is terminal `unknown`; the smoke blocks deployment, and a production report is
  never automatically replayed after an ambiguous provider request.
- Legacy and v2 report flags are mutually exclusive before collection or delivery starts.

## Repository verification

```bash
uv run pytest -q tests/test_total_asset_digest.py tests/test_telegram_delivery.py tests/test_deploy_cloud_run.py
bash scripts/check.sh quick
bash scripts/check.sh full
```

The local fixture must verify exact total/change, account and asset reconciliation, no internal identifier in the
caption, deterministic PNG signature/dimensions, one provider operation, redacted ledger evidence and ambiguous-send
sealing. No real Telegram request is part of repository verification.

## Production release manifest

1. Confirm the candidate is merged to current `origin/master` and the protected full gate passed.
2. Confirm numeric pinned versions exist for `KIS_TELEGRAM_BOT_TOKEN_VERSION` and
   `KIS_TELEGRAM_CHAT_ID_VERSION`; do not read or print their values.
3. Run the `wi055-s01` deploy target. It builds once, performs the same-image finance-free photo smoke, then updates
   the three existing core Jobs with:
   - legacy report `false`
   - v2 report `true`
   - owner destination approval `true`
   - destination alias `dest.owner.primary`
4. Do not manually execute a production-value slot. Observe the next scheduled slot and reconcile owner receipt with
   one terminal Control-ledger row containing matching report/chart hashes.

## Rollback manifest

Rollback triggers are any destination mismatch, identifier exposure, amount/allocation mismatch, duplicate receipt,
misleading partial total, unreadable chart, unexpected provider-cost increase or owner rejection of information value.

1. Preserve execution name, image digest, run ID, report/chart hashes, provider outcome and owner observation without
   copying financial content into logs or this document.
2. Immediately stop future reports by setting both total-asset report flags to `false`, or restore the last safe image
   if the release affected another core path. Do not replay an ambiguous slot.
3. Verify all three core Job revisions have the same disabled/restored image and flags. Schedulers remain unchanged.
4. Append a corrective sub-item/Work Item. Do not delete the failed run, rewrite Control evidence, rotate an unaffected
   secret or modify production portfolio data.

The legacy percentage-only presentation is retained as evidence but is not the preferred user-facing fallback because
the owner rejected its information value. Disabling only the report is therefore the default safe rollback.
