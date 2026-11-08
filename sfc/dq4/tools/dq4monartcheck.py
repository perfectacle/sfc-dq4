"""2장 전투 몬스터 NDS 그림(dq4monport)이 빌드 롬에 기대대로 들어갔는지 보는 검사. 형식 문서
sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」.

기대 그림은 dq4monport.doc 가 원래 DQ5 롬으로 쓰는 PNG(색 번호)와 monsters.json 의 색(BGR555)이다.
- 정적: 빌드 롬에서 PORT·EVENT 번호마다 그림(dq5monwrite.picture_grid, 옮긴 그림 표를 따라감)과 색(dq5mongfx.monster)을
  풀어 기대와 견준다. 빌드는 그 롬의 조우에 아직 나오지 않는 번호를 빼므로(dq4monport.build 의 appear), 원래 DQ5 그림·색과
  같은 번호는 「아직」 으로 두고, 기대와도 원래와도 다르면 실패다. 들어간 번호의 그림을 같이 쓰는 다른 DQ5 몬스터의 색도
  기대 색이어야 한다(dq4monport.doc).
- 전투 화면(snes9x 헤드리스): dq4battlescene 처럼 저장 기록으로 이어 해 탑 39/01 에 서고, 조우 루틴 23:E7C2 를
  force_code 로 덮어 번호 하나를 한 마리 무리로, 그다음 빌드 롬의 무리 조합에 있는 2~3종을 종마다 한 마리로(mixes)
  붙인다. 시드는 dq4ch1walkcheck.rng_for(0). 차례 창(7E:0A00 = 17)이 뜬 뒤
  SETTLE 프레임에 VRAM(libretro 메모리 3)과 직렬화 상태의 OAM·CGRAM 을 읽어, OBJ 만 그린 색 번호 격자(dq5mongfx.oam_grid)
  에서 번호마다 기대 그림이 픽셀마다 맞는 자리를 찾고, 그 자리를 덮는 OAM 의 팔레트 줄 색이 기대 색인지 본다. 같은 전투를 한 번
  더 돌려 덤프가 같은지(결정적인지)도 본다. 「아직」 번호는 빌드 롬의 그림(원래 DQ5 그림)과 견준다.

  python sfc/dq4/tools/dq4cores.py
  python sfc/dq4/tools/dq4monartcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/monartcheck [--static-only]
결과: OUT/results.json, OUT/expected/(기대 PNG·monsters.json), OUT/battle/<번호[-번호…]>.png(차례 창 프레임 화면).
DQ4_ASSETS(NDS 그림)가 있어야 한다.
"""
import argparse
import ctypes as C
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4monport  # noqa: E402
import dq5mongfx as M  # noqa: E402
import dq5monwrite as W  # noqa: E402
from dq5map import Rom  # noqa: E402

CORE = 'snes9x'
SCENE = 'monart'
SEED = 0
TURN_LIMIT = 3000                 # 전투가 걸린 뒤 차례 창이 뜨기까지(실측 140프레임)
SETTLE = 10                       # 차례 창이 뜬 뒤 덤프까지
# snes9x(dq4cores 가 고정한 fae2fea) 직렬화 상태: 「#!s9xsnp:」 머리 뒤 「이름:길이6자리:」 블록. PPU 블록 안에서 CGRAM 은
# 큰 끝 워드 256개, OAM 은 544바이트(낮은 표 512 + 높은 표 32). 자리는 전투 화면 덤프로 잼(OAM 은 match_oam 이 233/233,
# CGRAM OBJ 팔레트 0 은 몬스터 02 의 색과 같았음). 코어를 바꾸면 이 값을 다시 잰다
SNAPSHOT_MAGIC = b'#!s9xsnp:'
PPU_SIZE = 2652
PPU_CGRAM, PPU_OAM = 64, 2003
OBJ_PALETTES = 128                # CGRAM 에서 OBJ 팔레트 0 의 색 번호


def targets():
    """(종류, FC 번호, DQ5 번호) — dq4monport 의 PORT 와 EVENT."""
    return [('port', fc, m) for fc, m in dq4monport.PORT.items()] + \
        [('event', fc, m) for fc, m in dq4monport.EVENT.items()]


def expected(dq5, folder):
    """{DQ5 번호: (색 번호 격자, 색 목록)}, 같은 색을 받는 다른 번호 {번호: 색 목록}. dq4monport.doc 가 folder 에 쓴
    PNG·monsters.json 을 읽는다. dq5 는 원래 DQ5 롬(Rom)."""
    doc = json.loads(dq4monport.doc(dq5, folder).read_text())
    images = {int(p['picture'], 16): p['image'] for p in doc['pictures']}
    colors = {int(e['monster'], 16): e['colors'] for e in doc['monsters']}
    want = {}
    for _, _, m in targets():
        g = M.monster(dq5, m)[0]
        want[m] = (W.image_grid(folder / images[g]), colors[m])
    shared = {m: c for m, c in colors.items() if m not in want}
    return want, shared


