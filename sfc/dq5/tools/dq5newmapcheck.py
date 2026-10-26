"""새 맵 번호(dq5newmap.py + dq5exitreloc.py --new-map)를 MesenCE에서 밟아 확인한다.

새 맵 0D/05 를 0D/02 의 레코드·속성으로 만들고, 0D/01 의 출구 1(원래 0D/02 로 감)을 0D/05 로 돌린 롬을 만든다.
0D/05 의 출구는 0D/02 와 같은 0D/01 출구 1 이다. 0D/05 의 인물 목록은 다음 그룹 첫 맵(0E/00, 인물 없음)을 읽는다.
원본 롬과 같은 자리를 밟아 도착 맵·칸·층과, 맵 속성이 들어간 WRAM(구역·전투 배경·주문 막기·곡 인자)·인물 뒤 슬롯을 견준다.
출력은 --out의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5newmapcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5exit import arrival, exit_attrs
from dq5exitcheck import command, dp86_allowed, require, run, warp_exit
from dq5map import Rom, lorom

HERE = Path(__file__).resolve().parent
NEW = {'format': 'dq5newmap/1', 'maps': [{'map': '0D/05', 'record': {'copy': '0D/02'}, 'attrs': {'copy': '0D/02'}}]}
# 출구 표가 원래 자리보다 2바이트 늘어 넘치므로 출구는 옛 레코드 자리로, 레코드는 늘린 뱅크로 옮긴다.
EXIT_PLACES = ('--exits-at', '2A:D812', '--records-at', '3F:8000')
# (이름, 롬, TO, TEST, 기대: 맵, 칸(('arrival', BC, BD, 출구) 면 그 출구의 도착 칸), 층, 속성을 견줄 장면,
#  인물 뒤 슬롯 7E:1983(None 이면 보지 않음))
# 0D/01·0D/02 의 계단 블록은 (14~15, 10~11). 블록 밖 (14,9) 에서 내려가야 발동한다(블록 안에서 시작하면 그대로 섬).
# 0D/02 의 인물 한 명이 (10,8) 에 서 있어 원본은 (10,6) 에서 멈춘다. 0D/05 는 인물이 없어(슬롯 08) 그 자리까지 간다.
CASES = [
    ('enter', 'n', '0D/01,14,9,1', 'down:16', ('0D/05', ('arrival', 0x0D, 5, 0), None, 'enter-original', 0x08)),
    ('enter-original', 'original', '0D/01,14,9,1', 'down:16', ('0D/02', ('arrival', 0x0D, 2, 0), None, None, 0x09)),
    ('walk', 'n', '0D/05,12,4,1', 'left:32,down:32', ('0D/05', (10, 8), 1, 'walk-original', 0x08)),
    ('walk-original', 'original', '0D/02,12,4,1', 'left:32,down:32', ('0D/02', (10, 6), 1, None, 0x09)),
    ('leave', 'n', '0D/05,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, 'leave-original', None)),
    ('leave-original', 'original', '0D/02,14,9,1', 'down:16', ('0D/01', ('arrival', 0x0D, 1, 1), None, None, None)),
    ('later', 'n', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, 'later-original', None)),
    ('later-original', 'original', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None, None, None)),
    ('later-stay', 'n', '21/02,50,43,1', 'wait:16', ('21/02', (50, 43), None, 'later-stay-original', None)),
    ('later-stay-original', 'original', '21/02,50,43,1', 'wait:16', ('21/02', (50, 43), None, None, None)),
    ('earlier', 'n', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None, 'earlier-original', None)),
    ('earlier-original', 'original', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None, None, None)),
]


def build_rom(original, out):
    """새 맵 패치와 출구 패치를 원본에서 따로 만들어 함께 빌드한다."""
    source = out / 'newmap.json'
    source.write_text(json.dumps(NEW, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    command('dq5newmap.py', original, 'patch', source, '-o', out / 'newmap.dq5patch.json')
    command('dq5newmap.py', original, 'check', source)
    exits = out / 'exits.json'
    command('dq5exitreloc.py', original, 'dump', '-o', exits, '--new-map', '0D/05')
    doc = json.loads(exits.read_text(encoding='utf-8'))
    rows = {r['map']: r for r in doc['exits']}
    rows['0D/05']['records'] = [dict(rows['0D/02']['records'][0])]
    rows['0D/01']['records'][1] = {'kind': 'same-group', 'destination_map': 5, 'exit': 0}
    exits.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    command('dq5exitreloc.py', original, 'patch', exits, '-o', out / 'exits.dq5patch.json', '--new-map', '0D/05', *EXIT_PLACES)
    command('dq5exitreloc.py', original, 'check', exits, '--new-map', '0D/05', *EXIT_PLACES)
    rom = out / 'newmap.sfc'
    command('dq5build.py', original, 'build', out / 'newmap.dq5patch.json', out / 'exits.dq5patch.json',
            '-o', rom, '--ips', out / 'newmap.ips')
    return rom


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/newmapcheck')
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
        built = build_rom(original, out)
        roms = {'original': (original, lorom(0x2AEFF5), dp86_allowed(original)),
                'n': (built, warp_exit(built), dp86_allowed(built))}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir), CASES))
        attrs, slots = {}, {}
        for case in CASES:
            text = (out / case[0] / 'warp.txt').read_text(encoding='utf-8')
            found = re.search(r'map attrs (1A98=\w\w 1AA0=\w\w 194D=\w\w 194B=\w\w) 1983=(\w\w)', text)
            require(found is not None, f'{case[0]}: 속성 줄이 없음')
            attrs[case[0]], slots[case[0]] = found[1], int(found[2], 16)
        results = []
        for (name, rom, to, test, (want_map, want_cell, want_layer, pair, slot)), (got_map, cell, layer, _) in zip(CASES, seen):
            if want_cell and want_cell[0] == 'arrival':
                _, bc, bd, n = want_cell
                data = Rom(roms[rom][0].read_bytes())
                want_cell = arrival(data, bc, bd, n, exit_attrs(data))
            ok = (got_map == want_map and cell == tuple(want_cell) and (want_layer is None or layer == want_layer)
                  and (pair is None or attrs[name] == attrs[pair]) and (slot is None or slots[name] == slot))
            results.append({'case': name, 'rom': rom, 'to': to, 'test': test, 'map': got_map, 'cell': list(cell),
                            'layer': layer, 'attrs': attrs[name], 'slot': slots[name], 'expected_slot': slot,
                            'expected_map': want_map,
                            'expected_cell': list(want_cell), 'attrs_like': pair, 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for r in results:
            print(f'{r["case"]}: {r["map"]} {tuple(r["cell"])} 층 {r["layer"]:02X} {r["attrs"]} 1983={r["slot"]:02X}'
                  f'{"" if r["passed"] else " 불일치"}')
        failed = [r['case'] for r in results if not r['passed']]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 장면 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
