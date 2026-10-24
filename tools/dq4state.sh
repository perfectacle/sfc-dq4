#!/bin/sh
# DQ4 실험 출발점 세이브스테이트를 롬에서 다시 만든다. 저장소 최상위에서 실행한다.
#   work/state/dq4-ch1-throne.mss     1장 시작, 바트랜드 성 왕좌의 방, 라이안이 조작 가능
#   work/state/dq4-ch1-courtyard.mss  왕좌의 방에서 걸어 나온 성 앞(맵 $0028=0A)
#   work/state/dq4-ch1-field.mss      성 아래 마을 서쪽 끝으로 나온 필드($0028=00)
#   work/state/dq4-ch1-battle.mss     필드에서 오가다 만난 전투(おおみみず 둘, $6E49=07 07)
# 사용: MESENCE=/path/to/Mesen tools/dq4state.sh
# 단계마다 앞 단계의 세이브스테이트에서 seq.lua 로 입력을 재생한다. 오프닝은 입력 시점에 따라
# 장면이 앞뒤로 밀리므로 한 번에 긴 입력을 주지 않고 장면마다 끊는다.
set -e
: "${MESENCE:?MESENCE 에 MesenCE 실행 파일 경로를 주세요}"
root=$(pwd)
rom=$root/rom/dq4.nes
tmp=$root/work/dq4state
LIBDIR=${LIBDIR:-$(uv run --locked krpatch fc lua)}
export LIBDIR
mkdir -p "$tmp" "$root/work/state"

# step 이름 시작상태 SEQ TAIL
step() {
  mkdir -p "$tmp/$1"
  SHOT_DIR=$tmp/$1 STATE=$2 SEQ=$3 TAIL=$4 EVERY=0 WATCH="x=0044;y=0045;map=0028" \
    "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros "$rom" "$LIBDIR/seq.lua" >/dev/null 2>&1
  echo "$1: $(tail -1 "$tmp/$1/watch.txt")"
}

# 이름 입력 화면(이름은 「あああ」까지 들어간 상태)
mkdir -p "$tmp/name"
SHOT_DIR=$tmp/name MAXF=760 EVERY=0 SAVEAT=750 STATE_OUT=name.mss \
  SEQ="a@300:4,a@320:4,a@340:4,a@360:4,start@400:4,a@440:4,a@560:4,a@700:4" \
  "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros "$rom" "$LIBDIR/mkstate.lua" >/dev/null 2>&1

# 커서를 「おわり」로: 아래 5칸, 오른쪽 9칸
d="down:10,wait:10,"; r="right:10,wait:10,"
step owari "$tmp/name/name.mss" "wait:10,$d$d$d$d$d$r$r$r$r$r$r$r$r${r}wait:10" 5

# 이름 확정 뒤 대사를 A 로 넘기고 B 로 명령 창을 닫는다
a=""; i=0
while [ $i -lt 34 ]; do a="${a}a:6,wait:44,"; i=$((i + 1)); done
step throne "$tmp/owari/end.mss" "${a}wait:100,b:6,wait:60,b:6,wait:60" 30

# 아래로 걷다가 병사를 왼쪽으로 비켜 성 밖으로
step courtyard "$tmp/throne/end.mss" "down:150,left:16,down:300" 200

# 마을 길(13열)로 1C행까지 내려가 서쪽 끝으로 나간다
step field "$tmp/courtyard/end.mss" "down:144,right:16,down:160,left:400,wait:200" 60

# 마을에서 한 칸 떨어져 위아래로 오가면 전투가 난다
s="left:16,up:64,"; i=0
while [ $i -lt 15 ]; do s="${s}up:48,down:48,"; i=$((i + 1)); done
step battle "$tmp/field/end.mss" "${s}wait:10" 10
echo "battle: 몬스터 무리 $(od -An -tx1 -j $((0x0E49)) -N2 "$tmp/battle/end.sram")"

cp "$tmp/throne/end.mss" "$root/work/state/dq4-ch1-throne.mss"
cp "$tmp/throne/end.png" "$root/work/state/dq4-ch1-throne.png"
cp "$tmp/courtyard/end.mss" "$root/work/state/dq4-ch1-courtyard.mss"
cp "$tmp/courtyard/end.png" "$root/work/state/dq4-ch1-courtyard.png"
cp "$tmp/field/end.mss" "$root/work/state/dq4-ch1-field.mss"
cp "$tmp/battle/end.mss" "$root/work/state/dq4-ch1-battle.mss"
cp "$tmp/battle/end.png" "$root/work/state/dq4-ch1-battle.png"
