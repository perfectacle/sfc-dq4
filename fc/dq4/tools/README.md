# dq4 도구: FC 원작 분석

저장소 최상위에서 `uv run --locked python fc/dq4/tools/<스크립트>` 로 실행합니다. 롬은 첫 인자로 줍니다(`rom/dq4.nes`). 모듈끼리는 같은 폴더에서 import 합니다. 셸 스크립트도 저장소 최상위에서 `fc/dq4/tools/dq4warp.sh …` 로 실행하고, MesenCE 프로브(`lua/`)는 `"$PWD/fc/dq4/tools/lua/<스크립트>"` 로 줍니다. 포팅용 그래픽 도구는 [sfc/dq4/tools/README.md](../../../sfc/dq4/tools/README.md) 에 있습니다.

## MesenCE: 툴킷의 FC 스크립트

DQ4(FC)는 툴킷의 FC 용 Lua(`krpatch fc lua`)를 씁니다. 스크립트 목록과 환경 변수는
[툴킷 README 의 `fc lua`](https://github.com/perfectacle/kr-patch-toolkit/blob/v0.5.0/README.md#fc-lua-mesence-scripts)
가 정본입니다. 프로브에 `DRIVER=$LIBDIR/seq.lua` 를 주면 세이브스테이트에서 시작하므로
[공통 도구](../../../tools/README.md) 의 `seqlib.sh` 가 필요 없습니다.

```sh
export LIBDIR=$(uv run krpatch fc lua)
fc/dq4/tools/dq4state.sh    # work/state/dq4-ch1-throne.mss, dq4-ch1-courtyard.mss 를 롬에서 다시 만듦

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
| `dq4state.sh` | 전원 켜기부터 1장 왕좌의 방, 성 밖, 필드, 첫 전투까지 단계별로 입력을 재생해 세이브스테이트를 만들고 장면마다 좌표·맵 번호를 찍음. 같은 결과가 나오도록 MesenCE 에 `--nes.ramPowerOnState=AllZeros` 를 주고, 전원을 켜는 첫 단계는 `lua/debugsram.lua` 로 SRAM 을 `00` 으로 채움(MesenCE 의 `Saves/dq4.sav` 를 따르지 않게). `STATE_DIR` 로 출력 폴더. `MESENCE` 필요 |
| `dq4warp.sh OUT GG/KK [X Y [DIR]]\|field F X Y` | DQ4 장면 이동. 1장 세이브스테이트에서 게임의 출구·맵 가장자리 루틴을 타고 목적지로 옮겨 `OUT/warp.mss`(조작 가능)를 만듦. 좌표를 빼면 그 맵으로 들어오는 출구의 도착 자리. `lua/warp.lua` 는 프로브의 `DRIVER` 로도 씀. `STATE` 는 상대 경로(워크트리 기준)도 되고, 앞 실행의 `end.mss` 에서 이어 갈 수 있음. [fc/dq4/docs/dq4-warp.md](../docs/dq4-warp.md) |

## Python과 프로브

| 스크립트 | 하는 일 |
| --- | --- |
| `dq4map.py rom list\|check\|G K` | DQ4 마을·던전 맵 풀기. `list` 맵 269개, `check` 해제 경계 전수 검사, `G K --compare at.bin` 으로 `lua/atpc.lua` 덤프(`$7800`)와 비교. `exits G K` 출구(`--compare end.ram` 은 `$05A0`), `npcs G K` 인물(진행 플래그로 고른 목록. `--ram`·`--set` 으로 플래그, `--compare` 는 인물 표 `$6F60`~, 덤프 파일이나 `end.*` 폴더), `lists [G K]` 진행 목록 표 `1C:$9D0E` |
| `lua/atpc.lua` | FC: PC 가 `AT` 에 닿을 때 CPU 메모리(`RANGE`, 기본 `0000-7FFF`)를 `at_PPPP_N.bin` 으로. `DRIVER` 로 입력 드라이버 |
| `dq4field.py rom check\|F\|compare lk.txt\|entrances\|places` | DQ4 필드 풀기. 게임의 `0F:$D259` 를 그대로 따라 가장자리 +2 칸까지 풂(필드 0·1·3, 2 는 쓰이지 않음). `F --png` 회색조 그림, `compare` 는 `lua/fieldlookup.lua`(게임의 좌표 → 타일 조회 기록)와 비교, `entrances` 필드 → 마을 입구 74개, `places` ルーラ 목적지 레코드 32개와 장소 이름·그룹 |
| `dq4data.py rom names\|items\|monsters\|spells\|levels [인물]\|actions\|ai` | DQ4 이름 목록(주문·직업·아이템·몬스터…), 아이템 종류·강도·가격·장비 인물·플래그·전투 사용 행동, 몬스터 능력치·드롭·행동 ID·행동 수·AI·HP 재생·회심·시작 상태·내성, 주문 MP·대상·배우는 레벨, 인물별 레벨 1~99 경험치·능력치 기준값, 전투 행동 ID 256개의 처리 루틴·위력·양·성공률, 몬스터 행동 가중치와 동료 AI 의 인물별 주문 칸 |
| `lua/statspoke.lua` | FC: 세이브스테이트를 불러온 뒤 `ONCEAT` 프레임에 한 번 RAM(`ONCE="60C5=E8,03,00;…"`)이나 PRG ROM(`ROMONCE`, 메모리 위만)에 쓰고 `NEXT`(기본 `seq.lua`)를 돌림. 프로브의 `DRIVER` 로 씀 |
| `lua/statsstack.lua` | FC: PC 가 `AT`(쉼표로 여럿)에 닿을 때마다 뱅크·A X Y·`LOG` 주소 값·스택 `STACK` 바이트를 `stack.txt` 로 |
| `lua/statsram.lua` | FC: CPU 주소 `LO`-`HI`(RAM)를 읽는(`KIND=write` 면 쓰는) 명령을 명령 주소·뱅크·주소마다 묶어 횟수·처음 프레임·값을 `ram.txt` 에. 전투 상태 바이트를 읽는 곳 찾기에 씀 |
| `lua/statsreads.lua` | FC: PRG 오프셋 `LO`-`HI` 를 읽을 때마다 읽은 명령의 PC·오프셋·A X Y(`STACK=n` 이면 스택도)를 `rd.txt` 로 |
| `lua/statspc.lua` | FC: PC 가 `PCPOKE`(`주소[@뱅크]:주소=바이트들;…`)의 주소에 닿을 때 RAM 에 쓰고 `PCNEXT`(기본 `seq.lua`)를 돌림. 전투 시작 `18:$A11A` 에서 무리 바꾸기, 몬스터 행동 ID 바꾸기에 씀 |
| `dq4text.py rom all\|MSG\|controls\|windows\|export` | DQ4 대사 풀기. `all` 은 메시지 2633개 전부, `--bytes` 글자 바이트, `MSG[,MSG…] --compare end.ram` 으로 창 줄 버퍼(`$06AA`, 전투 창이면 옆의 `end.nt`)와 비교(치환은 아무 글자와 맞춤, 자동 `＊「` 포함), `controls` 제어 바이트 처리기·뜻·쓰는 메시지 수, `windows` 창 문자열 표 `16:$A572`, `windows --layout` 창 레코드 115개(자리·폭·열·본문·여는 BRK 자리, `--meaning` 이면 갈래마다 뜻), `windows --items` 본문 바이트 뜻 표(루틴 항목·항목 루틴 `80`~`9F`·목록 `Dn`·`C1`·자리 루틴), `windows --trace item.txt…` `textitem.lua` 기록을 창 열기마다 한 줄로, `windows --compare DIR…` `textlayout.lua` 결과의 nametable 틀과 레코드 견주기, `export [DIR]` 메시지·창 문자열·이름 목록·창 레코드를 기호 텍스트 JSON·TSV 로 `work/text/` 에(커밋 금지), `export --check` 기호 → 바이트 왕복과 부호 → 롬 비트열 검사 |
| `lua/textforce.lua` | FC: 메시지 출력 `16:$8656` 진입 때 X:A 를 `MSG` 로 바꾸고 `ARGS`(`F9=01,0554=10` 꼴)로 RAM 을 써서 아무 메시지나 띄움. `FAKE`(글자 바이트)로 메시지 첫 바이트들을 바꾸고, `AT` 로 처리기 들머리에서 RAM 을 씀. 창 줄 버퍼 변화를 `buf.txt`(`BUFLEN`), 진입을 `enter.txt`, `HOOK` 주소 실행을 `hook.txt`, `DUMPEVERY` 프레임마다 RAM·nametable 을 `fNNNNN.ram/.nt` 로. `DRIVER` 로 입력 드라이버 |
| `lua/textbrk.lua` | FC: BRK 뱅크 호출(`$C408`)을 모두 잡아 호출 위치마다 바이트·횟수·실제 복귀 자리를 `brk.txt`, 메시지·플래그 형식의 번호·값을 `events.txt` 로 |
| `lua/textlayout.lua` | FC: 창 열기 `16:$8A03` 마다 `$F5`~`$F8`·스크롤·스택·레코드 주소를 `open.txt` 로, 열기 뒤 nametable 쓰기의 처음·마지막 값을 `ppu.txt` 로, 열 때 nametable 을 `oNN.nt` 로. `WIN`(`F7`·`F8`)으로 첫 열기의 창 번호를 바꿈 |
| `lua/textitem.lua` | FC: 창 본문을 그리는 동안 항목(`16:$9783`·`$97D5`), 항목 루틴(`16:$96E4`, 돌아온 뒤 줄 수·`$07B0`), 목록·`C1`·자리 루틴·`E0`~`FF`, 줄 버퍼에 넣은 글자(`16:$981C`·`$983F`)를 `item.txt` 로. `WIN`(`F7`)으로 첫 열기의 창 번호를 바꿈 |
| `lua/textwin.lua` | FC: 창 문자열 표 항목 찍기(`16:$9783`)와 `80` 이상 바이트(`16:$97B0`, 루틴·문자열 갈래)를 `win.txt` 로 |
| `lua/textfont.lua` | FC: CHR-RAM 오프셋 `PPU`(기본 `10B0-10B7`) 쓰기마다 프레임·PC·값·`$0507` 을 `font.txt` 로 |
| `lua/textmodoki.lua` | FC: 전투 행동 분기 `11:$8C85` 의 행동 번호를 기록하고 `FORCE` 로 바꿈. 몬스터 칸 레코드(`RANGE`, 기본 `7274-72FF`) 쓰기, `HOOK`(뱅크 `11` 주소) 실행, 메시지 진입을 `modoki.txt` 로 |
| `lua/textx3.lua` | FC: 정한 PRG 오프셋이 실행될 때 레지스터를 바꾸고(`REGS`), 메모리 위 PRG 바이트를 바꾼 뒤(`PRGPOKE`) 다른 프로브(`THEN`, 기본 `textbrk.lua`)를 돌림. 드문 갈래의 BRK 복귀, 창 레코드 바이트 하나의 효과 확인용. 바꾼 순간은 `regs.txt` |
| `dq4bank.py rom call\|table\|compare\|free\|cover` | DQ4 BRK 뱅크 호출 풀기(특수 형식 `x3`(길이 `len=`)·메시지·플래그·소리 포함). `free` 뱅크별 FF·00 연속 구간, `cover cover.txt…` 뱅크별 실행 오프셋 수. `compare trace.txt` 로 `probe/trace.lua` 기록(`TRACE=C446,C455,C3CD LOG=0023,0024,0025,0026,0027,0507`)과 비교 |
| `dq4encounter.py rom maps\|zones\|odds\|dungeons\|formations\|bosses\|henge\|scripts\|check` | DQ4 적 조우 표. `maps` 필드 구역 지도(`--png` 는 `work/` 에만), `zones [Z]` 구역별 칸·몬스터, `odds Z [--night\|--dungeon]` 칸 확률, `dungeons` 던전 층별 구역, `bosses` 특수 전투와 부르는 곳(상자·デスパレス 표 포함), `henge` へんげのつえ 모습 표 `1E:$B079`(칸·그림 번호·`$6297`·그 그림을 쓰는 맵 수), `scripts` 맵·이벤트 목록의 인물 블록을 `dq4npcblock` 으로 풀어 명령 21(특수 전투) 찾기, `check [enc.txt…]` 표 경계 검사와 `lua/enc.lua` 기록 대조(필드·던전·그룹 3A 칸·성수·`$6BEB`·특수 전투, 기습·선제 횟수) |
| `dq4talk.py rom G K\|id N\|all\|calls\|events\|looks\|compare DIR` | DQ4 인물 대화 스크립트 풀기. `G K` 맵의 인물마다 자리·겉모습·대화 번호·스크립트·대사(`--ram` 으로 플래그·장·시간·일행·소지품을 풀어 나올 메시지만, 이벤트 목록과 밤도 덤프대로, `--night` 은 밤 목록), `all` 낮·밤·이벤트 목록 전수 검사, `calls` 호출 문장이 부르는 루틴의 갈래, `events [--compare DIR…]` 이벤트 표 `1C:$BF74` 50개의 전투·플래그·메시지·장소·부르는 곳(`EV` 실행 기록과 대조), `looks` 그림 번호마다 쓰는 인물, `compare` 는 `lua/talk.lua` 기록(진입 슬롯·대화 번호·조건 결과·서비스·이벤트·전투·메시지)과 대조(`--no` 는 「いいえ」). `lua/talk.lua` 의 `SLOT`(여럿 가능)으로 아무 인물에게나, `TID` 로 아무 대화 번호나, `EV` 로 아무 이벤트나 돌리고 `SET` 으로 첫 말 걸기 전에 RAM 을 씀. `lua/talkseek.lua` 는 인물에게 걸어가 말 거는 입력 드라이버, `lua/talkreads.lua` 는 대화 번호를 꺼내는 `1C:$96C7` 이 `$64` 를 바꿔 둔 동안 읽힌 RAM 주소(`ADDRS`)와 PC 를 남기는 프로브. `lua/talkwin.lua` 는 `talk.lua`(`TALK` 에 절대 경로)를 감싸 `WIN=1` 이면 특수 전투에서 적 HP 를 1·수비력을 0 으로 낮추고 일행 HP 를 채워 이기게 하고, 자동 입력 `$0530`~`$0533`(`auto.txt`)·`EVADDR` 진입(`extra.txt`)을 남기며 `PRGPOKE` 로 PRG 를 메모리에서만 바꿈 |
| `lua/enc.lua` | FC: 필드·맵 안에서 시행마다 세이브스테이트를 다시 불러 기다림을 바꿔 걷고, 걸음·조우 판정(조우율·난수)·고른 무리·`$6E44`·메시지 번호를 `enc.txt` 로. `STATE`, `TRIALS`, `WAIT0`, `WAITSTEP`, `POS`(필드 좌표 한 번 쓰기), `POKE1`, `LIMIT`, `WALK=random`(네 방향), `CONT`(전투 뒤 더 돌며 메시지), `FORCE44`, `BOSS=NN`(메모리상 PRG 를 덮어 특수 전투 NN), `PRE`(먼저 누를 방향), `ROUTE`(필드 좌표를 차례로 맞춰 걷기), `POKE`(프레임마다 쓰기), `PRG`(메모리상 PRG 바꾸기), `SHOT`. 배 위 `$07` 을 쓴 곳·특수 전투 복귀 주소도 적음 |
| `lua/encwatch.lua` | FC: `DRIVER`(`warp.lua`·`seq.lua`·`enc.lua`)와 함께 돌며 특수 전투 진입(`18:$A1AD` A), デスパレス 대화(`15:$B10E`·`08:$B752`), へんげのつえ(`1E:$B02F`, `$6296`·`$6297` 쓰기), `$6E44` 쓰기·읽기, `1E:$A5AD`·`$A3BA`·`$A1C9`, 메시지를 `encwatch.txt` 로. `POKE`/`POKE1`/`POKEFROM`, `POKE44`(`18:$A123` 에서 `$6E44` 바꾸기), `ROUTE`(맵 좌표 `$44`/`$45` 를 차례로 맞춰 걷기, 막히면 B), `RD44`, `MAXF` |
| `dq4block.py rom defs T\|G K\|field F\|props\|compare DIR\|effects G K\|tables\|links [G K]\|json [OUT]` | DQ4 맵 블록 → 타일 4개·팔레트·통행 속성. `defs T` 맵 종류 T 의 블록 정의·애니메이션·낮 팔레트, `props [--maps]` 롬 전체 맵·필드의 속성 값별 뜻·맵 수, `G K` 통행 지도(`--nt` nametable 타일 번호, `--png` 는 `work/` 에만), `compare DIR [PREFIX]` 은 `seq.lua`·`warp.lua` 의 `end.*`(또는 `blockload.lua` 덤프)와 블록 표·CHR·팔레트·`$7800`·화면 nametable 비교. `effects G K` 맵의 속성 값마다 지형 효과·떨어지는 칸 목적지, `tables` 속성 값마다 `terrain()` 과 떨어지기·리프트(사각형 포함)·タンス/つぼ·팻말 표, `links [G K]` 계단·旅の扉 등 출구 칸마다 목적지(`08:$B22E`, 레코드가 모자란 칸은 게임이 읽는 없는 맵까지), `json` 맵 279개·필드 전부의 속성·칸·출구 연결·표를 `work/dq4block.json` 으로 |
| `dq4fcgfx.py rom all\|maps\|field\|gfx OUT`, `scenes OUT SPEC.json`(항목에 `ppulog`·`mirror` 면 줄 스크롤), `verify DIR…` | DQ4 원작 그림 뽑기: 맵 279개(낮·밤, 인물·출구·상자·문·계단·떨어지는 칸·리프트·タンス·팻말 주석판), 필드 3개(입구 주석판), 맵 종류별 블록 시트, CHR 뱅크 `0C`·`0D`, 폰트, `lua/fcgfxscene.lua` 덤프 장면(장 제목·엔딩 포함, 있는 목록에 더함), 갤러리 HTML. 장소 이름은 ルーラ 목적지 표·대사·맵 연결에서. 성문 연출 중 화면도 그림. 출력은 커밋하지 않음(비공개 에셋 저장소). `verify` 는 스프라이트를 끈 MesenCE 화면과 롬만으로 그린 화면을 픽셀로 비교(필드·폭포는 팔레트 순환 6단계 중 맞는 것). [fc/dq4/docs/dq4-fcgfx.md](../docs/dq4-fcgfx.md) |
| `lua/fcgfxpal.lua` | FC: NES 색 번호 `00`~`3F` 마다 화면 전체를 그 색으로 칠해 `pal-XX.png` 로(MesenCE 색 재기). `STATE` |
| `lua/fcgfxscene.lua` | FC: `AT` 프레임마다 화면과 nametable·CHR·팔레트·OAM·RAM·`$2000` 값을 `fNNNNN.*` 로. 입력은 `DRIVER`(전원부터는 `debugsram.lua` 의 `SRAM_DRIVER`) |
| `lua/fcgfxscroll.lua` | FC: `LOG` 프레임의 `$2000`·`$2001`·`$2005`·`$2006` 쓰기(`CHRLOG` 면 CHR 쪽 `$2007` 쓰기)를 scanline·cycle·pc 와 함께 `ppulog.txt`·`chrlog.txt` 로, `AT` 덤프는 `fcgfxscene.lua` 와 같음. `dq4fcgfx.py scenes` 의 줄 스크롤 입력 |
| `lua/fcgfxrula.lua` | FC: ルーラ·キメラのつばさ 목록 순번 `$76` 을 `PICK` 으로 바꿔 `1E:$AE19` 에 원하는 목적지를 넣고, 레코드를 쓴 뒤 RAM 을 `fcgfxrula.txt` 로 |
| `dq4shop.py rom [G K\|people\|hidden]` | DQ4 무기·방어구·도구 가게 목록 전부(장소별 값 `15:$B2F7`: 메달·코인 포함)와 여관 1인 값. `G K` 는 그 장소의 목록·여관·가게 인물(스크립트·호출로 여는 가게 포함), `--compare end.ram [end.sram]` 으로 가게 창 목록 `$07BD` 와 비교(SRAM 을 주면 덧붙임까지). `people` 은 롬 전체의 「인물 → 가게(종류·품목·여관 값)」 표와 들어갈 때 숨거나 옮겨지는 조건. `hidden [--json]` 은 맵에 들어갈 때 장소 루틴(`1C:$A010`·`$AD32`)이 인물마다 숨기거나 옮기는 조건 전부(루틴을 기호로 돌려 원자의 곱의 합으로 줄이고, 장 ⇔ `$6282`·한 곳에서만 켜는 장면 플래그 ⇒ 장 의 진행 관계로 나올 수 없는 조합을 거름. `--raw` 면 거르지 않음), `hidden G K --compare DIR` 은 `seq.lua`·`warp.lua` 덤프 폴더나 `lua/atpc.lua` 의 `at_*.bin`(`AT=9EB4`)의 (80,80) 슬롯과, 옮김·방향·간격·상태·그림 열을 예측과 비교 |
| `dq4chest.py rom G K\|all\|check\|loot` | DQ4 보물상자(칸·내용물·열었음 플래그 `$625D`~)와 발밑 숨은 물건(특수 내용 설명 포함). `check` 맵마다(마지막 그룹 `48` 포함) 상자 칸 수와 개수 표 비교, `G K --compare end.sram` 으로 열었음 비트. `loot [--json]` 은 상자·발밑·タンス·つぼ·대화로 받는 물건을 합친 「맵·자리 → 얻는 것·플래그」 롬 전체 표 |
| `lua/blockload.lua` | FC: PRG 오프셋 `AT`(쉼표로 여럿)의 명령이 실행될 때 CPU 메모리·CHR-RAM·nametable·팔레트를 `ld_OOOOO_N.*` 로(`LIMIT` 번). `DRIVER` 로 입력 드라이버 |
| `lua/blockreads.lua` | FC: CPU 메모리 `RANGE`(예 `6F20-6F5F`)를 읽는 명령을 PC 마다 모아 `ramreads.txt` 로(`MAXF`, `FROM`) |
| `lua/blockwrites.lua` | FC: `eventwalk.lua` 를 돌리며(`EVENTWALK` 에 그 경로) CPU 메모리 `RANGE` 에 쓰는 명령을 PC 마다 `wlog.txt` 로, PRG 오프셋 `TR` 의 실행을 프레임·A·복귀 주소와 함께 `tr.txt` 로. 저장·리셋·불러오기에 걸친 쓰기를 찾는 데 씀 |
| `lua/shopwalk.lua` | FC: 맵 좌표 `$44/$45` 를 보며 `WAY`(`"12,1C 0D,1C"`) 칸들로 걷고 `end.mss` 등 덤프. `STATE`, `TAIL`, `MAXF` |
| `lua/shopcall.lua` | FC: PC 가 `AT`(쉼표로 여럿)에 닿을 때 A·X·Y·복귀 주소·`($X)` 포인터·`$0507` 을 `calls.txt` 로. `ONLYA`, `LIMIT`, `MAXF`, `DRIVER` |
| `lua/shoppoke.lua` | FC: PC 가 `AT` 에 닿을 때 `POKE`(`3D=03;…`)를 RAM 에 씀. `BANK`(`$0507` 일치 때만), `ONCE`, `DRIVER` |
| `lua/shopreads.lua` | FC: `RANGE`(기본 `6000-62FF`)를 읽는 명령을 「뱅크:PC 주소 값 횟수 첫프레임」으로 `reads.txt` 에. `FROM`, `BANK`, `PCLO`/`PCHI`, `MAXF`, `DRIVER` |
| `lua/shopprg.lua` | FC: 첫 프레임에 메모리의 PRG ROM 을 `PRG`(`55CCA=4CF4BE;…`, PRG 오프셋)대로 바꿈(롬 파일은 그대로). `DRIVER` |
| `lua/shopprice.lua` | FC: 가격 함수 `15:$B2F7` 에 들어갈 때의 아이템과 나올 때의 값을 「프레임 장소 아이템 값」으로 `price.txt` 에. `MAXF`, `DRIVER` |
| `dq4event.py rom sram\|flags\|chapters\|chars\|places\|events\|ending\|ops` | DQ4 저장 데이터. `sram end.sram` 작업 영역·모험의 서 3칸(CRC 검사)·인물 레코드, `flags` 이벤트 플래그 영역, `flags --xref [NN]` 플래그 비트마다 쓰는 곳·검사하는 곳(BRK·절대 주소·대화 스크립트·인물 블록·맵 인물 목록 표), `flags --meaning` 한 비트 플래그마다 뜻([확인]·[추정], 장소 이름과 대사 첫 줄), `chapters` 1~5장 시작 표, `chars [--compare end.sram]` 장 시작 인물 레코드, `places` 귀환 자리 표와 ルーラ 행선지, `events` 인물 블록의 이벤트 명령과 맵 이벤트 표, `ending` 5장 끝의 엔딩 장면 목록, `ops [--flag NN]` 롬의 BRK 플래그 명령 모양 |
| `dq4npcblock.py rom G K\|alt\|check\|stats\|patterns\|trace FILE` | DQ4 인물 블록(움직임·자동 이벤트 스크립트) 디코더. `G K` 맵 인물마다 블록1·2 를 명령 단위로, `alt` 이벤트 목록, `check` 롬 전체(못 읽은 명령·넘친 명령·점프 대상), `stats` 명령마다 쓰인 수, `patterns` 명령 22 의 일행 움직임 패턴, `trace` 는 `lua/npcblock.lua` 기록(슬롯마다 실행한 명령 주소·자리, `DRIVER` 로 `warp.lua` 도 씀)과 대조 |
| `dq4story.py rom events\|jobs READY OUT\|run JOBS RUNS [-j N]\|confirm RUNS... [--json OUT]\|story [N]` | DQ4 이야기 진행. `events` 블록 이벤트 루틴 138개가 보는 것·하는 것, `jobs` [추정] 플래그를 켜는 곳마다 실험 시나리오, `run` 시나리오를 MesenCE 로(`MESENCE`·`LIBDIR`), `confirm` 실행 기록에서 비트마다 켜고 끈 장면, `story` 장마다 진행 순서 → 플래그. 뜻 표는 `dq4flags.py`. [dq4-story-format.md](../docs/dq4-story-format.md) |
| `lua/eventwalk.lua` | FC: 세이브스테이트에서 좌표 목표(`x=NN`/`y=NN`)와 버튼으로 걷고 `reset:1` 로 리셋. `POKEAT` 프레임별 RAM 쓰기, `PRGPOKE` 메모리의 PRG ROM 바꾸기(롬 파일은 그대로). 프로브의 `DRIVER` 로도 씀. 끝나면 `walk.txt`·`end.*` |
| `lua/eventflags.lua` | FC: 이벤트 플래그 영역(`$627B`~`$62EE`, `RANGE`) 읽기·쓰기를 PC·뱅크·BRK 주소와 함께 `flags.txt` 로. `FROM`, `MAXF` |
| `lua/flagsweep.lua` | FC: 플래그 영역·일행 자리·`$618E` 쓰기(쓴 PC, BRK 자리, 블록 슬롯)와 메시지·대화 번호·이벤트·전투·맵 바뀜을 `sweep.txt` 로. `PIN`(인물을 주인공 앞에 붙임, `auto`)·`SLOT`·`TID`·`EV`·`PRGPOKE`(메모리상 PRG 쓰기). 드라이버는 `warp.lua` 등 |
| `lua/npcbits.lua` | FC: 인물 표 `$70E0` 를 매 프레임 `OR`/`AND` 로 바꾸고 OAM 변화·슬롯 자리·`SHOTS` 화면을 `npcbits.txt` 로 |
| `dq4debug.py rom unrun\|find\|brk COVER...` | DQ4 미실행 코드 찾기. `cover.lua` 기록 여러 개를 합쳐 실행된 명령에서 닿는데 안 돈 코드 덩어리(`unrun`), 패드 2·`$4017`·디버그 스위치 `$C000` 읽기(`find`), 부르는 곳 없는 BRK 함수(`brk`). [fc/dq4/docs/dq4-debug.md](../docs/dq4-debug.md) |
| `lua/debugpad.lua` | FC: 입력 드라이버 앞에 끼워 PRG 롬 메모리를 덮어쓰고(`ROMPATCH`, 예: `3C000=7F;7C000=7F`), 패드 2 를 흉내 내고(`PAD2`, `$15` 값), 바뀐 RAM 을 프레임마다 `debugpad.txt` 로(`LOGW`). 다른 프로브의 `DRIVER` 로 쓸 때는 `PAD_DRIVER` |
| `lua/debugreads.lua` | FC: 디버그 스위치 `$C000`(PRG `3C000`·`7C000`)을 읽는 명령을 모아 `debugreads.txt`(PRG 오프셋, 주소, 횟수, 첫 프레임). `DRIVER`, `MAXF` |
| `lua/debugtrap.lua` | FC: PRG 롬 오프셋(`TRAP`, 예: `401B9`)의 명령이 실행될 때만 프레임·레지스터·`LOG` 주소·스택을 `debugtrap.txt` 로(다른 뱅크의 같은 CPU 주소는 거름). 처음 걸린 뒤 `SHOTS_AFTER` 프레임마다 화면 4장. 드라이버는 `TRAP_DRIVER` |
| `lua/debugsram.lua` | FC: 전원을 켜기 전에 SRAM 8KB 를 `00`(또는 `SRAM` 파일)으로 채우고 `SRAM_DRIVER`(없으면 `DRIVER`)를 돌림. 테스트러너가 불러오는 `Saves/<롬 이름>.sav` 와 상관없이 같은 결과를 내려고 씀 |
| `dq4fcsprite.py rom field\|monster\|sheet\|boss\|changes\|who N\|check-rom\|check-field DIR\|check-monster DIR\|check-boss DIR` | DQ4(FC) 원작 그림 뽑기. `field [N]` 필드 인물·일행·탈것(그림 번호마다 32×64 시트: 행 남·서·동·북, 열 걸음 0·1), `monster [ID]` 전투 몬스터, PNG 1배·8배(색 번호 0 투명)와 색 번호 행렬 `.txt`. `sheet` 전부 만들어 `work/dq4-fcsprite/index.html` 로 묶음, `assets OUT` 은 비공개 에셋 저장소 규칙(1배 PNG·`index.json`·`SOURCE.txt`·`gallery/sprites.html`)으로, `who N` 그 그림을 쓰는 맵·인물. `check-field` 는 `seq.lua`·`warp.lua` 덤프의 `$7200`·CHR·OAM·OBJ 팔레트, `check-monster` 는 `lua/spritebattle.lua` 덤프의 화면 픽셀과 비교. `boss` 는 デスピサロ 형태 0~7(같은 상자), `check-boss` 는 `lua/spriteboss.lua` 덤프 `f0`~`f7` 과 비교, `changes` 는 이벤트가 칸 그림을 바꾸는 곳(BRK `0D 87`)과 へんげのつえ 그림 표. [fc/dq4/docs/dq4-fcsprite-format.md](../docs/dq4-fcsprite-format.md) |
| `lua/spriteframes.lua` | FC: 전투를 일으켜 A 를 누르며 프레임마다 nametable·팔레트·OAM·CHR 이 바뀐 바이트 수, PPU 쓰기, 메시지 번호를 적음(`CALLS`·`WATCH`·`RAW`·`HPFILL`). 전투 연출 보기 |
| `lua/sprite62a5.lua` | FC: `08:$85BE` 가 `$62A5` 를 읽을 때만 bit7 을 켜 勇者 그림 고르기를 봄. `DRIVER=warp.lua` 와 같이 |
| `lua/spritebattle.lua` | FC: 필드 세이브스테이트(`STATE`)에서 위아래로 걸으며 조우 판정 `18:$9D06` 을 메모리상 `CLC`/`RTS` 로 바꿔 전투를 일으키고, 전투 시작 `18:$A11A` 에서 무리 칸을 `MON`(`"67:1,03:2"`, ID:마릿수)으로 덮음. `WAIT` 프레임 뒤 `end.*` 덤프, `COVER=1` 이면 그동안의 `cover.txt`(`krpatch fc listing` 형식), `READS=1` 이면 PRG 읽기 쪽별 `reads.txt` |
| `lua/spriteboss.lua` | FC: `spritebattle.lua` 와 같은 방법으로 전투를 일으켜(기본 `MON=AE:1`) 적 HP 를 `HP` 이하로 누르고 A 를 누름. 형태 번호 `$6E7E` 가 바뀔 때마다 `WAIT` 프레임 뒤 `f<순번>.*` 덤프(`FORMS` 개). `CALLS="14:AC1A,0F:C73E"` 면 그 주소를 실행할 때마다 프레임·A X Y·`ZP` 바이트를 `calls.txt` 에, `OAMLOG=1` 이면 OAM 조합이 바뀐 프레임을 `oamlog.txt` 에. `PRESS=1`·`HPFRAMES` 로 전투를 끝내고 필드로 돌아온 화면도 덤프 |
