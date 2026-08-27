# 검토 패키지 D — 감시·신호·대화 workflow

> 상태: 사용자 승인 완료, 구현 미승인
> 기준일: 2026-08-27
> 범위: 경보 계산·전송·권한·대화 workflow의 논리 계약
> 비범위: Telegram bot 생성, OAuth 변경, 신호 코드, scheduler, DB·배포 변경

## 1. 한눈에 보는 권고안

| ID | 승인할 권고 | 핵심 이유 |
| --- | --- | --- |
| D-1 | 절대 변화·변동성·포트폴리오 기여도를 결합하고 3년 replay와 shadow 운영으로 보정 | 현재 이력이 임계치 확정에 부족하고 자산별 변동성이 다름 |
| D-2 | 사용자의 2% 규칙을 `Turtle-inspired portfolio risk cap`으로 명명하고 ATR20과 thread stop을 분리 | 전통 Turtle 규칙으로 오인하지 않으면서 계획손실을 총자산에 연결 |
| D-3 | Telegram은 outbound-only, `주의` 이상, 상태 기반 de-duplication으로 운영 | 알림 피로와 민감정보 노출을 줄임 |
| D-4 | Remote MCP OAuth scope를 읽기·수집 trigger·일지 쓰기로 분리 | 예약 작업과 journal write가 조회 권한을 자동 상속하지 않게 함 |
| D-5 | LLM 예약 작업은 보조 trigger·reviewer이며 필수 수집의 SSOT가 아님 | LLM을 사용하지 않아도 데이터가 쌓여야 함 |
| D-6 | 누락 일지·미지정 매도를 review queue로 만들고 사용자 답변만 투자 의도의 권위 원천으로 사용 | LLM이 거래 이유를 사후 창작하는 것을 방지 |
| D-7 | 발표 직전 consensus miss, 회사 guidance 하향과 발표 후 forward 하향 revision을 별도 위험 신호로 운영 | 실적 숫자뿐 아니라 시장 기대의 변화와 전망이 꺾이는 시점을 감지해야 함 |

## 2. 확인된 현황

### 2.1 신호 데이터 준비도

현재 `price_history`와 canonical 총자산 일별 이력은 초기 후보 알고리즘을 실행할 수 있지만, 균형형
임계치를 통계적으로 확정하기에는 부족하다.

| 데이터 | 현재 확인 범위 | 제약 |
| --- | --- | --- |
| KRX 가격 | 1종목, 53거래일 | SMA120·3년 변동성·자산유형별 replay 불가 |
| NAS 가격 | 6종목, 총 785행·321개 날짜 | 종목별 coverage가 불균일하고 현재 보유범위와 일치 보장 없음 |
| canonical 총자산 | 27일 | 포트폴리오 기여·위험 임계치 보정 불가 |

기존 `get-portfolio-anomalies`는 한 계좌의 국내/연금 feeder 총평가액에 단일 z-score를 적용한다. 글로벌
canonical 총자산, 종목 기여도, 보유 에피소드 고점, 자산유형 및 signal state를 합친 새 엔진을 대체하지
못한다.

기존 `get-bollinger-bands`는 cached `close`에 window 20·2σ를 계산하지만 현재 price basis를 명시하지 않고
band 밖을 곧바로 `과매수/과매도`로 표시한다. 이는 승인된 수정주가·보조 context 계약과 다르므로 그대로
운영 경보에 재사용하지 않고 구현 단계에서 metric version과 표현을 교정한다.

### 2.2 현재 인증과 예약 실행

- Remote MCP는 OAuth bearer를 검증하지만 현재 필수 scope는 단일 `mcp:read`다.
- journal write와 collection trigger에 대한 tool별 별도 scope는 아직 없다.
- Cloud Run Jobs와 Scheduler는 국내 주문이력 15:35, 해외 거래이력 07:35 등 일부 수집만 실행한다.
- Telegram sender, 세 평가시각의 감시 job과 delivery ledger는 아직 없다.
- 사용자가 확정한 사용자-facing SSOT는 Remote MCP이며 local stdio MCP는 미래 제품 계약에서 제외된다.

## 3. 권고 계약

