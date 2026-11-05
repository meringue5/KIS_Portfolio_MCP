# 운영 모델 — 무엇을 믿고 어떻게 고칠 것인가

> 읽는 목적: 현재 시스템을 이해하고 변경할 때 필요한 의미·이유·판정 규칙.
> 기존 승인 요구·ADR·계약을 압축한 설명이며 새 기능 승인이나 현재 운영 정상 판정이 아닙니다.
> [기능별 코드·테스트](traceability.md) · [현재 업무/후보](../TODO.md) · [증상 대응](troubleshooting.md)

## 이 서비스의 역할

대화와 독립적으로 개인 보유자산을 관측·보존하고, 근거와 한계를 표시해 조회·분석·알림을 제공합니다.
사용자는 하나의 OAuth Remote MCP로 접근합니다. 자산 사실을 추측해 채우거나 자동 주문하지 않습니다.
수집·품질·전송을 분리하므로 부분 장애는 해당 능력을 제한하고 검증된 다른 능력은 유지합니다.

## 혼동하면 안 되는 여섯 가지 값

| 개념 | 의미 / 사용할 수 있는 근거 | 이 값만으로 알 수 없는 것 |
| --- | --- | --- |
| 관측값 | 특정 source·basis·시각에 받은 사실 | 미관측 구간, 실제 결제 시각, 현재와의 동일성 |
| canonical 총자산 | 요구 계좌·자산·가격·FX가 완전하고 합계가 대사된 평가액 | 현금흐름 조정 수익률 |
| 부분 결과 | 자체 범위의 근거가 있는 국내 현황·구성·소계 | 전체 자산의 완전 합계 |
| 평가액 변화 | 비교 가능한 두 상태의 원화 평가액 차이; FX·수량 변화도 포함 | 순수 가격수익·외부 자금 유입/유출 원인 |
| 투자 성과 | 정확한 범위의 자본 흐름·분류·시점까지 검증한 조정 수익률 | 행이 있거나 차액이 0이라는 사실만으로 계산 가능하지 않음 |
| reference 이력 | 가정·종류·시점을 명시한 비정본 참고 총액 | canonical 품질·성과·alert 입력 자격 |

현금 이력은 **관측 금액·basis·시각·날짜별 변화와 제한된 거래 문맥**입니다. 원인이 unknown이면 그대로
둡니다. 입출금/RP·실제 결제의 원인 추정과 완전 대사는 제공하지 않습니다. 0은 관측된 0이고, missing은
정보가 없는 상태입니다. 최신 관측이라도 settled cash라는 의미까지 보증하지 않습니다.

## 근거가 있어야 상태를 올릴 수 있다

- API 문서 존재 → 구현 존재 → credential 접근 → 실제 응답 → 요청 범위 coverage → 계산/사용 자격은 별개입니다.
- 빈 결과는 원천·계좌·시장·기간 전체가 증명됐을 때만 ‘사건 없음’입니다. watermark는 이어받을 위치이지 완전성 증거가 아닙니다.
- 금액 합산이 맞는 것은 일관성 검사입니다. 해외 feeder나 계좌가 빠지지 않았다는 독립 증거가 아닙니다.
- 관측 슬롯 존재, Job 프로세스 성공, dataset quality pass, publish 완료, provider 전송 성공, 사용자 수신은 서로 다른 증거입니다.
- 문서의 approved/active 계약과 공개 tool 이름은 현재 기간의 source 가용성을 보증하지 않습니다.
- 미지원·source gap·partial·stale·failed·unavailable을 0이나 pass로 바꾸지 않습니다. 원인과 누락 범위를 돌려줍니다.

## 시간·수정·동일성

source가 뜻하는 effective/observation time, 우리가 알게 된 knowledge/recording time, 요청 cutoff를 구분합니다.
과거 조회는 당시 알 수 있었던 revision만 사용합니다. 늦게 들어온 자료나 보정은 이력을 덮지 않고 새 revision입니다.
경제적 거래 identity와 source 관측 identity는 다를 수 있습니다. source-proven alias로 현재 projection을 바로잡고,
원문 삭제·가격/시간/수량만의 DISTINCT로 정상 주문까지 합치지 않습니다. 같은 input replay는 no-op이며 충돌은 실패입니다.

## 경계와 그 이유

