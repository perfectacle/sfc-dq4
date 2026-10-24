#!/bin/sh
# 툴킷 Lua 폴더를 본떠 boot.lua 만 다른 드라이버(기본 seqboot.lua, 셋째 인자로 walk.lua 등)로 바꾼 폴더를 만들고
# 그 경로를 출력한다. 프로브(rprof.lua 등)가 끝에서 부르는 boot.lua 가 그 드라이버가 된다.
# 사용: export LIBDIR=$(tools/lua/seqlib.sh "$(krpatch sfc lua)" work/seqlib [walk.lua])
set -e
src=$1; dst=$2; driver=${3:-seqboot.lua}
mkdir -p "$dst"
ln -sf "$src/lib.lua" "$dst/lib.lua"
ln -sfn "$src/probe" "$dst/probe"
cp "$(dirname "$0")/$driver" "$dst/boot.lua"
cd "$dst" && pwd
