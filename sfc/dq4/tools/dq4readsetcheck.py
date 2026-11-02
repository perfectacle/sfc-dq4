"""읽은 롬 바이트 캐시(dq4readset)의 건전성 검사. 형식은 sfc/dq4/docs/dq4-readset-format.md.

가벼운 장면 두 개(전원부터 서장 첫 장면까지, 그 상태에서 버튼을 눌러 필드·창을 거치는 것)마다:

  결정성  같은 장면을 두 번 돌리면 출력(세이브스테이트는 롬 이름을 지운 해시)과 읽은 집합이 같다
  밖      읽은 집합과 롬 머리($7FB0~$7FFF) 밖 바이트를 모두 뒤집은 롬으로 돌려도 출력·읽은 집합이 같고, 캐시가 맞는다
  안      읽은 집합 안 바이트 하나를 바꾸면 캐시가 빗나간다
  HDMA    HDMA 표 첫 바이트가 롬이면 읽은 집합에 들어 있다(카운터가 HDMA 읽기도 잡는지)

그리고 롬 HDMA 표를 일부러 켜는 장면(lua/dq4readsethdma.lua)에서 표 다섯 바이트가 모두 읽은 집합에 드는지 본다.
게임 장면에는 롬을 표로 쓰는 HDMA 가 드물어 위 HDMA 항목만으로는 확인이 안 될 수 있다.

캐시는 --out 아래 따로 두어(DQ4_READSET_CACHE) 공유 캐시를 건드리지 않는다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4readsetcheck.py --rom work/ch1/dq4-ch1.sfc --out work/readsetcheck
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4ch1walkcheck as walk  # noqa: E402
import dq4readset as rs  # noqa: E402

HEADER = range(0x7FB0, 0x8000)
HDMA_LUA = HERE / 'lua' / 'dq4readsethdma.lua'
HDMA_TABLE = range(0x3F0000, 0x3F0005)
# 서장 첫 장면에서: 말 걸기·명령 창 열고 닫기·걷기
FIELD_PRE = 'wait:60,a:6,wait:90,a:6,wait:90,b:6,wait:60,down:24,wait:20,left:24,wait:20,a:6,wait:60,b:6,wait:60,up:24'


def scenes(libdir, start):
    """(이름, Lua, 환경). field 는 boot 가 만든 상태에서 시작한다."""
    field = {'LIBDIR': libdir, 'STATE': str(start), 'PRE': FIELD_PRE, 'SHOTS': '300,600', 'VRAMDUMP': '600',
             'MAXF': '610'}
    return [('boot', walk.pc.MKSTATE, {'LIBDIR': libdir, **walk.PROLOGUE_START}),
            ('field', walk.MSG, field)]


def run_once(mesence, rom, script, env, dest, store):
    full = {k: v for k, v in os.environ.items() if k not in walk.LUA_ENV}
    full.update(env, SHOT_DIR=str(dest), READSET_HDMA='1')
    shutil.rmtree(dest, ignore_errors=True)
    info = rs.run(mesence, rom, script, dest, full, timeout=600, cwd=dest, store=store)
    entry = rs.find(store.entries(info['key']), Path(rom).read_bytes())
    outputs = rs.tree_hash(dest, skip=(rs.ENTRY, rs.OUT, rs.HDMA))
    hdma = (dest / rs.HDMA).read_text().split('\n') if (dest / rs.HDMA).exists() else []
    return info, entry, outputs, [line for line in hdma if line.strip()]


def check_scene(mesence, rom_path, name, script, env, out, store):
    problems = []
    data = Path(rom_path).read_bytes()
    os.environ['DQ4_READSET'] = 'off'
    info, entry, ref, hdma = run_once(mesence, rom_path, script, env, out / f'{name}-a', store)
    if entry is None:
        return {'name': name, 'problems': ['읽은 집합을 얻지 못함(장면이 emu.stop 에 닿지 않음)']}, None
    ranges = rs.unpack(entry['ranges'])
    _, entry2, again, hdma2 = run_once(mesence, rom_path, script, env, out / f'{name}-b', store)
    if again != ref or entry2 is None or entry2['ranges'] != entry['ranges']:
        problems.append('결정성: 같은 장면 두 번의 출력·읽은 집합이 다름')
    keep = bytearray(len(data))
    for s, n in ranges:
        keep[s:s + n] = b'\1' * n
    for i in HEADER:
        keep[i] = 1
    flipped = bytes(b ^ 0xFF if not k else b for b, k in zip(data, keep))
    rom_out = out / f'{name}-outside.sfc'
    rom_out.write_bytes(flipped)
    if rs.find([entry], flipped) is None:
        problems.append('밖: 읽은 집합 밖만 바꾼 롬에서 캐시가 빗나감')
    _, entry3, outside, hdma3 = run_once(mesence, rom_out, script, env, out / f'{name}-outside', store)
    if outside != ref:
        problems.append(f'밖: 출력이 다름 {sorted(k for k in set(ref) | set(outside) if ref.get(k) != outside.get(k))}')
    if entry3 is None or entry3['ranges'] != entry['ranges']:
        problems.append('밖: 읽은 집합이 다름')
    rom_out.unlink()
    inside = bytearray(data)
    s, n = max(ranges, key=lambda r: r[1])
    inside[s + n // 2] ^= 0x01
    if rs.find([entry], bytes(inside)) is not None:
        problems.append('안: 읽은 집합 안 바이트를 바꿨는데 캐시가 맞음')
    tables = sorted(set(hdma + hdma2 + hdma3))
    missed = [t for t in tables if t.endswith(' 0')]
    if missed:
        problems.append(f'HDMA: 롬 표 첫 바이트가 읽은 집합에 없음 {missed[:8]}')
    os.environ.pop('DQ4_READSET')
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'readset': sum(n for _, n in ranges), 'ranges': len(ranges), 'flipped': len(data) - sum(keep),
            'hdma_tables': len(tables)}, out / f'{name}-a'


def check_hdma(mesence, rom, libdir, out, store):
    os.environ['DQ4_READSET'] = 'off'
    info, entry, _, _ = run_once(mesence, rom, HDMA_LUA, {'LIBDIR': libdir}, out / 'hdma', store)
    os.environ.pop('DQ4_READSET')
    if entry is None:
        return {'name': 'hdma', 'status': 'failed', 'problems': ['읽은 집합을 얻지 못함']}
    read = {i for s, n in rs.unpack(entry['ranges']) for i in range(s, s + n)}
    missing = [f'{i:06X}' for i in HDMA_TABLE if i not in read]
    return {'name': 'hdma', 'status': 'failed' if missing else 'passed',
            'problems': [f'HDMA 표 바이트가 읽은 집합에 없음 {missing}'] if missing else []}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    out = a.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    store = rs.Store(out / 'cache')
    rom = a.rom.resolve()
    results = []
    for name, script, env in scenes(libdir, out / 'boot-a' / 'start.mss'):
        r, _ = check_scene(mesence, rom, name, script, env, out, store)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        if name == 'boot' and not (out / 'boot-a' / 'start.mss').exists():
            break
    r = check_hdma(mesence, rom, libdir, out, store)
    results.append(r)
    print(json.dumps(r, ensure_ascii=False), flush=True)
    ok = all(r.get('status') == 'passed' for r in results) and len(results) == 3
    print(json.dumps({'status': 'passed' if ok else 'failed'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