### D-1. 균형형 경보 엔진과 calibration gate

#### 3.1.1 공통 severity

모든 신호는 `정상`, `주의`, `경고`, `긴급` 중 하나와 rule version을 반환한다. Telegram은 `주의` 이상만
전송한다. 신호별 severity 중 가장 높은 값을 종목 상태로 사용하되 어떤 규칙이 기여했는지 모두 남긴다.

#### 3.1.2 초기 가드레일

아래 값은 운영 확정치가 아니라 3년 replay 전 과도한 오탐·누락을 막는 **bootstrap boundary**다.

| 신호 | 주의 | 경고 | 긴급 |
| --- | --- | --- | --- |
| 일간 가격 충격 | `abs(return) >= max(3%, 2×vol20)` | `max(5%, 3×vol20)` | `max(8%, 4×vol20)` |
| 일간 포트폴리오 기여 | 절대 0.25%p 이상 | 0.75%p 이상 | 1.50%p 이상 |
| 보유 에피소드 고점 대비 낙폭 | -8% 이하 | -12% 이하 | -20% 이하 |
| 거래량 | 가격 주의 조건과 `volume/SMA20 >= 1.5`가 함께 발생하면 한 단계 강화 | `>= 2.5`면 한 단계 강화 | 단독 긴급 없음 |

ETF·REIT·레버리지·인버스는 동일 절대수치로 비교하지 않는다. `vol20`과 상품구조를 우선하고,
bootstrap 절대 floor는 3년 replay에서 asset class별로 조정한다. 데이터가 20개 미만이면 변동성·거래량
신호를 `insufficient_history`로 두고 절대 변화와 기여도만 평가한다.

#### 3.1.3 추세·RSI·VIX

- `SMA20` 하향 이탈만으로 Telegram을 보내지 않는다. 거래량 급증, 가격 충격 또는 `SMA20 < SMA50`
  전환과 결합하면 `주의` 후보가 된다.
- 수정종가가 `SMA50` 아래이고 `SMA20 < SMA50`, 낙폭 조건이 함께 있으면 `경고` 후보로 강화한다.
- `SMA120` 이탈은 장기 위험 맥락이며 단독 `긴급`이 아니다.
- RSI14의 30/70 이탈은 context다. 가격·거래량·추세 확인 없이 단독 Telegram 신호로 사용하지 않는다.
- 볼린저 밴드는 수정종가 기준 `SMA20 ± 2σ`를 기본으로 계산하고 `%B`, bandwidth와 squeeze/band expansion을
  함께 보존한다. 상·하단 접촉만으로 과매수·과매도 또는 매수·매도를 단정하지 않고, 가격 충격·거래량·
  SMA·RSI와 결합되는 보조 context로만 사용한다.
- VIX 20/30/40은 시장 regime tag 후보이며 개별종목 방향 신호가 아니다. 종목 충격 threshold를
  완화하거나 설명 context를 추가할 수 있지만 VIX만으로 매수·매도 경보를 만들지 않는다.

#### 3.1.4 활성화 gate

1. 승인된 3년 가격 backfill 후 현재 보유 각 자산을 replay한다.
2. bootstrap threshold의 자산별 신호 빈도, 최대 누락과 포트폴리오 기여를 비교한다.
3. 알림 예산은 거래일 평가 slot당 중앙값 2건 이하, 95 percentile 5건 이하를 목표로 한다.
4. 2주 동안 DB에만 저장하는 shadow 운영을 하고 Telegram 전송 표본을 사용자와 검토한다.
5. threshold version과 승인 시점을 기록한 후에만 실제 delivery를 켠다.

### D-2. 2% 포트폴리오 위험 규칙

사용자 요구를 전통 Turtle system 전체와 동일하다고 부르지 않고 **Turtle-inspired 2% portfolio risk cap**으로
정의한다.

```text
risk_budget_krw = canonical_total_assets_krw × 0.02
planned_loss_krw = open_quantity × abs(reference_price - thread_stop_price) × fx
risk_ratio = planned_loss_krw / canonical_total_assets_krw
```

