# dq5 도구

저장소 최상위에서 `uv run --locked python sfc/dq5/tools/<스크립트>` 로 실행합니다. 롬은 첫 인자로 줍니다(`rom/dq5.sfc`). 모듈끼리는 같은 폴더에서 import 합니다.

MesenCE 프로브(`lua/`)는 [트랙 공통 도구](../../../tools/README.md) 의 `LIBDIR`·`MESENCE` 설정과 `seqlib.sh` 드라이버를 그대로 씁니다. 스크립트 경로만 `"$PWD/sfc/dq5/tools/lua/<스크립트>"` 로 줍니다.

## Python

| 스크립트 | 하는 일 |
| --- | --- |
| `dq5map.py rom BC BD` | DQ5 실내 맵 디코더. `--compare` 로 게임 셀 버퍼(속성 패스 끝)와 비교, `--png` 로 그림(팔레트도 롬에서). BC `50`~`54` 맵은 따로 된 포인터·블록·CHR 과 맵 전후 처리(슬롯 건너뛰기·블록 먼저 올리기·`+4` 찍기)를 따름 |
| `dq5field.py rom` | DQ5 필드 세계 지도 풀기. `--world 0~2` 로 `$1949` 세계 고르기, `--compare` 로 WRAM 과 비교, `--png` 회색조 지도, `--entrances` 로 입구 47개와 도착 자리 |
| `dq5trigger.py rom [BC BD]` | DQ5 실내 맵 영역 이동 레코드(맵을 빼면 전체 통계) |
| `attrgrid.py rom BC BD` | 통행 격자를 글자로 찍기(경로 잡기용) |
| `dq5exit.py rom BC BD` | DQ5 실내 맵 출구 셀·목적지·도착 자리. 맵을 푼 뒤 도는 맵별 루틴(`15:F907`)이 바꾸는 출구 셀도 반영 |
| `dq5npc.py rom BC BD` | DQ5 실내 맵 인물 목록과 인물 표 값·인라인 스크립트 명령. `--night` 밤 목록, `--flags 21AD=10` 이벤트 플래그, `--compare` 로 인물 표(`7E:3000-`) 23칸 비교, `--list 108BBD` 목록 주소로 보기, `--check-scripts` 모든 스크립트 길이 검사 |
| `dq5text.py rom 번호` | DQ5 보행 모드 메시지를 글자로(`--codes` 로 코드). `--controls` 제어 코드 처리기와 뜻, `--window N` 메뉴 창 레코드와 항목 문자열. 폰트 그리기(`glyph`), 글자표(`CHARS`), 이름 문자열(`string`·`string_codes`)도 이 모듈 |
| `dq5battletext.py rom [번호…]` | DQ5 전투 모드 메시지(`24:8C39`) 432개를 풂. 제어 코드는 `{F7}` 꼴 |
| `dq5talk.py rom 대화번호` | 대화 번호의 갈래·스크립트·메시지(조건 코드 뜻, 특수 기능 처리기, 묻기 갈래 포함). `BC BD` 를 주면 그 맵 인물 전부, `--check` 로 스크립트 574개 경계 검사, `--calls` 로 네이티브 호출 대상·갈래·하는 일, `--field` 로 `BRK 80`~`93` 필드 설명자 |
| `dq5hangul.py rom expand\|retree -o 롬` | DQ5 한글 넣기 실현성 실험용 롬: `expand --size 2\|3\|4` 롬 확장(표지·체크섬), `retree` 메시지를 새 허프만 트리로 다시 부호화해 뱅크 30 으로 옮기고 글자 3DB·3DC(「한」「글」)를 더함. `proto` 한글 시제품(메시지 129·이름·명령 창). 결과 롬은 `work/` 에만 |
| `dq5hangulfont.py` | 한글 시제품 글꼴: 자모를 좌표로 정의해 조합한 점 그림(`render(글자, 폭, 높이)`). 남의 글꼴을 쓰지 않음 |
| `dq5chest.py rom [BC BD]` | DQ5 보물상자(번호·칸·열림 플래그·내용물), タンス·ツボ·タル 항목, 발밑 표(`1E:F08B`), 두 칸 앞 표(`1E:F435`). 물건 이름과 `D000`~`D009` 의 뜻까지 |
| `dq5shop.py rom` | DQ5 상점 품목 목록(종류·마을 그룹 키)과 물건 가격, 작은 메달·코인 교환 값, 격투장 시합 50개(문턱 레벨·倍率), 슬라임 레이스 바탕 줄과 倍率 식(`slime_odds`), 여관 1인 값 |
| `dq5growth.py rom` | DQ5 레벨업 성장 표: 사람(`23:9E41`, `--person`)·동료 몬스터(`23:A1B1`, `--monster`) 레코드의 레벨 1~99 능력치 일곱과 누적 경험치(`stat_at`·`exp_at`·`gains`) |
| `dq5sram.py rom 세이브` | DQ5 SRAM 세이브 8KB: 머리 두 곳, 쓰는 칸 비트, 모험의 서 3칸의 상태·체크섬(저장값과 `25:8450` 계산값)·주인공 이름·레벨·금화. `--fix out` 으로 체크섬을 다시 계산해 씀 |
| `dq5item.py rom` | DQ5 물건 216개의 장비 칸·공격력/수비력·사람 장비 비트·동료 몬스터 장비 비트(16비트)·가격과 표 k0~k4 원값 |
| `dq5monster.py rom` | DQ5 몬스터 236개의 필드(HP·MP·민첩·공격·수비·경험치·금화·행동 수·재생·떨어뜨리는 물건·동료 확률과 종류 등), 행동 6개, 내성 18칸. `--companions` 동료 레코드(`23:AED1`) 41개 |
| `dq5spell.py rom` | DQ5 전투 행동 171개(주문·몬스터 행동)의 이름·MP·범위 비트·처리 루틴·피해/회복량·내성 종류 |
| `dq5damage.py 공격력 수비력` | DQ5 보통 공격 피해 범위(`20:B030`)와 회심 피해 범위(`20:AB04`). `--party` 는 맞는 쪽이 일행(공격력/16 갈래) |
| `dq5recruit.py rom` | DQ5 동료가 되는 몬스터 41종의 확률 등급(필드 76)·동료 종류(필드 77)·들인 수 0·1·2 일 때의 1/N(`27:8162`·`8172`·`8182`)과 반드시 동료가 되는 가진 물건(`26:8D33`) |
| `dq5drop.py rom` | DQ5 몬스터 220종이 떨어뜨리는 물건(필드 75)과 확률 1/N(필드 74 → `27:8218`) |
| `dq5daynight.py rom` | DQ5 낮밤: 시간대 `$075E` 의 걸음당 증가·자르는 값(`00:82D3`), 밤 문턱(`21:8000`), 필드 색 벌 구간(`01:A16B`), `$075E` 에 상수를 쓰는 곳. `--start 50 --steps 200` 으로 걸은 뒤 값과 낮밤 |
| `dq5encounter.py rom [BC BD]` | DQ5 전투 조우 구역 85개의 칸별 무리·확률·마릿수. `BC BD` 는 그 실내 맵의 구역, `--maps` 조우가 있는 실내 맵, `--field` 필드 구역 격자, `--events` 이벤트 전투 무리 표(`23:D757`), `--trace trace.txt` 로 `probe/trace.lua` 기록(`TRACE=23E7C2,23E9B0,23EA40,23E98F LOG=7E1001,7E1003,7E1005,7E1007`)의 무리를 표와 대조, `--steps trace.txt` 로 걸음마다의 구역·조우율(`TRACE=0082AF LOG=7E00BC,7E00BE,7E00B6,7E00B8,7E1948,7E075E,7E21C9`)을 격자·지형으로 계산한 값과 대조 |
| `dq5mongfx.py rom [몬스터…]` | DQ5 전투 몬스터 그림(그림 번호·머리·조각·색). `--png` 그림, `--compare at.bin` 게임 버퍼(`7E:4000`)와 타일 비교, `--shot` 전투 화면과 RGB 비교, `--oam o.oam v.vram` OBJ 색 번호 비교, `--layout "몬스터:마릿수[:무리 값],…"` 무리 배치(그림 상자 OAM 좌표) |
| `dq5battlebg.py rom [번호]` | DQ5 전투 배경 49개(번호 `$1AA0 & 7F`, 그림·목록·팔레트 주소). `--png` 256x128 띠, `--cgram` 레코드 밖 색, `--alt` 밤 팔레트, `--era N` 세계, `--indoor` 실내, `--terrain X,Y` 필드 좌표의 지형(= 배경 번호), `--compare 덤프폴더 프레임` 으로 `dq5battledump.lua` 덤프와 비교 |
| `dq5anim.py rom [BC BD]` | DQ5 실내 맵의 움직이는 타일: 종류 16개(주기·벌 수·타일 수·자료 주소·원본 블록)와 맵 103곳의 종류. `BC BD` 는 그 맵, `--check 덤프폴더 첫 끝` 으로 `lua/dq5gfxdump.lua` 의 프레임별 덤프와 벌 바꾸기·줄 돌리기를 견줌 |
| `dq5sound.py rom` | DQ5 소리 명령 입구(`24:FE91`~ 14개), `BRK 0F`~`19` 가 부르는 명령, 맵 346개의 곡 번호(맵 레코드 `+5`). `--check snd.txt --map BC/BD` 로 `lua/dq5sndlog.lua` 기록의 맵 곡과 견줌 |
| `dq5gfx.py rom` | DQ5 그래픽을 `--out` 아래 분류 폴더에 PNG 로(sfc-dq4-assets 의 폴더·파일 규칙): `maps/`(맵 364개, `-night`·`-setNN`·`-annot`), `field/`, `monsters/`, `battlebg/`, `gfx/blocks/`(CHR·블록), `gfx/screens/`(창·창 레코드 목록 창·세계 지도·타이틀 글자), `gfx/anim/`(실내 움직이는 타일과 맵 GIF 포함), `gfx/font.png`. 폴더마다 `index.json`·`SOURCE.txt`. `--only`·`--maps` 로 일부만, `--check 덤프 BC/BD` 로 `lua/dq5gfxdump.lua` 덤프의 BG 화면과 픽셀 비교 |
| `dq5gallery.py rom` | `dq5gfx.export_all` 을 돌리고 `--out` 의 `gallery/index.html`·`sprites.html` 을 만듦(에셋 저장소 `fc/dq4/gallery` 와 같은 꼴, `../<분류>/` 상대 링크). 인물 스프라이트는 `sprites/index.json` 이 있으면 링크, 없으면 `dq5sprite.export_all` 로 뽑음 |
| `lua/dq5battledump.lua` | 전투 그림 실험: `AT` 실행 때 WRAM(`at.bin`), `DUMPF` 프레임에 WRAM·VRAM·CGRAM·OAM·화면, `FROM`~`TO` DMA 기록. `boot.lua`(walk.lua) 뒤에 붙여 씀 |
| `lua/dq5hdma.lua` | `DUMPF` 프레임에 `$420C`·DMA 채널 레지스터(`hNNNNN.txt`), WRAM, 화면. `boot.lua`(walk.lua) 뒤에 붙여 씀 |
| `lua/dq5msgswap.lua` | 전투 메시지 루틴 `24:8C39` 에 들어올 때 A 가 `FROMMSG` 이면 `TOMSG` 를 차례로 넣어 아무 메시지나 전투 창에 띄우고 `SHOTS` 프레임에 화면을 찍음. 메시지 번호 기록 `msg.txt` |
| `lua/dq5sndlog.lua` | 소리 명령 대기열 `24:FF83` 에 들어오는 명령·인자·부른 곳을 `snd.txt` 로, `SHOTS` 프레임에 화면 |
| `dq5sprite.py rom` | DQ5 필드 인물 스프라이트 세트 147개(그림 번호 → 세트 `25:86D0`, 레코드 `1F:D63D`, 런 길이 타일)와 맵 OBJ 타일 27개(`1F:D59A`). `--out work/sprites` 로 sfc-dq4-assets 규칙의 1배 그림: 세트마다 `<세트>[-<이름>].png`(행 아래·왼쪽·오른쪽·위 × 걸음 프레임 0·1, 투명 배경)·누운 모양(`-lying.png`, 24x16)·탈것(`v80-まほうのじゅうたん-1.png` 등, `$1954` 80~82 의 부분마다)·색 번호 보기(`-index.png`). 이름은 일행 표(`05:D9D5`·동료 `05:D9E1`)와 대화 화자에서·맵 OBJ 타일 `obj-<BC>-<BD>.png`·`index.json`(색 번호 행렬 포함). `--scale`·`--grid` 로 확대·격자, `--list` 목록, `--compare 덤프폴더…` 로 `lua/dq5sprdump.lua` 덤프의 VRAM·칸 목록·OAM 과 비교. 갤러리는 `export_all(rom, outdir)` 를 import. 뽑은 결과는 비공개 `sfc-dq4-assets` 의 `sfc/dq5/sprites/` |
| `dq5sprite.py rom` | DQ5 필드 인물 스프라이트 세트 147개(그림 번호 → 세트 `25:86D0`, 레코드 `1F:D63D`, 런 길이 타일)와 맵 OBJ 타일 27개(`1F:D59A`). `--out work/sprites` 로 sfc-dq4-assets 규칙의 1배 그림: 세트마다 `<세트>[-<이름>].png`(행 아래·왼쪽·오른쪽·위 × 걸음 프레임 0·1, 투명 배경)·누운 모양(`-lying.png`, 24x16)·탈것(`v80-まほうのじゅうたん-1.png` 등, `$1954` 80~82 의 부분마다)·색 번호 보기(`-index.png`). 이름은 일행 표(`05:D9D5`·동료 `05:D9E1`)와 대화 화자에서·맵 OBJ 타일 `obj-<BC>-<BD>.png`·맵 OBJ 물체(`objat-<맵>-<번호>.png`, `16:F862` 배치)·`index.json`(색 번호 행렬 포함). `--scale`·`--grid` 로 확대·격자, `--list` 목록, `--compare 덤프폴더…` 로 `lua/dq5sprdump.lua` 덤프의 VRAM·칸 목록·OAM 과 비교. 갤러리는 `export_all(rom, outdir)` 를 import. 뽑은 결과는 비공개 `sfc-dq4-assets` 의 `sfc/dq5/sprites/` |
| `dq5flags.py rom [2192.7]` | DQ5 이야기 플래그(`7E:2190`~`220F`) 비트·바이트마다 켜는 곳·끄는 곳·보는 곳(대화·인물 스크립트·인물 목록 표·맵별 루틴·맵 조건 표·이벤트 스크립트·네이티브 `BRK 0B`·`0C`·`0D`·롱 주소)과 문맥 메시지. `--source` 출처 고르기, `--check flagtrace.txt` 로 게임 기록과 대조 |
| `dq5event.py rom [주소]` | DQ5 이벤트 스크립트(`00:BEC3`). 이벤트 표 `23:E2C2` 10개의 목표 자리와 스크립트, 주소를 주면 그 스크립트, `--all` 로 `15:F150`~`F7CF` 의 86개, `--number N` 스크립트 번호 표(`23:E325`), `--starts` 번호 표·이벤트 표·코드·`02:B705` 직접 호출·점프에서 모은 106개, `--list` 시작 주소·부르는 곳(`LDA #n` + `JSL` 이나 받침 루틴 `JMP`)·첫 메시지 한 줄씩 |
| `dq5framediff.py 원래 패치` | `lua/dq5framedump.lua` 결과 둘(`frames.bin`)을 덤프마다 견주어 WRAM·VRAM·CGRAM·OAM 의 다른 구간과 처음 다른 덤프 번호를 보임. 기본은 DP·스택 임시 값을 뺌(`--all` 이면 모두) |
| `dq5figures.py` | `sfc/dq5/images/` 의 그림을 다시 만듦(롬 필요, 게임 화면 비교 그림만 `work/` 덤프 필요) |

