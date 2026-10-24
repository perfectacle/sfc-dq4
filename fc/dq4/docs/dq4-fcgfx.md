# DQ4(FC) 원작 그래픽 렌더링

SFC 로 다시 그릴 때 참고하려고 FC 원작의 마을·던전 맵 279개, 필드, 블록·CHR·폰트 시트, 타이틀·창·전투 화면을 PNG 로 뽑는 도구 [tools/dq4fcgfx.py](../tools/dq4fcgfx.py) 의 쓰는 법과, 그리면서 새로 확인한 것(MesenCE 색, 필드 물가 블록)입니다. 블록·타일·팔레트 해석은 [dq4-block-format.md](dq4-block-format.md), 맵·출구·인물은 [dq4-map-format.md](dq4-map-format.md), 필드는 [dq4-field-format.md](dq4-field-format.md) 를 따릅니다. 실험 과정은 [2026-10-25-30 일지](journal/dq4/2026-10-25-30-fcgfx.md) 에 있습니다.

뽑은 그림은 롬 그래픽이라 이 저장소에 커밋하지 않습니다. 비공개 저장소 `perfectacle/sfc-dq4-assets` 의 `fc/dq4/` 아래에 두고, 폴더마다 `SOURCE.txt` 에 만든 커밋·명령·롬 SHA-1 을 적습니다.

## 출력

```sh
uv run --locked python tools/dq4fcgfx.py rom/dq4.nes all OUT          # OUT/{maps,field,gfx,gallery}
uv run --locked python tools/dq4fcgfx.py rom/dq4.nes scenes OUT SPEC.json   # MesenCE 덤프 장면 → OUT/gfx/screens
uv run --locked python tools/dq4fcgfx.py rom/dq4.nes gallery OUT      # 장면을 넣은 뒤 갤러리만 다시
uv run --locked python tools/dq4fcgfx.py rom/dq4.nes map 02 01 work/x.png [--night|--annot]
```

맵 목록은 `dq4chest.all_maps`(279개)입니다. `dq4map.maps` 는 마지막 그룹 `48`(맵 10개, 맵 종류 `1B`·`1C`)을 빼므로, 렌더러는 자기 프로세스 안에서만 `dq4map.load` 를 `dq4chest.load` 로 바꿔 씁니다.

| 폴더 | 파일 | 내용 |
| --- | --- | --- |
| `maps/` | `GG-KK-<이름>.png` | 맵 1배(블록 16×16 픽셀). 칸마다 제 블록으로 그려 다른 구역(집 안 등)도 보임 |
| | `…-night.png` | 밤 팔레트(`$62ED` ≥ `78`)가 낮과 다른 맵 176개만 |
| | `…-annot.png` | 주석판: 노랑 인물(낮 목록 순번), 보라 밤에만 있는 인물, 하늘색 출구(목적지 그룹), 빨강 `T` 보물상자, 분홍 `F` 발밑 숨은 물건. 칸 속성(`dq4block.terrain`)으로: 주황 `D0`~`D3` 문(잠금 단계), 초록 `S` 계단·출구 검사 칸(출구 표에 없는 것), 가는 분홍 테두리 떨어지는 칸, `L` 리프트, `W` 旅の扉, `!` 데미지 바닥, `^>v<` 움직이는 바닥, `P` タンス·つぼ, `N` 팻말 |
| | `index.json` | 맵마다 그룹·순번·맵 종류·크기·이름, 인물(자리·겉모습·대화 번호)·출구·상자·발밑 물건, 칸 속성 표시(문 잠금 단계, 리프트 짝, タンス·つぼ 내용물 `dq4block.pots`, 팻말 메시지 `dq4block.signs`), 떨어지는 칸(목적지 `dq4block.fall` 마다 칸 묶음) |
| `field/` | `field0.png`~`field3.png`, `-night`, `-annot` | 필드 4개 1배. 밤은 필드 팔레트의 가장 어두운 단계(`$62ED` `84`~`BF`). 주석판은 입구 칸에 그룹 번호 |
| `gfx/blocks/` | `typeTT.png`, `index.json` | 맵 종류 51가지(필드 `00` 포함)의 블록 `00`~`21` 2배, 칸 아래에 블록 번호·속성 값. `index.json` 에 속성 이름(`dq4block.kind_name`) |
| `gfx/` | `chr0C-gray.png`, `chr0C-color.png`, `chr0D-…` | PRG 뱅크 `0C`·`0D` 전체(타일 1024개) 2배. 색은 그 뱅크를 가장 많이 쓰는 (맵 종류, 팔레트) |
| | `font.png` | `18:$B840` 의 글자 141개 4배. 창 테두리와 커서 ▶ 도 이 안에 있음 |
| `gfx/screens/` | `<장면>-nt.png`, `-bgchr.png`, `-shot.png` | MesenCE 덤프의 nametable 두 장(512×240)·BG 패턴 표·화면 |
| `gallery/` | `index.html` | 위 전부의 썸네일. 상대 경로만 쓰고 외부 리소스가 없음. `sprites.html` 은 스프라이트 쪽이 만듦 |

