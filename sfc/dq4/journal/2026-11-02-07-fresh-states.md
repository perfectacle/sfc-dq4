# 2026-11-02-07: 장면 검사의 출발 상태를 검사 롬으로 만들기

다른 빌드로 만든 세이브스테이트를 지금 롬에 불러오면 폭주한다. 그런데도 dq4 장면 검사 열셋은 옛 `work/state/ship.mss`(DQ5 선실)나 손으로 고른 1장 상태를 `--state` 로 받고 있었다. 출발 상태를 검사 롬에서 직접 만드는 `dq4freshstate.py` 를 두고, 상태 옆에 만든 롬의 SHA-1 을 적어 다른 빌드의 상태를 주면 불러오기 전에 멈추게 했다. 결과는 [저장 기록 검사](../docs/dq4-savefixture-format.md#검사-롬으로-만든-출발-상태) 에 반영했다.

## 1. 무엇이 낡은 상태를 읽고 있었나

`sfc/dq4/tools` 에서 `work/state/` 를 가리키거나 `--state` 를 받는 검사를 모았다. 옛 선실 상태를 `--state` 기본값으로 둔 것이 열(`dq4chestcheck`·`dq4dungeonencountercheck`·`dq4environmentromcheck`·`dq4fieldcheck`·`dq4fieldencountercheck`·`dq4fieldtravelcheck`·`dq4groupcheck`·`dq4npccheck`·`dq4signcheck`·`dq4wellresetcheck`), 꼭 주어야 하는 것이 셋(`dq4bg3slotcheck`·`dq4namegamecheck`·`dq4battlemsgcheck`)이었다. 창 글자 검사(`dq4windowcheck`)는 이미 서장 끝 캐시에서 순간이동하는 방식으로 옮겨 있었다.

## 2. 롬마다 만들 수 있는 출발 상태

| 롬 | 출발 상태 |
| --- | --- |
| 1장 롬(머리 `DRAGONQUEST4`) | 서장 끝. `dq4ch1walkcheck.prologue` 의 롬 SHA-1 별 캐시 |
| 그 밖(`groups.sfc`, `menu.sfc`, 원본) | 배 선실 `17/00`. `lua/dq4shipstate.lua` 로 6973프레임, 약 20초 |

1장 롬은 새 게임이 DQ4 서장으로 가서 DQ5 선실을 만들 수 없다. 장면 검사 대부분은 `dq5warp.lua` 로 순간이동해 시작하므로 서장 끝에서 떠나도 같은 장면에 선다.

## 3. 옮기기 전과 뒤

옮기기 전은 `origin/main` 그대로의 코드와 옛 상태(`ship.mss`, 1장은 `dq4-ch1-field.mss`), 뒤는 검사 롬으로 만든 상태로 같은 롬을 돌렸다.

| 검사 | 롬 | 전 | 뒤 |
| --- | --- | --- | --- |
| `dq4signcheck` | 1장 | 통과 38 | 통과 38 |
| `dq4namegamecheck` | `menu.sfc` | 통과 7 | 통과 7 |
| `dq4battlemsgcheck` | 1장 | 실패: 둘째 차례에서 TypeError | 통과(418번, 멈춤 0) |
| `dq4wellresetcheck` | 1장(+`groups.sfc`) | 통과 | 통과 |
| `dq4dungeonencountercheck` | 1장 | 실패 2장면 | 실패 같은 2장면 |
| `dq4bg3slotcheck` | `overture.sfc`·`menu.sfc` 8맵 | 화면 다른 맵 6, `17/00` 못 감 | 같음 |
| `dq4chestcheck` | `groups.sfc` | 통과 69 | 통과 69 |
| `dq4environmentromcheck` | `groups.sfc` | 실패: 픽셀 차이 2맵 | 같음 |
| `dq4fieldcheck` | `groups.sfc` | 통과 | 통과 |
| `dq4fieldencountercheck` | `groups.sfc` | 통과 | 통과 |
| `dq4fieldtravelcheck` | `groups.sfc` | 통과 | 통과 |
| `dq4npccheck` | `groups.sfc` | 실패 8대화 | 같은 8대화 |
| `dq4groupcheck` | `groups.sfc` | 실패 1계단 | 같은 1계단 |

옮기기 전후로 결과가 바뀐 것은 전투 메시지 검사뿐이다. 옛 1장 상태에서는 한 묶음이 멈춰 둘째 차례가 돌았고, 차례를 도는 변수 `batch` 가 묶음 크기를 덮어 `range(0, len(todo), batch)` 가 죽었다. 변수 이름을 나눠 고치고 `test_dq4battlemsgcheck.py` 로 막았다. 새 상태에서는 첫 차례에 418번이 모두 찍혔다.

전후 모두 실패한 넷은 출발 상태와 상관없는 지금 빌드의 결과다. 고치지 않고 남겼다.

- `dq4dungeonencountercheck`: `39-03-field`·`3A-00-field` 에서 던전 걸음마다 읽은 재생 곡 `$1D8B` 에 `FF` 가 섞임(`3A/00` 은 `09` 와 `FF` 가 번갈아). 옛 상태에서는 `39/03` 의 곡이 아예 `FF` 만이었다. 새 상태에서는 곡 `0A` 가 울린 뒤 영역을 오갈 때 `FF` 가 끼었다.
- `dq4environmentromcheck`: 오프라인 그림과 픽셀 차이 `konenbery-06` 88, `imuru` 119.
- `dq4npccheck`: `talk-3600-18`·`19`, `3601-28`·`29`, `3603-1`·`2`, `3700-23`·`25` 가 기대 대사 대신 129 「그 방향에는 아무도 없다」.
- `dq4groupcheck`: `stair-4007-0` 이 `40/0E` (36,19) 대신 `40/07` (44,21) 에 섬.

## 4. 1장 롬에 없는 장면

우물 검사의 `load` 는 선실에서 위 사람의 대화 번호를 교회(05)로 바꿔 말을 걸어 기록하고, 리셋 뒤 이어 한다. 1장 롬 서장 끝에서 같은 입력을 주면 기록 칸이 비어 있었다. `36/00` 교회로 순간이동해 신부 앞(10,44)에서 말을 걸어도 명령 창 제목 「명령을 내려줘」 만 남고 기록이 되지 않았다. 그래서 이 장면은 `--load-rom` 으로 준 `groups.sfc`(같은 이어 하기 훅 `25:8278` 이 든 롬)의 선실에서 본다. 두 롬 모두 훅이 걸렸는지 확인하고 시작한다. 전멸 장면은 1장 롬에서 그대로 돌고, 서장 끝의 다시 시작 자리가 선실의 `02` 와 달라 `wipe-02` 는 `$195E` 를 `02` 로 둔다.

## 5. 재발 방지

`test_dq4freshstate.py` 가 롬 없이 본다.

- SHA-1 이 없거나 다른 상태를 `require_same_build`·`resolve` 가 거절함
- 옮긴 열셋이 `dq4freshstate` 를 거침
- `--state` 를 받는 dq4 도구가 `dq4freshstate` 로 같은 빌드인지 봄, 도구 안에 `work/state/` 경로가 없음(아직 옮기지 않은 `dq4doorcheck`·`dq4doorstandcheck`·`dq4sparfx` 만 목록으로 뺌)

통과하는 장면 검사는 `guards.toml` 에 `dq4-groups-scenes`(상자·필드·필드 조우·ルーラ), `dq4-battle-msgs`, `dq4-well-reset`, `dq4-name-game` 으로 등록했다. 실패가 남은 넷은 등록하지 않았다.

## 남은 것

- 위 넷의 실패 원인(게임 쪽인지 검사의 기대가 낡았는지).
- 1장 롬 교회에 순간이동한 뒤 대화가 되지 않는 까닭.
- `dq4doorcheck`·`dq4doorstandcheck`·`dq4sparfx` 옮기기.
