# tools

## lua/: MesenCE 분석 스크립트

[MesenCE](https://github.com/nesdev-org/MesenCE) 의 `--testrunner` 로 롬을 화면 없이
돌리며 RAM·ROM 접근을 기록합니다. 모두
[kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) 의 `boot.lua`
(전원 켜기부터 버튼 입력·스크린샷)를 불러 쓰므로, 툴킷 Lua 폴더를 `LIBDIR` 로
넘깁니다.

```sh
export LIBDIR=$(krpatch snes lua)     # 툴킷 Lua 폴더
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

툴킷에도 같은 방식의 스크립트가 있습니다(`$LIBDIR/probe/`): 특정 PC 실행 시 레지스터
기록(`trace.lua`), 호출자 기록(`calls.lua`) 등.
