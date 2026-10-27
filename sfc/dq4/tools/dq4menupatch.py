"""타이틀 뒤 모험의 서 메뉴(DQ5 창 레코드)를 한글로 바꾼다.

창 글자는 바이트가 곧 BG3 타일 번호라(04:B0F0) 한글을 넣을 칸이 없다. 그래서 메뉴 문구를 빌드할 때 통째로 그려
8점 폭의 「열」로 자르고, 열 k 를 BG3 타일 200+k(글자 줄)·300+k(아래 줄)에 둔다. 메뉴 화면에서는 VRAM 워드
2000~7FFF 가 비어 있으므로(타이틀 FadeOut 이 VRAM 을 모두 지움) 타이틀이 끝날 때 한 번 올린다.
창 레코드에는 접두 9F n k(열 k 부터 n 개)를 쓰고, 04:B11E 훅이 타일맵에 10비트 타일 번호로 쓴다.
형식은 sfc/dq4/docs/dq4-menu-format.md.

  python sfc/dq4/tools/dq4menupatch.py build --rom work/overture/dq4-title-overture.sfc \\
      --out work/menu/dq4-menu.sfc
  python sfc/dq4/tools/dq4menupatch.py sheet --out work/menu/sheet.png   # 문구 열 그림

글꼴은 Galmuri v2.40.4(SIL OFL 1.1)의 BDF 를 DQ4_GALMURI 폴더에서 읽는다(저장소에 넣지 않음, 받는 법은 형식 문서).
창 글자는 galmuri9, 자모판은 galmuri7, 메시지는 galmuri11 이 채택이다(원작 창 가나 8×8 과 메시지 가나 11~13 점에 맞춤).
나머지는 비교 시안이다.
"""
import argparse
import hashlib
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools')]

from dq4romassets import differences, ips_patch, set_checksum  # noqa: E402
from dq5map import lorom  # noqa: E402

BASE_SHA1 = 'ed46db6d9e8113191de124949f7d50a375adc410'   # 서곡 채택본(dq4-overture-format.md)
PREFIX = 0x9F               # 창 레코드에 쓰이지 않는 캔버스 타일 번호. 바로 뒤 [열 수][첫 열]
COLUMNS = 0x100             # 열 k 는 타일 200+k(글자 줄)·300+k(아래 줄)
LAST_COLUMN = 0xD0          # D0~E7 은 목록 세 이름, F8~FF 는 이름 입력 칸
HOOK = 0x608000             # 창 접두 처리
UPLOAD = 0x608100           # 타이틀 FadeOut 끝에서 열 그림을 VRAM 2000 에 올림
TILES = 0x609000            # 열 그림 8KB: 글자 줄 256 타일, 이어서 아래 줄 256 타일
WIN_DISPATCH = 0x04B11E     # CMP #$01 갈래(wintest 와 같은 자리)
FADEOUT_EXIT = 0x30829A     # dq4titlelayers.asm FadeOut 의 JML $03FE5C
MENU_ENTRY = 0x03FE5C
BAND = 16                   # 글자 줄 8점 + 아래 줄 8점

GALMURI = {
    'galmuri11': ('Galmuri11.bdf', '98716d08aa5762e6ce440d5a757d107cb5d3f32a53861878be06c00aacc23304'),
    'galmuri9': ('Galmuri9.bdf', 'cc9b6d6f660d8391016be7691b3fc3f864bfa3b095f67bc5e830e9b03ce42162'),
    'galmuri11c': ('Galmuri11-Condensed.bdf', '5adbdedb3d118e99cc7e114b746b3cf6f6a46a4642e0ff215d6a431e55901995'),
    'galmuri7': ('Galmuri7.bdf', '0ec6b8707e8c47d85995b5b2b507180aed7bcc724792fe5477e998d41f8b075f'),
}

