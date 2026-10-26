#!/usr/bin/env bash
# NDS DQ4 참고용 추출물(비공개 에셋 저장소의 nds/dq4/)을 롬에서 처음부터 다시 만든다.
#
#   nds/dq4/tools/ndsassets.sh OUT [ASSETS]
#
# 저장소 최상위에서 실행한다. OUT 에 에셋 저장소의 nds/dq4/ 와 같은 모양으로 만들고, ASSETS(에셋
# 저장소 체크아웃)를 주면 마지막에 ASSETS/nds/dq4/ 로 동기화한다. 단계는 STEPS 로 고른다
# (기본 "unpack gfx screens sound", 예: STEPS="gfx screens"). screens·sound 는 DESMUME_CORE 가 필요하다.
# 롬은 rom/dq4ds.nds·rom/dq4ds-kr.nds, 풀어 둔 롬은 work/nds/{jp,kr}, 중간 결과는 work/nds/assets/.
# 근거와 재현 범위는 nds/dq4/README.md 「에셋 다시 만들기」.
set -euo pipefail

OUT=${1:?OUT 폴더를 주세요}
ASSETS=${2:-}
STEPS=${STEPS:-unpack gfx screens sound}
PY="uv run --locked python"
TOOLS=nds/dq4/tools
WORK=work/nds/assets
JP_SHA1=84baf75d79b842fa5ecfdc66c112f1d19bf228ae
KR_SHA1=a2ee52765cd54715e777b2993277e752e3ec276d

has() { [[ " $STEPS " == *" $1 "* ]]; }
say() { printf '== %s\n' "$*" >&2; }

check_rom() {
  local got
  got=$(shasum -a 1 "$1" | cut -d' ' -f1)
  [[ $got == "$2" ]] || { echo "$1 의 SHA-1 이 $got 입니다(기대 $2)" >&2; exit 1; }
}

say "롬 확인"
check_rom rom/dq4ds.nds $JP_SHA1
check_rom rom/dq4ds-kr.nds $KR_SHA1
if has screens || has sound; then
  : "${DESMUME_CORE:?screens·sound 단계는 DESMUME_CORE(desmume libretro 코어 경로)가 필요합니다}"
fi

COMMIT=$(git rev-parse --short HEAD)
git diff --quiet HEAD -- nds/dq4/tools || COMMIT="$COMMIT(+고친 도구)"
mkdir -p "$OUT" "$WORK"
# 단계마다 OUT 안을 지우고 새로 쓰므로, 비었거나 전에 이 스크립트가 쓴 폴더만 받는다.
if [[ -n $(ls -A "$OUT") && ! -f $OUT/manifest.json && ! -d $OUT/screens && ! -d $OUT/sound ]]; then
  echo "$OUT 는 비어 있지 않고 추출물 폴더도 아닙니다" >&2
  exit 1
fi

# 각 폴더의 SOURCE.txt. $1 폴더, $2 설명, 나머지는 명령 줄.
source_txt() {
  local dir=$1 what=$2
  shift 2
  {
    echo "$what"
    echo "sfc-dq4 커밋: $COMMIT"
    echo "원본 롬: rom/dq4ds.nds SHA-1 $JP_SHA1 (NDS 일본판)"
    echo "한글패치 롬: rom/dq4ds-kr.nds SHA-1 $KR_SHA1 (그래픽의 kr/ 만)"
    echo "desmume libretro 코어(맵 화면·소리 장면): libretro/desmume 95b4d79"
    echo "전체 명령(sfc-dq4 저장소 최상위에서): nds/dq4/tools/ndsassets.sh OUT <sfc-dq4-assets>"
    echo "이 폴더를 만든 명령:"
    printf '  %s\n' "$@"
  } >"$dir/SOURCE.txt"
}

if has unpack; then
  for v in jp:dq4ds kr:dq4ds-kr; do
    d=work/nds/${v%%:*}
    if [[ -d $d/data ]]; then
      say "풀기: $d 가 이미 있어 건너뜀"
    else
      say "풀기: rom/${v#*:}.nds → $d"
      uv run --locked krpatch nds unpack "rom/${v#*:}.nds" "$d"
    fi
  done
fi

if has gfx; then
  say "그래픽"
  # 그래픽 폴더만 새로 만든다. screens/·sound/ 는 각자의 단계가 맡는다.
  find "$OUT" -mindepth 1 -maxdepth 1 ! -name screens ! -name sound -exec rm -rf {} +
  $PY $TOOLS/ndsgfx.py export "$OUT" --kr work/nds/kr
  source_txt "$OUT" "NDS DQ4 그래픽(screens/·sound/ 는 각 폴더의 SOURCE.txt)" \
    "$PY $TOOLS/ndsgfx.py export OUT --kr work/nds/kr" \
    "$PY $TOOLS/ndsgfx.py gallery OUT"
fi

if has screens; then
  say "맵 화면"
  rm -rf "$OUT/screens"
  $PY $TOOLS/ndswarp.py screens "$OUT/screens"
  source_txt "$OUT/screens" "NDS DQ4 맵 화면(README.txt 에 찍은 방법)" \
    "$PY $TOOLS/ndswarp.py screens OUT/screens"
fi

if has sound; then
  say "소리"
  rm -rf "$OUT/sound"
  $PY $TOOLS/ndssound.py export "$OUT/sound"
  for i in 0 1 2 3; do
    $PY $TOOLS/ndssound.py scenes "$WORK/sc$i.json" --maps all --shard "$i/4" &
  done
  wait
  $PY $TOOLS/ndssound.py summary "$WORK/summary.json" "$WORK"/sc{0,1,2,3}.json
  $PY $TOOLS/ndssound.py gallery "$OUT/sound" --scenes "$WORK/summary.json"
  source_txt "$OUT/sound" "NDS DQ4 소리" \
    "$PY $TOOLS/ndssound.py export OUT/sound" \
    "$PY $TOOLS/ndssound.py scenes $WORK/scI.json --maps all --shard I/4   # I = 0 1 2 3" \
    "$PY $TOOLS/ndssound.py summary $WORK/summary.json $WORK/sc0.json $WORK/sc1.json $WORK/sc2.json $WORK/sc3.json" \
    "$PY $TOOLS/ndssound.py gallery OUT/sound --scenes $WORK/summary.json"
fi

# 첫 페이지는 옆 폴더(screens/·sound/)가 있어야 그 링크가 들어가므로 마지막에 쓴다.
if [[ -f $OUT/manifest.json ]]; then
  $PY $TOOLS/ndsgfx.py gallery "$OUT"
fi

if [[ -n $ASSETS ]]; then
  dst=$ASSETS/nds/dq4
  mkdir -p "$dst"
  # 하위 폴더마다 --delete 로 맞추되, 이번에 만들지 않은 단계의 폴더는 건드리지 않는다.
  # README.md 는 에셋 저장소에서 손으로 쓰는 안내라 지우지 않는다.
  if has gfx; then
    say "동기화: 그래픽 → $dst"
    rsync -a --delete --exclude /screens --exclude /sound --exclude /README.md "$OUT/" "$dst/"
  elif [[ -f $OUT/index.html ]]; then
    cp "$OUT/index.html" "$dst/index.html"
  fi
  for sub in screens sound; do
    if has $sub; then
      say "동기화: $sub → $dst/$sub"
      rsync -a --delete "$OUT/$sub/" "$dst/$sub/"
    fi
  done
fi
say "끝"
