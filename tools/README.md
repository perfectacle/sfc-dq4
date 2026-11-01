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
| `wlog.lua` | 드라이버 입력을 재생하면서 지정한 WRAM 바이트들 중 하나라도 바뀔 때마다 프레임과 모든 값을 기록. 인물 스크립트를 덮어 결과를 볼 때 | `WLOG`(`x=7E3028;y=7E3088`), `MAXF` | `wlog.txt` |
| `vramdiff.lua` | 드라이버 입력을 재생하면서 `A0` 프레임부터 `STEP` 마다 VRAM(`MEM=cg` 면 CGRAM)이 바뀐 바이트 수와 범위를 기록. `POKE1` 은 둘째 프레임에 한 번 씀 | `A0`, `STEP`, `LAST`, `MEM`, `POKE1` | `vram.txt` |
| `hookdiff.lua` | 드라이버 입력을 재생하고 `LAST` 프레임에 WRAM·VRAM·CGRAM·OAM 을 덤프(`w.bin`·`v.bin`·`c.bin`·`o.bin`). `POKE1` 은 둘째 프레임에 한 번, `EXEC` 는 PC 실행 횟수. 같은 세이브스테이트로 두 번 돌려 견줄 때 | `LAST`, `POKE1`, `EXEC` | `w.bin` 등, `exec.txt`, `end.png` |

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

## Python

저장소 최상위에서 `uv run python tools/<스크립트>` 로 실행합니다(`uv sync` 가 툴킷 v0.8.0 과 Pillow 를 설치).

표는 트랙마다 나눕니다. 자기 트랙 도구는 자기 절에만 줄을 더합니다.

### 공통

