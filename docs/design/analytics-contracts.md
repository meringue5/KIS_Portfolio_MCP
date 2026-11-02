# 분석값의 의미·계산·publish 규칙

> 기존 승인 계산을 용도별로 통합합니다. 원천 coverage나 미지원 값을 계산 가능으로 승격하지 않습니다.
> [운영 모델](../operating-model.md) · [metric 계약](../../governance/catalog/metrics.toml) · [기능/검증 지도](../traceability.md)

## 분석값을 구분하는 이유

평가액 변화는 price·수량·FX·현금 관측의 변화를 포함합니다. 투자 성과는 외부 자본 흐름과 구간의
비교 가능성을 따로 증명해야 합니다. lot path와 episode drawdown, owner-plan risk는 각각 lifecycle과
판단 기준이 다르며 서로 대체하지 않습니다. 아래 식은 계약이지 현재 모든 계좌/기간에 제공된다는 선언이 아닙니다.

## 원화 평가액 변화

비교 grain은 `(previous canonical daily state, current canonical daily state, instrument)`입니다. 동일 instrument는
계좌 간 합산할 수 있고 account breakdown에는 설정된 alias만 반환합니다. 외화 position 변화는 FX 효과와 결합된 값입니다.

```text
valuation_change_krw = current_value_krw - previous_value_krw
total_asset_impact_pct = valuation_change_krw / previous_total_asset_krw * 100
share_of_total_change_pct = valuation_change_krw / total_asset_change_krw * 100
explained_change_sum_krw = holding_change_sum_krw + cash_change_krw
unexplained_residual_krw = total_asset_change_krw - explained_change_sum_krw
```

분모 0이면 해당 비율은 null과 이유입니다. 합계 tolerance는 `max(KRW 1, abs(compared total assets) × 1e-6)`의 기존 계약을 따릅니다.
신규/전량매도 판정은 두 상태 모두 complete/pass, 동일 required account scope, observed=required coverage,
holdings+cash 대사가 함께 통과할 때만 제공합니다. 실패 시 degraded/blockers와 null flags를 반환합니다.
진단용 변화값이 보이더라도 공식 metric은 nullable quality outcome일 수 있습니다.

## 현금흐름 조정 성과와 wealth chain

BMV/EMV는 같은 범위의 시작/끝 평가액, CF는 부호 있는 외부 owner 자본 흐름입니다. 입금은 +, 출금은 −이며
`w_i=(end-t_i)/(end-start)`입니다.

```text
denominator = BMV + sum(w_i * CF_i)
return = (EMV - BMV - sum(CF_i)) / denominator
component contribution_j = (EMV_j - BMV_j - sum(CF_ij)) / denominator
residual = return - sum(component contribution_j)
wealth_t = wealth_(t-1) * (1 + return_t)
drawdown_t = wealth_t / high_water_t - 1
```

ratio는 `DECIMAL(38,10)` half-even, residual 허용오차는 `1e-10`입니다. 외부 owner flow는 consolidated
`cash|currency` component에만 배정합니다. 내부이체·trade settlement·FX leg는 외부 자본이 아니며 fee/tax/dividend/interest는 성과입니다.

**동시에 필요한 gate:** 동일 slot의 pass 상태·완전하고 같은 계좌 scope, 모든 중간 날짜의 market calendar와 다음 open KRX
session, 정확한 time range/account hash의 cash-event coverage quality 증거, cutoff 당시 pass/known 분류,
유효한 부호·통화·비영 분모, contribution 대사입니다. unknown 분류·unreconciled internal legs·미지원 비KRW owner flow는 unavailable입니다.
빈 cash table은 zero-flow 증거가 아니며 current-only FX나 미래 classification을 과거 계산에 사용하지 않습니다.
첫 state wealth base는 1입니다. non-pass/missing return은 chain을 끊고, 나중 pass가 나와도 자동으로 1부터 다시 시작하지 않습니다.
총자산 원화 최고점은 입출금의 영향을 받으므로 성과 high-water가 아닙니다. 현재 현금 관측/참고 이력은 이 gate를 충족시키지 않습니다.

## lot·episode·owner risk

```text
lot_mfe = max(adjusted_high / adjusted_entry_cost - 1)
lot_mae = min(adjusted_low / adjusted_entry_cost - 1)
episode_high = max(adjusted_high)
episode_drawdown = last_adjusted_close / episode_high - 1
thread_planned_loss_krw = open_quantity * (reference_price - stop_price) * point_in_time_fx
thread_risk_ratio = thread_planned_loss_krw / canonical_total_assets_krw
```

lot path는 자기 effective unit cost부터 자기 episode/close cutoff까지만 봅니다. episode가 0으로 닫히면
그 뒤 가격을 쓰지 않고 새 episode의 high-water는 새로 계산합니다. 추가매수·부분매도 수량 경로를 이 식으로
cash-flow-adjusted thread return이라고 부르지 않습니다.

공식 risk plan은 owner-authored append-only revision입니다. long position의 `stop_price < reference_price`, 같은 통화,
`0 < risk budget ratio <= 0.02`를 지킵니다. expected prior revision·effective time·knowledge time을 구분합니다.
일지 prose·LLM 답·ATR 제안은 stop/reference를 만들지 못하며 제안은 `advice_metadata`로만 남습니다.

숫자 publish는 cutoff에 유효/알려진 lot·episode, 재구성/lot quality pass, lot 잔량=episode 수량,
같은 slot의 canonical position/계좌 coverage, 각 open lot의 단일 current thread, lifecycle 안의 adjusted
`operational_strict` pass price, owner plan·PIT FX·완전하고 양수인 총자산을 함께 요구합니다.
instrument 합계는 모든 open thread가 numeric이고 수량도 맞을 때만 numeric입니다. 누락은 이유 있는 null입니다.

## 검토 질문과 보정의 권한

risk plan 부재, 일지 부재, 미지정 FIFO 배분, 미해결 allocation exception은 각각 review item입니다.
system은 발견만 하고 owner만 answer/dismiss합니다. 무응답을 기본 stop·일지·매도 의도로 채우지 않습니다.
resolution은 실제 authoritative revision을 참조하며 Control에 intent를 복제하지 않습니다.

metric은 definition/version·PIT·lineage를 고정합니다. 동일 논리키의 exact replay는 no-op, 값/lineage 충돌은 실패입니다.
기존 통계/legacy view를 계약 없이 공식 성과로 채택하지 않습니다. source·pipeline 승인은 별개입니다.

## 수정할 곳과 근거

[성과](../../src/kis_portfolio/modules/monitoring/portfolio_performance.py),
[평가 변화](../../src/kis_portfolio/modules/monitoring/valuation_change.py),
[lot/thread risk](../../src/kis_portfolio/modules/monitoring/lot_thread_risk.py).
검증은 [성과](../../tests/test_v2_portfolio_performance.py), [평가 변화](../../tests/test_v2_valuation_change.py),
[Remote 계약](../../tests/test_remote_v2_warehouse.py), [owner 명령](../../tests/test_remote_v2_revisions.py)에서 시작합니다.
원래 단계별 승인·적용 결과는 [구축 압축본](../history/README.md), 계산 계약의 장기 근거는
[요구사항](../requirements/kis-portfolio-data-platform-requirements.md)과 [SPEC](../../SPEC.md)에 있습니다.
