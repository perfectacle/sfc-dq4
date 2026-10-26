#!/bin/sh
# Build the desmume libretro core with the sfc-dq4 memory watch (desmume-watch.patch).
#
#   sh nds/dq4/tools/build-desmume-watch.sh OUT [SRC]
#
# OUT is the core file to write (desmume_libretro.dylib on macOS, .so on Linux).
# SRC is the desmume checkout to use; default work/desmume-watch. The script owns
# SRC: it checks out the base commit with --force before applying the patch.
set -eu

BASE=95b4d79
REPO=https://github.com/libretro/desmume.git
PATCH=$(cd "$(dirname "$0")" && pwd)/desmume-watch.patch

[ $# -ge 1 ] || { echo "usage: $0 OUT [SRC]" >&2; exit 2; }
OUT=$1
SRC=${2:-work/desmume-watch}

[ -d "$SRC/.git" ] || git clone "$REPO" "$SRC"
git -C "$SRC" fetch --quiet origin
git -C "$SRC" checkout --quiet --force "$BASE"
git -C "$SRC" apply "$PATCH"

# The Makefile does not track header dependencies, so a stale object would miss the
# MMU.h hook. Always rebuild from scratch.
make -C "$SRC/desmume/src/frontend/libretro" clean >/dev/null
make -C "$SRC/desmume/src/frontend/libretro" -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

for f in desmume_libretro.dylib desmume_libretro.so; do
    if [ -f "$SRC/desmume/src/frontend/libretro/$f" ]; then
        mkdir -p "$(dirname "$OUT")"
        cp "$SRC/desmume/src/frontend/libretro/$f" "$OUT"
        echo "$OUT"
        exit 0
    fi
done
echo "no core built in $SRC/desmume/src/frontend/libretro" >&2
exit 1
