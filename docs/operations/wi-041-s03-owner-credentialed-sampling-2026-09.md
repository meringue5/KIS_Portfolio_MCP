# WI-041-S03 owner-credentialed U.S. consensus sampling — 2026-09-01

> Work Item: `WI-041-S03`
> 분류: research-only source and rights sampling
> 변경 경계: Alpha Vantage 무료 개인 key 발급, Secret Manager 보관, 최신 미국 직접주식 최대 4 physical calls;
> 유료 전환, production 활성화, 원문 저장, DB/DDL/pipeline/MCP/deployment 변경 없음

## 현재 결론

Alpha Vantage 무료 key로 `EARNINGS_ESTIMATES`의 실제 schema를 처음 확인했지만, 현재 상태로는
`dataset.consensus-snapshot`의 canonical point-in-time source로 승인할 수 없다.

- owner가 무료 계정/API key 발급과 개인 이용 약관 수락을 승인했다. credential은 대화·repository·DB에
  출력하거나 저장하지 않고 GCP Secret Manager의 `kis-portfolio-alpha-vantage-api-key` version 1에만 저장했다.
  resource label은 `service=kis-portfolio`, `provider=alpha-vantage`, `environment=research`이고 runtime accessor나
  Cloud Run/Job reference는 추가하지 않았다.
- latest canonical overview의 `NASD / overseas_direct / equity / USD` distinct issuer count는 4개였다. 실제 symbol은
  증적에 남기지 않고 `US-01`~`US-04`로 익명화했다.
- 총 4 physical calls를 재시도·pagination 없이 수행했다. `US-01`은 HTTP 200의 실제 estimate payload를
  반환했고, `US-02`~`US-04`는 HTTP 200의 provider `Information` envelope만 반환했다. 따라서 schema 증적은
  1개 issuer에 한정되고 held-scope coverage는 1/4로 실패했다.
- 성공 표본은 `symbol`과 41-row `estimates` 배열을 반환했다. 모든 관측 field는 string이고 raw value는
  저장하지 않았다.
- EPS에는 analyst count, average/high/low, 7/30/60/90일 전 average와 trailing 7/30일 상향·하향 revision count가
  있었다. Revenue에는 analyst count와 average/high/low가 있었고, row에는 `date`와 `horizon`이 있었다.
- provider observation/publication time, immutable revision id, source estimate population identity와 historical
  snapshot lineage는 없었다. 7/30/60/90일 전 비교값은 현재 응답 안의 rolling comparison이며 과거 시점에
  실제로 알 수 있었던 payload를 재현하는 revision ledger가 아니다.
- 그러므로 written retention right가 생기더라도 이 endpoint 하나만으로 발표 직전 consensus나 과거
  point-in-time replay를 backfill할 수 없다. 권리가 허용된다면 향후 수집 시점부터 forward-only snapshot을
  축적해 current outlook/revision signal 후보로 재평가할 수 있을 뿐이다.

## 호출 및 데이터 취급 증적

| 단계 | 결과 | 외부 호출 | 영속화 |
| --- | --- | ---: | --- |
| first local probe | 임시 script가 project `.env`를 찾지 못해 MotherDuck 연결 전에 중단 | Alpha 0 | none |
| corrected held-scope probe | latest overview에서 미국 직접주식 4개 확인 | Alpha 0 | none |
| Alpha sample | 1 actual payload, 3 `Information` envelopes | Alpha 4 | sanitized schema only in this document |
| credential storage | Secret Manager resource/version metadata 확인 | provider data 0 | secret version 1 only |

계좌번호, issuer symbol, API key, raw estimate value, raw provider message와 raw response는 문서·DB·GCS에 저장하지
않았다. API key 전달에 사용한 mode `0600` 임시 파일과 조사용 임시 script는 실행 직후 삭제했다.

## 성공 표본의 sanitized schema

