## Outcome

사용자 또는 운영 관점의 결과를 적습니다.

## Traceability

- Issue / Work Item:
- Requirement / DEC:
- ADR:

## Classification

- Type: defect / clarification / change / architecture / incident / maintenance / governance
- Contract gap or contract change:

## Impact

- Architecture:
- Data/schema/backup:
- Security/privacy:
- MCP/API compatibility:
- Deployment/rollback:
- Cost/SLO:

영향이 없으면 `none`과 근거를 적습니다.

## Verification

- [ ] `bash scripts/check.sh full`
- [ ] 관련 migration·restore·remote smoke 또는 운영 증거
- [ ] traceability와 owning documents 갱신
- [ ] secret, raw token, 전체 계좌번호가 diff·로그·본문에 없음

## Acceptance and rollback

- Acceptance evidence:
- Remaining risk:
- Rollback:
