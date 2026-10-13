---
id: WI-068
title: Recover retained legacy portfolio history for bounded longitudinal use
status: in_progress
type: architecture
owner: owner
decision_refs: DEC-062, ADR-033
requirement_refs: owner intake 2026-10-13, WI-066 truthful-history boundary
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-066
discovered_from: WI-066
supersedes: none
rollback_of: none
execution_scope: isolated approved implementation and recovery rehearsal; protected production release follows verification
production_effects: none
architecture_impact: approved owner-only noncanonical reference dataset and explicit opt-in projection; canonical defaults unchanged
data_impact: approved additive migration 0021 and pinned noncanonical reference import; retained V1/native V2 immutable, no canonical promotion
security_impact: historical portfolio payload remains confidential and owner-only; no raw account identifiers or backup locators may enter MCP responses
cost_impact: expected storage-local analysis with no new paid source; any new always-on service or material query cost requires approval
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: owner-Claude longitudinal question and direct Codex July history probes from 2026-10-13; implementation evidence pending
stabilization_window: immediate direct Codex positive/partial/error plus owner-Claude same-question replay
stabilization_exit_refs: protected migration/import/restore, direct Codex replay, owner-Claude acceptance
rollback_plan: disable reference opt-in by restoring prior Remote revision/tag; retain append-only reference and original data
---

# WI-068 — Recover retained legacy portfolio history for bounded longitudinal use

## Problem and evidence

The owner operated earlier versions of the portfolio application long enough to accumulate historical portfolio,
holding, price, FX and transaction observations. Those records were not designed for the current governed V2 schema
and are retained in legacy MotherDuck objects and private backups. WI-066 deliberately quarantined incomplete legacy
total-asset aggregates instead of presenting them as trustworthy drawdown history; it did not reconstruct or publish
the retained source data.

On 2026-10-13, production inspection and actual MCP calls established that the situation is mixed rather than simply
"history absent":

- retained V1 portfolio data exists, but the migrated V2 daily state contains only 27 legacy dates from 2026-04-19
  through 2026-08-27 and only one July date, 2026-07-24;
- the 2026-07-24 aggregate cannot be promoted as a complete total because the overseas feeder was not represented;
- retained and migrated price observations exist for part of the historical period, but coverage and price basis vary
  by instrument;
- the WI-066 protected release changed only a derived view and quality interpretation. Its preserved execution
  evidence reports `source_calls=0`, `data_rows_mutated=0` and `deletions=0`;
- owner-Claude attempted to reconstruct history from transaction data but stopped because the public tool and governed
  data surface could not provide sufficient source-grounded inputs.

The data may have high present decision value even if its value naturally decays as native V2 history accumulates.
It therefore needs a bounded recovery decision, not silent deletion, automatic canonical adoption, or an open-ended
rewrite of current history contracts.

## Owner approval — 2026-10-13

The owner explicitly approved the 25-date private candidate and the separate noncanonical DB/MCP contract,
then requested implementation and activation. DEC-062 and ADR-033 record this decision. Original rows,
WI-066 quarantine, native-V2 priority and unavailable Aug 6/25 boundaries remain mandatory.

## Classification and contract

- Initial classification: architecture and data-recovery change, discovered from WI-066; not proof that the retained
  records are canonical or complete.
- Compared contracts: WI-066 legacy quarantine, Data Governance Harness contract-first and publish gates,
  `docs/data-catalog.md`, `docs/backup.md`, and the V2 Bronze/Silver/Gold lineage boundary.
- Contract result: retained backups may be inspected as recovery inputs, but existence alone does not authorize
  canonical publication or MCP consumption. Provenance, grain, time semantics, coverage and quality must be established
  first.
- Approval history: the initial intake authorized investigation only. The owner later authorized bounded recovery
  preparation for retained dates with absent overseas cash assumed zero. The concrete production storage/consumption
  architecture still awaits approval; no DDL, backfill, public API/MCP activation or deployment has occurred.
- Decision gate: after inventory, compare and obtain owner approval for one of three bounded patterns:
  1. immutable legacy landing plus compatibility transformation into versioned V2 datasets;
  2. an owner-only governed reference dataset/read model that remains explicitly noncanonical;
  3. a hybrid that promotes only source-grounded facts and leaves incomplete aggregates reference-only.

## Scope

