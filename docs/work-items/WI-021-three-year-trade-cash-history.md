---
id: WI-021
title: Collect bounded three-year trade and cash history
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-009..014, DEC-030, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0403
parent_work_item: none
depends_on: WI-016, WI-020
architecture_impact: extends the approved managed broker-history pipeline without a new service
data_impact: bounded Bronze landing and canonical trade/cash history with reversible links
security_impact: confidential broker history; aggregate-only operational evidence
cost_impact: bounded scale-to-zero backfill under explicit call and row budgets
---

# WI-021 — Collect bounded three-year trade and cash history

## Problem and evidence

Correct source semantics exist for current broker history, but continuous three-year trade/cash coverage required for
reconstruction and return analysis has not been collected or reconciled.

## Classification and contract

- `change`; production backfill remains a separate operational gate.
- Raw source observations remain immutable and canonical links reversible.

## Scope

- Include bounded domestic/overseas collection, pagination, quality, lineage and reconciliation dry-run.
- Exclude inferred lot allocation and return metrics.

## Acceptance criteria

- [x] call/page budgets fail closed and resumable partitions are idempotent.
- [x] known source gaps remain explicit.
- [x] approved live backfill, restore and aggregate reconciliation evidence exist before closeout.

## Change impact

- Existing managed Job pattern; no always-on service or public MCP change.

## Plan

1. Plan partitions and source budgets.
2. Add pipeline evidence and dry-run reconciliation.
3. Apply only the separately approved bounded backfill.

## Sub-items

- `WI-021-S01` — deterministic three-year backfill planner and source-boundary partitions (`closed`).
  - [x] every callable partition is bounded, ordered and has a stable non-secret key.
  - [x] domestic partitions never cross the KIS old/recent route boundary.
  - [x] unsupported IRP recent history and unavailable cash-history sources remain explicit gaps.
  - [x] the planner performs no source call, database write or inferred cash-event creation.
- `WI-021-S02` — per-source page budget, global physical-call ceiling and fail-closed reservation (`closed`).
  - [x] the complete default plan reserves within an explicit global ceiling before execution.
  - [x] every physical call through the S02 guard requires a partition reservation and exhaustion raises first.
  - [x] unknown partitions, known gaps and invalid/over-wide page policies fail closed.
  - [x] budget identity and evidence contain no credential or account number.
- `WI-021-S03` — partition resume, idempotent logical runs and monotonic source watermarks (`closed`).
  - [x] completed partitions are reused without another handler or source call.
  - [x] a failed partition resumes with the same run identity and persisted physical-call usage.
  - [x] watermark advances only after publish, rejects gaps and never moves backwards.
  - [x] the runtime uses existing governed Control objects and performs no production collection.
- `WI-021-S04` — fixture page binding, canonical event normalization and reconciliation dry-run (`closed`).
  - [x] every guarded fixture page lands immutable row observations and publishes only reconciled trade/cash facts.
  - [x] official side, quantity, price, fee, tax and settlement fields are preserved without inferred fills.
  - [x] source-row classification and canonical event counts reconcile; incomplete pagination fails closed.
  - [x] this sub-item creates no purchase lot, source network call or production warehouse mutation.
- `WI-021-S05` — physical KIS page adapter and fixed-argument production preflight (`closed`).
  - [x] each HTTP page is reserved before I/O and uses the approved route/TR/continuation contract.
  - [x] production execution requires an exact approved plan hash, account scope, database mode and explicit apply flag.
  - [x] preview and failure output contain no credential or raw account number.
- `WI-021-S06` — bounded production execution, reconciliation and recovery evidence (`closed`).
  - [x] pre-backfill V2 backup exists before the first source call.
  - [x] all callable partitions terminate or retain an explicit resumable failure/known gap.
  - [x] aggregate reconciliation, private GCS upload and isolated restore pass before parent closeout.
  - [x] actual call, row, storage and elapsed-cost evidence remains within the approved bounds.

## Evidence

- `src/kis_portfolio/services/trade_cash_backfill.py` is a pure planner with a stable versioned partition key;
  `plan-trade-cash-backfill-v2` exposes the public manifest without source or warehouse access.
- The deterministic five-account `2023-08-28..2026-08-28` reference plan has 137 partitions: 131 callable and six
  named gaps. Its page-cap projection is planning metadata and no execution budget is enforced in S01.
- `tests/test_trade_cash_backfill_planner.py` covers exact coverage, boundary splits, IRP/domestic-cash gaps,
  credential exclusion, input-order determinism, virtual-source gaps and the read-only CLI.
- `bash scripts/check.sh quick`: passed with 83 governed contracts.
- `bash scripts/check.sh full`: 278 tests passed; all Project OS, data governance, architecture, warehouse and MCP
  surface gates passed. One existing Authlib deprecation warning remains.
- WI-021-S02 default policy reserves domestic order `93×3`, overseas order `19×3` and overseas transaction `19×2`:
  374 worst-case calls under the 400 global ceiling, leaving 26 calls of headroom.
