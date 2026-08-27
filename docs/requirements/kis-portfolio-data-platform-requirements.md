# KIS Portfolio 데이터 플랫폼 요구사항

> 상태: 요구사항 검토용 초안
> 제품명: KIS Portfolio (`kis-portfolio`)
> 문서 범위: 요구사항 분석만 포함
> 구현 상태: 미승인. 이 초안은 코드, DB, 배포 또는 기존 아키텍처 변경을 승인하지 않는다.

## 최근 승인

### 가격 이력 backfill 권고안

- 현재 보유종목의 최근 3년 일봉 OHLCV를 최초 1회 backfill한다.
- 이후에는 거래일마다 일봉을 증분 수집한다.
- 신규 종목이 포트폴리오에 편입되면 해당 종목도 최근 3년 일봉을 backfill한다.
- 보유종목, 현금 및 총자산 스냅샷은 관리되는 시스템의 운영 시작일부터 직접 관측값으로 누적한다.
- 시스템 운영 이전의 보유 이력은 신뢰할 수 있는 거래내역으로 재구성 가능한 범위에서만 만들고,
  직접 관측값과 구분해 `reconstructed` 또는 이에 준하는 상태로 표시한다.

**권고 이유**

- 다양한 rolling-high 기간과 보유기간 고점 대비 낙폭을 검토할 수 있다.
- 단기·중기 추세를 계산하고 서로 다른 시장 국면에서 경보 임계치를 검토할 수 있다.
- 이동평균, RSI와 거래량 지표의 후보 계산식을 과거 데이터로 비교할 수 있다.
- 주식, ETF, REIT별 경보 민감도를 과거 데이터로 시뮬레이션할 최소한의 여유를 제공한다.
- 현재 보유종목으로 범위를 제한해 불필요한 전 종목 수집을 피한다.

**승인 결과**

2026-08-27 사용자가 최근 3년 일봉 backfill 권고안을 수용했다. 이 승인은 논리적 수집 범위를
확정한 것이며, 아직 API 호출이나 DB 적재를 승인한 것은 아니다. 용량 사전검토 결과는 6.2절에
기록한다.

### 평단가와 매수 lot·투자 thread 병렬 분석

- 계좌 및 종목의 기본 손익 표현은 증권사가 제공하는 평단가 기반 포지션을 유지한다.
- 각 매수 사실은 별도의 매수 lot으로 보존하고, 평단가 집계 과정에서 개별 이력을 잃지 않는다.
- 하나 이상의 매수 lot과 관련 매도를 같은 투자 판단의 `trade thread`로 묶을 수 있어야 한다.
- 시스템은 포지션 전체 손익과 lot·thread별 손익을 동시에 제공해야 한다.
- 증권사의 공식 손익과 내부 lot·thread 분석 손익을 명확히 구분한다.
- 원천 거래가 불완전한 경우 직접 관측, 사용자 입력, 재구성 및 추정 상태를 구분한다.

**승인 결과**

2026-08-27 사용자는 평단가 방식을 기본으로 유지하면서 매수 lot과 투자 thread 기반 분석을 별도
트랙으로 제공하는 방향을 승인했다. 이 승인은 논리적 요구와 개념 모델을 확정한 것이며, 물리 DB
schema, 과거 거래 backfill, 매도 lot 배분 규칙 또는 MCP 인터페이스 구현을 승인한 것은 아니다.

## 통합 승인 완료: 패키지 C·D·E

사용자 요청에 따라 남은 조사를 먼저 완료한 뒤 다음 세 패키지를 피드백과 함께 일괄 승인했다.

- [패키지 C — 실적·가치·배당·매크로](./review-package-c-fundamentals-dividend-macro.md)
- [패키지 D — 감시·신호·대화 workflow](./review-package-d-monitoring-conversation.md)
- [패키지 E — 데이터 플랫폼과 운영](./review-package-e-data-platform-operations.md)

| 패키지 | 승인된 결정 | 핵심 권고 |
| --- | ---: | --- |
| C | DEC-020~DEC-025 | OpenDART·SEC actual, point-in-time consensus, 배당 3상태, 표준 macro profile, licensed report gate |
| D | DEC-026~DEC-032 | replay 기반 경보, Bollinger 보조지표, 2% risk cap, Telegram, consensus 위험 신호, journal review |
| E | DEC-033~DEC-041 | Remote MCP SSOT, scale-to-zero·batch-first, 월 5만원 상한, versioned schema, off-site recovery |

이 승인은 논리 요구사항과 아키텍처 제약을 확정한 것이다. 구현·적재·배포는 시작하지 않고 다음 단계의
구현계획, 비용 baseline과 migration 순서를 별도로 검토한다.

## 1. 문서 목적

이 문서는 KIS Portfolio를 포트폴리오 조회 중심 MCP에서 지속적으로 데이터를 수집하고 관리하는
개인 투자 데이터 플랫폼으로 발전시키기 위한 요구사항 기준선이다.

다음을 구분해 누적 기록한다.

- 사용자가 명시적으로 확정한 결정
- 제안 후 사용자가 수용한 작업 가정
- 데이터 제품 후보와 논리적 원천 데이터 요구
- 비기능 및 데이터 거버넌스 요구사항
- 추가 검토가 필요한 미결정 사항
- 요구사항과 구현 대안 사이의 경계

이 문서에 기존 코드, MotherDuck 기능, Cloud Run Job 또는 MCP 도구가 언급되어도 별도 승인 전에는
그 기술이나 구현을 채택한 것으로 보지 않는다.

## 2. 제품 비전

KIS Portfolio는 포트폴리오 상태를 이해하고 중요한 변화를 감지하며, 거래 판단의 근거를 보존하고,
Remote MCP를 통해 재현 가능한 대화형 분석을 수행하는 데 필요한 데이터를 지속적으로 축적해야 한다.

목표 제품은 다음과 같다.

> 자산과 사건을 기록하고, 위험과 기회를 감시하며, Remote MCP를 통해 근거 있는 분석을 제공하는
> 개인 투자 의사결정 지원 데이터 플랫폼

이 시스템은 자동매매 시스템이 아니다. 신호와 분석은 사람의 의사결정을 지원하지만 실제 주문을
승인하거나 실행하지 않는다.

## 3. 문제와 동기

### 3.1 포트폴리오 감시

- 사용자는 현업 중 주식시장을 계속 모니터링할 수 없다.
- 사용자가 확인하기 전에 보유종목이 크게 하락하거나 상승할 수 있다.
- 하락 시 추세 형성 여부, 낙폭, 전체 포트폴리오에 가장 큰 영향을 준 종목을 확인하기 어렵다.
- 상승 시 언제 비중을 줄이거나 청산할지 판단할 일관된 근거가 없다.
- 총자산이 장기적으로 상승, 정체 또는 하락 중인지 파악하기 어렵다.

### 3.2 기회 감시

- 사용자가 관심을 두지 않는 동안 관심종목이 크게 움직일 수 있다.
- 장기적으로는 놓친 기회와 실제 보유종목 및 과거 의사결정을 비교하고 싶다.

### 3.3 펀더멘털 및 가치평가

- 시장 리포트, 분기별 실적과 사업 전망 변화를 추적하고 싶다.
- 실적 발표와 명시적인 전망 데이터 또는 가정을 바탕으로 12개월 forward 전망을 계속 갱신하고 싶다.
- 매수와 매도 판단을 돕는 valuation 또는 risk/reward band를 만들고 싶다.

### 3.4 배당 수익

- 월별 배당 수익 이력과 기간별 증감 현황을 관리하고 싶다.

### 3.5 거래 기억과 회고

- 거래와 영속적인 매매일지를 연결하고 싶다.
- 평단가로 집계된 종목 손익뿐 아니라 각 매수 판단의 개별 손익과 손실 구간을 확인하고 싶다.
- 같은 종목의 최초 매수, 추가매수 및 서로 다른 투자 논리를 구분해 사후 평가하고 싶다.
- 매수 후 최대 유리·불리 구간과 고점에서 반납한 수익을 추적해 반복되는 판단 오류를 확인하고 싶다.
- LLM이 거래내역을 확인하고, 일지가 없는 거래에 대해 거래 이유를 질문한 뒤 일지를 작성하거나
  기존 일지를 수정할 수 있어야 한다.
