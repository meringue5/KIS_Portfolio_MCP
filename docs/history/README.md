# 구축 원문 보관 — 필요할 때만 펼치기

현재 동작은 [운영 모델](../operating-model.md), 수정 규칙은 [현행 설계 계약](../design/README.md)을 읽습니다.
이 폴더는 과거를 기본 context로 읽기 위한 목차가 아니라 **근거 회수 경로**입니다.

## 복구 가능한 원본

- [압축 원문 35개](v2-construction-2026-11-03.tar.gz) — Git 기준 `a8fdfa599ba1e4876ded726d23d577a4640eff9d`의 원본 byte 그대로.
- [파일별 경로·크기·SHA-256 / 의미 보존 위치](v2-construction-2026-11-03.manifest.json). archive 전체 SHA-256도 포함합니다.
- 내용은 기존 공개 저장소 자료뿐입니다. 새 운영 데이터·금액·계좌·credential·private evidence를 추가하지 않았습니다.
- archive 만들기 후 모든 member를 다시 읽어 원본 hash와 대조했고, 별도 임시 폴더 복원도 검증했습니다.

## 찾고 싶은 근거부터

| 왜 과거를 보는가 | 고정된 원문 / archive member |
| --- | --- |
| 당시 구조 대안·cost 조사와 결정의 맥락 | [원래 system design](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/kis-portfolio-v2-system-design.md), [delta review](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/v2-architecture-delta-review.md) |
| 특정 backfill·재구성의 preflight/dry-run/실행 순서 | [WI-021 실행](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/wi-021-s06-production-execution.md), [WI-022 실행](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/wi-022-s06-production-execution.md); member 경로는 manifest 참조 |
| 성과·risk·alert 계약을 처음 정의한 표현 | [분석 원계약](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/wi-023-portfolio-performance-contract.md), [신호 원계약](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/wi-029-signal-replay-shadow-contract.md) |
| 과거 legacy 참고값의 날짜·가정·계산 조사 | [WI-068 원계약](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/design/wi-068-legacy-total-recovery-contract.md) |
| 예전 TODO·추적표·의존 그래프의 내용 | [TODO](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md), [추적표](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/traceability-before-operations-2026-11-02.md), [그래프](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/milestone-map-before-operations-2026-11-02.md) |

위 링크는 **고정 commit의 사례**입니다. 최신 source/보안/승인/절차로 해석하지 않습니다. 현행 규칙은 통합 계약을 따르고,
왜 그런 규칙이 생겼는지 질문이 생길 때만 원문을 읽습니다. 시간순으로 전부 다시 읽을 필요는 없습니다.

## 인수와 구축 경과

[V2 인수의 현행 의미](../milestones/v2-acceptance.md)는 범위·한계·운영 책임만 남깁니다.
당시 기록이 필요하면 [MS-008 원문](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/milestones/MS-008-real-use-mcp-acceptance.md),
[MS-004 원문](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/milestones/MS-004-v2-canonicalization-retirement.md) 또는 manifest의 다른 baseline member를 찾습니다.
WI와 dated operations evidence는 별도의 사례/추적 기록으로 보존하며 현행 설명서로 자동 승격하지 않습니다.

## 로컬에서 원문을 읽거나 복원

저장소 루트에서 표준 tar만 사용합니다. 별도 도구·DB·index generator가 필요하지 않습니다.

```bash
# 한 문서만 읽기: archive 안에는 원래 repository-relative 경로가 들어 있습니다.
tar -xOf docs/history/v2-construction-2026-11-03.tar.gz docs/design/wi-023-portfolio-performance-contract.md

# 새 임시 폴더에 복원: 현재 문서 위에 덮어쓰지 않습니다.
mkdir -p /private/tmp/kis-v2-docs-restore
tar -xzf docs/history/v2-construction-2026-11-03.tar.gz -C /private/tmp/kis-v2-docs-restore
```

복원된 옛 계획의 명령·숫자·미완료 표시·기간 제한은 당시 맥락입니다. 복원 자체가 source replay·migration·배포 승인은 아닙니다.
raw 원본이 필요하면 Git에서도 `git show a8fdfa599ba1e4876ded726d23d577a4640eff9d:<member-path>`로 확인할 수 있습니다.
