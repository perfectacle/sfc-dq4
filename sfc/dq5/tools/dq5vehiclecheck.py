"""탈것 칸 수·프레임 수 쓰기(dq5objlayout.py --vehicle-at)와 옮기기만 하는 블록을 MesenCE에서 잰다.

장면은 dq5warp.lua 로 필드에 내려 $1954 를 바꾸고(LATESET) 네 방향으로 걷는 것이다(양탄자 (328,27), 天空城·
マスタードラゴン (310,60)). 롬마다 두 번 돌린다.
  - lua/dq5vehicleblocks.lua: 00:FC08 이 그릴 때마다 슬롯·간격·방향까지 더한 첫 칸 오프셋을 모은다.
  - lua/dq5gfxdump.lua: 걷는 동안 20번 WRAM·VRAM·OAM·CGRAM 과 다음 프레임 화면을 덤프한다(양탄자만).
원본 롬: 부분마다 그린 블록이 방향 4 × 프레임 수(天空城 은 0 하나)와 같은지, 옮긴 블록($06 + 1) 가운데 나머지는
  그려지지 않는지 본다.
マスタードラゴン 의 걷기 밖 장면: 필드 (341,56) 에서 내려가 멈춘 자리에서 좌·우로 돌고 A 로 착륙, 필드
  (251,200) 에서 그룹 03 에 내린 뒤 (251,216) 으로 걸어 나와 이륙(7E:2190 bit5), 天空城 06/00 (7E:2190 bit7).
  착륙·이륙은 슬롯 7 이 걷기 간격·32A0 = 8X(01:BF81)로 land0·land1 블록을, 天空城 은 37C0 = S(01:BBB4)·
  32A0 = 83 으로 tenkuu0~3 블록을 그리는지 본다(원본 롬은 15·16 과 12~15). 블록마다 처음·마지막으로 그린 셀 프레임
  + 2(00:FC60 에서 OAM 덤프까지 두 프레임)를 덤프해, 슬롯 칸 목록이 칸 표와 같고 OAM 에 그 블록이 그대로 놓였고 화면
  픽셀이 같은지 본다. land1 은 그린 프레임 안에 걷기 블록으로 다시 그려져 OAM 에 나오지 않으므로 land0 만 본다.
고친 롬: 양탄자를 3프레임으로, 부분 3 을 3x1 → 4x1 로 바꾸고(프레임 2 는 프레임 0 을 좌우로 뒤집은 칸, 부분 3 의
  넷째 칸은 첫 칸) 칸 표를 --vehicle-at 에 옮긴다. 그린 블록이 새 간격의 12블록과 같은지, 슬롯 칸 목록이 문서와 같은지,
  OAM 에 부분마다 문서의 블록이 그대로(자리·타일·반전·팔레트) 놓였는지, 부분 1·2 를 덤프 VRAM·CGRAM 으로 칠한
  픽셀이 화면과 같은지 본다(부분 3 은 색 연산 그림자라 화면은 견주지 않음). 원본 롬의 덤프도 같은 검사를 거친다.
고친 マスタードラゴン 두 벌(--dragon-at 에 칸 표): 4프레임(프레임 3 은 프레임 1 을 좌우로 뒤집은 칸, 그림자 상하 반전
  32칸은 옮긴 표)과 부분 1 을 4x4 → 5x5(줄마다 첫 칸을 더하고 마지막 줄을 한 번 더). 걷기 블록·덤프와 네 장면을 원본과
  같은 검사로 잰다. 원본 롬도 マスタードラゴン 걷기 덤프와 장면 덤프를 같은 검사로 거친다.
  MESENCE=… python sfc/dq5/tools/dq5vehiclecheck.py rom/dq5.sfc --state work/state/ship.mss --vehicle-at 04:FEE0
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5objlayout import FORMAT, SCENES as SCENE_SITES, VEHICLE_PARTS, dump, vehicle_part  # noqa: E402
from dq5objlayoutcheck import find_grid, screen_match, w16  # noqa: E402

HERE = Path(__file__).resolve().parent
WALK = 'wait:100,left:120,up:120,right:120,down:120,left:60,down:60,right:60,up:60'
# 걷기는 560프레임쯤 시작해 1381프레임에 끝나고, 드라이버는 끝나면 멈춘다.
SCENES = {0x80: '328,27', 0x81: '310,60', 0x82: '310,60'}
FROM, UNTIL = 560, 1375
DUMPF = tuple(range(600, 1361, 40))
ATTR = {'80-1': 0x0000, '80-2': 0x0000, '80-3': 0x0A00, '82-1': 0x0000, '82-2': 0x0A00}
FRAMES = 3
# マスタードラゴン 의 걷기 밖 장면: (환경, 그려야 할 82-1 장면 블록, 화면에 나와야 할 블록). TEST 는 셀 끝(UNTIL)보다 길다.
LAND, TENKUU = ('land0', 'land1'), ('tenkuu0', 'tenkuu1', 'tenkuu2', 'tenkuu3')
DRAGON_SCENES = {
    'land-right': ({'FIELD': '341,56', 'LATESET': '1954=82', 'TEST': 'wait:150,right:4,wait:10,a:6,wait:700'},
                   LAND, ('land0',)),
    'land-left': ({'FIELD': '341,56', 'LATESET': '1954=82', 'TEST': 'wait:150,left:4,wait:10,a:6,wait:700'},
                  LAND, ('land0',)),
    'takeoff': ({'FIELD': '251,200', 'SET': '2190|20', 'LATESET': '1954=82', 'TEST': 'wait:300,down:200,wait:400'},
                LAND, ('land0',)),
    'tenkuu-0600': ({'TO': '06/00,37,58', 'SET': '2190|80', 'TEST': 'wait:900'}, TENKUU, TENKUU),
}
LAG = 2
# 고친 マスタードラゴン: (프레임 수, 부분 1 크기).
DRAGON_EDITS = {'dragon4': (4, None), 'dragon5x5': (3, '5x5')}
SCENE_FROM, SCENE_UNTIL = 300, 1300


def mirror(rows):
    flip = lambda t: t[1:] if t.startswith('h') else 'h' + t  # noqa: E731
    return [' '.join(flip(t) for t in reversed(r.split())) for r in rows]


def edit_doc(rom):
    out = []
    for v in dump(rom)['vehicles']:
        if VEHICLE_PARTS[v['part']]['vid'] != 0x80:
            continue
        cells = {}
        for d in ('up', 'right', 'down', 'left'):
            for f in range(FRAMES):
                rows = v['cells'][f'{d}{f}'] if f < 2 else mirror(v['cells'][f'{d}0'])
                if v['part'] == '80-3':
                    rows = [r + ' ' + r.split()[0] for r in rows]
                cells[f'{d}{f}'] = rows
        row = {'part': v['part'], 'frames': FRAMES, 'cells': cells}
        if v['part'] == '80-3':
            row['size'] = '4x1'
        out.append(row)
    return {'format': FORMAT, 'vehicles': out}


def dragon_doc(rom, frames, size):
    """マスタードラゴン 두 부분의 모든 블록. 프레임 3 은 프레임 1 을 좌우로 뒤집은 칸, size 면 부분 1 줄마다 첫 칸을
    더하고 마지막 줄을 한 번 더 둔다. 장면 블록(land·tenkuu)은 롬 그대로."""
    out = []
    for v in dump(rom)['vehicles']:
        if VEHICLE_PARTS[v['part']]['vid'] != 0x82:
            continue
        cells = {}
        for d in ('up', 'right', 'down', 'left'):
            for f in range(frames):
                cells[f'{d}{f}'] = v['cells'][f'{d}{f}'] if f < 3 else mirror(v['cells'][f'{d}1'])
        cells |= {k: rows for k, rows in v['cells'].items() if k.startswith(('land', 'tenkuu'))}
        row = {'part': v['part'], 'frames': frames, 'cells': cells}
        if size and v['part'] == '82-1':
            grow = lambda rows: [r + ' ' + r.split()[0] for r in rows + rows[-1:]]  # noqa: E731
            row['size'], row['cells'] = size, {k: grow(rows) for k, rows in cells.items()}
        out.append(row)
    return {'format': FORMAT, 'vehicles': out}


def build(original, out, name, doc, at):
    (out / f'{name}.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
    print(tool('dq5objlayout.py', original, 'check', out / f'{name}.json', '--vehicle-at', at).stdout, end='')
    tool('dq5objlayout.py', original, 'patch', out / f'{name}.json', '-o', out / f'{name}.dq5patch.json',
         '--vehicle-at', at)
    path = out / f'{name}.sfc'
    tool('dq5build.py', original, 'build', out / f'{name}.dq5patch.json', '-o', path, '--ips', out / f'{name}.ips')
    return path


def tool(name, *args):
    return subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True,
                          text=True, timeout=300)


def run(rom, name, lua, extra, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'TO',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY', 'DUMPF', 'FROM', 'UNTIL')}
    env.update({'LIBDIR': str(libdir), 'STATE': str(state), 'SHOT_DIR': str(dest), 'MAXF': '2000', 'SETTLE': '120',
                'TEST': WALK} | extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua' / lua),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=300)
    return dest


def drawn(dest):
    """blocks.txt → {(가로, 세로, 37C0, 37E0): (32A0, {첫 칸 오프셋(바이트)})}."""
    out = {}
    for line in (dest / 'blocks.txt').read_text().splitlines():
        slot, base, size, d, f, a0, off, *_ = line.split()
        cols, rows = map(int, size.split('x'))
        key = (cols, rows, int(d, 16), int(f, 16))
        out.setdefault(key, (int(a0, 16), set()))[1].add(int(off))
    return out


def scene_expect(rom, keys):
    """장면이 슬롯 7 에 두는 (37C0, 32A0)과 그려야 할 82-1 블록."""
    p = vehicle_part(rom, '82-1')
    per = p['cols'] * p['rows']
    if keys[0].startswith('land'):
        stride, a0 = p['dir'], rom.u8(SCENE_SITES['82-1']['land']['last'])
    else:
        stride, a0 = rom.u8(SCENE_SITES['82-1']['tenkuu']['stride']), rom.u8(SCENE_SITES['82-1']['tenkuu']['last'])
    return stride, a0, {p['scene'][k][0] // per for k in keys}


def scene_blocks(rom, dest, stride, a0):
    """blocks.txt 에서 82-1 크기 슬롯이 37C0 = stride, 32A0 = a0 로 그린 블록 → (처음, 마지막) 셀 프레임."""
    p = vehicle_part(rom, '82-1')
    per = p['cols'] * p['rows']
    out = {}
    for line in (dest / 'blocks.txt').read_text().splitlines():
        _, _, size, d, _, got, off, _, _, _, first, last = line.split()
        if size == f'{p["cols"]}x{p["rows"]}' and (int(d, 16), int(got, 16)) == (stride, a0):
            b = int(off) // 2 // per
            f0, f1 = out.get(b, (int(first), int(last)))
            out[b] = (min(f0, int(first)), max(f1, int(last)))
    return out


def block_report(rom, vid, seen):
    """부분마다 (그린 블록, 옮긴 블록 수, 그린 블록이 방향 4 × 프레임과 같은지)."""
    rows = {}
    for n, site in VEHICLE_PARTS.items():
        if site['vid'] != vid:
            continue
        p = vehicle_part(rom, n)
        per = p['cols'] * p['rows']
        _, offs = seen.get((p['cols'], p['rows'], p['dir'], p['frame']), (None, set()))
        blocks = sorted({o // 2 // per for o in offs})
        want = sorted({i[0] // per for i in p['blocks'].values()})
        rows[n] = {'drawn': blocks, 'copied': p['copied'] // per, 'expected': blocks == want and all(o % (per * 2) == 0
                                                                                                  for o in offs)}
    return rows


def frames(dest, dumpf=DUMPF):
    for f in dumpf:
        tag = dest / f'f{f:05d}'
        yield {k: Path(f'{tag}.{k}').read_bytes() for k in ('wram', 'vram', 'oam', 'cgram')} | \
            {'png': Image.open(dest / f'f{f + 1:05d}.png').convert('RGB')}


def part_cells(rom, n):
    """슬롯 칸 목록에 들어갈 칸 워드: 옮겨 쓰는 칸 바이트 + 타일 180 + 반전 + 팔레트, 상하 반전 표 반영."""
    p = vehicle_part(rom, n)
    cells = [0x180 + (c & 0x7F) | (0x4000 if c & 0x80 else 0) | ATTR[n]
             for c in (rom.u8(p['table'] + i) for i in range(p['copied']))]
    return [c | (0x8000 if i in p['vflip'] else 0) for i, c in enumerate(cells)]


def oam_scene(rom, d, names, screen=()):
    """부분마다 슬롯 칸 목록이 롬의 칸 표와 같은 탈것 슬롯, OAM 에서 찾은 블록(걷기·장면 열쇠), screen 부분은 화면 픽셀."""
    w = d['wram']
    items = S.oam_groups(d['oam'])
    out = {}
    for n in names:
        p = vehicle_part(rom, n)
        per = p['cols'] * p['rows']
        want = part_cells(rom, n)
        slot = next((s for s in range(0x20) if w[0x3220 + s] == 0xFE and (w[0x34E0 + s], w[0x3500 + s]) ==
                     (p['cols'], p['rows']) and [w16(w, w16(w, 0x8000 + w[0x3200 + s]) + i * 2)
                                                for i in range(len(want))] == want), None)
        row = {'slot': slot, 'block': None}
        for key, idx in (p['blocks'] | p['scene']).items():
            hit = find_grid(items, [want[i] for i in idx], p['cols'])
            if hit:
                row['block'], row['at'], row['index'] = key, hit[1:], idx[0] // per
                if n in screen:
                    row['screen'] = screen_match(d, items[hit[0]:hit[0] + per], items[:hit[0]])
                break
        out[n] = row
    return out


def full(s):
    return s[0] == s[1] and s[1] > 0


def dragon_runs(name, path, out, state, mesence, libdir, results, checks):
    """マスタードラゴン: 걷기 블록·덤프와 네 장면의 블록·덤프."""
    rom = Rom(path.read_bytes())
    scene = {'FIELD': SCENES[0x82], 'LATESET': '1954=82'}
    dest = run(path, f'{name}-82-blocks', 'dq5vehicleblocks.lua', scene | {'FROM': str(FROM), 'UNTIL': str(UNTIL)},
               out, state, mesence, libdir)
    seen = drawn(dest)
    report = block_report(rom, 0x82, seen)
    results[f'{name}-82-blocks'] = report
    frames_ = vehicle_part(rom, '82-1')['frames']
    checks[f'{name}-82-blocks'] = all(r['expected'] and r['drawn'] == list(range(4 * frames_)) for r in report.values())
    checks[f'{name}-82-a0'] = {a0 for a0, _ in seen.values()} == {0x80 | (frames_ - 1)}
    dest = run(path, f'{name}-82-dump', 'dq5gfxdump.lua', scene | {'DUMPF': ','.join(f'{f},{f + 1}' for f in DUMPF)},
               out, state, mesence, libdir)
    rows = [oam_scene(rom, d, ('82-1', '82-2'), ('82-1',)) for d in frames(dest)]
    results[f'{name}-82-dump'] = rows
    checks[f'{name}-82-oam'] = all(r['slot'] is not None and r['block'] and (n == '82-2' or full(r['screen']))
                                   for row in rows for n, r in row.items())
    if frames_ > 3:
        checks[f'{name}-82-frame3'] = any((row['82-1']['block'] or '').endswith('3') for row in rows)
    p = vehicle_part(rom, '82-1')
    per, want = p['cols'] * p['rows'], part_cells(rom, '82-1')
    for scene_name, (extra, keys, visible) in DRAGON_SCENES.items():
        stride, a0, blocks = scene_expect(rom, keys)
        case = f'{name}-{scene_name}'
        dest = run(path, f'{case}-blocks', 'dq5vehicleblocks.lua',
                   extra | {'FROM': str(SCENE_FROM), 'UNTIL': str(SCENE_UNTIL)}, out, state, mesence, libdir)
        got = scene_blocks(rom, dest, stride, a0)
        results[case] = sorted(got)
        checks[case] = set(got) == blocks
        dumpf = sorted({f + LAG for span in got.values() for f in span})
        if not dumpf:
            continue
        dest = run(path, f'{case}-dump', 'dq5gfxdump.lua', extra | {'DUMPF': ','.join(f'{f},{f + 1}' for f in dumpf)},
                   out, state, mesence, libdir)
        shown = {}
        for f, d in zip(dumpf, frames(dest, dumpf)):
            w, items = d['wram'], S.oam_groups(d['oam'])
            if [w16(w, w16(w, 0x8000 + w[0x3207]) + i * 2) for i in range(len(want))] != want:
                continue
            for b in got:
                hit = find_grid(items, want[b * per:(b + 1) * per], p['cols'])
                if hit and full(screen_match(d, items[hit[0]:hit[0] + per], items[:hit[0]])):
                    shown.setdefault(b, []).append(f)
        results[f'{case}-dump'] = {b: shown.get(b, []) for b in sorted(got)}
        checks[f'{case}-oam'] = all(shown.get(p['scene'][k][0] // per) for k in visible)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/vehiclecheck')
    ap.add_argument('--vehicle-at', default='04:FEE0', help='옮긴 칸 표 자리(dq5objlayout.py --vehicle-at)')
    ap.add_argument('--dragon-at', default='0B:FBB0', help='고친 マスタードラゴン 의 칸 표 자리')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        base = Rom(original.read_bytes())
        (out / 'layout.json').write_text(json.dumps(edit_doc(base), indent=1) + '\n', encoding='utf-8')
        print(tool('dq5objlayout.py', original, 'check', out / 'layout.json', '--vehicle-at', args.vehicle_at).stdout,
              end='')
        tool('dq5objlayout.py', original, 'patch', out / 'layout.json', '-o', out / 'layout.dq5patch.json',
             '--vehicle-at', args.vehicle_at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'layout.dq5patch.json', '-o', edited, '--ips', out / 'edited.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results, checks = {}, {}
        runs = [('original', original, vid) for vid in (0x80, 0x81)] + [('edited', edited, 0x80)]
        for rom_name, path, vid in runs:
            rom = Rom(path.read_bytes())
            scene = {'FIELD': SCENES[vid], 'LATESET': f'1954={vid:02X}'}
            name = f'{rom_name}-{vid:02X}'
            dest = run(path, f'{name}-blocks', 'dq5vehicleblocks.lua', scene | {'FROM': str(FROM), 'UNTIL': str(UNTIL)},
                       out, state, mesence, libdir)
            seen = drawn(dest)
            report = block_report(rom, vid, seen)
            results[f'{name}-blocks'] = report
            checks[f'{name}-blocks'] = all(r['expected'] for r in report.values())
            if vid == 0x80:
                dest = run(path, f'{name}-dump', 'dq5gfxdump.lua',
                           scene | {'DUMPF': ','.join(f'{f},{f + 1}' for f in DUMPF)}, out, state, mesence, libdir)
                rows = [oam_scene(rom, d, ('80-1', '80-2', '80-3'), ('80-1', '80-2')) for d in frames(dest)]
                results[f'{name}-dump'] = rows
                checks[f'{name}-oam'] = all(r['slot'] is not None and r['block'] and (n == '80-3' or full(r['screen']))
                                            for row in rows for n, r in row.items())
                checks[f'{name}-a0'] = {a0 for a0, _ in seen.values()} == {0x80 | (vehicle_part(rom, '80-1')['frames'] - 1)}
        dragon_runs('original', original, out, state, mesence, libdir, results, checks)
        for name, (frames_, size) in DRAGON_EDITS.items():
            path = build(original, out, name, dragon_doc(base, frames_, size), args.dragon_at)
            dragon_runs(name, path, out, state, mesence, libdir, results, checks)
        edited_rom = Rom(edited.read_bytes())
        checks['edited-size'] = vehicle_part(edited_rom, '80-3')['cols'] == 4 and \
            all(results['edited-80-blocks'][n]['drawn'] == list(range(4 * FRAMES)) for n in ('80-1', '80-2', '80-3'))
        # 프레임 2 는 프레임 0 을 뒤집은 것이라, 칸이 프레임 0·1 과 다른 블록이 OAM 에 나왔는지 따로 본다.
        checks['edited-frame2'] = any(r['block'] and r['block'].endswith('2') for row in results['edited-80-dump']
                                      for r in row.values())
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=1, default=str) + '\n', encoding='utf-8')
        for case, rows in results.items():
            if isinstance(rows, list) and (not rows or isinstance(rows[0], int)):
                print(f'{case} 82-1: 그린 장면 블록 {rows}')
            elif case.endswith('-blocks'):
                for n, r in rows.items():
                    print(f'{case} {n}: 그린 블록 {r["drawn"]} / 옮긴 블록 {r["copied"]}')
            elif isinstance(rows, dict):
                print(f'{case}: 블록마다 OAM·화면에 그대로 나온 덤프 프레임 {rows}')
            else:
                seen = {n: sorted({row[n].get('block') or '-' for row in rows}) for n in rows[0]}
                print(f'{case}: 덤프 {len(rows)}개, OAM 블록 {seen}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout, error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
