"""DQ5 실내 맵마다 OBJ 팔레트 줄·인물 슬롯 수·OBJ VRAM 끝을 MesenCE에서 잰다. 결과는 dq5-graphics-format.md 「맵마다 남는 OBJ 팔레트 줄과 VRAM」.

선실 세이브스테이트에서 dq5warp.lua 로 실내 맵 346곳(들어갈 칸은 dq5mapmusic.entry_cells)에 들어가, lua/dq5objsweep.lua 로
그 맵에 있는 동안(SETTLE 뒤 TEST 의 걷기까지) 매 프레임 보이는 OAM 의 팔레트별 수, 인물 슬롯 수, $1995 를 모은다.
끝 프레임의 CGRAM OBJ 줄 4~7 이 04:96D6 과 같은지, 그 맵의 01:9A12 항목이 덮는 OBJ 줄도 함께 적는다.
결과는 OUT/<맵>/ 과 OUT/summary.json. MESENCE 가 있어야 한다.

  python sfc/dq5/tools/dq5objsweep.py rom/dq5.sfc work/state/ship.mss work/objsweep [--maps 02/06,04/06]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5mapmusic import entry_cells  # noqa: E402
from dq5sound import map_songs  # noqa: E402

PROBE = os.path.join(HERE, 'lua', 'dq5objsweep.lua')
WALK = 'left:30,right:30,up:30,down:30,wait:30'
# 탈것 타일이 올라오는 첫 번호(01:C4BE 의 $00 = VRAM $7800, 16:F7DD 의 7E:1997 = 180). OBJ 이름 표는 512타일.
VEHICLE_TILE, OBJ_TILES = 0x180, 0x200


def parse(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        k, _, v = line.strip().partition('=')
        out[k] = v
    return out


def look(rom, name, d):
    """한 맵의 결과. 실행이 맵에 닿지 못했으면 None."""
    path = os.path.join(d, 'objsweep.txt')
    if not os.path.exists(path):
        return None
    got = parse(path)
    if int(got['frames']) == 0:
        return None
    bc, bd = (int(v, 16) for v in name.split('_'))
    cgram = open(os.path.join(d, 'final.cgram'), 'rb').read()
    line = lambda p: [cgram[256 + (p * 16 + i) * 2] | cgram[257 + (p * 16 + i) * 2] << 8 for i in range(1, 16)]  # noqa: E731
    base = [[rom.u16(S.OBJ_PALETTES + (p * 16 + i) * 2) for i in range(1, 16)] for p in range(8)]
    covered = sorted({e['line'] - 8 for e in S.map_palettes(rom)
                      if 8 <= e['line'] <= 15 and e['bc'] == bc and e['bd'] in (bd, 0xFF)})
    gfx = got['gfx'].split()
    return {'map': f'{bc:02X}/{bd:02X}', 'frames': int(got['frames']), 'slots': int(got['slots']),
            'sets': sorted({f'{S.gfx_set(rom, int(g, 16)):02X}' for g in gfx}),
            'v1995': int(got['v1995']), 'v1997': int(got['v1997']),
            'oam': {p: int(got[f'pal{p}']) for p in range(8) if int(got[f'pal{p}'])},
            'oam_tile': {p: int(got[f'tile{p}']) for p in range(8) if int(got[f'pal{p}'])},
            'cgram_same': [line(p) == base[p] for p in range(8)], 'map_lines': covered}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('state')
    ap.add_argument('out')
    ap.add_argument('--maps', help='쉼표로 구분한 BC/BD(기본은 실내 맵 전부)')
    ap.add_argument('--jobs', type=int, default=6)
    a = ap.parse_args()
    mesen = os.environ.get('MESENCE')
    if not mesen:
        ap.error('MESENCE 가 필요함')
    rom = Rom(open(a.rom, 'rb').read())
    maps = a.maps.split(',') if a.maps else [f'{bc:02X}/{bd:02X}' for bc, bd, _ in map_songs(rom)]
    cells = entry_cells(a.rom, maps, a.jobs)
    krlua = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    lib = os.path.abspath(os.path.join(a.out, 'warplib'))
    os.makedirs(lib, exist_ok=True)
    for name in ('lib.lua', 'probe'):
        if not os.path.lexists(os.path.join(lib, name)):
            os.symlink(os.path.join(krlua, name), os.path.join(lib, name))
    shutil.copyfile(os.path.join(HERE, 'lua', 'dq5warp.lua'), os.path.join(lib, 'boot.lua'))

    def run(m):
        d = os.path.abspath(os.path.join(a.out, m.replace('/', '_')))
        os.makedirs(d, exist_ok=True)
        env = dict(os.environ, LIBDIR=lib, STATE=os.path.abspath(a.state), SHOT_DIR=d, SETTLE='60', TEST=WALK, MAXF='1000',
                   TO=f'{m},{",".join(str(v) for v in cells[m])}')
        subprocess.run([mesen, '--testrunner', os.path.abspath(a.rom), PROBE, '--Snes.DisableFrameSkipping=true'], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return m, look(rom, m.replace('/', '_'), d)

    todo = [m for m in maps if m in cells]
    with ThreadPoolExecutor(a.jobs) as ex:
        rows = dict(ex.map(run, todo))
    done = [r for r in rows.values() if r]
    missed = sorted(m for m, r in rows.items() if r is None) + sorted(m for m in maps if m not in cells)
    summary = {'maps': len(maps), 'reached': len(done), 'missed': missed, 'rows': sorted(done, key=lambda r: r['map'])}
    with open(os.path.join(a.out, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f'맵 {len(maps)}곳 중 {len(done)}곳 도착, 못 간 곳 {len(missed)}: {" ".join(missed)}')
    if not done:
        return 1
    top = max(done, key=lambda r: r['slots'])
    many = max(done, key=lambda r: len(r['sets']))
    print(f'인물 슬롯 최대 {top["slots"]}({top["map"]}), 맵에 나온 세트 종류(센 프레임 합집합) 최대 {len(many["sets"])}({many["map"]})')
    for p in range(8):
        used = [r['map'] for r in done if p in r['oam']]
        lines = [r['map'] for r in done if p in r['map_lines']]
        moved = [r['map'] for r in done if not r['cgram_same'][p]]
        print(f'OBJ 팔레트 {p}: OAM 에 보인 맵 {len(used)}, 01:9A12 가 덮는 맵 {len(lines)}, 끝 CGRAM 이 04:96D6 과 다른 맵 {len(moved)}'
              + (f' ({" ".join(used[:12])}{" …" if len(used) > 12 else ""})' if p >= 4 and used else ''))
    free = sorted(done, key=lambda r: r['v1995'])
    print(f'$1995 최대 {free[-1]["v1995"]:03X}({free[-1]["map"]}) → 탈것 {VEHICLE_TILE:03X} 까지 {VEHICLE_TILE - free[-1]["v1995"]}타일, '
          f'최소 {free[0]["v1995"]:03X}({free[0]["map"]})')
    over = [r['map'] for r in done if any(t >= r['v1995'] and t < OBJ_TILES for t in r['oam_tile'].values())]
    print(f'$1995 이상 타일을 OAM 이 쓴 맵 {len(over)}: {" ".join(over[:20])}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