- Include: inventory every retained local, MotherDuck and private-backup artifact that may contain portfolio snapshots,
  holdings, prices, FX, cash, trades or source timestamps; record checksum/provenance without exposing secrets.
- Include: characterize each artifact's grain, logical/effective/knowledge time, account and instrument coverage,
  duplicates, nulls, feeder completeness, valuation basis and recoverable lineage.
- Include: reconcile retained V1 rows, earlier V1-to-V2 migration inputs and outputs, and current V2 history without
  mutating any of them.
- Include: build representative July fixtures and a coverage matrix showing which questions are supportable as
  canonical facts, reference-only facts, derived estimates or unavailable.
- Include: compare canonical compatibility import, separate internal reference read model/API, and hybrid approaches
  for implementation effort, fidelity, decay horizon, security, backup, rollback and MCP usability.
- Include after separate owner approval: define the chosen data/read-model contracts, migration or projection,
  quality labels and actual-client acceptance suite.
- Exclude: inferring missing cash flows or totals solely from valuation differences; treating transaction reversal as
  authoritative without complete opening state, corporate actions, fees, FX and cash evidence.
- Exclude: weakening WI-066 quarantine, overwriting native V2 rows, deleting retained source/backup data, or silently
  presenting reference-only data as canonical performance history.
- Exclude: the independent `get-market-history` adjusted-versus-raw selection defect except where its evidence is
  needed to prevent a false conclusion that a retained dataset is empty.
- Exclude: deploying WI-067 or bundling this recovery with its calendar-aware pipeline-status release.

## Acceptance criteria

- [ ] A checksum- and provenance-backed inventory identifies every retained artifact inspected, its time span, object
      shape, approximate row count, sensitivity and restore/read status.
- [ ] A field-level compatibility matrix maps recoverable legacy facts to current dataset contracts and labels every
      unmappable or ambiguous field without guessing.
- [ ] July 2026 coverage is demonstrated with deterministic fixtures for complete, partial, conflicting and absent
      portfolio/price/FX/transaction inputs.
- [ ] The three architecture patterns are compared and an owner-approved ADR/DEC selects the bounded consumption
      boundary before any production implementation begins.
- [ ] The selected design preserves immutable raw evidence, explicit legacy provenance, native-V2 precedence and
      non-overwriting idempotency.
- [ ] Canonical outputs pass reconciliation and quality gates; reference-only outputs are visibly noncanonical and
      cannot satisfy canonical performance or total-asset metrics.
- [ ] Actual authenticated Codex and owner-Claude positive, partial and error scenarios answer the July longitudinal
      question using only evidence allowed by the selected contract.
- [ ] Backup/restore, rollback, quick and full repository gates pass before release consideration.

## Change impact

- Architecture: likely introduces a legacy-recovery boundary or compatibility projection. The choice changes SSOT,
  lineage and consumer responsibilities and therefore requires an approved ADR before implementation.
- Data/schema/backup: inventory is read-only. Any new dataset, schema, transformation, restored object or retention
  rule requires DGH manifests, `docs/data-catalog.md`, machine catalog, versioned migration and backup/restore updates.
- Security/privacy: confidential owner portfolio history only. Keep backup URIs, raw account identifiers, credentials
  and unrestricted payloads out of Work Item evidence and public MCP responses.
- MCP/API compatibility: no change at intake. A future reference read model must use the common governed envelope and
  explicit canonical/reference/estimated/unavailable semantics; adding a public tool requires separate approval.
- Deployment/rollback: none at intake. A future release must be reversible, non-destructive and independently
  deployable from WI-067.
- Cost/SLO: prefer bounded existing-storage reads. The historical value decays over time, so avoid a permanent service
  unless measured reuse justifies its operational cost.

## Plan

1. Locate and fingerprint retained V1 objects and backup manifests without restoring into production or changing live
   database state.
2. Profile coverage and semantics, then reconcile the retained source, prior migration ledger and current V2 rows.
3. Freeze sanitized July fixtures and produce a canonical/reference/estimated/unavailable compatibility matrix.
4. Compare the three architecture patterns and request owner approval for the smallest useful boundary.
5. Only in a later approved phase, register contracts and implement the selected import/projection/read model.
6. Verify with deterministic tests, backup/restore rehearsal and immediate authenticated Codex/Claude real-use calls.

## Sub-items

- `none` at intake. Implementation corrections within the approved outcome may become `WI-068-SNN`; independent
  query-selection or new-source outcomes require separate Work Items.