# 메뉴에서만 여는 창 → 줄 목록. 줄은 조각의 목록이고, 문자열은 한글로 그린 열, bytes 는 원래 창 바이트(공백 01·숫자 03~0A·
# 항목 시작 FE)를 그대로 쓴다. 문구는 FC DQ4 그룹 1(16:$B3AC~)을 옮겼고, 설정 항목만 스테레오까지 묻는 DQ5 동작에 맞췄다.
WINDOWS = {
    0x5E: [['모험의 서를 만든다']],
    0x5F: [['모험을 한다'], ['설정을 바꾼다'], ['모험의 서를 지운다']],
    0x60: [['모험을 한다'], ['설정을 바꾼다'], ['모험의 서를 만든다'], ['모험의 서를 복사한다'], ['모험의 서를 지운다']],
    0x64: [['모험의 서', b'\x01\x03']],
    0x65: [['모험의 서', b'\x01\x04']],
    0x66: [['모험의 서', b'\x01\x05']],
    0x67: [['모험의 서', b'\x01\x03'], ['모험의 서', b'\x01\x04']],
    0x68: [['모험의 서', b'\x01\x04'], ['모험의 서', b'\x01\x05']],
    0x69: [['모험의 서', b'\x01\x03'], ['모험의 서', b'\x01\x05']],
    0x6A: [['모험의 서', b'\x01\x03'], ['모험의 서', b'\x01\x04'], ['모험의 서', b'\x01\x05']],
    0x86: [['스테레오', b'\x01', b'\xfe', '모노']],
}
# 게임 안에서도 여는 창(32 는 교회 등의 はい/いいえ). 롬 레코드는 그대로 두고 창 표 칸을 낮은 WRAM 자리로 돌린 뒤,
# 그 자리에 메뉴에서는 한글 레코드를, 맵을 불러올 때(2B:82BD)부터는 원래 레코드를 복사해 둔다.
# 6B·6C 는 이름 입력의 이름 칸과 판이다(게임 안의 이름 짓기도 씀, dq4nameentry.py).
SHARED = {
    0x32: [['예'], ['아니요']],
    0x62: [['아니요'], ['예']],
    0x6B: 'field',
    0x6C: 'board',
}
SHARED_WRAM = 0x1AC0        # 7E:1ABC~1BB1 은 DQ5 트랙이 실행한 장면 열일곱에서 접근이 없던 자리(dq5-hangul-format.md)
MENU_FLAG = 0x1BB0          # 메뉴에서 A5, 맵을 불러오면 00. 이름 입력 03:8B72 가 본다
SHARED_KR = 0x60B000        # 한글 레코드들과 표시 A5(창마다 원래와 한글 중 긴 쪽만큼 칸을 잡음)
SHARED_JP = 0x60B400        # 원래 레코드들과 표시 00
MAP_LOAD = 0x2B82BD         # LDA #$1C / STA $0725 (맵을 불러올 때마다)
# 창 63(표시 속도)은 FE 항목 창이 아니라 줄 글 + 숫자 항목이라 따로 엮는다(speed_record).
SPEED_WINDOW = 0x63
SPEED_TEXT = ('원하는 표시 속도는?', '빠름', '느림')


def load_bdf(path):
    """BDF 의 글자마다 (넓이 DWIDTH, BBX w h x y, 줄 비트 목록)."""
    glyphs, cur, bitmap = {}, None, None
    for line in Path(path).read_text(encoding='latin-1').splitlines():
        k = line.split()
        if not k:
            continue
        if k[0] == 'ENCODING':
            cur = {'code': int(k[1])}
        elif k[0] == 'DWIDTH' and cur is not None:
            cur['adv'] = int(k[1])
        elif k[0] == 'BBX' and cur is not None:
            cur['bbx'] = tuple(int(v) for v in k[1:5])
        elif k[0] == 'BITMAP' and cur is not None:
            bitmap = []
        elif k[0] == 'ENDCHAR' and cur is not None:
            w = cur['bbx'][0]
            nbits = (w + 7) // 8 * 8
            cur['rows'] = [[(int(r, 16) >> (nbits - 1 - x)) & 1 for x in range(w)] for r in bitmap]
            if cur['code'] >= 0:
                glyphs[chr(cur['code'])] = cur
            cur, bitmap = None, None
        elif bitmap is not None:
            bitmap.append(k[0])
    return glyphs


