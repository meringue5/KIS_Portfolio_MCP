# 알림 평가·상태·전송 규칙

> 신호를 계산한 것, 전달할 상태가 된 것, 실제 전송/수신한 것은 다릅니다.
> 기존 승인 계약·후속 교정을 현행 의미로 통합합니다. 새 rule·destination·전송 권한을 주지 않습니다.

> DEC-064 시간·문구 변경은 WI-078 보호 배포로 운영 반영됐으며 실제 수신 인수를 수집 중입니다.

## 범위와 의미

### 서로 다른 세 제품

| 결과 | 의미 / 지켜야 할 경계 |
| --- | --- |
| 세 시각 보유종목 현황 | 08:00 해외 및 10:00/14:00/16:00 국내 평가 slot의 통합 상태. 상태 변화가 없어도 현황 요구를 충족 |
| 종목별 상세 신호 | quality-pass의 eligible transition만 전달. 현황 수신이 상세 수신의 증거는 아님 |
| 총자산 이미지 보고서 | 08:00/14:00 현재 금액·구성, 가능할 때 이전 같은 slot 비교. 신호 건강의 증거가 아님 |

미보유 관심종목은 이 보유종목 범위로 끼워 넣지 않습니다. ETF/REIT/leveraged/inverse도 자기 상장 종목의
가격·추세·lot/평가 변화로 다루며 구성종목 look-through를 추정하지 않습니다.

## 판단 규칙

### identity·시간·rule

alert identity는 rule ID/version+opaque subject type/ID에 기반하며 slot retry를 넘어 유지됩니다.
candidate는 logical session key와 slot을 추가합니다. 현재 source slot은 `kr-0800`, `kr-1000`, `kr-1400`, `kr-1600`이며 해외 평가 identity는 `us-close`입니다. 과거 `kr-1430` 기록을 보존합니다.
U.S. close는 **미국 session date**가 identity를 소유합니다. 다른 한국 날짜/휴일에 같은 session을 선택하면
기존 candidate를 재사용하며 10:00/14:00/16:00에 같은 미국장 상태전이나 전송을 만들지 않습니다.

rule version과 candidate logical key는 immutable입니다. 사용한 threshold를 덮지 않고 새 version과 owner 승인/철회를 남깁니다.
현재 permanent rule은 expiry 없는 승인 successor이지만 revocation과 runtime flag는 항상 적용됩니다.
이전 7일 canary·shadow 최초 활성화 순서는 과거 승인 경로이지 현재 rule의 자동 만료나 매 릴리즈 TODO가 아닙니다.

### 상태와 전송 자격

severity는 `normal/정상`, `watch/주의`, `warning/경고`, `critical/긴급`이며 전달 floor는 watch(rank 1)입니다.
partial/stale/reconstructed/insufficient_history 등 non-pass 입력은 suppressed evidence를 남기고 이전 alert state를 갱신하거나 claim하지 않습니다.

| 기존 상태 → 관측 | 상태전이 의미 / 상세 전송 |
| --- | --- |
| 새 successor의 첫 관측 | silent baseline; 새 시장 사건으로 보내지 않음 |
| normal → active watch+ / active 재진입 | entered/reentered; eligible 상세 |
| active → 동일 fingerprint | no change; 상세 없음 |
| active → severity 상승 / watch+ signal-set 변경 | escalated/updated; eligible 상세 |
| active → 낮아졌으나 active | deescalated; 상세 없음 |
| active watch+ → normal | recovered; 이전 전달 severity를 routing에 사용 |

re-entry는 episode를 증가시킵니다. 후보는 evaluation time 순으로 처리하며 늦은 과거 candidate는 out_of_order
outcome만 남기고 현재 state를 바꾸지 않습니다. 같은 논리키의 다른 내용은 hard conflict입니다.

전송은 active/external rule, 최신 owner approval, pass candidate, delivery-required transition, 유효 severity,
정확한 enable flag·private destination·token, renderer 검증과 lease 취득을 모두 요구합니다.
claim 때 approval/validity를 다시 확인하므로 뒤늦은 revoke가 이깁니다. disabled/불완전 설정은 요청·claim을 만들지 않습니다.
expected-prior state revision과 unique insert/lease compare-update를 사용합니다. 한 run의 dispatch 상한은 기존 20입니다.

### 전송 결과는 추측하지 않는다

| 관측 | ledger / 처리 |
| --- | --- |
| provider의 message ID 확인 | sent, terminal; ID 참조는 hash |
| 명시 HTTP 429 / 5xx | retryable failure, 기존 bounded 정책으로 다음 scheduled run에서 처리 |
| 명시 HTTP 4xx / unsafe payload | permanent failure, terminal; unsafe는 요청하지 않음 |
| timeout·모호한 응답·network exception | unknown, terminal; 자동 재획득·다른 방식 fallback·과거 replay 없음 |

rule/state/candidate outcome/dispatch claim/delivery attempt는 별도 ledger입니다. evaluation 성공이 transport 성공은 아닙니다.
logical no-change/zero-candidate slot도 terminal run/quality marker가 있어야 관측 완료로 인정합니다.