def picture(rom, m):
    """빌드 롬에서 몬스터 m 의 (색 번호 격자, 색 목록). 격자는 dq4monport 의 PNG 와 같은 크기(가로·세로 8픽셀 칸)."""
    g, colors = M.monster(rom, m)
    return W.picture_grid(rom, g)[0], colors


def grid_diff(a, b):
    """두 격자에서 다른 픽셀 수. 크기가 다르면 None."""
    if len(a) != len(b) or any(len(x) != len(y) for x, y in zip(a, b)):
        return None
    return sum(p != q for x, y in zip(a, b) for p, q in zip(x, y))


def static_check(dq5, rom, want, shared):
    """번호마다 {'status': 'ported'|'later'|'wrong', …}, 문제 목록."""
    rows, problems = {}, []
    for kind, fc, m in targets():
        grid, colors = picture(rom, m)
        exp_grid, exp_colors = want[m]
        row = {'kind': kind, 'fc': f'{fc:02X}', 'picture': f'{M.monster(rom, m)[0]:02X}',
               'pixels_differ': grid_diff(grid, exp_grid), 'colors': colors == exp_colors}
        if row['pixels_differ'] == 0 and row['colors']:
            row['status'] = 'ported'
        elif (grid, colors) == picture(dq5, m):
            row['status'] = 'later'
        else:
            row['status'] = 'wrong'
            problems.append(f'{m:02X}(FC {fc:02X}): 빌드 롬 그림이 기대와도 원래 DQ5 와도 다름 '
                            f'(다른 픽셀 {row["pixels_differ"]}, 색 {"같음" if row["colors"] else "다름"})')
        rows[f'{m:02X}'] = row
    ported = {int(k, 16) for k, r in rows.items() if r['status'] == 'ported'}
    for other, colors in shared.items():
        g = M.monster(rom, other)[0]
        if any(M.monster(rom, m)[0] == g for m in ported) and M.monster(rom, other)[1] != colors:
            problems.append(f'{other:02X}: 들어간 그림 {g:02X} 을 같이 쓰는데 색이 기대와 다름')
    if not ported:
        problems.append('들어간 번호가 하나도 없음')
    return rows, problems


# --- 전투 화면 ---------------------------------------------------------------------------------------------

def snapshot_blocks(raw):
    """snes9x 직렬화 상태의 {블록 이름: (시작, 길이)}."""
    if not raw.startswith(SNAPSHOT_MAGIC):
        raise ValueError('snes9x 직렬화 상태가 아님')
    p, out = raw.index(b'\n') + 1, {}
    while p + 11 <= len(raw) and raw[p + 3:p + 4] == b':' and raw[p + 10:p + 11] == b':':
        n = int(raw[p + 4:p + 10])
        out[raw[p:p + 3].decode()] = (p + 11, n)
        p += 11 + n
    return out


def ppu_dump(raw):
    """(OAM 544바이트, CGRAM 색 256개)."""
    blocks = snapshot_blocks(raw)
    if blocks.get('PPU', (0, 0))[1] != PPU_SIZE:
        raise ValueError(f'PPU 블록 길이 {blocks.get("PPU")} — 코어가 바뀌었으면 PPU_OAM·PPU_CGRAM 을 다시 잴 것')
    at = blocks['PPU'][0]
    ppu = raw[at:at + PPU_SIZE]
    cgram = [ppu[PPU_CGRAM + 2 * i] << 8 | ppu[PPU_CGRAM + 2 * i + 1] for i in range(256)]
    return ppu[PPU_OAM:PPU_OAM + 544], cgram


def locate(grid, want):
    """OBJ 격자 grid(224줄 × 256)에서 want 의 불투명 픽셀이 가장 많이 맞는 자리. (맞은 수, 불투명 수, x, y, 상자 안에서
    want 는 투명인데 OBJ 가 그려진 픽셀 수)."""
    H, Wd = len(want), len(want[0])
    opaque = [(x, y, v) for y, row in enumerate(want) for x, v in enumerate(row) if v]
    best = (-1, 0, 0)
    for oy in range(0, len(grid) - H + 1):
        for ox in range(0, len(grid[0]) - Wd + 1):
            hit = sum(grid[oy + y][ox + x] == v for x, y, v in opaque[::7])
            if hit > best[0]:
                best = (hit, ox, oy)
    _, ox, oy = best
    hit = sum(grid[oy + y][ox + x] == v for x, y, v in opaque)
    extra = sum(1 for y, row in enumerate(want) for x, v in enumerate(row) if not v and grid[oy + y][ox + x])
    return hit, len(opaque), ox, oy, extra


