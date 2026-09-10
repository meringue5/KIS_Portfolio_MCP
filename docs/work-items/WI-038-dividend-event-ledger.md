---
id: WI-038
title: Build declared entitled and received dividend ledger
status: verified
type: change
owner: owner
decision_refs: ADR-021, ADR-023, ADR-026
requirement_refs: DEC-023
milestone_ref: MS-003
delivery_refs: V2-W0407
parent_work_item: none
depends_on: WI-020, WI-021, WI-037
architecture_impact: ADR-026 approved; separate action entitlement and cash receipt-link ledgers on shared runtime
data_impact: append-only dividend states and reconciliation links
security_impact: account-level received amounts remain confidential
cost_impact: bounded filing and account-history processing
execution_scope: isolated
production_effects: none
---

# WI-038 — Build declared entitled and received dividend ledger

## Problem and evidence

Dividend tables exist as foundations, but declared, entitled, received and corrected states are not populated and
reconciled to positions and cash events.

## Classification and contract

- `change` implementing the approved dividend state machine.

## Scope

- Include gross/tax/net/currency, dates, account entitlement, cash receipt and manual provenance.
- Exclude tax advice and invented receipts.

## Acceptance criteria

- [ ] state gaps and corrections remain explicit and reversible.
- [ ] cash and filing reconciliation, restore and full gates pass.
- [ ] monthly history and change can be reproduced.

## Change impact

- Additive confidential Silver ledger; no Telegram payload activation.

## Plan

1. Freeze state transitions. 2. Implement reconciliation. 3. Verify account/source gaps.

## Isolated implementation checkpoint — 2026-09-10

- Activated after WI-037 reached `verified` under the MS-003 continuous isolated-overlap gate.
- This phase is limited to additive migration 0015, repository code, safe fixtures, local DuckDB verification,
  backup/restore and reconciliation evidence.
- Production DB migration, live DB writes, source activation or calls, credentials/IAM, Cloud Run/Scheduler,
  public MCP/Telegram activation, cleanup and cutover remain prohibited.
- Exit line: action, account entitlement and reversible receipt-link revisions preserve cash-event monetary SSOT;
  monthly native/FX read models reproduce from local fixtures; fresh migration, fail-closed legacy preflight and
  restore checks pass.

## Sub-items

- `WI-038-S01` — closed: research dividend action, account entitlement, received cash, correction, reconciliation and
  source/account coverage boundaries without implementation or activation.
- `WI-038-S02` — closed after owner approval: froze the implementation-ready action/entitlement/receipt-link, cash
  SSOT, PIT, correction, coverage, migration, source-budget and capacity contract design without implementation.
- `WI-038-S03` — closed: adopt ADR-026, requirements/system design and eight approved-but-inactive DGH contract
  deltas without implementation, DDL, source calls or activation.

## Research checkpoint — 2026-09-01

- The approved four-state intent remains valid, but immutable issuer action, account entitlement and cash receipt
  identities should not be represented as one mutable lifecycle row.
- KIS domestic account rights are a semantic candidate for entitlement/allocation/tax, while prior IRP zero-row
  coverage remains a source gap. Overseas rights are schedule/per-share facts, not account receipt evidence.
- WI-021 cash history only normalized trade settlement, fee and tax facts; its existing cash events cannot be
  retrospectively labelled as dividend receipts without source evidence.
- The current logical/physical contract lacks state-specific dates, eligible quantity/rate, bitemporal provenance,
  correction/reversal lineage, cash links and coverage evidence; contract hardening precedes implementation.
- Received cash is the monthly-income monetary SSOT. Declared/entitled estimates remain separate, and manual evidence
  may reconcile gaps but never overwrite a broker event.
- Evidence: `docs/operations/wi-038-pre-research-2026-09.md`.

## Evidence

- `docs/operations/wi-038-pre-research-2026-09.md`
- `docs/operations/wi-038-s02-contract-design-2026-09.md`
- `docs/operations/wi-038-s03-contract-adoption-2026-09.md`
- `docs/operations/wi-038-isolated-verification-2026-09.md`
- `bash scripts/check.sh quick`

