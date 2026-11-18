"""MesenCE 장면에서 화면에 보인 창의 테두리·창 밖 글자·깨진 칸을 찾는다.

형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 테두리 검사」. lua/dq4winwatch.lua 가 장면 동안 BG3 이 바뀔 때마다 적은
모습(타일맵 32 × 32, BG3 글자 칸 000~3FF 그림, 스크롤)을 읽는다. dq4mesen.py 가 모든 실행 뒤에 부른다.

창 찾기: 모서리 타일(08C, 겹친 창의 이음 모서리 08B. 좌우·상하 뒤집기로 네 모서리)에서 위 변·왼쪽 변을 따라 맞은편
모서리를 찾아 창 사각형을 정한다. 한쪽 모서리가 가려졌으면 다른 변으로 찾는다. 테두리 그림이 롬 04:E978(08B~095)과
다른 모습(타이틀 등 BG3 을 창 밖 일에 쓰는 화면)은 보지 않는다.

  테두리  창 네 변의 칸마다, 그 자리에 와야 할 테두리 타일(모서리 08C, 위·아래 변 08D, 옆 변 08E 와 그 뒤집기)의 흰 선
          점(색 1)이 화면 칸에도 모두 흰색이어야 한다. 이름 위 줄을 합성한 칸·탁점 붙은 변(092~095)·구분선 이음(08F)은
          선이 그대로라 통과한다. 다른 창 V 의 사각형 안에 든 칸은, V 의 테두리 가운데 이 창 사각형 안에 든 칸이 모두
          성하면(V 가 위에 있음) 가려진 것으로 친다. 메시지 창 아래 변 가운데의 넘김 표시(▼ 07B)는 원래 DQ5 가 변 위에
          그리므로 아래 변에서는 통과한다.
  창 밖   창 사각형 바로 바깥 한 칸 테두리(다른 창 사각형 밖)는 투명(색 0)이어야 한다. 글자가 창을 넘었다.
  깨짐    창 안쪽 칸 그림에 투명한 점(색 0)이 있다. 창 바탕을 뚫은 쓰레기 타일이다.
  가나    창 안쪽 칸 그림이 롬 가나(04:E528 1bpp, 둘째 평면 FF)와 같다. 옮기지 않은 일본어 글자다.

화면에 보이는 줄(세로 스크롤로 224점 안)에 든 칸만 걸린다.

  uv run --locked python sfc/dq4/tools/dq4winwatch.py --rom 롬 폴더…   (폴더의 winwatch.bin 을 판정해 찍는다)
"""
import argparse
import os
from pathlib import Path
import struct
import sys

LOG = 'winwatch.log'
DATA = 'winwatch.bin'
BORDER_ROM = 0x04E978           # 08B~095, 타일마다 평면 0 8바이트 + 평면 1 8바이트
BORDER_FIRST, BORDER_LAST = 0x8B, 0x95
KANA_ROM = 0x04E528             # 칸 01 부터 1bpp 8바이트
KANA = range(0x010, 0x079)
CORNERS = (0x8B, 0x8C)
CORNER, EDGE, SIDE = 0x8C, 0x8D, 0x8E
PROMPT = 0x7B                   # 메시지 넘김 표시 ▼
TILES = 0x400                   # 모습에 적는 BG3 글자 칸 수(타일맵 낱말의 칸 번호 10비트 전부)
SCREEN_H = 224
# 이만큼 이어 보인 모습만 판정한다. DQ5 는 메시지 창을 열 때 한두 프레임마다 아래에서 두 줄씩 키우며 그 줄의 옛 창을
# 지워, 그 사이 모습은 옛 창 아래쪽이 없거나 새 창 위 변이 없다(원래 엔진의 동작, 한 모습이 2프레임까지 감)
STEADY = 3
# DQ4_WINDOW_WATCH: report 면 winwatch.log 와 표준 오류에만 적고, fail 이면 걸린 실행을 실패로 올린다
MODES = ('report', 'fail')


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


class Shot:
    __slots__ = ('id', 'frame', 'map', 'chr', 'hs', 'vs')

    def __init__(self, id_, frame, words, chr_, hs, vs):
        self.id, self.frame, self.map, self.chr, self.hs, self.vs = id_, frame, words, chr_, hs, vs


