"""winwatch 기록의 창 안 글자를 읽는다(UI 깨짐 검사 U2). 형식은 sfc/dq4/docs/dq4-window-text-format.md 「화면 글자 읽기」.

창마다(dq4winwatch.Screen.rects) 사각형 전체(테두리 칸 포함, 테두리 흰 선 점은 지움)의 칸 그림을 이어 점 격자로 만들고,
바탕색(가장 많은 색)이 아닌 점을 잉크로 본다. 9점 글꼴은 윗줄·구분선 칸까지 걸쳐 그리므로 테두리 칸도 넣는다.
- 롬 글자 칸: 칸 번호가 01~8A 이고 그림이 그 칸의 롬 1bpp 글자(04:E528)와 같은 칸은 그 바이트를 dq5text 로 푼 글자(NFKC)로
  읽고 잉크에서 지운다. 숫자·영문·가나·기호가 이 길이다.
- 그린 글자: 나머지 잉크는 빌드가 쓰는 Galmuri 글꼴(창 Galmuri9, 메시지 Galmuri11, 좁은 Galmuri7)의 글리프와 맞춘다.
  글리프 하나는 진행 폭만큼의 세로 열 무늬(띠 16줄, 한 의 윗줄이 1줄, dq4menupatch.Font.char)다. 띠 윗줄 y0 을 잉크 줄마다
  시험해, 왼쪽부터 열 무늬가 글리프와 꼭 같은 곳을 이어 가장 많은 잉크를 덮는 읽기를 고른다(parse_band 의 DP). 맞는 글리프가
  없는 잉크 열은 UNREAD 로 남긴다(추정으로 메우지 않음).
- 한 창의 글자를 줄(y 가 6점 안)로 묶어 x 차례로 잇고, 사이가 3점 이상이면 띄움을 넣는다.
"""
import functools
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

ROM_FONT = 0x04E528          # 칸 01 부터 1bpp 8바이트(dq4winwatch.KANA_ROM 과 같은 표)
ROM_TILES = range(0x01, 0x8B)
FONTS = ('galmuri9', 'message', 'dq5message', 'galmuri11', 'galmuri7')
MESSAGE_CELL = 13          # 메시지 글자 묶음은 13줄 칸의 아래에 맞춰 그린다(dq4menumsg, 24:A6DA)
# 테두리·밑줄과 모양이 같아 창 선을 글자로 읽게 되는 글자(게임 글에 쓰지 않음)
NOT_TEXT = set('‾▔▁_│─━┃¯') | {chr(c) for c in range(0x2500, 0x25A0)} | {chr(c) for c in range(0x2800, 0x2900)}
# 7B~8A 는 창 바이트를 dq5text 로 풀면 로마자·가나(탁점 접두 83·84 포함)지만 칸 그림은 기호다. 원본 DQ5 1bpp 그림으로 정한
# 뜻만 둔다(넘김 ▼ 는 dq4winwatch.PROMPT, 고르기 손가락 ▶ 는 상점 목록 화면). 그림으로 뜻을 못 정한 칸은 None
ROM_TILE_CHARS = {0x7B: '▼', 0x7C: '▶', 0x7D: '→', 0x7E: None, 0x7F: None, 0x80: None, 0x81: None, 0x82: '/',
                  0x83: None, 0x84: None, 0x85: ':', 0x86: 'Ex', 0x87: 'Lv', 0x88: '-', 0x89: '*', 0x8A: 'E'}
DQ5_ROM = HERE.parents[2] / 'rom' / 'dq5.sfc'
BAND = 16
UNREAD = '⍰'
UNREAD_COST = 8              # 못 읽은 잉크 열 하나를 덮은 점 몇 개로 칠지(읽기 고르기)
LINE_GAP = 6                 # 같은 줄로 묶는 글자 y 차
SPACE_GAP = 3                # 이만큼 비면 띄움


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


@functools.lru_cache(maxsize=None)
def font(name):
    import dq4menupatch as MP
    return MP.Font(name)


ROM_FOR_MESSAGES = None       # dq5message 표를 만들 빌드 롬(use_rom 으로 둠)


def use_rom(rom):
    """메시지 원본 글자 표를 이 빌드 롬 기준으로 다시 만든다."""
    global ROM_FOR_MESSAGES
    ROM_FOR_MESSAGES = bytes(rom)
    glyph_table.cache_clear()
    widths.cache_clear()
    band_height.cache_clear()


