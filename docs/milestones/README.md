# Milestone and Work Item control

Milestone은 승인된 요구와 설계 delivery item을 실행 가능한 Work Item으로 묶는 기준선이다. 식별자와 관계의
machine-readable SSOT는 `governance/project/milestones.toml`, 상태·작업·증거의 SSOT는 개별
`docs/work-items/WI-*.md`, 전체 연결은 `docs/traceability.md`가 담당한다.

## 상위 설계와 매핑 문서

| 알고 싶은 것 | 문서 |
| --- | --- |
| V2의 시스템 구성·경계 | [`docs/design/kis-portfolio-v2-system-design.md`](../design/kis-portfolio-v2-system-design.md) |
| 승인 설계를 구현 단위로 나눈 계획 | [`docs/design/kis-portfolio-v2-delivery-plan.md`](../design/kis-portfolio-v2-delivery-plan.md) |
| milestone별 outcome·인수 조건·사람이 읽는 순서 | 이 문서와 [`MS-002`](./MS-002-portfolio-analytics-alerting.md), [`MS-003`](./MS-003-enrichment-remote-cutover.md), [`MS-004`](./MS-004-v2-canonicalization-retirement.md) |
| Work Item identity·dependency·sequence의 정본 | [`governance/project/milestones.toml`](../../governance/project/milestones.toml) |
| 요구·결정·구현·증거 연결 | [`docs/traceability.md`](../traceability.md) |

아래 그래프는 registry의 관계를 사람이 읽기 쉽게 투영한 것이다. 관계가 충돌하면 그래프가 아니라
`governance/project/milestones.toml`이 우선한다. 화살표 `A → B`는 **B가 A의 완료를 요구한다**는 뜻이다.

## 프로그램 전체 마일스톤

```mermaid
flowchart LR
    MSGOV["MS-GOV<br/>Project OS<br/>closed"]
    MS1["MS-001<br/>Canonical portfolio + managed collection<br/>closed"]
    MS2["MS-002<br/>Analytics + risk signals + Telegram<br/>in progress"]
    MS3["MS-003<br/>Enrichment + Remote MCP V2 + cutover<br/>proposed"]
    MS4["MS-004<br/>V2 canonicalization + V1 retirement<br/>proposed"]

    MS1 --> MS2 --> MS3 --> MS4
    MSGOV -. governs .-> MS2
    MSGOV -. governs .-> MS3
    MSGOV -. governs .-> MS4

    classDef closed fill:#d7f5df,stroke:#2d7a46,color:#173b24;
    classDef active fill:#fff1bf,stroke:#9a6b00,color:#4b3500;
    classDef proposed fill:#eef1f5,stroke:#667085,color:#344054;
    class MS1,MSGOV closed;
    class MS2 active;
    class MS3,MS4 proposed;
```

이 마일스톤 화살표는 현재 승인된 **formal start gate**다. 따라서 MS-002가 닫히기 전에는 MS-003의
읽기 전용 조사·설계 준비는 가능하지만, production code·data·infrastructure를 바꾸는 구현 착수는 현재
baseline상 허용되지 않는다. 조기 병행 구현을 원하면 MS-003의 `depends_on = ["MS-002"]`를 바꾸는 별도
governance 결정과 revision log가 먼저 필요하다.

## 완료된 기반에서 현재 위치까지

다음 그래프는 MS-001과 MS-002의 실제 Work Item dependency를 보여준다. 초록색은 닫힌 작업, 노란색은
현재 관찰 중인 작업, 회색 점선 경로는 초기 V2에서 제외되어 역사만 보존하는 ETF 작업이다.