class Font:
    """글자 → (넓이, 16줄 띠 안의 점 목록). 한글 윗줄을 띠의 1줄에 맞춘다(가나 글자는 글자 줄 0~7 을 거의 다 씀)."""

    def __init__(self, name):
        self.name = name
        folder = os.environ.get('DQ4_GALMURI')
        if not folder:
            raise SystemExit('DQ4_GALMURI 에 Galmuri BDF 가 든 폴더를 주세요(sfc/dq4/docs/dq4-menu-format.md)')
        file, sha = GALMURI[name]
        path = Path(folder) / file
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise SystemExit(f'{path}: Galmuri v2.40.4 의 {file} 가 아님')
        self.glyphs = load_bdf(path)
        g = self.glyphs['한']
        self.top = g['bbx'][1] + g['bbx'][3]   # 한 의 윗줄이 띠의 1줄에 오는 기준선

    def char(self, ch):
        g = self.glyphs[ch]
        w, h, bx, by = g['bbx']
        pts = []
        for i, row in enumerate(g['rows']):
            y = self.top - (by + h - 1 - i)
            pts.extend((bx + x, y) for x, v in enumerate(row) if v)
        return g['adv'], pts


def render(font, text, tight=False):
    """문자열을 16줄 띠 하나로. 왼쪽 1점은 비운다(가나 글자도 왼쪽 열이 비어 있음). 돌려주는 것은 열 목록.
    tight 면 마지막 글자의 진행 폭 대신 점이 있는 데까지만 센다(이름 입력 판의 한 칸 자모)."""
    x, pts = 1, []
    for ch in text:
        adv, p = font.char(ch)
        pts.extend((x + px, py) for px, py in p)
        x += adv
    width = max(([] if tight else [x]) + [px + 1 for px, _ in pts], default=1)
    ncols = (width + 7) // 8
    band = [[0] * (ncols * 8) for _ in range(BAND)]
    for px, py in pts:
        if not 0 <= py < BAND:
            raise ValueError(f'{text!r}: 띠 밖의 점 y={py}')
        band[py][px] = 1
    return [[row[c * 8:c * 8 + 8] for row in band] for c in range(ncols)]


def tile_2bpp(rows):
    """1bpp 8줄 → BG3 2bpp. 04:E17D 의 가나 칸처럼 둘째 평면을 FF 로: 점은 색 3, 빈 곳은 색 2(창 바탕)."""
    out = bytearray()
    for r in rows:
        out += bytes((int(''.join(map(str, r)), 2), 0xFF))
    return bytes(out)


class Atlas:
    """문자열 → (열 수, 첫 열). 같은 문자열은 한 번만 그린다."""

    # BG1·BG2 글자 기준도 VRAM 워드 2000 이라 메뉴의 빈 타일맵(타일 0)이 열 0·1 자리를 4bpp 로 읽는다. 그래서 비워 둔다.
    FIRST = 2

    def __init__(self, font):
        self.font, self.runs, self.cols = font, {}, [None] * self.FIRST

    def run(self, text, font=None):
        tight = font is not None
        font = font or self.font
        key = (text, font.name)
        if key not in self.runs:
            cols = render(font, text, tight)
            self.runs[key] = (len(cols), len(self.cols))
            self.cols.extend(cols)
            if len(self.cols) > LAST_COLUMN:
                raise ValueError(f'열이 {LAST_COLUMN} 개를 넘음(그 뒤는 이름 칸)')
        return self.runs[key]

    def tiles(self):
        cols = self.cols + [None] * (COLUMNS - len(self.cols))
        empty = bytes(16)
        return (b''.join(tile_2bpp(c[:8]) if c else empty for c in cols)
                + b''.join(tile_2bpp(c[8:]) if c else empty for c in cols))


def window_record(data, addr):
    """창 레코드(뱅크 04)의 바이트를 끝 80 까지."""
    o = lorom(addr)
    end = data.index(0x80, o + 6)
    return bytes(data[o:end + 1])


def window_count(data):
    """창 표 칸 수. 표 바로 뒤에 첫 레코드가 오므로 가장 낮은 레코드 주소까지(dq5text.window 와 같은 셈)."""
    first = int.from_bytes(data[lorom(0x04EB48):lorom(0x04EB48) + 2], 'little')
    return (first - 0xEB48) // 2