## Isolated verification — 2026-09-10

- Added checksum-verified migration 0015 with 7 additive tables and 5 rebuild views. A non-empty legacy dividend
  foundation fails closed without applying the migration.
- Implemented safe fixture normalization, hash-verified private source landing, immutable action/entitlement/link and
  sourced component repositories, explicit `system_as_of` queries, reversible link corrections and monthly native/FX
  projections.
- Verified source gaps, cash classification/account/currency matching, many-to-many allocation bounds, 64/320 call
  budgets, 10-page cap, 1 GiB/500,000-row stop lines, quality-gated monotonic watermark and fresh backup restore.
- Focused: 10 passed. Filing/dividend/warehouse/package integration: 33 passed. Full: 539 passed with one existing
  Authlib deprecation warning.
- No source call, live DB access or migration, credential/IAM, infrastructure, schedule, public MCP/Telegram,
  cleanup, cutover or production effect occurred.

## Closeout

- Result: parent is `verified` in isolated scope; S01~S03 remain closed and approved contracts remain inactive.
- Remaining risk: KIS domestic field semantics and history depth need a separately approved bounded source sampling;
  IRP and U.S. actual receipt remain `source_gap`. Production migration, backfill and consumer acceptance remain gated.
- Follow-up Work Item: dependency-ordered MS-003 work may continue with WI-039. WI-038 production activation waits for
  the MS-002 closure and a separate release decision.

## Contract design checkpoint — 2026-09-02

- WI-037/ADR-025 is now closed as the filing prerequisite design. The proposed dividend architecture uses separate
  issuer action, account entitlement and cash receipt-link revision ledgers; cash events remain monetary SSOT.
- Proposed ADR-026 defines system-as-of, correction versus reversal, source/coverage fail-closed behavior and shared
  modular-monolith implementation without a separate service or duplicated runtime.
- The owner package proposes eight approved-but-inactive DGH deltas, additive migration 0015, KIS routine/backfill
  caps of 64/320 calls, a 10-page partition cap and 1 GiB/500,000-row stop lines.
- IRP and U.S. actual receipt remain explicit `source_gap` until broker or owner-private statement evidence exists;
  estimates never become received cash.
- Evidence: `docs/operations/wi-038-s02-contract-design-2026-09.md`.
- Result: `WI-038-S02` is ready for owner decision. Parent `WI-038` and MS-003 remain proposed; no contract adoption,
  code, DDL, source call, credential, data, infrastructure, schedule or MCP change occurred.
- Follow-up Work Item: after owner approval, append `WI-038-S03` for canonical ADR/requirements/DGH adoption. Runtime
  implementation remains behind the MS-002 → MS-003 formal gate.

## Contract adoption checkpoint — 2026-09-02

- The owner approved the complete WI-038-S02 package. ADR-026 is canonical and the action, entitlement,
  cash receipt-link and monthly-summary boundary is reflected in requirements, system design and DGH contracts.
- Eight contract deltas are approved but inactive: four dataset additions, two dataset revisions, one collection and
  one dedicated logical pipeline. The umbrella collection/pipeline remains for compatibility and orchestration.
- `cash-transaction-event` remains monetary SSOT; `system_as_of` is the default; correction, cash reversal, IRP/U.S.
  `source_gap`, manual provenance and KIS/object/row stop lines are fail-closed contracts.
- Evidence: `docs/operations/wi-038-s03-contract-adoption-2026-09.md`.
- Result: `WI-038-S02` and `WI-038-S03` are closed. Parent `WI-038` and MS-003 remain proposed; no code, DDL,
  source call, credential, data, infrastructure, schedule, runtime registry or MCP change occurred.
- Follow-up Work Item: implementation starts only after the MS-002 → MS-003 formal gate and must add migration 0015,
  fixtures, recovery evidence and a separate production activation decision.
