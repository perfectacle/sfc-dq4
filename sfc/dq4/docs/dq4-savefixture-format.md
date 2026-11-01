# 저장 기록으로 시작하는 검사

장면 검사가 서장(약 1만8천 프레임)을 걷지 않고 원하는 상태에서 시작하도록, 저장 기록(SRAM)을 만들어 넣고 「이어 하기」로 시작합니다. 도구는 `sfc/dq4/tools/dq4savefixture.py`, 회귀 가드는 [`guards.toml`](../guards.toml) 의 `dq4-savefixture` 입니다. SRAM 형식은 DQ5 그대로이고 [DQ5 SRAM 세이브](../../dq5/docs/dq5-data-format.md) 와 `sfc/dq5/tools/dq5sram.py` 를 씁니다. 실측은 libretro snes9x 1.63 `fae2fea`·bsnes 115 `63ee22f7`([코어](dq4-compat-format.md#코어)), 1장 롬(`dq4build.py` 출력 `dq4-ch1-full.sfc`)으로 했습니다.

## SRAM

| 자리(`70:`) | 내용 |
| --- | --- |
| `0000`, `1FF2` | 머리 「DRAGON QUEST V」(14바이트). 켤 때 `25:8062` 가 두 곳을 보고, 둘 다 다르면 SRAM 을 지움 |
| `000E` | 쓰는 칸 비트(칸 1 = `01`, 2 = `02`, 3 = `04`) |
| `000F`~`0011` | 칸마다 상태. `C0` 이 마지막으로 기록한 칸이고 이어 하기 커서가 그 칸에 섬 |
| `0012`, `0AB2`, `1552` | 칸 1~3, 칸마다 `AA0` 바이트 = WRAM `7E:2000`~`2A9F` 그대로 |
| 칸 `+A9E` | 체크섬: 앞 `54F` 워드의 16비트 합(`25:8450`) |

맨바닥 SRAM 에 머리 두 곳, `000E` = `01`, 상태 `C0`, 칸 1 하나만 두어도 이어 하기가 정상으로 돕니다(snes9x·bsnes). 칸의 내용은 새 게임이 첫 기록을 쓴 칸을 밑판으로 씁니다. 새 게임은 약 964프레임에 칸 2 를 씁니다(서장 검사와 같은 부팅 입력). 밑판은 저장소에 넣지 않고 snes9x 로 한 번 만들어 원래 체크아웃의 `work/cache/states/savefixture-newgame-<키>.srm` 에 둡니다(`DQ4_STATES_CACHE` 로 바꿈). 키는 롬 SHA-1, snes9x 코어 파일 SHA-256, 새 게임 입력(Y 를 누르는 프레임, A 연타 주기와 끝 프레임, 기다리는 프레임 수)을 묶은 해시입니다. 셋 중 하나만 바뀌어도 칸 내용이 달라질 수 있어 다시 만듭니다(`new_game_key`).

체크섬이 틀린 칸은 켤 때가 아니라 타이틀을 넘겨 기록 목록을 고를 때 지워집니다. 두 코어 모두 398프레임에 `000E` 의 칸 비트가 꺼지고 칸 `AA0` 바이트가 0 이 됐고, 그 뒤 새 게임이 시작했습니다.

## 이어 할 자리

| 자리 | 내용 |
| --- | --- |
| `7E:2033` bit0-6 | ルーラ 칸 번호(0~21) |
| `7E:2033` bit7 | 밤. `25:8278` 이 시각 `7E:075E` 를 밤이면 `0190`, 아니면 `0050` 으로 둠 |
| `25:85D5`[칸] | 칸의 그룹(`01:8001` 이 0 이면 `25:85EB`) |
| `25:8621` | 6바이트 항목 `[BC][BD][X][Y][층][198E]`, `FF` 로 끝남. 칸의 그룹과 같은 첫 항목에 섬 |

1장 롬에서 표로 고른 자리와 이어 한 뒤 선 자리(snes9x, 맵에 선 프레임)는 같았습니다.

| 칸 | 그룹 | 선 자리 | 프레임 |
| --- | --- | --- | --- |
| 0 | `44` | `44/01` (6,9) | 436 |
| 2 | `36` 바트랜드 | `36/00` (10,45) 교회 신부 앞 | 445 |
| 7 | `37` 이무르 | `37/00` (50,9) 교회 신부 앞 | 432 |
| 8 | `3C` 서장 마을 | `3C/01` (6,30) | 422 |
| 11 | `42` | 표에 없음: 필드 | — |
| 16 | `15` | 표에 없음: 필드 | — |

표에 그룹이 없는 칸으로 이어 하면 필드에 섭니다. 전멸 뒤 다시 시작(`01:899F`)이 항목 0 으로 가는 것과 다릅니다([다시 시작 자리](dq4-chapter1-format.md#다시-시작-자리)). 필드의 어느 칸에 서는지는 재지 않았고, 도구는 이런 칸을 고르면 오류를 냅니다.

맵에 들어설 때 게임이 `7E:2193`·`21C7`(도착 그룹)과 `21CB`·`21CC` 를 고쳐 쓰므로, 불러온 `7E:2000`~`2A9D` 는 기록 칸과 이 네 바이트만 다릅니다(두 코어 같음). `21CB`·`21CC` 가 무엇인지는 확인하지 못했습니다.

## 만들 수 있는 상태와 없는 상태

기록 칸 안(`7E:2000`~`2A9D`)이면 무엇이든 고칠 수 있습니다. 도구가 이름으로 다루는 것은 아래와 같습니다.

| 값 | 자리 |
| --- | --- |
| 금화 | `7E:2019`~`201B` |
| 주인공 레벨·HP·최대 HP·MP·최대 MP | 일행 기록 0(`7E:2040`, 42바이트)의 `+12`, `+02`, `+0E`, `+04`, `+10` |
| 주인공 물건 12칸 | `+16`~`+21`, 빈 칸 `FF`. 바이트는 DQ5 물건 번호 그대로(새 게임 밑판은 `42 00`) |
| 동료 | `dq4compatcheck.party_pokes`(`dq5warp.lua` buildParty 와 같음) |
| 1장 flag | `dq4ch1walkcheck.FLAGS` |
| 앞 구간이 기록에 남기는 것 | `dq4ch1walkcheck.EFFECTS`(호이민 합류, 우물 상자) |
| 자리·밤 | `7E:2033` |

저장되지 않아 이어 하면 정해지는 것은 아래와 같습니다. 이어 한 뒤 `core.poke` 나 `dq4compatcheck.Walker.warp` 로 둡니다.

- 난수 `7E:075B`~`075D`, 시각 `075E`·`075F`(이어 하면 `0050`/`0190`), 프레임 카운터
- 주인공이 선 칸과 방향(표의 자리에 섬), 인물 위치
- 우물 flag: `25:8278` 의 훅이 이어 할 때 끕니다([던전 조우와 곡](dq4-chapter1-format.md#던전-조우와-곡))

같은 SRAM·같은 입력을 두 번 돌리면 맵에 선 프레임과 그 뒤 90프레임의 WRAM 128KB 가 0바이트 다릅니다(두 코어 각각). 이어 한 뒤 `Walker.warp` 로 탑 `39/04` 에 순간이동하면 snes9x 787프레임, bsnes 788프레임에 서고 일행·flag·금화는 그대로입니다.

## 코어에 넣기

| 코어 | SRAM 넣기 | 읽기 |
| --- | --- | --- |
| snes9x | `retro_get_memory_data(0)` 에 씀(게임을 연 뒤) | 같은 포인터 |
| bsnes 115 | `retro_get_memory_data`·`retro_get_memory_size` 가 nullptr·0 을 줌. 저장 폴더(`RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY`)의 `<롬 이름>.srm` 을 게임을 열 때 읽으므로 열기 전에 파일로 둠 | 직렬화 상태의 오프셋 558 부터 8KB |

한 프로세스에서 같은 코어 파일로 `Core` 를 여럿 열면 dylib 의 전역 상태를 나눠 씁니다. bsnes 는 앞 게임을 내리지 않고 다음 게임을 열면 `.srm` 대신 앞 게임의 SRAM 이 남았습니다. 다음 `Core` 를 열기 전에 `dq4savefixture.close` 로 `retro_unload_game` 을 부르고 `Core.close` 로 헤드리스 자리(`tools/headless_slots.py`)를 놓습니다.

## 사용법

```sh
# SRAM 파일 만들기(칸 1). 값은 여러 번 줌
uv run --locked python sfc/dq4/tools/dq4savefixture.py make --rom work/ch1/dq4-ch1-full.sfc --out work/fx/imuru.srm \
    --set place=imuru --set gold=1000 --set effect=hoimin --set flag=HOIMIN
# 두 코어에서 검사
uv run --locked python sfc/dq4/tools/dq4savefixture.py check --rom work/ch1/dq4-ch1-full.sfc --out work/savefixture
```

`--set` 의 값은 `gold=`, `level=`, `hp=`, `max_hp=`, `mp=`, `max_mp=`, `items=CD,01`(16진), `party=05`, `flag=HOIMIN,KIDNAPPED`(앞에 `-` 면 끔), `effect=hoimin`, `place=`(이름 `batland`·`imuru`·`prologue`·`santeem` 또는 한글, 또는 칸 번호), `night=1`, `poke=2058=CD;2223|08`(`dq5warp.lua` SET 꼴, `=`·`|`·`&`)입니다.

검사에서 쓸 때는 라이브러리로 부릅니다.

```python
import dq4savefixture as fx
slot = fx.SaveSlot.new_game(rom)          # 밑판(캐시)
slot.place = 'imuru'
slot.set_party('05')
slot.flag('HOIMIN')
core = fx.open_core(core_path, rom, out_dir, slot.to_sram())
arrived = fx.boot(core, slot.goal)        # 맵에 선 프레임, 그 뒤 90프레임 더 돎
core.poke(dq4compatcheck.sets(dq4ch1walkcheck.pins({})))   # 난수·시각을 걷기 검사와 같이
```

`dq4compatcheck.Walker` 와 함께 쓸 때는 `Walker` 가 `out/c.sfc` 를 `out` 을 저장 폴더로 여므로, 만들기 전에 `out/c.srm` 을 두고 `load_sram(walker.c, sram)`(넣은 SRAM 이 보이는지 확인) 뒤 `boot(walker.c, goal, step=walker.step)` 으로 부릅니다. `with closing(core):` 를 쓰면 예외로 끝나도 코어를 닫습니다.

이어 하기 입력은 start 2프레임, 10프레임 쉼, 그 뒤 A 2프레임·14프레임 쉼을 되풀이합니다. 맵에 서는 것은 432~445프레임, 화면이 밝아지는 것은 약 502~525프레임입니다. 도착은 맵·칸(`7E:00BC`·`00BD`·`3020`·`3080`)이 표의 자리와 같아진 첫 프레임으로 봅니다. `7E:2000` 블록을 기록 칸과 견주면 켤 때 `25:81CF` 가 칸을 WRAM 에 미리 불러 516프레임 무렵 거짓으로 같아지므로 쓰지 않습니다. 300프레임 전에는 보지 않습니다.

## 검사(`check`)

코어마다 프로세스 하나로 bsnes·snes9x 를 함께 돌립니다. 밑판에 금화 12345, 주인공 레벨 10·HP 99/99, 셋째 칸 そらとぶくつ 와 우물 상자 비트, 호이민 합류와 flag, 자리 이무르(칸 7)를 고친 SRAM 으로 봅니다.

| 무엇 | snes9x | bsnes |
| --- | --- | --- |
| (a) 고친 42바이트가 불러온 WRAM 과 같음, 금화·flag·일행 | 같음, 432프레임 | 같음, 433프레임 |
| (a) 밤 칸이 시각 `0190` 으로 섬 | `0190` | `0190` |
| (b) 체크섬을 1비트 틀린 칸이 지워짐 | 398프레임 | 398프레임 |
| (c) 같은 입력 두 번의 WRAM 128KB 차이 | 0바이트 | 0바이트 |
| (d) 이어 한 뒤 `39/04` 로 순간이동, 일행·flag·금화 그대로 | 787프레임 (46,42) | 788프레임 (46,42) |

한 번 도는 데 약 6초입니다(밑판 캐시가 있을 때).

## 남은 것

- MesenCE 에서 같은 SRAM 으로 이어 하기(`.srm` 을 MesenCE 저장 폴더에 두는 법과 테스트 러너에서의 이어 하기 입력).
- 표에 없는 그룹의 칸으로 이어 했을 때 필드의 어느 칸에 서는지와 그 루틴.
- `7E:21CB`·`21CC` 를 맵에 들어설 때 고쳐 쓰는 까닭.
- 기존 장면 검사(`dq4ch1walkcheck` 의 묶음 걷기 등)를 서장 세이브스테이트 대신 이 기록으로 시작하게 옮기기.
