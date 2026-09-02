# WI-040-S03 catalog and quality read-model contract adoption — 2026-09-02

> Work Item: `WI-040-S03`
> 상태: closed
> 변경 분류: data contract and canonical design clarification
> owner decision: WI-040-S02의 여덟 권고안 전부 승인

## Adopted outcome

- DGH에 `read_model` kind와 `read_model.` namespace를 추가했다.
- existing physical Control objects에 six logical approved dataset contracts를 연결했다:
  `dataset.pipeline-run-evidence`, `dataset.pipeline-stage-evidence`, `dataset.data-quality-evidence`,
  `dataset.data-lineage-evidence`, `dataset.pipeline-watermark-state`, `dataset.pipeline-run-summary-compat`.
- source-less 예외는 `layer=control`과 `control_origin=managed-pipeline-runtime`을 동시에 만족하는 runtime run
  evidence에만 허용한다.
- three application contracts `read_model.data-catalog-v1`, `read_model.data-quality-v1`,
  `read_model.pipeline-run-v1`을 `approved + inactive`로 채택했다.
- 모든 read model은 typed allowlist와 suppressed fields, 256 KiB response ceiling, bounded page/lookback,
  explicit unavailable policy와 `unavailable > failed > partial > stale > not_assessed > pass` 상태 계약을 가진다.
- packaged manifest/object registry가 catalog 결정 SSOT이고 MotherDuck Control은 운영 증거다. provider call,
  DB catalog 복제본과 arbitrary SQL은 허용하지 않는다.
- `pipeline_run_summary`는 compatibility view일 뿐 공식 overall quality가 아니다. Public MCP/OAuth registration은
  WI-042에 남겨 `get-pipeline-run`과 approved 18-tool budget을 유지한다.

## Enforcement

DGH checker는 source-less Control origin 범위, integer bounds, allowed/suppressed field disjointness, 최소 한 개의
governed input과 production read-model lifecycle/active-input 조건을 검증한다. Fixture tests는 허용된 repository
상태와 non-Control origin, field overlap, oversized/unbounded 및 premature production activation 거부를 확인한다.

## Boundary

이번 sub-item은 계약과 문서만 채택했다. DTO/query/application code, DDL, migration, DB write, source call,
credential, infrastructure, schedule, deployment, public MCP registration과 runtime activation은 변경하지 않았다.
현재 physical object 수와 warehouse catalog allowlist도 바뀌지 않았다.

## Verification

- focused governance tests: `10 passed`
- Project OS checker: `54 tracked Work Items`, one active parent implementation Work Item
- DGH checker: `161 registered contracts`
- architecture, warehouse and MCP-surface check: passed; current compatibility surface `35 tools`
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: `443 passed`, existing Authlib deprecation warning one

## Result and next gate

`WI-040-S03`은 closed다. Parent WI-040과 MS-003은 proposed이고 runtime implementation gate는 열지 않았다.
다음으로 가치 있는 사전조사는 WI-042-S01의 existing tool/OAuth/18-tool mapping과 thin adapter boundary audit다.
