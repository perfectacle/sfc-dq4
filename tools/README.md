# tools

## lua/: MesenCE 분석 스크립트

[MesenCE](https://github.com/nesdev-org/MesenCE) 의 `--testrunner` 로 롬을 화면 없이
돌리며 RAM·ROM 접근을 기록합니다. 모두
[kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) 의 `boot.lua`
(전원 켜기부터 버튼 입력·스크린샷)를 불러 쓰므로, 툴킷 Lua 폴더를 `LIBDIR` 로
넘깁니다.

```sh
export LIBDIR=$(uv run krpatch sfc lua)   # 툴킷 Lua 폴더
export MESENCE=/path/to/MesenCE       # macOS: .../MesenCE.app/Contents/MacOS/Mesen

mkdir -p work/wprof
SHOT_DIR=$PWD/work/wprof MAXF=1720 EVERY=0 PERIOD=40 TAP=a FROM=1625 TO=1710 \
  "$MESENCE" --testrunner "$PWD/rom/dq5.sfc" "$PWD/tools/lua/wprof.lua"
```

`SHOT_DIR` 와 롬·스크립트 경로는 절대 경로로 주세요. 상대 경로는 MesenCE 의
작업 폴더 기준으로 풀려 결과 파일이 엉뚱한 곳에 생깁니다. `work/` 는 커밋되지
않습니다.

입력은 `boot.lua` 의 환경 변수로 줍니다: `PERIOD`·`TAP`(주기적으로 누를 버튼),
`SEQ`(`버튼@프레임:길이` 목록), `MAXF`(종료 프레임), `EVERY`(스크린샷 간격, 0 이면 끔).
`PERIOD=40 TAP=a` 로 DQ5 를 켜면 이름 입력을 거쳐 1650프레임쯤 글래스트 성 왕좌의
방에서 다음 방으로 맵이 바뀝니다. 아래 예시 프레임은 이 장면 기준입니다.

| 스크립트 | 하는 일 | 추가 환경 변수 | 결과 |
| --- | --- | --- | --- |
| `wsnap.lua` | 일정 간격으로 WRAM 128KB 와 화면 저장 | `FROM`, `STEP` | `wNNNNN.bin`, `sNNNNN.png` |
| `wwatch.lua` | 지정 범위에 쓰는 PC 를 범위·PC 별로 모음 | `WATCH`(`7E00A5-7E00A7,...`), `FROM` | `wwatch.txt` |
| `wprof.lua` | 구간 동안 WRAM 쓰기를 PC 별 횟수·주소 범위로 집계 | `FROM`, `TO` | `wprof.txt` |
| `rprof.lua` | 구간 동안 ROM 데이터 읽기(명령 인출 제외)를 PC 별 집계 | `FROM`, `TO` | `rprof.txt` |
| `pcseq.lua` | 주소 범위에서 실행된 PC 를 레지스터와 함께 순서대로 기록 | `LO`, `HI`, `FROM`, `LIMIT` | `pcseq.txt` |
| `cover.lua` | 구간 동안 주소 범위에서 실행된 PC 와 그때의 M·X 플래그 | `LO`, `HI`, `FROM`, `TO` | `cover.txt` |
| `atpc.lua` | PC 가 처음 닿는 순간 WRAM 128KB·CGRAM·VRAM·화면 저장(프레임 중간 시점). `POKE` 로 값 고정 | `AT`(쉼표로 여럿), `FROM`, `POKE`(`7E075E=F0;...`) | `at_PPPPPP.bin`, `at_PPPPPP.cgram` |
| `rwatch.lua` | 지정 범위를 읽는 PC 를 범위·PC 별로 모음 | `WATCH`, `FROM` | `rwatch.txt` |
| `rprofw.lua` | 구간 동안 범위(`LO`~`HI`) 읽기를 PC 별로 집계하고, 셀 안 오프셋(주소 하위 3비트) 분포도 셈 | `LO`, `HI`, `FROM`, `TO` | `rprofw.txt` |
| `mkstate.lua` | 부팅 입력 후 `SAVEAT` 프레임에 세이브스테이트와 화면 저장 | `SAVEAT`, `STATE`(파일 이름), `TAPUNTIL` | `<STATE>`, `<STATE>.png` |
| `walk.lua` | 세이브스테이트에서 주인공을 셀 좌표 경유점으로 자동 보행, 맵 번호가 바뀔 때마다 기록. `down:90` 처럼 방향:프레임도 됨. `ROMPATCH` 로 실험용 ROM 덮어쓰기, `POKE` 로 RAM 값 고정 | `STATE`, `PRE`, `WAYPOINTS`(`x,y;down:90`), `CHANGES`, `HOLD`, `AFTER`, `MAXF`, `ROMPATCH`(`오프셋=바이트`), `POKE`, `WATCH` | `walk.txt`, `end.png` |
| `shots.lua` | 드라이버(`boot.lua`) 입력을 재생하면서 정한 프레임마다 화면 저장. 메시지 창 여러 쪽을 볼 때 | `SHOTS`(`300,420,...`) | `sNNNNN.png` |
| `seqboot.lua` | 세이브스테이트에서 `SEQ` 입력을 재생하는 드라이버 | `STATE`, `SEQ`, `MAXF`, `EVERY` | |
| `execcount.lua` | 드라이버(`boot.lua`) 입력을 재생하면서 PC 가 실행된 횟수를 맵(`$BC/$BD`)별로 셈. 매 프레임 도는 루틴인지 볼 때 | `EXEC`(`02AE55,0080B1`), `MAXF` | `exec.txt` |
| `slottrack.lua` | 드라이버 입력을 재생하면서 슬롯 인물의 셀 좌표(`7E:3020`·`3080`)가 바뀔 때마다 프레임과 함께 기록. 인물 스크립트의 걷는 길을 볼 때 | `SLOT`(16진), `MAXF` | `track.txt` |

세이브스테이트에서 시작하는 상황에 다른 프로브를 쓰려면, 드라이버를 `boot.lua` 로 둔 Lua 폴더를 만들어 `LIBDIR` 로 줍니다.

```sh
export LIBDIR=$(tools/lua/seqlib.sh "$(uv run krpatch sfc lua)" work/walklib walk.lua)
STATE=$PWD/work/state/ship.mss PRE="b:4,wait:40" WAYPOINTS="3,11;3,24;7,24;7,22" \
  SHOT_DIR=$PWD/work/x FROM=340 TO=398 MAXF=400 LO=2AE000 HI=2AFFFF \
  "$MESENCE" --testrunner "$PWD/rom/dq5.sfc" "$PWD/tools/lua/cover.lua"
```

프로브의 결과 파일은 `MAXF`(또는 `TO`) 직전에 쓰이므로, 드라이버가 먼저 멈추지 않게 `MAXF` 를 맞춥니다.

툴킷에도 같은 방식의 스크립트가 있습니다(`$LIBDIR/probe/`): 특정 PC 실행 시 레지스터
기록(`trace.lua`), 호출자 기록(`calls.lua`) 등.

## FC DQ4: 툴킷의 FC 스크립트

DQ4(FC)는 툴킷의 FC 용 Lua(`krpatch fc lua`)를 씁니다. 스크립트 목록과 환경 변수는
[툴킷 README 의 `fc lua`](https://github.com/perfectacle/kr-patch-toolkit/blob/v0.5.0/README.md#fc-lua-mesence-scripts)
가 정본입니다. 프로브에 `DRIVER=$LIBDIR/seq.lua` 를 주면 세이브스테이트에서 시작하므로
위의 `seqlib.sh` 가 필요 없습니다.

```sh
export LIBDIR=$(uv run krpatch fc lua)
tools/dq4state.sh    # work/state/dq4-ch1-throne.mss, dq4-ch1-courtyard.mss 를 롬에서 다시 만듦

# 왕좌의 방에서 걸어 나가며 맵 번호·좌표를 쓰는 명령을 모은다
mkdir -p work/wr
DRIVER=$LIBDIR/seq.lua STATE=$PWD/work/state/dq4-ch1-throne.mss SEQ="down:150,left:16,down:300" \
  TAIL=200 EVERY=0 FROM=420 MAXF=640 WATCH="0028-0028,0044-0045,8000-FFFF" SHOT_DIR=$PWD/work/wr \
  "$MESENCE" --testrunner "$PWD/rom/dq4.nes" "$LIBDIR/probe/writes.lua"

uv run krpatch fc dis rom/dq4.nes E940 8 --bank 0F    # BB:AAAA, BB 는 16KB 뱅크
```

`seq.lua` 는 마지막 입력 뒤 `TAIL` 프레임에 멈추므로, 프로브가 결과를 쓰는 `MAXF - 1` 프레임까지
가도록 `TAIL` 을 넉넉히 줍니다.

| 스크립트 | 하는 일 |
| --- | --- |
| `dq4state.sh` | 전원 켜기부터 1장 왕좌의 방, 성 밖, 필드, 첫 전투까지 단계별로 입력을 재생해 세이브스테이트를 만들고 장면마다 좌표·맵 번호를 찍음. 같은 결과가 나오도록 MesenCE 에 `--nes.ramPowerOnState=AllZeros` 를 주고, 전원을 켜는 첫 단계는 `lua/fc/debugsram.lua` 로 SRAM 을 `00` 으로 채움(MesenCE 의 `Saves/dq4.sav` 를 따르지 않게). `STATE_DIR` 로 출력 폴더. `MESENCE` 필요 |
| `dq4warp.sh OUT GG/KK [X Y [DIR]]\|field F X Y` | DQ4 장면 이동. 1장 세이브스테이트에서 게임의 출구·맵 가장자리 루틴을 타고 목적지로 옮겨 `OUT/warp.mss`(조작 가능)를 만듦. 좌표를 빼면 그 맵으로 들어오는 출구의 도착 자리. `lua/fc/warp.lua` 는 프로브의 `DRIVER` 로도 씀. [docs/dq4-warp.md](../docs/dq4-warp.md) |

## Python

저장소 최상위에서 `uv run python tools/<스크립트>` 로 실행합니다(`uv sync` 가 툴킷 v0.5.0 과 Pillow 를 설치).

표는 트랙마다 나눕니다. 자기 트랙 도구는 자기 절에만 줄을 더합니다.

### 공통

| 스크립트 | 하는 일 |
| --- | --- |
| `listing.py rom cover.txt [시작 끝]` | `cover.lua` 결과로, 실제 실행된 명령만 실행 당시 M·X 폭으로 디스어셈블 |
| `check_docs.py` | 일지 이름·제목·순번 중복, README 일지 목록, 상대 링크, 개인 경로 검사(CI `docs` 잡과 같음) |

### dq5

[sfc/dq5/tools/README.md](../sfc/dq5/tools/README.md) 에 있습니다.

### dq4

| 스크립트 | 하는 일 |
| --- | --- |
| `dq4map.py rom list\|check\|G K` | DQ4 마을·던전 맵 풀기. `list` 맵 269개, `check` 해제 경계 전수 검사, `G K --compare at.bin` 으로 `lua/fc/atpc.lua` 덤프(`$7800`)와 비교. `exits G K` 출구(`--compare end.ram` 은 `$05A0`), `npcs G K` 인물(`--compare` 는 인물 표 `$6F60`~) |
| `lua/fc/atpc.lua` | FC: PC 가 `AT` 에 닿을 때 CPU 메모리(`RANGE`, 기본 `0000-7FFF`)를 `at_PPPP_N.bin` 으로. `DRIVER` 로 입력 드라이버 |
| `dq4field.py rom check\|F\|compare lk.txt` | DQ4 필드 풀기. `F --png` 회색조 그림, `compare` 는 `lua/fc/fieldlookup.lua`(게임의 좌표 → 타일 조회 기록)와 비교, `entrances` 필드 → 마을 입구 74개 |
| `dq4data.py rom names\|items\|monsters\|spells\|levels [인물]` | DQ4 이름 목록(주문·직업·아이템·몬스터…), 아이템 종류·강도·가격·장비 인물·플래그, 몬스터 능력치·드롭, 주문 MP·대상·배우는 레벨, 인물별 레벨 1~99 경험치·능력치 기준값 |
| `lua/fc/statspoke.lua` | FC: 세이브스테이트를 불러온 뒤 `ONCEAT` 프레임에 한 번 RAM(`ONCE="60C5=E8,03,00;…"`)이나 PRG ROM(`ROMONCE`, 메모리 위만)에 쓰고 `NEXT`(기본 `seq.lua`)를 돌림. 프로브의 `DRIVER` 로 씀 |
| `lua/fc/statsstack.lua` | FC: PC 가 `AT`(쉼표로 여럿)에 닿을 때마다 뱅크·A X Y·`LOG` 주소 값·스택 `STACK` 바이트를 `stack.txt` 로 |
| `lua/fc/statsreads.lua` | FC: PRG 오프셋 `LO`-`HI` 를 읽을 때마다 읽은 명령의 PC·오프셋·A X Y(`STACK=n` 이면 스택도)를 `rd.txt` 로 |
| `dq4text.py rom all\|MSG\|controls\|windows` | DQ4 대사 풀기. `all` 은 메시지 2633개 전부, `--bytes` 글자 바이트, `MSG[,MSG…] --compare end.ram` 으로 창 줄 버퍼(`$06AA`, 전투 창이면 옆의 `end.nt`)와 비교(치환은 아무 글자와 맞춤, 자동 `＊「` 포함), `controls` 제어 바이트 처리기·뜻·쓰는 메시지 수, `windows` 창 문자열 표 `16:$A572` |
| `lua/fc/textforce.lua` | FC: 메시지 출력 `16:$8656` 진입 때 X:A 를 `MSG` 로 바꾸고 `ARGS`(`F9=01,0554=10` 꼴)로 RAM 을 써서 아무 메시지나 띄움. `FAKE`(글자 바이트)로 메시지 첫 바이트들을 바꾸고, `AT` 로 처리기 들머리에서 RAM 을 씀. 창 줄 버퍼 변화를 `buf.txt`(`BUFLEN`), 진입을 `enter.txt`, `HOOK` 주소 실행을 `hook.txt`, `DUMPEVERY` 프레임마다 RAM·nametable 을 `fNNNNN.ram/.nt` 로. `DRIVER` 로 입력 드라이버 |
| `lua/fc/textbrk.lua` | FC: BRK 뱅크 호출(`$C408`)을 모두 잡아 호출 위치마다 바이트·횟수·실제 복귀 자리를 `brk.txt`, 메시지·플래그 형식의 번호·값을 `events.txt` 로 |
| `lua/fc/textwin.lua` | FC: 창 문자열 표 항목 찍기(`16:$9783`)와 `80` 이상 바이트(`16:$97B0`, 루틴·문자열 갈래)를 `win.txt` 로 |
| `lua/fc/textfont.lua` | FC: CHR-RAM 오프셋 `PPU`(기본 `10B0-10B7`) 쓰기마다 프레임·PC·값·`$0507` 을 `font.txt` 로 |
| `dq4bank.py rom call\|table\|compare\|free\|cover` | DQ4 BRK 뱅크 호출 풀기(특수 형식 `x3`(길이 `len=`)·메시지·플래그·소리 포함). `free` 뱅크별 FF·00 연속 구간, `cover cover.txt…` 뱅크별 실행 오프셋 수. `compare trace.txt` 로 `probe/trace.lua` 기록(`TRACE=C446,C455,C3CD LOG=0023,0024,0025,0026,0027,0507`)과 비교 |
| `dq4encounter.py rom maps\|zones\|odds\|dungeons\|formations\|bosses\|check` | DQ4 적 조우 표. `maps` 필드 구역 지도(`--png` 는 `work/` 에만), `zones [Z]` 구역별 칸·몬스터, `odds Z [--night\|--dungeon]` 칸 확률, `dungeons` 던전 층별 구역, `bosses` 특수 전투, `check [enc.txt…]` 표 경계 검사와 `lua/fc/enc.lua` 기록 대조(필드·던전·그룹 3A 칸·성수·`$6BEB`·특수 전투, 기습·선제 횟수) |
| `dq4talk.py rom G K\|id N\|all\|calls\|compare DIR` | DQ4 인물 대화 스크립트 풀기. `G K` 맵의 인물마다 자리·겉모습·대화 번호·스크립트·대사(`--ram` 으로 플래그·장·시간·일행·소지품을 풀어 나올 메시지만, 이벤트 목록과 밤도 덤프대로, `--night` 은 밤 목록), `all` 낮·밤·이벤트 목록 전수 검사, `calls` 호출 문장이 부르는 루틴의 갈래, `compare` 는 `lua/fc/talk.lua` 기록(진입 슬롯·대화 번호·조건 결과·서비스·이벤트·전투·메시지)과 대조(`--no` 는 「いいえ」). `lua/fc/talk.lua` 의 `SLOT`(여럿 가능)으로 아무 인물에게나, `TID` 로 아무 대화 번호나 돌리고 `SET` 으로 첫 말 걸기 전에 RAM 을 씀. `lua/fc/talkseek.lua` 는 인물에게 걸어가 말 거는 입력 드라이버 |
| `lua/fc/enc.lua` | FC: 필드·맵 안에서 시행마다 세이브스테이트를 다시 불러 기다림을 바꿔 걷고, 걸음·조우 판정(조우율·난수)·고른 무리·`$6E44`·메시지 번호를 `enc.txt` 로. `STATE`, `TRIALS`, `WAIT0`, `WAITSTEP`, `POS`(필드 좌표 한 번 쓰기), `POKE1`, `LIMIT`, `WALK=random`(네 방향), `CONT`(전투 뒤 더 돌며 메시지), `FORCE44`, `BOSS=NN`(메모리상 PRG 를 덮어 특수 전투 NN), `SHOT` |
| `dq4block.py rom defs T\|G K\|field F\|props\|compare DIR\|effects G K\|tables\|json [OUT]` | DQ4 맵 블록 → 타일 4개·팔레트·통행 속성. `defs T` 맵 종류 T 의 블록 정의·애니메이션·낮 팔레트, `props [--maps]` 롬 전체 맵·필드의 속성 값별 뜻·맵 수, `G K` 통행 지도(`--nt` nametable 타일 번호, `--png` 는 `work/` 에만), `compare DIR [PREFIX]` 은 `seq.lua`·`warp.lua` 의 `end.*`(또는 `blockload.lua` 덤프)와 블록 표·CHR·팔레트·`$7800`·화면 nametable 비교. `effects G K` 맵의 속성 값마다 지형 효과·떨어지는 칸 목적지, `tables` 속성 값마다 `terrain()` 과 떨어지기·리프트·タンス/つぼ·팻말 표, `json` 맵·필드 전부의 속성·칸·표를 `work/dq4block.json` 으로 |
| `dq4shop.py rom [G K\|people]` | DQ4 무기·방어구·도구 가게 목록 전부와 여관 1인 값. `G K` 는 그 장소의 목록·여관·가게 인물(스크립트·호출로 여는 가게 포함), `--compare end.ram [end.sram]` 으로 가게 창 목록 `$07BD` 와 비교(SRAM 을 주면 덧붙임까지). `people` 은 롬 전체의 「인물 → 가게(종류·품목·여관 값)」 표 |
| `dq4chest.py rom G K\|all\|check` | DQ4 보물상자(칸·내용물·열었음 플래그 `$625D`~)와 발밑 숨은 물건(특수 내용 설명 포함). `check` 맵마다(마지막 그룹 `48` 포함) 상자 칸 수와 개수 표 비교, `G K --compare end.sram` 으로 열었음 비트 |
| `lua/fc/blockload.lua` | FC: PRG 오프셋 `AT`(쉼표로 여럿)의 명령이 실행될 때 CPU 메모리·CHR-RAM·nametable·팔레트를 `ld_OOOOO_N.*` 로(`LIMIT` 번). `DRIVER` 로 입력 드라이버 |
| `lua/fc/blockreads.lua` | FC: CPU 메모리 `RANGE`(예 `6F20-6F5F`)를 읽는 명령을 PC 마다 모아 `ramreads.txt` 로(`MAXF`, `FROM`) |
| `lua/fc/shopwalk.lua` | FC: 맵 좌표 `$44/$45` 를 보며 `WAY`(`"12,1C 0D,1C"`) 칸들로 걷고 `end.mss` 등 덤프. `STATE`, `TAIL`, `MAXF` |
| `lua/fc/shopcall.lua` | FC: PC 가 `AT`(쉼표로 여럿)에 닿을 때 A·X·Y·복귀 주소·`($X)` 포인터·`$0507` 을 `calls.txt` 로. `ONLYA`, `LIMIT`, `MAXF`, `DRIVER` |
| `lua/fc/shoppoke.lua` | FC: PC 가 `AT` 에 닿을 때 `POKE`(`3D=03;…`)를 RAM 에 씀. `BANK`(`$0507` 일치 때만), `ONCE`, `DRIVER` |
| `lua/fc/shopreads.lua` | FC: `RANGE`(기본 `6000-62FF`)를 읽는 명령을 「뱅크:PC 주소 값 횟수 첫프레임」으로 `reads.txt` 에. `FROM`, `BANK`, `PCLO`/`PCHI`, `MAXF`, `DRIVER` |
| `lua/fc/shopprg.lua` | FC: 첫 프레임에 메모리의 PRG ROM 을 `PRG`(`55CCA=4CF4BE;…`, PRG 오프셋)대로 바꿈(롬 파일은 그대로). `DRIVER` |
| `dq4event.py rom sram\|flags\|chapters\|chars\|places\|events\|ops` | DQ4 저장 데이터. `sram end.sram` 작업 영역·모험의 서 3칸(CRC 검사)·인물 레코드, `flags` 이벤트 플래그 영역, `flags --xref [NN]` 플래그 비트마다 쓰는 곳·검사하는 곳(BRK·절대 주소·대화 스크립트·인물 블록·맵 인물 목록 표), `chapters` 1~5장 시작 표, `chars [--compare end.sram]` 장 시작 인물 레코드, `places` 귀환 자리 표와 ルーラ 행선지, `events` 인물 블록의 이벤트 명령과 맵 이벤트 표, `ops [--flag NN]` 롬의 BRK 플래그 명령 모양 |
| `lua/fc/eventwalk.lua` | FC: 세이브스테이트에서 좌표 목표(`x=NN`/`y=NN`)와 버튼으로 걷고 `reset:1` 로 리셋. `POKEAT` 프레임별 RAM 쓰기, `PRGPOKE` 메모리의 PRG ROM 바꾸기(롬 파일은 그대로). 프로브의 `DRIVER` 로도 씀. 끝나면 `walk.txt`·`end.*` |
| `lua/fc/eventflags.lua` | FC: 이벤트 플래그 영역(`$627B`~`$62EE`, `RANGE`) 읽기·쓰기를 PC·뱅크·BRK 주소와 함께 `flags.txt` 로. `FROM`, `MAXF` |
| `dq4graphics.py [--check] [--output 폴더]` | 롬 없이 스프라이트·블록·샘플 맵·타이틀을 PNG·SFC 4bpp·팔레트로 출력. `--check` 는 파일을 쓰지 않고 반복 생성·왕복 검사 |
| `dq4pixels.py` | 스프라이트·지형 제작물을 모으는 모듈 |
| `dq4sprites.py` | DQ4 인물 9명의 16×24 스프라이트 원본. 인물별 팔레트와 색 번호 문자 행렬(방향마다 정지 자세, 보행은 몸만 바꿈). 실행하면 색 수와 행 폭 검사 |
| `dq4spritelab.py hero\|data 이름\|compare 이름` | `hero` 는 `lua/dq4objdump.lua` 덤프에서 DQ5 주인공 4방향을 16×24 로 복원(`work/dq4-sprites/dq5-hero.png`), `data` 는 `lua/dq4sprite.lua` 용 4bpp·팔레트 Lua, `compare` 는 원작과 같은 배경·8배로 나란히. [docs/dq4-sprite-format.md](../docs/dq4-sprite-format.md) |
| `lua/dq4objdump.lua` | SFC: 필드 세이브스테이트(`STATE`)에서 4방향으로 걷다 멈춘 VRAM·OAM·CGRAM 과 주인공을 숨긴 화면을 `OUT` 에 덤프 |
| `lua/dq4sprite.lua` | SFC: 필드 `01/00` 에서 주인공 OBJ 를 `DATA` 의 스프라이트로 프레임마다 바꿔 보여 줌(VRAM `D000`·OAM 0~5·팔레트 3). `STATE`, `OUT`, `TEST=1` 이면 4방향 자동 보행 후 `walk-test.txt`. 영구 삽입 아님 |
| `dq4terrain.py` | 성·마을 블록 49종과 이름 격자 맵의 편집 원본 |
| `dq4title.py` | 보관한 생성 원본을 256×224, 타일별 8개 BG 팔레트 타이틀로 변환하는 모듈 |
| `dq4figures.py` | 제작 원본으로 그래픽 문서의 WebP·합성 보행 애니메이션 재생성(롬 불필요) |
| `dq4debug.py rom unrun\|find\|brk COVER...` | DQ4 미실행 코드 찾기. `cover.lua` 기록 여러 개를 합쳐 실행된 명령에서 닿는데 안 돈 코드 덩어리(`unrun`), 패드 2·`$4017`·디버그 스위치 `$C000` 읽기(`find`), 부르는 곳 없는 BRK 함수(`brk`). [docs/dq4-debug.md](../docs/dq4-debug.md) |
| `lua/fc/debugpad.lua` | FC: 입력 드라이버 앞에 끼워 PRG 롬 메모리를 덮어쓰고(`ROMPATCH`, 예: `3C000=7F;7C000=7F`), 패드 2 를 흉내 내고(`PAD2`, `$15` 값), 바뀐 RAM 을 프레임마다 `debugpad.txt` 로(`LOGW`). 다른 프로브의 `DRIVER` 로 쓸 때는 `PAD_DRIVER` |
| `lua/fc/debugreads.lua` | FC: 디버그 스위치 `$C000`(PRG `3C000`·`7C000`)을 읽는 명령을 모아 `debugreads.txt`(PRG 오프셋, 주소, 횟수, 첫 프레임). `DRIVER`, `MAXF` |
| `lua/fc/debugtrap.lua` | FC: PRG 롬 오프셋(`TRAP`, 예: `401B9`)의 명령이 실행될 때만 프레임·레지스터·`LOG` 주소·스택을 `debugtrap.txt` 로(다른 뱅크의 같은 CPU 주소는 거름). 처음 걸린 뒤 `SHOTS_AFTER` 프레임마다 화면 4장. 드라이버는 `TRAP_DRIVER` |
| `lua/fc/debugsram.lua` | FC: 전원을 켜기 전에 SRAM 8KB 를 `00`(또는 `SRAM` 파일)으로 채우고 `SRAM_DRIVER`(없으면 `DRIVER`)를 돌림. 테스트러너가 불러오는 `Saves/<롬 이름>.sav` 와 상관없이 같은 결과를 내려고 씀 |

스프라이트·맵 출력은 채택되지 않은 초기 시안입니다. 타이틀·일러스트만 보존 대상으로 평가됐으며, 후속 작업은 [그래픽 핸드오프](../docs/dq4-graphics-handoff.md)를 먼저 읽습니다. 그래픽 출력의 배치·제약은 [dq4-graphics.md](../docs/dq4-graphics.md)에 있습니다. 생성 원본과 프롬프트는 `tools/dq4art/` 에 보관합니다. `uv run --locked python tools/dq4graphics.py` 로 기본 출력 `work/dq4-graphics/` 를 만들고, `uv run --locked python tools/dq4figures.py` 로 문서 그림을 다시 만듭니다.
