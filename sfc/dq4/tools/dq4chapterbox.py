"""FC 처럼 검은 화면에 금테 상자로 장 제목을 띄우고, 검은 화면의 메시지 창 서술 뒤에 맵을 밝힌다.

맵을 불러올 때 주화면 층 그림자 $0733 을 BG3(창 층)만으로 두면 맵·인물이 안 그려져 바탕색(검정)만 남는다.
상자는 BG3 의 메시지 캔버스 타일 자리에 올린다. 테두리와 바탕은 FC 롬의 장 제목 상자 타일(1A:$8CB0)을 풀어 쓰고,
제목 글자는 Galmuri11 을 FC 글자처럼 가로로 굵게 하고 FC 와 같은 규칙으로 그림자를 단다.
형식은 sfc/dq4/docs/dq4-chapter1-format.md.

  python sfc/dq4/tools/dq4chapterbox.py preview --out work/ch1/chapter-box.png
"""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq5map import lorom  # noqa: E402

# FC: 1A:$80C5 → $8254 가 1A:$8CB0 의 1비트 타일로 상자 타일 $01~$AC 를 만든다(fc/dq4/docs/dq4-fcgfx.md).
FC_TILES = (0x1A, 0x8CB0)
FC_NO_SHADOW = (0x1D, 0x20, 0xA1, 0xA8)    # 이 두 묶음은 plane 1 이 모두 00
# 1장 제목 상자의 nametable(열 4~29, 행 8~13). 바깥 줄이 테두리, 안이 바탕 9A
FC_BORDER = {'tl': 0xA1, 't': 0xA2, 'tr': 0xA3, 'l': 0xA4, 'r': 0xA5, 'bl': 0xA6, 'b': 0xA7, 'br': 0xA8}
FC_FILL = 0x9A
BOX_COL, BOX_ROW, BOX_W, BOX_H = 4, 8, 26, 6
TEXT_ROW = 2                                # 상자 안 글자 띠(16점)의 첫 행
TITLE = '제1장   왕궁의 전사들'

# FC 팔레트(MesenCE 색): 0 검정, 1 금색(테두리)·흰색(글자), 2 파랑, 3 흰색
GOLD, BLUE, WHITE = (234, 158, 34), (20, 18, 167), (255, 254, 255)

# BG3 캔버스: 메시지 창 안쪽이 타일 096~17F 를 비트맵처럼 쓴다(VRAM 워드 1000 + 타일 × 8). 상자를 지운 뒤
# 다음 메시지가 이 자리를 다시 그린다.
CANVAS = 0x096
CANVAS_END = 0x180
BG3_CHR, BG3_MAP = 0x1000, 0x3C00           # VRAM 워드
MAP_BUFFER = 0x7E5000                      # BG3 타일맵 버퍼(2KB). NMI 가 VRAM 3C00 으로 올린다
CGRAM_BUFFER = 0x7E3914                    # CGRAM 과 같은 지금 색 버퍼
PAL_BORDER, PAL_TEXT = 1, 2                # BG3 팔레트(CGRAM 4~7, 8~11). 상자가 떠 있는 동안만 덮는다
BLANK = 0x2C00                             # 창 밖 BG3 칸(타일 0, 팔레트 3, 우선)

FADE_STEP = 1       # 밝기 한 단계 프레임
HOLD = 60           # 상자를 다 밝힌 채 두는 프레임(FC 는 페이드까지 75~90프레임쯤)
REVEAL_STEP = 1
SONG_WAIT_MAX = 300  # 맵 곡이 시작되기를 기다리는 상한(프레임). FC 는 서술 창이 닫히고 67프레임 뒤 성 곡
# 맵 곡 건너뛰기 비트(7E:21A5 bit6). 원래 롬에서는 03:C729 만 켠다. 켜져 있으면 01:C2FA 가 동료 자리 맞추기(00:D515)도
# 건너뛰지만, 새 게임부터 맵을 밝힐 때까지 01:C2FA·00:D515 는 한 번도 돌지 않았다(실측)
SKIP_SONG = (0x7E21A5, 0x40)


