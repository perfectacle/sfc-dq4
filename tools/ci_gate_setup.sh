#!/usr/bin/env bash
# 배포 관문 워크플로(.github/workflows/guard-shards.yml, roms 는 composite action .github/actions/ci-roms 가 부름)의 러너 준비. 저장소 뿌리에서 부른다.
#
#   tools/ci_gate_setup.sh roms    암호화한 롬 묶음을 받아 rom/ 에 풀고, 롬 SHA-256 목록을 $RUNNER_TEMP/rom-hashes.txt 에
#                                  (CI_ROM_TOKEN: 에셋 저장소 읽기 토큰, CI_ROM_AGE_KEY: age 개인 키)
#   tools/ci_gate_setup.sh tools   asar·Galmuri·libretro 코어를 $RUNNER_TEMP/gate-tools 에 두고 ASAR·DQ4_GALMURI·DQ4_CORES 를
#                                  $GITHUB_ENV 에(코어는 actions/cache 가 그 폴더를 되살렸으면 다시 빌드하지 않는다)
#
# 시크릿은 환경 변수로만 받는다. 이 스크립트는 그 값을 찍지 않으며 set -x 를 켜지 않는다.
set -euo pipefail
set +x

ASSETS_REPO=perfectacle/sfc-dq4-assets
ROM_TAG=ci-roms-v1
ROM_FILE=ci-roms-v1.tar.zst.age
ROMS=(dq5.sfc dq6.sfc dq4.nes dq4-rev0.nes dq4ds.nds dq4ds-kr.nds dq4ds-kr.ml1 dq4ds-kr.sav)
# 2024-03-13 의 v1.91. 로컬 체크아웃이 쓰는 asar 와 같은 판
ASAR_COMMIT=6a6dbdaed8cb773e583052ce4f66375bd896c3a1
# 2026-07-12 의 v2.40.4. 빌드가 읽는 .bdf 는 로컬 DQ4_GALMURI 의 것과 SHA-256 이 같다
GALMURI_URL=https://github.com/quiple/galmuri/releases/download/v2.40.4/Galmuri-v2.40.4.zip
GALMURI_SHA256=c8b3d9861a62ae73c8b1178091401cd79994812437ef386413f6dd54856e60e7

: "${RUNNER_TEMP:?RUNNER_TEMP 가 없음(GitHub Actions 러너에서 부른다)}"
TOOLS="$RUNNER_TEMP/gate-tools"

need_secret() {
  if [ -z "${!1:-}" ]; then
    echo "::error::시크릿 $1 이 설정되지 않음. sfc/dq4/docs/dq4-release-check-format.md 「CI 에서 돌리기」 를 본다"
    exit 1
  fi
}

roms() {
  need_secret CI_ROM_TOKEN
  need_secret CI_ROM_AGE_KEY
  local key="$RUNNER_TEMP/ci-age.key" bundle="$RUNNER_TEMP/$ROM_FILE"
  if ! grep -qE '^AGE-SECRET-KEY-' <<<"$CI_ROM_AGE_KEY"; then
    echo "::error::CI_ROM_AGE_KEY 에 age 개인 키 줄(AGE-SECRET-KEY-…)이 없음"
    exit 1
  fi
  # 여러 줄 시크릿이라 개인 키 줄도 따로 가린다
  grep -E '^AGE-SECRET-KEY-' <<<"$CI_ROM_AGE_KEY" | sed 's/^/::add-mask::/'
  (umask 077 && printf '%s\n' "$CI_ROM_AGE_KEY" >"$key")
  GH_TOKEN="$CI_ROM_TOKEN" gh release download "$ROM_TAG" -R "$ASSETS_REPO" -p "$ROM_FILE" -D "$RUNNER_TEMP" --clobber
  mkdir -p rom
  age -d -i "$key" "$bundle" | zstd -dc | tar -x --no-same-owner -C rom -f -
  rm -f "$key" "$bundle"
  for f in "${ROMS[@]}"; do
    [ -s "rom/$f" ] || { echo "::error::롬 묶음에 $f 가 없음"; exit 1; }
  done
  (cd rom && sha256sum -- *) >"$RUNNER_TEMP/rom-hashes.txt"
  echo "롬 ${#ROMS[@]}개를 rom/ 에 풂"
}

tools() {
  mkdir -p "$TOOLS"
  if [ ! -x "$TOOLS/asar/bin/asar" ]; then
    local src="$RUNNER_TEMP/asar-src"
    rm -rf "$src" && mkdir -p "$src"
    git -C "$src" init -q
    git -C "$src" remote add origin https://github.com/RPGHacker/asar
    git -C "$src" fetch -q --depth 1 origin "$ASAR_COMMIT"
    git -C "$src" -c advice.detachedHead=false checkout -q FETCH_HEAD
    [ "$(git -C "$src" rev-parse HEAD)" = "$ASAR_COMMIT" ] || { echo "::error::asar 커밋이 다름"; exit 1; }
    cmake -S "$src/src" -B "$src/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$src/build" --target asar-standalone -j "$(nproc)" >/dev/null
    mkdir -p "$TOOLS/asar/bin"
    cp "$src/build/asar/bin/asar" "$TOOLS/asar/bin/asar"
    rm -rf "$src"
  fi
  "$TOOLS/asar/bin/asar" --version | head -1

  local zip="$RUNNER_TEMP/galmuri.zip"
  curl -fsSL -o "$zip" "$GALMURI_URL"
  echo "$GALMURI_SHA256  $zip" | sha256sum -c --quiet -
  rm -rf "$TOOLS/galmuri" && mkdir -p "$TOOLS/galmuri"
  unzip -q -j -o "$zip" '*.bdf' -d "$TOOLS/galmuri"
  rm -f "$zip"

  DQ4_CORES="$TOOLS/cores" uv run --frozen python sfc/dq4/tools/dq4cores.py

  {
    echo "ASAR=$TOOLS/asar/bin/asar"
    echo "DQ4_GALMURI=$TOOLS/galmuri"
    echo "DQ4_CORES=$TOOLS/cores"
  } >>"$GITHUB_ENV"
}

case "${1:-}" in
  roms) roms ;;
  tools) tools ;;
  *) echo "사용: $0 roms|tools" >&2; exit 2 ;;
esac