- 일지가 누락된 거래를 나중에 예약 작업으로 찾아낼 수 있어야 한다.
- 사용자와 LLM이 이후에 거래와 일지를 함께 검토할 수 있어야 한다.

### 3.6 대화형 및 직접 분석

- 사용자는 필요할 때 MotherDuck에 직접 접속해 자료를 추출하고 그래프를 만들 수 있어야 한다.
- Remote MCP를 통한 LLM 대화로도 동일한 관리 데이터를 분석할 수 있어야 한다.
- MCP는 LLM이 테이블과 지표의 의미를 추측하지 않도록 카탈로그, 지표 정의, lineage, freshness,
  품질 메타데이터를 제공해야 한다.
- LLM과 대화하지 않는 동안에도 데이터 수집은 계속되어야 한다.

### 3.7 위험 신호와 시장 맥락

- 실적, 전망, 가치평가 밴드를 바탕으로 investor 관점의 매수·매도 판단을 지원하고 싶다.
- Turtle 방식의 총자산 위험 규칙, RSI, VIX 등을 이용한 trader 관점의 신호도 원한다.
- 보유종목과 연관된 매크로 사건을 보존하고 가격·포트폴리오 변화와의 시간적 관계를 분석하고 싶다.
- 사건과 가격 변동의 관찰된 연관성과 인과관계 주장은 구분해야 한다.

## 4. 확정된 제품 결정

### DEC-001: 제품명은 KIS Portfolio를 유지한다

- 제품명은 **KIS Portfolio**다.
- 시스템 식별자는 `kis-portfolio`를 유지한다.
- `Vault Chancellor`를 별도 앱 이름으로 채택하지 않는다.

### DEC-002: Remote MCP가 유일한 사용자-facing MCP SSOT다

- OAuth로 보호되는 Remote MCP만 지원되는 사용자-facing MCP 표면으로 둔다.
- iPhone 등 원격 사용자가 Mac 로컬 MCP 실행 안내를 받지 않도록 해야 한다.
- local stdio MCP는 미래 사용자-facing 제품 계약에 포함하지 않는다.
- 개발·테스트에서 내부 코드를 어떻게 재사용할지는 후속 아키텍처 단계의 구현 결정이다.

### DEC-003: 수집은 LLM 활동과 독립적이어야 한다

- 사용자가 LLM과 대화하지 않아도 필요한 데이터가 계속 축적되어야 한다.
- 플랫폼 기반 정기 수집을 일급 요구사항으로 둔다.
- 더 최신 데이터가 필요할 때 on-demand 갱신을 보완적으로 사용할 수 있다.

### DEC-004: LLM 예약 작업이 Remote MCP를 통해 관리된 작업을 요청할 수 있어야 한다

- LLM 예약 작업은 Remote MCP를 통해 승인된 수집, 분석, 브리핑, 품질 점검 또는 일지 검토를
  요청할 수 있어야 한다.
- 이 경로는 추가 trigger이며 지속 수집을 보장하는 유일한 경로가 아니다.
- 구체적인 MCP 인터페이스, 권한, orchestration 기술은 후속 설계에서 결정한다.

### DEC-005: 최초 감시 범위

- 국내 및 미국 시장의 현재 보유 상장상품 전체를 감시한다.
- 주식, ETF, REIT를 포함한다.
- 단일 임계치를 공통 적용하지 않고 자산 유형별로 다른 경보 기준을 둘 수 있어야 한다.
- 미보유 관심종목은 최초 릴리스 범위에서 제외한다.

### DEC-006: 선제 알림 채널은 Telegram이다

- 선제적 포트폴리오 알림은 Telegram으로 전달한다.
- 평가 시간대는 `Asia/Seoul`을 사용한다.
- 평가 시각은 적용 가능한 평일·시장일의 10:00, 14:30, 16:00이다.
- Telegram에는 `주의` 이상만 전송한다.
- 정상 결과도 DB에 저장해 나중에 조회할 수 있어야 한다.

### DEC-007: 최초 경보 민감도는 균형형이다

- 일상적인 시장 잡음은 제외하면서 의미 있는 변화를 포착하는 균형형 민감도를 사용한다.
- 정확한 수치 임계치는 아직 확정하지 않았다.
- 임계치는 과거 데이터에 대한 시뮬레이션과 검토 후 확정해야 한다.

### DEC-008: 자동 주문을 수행하지 않는다

- 모든 신호는 의사결정 지원용이다.
- 감시, 분석, 매매일지, 예약 작업 또는 MCP 요구사항은 실제 주문 실행 권한을 포함하지 않는다.

### DEC-009: 평단가와 매수 lot·투자 thread 분석을 병렬로 유지한다

- 계좌·종목 단위의 기본 포지션 표현과 공식 reconciliation은 증권사 평단가를 기준으로 한다.
- 모든 canonical 매수 사실은 개별 매수 lot으로 보존한다.
- 매수 lot은 투자 판단 단위인 `trade thread`에 연결할 수 있으며, 하나의 thread는 여러 번의
  분할매수·추가매수와 관련 매도를 포함할 수 있다.
- 신규 매수는 기본적으로 새 thread 후보가 되며, 사용자 또는 LLM과의 명시적 확인을 통해 기존
  thread의 추가매수로 연결할 수 있다.
- lot·thread 분석은 공식 세무 또는 증권사 손익을 대체하지 않는 개인 분석 트랙이다.
- 원천 체결과 사용자가 작성한 매매일지는 삭제하거나 덮어쓰지 않고 변경 이력을 보존한다.

### DEC-010: v1 purchase lot은 체결된 매수 주문 단위로 한다

- 총체결수량이 0보다 큰 매수 주문 1건을 v1의 purchase lot 1건으로 정의한다.
- 국내·해외 주문체결 원천이 제공하는 주문번호, 주문시각, 평균체결가와 총체결수량을 사용한다.
- 한 주문 안의 개별 fill을 구분할 수 없는 경우 평균체결가와 총체결수량을 사용하되, 추정 fill을
  생성하지 않는다.
- 내부 identity는 계좌·상품코드·주문일·주문채번지점번호·주문번호를 기본으로 하고, 해외는 거래소를
  추가한다. 사람이 읽는 `display_key`는 내부 identity와 분리한다.
- 하나의 trade thread는 사용자의 투자 판단에 따라 하나 이상의 주문 단위 purchase lot을 포함한다.
- 향후 체결번호·체결시각·개별 체결수량을 제공하는 신뢰 가능한 원천이 확보되면 fill을 하위 grain으로
  확장할 수 있다.
- 이 결정은 논리 데이터 계약이며 물리 schema, 수집 코드, backfill 및 배포를 승인하지 않는다.

### DEC-011: IRP 최근 거래는 provisional 상태와 지연 reconciliation으로 관리한다

- 3개월 이전 IRP 주문은 `CTSC9215R`에서 확인한 원천 사실로 지연 수집한다.
- 공통 최근구간 API가 제공하지 못하는 기간은 최신 잔고 기반 `provisional` reconciliation 상태로 둔다.
- 사용자 보완은 `manual` 근거로 보존하고, 거래가 과거 endpoint에 나타나면 `actual` 또는
  `reconciliation_exception`으로 정정한다.
- 날짜가 없는 IRP 현재 주문상태 API는 보조 관측으로만 사용하며 전체 거래 이력을 대표하지 않는다.

### DEC-012: 거래내역도 최근 3년을 초도 backfill한다

- 국내·해외 주문·거래내역의 최초 backfill 범위를 가격 일봉과 같은 최근 3년으로 한다.
- 실제 주문은 purchase lot 또는 sell event로 보존하고, replay 수량과 현재 잔고가 맞으며 예외가 없으면
  파생 상태를 `reconstructed`로 표시한다.
- 차이는 실제 주문을 덮어쓰지 않고 잔여수량만 `inferred_opening`으로 만들며, 설명 불가능하거나 음수인
  잔여분은 `reconciliation_exception`으로 둔다.
- 현재 증권사 평단가를 과거 실제 매수가격으로 소급하지 않는다.

### DEC-013: 해외 주문과 비용·환율 거래사건은 가역적인 후보 관계로 연결한다

