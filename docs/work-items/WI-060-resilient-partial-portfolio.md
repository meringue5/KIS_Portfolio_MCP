---
id: WI-060
title: Isolate portfolio capability failures and provide accurate partial results
status: stabilizing
type: architecture
owner: owner
decision_refs: DEC-055, DEC-057, ADR-021, ADR-023, ADR-024, ADR-028, ADR-029
requirement_refs: DEC-029, DEC-031, DEC-032, DEC-038, DEC-055, DEC-057
milestone_ref: MS-007
delivery_refs: none
parent_work_item: none
depends_on: none
discovered_from: WI-059, WI-055, WI-058
supersedes: none
rollback_of: none
execution_scope: production
production_effects: guarded Remote MCP and three fixed-slot owned-core Job deployment
architecture_impact: yes; separate capability quality, read-model and report boundaries without changing the V2 trust boundary
data_impact: approved additive FX source/observation/rate-type contracts are production-active under guarded fallback
security_impact: retain owner-only destination and masked accounts; add one pinned Korea Eximbank secret readable only by the pipeline identity; no payload or secret logging
cost_impact: free official source; at most one fallback call per managed run and no new standing resource
stabilization_window: protected source preflight plus immediate real MCP review and first owner-visible scheduled report after release
stabilization_exit_refs: immutable release workflow, exact Job and Remote image labels, source preflight result, real Claude MCP output, redacted owner receipt
rollback_plan: preserve the prior Remote traffic split and exact three Job exports; restore them automatically on source preflight, promotion or canonical smoke failure
---

# WI-060 — Resilient partial portfolio usability

## Problem and evidence

The owner rejected a system where a missing prior same-slot state or delayed USD/KRW rate makes all useful
current holdings disappear from the Telegram report, and where Claude's MCP reads repeatedly show unusable or
misleading quality. On 2026-09-17 the 10:00 owner report was unavailable because the 9/16 10:00 state was absent.
Separately, the 9/17 10:16 stored KRX/KRW position subset contained 17 pass-quality instruments and remained
queryable without FX. This subset is not a complete total asset value and includes KRX-listed overseas-themed ETFs.

Code audit found that `get-portfolio-overview` includes non-pass Gold rows in its numeric sum, while its outer
envelope reports `pass` whenever any rows exist. `get-performance-history` tests for the literal `passed`, though
Gold writes `pass`; its fixture repeats the wrong literal. These are independently reproducible read-model defects.

## Classification and contract

- Architecture/change: current DEC-055 explicitly suppresses all amounts and chart if either state is incomplete.
  The owner's feedback requests a different product behavior, not a silent exception to that decision.
- Defect: remote read-model quality aggregation and performance-history status literal disagree with persisted Gold.
- Data-source change: the approved Korea Eximbank source remains a separately typed `deal_bas_r` fallback and is
  admitted only for the requested date after a bounded comparison with a recent governed KIS reference.
- Detailed proposal and failure matrix: `docs/design/resilient-capability-degradation-review.md`.

## Scope and release unit

- Isolated phase: map producer-to-consumer dependencies, specify independently useful capability cells, freeze
  deterministic failure fixtures and correct clear false-green/false-degraded read-model defects under review.
- Approved isolated implementation: expose verified current KRW holdings and labeled partial reports independently
  of prior comparison and USD conversion; evaluate a secondary FX source without mixing unlike rate definitions.
- Exclude: fabricated total assets, stale FX silently treated as current, manual replay of old Telegram sends and
  any unguarded production collection or public MCP change.
- Ship the WI-060 user-visible correction as **one protected release candidate** after its contracts, fixtures,
  no-send production preflight and CI pass. Small reviewed commits and PR updates are allowed; do not activate a
  half-fixed MCP or Telegram surface in separate production deployments. This is a WI-060 boundary, not a promise
  to finish every unrelated historical TODO before release.
- The approved Korea Eximbank credential is referenced by pinned Secret Manager version. Its source rights, typed
  rate semantics, bounded cost and activation contracts are part of the same protected candidate; a read-only live
  preflight must pass before Remote traffic promotion or the prior Job definitions are restored. Release source
  validation uses the latest governed KIS business date so its result is independent of the provider's same-day
  publication time; runtime collection still requests its exact logical date and degrades explicitly when unpublished.

## Acceptance criteria

- [x] A missing prior slot disables only comparison and contribution, not a verified current-only capability.
- [x] Stale FX disables USD-to-KRW conversion and complete KRW total, not native values or verified KRX/KRW rows.
- [x] Missing one source or optional macro/ETF look-through never yields a false `pass` and never erases unrelated
  verified components; every numeric subtotal is labeled by coverage, source time and valuation basis.
- [x] MCP and Telegram fixtures reproduce user-visible complete, partial and unavailable cases without a clock wait.
- [ ] Real Claude/MCP and owner-visible Telegram review accepts the presentation before production closeout.
- [x] Any secondary FX source has approved rights, cost, source-date/rate-type mapping and deterministic conflict
  handling; no production calls or credentials are added merely to pass tests.

