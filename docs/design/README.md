# 현행 설계 규칙

구축 순서가 아니라 **무슨 뜻이고 언제 성립하며 어떻게 수정해야 하는가**를 설명합니다.
모든 문서는 기존 승인 계약의 재서술이며 새 제품 승인이나 현재 데이터 가용성 보증이 아닙니다.

| 질문 | 읽을 계약 |
| --- | --- |
| 전체 시스템을 이해하려면? | [운영 모델](../operating-model.md) |
| 책임·저장소·runtime 경계와 선택 이유는? | [시스템 경계](kis-portfolio-v2-system-design.md) |
| 빈 거래 구간·identity·수집 budget·lot 재구성을 믿을 조건은? | [원장·재구성](portfolio-ledger-contracts.md) |
| 평가액 변화·성과·drawdown·owner risk의 차이와 식은? | [분석](analytics-contracts.md) |
| signal 상태·상세·현황·보고·중복·배송 불확실성은? | [알림·전송](alert-delivery-contracts.md) |
| 과거 reference를 어디까지 사용할 수 있나? | [참고 이력](reference-history-contract.md) |

정확한 기능의 코드·검증은 [기능 지도](../traceability.md), 필드·버전·물리 객체·권한의 정본은 각각
[계약 registry](../../governance/catalog/), [데이터 catalog](../data-catalog.md), [보안](../security-and-secrets.md),
[요구 DEC](../requirements/kis-portfolio-data-platform-requirements.md)와 [SPEC](../../SPEC.md)입니다.

원래 조사·검토·실행·대안 비교·canary/shadow 타임라인은 [압축된 구축 원문](../history/README.md)에 있습니다.
[delivery ID 목록](kis-portfolio-v2-delivery-plan.md)은 기존 검사/추적 호환을 위한 식별자 보존이며 현재 작업 계획이 아닙니다.
