# WI-038-S03 Dividend Contract Adoption — 2026-09

## Status

- Work Item: `WI-038-S03`
- Classification: architecture/data-contract adoption
- Result: closed
- Parent: `WI-038` remains proposed
- Milestone: `MS-003` remains proposed behind the `MS-002 → MS-003` formal gate
- Owner approval: 2026-09-02 complete WI-038-S02 package accepted

## Canonical decisions adopted

1. ADR-026 separates issuer dividend action revisions, account entitlement revisions and reversible cash receipt-link
   revisions. No mutable four-state lifecycle row is canonical.
2. `dataset.cash-transaction-event` is the monetary SSOT for native gross, tax and net. Missing components stay null;
   estimates and manual evidence never overwrite broker facts.
3. `system_as_of` is the default for live analysis and operational replay. Retrospective source-effective analysis is
   explicitly labeled and preserves timestamp precision.
4. Issuer action correction/cancellation and cash reversal are separate append-only revision paths.
5. KIS domestic account-right data is a bounded candidate. IRP and U.S. actual receipt remain `source_gap` until
   broker or owner-private statement evidence exists; schedule times quantity is never received cash.
6. KIS ceilings are 64 routine and 320 backfill physical calls, with 10 pages per partition. Initial capacity stop
   lines are 1 GiB of private Bronze objects and 500,000 Silver rows.
7. Proposed migration 0015 is additive-only and must fail closed if legacy dividend foundations contain rows or an
   unknown consumer exists.
8. Filing and dividend are distinct logical pipelines but share the modular-monolith image, runner, adapters,
   landing, repositories, MotherDuck, GCS and release artifact. No separate service, repository or always-on worker.

## DGH delta

Approved, not activated:

- revised `dataset.cash-transaction-event` 1.1.0
- revised `dataset.dividend-event` 2.0.0
- added `dataset.dividend-source-observation` 1.0.0
- added `dataset.dividend-entitlement` 1.0.0
- added `dataset.dividend-reconciliation` 1.0.0
- added `dataset.dividend-monthly-summary` 1.0.0
- added `collection.dividend-ledger-v1` 1.0.0
- added `pipeline.dividend-ledger-v1` 1.0.0

The existing fundamentals/dividends umbrella collection and pipeline remain for compatibility and future shared
orchestration. The dedicated dividend pipeline is the logical owner of dividend watermarks, budgets and quality.

## Explicit non-effects

This Work Item did not change application code, DDL, live MotherDuck objects, credentials, IAM, source calls, stored
data, GCP infrastructure, Scheduler, Cloud Run runtime registry, Telegram or Remote MCP. Migration 0015, fixtures,
recovery proof, backfill and production activation require later implementation and release gates.

## Verification

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: passed, 129 registered contracts
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: passed, 438 tests and 1 existing Authlib deprecation warning
