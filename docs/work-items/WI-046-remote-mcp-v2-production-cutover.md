---
id: WI-046
title: Cut production connectors and schedules over to Remote MCP V2
status: in_progress
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-030, DEC-034, DEC-045
milestone_ref: MS-003
delivery_refs: V2-W0704, V2-W0705, V2-W0707
parent_work_item: none
depends_on: WI-045
execution_scope: production
production_effects: bounded_remote_connector_and_scheduler_cutover
architecture_impact: changes the production MCP and Scheduler SSOT
data_impact: V2 writers become primary while V1 remains paused for rollback
security_impact: OAuth scopes and production identities switch to V2
cost_impact: actual production configuration remains within approved envelope
---

# WI-046 — Cut production connectors and schedules over to Remote MCP V2

## Problem and evidence

Passing dual-run evidence must be converted into one bounded, reversible production cutover.

## Classification and contract

- `architecture` cutover requiring explicit owner approval at the execution gate.
- The owner approved starting the transition after accepting the 2026-09-11 14:30 observation and the immutable
  WI-045 manifest. Production mutations must run from tested `master` through the protected GitHub Actions path.
- Preserve the pre-cutover Remote MCP revision and V1 schedule definitions for at least a seven-day rollback window.
  Do not delete V1 services, jobs, schedules, data, secrets or revisions in this Work Item.

## Scope

- Include connector refresh, V2 Scheduler activation, V1 pause, approval record and rollback window.
- Exclude V1 deletion and final retirement.

## Acceptance criteria

- [x] owner approves immutable manifest and rollback window.
- [ ] Remote MCP/iPhone and scheduled runs pass production smoke.
- [ ] rollback to V1 revision and schedules is rehearsed.

## Change impact

- Production SSOT switch; preservation-first and reversible.

## Plan

1. Stage additive schema/state copy and no-traffic candidates. 2. Run live-client smoke. 3. Promote auth then Remote
traffic with rollback holds. 4. Observe and close the rollback window.

## Sub-items

- `WI-046-S01` — correct the Claude `resource=None` OAuth interoperability failure while retaining strict
  canonical resource binding.
- `WI-046-S02` — correct the production-read `pass`/`passed` status mismatch and make the managed collection
  command's returned logical run handle resolve both new and previously scheduled idempotent runs.
- `WI-046-S03` — restore the verified server-side owner identity as the standard access-token subject so Remote
  commands retain the owner-authority boundary used by the approved contract.
- `WI-046-S04` — restore the approved fixed-Job command boundary: reuse an existing logical run without dispatch,
  invoke only the current KST date through the slot-specific immutable Job definition, and never request container
  overrides from Remote.

## Evidence

- 2026-09-11 activation: WI-045 closed on PR #77/master `6245238` with a passing ten-date readiness assessment,
  private exact-hash restore, current cost pass and target-specific immutable rollback digests. The owner explicitly
  instructed the project to stop further MS-002 observation and begin transition.
- Execution order remains fail closed: merge the protected release implementation, apply additive migrations,
  deploy/smoke inactive V2 targets, refresh production connectors, switch schedules, then observe. Any failed gate
  restores the recorded V1 revision/schedules while preserving V2 data.
- Production inspection found auth `00021` and remote `00031` serving V1 at 100% traffic with MotherDuck OAuth state
  and the default Compute identity. The staged target therefore recopies active state to Firestore, uses dedicated
  auth/remote identities and leaves serving traffic untouched.
- The production V2 owned-core schedules at 10:00, 14:30 and 16:00 are already enabled and healthy. Domestic and
  overseas order-history plus token warm-up schedules remain required feeders, not duplicate V1 schedules, so the
  no-traffic stage does not pause or recreate any Scheduler resource.
- Repository production adapters now cover the exact 15 governed reads, three managed commands and append-only
  owner revisions through migration `0018`. Unsupported cursor/grain/account projections fail closed; account-filtered
  totals are calculated within the selected alias rather than returning a global total.
- Protected `wi046-stage` builds one immutable image, applies `0018`, recopies active state, uses only pre-provisioned
  Firestore/secret/fixed-Job permissions, deploys `wi046-auth`/`wi046-v2` no-traffic tags and checks
  health/discovery/unauthenticated rejection. Local dry-run and 98 focused tests passed.