- 주문체결과 일별거래 row를 서로 다른 immutable 원천 사건으로 보존한다.
- 계좌·시장·거래일·종목·매매방향·수량과 가격·금액 허용오차를 통과한 후보가 하나일 때만
  `derived_candidate` link를 만든다.
- 후보가 없거나 둘 이상이면 자동 연결하지 않고 review queue에 둔다.
- candidate link는 분석에 사용할 수 있지만 raw row를 병합·삭제하지 않으며, 더 강한 근거가 생기면
  상태와 변경 이력을 보존하면서 승격한다.

### DEC-014: 미지정 매도는 FIFO로 임시 배분하고 LLM이 확인한다

- 사용자가 지정한 lot·thread 연결을 최우선 `explicit` 근거로 사용한다.
- thread만 지정하면 그 thread의 오래된 open lot부터 FIFO로 배분한다.
- 지정이 없으면 같은 계좌·종목의 전체 open lot에 FIFO를 적용하되 `inferred`로 표시한다.
- LLM은 다음 예약 검토에서 축소·종료한 투자 판단을 질문하고, 답변은 원천 사건을 변경하지 않는
  append-only allocation revision으로 기록한다.
- 내부 배분 손익은 증권사 공식 평단가·실현손익·세무기록과 분리한다.

### DEC-015: 수정주가를 분석 기준으로 하고 원주가와 provenance를 병렬 보존한다

- Bronze에는 vendor raw 응답, 요청한 조정 옵션, 요청 범위, page와 수집 시각을 보존한다.
- Silver 일봉은 수정주가와 원주가를 함께 표현할 수 있는 price basis를 가진다.
- 수익률, 이동평균, RSI, 고점과 낙폭의 기본 입력은 수정주가 OHLC로 한다.
- 거래내역 reconciliation, 실제 체결가 대조와 원천 감사에는 원주가를 사용한다.
- 거래량과 거래대금은 vendor 관측값으로 보존하고 corporate action의 영향을 품질 상태로 표시한다.

### DEC-016: v1 추세·거래량·RSI 계산 계약을 고정한다

- 추세의 기본 이동평균은 수정 종가의 `SMA20`, `SMA50`, `SMA120`이다.
- 거래량은 원거래량, `SMA20(volume)`과 `volume / SMA20(volume)`을 기본 지표로 한다.
- RSI는 일봉 수정 종가와 Wilder smoothing을 사용하는 `RSI14`를 기본으로 한다.
- `RSI20`은 비교·연구용으로 허용하지만 기본 경보 입력으로 사용하지 않는다.
- `RSI50`과 `RSI120`은 기본 생성하지 않으며 50·120일 추세는 이동평균이 담당한다.
- 관측이 부족한 지표는 `insufficient_history`로 표시하고 계산 버전과 price basis를 노출한다.

### DEC-017: 보유 에피소드 고점을 주 지표로 하고 ATH 명칭을 엄격히 사용한다

- 같은 계좌·종목의 수량이 0보다 커진 때부터 다시 0이 될 때까지를 보유 에피소드로 정의한다.
- 전량 매도 후 재매수하면 새 에피소드로 시작한다.
- 포지션, purchase lot과 trade thread는 각 시작일부터 수정주가 일중 고가의 최고값을 별도로 가진다.
- 단기 맥락은 20·50·120거래일 rolling high와 대비 낙폭으로 제공한다.
- 상장 이후 전 기간을 완전하게 수집한 경우에만 `all_time_high`라는 이름을 사용한다.
- 승인된 3년 구간의 최고값은 `available_history_high_3y`이며, 252거래일 고점은 v1 기본 경보에서 제외한다.

### DEC-018: KRX·운용사 PDF를 ETF 구성의 canonical source로 사용한다

- 국내 상장 ETF의 canonical 구성종목 원천은 KRX PDF 또는 동일한 운용사 공식 PDF다.
- KIS 구성종목시세는 당일 상위 구성종목 확인과 cross-check에만 사용하고 완전성 source로 사용하지 않는다.
- 구성 row는 주식뿐 아니라 현금, 채권, 선물, swap, ETN과 nested ETF를 원래 유형으로 보존한다.
- nested ETF는 최대 3단계, cycle guard와 source-date 일치 규칙으로 펼치며 미해결 비중은
  `unexpanded_residual`로 남긴다.
- 향후 미국 상장 ETF가 편입되면 공식 issuer source를 확인할 때까지 look-through를
  `unsupported_source`로 표시한다.

### DEC-019: ETF 구성종목 일별 snapshot을 최근 3년 범위로 보존한다

- 거래일마다 최신 공개 PDF를 한 번 수집하고 기준일, 수집시각, source URL과 hash를 보존한다.
- 10:00 평가 전 새 PDF가 없으면 직전본과 age를 명시한다.
- ETF 구성종목 일별 snapshot의 기본 retention과 초도 backfill 목표는 최근 3년이다.
- 원본 binary의 물리 보존 위치와 change-only 최적화는 패키지 E에서 결정한다.
- 이 결정은 논리 수집 계약이며 실제 자동수집, schema, backfill 또는 배포를 승인하지 않는다.

### DEC-020~DEC-025: 실적·가치·배당·매크로 계약

- `DEC-020`: 국내 actual은 OpenDART, 미국 actual은 SEC EDGAR를 canonical source로 하고 5년·8분기를
  최초 적재 목표로 한다.
- `DEC-021`: consensus, 사용자 시나리오와 model 시나리오를 분리하고 발표 직전 consensus 분포·analyst
  count·revision을 point-in-time snapshot으로 보존한다. 미국 licensed consensus gap을 숨기지 않는다.
- `DEC-022`: fundamental valuation band와 trade thread의 risk/reward band를 별도 데이터 제품으로 둔다.
- `DEC-023`: 배당을 declared·entitled·received·corrected 상태로 보존하고 해외·IRP 실수령 gap에는
  provenance가 있는 manual import를 허용한다.
- `DEC-024`: ECOS·FRED/ALFRED·Cboe 기반 `macro_profile_v1`과 versioned regime 해석을 사용하고, 신규
  지표는 source·metric contract 승인으로 확장한다.
- `DEC-025`: 리서치는 이용권한 확인 전 metadata·link·허용된 구조화 사실만 보존한다.

### DEC-026~DEC-032: 감시·신호·대화 계약

- `DEC-026`: 가격 충격·변동성·기여도·추세를 결합하고 3년 replay와 2주 shadow를 통과한 rule version만
  실제 경보에 사용한다. 볼린저 `SMA20 ± 2σ`, `%B`, bandwidth는 단독 신호가 아닌 보조 context다.
- `DEC-027`: thread stop을 우선하는 Turtle-inspired 2% portfolio risk cap을 사용하고 ATR20 `2N`은
  stop이 없을 때의 제안값으로만 사용한다.
- `DEC-028`: Telegram은 outbound-only, `주의` 이상, 최소 민감정보와 상태 기반 de-duplication으로 운영한다.
- `DEC-029`: Remote MCP 권한을 `mcp:read`, `mcp:collect`, `mcp:journal.write`로 분리하고 주문 scope는 두지 않는다.
- `DEC-030`: 플랫폼 Scheduler가 필수 수집의 SSOT이며 LLM 예약 작업은 allowlisted 보조 trigger다.
- `DEC-031`: 누락 journal·thread·sell allocation은 review queue로 만들고 사용자 답변만 투자 의도의
  권위 원천으로 기록한다.
- `DEC-032`: 발표 직전 consensus miss, 회사 guidance 하향과 발표 후 NTM consensus 하향 revision을
  point-in-time 위험 신호로 관리한다.

### DEC-033~DEC-041: 데이터 플랫폼·운영·비용 계약

- `DEC-033`: source client, shared core, Remote MCP, batch runner, data plane 경계를 유지하고 별도 REST
  microservice는 실제 consumer 요구가 생길 때만 추가한다.
- `DEC-034`: Remote MCP만 사용자-facing MCP SSOT로 두고 local stdio는 제품표면에서 단계적으로 퇴역한다.
- `DEC-035`: Cloud Run Jobs와 Scheduler를 primary orchestrator로 유지하고 MotherDuck Flights는 보류한다.
- `DEC-036`: live drift를 먼저 통합한 뒤 versioned migration과 검증을 통해 Bronze·Silver·Gold·Control·
  Security를 물리 분리한다.
