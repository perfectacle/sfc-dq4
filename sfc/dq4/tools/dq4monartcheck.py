"""2장 전투 몬스터 NDS 그림(dq4monport)이 빌드 롬에 기대대로 들어갔는지 보는 검사. 형식 문서
sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」.

기대 그림은 dq4monport.doc 가 원래 DQ5 롬으로 쓰는 PNG(색 번호)와 monsters.json 의 색(BGR555)이다.
- 정적: 빌드 롬에서 PORT·EVENT 번호와 ART 의 그림을 쓰는 번호(빌린 번호의 그림 자리가 기대)마다 그림(dq5monwrite.picture_grid, 옮긴 그림 표를 따라감)과 색(dq5mongfx.monster)을
  풀어 기대와 견준다. 빌드는 그 롬의 조우에 아직 나오지 않는 번호를 빼므로(dq4monport.build 의 appear), 원래 DQ5 그림·색과
  같은 번호는 「아직」 으로 두고, 기대와도 원래와도 다르면 실패다. 들어간 번호의 그림을 같이 쓰는 다른 DQ5 몬스터의 색도
  기대 색이어야 한다(dq4monport.doc).
- 정적 팔레트(background_problems, color_problems): 전투 배경 레코드가 OBJ 팔레트 줄을 덮지 않는지, 모든 몬스터 번호의
  그림이 제 레코드 색 수 안의 색 번호만 쓰는지. 무리 k 의 그림 레코드 색은 OBJ 팔레트 k(줄 8 + k)의 1~n 번에만 들어가고
  (22:90C4·22:9121 → 22:A5A4), 나머지 칸은 22:8811 이 깐 맵 CGRAM 사본(7E:2D00)과 배경 레코드가 남긴 색이기 때문이다.
- 전투 화면(snes9x 헤드리스): dq4battlescene 처럼 저장 기록으로 이어 해 탑 39/01 에 서고, 조우 루틴 23:E7C2 를
  force_code 로 덮어 무리를 붙인다. 무리 차례 k 가 7E:1001+k 이고(force_code), 전투는 그 차례를 줄 k 로 놓는다(22:A0BE
  TXA/STA $0CD7,Y, 22:90C4 가 줄 8 + k 에 레코드 색을 깖). 장면은 번호마다 한 마리 무리, 빌드 롬의 나올 수 있는 무리 조합
  (reachable_orders)을 그 차례 그대로 종마다 한 마리로 붙여 (종, 줄) 짝을 탐욕으로 모두 덮는 것(cover), 한 조합에 같은 종이
  둘 이상 드는 종마다 그런 조합 하나(cover 의 twice), 격투장 시합 표의 시합 모두(arena_matches), 낮과 다른 밤 레코드를 가진
  배경마다 밤 전투(night_backgrounds)다. 시드는 dq4ch1walkcheck.rng_for(0). 차례 창(7E:0A00 = 17)이 뜬 뒤
  SETTLE 프레임에 VRAM(libretro 메모리 3)과 직렬화 상태의 OAM·CGRAM 을 읽어, OBJ 만 그린 색 번호 격자(dq5mongfx.oam_grid)
  에서 무리마다 기대 그림이 픽셀마다 맞는 자리를 찾고, 그 자리를 덮는 OAM 의 팔레트 줄이 그 무리의 줄이며 줄마다 CGRAM 색이
  그 무리 종의 색인지 본다. 전투가 걸린 뒤 차례 창까지 프레임마다도 보이는 몬스터(7E:0C60+i bit7)의 보이는 줄(7E:0CD7+i)
  색을 본다(등장 연출). 같은 전투를 한 번 더 돌려 덤프가 같은지(결정적인지)도 본다. 「아직」 번호와 대상 밖 종은 빌드 롬의
  그림과 견준다.

  python sfc/dq4/tools/dq4cores.py
  python sfc/dq4/tools/dq4monartcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/monartcheck [--static-only]
결과: OUT/results.json, OUT/expected/(기대 PNG·monsters.json), OUT/battle/<장면>.png(차례 창 프레임 화면).
DQ4_ASSETS(NDS 그림)가 있어야 한다.
"""
import argparse
import ctypes as C
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

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
# 전투 배경 팔레트(22:85EE → 22:8801). $1AA0(80 이상이면 72 를 뺌, 7F 로 자름)이 22:8983 낱말 표의 칸이고 그 아래 바이트
# & FC 가 $0D14 다. 표 바로 뒤 22:89E5 는 코드(22:86B8 JSR $89E5)라 표는 31 칸이다. 22:881D~8850: $1949 가 0 이면 $1AA1(밤,
# 22:8AFF)일 때 $0D14 + 2, 아니면 $0D14, $1949 가 1·2 이상이고 $0D14 < 1E 면 $0D14 + 98·+ B4 를 28:BDFC 낱말 표의 칸으로
# 써서 28 뱅크 레코드를 읽는다. 레코드는 [줄 수][첫 줄] 뒤 줄마다 [색 수 n][색 n개]이고, 22:A5A4 가 줄을 7E:2D00 + 20 × 줄
# (22:AB23)의 1~n 번 색에 쓴다
BG_INDEX, BG_COUNT = 0x228983, 0x31
BG_RECORDS = 0x28BDFC
BG_MODES, BG_MODE_BELOW = (0x98, 0xB4), 0x1E
BG_VALUE, BG_NIGHT = 0x7E1AA0, 0x7E1AA1
OBJ_LINE = 8                      # 줄 8 부터가 CGRAM 128 이상(OBJ 팔레트)
LINE_COLORS = 15
# 몬스터 i 의 보이는 OBJ 줄과 상태. 22:97C6 은 상태 bit7·6 이 켜진 몬스터의 줄에 4 를 더한다(22:9794 가 줄 k 를 4 + k 로 베낀 뒤)
SHOWN_LINE, SHOWN_STATE, SHOWN_BIT, SHIFTED = 0x7E0CD7, 0x7E0C60, 0x80, 4