def window_span(data, n):
    """창 n 레코드의 바이트를 다음 레코드 시작까지(6B 처럼 끝 80 이 없는 레코드도 있음)."""
    a = window_addr(data, n) & 0xFFFF
    starts = sorted({window_addr(data, m) & 0xFFFF for m in range(window_count(data))})
    end = next(s for s in starts if s > a)
    return bytes(data[lorom(0x040000 | a):lorom(0x040000 | end)])


def window_addr(data, n):
    return 0x040000 | int.from_bytes(data[lorom(0x04EB48 + n * 2):lorom(0x04EB48 + n * 2) + 2], 'little')


def piece_bytes(atlas, piece):
    if isinstance(piece, bytes):
        return piece, len(piece)
    n, k = atlas.run(piece)
    return bytes((PREFIX, n, k)), n


def item_record(atlas, head, rows):
    """FE 항목 창. 너비 = 가장 긴 줄(커서 칸 포함) + 테두리 2, 높이 +1(마지막 줄 아래에 한글 아랫부분이 옴)."""
    body, widest = bytearray(), 0
    for row in rows:
        width = 0
        body.append(0xFE)
        width += 1
        for piece in row:
            b, w = piece_bytes(atlas, piece)
            body += b
            width += w
        body.append(0xFF)
        widest = max(widest, width)
    h = bytearray(head)
    if widest + 2 > 0x3F or h[3] & 0x0F == 0x0F:
        raise ValueError(f'창 머리 {head.hex()}: 너비 {widest + 2} 또는 높이가 넘침')
    h[2] = (h[2] & 0xC0) | (widest + 2)
    h[3] = (h[3] & 0xF0) | ((h[3] & 0x0F) + 1)
    return bytes(h) + bytes(body) + b'\x80'


def speed_record(atlas, old):
    """창 63: [질문] FF FF FF [빠름 · 공백 · 느림] FF FF FE 1 … FE 8 FF. 빠름·느림은 원래처럼 숫자 1·8 위에 맞춘다."""
    q, fast, slow = SPEED_TEXT
    nq, kq = atlas.run(q)
    nf, kf = atlas.run(fast)
    ns, ks = atlas.run(slow)
    gap = 16 - nf - ns          # 원래 はやい(3)+공백 10+おそい(3) = 16칸
    if gap < 0 or nq > (old[2] & 0x3F) - 3:
        raise ValueError('표시 속도 창의 한글 줄이 창보다 김')
    digits = old[old.index(b'\xfe', 6):]
    return (old[:6] + bytes((PREFIX, nq, kq)) + b'\xff\xff\xff' + bytes((PREFIX, nf, kf)) + b'\x01' * gap
            + bytes((PREFIX, ns, ks)) + b'\xff\xff' + digits)


