---
id: WI-054
title: Audit and correct MS-002 production readiness before user acceptance
status: closed
type: clarification
owner: owner
decision_refs: ADR-021, ADR-023, DEC-051
requirement_refs: DEC-004, DEC-015..017, DEC-026..030, DEC-038, DEC-048, DEC-051
milestone_ref: MS-002
delivery_refs: none
parent_work_item: none
depends_on: WI-028
architecture_impact: none; restores approved product acceptance semantics without changing service boundaries
data_impact: audit first; any production activation must reuse governed metrics and quality gates
security_impact: final payload remains allowlisted and excludes account numbers and absolute portfolio values
cost_impact: reuse three scale-to-zero schedules and Telegram transport; no always-on service
---

# WI-054 — Audit and correct MS-002 production readiness before user acceptance

## Problem and evidence

The owner received a live S02 Telegram message whose generic `보유 종목` label, `DB-only shadow 평가` summary and
internal reason code prove transport but provide too little information for practical portfolio monitoring. The
approved monitoring-v1 requirement already requires safe instrument identity, market/type, price or portfolio change,
held-episode drawdown, contribution, trend, freshness/quality and reproducible reasons.

Several closed MS-002 Work Items also explicitly retain repository-local, unapplied or production fail-closed states.
Treating their narrow implementation closure as product readiness would allow MS-002 to close without its approved
user outcome.

## Classification and contract

- Classification: `clarification` of milestone acceptance plus implementation-gap audit; this is not a new analytics
  requirement.
- Compared contracts: DEC-051 and monitoring-v1 sections 5.3~5.6, MS-002 outcome/acceptance, WI-019/023~025/033 and
  WI-030 implementation evidence.
- Contract result: the S02 payload and mixed Work Item closure meanings do not satisfy production user acceptance.
- Approval: owner approved all six correction steps and immediate transition to real-use stabilization on 2026-09-03.

## Scope

- Classify every initial-scope MS-002 product capability as implemented, production-active, publish-ready and
  user-visible using current code and live evidence.
- Identify exact upstream blockers for the production-value Telegram payload without bypassing quality gates.
- Amend MS-002 acceptance so production-equivalent real use, stabilization and owner acceptance are mandatory.
- Route Telegram payload implementation and release-candidate activation to `WI-030-S03`.
- Preserve S02 immutable canary, replay, shadow and delivery-ledger history.
- Exclude ETF constituent look-through, MS-003 enrichment, order execution and silent publication of unavailable data.

## Acceptance criteria

- [x] Every initial-scope MS-002 capability has evidence-backed readiness status and blocker/owner.
- [x] Required production message fields map to governed datasets/metrics or explicit unavailable reasons.
- [x] No closed Work Item is represented as production-ready solely because local tests passed.
- [x] MS-002, milestone map, WI-030 and traceability all require real-use stabilization and owner acceptance.
- [x] `WI-030-S03` has a bounded, testable implementation and rollback handoff.
- [x] Project OS quick/full gates pass.

## Production-readiness matrix

2026-09-03 aggregate-only MotherDuck inspection and current code establish this baseline. `implemented` means code and
contract exist; it does not imply the later three columns.

| Capability | Implemented | Production-active | Publish-ready | User-visible | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| adjusted/raw price history | yes | yes | yes for current alert input | only change percent | 21 instruments have adjusted history; latest KR 2026-09-02 and U.S. 2026-09-01 |
| safe instrument label, market and type | yes | yes | yes with one explicit classification caveat | no | all 21 current instruments have names; 20 official-reference classifications and one fixture-route ETF |
| SMA20/50/120, volume ratio, RSI14, Bollinger context | yes | direct live evaluation | yes when per-observation price quality passes | internal codes only | `SignalObservation` contains values, but public context drops them and `gold.metric_values` is empty |
| portfolio daily state | yes | yes | latest three KR dates/slots pass | no direct analytic message | latest nine KR slots contain 31 pass rows each; full history still has 889 non-pass rows |
| portfolio performance and return contribution | yes | no metric publication | no | no | missing external-cash coverage and historical non-pass state; zero live metric rows |
| held-episode high/drawdown and lot/thread risk | yes | no | no | no | zero reconstructed episodes, zero passing open lots, 57 open reconstruction exceptions and zero owner plans |
| KRW valuation-change contribution | yes | no official publication | no | no | V1 quality projection/latest-pair incomplete and V2 history contains non-pass rows; zero live metric rows |
| alert state, de-duplication and Telegram transport | yes | yes, bounded S02 canary | technically ready | generic template only | live claims/sends pass, but producer hard-codes `보유 종목` and `DB-only shadow 평가` |
| replay/shadow threshold approval | yes | collecting | not permanent-ready | n/a | WI-029-S05 runs through 2026-09-10 and still requires reconciliation/owner review |

