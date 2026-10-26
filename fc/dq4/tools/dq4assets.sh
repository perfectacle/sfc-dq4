#!/bin/sh
# 비공개 에셋 저장소(perfectacle/sfc-dq4-assets)의 fc/dq4/ 전체를 롬 하나에서 다시 뽑는다. 저장소 최상위에서 실행한다.
# 사용: MESENCE=/path/to/Mesen fc/dq4/tools/dq4assets.sh [OUT]
#   OUT(기본 work/dq4assets)에 에셋 저장소 fc/dq4/ 와 같은 배치로 만든다. 비어 있지 않으면 멈춘다.
#   롬은 rom/dq4.nes(일본판 Rev A)여야 한다. SHA-1 이 다르면 멈춘다.
#   맵·필드·gfx·스프라이트·몬스터·소리는 롬만 읽는다. 장면 화면(gfx/screens)은 MesenCE 를 전원 켜기부터
#   정해 둔 입력으로 돌려 뜬다(세이브스테이트도 이 스크립트 안에서 만든다). MESENCE 가 없으면 장면 화면만 빠진다.
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
py fc/dq4/tools/dq4sound.py rom/dq4.nes export "$tmp/sound"
mkdir -p "$out/sound"
rev=$(git rev-parse HEAD)
for k in songs sfx; do
  mv "$tmp/sound/$k" "$out/sound/"
  printf 'sfc-dq4 커밋: %s\n명령: uv run --locked python fc/dq4/tools/dq4sound.py rom/dq4.nes export $OUT  (OUT/%s 를 여기로)\n롬: FC 「ドラゴンクエストIV」 일본판 Rev A, SHA-1 %s\n' \
    "$rev" "$k" "$sha" > "$out/sound/$k/SOURCE.txt"
done
rm -rf "$tmp"

if [ -z "$MESENCE" ]; then
  echo "MESENCE 가 없어 장면 화면(gfx/screens)을 건너뜀" >&2
  exit 0
fi

# 장면 덤프는 저장소 상대 경로로 둔다(index.json 의 dump 에 그대로 적힘)
w=work/dq4scenes
rm -rf "$root/$w"
mkdir -p "$root/$w"
LIBDIR=${LIBDIR:-$(uv run --locked krpatch fc lua)}
export LIBDIR
lua=$root/fc/dq4/tools/lua
# mesen LUA VAR=값 …: 환경 변수를 주고 테스트러너로 LUA 를 돌린다
mesen() { l=$1; shift; env "$@" "$MESENCE" --testrunner --nes.ramPowerOnState=AllZeros "$rom" "$l" >/dev/null 2>&1 || true; }
need() { [ -e "$1" ] || { echo "MesenCE 결과가 없음: $1" >&2; exit 1; }; }
rep() { s=""; i=0; while [ $i -lt "$1" ]; do s="$s,$2"; i=$((i + 1)); done; echo "${s#,}"; }

# 1장 왕좌의 방·첫 전투, 이름 확정 직전(「おわり」) 세이브스테이트
STATE_DIR=$root/$w/state sh fc/dq4/tools/dq4state.sh
owari=$root/work/dq4state/owari/end.mss
throne=$root/$w/state/dq4-ch1-throne.mss
need "$owari"

# 전원 켜기: 제작진·IV 로고·타이틀, 그리고 dq4state.sh 의 이름 입력 입력으로 모험의 서·이름 입력 창
mkdir -p "$root/$w/boot" "$root/$w/name"
mesen "$lua/debugsram.lua" SHOT_DIR=$root/$w/boot MAXF=2500 EVERY=0 AT=760,1040,2440 SRAM_DRIVER=$lua/fcgfxscene.lua
mesen "$lua/debugsram.lua" SHOT_DIR=$root/$w/name MAXF=800 EVERY=0 AT=480,740 SRAM_DRIVER=$lua/fcgfxscene.lua \
  SEQ="a@300:4,a@320:4,a@340:4,a@360:4,start@400:4,a@440:4,a@560:4,a@700:4"