- `DEC-037`: typed row는 MotherDuck, content-addressed 원문은 private object storage, 복구본은 off-site
  Parquet에 둔다.
- `DEC-038`: source·pipeline·run·watermark·quality·metric·lineage catalog를 Remote MCP와 직접 SQL이
  공유한다.
- `DEC-039`: 3년은 최소 hot history와 초도 적재 범위이며 canonical 사실은 자동 삭제하지 않는다.
- `DEC-040`: 매일 off-site Parquet, 분기 복원 rehearsal, RPO 24시간·RTO 4시간을 목표로 한다.
- `DEC-041`: 전체 월 실제 지출 상한은 50,000원이다. request-based `min-instances=0`, 명시적 max instances,
  실행 후 종료하는 batch job을 기본으로 하며 상시 worker·dedicated compute를 채택하지 않는다. 비용은
  70%·85%·100% 단계로 관측·gate하고 신규 구성은 정상월·backfill월·장애월 비용을 먼저 제시한다.

DEC-020~DEC-041도 구현 승인이 아니다. 상세 grain, 품질 gate와 대안은 각 검토 패키지가 소유한다.

## 5. 첫 번째 데이터 제품: 보유종목 감시 v1

`보유종목 감시 v1`은 데이터 제품 작업명이며 KIS Portfolio 앱 이름을 대체하지 않는다.

### 5.1 목적

국내·미국 보유종목의 중요한 변화를 사용자가 조사할 수 있을 만큼 빠르게 감지하고 설명하며,
모든 평가 결과를 이후 분석을 위해 보존한다.

### 5.2 평가 시각

| 시각(KST) | 대상과 목적 |
| --- | --- |
| 10:00 | 직전 미국장 마감 요약 및 국내장 오전 상태 평가 |
| 14:30 | 국내장 마감 전 위험·변동 평가 |
| 16:00 | 국내장 마감 평가 및 일일 결과 |

미국 보유종목의 일일 마감 결과는 10:00 평가에서 다룬다. 같은 미국장 마감 신호를 14:30이나
16:00에 반복 전송하지 않는다.

### 5.3 최초 감지 신호

첫 릴리스는 다음 네 가지를 모두 포함한다.

1. 전일 종가 대비 등락
2. 최근 고점 대비 낙폭
3. 해당 종목이 전체 포트폴리오 손익에 미친 기여도
4. 단기·중기 추세 변화

RSI, VIX, Turtle 위험 규칙 등은 원천 데이터와 계산 계약을 승인한 뒤 후속 범위에서 다룬다.

### 5.4 심각도와 전송 정책

- `정상`: 저장하지만 Telegram으로 전송하지 않는다.
- `주의`: Telegram으로 전송한다.
- `경고`: 더 강한 강조와 함께 전송한다.
- `긴급`: 최고 우선순위 상태로 전송한다.

변화가 없는 같은 신호를 반복 전송하지 않는다. 심각도가 높아지거나 상태가 유의미하게 바뀌면
다시 전송할 수 있다. 정확한 중복 억제 및 재알림 시간은 후속 설계에서 정한다.

### 5.5 설명 요구사항

저장된 평가와 전송된 경보에서 다음 정보를 확인할 수 있어야 한다.

- 계좌정보를 안전하게 처리한 종목 식별정보
- 시장과 자산 유형
- 평가 시각과 원천 데이터 기준 시각
- 가격 또는 포트폴리오 변동
- 최근 고점 대비 낙폭
- 포트폴리오 손익 기여도
- 추세 상태와 변화
- 심각도 및 해당 심각도를 만든 규칙
- 데이터 freshness, 누락 및 품질 상태
- 계산을 재현할 수 있는 provenance

### 5.6 인수 기준 방향

수치 기반 인수 기준은 아직 미확정이다. 최종 인수 기준에는 적어도 다음이 포함되어야 한다.

- 대상 보유종목 전체를 시장별 평가 시각에 맞춰 평가한다.
- 정상 결과도 알림 여부와 관계없이 보존한다.
- `주의` 이상이면 Telegram 경보가 생성된다.
- 변화 없는 같은 경보를 불필요하게 반복하지 않는다.
- 결과에서 기준 시각, 규칙, 입력 및 품질 상태를 확인할 수 있다.
- 누락되거나 오래된 입력을 완전하고 최신인 결과처럼 표시하지 않는다.

## 6. 보유종목 감시 v1 논리적 데이터 장바구니

다음은 논리적 데이터 요구 목록이다. 아직 정확한 KIS endpoint, TR_ID, 외부 제공자, connector,
물리 테이블 또는 구현 주기를 선택한 것이 아니다.

| 수집 후보 | 분석 목적 | 최초 수집 방향 | 상태 |
| --- | --- | --- | --- |
| 계좌별 보유종목·수량·매입·평가 정보 | 감시 대상과 포트폴리오 비중 파악 | 10:00, 14:30, 16:00 | 선택 |
| 계좌별 현금·예수금 | 총자산과 현금 비중 계산 | 동일 평가 시각 | 선택 |
| 보유종목 현재가와 직전 종가 | 당일 등락과 손익 기여도 계산 | 적용 가능한 평가 시각 | 선택 |
| 일별 OHLCV 가격 이력 | 고점 대비 낙폭과 단기·중기 추세 | 최근 3년 backfill 후 일별 증분 | 선택, 3년 승인 |
| 환율 | 미국 자산과 현금의 일관된 원화 환산 | 적용 가능한 평가 시각 및 일별 보존 | 선택 |
| 종목 마스터 | 시장, 통화, 주식·ETF·REIT 구분 | 정기적인 관리 동기화 | 선택 |
| 국내·미국 시장 캘린더 | 휴장일과 마감 기준 결정 | 연 단위·기준정보 동기화 | 선택 |
| 국내·해외 주문·체결 이력 | 보유량 변화, 매수 lot과 매도 연결, 투자 thread 손익 설명 | 일별 증분 | 선택 |
| 입출금·환전·배당·세금·수수료 | 시장 손익과 외부 현금흐름 분리 | 가능한 범위에서 일별 증분 | 선택 |
| 수집 실행·데이터 품질 기록 | 누락, 실패, 지연, 중복 판정 | 모든 수집·평가 실행 | 선택 |
| ETF 구성종목과 비중 | ETF 내부 경제적 노출 분석 | 기준일 스냅샷, 실제 주기는 원천에 따라 결정 | 선택 |

### 6.1 가격 이력 backfill 결정

승인된 논리적 범위는 다음과 같다.

- 현재 보유종목은 최근 3년 일봉을 backfill한다.
- 신규 편입 종목도 편입 시 동일하게 최근 3년 일봉을 backfill한다.
- 보유, 현금, 총자산 관측은 관리되는 시스템 운영 시작일부터 계속 누적한다.
- 과거 보유 이력은 신뢰할 수 있는 거래 데이터가 허용하는 범위에서만 재구성한다.
- 재구성 또는 추정 이력은 직접 관측 이력과 명확히 구분한다.

2026-08-27 사용자가 이 범위를 승인했다. 구현 전에는 정확한 원천 제공 범위, 호출량, 적재 방식과
초도 적재 검증 계획을 별도로 승인받아야 한다.

### 6.2 MotherDuck 용량 사전검토

2026-08-27 운영 MotherDuck을 계좌번호와 금액 없이 read-only로 점검한 기준은 다음과 같다.

- 현재 `kis_portfolio` database size: 약 49 MiB
- 최신 보유종목: 21개 symbol, 26개 계좌별 보유 row
- 자산 유형: 주식 7개, ETF 14개
- 현재 `price_history`: 약 838 rows
- 현재 관련 누적량: `portfolio_snapshots` 267 rows, `asset_overview_snapshots` 48 rows,
  `asset_holding_snapshots` 1,619 rows

현재 보유종목 21개에 최근 3년 거래일을 종목당 약 756일로 가정하면 최초 가격 적재량은 약
15,876 rows다. OHLCV typed column과 key/index 여유를 보수적으로 고려해도 계획상 10 MiB 미만의
증가로 본다. 실제 압축 크기는 pilot 적재 후 다시 측정해야 한다.

