# 2026-11-04-01: NMI 작업 FF9A 는 슬라임 레이스 화면

[창 글자 형식 문서](../docs/dq4-window-text-format.md#nmi-작업마다-걸기2026-11-03)의 「남은 것」 가운데 「`FF9A` 작업(`03:A211` 이 고름)이 어느 장면인지」 를 풀었습니다. `FF9A` 는 슬라임 레이스 화면의 NMI 작업이었습니다. 메뉴 빌드 롬(`menu.sfc`)에서 그 장면을 띄워, `FF9A` NMI 마다 `WqNmiEntry` 가 돌고 창 글자 대기열이 다음 NMI 에 나가는 것을 확인했습니다. 실행 검사 `dq4-ff9a-nmi` 로 남겼습니다.

## 1. 03:A211 을 누가 부르나

`00:8800` 은 `$1944` 에 `FF9A` 를 넣는 짧은 루틴입니다. 롬 바이트를 훑으면 원본 DQ5 롬에서 `JSL $008800`(`22 00 88 00`, 뱅크 `$80` 거울 오퍼랜드 포함)은 `03:A211` 하나이고, `JML $008800` 은 롬 전체에, `JSR $8800`·`JMP $8800` 은 뱅크 `00` 에 없습니다(아래 「근거」 의 `--facts`). 이 훑기는 곧바로 뛰는 명령의 바이트 모양만 봅니다. 간접 점프(`JMP (abs)`·`JMP (abs,X)`·`JSR (abs,X)`·`JML [abs]`)나 표에 담긴 주소로 가는 길은 잡지 못합니다. 그 앞뒤를 디스어셈블했습니다.

```text
03:A1EE  PHP / PHB / PHK / PLB / JSR $A3A9
03:A1F5  REP #$20 … STA $1200 … STA $1202     레이스 값
03:A209  JSL $00954E
03:A211  JSL $008800                          NMI 작업을 FF9A 로
03:A215  PHD / LDA #$1200 / TCD / JSL $11C031 / PLD   뱅크 11 의 레이스 본체
03:A221  JSL $00879C … BRK 8E / BEQ $A215     되풀이
…        JSL $009556 … PLB / PLP / RTL
```

`03:A1EE` 를 부르는 것도 같은 범위에서 `JSL $03A1EE` 가 `06:F21E` 하나이고, `JML $03A1EE` 는 롬 전체에, `JSR $A1EE`·`JMP $A1EE` 는 뱅크 `03` 에 없습니다. `06:F21E` 는 대화 뱅크 `06` 의 시설 처리기 안입니다. 바로 앞 `06:F210` 은 DQ5 handoff 가 적은 슬라임 레이스 코인 검사(`BNE`)이고, 시설 번호 `0D` 가 슬라임 레이스입니다([DQ5 가게 종류](../../dq5/docs/dq5-data-format.md#가게-종류-06dbd2)). 원본 DQ5 롬의 인물 기록을 `dq5npcrecord.py rom/dq5.sfc dump` 로 풀면 대화 번호 `00D` 는 `19/02`(오라클베리 카지노)의 낮·밤 둘뿐입니다.

형식 문서가 짚었던 `03:A175` 의 `JSL $03A1C9` 는 다른 길입니다. `03:A1C9` 는 `03:AD0C` 로 표 `0A`~`0D` 를 차례로 거는 루틴이고, `$1944` 를 건드리지 않습니다. 이것이 어느 장면인지는 아직 모릅니다.

## 2. 원본 DQ5 에서 장면 띄우기

원본 롬으로 만든 배 선실 상태(`dq4freshstate`)에서 난수(`7E:075B`~`075D`)·시각(낮)을 고정하고 걸음 조우를 없앤 채(`dq4ch1walkcheck.RNG`·`DAY_SET`·`NO_ENCOUNTERS`) 인물 슬롯 1~1F 의 대화 번호(`7E:36E0`·`7E:3700`+슬롯)를 `00D`, 코인(`7E:203C`~)을 100 으로 두고, 위의 파파스에게 말을 건 뒤 A 를 60프레임마다 눌렀습니다. NMI 공통 입구 `00:887C`(`JMP ($1944)`)에서 작업 번호를 셌습니다(`sfc/dq4/tools/lua/dq4ff9acheck.lua`).

```text
8926 846     필드
FF9A 1923    레이스
```

1800프레임 화면은 슬라임 다섯 마리와 배당 표(「1-2 91×14」 등)였습니다.

## 3. menu.sfc 에서 대기열 확인

같은 입력과 같은 고정값을 `menu.sfc` 와 그 롬으로 만든 선실 상태로 돌렸습니다. `WqNmiEntry` 자리는 필드 받침 `00:FF9E` 의 `JSL` 대상(`60:D66C`)에서 읽고, `00:FF9A` → `WqNmiFF9A`(`60:D690`)의 첫 `JSL` 이 그곳인지 봅니다(정적 확인). `FF9A` 작업 동안 대기열 `!wq_*` 가 비어 있을 때 항목 하나(VRAM 워드 `0F80` = BG3 칸 `1F0`, 방식 0, 한 칸, 16바이트 그림)를 넣었습니다. 그림은 넣을 때마다 바꾸고, 넣기 직전에 VRAM 이 그 그림과 다른지 먼저 봅니다. 넣은 뒤 두 번째 NMI 입구에서 항목 수와 VRAM 을 봅니다.

```text
FF9E 846   WqNmiEntry 846
FF9A 1923  WqNmiEntry 1923
878 nmi 847 task FF9A count 0 vram same before differs
909 nmi 878 task FF9A count 0 vram same before differs
940 nmi 909 task FF9A count 0 vram same before differs
```

레이스 화면은 원본과 같이 떴습니다. 검사는 같은 상태·입력으로 두 번 돌려 기록(`nmi.txt`·`inject.txt`)이 바이트째 같아야 통과하고(`REPEAT`), 두 번 모두 같았습니다.

`--break-entry` 는 `WqNmiEntry` 첫 바이트를 `RTL` 로 바꿔(메모리에서만) 돌립니다. 받침 바이트는 그대로라 정적 확인은 지나고, NMI 마다 `WqNmiEntry` 에 들어가기는 합니다(`FF9A` 1923번 모두). 그러나 대기열을 보내지 않아 게임이 넣어 둔 항목이 끝까지 남았고, 검사는 대기열이 비어 있을 때만 항목을 넣으므로 한 번도 넣지 못했습니다. 실제 출력(`results.json`)은 `"problems": ["넣은 항목 확인 0번(기대 3)"]`, `"inject": []`, `FF9A` `count 1923`·`entry 1923` 이었습니다. 이전에 시험한 「`WqNmiFF9A` 의 `JSL` 을 다른 곳으로 돌린 롬」 은 이 정적 확인(첫 `JSL` 이 `WqNmiEntry` 인지)에 먼저 걸리는 변이라, 실행 중 동작의 근거가 아닙니다.

## 4. DQ4 에서는

옮긴 FC 가게는 시설 번호 `01`~`06` 만 씁니다(`dq4shopport.SERVICE`). 지금 빌드한 1장 롬(`dq4-ch1-full.sfc`, SHA-1 `cbd7add2`)의 인물 기록을 같은 도구로 풀어도 대화 번호 `00D` 는 원래 DQ5 맵 `19/02` 의 둘뿐입니다. `19/02` 로 가는 길이 1장 롬에 없는지는 재지 않았습니다(「남은 것」). 1장 롬에는 선실이 없어 이 검사는 `menu.sfc` 로 돕니다.

**근거.** 이 브랜치(`feat/dq4-ff9a-nmi`)의 워크트리에서 `work/ch1` 을 지우고 다시 빌드한 롬(`uv run --locked python sfc/dq4/tools/dq4build.py --out work/ch1`, `menu.sfc` SHA-1 `f0fbaa1b`, `dq4-ch1-full.sfc` SHA-1 `cbd7add2`)을 `--facts` 로 읽었습니다. 원래 체크아웃의 `work/ch1` 처럼 이 패치보다 먼저 빌드한 롬에는 받침이 없어 결과가 다릅니다.

```text
uv run --locked python sfc/dq4/tools/dq4ff9acheck.py --rom <롬> --facts
                    JSL $008800  JML  JSR·JMP(뱅크 00)  JSL $03A1EE  JML  JSR·JMP(뱅크 03)
rom/dq5.sfc         03:A211      없음  없음          06:F21E      없음  없음
menu.sfc            03:A211      없음  없음          06:F21E      없음  없음
dq4-ch1-full.sfc    03:A211      없음  없음          06:F21E      없음  없음

바이트 비교         menu.sfc = dq4-ch1-full.sfc   원본 = menu.sfc
00:FF9A (4)         같음                          다름(받침)
00:FF9E (7)         같음                          다름(받침)
WqNmiFF9A (12)      같음                          -
WqNmiEntry (36)     같음                          -
03:A1EE (0x69)      같음                          같음
06:F210 (0x12)      같음                          같음
```

## 5. 재발 방지

- 실행 검사 `dq4-ff9a-nmi`(`sfc/dq4/guards.toml`): `dq4ff9acheck.py --rom work/ch1/menu.sfc`. `FF9A` NMI 가 있고, 그 NMI 마다 `WqNmiEntry` 가 돌고, 넣은 항목 셋이 모두 다음 NMI 에 나가고(넣기 전 VRAM 다름), 두 실행 기록이 같아야 통과합니다. 가드의 `paths` 는 명령의 진입 스크립트·빌드 단계와 그 직접 import 를 모두 담고, `test_dq4readset` 의 `test_walk_guards_watch_their_imports` 가 지킵니다.
- 단위 테스트 `test_dq4ff9acheck`: 받침 읽기(받침 없는 롬은 멈춤, `WqNmiFF9A` 가 다른 곳을 부르면 드러남), 판정(넣기 전부터 같으면 실패 포함), 변이 패치, 두 실행 견주기.

## 남은 것

- `03:A175` → `03:A1C9`(표 `0A`~`0D`)가 어느 장면인지.
- 1장 롬으로 `19/02` 에 순간이동해 레이스를 띄워 보지는 않았습니다.
- 1장 롬에서 `19/02` 로 가는 출구·입구·순간이동이 없는지(그래서 DQ4 를 하는 동안 이 장면이 나오지 않는지)는 확인하지 않았습니다.
