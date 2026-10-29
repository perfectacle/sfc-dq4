"""새 그룹(36)의 필드 출구·도착·팔레트 세트·인물 목록을 MesenCE 에서 밟아 확인한다.

원본에서 도구마다 패치를 만들어 함께 빌드한다.
  dq5newmap.py       36/00(03/00 의 레코드·속성), 그룹 36 의 들어가는 곳(=도착)은 36/00 (38,68) 층 1. 들어가는 곳 표 3E:C000,
                     문 표 3D. 03/00 은 층 1 의 맵이다. 맵 밖으로 걸어 나가려면 주인공 층이 $182F 와 같아야 하는데, $182F 를
                     2 로 두는 맵별 루틴은 01/00·07/00 에만 걸려 새 그룹 맵은 늘 1 이다
  dq5npcrelocate.py  그룹 36 의 인물 그룹 포인터와 빈 목록
  dq5exitreloc.py    36/00 의 출구(기본값, 필드로 나감)
  dq5fieldtables.py  보조 입구 표 끝에 (345,56) → 그룹 36. 입구 표 둘을 3C:8000 으로
  dq5palsetwrite.py  그룹 36 의 기본 세트 06, 36/00 은 세트 13(16진). 찾기 루틴·표를 3C:9000 으로(롬 g 만)
롬 g 는 다섯을 모두, 롬 p 는 팔레트 세트만 뺀다.

  exit     g: 36/00 (38,70) 에서 아래로 걸어 필드로 나옴. 일반 표에 36 이 없으므로 보조 표대로 (345,57) 에 섬
  exit-03  g: 03/00 에서 같이 나옴. 옮긴 보조 표의 그룹 03 자리(원본과 같은 (251,216))
  enter    g: 필드 341,56 에서 오른쪽으로 걸어 보조 입구 (345,56) 에 들어 36/00 의 도착 자리 (38,68) 에 섬
  enter-original  원본: 같은 걸음으로 필드에 남음
  palette  g: 36/00 에 선 CGRAM 1~7번 줄이 만든 롬의 dq5map.map_cgram(36/00) 과 같음
  palette-03  원본 03/00 의 같은 비교(대조)
  nopal    p: 팔레트 세트 표에 36 이 없는 롬에서 36/00 의 CGRAM 이 어느 맵의 팔레트와 같은지 기록
인물: 만든 롬의 dq5npc.all_lists 에 36/00 이 있고 그 목록이 비었으면, 게임의 인물 뒤 슬롯 7E:1983 이 08 인지 본다.

  MESENCE=… python sfc/dq5/tools/dq5newgroupcheck.py rom/dq5.sfc --state work/state/ship.mss \\
      --field-state work/state/field-free.mss
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import dq5npc
from dq5exitcheck import command, dp86_allowed, require, warp_exit
from dq5map import Rom, lorom, map_cgram
from dq5progresscheck import environment

HERE = Path(__file__).resolve().parent
NEW = {'group': 0x36, 'x': 345, 'y': 56}
PALETTE = {'format': 'dq5palset/1', 'groups': [{'group': '36', 'default': 6, 'maps': [{'map': '00', 'set': 0x13}]}]}
# 도착: [세계 코드 1(세계 0)·맵 00][X][Y][층][방향 0]. 형식은 dq5fieldtables.py 의 arrivals 와 같다.
ARRIVAL = [0x20, 38, 68, 1, 0]
NEWMAP = {'format': 'dq5newmap/1', 'groups': [{'group': '36', 'entrance': {'bytes': ARRIVAL}}],
          'maps': [{'map': '36/00', 'record': {'copy': '03/00'}, 'attrs': {'copy': '03/00'}}]}
ARRIVALS = 0x3EC000
NEWMAP_AT = ('--entrance-table-at', f'{ARRIVALS >> 16:02X}:{ARRIVALS & 0xFFFF:04X}', '--door-bank', '3D')
EXIT_PLACES = ('--exits-at', '2A:D812', '--records-at', '3F:8000')
NEW_MAP = ('--new-map', '36/00')


def save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def build_rom(original, out, key):
    manifests = []

    def step(tool, name, doc, *args, check=True):
        source = out / f'{key}-{name}.json'
        save(source, doc)
        manifest = out / f'{key}-{name}.dq5patch.json'
        command(tool, original, 'patch', source, '-o', manifest, *args)
        if check:
            command(tool, original, 'check', source, *args)
        manifests.append(manifest)

    step('dq5newmap.py', 'newmap', NEWMAP, *NEWMAP_AT)
    step('dq5npcrelocate.py', 'npc', {'format': 'dq5npcrelocate/1', 'scripts': []}, *NEW_MAP, check=False)
    exits = out / f'{key}-exits.json'
    command('dq5exitreloc.py', original, 'dump', '-o', exits, *NEW_MAP)
    step('dq5exitreloc.py', 'exits', json.loads(exits.read_text(encoding='utf-8')), *NEW_MAP, *EXIT_PLACES)
    command('dq5fieldtables.py', original, 'dump', '-o', out / 'fieldtables.json')
    tables = json.loads((out / 'fieldtables.json').read_text(encoding='utf-8'))
    aux = [{k: e[k] for k in ('group', 'x', 'y')} for e in tables['entrances'] if e['table'] == 'aux']
    step('dq5fieldtables.py', 'entrances', {'format': 'dq5fieldtables/1', 'entrance_tables': {'aux': aux + [NEW]}},
         '--entrances-at', '3C:8000', *NEW_MAP, check=False)
    if key == 'g':
        step('dq5palsetwrite.py', 'palette', PALETTE, '--table-at', '3C:9000', *NEW_MAP)
    built = out / f'{key}.sfc'
    command('dq5build.py', original, 'build', *manifests, '-o', built, '--ips', out / f'{key}.ips')
    return built


def warp(rom, name, state, out, mesence, libdir, to, test):
    dest = out / name
    dest.mkdir()
    env = environment(libdir, state, dest)
    env.update(TO=to, TEST=f'{test},wait:300', SETTLE='120', MAXF='1800', WARPEXIT=f'{warp_exit(rom):X}',
               DP86OK=dp86_allowed(rom))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5warp.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    require('timeout' not in (dest / 'warp.txt').read_text(encoding='utf-8'), f'{name}: 장면 이동 시간 초과')


def walk(rom, name, state, out, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = environment(libdir, state, dest)
    env.update(DRIVER=str(HERE / 'lua/dq5msg.lua'), MAXF='500', PRE='right:40,wait:400')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5tablecheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)


def place(out, name):
    ram = (out / name / 'final.wram').read_bytes()
    where = {'map': f'{ram[0xBC]:02X}/{ram[0xBD]:02X}', 'BE': ram[0xBE], '1983': ram[0x1983], '075E': ram[0x075E]}
    if ram[0xBE] & 0x80:
        where['cell'] = [ram[0x3020], ram[0x3080]]
    else:
        where['field'] = [int.from_bytes(ram[0xB6:0xB8], 'little'), int.from_bytes(ram[0xB8:0xBA], 'little')]
    return where


def bg_rows(out, name):
    return (out / name / 'final.cgram').read_bytes()[0x20:0x100]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path, help='배 선실 세이브스테이트')
    ap.add_argument('--field-state', required=True, type=Path, help='필드 341,56 에 선 세이브스테이트')
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/newgroupcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, field = args.rom.resolve(), args.state.resolve(), args.field_state.resolve()
        mesence = Path(args.mesence).resolve()
        for path in (original, state, field, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        g, p = build_rom(original, out, 'g'), build_rom(original, out, 'p')
        built = Rom(g.read_bytes())
        lists = {name: at for at, name in dq5npc.all_lists(built)}
        require('36/00' in lists, '만든 롬의 인물 목록에 36/00 이 없음')
        npc_empty = not dq5npc.list_entries(built, lists['36/00'])
        jobs = {
            'exit': lambda: warp(g, 'exit', state, out, mesence, libdir, '36/00,38,70,1', 'down:60'),
            'exit-03': lambda: warp(g, 'exit-03', state, out, mesence, libdir, '03/00,38,70,1', 'down:60'),
            'enter': lambda: walk(g, 'enter', field, out, mesence, libdir),
            'enter-original': lambda: walk(original, 'enter-original', field, out, mesence, libdir),
            'palette': lambda: warp(g, 'palette', state, out, mesence, libdir, '36/00,38,60,1', 'wait:10'),
            'palette-03': lambda: warp(original, 'palette-03', state, out, mesence, libdir, '03/00,38,60,1', 'wait:10'),
            'nopal': lambda: warp(p, 'nopal', state, out, mesence, libdir, '36/00,38,60,1', 'wait:10'),
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: job(), jobs.values()))
        seen = {name: place(out, name) for name in jobs}
        orig = Rom(original.read_bytes())
        arrival = bytes(built.d[lorom(ARRIVALS + 0x36 * 5):][:5])
        results = {'seen': seen, 'npc_36_00_empty': npc_empty, 'arrival_36': arrival.hex(' ')}
        checks = {
            'exit': seen['exit'].get('field') == [NEW['x'], NEW['y'] + 1],
            'exit-03': seen['exit-03'].get('field') == [251, 216],
            'enter': seen['enter']['map'] == f'36/{arrival[0] & 0x1F:02X}' and seen['enter'].get('cell') == [arrival[1], arrival[2]],
            'enter-original': seen['enter-original']['BE'] & 0x80 == 0,
            'palette': seen['palette']['map'] == '36/00'
            and bg_rows(out, 'palette') == map_cgram(built, 0x36, 0, seen['palette']['075E'] >= 0xF0)[0x20:0x100],
            'palette-03': seen['palette-03']['map'] == '03/00'
            and bg_rows(out, 'palette-03') == map_cgram(orig, 0x03, 0, seen['palette-03']['075E'] >= 0xF0)[0x20:0x100],
            'npc': npc_empty and seen['palette']['1983'] == 0x08,
        }
        night = seen['nopal']['075E'] >= 0xF0
        nopal = bg_rows(out, 'nopal')
        results['nopal_same_as'] = [f'{bc:02X}/{bd:02X}' for bc, bd in ((0x17, 0), (0x03, 0))
                                    if map_cgram(orig, bc, bd, night)[0x20:0x100] == nopal]
        results['nopal_same_as_36_00_set'] = nopal == bg_rows(out, 'palette')
        results['checks'] = checks
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for name, where in seen.items():
            print(f'{name}: {where}{"" if checks.get(name, True) else " 불일치"}')
        print(f'인물 36/00 목록 비었음={npc_empty}, 1983={seen["palette"]["1983"]:02X}; 도착 36 {arrival.hex(" ")}; '
              f'팔레트 없는 36/00 = {results["nopal_same_as"] or "17/00·03/00 아님"}')
        failed = [k for k, v in checks.items() if not v]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(jobs)}회 실행, 새 그룹 검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
