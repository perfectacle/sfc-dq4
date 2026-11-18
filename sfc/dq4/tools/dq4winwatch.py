"""MesenCE 장면에서 화면에 보인 UI(창·글자·커서·스프라이트)가 깨진 곳을 찾는 판정 틀.

형식은 sfc/dq4/docs/dq4-window-text-format.md 「UI 깨짐 검사」. lua/dq4winwatch.lua 가 장면 동안 BG3 이 바뀔 때마다 적은
모습(타일맵 32 × 32, BG3 글자 칸 000~3FF 그림, 스크롤, OAM, CGRAM)을 읽는다. dq4mesen.py 가 모든 실행 뒤에 부른다.

규칙은 같은 폴더의 dq4winrule_<이름>.py 하나에 하나씩 둔다. 규칙 파일은 NAME(걸린 칸에 붙는 이름), MODE('report' 또는
'fail'), ALLOW(예외 표: Allow 목록, 하나마다 까닭), check(screen) → [(줄, 열, 설명)] 을 둔다. screen 은 Screen 이고
찾은 창(rects)·위 창(tops)·테두리 선 판정(stroke_ok) 등을 한 번만 셈해 규칙끼리 나눠 쓴다. 규칙을 더하는 일은 파일 하나를
더하는 것이고 이 파일을 고치지 않는다.

창 찾기: 모서리 타일(08C, 겹친 창의 이음 모서리 08B. 좌우·상하 뒤집기로 네 모서리)에서 위 변·왼쪽 변을 따라 맞은편
모서리를 찾아 창 사각형을 정한다. 한쪽 모서리가 가려졌으면 다른 변으로 찾는다. 네 변 모두 반 넘게 테두리 선이 보여야
(위 창이 가린 칸은 보인 것으로 셈) 창이다. 두 모서리만 보이는 창은 옆 변을 따라가 위 창 안으로 들어간 자리를 가려진 변으로
둔다. 겹친 두 창은 겹친 곳에서 테두리가 더 성한 쪽이 위다. 테두리 그림이 롬 04:E978(08B~095)과 다른 모습(BG3 을 창 밖
일에 쓰는 화면)은 창 규칙에 빈 창 목록을 준다(screen.window_screen 이 거짓).

STEADY 프레임보다 짧게 보인 모습은 판정하지 않는다. 화면에 보이는 줄(세로 스크롤로 224점 안)에 든 칸만 걸린다.

  DQ4_WINDOW_WATCH  rules(기본): 규칙 파일의 MODE 대로. report: 모두 보고만. fail: 모두 실패로
  uv run --locked python sfc/dq4/tools/dq4winwatch.py --rom 롬 폴더…   (폴더의 winwatch.bin 을 판정해 찍는다)
"""
import argparse
from dataclasses import dataclass
import fnmatch
import functools
import importlib
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
LOG = 'winwatch.log'
DATA = 'winwatch.bin'
VERSION = 4
# 엔진 창 틀 그리기 기록 뒤 이만큼 프레임 안에 이어진 그리기는 한 번의 다시 그리기(창을 닫은 뒤 남은 창을 아래부터)로 본다
REPAINT_GAP = 8
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
MODES = ('rules', 'report', 'fail')


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


class Shot:
    __slots__ = ('id', 'frame', 'map', 'chr', 'hs', 'vs', 'oam', 'cgram', 'wram')

    def __init__(self, id_, frame, words, chr_, hs, vs, oam=bytes(544), cgram=bytes(512), wram=None):
        self.id, self.frame, self.map, self.chr, self.hs, self.vs = id_, frame, words, chr_, hs, vs
        self.oam, self.cgram = oam, cgram
        self.wram = wram or {}      # {7E 뱅크 주소: 바이트} 규칙이 선언한 WRAM 조각(wram_ranges)


