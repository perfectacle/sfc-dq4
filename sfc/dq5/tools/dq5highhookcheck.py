"""그룹 51·54 의 새 맵과 고층 목록 고르기 스텁(dq5exitreloc.py --high-hook-at)을 MesenCE 에서 밟아 확인한다.

원본에서 도구마다 패치를 만들어 함께 빌드한다(롬 k).
  dq5newmap.py        51/58 (51/55 의 레코드), 54/54 (54/53 의 레코드)
  dq5encounterwrite.py 두 새 맵의 속성(23:FDD6 목록)을 복사한 맵과 같은 값으로. 목록은 3D:8000 으로
  dq5exitreloc.py     51/58 의 영역 이동은 51/55 것, 54/54 는 54/53 것을 그대로. 고층 목록은 3F:E000,
                      01:9510 을 3F:F000 의 스텁으로
장면(배 선실 세이브스테이트에서 dq5warp.lua):
  new51 / old51 / orig51   51/58·51/55(k)·51/55(원본) (12,71) 에서 아래로 걸어 영역 이동 (12,72) 을 밟음 → 51/51
  new54 / old54 / orig54   54/54·54/53(k)·54/53(원본) (17,41) 에서 아래로 → 54/52
  other50 / orig50         50/51(k)·원본 (31,17) 에서 아래로 → 05/01. 스텁이 51·54 가 아닌 그룹을 원래 갈래로 보냄
  stay51                   51/58 (12,71) 에 서 있기만 함 → 그대로
  nohook51                 롬 n(새 맵·속성만, 출구 패치 없음)의 51/58 에서 같은 걸음. 결과만 적는다(대조)

  MESENCE=… python sfc/dq5/tools/dq5highhookcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5encounterwrite import MAP_SIZE, high_base, high_map_slots
from dq5encounterwrite import read as enc_read
from dq5exitcheck import command, dp86_allowed, require, run, warp_exit
from dq5map import Rom, lorom

HERE = Path(__file__).resolve().parent
COPIES = {'51/58': '51/55', '54/54': '54/53'}
EXIT_PLACES = ('--high-at', '3F:E000', '--high-hook-at', '3F:F000')
NEW = tuple(x for m in COPIES for x in ('--new-map', m))
# (이름, 롬, TO, TEST, 기대 맵·칸(None 이면 보지 않음))
CASES = [
    ('new51', 'k', '51/58,12,71,1', 'down:16', ('51/51', None)),
    ('old51', 'k', '51/55,12,71,1', 'down:16', ('51/51', None)),
    ('orig51', 'original', '51/55,12,71,1', 'down:16', ('51/51', None)),
    ('new54', 'k', '54/54,17,41,1', 'down:16', ('54/52', None)),
    ('old54', 'k', '54/53,17,41,1', 'down:16', ('54/52', None)),
    ('orig54', 'original', '54/53,17,41,1', 'down:16', ('54/52', None)),
    ('other50', 'k', '50/51,31,17,1', 'down:16', ('05/01', None)),
    ('orig50', 'original', '50/51,31,17,1', 'down:16', ('05/01', None)),
    ('stay51', 'k', '51/58,12,71,1', 'wait:16', ('51/58', (12, 71))),
    ('nohook51', 'n', '51/58,12,71,1', 'down:16', (None, None)),
]
# 새 맵 장면은 같은 걸음의 원본 장면과 도착 칸·층까지 같아야 한다.
PAIRS = {'new51': 'orig51', 'old51': 'orig51', 'new54': 'orig54', 'old54': 'orig54', 'other50': 'orig50'}


def save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def build_rom(original, out):
    rom = Rom(original.read_bytes())
    manifests = []
    newmap = out / 'k-newmap.json'
    save(newmap, {'format': 'dq5newmap/1', 'maps': [{'map': m, 'record': {'copy': c}} for m, c in COPIES.items()]})
    command('dq5newmap.py', original, 'patch', newmap, '-o', out / 'k-newmap.dq5patch.json')
    command('dq5newmap.py', original, 'check', newmap)
    manifests.append(out / 'k-newmap.dq5patch.json')
    slots = high_map_slots(rom, high_base(rom))
    rows = []
    for m, c in COPIES.items():
        raw = enc_read(rom, slots[tuple(int(v, 16) for v in c.split('/'))], MAP_SIZE)
        rows.append({'map': m, 'areas': list(raw[:3]), 'tail': list(raw[3:6])})
    enc = out / 'k-encounter.json'
    save(enc, {'format': 'dq5encounter/1', 'maps': rows})
    command('dq5encounterwrite.py', original, 'patch', enc, '-o', out / 'k-encounter.dq5patch.json',
            '--high-at', '3D:8000')
    manifests.append(out / 'k-encounter.dq5patch.json')
    bare = out / 'n.sfc'
    command('dq5build.py', original, 'build', *manifests, '-o', bare, '--ips', out / 'n.ips')
    exits = out / 'k-exits.json'
    command('dq5exitreloc.py', original, 'dump', '-o', exits, *NEW)
    table = json.loads(exits.read_text(encoding='utf-8'))
    lists = {tuple(r['maps']): r for r in table['high_triggers']}
    for m, c in COPIES.items():
        source = next(r for maps, r in lists.items() if c in maps)
        lists[(m,)]['records'] = source['records']
    save(exits, table)
    command('dq5exitreloc.py', original, 'patch', exits, '-o', out / 'k-exits.dq5patch.json', *NEW, *EXIT_PLACES)
    command('dq5exitreloc.py', original, 'check', exits, *NEW, *EXIT_PLACES)
    manifests.append(out / 'k-exits.dq5patch.json')
    built = out / 'k.sfc'
    command('dq5build.py', original, 'build', *manifests, '-o', built, '--ips', out / 'k.ips')
    return built, bare


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/highhookcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        built, bare = build_rom(original, out)
        roms = {'original': (original, lorom(0x2AEFF5), dp86_allowed(original)),
                'k': (built, warp_exit(built), dp86_allowed(built)), 'n': (bare, warp_exit(bare), dp86_allowed(bare))}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = dict(zip((c[0] for c in CASES),
                            pool.map(lambda case: run((*case[:4], None), roms, state, out, mesence, libdir), CASES)))
        results, failed = [], []
        for name, rom, to, test, (want_map, want_cell) in CASES:
            got_map, cell, layer, _ = seen[name]
            ok = want_map is None or got_map == want_map and (want_cell is None or cell == want_cell)
            if name in PAIRS:
                ok = ok and seen[name][:3] == seen[PAIRS[name]][:3]
            results.append({'case': name, 'rom': rom, 'to': to, 'test': test, 'map': got_map, 'cell': list(cell),
                            'layer': layer, 'passed': ok})
            print(f'{name}: {got_map} {cell} 층 {layer:02X}{"" if ok else " 불일치"}')
            if not ok:
                failed.append(name)
        save(out / 'results.json', results)
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 장면 통과')
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
