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
| `seqboot.lua` | 세이브스테이트에서 `SEQ` 입력을 재생하는 드라이버 | `STATE`, `SEQ`, `MAXF`, `EVERY` | |

세이브스테이트에서 시작하는 상황에 다른 프로브를 쓰려면, 드라이버를 `boot.lua` 로 둔 Lua 폴더를 만들어 `LIBDIR` 로 줍니다.

```sh
export LIBDIR=$(tools/lua/seqlib.sh "$(uv run krpatch sfc lua)" work/walklib walk.lua)
STATE=$PWD/work/state/ship.mss PRE="b:4,wait:40" WAYPOINTS="3,11;3,24;7,24;7,22" \
  SHOT_DIR=$PWD/work/x FROM=340 TO=398 MAXF=400 LO=2AE000 HI=2AFFFF \
  "$MESENCE" --testrunner "$PWD/rom/dq5.sfc" "$PWD/tools/lua/cover.lua"
```

프로브의 결과 파일은 `MAXF`(또는 `TO`) 직전에 쓰이므로, 드라이버가 먼저 멈추지 않게 `MAXF` 를 맞춥니다.

## Python

저장소 최상위에서 `uv run python tools/<스크립트>` 로 실행합니다(`uv sync` 가 툴킷 v0.4.0 과 Pillow 를 설치).

| 스크립트 | 하는 일 |
| --- | --- |
| `listing.py rom cover.txt [시작 끝]` | `cover.lua` 결과로, 실제 실행된 명령만 실행 당시 M·X 폭으로 디스어셈블 |
| `dq5map.py rom BC BD` | DQ5 실내 맵 디코더. `--compare` 로 게임 셀 버퍼(속성 패스 끝)와 비교, `--png` 로 그림(팔레트도 롬에서) |
| `dq5field.py rom` | DQ5 필드 세계 지도 풀기. `--compare` 로 WRAM 과 비교, `--png` 회색조 지도 |
| `dq5trigger.py rom [BC BD]` | DQ5 실내 맵 영역 이동 레코드(맵을 빼면 전체 통계) |
| `attrgrid.py rom BC BD` | 통행 격자를 글자로 찍기(경로 잡기용) |
| `dq5exit.py rom BC BD` | DQ5 실내 맵 출구 셀·목적지·도착 자리 |
| `dq5npc.py rom BC BD` | DQ5 실내 맵 인물 목록. `--night` 밤 목록, `--flags 21AD=10` 이벤트 플래그, `--compare` 로 인물 표(`7E:3000-`)와 비교 |
| `figures.py` | `docs/images/` 의 그림을 다시 만듦(롬 필요, 게임 화면 비교 그림만 `work/` 덤프 필요) |

툴킷에도 같은 방식의 스크립트가 있습니다(`$LIBDIR/probe/`): 특정 PC 실행 시 레지스터
기록(`trace.lua`), 호출자 기록(`calls.lua`) 등.
