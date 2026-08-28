# KIS Portfolio Cost Baseline — 2026-08

> 조사일: 2026-08-28 KST
> Work Item: `WI-002` / delivery item `V2-W0001`
> 범위: GCP 최근 3개 완료월 + 8월 MTD, 현재 runtime cost driver, MotherDuck 저장 사용량
> 변경 경계: read-only 조사. billing export, budget, resource, secret, deployment는 변경하지 않음

## 결론

현재 GCP의 보수적 정상월 기준선은 **월 약 3,700~5,100원**, 운영 판단 기준값은 상단인
**월 5,100원**으로 둔다. 7월 실제 비용 49,473원은 현재 구조의 정상 비용이 아니라 auth와 Remote MCP에
각각 `min-instances=1`을 두었던 warm-service 기간의 비용이다. 두 서비스는 8월 11일 scale-to-zero로
전환됐고, 전환일을 제외한 8월 12~26일 실제 비용은 1,835원으로 이전 동기간보다 88% 감소했다.

- 정상월 7,500원 목표 대비 보수적 headroom: 약 2,400원, 32%
- 월 50,000원 ceiling 대비 headroom: 약 44,900원, 90%
- 8월 월말 forecast 9,980원은 8월 1~11일의 warm-instance 잔여 비용을 포함하므로 정상월 기준선으로
  사용하지 않는다.
- MotherDuck console에서 현재 **Lite Plan (with limits), $0/month**와 미등록 결제수단을 확인했다.
  현재 49 MiB이며 Lite 포함량 10 GB보다 충분히 작아 MotherDuck 비용 baseline은 **월 0원**이다.

## GCP 실제 비용

Cloud Billing Reports의 charge-period, project 1개, credit 포함 net subtotal을 사용했다. Console의 billing
data는 2026-08-26까지 반영돼 있었고 tax는 `—`로 표시됐다.

| 기간 | Actual / forecast | Net cost | 주요 attribution |
| --- | --- | ---: | --- |
| 2026-05 | actual | ₩730 | Secret Manager ₩562, Artifact Registry ₩140, Cloud Run ₩27 |
| 2026-06 | actual | ₩32,706 | Cloud Run ₩30,981, Secret Manager ₩1,526, Artifact Registry ₩199 |
| 2026-07 | actual | ₩49,473 | Cloud Run ₩47,679, Secret Manager ₩1,565, Artifact Registry ₩228 |
| 2026-08-01~26 | actual MTD | ₩9,702 | Cloud Run ₩8,368, Secret Manager ₩1,154, Artifact Registry ₩179 |
| 2026-08-01~31 | console forecast | ₩9,980 | scale-to-zero 전 비용을 포함한 transition month |

5~8월 MTD 합계는 92,610원이다. 완료월 단순 평균은 27,636원이지만 6~7월의 warm-instance 실험 때문에
현재 비용 예측에는 사용하지 않는다.

### 고비용 원인

7월 Cloud Run SKU 중 idle minimum-instance CPU가 22,996원, memory가 19,630원이었다. 합계 42,626원은
7월 전체 비용의 86.2%다. 일반 request CPU·memory net은 약 4,835원, Jobs는 약 116원, network는 약
102원이었다. 즉 5만원에 가까운 비용은 traffic이나 batch가 아니라 **유휴 warm capacity**가 만들었다.

6월도 minimum-instance CPU·memory가 23,206원으로 전체 32,706원의 70.9%였다. 8월에는 8월 11일까지
누적된 minimum-instance 비용이 7,545원 남아 있다.

Cloud Run revision metadata상 auth와 remote의 `minScale=1` revision은 각각 2026-06-13부터 운영됐고,
2026-08-11 11:36 KST 전후 생성된 revision부터 `minScale`이 제거됐다. 현재 두 service는 다음 계약이다.

| Service | Min | Max | Billing | 비고 |
| --- | ---: | ---: | --- | --- |
| `kis-portfolio-auth` | 0 | 1 | request-based default | concurrency 80, timeout 300s |
| `kis-portfolio-remote` | 0 | 1 | request-based default | concurrency 20, timeout 3,600s |

Google Cloud 문서도 request-based service에서 minimum instances를 0으로 두면 idle 시간은 과금되지 않고,
minimum instances를 유지하면 idle rate가 발생한다고 설명한다.

### 현재 정상월 환산

전환일을 제외한 8월 12~26일 15일 actual은 다음과 같다.

| Service | 15일 actual | 30.44일 단순 환산 |
| --- | ---: | ---: |
| Secret Manager | ₩966 | 약 ₩1,960 |
| Cloud Run | ₩720 | 약 ₩1,461 |
| Artifact Registry | ₩149 | 약 ₩302 |
| 합계 | **₩1,835** | **약 ₩3,724** |

배포와 호출이 있었던 최근 8월 21~26일 6일 actual은 1,004원이며 월 환산은 약 5,093원이다. 따라서
정상월 band를 3,700~5,100원으로 잡고, budget 판단에는 상단 5,100원을 사용한다. 8월 초 min-instance가
Cloud Run free-tier credit을 먼저 소비했으므로, 깨끗한 scale-to-zero 월의 net cost는 이보다 낮을 수도
있지만 baseline은 credit에 의존해 낮추지 않는다.

## 고정성 비용과 저장량

### Secret Manager

- 현재 secret resource: 23개
- 7월 billing usage: active secret version 23 version-month, net 1,565원
- 공식 free tier: billing account 전체에서 active version 6개와 월 10,000 access
- 승인된 최대 6개 trust-boundary bundle이 구현되면 version-storage 비용은 free tier 안으로 들어갈 가능성이
  높다. 이 절감은 아직 구현되지 않았으므로 현재 baseline에는 반영하지 않는다.