@dataclass
class Record:
    """winwatch.bin 한 벌. 프레임 차례 목록은 모두 (프레임, …)."""
    shots: dict                 # {모습 번호: Shot}
    events: list                # [(프레임, 모습 번호 또는 -1)]
    draws: list                 # [(프레임, 창 번호, 사각형)] 엔진 창 틀 그리기
    oam: list                   # [(프레임, OAM 544바이트)] 화면이 켜진 동안 OAM 이 바뀐 프레임
    obj: list                   # [(프레임, 이름 자리, 둘째 표 거리(낱말), 크기 꼴, 밝기, 강제 블랭크)]
    maps: list                  # [(프레임, $BC, $BD, $1949, 전투 1/0)]
    objvram: list               # [(프레임, 이름 자리, 둘째 표 거리, OBJ VRAM 16KB)] 맵이 바뀐 뒤 한 번


def wram_ranges():
    """[(7E 뱅크 주소, 길이)] 규칙 파일들이 WRAM 에 선언한 조각(겹치면 합침)."""
    spans = sorted({(a, n) for m in rules() for a, n in getattr(m, 'WRAM', ())})
    out = []
    for a, n in spans:
        if out and a <= out[-1][0] + out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], a + n - out[-1][0]))
        else:
            out.append((a, n))
    return out


def wram_env(ranges=None):
    """dq4winwatch.lua 의 WINWATCH_WRAM 값."""
    return ','.join(f'{a:04X}:{n}' for a, n in (wram_ranges() if ranges is None else ranges))


def parse(data, ranges=None):
    """Record. 모습 기록은 앞 모습과 달라진 낱말·칸 그림·OAM·CGRAM 낱말만 담아 차례로 덮어 간다. 한 번도 적지 않은 칸 그림은
    0 으로 둔다(그 모습의 타일맵이 가리키지 않는 칸). WRAM 조각은 기록 첫머리 R 의 목록(ranges 로 덮을 수 있음)으로 W 의
    번호를 주소로 바꾼다."""
    shots, events, draws, oams, objs, maps, objvram = {}, [], [], [], [], [], []
    if data[:1] != b'V' or struct.unpack_from('<H', data, 1)[0] != VERSION:
        raise ValueError(f'winwatch 기록 판이 {VERSION} 이 아님')
    o = 3
    head = struct.Struct('<IIHHHHHHHH')
    words, chr_, oam, cgram = [0] * 1024, bytearray(TILES * 16), bytearray(544), bytearray(512)
    live, jv = bytearray(544), bytearray(0x4000)
    addrs = [a + k for a, n in (ranges or ()) for k in range(n)]
    wram, last = {}, None
    while o < len(data):
        kind = data[o:o + 1]
        if kind == b'R':
            (n,) = struct.unpack_from('<H', data, o + 1)
            spec = data[o + 3:o + 3 + n].decode('ascii')
            o += 3 + n
            if ranges is None:
                pairs = [p.split(':') for p in spec.split(',') if p]
                addrs = [int(a, 16) + k for a, m in pairs for k in range(int(m))]
        elif kind == b'S':
            id_, frame, _, _, hs, vs, ncell, ntile, noam, ncg = head.unpack_from(data, o + 1)
            o += 1 + head.size
            for _ in range(ncell):
                i, w = struct.unpack_from('<HH', data, o)
                words[i] = w
                o += 4
            for _ in range(ntile):
                (t,) = struct.unpack_from('<H', data, o)
                chr_[t * 16:t * 16 + 16] = data[o + 2:o + 18]
                o += 18
            for store, n in ((oam, noam), (cgram, ncg)):
                for _ in range(n):
                    i, w = struct.unpack_from('<HH', data, o)
                    store[2 * i:2 * i + 2] = struct.pack('<H', w)
                    o += 4
            last = shots[id_] = Shot(id_, frame, tuple(words), bytes(chr_), hs, vs, bytes(oam), bytes(cgram), dict(wram))
        elif kind == b'W':
            (n,) = struct.unpack_from('<H', data, o + 1)
            o += 3
            for _ in range(n):
                i, v = struct.unpack_from('<HB', data, o)
                if i < len(addrs):
                    wram[addrs[i]] = v
                o += 3
            if last is not None:
                last.wram = dict(wram)
        elif kind == b'D':
            frame, no, x, y, w, h = struct.unpack_from('<IBBBBB', data, o + 1)
            draws.append((frame, no, (y, x, y + h - 1, x + w - 1)))
            o += 10
        elif kind == b'E':
            frame, id_ = struct.unpack_from('<Ii', data, o + 1)
            events.append((frame, id_))
            o += 9
        elif kind == b'O':
            frame, n = struct.unpack_from('<IH', data, o + 1)
            o += 7
            for _ in range(n):
                i, w = struct.unpack_from('<HH', data, o)
                live[2 * i:2 * i + 2] = struct.pack('<H', w)
                o += 4
            oams.append((frame, bytes(live)))
        elif kind == b'B':
            objs.append(struct.unpack_from('<IHHBBB', data, o + 1))
            o += 12
        elif kind == b'M':
            maps.append(struct.unpack_from('<IBBBB', data, o + 1))
            o += 9
        elif kind == b'J':
            frame, base, off, n = struct.unpack_from('<IHHH', data, o + 1)
            o += 11
            for _ in range(n):
                (k,) = struct.unpack_from('<H', data, o)
                jv[k * 32:k * 32 + 32] = data[o + 2:o + 34]
                o += 34
            objvram.append((frame, base, off, bytes(jv)))
        else:
            raise ValueError(f'winwatch 기록이 {o} 에서 깨짐')
        if o > len(data):
            raise ValueError('winwatch 기록이 중간에 끊김')
    return Record(shots, events, draws, oams, objs, maps, objvram)


