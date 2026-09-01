# WI-037-S03 filing contract adoption — 2026-09-02

> Work Item: `WI-037-S03`
> 상태: in progress
> 분류: architecture/data-contract adoption
> 승인 근거: 2026-09-02 owner approval of the WI-037-S02 six-item package
> 변경 경계: SPEC and DGH canonical contracts only; code, DDL, DB, source call, credential, fixture, deployment and activation 없음

## Outcome

ADR-025와 WI-037-S02의 7-contract delta를 canonical SSOT에 `approved`로 반영하되 전부 inactive로 둔다.
기존 fundamentals/dividends umbrella는 history와 향후 orchestration 의도로 보존하지만 activation하지 않는다.

## Shared implementation constraint

filing actual과 dividend reconciliation은 schedule, watermark, quality와 실패 상태를 논리적으로 격리한다.
그러나 다음 구현은 같은 modular-monolith image, managed pipeline runner, source adapter, Bronze landing,
repository, MotherDuck, GCS와 release artifact를 재사용해야 한다. 별도 service/repository/always-on worker를
만들거나 공통 코드를 복제하지 않는다. 분리로 코드 중복 또는 운영 구성이 불필요하게 증가하면 구현 gate를
실패시키고 ADR-025를 재검토한다.

## Approved canonical delta

1. `ADR-025`
2. `dataset.filing-source-artifact` 1.0.0
3. `dataset.issuer-source-alias` 1.0.0
4. `dataset.filing-event` 2.0.0
5. `dataset.financial-fact` 2.0.0
6. `dataset.fundamental-concept-mapping` 1.0.0
7. `collection.filing-actual-v1` 1.0.0
8. `pipeline.filing-actual-v1` 1.0.0

두 existing dataset은 major version update이고 나머지 다섯 contract는 additive다. `source.opendart`와
`source.sec-edgar`는 provider/rights/auth 역할이 바뀌지 않아 1.0.0을 유지한다.

## Acceptance criteria

- [ ] SPEC에 owner-approved ADR-025와 shared implementation constraint가 기록된다.
- [ ] 7개 DGH delta가 approved/inactive 상태와 상호 참조 무결성을 가진다.
- [ ] existing umbrella contract가 active로 오해되지 않으며 dedicated filing 경로만 future implementation을 소유한다.
- [ ] requirement review, Work Item, milestone과 traceability가 같은 승인 상태를 가리킨다.
- [ ] quick/full gate가 통과하고 runtime/DB/external mutation이 없다.

## Current disposition

S03 canonical adoption을 시작했다. 승인과 activation은 분리되며 이 Work Item은 production 권한을 부여하지 않는다.
