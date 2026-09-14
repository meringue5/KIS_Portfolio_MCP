# WI-049-S03 Artifact Registry 유지/제거 명세 — 2026-09

## 판정

2026-09-14 06:05 KST의 읽기 전용 재조사에서 Artifact Registry 2개 repository, 6개 package, 108개
digest를 확인했다. 현행 WI-035 보수 정책을 그대로 적용한 결과는 **유지 49개, 제거 후보 59개**다.

이 문서 자체는 삭제 승인이 아니다. 기계 판독 정본은
`governance/project/evidence/wi049/artifact-cleanup-spec-2026-09-14.json`이며 `mode=dry_run`,
`apply_allowed=false`, `owner_approved=false`다.

## 분류 규칙

다음 중 하나라도 참이면 유지한다.

1. 현재 Cloud Run traffic, service template 또는 예약 Job이 참조한다.
2. V2 forward recovery에 필요한 digest다.
3. tag가 하나라도 있다.
4. package별 최신 3개에 포함된다.
5. 생성 후 30일이 지나지 않았다.

따라서 제거 후보는 **모든 유지 사유가 없고, tag가 없으며, 최신 3개 밖이고, 30일 이상 지난 digest**로
한정된다. `kis-portfolio` 정본 repository의 33개 digest는 모두 유지한다.

## 현재 운영 보호 digest

| 용도 | Repository | Digest |
| --- | --- | --- |
| Auth 100% traffic | `kis-portfolio` | `b3b620eb...85ad43` |
| Remote 100% traffic + Auth tagged candidate | `kis-portfolio` | `c8abbb57...dfcf6b` |
| Remote template + core 10:00/14:30/16:00 Jobs | `kis-portfolio` | `a35e6899...8208ab` |
| 국내 주문 이력 Job | `cloud-run-source-deploy` | `c3b15efd...19b49` |
| 해외 거래 이력 Job | `cloud-run-source-deploy` | `7a0846ac...b7346f` |
| token warmup Job | `cloud-run-source-deploy` | `394ddf8c...cba3b2` |

위 digest는 제거 후보 집합과 교집합이 없다.

## Package별 결과

| Repository / package | 전체 | 유지 | 제거 후보 | 제거 후보 논리적 용량 |
| --- | ---: | ---: | ---: | ---: |
| `cloud-run-source-deploy/kis-portfolio-auth` | 20 | 3 | 17 | 1,735,273,907 bytes |
| `cloud-run-source-deploy/kis-portfolio-domestic-order-history` | 13 | 3 | 10 | 1,023,759,607 bytes |
| `cloud-run-source-deploy/kis-portfolio-overseas-transaction-history` | 7 | 3 | 4 | 409,576,260 bytes |
| `cloud-run-source-deploy/kis-portfolio-remote` | 29 | 4 | 25 | 2,520,314,639 bytes |
| `cloud-run-source-deploy/kis-portfolio-token-warmup-dry-run` | 6 | 3 | 3 | 307,189,089 bytes |
| `kis-portfolio/kis-portfolio` | 33 | 33 | 0 | 0 bytes |
| **합계** | **108** | **49** | **59** | **5,996,113,502 bytes** |

용량은 각 image manifest의 `imageSizeBytes` 합계다. layer 공유와 Artifact Registry 과금 방식을 반영한
실제 회수 용량 또는 절감액이 아니므로 비용 절감 보장으로 사용하지 않는다.

## 유지 대상

- `cloud-run-source-deploy`: active Job digest, package별 최신 3개, `latest` tag, 30일 미만 digest를 합쳐
  16개를 유지한다.
- `kis-portfolio`: 현재 V2 운영·forward recovery·과거 검증의 Git SHA tag가 붙은 31개와 아직 30일 미만인
  untagged 2개, 총 33개를 모두 유지한다.
- exact digest 목록은 machine-readable 정본의 `retain_targets`가 소유한다.

## 제거 대상

