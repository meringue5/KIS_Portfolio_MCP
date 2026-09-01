# WI-041-S04 bounded Alpha Vantage personal-use review — 2026-09-01

> Work Item: `WI-041-S04`
> 상태: ready for owner contract decision
> 분류: clarification/change; research and contract design only
> 선행 증거: `WI-041-S01`~`S03`
> 변경 경계: production call, DB write, raw retention, DDL, pipeline, MCP, deployment와 외부 메시지 없음

## Trigger and governance lesson

`WI-041-S03`은 공식 API를 통한 개인 사용과 기업 데이터 플랫폼의 재배포·장기 raw archive를 충분히
구분하지 않고, provider의 개별 written permission을 사실상 필수 gate로 적용했다. DGH 자체가 모든 source에
개별 support 답변을 요구한 것은 아니며, S03의 과도한 판정은 agent가 ETF production rights 수준을 일반
consensus 개인사용에도 확장 적용한 데서 생겼다.

Project OS에 따라 S03의 불변 이력과 negative outcome은 보존한다. S04는 같은 ID를 다시 열거나 S03을
성공으로 고쳐 쓰지 않고, 공개 약관이 명시적으로 허용한 owner-only use와 여전히 불명확하거나 금지해야 할
사용을 위험에 비례해 다시 분류한다. 이 사례는 “fail-closed”가 곧 “모든 불확실성에 최고 수준의 gate를
적용한다”는 뜻이 아니며, 계약의 실제 문구·사용자·소비자·재배포 경계를 먼저 대조해야 함을 보여준다.

## Facts already established

- Alpha Vantage는 web crawling 후보가 아니라 owner-issued key를 사용하는 공식
  `EARNINGS_ESTIMATES` API 후보다.
- 2026-09-01 확인한 공식 Terms of Service는 API를 Alpha Vantage Platform에 포함하고 personal,
  non-commercial use를 허용한다. investment analysis, research, testing, monitoring과 private/individual
  activity는 commercial-use 경계 밖의 예로 명시돼 있다.
- 공식 support는 무료 key의 표준 한도를 25 requests/day로 안내하고 공식 MCP/AI-agent 사용 경로도 제공한다.
- license는 non-exclusive, non-sublicensable, non-transferable, revocable이고 provider는 Platform/Content의
  권리를 보유한다. 약관은 private normalized snapshot의 보존이나 종료 후 삭제를 명시적으로 설명하지 않는다.
- S03의 bounded sample은 four physical calls 중 한 건에서 41-row schema를 확인했다. 이 endpoint는 현재
  rolling comparison을 제공하지만 historical provider snapshot/revision lineage는 제공하지 않는다.

Official references:

- <https://www.alphavantage.co/terms_of_service/>
- <https://www.alphavantage.co/support/>
- <https://www.alphavantage.co/documentation/>

## Review scope

S04는 다음 세 경계를 별도로 판정하고 계약 초안을 만든다.

| Tier | Candidate use | Initial disposition to validate |
| --- | --- | --- |
| A | 공식 API 호출, memory 내 parse, owner에게 즉시 분석 결과 표시 | published personal-use license 안의 허용 후보 |
| B | 필요한 consensus field만 정규화해 owner-only MotherDuck에 forward-only snapshot으로 보존하고 private MCP가 소비 | reasoned personal-use 후보; raw 제외, 최소보존·삭제가능성·약관 version 통제 필요 |
| C | raw response 장기 mirror, public/multi-user MCP, 제3자 제공, 판매·상업 이용, realtime entitlement 우회 | 금지; 별도 plan/license 없이는 활성화하지 않음 |

Tier B의 “reasoned personal-use”는 법률 보증이나 provider 권리 양도가 아니다. published terms, single owner,
non-commercial purpose, no redistribution, data minimization과 revocable collection을 함께 근거로 삼는 bounded
risk acceptance다. 공개 약관이 바뀌거나 사용자가 늘어나면 자동으로 collection을 멈추고 재검토해야 한다.

## Required contract decisions

1. Alpha Vantage를 placeholder가 아닌 별도 proposed source ID/version으로 등록할지 결정한다.
2. `dataset.consensus-snapshot`을 historical provider PIT와 forward-collected owner snapshot으로 분리할지
   결정한다. 현재 endpoint로 과거 knowledge state를 backfill하지 않는다.
3. raw response는 persist하지 않고, allowlisted normalized field와 `fetched_at`, provider, horizon, forecast date,
   quality/coverage만 저장하는 schema를 정의한다.
4. retention, private backup, deletion/revocation과 terms-review cadence를 명시한다. 약관에 없는 권리를
   “explicitly allowed”라고 쓰지 않고 owner risk acceptance와 보완 통제를 기록한다.
5. current held U.S. direct issuers만 allowlist하고 25/day 아래의 physical-call budget, serialized spacing,
   provider `Information` envelope의 fail-closed partial handling을 설계한다.
6. official API만 사용하며 crawling, scraping, entitlement 우회와 raw redistribution을 명시적으로 제외한다.
7. private MCP는 normalized read model만 소비하고 provider payload나 API key를 노출하지 않는다.

## Acceptance criteria

- [x] published terms와 실제 owner-only use의 mapping이 근거 URL·검토일·license/risk class로 기록된다.
- [x] Tier A/B/C와 raw/normalized/derived/redistribution 경계가 승인 가능한 문장으로 고정된다.
- [x] forward-only time semantics, no historical backfill와 missing coverage가 dataset 계약에 반영된다.
- [x] source-call budget, spacing, partial/failure와 terms-change kill switch가 정의된다.
- [x] source/collection/dataset/pipeline contract delta가 versioned proposal로 제시된다.
- [x] owner가 contract와 residual risk를 승인하기 전 production 활성화·DB write·MCP 노출이 없다.
- [x] `bash scripts/check.sh quick`과 `bash scripts/check.sh full`이 통과한다; 117 DGH contracts and 438 tests.

