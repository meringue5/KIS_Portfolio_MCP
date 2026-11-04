# 과거 참고 이력의 사용 규칙

> 의미: 보존된 일부 관측으로 만든 **가정이 표시된 비정본 총액 수준값**. 공식 성과나 과거의 완전한 자산 상태가 아닙니다.
> 승인 경계는 DEC-062/ADR-033 및 해당 [dataset/read 계약](../../governance/catalog/read-models.toml)을 따릅니다.

## 범위와 의미

### canonical과 섞지 않는 이유

합계가 원문 component와 일치해도 빠진 해외 feeder·현금·시점 차이를 증명하지 못합니다. source consistency는
completeness가 아닙니다. 참고값은 원래 source와 현행 canonical state를 덮지 않고 별도 version/lineage로 제공합니다.
같은 날짜의 native passing state가 우선이며 reference는 quality/return/drawdown/alert/contribution 자격을 충족시키지 않습니다.

## 판단 규칙

### 승인된 bounded 계산

- 보존된 날짜별 latest overview와 **그 overview에 연결된 holding rows만** 사용합니다. 서로 다른 fetch의 계좌를 섞지 않습니다.
- 관측된 원화금액은 그대로 보존합니다. KRW가 null이고 USD 평가액이 있는 foreign position만 승인된 external FX로 환산합니다.
- 당시 유효 원화 basis를 새 FX로 덮지 않습니다. 누락 해외 cash=0의 한정 owner 가정은 누락 position=0을 허용하지 않습니다.
- 해외 position 관측이 없으면 total reference도 null입니다. 없는 수량·가격·flow·corporate action을 만들지 않습니다.
- 승인 FX는 FRED DEXKOUS/FRB H.10의 NY noon buying rate(KRW/USD), legacy date 이하 최신 nonmissing,
  최대 4 calendar days lag입니다. KIS 적용환율·한국 종가·당시 알았던 PIT로 가장하지 않는 retrospective 평가입니다.
- provider/series/rate type·요청/사용 observation date·lag·fetched time·input hash·원 timestamp·가정·분류를 보존합니다.

승인 집합은 총 27 retained dates 중 **14 recorded reference + 11 estimated reference + 2 unavailable**입니다.
따라서 25일이 labelled total-level reference이며 canonical 성과 날짜가 아닙니다. 두 unavailable 날짜는
2026-08-06/25입니다. 개별 날짜와 계산·source 검증의 원래 기록은 [압축 원문](../history/README.md)에 있습니다.

### 저장·조회·수정

`silver.portfolio_legacy_total_reference`의 grain은 recovery version+date+input hash입니다. 원본금액/reference금액,
classification·assumptions·knowledge/recorded time·FX provenance를 append-only correction/supersession으로 보존합니다.
legacy/default quarantine와 원래 행, native ledgers를 수정하지 않습니다.

`get-performance-history(include_legacy_reference=true)`가 별도 `reference_history`로 명시 opt-in합니다.
자동 fallback·보간·추정 canonical merge는 없습니다. total-only grain이므로 account filter와 결합하면
bounded unsupported-combination 오류입니다. MCP read에서 source API를 호출하지 않습니다.
materialization/recovery는 별도 승인된 bounded 작업이며 추가 provider·상시 source·전송을 자동 활성화하지 않습니다.

private Parquet manifest와 fresh local restore는 dataset을 포함합니다. rollback은 opt-in projection/version을
비활성화하고 source/가정/이력을 보존합니다.

## 변경과 검증

### 수정·검증

코드: [reference service](../../src/kis_portfolio/services/legacy_total_reference.py),
[Remote projection](../../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py).
검증: [legacy cases](../../tests/test_legacy_total_reference.py), [Remote](../../tests/test_remote_v2_warehouse.py).
필수 oracle은 native precedence, missing position→null, explicit zero-cash 가정의 한계,
account-filter 오류, default quarantine 유지와 source/계산 hash입니다.

## 관련 근거

### 사례와 근거

실제 인수 기록은 [WI-068](../work-items/WI-068-retained-legacy-history-recovery.md)에 연결합니다.