## Stabilization plan

- Observation period/sample: not applicable during intake. A future user-visible activation must replay July and
  current-native windows immediately, then observe bounded production reads without waiting for a scheduler slot.
- Signals: source/target row counts, key uniqueness, provenance coverage, canonical versus reference classification,
  reconciliation deltas, query latency and MCP missing-coverage reasons.
- Rollback trigger and safe state: any overwrite, false canonical promotion, unexplained reconciliation delta, secret
  exposure or regression of native V2 reads; disable the new consumer/projection and retain immutable source evidence.
- Exit evidence and owner acceptance: selected contract, restore rehearsal, production-equivalent reconciliation,
  actual-client positive/partial/error evidence and owner acceptance of the original longitudinal question.

## Real-use acceptance

- User-visible basis: yes; the outcome exists so Codex and Claude can use retained history without fabricating
  continuity or declaring existing backup data absent.
- Actual approved clients/transports: authenticated Codex Remote MCP and owner-Claude custom connector.
- Immediate positive scenario: a retained interval with source-grounded holdings/prices returns usable history with
  explicit legacy provenance.
- Immediate partial scenario: July inputs missing an overseas feeder or adjusted basis return bounded facts and named
  missing coverage rather than a complete total or empty-data claim.
- Immediate error scenario: unsupported range, ambiguous artifact or unavailable reference boundary returns an
  owner-debuggable error without exposing backup paths or account identifiers.
- Findings: same-outcome recovery defects belong to WI-068 sub-items; independent query semantics, providers or public
  tool additions require separate Work Items and approval.

## Evidence

- Owner report: earlier application versions accumulated historical data now believed to remain in incompatible
  backups; owner-Claude could not reconstruct it through the public tool/data surface.
- Direct production evidence on 2026-10-13: V1/V2 history is retained but sparse and mixed; July price data exists for
  part of the portfolio while the legacy total-asset aggregate is incomplete.
- WI-066 Cloud Run execution `kis-portfolio-wi066-wqrjl`: succeeded with an unchanged 3,369-row fingerprint,
  `view_replaced=true`, `source_calls=0`, `data_rows_mutated=0` and `deletions=0`.
- First read-only investigation, 2026-10-13: [inventory and architecture comparison](../operations/wi-068-retained-legacy-history-inventory-2026-10-13.md),
  [sanitized artifact fingerprints/coverage](../../governance/project/evidence/wi068/retained-artifact-inventory-2026-10-13.json),
  and [July observed-shape/synthetic conflict cases](../../governance/project/evidence/wi068/july-compatibility-shapes-2026-10-13.json).
- Observed 473 readable local Parquet files across 15 directories (14 manifests and one incomplete export),
  20 private GCS recovery indices with verified manifest hashes and 1,140 existing size-matching object references,
  86 private portfolio raw objects, retained main/V2 facts and empty known `my_db` tables. No production restore performed.
- Both V1 backups' portfolio/overseas/overview/holding families remain in live MotherDuck: eight comparisons report
  zero missing rows and zero changed row hashes. This supports preservation within the inspected scope, not universal
  proof that no historical artifact was lost.
- July raw brokerage balance exists on 07-06/24/29; daily-state import covers only 07-24. July V2 prices contain
  18 dual-basis instruments plus one raw-only provenance-gap instrument. July overseas KRW/cash coverage and daily FX
  remain insufficient; 22 July cash events are fee-only. No legacy canonical total candidate was established.
- Recommended architecture proposal: bounded hybrid with native-V2 precedence and source-fact-only promotion;
  owner approval, field/pagination/time reconciliation and explicit reference consumption contracts remain required.
  WI-068 stays `proposed`; no implementation phase, DDL, backfill, publish, API/MCP tool or deployment was started.
- Gate evidence: quick passed using repository Python 3.13.3 and an isolated writable uv cache; final full passed: 815 tests, one warning (35.12s).
- Investigation limits: metadata/manifest verification does not claim every GCS payload SHA-256 or a fresh restore;
  whole-disk and external storage are outside this first investigation. GCS version metadata shows no noncurrent or soft-deleted objects.
- Owner clarification on 2026-10-13: daily total assets are the priority; account detail can follow. Read-only recheck
  confirms positive stored totals on 7/24 for all five accounts and on 7/06/29 for brokerage; historical overview
  observations span April 7, May 9, June 5 and July 1 distinct dates. These totals are not absent or universally
  unusable, but overseas completeness and extractor semantics remain separate gates. See the report's total-first
  clarification and aggregate evidence. V1 batch code/deployment provenance needs further investigation; sparse
  snapshot rows alone cannot identify MCP versus batch origin.