def stacks(draws):
    """[(프레임, [사각형, …])] 엔진 창 그리기 기록에서 그 프레임 뒤로 떠 있는 창(아래 → 위). 이미 있는 창(맨 위가 아님)을
    다시 그리면 창을 닫은 뒤의 다시 그리기로 보고, REPAINT_GAP 안에 이어진 그리기로 목록을 새로 짠다."""
    out, cur, last, burst, numbers = [], [], None, False, {}
    for frame, no, rect in draws:
        if burst and last is not None and frame - last > REPAINT_GAP:
            burst = False
        if not burst and rect in cur and rect != cur[-1]:
            cur, burst = [], True
        if rect in cur:
            cur.remove(rect)
        cur.append(rect)
        numbers[rect] = no
        last = frame
        out.append((frame, list(cur), dict(numbers)))
    return out


def planar(p0, p1):
    return tuple(tuple(((p0[r] >> (7 - c)) & 1) | (((p1[r] >> (7 - c)) & 1) << 1) for c in range(8)) for r in range(8))


def vram_tile(chr_, t):
    o = t * 16
    return planar(chr_[o:o + 16:2], chr_[o + 1:o + 16:2])


def flip(px, h, v):
    rows = px[::-1] if v else px
    return tuple(r[::-1] for r in rows) if h else tuple(rows)


WINDOW_TABLE = 0x04EB48         # 창 번호 × 2 → 창 레코드(뱅크 04)
WINDOW_COUNT = 0x94
SHARED_JP = 0x60B400            # 8000 아래(04:1AC0~)를 가리키는 창 레코드의 롬 사본(dq4menupatch.SHARED_JP)
DQ5_ROM = HERE.parents[2] / 'rom' / 'dq5.sfc'