## Initial plan

1. 공식 약관과 S03 schema evidence를 contract field별로 매핑한다.
2. 최소보존 source/dataset/pipeline delta와 alternatives를 작성한다.
3. user approval package에서 retention, backup, schedule/call budget과 residual risk를 한 번에 제시한다.
4. 승인 후에만 contracts를 approved로 올리고 구현은 별도 순차 sub-item으로 진행한다.

## Proposed DGH delta

| Contract | Version/status | Role and boundary |
| --- | --- | --- |
| `source.alpha-vantage-personal` | 1.0.0 / proposed | official API only, owner-only personal/non-commercial, secondary, no crawling/redistribution |
| `collection.consensus-research-later` | 1.1.0 / proposed | retains KIS/historical-provider gaps and adds Alpha forward-only candidate |
| `dataset.alpha-vantage-consensus-forward-snapshot` | 1.0.0 / proposed | restricted normalized Silver snapshots, three-year rolling retention, private Parquet backup, zero raw retention |
| `pipeline.alpha-vantage-consensus-forward-v1` | 1.0.0 / proposed | scale-to-zero U.S.-morning collection, memory normalization, bounded quality/publish |

기존 `source.consensus-provider-tbd`와 `dataset.consensus-snapshot`은 수정하지 않았다. 전자는 historical
licensed provider gap을, 후자는 실제 provider knowledge snapshots를 요구하는 canonical PIT 계약을 계속
소유한다. Alpha forward dataset을 별도로 둠으로써 rolling comparison을 과거 PIT로 승격하거나 canonical
계약을 조용히 약화하지 않는다.

## Recommended bounded operating contract

- Scope: latest canonical holdings 중 `NASD / overseas_direct / equity / USD`인 현재 미국 직접주식만 사용한다.
- Schedule: governed calendar의 직전 완료 U.S. session 뒤 한국 오전에 한 번 실행한다. DST-safe 실제 시각은
  deployment 설계에서 확정하고, 장중 polling은 하지 않는다.
- Budget: 현재 4 physical calls/day, hard maximum 8/day, provider account 전체 25/day를 절대 넘지 않는다.
- Pacing: issuer별 직렬 실행, physical call 간 최소 15초, 같은 run에서 retry하지 않는다.
- Persistence: raw JSON과 provider free-text message는 저장하지 않는다. allowlisted normalized fields,
  `fetched_at`, provider date/horizon, coverage와 quality만 append한다.
- Time semantics: activation 이후 `fetched_at`부터 forward-only다. 7/30/60/90-day comparison은 응답 속성일
  뿐이며 그 과거 날짜의 knowledge snapshot으로 사용하지 않는다.
- Consumption: owner-only 분석과 private MCP normalized read model만 허용한다. Telegram, public/multi-user MCP,
  redistribution과 commercial use는 제외한다.
- Kill switch: 분기별 및 terms-change 검토가 만료되거나, shape/entitlement/terms가 바뀌면 수집과 publish를
  멈추고 재승인한다.

## Capacity and cost envelope

현재 4 issuers, 표본의 41 forecast rows와 EPS/revenue 두 metric을 보수적으로 모두 별도 row로 정규화하면
`4 × 41 × 2 × 252 × 3 = 247,968` rows/3 years다. hard maximum 8 issuers에서도 약 495,936 rows다.

- 1 row를 압축 전 1 KiB로 과대 추정해도 최대 약 0.5 GiB이고, 실제 typed/Parquet 저장은 이보다 작을
  가능성이 높다. 기존 MotherDuck/비공개 Parquet 예산에 비해 작은 범위다.
- current scope는 약 1,008 calls/year, hard maximum은 약 2,016 calls/year이며 각 provider day의 25-call
  account limit 아래다.
- 15초 pacing이면 4 issuers는 최소 45초, 8 issuers는 최소 105초에 request latency가 더해진다. 상시 service가
  아니라 scale-to-zero Job 하나로 처리할 수 있어 월 50,000원 architecture 경계를 바꾸지 않는다.
- subscription, realtime entitlement, always-on service와 별도 warehouse는 포함하지 않는다.

## Owner decision package

권고안은 다음 네 항목을 한 묶음으로 승인하는 것이다.

1. 공개 약관을 개인·비상업·비공개 API 수집과 내부 분석의 충분한 근거로 채택하고 별도 support inquiry는
   요구하지 않는다.
2. raw response는 보존하지 않고 normalized forward snapshot을 3년 rolling 보존하며 private Parquet backup을
   허용한다.
3. 현재 4, hard maximum 8 calls/day와 15초 spacing, no same-run retry를 승인한다.
4. historical PIT, pre-activation backfill, public/multi-user/Telegram/redistribution/commercial 사용은 계속
   unsupported로 둔다.

Residual risk는 provider가 private normalized retention을 명시적으로 설명하지 않았다는 점과 license가
revocable하다는 점이다. 보완 통제는 single owner, official API, zero raw retention, restricted dataset,
three-year rolling retention, private backup, quarterly terms review와 즉시 kill switch다.

## Current disposition

S04의 contract design은 검토 가능한 `ready` 상태다. Alpha key는 research-only Secret Manager resource에
남아 있고 runtime accessor는 없다. owner가 위 package를 승인하기 전 모든 새 DGH contract는 `proposed`이며,
S03 rejected history, parent `WI-041` proposed 상태와 MS-003 formal gate는 변경하지 않는다. Full verification은
117개 DGH contracts와 438 tests를 통과했다.