- Read-only V1 batch follow-up: [provenance report](../operations/wi-068-v1-batch-provenance-2026-10-13.md) and
  [aggregate audit/source/table evidence](../../governance/project/evidence/wi068/v1-batch-provenance-2026-10-13.json)
  connect the pre-V2 inspection's three Cloud Run Jobs to order/transaction/token tables in `kis_portfolio`, not
  total-asset snapshot collection. Complete pre-V2 audit has 313 records; July has 23 failed domestic terminals,
  18 successful/5 failed overseas terminals and 23 successful token terminals. Domestic raw collection begins
  on Aug 11; source-level failure cause remains unproven. PR #1 is closed-unmerged; all 37 pre-V2 deploy runs' 21
  source CLIs lack the fourth asset snapshot command, and the exact asset Job-name audit is empty. These findings
  support a scoped collection/operations gap, not a universal assertion that the owner's remembered independent
  collector never existed or that any historical data was deleted. No production mutation or remediation performed. Follow-up quick and full shared gates passed (815 tests, one warning).
- Owner requested concrete filling after accepting bounded dates and missing overseas cash = 0. A private local
  27-date preview now contains 14 recorded references, 11 estimates and 2 unavailable global totals (Aug 6/25).
  Earlier 27-date availability meant retained observations, not 27 verified repaired totals. The ten rows with
  missing KRW position valuation use actual public FRED DEXKOUS dated observations; May 22 additionally requires
  the cash-zero assumption. No missing position/quantity is fabricated. Retained V2 legacy-state count/hash unchanged.
- [Concrete proposed consumption contract](../design/wi-068-legacy-total-recovery-contract.md) and
  [sanitized candidate evidence](../../governance/project/evidence/wi068/total-recovery-candidate-2026-10-13.json)
  define separate append-only noncanonical references and an explicit opt-in array on existing performance history.
  Dataset v0.1.0 is proposed; the read-model draft remains outside the runtime registry until architecture approval. Monetary preview stays owner-only under ignored var;
  no DDL, production write, backfill, public API code or deployment occurred. Exact production boundary awaits owner ADR. Quick and full shared gates pass (815 tests, one warning).
- Implementation, contract and release evidence: pending a later owner-approved phase.

## Closeout

- Result: proposed architecture/data-recovery intake only; no implementation or production effect authorized.
- Remaining risk: retained artifacts may be incomplete, mutually inconsistent, unavailable to the current runtime or
  too ambiguous for canonical promotion. Their decision value also decays as native V2 history accumulates.
- Follow-up Work Item: pending inventory and owner architecture decision; do not pre-allocate an ID.

## Approved implementation evidence — 2026-10-13

- DEC-062/ADR-033 approved by owner after reviewing the 25 valued/2 unavailable candidate.
- Migration 0021 adds a separate append-only, backed-up reference table; explicit opt-in on the existing performance
  tool returns separate total levels. Default legacy quarantine, native state and independent market basis defect unchanged.
- Pinned input SHA: `c1b5a62d0146b1f72265519aed09a3952768329b1b5afa00f6802b622c23e95b`.
- Actual private candidate rehearsed in disposable local DuckDB: inserted 27, replay inserted 0, projection 25;
  Aug 6/25 remain unavailable. No amounts or raw source locators enter tracked evidence.
- Synthetic tests cover reconciliation, input hash failure, native precedence, unavailable NULL, total-only/range errors,
  append-only conflict, pre/post private backup/fresh restore and release replay.
- Protected release target `wi068` updates only a bounded one-off migration/import Job and the Remote stable/tag
  routes after backup/restore succeeds. Account-history/core producer Jobs, schedulers, auth/IAM and source credentials
  are not touched. Rollback restores both prior routes and retains all source/reference data.
- Initial full gate exposed a test-fixture dependency on whichever WI was active; fixture isolation was corrected,
  without relaxing the one-active-implementation rule. Final gate and actual production/client evidence follow.

- Verification: repository Python 3.13.3; quick passed, full passed **833 tests** (39.89s);
  `git diff --check` clean. Existing Authlib deprecation warning only. Protected activation/client replay pending.