def parse(data):
    """({모습 번호: Shot}, [(프레임, 모습 번호 또는 -1 = 화면 꺼짐)]). 모습 기록은 앞 모습과 달라진 낱말·칸 그림만 담아
    차례로 덮어 간다. 한 번도 적지 않은 칸 그림은 0 으로 둔다(그 모습의 타일맵이 가리키지 않는 칸)."""
    shots, events, o = {}, [], 0
    head = struct.Struct('<IIHHHHHH')
    words, chr_ = [0] * 1024, bytearray(TILES * 16)
    while o < len(data):
        kind = data[o:o + 1]
        if kind == b'S':
            id_, frame, _, _, hs, vs, ncell, ntile = head.unpack_from(data, o + 1)
            o += 1 + head.size
            for _ in range(ncell):
                i, w = struct.unpack_from('<HH', data, o)
                words[i] = w
                o += 4
            for _ in range(ntile):
                (t,) = struct.unpack_from('<H', data, o)
                chr_[t * 16:t * 16 + 16] = data[o + 2:o + 18]
                o += 18
            shots[id_] = Shot(id_, frame, tuple(words), bytes(chr_), hs, vs)
        elif kind == b'E':
            frame, id_ = struct.unpack_from('<Ii', data, o + 1)
            events.append((frame, id_))
            o += 9
        else:
            raise ValueError(f'winwatch 기록이 {o} 에서 깨짐')
        if o > len(data):
            raise ValueError('winwatch 기록이 중간에 끊김')
    return shots, events


def planar(p0, p1):
    return tuple(tuple(((p0[r] >> (7 - c)) & 1) | (((p1[r] >> (7 - c)) & 1) << 1) for c in range(8)) for r in range(8))


def vram_tile(chr_, t):
    o = t * 16
    return planar(chr_[o:o + 16:2], chr_[o + 1:o + 16:2])


def flip(px, h, v):
    rows = px[::-1] if v else px
    return tuple(r[::-1] for r in rows) if h else tuple(rows)


class Ref:
    """롬에서 읽은 테두리·가나 그림."""

    def __init__(self, rom):
        o = lorom(BORDER_ROM)
        self.border = {t: planar(rom[o + i * 16:o + i * 16 + 8], rom[o + i * 16 + 8:o + i * 16 + 16])
                       for i, t in enumerate(range(BORDER_FIRST, BORDER_LAST + 1))}
        k = lorom(KANA_ROM)
        self.kana = {t: planar(rom[k + (t - 1) * 8:k + t * 8], b'\xff' * 8) for t in KANA}
        self._stroke = {}

    def stroke(self, tile, h, v):
        key = tile, h, v
        if key not in self._stroke:
            px = flip(self.border[tile], h, v)
            self._stroke[key] = tuple((r, c) for r in range(8) for c in range(8) if px[r][c] == 1)
        return self._stroke[key]


def word(shot, r, c):
    return shot.map[(r & 31) * 32 + (c & 31)]


def shown(shot, w):
    """칸 낱말 w 가 화면에 그리는 8 × 8 색 번호(글자 칸 밖이면 None)."""
    t = w & 0x3FF
    if t >= TILES:
        return None
    return flip(vram_tile(shot.chr, t), w & 0x4000, w & 0x8000)


def corner_kind(w):
    if w & 0x3FF not in CORNERS:
        return None
    return {(0, 0): 'TL', (1, 0): 'TR', (0, 1): 'BL', (1, 1): 'BR'}[(bool(w & 0x4000), bool(w & 0x8000))]


def windows(shot):
    """[(위 줄, 왼쪽 열, 아래 줄, 오른쪽 열)] 화면 타일맵에서 찾은 창 사각형(끝 칸 포함)."""
    kinds = {(r, c): k for r in range(32) for c in range(32) if (k := corner_kind(word(shot, r, c)))}

    def first(r, c, dr, dc, want):
        r, c = r + 2 * dr, c + 2 * dc
        while 0 <= r < 32 and 0 <= c < 32:
            if kinds.get((r, c)) == want:
                return r if dr else c
            r, c = r + dr, c + dc
        return None

    found = set()
    for (r, c), k in kinds.items():
        if k == 'TL':
            c2, r2 = first(r, c, 0, 1, 'TR'), first(r, c, 1, 0, 'BL')
            if c2 is not None and r2 is None:
                r2 = first(r, c2, 1, 0, 'BR')
            if r2 is not None and c2 is None:
                c2 = first(r2, c, 0, 1, 'BR')
            if c2 is not None and r2 is not None:
                found.add((r, c, r2, c2))
        elif k == 'BR':
            c1, r1 = first(r, c, 0, -1, 'BL'), first(r, c, -1, 0, 'TR')
            if c1 is not None and r1 is None:
                r1 = first(r, c1, -1, 0, 'TL')
            if r1 is not None and c1 is None:
                c1 = first(r1, c, 0, -1, 'TL')
            if c1 is not None and r1 is not None:
                found.add((r1, c1, r, c))
    return sorted(found)