| 스크립트 | 하는 일 |
| --- | --- |
| `listing.py rom cover.txt [시작 끝]` | `cover.lua` 결과로, 실제 실행된 명령만 실행 당시 M·X 폭으로 디스어셈블 |
| `guards.py [--base REF [--pr-body FILE]]` | 트랙별 `guards.toml`(롬이 있어야 도는 회귀 가드) 형식 검사, 바뀐 파일로 걸리는 검사와 명령 찍기, PR 본문 결과 줄 확인(CI `required-checks` 잡과 같음). [guards 스킬](../.agents/skills/guards/SKILL.md) |
| `check_docs.py` | 일지 이름·제목·순번 중복, README 일지 목록, 상대 링크, 개인 경로, 충돌 표시 검사(CI `docs` 잡과 같음) |
| `headless_slots.py` | 머신 전체의 헤드리스 에뮬레이터 프로세스 수 제한. 아래 [HEADLESS_SLOTS](#headless_slots-헤드리스-에뮬레이터-자리) |

### dq5

[sfc/dq5/tools/README.md](../sfc/dq5/tools/README.md) 에 있습니다.

### dq4

FC 원작 분석 도구는 [fc/dq4/tools/README.md](../fc/dq4/tools/README.md), SFC 포팅용 그래픽 도구는 [sfc/dq4/tools/README.md](../sfc/dq4/tools/README.md) 에 있습니다.

## HEADLESS_SLOTS: 헤드리스 에뮬레이터 자리

여러 세션이 한 머신에서 검사를 병렬로 돌리면 에뮬레이터 프로세스가 코어 수보다 많아져 모두 느려집니다. 그래서 헤드리스 에뮬레이터 프로세스 하나가 뜨기 전에 머신 전체에서 함께 쓰는 자리(slot)를 하나 잡고, 끝나면 놓습니다.

- 자리는 원래 체크아웃의 `work/cache/slots/` 에 있는 잠금 파일입니다. 워크트리에서 돌려도 같은 곳을 씁니다. 자리를 쥔 프로세스가 죽으면 잠금이 저절로 풀리므로 파일을 지울 필요가 없습니다.
- 자리 수는 `HEADLESS_SLOTS` 로 정합니다. 기본은 CPU 수의 절반(최소 1)이고, `0` 이나 `off` 면 제한하지 않습니다.
- 프로세스마다 `HEADLESS_SLOTS` 가 다르면, 지금 자리를 쥐었거나 기다리는 프로세스들의 값 중 가장 작은 값을 모두가 따릅니다. 그 값을 쓰는 프로세스가 다 끝나면 다시 자기 값을 씁니다.
- 빈 자리가 없으면 `[headless_slots] <이름>: 자리 N개 모두 사용 중, 기다림` 을 찍고 기다리다가, 잡으면 `자리 i 잡음, X초 기다림` 을 찍습니다. 기다린 시간은 `subprocess` 의 시간 제한과 `guards.py --timeout` 에 듭니다(`dq4compatcheck.py` 의 묶음·코어 프로세스 시간 제한은 자리를 잡은 뒤부터 잽니다).
- 자리를 잡는 곳은 MesenCE 를 띄우는 공통 러너와 `sfc/dq4/tools/dq4libretro.py` 의 `Core`(코어 하나당 하나)입니다. 공통 러너는 MesenCE 하나당 자리 하나를 잡습니다.
  - dq4: `sfc/dq4/tools/dq4mesen.py` 의 `run`·`Runner`(롬을 실행마다 다른 이름으로 복사하고 배터리 기록을 지움. `Runner` 는 자리를 잡은 뒤 `timeout`(기본 900초)을 넘기면 끕니다)와 `testrunner`(받은 인자 그대로 `subprocess.run`). `fc/dq4/tools/dq4story.py` 도 `testrunner` 를 씁니다.
  - dq5: `sfc/dq5/tools/dq5mesen.py` 의 `testrunner`(`subprocess.run` 꼴)·`testrunner_popen`(`subprocess.Popen` 꼴, 프로세스가 끝나는 즉시 자리를 놓고 `timeout` 을 주면 넘길 때 끕니다).
  - `testrunner` 들은 `headless_slots.run`·`headless_slots.popen` 을 부릅니다. `timeout` 은 자리를 잡은 뒤부터 잽니다.
- MesenCE 를 직접 띄우는 코드는 위 두 러너 파일에만 둡니다. 셸 스크립트는 `uv run --locked python sfc/dq4/tools/dq4mesen.py 인자…` 로 띄웁니다(`MESENCE` 의 실행 파일에 `--testrunner` 와 인자를 붙이고, 그 종료 코드로 끝납니다).
- `tools/tests/test_testrunner_callers.py` 가 다른 파일에서 아래를 찾으면 실패합니다.
  - Python: `'--testrunner'` 로 접히는 문자열(`'--' + 'testrunner'`, f-string, `''.join(…)`, `%` 포함, docstring 제외). 실행 파일이 `mesence`·`mesen`·`MESENCE` 이거나 그것을 대입받은 이름(`exe = os.environ['MESENCE']`, `cmd = [exe, …]`)인 `subprocess`·`os.system`·`os.popen`·`os.exec*`·`os.spawn*`·`asyncio.create_subprocess_*` 호출. `import subprocess as sp`, `from subprocess import run` 같은 별칭도 풉니다.
  - 셸(추적되는 `.sh` 와 `#!…sh` 파일): 주석이 아닌 줄의 `--testrunner` 나 `$MESENCE`(`${MESENCE:?…}` 확인은 뺌).
- 자리를 쥔 프로세스가 자리를 잡는 자식을 기다리면 자리가 하나일 때 서로 막힙니다. 자리는 에뮬레이터 프로세스를 띄우는 동안만 쥐고, 자식 Python 도구를 띄우기 전에는 쥔 자리(코어 등)를 놓습니다.
- 새 도구는 위 러너를 부릅니다. 에뮬레이터가 MesenCE 가 아니면 띄우는 자리를 감쌉니다.

```python
import headless_slots   # tools/ 를 sys.path 에

headless_slots.run([emulator, rom], '내 검사', timeout=600)      # subprocess.run 꼴
p = headless_slots.popen([emulator, rom], '내 검사', timeout=600)  # subprocess.Popen 꼴
with headless_slots.slot('내 검사') as s:                          # 직접 감쌀 때
    ...
print(s.waited)         # 기다린 초
```