def targets():
    """(종류, FC 번호, DQ5 번호) — dq4monport 의 PORT 와 EVENT, ART 의 그림을 쓰는 번호(art_users)."""
    return [('port', fc, m) for fc, m in dq4monport.PORT.items()] + \
        [('event', fc, m) for fc, m in dq4monport.EVENT.items()] + \
        [('art', fc, m) for fc in dq4monport.ART for m in sorted(dq4monport.art_users(fc))]


def sources():
    """{DQ5 번호: 그림 자리 번호}: 원래 DQ5 롬에서 그 번호가 받을 그림이 있는 번호(ART 는 빌린 번호, 나머지는 제 번호)."""
    return {m: d for _, d, users in dq4monport.entries() for m in users}


def expected(dq5, folder):
    """{DQ5 번호: (색 번호 격자, 색 목록)}, 같은 색을 받는 다른 번호 {번호: 색 목록}. dq4monport.doc 가 folder 에 쓴
    PNG·monsters.json 을 읽는다. dq5 는 원래 DQ5 롬(Rom)."""
    doc = json.loads(dq4monport.doc(dq5, folder).read_text())
    images = {int(p['picture'], 16): p['image'] for p in doc['pictures']}
    colors = {int(e['monster'], 16): e['colors'] for e in doc['monsters']}
    want, source = {}, sources()
    for _, _, m in targets():
        d = source[m]
        want[m] = (W.image_grid(folder / images[M.monster(dq5, d)[0]]), colors[d])
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
        elif (grid, colors) == picture(dq5, m) and m in dq4monport.LATER:
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


def background_slots(rom):
    """{28:BDFC 표 칸: [(배경 $1AA0, $1949 경우 0·1·2, 밤)]}: 배경 31 칸 모두가 읽을 수 있는 레코드 칸."""
    out = {}
    for bg in range(BG_COUNT):
        k = rom.u16(BG_INDEX + 2 * bg) & 0xFC
        out.setdefault(k, []).append((bg, 0, False))
        out.setdefault(k + 2, []).append((bg, 0, True))
        if k < BG_MODE_BELOW:
            for mode, add in enumerate(BG_MODES, 1):
                out.setdefault(k + add, []).append((bg, mode, False))
    return out