# 세이브스테이트에서 이어 뜨기: scene 폴더 STATE SEQ AT [TAIL [STOP]]
scene() {
  mkdir -p "$root/$w/$1"
  mesen "$lua/fcgfxscene.lua" DRIVER=$LIBDIR/seq.lua STATE="$2" SEQ="$3" AT="$4" TAIL="${5:-2000}" ${6:+STOP=$6} \
    EVERY=0 SHOT_DIR="$root/$w/$1"
}
scene ch1t "$owari" "$(rep 8 a:4,wait:46)" 210
scene ch1 "$throne" wait:1 60
scene battle "$root/$w/state/dq4-ch1-battle.mss" wait:1 30,120

# 디버그 장 고르기(고정 뱅크 $C000 bit3, 메모리만 바꿈)로 2장·5장. 성별·메시지 속도 다음에 「シナリオ」 창이 뜬다
pick="wait:10,a:6,wait:60,a:6,wait:60,a:6,wait:120"
mkdir -p "$root/$w/ch2" "$root/$w/ch5"
mesen "$lua/eventwalk.lua" STATE="$owari" SEQ="$pick,right:4,wait:20,a:6,wait:200,$(rep 16 a:4,wait:46),wait:100,$(rep 3 b:6,wait:60)" \
  TAIL=30 PRGPOKE="3C000=F7;7C000=F7" SHOT_DIR="$root/$w/ch2"
ch2=$root/$w/ch2/end.mss
need "$ch2"
mesen "$lua/fcgfxscene.lua" DRIVER="$lua/eventwalk.lua" STATE="$owari" SEQ="$pick,$(rep 4 right:4,wait:20),a:6,wait:200,$(rep 60 a:4,wait:46)" \
  TAIL=4000 PRGPOKE="3C000=F7;7C000=F7" AT=1900 EVERY=0 SHOT_DIR="$root/$w/ch5"

# 장 끝: 조건 플래그를 쓰고 그 맵으로 워프한 뒤 60프레임마다 A(fc/dq4/docs/dq4-save-format.md 의 장 끝 표)
ends() {
  STATE=$2 SET=$3 WAIT=60 TAIL=10 sh fc/dq4/tools/dq4warp.sh "$w/ce$1" "$4" "$5" "$6" >/dev/null
  need "$root/$w/ce$1/warp.mss"
  scene "ce${1}s" "$root/$w/ce$1/warp.mss" "wait:56,$(rep 25 a:4,wait:56)" "$7"
}
ends 1 "$throne" "6283=80;6285=04" 02/00 12 0B 120,780
ends 2 "$ch2" "6287=18" 01/00 0E 1A 300,1020
ends 3 "$ch2" "615A=02;6282=C0" 42/01 1F 08 540,1140
ends 4 "$ch2" "615A=03;6282=E0;628A=10" 04/00 0B 1C 300,1320

# 엔딩: 5장 끝 조건으로 天空城에 워프. 바다 장면은 줄 스크롤 기록과 함께, 나머지는 1만 프레임씩 이어서
STATE=$ch2 SET="615A=04;6282=F0;62A1=20" WAIT=60 TAIL=10 sh fc/dq4/tools/dq4warp.sh "$w/ed0" 2D/00 0C 07 >/dev/null
prev=$root/$w/ed0/warp.mss
need "$prev"
mkdir -p "$root/$w/sea"
mesen "$lua/fcgfxscroll.lua" DRIVER=$LIBDIR/seq.lua STATE="$prev" SEQ=wait:1 TAIL=1900 EVERY=0 AT=1000,1001,1002,1003,1800,1801 \
  LOG=1000-1003,1800-1801 SHOT_DIR="$root/$w/sea"
for k in 1 2 3 4; do
  case $k in 1) at=2600 ;; 2) at=5000 ;; 3) at=2800,6000 ;; 4) at=1000,5000 ;; esac
  # STOP 을 seq.lua 가 멈추는 프레임보다 뒤로 두어 다음 조각이 이어 갈 end.mss 를 남긴다
  scene "ed$k" "$prev" wait:1 "$at" 10000 10100
  prev=$root/$w/ed$k/end.mss
  need "$prev"