def border_cells(rect):
    """[(줄, 열, 테두리 타일, 좌우, 상하)]"""
    r1, c1, r2, c2 = rect
    out = [(r1, c1, CORNER, 0, 0), (r1, c2, CORNER, 1, 0), (r2, c1, CORNER, 0, 1), (r2, c2, CORNER, 1, 1)]
    out += [(r1, c, EDGE, 0, 0) for c in range(c1 + 1, c2)] + [(r2, c, EDGE, 0, 1) for c in range(c1 + 1, c2)]
    out += [(r, c1, SIDE, 0, 0) for r in range(r1 + 1, r2)] + [(r, c2, SIDE, 1, 0) for r in range(r1 + 1, r2)]
    return out


def sides(rect):
    """네 변(모서리 포함)의 테두리 칸 목록."""
    r1, c1, r2, c2 = rect
    cs = border_cells(rect)
    return [[x for x in cs if x[0] == r1], [x for x in cs if x[0] == r2], [x for x in cs if x[1] == c1],
            [x for x in cs if x[1] == c2]]


# 두 모서리만 보이는 창(나머지가 위 창에 가려짐): 같은 변의 두 모서리, 그 변에서 두 옆 변이 뻗는 쪽(줄·열 증감)
PAIRS = (('BL', 'BR', -1, 'col'), ('TL', 'TR', 1, 'col'), ('TL', 'BL', 1, 'row'), ('TR', 'BR', -1, 'row'))


def covered(shot, rects, stroke_ok):
    """찾은 창(rects)에 반쯤 가려져 두 모서리만 보이는 창. 보이는 두 모서리에서 옆 변을 따라가다 두 변이 모두 가린 창
    안으로 들어간 자리를 가려진 변으로 둔다(그 변은 가린 창 안이라 판정에서 가려진 것으로 친다)."""
    kinds = {(r, c): k for r in range(32) for c in range(32) if (k := corner_kind(word(shot, r, c)))}
    used = {p for rect in rects for p in ((rect[0], rect[1]), (rect[0], rect[3]), (rect[2], rect[1]), (rect[2], rect[3]))}
    out = []
    for a, b, step, along in PAIRS:
        for (r, c), k in kinds.items():
            if k != a or (r, c) in used:
                continue
            # 짝 모서리: 같은 줄(along = col)이면 오른쪽, 같은 열이면 아래로 가장 가까운 것
            far = None
            for x in range((c if along == 'col' else r) + 2, 32):
                p = (r, x) if along == 'col' else (x, c)
                if kinds.get(p) == b:
                    far = x
                    break
            if far is None or ((r, far) if along == 'col' else (far, c)) in used:
                continue
            ends = []
            for side in ((c, far) if along == 'col' else (r, far)):
                x = (r if along == 'col' else c) + step
                tile_h = 1 if along == 'col' and side == far else 0
                tile_v = 1 if along == 'row' and side == far else 0
                while 0 <= x < 32:
                    cell = (x, side) if along == 'col' else (side, x)
                    tile = SIDE if along == 'col' else EDGE
                    if not stroke_ok(*cell, tile, tile_h, tile_v):
                        break
                    x += step
                cell = (x, side) if along == 'col' else (side, x)
                ends.append(x if 0 <= x < 32 and any(inside(v, *cell) for v in rects) else None)
            if None in ends or abs(ends[0] - ends[1]) > 0:
                continue
            e = ends[0]
            if along == 'col':
                rect = (e, c, r, far) if step < 0 else (r, c, e, far)
            else:
                rect = (r, e, far, c) if step < 0 else (r, c, far, e)
            if rect[2] - rect[0] >= 1 and rect[3] - rect[1] >= 1 and rect not in out:
                out.append(rect)
    return out


