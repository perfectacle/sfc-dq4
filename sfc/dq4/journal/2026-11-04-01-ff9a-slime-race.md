# 2026-11-04-01: NMI 작업 FF9A 는 슬라임 레이스 화면

[창 글자 형식 문서](../docs/dq4-window-text-format.md#nmi-작업마다-걸기2026-11-03)의 「남은 것」 가운데 「`FF9A` 작업(`03:A211` 이 고름)이 어느 장면인지」 를 풀었습니다. `FF9A` 는 슬라임 레이스 화면의 NMI 작업이었습니다. 메뉴 빌드 롬(`menu.sfc`)에서 그 장면을 띄워, `FF9A` NMI 마다 `WqNmiEntry` 가 돌고 창 글자 대기열이 다음 NMI 에 나가는 것을 확인했습니다. 실행 검사 `dq4-ff9a-nmi` 로 남겼습니다.

## 1. 03:A211 을 누가 부르나

`00:8800` 은 `$1944` 에 `FF9A` 를 넣는 짧은 루틴입니다. 원본 DQ5 롬에서 `JSL $008800` 은 `03:A211` 하나입니다. 그 앞뒤를 디스어셈블했습니다.

```text
03:A1EE  PHP / PHB / PHK / PLB / JSR $A3A9
03:A1F5  REP #$20 … STA $1200 … STA $1202     레이스 값
03:A209  JSL $00954E
03:A211  JSL $008800                          NMI 작업을 FF9A 로
03:A215  PHD / LDA #$1200 / TCD / JSL $11C031 / PLD   뱅크 11 의 레이스 본체
03:A221  JSL $00879C … BRK 8E / BEQ $A215     되풀이
…        JSL $009556 … PLB / PLP / RTL
```

`03:A1EE` 를 부르는 `JSL $03A1EE` 는 롬에 `06:F21E` 하나입니다. 대화 뱅크 `06` 의 시설 처리기 안입니다. 바로 앞 `06:F210` 은 DQ5 handoff 가 적은 슬라임 레이스 코인 검사(`BNE`)이고, 시설 번호 `0D` 가 슬라임 레이스입니다([DQ5 가게 종류](../../dq5/docs/dq5-data-format.md#가게-종류-06dbd2)). 원래 DQ5 인물 가운데 대화 번호 `00D` 는 `19/02`(오라클베리 카지노)의 낮·밤 둘뿐이었습니다(`dq5npcrecord.py dump`).

형식 문서가 짚었던 `03:A175` 의 `JSL $03A1C9` 는 다른 길입니다. `03:A1C9` 는 `03:AD0C` 로 표 `0A`~`0D` 를 차례로 거는 루틴이고, `$1944` 를 건드리지 않습니다. 이것이 어느 장면인지는 아직 모릅니다.

## 2. 원본 DQ5 에서 장면 띄우기

배 선실 세이브스테이트에서 인물 슬롯 1~1F 의 대화 번호(`7E:36E0`·`7E:3700`+슬롯)를 `00D`, 코인(`7E:203C`~)을 100 으로 두고, 위의 파파스에게 말을 건 뒤 A 를 60프레임마다 눌렀습니다. NMI 공통 입구 `00:887C`(`JMP ($1944)`)에서 작업 번호를 셌습니다(`sfc/dq4/tools/lua/dq4ff9acheck.lua`).

```text
8926 846     필드
FF9A 1923    레이스
```

1800프레임 화면은 슬라임 다섯 마리와 배당 표(「1-2 91×14」 등)였습니다.

## 3. menu.sfc 에서 대기열 확인

같은 입력을 `menu.sfc` 와 그 롬으로 만든 선실 상태(`dq4freshstate`)로 돌렸습니다. `WqNmiEntry` 자리는 필드 받침 `00:FF9E` 의 `JSL` 대상(`60:D66C`)에서 읽고, `00:FF9A` → `WqNmiFF9A`(`60:D690`)의 첫 `JSL` 이 그곳인지 봅니다. `FF9A` 작업 동안 대기열 `!wq_*` 가 비어 있을 때 항목 하나(VRAM 워드 `0F80` = BG3 칸 `1F0`, 방식 0, 한 칸, 16바이트 그림)를 넣었습니다. 넣은 뒤 두 번째 NMI 입구에서 항목 수와 VRAM 을 봅니다.

```text
FF9E 846   WqNmiEntry 846
FF9A 1923  WqNmiEntry 1923
878 nmi 847 task FF9A count 0 vram same
909 nmi 878 task FF9A count 0 vram same
940 nmi 909 task FF9A count 0 vram same
```

레이스 화면은 원본과 같이 떴습니다. 두 번 돌려 횟수가 같았습니다. `WqNmiFF9A` 의 첫 `JSL` 을 `WqNmiEntry` 끝의 `RTL`(`60:D68F`)로 돌린 롬에서는 `FF9A` NMI 마다의 `WqNmiEntry` 가 0번, 넣은 항목이 남아(항목 수 1, VRAM 다름) 검사가 실패했습니다.

## 4. DQ4 에서는

옮긴 FC 가게는 시설 번호 `01`~`06` 만 씁니다(`dq4shopport.SERVICE`). 1장 롬(`dq4-ch1-full.sfc`)의 인물 가운데 대화 번호 `00D` 도 원래 DQ5 맵 `19/02` 의 둘뿐이고, `19/02` 는 1장 이야기에서 가는 맵이 아닙니다. 그래서 DQ4 를 하는 동안에는 이 장면이 나오지 않습니다. 1장 롬의 `00:FF9A`·`WqNmiEntry`·`WqNmiFF9A`·`03:A1EE`·`06:F21E` 바이트는 `menu.sfc` 와 같습니다. 1장 롬에는 선실이 없어 이 검사는 `menu.sfc` 로 돕니다.

## 5. 재발 방지

- 실행 검사 `dq4-ff9a-nmi`(`sfc/dq4/guards.toml`): `dq4ff9acheck.py --rom work/ch1/menu.sfc`. `FF9A` NMI 가 있고, 그 NMI 마다 `WqNmiEntry` 가 돌고, 넣은 항목 셋이 모두 다음 NMI 에 나가야 통과합니다.
- 단위 테스트 `test_dq4ff9acheck`: 받침 읽기(받침 없는 롬은 멈춤, `WqNmiFF9A` 가 다른 곳을 부르면 드러남)와 판정.

## 남은 것

- `03:A175` → `03:A1C9`(표 `0A`~`0D`)가 어느 장면인지.
- 1장 롬으로 `19/02` 에 순간이동해 레이스를 띄워 보지는 않았습니다.