| 선택한 경계 | 이유 | 변경할 때 지킬 것 |
| --- | --- | --- |
| core와 MCP/배치 adapter 분리 | 계산·검증을 transport와 독립 재현 | tool에서 임의 SQL·source 명령·추론을 새로 소유하지 않음 |
| Firestore 운영 state / MotherDuck 분석 사실 / GCS 원문·복구 / Secret Manager 장기 key | 수명·transaction·민감도·복구 책임이 다름 | 인증/lease를 분석 테이블에 다시 결합하지 않음 |
| 고정 registry·Job args / 공통 immutable image | 중복 trigger와 임의 실행·버전 drift를 통제 | idempotency·lease·budget·run/stage/quality/lineage 보존 |
| raw append-only / 정제된 projection에서 보정 | 나중에 원인과 당시 지식을 재구성 | 같은 key 충돌을 덮거나 과거 실패를 지우지 않음 |
| 모르는 값은 null·이유 / 독립 능력은 분리 제공 | 거짓 완전성보다 제한된 정확성이 유용 | 전체 총액 불가를 국내 현황 불가로 전파하지 않음 |
| 평가·상태전이·전송 분리 | 알림 중복과 전송 불확실성을 별도 통제 | unknown 배송은 자동 재전송하지 않음 |

자세한 정본 경계는 [ARCHITECTURE](../ARCHITECTURE.md), 결정은 [SPEC](../SPEC.md), 데이터/보안/배포는 각각
[카탈로그](data-catalog.md)·[보안](security-and-secrets.md)·[배포](deployment.md)가 소유합니다.

## 현재 제공과 의도적으로 남긴 한계

- DEC-064 승인 변경은 보유종목 현황 08:00 해외·10:00/14:00/16:00 국내, 총자산 보고서 08:00/14:00입니다. WI-078 보호 배포 전까지 운영은 기존 세 시각·10:00/16:00를 유지합니다. 현황과 상세 transition 알림은 다른 제품입니다.
- 현금 관측·참고 이력은 위 의미 그대로 제공합니다. 조건부 성과/전망/배당은 실제 입력 계약·기간 coverage를 확인합니다.
- 관심종목 알림은 차기 검토 후보, ETF 구성종목 look-through는 초기 인수 밖입니다. 주문·실시간 전종목 수집·다중사용자 서비스는 현재 제품이 아닙니다.
- 구축 완료는 모든 미래 데이터·source·기능이 제공된다는 뜻이 아닙니다. [인수 경계](milestones/v2-acceptance.md)를 따릅니다.

## 수정 작업에서 답해야 할 질문

1. 어떤 값·상태·scope의 의미를 바꾸는가? [기능 지도](traceability.md)에서 기존 요구·구현·테스트를 찾습니다.
2. 관측/coverage/identity/시간/계산/transport 중 어느 경계의 문제인가? 단순 no-rows를 source 미지원으로 단정하지 않습니다.
3. [원장·재구성](design/portfolio-ledger-contract.md), [분석](design/analytics-contract.md),
   [알림·전송](design/alert-delivery-contract.md), [참고 이력](design/reference-history-contract.md)의 불변식을 유지하는가?
4. 정상·부분·오류에서 기대 결과와 독립 oracle을 고정했는가? unit PASS와 실제 client 인수는 구분합니다.
5. runtime/data를 바꾸면 기존 배포·backup/restore·rollback 경로를 검증하고, 변경한 능력의 실제 사용을 확인합니다.
6. 운영 결함은 같은 outcome의 보정으로 추적하고 완료 milestone을 되열지 않습니다. 새 기능은 별도 검토합니다.

작업 절차·권한은 [Project OS](governance/project-operating-system.md)가 정본입니다. 이 요약이 요구를 완화하지 않습니다.

## 사례는 규칙의 근거가 필요할 때만

| 이해가 필요한 이유 | 개별 사례 |
| --- | --- |
| watermark/빈 행이 왜 완전성 증명이 아닌가 | [거래 구간 증명 교정](work-items/WI-063-incremental-trade-event-collection.md) |
| 합계가 일치해도 과거 총액이 왜 격리되는가 | [legacy 불완전 이력](work-items/WI-066-legacy-total-asset-history-quality-recovery.md) |
| 현황 수신과 상세 수신을 왜 따로 인수하는가 | [영구 상세 신호](work-items/WI-070-permanent-held-position-telegram-signals.md), [세 시각 현황](work-items/WI-076-three-slot-held-signal-status.md) |
| 관측 현금과 결제 대사를 왜 구분하는가 | [현금의 인수된 범위](work-items/WI-071-owner-cash-flow-history-management.md) |

이 사례들을 매번 순서대로 읽을 필요는 없습니다. 더 오래된 설계·구축 과정은 [압축 원문](history/README.md)으로 내려갑니다.