def obj_palettes(oam, box):
    """box(x, y, 가로, 세로)와 겹치는 화면 안 OBJ 의 팔레트 번호 집합. oam_grid 와 같이 y + 1 줄부터 그린다."""
    bx, by, bw, bh = box
    out = set()
    for i in range(128):
        x, y, _, a = oam[i * 4:i * 4 + 4]
        h = oam[512 + (i >> 2)] >> ((i & 3) * 2) & 3
        x |= (h & 1) << 8
        if x >= 256:
            x -= 512
        if y >= 224:
            continue
        n = 16 if h >> 1 else 8
        if x < bx + bw and bx < x + n and y + 1 < by + bh and by < y + 1 + n:
            out.add(a >> 1 & 7)
    return out


def judge_screen(oam, vram, cgram, want, colors):
    """한 전투 덤프를 기대 그림·색과 견준 (요약, 문제 목록)."""
    hit, total, x, y, extra = locate(M.oam_grid(oam, vram), want)
    pals = obj_palettes(oam, (x, y, len(want[0]), len(want)))
    s = {'hit': hit, 'opaque': total, 'at': [x, y], 'extra': extra, 'palettes': sorted(pals)}
    problems = []
    if hit != total:
        problems.append(f'OBJ 그림 {hit}/{total} 픽셀만 맞음 @({x},{y})')
    if extra:
        problems.append(f'기대 그림이 투명한 자리에 OBJ 픽셀 {extra}개')
    if len(pals) != 1:
        problems.append(f'그림 자리의 OBJ 팔레트가 하나가 아님 {sorted(pals)}')
    else:
        p = OBJ_PALETTES + 16 * next(iter(pals)) + 1
        got = cgram[p:p + len(colors)]
        s['colors'] = got == colors
        if got != colors:
            problems.append(f'CGRAM 팔레트 {next(iter(pals))} 색이 기대와 다름')
    return s, problems


class Battles:
    """snes9x 하나로 이어 하기 → 탑에 선 상태를 만들고, 번호마다 그 상태에서 전투를 붙인다."""

    def __init__(self, rom_path, numbers, out):
        import dq4battlescene as B
        self.B = B
        # 몬스터가 먼저 움직여도 쓰러지거나 일행을 쓰러뜨리지 않게
        B.SCENES[SCENE] = {'what': '2장 몬스터 그림', 'group': [(numbers[0], 1)], 'turn': 'defend',
                           'monsters': {m: {'hp': 2000, 'attack': 0} for m in numbers}}
        out.mkdir(parents=True, exist_ok=True)
        self.run = B.Run(CORE, rom_path, SCENE, out)
        self.state = self.run.prepare()

    def close(self):
        import dq4savefixture as fx
        fx.close(self.run.c)

    def battle(self, numbers, shot=None):
        """번호마다 한 마리인 무리를 붙여 차례 창 뒤 SETTLE 프레임의 (OAM, VRAM, CGRAM, 정보)."""
        import dq4ch1walkcheck as wc
        import dq4compatcheck as cc
        B, c, w = self.B, self.run.c, self.run.w
        group = [(m, 1) for m in numbers]
        name = ' '.join(f'{m:02X}' for m in numbers)
        c.load(self.state)
        w.cheat_key, w.rom_cheats = None, {}
        c.poke(cc.sets(wc.rng_for(SEED)))
        c.poke([(B.GROUP + i, 0) for i in range(8)])
        w.rom_cheats = {'force': cc.rom_codes(B.ENCOUNTER, B.force_code(group, 0))}
        w.apply()
        sentinel = B.group_sentinel(group)
        t0 = c.n
        while bytes(c.rd(B.GROUP + i) for i in range(len(sentinel))) != sentinel:
            if c.n - t0 >= B.STEP_LIMIT:
                raise RuntimeError(f'{name}: 전투가 걸리지 않음')
            w.step({'down'})
        w.rom_cheats = {}
        w.apply()
        start = c.n
        while c.rd(B.WINDOW) != B.TURN_WINDOW:
            if c.n - start >= TURN_LIMIT:
                raise RuntimeError(f'{name}: 차례 창이 뜨지 않음')
            w.step()
        turn = c.n - start
        for _ in range(SETTLE):
            w.step()
        if shot:
            c.shot(shot)
        size = c.lib.retro_get_memory_size(3)
        vram = bytes((C.c_ubyte * size).from_address(c.lib.retro_get_memory_data(3)))
        oam, cgram = ppu_dump(c.save()[0])
        return oam, vram, cgram, {'turn_frame': turn}


