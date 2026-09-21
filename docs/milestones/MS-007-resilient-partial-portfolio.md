# MS-007 — Resilient partial portfolio usability

> 상태: in_progress (isolated design only)
> 선행 milestone: MS-005 closed; MS-006 is discovery context, not a prerequisite
> machine registry: `governance/project/milestones.toml`

## Outcome

Keep exact complete totals fail-closed while making independently verified current holdings, native-currency
facts and scoped KRW subsets useful when comparison history, FX or optional analysis is missing.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-060 capability-isolated portfolio usability | none; discovered from WI-059 | in_progress, isolated design |

## Gates

- Implementation: MS-005 closed; WI-060 is currently isolated with no production effects.
- Production: MS-005 closed and separately approved DEC/ADR/data contracts. Do not wait for unrelated MS-006
  owner acceptance, which itself needs this usability correction.
- Exit: deterministic failure matrix, corrected read-model semantics, real Claude and Telegram user review,
  redacted quality/lineage evidence and owner acceptance. No single scheduled slot is the only test.
- Release unit: one protected WI-060 candidate after all approved in-scope changes pass synthetic and no-send
  preflight checks; verify the same immutable image on Remote MCP and report Job. Unapproved secondary FX source
  activation cannot be represented as completed or slipped into that release.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-17.1 | 2026-09-17 | Owner rejected all-or-nothing failures and requested a resilient but accurate architecture review | New MS-007/WI-060 discovered from but not blocked by MS-006; preserves recovery and release evidence |
| 2026-09-17.2 | 2026-09-17 | Owner requested fixing the in-scope failures before one production deployment | Consolidated release gate; implementation remains isolated until approval and verification |