def window_columns(rom, n):
    """창 n 레코드의 (x, 너비). 별칭(+0 bit7)은 별칭 자리 x 와 대상 창 너비."""
    def head(m):
        a = int.from_bytes(rom[lorom(WINDOW_TABLE + m * 2):lorom(WINDOW_TABLE + m * 2) + 2], 'little')
        o = lorom(0x040000 | a) if a >= 0x8000 else lorom(SHARED_JP) + a - 0x1AC0
        return rom[o:o + 3]
    b = head(n)
    if b[0] & 0x80:
        return b[0] & 0x1F, head(b[2])[2] & 0x1F
    return b[0] & 0x1F, b[2] & 0x1F


class Ref:
    """롬에서 읽은 테두리·가나 그림."""

    def __init__(self, rom):
        self.rom = rom
        o = lorom(BORDER_ROM)
        self.border = {t: planar(rom[o + i * 16:o + i * 16 + 8], rom[o + i * 16 + 8:o + i * 16 + 16])
                       for i, t in enumerate(range(BORDER_FIRST, BORDER_LAST + 1))}
        k = lorom(KANA_ROM)
        self.kana = {t: planar(rom[k + (t - 1) * 8:k + t * 8], b'\xff' * 8) for t in KANA}
        import dq4windowtext
        # 창 글자를 한글로 옮긴 빌드 단계(메뉴 단계부터)의 롬인가. 그 앞 단계(서곡·타이틀)와 원본 DQ5 는 가나가 맞다
        t = lorom(dq4windowtext.TEXT_BANK << 16 | dq4windowtext.INDEX)
        self.korean = any(rom[t:t + 0x2000].strip(b'\xff'))
        # 원본 DQ5 와 왼쪽 변(x)·오른쪽 변(x + 너비)이 다른 창 번호 {'왼쪽': {…}, '오른쪽': {…}}. 원본 롬이 없으면 None
        # (모든 창을 바뀐 것으로 봄)
        self.moved = None
        if DQ5_ROM.is_file():
            orig = DQ5_ROM.read_bytes()
            self.moved = {'왼쪽': set(), '오른쪽': set()}
            for n in range(WINDOW_COUNT):
                try:
                    (x, w), (ox, ow) = window_columns(rom, n), window_columns(orig, n)
                except IndexError:
                    x, w, ox, ow = 0, 0, 1, 1
                if x != ox:
                    self.moved['왼쪽'].add(n)
                if x + w != ox + ow:
                    self.moved['오른쪽'].add(n)
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


# 모서리에서 변을 따라 맞은편 모서리를 찾을 때 그 변 칸에 와야 할 테두리 타일(타일, 좌우, 상하): (출발, 찾는 모서리) 마다
WALKS = {('TL', 'TR'): (EDGE, 0, 0), ('TR', 'TL'): (EDGE, 0, 0), ('BL', 'BR'): (EDGE, 0, 1), ('BR', 'BL'): (EDGE, 0, 1),
         ('TL', 'BL'): (SIDE, 0, 0), ('BL', 'TL'): (SIDE, 0, 0), ('TR', 'BR'): (SIDE, 1, 0), ('BR', 'TR'): (SIDE, 1, 0)}


