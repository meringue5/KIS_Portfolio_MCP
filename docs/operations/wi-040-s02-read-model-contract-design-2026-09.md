# WI-040-S02 catalog, quality and pipeline read-model contract design — 2026-09-02

> Work Item: `WI-040-S02`
> 상태: owner approved; canonical adoption tracked by `WI-040-S03`
> 변경 분류: data-contract and consumer-boundary clarification
> 범위: WI-040-S01 evidence, current DGH manifests, V2 Control objects and approved Remote MCP V2 boundary
> 제외: contract adoption, DTO/query implementation, DDL, DB write, public MCP registration, deployment, live query

## 결론

`DB-only`는 **요청 중 KIS·ECOS·FRED 등 upstream network call을 하지 않는다**는 뜻으로 고정한다. catalog의
결정 SSOT는 container image에 함께 배포된 `governance/catalog/`와 `db/catalog.py`이며, MotherDuck Control은
run/stage/quality/lineage/watermark의 운영 증거만 제공한다. manifest를 Control table에 다시 복제해 두 번째
catalog SSOT를 만들지 않는다.

WI-040은 public MCP tool을 등록하지 않는다. 세 개의 versioned application read model
`catalog.v1`, `data-quality.v1`, `pipeline-run.v1`을 만들고, WI-042가 이를 각각 `get-data-catalog`,
`get-data-quality`, `get-pipeline-run`에 얇게 연결한다. 기존 문서에 혼재한 `get-pipeline-status`는 새 tool로
추가하지 않고 `pipeline-run.v1`의 내부 의미로만 흡수해 승인된 18-tool budget을 유지한다.

현재 `GovernanceReadModel`의 raw dict/JSON pass-through와 `pipeline_run_summary.status=succeeded`는 공식 green의
근거가 아니다. 새 read model은 typed DTO, sensitivity projection, required-evidence composition과 fail-closed
error taxonomy를 적용한다. 기존 class와 view는 구현 전까지 compatibility foundation이며 조용히 의미를
확장하지 않는다.

## 현재 근거와 변경 경계

- DGH registry는 152 contracts: source 19, collection 10, dataset 38, metric 33, pipeline 17,
  macro series 17, ETF profile 4, ETF route 14다.
- packaged reader는 source/dataset/collection/pipeline만 반환해 metric, macro series와 physical object가 빠진다.
- Control에는 `pipeline_runs`, `pipeline_stage_runs`, `quality_results`, `lineage_edges`, `watermarks`와
  `pipeline_run_summary`가 있고 physical catalog·Parquet backup 대상이지만 대응 logical dataset contract가 없다.
- `quality.details`, observed/expected value, stage evidence, raw error message, partition/input/output ref에는
  account·instrument·restricted object locator가 들어갈 수 있으므로 generic serialization을 금지한다.
- 이번 설계는 현재 physical grain과 SSOT를 보존하므로 새 ADR은 필요하지 않다. DB catalog snapshot,
  arbitrary SQL, sensitivity 완화, public tool 추가가 제안되면 architecture gate를 다시 연다.

## 권한과 데이터 흐름

```text
packaged canonical manifests + db/catalog.py
                 │
                 ├── catalog.v1 ───────────────┐
                 │                             │
MotherDuck control evidence                    ├── WI-042 thin MCP handlers
  ├── run/stage                                │   mcp:read only
  ├── quality                                  │
  ├── lineage                                  │
  └── watermark ── quality/pipeline-run.v1 ────┘
```

- Catalog request는 filesystem에 포함된 reviewed artifact만 읽고 DB나 provider availability를 성공 조건으로
  만들지 않는다.
- Quality와 pipeline request는 MotherDuck Control이 unavailable이면 `unavailable`이며 빈 목록이나 마지막
  cached success로 대체하지 않는다.
- Direct SQL, arbitrary file path, raw manifest field selection, caller-supplied table/view와 unbounded date range는
  어떤 DTO에도 없다.
- WI-040 application layer는 consumer policy를 요구하지만 OAuth token을 직접 해석하지 않는다. WI-042 adapter가
  검증한 `mcp:read` actor/scope를 전달하며, restricted payload permission은 그 scope에서 파생되지 않는다.

## 제안 DGH delta

Owner approval 뒤 별도 `WI-040-S03`에서 다음 계약을 canonical `approved`로 채택하되 모두 runtime inactive로
둔다. S03도 DDL이나 implementation을 하지 않는다.

### Control evidence datasets