- Preflight rejects the complete plan at 373/374 and minimum partition coverage at 130/131 before a call gate exists.
  The guarded async-call test proves page exhaustion does not invoke the physical callable; failed attempts consume
  their reservation.
- `bash scripts/check.sh quick`: passed after S02 code and contract documentation.
- `bash scripts/check.sh full`: 290 tests passed; all common gates passed with the same existing Authlib warning.
- WI-021-S03 registers the separate governed `pipeline.trade-cash-backfill-v2` identity and reuses
  `control.pipeline_runs`, `control.pipeline_stage_runs` and `control.watermarks`; no schema or live warehouse
  mutation was added.
- Every guarded reservation is checkpointed before source I/O. Failure injection proves the failed partition keeps
  its run ID and prior call usage, while an already completed partition is not invoked again.
- Publish advances a hashed non-secret source-stream watermark only across contiguous ranges; older replay is a
  no-op and a gap fails closed without moving the watermark.
- `bash scripts/check.sh quick`: passed after S03 implementation and governance contract registration.
- `bash scripts/check.sh full`: 295 tests passed; all common gates passed with the same existing Authlib warning.
- WI-021-S04 binds guarded fixture pages to deterministic content-based row identities, Bronze observations and
  Silver trade/cash facts. Domestic and overseas order aggregates preserve official side/quantity/price; overseas
  period transactions remain separate trade candidates and only explicit settlement/fee/tax amounts become cash facts.
- An incomplete-pagination fixture retains one Bronze observation but creates zero Silver trade rows and zero
  watermark rows. The reconciled fixture creates two trades and four cash facts, including a KRW-denominated
  domestic fee distinct from foreign-currency fee/tax/settlement, zero purchase lots and is a no-op
  on replay.
- `bash scripts/check.sh full`: 297 tests passed; all common gates passed with the existing Authlib warning.
- WI-021-S05 adds a dedicated KIS page adapter using the common pagination engine's pre-request reservation hook.
  Contract tests cover domestic recent, overseas order exchange mapping, overseas period transactions, two-page
  continuation and page-limit incompleteness.
- The fixed production command has no side effect without `--apply`; apply additionally requires exact plan/budget
  hashes, MotherDuck mode and a complete pre-backup manifest before opening a database connection.
- The reviewed `2023-08-28..2026-08-28` preflight produced plan `0755656ed8151a91`, budget
  `0a4abf9b795f9d73`, 131 callable partitions, six gaps and a 374/400 worst-case reservation.
- `bash scripts/check.sh full`: 303 tests passed; all common gates passed with the existing Authlib warning.
- WI-021-S06 production readiness preserves KIS `dmst_frcr_fee1` as a separate KRW fee rather than inheriting the
  overseas transaction currency. Targeted fixture/source tests (6 passed) and `bash scripts/check.sh quick` passed.
- `run-wi021-s06` and the dedicated manual Cloud Run target enforce private pre-backup upload/download/restore before
  the first KIS page, then post-backup and isolated aggregate reconciliation. The target is excluded from `all`, has no
  Scheduler and fixes one task, parallelism one and automatic retries zero. Recovery/deploy/reconciliation tests pass.
- Deployment dry-run resolved the fixed command, immutable digest shape, private bucket, dedicated pipeline service
  account and Secret Manager references without exposing values. `bash scripts/check.sh full`: 310 tests passed; all
  common gates passed with the existing Authlib warning.
- Operational runbook: `docs/design/wi-021-s06-production-execution.md`.
- GitHub Actions run `33145645614` completed from reviewed `master` commit `224913c8a273de4c4b5871a86c7c4b819f939b08`
  and immutable image `sha256:bf02b5582c63408691e2f3ab6bc05d59af26b6900234abbd7a41fa839476d863`.
  The explicit migration execution `kis-portfolio-wi021-s06-migration-gpzc6` applied only `0008`; recovery/backfill
  execution `kis-portfolio-wi021-s06-8q7q6` then completed in 1,036.614 seconds.
- Live reconciliation passed with 131/131 partitions, zero failures, 131/400 physical calls, 393 successful stages,
  262 passing quality rows, 150 valid lineage rows and 11 valid watermark streams. It reconciled 340 raw rows to
  263 trade events and 49 explicit cash events, with zero purchase lots and zero evidence failures.
- The verified private pre/post recovery points each contain 37 objects and total 7,756,343 / 8,115,216 bytes.
  Exact-hash download, fresh isolated restore and live/restored aggregate equality passed; the aggregate-only evidence
  object hash is `3015cab1bcf46130ecf68880ecc349088011d459ecc7fe8947596a187023a2ba`.
- Full operational evidence and the two fail-closed precursor attempts are recorded in
  `docs/operations/milestone-2-trade-cash-backfill-2026-08.md`.

## Closeout

- Result: WI-021-S01 through S06 and the parent are closed with live recovery evidence.
- Remaining risk: six approved broker-retention/source gaps remain explicit and no inferred lot allocation was created.
- Follow-up: WI-021 dependency is satisfied; lot reconstruction remains gated by WI-036, and dividend work by WI-037.