Top level은 `symbol`, `estimates` 두 field다. `estimates`는 41 rows였고 다음 18 fields가 관측됐다.

| Field group | Fields | Observed quality |
| --- | --- | --- |
| identity/horizon | `date`, `horizon` | 41/41 non-null; provider knowledge/revision time은 없음 |
| EPS population/range | `eps_estimate_analyst_count`, `eps_estimate_average`, `eps_estimate_high`, `eps_estimate_low` | 41/41 non-null; individual analyst distribution 없음 |
| EPS rolling comparisons | `eps_estimate_average_7_days_ago`, `_30_days_ago`, `_60_days_ago`, `_90_days_ago` | 41/41 non-null; historical snapshot identity 아님 |
| EPS revision counts | `eps_estimate_revision_up_trailing_7_days`, `_up_trailing_30_days`, `_down_trailing_7_days`, `_down_trailing_30_days` | up fields non-null; down-7은 22/41 null, down-30은 18/41 null |
| Revenue population/range | `revenue_estimate_analyst_count`, `revenue_estimate_average`, `revenue_estimate_high`, `revenue_estimate_low` | 41/41 non-null; rolling comparison/revision fields 없음 |

모든 non-null field의 JSON type은 string이었다. 숫자, date, horizon의 parser와 unit/fiscal-basis contract는
production activation 전에 별도로 명시해야 하며 string을 암묵적으로 number/date로 채택하지 않는다.

## Gate disposition

| Required activation property | S03 observation | Disposition |
| --- | --- | --- |
| metric identity and range | EPS/revenue average, high, low and count 명시 | schema candidate only |
| analyst distribution/population | count와 high/low만 존재; population definition과 individual distribution 없음 | incomplete |
| revision signal | EPS rolling average와 revision counts 존재 | current signal candidate |
| historical PIT/no leakage | publication/knowledge time, revision id와 historical payload lineage 없음 | failed |
| held-issuer coverage | 1 actual payload / 4 physical calls | failed |
| retention/backup/internal LLM right | 공개 약관은 명시적 답을 주지 않음 | written answer pending |
| cost/call budget | 무료 key; 이번 조사 4 calls | research only; production unapproved |

`source.consensus-provider-tbd`, `collection.consensus-research-later`와 `dataset.consensus-snapshot`은 계속
`proposed`이며 `backup_policy = excluded`를 유지한다. Secret 생성은 source activation이나 production 수집
승인이 아니다.

## Provider에 보낼 rights inquiry 초안

아래 외부 질의는 아직 전송하지 않았다. owner가 representational communication을 별도 승인하면
`support@alphavantage.co`에 보낸다.

> I use the free Alpha Vantage API solely for a private, single-user portfolio-analysis project. May I retain
> EARNINGS_ESTIMATES responses in a private cloud warehouse, keep encrypted/private backups, compute and retain
> derived metrics, and let my private LLM/MCP tools analyze the retained data? If the API account or subscription
> ends, may I continue retaining those private snapshots and derived results? Nothing will be redistributed or
> exposed publicly. Please identify any plan or attribution requirements that apply.

## Remaining action

1. owner approval을 받아 rights inquiry를 전송하고 provider의 written answer를 보존한다.
2. 3개의 `Information` envelope 원인은 raw message를 저장하지 않은 이번 bounded run에서 단정하지 않는다.
   추가 호출은 새 call budget과 retry spacing을 승인한 후에만 수행한다.
3. rights가 허용돼도 historical PIT failure 때문에 Alpha Vantage를 DEC-021의 단독 canonical source로 채택하지
   않는다. forward-only current signal로 범위를 축소할지는 별도 source/data-contract 결정으로 남긴다.

## Closeout state

`WI-041-S03`은 credential/schema 단계까지 진행됐지만 explicit rights evidence가 없고 held-scope coverage가
부분적이므로 `in_progress`다. Parent `WI-041`과 MS-003은 `proposed`를 유지한다.
