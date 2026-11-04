---
id: WI-077
title: Make accepted V2 documents navigable by feature, current task and symptom
status: closed
type: maintenance
owner: owner
decision_refs: DEC-047, GOV-013
requirement_refs: owner approved text-only operational documentation reorganization 2026-11-02
milestone_ref: MS-004
delivery_refs: none
parent_work_item: none
depends_on: WI-032
discovered_from: WI-032
supersedes: none
rollback_of: none
work_lane: operations
execution_scope: repository documentation only
production_effects: none
architecture_impact: none; navigation changes preserve all existing authorities and product boundaries
data_impact: none; no source, schema or monetary change
security_impact: no new private operational evidence or payload publication
cost_impact: none; no database, service, new CLI, generator or UI
user_visible_impact: no
real_use_acceptance: not_applicable
real_use_evidence_refs: not_applicable
rollback_plan: revert this documentation change; keep original history snapshots and issued identities
---

# WI-077 — Operational documentation navigation

## Problem and evidence

After V2 owner acceptance, the document home and TODO still lead through completed construction tasks and old
milestone states. Feature maintenance and symptom lookup require following numbered Work Items manually.

## Classification and contract

Maintenance of WI-032's accepted canonical documentation outcome under the operations lane of closed MS-004.
Owner approved a text-only reorganization after comparing document navigation, generated indexes and SQLite.
Preserve canonical requirements, architecture, data/security/deployment policy and immutable WI history.
No new policy or runtime behavior is approved. Closed milestones remain closed.

## Scope

Include document home, feature/requirement/code/test links, current TODO, symptom-oriented troubleshooting,
clearly dated historical snapshots and milestone-navigation corrections. Preserve original WI/design/evidence.
Exclude new tools, databases, generators, UI, automatic indexing and source/runtime changes.

## Acceptance criteria

- [x] Feature names lead to existing requirements, production code, relevant tests and accepted limitations.
- [x] TODO separates current tasks, recurring runbook duties and deferred/unreviewed ideas; old text is preserved.
- [x] Symptom lookup leads to first checks, bounded recovery guidance and owning historical records.
- [x] Current/historical status and document authority are unambiguous; issued identities and evidence survive.
- [x] Existing quick/full gates and one-off navigation/anchor checks pass; no tool or product test is added.

## Change impact

Documentation only; no authority, public MCP, source/data contract, dependency, cost or security boundary change.
Disposition metadata may classify new navigation/history files under the existing approved categories.

## Plan

1. Register this operations maintenance item; inspect baseline and ask about unresolved TODO classification.
2. Prepare current navigation, feature and troubleshooting maps; preserve construction text as historical material.
3. Review example navigation paths and links, run existing gates, and record any unresolved classification.

## Sub-items

- WI-077-S01: owner requested individual display of historical candidates after the initial grouped closeout; documentation-only correction.

## Stabilization plan

Not applicable: repository-only navigation. No elapsed production observation or deployment is needed.

## Real-use acceptance

Not applicable: no product-client behavior changes. Verify reader navigation through representative feature,
symptom and current-task queries using actual repository links instead of synthetic product acceptance.

## Evidence

Baseline: MS-008/V2 handoff PR #176; WI-071 accepted scope PR #175. Initial documentation inventory: 190 Markdown
files under docs, approximately 1.8MB. Old TODO and milestone navigation retained superseded construction states.

- Quick and full passed: 971 tests, one existing Authlib deprecation warning (51.68s full run).
- One-off navigation review checked current document paths/headings and rebased historical links. All 18 public
  tool names are discoverable in the feature map. Source code/test entry paths resolve in the actual repository.
- Representative reader paths reviewed: cash change → observed-cash route/limitations/test/WI-071; no Telegram →
  separate report/summary/detail checks and readiness runbook; next work → current tasks versus unreviewed ideas.
- All pre-existing WI, design, operations and requirements files remain byte-identical to baseline. Original TODO,
  traceability and milestone-map prose/tables/states are preserved in dated snapshots; only provenance banners
  and relative Markdown link destinations differ. Raw originals remain in Git at 1b628ce.
- Old TODO proposals are grouped as unreviewed candidates, not silently approved or discarded. Owner was asked
  about grouped versus individual display; grouping preserves all source text and remains easy to revise.
- GOV/DGOV requirement mappings and every issued WI reference remain available without changing checker policy.
- No new checker/test/tool/CLI/database/UI/generator or runtime/financial change.

## Closeout

