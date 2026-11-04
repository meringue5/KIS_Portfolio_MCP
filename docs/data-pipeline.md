# 데이터 흐름과 판정 경계

> 운영자가 필요한 것은 어느 단계에서 어떤 증거로 의미가 바뀌는지입니다. 구축 단계·run 일지는 [압축 원문](history/README.md)으로 분리했습니다.
> [운영 모델](operating-model.md) · [객체 정본](data-catalog.md) · [source/collection/dataset/metric/pipeline 계약](../governance/catalog/)

## 전체 흐름

```text
Scheduler 또는 고정 managed 요청
  → logical run / lease / 예산 검증
  → source 관측 + immutable raw/object hash
  → canonical identity/revision 정규화
  → quality / exact coverage / lineage
  → publish: canonical 상태·지표 또는 제한 사유
  → 저장 데이터 조회 / 신호 평가 / 별도 전송 claim·결과
```

Cloud Run Job 프로세스 성공만으로 이 흐름의 모든 능력이 pass가 되지 않습니다. run/stage/quality/publish와
실제 delivery는 별도로 확인합니다. MCP는 임의 수집/SQL 실행 경로가 아니라 governed query와 고정 command입니다.

## 단계가 소유하는 것과 하지 않는 것

| 단계 | 남겨야 할 사실 | 금지할 승격 |
| --- | --- | --- |
| source | operation·scope·시간·원문 hash·pagination·오류/빈 관측 | 응답 성공/빈 행을 전체 구간 무사건으로 해석 |
| Bronze | immutable 관측과 raw locator/knowledge/recording 근거 | dedup·보정 과정에서 source를 삭제/덮기 |
| Silver | 경제적 identity·revision·분류/계좌·canonical position/cash/trade | 서로 다른 주문 합치기, inferred opening을 실제 매수로 변환 |
| Gold | 검증된 상태·비교·versioned metric | partial 합계를 전체 총액, 미확인 flow를 성과 pass로 표시 |
| Control | run/stage/watermark/quality/lineage·진단·claim/결과 | cursor/watermark/Job success를 coverage/전송 성공 증명으로 대체 |
| consumer | scope·as-of·age·누락 이유·표시 경계 | 비정본 참고값을 canonical/성과/alert 입력에 혼합 |

물리 객체·grain·key·민감도·backup은 [data catalog](data-catalog.md), runtime state와 secret은
[보안 정책](security-and-secrets.md)이 정본입니다. live-only drift는 자동 채택·백업·삭제하지 않습니다.

## 재실행·revision·시간

logical run key는 `(pipeline_id, version, logical_date, slot, partition)`으로 고정합니다. 성공한 stage/run은
재사용하고 실패 stage부터 이어갑니다. scope/기간/plan 변경을 같은 checkpoint로 위장하지 않습니다.
source call/page/row/object-byte/deadline budget을 먼저 확인합니다. raw 입력·coverage는 replay hash,
후보 projection은 별도 hash로 묶어 변조와 충돌을 감지합니다.

effective/observation time과 knowledge/recording time은 분리합니다. 과거 cutoff 뒤에 알게 된 correction은
그 당시 결과에 새어 들어가지 않습니다. exact replay는 no-op, 정당한 보정은 append-only revision,
같은 논리 identity의 다른 content나 모호한 순서는 explicit failure입니다.

## 능력별 필수 근거

| 능력 | 어떤 근거가 함께 필요한가 | 부족하면 |
| --- | --- | --- |
| canonical 현재 자산 | 모든 required 계좌·국내/해외 position·현금 basis·가격/FX·component quality·합계 대사 | 완전 총액 보류; 독립 검증된 범위의 현황/소계만 명시 |
| 이전과의 변화 | 같은 slot·비교 가능한 scope/state·이전/현재 quality | 비교/기여도 보류; 검증된 현재 구성까지 차단하지 않음 |
| 거래 ledger의 빈 결과 | exact account/market/time의 모든 required source-partition·pagination·reconciliation·quality/lineage/publish | no-activity가 아니라 partial/unavailable |
| position/lot 재구성 | canonical trades·action coverage·시간순서·수량 경계·두 hash·atomic publish | provisional/not_assessed/exception과 근거 보존 |
| 성과·위험 | 각 formula의 PIT·flow/owner-plan·가격/FX·reconciliation gate | numeric null과 원인; valuation change로 대체하지 않음 |
| signal/전송 | pass metric/input·approved immutable rule·전이·claim·provider terminal 결과 | 상태/전송을 분리한 suppression/failure/unknown |

[원장·재구성](design/portfolio-ledger-contract.md), [분석](design/analytics-contract.md),
[알림·전송](design/alert-delivery-contract.md)이 상세 불변식과 테스트 출발점을 소유합니다.

## 기본 경로·독립 경로·조건부 경로

- owned-portfolio core는 기존 fixed slot에서 필수 자산 관측→정규화→품질→publish→보고/신호 능력을 계산합니다.
- trade incremental은 독립 producer입니다. 거래 source 실패를 자산 현황 전체 실패로 전파하거나 자산 refresh 성공으로 거래 coverage를 가장하지 않습니다.
- held-instrument classification, 가격/FX, action, fundamentals/dividends, macro, research는 각각 선언된 source·권리·budget·scope를 따릅니다.
  umbrella pipeline 계약이나 source accessor 구현이 전용 source/trigger의 운영 활성 증거는 아닙니다.
- corporate action의 positive pre/post units가 확인된 분할만 reciprocal quantity/price effect를 만듭니다.
  successor도 결과 instrument를 확인해야 합니다. action 없음과 미평가를 구분하며 정확한 기간/종목 coverage 없이는 absence를 pass로 만들지 않습니다.
- 현금 진단 companion은 성공한 refresh 뒤 기존 flag가 허용할 때 stored-input만 읽습니다. 원래 runtime writer/schema는
  deferred/NULL monetary output만 허용하며 실패가 core/report를 실패시키지 않습니다.
- 현금 관측 이력은 기존 immutable Bronze를 재구성하는 read-only 경로입니다. 새 source나 cash fact를 쓰지 않고 missing/zero·basis·시점·unknown 원인을 유지합니다.
- legacy total reference는 명시 opt-in하는 별도 total-level 경로입니다. [reference 계약](design/reference-history-contract.md)을 따르고 native 우선순위를 바꾸지 않습니다.

현재 exact pipeline/version/activation/alias/실행 가능성은 [계약](../governance/catalog/pipelines.toml),
[배치 adapter](../src/kis_portfolio/adapters/batch/cli.py), [managed 명령](../src/kis_portfolio/services/remote_commands.py),
`get-pipeline-run`의 실제 evidence를 함께 확인합니다. 이 문서는 모든 declared pipeline의 현재 운영을 선언하지 않습니다.

## 실행 결과 해석

예정 slot의 관측 coverage와 그 slot run의 성공 quality는 다릅니다. calendar가 증명한 closed-market quiet window,
아직 도래하지 않은 slot, 진짜 누락 slot, calendar 미확인은 구분합니다. 과거 failed-but-observed run을 지우거나
window가 완전하다는 이유로 run health까지 pass로 바꾸지 않습니다.

운영 확인은 [런북](operations/steady-state-operations-runbook.md), 증상별 행동은 [트러블슈팅](troubleshooting.md),
정확한 코드·회귀 검증은 [기능 지도](traceability.md)에서 찾습니다. source/data 변경은 기존 DGH/backup/restore/실제 client 인수를 그대로 따릅니다.