```mermaid
flowchart LR
    subgraph M1F["MS-001 — foundation"]
        W9["WI-009<br/>portfolio ledger"] --> W10["WI-010<br/>trade / lot / thread"]
        W10 --> W11["WI-011<br/>Firestore state"] --> W12["WI-012<br/>managed collection"]
        W9 --> W11
        W9 --> W12
        W10 --> W12
    end

    subgraph M2F["MS-002 — analytics and alert foundation"]
        W13["WI-013<br/>metric foundation"] --> W14["WI-014<br/>readiness review"]
        W14 --> W15["WI-015<br/>price history"] --> W16["WI-016<br/>broker correction"]
        W16 --> W17["WI-017<br/>instrument routing"]
        W19["WI-019<br/>trend metrics"]
        W20["WI-020<br/>cash events"] --> W21["WI-021<br/>3-year trade/cash"]
        W36["WI-036<br/>corporate actions"]
        W22["WI-022<br/>position/lot reconstruction"]
        W23["WI-023<br/>return/contribution/drawdown"]
        W24["WI-024<br/>thread risk plan"]
        W25["WI-025<br/>lot/thread risk metrics"]
        W33["WI-033<br/>valuation-change contribution"]
        W28["WI-028<br/>alert ledger"]
        W29A["WI-029 / S05<br/>shadow calibration"]
        W26["WI-026<br/>ETF constituents<br/>rejected"]
        W27["WI-027<br/>ETF look-through<br/>rejected"]

        W13 --> W19
        W15 --> W19
        W13 --> W20
        W16 --> W20
        W16 --> W21
        W15 --> W36
        W21 --> W22
        W36 --> W22
        W9 --> W23
        W15 --> W23
        W22 --> W23
        W20 --> W23
        W21 --> W23
        W10 --> W24
        W22 --> W24 --> W25
        W15 --> W25
        W19 --> W25
        W22 --> W25
        W9 --> W33
        W13 --> W33
        W19 --> W28
        W23 --> W28
        W25 --> W28
        W33 --> W28 --> W29A
        W12 -.-> W26
        W17 -.-> W26 -.-> W27
        W9 -.-> W27
        W17 -.-> W27
    end

    W9 --> W13
    W12 --> W13
    W10 --> W22
    W14 --> W17

    classDef closed fill:#d7f5df,stroke:#2d7a46,color:#173b24;
    classDef active fill:#fff1bf,stroke:#9a6b00,color:#4b3500;
    classDef rejected fill:#eef1f5,stroke:#98a2b3,color:#667085;
    class W9,W10,W11,W12,W13,W14,W15,W16,W17,W19,W20,W21,W36,W22,W23,W24,W25,W33,W28 closed;
    class W29A active;
    class W26,W27 rejected;
```

### 그래프에서 압축한 초기·거버넌스 Work Item

- `WI-000`~`WI-008`은 현재 milestone registry가 도입되기 전 Project OS, architecture, Data Governance,
  source inventory, V2 foundation과 V1→V2 전환을 만든 bootstrap/history다. 현재 실행순서를 결정하지 않으므로
  위 제품 dependency graph에는 넣지 않았고, 상태와 증거는 각 Work Item과 `docs/traceability.md`에 보존한다.
- MS-GOV 경로는 `WI-018 → WI-031 → WI-034 → WI-052 → WI-053`이며 모두 닫혔다. 이 경로가 milestone
  identity, MS-003/004 baseline, 잔여 delivery ownership과 ETF 초기 V2 제외 결정, 이 dependency map을
  만들었다.
- 따라서 `docs/work-items/`에 파일이 있지만 그래프에 없는 번호가 곧 누락 작업을 뜻하지는 않는다.

## 현재 위치와 남은 Work Item 의존성

완료된 선행 Work Item은 그래프의 복잡도를 줄이기 위해 생략했다. 아래에는 아직 닫히지 않은 경로와
그 사이의 실제 dependency만 표시한다.

