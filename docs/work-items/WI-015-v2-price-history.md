---
id: WI-015
title: Build the V2 dual-basis revision-aware price ledger
status: in_progress
type: defect
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-005, DEC-015..017, DEC-030, DEC-041, DEC-044
architecture_impact: implements the approved price dataset and managed backfill boundary without adding a provider
data_impact: additive price revision ledger, corrected basis provenance and bounded reconstructed history
security_impact: internal market data only; KIS credentials remain runtime-only
cost_impact: scale-to-zero one-off backfill, existing KIS source, hard physical-call ceiling
---

# WI-015 — Build the V2 dual-basis revision-aware price ledger

## Problem and evidence

The domestic KIS history request uses adjusted-price option `0`, but V1 saves it with `adjusted=false` and the V2
bridge writes every recent row as `raw`. The current Silver table also overwrites later observations of the same
instrument/session/basis, so historical evaluation cannot select the revision known at its cutoff.

## Classification and contract

- Classification: `defect` against approved DEC-015 and `dataset.price-bar-daily`.
- Endpoint-specific option semantics remain explicit: domestic `0=adjusted, 1=raw`; overseas `0=raw, 1=adjusted`.
- A history fetched today is `retrospective_reconstructed`; it never becomes strict historical knowledge or an alert.
- Existing ambiguous KRX cache rows are quarantined/recollected, not silently promoted.

## Scope

- Include: explicit basis request/save policy, append-only revisions, current canonical projection, as-of selection,
  pagination guards, bounded backfill plan/adapter, catalog/migration/backup and deterministic fixtures.
- Exclude: trend metrics, Telegram, new provider, production alerting and destructive rewrite of existing rows.

## Acceptance criteria

- [ ] domestic and overseas request options map to basis by endpoint and are tested independently.
- [ ] raw response/page evidence and normalized revisions preserve effective, fetched/knowledge and basis provenance.
- [ ] identical revision hashes are no-op; changed observations append and as-of reads exclude later knowledge.
- [ ] raw/adjusted fallback is forbidden and retrospective history cannot pass strict replay.
- [ ] backfill planning is bounded per instrument/basis with cursor-stall and physical-call ceilings.
- [ ] current V2 collection no longer labels adjusted domestic history as raw.
- [ ] migration, catalog, backup/restore and full Project OS gates pass.
- [ ] production migration/backfill records coverage and reconciliation evidence before closeout.

## Change impact

- Architecture/data: additive revision object and approved managed price pipeline; current canonical table remains.
- Security/cost: no new secret; bounded KIS history reads and scale-to-zero batch only.
- Deployment/rollback: deploy code before fixed-argument backfill; disable the price job and retain landed/revision data.
- MCP compatibility: none; no public tool change.

## Plan

1. Register the managed price pipeline and physical revision object.
2. Implement endpoint-specific basis semantics and revision/as-of repository behavior.
3. Add bounded pagination/backfill adapter and synthetic fixtures.
4. Run migration, backup/restore, full regression and production dry-run/reconciliation.
5. Apply the additive production migration and bounded backfill only after preflight evidence passes.

## Evidence

- Official KIS examples and repository probe evidence are linked in the Milestone 2 readiness review.
- `bash scripts/check.sh quick`: passed with 49 governed contracts.
- `bash scripts/check.sh full`: 234 tests passed; architecture, warehouse and MCP surface gates passed.
- Synthetic page tests cover domestic 100/101-row sharding, overseas `tr_cont=N`, endpoint-specific options,
  cursor stall, physical-call exhaustion and managed run/quality/lineage/watermark evidence.
- V1 migration test proves ambiguous KRX `adjusted=false` cache rows remain Bronze quarantine and are not promoted.
- Production migration, dry-run and bounded backfill evidence: pending.

## Closeout

- Result: in progress.
- Remaining risk: production history is reconstructed at current knowledge time.
- Follow-up Work Item: WI-016 broker history contract correction.
