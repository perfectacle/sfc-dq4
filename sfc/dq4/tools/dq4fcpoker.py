"""FC 3장 엔돌 카지노의 포커를 DQ5 슬롯 틀 위에 옮긴다(판 흐름·판정·배당·더블 업은 FC, 카드 그림은 NDS).

FC 포커(뱅크 17, fc/dq4/docs/dq4-chapter3-format.md 「포커」)의 규칙을 dq4fcpoker.asm 이 따르고, 이 모듈은 자료를 만든다.
- 카드: NDS data/MINIGAME/POKER(에셋 저장소 nds/dq4/minigame/poker, 42×64) 를 줄이지 않고 6×8 타일 칸에 두고 무늬마다
  15색(dq4monart.palette). 슬라임·검·방패·왕관 = FC 무늬 0~3, 조커·뒷면은 joker_omote.
- 화면은 BG1 한 장: DQ5 슬롯 NMI(00:FEDD)가 7E:6000 을 매 프레임 VRAM 1400 으로 보내므로 BG1 맵을 1400 에 두고 카드·글
  창·배당 표를 7E:6000 에 쓴다. 글 창 테두리는 DQ5 글자(04:E528, 11:BFCC 와 같은 꼴)를 4bpp 로, 한글은 Galmuri7.
- 들어가는 길은 슬롯과 같다: 02:A8BC → 11:BF71(dq4fcslot 의 입구가 기계 번호 POKER 면 여기로).
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

from dq5map import lorom  # noqa: E402

POKER = 0x20                       # 02:A8BC 에 넘기는 번호(dq4fcslot 입구가 가름)
SUITS = ('slime1', 'ken1', 'tate1', 'crown1')
CARD_W, CARD_H, CELL_W, CELL_H = 42, 64, 6, 8
JOKER, BACK = 52, 53
FC_BANK = 0x17
PAY_TABLE = 0x81D6                 # 패 0~8 배당(2바이트)
HAND_TILES = (0x9CCE, 0x9CDE)      # 손가락 8×8 둘
HAND_PAL = 4                       # FC 스프라이트 팔레트 0(= 전체 팔레트 4번째 묶음)
FELT = 0x0A                        # FC 바닥색
FC_PALETTE = 0xA975                # 슬롯과 같은 표의 앞은 BG; 포커 손가락 색은 FC 실측 팔레트(0A 30 37 17)
HAND_COLORS = (0x30, 0x37, 0x17)
FONT_AT = 0x04E528                 # DQ5 BG3 글자(11:BFCC 가 읽는 곳)
FONT_TILES = {0x01: None, 0x8C: None, 0x8D: None, 0x8E: None}
# 포커 화면 자리(BG1 맵 행·열). 필드에서 넘어온 겹침 주사(239줄, $2133)를 그대로 두므로 맵 0행과 29행은 TV 에서 가려진다
CARD_ROW, CARD_COL0 = 11, 1
LABEL_ROW, DEAL_ROW, DEAL_COL = 19, 21, 13
WINDOW_ROW = 23
from dq4ch3slots import POKER_CODE, POKER_TILES  # noqa: E402
CODE_AT, CODE_END = POKER_CODE
TILES_AT, TILES_END = POKER_TILES                 # 타일 앞 512칸(16KB)
TILE_LIMIT = 0x400

TEXTS = {
    'bet': ('걸 코인 수를 정해 주세요!', '1장부터 10장까지 걸 수 있습니다.'),
    'hold': ('남길 카드를 골라 주세요!', '다 고르면 「나눠 줌」을 누르세요.'),
    'win': ('축하합니다!', ('코인 ', '#', '장이 당첨되었습니다.')),
    'double_ok': (('성공하면 ', '#', '장이 됩니다!'),),
    'double_ask': (('#', '번째 더블 업에 도전하시겠습니까?'),),
    'double_pick': ('이 카드보다 센 카드를', '4장 가운데서 골라 주세요!'),
    'draw': ('비겼습니다!', '한 번 더……'),
    'lose': ('아쉽네요!',),
    'again': ('한 번 더 포커에 도전하시겠습니까?',),
    'nocoin': ('코인이 없으니 코인을 사신 뒤', '다시 와 주세요!'),
}
LABELS = (('keep', '남김', False), ('swap', '바꿈', False), ('deal', '나눠 줌', False), ('yes', '예', True),
          ('no', '아니요', True))
PAY_NAMES = ('로열 스트레이트 플러시', '파이브 카드', '스트레이트 플러시', '포 카드', '풀 하우스', '플러시',
             '스트레이트', '스리 카드', '투 페어')
DIGITS = '0123456789'


def assets():
    folder = os.environ.get('DQ4_ASSETS')
    if not folder:
        raise SystemExit('DQ4_ASSETS 에 에셋 저장소 체크아웃을 주세요(nds/dq4/minigame/poker)')
    return Path(folder) / 'nds' / 'dq4' / 'minigame' / 'poker'


def cards():
    """카드 54장(FC 번호 c = 숫자 × 4 + 무늬, 52 조커, 53 뒷면)의 15색 RGBA 그림과 팔레트 묶음 번호(0~4)."""
    from PIL import Image
    import dq4monart
    out, pals = {}, []
    folder = assets()

    def reduce(images):
        strip = Image.new('RGBA', (CARD_W * len(images), CARD_H))
        for i, im in enumerate(images):
            strip.paste(im, (CARD_W * i, 0))
        red, pal, _ = dq4monart.reduce(strip)
        return [red.crop((CARD_W * i, 0, CARD_W * (i + 1), CARD_H)) for i in range(len(images))], [c for _, c in pal]
    for s, name in enumerate(SUITS):
        sheet = Image.open(folder / f'{name}.png').convert('RGBA')
        imgs = [sheet.crop((CARD_W * (k % 6), CARD_H * (k // 6), CARD_W * (k % 6 + 1), CARD_H * (k // 6 + 1)))
                for k in range(13)]
        red, pal = reduce(imgs)
        for rank, im in enumerate(red):
            out[rank * 4 + s] = (im, len(pals))
        pals.append(pal)
    jk = Image.open(folder / 'joker_omote.png').convert('RGBA')
    (joker, back), pal = reduce([jk.crop((0, 0, CARD_W, CARD_H)), jk.crop((CARD_W, 0, 2 * CARD_W, CARD_H))])
    out[JOKER], out[BACK] = (joker, len(pals)), (back, len(pals))
    pals.append(pal)
    return out, pals


def tile4(pixels):
    """8×8 색 번호(0~15) → SNES 4bpp."""
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = pixels[y * 8 + x]
            for p in range(4):
                if v >> p & 1:
                    out[(p // 2) * 16 + y * 2 + (p & 1)] |= 0x80 >> x
    return bytes(out)


class Tiles:
    """BG1 타일(4bpp) 모으기. 같은 그림은 한 번."""

    def __init__(self):
        self.data, self.index = {0: bytes(32)}, {bytes(32): 0}
        self.free = [n for n in range(1, TILE_LIMIT) if n not in FONT_TILES]

    def put(self, raw, at=None):
        if raw in self.index:
            return self.index[raw]
        n = at if at is not None else self.free.pop(0)
        if at is not None:
            self.free.remove(at) if at in self.free else None
        self.index[raw], self.data[n] = n, raw
        return n

    def blob(self):
        last = max(self.data)
        out = bytearray(32 * (last + 1))
        for n, raw in self.data.items():
            out[32 * n:32 * n + 32] = raw
        return bytes(out)


def font_tiles(dq5):
    """창 테두리·빈칸(DQ5 BG3 글자 01·8C~8E)을 4bpp(색 0~3)로. 01 은 1bpp(평면 1 = FF), 8B~ 는 2bpp."""
    out = {}
    for t in FONT_TILES:
        if t < 0x8B:
            rows = dq5[lorom(FONT_AT) + (t - 1) * 8:][:8]
            px = [((r >> (7 - x)) & 1) | 2 for r in rows for x in range(8)]
        else:
            base = lorom(FONT_AT) + 0x8A * 8 + (t - 0x8B) * 16
            p0, p1 = dq5[base:base + 8], dq5[base + 8:base + 16]
            px = [((p0[y] >> (7 - x)) & 1) | (((p1[y] >> (7 - x)) & 1) << 1) for y in range(8) for x in range(8)]
        out[t] = tile4(px)
    return out


def text_tiles(font, text, window):
    """글 → 타일 칸들(색: 점 3, 창 글은 바탕 2·배당 표 글은 바탕 0)."""
    import dq4menupatch
    cols = dq4menupatch.render(font, text)
    tiles = []
    for col in cols:
        if any(any(r) for r in col[8:]):
            raise ValueError(f'{text!r}: 한 줄(8점) 밖의 점')
        tiles.append(tile4([3 if v else (2 if window else 0) for r in col[:8] for v in r]))
    return tiles


def build(dq5, dq4, font):
    """(타일 바이트, 표 바이트들 dict, 팔레트 바이트)."""
    tiles = Tiles()
    for t, raw in font_tiles(dq5).items():
        tiles.put(raw, at=t)
    blank_window = font_tiles(dq5)[0x01]
    # 글: 줄마다 [타일 번호…], 수 자리(#)는 FF
    texts = bytearray()
    text_at = {}
    for name, lines in TEXTS.items():
        text_at[name] = len(texts)
        texts.append(len(lines))
        for line in lines:
            pieces = (line,) if isinstance(line, str) else (line[0] if isinstance(line[0], tuple) else line)
            row = []
            for piece in pieces:
                if piece == '#':
                    row.append(0xFFFF)
                else:
                    row += [tiles.put(t) for t in text_tiles(font, piece, True)]
            texts.append(len(row))
            for n in row:
                texts += n.to_bytes(2, 'little')
    labels = bytearray()
    label_at = {}
    for key, name, window in LABELS:
        label_at[key] = len(labels)
        row = [tiles.put(t) for t in text_tiles(font, name, window)]
        labels.append(len(row))
        for n in row:
            labels += n.to_bytes(2, 'little')
    digits = [tiles.put(text_tiles(font, d, False)[0]) for d in DIGITS]
    wdigits = [tiles.put(text_tiles(font, d, True)[0]) for d in DIGITS]
    pay = bytearray()
    for name in PAY_NAMES:
        row = [tiles.put(t) for t in text_tiles(font, name, False)]
        pay.append(len(row))
        for n in row:
            pay += n.to_bytes(2, 'little')
    # 카드: 장마다 6×8 칸 낱말(타일 | 팔레트)
    imgs, pals = cards()
    words = bytearray()
    for c in range(54):
        im, p = imgs[c]
        cell = [[0] * (CELL_W * 8) for _ in range(CELL_H * 8)]
        colors = {rgb: i + 1 for i, rgb in enumerate(pals[p])}
        px = im.load()
        for y in range(CARD_H):
            for x in range(CARD_W):
                r, g, b, a = px[x, y]
                if a >= 128:
                    cell[y][3 + x] = colors[(r, g, b)]
        for ty in range(CELL_H):
            for tx in range(CELL_W):
                raw = tile4([cell[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8)])
                n = tiles.put(raw)
                words += (n | (CARD_PAL + p) << 10).to_bytes(2, 'little')
    import dq4chapterbox
    import dq4block

    def color(rgb):
        return dq4chapterbox.bgr555(rgb)
    cg = bytearray(256)
    felt = color(dq4block.nes_rgb(FELT))
    white, black = color((255, 255, 255)), color((0, 0, 0))
    cg[0:8] = felt + white + black + white
    for i, pal in enumerate(pals):
        o = (CARD_PAL + i) * 32
        cg[o:o + 2] = felt
        for k, rgb in enumerate(pal):
            cg[o + 2 + 2 * k:o + 4 + 2 * k] = color(rgb)
    obj = bytearray(32)
    obj[2:8] = b''.join(color(dq4block.nes_rgb(c)) for c in HAND_COLORS)
    from kr_patch.fc import ines
    prg = ines.prg(Path(dq4).read_bytes())

    def fc(a, n):
        o = FC_BANK * 0x4000 + a - 0x8000
        return prg[o:o + n]
    hand = b''.join(tile4([((fc(a, 16)[y] >> (7 - x)) & 1) | (((fc(a, 16)[8 + y] >> (7 - x)) & 1) << 1)
                           for y in range(8) for x in range(8)]) for a in HAND_TILES)
    return {
        'tiles.bin': tiles.blob(), 'cards.bin': bytes(words), 'texts.bin': bytes(texts), 'labels.bin': bytes(labels),
        'pay.bin': bytes(pay), 'payout.bin': fc(PAY_TABLE, 18),
        'digits.bin': b''.join(n.to_bytes(2, 'little') for n in digits),
        'wdigits.bin': b''.join(n.to_bytes(2, 'little') for n in wdigits),
        'cgram.bin': bytes(cg), 'objcg.bin': bytes(obj), 'hand.bin': hand,
    }, {'text_' + k: v for k, v in text_at.items()} | {'label_' + k: v for k, v in label_at.items()}, blank_window


CARD_PAL = 1                       # 카드 팔레트 1~5(0 은 글)


def apply(data, dq5, dq4, font, asar=None):
    asar = asar or os.environ.get('ASAR')
    if not asar:
        raise SystemExit('ASAR 에 asar 실행 파일을 주세요(sfc/dq4/docs/dq4-menu-format.md)')
    d = bytearray(data)
    if any(d[lorom(CODE_AT):lorom(CODE_END - 1) + 1]):
        raise SystemExit('FC 포커 코드 자리가 비어 있지 않음')
    files, offsets, _ = build(dq5, dq4, font)
    if any(d[lorom(TILES_AT):lorom(TILES_END - 1) + 1]):
        raise SystemExit('FC 포커 타일 자리가 비어 있지 않음')
    head = TILES_END - TILES_AT
    files['tiles1.bin'], files['tiles2.bin'] = files['tiles.bin'][:head], files['tiles.bin'][head:]
    defs = ''.join(f'!{k} = ${v:X}\n' for k, v in {'poker_at': CODE_AT, 'poker_end': CODE_END, 'tiles_at': TILES_AT,
                                                    'tiles_end': TILES_END, 'card_row': CARD_ROW,
                                                    'card_col0': CARD_COL0, 'label_row': LABEL_ROW, 'deal_row': DEAL_ROW,
                                                    'deal_col': DEAL_COL, 'window_row': WINDOW_ROW, **offsets}.items())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, blob in files.items():
            (tmp / name).write_bytes(blob)
        (tmp / 'main.asm').write_text(defs + (HERE / 'dq4fcpoker.asm').read_text())
        (tmp / 'rom.sfc').write_bytes(bytes(d))
        r = subprocess.run([asar, '--fix-checksum=off', str(tmp / 'main.asm'), str(tmp / 'rom.sfc')],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'asar: {r.stdout}{r.stderr}')
        return (tmp / 'rom.sfc').read_bytes()


def fc_hand(hand):
    """FC 17:$8203 과 같은 판정: 카드 다섯(0~52) → 패 0~8, 없으면 None. 검사 기준(롬 판정과 견줌)."""
    ranks = [0 if c == JOKER else (c >> 2) + 1 for c in hand]
    suits = [0xFF if c == JOKER else 1 << (c & 3) for c in hand]
    counts = [0] * 13
    for r in ranks:
        if r == 0:
            counts = [n + 1 for n in counts]
        else:
            counts[r - 1] += 1
    joker = 0 in ranks
    flush = (suits[0] & suits[1] & suits[2] & suits[3] & suits[4]) != 0

    def run(x):                     # FC 853C: counts[x..x+3] 모두 있음
        return all(counts[x + i] for i in range(4)) if x + 4 <= 13 else False

    def straight():
        if not joker:
            if any(n >= 2 for n in counts):
                return False
            x = next(i for i, n in enumerate(counts) if n)
            if x == 0:
                return run(1) or run(9)
            return run(x + 1)
        if any(n >= 3 for n in counts):
            return False
        x = next(i for i, n in enumerate(counts) if n == 2) + 1
        if x == 10:
            return True

        def gaps(start):
            miss = 0
            for i in range(4):
                if start + i >= 13 or counts[start + i] != 2:
                    miss += 1
                    if miss > 1:
                        return False
            return True
        if x == 1:
            return gaps(1) or gaps(9)
        return gaps(x)
    three = next((i for i in range(12, -1, -1) if counts[i] == 3), None)
    pair = lambda top: next((i for i in range(top, -1, -1) if counts[i] == 2), None)  # noqa: E731
    if flush and straight():
        return 2 if joker or not (counts[0] and counts[12]) else 0
    if 5 in counts:
        return 1
    if flush and straight():
        return 2
    if 4 in counts:
        return 3
    if three is not None:
        if joker:
            if three - 1 >= 0 and next((i for i in range(three - 1, -1, -1) if counts[i] == 3), None) is not None:
                return 4
        elif pair(12) is not None:
            return 4
    if flush:
        return 5
    if straight():
        return 6
    if three is not None:
        return 7
    if not joker:
        p = pair(12)
        if p is not None and p - 1 >= 0 and pair(p - 1) is not None:
            return 8
    return None