def hook_code():
    """04:B11E 에서 JSL. A = 창 바이트(8비트), X = 레코드 자리(DB 04), Y = $E0(7E 타일맵 버퍼) 기준 자리.
    01 이면 원래처럼 칸만 넘기고, 9F 면 열 n 개를 글자 줄(타일 200+k)과 아래 줄(300+k)에 쓴다. C = 처리 끝.
    n = 0 이면 칸도 그림도 없다. 이름 입력 판이 9F 00 FE 로 줄 칸 수(04:C6E7 이 첫 줄의 FE 바이트를 셈)를 맞출 때 쓴다."""
    loop = bytes((
        0x8A, 0x99, 0x00, 0x00,                  # TXA / STA $0000,Y         글자 줄 낮은 바이트 = k
        0xB9, 0x01, 0x00, 0x29, 0xFC, 0x48,      # LDA $0001,Y / AND #$FC / PHA   속성(팔레트·우선)은 그대로
        0x09, 0x02, 0x99, 0x01, 0x00,            # ORA #$02 / STA $0001,Y    타일 200+k
        0x8A, 0x99, 0x40, 0x00,                  # TXA / STA $0040,Y         아래 줄
        0x68, 0x09, 0x03, 0x99, 0x41, 0x00,      # PLA / ORA #$03 / STA $0041,Y   타일 300+k
        0xC8, 0xC8, 0xE8,                        # INY / INY / INX
        0xA3, 0x04, 0x3A, 0x83, 0x04))           # LDA $04,S / DEC A / STA $04,S  남은 열 수
    loop += bytes((0xD0, (-(len(loop) + 2)) & 0xFF))   # BNE loop
    return bytes((
        0xC9, 0x01, 0xD0, 0x04, 0xC8, 0xC8, 0x38, 0x6B,   # CMP #$01 / BNE / INY / INY / SEC / RTL
        0xC9, PREFIX, 0xF0, 0x02, 0x18, 0x6B,             # CMP #$9F / BEQ / CLC / RTL
        0xBD, 0x00, 0x00, 0xE8, 0x48,                     # LDA $0000,X / INX / PHA      n
        0x18, 0x6D, 0xDE, 0x0A, 0x3A, 0x8D, 0xDE, 0x0A,   # CLC / ADC $0ADE / DEC A / STA $0ADE  칸 셈(접두에서 1 셌음)
        0xBD, 0x00, 0x00, 0xE8,                           # LDA $0000,X / INX            k
        0xDA, 0x8B,                                       # PHX / PHB
        0xC2, 0x30, 0x29, 0xFF, 0x00, 0xAA,               # REP #$30 / AND #$00FF / TAX
        0x98, 0x18, 0x65, 0xE0, 0xA8,                     # TYA / CLC / ADC $E0 / TAY    버퍼 안 주소
        0xE2, 0x20, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB,         # SEP #$20 / PEA $7E7E / PLB / PLB
        0xA3, 0x04, 0xF0, len(loop),                      # LDA $04,S / BEQ 끝(열 0 개: 그리지 않음)
    )) + loop + bytes((
        0xC2, 0x20, 0x98, 0x38, 0xE5, 0xE0, 0xA8,         # REP #$20 / TYA / SEC / SBC $E0 / TAY
        0xE2, 0x20, 0xAB, 0xFA, 0x68, 0x38, 0x6B))        # SEP #$20 / PLB / PLX / PLA / SEC / RTL


COPY_KR = 0x608200
COPY_JP = 0x608240
MAP_HOOK = 0x608280


def copy_code(src, length):
    """src(뱅크 60)의 length 바이트를 7E:SHARED_WRAM 으로 MVN. 레지스터·DB 를 그대로 두고 RTL."""
    n = length - 1
    return bytes((
        0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0x8B,        # PHP / REP #$30 / PHA / PHX / PHY / PHB
        0xA2, src & 0xFF, src >> 8 & 0xFF,               # LDX #src
        0xA0, SHARED_WRAM & 0xFF, SHARED_WRAM >> 8,      # LDY #$1AC0
        0xA9, n & 0xFF, n >> 8,                          # LDA #len-1
        0x54, 0x7E, src >> 16,                           # MVN $7E,$60
        0xAB, 0x7A, 0xFA, 0x68, 0x28, 0x6B))             # PLB / PLY / PLX / PLA / PLP / RTL


def map_hook_code():
    """2B:82BD(맵을 불러올 때)의 LDA #$1C / STA $0725 자리. 공용 창을 원래 레코드로 되돌리고 원래 두 명령을 한다."""
    return bytes((0x22, COPY_JP & 0xFF, COPY_JP >> 8 & 0xFF, COPY_JP >> 16,
                  0xA9, 0x1C, 0x8D, 0x25, 0x07, 0x6B))