def background_record(rom, slot):
    """28:BDFC 표 칸의 (레코드 주소, 첫 줄, [줄마다 색 목록])."""
    at = 0x280000 | rom.u16(BG_RECORDS + slot)
    count, first = rom.u8(at), rom.u8(at + 1)
    lines, p = [], at + 2
    for _ in range(count):
        n = rom.u8(p)
        lines.append([rom.u16(p + 1 + 2 * i) for i in range(n)])
        p += 1 + 2 * n
    return at, first, lines


def background_problems(rom):
    """전투 배경 레코드(낮·밤, $1949 경우 셋)가 OBJ 팔레트 줄(8 이상)이나 줄 밖(색 15개 넘음)에 쓰는 것."""
    problems = []
    for slot, users in sorted(background_slots(rom).items()):
        at, first, lines = background_record(rom, slot)
        if first + len(lines) > OBJ_LINE or any(len(c) > LINE_COLORS for c in lines):
            bgs = ' '.join(sorted({f'{bg:02X}' for bg, _, _ in users}))
            problems.append(f'배경 {bgs} 레코드 {at >> 16:02X}:{at & 0xFFFF:04X}: 줄 {first}~{first + len(lines) - 1}, '
                            f'색 수 {[len(c) for c in lines]}')
    return problems


def color_problems(rom):
    """모든 몬스터 번호에서 그림이 쓰는 가장 큰 색 번호가 레코드 색 수(15 이하)를 넘는 것. 넘는 번호는 OBJ 팔레트의 맵·배경
    색으로 그려진다."""
    import dq5monwrite
    problems, top = [], {}
    for m in range(M.COUNT):
        g, colors = M.monster(rom, m)
        if g not in top:
            top[g] = max(max(row) for row in dq5monwrite.picture_grid(rom, g)[0])
        if top[g] > len(colors) or len(colors) > LINE_COLORS:
            problems.append(f'{m:02X}: 그림 {g:02X} 의 색 번호 {top[g]}, 레코드 색 {len(colors)}개')
    return problems


# --- 나올 수 있는 무리 조합 ------------------------------------------------------------------------------------

def event_groups():
    """이 해킹의 사건 무리 번호(dq4chapter1 이 dq4monport.build 에 넘기는 것과 같음)."""
    import dq4ch1event
    import dq4ch2event
    import dq4ch3event
    return [dq4ch1event.BOSS_GROUP, *(g['index'] for g in dq4ch2event.encounter_groups() +
                                      dq4ch3event.encounter_groups())]


def reachable_areas(dq5, prg):
    """이 롬에서 나올 수 있는 DQ5 구역. dq4groupbuild 가 zone-report.json 에 쓰는 것과 같은 dq4fieldencounter.docs 의 구역
    (FC 필드·3장·던전 구역이 받은 DQ5 구역)과 배의 SEA_AREAS 를 원래 DQ5 롬과 FC PRG 에서 바로 센다."""
    import dq4fieldencounter
    import dq4groupbuild
    import dq5encounterwrite
    enc = dq5encounterwrite.dump(Rom(dq5))
    _, _, report = dq4fieldencounter.docs(prg, dq5, enc, dq4groupbuild.dungeon_zones(prg).values())
    return {v['zone'] for v in report.values()} | set(dq4fieldencounter.SEA_AREAS)


def reachable_orders(rom, areas, events):
    """{무리 차례(번호 튜플): 처음 나온 곳}: 빌드 롬의 구역 표·사건 무리에서 dq5monlimits.compositions 가 늘어놓는 조합
    가운데 닿는 구역(areas)과 사건 무리(events)의 것. dq4monport.build 의 scoped 와 같은 거르기(닿지 않는 구역은 칸
    가중치 0)다. 튜플 차례는 조합의 무리 차례(마릿수 0 무리를 뺀 7E:1001~ 차례)다."""
    import dq5monlimits
    area = dq5monlimits.area
    names = {f'이벤트 무리 {g:02X}' for g in events}

    def scoped_area(r, n, *rest):
        ar = area(r, n, *rest)
        return ar if n in areas else {**ar, 'weights': [0] * len(ar['weights'])}
    dq5monlimits.area = scoped_area
    try:
        found, _ = dq5monlimits.compositions(rom)
    finally:
        dq5monlimits.area = area
    out = {}
    for k, where in found.items():
        if where.startswith('구역 ') or where in names:
            out.setdefault(tuple(m for m, _, _ in k), where)
    return out