done

spec=$w/scenes.json
cat > "$root/$spec" <<EOF
[
 {"name": "credits", "title": "부팅 제작진 화면(760프레임)", "prefix": "$w/boot/f00760"},
 {"name": "logo-iv", "title": "IV 로고(1040프레임)", "prefix": "$w/boot/f01040"},
 {"name": "title", "title": "타이틀(2440프레임)", "prefix": "$w/boot/f02440"},
 {"name": "adventure-book", "title": "모험의 서 창(전원 켜고 480프레임)", "prefix": "$w/name/f00480"},
 {"name": "name-entry", "title": "이름 입력 창(740프레임)", "prefix": "$w/name/f00740"},
 {"name": "status-window", "title": "1장 시작, 상태 창", "prefix": "$w/ch1/f00060"},
 {"name": "command-window", "title": "5장 시작, 명령 창·대사 창", "prefix": "$w/ch5/f01900"},
 {"name": "battle", "title": "1장 첫 전투(30프레임)", "prefix": "$w/battle/f00030"},
 {"name": "battle2", "title": "1장 첫 전투(120프레임)", "prefix": "$w/battle/f00120"},
 {"name": "chapter1-title", "title": "1장 제목(第一章 王宮の戦士たち, 새로 시작)", "prefix": "$w/ch1t/f00210"},
 {"name": "chapter1-end", "title": "1장 끝(第一章 王宮の戦士たち 完)", "prefix": "$w/ce1s/f00120"},
 {"name": "chapter2-title", "title": "2장 제목(第二章 おてんば姫の冒険)", "prefix": "$w/ce1s/f00780"},
 {"name": "chapter2-end", "title": "2장 끝(完)", "prefix": "$w/ce2s/f00300"},
 {"name": "chapter3-title", "title": "3장 제목(第三章 武器屋トルネコ)", "prefix": "$w/ce2s/f01020"},
 {"name": "chapter3-end", "title": "3장 끝(完)", "prefix": "$w/ce3s/f00540"},
 {"name": "chapter4-title", "title": "4장 제목(第四章 モンバーバラの姉妹)", "prefix": "$w/ce3s/f01140"},
 {"name": "chapter4-end", "title": "4장 끝(完)", "prefix": "$w/ce4s/f00300"},
 {"name": "chapter5-title", "title": "5장 제목(第五章 導かれし者たち)", "prefix": "$w/ce4s/f01320"},
 {"name": "ending-dawn1", "title": "엔딩: 바다 위 天空城, 동트기 전(줄 스크롤)", "prefix": "$w/sea/f01000", "ppulog": "$w/sea/ppulog.txt", "mirror": "h"},
 {"name": "ending-dawn2", "title": "엔딩: 바다 위 天空城, 동튼 뒤(줄 스크롤)", "prefix": "$w/sea/f01800", "ppulog": "$w/sea/ppulog.txt", "mirror": "h"},
 {"name": "ending-cloud", "title": "엔딩: 구름 위 天空城과 열기구", "prefix": "$w/ed1/f02600"},
 {"name": "ending-staff1", "title": "엔딩 스태프 롤 첫머리", "prefix": "$w/ed3/f02800"},
 {"name": "ending-staff2", "title": "엔딩 스태프 롤", "prefix": "$w/ed3/f06000"},
 {"name": "ending-staff3", "title": "엔딩 스태프 롤", "prefix": "$w/ed4/f01000"},
 {"name": "ending-the-end", "title": "엔딩 마지막(The End)", "prefix": "$w/ed4/f05000"}
]
EOF
py fc/dq4/tools/dq4fcgfx.py rom/dq4.nes scenes "$out" "$spec"
py fc/dq4/tools/dq4fcgfx.py rom/dq4.nes gallery "$out"
echo "에셋 → $out"
