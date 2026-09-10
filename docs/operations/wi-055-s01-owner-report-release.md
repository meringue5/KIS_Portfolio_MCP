# WI-055-S01 Owner Total-Asset Report Release and Rollback

## Scope and immutable baseline

- Corrective presentation: `pipeline.telegram-total-asset-report-v2`. S01 established the exact-value report, S03
  added the owner-approved absolute-impact Top 5 holding chart in `2.1.0`, and S04 structures the caption in `2.2.0`
  while preserving the destination, quality and privacy boundaries.
- Preserved baseline: legacy `pipeline.telegram-total-asset-digest-v1`, master `1025f4a`, and the 2026-09-09
  10:00/16:00 delivery ledgers remain immutable evidence.
- Existing three fixed-slot core Jobs and their Schedulers are reused. No database migration, source activation,
  service, Scheduler, IAM grant or secret is created by this release.
- Repository verification is side-effect free. Production execution requires the normal protected GitHub environment
  and the explicit deploy target matching the reviewed presentation revision.

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
- The deterministic 1200x1080 RGB PNG is capped at 10 MB. It includes a five-row diverging impact panel; synthetic
  verification uses fabricated values only, and actual size remains data-independent apart from compressibility.
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
3. Run the `wi055-s03` deploy target. It builds once, performs the same-image finance-free photo smoke, then updates
   the three existing core Jobs with:
   - legacy report `false`
   - v2 report `true`
   - owner destination approval `true`
   - destination alias `dest.owner.primary`
4. Do not manually execute a production-value slot. Observe the next scheduled slot and reconcile owner receipt with
   one terminal Control-ledger row containing matching report/chart hashes.

S03 must not reuse the historical S01 label: all three Jobs must show deploy target `wi055-s03-top5-impact`. The
`wi055-s01` target remains available only to reproduce or restore its immutable release behavior.

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

## Release evidence — 2026-09-09

- First workflow attempt `34335622544` was a safe no-op because the new target had no matching workflow step. It sent
  no message and changed no Cloud Run resource; WI-055-S02 preserves and corrects that defect.
- PR #60/master `23707e7` added the exact dispatch. Protected run `34336332698` then passed tests, authentication,
  finance-free photo smoke execution `kis-portfolio-wi030-s03-prjlf`, and all three core Job updates.
- Deployed image: `sha256:b54a9819...9ffd`; labels on every Job are git SHA `23707e7`, GitHub run
  `34336332698`, deploy source `github-actions` and target `wi055-s01-owner-report`.
- Read-only verification confirmed the three non-sensitive controls: legacy `false`, v2 `true`, owner approval
  `true`, with destination alias `dest.owner.primary`. Scheduler, DB, IAM and Secret resources were not changed.
- Stabilization exit remains the next scheduled owner receipt plus matching terminal v2 Control-ledger evidence and
  explicit owner acceptance of the exact amounts, alias composition and chart information value.

## WI-055-S03 release evidence — 2026-09-09

- PR #62 merged the Top 5 presentation as master `46b6e74`; CI run `34338982164` passed.
- Protected deploy run `34339178599` passed in 3m7s. Finance-free same-image smoke execution
  `kis-portfolio-wi030-s03-9hv7s` completed successfully before any core Job update.
- All three fixed-slot core Jobs now use image `sha256:b7c82ed0...41c9a` and labels for git SHA `46b6e74`, GitHub run
  `34339178599`, deploy source `github-actions` and target `wi055-s03-top5-impact`.
- Read-only verification confirmed legacy `false`, v2 `true`, owner approval `true` and `dest.owner.primary` on every
  Job. No Scheduler, DB, IAM, Secret or public MCP resource was changed, and no production-value report was manually
  executed. The next scheduled owner receipt is the stabilization evidence.

## WI-055-S04 release evidence — 2026-09-10

- The 10:00 v2.1 report was reconciled and provider-sent; the owner confirmed client receipt and accepted its values,
  coverage and chart. Only caption structure was requested for correction.
- Presentation `2.2.0` groups summary, account allocation and asset allocation into Telegram-supported fixed-width
  blocks and renders Top 5 as paired label/value rows. Korean display width is accounted for without changing values.
- Focused report, transport and release tests passed 76; the full gate passed 541 tests. A fabricated five-account,
  three-asset caption was visually reviewed.
- The `wi055-s04` dry-run proved one build digest, finance-free photo smoke first, then the same image and atomic
  legacy-off/v2-on owner-only flags for all three fixed-slot Jobs under `wi055-s04-caption-layout`.
- The owner separately confirmed that the 16:00 pre-release v2.1 report was client-visible. PR #68 then merged the
  structured caption as master `c1481b6`; its required CI passed before release.
- Protected deploy run `34466281709` passed in 3m20s. It built image
  `sha256:be069287...ddf9` once, then finance-free photo-smoke execution
  `kis-portfolio-wi030-s03-gsplw` completed successfully in 10.57s before any core Job update.
- Read-only verification confirmed all three fixed-slot core Jobs are `Ready=True` on that same image, with git SHA
  `c1481b6`, GitHub run `34466281709`, deploy source `github-actions`, target
  `wi055-s04-caption-layout`, legacy `false`, v2 `true`, owner approval `true` and `dest.owner.primary`.
- No production-value slot was manually executed. Scheduler, DB, IAM, Secret and public MCP resources were not
  changed. If client rendering regresses on the next scheduled report, preserve the attempt and restore S03 image
  `sha256:b7c82ed0...41c9a` or disable both report flags; Scheduler and portfolio data remain untouched.