def arena_matches(rom):
    """빌드 롬 격투장 시합 표(dq4shopport.arena_writes: 23:DA97 [몬스터][배율] ×4)에서 고를 수 있는 시합(문턱 23:DC27 이 0)의
    몬스터 차례. 26:8ECF 가 이 차례로 7E:1001~ 에 둔다."""
    import dq4shopport
    out = []
    for k in range(dq4shopport.ARENA_SIZE):
        if rom.u8(dq4shopport.ARENA_LEVELS + k):
            break
        row = [rom.u8(dq4shopport.ARENA_MATCHES + 8 * k + i) for i in range(8)]
        out.append(tuple(row[2 * i] for i in range(4) if row[2 * i] != 0xFF))
    return out


def pairs_of(orders, species, placed=None):
    """무리 차례들에서 species 종의 (종, 줄) 짝. placed(차례 → 무리마다 놓인 수)를 주면 놓이지 않는 무리는 뺀다."""
    return {(m, k) for o in orders for k, m in enumerate(o)
            if m in species and (placed is None or placed(o)[k])}


def cover(orders, species, done=(), placed=None):
    """(짝 덮기 무리 차례 목록, 같은 종 둘 이상 무리 차례 목록). 앞은 done 이 덮지 않은 species 의 (종, 줄) 짝을 가장 많이
    새로 덮는 차례부터 탐욕으로 고른다(같은 수면 무리가 많은 것, 그다음 번호 차례). 뒤는 한 조합에 같은 종이 둘 이상 드는
    species 의 종마다 하나가 되도록, 아직 고르지 않은 그런 종을 가장 많이 담은 차례부터 고른다."""
    orders = sorted(orders)
    each = {o: pairs_of([o], species, placed) for o in orders}
    left = set().union(*each.values()) - set(done)
    picked = []
    while left:
        best = max(orders, key=lambda o: (len(each[o] & left), len(o)))
        picked.append(best)
        left -= each[best]
    def doubled(o):
        lines = [m for m, k in each[o]]
        return {m for m in lines if lines.count(m) > 1}
    want = set().union(*(doubled(o) for o in orders)) - set().union(*(doubled(o) for o in picked))
    extra = []
    while want:
        best = max(orders, key=lambda o: (len(doubled(o) & want), len(o)))
        extra.append(best)
        want -= doubled(best)
    return picked, extra


def night_backgrounds(rom):
    """밤 레코드가 낮과 다른 배경 [(배경 $1AA0, 밤 레코드 주소)]을 밤 레코드마다 하나($1949 = 0)."""
    out, seen = [], set()
    for bg in range(BG_COUNT):
        k = rom.u16(BG_INDEX + 2 * bg) & 0xFC
        day, night = (background_record(rom, s)[0] for s in (k, k + 2))
        if day != night and night not in seen:
            seen.add(night)
            out.append((bg, night))
    return out


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
    g = np.asarray(grid)
    rows, cols = g.shape[0] - H + 1, g.shape[1] - Wd + 1
    hits = np.zeros((rows, cols), dtype=np.int32)
    for x, y, v in opaque[::7]:
        hits += g[y:y + rows, x:x + cols] == v
    # argmax 는 줄 차례로 처음 가장 큰 자리(위에서 아래, 왼쪽에서 오른쪽)
    oy, ox = divmod(int(hits.argmax()), cols)
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


def line_colors(cgram, line, n):
    p = OBJ_PALETTES + 16 * line + 1
    return cgram[p:p + n]