The live warehouse has zero rows in both `control.metric_definitions` and `gold.metric_values`. The scheduled signal
currently calculates price/trend observations directly from governed price revisions, while contribution, episode
drawdown and thread risk remain `None`; it must not imply those values were evaluated.

## Required Telegram field map

| Product fact | Current source | S03 first real-use behavior | MS-002 close requirement |
| --- | --- | --- | --- |
| instrument name | `silver.instruments_current.name` | render the safe label; fail closed if absent | all delivered subjects identified safely |
| market / asset type | `silver.instruments_current` | render owner-readable market/type with classification caveat | no heuristic or look-through claim |
| daily change | price replay observation | render signed percent | freshness and price quality pass |
| trend / volume / RSI / Bollinger | price replay observation | render bounded values and translated context | same point-in-time input as severity decision |
| episode drawdown | approved metric, currently unavailable | render explicit `계산 보류` reason, never zero | production episode/metric readiness passes |
| KRW valuation-change contribution | approved metric, currently unavailable | render explicit `계산 보류`; never call it investment return | comparable-state metric readiness passes |
| freshness / quality | candidate input time and quality | render KST source/evaluation basis and pass status | stale/partial candidates remain unsent |
| reason | versioned reason-code allowlist | translate to Korean while retaining stable code only in ledger | every severity has an owner-readable explanation |

## WI-030-S03 implementation handoff

1. Version the alert-candidate and Telegram pipeline contracts for the expanded allowlisted presentation context; do
   not change candidate grain, state identity, secrets, schedule or absolute-value prohibition.
2. Join governed instrument label/market/type and preserve price/trend observation values in immutable candidate public
   context. Add a bounded Korean reason dictionary and KST presentation.
3. Render unavailable contribution/drawdown explicitly during the first production-equivalent release candidate. A
   missing governed value cannot be omitted silently, represented as zero or inferred from another field.
4. Revoke or let S02 expire without editing it, then activate exactly one new immutable release candidate on the same
   three jobs. Rollback remains the Telegram enable flag plus an append-only owner revocation.
5. Stabilize message volume, usefulness, de-duplication, data quality, security and receipt in the real destination.
6. Remediate and activate the production metric path for episode drawdown and KRW valuation-change contribution before
   permanent rule approval and MS-002 close. Portfolio performance/thread-risk blockers remain explicit rather than
   being hidden inside the Telegram task.

## Change impact

- Architecture: no new boundary; the existing batch → alert state → Telegram path remains.
- Data/schema/backup: audit-only initially; follow-up activation must use existing governed objects or a separately
  reviewed additive contract change.
- Security/privacy: preserve the allowlist and absolute-portfolio-value prohibition while adding owner-readable facts.
- MCP/API compatibility: none for the audit; S03 may add only Telegram presentation fields.
- Deployment/rollback: S03 uses a new immutable release candidate; S02 evidence is never edited in place.
- Cost/SLO: three existing scheduled jobs and attempt budget remain; no additional standing resource.

## Plan

1. Build the MS-002 production-readiness matrix from Work Item contracts, code and live evidence.
2. Map each required Telegram fact to its current producer, quality status and activation blocker.
3. Freeze the S03 payload, release-candidate, rollback and owner-acceptance contract.
4. Close this audit only when S03 can proceed without an implicit quality or scope bypass.

## Sub-items

- `none`; the concrete Telegram implementation remains `WI-030-S03` under its existing outcome.

## Evidence

- 2026-09-02 live S02 payload reproduced the generic subject/shadow summary/internal-code behavior.
- Initial document inspection found explicit production gates in WI-019, WI-023~025, WI-033 and WI-036.
- Aggregate-only live inspection: `gold.metric_values=0`, `control.metric_definitions=0`; all 21 current instruments
  have a name, 20 are official-reference classified and one ETF uses a fixture route.
- Existing readiness inspectors: portfolio performance blocked by historical non-pass state and external-cash coverage;
  lot/thread risk blocked by zero reconstructed episodes/passing lots, 57 exceptions and zero owner plans; valuation
  change blocked by V1 quality projection/latest pair and historical V2 non-pass rows.
- Latest three KR dates and three daily slots each have 31 pass portfolio-state rows, so current-state remediation may
  be narrower than historical readiness reports implied; no quality gate is relaxed by this observation.
- `bash scripts/check.sh quick`: passed with 55 tracked Work Items, one active implementation Work Item and 161
  governed contracts.
- Full regression: 443 passed with one third-party Authlib deprecation warning.

## Closeout

- Result: closed; S03 can enter real-use with useful live price/trend facts and explicit
  unavailable reasons, but permanent MS-002 acceptance remains blocked on the governed drawdown/contribution path.
- Remaining risk: 57 reconstruction exceptions, missing metric registry/value publication and historical quality gaps
  require bounded remediation; they cannot be solved by presentation logic.
- Follow-up Work Item: WI-030-S03.