### Artifact Registry

- 현재 repository size: 2,652.602 MB
- cleanup policy: 없음
- 최근 actual: 월 179~228원

build-once digest와 cleanup policy의 직접 절감액은 작지만 target별 중복 image와 장기 누적을 막는 운영상
가치가 있다. cleanup은 active/rollback digest 확인 뒤 별도 Work Item에서 수행한다.

### Cloud Run Jobs와 Scheduler

현재 Job 3개와 평일 Scheduler 3개가 있다. 7월 Job CPU·memory net은 약 116원이고, 8월 MTD는 약 90원이다.
Scheduler·Cloud Build·Cloud Storage는 현재 report에서 없거나 월 1원 이하 수준이다. batch-first 구성이
비용 병목이라는 증거는 없다.

## MotherDuck과 외부 provider

로그인된 MotherDuck Billing/Plans 화면에서 현재 plan은 `Lite Plan (with limits)`, platform access는
`$0/month`, storage 10 GB와 Pulse 10 CU-hours 포함으로 확인됐다. 화면에는 “Add a credit card to remove
limits”가 표시되어 결제수단도 등록되지 않은 상태다. 따라서 포함 한도 안에서의 현재 MotherDuck actual
baseline은 월 0원이다.

MotherDuck live metadata는 다음 사용량을 보였다.

- `PRAGMA database_size`: `kis_portfolio` 49.0 MiB
- active bytes: 47,984,640
- historical bytes: 102,531,072
- failsafe bytes: 47,058,944
- 합계 약 188.4 MiB, Lite 10 GB 포함량의 약 1.8%

현재 계정에서 query history 조회는 “이 plan에서 제공되지 않으며 Business upgrade가 필요”하다는 응답을
반환한다. compute 사용시간의 세부 counter는 Lite 화면에서 제공되지 않지만, 결제수단 없이 한도형 Lite를
사용하므로 비용 baseline에는 0원으로 반영한다.

### 보이는 두 user database 판정

MotherDuck Home에는 `kis_portfolio`, `my_db`, provider sample인 `sample_data`가 보인다. `sample_data`는
사용자 소유 운영 DB가 아니다. 두 user database를 실제 runtime과 비교한 결과는 다음과 같다.

| Database | 생성 시각 | 객체·row | Runtime reference | 판정 |
| --- | --- | --- | --- | --- |
| `kis_portfolio` | 2026-04-19 | live 27 tables + 3 views, 약 49 MiB | MCP, auth, 세 batch Job 모두 사용 | 유일한 운영 SSOT |
| `my_db` | 2026-04-16 | 5 tables + 1 view, 모든 table 0 rows, 약 256 KiB | code, deploy env, 운영 view reference 없음 | 초기 실험에서 남은 empty legacy database |

`my_db`의 table은 `portfolio_snapshots`, `price_history`, `exchange_rate_history`, `trade_profit_history`,
`schema_migrations`이며 모두 0행이다. 현재 code default와 모든 Cloud Run service/Job의
`MOTHERDUCK_DATABASE`는 `kis_portfolio`다. 따라서 MCP와 batch가 서로 다른 DB에 쓰는 상태가 아니라,
**빈 legacy database가 UI에 남아 분리된 것처럼 보이는 상태**다.

`my_db`는 제거 후보지만 database 삭제는 별도 destructive maintenance Work Item과 사용자 승인을 받아야
한다. 삭제 전 schema-only manifest와 0-row evidence를 보존하고, 삭제 후 MCP·batch smoke와 live inventory를
다시 확인한다.

현재 runtime 환경에는 KIS와 MotherDuck 외 유료 market-data provider가 연결되어 있지 않다. Telegram과
FRED/OpenDART/SEC 등은 V2 source 계획일 뿐 현재 비용에 포함되지 않는다.

## Budget와 측정 방식 결정

1. 월 7,500원 budget과 50/90/100% actual, 100% forecast alert를 유지한다.
2. 월 50,000원 ceiling도 유지한다. 7월은 49,473원으로 ceiling의 98.9%였으므로 warm service 재도입은
   반드시 새 cost ADR/승인을 요구한다.
3. 현재 billing account에는 이 project 하나만 연결돼 있어 Console report로 attribution이 충분하다.
   BigQuery billing export는 아직 없으며, 현재 규모에서는 새 dataset/export를 만들지 않고 월간 수동
   snapshot을 기준으로 삼는다.
4. project가 늘어나거나 월 서비스/SKU 수가 수동 검토 범위를 넘으면 BigQuery detailed export를 다시
   검토한다.
5. 다음 cost review에서는 완전한 scale-to-zero 월 1개를 확보해 5,100원 보수 baseline을 실제 월말 값으로
   교체하고 MotherDuck Lite 한도 도달 여부를 확인한다.

## 증거와 한계

- Cloud Billing Reports: 월별 net cost, credit, service/SKU attribution, forecast
- `gcloud`: budget 7,500원, service/revision scaling, Job/Scheduler, secret count, registry size
- MotherDuck Billing/Plans: Lite Plan with limits, $0/month, 결제수단 미등록
- MotherDuck read-only metadata: database/storage bytes, non-Business query-history restriction,
  `my_db` 5 tables 모두 0 rows
- Cloud Run live env: MCP·auth·세 batch Job 모두 `MOTHERDUCK_DATABASE=kis_portfolio`
- repository: 추가 유료 provider runtime 설정 없음
- 확인하지 않은 것: MotherDuck Lite compute 세부 counter, GCP 카드 청구·세금, 미래 데이터 provider 가격

공식 가격 근거:

- [Cloud Run minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing)
- [MotherDuck pricing](https://motherduck.com/product/pricing/)
