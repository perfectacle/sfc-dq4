"""몬스터 그림의 크기와 머리 +0~+4 를 바꾼 롬을 MesenCE 전투에서 dq5mongfx.layout 의 예측과 견준다.

그림 둘을 고친다(dq5monwrite.py 의 dq5monster/1, 크기는 PNG 로, 머리는 "header" 로).
  BIG    그림 4F(몬스터 E2, 6x7 칸)를 가로·세로 2칸 큰 8x9 상자에 왼쪽 1칸·위 2칸 띄워 놓는다.
  SMALL  그림 1C(몬스터 E6, 10x11 칸)에서 왼쪽 1칸·위 1칸, 오른쪽 1칸·아래 1칸을 잘라 8x9 로 줄인다.
둘 다 타격 기준점 +3·+4 를 그림이 옮긴 칸만큼 옮겨 "header" 로 쓴다. 그림자 보정은 상자 가운데·아랫단에서 재므로
(그래픽 형식의 「그림자」) 그림이 상자 안에서 옮긴 만큼 가운데·아랫단도 옮겨 그대로 둔다.
두 몬스터는 원본 무리 조합에서 늘 혼자 나와, dq5monwrite.py 의 조합 검사를 지난다.
첫 필드 이벤트 전투 무리를 BATTLE 로 덮어(dq5warp.lua) 큰 몬스터만·작은 몬스터만·둘과 고치지 않은 몬스터를 섞은 전투를
원본 롬과 고친 롬에서 싸운다. 덤프(dq5gfxdump.lua)에서 본다.
  OBJ 자리   OAM 의 보이는 OBJ (x, y) 묶음이 layout 의 상자 + 조각 자리와 같은지
  그림       몬스터마다 OBJ 색 번호(match_oam, 겹치는 픽셀은 뺌)와 VRAM OBJ 영역의 타일
  무리 표    7E:0C3D(가로 칸)·0C42(세로 칸 × 8)·0C5B(들어올림 × 8)·0C2E·0C33(그림자 보정)·0C38(그림자 모양)·
             0C51·0C56(타격 기준점)이 그 롬의 머리와 같은지(22:92C2)
  자리·줄 목록 7E:0D3D(그림)·0D4D(첫 16x16 자리)·0D6D(줄 목록 첫 칸)가 그림을 푸는 차례대로 0 부터 이어지는지
  그림자     같은 전투를 그림자 모양을 0 으로 덮은 롬에서도 싸워, 두 화면이 다른 픽셀이 모두 그래픽 형식 「그림자」의 식
             (스크린샷 y = 상자 위 + 8h + (+2) - 24 + dy, x = 상자 왼쪽 + 4w + (+1) + 1 + 구간 x)의 자리이고, 식의 자리 가운데
             안 보인 픽셀은 몬스터 OBJ 아래인지. 아래 창(스크린샷 y 152 부터)은 견주지 않는다
타격 효과는 큰 몬스터 1마리·작은 몬스터 1마리 전투에서 따로 본다(dq5hitlog.lua, A 를 눌러 싸우고 주인공 HP 를 999 로 고정).
  기준 칸    22:DB3D 가 7E:9E78·9E79 에 둔 값이 layout 의 상자로 센 (x / 8 + (+3), y / 8 + (+4) - 7)과 같은지
  효과 그림  두 프레임 뒤 BG3 타일맵에서 바뀐 칸을 기준 칸에서 잰 자리가 원본 롬과 고친 롬에서 같은지(같은 차례의 타격끼리)

  MESENCE=… python sfc/dq5/tools/dq5monsizecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5mongfx as M  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5monlimits import Pictures  # noqa: E402
from dq5monwrite import FORMAT, following_table, picture_grid  # noqa: E402
import dq5mesen  # noqa: E402

HERE = Path(__file__).resolve().parent
BIG, SMALL, PLAIN = (0x4F, 0xE2), (0x1C, 0xE6), 0x00     # (그림, 몬스터), 고치지 않는 몬스터(スライム)
DUMPF = '1200,1400'
SHOT_TOP = 7                    # MesenCE 스크린샷 y = OAM y - 7
WINDOW_TOP = 152                # 이 전투에서 아래 창이 덮기 시작하는 스크린샷 y
SHADOWS = 0x22B4FE
HIT_SET, HIT_MAXF = 0x22DB6D, 2200                        # 22:DB6A STA $9E79 다음 PC, dq5hitlog.lua 를 멈출 프레임
ATTACK = 'wait:300,' + 'a:8,wait:40,' * 25
GROUP_TABLE = {'w': 0x0C3D, 'h8': 0x0C42, 'raise8': 0x0C5B, 'shadow_dx': 0x0C2E, 'shadow_dy': 0x0C33,
               'shadow': 0x0C38, 'hit_x': 0x0C51, 'hit_y': 0x0C56}


def moved(grid, w, h, dx, dy):
    """grid 를 w x h 칸 상자에 칸 (dx, dy) 만큼 옮겨 놓는다. 밖으로 나가는 픽셀은 버린다."""
    out = [[0] * (w * 8) for _ in range(h * 8)]
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if 0 <= y + dy * 8 < h * 8 and 0 <= x + dx * 8 < w * 8:
                out[y + dy * 8][x + dx * 8] = v
    return out


def save(path, grid):
    image = Image.new('P', (len(grid[0]), len(grid)))
    image.putpalette([c for i in range(16) for c in (i * 16,) * 3])
    image.putdata([c for row in grid for c in row])
    image.save(path)


def document(rom, out):
    rows = []
    for name, (g, _), dw, (dx, dy) in (('big', BIG, 2, (1, 2)), ('small', SMALL, -2, (-1, -1))):
        grid, d = picture_grid(rom, g)
        hd = M.header(rom, g)
        w, h = d['w'] + dw, d['h'] + dw
        save(out / f'{name}.png', moved(grid, w, h, dx, dy))
        header = {'hit_x': min(max(hd['hit_x'] + dx, 0), w - 1), 'hit_y': min(max(hd['hit_y'] + dy, 0), h - 1)}
        rows.append({'picture': f'{g:02X}', 'image': f'{name}.png', 'header': header})
    doc = {'format': FORMAT, 'pictures': rows}
    (out / 'monster.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
    return doc


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True, text=True,
                   timeout=600)


def run(rom, name, groups, out, state, mesence, libdir, lua='dq5gfxdump.lua', **extra):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE', 'SET',
                        'WAGON', 'EVERY', 'TO')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1600', SETTLE='300',
               FIELD='341,56', BATTLE=','.join(f'{m:02X}:{n}' for m, n, _ in groups), TEST='wait:900', DUMPF=DUMPF)
    env.update(extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua' / lua),
                            '--Snes.DisableFrameSkipping=true', env=env, stdout=log, stderr=subprocess.STDOUT,
                            check=True, timeout=240)
    return dest


def shadowless(rom_path, dest):
    """머리 +0 의 그림자 모양(bit0-4)을 그림 BIG·SMALL·고치지 않는 몬스터의 그림 모두 0 으로 덮은 롬."""
    data = bytearray(rom_path.read_bytes())
    rom = Rom(bytes(data))
    with following_table():
        for g in (BIG[0], SMALL[0], M.monster(rom, PLAIN)[0]):
            data[lorom(M.head(rom, g))] &= 0xE0
    dest.write_bytes(bytes(data))
    return dest


def shadow_pixels(rom, groups):
    """layout 의 상자마다 그림자 모양의 가로 구간을 스크린샷 좌표로 늘어놓은 픽셀 모음."""
    out = set()
    with following_table():
        for m, bx, by in M.layout(rom, list(groups)):
            hd = M.header(rom, M.monster(rom, m)[0])
            if not hd['shadow']:
                continue
            a = 0x220000 | rom.u16(SHADOWS + hd['shadow'] * 2)
            for i in range(rom.u8(a)):
                dy, left, right = (rom.u8(a + 1 + i * 3 + j) for j in range(3))
                y = by + 8 * hd['h'] + hd['shadow_dy'] - 24 + dy
                x = bx + 4 * hd['w'] + hd['shadow_dx'] + 1
                out.update((x + k, y) for k in range(left, right))
    return out


def look_shadow(rom, dest, plain, groups):
    """그림자 있는 전투(dest)와 그림자 모양 0 인 전투(plain)의 화면 차이를 식의 자리와 견준다."""
    want = shadow_pixels(rom, groups)
    out = {}
    for tag in DUMPF.split(','):
        name = f'f{int(tag):05d}'
        a = Image.open(dest / f'{name}.png').convert('RGB')
        b = Image.open(plain / f'{name}.png').convert('RGB')
        pa, pb = a.load(), b.load()
        # 창 안(커서 깜빡임 등)은 두 실행이 어긋날 수 있고 그림자도 그 아래에 있으면 보이지 않으므로 창 위만 견준다.
        seen = {(x, y) for y in range(WINDOW_TOP) for x in range(a.size[0]) if pa[x, y] != pb[x, y]}
        grid = M.oam_grid((dest / f'{name}.oam').read_bytes(), (dest / f'{name}.vram').read_bytes())
        # oam_grid 의 줄은 OAM y + 1 이라 스크린샷 y 는 그보다 SHOT_TOP + 1 작다.
        covered = {(x, y - SHOT_TOP - 1) for y in range(224) for x in range(256) if grid[y][x]}
        hidden = {p for p in want - seen if p not in covered and p[1] < WINDOW_TOP}
        out[name] = {'seen': len(seen), 'want': len({p for p in want if p[1] < WINDOW_TOP}), 'outside': len(seen - want),
                     'under_obj': len(want & covered - seen), 'missing': len(hidden),
                     'match': bool(seen) and seen <= want and not hidden}
    return out


def hits(dest):
    """dq5hitlog.lua 결과 → [(프레임, (x, y), 기준 칸에서 잰 BG3 바뀐 칸들)]. 22:DB3D 가 쓴 것만."""
    changed = {}
    for line in (dest / 'bg3.txt').read_text(encoding='utf-8').split('\n'):
        if line.strip():
            h, col, row, value = line.split()
            changed.setdefault(int(h), []).append((int(col), int(row), value))
    out = []
    for line in (dest / 'hits.txt').read_text(encoding='utf-8').split('\n'):
        if not line.strip():
            continue
        n, x, y, pc = line.split()
        bank, addr = pc.split(':')
        if int(bank, 16) << 16 | int(addr, 16) != HIT_SET:
            continue
        x, y = int(x, 16), int(y, 16)
        # 창 글자(위 상태 창·아래 창)도 BG3 라, 몬스터가 있는 줄 5~19 만 본다.
        rel = sorted((c - x, r - y, v) for c, r, v in changed.get(int(n), []) if 5 <= r < 20 and v != '0000')
        out.append((int(n), (x, y), rel))
    return out


def predicted(rom, groups):
    """layout 의 상자마다 조각 자리, 상자 목록."""
    boxes = M.layout(rom, list(groups))
    want = Counter()
    for m, bx, by in boxes:
        for x, y, *_ in M.decode(rom, M.monster(rom, m)[0])['pieces']:
            want[(bx + x, by + y)] += 1
    return want, boxes


def seen_objs(oam):
    seen = Counter()
    for i in range(128):
        x, y = oam[i * 4], oam[i * 4 + 1]
        x |= (oam[512 + (i >> 2)] >> ((i & 3) * 2) & 1) << 8
        if y < 224:
            seen[(x - 512 if x >= 256 else x, y)] += 1
    return seen


def expected_table(rom, m):
    hd = M.header(rom, M.monster(rom, m)[0])
    return {'w': hd['w'], 'h8': hd['h'] * 8, 'raise8': hd['raise'] * 8, 'shadow_dx': hd['shadow_dx'] & 0xFF,
            'shadow_dy': hd['shadow_dy'] & 0xFF, 'shadow': hd['shadow'], 'hit_x': hd['hit_x'], 'hit_y': hd['hit_y']}


def look(rom, dest, groups):
    with following_table():
        want, boxes = predicted(rom, groups)
        pics = Pictures(rom)
        loads = pics.loads(groups)
        rows, start = [], 0
        for g, slot, _ in loads:
            rows.append([f'{g:02X}', slot, start])
            start += M.header(rom, g)['h']
        out = {'boxes': [[f'{m:02X}', x, y] for m, x, y in boxes], 'loads': rows}
        for tag in DUMPF.split(','):
            name = f'f{int(tag):05d}'
            oam, vram = (dest / f'{name}.oam').read_bytes(), (dest / f'{name}.vram').read_bytes()
            wram = (dest / f'{name}.wram').read_bytes()
            seen = seen_objs(oam)
            grid = M.oam_grid(oam, vram)
            objs = vram[0xC000:0x10000]
            per, drawn = {}, {}
            for m, _, _ in groups:
                g = M.monster(rom, m)[0]
                image = M.index_image(M.decode(rom, g))
                _, _, x, y = M.match_oam(rom, m, oam, vram)
                drawn[m] = {(x + i, y + j): v for j, row in enumerate(image) for i, v in enumerate(row) if v}
                tiles = [t for p in M.decode(rom, g)['pieces'] if not p[4] for t in p[3]]
                found = sum(1 for t in tiles if any(objs[o:o + 32] == t for o in range(0, len(objs), 32)))
                per[f'{m:02X}'] = {'at': [x, y], 'vram': [found, len(tiles)]}
            for m, pixels in drawn.items():
                others = {at for k, d in drawn.items() if k != m for at in d}
                mine = [(at, v) for at, v in pixels.items() if at not in others and 0 <= at[0] < 256 and 0 <= at[1] < 224]
                per[f'{m:02X}']['oam'] = [sum(grid[y][x] == v for (x, y), v in mine), len(mine)]
            table = {}
            for i, (m, _, _) in enumerate(groups):
                got = {k: wram[a + i] for k, a in GROUP_TABLE.items()}
                table[f'{m:02X}'] = {'got': got, 'match': got == expected_table(rom, m)}
            loaded = [[f'{wram[0x0D3D + i]:02X}', wram[0x0D4D + i], wram[0x0D6D + i]]
                      for i in range(16) if wram[0x0D3D + i] != 0xFF]
            out[name] = {'objs': [sum(seen.values()), sum(want.values())], 'objs_match': seen == want,
                         'monsters': per, 'table': table, 'loaded': loaded, 'loaded_match': loaded == rows}
    return out


def passed(result):
    if not all(v['match'] for v in result['shadow'].values()):
        return False
    for tag in DUMPF.split(','):
        r = result[f'f{int(tag):05d}']
        if not (r['objs_match'] and r['loaded_match'] and all(t['match'] for t in r['table'].values())
                and all(p['oam'][0] == p['oam'][1] > 0 and p['vram'][0] == p['vram'][1] for p in r['monsters'].values())):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/monsizecheck')
    ap.add_argument('--at', default='3B:8000', help='옮길 그림과 24비트 머리 포인터 표 자리(dq5monwrite.py --at)')
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
        document(base, out)
        tool('dq5monwrite.py', original, 'check', out / 'monster.json', '--at', args.at)
        tool('dq5monwrite.py', original, 'patch', out / 'monster.json', '-o', out / 'monster.dq5patch.json', '--at', args.at)
        edited = out / 'edited.sfc'
        tool('dq5build.py', original, 'build', out / 'monster.dq5patch.json', '--size', '2', '-o', edited,
             '--ips', out / 'edited.ips')
        patched = Rom(edited.read_bytes())
        with following_table():
            sizes = {f'{g:02X}': [[M.header(base, g)['w'], M.header(base, g)['h']],
                                  [M.header(patched, g)['w'], M.header(patched, g)['h']]] for g in (BIG[0], SMALL[0])}
        battles = {'big': ((BIG[1], 2, 0),), 'small': ((SMALL[1], 3, 0),),
                   'mixed': ((BIG[1], 1, 0), (PLAIN, 2, 0), (SMALL[1], 1, 0))}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results, failed = {'sizes': sizes}, []
        roms = (('original', original, shadowless(original, out / 'original-noshadow.sfc')),
                ('edited', edited, shadowless(edited, out / 'edited-noshadow.sfc')))
        for case, groups in battles.items():
            for kind, rom, plain in roms:
                name = f'{case}-{kind}'
                read = Rom(rom.read_bytes())
                dest = run(rom, name, groups, out, state, mesence, libdir)
                results[name] = look(read, dest, groups)
                results[name]['shadow'] = look_shadow(read, dest, run(plain, f'{name}-noshadow', groups, out, state,
                                                                      mesence, libdir), groups)
                if not passed(results[name]):
                    failed.append(name)
        for case, m in (('hit-big', BIG[1]), ('hit-small', SMALL[1])):
            got = {}
            for kind, rom, _ in roms:
                read = Rom(rom.read_bytes())
                with following_table():
                    (_, bx, by), = M.layout(read, [(m, 1, 0)])
                    hd = M.header(read, M.monster(read, m)[0])
                want = (bx // 8 + hd['hit_x'], by // 8 + hd['hit_y'] - 7)
                got[kind] = hits(run(rom, f'{case}-{kind}', ((m, 1, 0),), out, state, mesence, libdir, 'dq5hitlog.lua',
                                     TEST=ATTACK, MAXF=str(HIT_MAXF), POKE='7E2042=E7,7E2043=03'))
                results[f'{case}-{kind}'] = {'want': want, 'hits': [[n, list(at), len(rel)] for n, at, rel in got[kind]],
                                             'match': bool(got[kind]) and all(at == want for _, at, _ in got[kind])}
            same = len(got['original']) == len(got['edited']) and all(
                a[2] == b[2] for a, b in zip(got['original'], got['edited']))
            for kind in ('original', 'edited'):
                results[f'{case}-{kind}']['same_effect'] = same
                if not (results[f'{case}-{kind}']['match'] and same):
                    failed.append(f'{case}-{kind}')
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('크기(원래 → 고침): ' + ', '.join(f'그림 {g} {a[0]}x{a[1]} → {b[0]}x{b[1]}' for g, (a, b) in sizes.items()))
        for name, r in results.items():
            if name == 'sizes':
                continue
            if name.startswith('hit-'):
                print(f'{name}: 기준 칸 예측 {r["want"]}, 타격 {len(r["hits"])}번 '
                      + ' '.join(f'{n}:{tuple(at)}' for n, at, _ in r['hits'])
                      + f' {"같음" if r["match"] else "다름"}; 효과 그림 자리 원본과 {"같음" if r["same_effect"] else "다름"}')
                continue
            last = r[f'f{int(DUMPF.split(",")[-1]):05d}']
            print(f'{name}: 상자 {r["boxes"]}; OBJ {last["objs"][0]}/{last["objs"][1]} '
                  f'{"같음" if last["objs_match"] else "다름"}; '
                  + '; '.join(f'{m} OBJ {p["oam"][0]}/{p["oam"][1]} @({p["at"][0]},{p["at"][1]}) VRAM {p["vram"][0]}/{p["vram"][1]}'
                              for m, p in last['monsters'].items())
                  + f'; 무리 표 {"같음" if all(t["match"] for t in last["table"].values()) else "다름"}'
                  + f'; 그림·자리·줄 목록 {last["loaded"]} {"같음" if last["loaded_match"] else "다름"}'
                  + '; 그림자 ' + ', '.join(f'{v["seen"]}/{v["want"]}(OBJ 아래 {v["under_obj"]}) '
                                          f'{"같음" if v["match"] and not v["outside"] else "다름"}'
                                          for v in r['shadow'].values()))
        if failed:
            raise ValueError('불일치: ' + ', '.join(failed))
        print(f'전투 {len(battles) * 4 + 4}개가 예측과 같음')
        return 0
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
