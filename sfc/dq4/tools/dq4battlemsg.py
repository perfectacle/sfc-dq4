"""DQ5 전투 메시지(dq5battletext)를 한글로. dq4windowname.apply 가 창 이름 asm 과 함께 넣는다.
형식은 sfc/dq4/docs/dq4-battle-text-format.md.

전투 글은 바이트가 곧 BG3 타일 번호다. 한글은 메시지 안의 한글 구간(E3 n 바이트…)으로 두고, dq4battlemsg.asm 이 그 구간을
Galmuri9 띠로 그려 전투 글 칸 풀에 올린 뒤 그 칸의 코드를 글 큐(0ECB)에 넣는다. 이름(F7 등)도 같은 풀로 그린다.

문장 안의 표시: {F7} 같은 두 자리 16진은 원문 제어 코드, {은}·{이}·{을}·{로}·{과}·{아}·{여} 는 바로 앞에 그린 글자의
받침으로 고르는 조사, '/' 는 줄 바꿈(FF), '|' 는 쪽 넘김(FD). 끝 부호는 원문을 따른다. 문장 부호(PUNCT)는 Galmuri9
글리프를 가나 글리프 뒤에 더해 한글과 같은 띠에 그린다.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1] / 'dq5' / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import dq4nameentry as ne  # noqa: E402

STREAM_AT = '4C:8000'
TABLE_AT = 0x4D8000
CODE_AT = 0x60EB00               # 창 이름 코드(60:C000~)·가나 표(60:E800~) 뒤. WnFetch 를 JSR 로 부르려고 같은 뱅크
RUN = 0xE3                       # 24:86F2 표에서 빈 처리기(24:86D3)로 가던 코드
RUN_TABLE = 0x2486F4             # 24:86F2 + (E3 - E2) × 2
RUN_STUB = 0x249C2E              # 디코더를 옮기면 쓰이지 않는 원래 전투 허프만 트리 자리
# 구간 안 토큰: 10 = 띄움(점, 부호 있음), 11 = 조사, 12~1F x = 글자 표 쪽(토큰 - 12) + 1 의 x 칸, 20~FF = 글자 표 쪽 0.
# 표는 바이트 값으로 바로 찾는 256칸 쪽들이고, 끝 부호(E7·EF·FE) 칸은 비운다. 24:8C39 가 끝 부호를 세어 앞 메시지를
# 건너뛰므로 구간 안에 끝 부호 바이트가 있으면 안 된다
ADVANCE, JOSA_TOKEN, PAGE0, CHAR0 = 0x10, 0x11, 0x12, 0x20
ENDS = (0xE7, 0xEF, 0xFE)
SPACE_PX = 5
GLYPH_PX = 10                    # 이름과 같은 한글 간격
LINE_CELLS = 26
# 줄 칸 검사에 쓰는 이름·숫자 칸 수. 한글 이름은 대부분 일곱 칸 안이고(물건·주문 몇은 아홉~열 칸), 숫자는 데미지 세 자리.
# 이보다 긴 이름으로 줄이 26칸을 넘으면 WnBattleChar 가 넘는 글자를 버린다
NAME_CELLS = 7
NUMBER_CELLS = 3
BUFFER = 128
PUNCT = '!?.,…「」~0123456789'     # 숫자는 이름 안 숫자(가나 이름의 02~0B)를 그릴 때
# 전투 메시지가 이름을 찍는 표: 주문·특기 3, 몬스터 4, 물건 5(dq5battletext.CONTROLS 의 F4·F6·F5, F7 의 몬스터 무리)
NAME_TABLES = (3, 4, 5)
NAMES_AT = 0x4DA000
# 전투 첫머리 창 25 의 「(이름)が　あらわれた！」(04:BFF5 가 이름 뒤에 04:C05B 의 9바이트를 찍음)를 바꾼 이름 뒤 말
APPEAR = '{이} 나타났다!'
GROUP_NAME, GROUP_NAME_LEN = 0x248950, 6

# 칸 풀. A 는 전투 연출이 덮지 않는 칸(원래 BG3 타일맵 자리였던 1D0~1FF 와, 연출이 덮지 않은 163~165·17D~17F),
# B 는 큰 주문(ベギラゴン·バギクロス·メガンテ·メガザル 등) 연출만 덮는 칸이라 연출이 끝나면 사본에서 다시 올린다.
POOL_A = list(range(0x1D0, 0x200)) + [0x163, 0x164, 0x165, 0x17D, 0x17E, 0x17F]
POOL_B = list(range(0x144, 0x163))
# C 는 전투 중 BG3 타일맵이 가리키지 않고 큰 주문 연출만 덮는 칸. 사본을 둘 WRAM 이 없어 복원하지 않으므로 맨 나중에 쓴다
# (한 화면에 85칸 넘게 쓸 때만). 096~098 은 전투 화면이 쓰는 칸이라 뺐다.
POOL_C = list(range(0x099, 0x0B0)) + list(range(0x123, 0x144)) + list(range(0x166, 0x17D))
POOL = POOL_A + POOL_B + POOL_C
# 원래 전투 글(메시지 432개·이름 표·탁점 92/93·숫자·채움 8D)이 격자에 쓰지 않는 바이트. 글자 H M P G(0C~0F)·6E·
# ▼ 둘레(7B~7F)는 코드가 따로 쓸 수 있어 뺐다.
# 가나 바이트 10~7A 는 이름을 모두 Galmuri 로 그리므로(BmKana) 격자에 오지 않아 함께 쓴다.
CODES = ([0x80, 0x81, 0x82, 0x85, 0x86, 0x88, 0x8A, 0x8B, 0x8C, 0x8E, 0x8F, 0x90, 0x91, 0x94, 0x95, 0x96, 0x97, 0x98,
          0x99, 0x9B, 0x9E, 0x9F, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA8, 0xA9, 0xAA, 0xAB, 0xAD, 0xAE]
         + list(range(0xB0, 0xE2)) + [b for b in range(0x10, 0x7B) if b != 0x6E])[:len(POOL)]
# 번역하지 않는 번호 가운데 끝 부호 앞까지 쓰레기 바이트인 것(가나 바이트가 들어 있어 코드와 겹치지만 띄우지 않음)
UNUSED = range(0x1A3, 0x1B0)
TILES = {'＊': 0x89, **{str(d): 0x02 + d for d in range(10)}}
PAIRS = {'MP': (0xAC, 0xAF), 'HP': (0xA7, 0xAF)}      # 원래 글자 두 칸으로 된 표시
JOSA = (('은', '는'), ('이', '가'), ('을', '를'), ('으로', '로'), ('과', '와'), ('아', '야'), ('이여', '여'))
JOSA_KEYS = {'은': 0, '이': 1, '을': 2, '로': 3, '과': 4, '아': 5, '여': 6}

from dq4battletexts import SOURCE  # noqa: E402


# 전투 글 엔진의 WRAM(7E:A5F1~A91F 는 DQ5 장면 770개에서 원래 코드의 접근이 없던 자리). dq4windowname.asm 도 쓰므로
# 두 asm 보다 먼저 정의한다
WRAM = '''!bm_last   = $A5F2          ; 마지막에 그린 글리프(조사용), FFFF = 받침 없음으로 봄
!bm_x      = $A5F4          ; 띠 안 점 자리
!bm_p      = $A5F6          ; 구간 안 읽을 자리
!bm_n      = $A5F8          ; 구간 바이트 수
!bm_q      = $A5FA          ; 글 큐 쓸 자리
!bm_c      = $A5FC          ; 열
!bm_k      = $A5FE          ; 풀 번호
!bm_shadow = $A600          ; 풀 B 칸마다 평면 0 8바이트
!bm_pat    = $A6F8          ; 풀 번호마다 위 칸 무늬(0 = 아래 칸), 164바이트
!bm_used   = $A79C          ; 풀 번호마다 1비트: 화면 격자나 큐에 있음(끝에 1바이트 여유)
!bm_base   = $A7B2          ; 풀 번호마다 1비트: 위 칸 바탕이 창 위 테두리(끝에 1바이트 여유)
!bm_bits   = 22             ; 비트 표 바이트 수
!bm_band   = $A800          ; 띠 9줄 × !bm_w 바이트(줄 0 = 글자 맨 윗줄)
!bm_carry  = $A905          ; 1바이트: 1 = 앞 이름의 덜 찬 마지막 열을 띠 첫 열에 남김
!bm_bs     = $A906          ; 1바이트: 찾는 위 칸 바탕(0 빈칸, 1 창 위 테두리)
!bm_tail   = $A907          ; 1바이트: 구간 끝 띄움 점 수(마지막 토큰이 띄움이 아니면 0)
!bm_t8     = $A908          ; 올릴 칸 평면 0 8바이트
!bm_v      = $A910
!bm_r      = $A912
!bm_s      = $A914
!bm_o      = $A916
!bm_sh     = $A918          ; 3바이트: 민 글자 줄
!bm_upc    = $A91B          ; 1바이트: BmColumn 이 고른 짝 위 칸 코드
!bm_g      = $A91C          ; 글리프 높은 바이트, BmEmit 에서는 올릴 열 수
!bm_pt     = $A91E          ; 1바이트: 찾는 위 줄 무늬
!bm_w      = 29             ; 26칸 + 밀린 글리프 몫
!bm_buf    = $0E4B          ; 전투 메시지 푼 버퍼(128바이트)
!bm_queue  = $0ECB          ; 글 큐(64바이트)
!bm_grid   = $1DD5          ; 글자 격자 26칸 × 6줄

'''


def glyph(ch):
    return ne.GLYPHS.index(ch)


def jong(ch):
    """0 받침 없음, 1 있음, 2 ㄹ. 자음 자모는 이름(기역…)처럼 있음."""
    if 'ㄱ' <= ch <= 'ㅣ':
        return 0 if ch >= 'ㅏ' else 2 if ch == 'ㄹ' else 1
    if '가' <= ch <= '힣':
        j = (ord(ch) - 0xAC00) % 28
        return 0 if j == 0 else 2 if j == 8 else 1
    return 0


def items(text, punct):
    """문장 → [('ctl', b) | ('tile', b) | ('g', 글리프, 폭) | ('adv', 점) | ('josa', k)]."""
    out, i = [], 0
    while i < len(text):
        c = text[i]
        m = re.match(r'\{([0-9A-F]{2})\}', text[i:])
        if m:
            out.append(('ctl', int(m[1], 16)))
            i += 4
            continue
        m = re.match(r'\{(.)\}', text[i:])
        if m:
            out.append(('josa', JOSA_KEYS[m[1]]))
            i += 3
            continue
        if c == '/':
            out.append(('ctl', 0xFF))
        elif c == '|':
            out.append(('ctl', 0xFD))
        elif c == ' ':
            out.append(('adv', SPACE_PX))
        elif text[i:i + 2] in PAIRS:
            out += [('tile', b) for b in PAIRS[text[i:i + 2]]]
            i += 2
            continue
        elif c in TILES:
            out.append(('tile', TILES[c]))
        elif c in punct:
            out.append(('g', *punct[c]))
        else:
            out.append(('g', glyph(c), GLYPH_PX))
        i += 1
    return out


def charset(punct):
    """{글리프: 토큰 바이트}. 자주 나오는 글리프부터 쪽 0(1바이트), 나머지는 쪽 1~(2바이트)."""
    from collections import Counter
    freq = Counter(t[1] for text in SOURCE.values() for t in items(text, punct) if t[0] == 'g')
    order = [g for g, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    slots = [(b,) for b in range(CHAR0, 0x100) if b not in ENDS]
    slots += [(PAGE0 + p, x) for p in range(CHAR0 - PAGE0) for x in range(0x100) if x not in ENDS]
    if len(order) > len(slots):
        raise ValueError('글자 표가 모자람')
    return dict(zip(order, slots))


def char_pages(chars):
    """글자 표 쪽마다 256칸 × 16비트(빈 칸 0)."""
    pages = 1 + max((t[0] - PAGE0 + 1 for t in chars.values() if len(t) == 2), default=0)
    out = bytearray(pages * 0x200)
    for g, t in chars.items():
        k = (t[0] if len(t) == 1 else (t[0] - PAGE0 + 1) * 0x100 + t[1])
        out[k * 2:k * 2 + 2] = g.to_bytes(2, 'little')
    return bytes(out)


def encode(text, end, punct, chars):
    """메시지 바이트(끝 부호 포함)와 줄마다 칸 수. chars 는 charset() 의 글자 표."""
    codes, run, lines, cells, px = [], [], [], 0, 0

    def flush():
        nonlocal run, cells, px
        if run:
            if px and all(t[0] == 'adv' for t in run):
                codes.extend([0x01] * -(-px // 8))
            else:
                body = bytearray()
                for t in run:
                    if t[0] == 'g':
                        body += bytes(chars[t[1]])
                        if t[2] != GLYPH_PX:
                            body += bytes((ADVANCE, (t[2] - GLYPH_PX) & 0xFF))
                    elif t[0] == 'adv':
                        body += bytes((ADVANCE, t[1]))
                    else:
                        body += bytes((JOSA_TOKEN, t[1]))
                codes.extend([RUN, len(body), *body])
            cells += -(-px // 8)
        run, px = [], 0

    for t in items(text, punct):
        kind = t[0]
        if kind in ('g', 'adv', 'josa'):
            run.append(t)
            px += t[1] if kind == 'adv' else t[2] if kind == 'g' else GLYPH_PX * len(JOSA[t[1]][0])
            continue
        flush()
        v = t[1]
        if kind == 'tile':
            codes.append(v)
            cells += 1
        elif v in (0xFF, 0xFD):
            codes.append(v)
            lines.append(cells)
            cells = 0
        else:
            codes.append(v)
            cells += NUMBER_CELLS if v == 0xFB else NAME_CELLS
    flush()
    codes.append(end)
    lines.append(cells)
    return codes, lines


def messages(rom, punct, chars):
    """{번호: 바이트}. 줄이 넘치거나 128바이트를 넘으면 거부한다."""
    import dq5battletext as bt
    from dq5map import Rom
    r = Rom(bytes(rom))
    out = {}
    for n, text in SOURCE.items():
        original = bt.message(r, n)
        end = original[-1]
        codes, lines = encode(text, end, punct, chars)
        if original[-2:-1] == [0xF2]:
            codes.insert(-1, 0xF2)          # 끝의 효과음·흔들림은 원문대로
        if max(lines) > LINE_CELLS:
            raise ValueError(f'전투 메시지 {n:03X}: 줄이 {LINE_CELLS}칸을 넘음 {lines}')
        if len(codes) > BUFFER:
            raise ValueError(f'전투 메시지 {n:03X}: {len(codes)}바이트, {BUFFER} 를 넘음')
        out[n] = codes
    return out


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def original_bytes(rom):
    """번역한 뒤에도 원래 전투 글이 격자에 쓸 수 있는 바이트: 원문으로 둔 메시지(UNUSED 빼고)·숫자·채움 8D·빈칸.
    이름은 모두 BmKana·이름 표로 그리므로 이름 바이트는 격자에 오지 않는다."""
    import dq5battletext as bt
    from dq5map import Rom
    r = Rom(bytes(rom))
    used = {0x01, 0x8D, *range(0x02, 0x0C)}
    for n in range(bt.COUNT):
        if n not in SOURCE and n not in UNUSED:
            used |= {b for b in bt.message(r, n) if b < 0xE2}
    return used


def tables(chars):
    """TABLE_AT 에 둘 표와 그 안 자리. 코드 → 풀 번호(FF 없음) 256, 풀 번호 → 타일 낱말, 받침(글리프마다), 조사(종류마다
    있음 둘 · 없음 둘 글리프, FFFF 없음)."""
    if len(CODES) != len(POOL) or len(set(CODES)) != len(CODES) or len(set(POOL)) != len(POOL):
        raise ValueError('풀 코드와 칸 수가 맞지 않음')
    index = bytearray(b'\xff' * 256)
    for k, c in enumerate(CODES):
        index[c] = k
    tile = b''.join(t.to_bytes(2, 'little') for t in POOL)
    jongs = bytes(jong(ch) for ch in ne.GLYPHS)
    josa = bytearray()
    for has, none in JOSA:
        for word in (has, none):
            gs = [glyph(ch) for ch in word] + [0xFFFF] * (2 - len(word))
            josa += b''.join(g.to_bytes(2, 'little') for g in gs)
    charmap = char_pages(chars)
    parts = {'index': bytes(index), 'codes': bytes(CODES), 'tile': tile, 'josa': bytes(josa), 'charset': charmap,
             'jong': jongs}
    blob, at = bytearray(), {}
    for name, raw in parts.items():
        at[name] = TABLE_AT + len(blob)
        blob += raw
    return bytes(blob), at


def punct_glyphs(d, font, render, first):
    """PUNCT 를 글리프 first 번부터 이름 입력 글리프 뱅크에 쓰고 {글자: (글리프, 나아갈 점)}."""
    out = {}
    for k, ch in enumerate(PUNCT):
        n = first + k
        cols = render(font, ch, True)
        if len(cols) > 2:
            raise ValueError(f'{ch}: 문장 부호가 두 열을 넘음')
        width = max((c * 8 + x + 1 for c, col in enumerate(cols) for row in col for x, v in enumerate(row) if v),
                    default=0)
        cols += [[[0] * 8 for _ in range(16)]] * (2 - len(cols))
        cell = b''.join(bytes(int(''.join(map(str, r)), 2) for r in col) for col in cols)
        o = lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32)
        if any(d[o:o + 32]):
            raise ValueError(f'글리프 {n} 자리가 비어 있지 않음')
        d[o:o + 32] = cell
        out[ch] = (n, width + 1)
    return out


def name_entries(d):
    """[(이름 바이트, [글리프 | 8000 + 띄울 점])]."""
    import dq4windowtext as wt
    import dq5namewrite as nw
    raw = nw.read_tables(bytes(d))
    numbered = wt.numbered_names()
    known = set(ne.GLYPHS)
    entries, seen = [], set()
    for t in NAME_TABLES:
        adopted = {**wt.adopted(wt.KINDS[t][0]), **{wt.kana_key(k): v for k, v in wt.EXTRA_NAMES.get(t, {}).items()}}
        texts = wt.rom_names(d, t, len(raw[t]))
        for n, (name, text) in enumerate(zip(raw[t], texts)):
            ko = numbered.get(t, {}).get(n) or adopted.get(wt.kana_key(text))
            if ko and name and bytes(name) not in seen and all(c in known or c == ' ' for c in ko):
                seen.add(bytes(name))
                entries.append((bytes(name), [0x8000 | SPACE_PX if c == ' ' else glyph(c) for c in ko]))
    # 24:893C 가 몬스터 무리를 묶어 부를 때 쓰는 고정 문자열(「まもののむれ」)
    group = bytes(d[lorom(GROUP_NAME):lorom(GROUP_NAME) + GROUP_NAME_LEN])
    if group not in seen:
        entries.append((group, [0x8000 | SPACE_PX if c == ' ' else glyph(c) for c in '마물 무리']))
    return entries


def tokens(text, punct):
    """이름 표 꼴 토큰: 글리프, 8000 + 띄울 점(낮은 바이트, 부호 있음), C000 + 조사 종류."""
    out = []
    for t in items(text, punct):
        if t[0] == 'g':
            out.append(t[1])
            if t[2] != GLYPH_PX:
                out.append(0x8000 | (t[2] - GLYPH_PX) & 0xFF)
        elif t[0] == 'adv':
            out.append(0x8000 | t[1])
        elif t[0] == 'josa':
            out.append(0xC000 | t[1])
        else:
            raise ValueError(f'{text!r}: 이름 표 토큰에는 글자 타일을 쓸 수 없음')
    return out


def name_blob(entries, appear):
    """[길이][이름 바이트…][토큰 수][16비트…] 를 잇고 길이 0 으로 끝낸 뒤, 첫머리 말 토큰을 붙인다.
    돌려주는 것: 바이트, 첫머리 말의 자리(블롭 안)."""
    out = bytearray()
    for name, toks in entries:
        out += bytes((len(name),)) + name + bytes((len(toks),))
        out += b''.join(t.to_bytes(2, 'little') for t in toks)
    out += b'\0'
    at = len(out)
    out += b''.join(t.to_bytes(2, 'little') for t in appear)
    return bytes(out), at


def apply(d, font, render, first_glyph):
    """d(bytearray)에 메시지 흐름·표를 쓰고 asm 정의를 돌려준다. 원래 전투 글이 풀 코드를 쓰면 거부한다."""
    import dq5battletextwrite as bw
    clash = original_bytes(d) & set(CODES)
    if clash:
        raise ValueError(f'원래 전투 글이 풀 코드를 씀: {sorted(clash)}')
    original = bw.read_messages(bytes(d))
    msgs = list(original)
    punct = punct_glyphs(d, font, render, first_glyph)
    entries = name_entries(d)
    chars = charset(punct)
    for n, codes in messages(d, punct, chars).items():
        msgs[n] = codes
    head = bytes(d[:0x200000])
    doc = bw.compile_messages(head, msgs, STREAM_AT)
    for w in doc['writes']:
        bank, addr = (int(x, 16) for x in w['at'].split(':'))
        o = lorom(bank << 16 | addr)
        raw = bytes.fromhex(w['hex'])
        want = bytes.fromhex(w['orig']) if 'orig' in w else bytes(len(raw))
        if bytes(d[o:o + len(raw)]) != want:
            raise ValueError(f'{w["at"]}: 전투 메시지 쓰기 자리가 예상과 다름')
        d[o:o + len(raw)] = raw
    blob, at = tables(chars)
    if TABLE_AT + len(blob) > NAMES_AT:
        raise ValueError('표가 이름 표 자리를 넘음')
    o = lorom(TABLE_AT)
    if any(d[o:o + len(blob)]):
        raise ValueError(f'{TABLE_AT:06X} 가 비어 있지 않음')
    d[o:o + len(blob)] = blob
    appear = tokens(APPEAR, punct)
    names, appear_at = name_blob(entries, appear)
    o = lorom(NAMES_AT)
    if any(d[o:o + len(names)]) or (NAMES_AT & 0xFFFF) + len(names) > 0x10000:
        raise ValueError(f'{NAMES_AT:06X}: 이름 표 자리가 비어 있지 않거나 뱅크를 넘음')
    d[o:o + len(names)] = names
    o = lorom(RUN_TABLE)
    if d[o:o + 2] != bytes.fromhex('d386'):
        raise ValueError(f'{RUN_TABLE:06X}: 코드 E3 처리기가 빈 처리기가 아님')
    return (WRAM + f'!bm_index = ${at["index"]:06X}\n!bm_tile = ${at["tile"]:06X}\n!bm_josa = ${at["josa"]:06X}\n'
            f'!bm_jong = ${at["jong"]:06X}\n!bm_charset = ${at["charset"]:06X}\n!bm_codes = ${at["codes"]:06X}\n!bm_code = ${CODE_AT:06X}\n!bm_count = {len(POOL)}\n'
            f'!bm_b0 = {POOL.index(POOL_B[0])}\n!bm_b1 = {POOL.index(POOL_B[0]) + len(POOL_B)}\n'
            f'!bm_run_stub = ${RUN_STUB:06X}\n!bm_run_table = ${RUN_TABLE:06X}\n!bm_space = {SPACE_PX}\n'
            f'!bm_digit0 = {punct["0"][0]}\n!bm_glyph_px = {GLYPH_PX}\n!bm_glyphs = {len(ne.GLYPHS)}\n!bm_names = ${NAMES_AT:06X}\n'
            f'!bm_appear = ${NAMES_AT + appear_at:06X}\n!bm_appear_count = {len(appear)}\n')


if __name__ == '__main__':
    rom = bytearray(open(sys.argv[1], 'rb').read())
    print(len(name_entries(rom)), 'names')
    punct = {ch: (0x900 + k, 4) for k, ch in enumerate(PUNCT)}
    for n, codes in messages(rom, punct, charset(punct)).items():
        print(f'{n:03X} {len(codes):3d} {bytes(codes).hex(" ")}')
