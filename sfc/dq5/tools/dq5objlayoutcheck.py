"""칸 배치 쓰기·새 맵 OBJ 물체를 MesenCE에서 원본과 견준다.

고친 롬(dq5objlayout.py 로 만듦)은
  - 배(세트 68, 필드에서 7E:21BF bit4 로 배에 탄 주인공 그림 4A)의 아래 방향 두 프레임을 왼쪽 방향 칸으로 바꾸고,
  - 04/06 에 새 맵 OBJ 물체 하나를 더한다(원래 물체 0C 와 같은 2x4 칸을 좌우로 뒤집어 (36,9) 에). 표가 9바이트
    늘어 칸 바이트 일부가 --at 으로 옮겨진다.
  - 마법의 양탄자 부분 2(3x3)의 아래 방향 두 프레임을 좌우로 뒤집는다.
세 장면(필드의 배, 04/06, 필드의 양탄자)을 원본 롬과 함께 dq5gfxdump.lua 로 덤프하고 이렇게 본다.
  - 배: 주인공 슬롯 칸 목록이 세트 칸 + 첫 타일과 같고, 화면의 OAM 6장이 그 아래 방향 블록 그대로(자리·타일·반전)인지.
  - 물체: 슬롯 칸 목록과 OAM 묶음이 표대로이고, 새 물체의 OAM 자리가 원래 물체 0C 자리 + 8 × (셀 차이)인지.
  - 양탄자: dq5sprite.compare 가 부분 2 의 OAM 묶음을 고친 롬의 프레임으로 맞추는지.
  - 화면: 찾은 OAM 묶음을 덤프 VRAM·CGRAM 으로 칠한 픽셀이 스크린샷과 같은지.
  MESENCE=… python sfc/dq5/tools/dq5objlayoutcheck.py rom/dq5.sfc --state work/state/ship.mss --at 16:FE10
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
from dq5objlayout import FORMAT, dump  # noqa: E402

HERE = Path(__file__).resolve().parent
SHIP_SET = '68'
OLD_OBJECT, NEW_AT = 0x0C, (36, 9)
SCENES = [('ship', {'FIELD': '328,39', 'SET': '21BF|10'}),
          ('map', {'TO': '04/06,38,11,1'}),
          ('carpet', {'FIELD': '341,56', 'LATESET': '1954=80'})]
# 프레임 f 끝에 덤프한 OAM 은 f+1 의 화면에 나오므로 다음 프레임 스크린샷도 남긴다.
DUMPF = (700, 800)


def mirror(rows):
    """칸 줄을 좌우로 뒤집는다(자리를 바꾸고 h 를 뒤집음)."""
    flip = lambda t: t[1:] if t.startswith('h') else 'h' + t  # noqa: E731
    return [' '.join(flip(t) for t in reversed(r.split())) for r in rows]


def edit_doc(rom):
    base = dump(rom)
    ship = next(s for s in base['sets'] if s['set'] == SHIP_SET)
    objects = base['objects']
    new = dict(objects[OLD_OBJECT], x=NEW_AT[0], y=NEW_AT[1], cells=mirror(objects[OLD_OBJECT]['cells']))
    carpet = next(v for v in base['vehicles'] if v['part'] == '80-2')
    return {'format': FORMAT,
            'objects': objects + [new],
            'vehicles': [{'part': '80-2', 'cells': {k: mirror(carpet['cells'][k]) for k in ('down0', 'down1')}}],
            'sets': [{'set': SHIP_SET, 'cells': {'down0': ship['cells']['left0'], 'down1': ship['cells']['left1']}}]}


def tool(name, *args):
    return subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True,
                          text=True, timeout=300)


def run(rom, name, extra, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'TO',
                        'ROMPATCH', 'SAVE', 'SET', 'WAGON', 'EVERY')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1500', SETTLE='120',
               TEST='wait:400', DUMPF=','.join(f'{f},{f + 1}' for f in DUMPF), **extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    return dest


def frames(dest):
    for f in DUMPF:
        tag = dest / f'f{f:05d}'
        yield {k: Path(f'{tag}.{k}').read_bytes() for k in ('wram', 'vram', 'oam', 'cgram')} | \
            {'png': Image.open(dest / f'f{f + 1:05d}.png').convert('RGB')}


def w16(w, a):
    return w[a] | w[a + 1] << 8


def find_grid(items, words, cols):
    """OAM 에서 칸 워드(타일 9비트·반전 4000·8000·팔레트) 차례 그대로 가로 cols 격자로 놓인 묶음의 왼쪽 위."""
    n = len(words)
    for i in range(128 - n + 1):
        grp = items[i:i + n]
        if not all(grp):
            continue
        x0, y0 = grp[0][0], grp[0][1]
        if all(g[2] == w & 0x1FF and g[3] & 0xCE == (w >> 8) & 0xCE and
               g[0] == x0 + (j % cols) * 8 and g[1] == y0 + (j // cols) * 8 for j, (g, w) in enumerate(zip(grp, words))):
            return i, x0, y0
    return None


def opaque(vram, items):
    out = set()
    for x, y, t, a in filter(None, items):
        p = S.pixels(vram[0xC000 + t * 32:][:32])
        out |= {(x + xx, y + yy) for yy in range(8) for xx in range(8)
                if p[7 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]}
    return out


def screen_match(d, items, above=()):
    """OAM 묶음을 덤프 VRAM·CGRAM 으로 칠해 스크린샷과 견준 (같은 픽셀, 불투명 픽셀). items 의 y 는 그려지는 줄(OAM y + 1)이고,
    MesenCE 스크린샷은 겹쳐 보기 모드라 위 8줄을 잘라 내므로 8 을 뺀다. above(앞 OAM 슬롯)에 가린 픽셀은 세지 않는다."""
    vram, cg, png = d['vram'], d['cgram'], d['png']
    covered = opaque(vram, above)
    same = total = 0
    for x, y, t, a in items:
        p = S.pixels(vram[0xC000 + t * 32:][:32])
        for yy in range(8):
            for xx in range(8):
                ci = p[7 - yy if a & 0x80 else yy][7 - xx if a & 0x40 else xx]
                sx, sy = x + xx, y + yy - 8
                if not ci or (x + xx, y + yy) in covered or not (0 <= sx < 256 and 0 <= sy < png.height):
                    continue
                c = cg[(128 + ((a >> 1) & 7) * 16 + ci) * 2] | cg[(128 + ((a >> 1) & 7) * 16 + ci) * 2 + 1] << 8
                rgb = tuple((v << 3 | v >> 2) for v in (c & 31, c >> 5 & 31, c >> 10 & 31))
                total += 1
                same += png.getpixel((sx, sy)) == rgb
    return same, total


def ship_scene(rom, d):
    """주인공 슬롯 0 의 칸 목록과 아래 방향 OAM."""
    w = d['wram']
    rec = S.set_record(rom, int(SHIP_SET, 16))
    lst = w16(w, 0x8000 + w[0x3200])
    got = [w16(w, lst + i * 2) for i in range(48)]
    base = (got[0] & 0x1FF) - (rec['cells'][0] & 0x7F)
    want = [base + (c & 0x7F) | (0x4000 if c & 0x80 else 0) for c in rec['cells']]
    cells_ok = [g & 0x41FF for g in got] == want
    items = S.oam_groups(d['oam'])
    for f in (0, 1):
        words = [got[S.SIMPLE_BASE['down'] + f * 6 + i] for i in range(6)]
        hit = find_grid(items, words, 2)
        if hit:
            grp = items[hit[0]:hit[0] + 6]
            return {'set': SHIP_SET, 'cells': cells_ok, 'frame': f'down{f}', 'at': hit[1:],
                    'screen': screen_match(d, grp, items[:hit[0]])}
    return {'set': SHIP_SET, 'cells': cells_ok, 'frame': None}


def object_scene(rom, d):
    """04/06 의 물체마다 슬롯 칸 목록·OAM 자리·화면."""
    w = d['wram']
    base = w16(w, 0x1997)
    items = S.oam_groups(d['oam'])
    out = {}
    for k, mp in enumerate(S.map_object_places(rom)):
        if (mp['bc'], mp['bd']) != (0x04, 0x06):
            continue
        n = mp['cols'] * mp['rows']
        want = [base + (b & 0x7F) | (0x4000 if b & 0x80 else 0) | mp['palette'] << 9 for b in mp['cells']]
        slot = next((s for s in range(0x20) if w[0x3220 + s] == 0xFE and w[0x34E0 + s] == mp['cols'] and
                     w[0x3500 + s] == mp['rows'] and
                     [w16(w, w16(w, 0x8000 + w[0x3200 + s]) + i * 2) & 0x4FFF for i in range(n)] == want), None)
        hit = find_grid(items, want, mp['cols'])
        row = {'xy': (mp['x'], mp['y']), 'slot': slot, 'at': hit[1:] if hit else None}
        if hit:
            row['screen'] = screen_match(d, items[hit[0]:hit[0] + n], items[:hit[0]])
        out[k] = row
    return out


def carpet_scene(rom, d):
    stats = {}
    S.compare(rom, d['wram'], d['vram'], d['oam'], d['cgram'], stats, verbose=False)
    return {f'{vid:02X}-{k + 1}': v for (vid, k), v in stats.get('vehicles', {}).items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/objlayoutcheck')
    ap.add_argument('--at', default='16:FE10', help='새 칸 바이트 자리(dq5objlayout.py --at)')
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
        print(tool('dq5objlayout.py', original, 'check', out / 'layout.json', '--at', args.at).stdout, end='')
        tool('dq5objlayout.py', original, 'patch', out / 'layout.json', '-o', out / 'layout.dq5patch.json',
             '--at', args.at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'layout.dq5patch.json', '-o', edited, '--ips', out / 'edited.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results = {}
        for rom_name, path in (('original', original), ('edited', edited)):
            rom = Rom(path.read_bytes())
            for scene, extra in SCENES:
                dest = run(path, f'{rom_name}-{scene}', extra, out, state, mesence, libdir)
                fn = {'ship': ship_scene, 'map': object_scene, 'carpet': carpet_scene}[scene]
                results[f'{rom_name}-{scene}'] = [fn(rom, d) for d in frames(dest)]
        new = len(S.map_object_places(Rom(edited.read_bytes()))) - 1
        full = lambda s: s[0] == s[1] and s[1] > 0  # noqa: E731
        ships = results['original-ship'] + results['edited-ship']
        maps = results['edited-map']
        # 맵 OBJ 물체의 X·Y 는 셀(8픽셀) 단위다.
        old_xy = S.map_object_places(base)[OLD_OBJECT]
        expect = [(m[OLD_OBJECT]['at'][0] + 8 * (NEW_AT[0] - old_xy['x']), m[OLD_OBJECT]['at'][1] + 8 * (NEW_AT[1] - old_xy['y']))
                  if m[OLD_OBJECT]['at'] else None for m in maps]
        checks = {
            'ship': all(r['cells'] and r['frame'] and full(r['screen']) for r in ships),
            'ship-moved': results['original-ship'][0]['at'] == results['edited-ship'][0]['at'],
            'objects': all(r['slot'] is not None and r['at'] and full(r['screen'])
                           for m in results['original-map'] + maps for r in m.values()),
            'new-object': all(new in m and m[new]['at'] == e for m, e in zip(maps, expect)),
            'carpet': all(r.get('80-2', [0, 0])[1] > 0 for r in results['original-carpet'] + results['edited-carpet']),
        }
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=1, default=str) + '\n', encoding='utf-8')
        for case, rows in results.items():
            for f, r in zip(DUMPF, rows):
                print(f'{case} f{f}: {r}')
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