def only_lines(oam, lines):
    """OAM 사본에서 팔레트 줄이 lines 밖인 OBJ 를 화면 밖(y F0)으로 뺀 것."""
    out = bytearray(oam)
    for i in range(128):
        if (oam[i * 4 + 3] >> 1 & 7) not in lines:
            out[i * 4 + 1] = 0xF0
    return bytes(out)


def judge_group(oam, vram, cgram, order, pictures, placed=None, floating=None):
    """무리 차례 order(무리마다 한 마리)의 덤프 판정. pictures 는 {번호: (격자, 색 목록)}. 줄 k 의 CGRAM 색이 order[k] 의 색이고,
    종마다 그 종의 무리 수만큼 그림을 찾아(찾은 자리는 지우고 다시 찾음) 픽셀이 맞고 OBJ 팔레트 줄들이 그 종의 줄들인지.
    종마다 제 줄 OBJ 만 남긴 OAM(only_lines)으로 찾으므로 가린 픽셀도 그 종 OBJ 의 타일·팔레트로 다 맞아야 한다. 화면에서
    겹친 두 종은 한쪽이 floating(머리 띄움 번호)일 때만 받는다.
    placed(무리마다 놓인 수, dq5monlimits.Pictures.place)가 0 인 무리는 화면 폭에 들지 않아 보지 않는다. 다른 무리의 줄은
    그대로 제 차례다(22:A0BE 가 무리 칸 번호를 줄로 씀). ({번호: [자리마다 요약]}, 문제 목록)."""
    problems, out = [], {}
    shown = [k for k in range(len(order)) if placed is None or placed[k]]
    for k in shown:
        m = order[k]
        if line_colors(cgram, k, len(pictures[m][1])) != pictures[m][1]:
            problems.append(f'{m:02X} 줄 {k} CGRAM 색이 기대와 다름')
    for m in dict.fromkeys(order[k] for k in shown):
        want = pictures[m][0]
        lines = [k for k in shown if order[k] == m]
        # 띄운 몬스터(줄 2)는 땅 몬스터와 화면에서 겹친다. 무리 칸 줄 = 팔레트 줄이라(22:A0BE) 제 줄 OBJ 만 남겨 찾는다.
        # 다른 줄로 그려진 OBJ 는 남지 않아 픽셀이 모자라 걸린다
        own = only_lines(oam, set(lines))
        grid = M.oam_grid(own, vram)
        found = []
        for _ in lines:
            hit, total, x, y, extra = locate(grid, want)
            pals = obj_palettes(own, (x, y, len(want[0]), len(want)))
            found.append({'hit': hit, 'opaque': total, 'at': [x, y], 'extra': extra, 'palettes': sorted(pals)})
            if hit != total:
                problems.append(f'{m:02X} OBJ 그림 {hit}/{total} 픽셀만 맞음 @({x},{y})')
            if extra:
                problems.append(f'{m:02X} 기대 그림이 투명한 자리에 OBJ 픽셀 {extra}개 @({x},{y})')
            if len(pals) != 1:
                problems.append(f'{m:02X} 그림 자리의 OBJ 팔레트가 하나가 아님 {sorted(pals)} @({x},{y})')
            for yy in range(len(want)):
                for xx in range(len(want[0])):
                    if want[yy][xx]:
                        grid[y + yy][x + xx] = 0
        got = sorted(p for f in found for p in f['palettes'])
        if got != lines:
            problems.append(f'{m:02X} 그림의 OBJ 팔레트 {got}, 무리 줄 {lines}')
        out[f'{m:02X}'] = found
    # 화면에서 겹쳐도 되는 것은 한쪽이 띄운 몬스터(줄 2)일 때뿐이다. 땅 몬스터끼리는 가로로 늘어놓아 겹치지 않는다
    floating = floating or set()
    spots = [(m, {(f['at'][0] + xx, f['at'][1] + yy) for yy, row in enumerate(pictures[m][0])
                  for xx, v in enumerate(row) if v}) for m, fs in ((int(k, 16), v) for k, v in out.items()) for f in fs]
    for i, (a, pa) in enumerate(spots):
        for b, pb in spots[i + 1:]:
            if a not in floating and b not in floating and pa & pb:
                problems.append(f'{a:02X}·{b:02X} 땅 몬스터끼리 화면에서 겹침 {len(pa & pb)}픽셀')
    return out, problems


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

    def battle(self, numbers, shot=None, pokes=(), colors=None, counts=None):
        """번호마다 한 마리인 무리를 numbers 차례로 붙여 차례 창 뒤 SETTLE 프레임의 (OAM, VRAM, CGRAM, 정보). pokes 는 전투를
        붙이기 전에 한 번 쓰는 WRAM 값. colors({번호: 색 목록})를 주면 전투가 걸린 뒤 차례 창까지 프레임마다, 보이는
        몬스터 i(SHOWN_STATE bit7)의 보이는 줄(SHOWN_LINE) CGRAM 색이 numbers[i] 의 색인지 보고 정보의 'appear' 에 센다.
        counts 를 주면 무리마다 그 마릿수로 붙이고, 정보의 'placed' 에 엔진이 놓은 마릿수(무리마다)를 둔다."""
        import dq4ch1walkcheck as wc
        import dq4compatcheck as cc
        B, c, w = self.B, self.run.c, self.run.w
        group = [(m, 1) for m in numbers] if counts is None else list(zip(numbers, counts))
        name = ' '.join(f'{m:02X}' for m in numbers)
        c.load(self.state)
        w.cheat_key, w.rom_cheats = None, {}
        c.poke(cc.sets(wc.rng_for(SEED)))
        c.poke([(B.GROUP + i, 0) for i in range(8)])
        c.poke(list(pokes))
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
        appear = {'frames': 0, 'shifted_frames': 0, 'wrong': []}
        while c.rd(B.WINDOW) != B.TURN_WINDOW:
            if c.n - start >= TURN_LIMIT:
                raise RuntimeError(f'{name}: 차례 창이 뜨지 않음')
            w.step()
            if colors is None:
                continue
            shown = [(i, c.rd(SHOWN_LINE + i)) for i in range(len(numbers)) if c.rd(SHOWN_STATE + i) & SHOWN_BIT]
            if not shown:
                continue
            cgram = ppu_dump(c.save()[0])[1]
            appear['frames'] += 1
            appear['shifted_frames'] += any(line >= SHIFTED for _, line in shown)
            for i, line in shown:
                want = colors[numbers[i]]
                if line >= OBJ_LINE or line_colors(cgram, line, len(want)) != want:
                    appear['wrong'].append([c.n - start, i, line])
        turn = c.n - start
        for _ in range(SETTLE):
            w.step()
        if shot:
            c.shot(shot)
        size = c.lib.retro_get_memory_size(3)
        vram = bytes((C.c_ubyte * size).from_address(c.lib.retro_get_memory_data(3)))
        oam, cgram = ppu_dump(c.save()[0])
        info = {'turn_frame': turn, 'background': [c.rd(BG_VALUE), c.rd(BG_NIGHT)]}
        if colors is not None:
            info['appear'] = appear
        if counts is not None:
            info['placed'] = placed_counts(c.rd, len(numbers))
        return oam, vram, cgram, info


