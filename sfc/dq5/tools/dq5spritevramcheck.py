"""인물 세트 타일 수를 48 까지 늘렸을 때 OBJ VRAM 을 MesenCE 에서 재고 dq5spritewrite.py 의 셈(vram_rows)과 견준다.

타일 48개가 모두 다르고 좌우 반전끼리도 다른 시험 무늬를 새 세트 70 에 넣고, 그림 번호를 70 으로 잇는 롬 넷을 만든다.
  hero:  그림 2E(어린 주인공, 1F:CF14 로 올라감)
  npc:   그림 2B(02/06 인물, 1F:CF1E)
  both:  2E 와 2B 둘 다(주인공 사본과 인물 사본이 따로 올라가는지)
  over:  그림 08(19/00 인물). 19/00 은 원래 7E:1995 가 1FE 라 512타일을 넘는다. 도구는 이 문서를 거부하므로 vram=False 로 만든다
02/06 과 19/00 에 dq5warp.lua 로 들어가 dq5gfxdump.lua 로 덤프하고, 7E:1995·VRAM 의 세트 타일·칸 목록을 본다.
--sweep 에 dq5objsweep.py 의 출력 폴더를 주면 맵마다 그때 플래그로 고른 목록의 셈이 잰 $1995 최대와 같은지도 센다.
--maps 로 준 맵은 원본 롬으로 다시 들어가 덤프 때의 $1995 를 셈과 견준다(훑기와 다른 맵을 다시 잴 때).
  MESENCE=… python sfc/dq5/tools/dq5spritevramcheck.py rom/dq5.sfc --state work/state/ship.mss [--sweep work/objsweep]
      [--maps 0A/00,17/00]
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
import dq5npc as N  # noqa: E402
import dq5sprite as S  # noqa: E402
import dq5spritewrite as W  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5mapmusic import entry_cells  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
NEW = 0x70
CASES = {'original': (), 'hero': (0x2E,), 'npc': (0x2B,), 'both': (0x2E, 0x2B), 'over': (0x08,)}
VISITS = {'02/06': '02/06,24,14,1', '19/00': '19/00,44,40'}
WARP_KEYS = ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET', 'WAGON',
             'EVERY')


def unique48(path):
    """칸 48개가 모두 다른 타일인 6타일 배치 그림. 타일마다 왼쪽 열을 채워 좌우 반전이 다른 타일과 같아지지 않게 한다."""
    grid = [[0] * 32 for _ in range(96)]
    corners = [(f * 16 + x, row * 24 + y) for row in range(4) for f in (0, 1) for x, y in S.SIMPLE_POS]
    for n, (x0, y0) in enumerate(corners):
        for y in range(8):
            grid[y0 + y][x0] = 1
            for b in range(6):
                grid[y0 + y][x0 + 1 + b] = (2 + n % 13 if n >> b & 1 else 0) if y % 2 == 0 else 15
            grid[y0 + y][x0 + 7] = 3 + y % 4
    image = Image.new('P', (32, 96))
    image.putpalette([c for i in range(16) for c in (i * 16, 255 - i * 16, i * 64 % 256)])
    image.putdata([c for line in grid for c in line])
    image.save(path)


def build(rom, out, gfx):
    if not gfx:
        return rom, {}, {}
    doc = {'format': W.FORMAT, 'new_sets': [{'set': f'{NEW:02X}', 'image': 'u48.png', 'palette': 0}],
           'gfx': [{'gfx': f'{g:02X}', 'set': f'{NEW:02X}'} for g in gfx]}
    sets, mapping = W.plan(rom, doc, out, vram=False)
    if len(sets[NEW][1]) != 48:
        raise ValueError('시험 무늬의 타일이 48개가 아님')
    return W.apply(rom, W.patch(rom, doc, out, at=0x3A8000, vram=False)), sets, mapping


def run(rom_path, tag, to, out, state, mesence, lib):
    dest = out / tag
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in WARP_KEYS}
    env.update(LIBDIR=str(lib), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120', TO=to, TEST='wait:400',
               DUMPF='620,700')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom_path), str(HERE / 'lua/dq5gfxdump.lua'),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT, check=True,
                            timeout=300)
    dumps = sorted(dest.glob('f0*.wram'))
    if not dumps:
        raise ValueError(f'{tag}: 덤프가 없음')
    return dest, dumps


def measure(rom, dest, dumps):
    """덤프마다 (맵, 7E:1995, 세트 70 의 사본 수, 세트마다 VRAM 에 그대로 있는 사본의 [맞은 타일, 전체])."""
    rows = []
    for w in dumps:
        wram, vram = w.read_bytes(), w.with_suffix('.vram').read_bytes()
        stats = {}
        S.compare(rom, wram, vram, w.with_suffix('.oam').read_bytes(), w.with_suffix('.cgram').read_bytes(), stats, False)
        rows.append({'map': f'{wram[0xBC]:02X}/{wram[0xBD]:02X}', 'v1995': wram[0x1995] | wram[0x1996] << 8,
                     'sets': {f'{s:02X}': v for s, v in stats.get('sets', {}).items()},
                     'oam': (stats.get('hits', 0), stats.get('groups', 0)), 'night': wram[0x075E] >= 0xF0,
                     'flags': {0x7E0000 | a: wram[a] for a in range(0x2190, 0x2200)}, 'wram': wram})
    return rows


def predicted(rom, sets, mapping, bc, bd, flags, night):
    """그때 플래그로 고른 목록(12:8009)과 그 맵의 맵 OBJ 타일로 dq5spritewrite.vram_use 의 셈."""
    a = N.list_address(rom, bc, bd, flags)
    people = {(f['gfx'], bool(f['misc'] & 0x80)) for e, _ in (N.list_entries(rom, a) if a is not None else [])
              if (f := N.parse(rom, e, night))}
    # 덤프 때의 7E:21B3 bit3 이 그림 9A 의 갈래를 정한다(1F:CF32). vram_use 는 모를 때 큰 쪽을 센다.
    wife = 0x2F if flags.get(0x7E21B3, 0) & 0x08 else 0x97
    people = {(wife if g == 0x9A else g, lying) for g, lying in people}
    final = {g: mapping.get(g, S.gfx_set(rom, g)) for g in range(S.GFX_COUNT)}
    return W.vram_use([('', W.map_reserve(S.map_objects(rom), bc, bd), night, people)], final.get,
                      lambda s: W.set_tiles(rom, sets, s, True))[0]


def sweep_model(rom, folder):
    """dq5objsweep.py 출력의 맵마다: 끝 WRAM 의 플래그로 고른 목록의 셈이 잰 $1995 최대와 같은지."""
    same, other = 0, []
    for d in sorted(Path(folder).iterdir()):
        txt, wram = d / 'objsweep.txt', d / 'final.wram'
        if not (txt.exists() and wram.exists()):
            continue
        got = dict(line.strip().split('=', 1) for line in txt.open(encoding='utf-8') if '=' in line)
        if int(got['frames']) == 0:
            continue
        w = wram.read_bytes()
        bc, bd = (int(v, 16) for v in d.name.split('_'))
        flags = {0x7E0000 | a: w[a] for a in range(0x2190, 0x2200)}
        want = predicted(rom, {}, {}, bc, bd, flags, w[0x075E] >= 0xF0)
        if want == int(got['v1995']):
            same += 1
        else:
            other.append(f'{d.name.replace("_", "/")} 잼 {int(got["v1995"]):03X} 셈 {want:03X}')
    return same, other


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spritevramcheck')
    ap.add_argument('--sweep', type=Path, help='dq5objsweep.py 의 출력 폴더')
    ap.add_argument('--maps', help='원본 롬으로 다시 잴 맵(쉼표로 구분한 BC/BD)')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        base = Rom(args.rom.read_bytes())
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        unique48(out / 'u48.png')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        lib = out / 'lib'
        shutil.copytree(krlua, lib)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', lib / 'boot.lua')
        results, checks = {}, {}
        for name, gfx in CASES.items():
            rom, sets, mapping = build(base, out, gfx)
            path = out / f'{name}.sfc'
            path.write_bytes(rom.d)
            for where, to in VISITS.items():
                if name in ('hero', 'npc', 'both') and where != '02/06' or name == 'over' and where != '19/00':
                    continue
                tag = f'{name}-{where.replace("/", "")}'
                rows = measure(rom, *run(path.resolve(), tag, to, out, args.state.resolve(), Path(args.mesence), lib))
                for row in rows:
                    bc, bd = (int(v, 16) for v in row['map'].split('/'))
                    row['predicted'] = predicted(base, sets, mapping, bc, bd, row['flags'], row['night'])
                    del row['flags'], row['wram']
                results[tag] = rows
        v = {tag: rows[-1] for tag, rows in results.items()}
        checks['셈과 잰 7E:1995'] = all(r['v1995'] == r['predicted'] for rows in results.values() for r in rows)
        checks['주인공 48타일은 7E:1995 를 바꾸지 않음'] = v['hero-0206']['v1995'] == v['original-0206']['v1995'] \
            and v['hero-0206']['sets'].get('70') == [48, 48]
        checks['인물 48타일은 그 세트만큼 늚'] = v['npc-0206']['sets'].get('70') == [48, 48]
        checks['주인공 사본과 인물 사본이 따로'] = v['both-0206']['sets'].get('70') == [96, 96] \
            and v['both-0206']['v1995'] == v['npc-0206']['v1995']
        over, orig = v['over-1900'], v['original-1900']
        # 그림 08 의 원래 세트 03 은 19/00 에서 그 그림만 써서 빠지는 것이 맞다. 그 밖에 빠진 세트는 넘쳐서 깨진 것이다.
        lost = sorted(set(orig['sets']) - set(over['sets']) - {f'{S.gfx_set(base, 0x08):02X}'})
        checks['넘치면 마지막 세트가 깨짐'] = over['v1995'] > W.OBJ_TILES >= orig['v1995'] and bool(lost) \
            and all(a == b for a, b in orig['sets'].values())
        print(f'over-1900 에서 칸 목록·VRAM 이 맞지 않게 된 세트: {" ".join(lost) or "없음"}')
        for tag, row in v.items():
            broken = ' '.join(s for s, (a, b) in sorted(row['sets'].items()) if a != b)
            print(f'{tag}: 7E:1995 {row["v1995"]:03X}(셈 {row["predicted"]:03X}), 세트 70 '
                  f'{"/".join(map(str, row["sets"].get("70", [0, 0])))}, 타일이 다른 세트 {broken or "없음"}, '
                  f'OAM 묶음 {row["oam"][0]}/{row["oam"][1]}')
        if args.sweep:
            same, other = sweep_model(base, args.sweep)
            print(f'objsweep 맵 {same + len(other)}곳 중 셈과 같은 곳 {same}, 다른 곳 {len(other)}: {", ".join(other)}')
        if args.maps:
            maps = args.maps.split(',')
            cells = entry_cells(str(args.rom), maps, 6)
            path = out / 'original.sfc'
            again = []
            for m in maps:
                tag = f'again-{m.replace("/", "")}'
                # entry_cells 는 (x, y[, 층]). 층을 빼면 dq5warp.lua 가 엉뚱한 층으로 내려놓을 수 있다.
                for row in measure(base, *run(path.resolve(), tag, ','.join([m, *map(str, cells[m])]), out,
                                               args.state.resolve(), Path(args.mesence), lib)):
                    bc, bd = (int(v, 16) for v in row['map'].split('/'))
                    again.append((m, row['map'], row['v1995'], predicted(base, {}, {}, bc, bd, row['flags'], row['night'])))
            results['again'] = [list(r) for r in again]
            checks['다시 잰 맵의 7E:1995 와 셈'] = all(m == got and v == want for m, got, v, want in again)
            for m in maps:
                rows = [r for r in again if r[0] == m]
                print(f'다시 잰 맵 {m}: 덤프 {len(rows)}개 ' + ', '.join(f'{got} 잼 {v:03X} 셈 {want:03X}' for _, got, v, want in rows))
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False, indent=1)
                                          + '\n', encoding='utf-8')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
