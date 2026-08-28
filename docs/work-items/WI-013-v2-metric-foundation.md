---
id: WI-013
title: Establish the V2 point-in-time metric foundation
status: closed
type: architecture
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-015..017, DEC-026, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0501
parent_work_item: none
depends_on: WI-009, WI-012
architecture_impact: implements the approved Gold metric boundary without adding a provider or runtime service
data_impact: versioned metric contracts, Gold metric values and point-in-time lineage
security_impact: derived confidential portfolio values remain in MotherDuck and are not externally delivered
cost_impact: local and MotherDuck batch computation only with no always-on process
---

# WI-013 — Establish the V2 point-in-time metric foundation

## Problem and evidence

Milestone 1 publishes canonical portfolio daily state, but the metric registry is empty and there is no governed,
replay-safe output contract for Milestone 2 signal evaluation. Computing signals directly from ad-hoc queries would
lose formula version, knowledge-time, quality and lineage evidence.

## Classification and contract

- Initial classification: approved `architecture` implementation for V2-W0501.
- Compared contracts: DEC-015..017, DEC-026, DEC-038, DEC-041, DEC-044, DGH metric lifecycle and V2-ADR-012.
- This implements the approved boundary; it does not change the provider, SSOT, retention or external delivery policy.
- Repository-local implementation is authorized by DEC-044. Production migration, deployment and Telegram delivery
  remain separate gates.

## Scope

- Include: metric TOML contracts, runtime registry, versioned Gold metric values, point-in-time input cutoff,
  quality/lineage evidence, deterministic fixture evaluation and migration/backup contracts.
- Exclude: final signal thresholds, Telegram API calls, destination lookup, external messages, paid providers,
  Remote MCP exposure and production migration.

## Acceptance criteria

- [x] every evaluated metric resolves to an approved versioned metric contract.
- [x] metric values preserve subject, evaluation slot, effective/as-of/knowledge time, quality and lineage.
- [x] evaluation rejects or excludes future price, FX, position and later-revision inputs.
- [x] the same logical metric evaluation is idempotent and a formula version is never mutated in place.
- [x] migration, catalog, repository, backup and restore contracts remain aligned.
- [x] Project OS full gate and disposable-database replay evidence pass.

## Change impact

- Architecture: adds the approved analytics application boundary over canonical Silver/Gold inputs.
- Data/schema/backup: additive V2 Gold and Control objects via versioned migration; Parquet backup included.
- Security/privacy: metric rows are confidential when their subject or value reveals portfolio state.
- MCP/API compatibility: none; no public tool is added.
- Deployment/rollback: no production deploy in this Work Item; rollback is to omit the new migration/consumer.
- Cost/SLO: bounded batch evaluation, scale-to-zero compatible, no new cloud service.

## Plan

1. Register the initial approved metric contracts and physical object contract.
2. Add additive migration and repository with point-in-time/idempotency tests.
3. Implement a deterministic evaluator fixture and quality/lineage evidence.
4. Verify fresh migration, backup/restore coverage and full Project OS gate.

## Sub-items

- `none`.

## Evidence

- Secret Manager metadata confirms an enabled `kis-portfolio-telegram-bot-token` version; its payload was not read.
- approved `metric.portfolio-value-krw` and `dataset.metric-value` contracts plus the managed evaluation pipeline
  contract are registered in the Data Governance Harness.
- migration `0004` adds immutable Control definitions and replay-safe Gold values without changing V1 objects.
- repository tests prove a rerun with a different execution-run ID is a no-op, while value/lineage conflicts and
  in-place definition changes fail closed.
- point-in-time fixtures independently reject future effective time and later knowledge/revision time.
- disposable backup/restore fixture writes a real metric row, exports every governed V2 backup table to Parquet,
  restores into a new DuckDB and verifies the value and definition.
- targeted tests: `10 passed`.
- Project OS full gate: `227 passed`, with one existing Authlib deprecation warning.

## Closeout

- Result: governed V2 metric registry, point-in-time engine and Gold persistence foundation completed locally.
- Review correction: parallel formula-fixture research found that an explicit `insufficient_history` evaluation could
  not be persisted while `value_decimal` was non-nullable. The Work Item was reopened before deployment to preserve
  unavailable/partial outcomes without inventing zero values, independently tested, and closed again.
- Remaining risk: production migration and historical replay are later gates.
- Follow-up Work Item: V2-W0502 cash-flow-adjusted return, contribution and drawdown metrics.