- 사용자·thread가 지정한 stop이 권위 원천이다.
- stop이 없으면 ATR20의 2배(`2N`)를 이용한 참고 stop과 허용수량을 **제안값**으로만 계산하고 risk cap
  준수라고 확정하지 않는다.
- `risk_ratio >= 1.5%`는 주의, `>= 2.0%`는 경고, `>= 2.5%` 또는 stop breach는 긴급 후보로 둔다.
- 분할매수는 같은 thread의 모든 open lot을 합산한다. 여러 thread는 각각과 종목 전체를 모두 본다.
- 총자산·환율·수량·stop의 freshness 또는 completeness가 부족하면 `unknown`, `partial`로 표시하고 자동
  수량 제안을 억제한다.
- 어떤 상태에서도 주문을 실행하지 않는다.

### D-3. Telegram delivery contract

1. 평가시각은 거래일 기준 KST 10:00, 14:30, 16:00이다. 미국장 결과는 10:00에서 한 번만 다룬다.
2. v1 bot은 outbound-only다. Telegram 명령으로 수집·일지·주문을 실행하지 않는다.
3. 메시지는 severity, 종목, 신호·측정값, 포트폴리오 기여, 기준시각, freshness·quality, rule version과
   다음 확인사항을 포함한다.
4. 전체 계좌번호, 총자산 절대액, credential과 raw payload는 보내지 않는다. 계좌가 필요하면 alias만 쓴다.
5. fingerprint는 `(evaluation_slot, market_session, symbol/scope, signal_code, rule_version)`이다. 같은 state는
   재전송하지 않는다.
6. severity 상승, 정상화 후 재진입, 새로운 signal code, 이전 전송 후 의미 있는 threshold band 이동만
   새 경보다.
7. 전송 성공·실패, Telegram message id, payload hash와 retry를 delivery ledger에 남긴다. bot token과
   chat id는 Secret Manager/runtime config에 두고 분석 table에 저장하지 않는다.

Telegram Bot API는 HTTPS 기반 `sendMessage`를 사용한다. destination은 구현 시 owner가 bot 대화를
시작한 뒤 1회 검증하고, 잘못된 chat으로 전송하는 것을 막는 test message 승인 절차를 둔다.

### D-4. Remote MCP scope와 tool 경계

현재 `mcp:read`를 호환 기본값으로 유지하면서 다음 scope를 추가한다.

| Scope | 허용 기능 |
| --- | --- |
| `mcp:read` | portfolio·catalog·analytics·signal·journal 조회 |
| `mcp:collect` | allowlist에 등록된 idempotent collection/pipeline run 요청 |
| `mcp:journal.write` | journal·thread answer와 revision 작성 |
| `offline_access` | refresh token 유지; 업무 권한 아님 |

- route-level bearer 확인 뒤 각 tool에서도 scope를 검사한다.
- `mcp:collect`는 임의 command나 SQL을 받지 않고 관리된 job ID와 제한된 parameter만 받는다.
- journal write는 idempotency key, expected revision과 audit actor가 필수다.
- 주문 scope는 만들지 않는다. disabled order stub도 write scope를 우회할 수 없다.
- 카탈로그는 LLM에 table, metric, freshness, quality와 지원하지 않는 해석을 제공한다.

### D-5. LLM 예약 작업

- 플랫폼 Scheduler가 필수 수집과 10:00·14:30·16:00 평가의 SSOT다.
- LLM 예약 작업은 Remote MCP로 `run-managed-collection`, `run-monitoring-evaluation`,
  `get-journal-review-queue` 같은 allowlisted 작업을 요청할 수 있다.
- 같은 job·logical date·slot은 idempotency key가 같아 중복 canonical fact나 Telegram을 만들지 않는다.
- LLM trigger가 실패하거나 클라이언트 예약 기능이 꺼져도 기본 수집은 계속된다.
- LLM은 실행 결과와 품질을 읽고 설명할 수 있지만 배치 내부 service credential을 받지 않는다.

### D-6. 매매일지 질문 workflow

