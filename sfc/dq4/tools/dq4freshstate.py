"""검사 롬으로 만든 출발 세이브스테이트(MesenCE 헤드리스).

세이브스테이트는 만든 롬의 WRAM·SPC·스택을 그대로 담아서, 다른 빌드로 만든 상태를 불러오면 바뀐 코드 자리로 돌아가
폭주할 수 있다. 그래서 장면 검사는 출발 상태를 검사하는 롬에서 직접 만들고, 상태 옆 곁 파일(`.rom-sha1`)에 그 롬과
상태 파일의 SHA-1 을 적어 둔다. 롬이 다르거나, 곁 파일이 없거나(손으로 고른 `work/state/*.mss`), 상태 파일이 적힌 뒤
바뀌었으면 `require_same_build` 가 불러오기 전에 멈춘다.

| 롬 | 출발 상태 |
| --- | --- |
| 1장 롬(머리 「DRAGONQUEST4」, dq4chapter1.py build 뒤) | 서장 끝(dq4ch1walkcheck 의 롬 SHA-1 별 캐시). 새 게임이 DQ4 서장으로 가므로 DQ5 선실은 만들 수 없다 |
| 그 밖(원본 DQ5, dq4groupbuild 롬 등 DQ5 새 게임이 남은 롬) | 배 선실 `17/00`(lua/dq4shipstate.lua, 같은 캐시 폴더) |

  python sfc/dq4/tools/dq4freshstate.py --rom work/dq4-groups/groups.sfc --out work/fresh   # 만들어 보기
"""

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4mesen as mesen  # noqa: E402

SHIP_LUA = HERE / 'lua' / 'dq4shipstate.lua'
# 1장 롬 머리(dq4chapter1.TITLE). 이 모듈이 dq4chapter1 의 무거운 import 를 끌어오지 않게 글자로 둔다
CHAPTER1_TITLE = b'DRAGONQUEST4'
HEADER = 0x7FC0
SIDECAR = '.rom-sha1'


def rom_sha1(data):
    return hashlib.sha1(data).hexdigest()


def kind_of(data):
    """'chapter1' 이면 서장 끝, 'ship' 이면 배 선실."""
    return 'chapter1' if data[HEADER:HEADER + len(CHAPTER1_TITLE)] == CHAPTER1_TITLE else 'ship'


def sidecar(state):
    return Path(f'{state}{SIDECAR}')


def stamp(state, data):
    """곁 파일에 「rom <롬 SHA-1>」·「state <상태 SHA-1>」 두 줄을 쓴다."""
    state = Path(state)
    sidecar(state).write_text(f'rom {rom_sha1(data)}\nstate {rom_sha1(state.read_bytes())}\n', encoding='utf-8')
    return state


def require_same_build(state, data):
    """state 가 data 롬으로 만든 그대로가 아니면 SystemExit. 불러온 뒤 폭주한 결과를 검사 결과로 믿지 않게 불러오기
    전에 멈춘다."""
    state, tag = Path(state), sidecar(state)
    if not state.is_file():
        raise SystemExit(f'세이브스테이트 없음: {state}')
    if not tag.is_file():
        raise SystemExit(f'{state}: 어느 롬으로 만들었는지 모름({tag.name} 없음). 검사 롬으로 만든 상태만 씀 — '
                         '--state 를 빼면 검사 롬으로 만든다')
    made = dict(line.split(' ', 1) for line in tag.read_text(encoding='utf-8').splitlines() if ' ' in line)
    if made.get('rom') != rom_sha1(data):
        raise SystemExit(f'{state}: 롬 {made.get("rom", "?")[:12]} 로 만든 상태인데 검사 롬은 {rom_sha1(data)[:12]}'
                         '(다른 빌드)')
    if made.get('state') != rom_sha1(state.read_bytes()):
        raise SystemExit(f'{state}: {tag.name} 를 적은 뒤 상태 파일이 바뀜')
    return state


def _ship(mesence, rom, out, cache):
    import dq4ch1walkcheck as walk
    # 서장 캐시와 같은 파일 목록(walk.run·dq4mesen.run·lua 전부·uv.lock·MesenCE)에 이 모듈을 더한다
    key = walk.code_key(mesence, Path(__file__), 'ship')
    state = out / 'ship.mss'
    hit = cache.get('ship', key, '.mss', state)
    if hit:
        return hit[0]
    walk.run(mesence, rom, SHIP_LUA, out, {'SAVE': 'ship.mss'}, 900)
    log = out / 'ship.txt'
    text = log.read_text(encoding='utf-8') if log.exists() else ''
    if not state.exists() or 'map 17/00' not in text:
        raise SystemExit(f'배 선실 상태를 만들지 못함({rom}): {text.strip()[-200:] or "기록 없음"}')
    cache.put('ship', key, '.mss', state, {'log': text.strip()})
    return state


def _chapter1(mesence, rom, data, out, cache):
    import dq4ch1walkcheck as walk
    state, r = walk.prologue(mesence, rom, data, out, walk.SEGMENTS, cache)
    if r['status'] != 'passed':
        raise SystemExit(f'서장 끝 상태를 만들지 못함({rom}): {r["problems"]}')
    return state


def make(mesence, rom, out):
    """rom 으로 만든 출발 세이브스테이트(SHA-1 을 적은 것)의 경로. 같은 롬·같은 코드로 만든 캐시가 있으면 그것을 쓴다."""
    import dq4ch1walkcheck as walk
    rom = Path(rom).resolve()
    data = rom.read_bytes()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache = walk.StateCache(data)
    state = _chapter1(mesence, rom, data, out, cache) if kind_of(data) == 'chapter1' else _ship(mesence, rom, out,
                                                                                               cache)
    final = out / 'start.mss'
    if state != final:
        shutil.copyfile(state, final)
    return stamp(final, data)


def add_argument(ap):
    ap.add_argument('--state', type=Path, help='이 롬으로 만든 출발 세이브스테이트(dq4freshstate 가 SHA-1 을 적은 것). '
                    '빼면 검사 롬으로 만든다(캐시)')


def resolve(state, mesence, rom, out):
    """--state 를 주면 같은 빌드인지 보고, 안 주면 rom 으로 만든다. 돌려준 경로는 rom 으로 만든 것이다."""
    if state:
        return require_same_build(Path(state).resolve(), Path(rom).read_bytes())
    return make(mesence, rom, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    print(make(mesence, a.rom, a.out))


if __name__ == '__main__':
    main()