def windows(shot, stroke_ok=None):
    """[(위 줄, 왼쪽 열, 아래 줄, 오른쪽 열)] 화면 타일맵에서 찾은 창 사각형(끝 칸 포함). stroke_ok 를 주면 모서리 사이 변
    칸이 거의 다 테두리 선이어야 맞은편 모서리로 친다(넷에 하나까지 끊김을 봐줌). 겹친 창이 많으면 다른 창의 모서리를
    잇는 것을 막는다."""
    kinds = {(r, c): k for r in range(32) for c in range(32) if (k := corner_kind(word(shot, r, c)))}

    def first(r, c, dr, dc, want):
        start = kinds[(r, c)]
        tile = WALKS[(start, want)]
        r0, c0 = r, c
        r, c = r + 2 * dr, c + 2 * dc
        while 0 <= r < 32 and 0 <= c < 32:
            if kinds.get((r, c)) == want:
                if stroke_ok is not None:
                    n = max(abs(r - r0), abs(c - c0)) - 1
                    broken = sum(not stroke_ok(r0 + dr * i, c0 + dc * i, *tile) for i in range(1, n + 1))
                    if 4 * broken > n:
                        return None
                return r if dr else c
            r, c = r + dr, c + dc
        return None

    def walk(r, c, dr, dc, want):
        return first(r, c, dr, dc, want) if (r, c) in kinds else None

    found = set()
    for (r, c), k in kinds.items():
        if k == 'TL':
            c2, r2 = first(r, c, 0, 1, 'TR'), first(r, c, 1, 0, 'BL')
            if c2 is not None and r2 is None:
                r2 = walk(r, c2, 1, 0, 'BR')
            if r2 is not None and c2 is None:
                c2 = walk(r2, c, 0, 1, 'BR')
            if c2 is not None and r2 is not None:
                found.add((r, c, r2, c2))
        elif k == 'BR':
            c1, r1 = first(r, c, 0, -1, 'BL'), first(r, c, -1, 0, 'TR')
            if c1 is not None and r1 is None:
                r1 = walk(r, c1, -1, 0, 'TL')
            if r1 is not None and c1 is None:
                c1 = walk(r1, c, 0, -1, 'TL')
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


