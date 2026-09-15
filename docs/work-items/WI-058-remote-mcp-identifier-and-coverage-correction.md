---
id: WI-058
title: Correct Remote MCP identifiers and empty-coverage semantics after real Claude use
status: stabilizing
type: defect
owner: owner
decision_refs: ADR-020, ADR-021, ADR-028
requirement_refs: DEC-002, DEC-029, DEC-031, DEC-032, DEC-034, DEC-038
milestone_ref: MS-005
delivery_refs: none
parent_work_item: none
depends_on: WI-051
discovered_from: WI-042, WI-046
supersedes: none
rollback_of: none
execution_scope: production
production_effects: deploy
architecture_impact: none; restores approved public identifiers, direct exposure and explicit unavailable semantics inside the existing Remote MCP boundary
data_impact: add per-run price-bar quality evidence without schema, grain, retention or source changes
security_impact: no new fields containing account ids, credentials, raw payloads or provider messages
cost_impact: no new source calls or standing resources
stabilization_window: one owner-confirmed Claude session against the canonical or compatibility-tag URL after revision 00046
stabilization_exit_refs: GitHub runs 34915731283 and 34916315077, revision kis-portfolio-remote-00046-4t8, owner Claude verification
rollback_plan: revert the corrective release to the current immutable V2 image if live read compatibility regresses
---

# WI-058 — Correct Remote MCP identifiers and empty-coverage semantics after real Claude use

## Problem and evidence

The first sustained Claude usage called `get-market-snapshot` with public symbol `000660`, `get-data-quality` with
canonical dataset `dataset.price-bar-daily`, and `get-pipeline-run` with public command name `portfolio-refresh`.
All three returned `no_governed_rows` even though read-only production inspection found current price bars and
successful owned-core runs. `get-exposure-analysis` also returned empty while current Gold position rows existed.

The causes are distinct: public symbol and command aliases are not resolved to internal canonical IDs, the owned-core
quality stage records account coverage but not the price-bar coverage it publishes, the generic empty envelope makes
missing evidence look like missing data, and the exposure SQL filters the nonexistent aggregate level `instrument`
instead of the canonical `position` level. The live Claude connector additionally used the preserved `wi046-v2`
tagged candidate URL rather than the canonical stable service URL; connector correction remains an operational step,
not a code excuse.

## Classification and contract

- Initial classification: `defect` in the approved Remote MCP read and runtime-quality contracts.
- Compared contracts: DEC-029/031/032/034/038, ADR-020/021/028, `pipeline.owned-portfolio-core-v2`,
  `dataset.price-bar-daily`, and the Remote V2 tool contracts.
- Contract result: existing implementation fails approved usability, direct-exposure and explicit-unavailable
  behavior; no new product capability or provider is requested.
- Approval: the owner reported the real-use failure and instructed the project to form hypotheses and find a
  solution on 2026-09-15.
- Release approval: the owner explicitly requested production deployment on 2026-09-15.

## Scope

- Include public symbol/canonical instrument resolution for market reads.
- Include `portfolio-refresh` to `pipeline.owned-portfolio-core-v2` read alias resolution.
- Include distinct empty reasons for unknown identifiers, missing quality evidence and absent governed rows.
- Include current price-bar quality evidence in each owned-core run without adding source calls.
- Include direct instrument exposure from canonical `position` Gold rows and explicit macro/ETF missing coverage.
- Include realistic non-empty regression fixtures using the exact Claude inputs.
- Exclude ETF constituent look-through, macro source activation, live quote read-through, schema changes and deployment.

## Acceptance criteria

- [x] `000660`, `KRX:000660` and canonical `v1|KRX|000660` resolve to the same governed market row.
- [x] `portfolio-refresh` resolves current owned-core runs; unknown aliases fail explicitly instead of returning an
      indistinguishable empty list.
- [x] recent owned-core runs record `dataset.price-bar-daily` coverage evidence and missing evidence is not described
      as missing dataset rows.
- [x] direct exposure returns current instrument rows; macro and unsupported ETF coverage remain explicit.
- [x] focused MCP/pipeline tests, quick gate and full gate pass.
- [x] production deployment and live Claude verification remain separately approved release/stabilization steps.

## Change impact

- Architecture: no new boundary, provider, scope or transport.
- Data/schema/backup: no schema change; one additional governed quality result per successful owned-core run.
- Security/privacy: public symbol aliases only; existing account alias and sensitive-field suppression remain.
- MCP/API compatibility: additive friendly aliases and more precise missing reasons; canonical identifiers remain valid.
- Deployment/rollback: deploy only the Remote MCP service and existing V2 owned-core batch jobs through the protected
  `master` workflow; do not change Scheduler, auth, Secret Manager configuration or schema.
- Cost/SLO: zero additional source calls; bounded metadata lookup only.

## Plan

1. Freeze the four real-Claude reproductions as non-empty and fail-explicit regression tests.
2. Normalize public instrument and pipeline references at the read adapter boundary.
3. Correct direct exposure and per-run price quality evidence.
4. Run focused, quick and full gates; then prepare a separate protected release/live-smoke handoff.

## Sub-items

- `none`.

## Stabilization plan

- Observation sample: one canonical stable-URL Claude session after a protected release.
- Signals: the three reported inputs return governed data or precise evidence status; direct exposure is non-empty;
  Cloud Run requests reach the stable URL.
- Rollback trigger: response validation, authorization, current portfolio reads or scheduled pipeline regression.
- Exit: protected release evidence plus owner-confirmed Claude results. No production action is authorized yet.

## Evidence

- Read-only production inspection on 2026-09-14/15: 16,041 V2 price rows across 24 instruments; three successful
  2026-09-14 owned-core slots; current SK hynix and Samsung Electronics bars; 1,961 Gold daily-state rows, all using
  `position` or `cash`; no `instrument` aggregate rows.
- Cloud Logging: reported Claude requests reached the preserved `wi046-v2` tagged URL and returned HTTP 200.
- Patched-adapter read-only query against production MotherDuck: `000660` resolved to `v1|KRX|000660` and returned
  the 2026-09-14 raw close 1,699,000; `portfolio-refresh` returned three succeeded runs; direct exposure returned 26
  position rows; missing price quality evidence, macro data and unsupported ETF look-through were distinguished.
- Verification: 32 focused warehouse/managed-collection tests passed; 63 adjacent MCP/read/governance tests passed;
  quick gate passed; full gate passed with 725 tests and one pre-existing Authlib deprecation warning.
- Release: PR #111 merged as `8e09c45bb0d92719c611d2bd194fd2ea42251bcf`; Remote workflow
  `34915731283` and V2 core Job workflow `34916315077` succeeded. The three jobs use the same immutable image digest
  `sha256:ea57f6cf8f40c26ec958cbac8dcfcb354d84b57257d7dcaf0ab09b12cdd5ab06` and retain their fixed slot arguments.
- Remote traffic: workflow created `kis-portfolio-remote-00046-4t8` with the expected SHA/image, but historical pinned
  traffic left it retired. A controlled 0% tagged health/auth smoke passed, then exact-revision traffic was promoted
  to 100%. Canonical and compatibility-tag `/health` return 200 and unauthenticated `/mcp` returns 401.

## Closeout

- Result: production release deployed and transport/auth smoke verified; stabilizing for owner Claude read acceptance.
- Remaining risk: authenticated tool payloads still require an owner Claude session; historical runs will not gain
  retroactive price-quality evidence, while the next successful owned-core run will record it.
- Follow-up Work Item: none yet.