- Protected run `34615723372` stopped before Cloud authentication because deployment vars leaked into pytest
  collection; PR #79/master `52de475` isolated the test runtime and 646 full tests passed. Retry `34616445622` built
  immutable image `sha256:546fa373...6a371`, then stopped at `iam.serviceAccounts.create` because the deliberately
  non-admin GitHub deployer cannot bootstrap identities. No migration, state copy, service revision, traffic or
  Scheduler mutation occurred.
- On 2026-09-12 the owner explicitly approved and applied the two exact minimum identities. Project-level inspection
  found only `roles/datastore.user` on each identity; all 26 secret policies found exactly the six approved auth
  secrets and the two approved Remote secrets; all 14 Cloud Run Job policies found Remote `roles/run.invoker` only on
  the 10:00, 14:30 and 16:00 owned-core jobs. Each new identity grants the GitHub deployer only service-account user;
  the deployer remains non-admin.
- Protected run `34621191176` built master `d534c3f` as immutable image `sha256:ce9ff2a0...02a1a`, applied migrations
  `0014` through `0018`, and copied active operational state to Firestore with exact source/verified counts:
  auth users 1, identities 1, clients 6, grants 5, codes 0, OAuth tokens 1 and KIS token-cache records 5. It then
  created auth `00022` and Remote `00032` at zero traffic, but failed closed while resolving tagged URLs because the
  gcloud projection did not match the returned traffic JSON. V1 stayed at 100% and no Scheduler changed.
- PR #81/master `d805739` replaced the projection with exact traffic-JSON parsing. PR #82/master `9f1f9aa` added a
  protected candidate-only resume path that emits no migration or state-copy Job command; full verification passed
  with 649 tests.
- Owner-approved protected run `34623252239` used that candidate-only path. It built immutable image
  `sha256:e0b655a8...7397`, deployed auth `00023` and final Remote `00034` under their dedicated identities, added the
  exact tagged Remote host to the transport allowlist, and passed health, OAuth protected-resource discovery and
  unauthenticated `/mcp` rejection smoke. Auth/Remote V1 revisions `00021`/`00031` still receive 100% traffic and both
  candidates receive 0%. All six existing Scheduler jobs remain enabled at their unchanged schedules.
- `WI-046-S01` diagnosis on 2026-09-12: Claude completed DCR, owner login, consent and token exchange, but every
  candidate `/mcp` call returned 401. Redacted Firestore inspection found 136 of 138 token digest documents bound
  to the literal `None` sentinel shown on the consent screen; Auth and Remote otherwise used the same database,
  sole pepper secret version and canonical URL. The resource server therefore rejected those digests before MCP
  dispatch. The correction binds omitted/`None` resource indicators to the canonical Remote URL, rejects other
  explicit targets at authorization, and rejects unbound access tokens at Remote verification. Existing digest
  records are preserved and naturally replaced on connector reauthorization. Focused auth/Remote/deploy regression
  passed 83 tests and the full gate passed 658 tests. The later protected candidate and live Claude reauthorization
  satisfied the transport portion of this verified sub-item; stable traffic remains a parent WI-046 gate.
- PR #87/master `3352e14` deployed corrected auth `00027-wed` and Remote `00036-tej` from immutable image
  `sha256:b3b620...85ad43`; protected auth promotion retained `00025-juq` as the exact rollback revision. The owner
  re-created the Claude connector under the canonical display name `KIS Portfolio`. The resulting production flow
  recorded DCR 201, authorize/consent 302, token 200 and two authenticated tagged Remote `/mcp` 200 responses. The
  later consent 400 was a duplicate submission after the one-time request had already completed, not the primary
  authorization outcome. Literal-None resource interoperability and actual Claude bearer use are therefore verified.
- The remaining Remote traffic switch is implemented as a separate protected `wi046-promote-remote` target. It
  requires exact rollback `00031-pbm` and tagged candidate `00036-tej`, changes only Remote traffic, verifies the
  stable health/discovery/unauthenticated boundary, and immediately restores the exact rollback revision on failure.
  Scheduler, Job, DB, Auth, secret and connector mutations are outside that promotion command.
