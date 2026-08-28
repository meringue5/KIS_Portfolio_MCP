# WI-025 production readiness evidence

## Scope

2026-08-28에 configured MotherDuck 운영 DB를 aggregate-only read로 점검했다. 검사기는 account, instrument,
thread, lot identity나 평가액을 출력하지 않으며 source call, migration, metric publish, backfill과 production
schedule 변경을 수행하지 않는다.

```bash
uv run python scripts/inspect_wi025_lot_thread_risk_readiness.py
```

## Result

| Gate | Aggregate evidence | Result |
| --- | ---: | --- |
| required objects | 5 expected, 4 present, 1 missing | blocked |
| reconstructed episode | 0 rows, 0 reconstructed open | blocked |
| reconstructed lot | 0 rows, 0 passing open | blocked |
| thread link | 0 open lots | not yet applicable |
| owner risk plan | 0 current rows | not yet applicable |
| adjusted operational-strict price | 0 rows, 0 instruments | blocked |
| canonical portfolio state | 920 rows, 31 pass rows, 28 dates, 1 fully passing slot | available but exact evaluated-slot gate remains required |
| reconstruction exception | 57 open | blocked |

`publish_ready=false`가 정답이다. WI-025 구현은 nullable fail-closed metric 계약과 local fixture evidence를
완성하지만, 위 운영 입력을 만들어낸 것으로 간주하거나 숫자 risk metric을 소급 발행하지 않는다. 특히 57개
reconstruction exception을 lot/thread 사실로 꾸미지 않고, owner stop이 없는 thread에는 ATR suggestion으로
공식 planned loss를 대체하지 않는다.

## Activation boundary

Production numeric activation은 별도 managed execution에서 다음이 모두 입증된 뒤에만 가능하다.

1. 필요한 migration/object가 tested master와 일치한다.
2. open episode/lot 수량이 같은 slot의 canonical position 수량과 정확히 reconcile된다.
3. 각 open lot은 정확히 한 current thread에 연결되고 owner-authoritative risk plan이 존재한다.
4. adjusted operational-strict price와 필요한 point-in-time FX가 pass한다.
5. pre/post private backup과 fresh restore, identical replay no-op가 통과한다.

이번 Work Item은 이 activation을 실행하지 않는다.