1. canonical 매수·매도 중 journal, thread 또는 sell allocation이 없는 항목을 review queue에 넣는다.
2. Remote MCP는 다음 검토대상과 이미 알려진 원천 사실만 반환한다.
3. LLM은 매수 이유, 기존 thread 추가매수 여부, 목표·손절·재검토 조건 또는 매도한 thread를 질문한다.
4. 사용자의 답변을 `contemporaneous` 또는 `retrospective`로 구분해 revision으로 저장한다.
5. 사용자가 답하지 않으면 원천 거래는 유지하고 queue를 snooze할 수 있다. LLM이 이유를 생성해 채우지 않는다.
6. 동일 질문의 반복은 `last_asked_at`, snooze와 completion 상태로 억제한다.

### D-7. Consensus surprise와 전망 하향 위험 신호

1. `earnings_consensus_miss`는 C-2의 발표 직전 consensus snapshot과 공식 actual을 비교한다. 매출,
   영업이익·EBIT, EPS 등 metric별 결과를 섞지 않는다.
2. `company_guidance_cut`은 회사가 제시한 guidance의 신규·하향·철회 상태를 원문 사건과 연결한다.
3. `forward_consensus_down_revision`은 발표 뒤 NTM 매출·영업이익·EPS의 7·30·90일 변화를 추적한다.
4. analyst count가 너무 적거나 snapshot이 오래됐거나 provider coverage가 불완전하면 경보를 억제하고
   `insufficient_consensus`로 표시한다.
5. 5%·10% 같은 초기 surprise/revision 구간은 bootstrap 후보일 뿐이다. 종목·업종별 과거 분포와 3년
   replay를 거쳐 severity를 확정한다.
6. Telegram에는 actual, consensus, surprise, analyst count, consensus as-of, forward revision과 source
   quality를 설명하고 매수·매도 지시로 표현하지 않는다.

## 4. 대안과 영향

| 선택 | 장점 | 단점 | 판정 |
| --- | --- | --- | --- |
| 고정 등락률만 사용 | 이해가 쉬움 | 주식·ETF·레버리지 변동성 차이를 무시 | 비권고 |
| z-score만 사용 | 상대변동을 반영 | 짧거나 조용한 표본에서 과민·둔감 | 비권고 |
| 절대+변동성+기여 결합 | 해석성과 자산별 적응을 함께 확보 | replay·버전 관리 필요 | **권고** |
| Telegram inbound command | 편리함 | 권한·오입력·감사 범위 급증 | v1 비권고 |
| 단일 OAuth scope | 구현이 단순 | 조회 client가 write·trigger 권한까지 가질 수 있음 | 비권고 |
| 볼린저 상·하단 접촉 단독 경보 | 익숙하고 계산이 간단 | 추세장에서 band walk와 반복 오탐이 많음 | 비권고 |
| consensus surprise·revision 분리 | 기대치 충족과 전망 변화의 시점을 재현 | licensed provider와 point-in-time snapshot 필요 | **권고** |

## 5. 승인할 결정

| ID | 결정 | 승인 상태 |
| --- | --- | --- |
| D-1 | bootstrap 경보식, Bollinger 보조 context, 3년 replay, 2주 shadow calibration gate | 승인 (`DEC-026`) |
| D-2 | Turtle-inspired 2% risk cap과 ATR20 제안값 | 승인 (`DEC-027`) |
| D-3 | outbound-only Telegram, 최소 payload와 state de-duplication | 승인 (`DEC-028`) |
| D-4 | `mcp:read`·`mcp:collect`·`mcp:journal.write` 분리 | 승인 (`DEC-029`) |
| D-5 | platform SSOT + LLM 예약 작업 보조 trigger | 승인 (`DEC-030`) |
| D-6 | 사용자 답변 중심 journal review queue | 승인 (`DEC-031`) |
| D-7 | point-in-time consensus miss·guidance cut·forward 하향 위험 신호 | 승인 (`DEC-032`) |

2026-08-27 사용자 피드백을 포함해 모두 승인했다. 구현은 시작하지 않는다. bootstrap 숫자는 replay
결과가 아니라 활성화 전 검토 기준이며, 운영 threshold 확정은 별도 구현·검증 단계의 acceptance gate다.

## 6. 공식 근거

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Cboe VIX 설명과 시장 데이터](https://www.cboe.com/tradable-products/vix)
- [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs)