하루 3회, 연 252일, 현재 26개 보유 row를 단순 적용하면 정규화 보유 스냅샷은 연간 약
19,656 rows다. 현재 raw JSON 평균 길이와 canonical overview payload를 함께 감안한 핵심 감시 데이터의
계획 범위는 대략 연 100 MiB 미만이다. 이 값은 구현 용량 보장이 아니라 retention 결정을 위한
사전 추정치다.

용량의 주요 변수는 가격 이력이 아니라 ETF 구성종목 이력이다. 현재 ETF 14개에 대해 평균 구성종목
수를 각각 100, 500, 1,000개로 가정해 매 거래일 전체 스냅샷을 저장하면 다음 행 수가 발생한다.

| ETF당 평균 구성종목 | 연간 구성종목 rows | 압축·index 포함 계획 범위 |
| ---: | ---: | ---: |
| 100 | 약 352,800 | 약 50-110 MiB/년 |
| 500 | 약 1,764,000 | 약 260-530 MiB/년 |
| 1,000 | 약 3,528,000 | 약 530 MiB-1.1 GiB/년 |

실제 크기는 원천 필드, symbol 길이, index, 중복률과 압축률에 따라 달라진다. 소스 카탈로그 조사에서
실제 ETF 구성종목 수와 제공 주기를 확인한 뒤 한 달 pilot로 row당 압축 크기를 측정해야 한다.

용량 관리 방향은 다음과 같다.

- 3년 OHLCV backfill은 용량상 수용한다.
- ETF 구성은 기준일을 보존하되, 원천이 매일 같은 전체 구성을 반복하면 snapshot hash와 effective-date
  방식을 이용한 change-only canonical 이력을 검토한다.
- 원천 재처리가 필요하면 raw payload 보존 위치와 retention을 별도로 정한다.
- 향후 실적보고서·시장 리포트의 PDF/BLOB를 MotherDuck table에 직접 쌓는 방안은 기본값으로 삼지 않고,
  object storage와 metadata/link 분리를 검토한다.
- 적재 전 예상 rows, pilot 후 실제 compressed size, 월별 증가량과 보존기간을 capacity contract로 둔다.

MotherDuck의 2026-08-27 공식 가격 안내상 Lite plan은 10 GB storage와 월 10시간 Pulse compute를
포함하고, storage는 compressed on-disk size를 기준으로 측정한다. 현재 약 49 MiB에서 시작하는
보유종목 3년 OHLCV는 10 GB 대비 미미하다. 다만 실제 구독 plan과 조직 전체 사용량은 MotherDuck
Billing 화면에서 별도로 확인해야 한다.

