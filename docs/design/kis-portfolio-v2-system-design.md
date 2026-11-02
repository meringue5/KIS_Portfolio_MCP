# 시스템 경계와 설계 이유

> 현행 의미 계약. 승인된 DEC/ADR의 재서술이며 새 architecture·source·배포 권한이 아닙니다.
> 먼저 [운영 모델](../operating-model.md), 코드 배치는 [ARCHITECTURE](../../ARCHITECTURE.md)를 읽습니다.

## 책임과 연결

```text
OAuth auth ── token/state ── Firestore
클라이언트 ── OAuth Remote MCP ── application/core ── governed read/write ports
Scheduler/managed 요청 ── fixed Cloud Run Jobs ── source adapters ── raw GCS + Bronze
                                              └─ normalize/quality/publish ── Silver/Gold/Control
                                                                             └─ 알림·전송
Secret Manager ── 각 identity가 필요한 장기 credential/key만 공급
```

| 경계 | 소유 책임 | 결합하면 안 되는 책임 / 이유 |
| --- | --- | --- |
| core/application | 요청 scope·계산·명령/조회 정책 | MCP·provider·물리 DB에 계산 의미를 종속시키지 않음 |
| auth service | OAuth 등록·동의·token lifecycle | KIS 계좌 credential·분석 데이터 접근과 분리 |
| Remote resource | stateless Streamable HTTP, actor/scope/resource 검증, bounded DTO | client에 KIS credential 주입, 임의 source·shell·SQL 실행 금지 |
| batch/runner | 고정 Job·budget·stage resume·quality/lineage·publish | LLM 활동에 필수 수집을 의존하거나 자유 env/arg override 허용 금지 |
| Firestore | OAuth digest/KIS token ciphertext·lease·run request | analytical 사실·대용량 원문을 OLTP state로 옮기지 않음 |
| MotherDuck | Bronze/Silver/Gold/Control 분석·revision | OAuth/token/lease의 운영 SSOT로 되돌리지 않음 |
| private GCS | immutable raw/object hash·Parquet 복구 | 무제한 원문 BLOB을 warehouse에 중복 저장하지 않음 |

serverless modular monolith를 유지하는 이유는 개인·저빈도 작업에 상시 worker나 기능별 network tier의 운영비가 더 크기 때문입니다.
auth/resource의 분리는 secret blast radius를 줄이고, 공통 immutable image는 버전 drift를 줄입니다.
세부 secret/IAM은 더 구체적인 [보안 정책](../security-and-secrets.md), 실제 image·route·Job 승격은 [배포 계약](../deployment.md)을 따릅니다.
과거 설계의 권한 표나 migration rollback 가설은 이 현행 정책을 덮지 않습니다.

## 데이터·실행 불변식

- 분석 plane은 `bronze/silver/gold/control`, 보안 state는 warehouse 밖입니다. runtime DDL 없이 versioned migration을 사용합니다.
- 원문 append, 정규화 identity/revision, canonical totals, versioned metrics, Control evidence를 분리합니다.
- trigger는 at-least-once라고 가정하고 logical idempotency key·stage resume·효과 claim으로 중복을 통제합니다.
- source call/page/row/byte/deadline budget과 exact scope를 먼저 고정합니다. 행 존재·Job 성공은 publish pass가 아닙니다.
- partial source failure는 독립 기능까지 차단하지 않으며, 검증되지 않은 전체 합계·성과·알림을 만들지 않습니다.
- 알림·전송은 separate ledger입니다. provider unknown·timeout을 다른 전송 방식으로 재시도하지 않습니다.
- [파이프라인 의미](../data-pipeline.md), [원장 계약](portfolio-ledger-contracts.md), [분석 계약](analytics-contracts.md),
  [알림 계약](alert-delivery-contracts.md), [참고 이력 계약](reference-history-contract.md)이 세부 경계를 연결합니다.

## 품질·복구·비용의 의미

데이터 유실·거짓 완전성·중복 경보를 일시적 cold start/지연보다 심각하게 봅니다. 다음 수치는 기존 설계의
**목표/운영 한계**이며 현재 측정 실적이나 클라우드 가격이 아닙니다.

| 항목 | 기존 목표 / 제약 | 확인할 소유 문서 |
| --- | --- | --- |
| schedule | due run 99%가 slot+10분 내 terminal | [운영 런북](../operations/steady-state-operations-runbook.md) |
| 조회 | warm P95 3초, cold P95 15초 목표; 60초 넘는 외부 작업은 async Job | [public/read 계약](../../governance/catalog/read-models.toml) |
| freshness/완전성 | 입력 계약 이내; partial/unknown과 missing coverage 명시 | [데이터 카탈로그](../data-catalog.md) |
| backup/restore | RPO 24시간, RTO 4시간; fresh local restore 증거 | [백업](../backup.md) |
| 비용 | 일반월 7,500원 목표 / 50,000원 ceiling, staged guard | [비용·릴리즈 가드](../operations/production-cost-release-guardrails.md) |

Billing budget 알림 자체는 지출 차단장치가 아닙니다. min/max·timeout·retry·call budget·optional source gate와
실제/예상 비용 검토가 통제 수단입니다. 새 상시 서비스·유료 provider·WebSocket·microservice를 문서 정비로 도입하지 않습니다.

## 무엇을 바꿀 때 어디를 확인하는가

- public tool/scope/auth: [MCP 등록](../../src/kis_portfolio/adapters/mcp/v2.py), [Remote](../../src/kis_portfolio/remote.py), [연결 계약](../remote-mcp-v2-migration.md).
- dataset/grain/key/lineage/retention: [DGH](../governance/data-governance-harness.md), [catalog](../data-catalog.md), [registry](../../governance/catalog/).
- runtime/migration: [배포](../deployment.md), [backup](../backup.md), [운영 런북](../operations/steady-state-operations-runbook.md).
- 검증: [기능 추적표](../traceability.md). transport/schema 테스트와 실제 승인 client의 positive/partial/error를 구분합니다.

## 승인 이유와 원래 비교안

장기 결정은 [SPEC](../../SPEC.md)의 ADR이 정본입니다. V2-ADR-001~017의 원래 대안·기반 비용 조사·migration
파형은 [구축 원문 압축본](../history/README.md)에 보존했습니다. 이 페이지는 그 타임라인을 매번 읽지 않도록
현재 책임과 선택 이유만 남깁니다. [delivery 식별자 목록](kis-portfolio-v2-delivery-plan.md)은 기존 검사 호환용이며 새 작업 순서가 아닙니다.