## Change impact

- Architecture: capability-oriented quality composition instead of one all-or-nothing report gate.
- Data/schema/backup: additive governed Bronze observation and existing Silver FX table use; the fallback preserves
  its distinct `deal_bas_r` type and source lineage, with no destructive migration.
- Security/privacy: no change to OAuth or Telegram owner-only destination; partial output remains confidential.
- MCP/API compatibility: prefer additive fields and explicit quality status; major version if existing field meaning
  must change. Preserve the 18-tool catalog unless separately approved.
- Deployment/rollback: the independent MS-007 gate depends on already-closed MS-005, not WI-059/MS-006
  stabilization. Any later release still needs approved product/data contracts and protected immutable V2 delivery.
- Cost/SLO: the second source is free at the approved public contract and is called at most once per managed run,
  only when the exact-date governed USD/KRW valuation rate is missing.

## Plan

1. Record the usability feedback, trace the dependency graph and identify false-green/false-negative behavior.
2. Define field-level quality/coverage and a presentation matrix in a proposed DEC/ADR for owner review.
3. Freeze executable fixtures for missing prior, stale FX, missing account, degraded row, optional context gaps
   and complete states. Implement isolated read-model and report slices; preserve exact totals as fail-closed.
4. Review source rights, rate basis and operations for secondary FX; activate only after contract approval.
5. Run quick/full gates, synthetic fault injection, no-send report previews and read-only production preflight.
   Review the exact single-release diff and rollback image. Use the narrow `wi060` target combining Remote MCP
   and the three fixed-slot owner-report Jobs instead of deploying unrelated services with `all` or treating two
   independent target runs as one release. Stage and smoke Remote at zero traffic first, preserve rollback
   coordinates, restore prior Job definitions on failure, and promote Remote only after all Job updates succeed.
6. Merge once and deploy one immutable image through the protected production workflow. Verify Git SHA and image
   labels across both Remote MCP and the scheduled report job before enabling the changed consumer behavior.
7. Verify real Claude/MCP output and an owner-visible Telegram report with source/coverage labels and receipt;
   retain stabilization evidence before closeout. A future scheduler slot is not the sole acceptance test.

## Sub-items

- `WI-060-S01` — pre-provision the exact FX Secret accessor and keep the protected release's IAM check read-only;
  discovered from protected run `35663503027` before any Job or serving-traffic change.
- `WI-060-S02` — validate the external source against the latest governed KIS date and verify the Cloud Resource
  Manager rollback prerequisite before any release mutation; discovered from protected run `35664495921`.

## Stabilization plan

- Isolated phase only. Before production, define bounded live and owner-visible review, rollback and exit evidence.
  Do not create a new dependency on the unavailable old report's owner-acceptance outcome.

## Evidence

- Architecture contract and MCP surface checks pass, yet neither checks degraded-result usability.
- Read-only MotherDuck inspection: 9/17 10:16 KRX/KRW 17 pass positions; 9/16 16:01 and 9/17 10:16 quantities
  are unchanged for those lines. These are different slots, not a canonical same-time daily return.
- WI-059-S01 readiness: `missing_prior_state` for 9/17 10:00 and `fx_input_stale` for 9/16 16:00.
- First isolated read-model slice: red tests reproduced a false `pass` overview with a degraded row and a
  false-degraded performance history using the actual Gold literal `pass`. The overview now suppresses a complete
  total when row/FX/account coverage is deficient, retains an explicitly named verified KRX/KRW position subtotal,
  and removes invalid converted amounts. The history literal is corrected and degraded sums are null.
  Focused warehouse tests: 34 passed; digest/read-surface adjacency: 33 passed. A read-only production DB
  preflight at 2026-09-17 14:32 showed `partial`, complete total suppressed, 22 verified KRX/KRW position lines,
  and `fx_input_stale` as the missing reason. Full shared gate: 741 passed, one pre-existing Authlib
  deprecation warning. No public service or Telegram deployment occurred.
- DEC-057/ADR-029 approve capability isolation. Shared quality composition, Telegram presentation `2.3.0`,
  data-quality/pipeline-run false-green correction and the one-image `wi060` protected target have focused
  deterministic coverage. `scripts/check_resilient_portfolio_cases.py` passes five immediate no-network/no-send
  scenarios. Korea Eximbank source, collection, dataset and pipeline contracts are now approved for guarded
  activation; the credential remains a pinned Secret Manager reference and no production fallback call has yet run.
- Read-only MotherDuck previews with branch code require no Scheduler wait: 2026-09-18 `kr-1000` and `kr-1600`
  are both `ready_partial` with only `prior_fx_input_stale`; 2026-09-21 both slots are `ready`/`pass`. No run row,
  source call or Telegram claim was created. The standalone fault matrix passed, the protected release command
  dry-run reused one immutable image for Remote MCP and all three fixed-slot Jobs, and the full repository gate
  passed with 749 collected tests and one pre-existing Authlib deprecation warning.