def inside(rect, r, c):
    return rect[0] <= r <= rect[2] and rect[1] <= c <= rect[3]


def visible(shot, r):
    y = (r * 8 - shot.vs) % 256
    return y < SCREEN_H or y > 256 - 8


def check(shot, ref):
    """[(줄, 열, 규칙, 설명)] 걸린 칸. 테두리 그림이 롬과 다른 모습(창 밖 일에 BG3 을 쓰는 화면)은 []."""
    if any(vram_tile(shot.chr, t) != ref.border[t] for t in (CORNER, EDGE, SIDE)):
        return []
    memo = {}

    def stroke_ok(r, c, tile, h, v):
        key = r, c, tile, h, v
        if key not in memo:
            px = shown(shot, word(shot, r, c))
            memo[key] = px is not None and all(px[y][x] == 1 for y, x in ref.stroke(tile, h, v))
        return memo[key]

    def frac(v, w):
        """창 v 의 테두리 칸 가운데 w 사각형 안에 든 것의 성한 비율(든 칸이 없으면 None)."""
        over = [cell for cell in border_cells(v) if inside(w, cell[0], cell[1])]
        return sum(stroke_ok(*cell) for cell in over) / len(over) if over else None

    def above(v, w):
        """v 가 w 위에 있다: 겹친 곳에서 v 의 테두리가 w 의 테두리보다 더 성하다(위 창의 테두리가 아래 창 위에 그려짐)."""
        a, b = frac(v, w), frac(w, v)
        return a is not None and (b is None or a > b)

    # 서로 다른 창의 모서리를 이어 붙인 사각형은 어느 변이 거의 다 끊겨 있다. 네 변 모두 반 넘게 성한(위에 있는 다른 창에
    # 가려진 칸은 성한 것으로 셈) 것만 창으로 본다. 가린 창이 먼저 정해져야 하므로 늘지 않을 때까지 되풀이
    rects, left = [], windows(shot)
    while True:
        more = [w for w in left if all(
            2 * sum(stroke_ok(*cell) or any(inside(v, cell[0], cell[1]) and above(v, w) for v in rects)
                    for cell in side) > len(side) for side in sides(w))]
        if not more:
            break
        rects += more
        left = [w for w in left if w not in more]
    rects += covered(shot, rects, stroke_ok)
    tops = {w: [v for v in rects if v != w and above(v, w)] for w in rects}
    bad = []
    for w in rects:
        for r, c, t, h, v in border_cells(w):
            if stroke_ok(r, c, t, h, v) or any(inside(x, r, c) for x in tops[w]) or not visible(shot, r):
                continue
            if t == EDGE and v and word(shot, r, c) & 0x3FF == PROMPT:
                continue
            edge = (('위', '아래')[r == w[2]] if r in (w[0], w[2]) else ('왼쪽', '오른쪽')[c == w[3]])
            bad.append((r, c, '테두리', f'창 {w} 의 {edge} 변 칸이 {word(shot, r, c):04X}'))
    seen = set()
    for w in rects:
        r1, c1, r2, c2 = w
        ring = [(r1 - 1, c) for c in range(c1 - 1, c2 + 2)] + [(r2 + 1, c) for c in range(c1 - 1, c2 + 2)]
        ring += [(r, c1 - 1) for r in range(r1, r2 + 1)] + [(r, c2 + 1) for r in range(r1, r2 + 1)]
        for r, c in ring:
            if not (0 <= r < 32 and 0 <= c < 32) or (r, c) in seen or any(inside(x, r, c) for x in rects):
                continue
            seen.add((r, c))
            px = shown(shot, word(shot, r, c))
            if (px is None or any(any(row) for row in px)) and visible(shot, r):
                bad.append((r, c, '창 밖', f'창 {w} 바깥 칸이 {word(shot, r, c):04X}'))
    marked = {(b[0], b[1]) for b in bad}
    for w in rects:
        r1, c1, r2, c2 = w
        for r in range(r1 + 1, r2):
            for c in range(c1 + 1, c2):
                if (r, c) in marked or not visible(shot, r) or any(inside(v, r, c) for v in tops[w]):
                    continue
                wd = word(shot, r, c)
                px = shown(shot, wd)
                if px is None or any(0 in row for row in px):
                    rule = '깨짐'
                elif wd & 0x3FF in KANA and px == flip(ref.kana[wd & 0x3FF], wd & 0x4000, wd & 0x8000):
                    rule = '가나'
                else:
                    continue
                marked.add((r, c))
                bad.append((r, c, rule, f'창 {w} 안 칸이 {wd:04X}'))
    return bad