def fc_tile(nes, n):
    """FC 상자 타일 n 의 8x8 색 번호."""
    bank, addr = FC_TILES
    o = 0x10 + bank * 0x4000 + (addr - 0x8000) + (n - 1) * 8
    p0 = nes[o:o + 8]
    if any(a <= n <= b for a, b in (FC_NO_SHADOW[:2], FC_NO_SHADOW[2:])):
        p1 = bytes(8)
    else:
        p1 = bytes([0xFF] + [~p0[y - 1] & 0xFF for y in range(1, 8)])
    return [[(p0[y] >> (7 - x) & 1) | (p1[y] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def title_mask(font, text, width):
    """글자 점(16줄 x width). Galmuri 를 한 점 오른쪽으로 겹쳐 굵게 하고 가운데에 둔다."""
    import dq4menupatch
    cols = dq4menupatch.render(font, text)
    band = [sum((col[y] for col in cols), []) for y in range(dq4menupatch.BAND)]
    w = max((x + 2 for row in band for x, v in enumerate(row) if v), default=0)
    if w > width:
        raise ValueError(f'{text!r}: 상자 안 {width}점을 넘음({w})')
    left = (width - w) // 2
    out = [[0] * width for _ in band]
    for y, row in enumerate(band):
        for x, v in enumerate(row):
            if v:
                out[y][left + x] = out[y][left + x + 1] = 1
    return out


def box_pixels(nes, font, text=TITLE):
    """상자 26x6 타일의 색 번호 그림과 타일마다의 팔레트(테두리 / 안)."""
    W, H = BOX_W * 8, BOX_H * 8
    img = [[0] * W for _ in range(H)]
    pal = [[PAL_TEXT] * BOX_W for _ in range(BOX_H)]
    for ty in range(BOX_H):
        for tx in range(BOX_W):
            v = 't' if ty == 0 else 'b' if ty == BOX_H - 1 else ''
            h = 'l' if tx == 0 else 'r' if tx == BOX_W - 1 else ''
            name = v + h
            n = FC_BORDER[name] if name else FC_FILL
            if name:
                pal[ty][tx] = PAL_BORDER
            t = fc_tile(nes, n)
            for y in range(8):
                img[ty * 8 + y][tx * 8:tx * 8 + 8] = t[y]
    # 글자: FC 처럼 plane 0 = 점, plane 1 = 한 줄 위 점을 뒤집은 값 → 점 1·3(흰색), 바로 아래 0(검은 그림자), 나머지 2(파랑)
    inner = (BOX_W - 2) * 8
    mask = title_mask(font, text, inner)
    for y, row in enumerate(mask):
        for x, g in enumerate(row):
            up = mask[y - 1][x] if y else 0
            img[TEXT_ROW * 8 + y][8 + x] = g | (0 if up else 2)
    return img, pal


def snes_tile(rows):
    out = bytearray()
    for r in rows:
        out += bytes((sum((v & 1) << (7 - x) for x, v in enumerate(r)),
                      sum((v >> 1 & 1) << (7 - x) for x, v in enumerate(r))))
    return bytes(out)


def box_data(nes, font, text=TITLE):
    """(타일 바이트, 타일맵 26x6 워드 바이트). 같은 타일은 한 번만 둔다."""
    img, pal = box_pixels(nes, font, text)
    tiles, index, words = bytearray(), {}, bytearray()
    for ty in range(BOX_H):
        for tx in range(BOX_W):
            t = snes_tile([img[ty * 8 + y][tx * 8:tx * 8 + 8] for y in range(8)])
            if t not in index:
                index[t] = CANVAS + len(index)
                tiles += t
            words += (0x2000 | pal[ty][tx] << 10 | index[t]).to_bytes(2, 'little')
    if CANVAS + len(index) > CANVAS_END:
        raise ValueError(f'상자 타일 {len(index)}장이 캔버스를 넘음')
    return bytes(tiles), bytes(words)


def bgr555(rgb):
    r, g, b = (round(c * 31 / 255) for c in rgb)
    return (b << 10 | g << 5 | r).to_bytes(2, 'little')


def palettes():
    """CGRAM 4~11: 테두리 [-, 금색, 파랑, 파랑], 글자 [-, 흰색, 파랑, 흰색]."""
    zero = bytes(2)
    return (zero + bgr555(GOLD) + bgr555(BLUE) + bgr555(BLUE) +
            zero + bgr555(WHITE) + bgr555(BLUE) + bgr555(WHITE))


# ── 65816 코드 ───────────────────────────────────────────────────────────────────────────
def le(v, n):
    return v.to_bytes(n, 'little')


def dma_vram(word, src, size):
    """M 8·X 16, DB 00 에서 채널 7 로 VRAM 쓰기."""
    return bytes((
        0xA9, 0x80, 0x8D, 0x15, 0x21,                       # LDA #$80 / STA $2115
        0xA2, *le(word, 2), 0x8E, 0x16, 0x21,               # LDX #word / STX $2116
        0xA9, 0x01, 0x8D, 0x70, 0x43,                       # LDA #$01 / STA $4370
        0xA9, 0x18, 0x8D, 0x71, 0x43,                       # LDA #$18 / STA $4371
        0xA2, *le(src & 0xFFFF, 2), 0x8E, 0x72, 0x43,       # LDX #src / STX $4372
        0xA9, src >> 16, 0x8D, 0x74, 0x43,                  # LDA #bank / STA $4374
        0xA2, *le(size, 2), 0x8E, 0x75, 0x43,               # LDX #size / STX $4375
        0xA9, 0x80, 0x8D, 0x0B, 0x42))                      # LDA #$80 / STA $420B


def dma_cgram(index, src, size):
    return bytes((
        0xA9, index, 0x8D, 0x21, 0x21,                      # LDA #index / STA $2121
        0xA9, 0x00, 0x8D, 0x70, 0x43,                       # LDA #$00 / STA $4370
        0xA9, 0x22, 0x8D, 0x71, 0x43,                       # LDA #$22 / STA $4371
        0xA2, *le(src & 0xFFFF, 2), 0x8E, 0x72, 0x43,
        0xA9, src >> 16, 0x8D, 0x74, 0x43,
        0xA2, *le(size, 2), 0x8E, 0x75, 0x43,
        0xA9, 0x80, 0x8D, 0x0B, 0x42))


def fill_vram(word, src, words):
    """빈 캔버스(타일 줄마다 plane 0 = 00, plane 1 = FF)로 채운다. src 는 00 FF 두 바이트. 낮은 바이트($2118)와
    높은 바이트($2119)를 고정 주소 DMA 두 번으로 따로 쓴다."""
    out = bytearray()
    for inc, reg, at in ((0x00, 0x18, src), (0x80, 0x19, src + 1)):
        out += bytes((
            0xA9, inc, 0x8D, 0x15, 0x21,                     # LDA #inc / STA $2115
            0xA2, *le(word, 2), 0x8E, 0x16, 0x21,
            0xA9, 0x08, 0x8D, 0x70, 0x43,                    # 고정 주소, 한 레지스터
            0xA9, reg, 0x8D, 0x71, 0x43,
            0xA2, *le(at & 0xFFFF, 2), 0x8E, 0x72, 0x43,
            0xA9, at >> 16, 0x8D, 0x74, 0x43,
            0xA2, *le(words, 2), 0x8E, 0x75, 0x43,
            0xA9, 0x80, 0x8D, 0x0B, 0x42))
    return bytes(out)


def mvn(src, dst, size):
    """M·X 16 에서 src → dst 로 size 바이트. DB 가 dst 뱅크가 되므로 부른 쪽이 되돌린다."""
    return bytes((
        0xA2, *le(src & 0xFFFF, 2), 0xA0, *le(dst & 0xFFFF, 2), 0xA9, *le(size - 1, 2),
        0x54, dst >> 16, src >> 16))


def wait(frames):
    return bytes((0x00, 0x09, frames))                      # BRK 09 n: n 프레임 기다림


def screen_off():
    """NMI 를 끄고(조이패드 자동 읽기는 둠) 화면을 끈다. 맵 층이 꺼져 있어 화면은 원래 검다."""
    return bytes((
        0xAD, 0x1E, 0x00, 0x29, 0x7F, 0x8D, 0x00, 0x42,     # LDA $001E / AND #$7F / STA $4200
        0xA9, 0x80, 0x8D, 0x00, 0x21))                      # LDA #$80 / STA $2100


def screen_on():
    """NMI 를 되살린다. 다음 NMI 가 $2100 을 그림자 $1D 로 쓴다."""
    return bytes((0xAD, 0x1E, 0x00, 0x8D, 0x00, 0x42))      # LDA $001E / STA $4200


def fade(first, last, step):
    """$1D 를 first 에서 last 까지 한 단계씩, 단계마다 step 프레임. M 8."""
    inc = 0x1A if last > first else 0x3A                   # INC A / DEC A
    cmp_ = last + (1 if last > first else -1)
    body = bytes((0x8D, 0x1D, 0x00)) + wait(step) + bytes((0xAD, 0x1D, 0x00, inc, 0xC9, cmp_ & 0xFF))
    return bytes((0xA9, first)) + body + bytes((0xD0, -(len(body) + 2) & 0xFF))


ENTER = bytes((0x08, 0x8B, 0x0B, 0xC2, 0x30, 0x48, 0xDA, 0x5A,     # PHP / PHB / PHD / REP #$30 / PHA / PHX / PHY
               0xF4, 0x00, 0x00, 0xAB, 0xAB, 0xE2, 0x20))         # PEA $0000 / PLB / PLB / SEP #$20
LEAVE = bytes((0xC2, 0x30, 0x7A, 0xFA, 0x68, 0x2B, 0xAB, 0x28, 0x6B))  # REP #$30 / PLY / PLX / PLA / PLD / PLB / PLP / RTL
DB0 = bytes((0xF4, 0x00, 0x00, 0xAB, 0xAB))                        # PEA $0000 / PLB / PLB


def map_rows(src_of_row):
    """상자 6행의 타일맵 버퍼 쓰기. src_of_row(r) 는 그 행 52바이트의 롬 주소(None 이면 BLANK 로 채움)."""
    out = bytearray((0xC2, 0x30))                                   # REP #$30
    for r in range(BOX_H):
        dst = MAP_BUFFER + ((BOX_ROW + r) * 32 + BOX_COL) * 2
        src = src_of_row(r)
        if src is None:
            # 첫 칸에 BLANK 를 쓰고 MVN 으로 뒤로 밀어 채운다
            out += bytes((0xA9, *le(BLANK, 2), 0x8F, *le(dst, 3)))  # LDA #BLANK / STA long
            out += mvn(dst, dst + 2, BOX_W * 2 - 2)
        else:
            out += mvn(src, dst, BOX_W * 2)
    return bytes(out) + DB0 + bytes((0xE2, 0x20))                   # SEP #$20


def if_pending(then, other=b''):
    """왕좌의 방(36/01)이고 연출이 아직이면(7E:219E & 04 꺼짐) then, 아니면 other. M 8, A 를 씀."""
    checks = [bytes((0xAD, 0xBC, 0x00, 0xC9, 0x36, 0xD0)),      # LDA $00BC / CMP #$36 / BNE
              bytes((0xAD, 0xBD, 0x00, 0xC9, 0x01, 0xD0)),      # LDA $00BD / CMP #$01 / BNE
              bytes((0xAF, 0x9E, 0x21, 0x7E, 0x29, 0x04, 0xD0))]  # LDA $7E219E / AND #$04 / BNE
    then = then + (bytes((0x80, len(other))) if other else b'')   # BRA 끝
    total = sum(len(c) + 1 for c in checks)
    out, end = bytearray(), 0
    for c in checks:
        end += len(c) + 1
        out += c + bytes((total + len(then) - end,))
    return bytes(out) + then + other


class Layout:
    """뱅크 하나에 코드·자료를 늘어놓는다."""

    def __init__(self, base, tiles, tilemap, pal):
        self.base, self.tiles, self.map, self.pal = base, tiles, tilemap, pal
        self.build()

    def build(self):
        # 코드 길이는 자료 주소에 따라 바뀌지 않으므로(즉값 폭 고정) 두 번 짜서 자리를 맞춘다
        addr = {'tiles': 0, 'map': 0, 'pal': 0, 'blank': 0}
        for _ in range(2):
            start, hook, box, reveal = self.code(addr)
            self.start_at = self.base
            self.hook_at = self.start_at + len(start)
            self.box_at = self.hook_at + len(hook)
            self.reveal_at = self.box_at + len(box)
            data_at = self.reveal_at + len(reveal)
            addr = {'blank': data_at, 'pal': data_at + 2, 'map': data_at + 2 + len(self.pal),
                    'tiles': data_at + 2 + len(self.pal) + len(self.map)}
        self.blob = start + hook + box + reveal + b'\x00\xff' + self.pal + self.map + self.tiles
        if (self.base & 0xFFFF) + len(self.blob) > 0x10000:
            raise ValueError('뱅크를 넘음')

    def code(self, a):
        # 새 게임 시작(시작 지점 표를 읽은 뒤): 21A5.6 이 켜져 있으면 맵을 불러올 때 곡을 바꾸지 않는다(00:CE6B).
        # 이 표는 「모험의 서를 만든다」에서 이름 입력 전에도 읽으므로 곡을 끄는 일은 여기서 하지 않는다
        start = (bytes((0xA9, 0x80, 0x85, 0xBE)) +                    # 원래: LDA #$80 / STA $BE
                 if_pending(bytes((0xAF, *le(SKIP_SONG[0], 3), 0x09, SKIP_SONG[1],   # LDA $7E21A5 / ORA #$40
                                   0x8F, *le(SKIP_SONG[0], 3)))) +                    # STA $7E21A5
                 bytes((0xA9, 0x80, 0x6B)))                            # LDA #$80 / RTL
        # 맵을 불러올 때: 연출 전이면 주화면을 BG3 만으로. 메뉴 곡은 메뉴를 나갈 때 줄어든다(dq4overture.MENU_FADE)
        hook = (if_pending(bytes((0xA9, 0x04)), bytes((0xA9, 0x17))) +
                bytes((0x8F, 0x33, 0x07, 0x7E, 0x6B)))                # STA $7E0733 / RTL
        put_map = map_rows(lambda r: a['map'] + r * BOX_W * 2)
        clear_map = map_rows(lambda r: None)
        pal_off = (PAL_BORDER * 4) * 2
        n = len(self.pal)
        # 덮는 팔레트(지금 색 버퍼)는 스택에 n 바이트를 잡아 두었다가 되돌린다. 맵을 불러올 때의 사본(3B14)은
        # 이 자리가 0 이었다(실측)
        save = bytes((0xC2, 0x30, 0x3B, 0x38, 0xE9, *le(n, 2), 0x1B,     # REP #$30 / TSC / SEC / SBC #n / TCS
                      0x1A, 0xA8, 0xA2, *le((CGRAM_BUFFER + pal_off) & 0xFFFF, 2),   # INC / TAY / LDX #buf
                      0xA9, *le(n - 1, 2), 0x54, 0x00, CGRAM_BUFFER >> 16,         # LDA #n-1 / MVN $00,$7E
                      0xE2, 0x20))
        restore = bytes((0xC2, 0x30, 0x3B, 0x1A, 0xAA, 0xA0, *le((CGRAM_BUFFER + pal_off) & 0xFFFF, 2),
                         0xA9, *le(n - 1, 2), 0x54, CGRAM_BUFFER >> 16, 0x00,     # TSC / INC / TAX / LDY / MVN $7E,$00
                         0x3B, 0x18, 0x69, *le(n, 2), 0x1B)) + DB0 + bytes((0xE2, 0x20))  # TSC / CLC / ADC #n / TCS
        box = (ENTER + save + bytes((0x9C, 0x1D, 0x00)) + screen_off() + bytes((0xC2, 0x10)) +   # STZ $001D
               dma_vram(BG3_CHR + CANVAS * 8, a['tiles'], len(self.tiles)) +
               dma_cgram(PAL_BORDER * 4, a['pal'], len(self.pal)) +
               bytes((0xC2, 0x30)) + mvn(a['pal'], CGRAM_BUFFER + pal_off, len(self.pal)) + DB0 +
               bytes((0xE2, 0x20)) + put_map +
               dma_vram(BG3_MAP, MAP_BUFFER, 0x800) + screen_on() +
               fade(1, 15, FADE_STEP) + wait(HOLD) + fade(14, 0, FADE_STEP) +
               screen_off() + bytes((0xC2, 0x10)) + clear_map +
               dma_vram(BG3_MAP, MAP_BUFFER, 0x800) +
               fill_vram(BG3_CHR + CANVAS * 8, a['blank'], len(self.tiles) // 2) +
               restore + dma_cgram(PAL_BORDER * 4, CGRAM_BUFFER + pal_off, n) +
               bytes((0xA9, 0x0F, 0x8D, 0x1D, 0x00)) + screen_on() + LEAVE)      # 메시지 창은 밝은 채로
        # FC 는 서술 창이 닫히면 곡을 멈추고, 왕좌의 방이 밝아질 때 성 곡을 튼다
        # 곡 자료를 SPC 로 보내는 동안(소리 롬에서 약 160프레임) 화면을 검게 두고, 곡이 시작되면 밝힌다
        song_wait = bytes((0xDA,)) + wait(1) + bytes((0xFA,                 # PHX / BRK 09 01 / PLX
                     0xAD, 0x4B, 0x19, 0x29, 0x7F, 0xCD, 0x8B, 0x1D,       # LDA $194B / AND #$7F / CMP $1D8B
                     0xF0, 0x03, 0xCA))                                    # BEQ 끝 / DEX
        song_wait = (bytes((0xA2, *le(SONG_WAIT_MAX, 2))) + song_wait +
                     bytes((0xD0, -(len(song_wait) + 2) & 0xFF)))          # LDX #max / … / BNE 고리
        reveal = (ENTER + bytes((0xAF, *le(SKIP_SONG[0], 3), 0x29, ~SKIP_SONG[1] & 0xFF,   # LDA / AND #$BF
                                 0x8F, *le(SKIP_SONG[0], 3))) +                       # STA $7E21A5
                  bytes((0x22, 0x8F, 0xFE, 0x23)) + song_wait +          # JSL $23FE8F(맵 곡을 틀고 21DF 를 지움)
                  bytes((0x9C, 0x1D, 0x00)) + wait(1) +                # 밝기 0 이 걸린 뒤 맵 층을 켠다
                  # NMI 는 $0733 을 늘 $212C 로 쓰지 않으므로(실측) 맵을 불러올 때처럼 직접 쓴다
                  bytes((0xA9, 0x17, 0x8D, 0x33, 0x07, 0x8D, 0x2C, 0x21, 0x8D, 0x2D, 0x21)) +
                  fade(1, 15, REVEAL_STEP) + LEAVE)
        return start, hook, box, reveal


START_AT = 0x25834A
START_ORIG = bytes.fromhex('a9 80 85 be')      # LDA #$80 / STA $BE, 뒤의 RTS 는 그대로
HOOK_AT = 0x2B8293
HOOK_ORIG = bytes.fromhex('a9 17 8d 33 07')    # LDA #$17 / STA $0733, 뒤의 STA $212C·$212D 가 A 를 씀
CODE_AT = 0x5F8000


def entry_points():
    """인물 스크립트가 부를 네이티브 주소 {'box', 'reveal'}. 코드가 자료보다 앞이라 자료 크기와 상관없다."""
    lay = Layout(CODE_AT, b'', bytes(BOX_W * BOX_H * 2), palettes())
    return {'box': lay.box_at, 'reveal': lay.reveal_at}


def writes(nes, font):
    """(롬 주소, 바이트, 원래 바이트 또는 None) 목록."""
    lay = Layout(CODE_AT, *box_data(nes, font), palettes())
    if {'box': lay.box_at, 'reveal': lay.reveal_at} != entry_points():
        raise AssertionError('네이티브 주소가 자료 크기에 따라 바뀜')
    return [(START_AT, bytes((0x22, *le(lay.start_at, 3))), START_ORIG),
            (HOOK_AT, bytes((0x22, *le(lay.hook_at, 3), 0xEA)), HOOK_ORIG),
            (CODE_AT, lay.blob, None)]


def apply(data, nes, font):
    d = bytearray(data)
    ws = writes(nes, font)
    for addr, payload, orig in ws:
        o = lorom(addr)
        if orig is not None and bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        if orig is None and any(d[o:o + len(payload)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(payload)] = payload
    return bytes(d)


def preview(nes, font, path):
    from PIL import Image
    img, pal = box_pixels(nes, font)
    colors = {PAL_BORDER: [(0, 0, 0), GOLD, BLUE, BLUE], PAL_TEXT: [(0, 0, 0), WHITE, BLUE, WHITE]}
    im = Image.new('RGB', (256, 224))
    px = im.load()
    for y, row in enumerate(img):
        for x, v in enumerate(row):
            px[BOX_COL * 8 + x, BOX_ROW * 8 + y] = colors[pal[y // 8][x // 8]][v]
    im.resize((512, 448), Image.NEAREST).save(path)


def main():
    import dq4menupatch
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preview')
    p.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    preview(args.dq4.read_bytes(), dq4menupatch.Font('galmuri11'), args.out)
    print(args.out)


if __name__ == '__main__':
    main()
