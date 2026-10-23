# WI-071 production transition

Owner authorized production transition after the isolated implementation and disclosure that all six live scopes
remain deferred. DEC-063/ADR-034 authorize this bounded useful diagnostic release; numeric enablement remains a
separate source-verification decision. Work remains WI-071; prior closed milestones/outcomes are unchanged.

## Product behavior and limits

Use the existing authenticated `get-data-quality` tool with `dataset_id="dataset.cash-balance-reconciliation"`.
Its typed `data.results` contains account alias/currency, observation interval, knowledge cutoff, revision,
formula/opaque lineage and explicit deferred reasons. Initial observed/expected/delta are NULL. It never emits
external-flow coverage or performance eligibility. An empty pre-activation/missing-run window is partial, not zero
cash movement. Bounds: 31 days, 100 rows/page, 256 KiB envelope; snapshot-bound cursor, optional exact producer run.
No new tool/parameter/scope; unrelated quality queries retain their existing schema/behavior.

`control.cash_balance_reconciliations` stores immutable interval revisions and unique visible-input hashes.
Observation, evaluation knowledge and actual recording clocks are separate. Transactional append retries bounded
conflicts, including COMMIT failures that already ended the transaction. PIT reads select only evaluations known
and recorded by cutoff; cursor anchors preserve that snapshot even if as_of was omitted on the first page.
Both the repository and schema prohibit initial numeric writes, including synthetic proofs. No financial input
is copied to Git; logs contain only safe counts, opaque run IDs and stable error codes.

After successful owned-portfolio refresh, a feature-gated companion pipeline reads two latest stored observations
for each of five KRW scopes plus brokerage USD and persists diagnostic results. It has its own run/stage/quality/
lineage evidence, source-call budget zero, no new Scheduler and no dependency of the core publish/report success.
A failed companion is unavailable/failed evidence; it does not replay broker collection or fail owner reporting.
The core pipeline definition/version and existing schedules, Telegram and held/watchlist settings remain unchanged.

The initial source adapter continues to attest neither settled basis nor freshness. Valuation residual cash,
withdrawable fallback, date-only sttl_dt, source-date coverage and fee-only cash ledger cannot activate numbers.
The existing fee/settlement mapping gaps are not corrected by this release. No cash/trade/portfolio facts change.

## Protected release and recovery

Build from current approved master via GitHub Actions target `wi071`, one immutable image. Capture prior Remote
stable/compatibility traffic and exact three core Job exports. Dedicated private recovery Job: verify immutable
provenance and current 0022/0023 prefix, reject unowned pre-existing diagnostic table drift, private pre-backup and
fresh restore rehearsal, additive 0023, bootstrap from the last successful source run, authoritative table
fingerprints unchanged, private post-backup/fresh restore including diagnostic rows. Pre-backup failure prevents
DDL; post failure retains additive history but prevents runtime promotion. No destructive migration/rollback.

Update only the three existing core Job images and feature flag; reuse the same image for Remote and move stable
and compatibility routes together with both-route smoke checks. On failure restore exact prior Job definitions and
prior Remote routes. Retain schema/evidence. No source account secrets are supplied to the recovery Job; it uses
existing warehouse/private-object credentials. No live portfolio Job/manual Telegram smoke is executed by WI-071.

Rollback: disable `KIS_CASH_RECONCILIATION_ENABLED`, restore previous Job specs and stable/tag revisions. Preserve
immutable source, migration and diagnostic history. SQL numeric guard stays until a separately reviewed future
migration; changing an environment flag alone cannot enable numeric output.

## Verification and acceptance

Local tests cover the independent synthetic core oracles, active contract bounds, immutable/replayed/concurrent
append, posting-versus-source completeness, PIT recording cutoff, authenticated read positive/partial/error,
invalid/foreign cursor, numeric write rejection, private restore round trip, pre/post failure boundaries and
image/flag-only deployment intent. Full shared harness must pass before push/PR and protected release.

Actual client acceptance after release: existing Codex OAuth reads the exact dataset (diagnostic positive with
six deferred scopes), reads an absent producer run or pre-activation window (explicit partial), and rejects an
invalid limit/cursor (bounded error). Also verify an unaffected existing quality query. Numeric positive remains
unsupported; do not inject synthetic values into production to manufacture acceptance. Verify source/image/run
labels and next successful scheduled companion; keep stabilizing until owner acceptance and scheduled evidence.

Reproduction:

```bash
.venv/bin/python -m pytest tests/test_cash_reconciliation.py tests/test_cash_reconciliation_production.py -q
.venv/bin/python scripts/rehearse_wi071_reconciliation.py
PATH="$PWD/.venv/bin:$PATH" UV_CACHE_DIR=/private/tmp/wi071-uv-cache bash scripts/check.sh full
```

Release, actual-client and stabilization results will be appended as observed. Tests and smoke are independent
from actual source completeness and owner acceptance.

Repository verification: **959 tests passed**, one existing Authlib deprecation warning; quick governance,
architecture, warehouse and 18-tool surface gates passed. Protected release pre/post failure and restore tests
passed, including unchanged authoritative tables. Older WI-064 fingerprint/rehearsal checks were made migration-
prefix-aware so a new additive table is not incorrectly queried in a 0021/0022 historical restore; original source
and identity assertions remain intact. No actual financial amounts or raw URI were published with the source.
