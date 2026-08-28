---
id: WI-033
title: Implement instrument-level total-asset valuation-change contribution
status: ready
type: change
owner: owner
decision_refs: DEC-048
requirement_refs: DEC-005, DEC-026, DEC-038, DEC-048, DGOV-005, DGOV-008
milestone_ref: MS-002
delivery_refs: V2-W0510
parent_work_item: none
depends_on: WI-009, WI-013
architecture_impact: adds a governed analytical read model and transition-compatible MCP response enrichment
data_impact: computes a versioned metric from canonical daily state; physical changes require additive migration and catalog updates
security_impact: preserves masking and must not expose account identifiers or credentials
cost_impact: bounded daily computation over held instruments; no always-on service
---

# WI-033 — Implement instrument-level total-asset valuation-change contribution

## Problem and evidence

The V1 `get-total-asset-daily-change` implementation returns only total previous/current value, amount change and
percentage change. Holdings already exist below canonical overview snapshots, but no governed response decomposes the
daily KRW valuation change by instrument, cash and residual. Generic V2 contribution language and WI-023 do not close
this gap: WI-023 is cash-flow-adjusted investment-return attribution, while this outcome is a point-to-point KRW
valuation-change explanation that includes FX effects for foreign holdings.

## Classification and contract

- Classification: approved product `change`, not a defect against the current V1 response contract.
- Compared contracts: DEC-026 monitoring explanation, V2 daily state, metric registry, V1 analytics/MCP code and
  tests, and WI-023 return/contribution/drawdown.
- Contract result: new metric and response contract. It must remain explicitly distinct from investment return.
- Approval: requirements/design registration is approved. Implementation can enter execution under DEC-044 after it
  becomes the single active implementation Work Item.

## Scope

- Include: compare prior/current canonical daily states; instrument previous/current KRW value, change, starting-total
  impact and share of total change; new/sold flags; top positive/negative contributors; cash change; explained sum,
  residual and reconciliation status; completeness/coverage gates; overseas FX caveat.
- Include: consolidate the same instrument across accounts with an optional masked account breakdown; enrich the
  transition V1 `get-total-asset-daily-change` response compatibly and project the same governed result through the V2
  performance/overview read model.
- Exclude: cash-flow-adjusted return attribution, realized/unrealized tax-lot P&L, trade causality and security-level FX
  isolation unless a separately governed metric is approved.

## Acceptance criteria

- [ ] `valuation_change_krw = current_value_krw - previous_value_krw` is returned per instrument with previous/current
  snapshot refs and values.
- [ ] `total_asset_impact_pct` uses previous total assets as the denominator; `share_of_total_change_pct` uses total
  KRW change and is null with an explicit reason when that denominator is zero.
- [ ] new/sold inference is emitted only when both days are complete and comparable with equal required account
  coverage; otherwise status is partial/degraded and potentially false inferences are suppressed.
- [ ] top positive/negative contributors, cash delta, holding delta sum, unexplained residual and tolerance-based
  reconciliation status are included.
- [ ] foreign results are labeled `KRW valuation change including FX`, never investment-return contribution.
- [ ] metric, data catalog, MCP response schema, golden fixtures, partial/missing-account/zero-denominator/FX tests and
  backward compatibility are updated in the same change.
- [ ] `bash scripts/check.sh quick` passes during work and `bash scripts/check.sh full` passes before closeout.

## Change impact

- Architecture: analytics application query reads governed Gold daily state and exposes one versioned result contract.
- Data/schema/backup: prefer replayable computation and existing metric ledger; any new object must update catalog,
  DDL/migration, repositories, backup and restore tests atomically.
- Security/privacy: aggregate by instrument by default; any account breakdown uses aliases/masking.
- MCP/API compatibility: additive V1 response fields during transition; V2 exposes the metric under the approved public
  tool budget without adding a raw endpoint-shaped tool.
- Deployment/rollback: feature/version flag can return the prior aggregate-only response while retaining metric rows.
- Cost/SLO: daily held-instrument cardinality only; batch-first and scale-to-zero constraints remain.

## Plan

1. Freeze response DTO, quality/comparability predicate and reconciliation tolerance with golden fixtures.
2. Implement replay-safe canonical-state comparison and metric persistence/projection.
3. Add the V1 compatibility enrichment and V2 read-model mapping.
4. Test complete, partial, account-missing, new, sold, cash, zero-change, foreign-FX and residual scenarios.
5. Run quick/full gates and record operating evidence.

## Sub-items

- `none` at baseline. FX-isolated attribution or return attribution is an independent outcome, not a silent extension.

## Evidence

- Contract review: current V1 analytics selects only total-level lag/change; holdings are stored by overview snapshot.
- Commands/tests: pending implementation.
- Operating evidence: pending implementation; no live DB or MCP runtime changed by WI-031.

## Closeout

- Result: ready.
- Remaining risk: current V1 snapshot-quality fields and the V2 daily-state completeness projection must be verified
  together before allowing new/sold inference.
- Follow-up Work Item: WI-028 consumes this output for contribution-aware alert state.
