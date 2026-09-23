# MS-008 — Real-use MCP acceptance and capability remediation

> 상태: in_progress
> 선행 milestone: MS-005 closed
> machine registry: `governance/project/milestones.toml`

## Outcome

User-visible functionality is not called complete merely because code, CI or deployment passed. The actual OAuth
Remote MCP client must execute deterministic positive, partial and error scenarios, and defects or honest capability
gaps found there must be classified and routed to an owned follow-up.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-061 real-use completion gate | none | closed |
| 2 | WI-062 direct Remote MCP remediation | WI-061 | stabilizing |
| 3 | WI-063 incremental trade-event collection | WI-062 | proposed |

## Gates

- Implementation and production gates depend on closed MS-005, the canonical V2 production baseline.
- WI-061 changes Project OS policy, template and deterministic checker, then dogfoods the rule on WI-062.
- WI-062 separates actual defects from accurate degraded results and inactive capability scope. No source activation,
  backfill or public-catalog removal is implied by registering the Work Item.
- WI-063 owns the newly proven contract/implementation gap: the recurring core pipeline declares trade-event output
  but does not increment the trade ledger or its source coverage watermark after the one-time backfill.
- Completion requires immediate reproducible client calls; waiting for a future scheduler slot cannot be the only
  acceptance method.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-23.1 | 2026-09-23 | Direct Codex calls showed that deployed tools can be healthy, degraded, empty or response-contract defective despite green CI | Create MS-008, WI-061 and WI-062 without changing earlier milestone identities |
| 2026-09-23.2 | 2026-09-23 | WI-061 checker regression and full 783-test gate passed; WI-062 declares the new real-use fields | Close WI-061 and start WI-062 as the sole implementation Work Item |
| 2026-09-23.3 | 2026-09-23 | Production rows ended 2026-08-25 and backfill watermark ended 2026-08-28 while current core runs omit trade collection | Register WI-063; keep WI-062 response correction active and do not claim September no-trade coverage |