class Screen:
    """한 모습의 판정 재료. 규칙끼리 나눠 쓰는 셈(창 찾기·위 창·테두리 선)은 처음 쓸 때 한 번만 한다."""

    def __init__(self, shot, ref, scene='', engine=None, numbers=None):
        """engine: 엔진 그리기 기록으로 안 그 때의 창 사각형(아래 → 위). None 이면 화면에서만 찾는다. numbers: 사각형 →
        엔진 창 번호($0A00)."""
        self.shot, self.ref, self.scene = shot, ref, scene
        self.engine, self.numbers = engine, numbers or {}
        self._stroke = {}

    def word(self, r, c):
        return word(self.shot, r, c)

    def shown(self, r, c):
        return shown(self.shot, word(self.shot, r, c))

    def visible(self, r):
        return visible(self.shot, r)

    def wram(self, addr, n=1):
        """이 모습 때의 WRAM(7E 뱅크 주소부터 n 바이트). 규칙 파일의 WRAM 선언에 든 바이트만, 없는 바이트는 None."""
        return [self.shot.wram.get(addr + k) for k in range(n)]

    @functools.cached_property
    def window_screen(self):
        """BG3 테두리 칸 그림이 롬과 같은가(창을 그리는 화면인가)."""
        return all(vram_tile(self.shot.chr, t) == self.ref.border[t] for t in (CORNER, EDGE, SIDE))

    def stroke_ok(self, r, c, tile, h, v):
        """(r, c) 칸에 테두리 타일 tile(뒤집기 h·v)의 흰 선 점이 모두 보이는가."""
        key = r, c, tile, h, v
        if key not in self._stroke:
            px = self.shown(r, c)
            self._stroke[key] = px is not None and all(px[y][x] == 1 for y, x in self.ref.stroke(tile, h, v))
        return self._stroke[key]

    def frac(self, v, w):
        """창 v 의 테두리 칸 가운데 w 사각형 안에 든 것의 성한 비율(든 칸이 없으면 None)."""
        over = [cell for cell in border_cells(v) if inside(w, cell[0], cell[1])]
        return sum(self.stroke_ok(*cell) for cell in over) / len(over) if over else None

    def above(self, v, w):
        """v 가 w 위에 있다: 겹친 곳에서 v 의 테두리가 w 의 테두리보다 더 성하다(위 창의 테두리가 아래 창 위에 그려짐)."""
        a, b = self.frac(v, w), self.frac(w, v)
        return a is not None and (b is None or a > b)

    @functools.cached_property
    def engine_rects(self):
        """엔진이 그린 창 가운데 화면에 남은 것(아래 → 위). 테두리 칸이 반 넘게 선이 보이거나 더 위 창에 가려져야 남은
        것으로 친다(닫힌 뒤 다시 그리지 않고 지운 창은 빠짐)."""
        if not self.engine or not self.window_screen:
            return []
        out = []
        for i, w in enumerate(self.engine):
            if not (0 <= w[0] <= w[2] < 32 and 0 <= w[1] <= w[3] < 32) or w[2] - w[0] < 1 or w[3] - w[1] < 1:
                continue
            above = self.engine[i + 1:]
            cells = border_cells(w)
            seen = sum(self.stroke_ok(*cell) or any(inside(v, cell[0], cell[1]) for v in above) for cell in cells)
            # 위 창에 다 가려진 창은 화면에 없는 것과 같다. 모서리 하나는 선이 보여야 남은 창이다(다른 창 변과 겹친 변
            # 칸은 그 창의 선으로도 통과하므로 변으로는 가르지 않음)
            if 2 * seen > len(cells) and any(self.stroke_ok(*cell) for cell in cells[:4]):
                out.append(w)
        return out

    @functools.cached_property
    def rects(self):
        """[(위 줄, 왼쪽 열, 아래 줄, 오른쪽 열)] 이 모습의 창. 창 화면이 아니면 []. 엔진 그리기 기록이 있으면 그 창을
        먼저(겹친 차례 그대로) 두고, 화면에서 찾은 창 가운데 엔진 창과 모서리를 함께 쓰지 않는 것을 더한다."""
        if not self.window_screen:
            return []
        if self.engine:
            eng = self.engine_rects
            corners = {p for w in eng for p in ((w[0], w[1]), (w[0], w[3]), (w[2], w[1]), (w[2], w[3]))}
            extra = [w for w in self.found if not {(w[0], w[1]), (w[0], w[3]), (w[2], w[1]), (w[2], w[3])} & corners
                     and w not in eng]
            return eng + extra
        return self.found

    @functools.cached_property
    def found(self):
        """화면 타일맵에서만 찾은 창."""
        # 서로 다른 창의 모서리를 이어 붙인 사각형은 어느 변이 거의 다 끊겨 있다. 네 변 모두 반 넘게 성한(위에 있는 다른
        # 창에 가려진 칸은 성한 것으로 셈) 것만 창으로 본다. 가린 창이 먼저 정해져야 하므로 늘지 않을 때까지 되풀이
        rects, left = [], windows(self.shot, self.stroke_ok)
        while True:
            more = [w for w in left if all(
                2 * sum(self.stroke_ok(*cell) or any(inside(v, cell[0], cell[1]) and self.above(v, w) for v in rects)
                        for cell in side) > len(side) for side in sides(w))]
            if not more:
                break
            rects += more
            left = [w for w in left if w not in more]
        return rects + covered(self.shot, rects, self.stroke_ok)

    @functools.cached_property
    def tops(self):
        """{창: 그 창 위에 있는 창 목록}. 엔진 창끼리는 그린 차례, 그 밖은 겹친 곳의 테두리로 가른다."""
        eng = self.engine_rects if self.engine else []
        out = {}
        for w in self.rects:
            if w in eng:
                out[w] = eng[eng.index(w) + 1:] + [v for v in self.rects if v not in eng and self.above(v, w)]
            else:
                out[w] = [v for v in self.rects if v != w and self.above(v, w)]
        return out

    def hidden(self, w, r, c):
        """(r, c) 가 창 w 위의 다른 창에 가려졌는가."""
        return any(inside(v, r, c) for v in self.tops[w])

    def in_window(self, r, c):
        return any(inside(w, r, c) for w in self.rects)


@dataclass(frozen=True)
class Allow:
    """규칙 예외 하나. scene 은 장면 폴더 경로(라벨)에 맞추는 fnmatch 꼴, cells 는 (줄, 열) 모음(없으면 모든 칸).
    why 는 왜 깨진 것이 아닌지(원래 DQ5 화면과 같음 등)."""
    scene: str
    why: str
    cells: frozenset = None

    def matches(self, scene, r, c):
        return fnmatch.fnmatch(scene, self.scene) and (self.cells is None or (r, c) in self.cells)