def analyze(folder, rom):
    """[(모습, 처음 프레임, 이어 보인 가장 긴 프레임 수, 걸린 칸)] winwatch.bin 이 없으면 None. STEADY 프레임보다 짧게 보인
    모습은 보지 않는다."""
    path = Path(folder) / DATA
    if not path.is_file():
        return None
    shots, events = parse(path.read_bytes())
    ref = Ref(rom)
    frames = {}
    for (f, i), nxt in zip(events, events[1:] + [(None, None)]):
        if i in shots:
            # 마지막 모습은 장면이 끝날 때까지 보였다(얼마나 더 보였는지는 모름)
            span = (nxt[0] - f) if nxt[0] is not None else STEADY
            first, n = frames.get(i, (f, 0))
            frames[i] = (first, max(n, span))
    out = []
    for i, shot in sorted(shots.items()):
        first, n = frames.get(i, (shot.frame, 0))
        if n < STEADY:
            continue
        bad = check(shot, ref)
        if bad:
            out.append((shot, first, n, bad))
    return out


def picture(shot, bad, margin=1):
    """걸린 칸 둘레의 타일맵 낱말(걸린 칸은 * 표)."""
    rows = sorted({r for r, *_ in bad})
    cols = sorted({c for _, c, *_ in bad})
    marks = {(r, c) for r, c, *_ in bad}
    lines = []
    for r in range(max(0, rows[0] - margin), min(32, rows[-1] + margin + 1)):
        cells = []
        for c in range(max(0, cols[0] - 3), min(32, cols[-1] + 4)):
            cells.append(f'{word(shot, r, c):04X}{"*" if (r, c) in marks else " "}')
        lines.append(f'  {r:2d}| ' + ' '.join(cells))
    return lines


def report(folder, rom, label=None):
    """winwatch.log 를 쓰고 걸린 모습 수를 돌려준다(기록이 없으면 None)."""
    found = analyze(folder, rom)
    if found is None:
        return None
    lines = []
    for shot, first, n, bad in found:
        rules = sorted({b[2] for b in bad})
        lines.append(f'모습 {shot.id} 프레임 {first}부터 {n}프레임 스크롤 {shot.hs},{shot.vs}: {len(bad)}칸 ({", ".join(rules)})')
        lines += [f'  {r},{c} {rule}: {why}' for r, c, rule, why in bad[:40]]
        lines += picture(shot, bad)
    (Path(folder) / LOG).write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    if found:
        print(f'[winwatch] {label or folder}: 창 깨짐 {len(found)}개 모습(첫 프레임 {found[0][1]}, '
              f'{found[0][3][0][2]} {found[0][3][0][0]},{found[0][3][0][1]}) — {Path(folder) / LOG}', file=sys.stderr)
    return len(found)


def mode():
    m = os.environ.get('DQ4_WINDOW_WATCH', 'report')
    if m not in MODES:
        raise SystemExit(f'DQ4_WINDOW_WATCH 는 {"·".join(MODES)} 가운데 하나: {m}')
    return m


class WindowBroken(RuntimeError):
    pass


def verdict(folder, rom_path, label=None):
    """report 를 쓰고, fail 모드면 걸린 것이 있을 때 WindowBroken 을 올린다."""
    rom = Path(rom_path).read_bytes()
    try:
        n = report(folder, rom, label)
    except (ValueError, struct.error) as e:
        if mode() == 'fail':
            raise WindowBroken(f'winwatch 기록을 읽지 못함: {Path(folder) / DATA}: {e}') from e
        print(f'[winwatch] {label or folder}: 기록을 읽지 못함: {e}', file=sys.stderr)
        return None
    if n and mode() == 'fail':
        raise WindowBroken(f'창 깨짐 {n}개 모습: {Path(folder) / LOG}')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('folders', type=Path, nargs='+')
    a = ap.parse_args()
    rom = a.rom.read_bytes()
    total = 0
    for f in a.folders:
        n = report(f, rom)
        if n is None:
            print(f'{f}: 기록 없음')
            continue
        total += n
        print(f'{f}: {n}개 모습')
        text = (f / LOG).read_text(encoding='utf-8')
        if text:
            print(text, end='')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
