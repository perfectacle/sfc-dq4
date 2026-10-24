#!/bin/sh
# DQ4 장면 이동: fc/dq4/tools/lua/warp.lua 를 돌려 목적지에서 조작 가능한 세이브스테이트를 만든다.
# 저장소 최상위에서 실행한다. MESENCE 필요.
#   fc/dq4/tools/dq4warp.sh OUT GG/KK [X Y [DIR]]   맵. X Y 를 빼면 그 맵으로 들어오는 첫 출구·입구의 도착 자리
#   fc/dq4/tools/dq4warp.sh OUT field F X Y          필드
# OUT 은 결과 폴더(work/ 아래 상대 경로도 됨). OUT/warp.mss, warp.png, warp.txt, end.* 가 생긴다.
# STATE, KEY, WAIT, SET, AFTER, SEQ, TAIL, STATE_OUT 은 환경 변수로 그대로 넘어간다(warp.lua 머리 주석).
set -e
: "${MESENCE:?MESENCE 에 MesenCE 실행 파일 경로를 주세요}"
[ $# -ge 2 ] || { sed -n 3,7p "$0"; exit 2; }
root=$(pwd)
out=$1
case $out in /*) ;; *) out=$root/$out ;; esac
mkdir -p "$out"
LIBDIR=${LIBDIR:-$(uv run --locked krpatch fc lua)}
export LIBDIR
STATE=${STATE:-$root/work/state/dq4-ch1-throne.mss}
export STATE
if [ "$2" = field ]; then
  export FIELD=$3 X=$4 Y=$5
  unset MAP
else
  export MAP=$2
  unset FIELD
  if [ $# -ge 4 ]; then
    export X=$3 Y=$4
    [ $# -ge 5 ] && export DIR=$5
  else
    # 연결 표(dq4map.exits 와 같은 도착 자리 계산)와 필드 입구의 도착 레코드에서 첫 자리
    set -- $(uv run --locked python - "${2%/*}" "${2#*/}" <<'EOF'
import sys
sys.path.insert(0, 'fc/dq4/tools')
from kr_patch.fc import ines
import dq4field
import dq4map
prg = ines.prg(open('rom/dq4.nes', 'rb').read())
g, k = int(sys.argv[1], 16), int(sys.argv[2], 16)
for a, b in dq4map.links(prg):
    for here, there in ((a, b), (b, a)):
        for e in dq4map.exits(prg, here[0], here[1]):
            if e[2:4] == (g, k):
                print('%02X %02X %X' % (e[4], e[5], e[6] & 3))
                sys.exit()
for e in dq4field.entrances(prg):
    if e[0] == g and e[3] == k:
        print('%02X %02X %X' % (e[4], e[5], e[6] & 3))
        sys.exit()
EOF
)
    [ $# -ge 3 ] || { echo "$MAP 로 들어오는 출구·입구가 없습니다. X Y 를 주세요" >&2; exit 1; }
    export X=$1 Y=$2 DIR=${DIR:-$3}
  fi
fi
SHOT_DIR=$out "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros "$root/rom/dq4.nes" \
  "$root/fc/dq4/tools/lua/warp.lua" >/dev/null 2>&1 || true
cat "$out/warp.txt"