@functools.lru_cache(maxsize=None)
def glyph_table(name):
    """{진행 폭: {열 무늬 튜플: 글자}} — 열 무늬는 띠 16줄의 비트(줄 0 = bit0). 모양이 같은 글자는 앞 것.
    message 는 메시지 캔버스 글자: 빌드가 롬에 넣는 그대로(dq4menumsg.hangul_rows·punct_rows, 13줄 칸 바닥 맞춤)."""
    table = {}

    def put(ch, adv, pts):
        if ch in NOT_TEXT or adv <= 0 or any(not 0 <= y < BAND or not 0 <= x < adv for x, y in pts):
            return
        cols = [0] * adv
        for x, y in pts:
            cols[x] |= 1 << y
        if any(cols):
            table.setdefault(adv, {}).setdefault(tuple(cols), ch)

    if name == 'message':
        import dq4menumsg as MM
        f = font('galmuri11')
        for ch in MM.CHARS:
            try:
                adv, rows = (MM.CELL_W, MM.hangul_rows(f, ch)) if '가' <= ch <= '힣' else MM.punct_rows(f, ch)
            except (KeyError, ValueError):
                continue
            top = MESSAGE_CELL - len(rows)
            put(ch, adv, [(x, top + y) for y, row in enumerate(rows) for x, v in enumerate(row) if v == '#'])
        return table
    if name == 'dq5message':
        # 원본 DQ5 메시지 글자 가운데 빌드가 그림을 바꾸지 않은 것(*「」·가나 등). 바꾼 번호는 한글이라 CHARS 이름이 틀린다
        import dq5text
        from dq5map import Rom
        if not DQ5_ROM.is_file() or ROM_FOR_MESSAGES is None:
            return table
        orig, hack = Rom(DQ5_ROM.read_bytes()), Rom(ROM_FOR_MESSAGES)
        go, gh = dq5text.font_groups(orig), dq5text.font_groups(hack)
        for code, ch in enumerate(dq5text.CHARS):
            if not 0 < code < dq5text.GLYPHS:
                continue
            a = dq5text.glyph(orig, code, go)
            if a != dq5text.glyph(hack, code, gh):
                continue
            w, h, rows = a
            top = MESSAGE_CELL - h
            put(ch, w, [(x, top + y) for y, row in enumerate(rows) for x, v in enumerate(row) if v])
        return table
    f = font(name)
    for ch in f.glyphs:
        if isinstance(ch, str) and len(ch) == 1:
            put(ch, *f.char(ch))
    return table


def rom_glyphs(rom):
    """{칸 번호: (8 × 8 잉크 무늬, 글자 또는 None)} — 칸 01~8A 의 빌드 롬 1bpp 글자와 그 창 바이트를 원본 DQ5 로 푼 글자.
    빌드가 그림을 바꾼 칸(원본 DQ5 그림과 다름)은 바이트 뜻이 그림과 다를 수 있어 글자 없음(None)으로 둔다."""
    import dq5text
    from dq5map import Rom
    orig = DQ5_ROM.read_bytes() if DQ5_ROM.is_file() else rom
    r = Rom(orig)
    o = lorom(ROM_FONT)
    out = {}
    for t in ROM_TILES:
        rows = rom[o + (t - 1) * 8:o + t * 8]
        if rows != orig[o + (t - 1) * 8:o + t * 8]:
            out[t] = (tuple(tuple(bool(b >> (7 - x) & 1) for x in range(8)) for b in rows), None)
            continue
        ink = tuple(tuple(bool(b >> (7 - x) & 1) for x in range(8)) for b in rows)
        try:
            ch = dq5text.text(dq5text.string_codes(r, bytes((t,))))
        except Exception:  # noqa: BLE001 — 풀리지 않는 바이트는 글자 없음
            ch = None
        if t in ROM_TILE_CHARS:
            out[t] = (ink, ROM_TILE_CHARS[t])
            continue
        out[t] = (ink, unicodedata.normalize('NFKC', ch) if ch and len(ch) == 1 else None)
    return out


@functools.lru_cache(maxsize=None)
def band_height(name):
    """글꼴 글리프가 쓰는 띠 줄 수(가장 아래 점 + 1). 띠를 16줄로 보면 다음 줄 글자의 윗부분이 들어와 맞지 않는다
    (상태 창 이름처럼 9점 글자가 구분선 줄까지 걸치는 창)."""
    return max((max(v).bit_length() for keys in glyph_table(name).values() for v in keys), default=BAND)


