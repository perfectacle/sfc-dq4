#!/bin/sh
# 비공개 에셋 저장소(perfectacle/sfc-dq4-assets)의 fc/dq4/ 전체를 롬 하나에서 다시 뽑는다. 저장소 최상위에서 실행한다.
# 사용: fc/dq4/tools/dq4assets.sh [OUT]
#   OUT(기본 work/dq4assets)에 에셋 저장소 fc/dq4/ 와 같은 배치로 만든다. 비어 있지 않으면 멈춘다.
#   롬은 rom/dq4.nes(일본판 Rev A)여야 한다. SHA-1 이 다르면 멈춘다.
#   소리의 FLAC 은 flac 명령(PATH)으로 만든다. 판이 다르면 FLAC 바이트가 다를 수 있어 sound/*/SOURCE.txt 에 판을 적는다.
#   모두 롬만 읽는다. 장면 화면(gfx/screens)은 dq4scenes.py 가 롬을 작은 NES(dq4nes.py)로 전원 켜기부터 돌려 뜬다
#   (에뮬레이터·세이브스테이트 필요 없음, 전체 15분쯤).
# 같은 커밋·같은 롬이면 몇 번 돌려도 바이트까지 같다.
set -e
root=$(pwd)
rom=$root/rom/dq4.nes
sha=1147ce6dfdc3354d8bb89be40f5d1a97a2be1aea
out=${1:-work/dq4assets}
case $out in /*) ;; *) out=$root/$out ;; esac
py() { uv run --locked python "$@"; }

got=$(py -c 'import hashlib, sys; print(hashlib.sha1(open(sys.argv[1], "rb").read()).hexdigest())' "$rom")
[ "$got" = "$sha" ] || { echo "rom/dq4.nes 의 SHA-1 이 $got 입니다($sha 이어야 함)" >&2; exit 1; }
if [ -d "$out" ] && [ -n "$(ls -A "$out")" ]; then
  echo "$out 이 비어 있지 않습니다. 빈 폴더를 주세요" >&2
  exit 1
fi
mkdir -p "$out"
tmp=$out/.tmp
mkdir -p "$tmp"

py fc/dq4/tools/dq4fcgfx.py rom/dq4.nes all "$out"
py fc/dq4/tools/dq4fcsprite.py rom/dq4.nes assets "$tmp/sprite"
mv "$tmp/sprite/sprites" "$tmp/sprite/monsters" "$out/"
mv "$tmp/sprite/gallery/sprites.html" "$out/gallery/"
py fc/dq4/tools/dq4sound.py rom/dq4.nes export "$tmp/sound" --flac
mkdir -p "$out/sound"
rev=$(git rev-parse HEAD)
for k in songs sfx; do
  mv "$tmp/sound/$k" "$out/sound/"
  printf 'sfc-dq4 커밋: %s\n명령: uv run --locked python fc/dq4/tools/dq4sound.py rom/dq4.nes export $OUT --flac  (OUT/%s 를 여기로, %s)\n롬: FC 「ドラゴンクエストIV」 일본판 Rev A, SHA-1 %s\n' \
    "$rev" "$k" "$(flac --version)" "$sha" > "$out/sound/$k/SOURCE.txt"
done
mv "$tmp/sound/dq4.nsf" "$out/sound/"
rm -rf "$tmp"

# 장면 덤프는 저장소 상대 경로로 둔다(index.json 의 dump 에 그대로 적힘)
w=work/dq4scenes
rm -rf "$root/$w"
py fc/dq4/tools/dq4scenes.py rom/dq4.nes "$w"
spec=$w/scenes.json
py fc/dq4/tools/dq4fcgfx.py rom/dq4.nes scenes "$out" "$spec"
py fc/dq4/tools/dq4fcgfx.py rom/dq4.nes gallery "$out"
echo "에셋 → $out"
