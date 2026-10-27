"""출구·영역 이동 쓰기와 표 옮기기를 MesenCE에서 밟아 확인한다.

고정 슬롯 변경 롬 세 벌(출구 세 종류·출발층·고층 공유 목록·음수 가장자리, 옮긴 사각형, 이동 효과음 플래그),
표를 옮긴 롬 세 벌(원본 그대로 옮김, 늘리고 옮김, 원래 자리에 다시 씀)과 원본 롬에서 같은 자리를 밟아
도착 맵·칸·주인공 층을 견준다. --audit 은 원본 롬 장면에서 표 뱅크를 DB 로 둔 동안 실행한 명령과
그 뱅크 롬 읽기를 모은다(lua/dq5exitcheck.lua). 원본 롬·선실 상태는 읽기만 하고 출력은 --out의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5exitcheck.py rom/dq5.sfc --state work/state/ship.mss [--audit]
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

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM

from dq5exit import arrival, exit_attrs
from dq5exitreloc import EXIT_INDEXED, EXIT_SHORT, STUB_SIZE, cpu, engine_exits, locate
from dq5map import Rom, lorom

HERE = Path(__file__).resolve().parent
EDITS = {
    'a': {'exits': [{'map': '01/00', 'index': 1, 'destination_map': 9, 'exit': 1},
                    {'map': '21/02', 'index': 0, 'group': 1, 'destination_map': 3, 'exit': 0},
                    {'map': '01/01', 'index': 0, 'destination_map': 4, 'x': 16, 'y': 6, 'layer': 1}],
          'triggers': [{'map': '01/00', 'index': 6, 'source_layer': 2, 'destination_map': 4, 'x': 16, 'y': 6},
                       {'map': '50/50', 'index': 0, 'shared_maps': ['50/50', '50/51'],
                        'destination_group': 1, 'destination_map': 4, 'x': 16, 'y': 6},
                       {'map': '01/06', 'index': 0, 'rect': [255, 6, 0, 9]}]},
    'b': {'triggers': [{'map': '01/00', 'index': 6, 'rect': [32, 58, 33, 59], 'source_layer': 2,
                        'destination_map': 4, 'x': 16, 'y': 6, 'span_raw': 1}]},
    'c': {'triggers': [{'map': '01/06', 'index': 0, 'flags': 0xC0}]},
}


def to_0104(rect, layer):
    return {'rect': rect, 'source_layer': layer, 'flags': 0xC0, 'destination_group': 1, 'destination_map': 4,
            'x': 16, 'y': 6, 'span_raw': 1, 'destination_layer': 1}


def grow(doc):
    exits = {r['map']: r['records'] for r in doc['exits']}
    exits['01/00'][1] = {'kind': 'position', 'destination_map': 4, 'x': 16, 'y': 6, 'layer': 1, 'group': 1}
    exits['01/03'].append({'kind': 'same-group', 'destination_map': 9, 'exit': 1})
    next(r for r in doc['triggers'] if r['map'] == '01/00')['records'].append(to_0104([32, 58, 33, 59], 2))
    doc['triggers'].append({'map': '01/03', 'records': [to_0104([14, 14, 15, 15], 1)]})
    # 50/* 공유 목록 앞에 원래 레코드와 같은 사각형·출발층으로 목적지만 다른 레코드를 넣는다. 실행기는 먼저 맞는 것을 쓴다.
    shared = doc['high_triggers'][0]['records']
    shared.insert(0, to_0104(shared[0]['rect'], shared[0]['source_layer']))


def shrink(doc):
    next(r for r in doc['exits'] if r['map'] == '01/01')['records'][0] = {
        'kind': 'same-group', 'destination_map': 4, 'exit': 1}


# (편집, 자리). r 은 원본 그대로 네 표를 모두 옮기고(출구는 뱅크 7C 에서 [$84] 로 읽음), g 는 늘린 출구를 뱅크 2A 의
# 옛 레코드 자리로, 레코드·고층 목록을 3F 로 옮기며 3바이트 늘어난 색인은 옛 출구 자리로 넘친다. p 는 줄여서 원래 자리에 쓴다.
RELOC = {
    'r': (None, {'exits': 0x7C8000, 'records': 0x3E8000, 'index': 0x0BFBB0, 'high': 0x3EA000}),
    'g': (grow, {'exits': 0x2AD812, 'records': 0x3F8000, 'high': 0x3FC000}),
    'p': (shrink, {}),
}
# 01/0A (9,10) 출구 블록은 두 칸 다 속성 33 이라 계단 판정(00:E2C5)을 넘지 못한다. 오른쪽 칸 +4 를 85 로 두면 열린다.
OPEN_0A = f'{0xC000 + (10 * 18 + 9) * 8 + 4:04X}=85'
# 01/03(폭 22)의 바닥 (3,13)·(4,13) 을 계단으로. 계단 판정(00:E2C5)은 주인공이 선 두 칸을 다 보고, 출구 셀로 세는 것은
# 오른쪽 칸(+4 = 85)뿐이다. 원래 출구 셀 (20,5) 뒤라 출구 번호 1 이 된다.
NEW_0103 = ';'.join(f'{0xC000 + (13 * 22 + x) * 8 + 4:04X}={v}' for x, v in ((3, '05'), (4, '85')))
# (이름, 롬, TO, TEST, 기대: 맵(field 면 필드로 나감), 칸·층(None 이면 보지 않음))
# 사각형이 넓으면 도착 칸이 들어선 자리에 비례하므로(2A:F650) 그런 장면은 맵과 층만 본다.
CASES = [
    ('same', 'a', '01/00,60,79,2', 'down:16', ('01/09', ('arrival', 1, 9, 1), None)),
    ('same-original', 'original', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None)),
    ('other', 'a', '21/02,111,8,1', 'up:16', ('01/03', ('arrival', 1, 3, 0), None)),
    ('other-original', 'original', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None)),
    ('position', 'a', '01/01,13,8,1', 'up:24', ('01/04', (16, 6), 1)),
    ('position-original', 'original', '01/01,13,8,1', 'up:24', ('01/00', (21, 28), 2)),
    ('layer', 'a', '01/00,32,59,2', 'down:16', ('01/04', None, 1)),
    ('layer-original', 'original', '01/00,32,59,2', 'down:16', ('01/00', None, 2)),
    ('high-50', 'a', '50/50,31,17,1', 'down:16', ('01/04', None, 1)),
    ('high-51', 'a', '50/51,31,17,1', 'down:16', ('01/04', None, 1)),
    ('high-original', 'original', '50/50,31,17,1', 'down:16', ('05/01', None, 1)),
    ('high-51-original', 'original', '50/51,31,17,1', 'down:16', ('05/01', None, 1)),
    ('edge-kept', 'a', '01/06,0,8,1', 'left:24', ('01/04', None, 1)),
    ('edge-kept-original', 'original', '01/06,0,8,1', 'left:24', ('01/04', None, 1)),
    ('edge-cut', 'a', '01/06,0,10,1', 'left:24', ('field', None, None)),
    ('edge-original', 'original', '01/06,0,10,1', 'left:24', ('01/04', (16, 8), 1)),
    ('rect', 'b', '01/00,32,57,2', 'down:16', ('01/04', None, 1)),
    ('rect-original', 'original', '01/00,32,57,2', 'down:16', ('01/00', (32, 58), 2)),
    ('rect-old', 'b', '01/00,32,61,1', 'up:16', ('01/00', None, 1)),
    ('rect-old-original', 'original', '01/00,32,61,1', 'up:16', ('01/01', None, None)),
    ('sound-off', 'c', '01/06,0,8,1', 'left:24', ('01/04', (16, 6), 1), {'sound': 0}),
    ('sound-original', 'original', '01/06,0,8,1', 'left:24', ('01/04', (16, 6), 1), {'sound': 1}),
    ('stair33-original', 'original', '01/0A,8,11,1', 'up:16', ('01/0A', (8, 10), 1)),
    ('stair33-opened', 'original', '01/0A,8,11,1', 'up:16', ('2A/00', ('arrival', 0x2A, 0, 0), None), {'late': OPEN_0A}),
    ('reloc-same', 'r', '01/00,60,79,2', 'down:16', ('01/03', ('arrival', 1, 3, 0), None)),
    ('reloc-other', 'r', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None)),
    ('reloc-position', 'r', '01/01,13,8,1', 'up:24', ('01/00', (21, 28), 2)),
    ('reloc-trigger', 'r', '01/00,32,61,1', 'up:16', ('01/01', None, None)),
    ('reloc-high-50', 'r', '50/50,31,17,1', 'down:16', ('05/01', None, 1)),
    ('reloc-high-51', 'r', '50/51,31,17,1', 'down:16', ('05/01', None, 1)),
    ('reloc-edge', 'r', '01/06,0,10,1', 'left:24', ('01/04', (16, 8), 1)),
    ('reloc-sound', 'r', '01/06,0,8,1', 'left:24', ('01/04', (16, 6), 1), {'sound': 1}),
    ('reloc-stair33', 'r', '01/0A,8,11,1', 'up:16', ('2A/00', ('arrival', 0x2A, 0, 0), None), {'late': OPEN_0A}),
    ('grow-kind', 'g', '01/00,60,79,2', 'down:16', ('01/04', (16, 6), 1)),
    ('grow-exit', 'g', '01/03,3,12,1', 'down:16', ('01/09', ('arrival', 1, 9, 1), None), {'late': NEW_0103}),
    # 원본은 01/03 의 레코드가 하나뿐이라 출구 1 은 다음 맵 01/04 의 첫 레코드(01/05 출구 0)를 읽는다.
    ('grow-exit-original', 'original', '01/03,3,12,1', 'down:16', ('01/05', ('arrival', 1, 5, 0), None),
     {'late': NEW_0103}),
    ('grow-trigger', 'g', '01/00,32,57,2', 'down:16', ('01/04', (16, 7), 1)),
    ('grow-index', 'g', '01/03,14,13,1', 'down:16', ('01/04', (16, 7), 1)),
    ('grow-index-original', 'original', '01/03,14,13,1', 'down:16', ('01/03', (14, 14), 1)),
    ('grow-other', 'g', '21/02,111,8,1', 'up:16', ('0E/03', ('arrival', 0x0E, 3, 1), None)),
    ('grow-high-50', 'g', '50/50,31,17,1', 'down:16', ('01/04', None, 1)),
    ('grow-high-51', 'g', '50/51,31,17,1', 'down:16', ('01/04', None, 1)),
    ('grow-edge', 'g', '01/06,0,10,1', 'left:24', ('01/04', (16, 8), 1)),
    ('place-kind', 'p', '01/01,13,8,1', 'up:24', ('01/04', ('arrival', 1, 4, 1), None)),
]
# --audit 이 DB 창을 모으는 원본 롬 장면: 출구 세 종류, 영역 이동(효과음 갈래 포함)·고층·음수 가장자리.
AUDIT = ('same-original', 'other-original', 'position-original', 'rect-old-original', 'high-original',
         'edge-original', 'sound-original', 'stair33-opened')
ENV_CLEAR = ('ADULT', 'ANYWHERE', 'AUDIT', 'AUDITOPEN', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE',
             'CELL', 'DP86OK', 'MSGLOG', 'ROMPATCH', 'SAVE', 'SET', 'STALE', 'WAGON', 'WARPEXIT')
# r 롬은 네 표를 모두 옮겼으므로 옛 자리(일반 표 2A:D812~F223, 고층 01:9635~9770)를 읽는 곳이 없어야 한다.
STALE = {'r': '2AD812-2AF223,019635-019770'}
# DB 를 기준으로 주소를 내는 꼴. long($xxxxxx)·[$xx]·직접 페이지($xx)·즉값·점프 대상은 DB 를 쓰지 않는다.
DB_ABS = re.compile(r'^(?!J|PE)[A-Z]{3} \$([0-9A-F]{4})(,[XY])?$')
DB_INDIRECT = re.compile(r'^[A-Z]{3} \(\$[0-9A-F]{2}(\)|,X\)|,S\),Y)')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=120)


def warp_exit(path):
    """dq5warp.lua 가 덮는 배 사다리 항목(원래 2A:EFF5, 17/00 첫 출구)의 파일 위치."""
    rom = Rom(path.read_bytes())
    return lorom(engine_exits(rom, locate(rom), 0x17, 0)[0][0])


def dp86_allowed(path):
    """$86 을 건드려도 되는 PC: 스텁(STA $86)과 [$84] 읽기 11곳. 출구가 뱅크 2A 밖이면 스텁 자리도 더한다."""
    rom = Rom(path.read_bytes())
    table = locate(rom)['exits']
    stub = [table - STUB_SIZE + 10] if table >> 16 != 0x2A else []
    return ','.join(f'{a:06X}' for a in (*EXIT_SHORT, *EXIT_INDEXED, *stub))


def run(case, roms, state, out, mesence, libdir, audit=False):
    name, rom, to, test, _, *extra = case
    extra = extra[0] if extra else {}
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ENV_CLEAR}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TO=to, TEST=f'{test},wait:300', WARPEXIT=f'{roms[rom][1]:X}', DP86OK=roms[rom][2])
    if 'late' in extra:
        env['LATESET'] = extra['late']
    if 'cell' in extra:
        env['CELL'] = extra['cell']
    if extra.get('msglog'):
        env['MSGLOG'] = '1'
    if rom in STALE:
        env['STALE'] = STALE[rom]
    if audit:
        env['AUDIT'] = '1'
        if os.environ.get('AUDITOPEN'):
            env['AUDITOPEN'] = os.environ['AUDITOPEN']
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(roms[rom][0]), str(HERE / 'lua/dq5exitcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=1800 if audit else 120)
    text = (dest / 'warp.txt').read_text(encoding='utf-8')
    match = re.search(r'final map (\w\w/\w\w) cell (\d+),(\d+) layer (\w\w) BE=(\w\w) sound (\d+)', text)
    require(match is not None and 'timeout' not in text, f'{name}: 보행 결과가 없음')
    dp86 = re.search(r'dp86 (\S+)', text)
    require(dp86 is not None and dp86[1] == '-', f'{name}: 출구 로더가 덮은 $86 을 다른 곳이 읽음 {dp86 and dp86[1]}')
    stale = re.search(r'stale reads (\d+) (\S+)', text)
    require(stale is not None and stale[1] == '0', f'{name}: 옛 표 자리를 읽음 {stale and stale[2]}')
    place = match[1] if int(match[5], 16) & 0x80 else 'field'
    return place, (int(match[2]), int(match[3])), int(match[4], 16), int(match[6])


def audit_report(rom, out):
    """DB 창 기록을 디스어셈블해 DB 기준으로 주소를 내는 명령과 그 명령의 롬 읽기를 모은다."""
    data, mapper = rom.read_bytes(), LoROM()
    executed, reads = {}, {}
    for name in AUDIT:
        for line in (out / name / 'dbwin.txt').read_text(encoding='utf-8').split('\n'):
            if line:
                pc, p, count = line.split()
                key = int(pc, 16), int(p, 16)
                executed[key] = executed.get(key, 0) + int(count)
        for line in (out / name / 'dbread.txt').read_text(encoding='utf-8').split('\n'):
            if line:
                pc, addr, _ = line.split()
                reads.setdefault(int(pc, 16), set()).add(int(addr, 16))
    access = []
    for (pc, p), count in sorted(executed.items()):
        if pc >> 16 in (0x7E, 0x7F) or pc & 0xFFFF < 0x8000:
            continue
        op = decode(data, pc, m8=bool(p & 0x20), x8=bool(p & 0x10), mapper=mapper)[0][22:]
        hit = DB_ABS.match(op)
        if hit or DB_INDIRECT.match(op):
            got = sorted(reads.get(pc, ()))
            access.append({'pc': cpu(pc), 'op': op, 'count': count, 'rom_reads': len(got),
                           'rom_range': f'{cpu(got[0])}~{cpu(got[-1])}' if got else '',
                           'abs_rom': bool(hit and int(hit[1], 16) >= 0x8000)})
    named = {a['pc'] for a in access}
    return {'instructions': len(executed), 'db_access': access,
            'reads_without_db_access': sorted(cpu(pc) for pc in reads if cpu(pc) not in named)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/exitcheck')
    ap.add_argument('--audit', action='store_true', help='원본 롬 장면에서 DB 창 감사만 함')
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
        roms = {'original': (original, lorom(0x2AEFF5), dp86_allowed(original))}
        cases = [c for c in CASES if c[0] in AUDIT] if args.audit else CASES
        for key, edits in () if args.audit else EDITS.items():
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            source.write_text(json.dumps({'format': 'dq5connections/1', **edits}, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')
            command('dq5exitwrite.py', original, 'patch', source, '-o', manifest)
            command('dq5exitwrite.py', original, 'check', source)
            command('dq5build.py', original, 'build', manifest, '-o', out / f'{key}.sfc', '--ips', out / f'{key}.ips')
            roms[key] = (out / f'{key}.sfc', lorom(0x2AEFF5), dp86_allowed(out / f'{key}.sfc'))
        for key, (edit, at) in () if args.audit else RELOC.items():
            source, manifest = out / f'{key}.json', out / f'{key}.patch.json'
            command('dq5exitreloc.py', original, 'dump', '-o', source)
            if edit:
                doc = json.loads(source.read_text(encoding='utf-8'))
                edit(doc)
                source.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            places = [x for name, addr in at.items() for x in (f'--{name}-at', cpu(addr))]
            command('dq5exitreloc.py', original, 'patch', source, '-o', manifest, *places)
            command('dq5exitreloc.py', original, 'check', source, *places)
            command('dq5build.py', original, 'build', manifest, '-o', out / f'{key}.sfc', '--ips', out / f'{key}.ips')
            roms[key] = (out / f'{key}.sfc', warp_exit(out / f'{key}.sfc'), dp86_allowed(out / f'{key}.sfc'))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = list(pool.map(lambda case: run(case, roms, state, out, mesence, libdir, args.audit), cases))
        results = []
        for (name, rom, to, test, (want_map, want_cell, want_layer), *extra), (got_map, cell, layer, sound) in zip(cases, seen):
            want_sound = extra[0].get('sound') if extra else None
            if want_cell and want_cell[0] == 'arrival':
                _, bc, bd, n = want_cell
                built = Rom(roms[rom][0].read_bytes())
                want_cell = arrival(built, bc, bd, n, exit_attrs(built))
            ok = (got_map == want_map and (want_cell is None or cell == tuple(want_cell))
                  and (want_layer is None or layer == want_layer) and (want_sound is None or sound == want_sound))
            results.append({'case': name, 'rom': rom, 'to': to, 'test': test, 'map': got_map, 'cell': list(cell),
                            'layer': layer, 'expected_map': want_map,
                            'expected_cell': list(want_cell) if want_cell else None,
                            'expected_layer': want_layer, 'sound': sound, 'expected_sound': want_sound, 'passed': ok})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        failed = [r['case'] for r in results if not r['passed']]
        for r in results:
            print(f'{r["case"]}: {r["map"]} {tuple(r["cell"])} 층 {r["layer"]:02X}{"" if r["passed"] else " 불일치"}')
        if args.audit:
            report = audit_report(original, out)
            (out / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            for a in report['db_access']:
                print(f'  {a["pc"]} {a["op"]:<16} {a["count"]:6d}회 롬 읽기 {a["rom_reads"]}곳 {a["rom_range"]}')
            print(f'DB 창 명령 {report["instructions"]}개, DB 기준 접근 {len(report["db_access"])}곳 '
                  f'(abs 8000~ {sum(a["abs_rom"] for a in report["db_access"])}곳), '
                  f'DB 기준 접근 아닌 롬 읽기 {report["reads_without_db_access"]}')
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