- PR #121 CI run `35605547380` passed the Project OS full gate. The release target now writes a retained rollback
  manifest, stages a tagged Remote candidate with zero traffic, probes health/discovery/auth boundary, updates all
  three Jobs with the same digest, then promotes and probes the canonical Remote endpoint. Candidate, Job-update,
  promotion or canonical-smoke failure leaves or restores the previous serving Remote revision and prior complete
  Job exports. The post-change dry-run exercised this order without provider calls, Telegram sends or production
  writes.
- The external FX slice has deterministic parser, source-date, stale-reference, cross-source disagreement and
  empty-response coverage. `scripts/check_fx_fallback_cases.py` passes four immediate no-network/no-DB/no-send
  cases. Focused client/service/pipeline/warehouse/release tests pass (96 tests). The WI-060 dry-run stages one
  immutable Remote revision at zero traffic, verifies the pre-provisioned exact-secret accessor binding, updates
  all three fixed-slot Jobs, executes the read-only source preflight, and promotes Remote only afterward. A failed
  preflight restores all prior Job definitions; HTTP error causes that could embed the auth query are discarded.
  The complete repository gate passes with 763 tests and one pre-existing Authlib deprecation warning.
- Protected run `35663503027` built merge `a72518e` as digest `sha256:ef124d7a...b81896` and staged Remote revision
  `kis-portfolio-remote-00063-vab` at 0% traffic, then stopped before any Job update because the intentionally
  non-admin GitHub deploy identity could not add the new Secret IAM binding. Existing Remote revision `00048-77w`
  remained at 100% and all Jobs remained unchanged. The corrective release path now treats IAM as pre-provisioned
  infrastructure and performs an exact read-only accessor check instead of requesting Secret IAM mutation rights.
  The exact `kis-portfolio-pipeline` accessor binding was then provisioned once with an owner-authorized local
  administrative identity; no project-wide role and no GitHub Actions IAM-administration permission was added.
- Protected run `35664495921` built merge `20334fd` and staged Remote revision
  `kis-portfolio-remote-00064-buq` at 0% while `00048-77w` continued to serve 100%. It updated the three report Jobs,
  but the source preflight execution `kis-portfolio-owned-core-v2-1000-dsx9x` ran at 07:51 KST before the official
  same-day rate was published and failed with a redacted `KoreaEximError`. Automated Job restoration then found the
  Cloud Resource Manager API disabled. After enabling that required API, the exact retained rollback exports were
  restored manually and all three Jobs again referenced prior digest
  `sha256:e02bf49aa13057287a323d368401dc4fc8eb41f633684a541b75f509bda762c3`; Remote `00048-77w` remained at 100%.
  A direct client check for 2026-09-22 later passed, confirming publication-time coupling rather than a bad key.
  `WI-060-S02` moves rollback-service readiness ahead of image build/deployment and makes release validation resolve
  the most recent governed KIS business date. Explicit `today` remains available for runtime availability tests.
  Focused preflight/release tests pass (83 tests), both immediate fault scripts pass (4 FX cases and 5 portfolio
  capability cases), and the complete repository gate passes with 770 tests and one pre-existing Authlib warning.
- Protected run `35741804406` stopped before image build, rollback capture or any production mutation. The rollback
  API was enabled, but `gcloud services list --format=value(name)` returned the canonical resource name
  `projects/.../services/cloudresourcemanager.googleapis.com` while the new guard compared it with the short service
  name. The parser now normalizes either form, its regression fixture uses the real output shape, and a missing
  rollback manifest after an intentional pre-mutation stop is a warning rather than a second workflow failure.
- PR #124 merged as `26ccdb8`. Protected run `35742953730` passed the full gate and deployed immutable digest
  `sha256:8d2c499a1efa4de5ec403f344ff9b6f5d42ab3526adf4e6f885dcb4fa6063907` to Remote revision
  `kis-portfolio-remote-00065-ley` and all three fixed-slot Jobs. The new Remote serves 100% traffic; its `/health`
  returns 200 and unauthenticated `/mcp` returns 401. Preflight execution
  `kis-portfolio-owned-core-v2-1000-p857r` completed successfully without a Telegram send: source
  `korea-eximbank`, requested/reference date 2026-09-22, native field `deal_bas_r`, deviation ratio
  `0.01711976487876561351947097722`, reason `pass`. Release labels on Remote and all Jobs match merge SHA
  `26ccdb8ca79d7b206d7de7093c947e228bfed811` and run `35742953730`.

## Closeout

- Result: stabilizing; implementation and protected production activation are complete.
- Remaining risk: real Claude MCP output and the first owner-visible scheduled partial/complete report presentation
  have not yet been accepted. Do not close WI-060 or MS-007 on provider/API success alone.
- Follow-up Work Item: none yet.
