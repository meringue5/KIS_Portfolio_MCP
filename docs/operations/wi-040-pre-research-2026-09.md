# WI-040 catalog and quality read-model pre-research — 2026-09-01

> Work Item: `WI-040-S01`
> 범위: repository와 live aggregate metadata read-only research
> 변경 경계: contract lifecycle, DDL, DB write, public MCP, deployment와 source call 없음

## 결론

WI-040은 새 governance engine을 만드는 작업이 아니다. repository manifest와 V2 Control evidence를 하나의
안전한 consumer contract로 합치는 작업이다. 현재 기반은 존재하지만 production consumer에 그대로 노출할
수준은 아니다.

- `GovernanceReadModel.catalog()`는 repository TOML을 직접 읽으며 sources, datasets, collections와 pipelines를
  반환하지만 승인된 metrics 28개를 누락한다.
- 기본 lifecycle filter는 proposed를 숨기지만 sensitivity/consumer scope filter가 없다. 따라서 승인된
  restricted owner-document source와 dataset metadata도 일반 catalog 결과에 포함된다.
- `quality(run_id)`는 `details` JSON과 observed/expected 값을 allowlist나 길이 제한 없이 반환한다.
- `pipeline_run_summary`는 run/stage count만 집계한다. required quality, freshness, watermark, missing partition과
  lineage 상태를 결합하지 않으므로 succeeded run을 consumer-green으로 오인할 수 있다.
- Control의 pipeline run/stage, quality, lineage, watermark와 summary view는 physical catalog에 있으나 대응하는
  DGH dataset contract가 없다. DGH의 physical/logical cross-link 원칙상 formal implementation 전 보강이 필요하다.
- 운영 MotherDuck inventory는 두 번 모두 session creation RPC `UNAVAILABLE`로 실패했다. 이 상황에서 cached
  success나 빈 결과를 반환하지 않고 `unavailable`로 표현하는 것이 read-model acceptance의 일부여야 한다.

따라서 parent WI-040 구현 전 DTO, sensitivity projection과 overall-status composition을 먼저 고정해야 한다.
이번 조사에서는 manifest, schema, DB 또는 MCP surface를 변경하지 않았다.

## 현재 재사용 가능한 기반

| Area | Existing input | Gap before implementation |
| --- | --- | --- |
| canonical catalog | DGH TOML manifests and deterministic checker | metric kind missing from reader; no release/schema version or consumer projection |
| pipeline run | `control.pipeline_runs`, `pipeline_stage_runs` | latest/list query, expected-stage comparison, resume state and bounded pagination absent |
| quality | `control.quality_results` | arbitrary detail projection; no dataset-level overall result or freshness/gap composition |
| lineage | `control.lineage_edges` | raw refs only; no stable opaque lineage reference or sensitivity boundary |
| watermark | `control.watermarks` | not joined to status; no freshness/contiguity interpretation |
| physical read view | `control.pipeline_run_summary` | run success can be reported without required quality and watermark evidence |
| application model | `src/kis_portfolio/platform/read_models.py` | raw dicts, no DTO/envelope/auth policy/error taxonomy |
| tests | basic success-path assertions in V2 pipeline/rehearsal tests | failed/partial/stale/restricted/unavailable and bounded-query tests absent |

The DGH registry currently contains 18 sources, 7 collections, 29 datasets, 28 metrics and 14 pipelines. Approved
records include one restricted source and two restricted datasets for owner-provided research documents. Their payload
must never be exposed merely because their contract is approved.

## Required consumer contracts

### Catalog projection

The repository manifests remain the decision SSOT. A DB snapshot, if introduced for DB-local serving, is a derived
release artifact with manifest hash and must not become a competing authority.

Recommended catalog item fields are kind, ID, version, lifecycle status, owner, short purpose, supported scope, grain,
layer, time semantics, freshness SLO, quality-rule identifiers, sensitivity class and contract hash. Authentication,
credential location, raw source URL, restricted description, internal cost detail and arbitrary manifest fields are not
pass-through fields. Default results include approved/active only; proposed requires an explicit owner-only diagnostic
option and remains unsupported for official analysis.