```mermaid
flowchart TB
    subgraph M2["MS-002 — 현재 실행 경로"]
        W29["WI-029 / S05<br/>2주 shadow 증적 수집<br/>verified / collecting"]
        W30["WI-030 / S01<br/>disabled Telegram prep<br/>verified"]
        M2DONE{"MS-002<br/>acceptance complete"}
        W29 --> W30 --> M2DONE
    end

    subgraph M3["MS-003 — enrichment, Remote MCP V2, cutover"]
        M3OPEN{"MS-003<br/>formal start gate"}
        W35["WI-035<br/>operations / cost / release"]
        W37["WI-037<br/>filing + fundamental facts"]
        W38["WI-038<br/>dividend ledger"]
        W39["WI-039<br/>macro profile"]
        W40["WI-040<br/>catalog + quality read model"]
        W41["WI-041<br/>consensus + forward outlook"]
        W42["WI-042<br/>stateless Remote MCP reads"]
        W43["WI-043<br/>MCP managed commands"]
        W44["WI-044<br/>client compatibility"]
        W45["WI-045<br/>V1/V2 dual-run readiness"]
        W46["WI-046<br/>Remote MCP V2 cutover"]

        M3OPEN --> W35
        M3OPEN --> W37
        M3OPEN --> W39
        M3OPEN --> W40
        W37 --> W38
        W37 --> W41
        W30 --> W42
        W40 --> W42
        W41 --> W42
        W42 --> W43
        W42 --> W44
        W43 --> W44
        W35 --> W45
        W44 --> W45 --> W46
    end

    subgraph M4["MS-004 — V1 retirement and V2 canonicalization"]
        W47["WI-047<br/>V1 public surface retirement"]
        W48["WI-048<br/>V1 main consumer transition"]
        W49["WI-049<br/>bounded resource cleanup"]
        W50["WI-050<br/>steady-state runbooks"]
        W51["WI-051<br/>final architecture audit"]
        W32["WI-032<br/>V2 canonical documentation"]

        W46 --> W47
        W46 --> W48
        W47 --> W49
        W47 --> W50
        W48 --> W50
        W47 --> W51
        W48 --> W51
        W49 --> W51
        W50 --> W51
        W51 --> W32
    end

    M2DONE -. milestone gate .-> M3OPEN

    classDef active fill:#fff1bf,stroke:#9a6b00,color:#4b3500;
    classDef blocked fill:#fde2e2,stroke:#b42318,color:#5b1712;
    classDef proposed fill:#eef1f5,stroke:#667085,color:#344054;
    classDef gate fill:#e8f1ff,stroke:#175cd3,color:#123b72;
    class W29,W30 blocked;
    class W35,W37,W38,W39,W40,W41,W42,W43,W44,W45,W46,W47,W48,W49,W50,W51,W32 proposed;
    class M2DONE,M3OPEN gate;
```

### 지금 무엇을 할 수 있는가

| 구분 | 현재 가능한 범위 |
| --- | --- |
| 계속 자동 진행 | `WI-029-S05`: 2026-09-10까지 DB-only shadow 증적 축적 |
| 준비 완료 | `WI-030-S01`: secret을 읽거나 외부 전송하지 않는 Telegram delivery 경로 검증 완료 |
| 2주 뒤 활성화 | `WI-030-S02`: S05 검토·owner rule-version·destination·test-message 승인 뒤 실행 |
| MS-003 사전 준비 | `WI-035`, `WI-037`, `WI-039`, `WI-040`의 source·비용·권리·계약 read-only 조사 |
| 현재 baseline에서 불가 | MS-003 production 구현·migration·배포. MS-002가 닫히거나 formal start gate가 개정돼야 함 |
| 별도 미래 intake | ETF constituent 수집과 look-through. `WI-026/027`은 초기 V2에서 rejected되어 재사용하지 않음 |

`WI-038`은 `WI-037`, `WI-041`도 `WI-037`을 기다린다. 사용자-facing Remote MCP 경로인 `WI-042`는
Telegram `WI-030`, catalog/quality `WI-040`, forward outlook `WI-041`이 모두 끝나야 시작한다. 이후
managed command(`WI-043`)와 client compatibility(`WI-044`)를 거쳐 dual-run과 production cutover로 간다.

## 불변 규칙

- Work Item ID는 발급 뒤 삭제·재사용·재번호화하지 않는다.
- 번호는 정렬이나 우선순위가 아니다. 실행순서는 `sequence`와 `depends_on`으로 관리한다.
- milestone 간 실행순서도 registry의 `depends_on`으로 관리하며 알 수 없는 dependency와 cycle은 gate에서
  실패한다.
- 기존 outcome 안의 발견 작업은 `WI-NNN-SNN` sub-item으로 append한다.
- 독립 acceptance 또는 rollback이 필요하면 현재 최댓값 다음의 새 WI를 발급한다.
- 순서·의존관계 변경은 해당 milestone 문서의 revision log에 남긴다.
- 완료된 WI는 새 범위를 흡수하기 위해 다시 정의하지 않는다.

## 변경 단위

마일스톤을 변경할 때 registry, 해당 milestone 문서, Work Item, traceability와 Project OS 검사를 같은
change set에서 갱신한다. 아직 마일스톤에 편입하지 않은 장기 설계 항목은 V2 delivery ID로만 유지하고
Work Item 번호를 미리 점유하지 않는다.

## 문서 revision

| Version | Date | Change | Identity / dependency impact |
| --- | --- | --- | --- |
| 2026-08-30.1 | 2026-08-30 | 상위 문서 지도, milestone 및 remaining Work Item Mermaid dependency graph 추가 | WI-053 append; 제품 dependency는 변경하지 않음 |
