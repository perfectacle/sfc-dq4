"""환경 훅 wrap 이 맵에 들어설 때와 필드로 나갈 때 매 프레임 루틴 7E:1AA6 을 맞게 두는지 보는 검사(MesenCE 헤드리스).
형식은 sfc/dq4/docs/dq4-environment-format.md 「물 애니메이션」.

wrap 은 15:F7D0(맵별 루틴 고르기)을 부른 뒤, $BE bit7(실내)이 켜져 있고 $BC/$BD 가 바꾼 맵이면 1AA6 을 물·분수·뚜껑
루틴으로 바꾼다. 필드에서도 $BC/$BD 는 막 나온 마을을 가리키므로 bit7 이 그 판단의 문턱이다. 그래서 장면마다 wrap 이
돌 때의 $BE 와 돌아온 뒤의 1AA6 을 lua/dq4wraplog.lua 로 적어 본다.
  leave   바트랜드(36/00) 출구에서 걸어 필드로: 01:9FD6 에서 bit7 꺼짐, 1AA6 은 필드 루틴 02:AB33 그대로
  walkin  필드에서 걸어 바트랜드로: 01:8F84 에서 bit7 켜짐, 물 루틴
  map-*   바꾼 맵(dq4environmentrom.MAPS) 하나하나에 필드 입구로 순간이동해 들어감: bit7 켜짐, 그 맵의 루틴(롬의 wrap 표에서
          읽은 물·분수·뚜껑, 어느 것도 아니면 15:F7D0 이 고른 것이 그대로 남아 우리 루틴이 아님). 새 그룹(GROUPS) 맵은 필드
          입구로 들어가야 하고, 그 밖의 맵(DQ5 그룹을 빌린 TARGETS)은 필드에서 닿지 않으면 이무르(실내)에서 들어간다
  reload  39/00 에서 지금 맵을 그 자리에서 다시 푸는 길(00:C71F → 01:98FC)을 한 번 태움: bit7 켜짐, 뚜껑 루틴 그대로

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4wrapcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/wrapcheck
  (--only map-burland,leave 는 그 장면만, --base 는 dq4heroblockcheck 의 출발 상태 hub/end.mss 를 다시 쓴다)
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from kr_patch.fc import ines

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4heroblockcheck as hb  # noqa: E402
from dq4environmentart import create_assets  # noqa: E402
from dq4environmentmap import prepare_maps  # noqa: E402
from dq4environmentrom import GROUPS, MAPS, ROUTINE_CALLS  # noqa: E402
from dq4environmentromcheck import _arrival  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from dq5map import lorom  # noqa: E402

DRIVER = HERE / 'lua' / 'dq4wraplog.lua'
FIELD_ROUTINE = 0x02AB33       # 필드의 매 프레임 루틴(바다 타일, 시각 색 02:AD2B → 01:A055)
FIELD_CALL, ENTER_CALL, RELOAD_CALL = 0x019FD6, 0x018F84, 0x0198FC
IMURU = '37/00,50,9'
EDGE = '36/00,28,80'           # 바트랜드 출구 바로 위. 여기서 아래로 걸으면 필드 (328,95) 에 선다
EDGE_WALK = 60
RELOAD = ('30-00', 230)        # 맵, 00:C71F 로 돌릴 프레임(도착 뒤 TEST 로 걷는 동안)
# dq5warp.lua 가 덮는 필드 입구 표·도착 표를 읽는 명령의 피연산자. 1장 롬은 두 표를 옮겼다
ENTRANCE_REF, ARRIVALS_REF = 0x2AFE12, 0x2AF394


def _r24(rom, addr):
    o = lorom(addr)
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def wrap_table(rom):
    """롬의 wrap 코드(dq4environmentrom.engine_code)를 읽어 wrap 주소와 맵마다 기대 루틴(None 이면 우리 루틴이 아님),
    우리 루틴 셋."""
    wrap = _r24(rom, ROUTINE_CALLS[0] + 1)
    for at in ROUTINE_CALLS:
        if rom[lorom(at)] != 0x22 or _r24(rom, at + 1) != wrap:
            raise ValueError(f'{at:06X} 가 wrap({wrap:06X})을 부르지 않음')
    # 문턱(어떤 맵에서 건너뛸지)의 바이트는 보지 않는다. 그 동작을 장면으로 보는 검사라 문턱을 바꾼 롬에서도 돌아야 한다.
    # 표 주소는 뒤쪽의 「JSL find / BCC / LDA waters,X / BEQ / CMP #$0002」 꼴에서 읽는다
    code = rom[lorom(wrap):lorom(wrap) + 0x60]
    if code[:4] != bytes((0x22, 0xD0, 0xF7, 0x15)):
        raise ValueError(f'wrap 이 15:F7D0 을 먼저 부르지 않음: {code[:4].hex()}')
    m = re.search(rb'\x22(...)\x90.\xBF(...)\xF0.\xC9\x02\x00\xF0.\xA9(..)\x80.\xA9(..)\x80.\xBF(...)\xF0.\xC2\x20\xA9(..)',
                  code, re.S)
    if not m:
        raise ValueError(f'wrap 의 루틴 고르기를 찾지 못함: {code.hex()}')
    find, waters, lids = (int.from_bytes(m[i], 'little') for i in (1, 2, 5))
    water, fountain, lid = (wrap & 0xFF0000 | int.from_bytes(m[i], 'little') for i in (3, 4, 6))
    targets = _r24(rom, find + 9)
    expected = {}
    for i, name in enumerate(MAPS):
        at = lorom(targets) + 2 * i
        if tuple(rom[at:at + 2]) != MAPS[name]:
            raise ValueError(f'{name}: wrap 표 {i}번이 {rom[at]:02X}/{rom[at + 1]:02X}, 기대 {MAPS[name]}')
        flag, dry = rom[lorom(waters) + 2 * i], rom[lorom(lids) + 2 * i]
        expected[name] = (fountain if flag == 2 else water) if flag else lid if dry else None
    return wrap, expected, {water, fountain, lid}


def parse(dest):
    """wrap.txt 의 wrap 실행마다 부른 자리·$BE·맵과 그 실행이 돌아온 뒤의 1AA6(돌아오지 않았으면 None), reload 표지."""
    text = (dest / 'wrap.txt').read_text() if (dest / 'wrap.txt').exists() else ''
    calls = []
    for line in text.splitlines():
        if (m := re.search(r'wrap from (\w+) BE=(\w+) BC=(\w+) BD=(\w+)', line)):
            calls.append({'from': int(m[1], 16), 'be': int(m[2], 16), 'map': (int(m[3], 16), int(m[4], 16)),
                          'routine': None})
        elif (m := re.search(r'back (\w+) .* 1AA6=(\w+)', line)) and calls and calls[-1]['routine'] is None \
                and int(m[1], 16) == calls[-1]['from'] + 4:
            calls[-1]['routine'] = int(m[2], 16)
    return calls, 'reload BE=' in text


def judge(calls, want_map, want_call, inside, want, ours):
    """want_map 에서 want_call 자리로 처음 돈 wrap 이 bit7 이 inside 인 채 돌고, 돌아온 뒤 1AA6 이 want 인지
    (want 가 None 이면 ours 가 아님). 그 뒤 맵을 나가며 도는 wrap 은 보지 않는다."""
    mine = [c for c in calls if c['map'] == want_map and c['from'] == want_call]
    if not mine:
        return [f'{want_map[0]:02X}/{want_map[1]:02X} 에서 {want_call:06X} 의 wrap 이 돌지 않음']
    c, problems = mine[0], []
    if bool(c['be'] & 0x80) != inside:
        problems.append(f"$BE={c['be']:02X}(bit7 {'꺼짐' if inside else '켜짐'})")
    got = c['routine']
    if got is None:
        problems.append('wrap 이 돌아오지 않음')
    elif want is None and got in ours or want is not None and got != want:
        problems.append(f"1AA6={got:06X}, 기대 {'우리 루틴이 아님' if want is None else f'{want:06X}'}")
    return problems


class Run:
    def __init__(self, mesence, rom, wrap, tables):
        self.mesence, self.rom, self.wrap, self.tables = mesence, rom, wrap, tables

    def warp(self, dest, state, to, **extra):
        env = {'WARPLUA': str(wc.WARP), 'STATE': str(state), 'TO': to, 'SAVE': 'end.mss', 'SETTLE': '60',
               'MAXF': '2000', 'WARPEXIT': f'{warp_exit(self.rom):X}', 'ANYWHERE': '1',
               'ROMPATCH': wc.NO_ENCOUNTERS, 'SET': wc.RNG, 'WRAP': f'{self.wrap:06X}', **self.tables, **extra}
        wc.run(self.mesence, self.rom, DRIVER, dest, env, 300, readset=True)
        log = (dest / 'warp.txt').read_text() if (dest / 'warp.txt').exists() else ''
        arrived = re.search(r'arrived map (\w\w)/(\w\w)', log)
        return dest / 'end.mss', (int(arrived[1], 16), int(arrived[2], 16)) if arrived else None

    def walk(self, dest, state, way, frames):
        env = {'STATE': str(state), 'DIR': way, 'WALKF': str(frames), 'SAVE': 'end.mss', 'ROMPATCH': wc.NO_ENCOUNTERS,
               'WRAP': f'{self.wrap:06X}'}
        wc.run(self.mesence, self.rom, DRIVER, dest, env, 120, readset=True)
        return dest / 'end.mss'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--dq4', default=Path('rom/dq4.nes'), type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', help='이 장면만(쉼표로 여럿: leave,walkin,reload,map-burland)')
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 출발 상태(dq4heroblockcheck 의 hub/end.mss)')
    ap.add_argument('--no-state-cache', action='store_true')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    began = time.monotonic()
    wrap, expected, ours = wrap_table(data)
    tables = {'ENTRANCE': f'{_r24(data, ENTRANCE_REF):06X}', 'ARRIVALS': f'{_r24(data, ARRIVALS_REF):06X}'}
    run = Run(mesence, rom, wrap, tables)
    cache = None if args.no_state_cache else wc.StateCache(data)
    base = args.base.resolve() if args.base else hb.make_base(mesence, rom, out, cache)[0]

    results = {}

    def done(name, problems, **info):
        results[name] = {'status': 'failed' if problems else 'passed', 'problems': problems, **info}
        print(json.dumps({'scene': name, **results[name]}, ensure_ascii=False), flush=True)

    imuru, at = run.warp(out / 'imuru', base, IMURU)
    if at != (0x37, 0x00):
        raise SystemExit('이무르에 들어서지 못함')
    edge, at = run.warp(out / 'edge', imuru, EDGE)
    if at != (0x36, 0x00):
        raise SystemExit('바트랜드 출구에 서지 못함')
    field = run.walk(out / 'leave', edge, 'down', EDGE_WALK)
    calls, _ = parse(out / 'leave')
    done('leave', judge(calls, (0x36, 0x00), FIELD_CALL, False, FIELD_ROUTINE, ours))
    if results['leave']['problems'] or not field.exists():
        raise SystemExit('필드에 서지 못해 나머지 장면을 돌리지 못함')

    want = expected.get
    scenes = {'walkin': None, 'reload': None, **{f'map-{n}': n for n in MAPS}}
    if args.only:
        keys = args.only.split(',')
        scenes = {k: v for k, v in scenes.items() if k in keys}
    prg = ines.prg(args.dq4.read_bytes())
    sources = {n: s for _, _, n, s, _, _, _ in prepare_maps(prg, create_assets(), MAPS)}

    def one(scene, name):
        dest = out / scene
        if scene == 'walkin':
            run.walk(dest, field, 'up', EDGE_WALK)
            calls, _ = parse(dest)
            return scene, judge(calls, (0x36, 0x00), ENTER_CALL, True, want('burland'), ours), {}
        if scene == 'reload':
            name, frame = RELOAD
            x, y = _arrival(sources[name])
            g, n = MAPS[name]
            _, at = run.warp(dest, field, f'{g:02X}/{n:02X},{x},{y}', RELOAD=str(frame),
                             TEST='left:40,up:40,right:40,down:40,wait:60')
            calls, fired = parse(dest)
            problems = [] if fired else ['00:C71F 로 돌리지 못함']
            problems += judge(calls, (g, n), RELOAD_CALL, True, want(name), ours)
            return scene, problems, {}
        g, n = MAPS[name]
        x, y = _arrival(sources[name])
        to = f'{g:02X}/{n:02X},{x},{y}'
        way = 'field'
        _, at = run.warp(dest, field, to)
        if at != (g, n) and name not in GROUPS:
            way = 'imuru'
            shutil.rmtree(dest)
            _, at = run.warp(dest, imuru, to)
        if at != (g, n):
            return scene, [f'{way} 에서 {to} 에 들어서지 못함'], {'way': way}
        calls, _ = parse(dest)
        first = next((c for c in calls if c['map'] == (g, n) and c['from'] == ENTER_CALL), None)
        return scene, judge(calls, (g, n), ENTER_CALL, True, want(name), ours), {
            'way': way, 'be': f"{first['be']:02X}" if first else None,
            'routine': f"{first['routine']:06X}" if first and first['routine'] is not None else None,
            'want': f'{want(name):06X}' if want(name) is not None else None}

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for scene, problems, info in pool.map(lambda kv: one(*kv), scenes.items()):
            done(scene, problems, **info)
    ok = all(r['status'] == 'passed' for r in results.values())
    report = {'status': 'passed' if ok else 'failed', 'seconds': round(time.monotonic() - began),
              'wrap': f'{wrap:06X}', 'tables': tables, 'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    ways = {}
    for r in results.values():
        ways[r.get('way', '-')] = ways.get(r.get('way', '-'), 0) + 1
    print(json.dumps({'status': report['status'], 'seconds': report['seconds'], 'scenes': len(results), 'ways': ways,
                      'failed': [k for k, r in results.items() if r['status'] != 'passed']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
