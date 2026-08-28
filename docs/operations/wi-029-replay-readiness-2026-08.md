# WI-029 replay and live-readiness evidence — 2026-08-28

## Scope and safety boundary

Configured MotherDuck의 V2 price revisions와 current instrument classification을 aggregate-only로 읽었다.
provider sample은 현재 해외 보유 symbol만 대상으로 KIS 상품정보 4회와 SEC issuer submissions 3회로 제한했다.
DB migration, source observation write, metric/candidate publish, schedule 변경과 외부 경보 전송은 수행하지 않았다.

실제 보유 symbol, account, 평가액과 source payload는 공개 저장소에 기록하지 않는다. 공식 분류 근거의
canonicalized aggregate hash는 `02aa0de08312cfb7e3de2143cb25a3823c5b6409e97120b96d897b6f84d0aa86`이다.

## Eligibility audit

| Gate | Aggregate evidence | Result |
| --- | ---: | --- |
| adjusted price revisions | 7,576 latest-revision observations, 18 instruments | pass |
| date span | 2023-08-28 through 2026-08-27, 1,096 calendar days | pass |
| provenance | all `retrospective_reconstructed` | calibration only |
| KIS product identity | 4/4 current overseas symbols matched exact product lookup | pass |
| SEC issuer identity | 4/4 symbols matched 3 exact CIK records | pass |
| resolved replay classes | ETF 14 instruments; stock 3; REIT 1 | pass |
| ETF constituent coverage | unavailable by DEC-049 / ADR-024 | opaque-security limitation |

The KIS and SEC evidence is applied only in memory for this readiness replay. Production classification still requires
managed V2 migrations and append-only `dataset.instrument-master` observations/versions; this report does not pretend
those writes happened.

## Reconstructed replay result

- Report hash: `a9048d06d758d5923899f15f2a6a034e9bb5f2b7e9efc2844706df6ebf13dc8d`
- Eligible observations: 7,576
- Stateful delivery candidates: 1,364
- Combined per-slot budget: median 0, nearest-rank p95 4; target median <= 2 and p95 <= 5 passed
- ETF: 4,564 observations, 729 dates, multiplier 0.75, 864 candidates, median 1, p95 5
- Stock: 2,259 observations, 753 dates, multiplier 0.75, 403 candidates, median 0, p95 2
- REIT: 753 observations, 753 dates, multiplier 0.75, 97 candidates, median 0, p95 1
- All three observed classes meet the 1,096-day and 600-session readiness floor.

These 1,364 rows are state transitions over three reconstructed years, not messages already sent and not an estimate
of investment-return accuracy. A passing median/p95 budget does not substitute for owner false-positive/miss labels.

## Remaining activation gates

1. Apply managed migrations 0011 through 0013 with the backup/restore gate.
2. Append the official overseas classification evidence without rewriting prior unknown versions.
3. Persist the immutable calibration report and complete owner false-positive/miss review.
4. Activate DB-only shadow evaluation with Telegram structurally unavailable.
5. Observe at least 14 elapsed days, reconcile expected slots and obtain owner rule-version approval.

Until those gates pass, WI-030 remains not ready and no Telegram delivery is authorized.