- exact 후보는 `cloud-run-source-deploy`의 59개뿐이다.
- package 분포는 Auth 17, 국내 주문 이력 10, 해외 거래 이력 4, Remote 25, token warmup 3이다.
- 모든 후보는 현재 조사 시점에 untagged, 30일 이상, package별 최신 3개 밖이며 active/forward-recovery
  참조가 없다.
- exact digest 목록은 machine-readable 정본의 `removal_targets`가 소유한다. wildcard, package 전체 삭제,
  repository 삭제 또는 tag 삭제로 이 명세를 넓힐 수 없다.

## 실행 전 재검증과 승인 경계

실제 삭제 전에 다음 조건을 모두 다시 확인해야 한다.

1. fresh inventory가 정본의 108개 identity와 일치하고 새 active/tag/reference가 없어야 한다.
2. 여섯 운영 보호 digest와 모든 retain digest가 존재해야 한다.
3. 삭제 명령은 59개 exact package@digest만 대상으로 하며 wildcard와 `--delete-tags`를 금지한다.
4. master GitHub Actions의 별도 S03 target만 apply할 수 있어야 한다.
5. 삭제 후 6개 예약 Job, 6개 Scheduler, 2개 서비스, `/health` 200, unauthenticated `/mcp` 401과
   owner-authenticated 대표 읽기를 검증한다.
6. 15개 보호 이력의 aggregate count가 감소하지 않고 WI-048 복구 index가 유지되어야 한다.
7. owner는 이 exact 59-digest artifact를 별도로 승인해야 한다. inventory가 달라지면 승인은 무효이며 새
   명세를 만든다.

현재 단계에서는 Artifact Registry를 포함한 어떤 운영 리소스도 변경하지 않았다.

## Owner approval

2026-09-14 owner가 machine-readable 정본의 59개 `removal_targets` 전체 정리를 승인했다. 별도 승인 artifact
`governance/project/evidence/wi049/artifact-cleanup-approval-2026-09-14.json`은 명세 canonical SHA-256
`bea06488...3ee9a`, exact count 59와 제외 변경군을 고정한다. 이 승인은 inventory drift나 tag/reference 변경을
허용하지 않는다.

구현 후 live dry-run은 59개 승인 대상을 다시 확인하고 `deleted_targets=[]`, `status=dry_run_pass`를
반환했다. master GitHub Actions 외부에서는 `--apply`가 실패한다.

## 실행 결과

2026-09-14 master workflow run `34784520628`이 fresh inventory, tag와 live-reference gate를 다시 통과한 뒤
59개 exact `package@digest`를 삭제했다. workflow의 삭제 후 검사는 모든 removal target 부재와 모든 retain
target 존재를 확인했고, Auth/Remote health 200 및 unauthenticated `/mcp` 401 smoke도 통과했다.

별도 live 재조사에서 현재 49개 digest가 정본의 retain 집합과 정확히 일치했고 removal 잔존과 retain 누락은
각각 0이었다. 여섯 live image reference는 모두 retain 집합에 속했다. 2개 서비스, 6개 예약 Job, 6개
Scheduler와 private WI-048 복구 index가 유지됐으며, 15개 보호 history aggregate count도 S01 기준선과
동일했다. 기계 판독 결과는
`governance/project/evidence/wi049/artifact-cleanup-result-2026-09-14.json`이 소유한다.

S03는 서비스 배포, traffic revision 또는 live image reference를 변경하지 않았다. 따라서 WI-048 closeout의
owner-authenticated 대표 읽기는 동일한 운영 revision에 계속 적용되며, workflow는 삭제 후 그 revision의 두
health endpoint와 unauthenticated 401 경계를 다시 검증했다.

5,996,113,502 bytes는 삭제된 image manifest의 논리적 합계일 뿐 layer 공유를 반영한 실제 과금 절감량이
아니다. Tag, data, backup, bucket, Firestore, IAM, Secret, Scheduler, Cloud Run Job/service는 이 실행에서
변경하지 않았다.