이름은 롬에 그룹 → 이름 표가 없어서 대사로 정합니다. 그룹마다 인물 대사(낮·밤, 조건 갈래 전부)에서 「ここは」「ようこそ」 뒤 30글자 안에 장소 이름표(`0B:$B634`, 28개)의 이름이 처음 나오는 것을 쓰고, 뒤에 「ほこら」「どうくつ」가 이어지면 붙입니다. 73개 그룹(`00`~`48`) 중 24개에 이름이 붙고, 나머지는 `GG-KK.png` 입니다. 글자는 롬의 글자표 그대로라 가타카나가 없는 글자는 히라가나입니다(예: `りバーサイド`).

## 색

NES 색 번호 → RGB 는 MesenCE 기본 팔레트를 화면에서 잰 값(`MESEN_RGB`)입니다. [tools/lua/fc/fcgfxpal.lua](../tools/lua/fc/fcgfxpal.lua) 가 세이브스테이트를 불러 nametable 을 빈 타일로, OAM 을 화면 밖으로 치운 뒤 BG 팔레트 색 0 을 `00`~`3F` 로 바꿔 가며 화면을 찍습니다. MesenCE 화면 덤프는 메모리를 바꾼 프레임보다 한 프레임 늦게 바뀌어서, 색마다 4프레임을 두고 마지막에 찍었습니다(처음 한 프레임씩 찍었을 때는 색이 하나씩 밀리고, 한 곳에서는 둘이 겹쳤음).

```sh
export LIBDIR=$(uv run krpatch fc lua)
STATE=$PWD/work/state/dq4-ch1-throne.mss SHOT_DIR=$PWD/work/pal \
  "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros $PWD/rom/dq4.nes $PWD/tools/lua/fc/fcgfxpal.lua
```

## 필드의 물가 블록

필드 블록 `00`(물)은 화면에 그릴 때 이웃에 따라 블록 `20`~`2F` 로 바뀝니다(`0F:$D478`). 이것을 빼면 물가가 들어간 화면이 덤프와 어긋납니다.

| 단계 | 루틴 | 내용 |
| --- | --- | --- |
| 정의 올리기 | `08:$851E` → `$80B7` | 필드(`$07` = 0)면 블록 `20`~`2F` 의 2바이트 정의를 포인터 `08:$80C2`(`$8ABB`)부터 차례로 올림. 모양 레코드·타일 올리기는 블록 `00`~`1F` 와 같음 |
| 이웃 보기 | `0F:$D4A8`·`$D4CC` | 왼쪽, 아래, 오른쪽, 위 순서로 필드 칸을 찾아(`0F:$D244`) 블록이 `00`·`16`·`0A` 가 아니면 1 을 밀어 넣음(`ROL`). 결과 + `20` 이 그릴 블록: bit3 왼쪽, bit2 아래, bit1 오른쪽, bit0 위가 땅 |
| 필드 3 | `0F:$D483` | 블록 `01` 은 난수(`0F:$C891`)가 `FA` 미만이면 `18`, 아니면 `19`. 그림에는 `18` 을 씀 |

블록 `20` 은 물 그대로, `21` 은 위 두 타일이 물가 타일(`0C:$8030`·`$8010`)입니다. 필드 덤프의 `$7600`+4×블록(`20`~`2F`)과 위 정의로 만든 타일 그림이 같았습니다(필드 0·1·3).

`0F:$D2AA` 는 좌표에서 3 을 뺀 값이 폭·높이를 넘을 때만 0 을 돌려주므로, 가장자리 칸의 이웃은 폭·높이 +2 칸까지 원래 줄 데이터를 읽습니다. 렌더러는 줄마다 256칸, 높이 +3 줄을 풀어 둡니다(`dq4field.decode` 는 폭에서 자름).

## 확인

롬만으로 그린 화면과 MesenCE 화면 덤프를 256×240 전체 픽셀로 비교합니다. 렌더러는 RAM 의 장소(`$63`/`$64`/`$65`)·화면 왼쪽 위 칸(`$7C`/`$7B`)·스크롤(`$0505` bit0, `$0508`, `$0509`)·구역(`$7140`)·`$07BA`·시각(`$62ED`)만 읽고 나머지는 롬에서 그립니다. 덤프는 MesenCE 에 `--nes.disableSprites=true --nes.forceBackgroundFirstColumn=true` 를 줘 스프라이트를 끄고 왼쪽 8픽셀도 BG 를 보이게 해서 뜹니다.