def upload_code():
    """타이틀 FadeOut 끝(메뉴로 넘어가기 직전)에서 열 그림 8KB 를 VRAM 워드 2000 에 DMA(채널 7)로 올린다.
    00:9556 으로 화면을 끄고($1D bit7 도 켜서 NMI 가 다시 켜지 않게), 끝나면 FadeOut 처럼 $1D·$2100 을 0 으로."""
    src = TILES
    return bytes((
        0x08, 0x8B, 0xC2, 0x30, 0x48, 0xDA, 0x5A,        # PHP / PHB / REP #$30 / PHA / PHX / PHY
        0xE2, 0x20, 0xF4, 0x00, 0x00, 0xAB, 0xAB,        # SEP #$20 / PEA $0000 / PLB / PLB
        0x22, 0x56, 0x95, 0x00,                          # JSL $009556
        0xA9, 0x80, 0x8D, 0x15, 0x21,                    # LDA #$80 / STA $2115
        0xA2, 0x00, 0x20, 0x8E, 0x16, 0x21,              # LDX #$2000 / STX $2116
        0xA9, 0x01, 0x8D, 0x70, 0x43,                    # LDA #$01 / STA $4370
        0xA9, 0x18, 0x8D, 0x71, 0x43,                    # LDA #$18 / STA $4371
        0xA2, src & 0xFF, src >> 8 & 0xFF, 0x8E, 0x72, 0x43,
        0xA9, src >> 16, 0x8D, 0x74, 0x43,
        0xA2, 0x00, 0x20, 0x8E, 0x75, 0x43,              # LDX #$2000 / STX $4375(8KB)
        0xA9, 0x80, 0x8D, 0x0B, 0x42,                    # LDA #$80 / STA $420B
        0x22, COPY_KR & 0xFF, COPY_KR >> 8 & 0xFF, COPY_KR >> 16,   # JSL copy_kr(공용 창을 한글로)
        0x64, 0x1D, 0x9C, 0x00, 0x21,                    # STZ $1D / STZ $2100
        0xC2, 0x30, 0x7A, 0xFA, 0x68, 0xAB, 0x28,        # REP #$30 / PLY / PLX / PLA / PLB / PLP
        0x5C, MENU_ENTRY & 0xFF, MENU_ENTRY >> 8 & 0xFF, MENU_ENTRY >> 16))


# 커서 이동 효과음. 04:CB29 선택 고리의 네 방향 처리기(위 CB5A·아래 CC0E·왼쪽 CC2F·오른쪽 CC5C)가 자리를 옮기는
# JSR 을 트램펄린으로 바꾸고, 커서 자리 $0AD7 이 바뀌었을 때만 BRK 19 33 00(창을 열고 고를 때의 소리, 기다리지 않음)을 낸다.
CURSOR_SE = 0x33
CURSOR_MOVES = {0x04CB66: 0xD584, 0x04CC1A: 0xD68C, 0x04CC47: 0xD794, 0x04CC73: 0xD82E}
# B(취소, $24 bit6)는 04:CCA1 BVS → 04:CD0A 로 창을 닫는다. 창 스택 맨 위($09FF + $0AD6)가 첫 메뉴면 아무것도 하지 않는다.
B_CANCEL = 0x04CD0A
TOP_MENUS = (0x5E, 0x5F, 0x60)


def cursor_common():
    """트램펄린이 넘긴 옛 $0AD7(스택)과 지금 값이 다르면 효과음. 이어서 처리기로 RTS."""
    return bytes((0x68, 0xCD, 0xD7, 0x0A, 0xF0, 0x04,          # PLA / CMP $0AD7 / BEQ +4
                  0x00, 0x19, CURSOR_SE, 0x00, 0x60))         # BRK 19 33 00 / RTS


def cursor_tramp(target, common):
    return bytes((0xAD, 0xD7, 0x0A, 0x48,                     # LDA $0AD7 / PHA
                  0x20, target & 0xFF, target >> 8,           # JSR 원래 자리 옮기기
                  0x4C, common & 0xFF, common >> 8 & 0xFF))   # JMP common


def b_check():
    """04:CD0A 의 LDA $0AE8 자리에서 JSR. 첫 메뉴면 이 JSR 과 CC9D 의 JSR 을 함께 버려 선택 고리로 돌아간다."""
    head = bytes((0xDA, 0xAE, 0xD6, 0x0A, 0xBD, 0xFF, 0x09, 0xFA))   # PHX / LDX $0AD6 / LDA $09FF,X / PLX
    body = bytearray()
    for i, n in enumerate(TOP_MENUS):
        left = len(TOP_MENUS) - 1 - i
        if left:
            body += bytes((0xC9, n, 0xF0, 4 * left))         # CMP #n / BEQ ignore
        else:
            body += bytes((0xC9, n, 0xD0, 0x03))             # CMP #n / BNE keep
    return head + bytes(body) + bytes((0x68, 0x68, 0x60,       # ignore: PLA / PLA / RTS
                                        0xAD, 0xE8, 0x0A, 0x60))  # keep: LDA $0AE8 / RTS


