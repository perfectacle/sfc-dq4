# tools

## lua/ — MesenCE `--testrunner` 프로브

모두 kr-patch-toolkit 의 `boot.lua`(부팅·A 연타·`SEQ` 입력)를 그대로 쓰므로 `LIBDIR` 에 툴킷 Lua 경로를 준다.

```sh
LIB=~/IdeaProjects/kr-patch-toolkit/src/kr_patch/snes/lua
MESEN=~/kr-patch/tools/MesenCE.app/Contents/MacOS/Mesen
LIBDIR=$LIB SHOT_DIR=$PWD/work/x MAXF=1720 EVERY=0 PERIOD=40 TAP=a FROM=1625 TO=1710 \
  $MESEN --testrunner $PWD/rom/dq5.sfc $PWD/tools/lua/wprof.lua
```

`SHOT_DIR` 는 절대 경로여야 한다(상대 경로면 MesenCE 작업 폴더 기준이 되어 결과가 사라진다).

| 스크립트 | 하는 일 | 결과 |
| --- | --- | --- |
| `wsnap.lua` | `FROM` 부터 `STEP` 프레임마다 WRAM·화면 덤프 | `wNNNNN.bin`, `sNNNNN.png` |
| `wwatch.lua` | `WATCH` 범위에 쓰는 PC 를 모음(`FROM` 전 무시) | `wwatch.txt` |
| `wprof.lua` | `FROM`~`TO` 동안 WRAM 쓰기를 PC 별 집계 | `wprof.txt` |
| `rprof.lua` | `FROM`~`TO` 동안 ROM 데이터 읽기를 PC 별 집계 | `rprof.txt` |
| `pcseq.lua` | `LO`~`HI` 에서 실행된 PC 를 순서대로 기록 | `pcseq.txt` |