| Contract | Physical object | Grain / natural key | 핵심 계약 |
| --- | --- | --- | --- |
| `dataset.pipeline-run-evidence` 1.0 | `control.pipeline_runs` | one logical run / `run_id`; `idempotency_key` unique | logical date, slot, opaque partition, definition version, terminal state, source calls, safe error code |
| `dataset.pipeline-stage-evidence` 1.0 | `control.pipeline_stage_runs` | one run and stage / `run_id, stage_name` | stage order, attempt, counts, calls and terminal state; evidence/error text restricted |
| `dataset.data-quality-evidence` 1.0 | `control.quality_results` | one rule evaluation / `quality_result_id` | run, dataset, rule, typed status and evaluated time; arbitrary values/details are not consumer fields |
| `dataset.data-lineage-evidence` 1.0 | `control.lineage_edges` | one run edge / `lineage_edge_id` | transform/version and evidence hash; raw refs stay internal |
| `dataset.pipeline-watermark-state` 1.0 | `control.watermarks` | one pipeline/partition/type | current accepted monotonic watermark and producing run |
| `dataset.pipeline-run-summary-compat` 1.0 | `control.pipeline_run_summary` | one run / `run_id` | compatibility run/stage count only; never official overall quality |

The first dataset is runtime-generated Control evidence rather than an external source dataset. DGH therefore needs a
backward-compatible optional `control_origin` field and checker rule: only `layer=control` may omit source/input when a
non-empty allowlisted origin such as `managed-pipeline-runtime` is present. Other five datasets reference the run
evidence or its derived inputs. This exception does not authorize arbitrary source-less analytics datasets.

No collection contract is added. Operational evidence is a mandatory side effect of every managed pipeline rather than
a separately scheduled data basket. No new physical object is proposed; existing object catalog and backup policy stay
unchanged.

### Read-model contracts

Add a DGH `read_model` kind with three `approved + inactive` definitions:

| Contract | Inputs | Activation boundary |
| --- | --- | --- |
| `read_model.data-catalog-v1` | packaged source/dataset/metric/pipeline/macro-series manifests and physical object registry | application service only; public MCP belongs to WI-042 |
| `read_model.data-quality-v1` | quality, run/stage, watermark and lineage evidence | DB-only bounded query; no raw details |
| `read_model.pipeline-run-v1` | run/stage, quality, watermark and lineage evidence plus packaged pipeline contract | exact/list queries; no Job trigger |

Required fields are `input_dataset_ids`, `consumer_scope`, `response_schema_ref`, `allowed_fields`,
`suppressed_fields`, `query_policy`, `status_policy`, `unavailable_policy` and `activation_state`. Checker rejects a
production read model that is not `active`, references non-active inputs, lacks bounded query policy or exposes a field
listed as suppressed.

## Common response envelope v1

All three DTOs use the approved envelope without copying source payloads:

| Field | Contract |
| --- | --- |
| `schema_version` | exact response contract version; initially `1.0.0` |
| `as_of` | UTC query/evaluation cutoff, never silently current wall clock for historical requests |
| `source` | `packaged-governance` or `motherduck-control`; contract/definition hash and availability only |
| `freshness` | typed status, evaluated time and safe reason code; prose SLO is not parsed as executable policy |
| `quality` | overall status and allowlisted reason codes; no arbitrary `details` JSON |
| `missing_coverage` | bounded typed gap count/list with opaque refs; empty means proven none, not evidence absent |
| `lineage_ref` | `lineage:v1:<sha256>` over canonical safe edge projection; raw input/output refs excluded |
| `request_id` | server-generated opaque ID for logs and diagnostics |
| `data` | read-model-specific typed payload |

Serialized response ceiling is 256 KiB. All free text is either a packaged reviewed catalog string or an allowlisted
reason message capped at 256 UTF-8 characters. Unknown DB JSON/string fields are suppressed and add
`suppressed_detail=true`; they are never forwarded optimistically.

## Catalog DTO v1

Initial kinds are `source`, `dataset`, `metric`, `pipeline`, `macro_series` and physical `object`. `collection` remains
an owner planning artifact and is not silently substituted for metric/catalog results. Default results include only
approved/active lifecycle; proposed/rejected planning records are absent from the Remote MCP DTO.

Allowed common fields are kind, ID, version, lifecycle, owner, public purpose, sensitivity, contract hash and
`details_available`. Per-kind projections add only:

- dataset: layer, grain, natural key, time semantics, freshness SLO, quality rule IDs/descriptions and backup class;
- metric: grain, formula reference, unit, PIT flag, quality gate and input dataset IDs;
- pipeline: output dataset IDs, reviewed stages, schedule/trigger state and activation state without secret profile;
- macro series: concept, region, provider series identity, native frequency/unit/seasonal adjustment, vintage capability,
  source owner, rights/attribution and activation state;
- physical object: qualified name, object type, layer, grain, key, sensitivity, backup class and linked dataset ID or an
  explicit `missing_contract_link` gap.

`access_method`, auth class, secret profile/location, rate-limit internals, raw source URL, internal cost text, provider
free text and manifest-unknown fields are suppressed. Public/internal items receive the allowlist. Confidential items
receive only common metadata and abstract scope. Restricted items receive ID/version/lifecycle/kind/sensitivity plus
`details_available=false`; restricted contents, locators and descriptions are never exposed through `mcp:read`.

Request fields are exact kind, exact ID optional, `limit` default 25/max 50 and opaque cursor. Sorting is kind, ID,
version. Cursor is base64url canonical JSON containing schema version, query hash and last sort tuple; it is strictly
validated, not an authorization token, and invalid/tampered input returns `invalid_cursor`.

## Quality DTO v1 and false-green rule

Request supports exact governed `dataset_id`, optional exact `run_id`, `as_of`, bounded lookback default 7/max 31 days,
limit default 50/max 200 and opaque cursor. Arbitrary rule ID, SQL expression and raw details selection are absent.

Rule projection contains dataset ID, allowlisted rule ID, normalized status, evaluated time, safe value class and an
optional bounded typed value only when a reviewed projector exists for that exact dataset/rule/version. Unknown rule
payload is suppressed and makes aggregate status at most `not_assessed`.

Overall status precedence is deterministic:

1. `unavailable`: required Control query/session could not be established; response has no invented evidence.
2. `failed`: terminal run/stage or required rule explicitly failed.
3. `partial`: a required stage, expected partition/slot, contiguous watermark or coverage element is known missing.
4. `stale`: required evidence is otherwise complete but the executable freshness threshold expired.
5. `not_assessed`: run is non-terminal, expected policy/rule projection is absent, or evidence cannot prove pass.
6. `pass`: all required conditions below are proven.

`pass` requires one terminal succeeded logical run, every stage in the exact packaged pipeline version succeeded once,
all registered required quality rules passed, the requested scope's expected partitions/slots are present, required
watermarks are fresh/contiguous and attributable to the same or a later accepted run, and no sensitivity projection
violation occurred. A succeeded run, zero rows, absent rules, unknown policy or empty query alone can never be green.

Pipeline and dataset-wide pass are distinct. An exact partition run may pass without proving the whole daily dataset.
Dataset-wide requests require a versioned coverage policy; when none exists the result is `not_assessed`, not pass.
Freshness thresholds and expected partition policies must be executable versioned inputs. Natural-language manifest
SLO text is catalog documentation and is never parsed into hidden runtime rules.

## Pipeline-run DTO v1

Request modes are exact `run_id` or list by exact `pipeline_id`; they are mutually exclusive. List mode uses lookback
default 7/max 31 days, limit default 20/max 50 and stable ordering by started time then run ID. No caller-provided
partition SQL, stage name, Job argument or environment override exists.

Response contains run ID, pipeline/version/definition hash, logical date, slot, opaque `partition_ref`, execution state,
composed overall status, source-call used/budget, stage summaries, first failed or resumable stage, freshness, quality,
watermark summaries, retry/resume eligibility and opaque lineage ref. Raw partition key, stage evidence, error message,
exception text, input/output refs and object URI are excluded. Only allowlisted error codes and stage names from the
exact packaged pipeline contract may appear; unknown values are redacted and prevent pass.

`partition_ref` is a versioned hash, not the raw partition key, because current and future partition keys may encode
account or instrument scope. `lineage_ref` is a safe join handle, not an endpoint that grants raw lineage access.

## Implementation and verification boundary

After owner adoption, the future implementation sub-item should:

1. add typed immutable DTOs, consumer policy, status enum and safe projection registry;
2. load catalog records from fixed packaged paths and calculate canonical contract hashes;
3. query the five Control evidence tables with parameter binding, exact catalog/schema qualification and application
   deadline; do not rely on `pipeline_run_summary` as overall status;
4. add per-pipeline executable coverage/freshness policy incrementally; absent policy remains `not_assessed`;
5. test restricted/proposed suppression, raw JSON/error/partition leakage, failed/partial/stale/not-assessed/unavailable,
   unknown rules/stages, missing watermarks/partitions, cursor tampering, page/response bounds and stable hashes;
