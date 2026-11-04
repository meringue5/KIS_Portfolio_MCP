# 운영 지식

이 서비스는 **관측한 사실을 보존하고, 믿을 수 있는 범위만 계산·표시·전송**합니다. 이 문서는 구축 일지가 아니라
현재 시스템을 이해하고 수정하는 입구입니다. 별도 DB·도구 없이 일반 Markdown과 기존 코드/계약을 사용합니다.

## 평소에 읽을 것

1. [운영 모델](operating-model.md): 총자산/성과/관측 현금의 차이, 근거·시간·identity·실패 판정과 선택 이유.
2. [기능 수정 지도](traceability.md): 해당 기능의 요구 → 코드 → 테스트 → 한계. 사례는 필요할 때만 열기.
3. 작업에 따라 [TODO](../TODO.md), [증상 대응](troubleshooting.md), [운영 런북](operations/steady-state-operations-runbook.md).

운영 작업을 접수하거나 닫을 때는 [Project OS의 운영 진입점](governance/project-operating-system.md#0-운영-작업의-진입점)을 따릅니다.

## 더 정확한 규칙이 필요할 때

| 질문 | 현행 설명 / 정본 |
| --- | --- |
| 어디까지가 누구 책임인가? | [시스템 경계와 이유](design/system-contract.md), [코드 구조](../ARCHITECTURE.md) |
| 언제 거래 없음/재구성/성과/배송을 믿는가? | [원장](design/portfolio-ledger-contract.md), [분석](design/analytics-contract.md), [알림](design/alert-delivery-contract.md), [참고 이력](design/reference-history-contract.md) |
| 값이 어떤 단계에서 공식 결과가 되는가? | [데이터 흐름과 판정 경계](data-pipeline.md), [객체 catalog](data-catalog.md), [versioned 계약](../governance/catalog/) |
| 제품에 무엇을 약속했는가? | [인수된 의미·제외 범위](milestones/v2-acceptance.md), [승인 요구/DEC](requirements/kis-portfolio-data-platform-requirements.md), [SPEC/ADR](../SPEC.md) |
| 실제 실행·접근·복구를 어떻게 하는가? | [연결](remote-mcp-v2-migration.md), [보안](security-and-secrets.md), [배포](deployment.md), [백업](backup.md), [비용 가드](operations/production-cost-release-guardrails.md) |
| 작업·승인·상태의 소유자는? | [Project OS](governance/project-operating-system.md), 개별 [WI](work-items/), [identity/dependency registry](../governance/project/milestones.toml) |

의미 요약은 기존 계약을 이해하기 위한 설명입니다. 새 기능·source·권한을 승인하거나 현재 데이터 가용성을
선언하지 않습니다. 상세 정본과 충돌하면 요구를 조용히 완화하지 말고 소유 작업에서 확인합니다.

## 특정 사례가 필요할 때만

‘왜 이 규칙이 생겼나’는 운영 모델의 [사례 링크](operating-model.md#사례는-규칙의-근거가-필요할-때만)로 내려갑니다.
옛 설계 대안·일회성 실행·Wave·마일스톤 경과·이전 TODO는 [검증된 원문 압축본](history/README.md)에 보존했습니다.
날짜별 operations/WI는 근거/추적 기록이며 평소의 필수 읽기 순서가 아닙니다.

[문서 분류](../governance/project/v1-document-disposition.toml)는 기존 검사 절차를 유지합니다.