def place(data, slack, code):
    """뱅크 04 의 줄어든 레코드 뒤 빈자리(끝 80 뒤라 읽는 곳이 없음)에 code 를 두고 주소를 돌려준다."""
    spot = next((s for s in slack if s[1] - s[0] >= len(code)), None)
    if spot is None:
        raise ValueError(f'뱅크 04 빈자리가 모자람({len(code)}바이트)')
    a = spot[0]
    put(data, a, code)
    spot[0] += len(code)
    return a


def put(data, addr, b, expect=None):
    o = lorom(addr)
    if expect is not None and bytes(data[o:o + len(expect)]) != expect:
        raise ValueError(f'{addr:06X}: 예상한 원래 바이트가 아님')
    data[o:o + len(b)] = b


def build(rom, font, jamo_font, message_font=None):
    """font = 창 글자, jamo_font = 자모판 한 칸 글자, message_font = 메시지 글자(없으면 galmuri11)."""
    data = bytearray(rom)
    atlas = Atlas(font)
    records = {}
    for n, rows in WINDOWS.items():
        a = window_addr(data, n)
        old = window_record(data, a)
        records[n] = [a, old, item_record(atlas, old[:6], rows)]
    a = window_addr(data, SPEED_WINDOW)
    old = window_record(data, a)
    records[SPEED_WINDOW] = [a, old, speed_record(atlas, old)]
    # 제자리에 들어가는 레코드를 먼저 쓰고, 넘치는 레코드는 줄어든 레코드 뒤에 남은 자리로 옮겨 창 표를 고친다.
    slack, moved = [], []
    for n, (a, old, new) in sorted(records.items()):
        if len(new) <= len(old):
            put(data, a, new)
            slack.append([a + len(new), a + len(old)])
        else:
            moved.append(n)
    for n in moved:
        a, old, new = records[n]
        spot = next((s for s in slack if s[1] - s[0] >= len(new)), None)
        if spot is None:
            raise ValueError(f'창 {n:02X}: 옮길 자리가 없음({len(new)}바이트)')
        put(data, spot[0], new)
        hits = [m for m in range(window_count(data)) if window_addr(data, m) == a]
        if not hits:
            raise ValueError(f'창 {n:02X}: 창 표에서 레코드를 찾지 못함')
        for m in hits:
            put(data, 0x04EB48 + m * 2, (spot[0] & 0xFFFF).to_bytes(2, 'little'))
        records[n][0] = spot[0]
        spot[0] += len(new)
    slack.sort(key=lambda s: s[0] - s[1])
    check = place(data, slack, b_check())
    put(data, B_CANCEL, bytes((0x20, check & 0xFF, check >> 8 & 0xFF)), bytes.fromhex('ade80a'))
    common = place(data, slack, cursor_common())
    for site, target in CURSOR_MOVES.items():
        t = place(data, slack, cursor_tramp(target, common))
        put(data, site, bytes((0x20, t & 0xFF, t >> 8 & 0xFF)), bytes((0x20, target & 0xFF, target >> 8)))
    import dq4nameentry as ne
    kr, jp, keys = bytearray(), bytearray(), None
    for n, rows in sorted(SHARED.items()):
        a = window_addr(data, n)
        old = window_span(data, n)
        if rows == 'field':
            new = ne.field_record(old, PREFIX)
        elif rows == 'board':
            new, keys = ne.board_record(atlas, old, jamo_font, PREFIX)
        else:
            new = item_record(atlas, old[:6], rows)
        slot = SHARED_WRAM + len(kr)
        size = max(len(old), len(new))
        kr += new.ljust(size, b'\x00')
        jp += old.ljust(size, b'\x00')
        put(data, 0x04EB48 + n * 2, slot.to_bytes(2, 'little'))
        records[n] = [0x7E0000 | slot, old, new]
    if SHARED_WRAM + len(kr) > MENU_FLAG:
        raise ValueError(f'공용 창 {len(kr)}바이트가 7E:{MENU_FLAG:04X} 을 넘음')
    pad = MENU_FLAG - SHARED_WRAM - len(kr)
    kr += bytes(pad) + b'\xa5'
    jp += bytes(pad) + b'\x00'
    put(data, SHARED_KR, bytes(kr), bytes(len(kr)))
    put(data, SHARED_JP, bytes(jp), bytes(len(jp)))
    for addr, code in ((COPY_KR, copy_code(SHARED_KR, len(kr))), (COPY_JP, copy_code(SHARED_JP, len(jp))),
                       (MAP_HOOK, map_hook_code())):
        put(data, addr, code, bytes(len(code)))
    put(data, MAP_LOAD, bytes((0x22, MAP_HOOK & 0xFF, MAP_HOOK >> 8 & 0xFF, MAP_HOOK >> 16, 0xEA)),
        bytes.fromhex('a91c8d2507'))
    hook = hook_code()
    put(data, HOOK, hook, bytes(len(hook)))
    up = upload_code()
    put(data, UPLOAD, up, bytes(len(up)))
    tiles = atlas.tiles()
    put(data, TILES, tiles, bytes(len(tiles)))
    put(data, WIN_DISPATCH, bytes((0x22, HOOK & 0xFF, HOOK >> 8 & 0xFF, HOOK >> 16, 0xB0, 0x05,
                                   0x20, 0x35, 0xB2, 0x80, 0xC4)), bytes.fromhex('c901f0052035b280c6c8c8'))
    put(data, FADEOUT_EXIT, bytes((0x5C, UPLOAD & 0xFF, UPLOAD >> 8 & 0xFF, UPLOAD >> 16)), bytes.fromhex('5c5cfe03'))
    bridges = {}
    for name, target in {'wait': 0x9D35, 'erase': 0xD1B9, 'draw': 0xD183, 'row': 0xD319, 'blink': 0xD162}.items():
        bridges[name] = place(data, slack, bytes((0x20, target & 0xFF, target >> 8, 0x6B)))
    data = ne.apply(bytes(data), keys, ne.glyph_blob(font, render), bridges)
    import dq4menumsg
    data, atlas.messages = dq4menumsg.apply(data, message_font or Font('galmuri11'))
    import dq4namegame
    data = dq4namegame.apply(data)
    import dq4bg3slot
    data = dq4bg3slot.apply(data)
    import dq4windowname
    data = dq4windowname.apply(data)
    return set_checksum(data), atlas, records


def sheet(atlas, path):
    from PIL import Image
    img = Image.new('RGB', (max(1, len(atlas.cols)) * 8, BAND), (40, 40, 40))
    for c, col in enumerate(atlas.cols):
        if col is None:
            continue
        for y, row in enumerate(col[:8] + col[8:]):
            for x, v in enumerate(row):
                if v:
                    img.putpixel((c * 8 + x, y), (255, 255, 255))
    img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--rom', required=True)
    b.add_argument('--font', default='galmuri9', choices=list(GALMURI))
    b.add_argument('--out', required=True)
    b.add_argument('--jamo-font', default='galmuri7', choices=list(GALMURI))
    s = sub.add_parser('sheet')
    s.add_argument('--font', default='galmuri9', choices=list(GALMURI))
    s.add_argument('--out', required=True)
    args = ap.parse_args()
    font = Font(args.font)
    if args.cmd == 'sheet':
        atlas = Atlas(font)
        for rows in [*WINDOWS.values(), *SHARED.values()]:
            for row in rows:
                for p in row:
                    if isinstance(p, str):
                        atlas.run(p)
        for t in SPEED_TEXT:
            atlas.run(t)
        sheet(atlas, args.out)
        return
    rom = Path(args.rom).read_bytes()
    if hashlib.sha1(rom).hexdigest() != BASE_SHA1:
        raise SystemExit(f'{args.rom}: 서곡 채택본({BASE_SHA1})이 아님')
    out, atlas, records = build(rom, font, Font(args.jamo_font))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(out)
    Path(args.out).with_suffix('.ips').write_bytes(ips_patch(rom, out))
    print(f'{args.out} sha1={hashlib.sha1(out).hexdigest()} 열={len(atlas.cols)} '
          f'바뀐 구간={len(differences(rom, out))}')
    print('\n'.join(atlas.messages))
    for n, (a, old, new) in sorted(records.items()):
        print(f'창 {n:02X} {a:06X} {len(old)}→{len(new)} {new.hex(" ")}')


if __name__ == '__main__':
    main()