MONSTER_SLOTS = 16              # 몬스터 한 마리마다 7E:0C60~ 표(dq5 그래픽 형식 「배치와 그림자」)


def placed_counts(rd, groups):
    """차례 창이 뜬 뒤 무리마다 놓인 마릿수: 보이는(SHOWN_STATE bit7) 몬스터 칸을 그 칸의 줄(SHOWN_LINE = 무리 차례,
    22:A0BE)로 센다. rd 는 WRAM 바이트 읽기."""
    out = [0] * groups
    for i in range(MONSTER_SLOTS):
        line = rd(SHOWN_LINE + i)
        if rd(SHOWN_STATE + i) & SHOWN_BIT and line < groups:
            out[line] += 1
    return out


def digest(oam, vram, cgram):
    return hashlib.sha1(oam + vram + bytes(v & 0xFF for v in cgram) + bytes(v >> 8 for v in cgram)).hexdigest()[:12]


def scenes(rom, orders, arena, species, placed=None):
    """전투 장면 [{'kind', 'order', 'pokes'}]과 (종, 줄) 짝 {'all', 'covered'}. 한 마리 무리(single)는 대상 번호마다,
    cover 는 나올 수 있는 무리 조합과 격투장 시합의 대상 종 짝 가운데 single·arena 가 덮지 않은 것을, twice 는 같은 종이
    둘 이상 드는 조합을 그 종마다 하나, four 는 짝을 이미 덮었어도 넷째 줄까지 쓰는 조합 모두, night 는 밤 레코드마다 종이
    가장 많이 놓이는 장면 차례 하나를 밤($1AA1 = 1)·그 배경($1AA0)으로. 짝은 placed(차례 → 무리마다 놓인 수)로 화면 폭에
    드는 무리만 센다('listed' 는 놓임과 상관없이 센 수)."""
    out = [{'kind': 'single', 'order': (m,)} for m in species]
    out += [{'kind': 'arena', 'order': o} for o in arena]
    done = pairs_of([s['order'] for s in out], species, placed)
    picked, twice = cover(orders, species, done, placed)
    out += [{'kind': 'cover', 'order': o} for o in picked] + [{'kind': 'twice', 'order': o} for o in twice]
    four = sorted(o for o in orders if len(o) == 4 and o not in picked + twice)
    out += [{'kind': 'four', 'order': o} for o in four]
    shown = (lambda o: sum(map(bool, placed(o)))) if placed else len
    longest = max([s['order'] for s in out], key=lambda o: (len(set(o)), shown(o)))
    out += [{'kind': 'night', 'order': longest, 'pokes': [(BG_VALUE, bg), (BG_NIGHT, 1)]}
            for bg, _ in night_backgrounds(rom)]
    every = list(orders) + list(arena)
    can = pairs_of(every, species, placed)
    return out, {'all': len(can), 'covered': len(can & pairs_of([s['order'] for s in out], species, placed)),
                 'listed': len(pairs_of(every, species))}