@functools.lru_cache(maxsize=None)
def widths(name):
    return {ch: adv for adv, keys in glyph_table(name).items() for ch in keys.values()}


def width(name, ch):
    return widths(name).get(ch, 8)


def interior(screen, w):
    """창 w 사각형 전체의 점 격자(색 번호, 위 창에 가려진 칸·글자 칸 밖·테두리 흰 선은 None)와 {(줄, 열): 칸 낱말}."""
    r1, c1, r2, c2 = w
    rows, cols = r2 - r1 + 1, c2 - c1 + 1
    grid = [[None] * (cols * 8) for _ in range(rows * 8)]
    words = {}
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            if screen.hidden(w, r, c):
                continue
            wd = screen.word(r, c)
            px = screen.shown(r, c)
            words[r - r1, c - c1] = wd
            if px is None:
                continue
            t = wd & 0x3FF
            # 테두리 칸(08B~095)은 글자가 아니다: 창 제목·9점 글자의 윗부분은 테두리 줄에 놓인 다른 칸에 그린다
            border = t in screen.ref.border
            # 테두리 줄·열에 놓인 다른 칸(창 제목·걸친 글자)도 그 자리 테두리 선 점은 선이다
            line = set()
            if r in (r1, r2):
                line |= set(screen.ref.stroke(0x8D, 0, r == r2))
            if c in (c1, c2):
                line |= set(screen.ref.stroke(0x8E, c == c2, 0))
            for y in range(8):
                grid[(r - r1) * 8 + y][(c - c1) * 8:(c - c1 + 1) * 8] = (
                    [None] * 8 if border else [None if (y, x) in line else v for x, v in enumerate(px[y])])
    return grid, words


def background(grid):
    from collections import Counter
    count = Counter(v for row in grid for v in row if v is not None)
    return count.most_common(1)[0][0] if count else None


def parse_band(ink, y0, name):
    """띠 윗줄 y0 의 한 줄 읽기: (덮은 잉크 점 수, 못 읽은 열 수, [(x, 글자)]). 이어진 못 읽음 열은 하나로 적는다."""
    table = glyph_table(name)
    W, H = len(ink[0]), len(ink)
    h = band_height(name)
    col = [sum(1 << k for k in range(h) if 0 <= y0 + k < H and ink[y0 + k][x]) for x in range(W)]
    best = [None] * (W + 1)
    best[0] = (0, 0, ())

    def better(a, b):
        return b is None or (a[0] - UNREAD_COST * a[1], -len(a[2])) > (b[0] - UNREAD_COST * b[1], -len(b[2]))

    for x in range(W):
        if best[x] is None:
            continue
        score, unread, chars = best[x]
        cand = []
        if not col[x]:
            cand.append((x + 1, (score, unread, chars)))
        else:
            tail = chars[-1] if chars else None
            mark = chars if tail and tail[1] == UNREAD and tail[0] == x - 1 else chars + ((x, UNREAD),)
            if tail and tail[1] == UNREAD and tail[0] == x - 1:
                mark = chars[:-1] + ((x, UNREAD),)
            cand.append((x + 1, (score, unread + 1, mark)))
        for adv, keys in table.items():
            if x + adv <= W:
                ch = keys.get(tuple(col[x:x + adv]))
                if ch is not None:
                    gain = sum(bin(v).count('1') for v in col[x:x + adv])
                    cand.append((x + adv, (score + gain, unread, chars + ((x, ch),))))
        for nx, v in cand:
            if better(v, best[nx]):
                best[nx] = v
    return best[W]


