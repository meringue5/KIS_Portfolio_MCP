# WI-026 ETF provider rights review — 2026-08-28

## Decision

`TIME`, `KoAct`, `RISE`, `PLUS`의 공식 사이트가 ETF 구성종목을 사람이 조회하거나 내려받을 수 있게
제공하는 사실은 확인했다. 그러나 `WI-026`이 요구하는 자동 수집, GCP 내 처리, raw 원문 보관과 파생
데이터 이용을 모두 허용하는 명시적 근거는 확인하지 못했다. 공개 접근 가능성은 이용권한이 아니므로 네
profile은 계속 `proposed` + `fixture_only`이며 production network registry에는 진입하지 않는다.

이 기록은 법률 자문이 아니라 Data Governance Harness가 production 수집을 허용할 수 있는지 판단한
운영 증거다. 불명확한 권리는 `unknown`으로 유지하고 금지로 확대 해석하지 않는다.

## Review method

- Evidence date: `2026-08-28 KST`
- Scope: 현재 보유 ETF에 연결된 네 issuer profile과 KRX의 허가형 대안
- Rights gate: `automation`, `cloud_processing`, `raw_retention`, `derived_use`가 모두 `allowed`여야 production
  activation 가능
- Safety boundary: 로그인 우회, 비공개 endpoint 탐색, 다운로드 자동화와 production 호출은 수행하지 않음
- Existing cross-check: KIS 30-row 구성 조회는 completeness source가 아니며 공식 look-through 대체재로 쓰지 않음

## Provider findings

| Sub-item | Official evidence | Finding | Contract result |
| --- | --- | --- | --- |
| `WI-026-S01` TIME | [TIMEFOLIO official site](https://www.timefolio.co.kr/)는 ETF 정보와 `All Rights Reserved` 표시를 제공 | 구성자료의 자동 수집·클라우드 처리·raw 보관·파생 이용에 대한 명시적 허가를 찾지 못함 | 네 권리 필드 `unknown`; `fixture_only`; blocked |
| `WI-026-S02` KoAct | [KoAct product page](https://www.samsungactive.co.kr/etf/view.do?id=2ETFJ9)는 구성종목과 전체 다운로드를 제공하고 [official home](https://www.samsungactive.co.kr/)은 `ALL RIGHTS RESERVED`를 표시 | 사람이 내려받을 수 있다는 사실 외 네 production 권리를 부여하는 조건을 찾지 못함 | 네 권리 필드 `unknown`; `fixture_only`; blocked |
| `WI-026-S03` RISE | [RISE PDF page](https://www.riseetf.co.kr/prod/document/pdf)는 PDF를 매일 공표한다고 안내하고 사이트는 `ALL RIGHTS RESERVED`를 표시 | 구성 PDF 자체에 대한 자동 처리·보관·파생 이용 허가를 찾지 못함. KB의 다른 공개 자료에 있는 재사용 제한은 참고 근거일 뿐 이 profile의 권리를 임의로 `prohibited`로 바꾸는 근거로 쓰지 않음 | 네 권리 필드 `unknown`; `fixture_only`; blocked |
| `WI-026-S04` PLUS | [PLUS legal notice](https://www.plusetf.co.kr/)는 사이트와 다운로드 파일을 소유 정보자산으로 규정하고 고객 편의를 위해 제공하며 지적재산권을 부여하지 않는다고 명시 | 현재 조건만으로는 production automation과 raw/derived use를 허가할 수 없음 | 네 권리 필드 `unknown`; `fixture_only`; blocked |

## Sanctioned alternative review: KRX Open API

[KRX Open API terms](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp)는 승인받은 API 이용자가
데이터를 활용해 응용프로그램과 서비스를 개발하는 경로를 정의한다. 다만 회원가입, 약관 동의, 인증키와
API별 활용 승인이 필요하며 비상업적 이용 등 해당 조건을 따라야 한다.

[KRX usage guide](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp)의 승인 절차와
[current service list](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)를 확인했지만,
현재 목록의 ETF 항목은 일별매매정보이며 ETF PDF/구성종목 전체를 제공하는 API는 확인되지 않았다. 따라서
KRX Data Marketplace 웹 화면을 Open API 약관의 허가 범위로 간주하거나 자동 수집해서는 안 된다.

## Blocking condition and resume gate

다음 중 하나가 충족되기 전에는 `WI-026`과 네 sub-item을 재개하지 않는다.

1. 공급자가 자동 수집, GCP 처리, private raw 보관과 개인 분석용 파생 이용을 서면 또는 적용 가능한 약관으로
   명시적으로 허용하고, 허용 host·호출 예산·증거일을 profile에 기록한다.
2. KRX 또는 다른 정식 데이터 제공자가 ETF 전체 구성종목을 제공하는 승인형 API/data product를 제공하고,
   owner가 해당 약관·비용을 승인하며 인증키/라이선스를 발급받는다.

재개 시 provider별로 별도 production profile revision을 만들고, 고정 host/argument adapter, private raw landing,
format drift quarantine, lineage, 비용 측정과 restore 증거를 같은 sub-item에서 검증한다. 과거 구성종목이
제공되지 않는 provider에 대해서는 activation 이후 forward history만 공식 데이터로 인정한다.

## Operational evidence

- Production source calls: `0`
- Profile changes: `0`; 기존 `unknown`/`fixture_only` 유지
- Production network registry: 기존 `0` profiles 유지
- Data writes, schedules, GCP resources and secrets: `0`
- User action required now: 없음. 허가형 데이터 경로를 새로 계약하려는 시점에만 owner 결정을 요청한다.
