# MS-005 — Production feedback and Remote MCP usability corrections

> 상태: stabilizing
> 선행 milestone: MS-004
> machine registry: `governance/project/milestones.toml`

## Outcome

완료된 V2 기준선을 되감지 않고 실제 Claude 사용에서 발견된 public identifier, availability semantics와
read-model 결함을 append-only corrective Work Item으로 교정한다.

## Baseline

| Sequence | Work Item | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- |
| 1 | WI-058 Remote MCP identifier and coverage correction | WI-051 | stabilizing; WI-058-S01 deployed and transport-verified, owner Claude acceptance pending |

## Gates

- implementation gate: MS-004 closed.
- production gate: MS-004 closed, but each production release still requires its normal protected workflow and owner
  authorization.
- acceptance: exact real-Claude inputs are regression-tested locally, then one canonical stable-URL Claude session
  confirms market, quality, pipeline-run and direct-exposure behavior after release.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-15.5 | 2026-09-15 | Deployed revision 00047, verified exact tagged Host at 0% and 100%, and retained owner-read stabilization | No identity change; release evidence appended |
| 2026-09-15.4 | 2026-09-15 | Opened WI-058-S01 after structured logs proved exact compatibility-tag Host rejection with HTTP 421 | Same WI outcome; append-only corrective sub-item |
| 2026-09-15.3 | 2026-09-15 | Released Remote revision 00046 and V2 core Jobs; entered owner-read stabilization | No identity change; release evidence appended |
| 2026-09-15.2 | 2026-09-15 | Owner approved protected Remote MCP and owned-core Job deployment | No identity change; production gate already satisfied by closed MS-004 |
| 2026-09-15.1 | 2026-09-15 | Opened corrective milestone and WI-058 from real Claude usage | New append-only milestone and Work Item; MS-003/MS-004 history remains closed |
