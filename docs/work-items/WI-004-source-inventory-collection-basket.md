---
id: WI-004
title: Select the governed source inventory and collection basket
status: closed
type: architecture
owner: owner
decision_refs: ADR-003, ADR-018, ADR-020, ADR-021, ADR-023
requirement_refs: DEC-003, DEC-005, DEC-010..DEC-025, DEC-030, DEC-035..DEC-044, DGOV-010
architecture_impact: canonical and secondary data-source selection
data_impact: approved source, dataset and collection contracts only; no production writes
security_impact: source authentication, license and sensitivity classification
cost_impact: free-first selection under monthly KRW 50000 ceiling; no purchase
---

# WI-004 — Select the governed source inventory and collection basket

## Problem and evidence

승인된 제품 요구는 보유종목·거래·가격·ETF 구성·공시·실적·컨센서스·배당·매크로와 신호 분석에 필요한
데이터 범위를 설명한다. 그러나 실제로 접근 가능한 원천, canonical/secondary 역할, 이용권한, 지연·호출
제약과 어떤 데이터를 먼저 수집할지에 대한 DGH contract는 아직 0건이다.

사용자는 2026-08-28에 기존 요구사항을 근거로 assistant가 원천과 수집 대상을 권고 선택하고, material
trade-off만 묶어서 사용자에게 승인 요청하는 방식으로 Phase 1을 진행하도록 요청했다.

## Classification and contract

- 초기 분류: `architecture`
- 비교한 요구사항/ADR/catalog: DEC-003/005/010~025/030/035~041, ADR-018/020/021/023,
  DGH source·collection·dataset contract
- 계약 미달인지 계약 변경인지: 승인 요구를 실제 source와 collection contract로 구체화하는 architecture
  selection
- 승인 필요 여부: owner가 core·recommended 계약과 수동 PDF 반입 계약을 승인했다. 유료 계약,
  production 수집·backfill·schedule은 별도 승인 필요

## Scope

- 포함: 현재 KIS capability 확인, 공식 원천 조사, source canonical/secondary/fallback 판정, v1 수집
  장바구니 required/recommended/later/excluded, 최소 dataset contract, 비용·license·freshness·gap 기록
- 제외: provider 가입·결제, credential 발급, production 호출, live DDL/backfill, Scheduler,
  MotherDuck 데이터 변경

## Acceptance criteria

- [x] 승인 요구사항마다 필요한 데이터가 source와 dataset에 매핑된다.
- [x] 각 source의 canonical 역할, 접근·인증, license, 지역, 비용, 호출·가용성 제약이 근거와 함께 기록된다.
- [x] required/recommended/later/excluded 장바구니와 선정·제외 이유가 설명된다.
- [x] source, dataset과 collection TOML이 DGH checker를 통과한다.
- [x] 무료·공식·현재 보유종목 중심의 v1이 월 50,000원 비용 상한 안에 있음을 검토한다.
- [x] 컨센서스·리서치처럼 권리·비용이 미확정인 항목은 공식 데이터로 가장하지 않는다.
- [x] 사용자에게 일일이 선택시키지 않고 material approval 질문만 한 묶음으로 제시한다.
- [x] production data, infrastructure, secret와 billing에는 변경이 없다.
- [x] owner-provided PDF를 자동 scraping과 분리한 restricted 수동 반입 계약이 있다.
- [x] consensus `later`의 표본검증·권리·비용 진입조건이 명시됐다.

## Change impact

- Architecture: canonical/secondary source와 collection 우선순위를 승인했다. 실제 producer/consumer가
  배포되기 전까지 `approved`를 유지하고 `active`로 승격하지 않는다.
- Data/schema/backup: approved manifest와 review 문서만 추가한다. DDL/backup 대상 변경 없음.
- Security/privacy: account-private KIS와 public source를 분리하고 credential은 기록하지 않는다.
- MCP/API compatibility: 없음. 미래 `get-data-catalog` 입력의 선행 계약이다.
- Deployment/rollback: repository manifest와 문서 revert만 필요하다.
- Cost/SLO: 무료 공식 source를 우선하며 유료/불명확 source는 later 또는 excluded로 격리한다.

## Plan

1. 현재 코드와 KIS capability를 승인 요구사항에 매핑한다.
2. 공식 문서에서 KIS/OpenDART/SEC/ETF/ECOS/FRED/Cboe와 consensus 후보의 접근·권리·제약을 조사한다.
3. canonical/secondary/fallback 판정과 dataset grain·freshness·quality gap을 작성한다.
4. proposed source/dataset/collection manifest와 human review package를 만든다.
5. DGH/Project OS full gate 후 material approval bundle을 사용자에게 제시한다.

## Evidence

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: 통과,
  `registered_contracts=40` — source 14, dataset 19, collection 7
- `bash scripts/check.sh quick`: Project OS, DGH, architecture, warehouse와 MCP surface 통과
- `bash scripts/check.sh full`: 193 passed, 1 기존 Authlib deprecation warning; 모든 공통 gate 통과
- review package: `docs/governance/source-inventory-and-collection-basket.md`
- owner acceptance: 2026-08-28 core·recommended 권고, 수동 PDF 반입, restricted 분류와 later gate 승인
- 공식 evidence: KIS/OpenDART/SEC/KRX/NYSE/Nasdaq/ETF issuer/ECOS/FRED·ALFRED/Cboe 링크를 review package에 기록
- 운영 증거: production API 호출, DB/DDL, service, Job, Scheduler, secret, provider signup과 billing 변경 없음

## Closeout

- 결과: 승인 요구를 14개 source, 19개 logical dataset과 required/recommended/later/excluded 7개 collection
  contract로 구체화했다. core·recommended 의존 계약은 `approved`, consensus와 unlicensed 경계는
  production 금지를 유지하도록 `proposed`다.
- 남은 위험: KIS consensus coverage, issuer별 ETF terms/history, FRED series별 권리, DART/SEC taxonomy와
  실제 row/file size는 activation 전에 bounded recorded fixture/rehearsal이 필요하다.
- 후속 Work Item: 승인된 basket의 bounded source sampling, V2 Wave 1~4 local 구현과 contract hardening.
  production adapter 호출·live DDL·backfill은 별도 승인 gate를 유지한다.