def read_window(screen, w, rom_table):
    """창 w 의 [(y, x, 글자열)] — y·x 는 창 사각형(테두리 포함) 안 점 자리."""
    grid, words = interior(screen, w)
    if not grid or not grid[0]:
        return []
    # 바탕색은 칸 줄마다 센다: 창 제목은 위 테두리 줄에 바탕과 글자색을 바꿔 그린다(창 제목 색)
    ink = []
    for r0 in range(0, len(grid), 8):
        bg = background(grid[r0:r0 + 8]) if any(v is not None for row in grid[r0:r0 + 8] for v in row) else None
        ink += [[v is not None and v != bg and v != 0 for v in row] for row in grid[r0:r0 + 8]]
    chars = []          # (줄 y, x, 글자, 폭)
    for (r, c), wd in sorted(words.items()):
        t = wd & 0x3FF
        if t not in rom_table:
            continue
        glyph, ch = rom_table[t]
        g = [list(row[::-1]) if wd & 0x4000 else list(row) for row in glyph]
        if wd & 0x8000:
            g = g[::-1]
        cell = [[ink[r * 8 + y][c * 8 + x] for x in range(8)] for y in range(8)]
        if ch and cell == g and any(any(row) for row in g):
            chars.append((r * 8, c * 8, ch, 8, 'rom', r * 8))
            for y in range(8):
                for x in range(8):
                    ink[r * 8 + y][c * 8 + x] = False
    H = len(ink)
    rows_with_ink = [y for y in range(H) if any(ink[y])]
    tried = sorted({y - k for y in rows_with_ink for k in range(BAND)} & set(range(-BAND + 1, H)))
    results = []
    for name in FONTS:
        table = glyph_table(name)
        if not table:
            continue
        for y0 in tried:
            score, unread, got = parse_band(ink, y0, name)
            real = []
            for x, ch in got:
                if ch == UNREAD:
                    continue
                cols = next(k for k, v in table[width(name, ch)].items() if v == ch)
                pix = {(y0 + k, x + i) for i, bits in enumerate(cols) for k in range(BAND) if bits >> k & 1}
                real.append((x, ch, pix))
            if real:
                results.append((score - UNREAD_COST * unread, y0, name, real))
    results.sort(key=lambda v: (-v[0], v[1], FONTS.index(v[2])))
    claimed = set()
    for _, y0, name, real in results:
        pix = set().union(*(p for _, _, p in real))
        if pix & claimed:
            continue
        for x, ch, _ in real:
            chars.append((y0 + 2, x, ch, width(name, ch), name, y0))
        claimed |= pix
    # 어느 글자로도 읽지 못한 잉크: 이어진 열 묶음마다 못 읽음 하나(그 묶음 잉크의 윗줄 자리)
    left = [(y, x) for y in range(H) for x in range(len(ink[0])) if ink[y][x] and (y, x) not in claimed]
    by_col = {}
    for y, x in left:
        by_col.setdefault(x, []).append(y)
    run = None
    for x in sorted(by_col) + [None]:
        if run and (x is None or x != run[1] + 1):
            chars.append((run[2] - 1, run[0], UNREAD, run[1] - run[0] + 1, None, run[2]))
            run = None
        if x is None:
            break
        top = min(by_col[x])
        run = (x, x, top) if run is None else (run[0], x, min(run[2], top))
    return lines_of(chars)


class Line:
    """창 안 한 줄. y·x 는 창 사각형(테두리 포함) 안 점 자리, items 는 [(x, 글자, 폭, 글꼴 또는 'rom'·None, 띠 윗줄)]."""

    def __init__(self, y, items):
        self.y, self.items = y, sorted(items)
        self.x = self.items[0][0]
        text, end = '', None
        for x, ch, wdt, _, _ in self.items:
            if end is not None and x - end >= SPACE_GAP:
                text += ' '
            text += ch
            end = x + wdt
        self.text = text

    @property
    def right(self):
        return max(x + w for x, _, w, _, _ in self.items)

    def __iter__(self):
        return iter((self.y, self.x, self.text))


def lines_of(chars):
    """글자 [(y, x, 글자, 폭, 글꼴, 띠 윗줄)] → [Line] (y 가 LINE_GAP 안인 글자를 한 줄로)."""
    groups = []
    for y, x, ch, wdt, kind, top in sorted(chars):
        for g in groups:
            if abs(g[0] - y) <= LINE_GAP:
                g[1].append((x, ch, wdt, kind, top))
                break
        else:
            groups.append([y, [(x, ch, wdt, kind, top)]])
    return sorted((Line(y, items) for y, items in groups), key=lambda ln: (ln.y, ln.x))


def read_screen(screen, rom_table):
    """{창 사각형: [Line]}."""
    return {w: read_window(screen, w, rom_table) for w in screen.rects}