The catalog must cover source, dataset, metric and pipeline as required by DGH. Collection can be a separate owner-only
planning view rather than silently replacing metrics in the main catalog.

### Quality projection

One response must state dataset/run/partition/slot, evaluated time, overall status, freshness, completeness,
reconciliation, missing coverage and an opaque lineage reference. Rule IDs and normalized status are allowed;
`details`, observed and expected values require per-rule typed projections and bounded strings. Unknown rule payloads
are suppressed, not serialized.

Overall status is green only when all of these hold:

1. the logical run is terminal succeeded;
2. every required stage succeeded exactly once;
3. every required dataset quality rule passed;
4. expected partitions and market slots are present;
5. required watermarks are fresh, contiguous and attributable to the same or a later accepted run;
6. no restricted/sensitive projection violation occurred.

Missing evidence maps to `unknown` or `not_assessed`; partial coverage to `partial`; expired freshness to `stale`; an
explicit failure to `failed`; DB/session failure to `unavailable`. None may be rendered as an empty green result.

### Pipeline and lineage projection

Pipeline status needs latest and exact-run queries with bounded page size, stable ordering and opaque continuation. It
must include definition/run version, logical date, slot, partition, source-call count versus budget, stage summary,
first failed or resumable stage, freshness state, quality aggregate, watermarks and retry/resume eligibility. Error
codes may be allowlisted; raw exception text is excluded.

Lineage output exposes stable input/output dataset IDs, transform ID/version, evidence hash reference and timestamps.
Raw object URIs, account or instrument identifiers and restricted document locators remain behind authorized
dataset-specific views.

## Contract hardening gate

Formal WI-040 should resolve these items before implementation:

1. Register governed logical datasets for pipeline-run/stage evidence, quality evidence, lineage evidence and
   watermark state, or approve a justified grouping whose grain and natural keys remain explicit.
2. Decide whether `DB-only` means no upstream network calls with packaged manifest SSOT, or requires a derived Control
   catalog snapshot. The latter needs a dataset contract, migration and manifest-hash reconciliation.
3. Freeze versioned DTOs and a common envelope containing schema version, as-of, freshness, quality, missing coverage,
   lineage reference and request ID.
4. Define consumer scopes for public/internal/confidential/restricted metadata. Restricted payload access is never
   inherited from catalog visibility.
5. Replace arbitrary JSON pass-through with typed rule projections and length/value-class guards.
6. Define deterministic status precedence and expected-stage/partition inputs so partial and failed runs cannot appear
   green.
7. Define bounded latest/history queries and unavailable/error behavior before WI-042 registers public MCP tools.

These are compatible implementation inputs if they preserve manifest SSOT and existing Control grains. A new catalog
SSOT, changed natural key, relaxed sensitivity or public arbitrary SQL would reopen the ADR gate.

## Suggested implementation sequence

1. Approve the missing Control dataset contracts and DB-only interpretation.
2. Add DTOs, sensitivity field allowlists and normalized status/error enums without public MCP registration.
3. Add repository queries for latest/list/exact run, required-stage aggregation, quality/freshness/gap composition and
   opaque lineage references.
4. Add fail-closed tests for proposed/restricted contracts, arbitrary quality details, partial stages, failed quality,
   stale/missing watermarks, missing partitions, DB unavailable and pagination bounds.
5. Verify local migration/rehearsal and live read-only inventory; a repeated live `UNAVAILABLE` remains explicit
   operational evidence rather than a reason to weaken the gate.
6. Hand the stable service/DTO contract to WI-042 for Remote MCP registration and client compatibility tests.

## Limits of this research

- MotherDuck live inventory did not complete: both attempts failed while creating the session with provider status
  `UNAVAILABLE`. No live row count, freshness or drift claim is made.
- No DB row, manifest lifecycle, contract version, schema, service or MCP tool was changed.
- No restricted payload, account identifier, source credential or raw quality detail was read.
- Current repository behavior may change before formal implementation; re-run inventory and contract comparison at
  WI-040 start.

`WI-040-S01` is closed as implementation input. Parent `WI-040` remains `proposed`, and MS-003 remains gated by
MS-002 operational acceptance.