- PR #88/master `918800b` added that Remote-only promotion gate after 59 focused and 661 full tests. Protected run
  `34694232734` then promoted `kis-portfolio-remote-00036-tej` to 100% stable traffic and passed its post-switch
  verification; exact rollback remains `kis-portfolio-remote-00031-pbm`. Independent inspection confirmed auth
  `00027-wed` still at 100%, all six Scheduler jobs enabled with unchanged schedules, stable health 200, canonical
  protected-resource metadata and unauthenticated stable `/mcp` 401. No DB, Job, Scheduler, secret, IAM or cleanup
  mutation occurred in this traffic step.
- Claude's first representative read session against Remote `00036-tej` returned real portfolio, performance,
  ledger, catalog and quality data, while matching tagged `/mcp` requests returned HTTP 200. It also exposed two
  command-smoke blockers now tracked by `WI-046-S02`: the overview compared stored `pass` rows with the nonexistent
  `passed` success token, and a command-generated run ID could not find an older scheduler run reused by the
  pipeline's logical idempotency key. Collection remains untested until these bounded corrections are deployed.
- `WI-046-S02` now uses the canonical stored `pass` value in the overview summary and exposes the pipeline logical
  idempotency key as the command's pollable run handle. `get-pipeline-run` resolves that handle against either a new
  run ID or an older scheduler run's idempotency key, preserving reuse without an unqueryable response. Focused
  Remote command/read/pipeline regression passed 40 tests, quick passed and full passed 662 tests with the existing
  single Authlib deprecation warning. No production command, DB write, Job, Scheduler, IAM, secret or traffic change
  occurred in this repository-only correction.
- First Claude managed-command smoke at 2026-09-12 23:17 KST reached Remote `00039-vub`, but failed before command
  state claim or Job enqueue with `invalid_actor`. The opaque access-token record retained the authenticated owner
  `user_id`, while its MCP `AccessToken.subject` projection was left empty. Reads had masked this through their
  client fallback; commands correctly refused to weaken owner authority. `WI-046-S03` restores that server-verified
  identity during authorization-code, refresh-token and access-token loading without trusting a client-supplied
  subject or changing scopes.
- `WI-046-S03` restores `subject` from the immutable server-side `user_id` whenever stored authorization codes,
  refresh tokens and access tokens are loaded. Focused OAuth/Remote command regression passed 34 tests and full
  passed 662 tests with the existing Authlib warning. The failed Claude call created no command claim, run request
  or Job execution, so its original idempotency key remains safe for one post-deployment retry.
- The second Claude retry reached corrected Remote `00042-pon` at 2026-09-13 01:16 KST and passed owner/scope
  authorization, but the Cloud Run Admin API rejected Job enqueue with `managed_job_enqueue_failed:403`. The Remote
  identity had the intended resource-scoped `roles/run.invoker`; the adapter nevertheless sent container argument
  overrides, which require `run.jobs.runWithOverrides` and contradicted the approved fixed-args/no-override trust
  boundary. The request released its transient command claim, persisted no command response, and started no Job.
  `WI-046-S04` corrects the adapter rather than widening IAM.
- `WI-046-S04` reads the warehouse logical idempotency key before dispatch: an existing `running` or `succeeded`
  run returns `reused` without a Cloud Run API call. A missing historical date fails closed because historical
  backfill requires the separately governed queue; only the current KST date may invoke its slot-specific Job, with
  an empty request body so the deployed fixed command/args remain authoritative. Production read-only evidence found
  the 2026-09-11 `kr-1600` logical run in `succeeded` state, backed by execution `...-9dbp6` completed at 16:04:49 KST.
  Focused owner/auth/command/adapter regression passed 30 tests; quick and full passed with 667 tests and the existing
  Authlib warning. No IAM, Job definition, Scheduler, DB row, secret, connector or traffic changed.

## Closeout

- Result: in progress.
- Remaining risk: rebind the canonical-name Claude connector from the temporary tagged URL to the stable URL, then
  capture stable-URL representative read/command and iPhone evidence. Protected Remote promotion, least-privilege IAM
  and live Claude OAuth/MCP transport are complete; exact V1 rollback is retained and retirement remains MS-004.
- Follow-up Work Item: WI-047.