def lines(screen):
    """규칙 파일이 나눠 쓰는 읽기: {창 사각형: [Line]}. 모습마다 한 번만 읽는다. 글꼴(DQ4_GALMURI)이 없으면 None."""
    got = getattr(screen, '_wintext', False)
    if got is False:
        try:
            rom = screen.ref.rom
            if ROM_FOR_MESSAGES != rom:
                use_rom(rom)
            got = read_screen(screen, rom_table_for(rom))
        except SystemExit:
            got = None
        screen._wintext = got
    return got


_ROM_TABLES = {}


def rom_table_for(rom):
    key = id(rom)
    if key not in _ROM_TABLES:
        _ROM_TABLES.clear()
        _ROM_TABLES[key] = rom_glyphs(rom)
    return _ROM_TABLES[key]


ADOPT = HERE.parents[2] / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'


@functools.lru_cache(maxsize=None)
def vocabulary():
    """창에 찍히는 이름의 낱말 모음: adopt.tsv 의 채택 이름(물건·몬스터·주문·인물 등)과 일행·동료 이름(dq4people.PARTIES,
    dq4groupbuild 의 PERSON_NAMES·COMPANION_NAMES)을 띄어쓰기로 나눈 것."""
    words = set()
    if ADOPT.is_file():
        rows = ADOPT.read_text(encoding='utf-8').splitlines()
        head = rows[0].split('\t')
        k = head.index('채택') if '채택' in head else 3
        for row in rows[1:]:
            cells = row.split('\t')
            if len(cells) > k:
                words.update(cells[k].split())
    for name in party_names():
        words.add(name)
    words |= ui_words()
    return frozenset(w for w in words if w)


def _strings(v, depth=0):
    if isinstance(v, str):
        yield v
    elif depth < 4 and isinstance(v, dict):
        for k, x in v.items():
            yield from _strings(k, depth + 1)
            yield from _strings(x, depth + 1)
    elif depth < 4 and isinstance(v, (list, tuple, set, frozenset)):
        for x in v:
            yield from _strings(x, depth + 1)


@functools.lru_cache(maxsize=None)
def ui_words():
    """창 고정 문구·제목·작전 등 빌드가 창에 쓰는 한글 낱말(dq4windowtext·dq4menupatch 의 모듈 표에 든 한글 글자열).
    잘림 규칙이 「조사」(→ 조사하다)·「불가」 처럼 온전한 낱말을 앞부분으로 보지 않게 한다."""
    import dq4menupatch
    import dq4windowtext
    out = set()
    for mod in (dq4windowtext, dq4menupatch):
        for name, v in vars(mod).items():
            if name.isupper():
                for text in _strings(v):
                    out.update(t for t in text.split() if any('가' <= ch <= '힣' for ch in t))
    return frozenset(out)


def word_chars(line):
    """줄에서 한글·영숫자 글자(기호·못 읽음 빼고)의 [(x, 글자, 폭, 글꼴, 띠 윗줄)]."""
    return [it for it in line.items if len(it[1]) == 1 and (it[1].isascii() and it[1].isalnum() or '가' <= it[1] <= '힣')]


@functools.lru_cache(maxsize=None)
def party_names():
    """{이름} 일행·동료로 창에 찍히는 사람 이름."""
    import dq4groupbuild as GB
    import dq4people
    names = {n for party in dq4people.PARTIES.values() for n in party}
    return frozenset(names | set(GB.PERSON_NAMES.values()) | set(GB.COMPANION_NAMES.values()))


def cell_of(w, x, y):
    """창 w 안 점 자리 → 화면 (줄, 열)."""
    return w[0] + y // 8, w[1] + x // 8


def near_cover(screen, w, line, margin=8):
    """줄 둘레(앞뒤 margin 점, 줄의 칸 두 줄)에 위 창에 가려진 칸이나 창 밖 칸이 있나: 가려진 줄은 앞만 보인다."""
    r1, c1, r2, c2 = w
    rows = {line.y // 8, (line.y + 10) // 8}
    for x in range(line.x - margin, line.right + margin, 8):
        for ry in rows:
            r, c = w[0] + ry, w[1] + x // 8
            if not (r1 <= r <= r2 and c1 <= c <= c2) or screen.hidden(w, r, c):
                return True
    return False


def has_final(ch):
    """한글 글자의 받침이 있나(가~힣 밖이면 None)."""
    if not '가' <= ch <= '힣':
        return None
    return (ord(ch) - 0xAC00) % 28 != 0
