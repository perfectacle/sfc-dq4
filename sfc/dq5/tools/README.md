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
| `dq5npc.py rom BC BD` | DQ5 실내 맵 인물 목록과 인물 표 값·인라인 스크립트 명령. `--night` 밤 목록, `--flags 21AD=10` 이벤트 플래그, `--compare` 로 인물 표(`7E:3000-`) 22칸 비교, `--list 108BBD` 목록 주소로 보기, `--check-scripts` 모든 스크립트 길이 검사 |
| `dq5text.py rom 번호` | DQ5 보행 모드 메시지를 글자로(`--codes` 로 코드). `--controls` 제어 코드 처리기와 뜻, `--window N` 메뉴 창 레코드와 항목 문자열. 폰트 그리기(`glyph`), 글자표(`CHARS`), 이름 문자열(`string`·`string_codes`)도 이 모듈 |
| `dq5talk.py rom 대화번호` | 대화 번호의 갈래·스크립트·메시지(조건 코드 뜻, 특수 기능 처리기, 묻기 갈래 포함). `BC BD` 를 주면 그 맵 인물 전부, `--check` 로 스크립트 574개 경계 검사, `--calls` 로 네이티브 호출 대상 |
| `dq5chest.py rom [BC BD]` | DQ5 보물상자(번호·칸·열림 플래그·내용물), タンス·ツボ·タル 항목, 발밑 표(`1E:F08B`). 물건 이름과 `D000`~`D009` 의 뜻까지 |
| `dq5shop.py rom` | DQ5 상점 품목 목록(종류·마을 그룹 키)과 물건 가격, 작은 메달·코인 교환 값, 여관 1인 값 |
| `dq5item.py rom` | DQ5 물건 216개의 장비 칸·공격력/수비력·사람 장비 비트·동료 몬스터 장비 비트(16비트)·가격과 표 k0~k4 원값 |
| `dq5monster.py rom` | DQ5 몬스터 236개의 필드(HP·MP·민첩·공격·수비·경험치·금화·행동 수·재생·떨어뜨리는 물건·동료 확률과 종류 등), 행동 6개, 내성 18칸. `--companions` 동료 레코드(`23:AED1`) 41개 |
| `dq5spell.py rom` | DQ5 전투 행동 171개(주문·몬스터 행동)의 이름·MP·범위 비트·처리 루틴·피해/회복량·내성 종류 |
| `dq5encounter.py rom [BC BD]` | DQ5 전투 조우 구역 85개의 칸별 무리·확률·마릿수. `BC BD` 는 그 실내 맵의 구역, `--maps` 조우가 있는 실내 맵, `--field` 필드 구역 격자, `--events` 이벤트 전투 무리 표(`23:D757`), `--trace trace.txt` 로 `probe/trace.lua` 기록(`TRACE=23E7C2,23E9B0,23EA40,23E98F LOG=7E1001,7E1003,7E1005,7E1007`)의 무리를 표와 대조, `--steps trace.txt` 로 걸음마다의 구역·조우율(`TRACE=0082AF LOG=7E00BC,7E00BE,7E00B6,7E00B8,7E1948,7E075E,7E21C9`)을 격자·지형으로 계산한 값과 대조 |
| `dq5mongfx.py rom [몬스터…]` | DQ5 전투 몬스터 그림(그림 번호·머리·조각·색). `--png` 그림, `--compare at.bin` 게임 버퍼(`7E:4000`)와 타일 비교, `--shot` 전투 화면과 RGB 비교, `--oam o.oam v.vram` OBJ 색 번호 비교, `--layout "몬스터:마릿수[:무리 값],…"` 무리 배치(그림 상자 OAM 좌표) |
| `dq5battlebg.py rom [번호]` | DQ5 전투 배경 49개(번호 `$1AA0 & 7F`, 그림·목록·팔레트 주소). `--png` 256x128 띠, `--cgram` 레코드 밖 색, `--alt` 밤 팔레트, `--compare 덤프폴더 프레임` 으로 `dq5battledump.lua` 덤프와 비교 |
| `lua/dq5battledump.lua` | 전투 그림 실험: `AT` 실행 때 WRAM(`at.bin`), `DUMPF` 프레임에 WRAM·VRAM·CGRAM·OAM·화면, `FROM`~`TO` DMA 기록. `boot.lua`(walk.lua) 뒤에 붙여 씀 |
| `dq5figures.py` | `sfc/dq5/images/` 의 그림을 다시 만듦(롬 필요, 게임 화면 비교 그림만 `work/` 덤프 필요) |

## lua/: MesenCE 분석 스크립트

| 스크립트 | 하는 일 | 추가 환경 변수 | 결과 |
| --- | --- | --- | --- |
| `lua/dq5savestate.lua` | 드라이버(`boot.lua`) 입력을 재생하다가 `SAVEAT` 프레임에 세이브스테이트와 화면 저장. `seqlib.sh` 로 `dq5warp.lua` 를 드라이버로 두면 장면 이동 뒤 걸어 들어간 곳을 남길 수 있음 | `SAVEAT`, `SAVENAME` | `<SAVENAME>`, `.png` |
| `lua/dq5warp.lua` | DQ5: 배 선실 세이브스테이트에서 조작 가능한 필드(`FIELD`), 아무 실내 맵(`TO`), 고른 무리와의 전투(`BATTLE`, `GROUP`)로 가서 세이브스테이트 저장. 사용법은 [dq5-handoff.md 「장면 이동 도구」](../handoff.md#장면-이동-도구) | `STATE`, `FIELD`(`X,Y`)·`TO`(`BC/BD,X,Y[,방향]`)·`BATTLE`(`몬스터:마릿수,…`)·`GROUP`(이벤트 무리 번호), `SET`(`2194\|80`), `POKE`, `ROMPATCH`, `TEST`, `SETTLE`, `SAVE`, `MAXF` | `warp.txt`, `end.png`, `<SAVE>` |
| `lua/dq5battle.lua` | DQ5: `walk.lua` 처럼 걸은 뒤 `LOOP` 입력(기본 A 연타)으로 싸우면서 전투 메시지(`24:8C39`) 번호와 `PEEK` 주소 값을 메시지마다 기록. 쓰는 예는 [dq5-data-format.md 「주문과 행동」](../docs/dq5-data-format.md#주문과-행동-268765) | `STATE`, `PRE`, `WAYPOINTS`, `LOOP`, `ROMPATCH`, `POKE`, `PEEK`(`7E07C0:64,…`), `SHOTMSG`, `SHOTDELAY`, `MAXF` | `battle.txt`, `sNNNNN.png`, `end.png` |
| `lua/dq5warptrace.lua` | DQ5: `dq5warp.lua` 를 그대로 돌리면서 PC 실행·WRAM 읽기·쓰기를 기록하고, 도착한 뒤 정한 프레임에 WRAM 을 고치거나 화면을 찍음 | `dq5warp.lua` 의 변수, `TRACE`, `LOG`, `RWATCH`·`WWATCH`(`1000-1000`), `WFROM`, `LATE`(`600:7E21C9=01`), `SHOTS` | `trace.txt`, `rwatch.txt`, `wwatch.txt`, `sNNNNN.png` |