### 사람이 읽는 메시지의 의미

DEC-064: recovered는 ‘이전 경고 조건 해제’이며 반등·추세 전환 확인이 아닙니다. 직전 경고의
조건이 이번 평가에서 충족되지 않았다고 설명하고 중립 ⚪ 표시를 씁니다. 활성 신호는 아이콘과
주의/경고/긴급 텍스트를 함께 표시합니다. 노란색은 일반 불렛이 아니라 watch 수준입니다.
해외 마감 평가는 08:00에만 수행하고 10:00 국내 평가에 반복 편입하지 않습니다.
총자산은 08:00/14:00 exact slot을 사용합니다. 첫 slot의 전일 비교 부재는 비교 영역만 보류합니다.
개장 전 국내 값은 마지막 source 시각의 관측이며 당일 장중 방향 신호로 평가하지 않습니다.


‘하회’는 현재 가격과 평균의 위치이고 ‘하향 이탈’은 이전 close≥이전 SMA20, 현재 close<현재 SMA20 사건입니다.
price-to-average와 SMA20-to-SMA50 구조를 분리합니다. 누락 analytics는 계산 보류+이유이지 0/배분/PnL 대체가 아닙니다.
KRX 10:00/14:00 누적거래량은 같은-slot 정규화 전까지 unavailable이며 full-day 평균과 비교하지 않습니다.
KRX close/U.S. close만 이전 20 completed sessions를 full-day baseline으로 사용합니다.

상세 메시지는 approved Rich HTML representation 하나, dynamic HTML escaping, allowlisted public_context만 사용합니다.
source KST 시각·시장/종류·quality와 제한된 분석을 표시하고 내부 rule/reason 코드는 ledger에 둡니다.
계좌번호·chat ID·credential·raw provider body·절대 자산금액은 신호 public_context에 넣지 않습니다.
owner 총자산 보고서의 승인된 금액 표시는 **별도 renderer/승인 경계**이며 이 privacy 규칙을 모든 보고서에 혼용하지 않습니다.
관련 allowlist·길이·비밀 정책은 [renderer](../../src/kis_portfolio/adapters/outbound/telegram.py)와 [보안](../security-and-secrets.md)이 정본입니다.

완전한 현재 총액/구성이 있으면 이전 비교만 없다는 이유로 다른 형식으로 축소하지 않습니다. 해외 feeder/FX
누락은 완전 총액을 막고, 이전 같은-slot 누락은 비교·기여도만 제한합니다. 다른 slot/이전 날짜로 조용히 대체하지 않습니다.

## 변경과 검증

### 새 rule·릴리즈를 검증하는 방법

- 재생 입력은 evaluation time/slot/subject 순서와 PIT를 고정합니다. `historical_live`와 retrospective reconstruction을 구분합니다.
- bootstrap threshold는 versioned 후보이지 현행 모든 자산의 기준 선언이 아닙니다. asset-class별·전체 조합 budget을 같이 검토합니다.
  기존 검토 목표는 stateful 후보 slot별 median≤2, nearest-rank p95≤5입니다. owner label 전에는 precision/false-positive 성능을 주장하지 않습니다.
- 새 calibration의 review-ready 기준은 실제 기간/coverage(기존 1,096 calendar days·asset-class별 600 eligible sessions),
  shadow는 기존 14 elapsed days·예정 slot 대사·민감값 위반 0·owner 검토 또는 기록된 명시적 인수 예외를 확인합니다.
  이미 인수·종료된 window를 매 운영 작업의 재구축 TODO로 만들지 않습니다.
- approval은 destination 검증·runtime 전송 enable을 대신하지 않습니다. Rich transport 변경은 기존 protected release의
  exact image/identity/secret/egress 경로에서 승인된 finance-free provider-confirmed smoke 후 승격합니다.
- rollback은 producer별 flag와 검증된 runtime definition 복원입니다. signal/배송 history·실패/unknown attempt는 보존합니다.

코드: [상태·claim](../../src/kis_portfolio/modules/monitoring/alerts.py), [전송](../../src/kis_portfolio/services/telegram_delivery.py),
[현황](../../src/kis_portfolio/services/signal_slot_report.py), [리포트](../../src/kis_portfolio/services/total_asset_digest.py).
검증: [replay](../../tests/test_v2_signal_replay.py), [calibration](../../tests/test_v2_signal_calibration.py),
[전송](../../tests/test_telegram_delivery.py), [리포트](../../tests/test_total_asset_digest.py).

## 관련 근거

### 사례와 근거

과거 canary·초기 shadow·배포 checklist와 특정 run 사례는 [압축 구축 기록](../history/README.md)에서만 펼칩니다.

DEC-064는 public MCP tool/scope를 늘리지 않습니다. 기존 kr-1430 수동 refresh 입력은 현재 오후 14:00 Job의 호환 alias이며 run handle도 실제 slot/version과 일치해야 합니다.
