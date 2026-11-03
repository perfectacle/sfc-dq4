"""읽은 롬 바이트 캐시(dq4readset)의 건전성 검사. 형식은 sfc/dq4/docs/dq4-readset-format.md.

가벼운 장면 두 개(전원부터 서장 첫 장면까지, 그 상태에서 버튼을 눌러 걷고 창을 여는 것)마다:

  결정성  같은 장면을 두 번 돌리면 출력(세이브스테이트는 롬 이름을 지운 해시)과 읽은 집합이 같다
  밖      읽은 집합과 키에 든 머리 밖 바이트를 모두 뒤집은 롬(머리 체크섬 $7FDC~$7FDF 도 뒤집음)으로 새로 돌려도
          출력·읽은 집합이 같다
  적중    그 롬으로 캐시를 켜고 돌리면 돌리지 않고 맞으며, 펼친 출력이 새로 돌린 출력과 같다
  안      읽은 집합 안 바이트 하나를 바꾸면 캐시가 빗나간다
  HDMA    게임 장면의 HDMA 표 첫 바이트가 롬이면 읽은 집합에 들어 있다

field 장면에서는 캐시를 켠 채 롬 밖 입력을 바꿔 본다: 환경 변수 값 하나, 에뮬레이터 명령줄 하나, 출발 상태 내용을
바꾸면 빗나가고, 출발 상태 파일을 다른 경로로 옮기기만 하면 맞는다.

합성 장면(lua/dq4readsetsynth.lua): 롬에 HDMA 표를 쓰고 켜며, Lua 로 롬을 읽는다. 표 바이트와 Lua 가 읽은 롬
바이트가 모두 읽은 집합에 들어야 한다(카운터가 HDMA 를 잡는가, 머리말이 emu.read 를 감싸는가).

캐시는 --out 아래 따로 두어(Store) 공유 캐시를 건드리지 않는다.

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
import dq4mesen as mesen  # noqa: E402
import dq4readset as rs  # noqa: E402

KEYED_HEADER = [i for h in rs.HEADER for i in range(h.start, h.stop)]
SYNTH_LUA = HERE / 'lua' / 'dq4readsetsynth.lua'
SYNTH_READ = [*range(0x3F0000, 0x3F0005), *range(0x3F0010, 0x3F0014), *range(0x3F0020, 0x3F0024), 0x3F0030, 0x3F0031]
# 서장 첫 장면에서: 말 걸기·명령 창 열고 닫기·걷기
FIELD_PRE = 'wait:60,a:6,wait:90,a:6,wait:90,b:6,wait:60,down:24,wait:20,left:24,wait:20,a:6,wait:60,b:6,wait:60,up:24'


def scenes(libdir, start):
    """(이름, Lua, 환경). field 는 boot 가 만든 상태에서 시작한다."""
    field = {'LIBDIR': libdir, 'STATE': str(start), 'PRE': FIELD_PRE, 'SHOTS': '300,600', 'VRAMDUMP': '600',
             'MAXF': '610'}
    return [('boot', walk.pc.MKSTATE, {'LIBDIR': libdir, **walk.PROLOGUE_START}),
            ('field', walk.MSG, field)]


class Runner:
    def __init__(self, mesence, store):
        self.mesence, self.store = mesence, store

    def __call__(self, rom, script, env, dest, cache=False, extra=mesen.ARGS, timeout=600):
        """(정보, 지금 롬과 맞는 항목, 출력 해시, HDMA 줄). cache 가 거짓이면 캐시를 읽지 않고 돌린다(쓰기는 함)."""
        full = {k: v for k, v in os.environ.items() if k not in walk.LUA_ENV}
        full.update(env, SHOT_DIR=str(dest), READSET_HDMA='1')
        old = {k: os.environ.get(k) for k in ('DQ4_READSET', 'DQ4_READSET_VERIFY')}
        os.environ.update(DQ4_READSET='' if cache else 'off', DQ4_READSET_VERIFY='0')
        try:
            shutil.rmtree(dest, ignore_errors=True)
            info = rs.run(self.mesence, rom, script, dest, full, timeout=timeout, cwd=dest, store=self.store,
                          extra=extra)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        entry = rs.find(self.store.entries(info['key']), Path(rom).read_bytes())
        outputs = rs.tree_hash(dest, skip=(rs.ENTRY, rs.OUT, rs.HDMA))
        hdma = (dest / rs.HDMA).read_text().split('\n') if (dest / rs.HDMA).exists() else []
        return info, entry, outputs, [line for line in hdma if line.strip()]


def differ(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))[:6]


def check_scene(go, rom_path, name, script, env, out):
    problems = []
    data = Path(rom_path).read_bytes()
    info, entry, ref, hdma = go(rom_path, script, env, out / f'{name}-a')
    if entry is None:
        return {'name': name, 'status': 'failed', 'problems': [f'읽은 집합을 얻지 못함(종료 코드 {info["returncode"]})']}
    ranges = rs.unpack(entry['ranges'])
    _, entry2, again, hdma2 = go(rom_path, script, env, out / f'{name}-b')
    if again != ref or entry2 is None or entry2['ranges'] != entry['ranges']:
        problems.append(f'결정성: 같은 장면 두 번이 다름 {differ(ref, again)}')
    keep = bytearray(len(data))
    for s, n in ranges:
        keep[s:s + n] = b'\1' * n
    for i in KEYED_HEADER:
        keep[i] = 1
    flipped = bytes(b ^ 0xFF if not k else b for b, k in zip(data, keep))
    rom_out = out / f'{name}-outside.sfc'
    rom_out.write_bytes(flipped)
    _, entry3, outside, hdma3 = go(rom_out, script, env, out / f'{name}-outside')
    if outside != ref:
        problems.append(f'밖: 새로 돌린 출력이 다름 {differ(ref, outside)}')
    if entry3 is None or entry3['ranges'] != entry['ranges']:
        problems.append('밖: 읽은 집합이 다름')
    hit, _, cached, _ = go(rom_out, script, env, out / f'{name}-outside-cached', cache=True)
    if not hit['cached']:
        problems.append('적중: 읽은 집합 밖만 바꾼 롬에서 캐시가 빗나감')
    elif cached != outside:
        problems.append(f'적중: 펼친 출력이 새로 돌린 출력과 다름 {differ(outside, cached)}')
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
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'readset': sum(n for _, n in ranges), 'ranges': len(ranges), 'flipped': len(data) - sum(keep),
            'checksum_flipped': all(not keep[i] for i in rs.CHECKSUM), 'hdma_tables': len(tables)}


def check_inputs(go, rom, script, env, out):
    """캐시를 켠 채 롬 밖 입력을 하나씩 바꾼다. 앞서 같은 입력으로 돈 항목이 있으므로 원래 입력이면 맞아야 한다."""
    problems = []
    if not go(rom, script, env, out / 'in-same', cache=True)[0]['cached']:
        problems.append('같은 입력인데 빗나감')
    state = Path(env['STATE'])
    moved = out / 'moved-state' / 'start.mss'
    moved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(state, moved)
    if not go(rom, script, dict(env, STATE=str(moved)), out / 'in-moved', cache=True)[0]['cached']:
        problems.append('출발 상태를 다른 경로로 옮겼을 뿐인데 빗나감')
    changed = out / 'changed-state' / 'start.mss'
    changed.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(state.read_bytes())
    data[-1] ^= 0xFF
    changed.write_bytes(data)
    cases = {'환경 변수 MAXF': (dict(env, MAXF='611'), mesen.ARGS),
             '에뮬레이터 명령줄': (env, (*mesen.ARGS, '--Snes.EnableStrictBoardMappings=false')),
             '출발 상태 내용': (dict(env, STATE=str(changed)), mesen.ARGS)}
    for i, (what, (e, extra)) in enumerate(cases.items()):
        if go(rom, script, e, out / f'in-{i}', cache=True, extra=extra, timeout=120)[0]['cached']:
            problems.append(f'{what} 을 바꿨는데 맞음')
    return {'name': 'inputs', 'status': 'failed' if problems else 'passed', 'problems': problems,
            'cases': ['같은 입력', '옮긴 상태', *cases]}


def check_synth(go, rom, libdir, out):
    info, entry, _, _ = go(rom, SYNTH_LUA, {'LIBDIR': libdir}, out / 'synth')
    if entry is None:
        return {'name': 'synth', 'status': 'failed', 'problems': [f'읽은 집합을 얻지 못함(종료 코드 {info["returncode"]})']}
    read = {i for s, n in rs.unpack(entry['ranges']) for i in range(s, s + n)}
    missing = [f'{i:06X}' for i in SYNTH_READ if i not in read]
    return {'name': 'synth', 'status': 'failed' if missing else 'passed',
            'problems': [f'HDMA 표·Lua 가 읽은 롬 바이트가 읽은 집합에 없음 {missing}'] if missing else []}


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
    go = Runner(mesence, rs.Store(out / 'cache'))
    rom = a.rom.resolve()
    results = []

    def report(r):
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    for name, script, env in scenes(libdir, out / 'boot-a' / 'start.mss'):
        report(check_scene(go, rom, name, script, env, out))
        if name == 'boot' and not (out / 'boot-a' / 'start.mss').exists():
            break
        if name == 'field':
            report(check_inputs(go, rom, script, env, out))
    report(check_synth(go, rom, libdir, out))
    ok = all(r.get('status') == 'passed' for r in results) and len(results) == 4
    print(json.dumps({'status': 'passed' if ok else 'failed'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