6. run local migration/rehearsal and live read-only inventory. Live `UNAVAILABLE` stays explicit and does not authorize
   cached or empty green output;
7. hand only the stable application contracts to WI-042; public names, OAuth scope and client compatibility remain there.

No DDL is expected for the initial implementation. If current Control columns cannot support the approved DTO without
semantic overloading, implementation stops and proposes additive migration `0017`; it does not change the existing
tables or view opportunistically.

## 남은 MS-003 선행조사 재점검

| Work Item | 현재 선행상태 | 지금 할 가치가 있는 다음 작업 |
| --- | --- | --- |
| WI-035 operations/cost | S01 research closed | 조사 반복 없음; 구현 전 rollback manifest·cost evaluator 설계/구현 범위를 고정 |
| WI-037 filing | S01~S03 closed | 추가 선행조사 없음; formal gate 뒤 implementation |
| WI-038 dividend | S01~S03 closed | 추가 선행조사 없음; formal gate 뒤 implementation |
| WI-039 macro | S01~S04 closed | 추가 선행조사 없음; formal gate 뒤 implementation |
| WI-040 catalog/quality | S01 closed, S02 owner-decision-ready | owner 승인 뒤 S03 canonical contract adoption |
| WI-041 consensus | S01/S02/S04 closed, S03 rejected preserved | 현재 추가 조사 없음; Alpha는 approved-inactive, historical PIT gap 명시 |
| WI-042 read surface | no sub-item | **다음 유효 조사 후보**: existing 35-tool/OAuth/18-tool mapping과 WI-040 DTO adapter boundary audit |
| WI-043 managed commands | no sub-item | WI-042 scope/DTO freeze 뒤 command authorization·Firestore port 조사 |
| WI-044 client compatibility | no sub-item | WI-042/043 contract 뒤 test matrix 작성; 실제 client smoke는 implementation 뒤 수행 |
| WI-045 dual-run readiness | no sub-item | WI-035/044 뒤 최신 운영 inventory로 조사; 지금 하면 증거가 stale해짐 |
| WI-046 cutover | no sub-item | WI-045 pass 뒤에만 cutover manifest/rollback review가 의미 있음 |

따라서 이번 S02 승인·S03 adoption 뒤에는 `WI-042-S01`만 선행조사로 여는 것이 권고 순서다. WI-043~046을
지금 동시에 조사하지 않는 것은 번호순 집착이 아니라 upstream public contract와 운영 evidence가 아직
고정되지 않아 결과가 빠르게 낡기 때문이다.

## Owner decision package

다음 여덟 항목을 한 묶음으로 승인 또는 수정한다.

1. DB-only를 provider call 없는 packaged-manifest + MotherDuck-Control 읽기로 정의하고 DB catalog 복제본은 만들지 않는다.
2. 기존 5개 Control evidence table과 compatibility summary view를 6개 logical dataset contract로 등록한다.
3. DGH에 source-less Control evidence용 제한적 `control_origin`과 3개 inactive `read_model` contract를 추가한다.
4. catalog는 source/dataset/metric/pipeline/macro-series/object를 제공하고 collection/proposed/restricted detail은 제외한다.
5. common envelope, typed projection, 256 KiB response와 page/lookback bounds를 채택한다.
6. `unavailable > failed > partial > stale > not_assessed > pass` precedence와 증거 없는 green 금지를 채택한다.
7. raw JSON, error text, partition key, lineage refs, secret/auth/cost internals을 suppress하고 opaque refs만 제공한다.
8. WI-040은 application read model까지만 소유하고 public tool/OAuth/client behavior는 WI-042 이후로 유지한다.

Owner는 여덟 항목을 2026-09-02 승인했다. `WI-040-S03`이 DGH schema, six dataset contracts, three read-model
contracts와 requirements/system-design clarification을 canonical SSOT에 채택한다. MS-002가 닫히고 MS-003
formal gate가 열린 뒤에만 DTO/query 구현을 시작한다.

## Verification boundary

이번 S02는 repository와 existing local schema를 read-only로 조사한 설계다. manifest lifecycle, checker,
application code, DDL, DB, source, secret, infrastructure, schedule, public MCP와 deployment를 변경하지 않았다.

- `python3 .agent/skills/kis-project-os/scripts/check_project_os.py`: passed, 54 tracked Work Items and one active
  implementation Work Item
- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: passed, 152 registered contracts
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: passed, 440 tests and one existing Authlib deprecation warning