## lua/: MesenCE 분석 스크립트

| 스크립트 | 하는 일 | 추가 환경 변수 | 결과 |
| --- | --- | --- | --- |
| `lua/dq5savestate.lua` | 드라이버(`boot.lua`) 입력을 재생하다가 `SAVEAT` 프레임에 세이브스테이트와 화면 저장. `seqlib.sh` 로 `dq5warp.lua` 를 드라이버로 두면 장면 이동 뒤 걸어 들어간 곳을 남길 수 있음 | `SAVEAT`, `SAVENAME` | `<SAVENAME>`, `.png` |
| `lua/dq5warp.lua` | DQ5: 배 선실 세이브스테이트에서 조작 가능한 필드(`FIELD`), 아무 실내 맵(`TO`, 그룹 `50` 이상 포함), 고른 무리와의 전투(`BATTLE`, `GROUP`)로, 동료 몬스터 일행(`PARTY`)·청년기 플래그(`ADULT`)를 넣고 가서 세이브스테이트 저장. 사용법은 [dq5-handoff.md 「장면 이동 도구」](../handoff.md#장면-이동-도구) | `STATE`, `FIELD`(`X,Y`)·`TO`(`BC/BD,X,Y[,방향]`)·`BATTLE`(`몬스터:마릿수,…`)·`GROUP`(이벤트 무리 번호), `PARTY`(`02,05`), `ADULT`(`1`·`2`), `WAGON`(`1`), `LATESET`(`1954=03`), `SET`(`2194\|80`), `POKE`, `ROMPATCH`, `TEST`, `SETTLE`, `SAVE`, `MAXF` | `warp.txt`, `end.png`, `<SAVE>` |
| `lua/dq5battle.lua` | DQ5: `walk.lua` 처럼 걸은 뒤 `LOOP` 입력(기본 A 연타)으로 싸우면서 전투 메시지(`24:8C39`) 번호와 `PEEK` 주소 값을 메시지마다 기록. 쓰는 예는 [dq5-data-format.md 「주문과 행동」](../docs/dq5-data-format.md#주문과-행동-268765) | `STATE`, `PRE`, `WAYPOINTS`, `LOOP`, `ROMPATCH`, `POKE`, `PEEK`(`7E07C0:64,…`), `SHOTMSG`, `SHOTDELAY`, `MAXF` | `battle.txt`, `sNNNNN.png`, `end.png` |
| `lua/dq5sprdump.lua` | DQ5: 세이브스테이트에서 `SEQ` 대로 걸으며 정한 프레임마다 WRAM·VRAM·OAM·CGRAM·화면 덤프(걷는 동안 조우 끔). `dq5sprite.py --compare` 가 읽음 | `STATE`, `OUT`, `SEQ`(`down@20:30,…`), `DUMPF`(`5,60`), `EVERY`·`FROM`, `MAXF`, `ROMPATCH`(런타임 롬), `POKE`(매 프레임 고정, 예 `7E075E=F0` 밤) | `wNNNN.bin`, `vNNNN.vram`, `oNNNN.oam`, `cNNNN.cgram`, `sNNNN.png` |
| `lua/dq5framedump.lua` | DQ5: `dq5warp.lua` 로 순간이동하면서 목적지(`TARGET`, 필드면 `FIELDT=1`)에 들어선 뒤 `STEP` 프레임마다 WRAM·VRAM·CGRAM·OAM 을 `frames.bin` 에 이음. `ROMPATCH` 만 바꿔 두 번 돌리고 `dq5framediff.py` 로 견줌. 기록용 스크립트를 얹지 않아 패치 하나의 효과만 남음. `LIBDIR` 의 `boot.lua` 를 `dq5warp.lua` 로 둠 | `dq5warp.lua` 의 변수, `TARGET`, `FIELDT`, `STEP`(8), `COUNT`(40), `COVLO`·`COVHI`(실행 PC 모으기) | `frames.bin`, `sNNN.png`, `cover.txt`, `warp.txt` |
| `lua/dq5flagtrace.lua` | DQ5: `BRK 0B`·`0C`·`0D` 를 부른 자리(BRK 처리기 `00:8F80` 의 스택에서)와 `7E:2190`~`220F` 쓰기(주소·값·PC, 처음 한 번)를 기록. `TO`·`FIELD` 면 `dq5warp.lua` 로, 아니면 `boot.lua` 드라이버로 돎 | `dq5warp.lua` 의 변수 또는 드라이버 변수, `MAXF` | `flagtrace.txt` |
| `lua/dq5warptrace.lua` | DQ5: `dq5warp.lua` 를 그대로 돌리면서 PC 실행·WRAM 읽기·쓰기를 기록하고, 도착한 뒤 정한 프레임에 WRAM 을 고치거나 화면을 찍음 | `dq5warp.lua` 의 변수, `TRACE`, `LOG`, `RWATCH`·`WWATCH`(`1000-1000`), `WFROM`, `LATE`(`600:7E21C9=01`), `SHOTS` | `trace.txt`, `rwatch.txt`, `wwatch.txt`, `sNNNNN.png` |
| `lua/dq5msg.lua` | DQ5: 세이브스테이트에서 롬·WRAM 을 고치고 입력을 재생하며(파파스에게 말 걸기 등) PC 실행·쓰기를 기록하고 화면·메모리를 남김. 쓰는 예는 [일지 2026-10-25-45](../journal/2026-10-25-45-text2.md) | `STATE`(없으면 전원 켜기부터), `PRE`, `ROMPATCH`, `SET`(첫 프레임, `206A=05`), `POKE`(매 프레임), `CALLS`, `LOG`, `WW`, `WWRANGE`(`7E3000-7E37FF:1F=0B`)·`WWFROM`, `SHOTS`, `DUMP`(`300:7E2000:64`), `VRAMDUMP`, `BG3FONT`(`26528:8A`, 롬의 창 글자를 VRAM 에 다시 씀), `MAXF` | `msg.txt`, `sNNNNN.png`, `end.png` |
| `lua/dq5gfxdump.lua` | DQ5: 드라이버 입력을 재생하며 정한 프레임에 WRAM·CGRAM·VRAM·OAM·화면과 PPU 상태(`emu.getState()` 의 `ppu.*`)를 덤프. `tools/lua/seqlib.sh` 로 `seqboot.lua` 를 드라이버로 두고 세이브스테이트에서 씀. `dq5gfx.py --check` 가 읽음 | `STATE`, `SEQ`, `DUMPF`(쉼표로 여럿) 또는 `EVERY`·`FROM`·`TO` | `fNNNNN.wram`·`.cgram`·`.vram`·`.oam`·`.png`·`.ppu.txt` |
| `lua/dq5vramlog.lua` | DQ5: VRAM 에 올리는 곳 찾기. `$420B` DMA 마다 B 버스 대상·원본·크기·VRAM 주소, `$2118`/`$2119` 를 쓰는 PC(다음 명령 주소)별 첫 프레임·VRAM 주소·횟수. 레지스터 미러 뱅크 `00`~`3F`·`80`~`BF` 모두 감시 | `FROM`, `STOPF`, `BBUS`(16진, 0 이면 전부), `VLO`·`VHI`(VRAM 워드) | `dma.txt`, `vport.txt` |