def digest(oam, vram, cgram):
    return hashlib.sha1(oam + vram + bytes(v & 0xFF for v in cgram) + bytes(v >> 8 for v in cgram)).hexdigest()[:12]


def mixes(rom, numbers):
    """여러 종 무리 [(번호, …)]: 빌드 롬의 무리 조합(dq5monlimits.compositions) 가운데 numbers 만으로 된 2~3종 조합을, 아직
    남과 함께 나오지 않은 번호를 가장 많이 덮는 것부터 고른다. 전투는 종마다 한 마리로 붙여 원래 조합보다 작게 둔다."""
    import dq5monlimits
    pool = set(numbers)
    combos = sorted({tuple(sorted({m for m, _, _ in comp})) for comp in dq5monlimits.compositions(rom)[0]})
    combos = [c for c in combos if 2 <= len(c) <= 3 and set(c) <= pool]
    left, out = set(pool), []
    while True:
        best = max(combos, key=lambda c: (len(left & set(c)), len(c)), default=None)
        if best is None or not left & set(best):
            return out
        out.append(best)
        left -= set(best)


def screen_check(rom_path, rom, want, rows, out):
    """번호 하나씩, 그다음 여러 종 무리(mixes)로 전투 화면 판정. {무리 이름: {번호: 요약}}, 문제 목록."""
    numbers = [m for _, _, m in targets()]
    groups = [(m,) for m in numbers] + mixes(rom, [m for m in numbers if rows[f'{m:02X}']['status'] == 'ported'])
    shots = out / 'battle'
    shots.mkdir(parents=True, exist_ok=True)
    run = Battles(rom_path, numbers, out / 'core')
    result, problems = {}, []
    try:
        for group in groups:
            name = '-'.join(f'{m:02X}' for m in group)
            shot = shots / f'{name}.png'
            oam, vram, cgram, info = run.battle(group, shot)
            again = digest(*run.battle(group)[:3])
            entry = {**info, 'shot': str(shot), 'digest': digest(oam, vram, cgram), 'monsters': {}}
            p = []
            if again != entry['digest']:
                p.append(f'같은 전투를 다시 돌린 덤프가 다름 {entry["digest"]} / {again}')
            for m in group:
                key = f'{m:02X}'
                grid, colors = want[m] if rows[key]['status'] == 'ported' else picture(rom, m)
                s, q = judge_screen(oam, vram, cgram, grid, colors)
                entry['monsters'][key] = s
                p += [f'{key} {x}' for x in q]
                print(f'{name:9s} {key} {rows[key]["status"]:6s} {s["hit"]}/{s["opaque"]} @({s["at"][0]},{s["at"][1]}) '
                      f'팔레트 {s["palettes"]}', flush=True)
            entry['problems'] = p
            problems += [f'{name}: {x}' for x in p]
            result[name] = entry
    finally:
        run.close()
    return result, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True, help='빌드 롬(dq4-ch1-full.sfc)')
    ap.add_argument('--dq5', type=Path, default=ROOT / 'rom' / 'dq5.sfc')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--static-only', action='store_true', help='전투 화면 검사를 건너뜀')
    a = ap.parse_args(argv)
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    dq5 = Rom(a.dq5.read_bytes())
    rom = Rom(a.rom.read_bytes())
    want, shared = expected(dq5, a.out / 'expected')
    rows, problems = static_check(dq5, rom, want, shared)
    for key, r in rows.items():
        print(f'정적 {key} (FC {r["fc"]} {r["kind"]}) {r["status"]}')
    later = [k for k, r in rows.items() if r['status'] == 'later']
    report = {'rom': hashlib.sha1(a.rom.read_bytes()).hexdigest(), 'static': rows, 'later': later}
    if not a.static_only:
        report['screen'], more = screen_check(a.rom, rom, want, rows, a.out)
        problems += more
    report['problems'] = problems
    report['seconds'] = round(time.time() - t0, 1)
    (a.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    ported = sum(r['status'] == 'ported' for r in rows.values())
    print(f'들어감 {ported}개, 아직(조우에 없음) {len(later)}개 {" ".join(later)}; 문제 {len(problems)}개; '
          f'{report["seconds"]}초')
    for p in problems:
        print('  ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
