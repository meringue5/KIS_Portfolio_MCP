# GCP V2 State and Secret Foundation — 2026-08-28

## Scope and authorization

DEC-045와 WI-005에 따라 기존 resource를 보존하면서 합의된 Secret Manager·Firestore 기반만
create-or-verify했다. Cloud Run 배포, IAM 변경, production traffic cutover와 secret payload read/write는
수행하지 않았다. 병렬 MotherDuck migration 증거는
[MotherDuck V2 Parallel Foundation](./motherduck-v2-foundation-2026-08.md)이 소유한다.

## Preflight inventory

- active account: `outerlight@gmail.com`
- project: `grand-forge-279904`
- Secret Manager API: enabled
- existing KIS Portfolio secret names: 23개; payload는 조회하지 않음
- Firestore API: disabled였으며 DEC-045에 따라 enabled
- existing database: `(default)`, `DATASTORE_MODE`, `asia-northeast3`, free tier, created 2025-02-16

## Provisioned result

| Resource | Result |
| --- | --- |
| Firestore API | enabled |
| `kis-portfolio-state` | `FIRESTORE_NATIVE`, Standard, `asia-northeast3` |
| Delete protection | enabled |
| PITR / managed backup / TTL deletes | disabled; 별도 비용 승인 전 사용하지 않음 |
| State schema marker | `system_config/state-schema-v1` write/read verified |
| Lease smoke | contender exclusion, fencing token 1, owner release verified |
| Existing `(default)` Datastore | unchanged |
| Existing Secret Manager entries | unchanged; no duplicate created |

## Cost boundary

named database는 free quota가 없으나 생성·보유 자체의 고정비는 없고 operation/storage 사용량만 과금된다.
공식 Seoul Standard 단가는 기본 모델에서 document reads $0.03/100,000, writes $0.09/100,000,
deletes $0.01/100,000이며 storage도 사용량 기준이다. 이 앱은 realtime listener나 대량 document scan을
사용하지 않고 short-lived token·lease·run request만 저장한다. 비용은 월간 cost baseline에 별도 SKU로
추적하고 35,000/42,500/50,000원 gate를 유지한다.

근거: [Firestore 가격](https://cloud.google.com/firestore/pricing),
[database 생성과 named client](https://cloud.google.com/firestore/docs/manage-databases).

## Reproduction

```bash
gcloud firestore databases list --project grand-forge-279904
uv run python scripts/bootstrap_firestore_state.py \
  --project grand-forge-279904 \
  --database kis-portfolio-state \
  --apply --use-gcloud-token
```

위 bootstrap은 secret 값을 출력하거나 저장하지 않는다. `--use-gcloud-token`은 현재 gcloud access token을
프로세스 메모리에서만 사용한다.