```sh
# 워프로 맵에 들어간 상태를 만들고, 그 상태에서 스프라이트를 끈 화면을 덤프
WAIT=100 TAIL=10 sh tools/dq4warp.sh work/w/0E-00 0E/00
DRIVER=$LIBDIR/seq.lua STATE=$PWD/work/w/0E-00/warp.mss SEQ="wait:2" TAIL=3 EVERY=0 SHOT_DIR=$PWD/work/v/0E-00 \
  "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros --nes.disableSprites=true --nes.forceBackgroundFirstColumn=true \
  $PWD/rom/dq4.nes $LIBDIR/seq.lua
uv run --locked python tools/dq4fcgfx.py rom/dq4.nes verify work/v/*/
```

| 덤프 | 결과 |
| --- | --- |
| 맵 종류 50가지마다 맵 하나(워프) | 48가지가 61440 픽셀 모두 같음. `2D`(`04/07`)·`18`(`3B/00`)은 아래 「남은 것」 |
| `02/00` | 워프로 들어가면 성문 연출이 화면을 옮겨 RAM 의 화면 자리와 다름. (0F,20) 에 바로 내리면 0 다름 |
| 밤(`SET="62ED=90"`): `02/00`·`0E/00`·`12/00`·필드 0 | 모두 0 다름 |
| 필드 0·1 | 0 다름(물가 블록을 넣은 뒤. 넣기 전 필드 1 은 243 픽셀 다름) |
| 필드 3 | 4796 픽셀 다름. 덤프의 BG 팔레트로 그리면 114. 용암·물 팔레트가 프레임마다 돌아감 |
| 필드 2 | 거의 모두 다름(「남은 것」) |

장면 화면(`scenes`)은 [tools/lua/fc/fcgfxscene.lua](../tools/lua/fc/fcgfxscene.lua) 로 뜬 nametable·CHR·팔레트 덤프를 그린 것이고 롬에서 직접 푼 것이 아닙니다. 화면과 견주면 제작진 화면·IV 로고·모험의 서 창·이름 입력·전투 두 장면은 스프라이트 자리를 빼고 0 다름, 타이틀은 IV 글자(스프라이트)와 아래 물결이 다르고, 필드의 상태 창·명령 창 장면은 걷는 인물(스프라이트가 OAM 덤프 자리와 달라 다 가려지지 않음)과 게임이 BG 를 가리는 왼쪽 8픽셀만 다릅니다(장면 덤프는 `forceBackgroundFirstColumn` 없이 떴음). 장면 목록은 `[{"name", "title", "prefix"}]` 꼴 JSON 이고 `prefix` 는 덤프 파일 앞부분(`work/scene/boot/f02440`)입니다.

```sh
# 전원을 켜서 2440프레임(타이틀)까지. 세이브스테이트에서는 DRIVER=$LIBDIR/seq.lua 와 STATE, SEQ 를 주고 이 Lua 를 그대로
SHOT_DIR=$PWD/work/scene/boot MAXF=2500 EVERY=0 AT=760,1040,2440 SRAM_DRIVER=$PWD/tools/lua/fc/fcgfxscene.lua \
  "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros $PWD/rom/dq4.nes $PWD/tools/lua/fc/debugsram.lua
```

폰트 141자(`18:$B840`)는 이름 입력·모험의 서·전투·5장 명령 창의 CHR 덤프(`$1000`+글자×16 앞 8바이트, 뒤 8바이트 0)와 모두 같았습니다. 전투 화면 BG 는 검은 바탕에 창뿐이라 따로 그린 전투 배경은 없습니다.

## 남은 것

- 맵 종류 `18`(`3B/00` 폭포): 물 타일 그림이 프레임마다 아래로 흐름. 애니메이션 목록(`1D:$8096`)에 없는 경로. 그림은 롬의 첫 그림.
- 맵 종류 `2D`(`04/07` 투기장): 화면이 RAM 스크롤보다 아래로 밀려 보임(관중 애니메이션 블록을 빼도 22382 픽셀 다름). 화면 분할이나 다른 스크롤 변수로 보임.
- 필드 2(42×54): 입구 표·도착 표에 없고 워프로 들어간 화면이 렌더링과 다름. 줄 레코드 해석이 이 필드에서 맞는지 모름.
- 필드 3 의 팔레트 돌리기 루틴과 순서. 맵의 밤 팔레트는 4곳만 화면으로 확인.
- 엔딩 화면, 장 제목 화면(장 시작 세이브스테이트는 그 뒤 장면).
- 그룹 49개의 이름(대사에 「ここは …」 가 없음).
- 성문 연출(`02/00`)이 화면을 옮기는 변수.
