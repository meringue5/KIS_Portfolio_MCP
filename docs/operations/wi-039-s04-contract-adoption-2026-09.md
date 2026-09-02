# WI-039-S04 macro contract adoption — 2026-09-02

> Work Item: `WI-039-S04`
> 상태: closed canonical adoption
> 변경 분류: architecture, requirements clarification and data-governance contract adoption
> 승인 근거: owner approved WI-039-S04 after reviewing the complete S02 package and S03 exact ECOS identities
> 제외: adapter, DDL, DB write, credential, infrastructure, source call, backfill, schedule, deployment, MCP activation

## Result

ADR-027 and the approved macro package are now canonical. `macro_profile_v1` contains exactly 17 series: five ECOS
identities verified in S03 and twelve FRED/ALFRED identities verified in S01/S02. Every series contract has lifecycle
`approved` and `activation_state = inactive`; no contract authorizes a production call or consumer.

The Data Governance Harness now recognizes `macro_series` as a first-class contract kind and rejects duplicate provider
identity, an undeclared source in a collection or pipeline, and a production series whose lifecycle or source is not
active. Runtime implementation remains a later WI-039 sub-item after the MS-003 implementation gate.

## Canonical delta

| Contract area | Adopted delta |
| --- | --- |
| ADR and requirements | ADR-027, Package C and platform-requirements clarification |
| DGH schema | new `macro_series` type and exact-series cross-references |
| new contracts | 17 macro series, 1 Gold macro profile snapshot and 5 transparent metrics |
| version upgrades | FRED/ALFRED 1.1, dormant Cboe reference 1.1, macro collection 2.0, observation dataset 2.0 and pipeline 2.0 |
| exact ECOS | `722Y001/D/0101000`, `731Y001/D/0000001`, `901Y009/M/0`, `901Y033/M/A00/2`, `901Y118/M/T002` |
| exact FRED | `DFF`, `DGS2`, `DGS10`, `T10Y2Y`, `CPIAUCSL`, `CPILFESL`, `UNRATE`, `PAYEMS`, `GDPC1`, `DTWEXBGS`, `DCOILWTICO`, `VIXCLS` |
| transport | ECOS plus FRED/ALFRED; direct Cboe calls remain zero |
| metrics | YoY, period delta, quarterly annualized growth, yield-curve state and VIX regime |
| registry total | 152 governed contracts, up from 129 |

The 23-contract increase is 17 exact series plus one Gold snapshot and five metrics. Existing source, collection,
observation and pipeline contracts were versioned in place and therefore do not increase the registry count.

## Revision, rights and activation boundary

- FRED/ALFRED observations use `provider-vintage`; ECOS uses `observed-content` and nullable provider realtime fields.
- Operational replay defaults to monotonic `system_as_of`; initial historical collection is labeled
  `retrospective_reconstructed` and does not acquire fictional past system knowledge.
- VIXCLS remains Cboe-owned, copyrighted, citation-required and owner-private. Telegram may later receive only an
  separately approved attributed regime context, never bulk raw history.
- All source calls, secrets, Scheduler configuration, migration 0016, DB objects, backfill and Remote MCP exposure remain
  inactive and require later implementation/release approval.
- Filing, dividend and macro retain separate logical identities while sharing the modular-monolith image, runner,
  HTTP policy, MotherDuck/GCS foundation and release artifact. No separate service, repository or always-on worker was
  introduced.

## Verification

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: passed, 152 registered contracts
- `uv run pytest tests/test_data_governance_contract.py -q`: passed, 7 tests
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: passed, 440 tests and one existing Authlib deprecation warning
