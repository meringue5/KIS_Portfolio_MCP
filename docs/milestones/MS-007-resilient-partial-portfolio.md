# MS-007 — Resilient partial portfolio usability

> 상태: stabilizing (protected production release complete; real-use acceptance pending)
> 선행 milestone: MS-005 closed; MS-006 is discovery context, not a prerequisite
> machine registry: `governance/project/milestones.toml`

## Outcome

Keep exact complete totals fail-closed while making independently verified current holdings, native-currency
facts and scoped KRW subsets useful when comparison history, FX or optional analysis is missing.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-060 capability-isolated portfolio usability | none; discovered from WI-059 | stabilizing; production active, owner acceptance pending |

## Gates

- Implementation: MS-005 closed; WI-060 has approved capability-isolated and external-FX contracts and the owner
  authorized the protected production release after providing the external-source credential.
- Production: MS-005 closed and separately approved DEC/ADR/data contracts. Do not wait for unrelated MS-006
  owner acceptance, which itself needs this usability correction.
- Exit: deterministic failure matrix, corrected read-model semantics, real Claude and Telegram user review,
  redacted quality/lineage evidence and owner acceptance. No single scheduled slot is the only test.
- Release unit: one protected WI-060 candidate after all approved in-scope changes pass synthetic and no-send
  preflight checks; verify the same immutable image on Remote MCP and report Job. Unapproved secondary FX source
  activation cannot be represented as completed or slipped into that release. The approved source must pass its
  read-only live preflight after Job staging and before Remote traffic promotion.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-17.1 | 2026-09-17 | Owner rejected all-or-nothing failures and requested a resilient but accurate architecture review | New MS-007/WI-060 discovered from but not blocked by MS-006; preserves recovery and release evidence |
| 2026-09-17.2 | 2026-09-17 | Owner requested fixing the in-scope failures before one production deployment | Consolidated release gate; implementation remains isolated until approval and verification |
| 2026-09-22.1 | 2026-09-22 | Owner provisioned the approved external FX credential; guarded fallback implementation and immediate fault cases completed | Production remains pending until full gate and protected live source preflight |
| 2026-09-22.2 | 2026-09-22 | Protected run exposed same-day publication-time coupling and a disabled rollback prerequisite; exact prior Job exports were restored | WI-060-S01 closed; WI-060-S02 appended for latest-governed source validation and pre-mutation rollback readiness |
| 2026-09-22.3 | 2026-09-22 | Pre-mutation run `35741804406` exposed canonical gcloud service-resource output instead of the mocked short name | No production mutation; WI-060-S02 fixture corrected to the real provider output shape |
| 2026-09-22.4 | 2026-09-22 | PR #124 and protected run `35742953730` activated one immutable WI-060 image after clock-independent source preflight | MS-007/WI-060 move to stabilizing; real Claude output and owner-visible report acceptance remain exit gates |
| 2026-09-23.1 | 2026-09-23 | Real Codex DCR reproduced an IPv4 loopback callback rejection before owner login | Append WI-060-S03; preserve owner-only OAuth and admit only structurally validated loopback callbacks before direct-client acceptance |
| 2026-09-23.2 | 2026-09-23 | Protected auth run `35751002463` changed service labels but reused the old ready revision/image | Keep WI-060-S03 open; force a per-run runtime-template marker and require revision-level evidence before login |