def background_lines(rom, cgram, value, night):
    """$1AA0 = value, 밤 night($1949 = 0)의 배경 레코드 줄마다 CGRAM 이 그 색인지. 어긋난 줄 목록."""
    i = (value - 0x72 if value & 0x80 else value) & 0x7F
    _, first, lines = background_record(rom, (rom.u16(BG_INDEX + 2 * i) & 0xFC) + 2 * bool(night))
    return [first + j for j, colors in enumerate(lines)
            if cgram[16 * (first + j) + 1:16 * (first + j) + 1 + len(colors)] != colors]


def screen_check(rom_path, rom, want, rows, out, orders, arena):
    """장면(scenes)마다 전투 화면 판정. ({장면 이름: 요약}, 문제 목록, 짝 수)."""
    import functools
    import dq5monlimits
    layout = dq5monlimits.Pictures(rom)

    @functools.cache
    def placed_of(order):
        # 빌드 롬은 커진 그림을 옮겨 24비트 머리 표로 찾는다. 원래 머리 표로 읽으면 옮긴 그림의 크기·띄움을 원래 것으로 센다
        with W.following_table():
            return [x[1] for x in layout.place(tuple((m, 1, 0) for m in order))[0]]
    numbers = [m for _, _, m in targets()]
    plan, pairs = scenes(rom, orders, arena, numbers, placed_of)
    every = sorted({m for s in plan for m in s['order']})
    pictures = {m: want[m] if rows.get(f'{m:02X}', {}).get('status') == 'ported' else picture(rom, m) for m in every}
    colors = {m: c for m, (_, c) in pictures.items()}
    # 빌드 롬 그림 머리 +0 bit7(띄움, dq5 그래픽 형식 「줄과 높이」)
    floating = {m for m in every if rom.u8(W.head_of(rom, M.monster(rom, m)[0])) & 0x80}
    shots = out / 'battle'
    shots.mkdir(parents=True, exist_ok=True)
    run = Battles(rom_path, every, out / 'core')
    result, problems = {}, []
    try:
        for s in plan:
            order, pokes = s['order'], s.get('pokes', [])
            placed = placed_of(order)
            name = s['kind'] + '-' + '-'.join(f'{m:02X}' for m in order) + ''.join(f'-{a & 0xFFFF:04X}={v:02X}'
                                                                                 for a, v in pokes)
            shot = shots / f'{name}.png'
            oam, vram, cgram, info = run.battle(order, shot, pokes, colors)
            again = digest(*run.battle(order, pokes=pokes)[:3])
            entry = {'kind': s['kind'], **info, 'placed': placed, 'shot': str(shot), 'digest': digest(oam, vram, cgram)}
            p = []
            if again != entry['digest']:
                p.append(f'같은 전투를 다시 돌린 덤프가 다름 {entry["digest"]} / {again}')
            entry['monsters'], q = judge_group(oam, vram, cgram, order, pictures, placed, floating)
            p += q
            appear = info['appear']
            if not appear['frames']:
                p.append('등장 연출 중 보이는 몬스터가 있는 프레임이 없음')
            if appear['wrong']:
                p.append(f'등장 연출 중 보이는 줄 색이 다른 프레임 {len(appear["wrong"])}개 (첫 [프레임, 몬스터, 줄] '
                         f'{appear["wrong"][0]})')
            if pokes and info['background'] != [v for _, v in pokes]:
                p.append(f'배경·밤 {info["background"]} 이 붙인 값 {[v for _, v in pokes]} 과 다름')
            off = background_lines(rom, cgram, *info['background'])
            if off:
                p.append(f'배경 레코드 줄 {off} 의 CGRAM 색이 레코드와 다름')
            entry['problems'] = p
            problems += [f'{name}: {x}' for x in p]
            result[name] = entry
            print(f'{name} 차례창 {info["turn_frame"]} 등장 {appear["frames"]}프레임 '
                  f'{"통과" if not p else "문제 " + str(len(p))}', flush=True)
    finally:
        run.close()
    return result, problems, pairs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True, help='빌드 롬(dq4-ch1-full.sfc)')
    ap.add_argument('--dq5', type=Path, default=ROOT / 'rom' / 'dq5.sfc')
    ap.add_argument('--dq4', type=Path, default=ROOT / 'rom' / 'dq4.nes')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--static-only', action='store_true', help='전투 화면 검사를 건너뜀')
    a = ap.parse_args(argv)
    from kr_patch.fc import ines
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    dq5 = Rom(a.dq5.read_bytes())
    rom = Rom(a.rom.read_bytes())
    want, shared = expected(dq5, a.out / 'expected')
    rows, problems = static_check(dq5, rom, want, shared)
    for key, r in rows.items():
        print(f'정적 {key} (FC {r["fc"]} {r["kind"]}) {r["status"]}')
    palette = background_problems(rom) + color_problems(rom)
    print(f'정적 팔레트: 배경 레코드 {len(background_slots(rom))}칸, 몬스터 {M.COUNT}번호, 문제 {len(palette)}개')
    problems += palette
    later = [k for k, r in rows.items() if r['status'] == 'later']
    report = {'rom': hashlib.sha1(a.rom.read_bytes()).hexdigest(), 'static': rows, 'later': later, 'palette': palette}
    if not a.static_only:
        orders = reachable_orders(rom, reachable_areas(dq5.d, ines.prg(a.dq4.read_bytes())), event_groups())
        arena = arena_matches(rom)
        report['screen'], more, report['pairs'] = screen_check(a.rom, rom, want, rows, a.out, orders, arena)
        report['orders'], report['arena'] = len(orders), len(arena)
        if report['pairs']['covered'] != report['pairs']['all']:
            more.append(f'(종, 줄) 짝 {report["pairs"]["covered"]}/{report["pairs"]["all"]} 만 덮음')
        print(f'조합 {len(orders)}개, 격투장 {len(arena)}시합, (종, 줄) 짝 {report["pairs"]["covered"]}/'
              f'{report["pairs"]["all"]}, 장면 {len(report["screen"])}개')
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