참고: [MotherDuck pricing](https://motherduck.com/product/pricing/),
[MotherDuck Fees Addendum](https://motherduck.com/fees-addendum/)

## 7. ETF look-through 요구사항

### 7.1 목적

국내·미국 보유 ETF 내부의 기업, 국가, 섹터, 통화 노출을 확인하고 기초 구성종목이 전체
포트폴리오에 미치는 영향을 추정한다.

### 7.2 필요한 원천 사실

- ETF 식별자와 시장
- 구성 기준일
- 구성종목 식별자와 정규화된 종목 identity
- 구성종목 비중
- 원천과 공표 시각
- coverage, staleness 및 confidence 상태
- 가능한 경우 현물형, 레버리지, 인버스, 합성 등 ETF 구조 분류

### 7.3 분석 요구사항

- 최신 구성으로 덮어쓰지 않고 ETF 구성 이력을 보존한다.
- 구성종목 비중 합계를 검증하고 불완전한 coverage를 기록한다.
- `ETF 평가액 × 구성종목 비중`으로 간접 노출을 계산한다.
- identity 연결이 가능한 경우 같은 기업의 직접 노출과 간접 노출을 합산해 보여준다.
- 기업, 국가, 섹터, 통화별 look-through를 제공한다.
- 총자산 계산에서는 ETF 평가액을 한 번만 포함하고, look-through는 노출 분석에만 사용한다.
- 단순 구성비 귀속이 오해를 만드는 레버리지·인버스·합성 상품은 별도로 다룬다.
- ETF 구성종목별 손익 기여도는 원천과 기준 시각을 포함한 추정치로 표시한다.

정확한 원천, 가용성, 갱신 주기, 라이선스와 과거 이력 범위는 소스 카탈로그 조사에서 확정한다.

## 8. 후속 데이터 제품

다음 요구는 유지하지만 보유종목 감시 v1에는 포함하지 않는다.

### 8.1 관심종목 기회 추적

- 관심종목 등록일과 등록 이유를 보존한다.
- 등록 이후 수익률, 최대 상승·하락 및 상대성과를 추적한다.
- 사후 정보를 과거 판단에 덧씌우지 않고 놓친 기회를 설명한다.

### 8.2 펀더멘털 및 Forward Outlook

- 분기·연간 실적 사실과 원문 출처를 보존한다.
- 보고 기간별 수정과 전망 변화를 추적한다.
- 공시 사실, 외부 consensus, 사용자 가정, 모델 생성 전망을 구분한다.
- 12개월 forward의 의미와 새 실적 발표 후 roll-forward 규칙을 정의한다.
- 원하는 band가 PER/PBR 등 valuation band인지, 전망 범위인지, risk/reward band인지 구분한다.
- 전망 또는 리서치 원천을 선정하기 전에 이용 권한, 라이선스, 수정 이력과 as-of 의미를 검증한다.

공식 원천과 live coverage, 실제 실적·consensus·사용자/모델 시나리오 분리 및 valuation 계약 권고는
`docs/requirements/review-package-c-fundamentals-dividend-macro.md`에 기록했다. C-1~C-3과 C-6은
DEC-020~DEC-022·DEC-025로 승인됐다. 실제 provider 선정과 구현은 미승인이다.

### 8.3 배당 원장

- 가능한 범위에서 선언일, 배당락일, 기준일, 지급일, 실제 수령액, 세금, 통화, 계좌를 보존한다.
- 월별 수익, 전년 대비 증감, 종목별 기여 및 예상·실수령 reconciliation을 제공한다.

KIS KSD·국내 계좌권리·미국 ICE 권리의 live 검증과 `declared → entitled → received` 계약은 Package C에
기록했다. 해외와 IRP 실제 입금 원천 gap을 일정×수량으로 채우지 않고 statement/manual provenance를
허용하는 C-4 권고는 DEC-023으로 승인됐다.

### 8.4 매수 lot·투자 thread 분석과 매매일지

#### 8.4.1 개념 계층

다음 네 계층을 서로 다른 grain으로 관리한다.

1. `trade execution`: KIS 등 원천에서 확인된 변경 불가능한 주문·체결 관측 사실. 원천이 주문별
   총체결수량과 평균체결가만 제공하면 주문 단위이며, 개별 fill을 추정 생성하지 않는다.
2. `purchase lot`: 한 번의 매수 판단과 원가·수량을 추적하는 분석 단위
3. `trade thread`: 같은 투자 논리에 속하는 하나 이상의 매수 lot과 관련 매도의 생명주기
4. `position`: 계좌·종목 단위의 평단가 기반 현재 보유 상태

원천에서 한 주문이 여러 체결로 나뉘고 개별 fill identity를 제공하는 경우에는 각 체결 사실을 보존한다.
현재 확인된 국내·해외 주문체결 API는 주문별 총체결수량과 평균체결가까지만 제공하므로, v1은
DEC-010에 따라 주문 단위 purchase lot을 사용한다.

#### 8.4.2 Identity와 표시 키

- 체결, lot 및 thread에는 각각 충돌하지 않는 영속 내부 식별자를 부여한다.
- 원천 주문번호, 체결번호, 체결 순번, 계좌 alias, 시장, 종목, 체결 시각 및 매매 방향을 가능한 범위에서
  canonical identity에 포함한다.
- 사용자가 제안한 `yyyy-mm-dd-hh-mm-ss-종목코드-매수` 형식은 사람이 읽고 검색할 수 있는
  `display_key`로 제공한다.
- 동일 초 복수 체결, 여러 계좌, 시장별 시간대 및 재수집을 안전하게 처리하기 위해 `display_key`를
  유일한 DB key로 사용하지 않는다.
- 재수집된 같은 원천 거래는 새 lot이나 thread를 중복 생성하지 않아야 한다.

#### 8.4.3 Thread 생명주기

- 각 신규 매수 lot은 기본적으로 새 trade thread 후보가 된다.
- 사용자는 해당 매수가 기존 투자 판단의 추가매수인지 별도 판단인지 지정할 수 있어야 한다.
- LLM은 매수 이유, 기대 시나리오, 재검토 조건 및 손절 기준을 질문하고 thread 일지에 기록할 수 있다.
- 하나의 종목에 장기 투자, 단기 반등 등 여러 thread가 동시에 존재할 수 있어야 한다.
- lot을 기존 thread에 연결해도 원천 매수 사실과 lot별 성과는 사라지지 않는다.
- thread 연결과 수정은 작성 주체, 시각, 이전 값 및 변경 사유를 포함한 이력으로 보존한다.

#### 8.4.4 매도와 lot·thread 연결

- 사용자가 매도와 대상 lot 또는 thread의 관계를 명시하면 그 연결을 개인 분석의 우선 근거로 사용한다.
- 명시적 연결이 없으면 FIFO 등 승인된 기본 규칙으로 임시 배분할 수 있으나 결과를 `inferred`로 표시한다.
- LLM은 미지정 매도에 대해 어떤 투자 thread를 축소하거나 종료한 것인지 질문할 수 있어야 한다.
- 일부 매도는 선택된 lot 또는 thread의 잔여 수량만 감소시키고, 전량 소진 시 종료 상태를 기록한다.
- 내부 매도 배분은 증권사의 공식 실현손익, 평단가 및 세무 기록과 별도로 reconciliation한다.
- 기본 배분 방식, 수정 가능 기간 및 증권사별 차이는 원천 조사와 후속 지표 계약에서 확정한다.

#### 8.4.5 분석 요구사항

포지션 전체와 각 lot·thread에 대해 가능한 범위에서 다음을 제공한다.

- 매수 수량, 매수가격, 수수료·세금 및 잔여 수량
- 현지 통화와 원화 기준 원가 및 손익
- 실현손익, 미실현손익 및 총손익
- 보유기간과 보유기간 수익률
- 최대 유리 구간(MFE)과 최대 불리 구간(MAE)
- 보유기간 고점 대비 낙폭과 평가이익 반납액
- 전체 종목 및 포트폴리오 손익에 대한 기여도
- 배당·분배금을 포함한 총수익과 가격수익의 구분
- 매수 당시 가격 추세, 거래량, RSI 등 승인된 시장 상태
- 매수 사유, 기대 시나리오, 재검토 조건, 손절 기준 및 사후 평가

추가매수와 일부 매도로 인한 현금흐름을 보정하지 않은 단순 평가금액 최고치는 thread의 수익 고점으로
사용하지 않는다.

#### 8.4.6 데이터 품질과 과거 이력

- 원천 거래로 확인된 사실은 `actual`, 사용자가 직접 보완한 값은 `manual`, 최초 확인 잔고에서 만든
  시작 lot은 `inferred_opening`, 신뢰 가능한 거래내역으로 재구성한 값은 `reconstructed` 또는 이에
  준하는 품질 상태로 구분한다.
- 과거 최초 매수정보가 없으면 현재 평단가나 최초 관측 잔고를 정확한 원천 lot처럼 표시하지 않는다.
- 국내·미국 시장의 시간대, 체결일, 결제일, 환율 기준과 수수료·세금 포함 여부를 명시한다.
- 액면분할, 병합, 종목변경, 합병, spin-off 등 corporate action이 lot 수량과 원가에 미치는 영향을
  추적할 수 있어야 한다.
- lot 합계는 canonical position의 수량·원가와 정기적으로 reconciliation하고 차이를 품질 상태로 남긴다.

#### 8.4.7 매매일지와 LLM workflow

- 국내·해외 canonical 거래 identity, purchase lot, trade thread와 매매일지를 연결한다.
- 일지가 없거나 thread가 지정되지 않은 거래를 탐지한다.
- LLM이 거래 이유와 thread 관계를 질문하고 Remote MCP를 통해 일지를 작성하거나 수정할 수 있어야 한다.
- 수정 이력, 작성 주체, 시각 및 거래 당시 기록과 사후 회고를 구분해 보존한다.
- 누락되거나 불완전한 일지 및 매도 매핑을 예약 작업으로 검토할 수 있어야 한다.

#### 8.4.8 패키지 A 승인 결과

거래 원장과 과거 복원의 현황, 대안과 권고안은
`docs/requirements/review-package-a-transaction-ledger.md`에서 함께 검토했다. IRP 최근구간 fallback,
거래내역 3년 초도 backfill, 해외 비용·환율 candidate link와 미지정 매도의 FIFO 임시 배분을
DEC-011~DEC-014로 승인했다.

### 8.5 위험 및 신호 엔진

- Turtle 방식의 위험 크기와 손실 한도를 계산 전에 명확히 정의하고 검증한다.
- RSI 기간, 봉 주기, 임계치 및 자산 유형별 차이를 정의한다.
- VIX 등 시장 위험 지표의 적용 범위를 정의한다.
- 모든 신호 정의를 버전 관리하고 계산에 사용된 입력 스냅샷을 보존한다.
- 신호는 정보 제공용이며 주문을 실행하지 않는다.

가격·추세·ETF 노출의 실제 원천 검증과 계산 권고안은
`docs/requirements/review-package-b-price-trend-etf.md`에서 함께 검토했다. B-1~B-5는
DEC-015~DEC-019로 승인됐으며 이 승인은 구현 승인이 아니다.

경보 bootstrap boundary, 3년 replay·shadow gate, 2% risk cap, Telegram delivery, Remote MCP scope와
LLM 예약·매매일지 review 계약은 `docs/requirements/review-package-d-monitoring-conversation.md`에
기록했다. Bollinger 보조 context와 consensus miss·guidance·forward revision 신호를 포함한 D-1~D-7은
DEC-026~DEC-032로 승인됐다.

### 8.6 매크로 및 사건 맥락

- 매크로, 정책, 산업 및 기업 사건을 날짜와 원천 provenance와 함께 보존한다.
- 사건을 영향을 받을 수 있는 보유종목 및 ETF 구성종목과 연결한다.
- 사건 전후의 관찰 가능한 수익률을 측정한다.
- 시간적 연관성, 모델 추론 및 검증된 인과관계를 구분한다.

ECOS·FRED/ALFRED·Cboe VIX와 OpenDART·SEC 사건의 source contract 및 direct·rule-based·hypothesis·
validated 관계 구분은 Package C에 기록했다. 일반적으로 알려진 금리·환율·물가·성장·고용·달러·유가·
VIX를 `macro_profile_v1`으로 시작하고 이후 versioned contract로 확장한다.

## 9. 데이터 거버넌스 요구사항

### 9.1 소스 데이터 카탈로그

기존 warehouse object catalog와 별도로 원천 데이터 카탈로그가 필요하다. 각 원천 데이터셋에는
최소한 다음을 기록해야 한다.

요구사항 분석 단계의 endpoint 단위 조사 결과는
[KIS Portfolio 소스 데이터 카탈로그](./source-data-catalog.md)에 누적한다.

- 제공자와 capability 영역
- 공식 데이터셋 또는 API 이름
- 해당하는 경우 endpoint와 TR_ID
- 시장과 계좌 상품 coverage
- 요청 기간, 페이징, 제공 가능한 과거 깊이
- 응답 grain과 natural key
- 원천 시각과 수정 가능성
- 호출 제한과 운영 제약
- 민감 필드와 허용 저장 형태
- 구현 상태와 최종 검증일
- 예정 수집 방식과 주기
- 연결되는 논리 데이터 제품
- 품질, freshness, retention 및 lineage 기대치

현재의 상위 수준 API capability map을 endpoint 단위 완전성 목록으로 간주하면 안 된다.

### 9.2 Warehouse 카탈로그

기존 warehouse catalog는 DB 객체의 목적, grain, key, 논리 계층, write mode, 민감도 및 백업 정책을
계속 관리한다. 소스 카탈로그와 warehouse catalog는 서로 연결하되 책임을 중복하지 않는다.

### 9.3 지표 카탈로그

SQL, MCP, Telegram 또는 향후 dashboard가 사용하는 지표에는 canonical 정의가 필요하다.

- 총자산과 현금
- 일별 및 기간 수익률
- 외부 현금흐름 보정 수익률
- 낙폭과 최근 고점 기간
- 종목별 손익 기여도
- 추세 상태
- 직접 및 ETF look-through 노출
- 배당 수익
- 실현 및 미실현 손익
- 평단가 기반 포지션 손익과 lot·thread 기반 분석 손익
- lot·thread별 MFE, MAE, 보유기간 고점 대비 낙폭 및 평가이익 반납
- 위험 및 신호 정의

### 9.4 Lineage와 품질

- 원천 데이터셋에서 raw 관측, canonical 상태, 분석 데이터 제품, MCP 결과, Telegram 메시지까지
  추적할 수 있어야 한다.
- 원천 기준 시각과 계산 시각을 따로 보존한다.
- completeness, freshness, uniqueness, reconciliation, referential integrity 규칙을 정의한다.
- 부분 결과를 명시적인 품질 상태 없이 완전한 결과처럼 보여주지 않는다.
- LLM 대화와 독립적으로 실행 이력과 실패 원인을 보존한다.

### 9.5 대화형 분석 메타데이터

Remote MCP는 다음의 관리된 설명을 분석에 제공할 수 있어야 한다.

- 사용 가능한 데이터 제품과 지표
- 테이블·view의 목적과 grain
- join 및 identity 규칙
- 원천 lineage와 알려진 제약
- freshness 및 품질 상태
- 승인된 계산 정의
- 적절한 질문과 지원하지 않는 해석

## 10. 수집 및 상호작용 요구사항

### 10.1 수집 방식

현재 요구되는 주요 수집 방식은 다음 두 가지다.

- 활성 LLM 세션 없이 실행되는 정기 수집
- 최신 데이터가 필요할 때 Remote MCP를 통해 요청하는 on-demand 수집

추후 소스 카탈로그에 따라 backfill, 기준 파일 또는 realtime/event 수집 방식이 추가될 수 있다.
원천 데이터셋과 수집 trigger는 서로 다른 개념으로 관리한다.

### 10.2 LLM 예약 작업 호환성

- LLM 예약 작업이 Remote MCP를 통해 관리된 작업을 요청할 수 있어야 한다.
- trigger가 무엇이든 결과의 의미와 품질 계약은 같아야 한다.
- 실행 결과는 감사 및 재현 가능해야 한다.
- LLM 예약 작업이 없거나 실패해도 필수적인 기본 수집은 중단되지 않아야 한다.

### 10.3 직접 SQL과 MCP 사용

- 사용자는 관리된 MotherDuck 데이터를 직접 조회할 수 있어야 한다.
- Remote MCP 분석은 직접 SQL과 같은 canonical 지표 정의를 사용해야 한다.
- 두 인터페이스의 결과가 다르면 그 의미상 이유를 문서화해야 한다.

## 11. 비기능 요구사항

### 11.1 설명 가능성과 재현성

- 모든 경보, 신호 및 중요한 분석 결과에서 규칙 버전, 주요 입력, 원천·기준 시각 및 품질 상태를
  확인할 수 있어야 한다.
- 전망과 추론된 영향은 관찰된 사실과 명확히 구분해야 한다.

### 11.2 보안과 개인정보

- 전체 계좌번호와 secret을 Telegram, 일반 로그 또는 MCP 설명에 노출하지 않는다.
- Telegram, KIS, OAuth 및 DB credential을 분석 데이터셋에 저장하지 않는다.
- 데이터 접근과 향후 write-capable MCP 동작은 명시적으로 권한을 부여하고 감사할 수 있어야 한다.

### 11.3 신뢰성

- 일부 계좌나 원천이 실패했을 때 완전한 결과라고 조용히 선언하지 않는다.
- 중복된 정기 또는 LLM trigger가 canonical fact나 경보를 중복 생성하지 않아야 한다.
- 원천 rate limit, retry, backoff 및 freshness 실패를 관찰할 수 있어야 한다.
- 휴장일, 시장 session, 한국·미국 시간대 차이를 명시적으로 처리한다.

### 11.4 진화 가능성

- 소스 계약과 지표 계약을 버전 관리한다.
- 재처리에 필요한 raw 관측은 승인된 retention·backup 정책에 따라 보존한다.
- 신규 원천이나 신호는 source catalog, target mapping, 품질 계약 및 acceptance review를 우회하지 않는다.

### 11.5 비용과 실행 형태

- 운영 인프라, 저장소, 네트워크와 외부 데이터 provider를 합친 월 실제 지출은 50,000원 이하여야 한다.
- 사용자-facing 서비스는 cold start를 허용하고 request 기반으로 scale-to-zero해야 한다.
- 정기 수집·정제·경보는 실행 후 종료하는 저비용 batch job을 기본으로 하며 상시 worker를 요구하지 않는다.
- 신규 구성요소와 수집주기는 정상월·초도적재월·장애 재시도월 비용을 비교한 뒤 채택한다.
- 예산 경보만으로 지출이 차단된다고 가정하지 않고 max instances, timeout·retry·source call budget과
  관리된 중지 경로를 함께 설계한다.

## 12. 요구사항과 관련된 현재 상태 관찰

- 프로젝트에는 Bronze, Silver, Gold, Control, Security 논리 계층이 이미 정의되어 있다.
- 기존 배치는 일부 raw 관측과 canonical row를 저장하지만, 수집·변환·분석 제공이 완결된 하나의
  관리 파이프라인으로 정립되지는 않았다.
- 현재 warehouse catalog는 기존 DB 객체를 관리하지만 KIS 및 외부 제공자가 제공할 수 있는 원천 데이터
  전체를 관리하지 않는다.
- KIS 가격 API는 국내·미국 일봉 OHLCV를 제공하지만 100행 단위 호출과 조정주가 의미를 명시적으로
  관리해야 한다. 현재 가격 캐시는 조정주가 metadata와 값이 어긋날 수 있고 dual price basis를 표현하지
  못한다.
- KIS ETF 구성종목시세는 현재 보유 국내 ETF 14종 모두 응답했지만 선언 642행 중 286행만 반환해
  완전한 look-through 원천으로 사용할 수 없다. KRX/운용사 일별 PDF가 canonical source 후보이다.
- KIS 국내 재무비율은 최신 국내 6자리 후보 8개 중 3개에 row가 있었고 종목추정실적은 8개 모두
  응답했지만 `DATA1`~`DATA5` semantic mapping이 불완전하다. 실제 실적은 OpenDART·SEC를 canonical로,
  KIS는 보조·experimental source로 쓰는 권고를 Package C에 기록했다.
- 국내 배당일정은 후보 8개 중 5개, 미국 ICE 권리일정은 직접보유 4개 모두 응답했다. 국내 계좌권리는
  IRP만 0 row였고 미국 실제 계좌 입금 identity는 확인되지 않아 예상·권리·실수령 분리가 필요하다.
- 현재 `price_history`의 KRX 이력은 1종목 53일, canonical 총자산은 27일뿐이므로 운영 경보 threshold를
  지금 확정할 수 없다. Package D는 3년 replay와 2주 shadow 검증을 활성화 gate로 둔다.
- live MotherDuck은 49.0 MiB이며 27 tables + 3 views가 있다. `cash_flow`, `trade_journal`,
  `asset_return_daily`와 총자산 품질 컬럼은 현 checkout과 drift 상태이고 `asset_return_daily`는 broken이다.
- MotherDuck Flights는 현재 Business plan 기능이다. Lite 10 GB 범위에서 Cloud Run Jobs/Scheduler를
  유지하고 typed data와 object storage를 분리하는 쪽을 Package E에서 승인했다. 기존 Cloud Run 배포
  문서도 auth·remote `min-instances=0`을 사용하므로 이 저비용 배포 topology는 재사용할 가치가 있다.
  다만 내부 adapter·repository·runtime DDL과 operational/analytics state 결합은 V2 계약에 맞춘
  재개발 대상으로 둘 수 있다.
- 운영 DB drift 문서에는 초기 `cash_flow`, `trade_journal`, `asset_return_daily` 객체가 기록되어 있지만,
  그 존재만으로 현재 계약이나 구현을 승인하지 않는다.
- 이 관찰은 후속 구현 계획 전에 다시 검증해야 한다.

## 13. 명시적으로 유보한 구현 결정

요구사항 분석 이후의 차세대 설계안은 `docs/design/kis-portfolio-v2-system-design.md`, 구현·전환 Wave는
`docs/design/kis-portfolio-v2-delivery-plan.md`에 정리했다. 두 문서는 아래 미결정 사항에 대한 권고안을
제시하지만 아직 구현이나 infrastructure 변경을 승인하지 않는다.

다음은 요구사항 기준선에서 아직 구현 결정으로 승인하지 않았다. V2 설계 문서가 제안한 항목도
Architecture delta 검토 전에는 선택된 구현으로 간주하지 않는다.

- 실제 Bronze/Silver/Gold schema 이동
- Telegram bot·destination의 실제 생성과 배포 환경
- 미국 licensed consensus provider와 해외·IRP 실제 배당 입금 원천
- KIS 종목추정실적 `DATA1`~`DATA5` semantic mapping
- 운영 signal threshold의 replay·shadow 보정 결과
- realtime REST polling과 WebSocket 적용 범위
- object storage bucket·region·lifecycle와 backup destination
- dashboard 및 시각화 기술
- trade execution, purchase lot, trade thread의 물리 schema와 저장 계층
- 주문 분할체결을 purchase lot으로 묶는 규칙과 기본 매도 배분 구현
- 실제 월 청구 baseline, 서비스별 비용 attribution과 5만원 예산의 비필수 작업 중지 정책

## 14. 미결정 사항

1. KIS 국내 종목추정실적의 metric·unit·revision mapping을 독립 자료와 대조한다.
2. 미국 consensus가 필요할 때 licensed provider와 비용·보존권한을 선택한다.
3. 해외와 IRP의 실제 배당 입금·세금 원천 또는 statement import 형식을 선택한다.
4. KRX·운용사 PDF의 자동 접근 방식, 이용조건과 과거 날짜 coverage를 검증한다.
5. Telegram destination owner, test message 승인과 장애 escalation을 구현계획에서 확정한다.
6. 3년 replay와 2주 shadow 결과로 주식·ETF·REIT·레버리지 threshold를 보정한다.
7. live drift 객체를 현재 branch에 통합할지 migration 전 확정한다.
8. private object storage의 region, encryption, lifecycle과 backup destination을 선택한다.
9. 거래·lot·thread·배당·fundamental·signal의 물리 schema와 migration을 설계한다.
10. 현재 GCP·MotherDuck·provider 실제 월 비용을 측정하고 35,000·42,500·50,000원 gate의 운영 동작을 확정한다.

## 15. 요구사항 분석 진행 순서

이 초안만으로 구현을 시작하지 않는다. 진행 순서는 다음과 같다.

1. 이 문서를 검토 가능한 요구사항 기준선으로 계속 관리한다.
2. 보유종목 감시 v1의 결정과 인수 기준을 마무리한다.
3. 선택된 논리적 장바구니에 대한 endpoint 단위 소스 카탈로그를 만든다.
4. 가용성, 비용, 라이선스, rate limit, 과거 이력 범위를 검토한다.
5. 실제 수집 데이터와 수집 계약을 승인한다.
6. 데이터 제품, 지표, lineage 및 품질 규칙을 정의한다.
7. 논리 데이터 아키텍처를 설계한다.
8. 물리 파이프라인과 플랫폼 대안을 비교한다.
9. 별도 승인을 위한 구현 계획을 작성한다.
10. 승인 후에만 코드 또는 데이터를 변경한다.

### 15.1 사용자 검토 패키지

검토 피로와 결정 간 충돌을 줄이기 위해 서로 의존하는 항목을 다음 패키지로 묶는다. 각 패키지는
`확인된 현황 → 권고안 → 대안과 영향 → 승인할 결정` 순서로 제시한다. 안전한 read-only 조사는
패키지 작성 전에 진행할 수 있지만, 구현·적재·배포는 별도 승인을 받는다.

| 순서 | 검토 패키지 | 함께 승인할 주요 항목 | 상태 |
| --- | --- | --- | --- |
| A | 거래 원장과 과거 복원 | lot grain, IRP 원천·fallback, backfill 깊이, 해외 비용·환율 결합, 매도 임시 배분 | 완료; DEC-010~DEC-014 승인 |
| B | 가격·추세·ETF 노출 | 조정/비조정 가격, 일봉·거래량, 이동평균·RSI, 보유기간 ATH, ETF 구성종목과 갱신주기 | 완료; DEC-015~DEC-019 승인 |
| C | 실적·가치·배당·매크로 | 공시·실적·forward 전망, valuation/risk-reward band, 배당 원장, 사건·매크로 원천 | 완료; DEC-020~DEC-025 승인 |
| D | 감시·신호·대화 workflow | 경보 임계치, 설명 payload, Telegram, Remote MCP, LLM 예약 작업, 매매일지 질문 | 완료; DEC-026~DEC-032 승인 |
| E | 데이터 플랫폼과 운영 | Bronze/Silver/Gold, 카탈로그·lineage·품질, MotherDuck 용량·보존, orchestration·복구 | 완료; DEC-033~DEC-041 승인 |

각 패키지가 너무 크면 독립적으로 승인 가능한 소단위로 나누되, 다음 패키지 전체의 미리보기를 함께
제공한다. 사용자가 명시적으로 요청하지 않는 한 단순 필드 하나마다 승인을 반복해서 요구하지 않는다.

## 16. 검토 이력

| 날짜 | 상태 | 내용 |
| --- | --- | --- |
| 2026-08-27 | V2 설계 검토 대기 | 현행 코드·운영 DB·Cloud Run·비용 구성을 재조사하고 serverless modular monolith, stateless Remote MCP, Firestore state plane, parallel schema와 Wave 0~8 전환 설계안을 작성함. 구현과 provisioning은 미승인 |
| 2026-08-27 | 요구 승인 | 패키지 C·D·E를 피드백과 함께 승인함. point-in-time consensus 위험 신호, 표준 macro profile v1, Bollinger 보조 context, 월 5만원 상한과 scale-to-zero·batch-first를 DEC-020~DEC-041로 확정함 |
| 2026-08-27 | 패키지 C·D·E 승인 대기 | 공식 원천·live coverage, 경보·Telegram·scope, orchestration·retention·recovery 조사를 끝내고 20개 권고를 통합 검토 문서로 묶음 |
| 2026-08-27 | 요구 승인 | 패키지 B의 dual price basis, SMA20·50·120·RSI14, 보유 에피소드 고점, KRX/운용사 PDF와 ETF 일별 3년 보존을 모두 승인함 |
| 2026-08-27 | 패키지 B 승인 대기 | 국내·미국 일봉의 조정 옵션·100행 제한, KIS ETF 30행 제한, KRX/운용사 PDF, RSI·보유기간 고점과 3년 용량 권고안을 문서화함 |
| 2026-08-27 | 요구 승인 | 패키지 A의 IRP provisional·지연 reconciliation, 거래 3년 backfill, 해외 derived candidate link, 미지정 매도 FIFO inferred 배분을 모두 승인함 |
| 2026-08-27 | 분석 결과 | 패키지 A read-only 조사에서 비IRP 국내 15개 보유종목은 3년 거래와 수량 일치 후보, IRP 7개와 미국주식 4개는 opening/reconciliation 필요로 판정함 |
| 2026-08-27 | 요구 승인 | v1 purchase lot을 체결된 매수 주문 단위로 확정하고 fill grain은 신뢰 가능한 원천 확보 후 확장하기로 함 |
| 2026-08-27 | 분석 결과 | 승인된 read-only probe에서 국내·해외 주문 이력의 확인 grain이 개별 fill이 아닌 주문 단위 체결 집계임을 확인하고, 주문 단위 purchase lot을 v1 권고안으로 기록함. IRP 최근구간은 source gap으로 남김 |
| 2026-08-27 | 요구 승인 | 평단가를 기본으로 유지하고 매수 lot·투자 thread 손익과 매매일지를 병렬 분석하는 개념 계약을 기록함 |
| 2026-08-27 | 요구 승인 | 최근 3년 일봉 backfill 범위를 승인하고 MotherDuck 용량 사전검토를 기록함 |
| 2026-08-27 | 초안 생성 | 현재 요구사항 분석 대화에서 확정된 요구와 결정을 통합했으며 구현은 승인하지 않음 |