def rules():
    """[규칙 모듈] dq4winrule_*.py, 이름 차례."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    out = []
    for p in sorted(HERE.glob('dq4winrule_*.py')):
        m = importlib.import_module(p.stem)
        for attr in ('NAME', 'MODE', 'ALLOW'):
            if not hasattr(m, attr):
                raise ValueError(f'{p.name}: {attr} 가 없음')
        if not hasattr(m, 'check') and not hasattr(m, 'check_run'):
            raise ValueError(f'{p.name}: check 나 check_run 이 없음')
        if m.MODE not in ('report', 'fail'):
            raise ValueError(f'{p.name}: MODE 는 report·fail')
        if any(not a.why.strip() for a in m.ALLOW):
            raise ValueError(f'{p.name}: 까닭 없는 예외')
        out.append(m)
    return out


def check(shot, ref, scene='', only=None, engine=None, numbers=None):
    """[(줄, 열, 규칙 이름, 설명, 규칙 MODE)] 걸린 칸. 한 칸은 먼저 건 규칙(이름 차례) 하나만 적는다."""
    screen = Screen(shot, ref, scene, engine, numbers)
    bad, marked = [], set()
    for rule in rules():
        if only and rule.NAME not in only:
            continue
        if not hasattr(rule, 'check'):
            continue
        for r, c, why in rule.check(screen):
            if (r, c) in marked or not screen.visible(r) or any(a.matches(scene, r, c) for a in rule.ALLOW):
                continue
            marked.add((r, c))
            bad.append((r, c, rule.NAME, why, rule.MODE))
    return bad


def analyze(folder, rom, scene=None):
    """[(모습, 처음 프레임, 이어 보인 가장 긴 프레임 수, 걸린 칸)] winwatch.bin 이 없으면 None. STEADY 프레임보다 짧게 보인
    모습은 보지 않는다."""
    path = Path(folder) / DATA
    if not path.is_file():
        return None
    rec = parse(path.read_bytes())
    shots, events, timeline = rec.shots, rec.events, stacks(rec.draws)
    ref = Ref(rom)
    scene = scene or str(folder)
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
        # 그린 프레임의 버퍼는 다음 NMI 에 화면으로 가므로 이 모습이 처음 보인 프레임 앞의 그리기까지 본다
        engine = None
        numbers = {}
        for f, stack, nos in timeline:
            if f >= first:
                break
            engine, numbers = stack, nos
        bad = check(shot, ref, scene, engine=engine, numbers=numbers)
        if bad:
            out.append((shot, first, n, bad))
    return out


@dataclass
class Run:
    """장면 하나 전체(check_run 규칙의 재료). record 는 Record, ref 는 Ref, scene 은 장면 폴더 경로 글."""
    record: Record
    ref: object
    scene: str


def run_hits(folder, rom, scene=None):
    """[(프레임, 규칙 이름, 설명, 규칙 MODE)] check_run 규칙이 장면 전체에서 건 것. 기록이 없으면 None."""
    path = Path(folder) / DATA
    if not path.is_file():
        return None
    run = Run(parse(path.read_bytes()), Ref(rom), scene or str(folder))
    out = []
    for rule in rules():
        if not hasattr(rule, 'check_run'):
            continue
        for frame, why in rule.check_run(run):
            if not any(a.cells is None and fnmatch.fnmatch(run.scene, a.scene) for a in rule.ALLOW):
                out.append((frame, rule.NAME, why, rule.MODE))
    return sorted(out)


def picture(shot, bad, margin=1):
    """걸린 칸 둘레의 타일맵 낱말(걸린 칸은 * 표)."""
    rows = sorted({b[0] for b in bad})
    cols = sorted({b[1] for b in bad})
    marks = {(b[0], b[1]) for b in bad}
    lines = []
    for r in range(max(0, rows[0] - margin), min(32, rows[-1] + margin + 1)):
        cells = []
        for c in range(max(0, cols[0] - 3), min(32, cols[-1] + 4)):
            cells.append(f'{word(shot, r, c):04X}{"*" if (r, c) in marks else " "}')
        lines.append(f'  {r:2d}| ' + ' '.join(cells))
    return lines


def report(folder, rom, label=None):
    """winwatch.log 를 쓰고 (걸린 모습 수, 실패로 치는 모습 수) 를 돌려준다(기록이 없으면 None)."""
    found = analyze(folder, rom, label)
    if found is None:
        return None
    lines, failing = [], 0
    force = mode()
    hits = run_hits(folder, rom, label) or []
    for frame, rule, why, rmode in hits:
        fail = force == 'fail' or (force == 'rules' and rmode == 'fail')
        failing += fail
        lines.append(f'프레임 {frame} {rule}: {why}{" 실패" if fail else ""}')
    for shot, first, n, bad in found:
        rules_ = sorted({b[2] for b in bad})
        fail = force == 'fail' or (force == 'rules' and any(b[4] == 'fail' for b in bad))
        failing += fail
        lines.append(f'모습 {shot.id} 프레임 {first}부터 {n}프레임 스크롤 {shot.hs},{shot.vs}: {len(bad)}칸 '
                     f'({", ".join(rules_)}){" 실패" if fail else ""}')
        lines += [f'  {r},{c} {rule}: {why}' for r, c, rule, why, _ in bad[:40]]
        lines += picture(shot, bad)
    (Path(folder) / LOG).write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    if hits:
        print(f'[winwatch] {label or folder}: 장면 규칙 {len(hits)}건(첫 프레임 {hits[0][0]} {hits[0][1]}) — '
              f'{Path(folder) / LOG}', file=sys.stderr)
    if found:
        first = found[0][3][0]
        print(f'[winwatch] {label or folder}: UI 깨짐 {len(found)}개 모습(실패 {failing}, 첫 프레임 {found[0][1]}, '
              f'{first[2]} {first[0]},{first[1]}) — {Path(folder) / LOG}', file=sys.stderr)
    return len(found) + len(hits), failing


def mode():
    m = os.environ.get('DQ4_WINDOW_WATCH', 'rules')
    if m not in MODES:
        raise SystemExit(f'DQ4_WINDOW_WATCH 는 {"·".join(MODES)} 가운데 하나: {m}')
    return m


class WindowBroken(RuntimeError):
    pass


def verdict(folder, rom_path, label=None):
    """report 를 쓰고, 실패로 치는 모습이 있으면 WindowBroken 을 올린다. 걸린 모습 수를 돌려준다."""
    rom = Path(rom_path).read_bytes()
    try:
        got = report(folder, rom, label)
    except (ValueError, struct.error) as e:
        if mode() == 'fail':
            raise WindowBroken(f'winwatch 기록을 읽지 못함: {Path(folder) / DATA}: {e}') from e
        print(f'[winwatch] {label or folder}: 기록을 읽지 못함: {e}', file=sys.stderr)
        return None
    if got is None:
        return None
    n, failing = got
    if failing:
        raise WindowBroken(f'UI 깨짐 {failing}개 모습: {Path(folder) / LOG}')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('folders', type=Path, nargs='+')
    a = ap.parse_args()
    rom = a.rom.read_bytes()
    total = 0
    for f in a.folders:
        got = report(f, rom)
        if got is None:
            print(f'{f}: 기록 없음')
            continue
        total += got[0]
        print(f'{f}: {got[0]}개 모습(실패 {got[1]})')
        text = (f / LOG).read_text(encoding='utf-8')
        if text:
            print(text, end='')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