Closed as repository-only maintenance after existing quick/full gates and actual navigation/preservation review.
Document home, feature traceability, current TODO and symptom index are the everyday entrypoints. Dated source
snapshots and original WI/design/acceptance evidence remain reachable. No elapsed operational observation or
MCP replay is applicable because the product behavior and public surface are unchanged.

Initial closeout left a review preference: grouped versus individual display of unreviewed TODO ideas. Neither representation
changes approval, priority or source facts. Product/source limitations and ambiguous historical identifiers are
shown explicitly; no DEC/ADR renumbering or new requirement approval is part of this closeout.

## WI-077-S01 — Individual TODO candidate display, 2026-11-02

Owner answered the pending review question: “후보도 새 TODO에서 개별적으로 보여주세요”. Replace the catch-all
candidate row with named, individually visible historical ideas. Keep every candidate unreviewed and unprioritized;
identify already delivered/superseded construction premises separately so they do not become new work. Preserve the
historical snapshot and product scope; no new feature, policy, tool or runtime effect.

Result: closed as documentation-only follow-up. Twelve historical ideas are individually visible with review
questions and original/current references. Delivered or superseded construction premises have a separate table.
Quick gate passed; 244 TODO/traceability paths and heading links resolved. Required full regression validation is
recorded in the follow-up PR/CI. All original snapshot files remain unchanged. The initial grouping preference
above is superseded by this direct owner answer; no review preference remains pending.

## WI-077-S02 — Semantic compaction requested 2026-11-03

Owner rejected navigation-only reorganization as insufficient: retain meaning rather than every construction
episode in everyday context; preserve original build records in a recoverable compressed backup and link to cases
only when needed. This corrects the same documentation outcome, not product functionality or approval scope.

Current work: derive an operating model and normalized current domain contracts from existing approved sources;
retire loose construction design/history/milestone narratives after byte-verified archival; preserve every issued
WI, delivery ID, registry relationship, requirement/ADR source and evidence. Update incoming references and retain
both local archive recovery and fixed-commit source links. Existing checks remain unchanged. No database, new
indexing tool, runtime, source or data effect. Current contract boundaries must not be weakened to shorten text.
Semantic accuracy and archive/reference validation are required before completion.

Result: closed after semantic consolidation and recovery validation. The original navigation-only closeout above
is superseded for the design/history/milestone reading model by this correction.

- Current knowledge separates operating meaning, system responsibility/why, ledger/coverage/reconstruction,
  analytics, alert delivery and reference-history contracts. It preserves formulas, quality/publish conditions,
  unknown/null semantics, owner authority and existing source/security limitations; construction phases and
  dated execution counts are not current instructions.
- 35 original construction documents (380,723 bytes, 4,509 lines) are archived at the exact base commit.
  The 136,549-byte gzip archive and every member match the SHA-256 manifest. Fresh temporary extraction
  was compared byte-for-byte with every original Git blob. Current core/index reading set: 774 lines.
- Reviewed distinctions include source consistency versus completeness, observed cash versus settled/flow
  evidence, valuation versus performance, independent partial capabilities, and terminal unknown delivery.
  Old security/migration hypotheses defer to current accepted policy; no approved boundary was relaxed.
- Existing local Markdown paths and heading links resolve after retirement; 69 issued delivery IDs are
  preserved. Milestone/WI identities and dependencies remain byte-preserved with only this sub-item appended.
  Original build prose is recoverable locally or through fixed-commit case links. Individual TODO candidates
  remain visible and unreviewed. No new tools, checks, DB, generator, runtime or product behavior.
- Existing full gate: 971 tests passed, one existing Authlib deprecation warning (52.16s). Quick/staged and
  protected PR checks remain required. No production/MCP replay applies to documentation-only behavior.

## WI-077-S03 — Steady-state Project OS alignment

Governance correction within the existing documentation outcome. PR #179 left the policy and Skill
on the construction-first reading path. The checker still treated a historical delivery-plan filename
as its identifier source. The local review also compared the old PR branch to a stale base.
Align policy, agent entry points, document format and existing identifier checks as one change.

Closed after applying the operating maintenance path to this correction. Policy §0 now routes the
work by symptom or feature, §3.1 owns the knowledge update, and the Skill and AGENTS use both.
The five domain contracts share the agreed structural order. The choice of singular
`<domain>-contract.md` names and placement of the delivery identity inventory beside the registry
are implementation choices for this correction.

Evidence: 570 local links and headings, five contract layouts, and all 69 issued delivery IDs
verified. Existing registry entries and the archive match the previous main branch. The current
checkout passed quick and full with 971 tests. Three restore subprocesses failed on an initial
run using the shared environment's editable checkout and passed after binding imports to the
current worktree. Repository-only governance change with no product client acceptance scenario.
