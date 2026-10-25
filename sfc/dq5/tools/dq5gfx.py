"""DQ5(SFC) 그래픽을 롬에서 PNG 로 뽑는다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「그래픽 내보내기와 갤러리」.

스프라이트를 새로 그릴 때 원작 그림을 같은 배율로 찾아보려는 용도다. 디코더는 다른 도구의 것을 그대로 쓴다.
OUT 아래 분류 폴더는 에셋 저장소(sfc-dq4-assets)의 공통 규칙을 따른다.

  maps/          실내 맵 346개와 그룹 $50 이상 18개(맵별 루틴 15:F907 반영). <BC>-<BD>[-마을 이름][-변형].png,
                 변형 annot(인물·출구·상자·タンス·발밑 표시), night(밤 팔레트), setNN(플래그 팔레트 세트 01:9771)
  field/         세계 지도 셋. field0(낮)·field0-night·field0-<포인터>(다른 시간대 팔레트)·field1·field2·fieldN-annot(입구)
  monsters/      전투 몬스터 236마리 <번호>-<이름>.png (dq5mongfx)
  battlebg/      전투 배경 49개 × 세계($1949) 셋 <번호>[-<세계>].png (dq5battlebg)
  gfx/blocks/    CHR 뱅크(chrNN-color·-gray), 맵마다 쓰는 블록(maps/), 필드 블록·타일
  gfx/screens/   창·메뉴 BG3 타일(04:E528)과 창 견본
  gfx/anim/      필드의 움직이는 타일(타일 454~459 8벌, 물 타일 돌리기, 물결 팔레트) 시트와 GIF
  gfx/font.png   폰트 글자 0x3DB 개

맵·지도·몬스터·배경은 1배, 타일 시트만 2배다. 분류 폴더마다 index.json(항목 목록)과 SOURCE.txt(만든 커밋·명령·롬)를 남긴다.
롬에서 뽑은 그림이므로 공개 저장소에 커밋하지 않는다.

사용:
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc [--out work/dq5gfx] [--only maps,field] [--maps 02/06,51/50]
  python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc --check work/d/f00005 06/03 [--set 26] [--night]
--check 는 sfc/dq5/tools/lua/dq5gfxdump.lua 로 그 맵에서 덤프한 VRAM·CGRAM 으로 BG2 위에 BG1 을 겹친 화면을 맵 그림과 비교한다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from dq5exit import apply_hook, exit_attrs  # noqa: E402
from dq5map import (CHR_PALETTE, GROUP_TABLE, HIGH_CHR_PALETTE, PALETTES, PALSET_LISTS, Decoder,  # noqa: E402
                    Rom, chr_pixels, lorom, map_cgram, map_pointer)

SLOT = 0xBE
# 01:9771: 맵을 들어갈 때 10:DE0B 로 고른 팔레트 세트를 플래그에 따라 바꾸는 표. [BC][BD|FF][플래그|FF][마스크][세트], FF 로 끝.
# 플래그 bit7 이 0 이면 7E:2190+번호 & 마스크가 켜졌을 때, 1 이면 꺼졌을 때 그 세트를 10:DDCF 로 다시 불러온다.
PALSET_FLAGS = 0x2A8690
# 0F:8ED7 그룹 포인터 54개. 마지막 그룹은 표 바로 앞에서 끝난다.
GROUPS = 0x36
HOOK_SCAN = 400
# 그룹 $50 이상: ($BC, $BD 개수). docs/dq5-map-format.md 「그룹 $50 이상」.
HIGH_MAPS = ((0x50, 2), (0x51, 8), (0x52, 1), (0x53, 3), (0x54, 4))
# 01:A16B: [하한 16비트][포인터 색인] 10개를 뒤에서부터 보아 $075E 이상인 첫 항목. 01:A189 포인터 → 2·3번 줄 색 1~15.
FIELD_TIME = 0x01A16B
FIELD_TIME_PTRS = 0x01A189
# 세계 1·2 의 2·3번 줄(01:A6A3).
FIELD_WORLD_ROWS = (None, 0x01A199, 0x01A3B5)
# 필드 4번 줄은 팔레트 세트 목록의 $34 번(10:EC48), 세계 0 은 색 1~3 을 01:A0F6 + $1961*6 의 물결 색으로 바꾼다(10단계).
FIELD_ROW4 = PALETTES + 0x34 * 32
FIELD_WAVE = 0x01A0F6
WAVE_STEPS = 10
# 04:E17D: BG3 창·메뉴 타일. 04:E528 에서 1bpp 138개(둘째 평면은 FF)를 타일 1 부터, 이어서 2bpp 11개를 올린다.
UI_TILES = 0x04E528
UI_1BPP, UI_2BPP = 0x8A, 0x0B
# 04:9870: CGRAM 0번 줄(BG3 2bpp 팔레트 넷) 32바이트.
UI_PALETTE = 0x0498D7
# 2B:8000: 필드 타일 454~459(VRAM 워드 3C60)의 8벌을 1E:D0FF 의 RLE(01:A64F 와 같은 꼴)로 7E:C800 에 푼다.
FIELD_ANIM = 0x1ED0FF
FIELD_ANIM_TILE, FIELD_ANIM_COUNT, FIELD_ANIM_SETS = 0x1C6, 6, 8
# 04:8000: 맵마다 VRAM BG 슬롯 001~ 에 올리는 공통 타일(문·보물상자 등 맵 위 물체가 씀).
# (슬롯, 자료, 형식): rle = 1F:D28B 런 길이 압축(낮은 바이트 줄기 뒤 높은 바이트 줄기), raw = 4bpp 그대로 6개.
COMMON_TILES = ((0x001, 0x04826E, 'rle'), (0x09E, 0x049287, 'rle'), (0x0A0, 0x049302, 'rle'), (0x0AE, 0x04940F, 'raw'))
COMMON_TILES_5352 = 0x0492C7  # 53/52 만 슬롯 09E 를 이것으로
# 01:F3C9: 맵을 푼 뒤 01:D2FC 표의 물체(닫힌 문 등)를 셀 위층에 그린다. 그룹마다·맵마다 [X][Y][종류][플래그][…] 5바이트,
# 항목 끝 바이트가 80 이상이면 그 맵 끝, C0 이상이면 그룹 끝(빈 맵은 그 바이트 하나).
DOOR_TABLE = 0x01D2FC
# 종류 → 그리는 루틴(01:F4AF). 없는 종류는 01:F635. 루틴이 쓰는 타일 워드 표(01 뱅크)는 아래 둘이 종류로 고른다.
DOOR_ROUTINES = {0x44: 0x01F6B1, 0x43: 0x01F5CA, 0x3F: 0x01F727, 0x40: 0x01F727, 0x49: 0x01F4E6, 0x42: 0x01F4E6,
                 0x41: 0x01F4E6, 0x48: 0x01F4E6, 0x46: 0x01F69E}
DOOR_TABLE_SELECT = {0xF7F7: ({0x3E: 0xFD9F, 0x3C: 0xFDAB, 0x3B: 0xFDB7, 0x3D: 0xFDC3, 0x4D: 0xFDCF}, 0xFDE7),
                     0xF7D6: ({0x48: 0xFE8F, 0x49: 0xFE2F, 0x42: 0xFE4F}, 0xFE6F),
                     0xF7C8: ({0x3F: 0xFDFF}, 0xFE17)}
# 03:C8B3: たびびとのちず 를 쓰면 모드 7 로 띄우는 세계 지도. 03:CAC2 가 VRAM 워드마다 타일맵 바이트와 점 하나를 만든다.
# 점은 필드 좌표($CE,$D0, 처음 0·10)의 블록 번호 → 03:CC48 의 니블 + 20(색 번호), 좌표는 03:CD48·03:CD58 표만큼 나아간다.
# 색 20~2F 는 03:CC2C. 타일맵은 16x15 타일(128x120 점)만 쓴다.
WORLD_SCREEN_COLORS = 0x03CC2C
WORLD_SCREEN_BLOCK_COLOR = 0x03CC48
WORLD_SCREEN_STEP_X, WORLD_SCREEN_STEP_Y = 0x03CD48, 0x03CD58
# 1E:D7E3: 타이틀 화면 글자(ENIX PRESENTS ~ DRAGON QUEST V)의 2bpp 타일. 필드 RLE(01:A64F)와 같은 꼴이고,
# 앞 16바이트(빈 타일 하나)를 더해 위·아래로 짝지으면 대부분 8x16 글자 하나지만, 타일을 나눠 쓰는 글자(D·E·M·W 등)도 있다.
CREDITS_FONT = 0x1ED7E3
# 02:FB2B: 글자 문자열(02:FF3B 의 24비트 포인터 둘: 0 = 엔딩 스태프 롤 1E:F5B8, 1 = 타이틀 1E:FEEC).
# 00~3F 는 글자 번호 → 1E:F539 + 번호*3 = [위 타일][아래 타일][너비(0 이면 8점)]. 그 밖은 제어:
# FC n 은 n*8점 띄움, FE 줄 끝, FD 빈 줄, F9 한 프레임 쉼, F8 VRAM 칸 하나 되돌림(점 자리는 그대로), FB n 은 줄 무늬 칸 n 개, F7·F6 n 은 인자 하나, F5 끝.
CREDITS_SCRIPTS = 0x02FF3B
CREDITS_GLYPHS = 0x1EF539
CREDITS_TEXT = 'ABCDEFGHIJKLNOPQRSTUVXYZ921'
CREDITS_BAND = 'band'
CREDITS_BAND_TILE = 0x1EF5A8
CREDITS_PAIRS = {(0x1B, 0x1C): '&', (0x1E, 0x1F): 'M', (0x20, 0x21): 'W', (0x23, 0x24): '©'}
# 엔딩 「THE END」: BG3 2bpp 타일 41개를 03:B459 의 런 길이 압축(1F:D28B, 낮은·높은 바이트 줄기)에서 VRAM 워드 4000 에,
# CGRAM 0~11 을 03:A502 에서(0번 색은 0). 타일맵은 03:A40A 가 03:A478 의 바이트 128개(bit0-6 타일, bit7 좌우 반전)로
# 7E:A007 에 32x4 칸을 만들고 0F:EBCE 가 VRAM 1D80(12~15줄)에 올린다. 속성은 03:A4F8 의 [타일 한계][속성 위 바이트]
# 쌍에서 타일 번호보다 한계가 큰 첫 쌍. 그림은 글자가 있는 3~28칸만 쓴다.
THE_END_TILES = 0x03B459
THE_END_COLORS = 0x03A502
THE_END_CELLS = 0x03A478
THE_END_ATTRS = 0x03A4F8
THE_END_COLS = (3, 29)


def the_end_map(rom):
    """03:A40A. 4줄 × 26칸의 타일맵 낱말(타일 | 속성 << 8)."""
    words = []
    for i in range(128):
        b = rom.u8(THE_END_CELLS + i)
        t, k = b & 0x7F, 0
        while not t < rom.u8(THE_END_ATTRS + k * 2):
            k += 1
        words.append(t | ((0x40 if b & 0x80 else 0) | rom.u8(THE_END_ATTRS + k * 2 + 1)) << 8)
    return [words[r * 32 + THE_END_COLS[0]:r * 32 + THE_END_COLS[1]] for r in range(4)]


# 25:85D5: ルーラ 목적지의 맵 그룹 22개. 이름은 이름 표 0B(23:D5F3) 의 같은 순번.
RURA_GROUPS, RURA_COUNT, TOWN_NAMES = 0x2585D5, 22, 0x0B


def rgb(c):
    # 5비트 → 8비트는 MesenCE 화면과 같게 (v << 3) | (v >> 2).
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


def cgram_colors(cg):
    return [rgb(cg[i * 2] | cg[i * 2 + 1] << 8) for i in range(len(cg) // 2)]


def planar(t):
    """4bpp 타일 32바이트 → 8x8 색 번호."""
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1
             | (t[16 + y * 2] >> (7 - x) & 1) << 2 | (t[17 + y * 2] >> (7 - x) & 1) << 3
             for x in range(8)] for y in range(8)]


def tile_image(px, colors, flip_h=False, flip_v=False):
    """색 번호 8x8 → RGBA(0 번 색은 투명)."""
    img = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    p = img.load()
    for y in range(8):
        for x in range(8):
            v = px[7 - y if flip_v else y][7 - x if flip_h else x]
            if v:
                p[x, y] = colors[v] + (255,)
    return img


def scaled(img, scale):
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def sheet(cells, cols, cell_w, cell_h, labels=None, bg=(32, 32, 40), pad=1, label_h=0, below=False):
    """같은 크기 그림을 격자로. labels 를 주면 칸 위(below 면 아래)에 작은 글씨."""
    rows = (len(cells) + cols - 1) // cols
    W, H = cols * (cell_w + pad) + pad, rows * (cell_h + label_h + pad) + pad
    out = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(out)
    for i, c in enumerate(cells):
        x, y = pad + i % cols * (cell_w + pad), pad + i // cols * (cell_h + label_h + pad)
        if labels:
            d.text((x, y + (cell_h if below else 0)), labels[i], fill=(200, 200, 120))
        if c is not None:
            out.paste(c, (x, y + (0 if below else label_h)), c if c.mode == 'RGBA' else None)
    return out


# ---------------------------------------------------------------- 실내 맵

def map_ids(rom):
    """실내 맵 346개와 그룹 $50 이상 18개의 ($BC, $BD)."""
    ptr = [rom.u16(GROUP_TABLE + g * 2) for g in range(GROUPS)] + [GROUP_TABLE & 0xFFFF]
    out = [(g, b) for g in range(GROUPS) for b in range((ptr[g + 1] - ptr[g]) // 3)]
    return out + [(g, 0x50 + b) for g, n in HIGH_MAPS for b in range(n)]


class TileCache:
    """(CHR, 팔레트 줄, 반전) → 8x8 RGBA. 맵 하나의 팔레트 안에서만 쓴다."""

    def __init__(self, rom, high, colors, override=None):
        self.rom, self.high, self.colors, self.px, self.img = rom, high, colors, {}, {}
        for chr_id, raw in (override or {}).items():
            self.px[chr_id] = planar(raw)

    def get(self, chr_id, pal, fh, fv):
        k = (chr_id, pal, fh, fv)
        if k not in self.img:
            if chr_id not in self.px:
                self.px[chr_id] = chr_pixels(self.rom, chr_id, self.high)
            self.img[k] = tile_image(self.px[chr_id], self.colors[pal * 16:pal * 16 + 16], fh, fv)
        return self.img[k]


def palette_overrides(rom):
    """01:9771 표: [(BC, BD 또는 None, 플래그 번호, 마스크, 세트)]."""
    out, a = [], PALSET_FLAGS
    while rom.u8(a) != 0xFF:
        e = [rom.u8(a + i) for i in range(5)]
        out.append((e[0], None if e[1] == 0xFF else e[1], e[2], e[3], e[4]))
        a += 5
    return out


def set_cgram(rom, s, alt=False):
    """map_cgram 과 같되 팔레트 세트 번호를 바로 준다(10:DDCF)."""
    lst = 0x100000 | rom.u16(PALSET_LISTS + s * 4 + (2 if alt else 0))
    cg = bytearray(0x200)
    for r in range(7):
        o = lorom(PALETTES + (rom.u16(lst + r * 2) & 0x7FF) * 32)
        cg[0x20 + r * 32:0x40 + r * 32] = rom.d[o:o + 32]
    for r in range(7, 1, -1):
        if cg[r * 32] | cg[r * 32 + 1]:
            cg[0:2] = cg[r * 32:r * 32 + 2]
            break
    return bytes(cg)


def decode_map(rom, bc, bd, flags=False):
    """flags 면 이야기 플래그를 모두 켠 상태: 맵 위 물체는 열린 모양, 맵별 루틴의 셀 지우기도 켜진 쪽."""
    high = bc >= 0x50
    dec = Decoder(rom, SLOT, high)
    trace = []
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd), trace=trace)
    buf = bytearray(buf)
    apply_hook(rom, bc, bd, buf, w)
    hook_clears(rom, bc, bd, buf, flags)
    if bc < 0x50:
        dec.doors = apply_doors(rom, bc, bd, buf, w, h, opened=flags)
    dec.common = common_tiles(rom, bc, bd)
    blocks = sorted({args[0] for *_, op, args in trace if op == 'block'}
                    | ({(rom.u8(map_pointer(rom, bc, bd) + 7) & 7) << 8 | rom.u8(map_pointer(rom, bc, bd) + 8)}
                       if rom.u8(map_pointer(rom, bc, bd) + 7) & 0x80 else set()))
    return dec, w, h, buf, blocks


def common_tiles(rom, bc, bd):
    """04:8000 이 맵마다 BG 슬롯 001~0B3 에 올리는 공통 타일 {슬롯: 32바이트}."""
    from dq5sprite import split_tiles
    out = {}
    for slot, a, kind in COMMON_TILES:
        if slot == 0x09E and (bc, bd) == (0x53, 0x52):
            a = COMMON_TILES_5352
        if kind == 'rle':
            tiles, _ = split_tiles(rom, a, False)
        else:
            o = lorom(a)
            tiles = [rom.d[o + i * 32:o + i * 32 + 32] for i in range(6)]
        for i, t in enumerate(tiles):
            out[slot + i] = bytes(t)
    return out


def door_entries(rom):
    """01:D2FC 표: {(BC, BD): [[X, Y, 종류, 플래그, 끝 바이트]]}."""
    out, a, y, g, m = {}, DOOR_TABLE, 0, 0, 0
    while g < GROUPS:
        b = rom.u8(a + y)
        if b < 0x80:
            e = [rom.u8(a + y + i) for i in range(5)]
            y += 5
            out.setdefault((g, m), []).append(e)
            b = e[4]
        else:
            y += 1
        if b >= 0xC0:
            g, m = g + 1, 0
        elif b >= 0x80:
            m += 1
    return out


def door_shape(rom, kind):
    """닫힌 상태 그리기 루틴을 따라 읽어 [(dx, dy, 위층 타일 워드)]. STA [$00],Y 의 Y 가 5·0D·15·1D 면 같은 줄의 0~3번째 셀,
    JSR 01:EFED 는 다음 줄(코드 읽기를 기계로 옮긴 것)."""
    from kr_patch.sfc.dis65816 import decode
    from kr_patch.sfc.mapper import LoROM
    pc, m8, x8, tab, y, src, row, out = DOOR_ROUTINES.get(kind, 0x01F635), True, True, None, 0, None, 0, []
    for _ in range(HOOK_SCAN):
        op = rom.u8(pc)
        _, n, _, _ = decode(rom.d, pc, m8=m8, x8=x8, mapper=LoROM())
        nxt = (pc & 0xFF0000) | ((pc + n) & 0xFFFF)
        if op in (0xC2, 0xE2):
            v = rom.u8(pc + 1)
            if v & 0x10:
                x8 = op == 0xE2
            if v & 0x20:
                m8 = op == 0xE2
        elif op == 0xA2 and n == 3:
            tab = rom.u16(pc + 1)
        elif op == 0xA0:
            y = rom.u8(pc + 1) if n == 2 else rom.u16(pc + 1)
        elif op == 0xC8:
            y += 1
        elif op == 0x88:
            y -= 1
        elif op == 0xB1:
            src = y
        elif op == 0xB2:
            src = 0
        elif op == 0x97 and not m8 and y in (0x05, 0x0D, 0x15, 0x1D) and src is not None:
            out.append(((y - 5) // 8, row, rom.u16(0x010000 | (tab + src))))
        elif op == 0x20:
            target = rom.u16(pc + 1)
            if target == 0xEFED:
                row += 1
            elif target in DOOR_TABLE_SELECT:
                table, default = DOOR_TABLE_SELECT[target]
                tab = table.get(kind, default)
        elif op == 0x82:
            nxt = (pc & 0xFF0000) | ((pc + 3 + rom.u16(pc + 1)) & 0xFFFF)
        elif op == 0x60:
            break
        pc = nxt
    return out


def apply_doors(rom, bc, bd, buf, w, h, doors=None, opened=False):
    """01:D2FC 의 물체를 셀 위층(+5·+6)에 그린다. opened 면 열린 모양(01:F8AB). 그린 물체 [(X, Y, 종류)]."""
    placed = []
    for x, y, kind, _, _ in (doors if doors is not None else door_entries(rom)).get((bc, bd), []):
        placed.append((x, y, kind))
        if opened:
            open_door(rom, buf, w, bc, bd, x, y, kind)
            continue
        for dx, dy, word in door_shape(rom, kind):
            if x + dx < w and y + dy < h:
                o = ((y + dy) * w + x + dx) * 8
                buf[o + 5], buf[o + 6] = word & 0xFF, word >> 8
    return placed


class Mini65:
    """맵 위 물체의 열린 모양 루틴(01:F8AB 아래)만 셀 버퍼 위에서 돌리는 작은 65816 해석기. 그 루틴들이 쓰는 명령만 있다.
    7E:C000 이후를 셀 버퍼로, 직접 페이지를 따로 두고, 01:EFED(다음 줄)와 25:FA15(셀 주소)는 결과만 옮겼다."""
    def __init__(self, rom, buf, w, bc, bd):
        self.rom, self.buf, self.w = rom, buf, w
        self.dp = bytearray(0x100)
        self.bc, self.bd = bc, bd
        self.a = self.x = self.y = 0; self.m8 = self.x8 = True; self.z = False; self.c = False
        self.stack = []
    def rd(self, addr, n):
        if 0x7EC000 <= addr < 0x800000:
            o = addr - 0x7EC000
            return sum(self.buf[o + i] << (8 * i) for i in range(n) if o + i < len(self.buf))
        if addr < 0x100:
            return sum(self.dp[(addr + i) & 0xFF] << (8 * i) for i in range(n))
        return sum(self.rom.u8(addr + i) << (8 * i) for i in range(n))
    def wr(self, addr, v, n):
        if 0x7EC000 <= addr < 0x800000:
            o = addr - 0x7EC000
            for i in range(n):
                if o + i < len(self.buf): self.buf[o + i] = (v >> (8 * i)) & 0xFF
        else:
            for i in range(n): self.dp[(addr + i) & 0xFF] = (v >> (8 * i)) & 0xFF
    def ptr(self, d): return self.dp[d] | self.dp[d+1] << 8 | self.dp[d+2] << 16
    def setz(self, v, n): self.z = (v & ((1 << (8*n)) - 1)) == 0
    def run(self, pc, limit=3000):
        from kr_patch.sfc.dis65816 import decode
        from kr_patch.sfc.mapper import LoROM
        rom = self.rom
        for _ in range(limit):
            op = rom.u8(pc); _, n, _, _ = decode(rom.d, pc, m8=self.m8, x8=self.x8, mapper=LoROM())
            na = 1 if self.m8 else 2; nx = 1 if self.x8 else 2
            nxt = (pc & 0xFF0000) | ((pc + n) & 0xFFFF)
            imm8 = rom.u8(pc + 1); imm = rom.u8(pc+1) if n == 2 else rom.u16(pc+1)
            if op == 0xC2 or op == 0xE2:
                if imm8 & 0x20: self.m8 = op == 0xE2
                if imm8 & 0x10: self.x8 = op == 0xE2
                if self.m8: self.a &= 0xFF  # keep B separately ignored
            elif op == 0xA6: self.x = self.rd(imm8, nx); self.setz(self.x, nx)
            elif op == 0xA4: self.y = self.rd(imm8, nx); self.setz(self.y, nx)
            elif op == 0xA5: self.a = self.rd(imm8, na); self.setz(self.a, na)
            elif op == 0x85: self.wr(imm8, self.a, na)
            elif op == 0x86: self.wr(imm8, self.x, nx)
            elif op == 0x84: self.wr(imm8, self.y, nx)
            elif op == 0x64: self.wr(imm8, 0, na)
            elif op == 0xA2: self.x = imm; self.setz(self.x, nx)
            elif op == 0xA0: self.y = imm; self.setz(self.y, nx)
            elif op == 0xA9: self.a = imm; self.setz(self.a, na)
            elif op == 0xCA: self.x = (self.x - 1) & 0xFFFF; self.setz(self.x, nx)
            elif op == 0x88: self.y = (self.y - 1) & 0xFFFF; self.setz(self.y, nx)
            elif op == 0xE8: self.x = (self.x + 1) & 0xFFFF; self.setz(self.x, nx)
            elif op == 0xC8: self.y = (self.y + 1) & 0xFFFF; self.setz(self.y, nx)
            elif op == 0xB7: self.a = self.rd(self.ptr(imm8) + self.y, na); self.setz(self.a, na)
            elif op == 0x97: self.wr(self.ptr(imm8) + self.y, self.a, na)
            elif op == 0xB2: self.a = self.rd((0x01 << 16) | (self.ptr(imm8) & 0xFFFF), na); self.setz(self.a, na)
            elif op == 0xB1: self.a = self.rd((0x01 << 16) | ((self.ptr(imm8) + self.y) & 0xFFFF), na); self.setz(self.a, na)
            elif op == 0x29: self.a &= imm; self.setz(self.a, na)
            elif op == 0x09: self.a |= imm; self.setz(self.a, na)
            elif op == 0x05: self.a |= self.rd(imm8, na); self.setz(self.a, na)
            elif op == 0x25: self.a &= self.rd(imm8, na); self.setz(self.a, na)
            elif op == 0x3A: self.a = (self.a - 1) & ((1 << (8*na))-1); self.setz(self.a, na)
            elif op == 0x1A: self.a = (self.a + 1) & ((1 << (8*na))-1); self.setz(self.a, na)
            elif op == 0x0A: self.c = bool(self.a >> (8*na-1) & 1); self.a = (self.a << 1) & ((1 << (8*na))-1); self.setz(self.a, na)
            elif op == 0x4A: self.c = bool(self.a & 1); self.a >>= 1; self.setz(self.a, na)
            elif op == 0x18: self.c = False
            elif op == 0x38: self.c = True
            elif op == 0x69: s = self.a + imm + self.c; self.c = s >= (1 << (8*na)); self.a = s & ((1 << (8*na))-1); self.setz(self.a, na)
            elif op in (0xC9, 0xE0, 0xC0):
                reg = self.a if op == 0xC9 else self.x if op == 0xE0 else self.y
                nn = na if op == 0xC9 else nx
                self.z = (reg & ((1<<(8*nn))-1)) == imm; self.c = (reg & ((1<<(8*nn))-1)) >= imm
            elif op == 0xC6: v = (self.rd(imm8, na) - 1) & 0xFFFF; self.wr(imm8, v, na); self.setz(v, na)
            elif op == 0x48: self.stack.append(self.a)
            elif op == 0x68: self.a = self.stack.pop(); self.setz(self.a, na)
            elif op == 0xDA: self.stack.append(self.x)
            elif op == 0xFA: self.x = self.stack.pop()
            elif op == 0x5A: self.stack.append(self.y)
            elif op == 0x7A: self.y = self.stack.pop()
            elif op == 0x08: self.stack.append((self.m8, self.x8))
            elif op == 0x28: self.m8, self.x8 = self.stack.pop()
            elif op == 0xAA: self.x = self.a
            elif op == 0x8A: self.a = self.x
            elif op == 0x98: self.a = self.y
            elif op == 0xA8: self.y = self.a
            elif op == 0xD0:
                if not self.z: nxt = (pc & 0xFF0000) | ((pc + 2 + (imm8 - 256 if imm8 & 0x80 else imm8)) & 0xFFFF)
            elif op == 0xF0:
                if self.z: nxt = (pc & 0xFF0000) | ((pc + 2 + (imm8 - 256 if imm8 & 0x80 else imm8)) & 0xFFFF)
            elif op == 0x90:
                if not self.c: nxt = (pc & 0xFF0000) | ((pc + 2 + (imm8 - 256 if imm8 & 0x80 else imm8)) & 0xFFFF)
            elif op == 0xB0:
                if self.c: nxt = (pc & 0xFF0000) | ((pc + 2 + (imm8 - 256 if imm8 & 0x80 else imm8)) & 0xFFFF)
            elif op == 0x80: nxt = (pc & 0xFF0000) | ((pc + 2 + (imm8 - 256 if imm8 & 0x80 else imm8)) & 0xFFFF)
            elif op == 0x82: nxt = (pc & 0xFF0000) | ((pc + 3 + rom.u16(pc+1)) & 0xFFFF)
            elif op == 0x22:
                t = rom.u24(pc + 1)
                if t == 0x25FA15:
                    a = 0xC000 + ((self.y & 0xFF) * self.w + (self.x & 0xFF)) * 8
                    a += 0x7E0000
                    self.dp[0], self.dp[1], self.dp[2] = a & 0xFF, (a >> 8) & 0xFF, a >> 16
                else: raise RuntimeError(f'JSL {t:06X} at {pc:06X}')
            elif op == 0x20:
                t = rom.u16(pc + 1)
                if t == 0xEFED:
                    a = (self.ptr(0) + self.w * 8) & 0xFFFFFF
                    self.dp[0], self.dp[1], self.dp[2] = a & 0xFF, (a >> 8) & 0xFF, a >> 16
                else:
                    self.stack.append(('ret', nxt)); nxt = (pc & 0xFF0000) | t
            elif op == 0x60:
                r = self.stack.pop()
                if r == 'top': return
                nxt = r[1]
            else:
                raise RuntimeError(f'op {op:02X} at {pc:06X}')
            if op == 0xA6 and imm8 == 0xBC: self.x = self.bc
            if op == 0xA6 and imm8 == 0xBD: self.x = self.bd
            pc = nxt
        raise RuntimeError('limit')


def open_door(rom, buf, w, bc, bd, x, y, kind):
    """01:F8AB: 플래그가 켜진(열린) 물체를 그린다. 종류 44·43·49·48 은 아무것도 그리지 않음."""
    m = Mini65(rom, buf, w, bc, bd)
    m.dp[0x0B], m.dp[0x0C], m.dp[0x08] = x, y, 1
    m.stack = ['top', kind]
    m.run(0x01F8AB)


def hook_clears(rom, bc, bd, buf, flags=False):
    """맵별 루틴(15:F907)이 `LDA #$7E / PHA / PLB` 뒤 STZ abs·TRB abs 로 셀 버퍼를 지우는 것을 buf 에 반영한다
    (dq5exit.apply_hook 은 LDA #즉값 / STA 만 본다). 35/03 의 1E:F39F 는 플래그(BRK #$0B 08 30)가 꺼져 있으면
    보물상자 하나의 위층을 지우고 가구 비트를 내린다. 플래그는 모두 꺼진 것으로 본다: BRK #$0B(00:93BA) 바로 뒤의 BEQ 는 건너뛰고
    BNE 는 지나간다(flags 면 반대로 모두 켜진 것으로). 그 밖의 분기는 따지지 않고 처음 RTL 까지 순서대로 읽는다."""
    from dq5exit import HOOK_NONE, map_hook
    from kr_patch.sfc.dis65816 import decode
    from kr_patch.sfc.mapper import LoROM
    pc = map_hook(rom, bc, bd)
    if pc == HOOK_NONE:
        return 0
    m8 = x8 = True
    imm = db = pushed = None
    n_written, after_flag = 0, False
    for _ in range(HOOK_SCAN):
        op = rom.u8(pc)
        _, n, _, _ = decode(rom.d, pc, m8=m8, x8=x8, mapper=LoROM())
        if after_flag and op == (0xD0 if flags else 0xF0):
            off = rom.u8(pc + 1)
            pc = (pc & 0xFF0000) | ((pc + 2 + (off - 256 if off & 0x80 else off)) & 0xFFFF)
            after_flag = False
            continue
        after_flag = False
        if op in (0xC2, 0xE2):
            v = rom.u8(pc + 1)
            if v & 0x20:
                m8 = op == 0xE2
            if v & 0x10:
                x8 = op == 0xE2
        elif op == 0xA9:
            imm = rom.u8(pc + 1) if m8 else rom.u16(pc + 1)
        elif op == 0x48:
            pushed = imm
        elif op == 0xAB:
            db = pushed
        elif op in (0x9C, 0x1C) and db == 0x7E:
            a = rom.u16(pc + 1) - 0xC000
            for k in range(1 if m8 else 2):
                if 0 <= a + k < len(buf):
                    buf[a + k] = 0 if op == 0x9C else buf[a + k] & ~((imm >> (8 * k)) & 0xFF) & 0xFF
                    n_written += 1
        elif op == 0x00:
            if rom.u8(pc + 1) != 0x0B:
                break
            n = 4
            after_flag = True
        elif op == 0x22:
            db = None
        if op in (0x6B, 0x60, 0x40):
            break
        pc = (pc & 0xFF0000) | ((pc + n) & 0xFFFF)
    return n_written


def anim_override(rom, bc, bd, counter):
    """카운터 7E:1ECE = counter 인 순간의 움직이는 타일 {CHR 번호: 32바이트}(dq5anim). 종류 14(걸을 때만)는 그대로."""
    import dq5anim
    high = bc >= 0x50
    moving, _ = dq5anim.map_types(rom, bc, bd)
    out = {}
    for t in moving:
        k = dq5anim.kind(rom, t)
        chrs = dq5anim.block_chrs(rom, k['blocks'], high)
        if t < 6:
            raw = dq5anim.frame_bytes(rom, t, dq5anim.frame_index(rom, t, counter))
            for i, c in enumerate(chrs[:k['tiles']]):
                out[c] = raw[i * 32:i * 32 + 32]
        elif t == 7:
            tiles = b''.join(dq5anim.chr_raw(rom, c, high) for c in chrs[:k['tiles']])
            for n in range(counter + 1):
                if n % k['period'] == 0 and n:
                    tiles = dq5anim.slide7(tiles, n)
            for i, c in enumerate(chrs[:k['tiles']]):
                out[c] = tiles[i * 32:i * 32 + 32]
        elif t != 14:
            shift = (counter // k['period']) % 8
            for c in chrs[:k['tiles']]:
                out[c] = dq5anim.roll(dq5anim.chr_raw(rom, c, high), shift)
    return out


def draw_cells(rom, dec, w, h, buf, cgram, layers=(2, 5), override=None):
    """override = {CHR 번호: 32바이트} 면 그 CHR 을 대신 그린다(움직이는 타일의 한 순간)."""
    colors = cgram_colors(cgram)
    slot_chr = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    tc = TileCache(rom, dec.high, colors, override)
    img = Image.new('RGB', (w * 8, h * 8), colors[0])
    for layer in layers:
        for cell in range(w * h):
            o = cell * 8 + layer
            word = buf[o] | buf[o + 1] << 8
            if not word:
                continue
            chr_id = slot_chr.get(word & 0x3FF)
            if chr_id is not None:
                t = tc.get(chr_id, (word >> 10) & 7, bool(word & 0x4000), bool(word & 0x8000))
            elif word & 0x3FF in getattr(dec, 'common', {}):
                pal = (word >> 10) & 7
                t = tile_image(planar(dec.common[word & 0x3FF]), colors[pal * 16:pal * 16 + 16],
                               bool(word & 0x4000), bool(word & 0x8000))
            else:
                continue
            img.paste(t, (cell % w * 8, cell // w * 8), t)
    return img


def block_image(rom, dec, n, colors, tc):
    """블록 하나를 그 자리 그대로(위층 줄도 한 그림에)."""
    h, w, upper, attr, rows = dec.load_block(n)
    slot_chr = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    img = Image.new('RGBA', (w * 8, h * 8), colors[0] + (255,))
    for r, row in enumerate(rows):
        for c, (_, word) in enumerate(row):
            t = tc.get(slot_chr[word & 0x3FF], (word >> 10) & 7, bool(word & 0x4000), bool(word & 0x8000))
            img.paste(t, (c * 8, r * 8), t)
    return img


# ---------------------------------------------------------------- 필드

def field_time_sets(rom):
    """세계 0 의 2·3번 줄 8벌(01:A189 포인터 표 순서): [(포인터, [그 벌을 고르는 $075E 하한…])]. 01:A132."""
    entries = [(rom.u16(FIELD_TIME + i * 3), rom.u8(FIELD_TIME + i * 3 + 2)) for i in range(10)]
    ptrs = [rom.u16(FIELD_TIME_PTRS + i * 2) for i in range(8)]
    return [(p, sorted(lo for lo, idx in entries if idx == i * 2)) for i, p in enumerate(ptrs)]


def field_cgram(rom, world, rows23=None, wave=0, base=(0x01, 0x00)):
    """필드 CGRAM 을 롬에서. 1·5~7번 줄은 마지막 맵(base)의 세트, 2·3번 줄은 시간대·세계, 4번 줄은 10:EC48(+물결)."""
    cg = bytearray(map_cgram(rom, *base))
    src = rows23 if world == 0 else FIELD_WORLD_ROWS[world]
    o = lorom(0x010000 | src)
    for r, k in ((2, 0), (3, 30)):
        cg[r * 32 + 2:r * 32 + 32] = rom.d[o + k:o + k + 30]
    o4 = lorom(FIELD_ROW4)
    cg[4 * 32:5 * 32] = rom.d[o4:o4 + 32]
    if world == 0:
        w = lorom(FIELD_WAVE + wave * 6)
        cg[4 * 32 + 2:4 * 32 + 8] = rom.d[w:w + 6]
    return bytes(cg)


def field_tiles(rom):
    """필드 타일 512개의 8x8 색 번호. 팔레트는 층마다 다르므로(00:BBAC) 칠하는 것은 부르는 쪽."""
    from dq5field import field_chr
    chrs = field_chr(rom)
    return [planar(chrs[i * 32:i * 32 + 32]) for i in range(512)]


def field_block_images(rom, cgram, tiles, layers=('lower', 'upper')):
    from dq5field import BLOCK_LOWER, BLOCK_UPPER, block_tiles, tile_word
    colors = cgram_colors(cgram)
    cache = {}
    out = []
    for m in range(512):
        img = Image.new('RGBA', (16, 16), colors[0] + (255,))
        for upper, table in ((False, BLOCK_LOWER), (True, BLOCK_UPPER)):
            if ('upper' if upper else 'lower') not in layers:
                continue
            for q, t in enumerate(block_tiles(rom, table, m)):
                word = tile_word(rom, t, upper)
                k = (word & 0x3FF, (word >> 10) & 7)
                if k not in cache:
                    cache[k] = tile_image(tiles[k[0]], colors[k[1] * 16:k[1] * 16 + 16])
                img.paste(cache[k], ((q & 1) * 8, (q >> 1) * 8), cache[k])
        out.append(img)
    return out


def world_image(rom, world, blocks):
    from dq5field import WORLDS, block_number, rle
    src_w, src_e = WORLDS[world]
    wmap, _ = rle(rom, src_w)
    hib, _ = rle(rom, src_e)
    size = 256 if world == 0 else 128
    img = Image.new('RGB', (size * 16, size * 16))
    for by in range(size):
        for bx in range(size):
            img.paste(blocks[block_number(wmap, hib, bx, by)], (bx * 16, by * 16))
    return img


# ---------------------------------------------------------------- 몬스터·폰트

# ---------------------------------------------------------------- 창·움직이는 타일

def ui_tiles(rom):
    """BG3 타일 0~149 의 2bpp 바이트(VRAM 워드 $1000 또는 $4000 부터 올라가는 그대로). 타일 0 은 0."""
    out = bytearray(16)
    o = lorom(UI_TILES)
    for t in range(UI_1BPP):
        for r in range(8):
            out += bytes([rom.d[o + t * 8 + r], 0xFF])
    o += UI_1BPP * 8
    for t in range(UI_2BPP):
        for r in range(8):
            out += bytes([rom.d[o + t * 16 + r], rom.d[o + t * 16 + 8 + r]])
    return bytes(out)


# 화면에서 본 창 타일맵(배 선실 덤프의 BG3): 8C 모서리, 8D 위 테두리, 8E 옆 테두리, 8F·90 가로줄, 01 빈칸. 40 = 좌우, 80 = 상하 반전.
UI_SAMPLE = (
    (0x08C, 0x08D, 0x08D, 0x08D, 0x08D, 0x08D, 0x08D, 0x48C),
    (0x08E, 0x010, 0x010, 0x010, 0x010, 0x001, 0x001, 0x48E),
    (0x08F, 0x090, 0x090, 0x090, 0x090, 0x090, 0x090, 0x48F),
    (0x08E, 0x00C, 0x001, 0x004, 0x006, 0x001, 0x001, 0x48E),
    (0x08E, 0x00D, 0x001, 0x001, 0x002, 0x001, 0x001, 0x48E),
    (0x08E, 0x087, 0x085, 0x001, 0x003, 0x001, 0x001, 0x48E),
    (0x88C, 0x88D, 0x88D, 0x88D, 0x88D, 0x88D, 0x88D, 0xC8C),
)


def field_anim_sets(rom):
    """타일 454~459 의 8벌: [벌][타일] = 32바이트."""
    from dq5field import rle
    data, _ = rle(rom, FIELD_ANIM)
    n = FIELD_ANIM_COUNT * 32
    return [[data[k * n + t * 32:k * n + t * 32 + 32] for t in range(FIELD_ANIM_COUNT)] for k in range(FIELD_ANIM_SETS)]


def rotate_pair(a, b, k):
    """01:C790 이 하는 일: 이웃한 두 타일의 줄마다(평면마다) 16비트를 k 픽셀 오른쪽으로 돌린다. 세계 1·2 는 왼쪽."""
    oa, ob = bytearray(32), bytearray(32)
    for i in range(32):
        v = a[i] << 8 | b[i]
        v = (v >> k | v << (16 - k)) & 0xFFFF
        oa[i], ob[i] = v >> 8, v & 0xFF
    return bytes(oa), bytes(ob)


# ---------------------------------------------------------------- 덤프한 VRAM 에서 BG 그리기

def read_ppu(path):
    """dq5gfxdump.lua 의 .ppu.txt → {키: 값}."""
    out = {}
    for line in open(path):
        k, _, v = line.strip().partition('=')
        out[k] = int(v) if v.lstrip('-').isdigit() else v
    return out


def chr_2bpp(t):
    return [[(t[y * 2] >> (7 - x) & 1) | (t[y * 2 + 1] >> (7 - x) & 1) << 1 for x in range(8)] for y in range(8)]


def bg_layer(vram, cgram, ppu, layer, bpp=None, transparent=False):
    """BG 하나의 타일맵 전체(32x32·64x32·32x64·64x64 칸)를 덤프한 VRAM·CGRAM 으로 그린다. 스크롤은 무시한다.
    bpp 를 안 주면 모드 1 기준(BG1·BG2 4bpp, BG3 2bpp)."""
    pre = f'ppu.layers[{layer}].'
    tm, cb = ppu[pre + 'tilemapAddress'] * 2, ppu[pre + 'chrAddress'] * 2
    dw, dh = ppu[pre + 'doubleWidth'] == 'true', ppu[pre + 'doubleHeight'] == 'true'
    bpp = bpp or (2 if layer == 2 else 4)
    colors = cgram_colors(cgram)
    W, H = 64 if dw else 32, 64 if dh else 32
    img = Image.new('RGBA', (W * 8, H * 8), (0, 0, 0, 0) if transparent else colors[0] + (255,))
    cache = {}
    for ty in range(H):
        for tx in range(W):
            screen = (tx >> 5) + ((ty >> 5) << (1 if dw else 0))
            o = (tm + screen * 0x800 + ((ty & 31) * 32 + (tx & 31)) * 2) & 0xFFFF
            word = vram[o] | vram[o + 1] << 8
            k = word & 0xDFFF
            if k not in cache:
                tile = word & 0x3FF
                a = (cb + tile * 8 * bpp) & 0xFFFF
                px = planar(vram[a:a + 32]) if bpp == 4 else chr_2bpp(vram[a:a + 16])
                pal = (word >> 10) & 7
                cache[k] = tile_image(px, colors[pal * (1 << bpp):pal * (1 << bpp) + (1 << bpp)],
                                      bool(word & 0x4000), bool(word & 0x8000))
            img.paste(cache[k], (tx * 8, ty * 8), cache[k])
    return img


def dump_screen(prefix):
    """dq5gfxdump.lua 덤프(prefix = 경로/fNNNNN)로 BG2 위에 BG1 을 겹치고 BG1 스크롤만큼 자른 256x224 화면."""
    vram, cgram = open(prefix + '.vram', 'rb').read(), open(prefix + '.cgram', 'rb').read()
    ppu = read_ppu(prefix + '.ppu.txt')
    comp = bg_layer(vram, cgram, ppu, 1)
    hi = bg_layer(vram, cgram, ppu, 0, transparent=True)
    comp.paste(hi, (0, 0), hi)
    W, H = comp.size
    hs, vs = ppu['ppu.layers[0].hscroll'] % W, ppu['ppu.layers[0].vscroll'] % H
    tiled = Image.new('RGB', (W * 2, H * 2))
    for x in (0, W):
        for y in (0, H):
            tiled.paste(comp, (x, y))
    return tiled.crop((hs, vs, hs + 256, vs + 224))


def match_screen(full, scr):
    """맵 그림 full 에서 화면 scr 이 가장 잘 맞는 자리 (x, y, 같은 픽셀, 맵 안 픽셀). 맵 밖 칸은 세지 않는다."""
    from PIL import ImageChops
    W, H = full.size
    out = (1, 2, 3)
    pad = Image.new('RGB', (W + 512, H + 448), out)
    pad.paste(full.convert('RGB'), (256, 224))

    def score(ox, oy):
        d = ImageChops.difference(pad.crop((ox, oy, ox + 256, oy + 224)), scr).convert('L')
        return d.histogram()[0]

    _, cx, cy = max((score(x, y), x, y) for y in range(0, H + 225, 8) for x in range(0, W + 257, 8))
    _, x, y = max((score(x, y), x, y) for y in range(max(0, cy - 8), cy + 9) for x in range(max(0, cx - 8), cx + 9))
    a, b = pad.crop((x, y, x + 256, y + 224)).load(), scr.load()
    inside = [a[i, j] == b[i, j] for j in range(224) for i in range(256) if a[i, j] != out]
    return x - 256, y - 224, sum(inside), len(inside)


def check(rom, prefix, bc, bd, pset=None, night=False):
    """덤프한 화면과 맵 그림 비교. 결과 (x, y, 같은 픽셀, 맵 안 픽셀)."""
    dec, w, h, buf, _ = decode_map(rom, bc, bd)
    cg = set_cgram(rom, pset, night) if pset is not None else map_cgram(rom, bc, bd, night)
    return match_screen(draw_cells(rom, dec, w, h, buf, cg), dump_screen(prefix))


# ---------------------------------------------------------------- 내보내기

class Out:
    """그림을 ROOT 아래 분류 폴더에 쓰고, 분류 폴더마다 index.json·SOURCE.txt 를 남긴다."""

    def __init__(self, root, rom_sha=''):
        self.root, self.items, self.rom_sha = root, [], rom_sha
        self.index = {}  # 분류 폴더 → index.json 내용(기본은 항목 목록)

    def save(self, img, rel, cat, title, group='', **meta):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path)
        self.items.append({'cat': cat, 'group': group, 'title': title, 'path': rel,
                           'w': img.width, 'h': img.height, **meta})

    def add(self, rel, cat, title, group='', **meta):
        self.items.append({'cat': cat, 'group': group, 'title': title, 'path': rel, **meta})

    def finish(self, command):
        dirs = {}
        for it in self.items:
            d = os.path.dirname(it['path'])
            top = d if d.startswith('gfx/') else d.split('/')[0]
            if top.startswith('gfx/blocks'):
                top = 'gfx/blocks'
            dirs.setdefault(top, []).append(dict(it, path=os.path.relpath(it['path'], top)))
        for top, items in dirs.items():
            folder = os.path.join(self.root, top)
            with open(os.path.join(folder, 'index.json'), 'w') as f:
                json.dump(self.index.get(top, items), f, ensure_ascii=False, indent=0)
            with open(os.path.join(folder, 'SOURCE.txt'), 'w') as f:
                f.write(source_text(command, self.rom_sha))


def source_text(command, rom_sha):
    try:
        commit = subprocess.run(['git', '-C', os.path.dirname(os.path.abspath(__file__)), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = '알 수 없음'
    return (f'sfc-dq4 커밋: {commit}\n명령: {command}\n'
            f'롬: SFC 「ドラゴンクエストV」 일본판, SHA-1 {rom_sha}\n')


def group_names(rom):
    """ルーラ 목적지 목록 25:85D5 의 맵 그룹 22개와 이름 표 0B(마을 이름)를 짝지은 {그룹: 이름}.
    그룹마다 「ここは ○○」 대사가 이 이름과 맞는다(01 ラインハット, 1A アルカパ, 21 サンタローズ 등)."""
    from dq5text import string, string_codes, text
    return {rom.u8(RURA_GROUPS + i): text(string_codes(rom, string(rom, TOWN_NAMES, i))) for i in range(RURA_COUNT)}


def map_stem(bc, bd, names):
    name = names.get(bc) if bc < 0x50 else None
    return f'{bc:02X}-{bd:02X}' + (f'-{name}' if name else '')


def map_marks(rom, bc, bd, buf, w, h):
    """주석판에 그릴 것: 출구 셀, 인물(낮 기본 목록), 보물상자, タンス·ツボ·タル, 발밑."""
    from dq5chest import chest_maps, chests, foot_entries, search_entries
    from dq5exit import exit_cells
    marks = {'exits': exit_cells(buf, w, h, exit_attrs(rom)), 'npcs': [], 'chests': [], 'search': [], 'foot': []}
    if bc < 0x50:
        from dq5npc import map_entries, parse
        for k, (a, _) in enumerate(map_entries(rom, bc, bd)):
            f = parse(rom, a)
            if f:
                marks['npcs'].append((k, f['x'] & 0x7F, f['y'] & 0x7F, f['gfx'], f['talk']))
    for cbc, cbd, start, _ in chest_maps(rom):
        if (cbc, cbd) == (bc, bd):
            marks['chests'] = [(n, x, y) for n, (x, y), _ in chests(rom, bc, bd, start)]
    marks['search'] = [(x, y) for sbc, sbd, x, y, *_ in search_entries(rom) if (sbc, sbd) == (bc, bd)]
    marks['foot'] = [(x, y) for sbc, sbd, x, y, *_ in foot_entries(rom) if (sbc, sbd) == (bc, bd)]
    return marks


def annotate(base, marks):
    """노랑 인물(번호, 왼쪽 칸 기준 16x16), 하늘색 출구, 빨강 T 보물상자, 분홍 S タンス·ツボ·タル, 분홍 F 발밑,
    주황 D 맵 위 물체(01:D2FC, 닫힌 문 등. 왼쪽 위 칸에 종류 번호)."""
    img = base.convert('RGB')
    d = ImageDraw.Draw(img)
    for x, y, kind in marks.get('doors', []):
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 150, 0))
        d.text((x * 8 + 1, y * 8 - 2), f'D{kind:02X}', fill=(255, 150, 0))
    for x, y in marks['exits']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(0, 200, 255))
    for x, y in marks['search']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 120, 200))
        d.text((x * 8 + 1, y * 8 - 2), 'S', fill=(255, 120, 200))
    for x, y in marks['foot']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 120, 200))
        d.text((x * 8 + 1, y * 8 - 2), 'F', fill=(255, 120, 200))
    for _, x, y in marks['chests']:
        d.rectangle((x * 8, y * 8, x * 8 + 7, y * 8 + 7), outline=(255, 40, 40))
        d.text((x * 8 + 1, y * 8 - 2), 'T', fill=(255, 40, 40))
    for k, x, y, _, _ in marks['npcs']:
        d.rectangle((x * 8, y * 8, x * 8 + 15, y * 8 + 15), outline=(255, 230, 0))
        d.text((x * 8 + 1, y * 8 + 3), f'{k}', fill=(255, 230, 0))
    return img


def export_maps(rom, out, only=None):
    names = group_names(rom)
    ids = map_ids(rom)
    if only:
        ids = [m for m in ids if m in only]
    for bc, bd in ids:
        stem = map_stem(bc, bd, names)
        dec, w, h, buf, blocks = decode_map(rom, bc, bd)
        marks = map_marks(rom, bc, bd, buf, w, h)
        marks['doors'] = getattr(dec, 'doors', [])
        meta = dict(map=f'{bc:02X}/{bd:02X}', name=names.get(bc, '') if bc < 0x50 else '', stem=stem,
                    size=f'{w}x{h}', addr=f'{map_pointer(rom, bc, bd):06X}', blocks=len(blocks), chrs=len(dec.chr_map),
                    npcs=len(marks['npcs']), exits=len(marks['exits']), chests=len(marks['chests']),
                    doors=len(marks['doors']))
        title = f'{bc:02X}/{bd:02X}' + (f' {meta["name"]}' if meta['name'] else '')
        group = f'그룹 {bc:02X}'
        day_cg = map_cgram(rom, bc, bd)
        day = draw_cells(rom, dec, w, h, buf, day_cg)
        out.save(day, f'maps/{stem}.png', 'maps', title, group, variant='낮', **meta)
        out.save(annotate(day, marks), f'maps/{stem}-annot.png', 'maps', title, group, variant='주석', **meta,
                 annot={k: v for k, v in marks.items()})
        night_cg = map_cgram(rom, bc, bd, alt=True)
        if night_cg != day_cg:
            out.save(draw_cells(rom, dec, w, h, buf, night_cg), f'maps/{stem}-night.png', 'maps', title, group,
                     variant='밤', **meta)
        for obc, obd, flag, mask, pset in palette_overrides(rom):
            if obc == bc and obd in (None, bd):
                cond = f'7E:{0x2190 + (flag & 0x7F):04X} & {mask:02X} {"= 0" if flag & 0x80 else "≠ 0"}'
                for alt in (False, True):
                    if alt and set_cgram(rom, pset, True) == set_cgram(rom, pset):
                        continue
                    out.save(draw_cells(rom, dec, w, h, buf, set_cgram(rom, pset, alt)),
                             f'maps/{stem}-set{pset:02X}{"-night" if alt else ""}.png', 'maps', title, group,
                             variant=f'세트 {pset:02X}' + (' 밤' if alt else ''), **meta,
                             note=f'{cond} 이면 01:9771 이 바꾸는 팔레트')
                break
        fdec, _, _, fbuf, _ = decode_map(rom, bc, bd, flags=True)
        if fbuf != buf:
            out.save(draw_cells(rom, fdec, w, h, fbuf, day_cg), f'maps/{stem}-flags.png', 'maps', title, group,
                     variant='플래그 켬', **meta, note='이야기 플래그를 모두 켠 상태: 문이 열리고(01:F8AB) 맵별 루틴의 셀 지우기도 켜진 쪽')
        colors = cgram_colors(day_cg)
        tc = TileCache(rom, dec.high, colors)
        imgs = [block_image(rom, dec, n, colors, tc) for n in blocks]
        cw = max(20, max(i.width for i in imgs))
        ch = max(i.height for i in imgs)
        out.save(sheet(imgs, max(1, min(16, 512 // (cw + 1))), cw, ch, [f'{n:03X}' for n in blocks], label_h=10,
                       below=True),
                 f'gfx/blocks/maps/{stem}.png', 'blocks', title, group, variant='블록', **meta)
        print(f'map {bc:02X}/{bd:02X} {w}x{h} blocks {len(blocks)}')


def export_chr(rom, out):
    """CHR 뱅크마다 1,024개(32개씩 32줄, 2배). -color 는 CHR 팔레트 번호대로 02/06(51/50) 낮 팔레트, -gray 는 색 번호."""
    gray = [(0, 0, 0)] + [(v * 17, v * 17, v * 17) for v in range(1, 16)]
    for high, base, pal_table, cg_map, count in ((False, 0x13, CHR_PALETTE, (0x02, 0x06), 0x1000),
                                                 (True, 0x1F, HIGH_CHR_PALETTE, (0x51, 0x50), 0x200)):
        colors = cgram_colors(map_cgram(rom, *cg_map))
        tc = TileCache(rom, high, colors)
        for part in range(0, count, 0x400):
            col, gr = [], []
            for chr_id in range(part, min(count, part + 0x400)):
                nib = rom.u8(pal_table + (chr_id >> 1))
                pal = ((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4
                col.append(scaled(tc.get(chr_id, (pal >> 2) & 7, False, False), 2))
                gr.append(scaled(tile_image(chr_pixels(rom, chr_id, high), gray), 2))
            bank = base + (part >> 10)
            for img, kind in ((col, 'color'), (gr, 'gray')):
                out.save(sheet(img, 32, 16, 16, pad=0, bg=(0, 0, 0)), f'gfx/blocks/chr{bank:02X}-{kind}.png', 'chr',
                         f'CHR {bank:02X}:8000 ({kind})', 'CHR', bank=f'{bank:02X}',
                         first=f'{part:03X}', palette=f'{cg_map[0]:02X}/{cg_map[1]:02X} 낮' if kind == 'color' else '색 번호')
    print('chr')


def export_field(rom, out):
    from dq5field import entrances, tile_word
    names = group_names(rom)
    tiles = field_tiles(rom)
    ents = entrances(rom)
    sets = field_time_sets(rom)
    day = next(p for p, los in sets if 2 in los)
    night = next(p for p, los in sets if 0xF2 in los)
    blocks_by = {}
    for ptr, los in sets:
        blocks = field_block_images(rom, field_cgram(rom, 0, ptr), tiles)
        blocks_by[ptr] = blocks
        stem = 'field0' if ptr == day else 'field0-night' if ptr == night else f'field0-{ptr:04X}'
        when = ', '.join(f'{v:04X}' for v in los) or '없음(시간대 표가 고르지 않음)'
        out.save(world_image(rom, 0, blocks), f'field/{stem}.png', 'field', '세계 0', '세계 지도',
                 variant='낮' if ptr == day else '밤' if ptr == night else f'01:{ptr:04X}', palette=f'01:{ptr:04X}',
                 note=f'$075E 하한 {when}')
    worlds = {0: blocks_by[day]}
    for world in (1, 2):
        worlds[world] = field_block_images(rom, field_cgram(rom, world), tiles)
        out.save(world_image(rom, world, worlds[world]), f'field/field{world}.png', 'field', f'세계 {world}',
                 '세계 지도', variant='낮', note=f'$1949 = {world}. 땅이 있는 왼쪽 위 128x128 블록')
    for world, blocks in worlds.items():
        img = world_image(rom, world, blocks)
        d = ImageDraw.Draw(img)
        el = []
        for g, x, y, w, (bd, ax, ay, _) in ents:
            if w != world:
                continue
            d.rectangle((x * 8 - 2, y * 8 - 2, x * 8 + 9, y * 8 + 9), outline=(255, 255, 0), width=2)
            d.text((x * 8 + 12, y * 8 - 2), f'{g:02X} {names.get(g, "")}', fill=(255, 255, 0))
            el.append({'group': f'{g:02X}', 'name': names.get(g, ''), 'x': x, 'y': y, 'to': f'{g:02X}/{bd:02X}',
                       'at': [ax, ay]})
        out.save(img, f'field/field{world}-annot.png', 'field', f'세계 {world}', '세계 지도', variant='주석',
                 entrances=el, note='노랑 = 04:FD97 입구(그룹 번호와 이름)')
    cg = field_cgram(rom, 0, day)
    labels = [f'{m:03X}' for m in range(512)]
    for layers, stem in ((('lower', 'upper'), 'field'), (('lower',), 'field-lower'), (('upper',), 'field-upper')):
        imgs = field_block_images(rom, cg, tiles, layers)
        out.save(sheet(imgs, 16, 20, 16, labels, label_h=10, below=True), f'gfx/blocks/{stem}.png', 'blocks',
                 f'필드 블록 512개 ({"·".join({"lower": "아래층", "upper": "위층"}[k] for k in layers)})', '필드',
                 note='블록 번호(9비트). 정의 2A:A32C·2A:AD27')
    colors = cgram_colors(cg)
    cells = []
    for t in range(512):
        p = (tile_word(rom, t, True) >> 10) & 7
        cells.append(scaled(tile_image(tiles[t], colors[p * 16:p * 16 + 16]), 2))
    out.save(sheet(cells, 32, 16, 16, pad=0, bg=(0, 0, 0)), 'gfx/blocks/field-tiles.png', 'chr',
             '필드 타일 512개 12:B1A8', 'CHR', note='VRAM 워드 2000-, 2배, 위층 표의 팔레트')
    print('field')


def frames_out(out, frames, stem, title, note, duration, group='필드'):
    sheet_img = sheet(frames, 1, frames[0].width, frames[0].height, [f'{k}' for k in range(len(frames))], label_h=10)
    out.save(sheet_img, f'gfx/anim/{stem}.png', 'anim', title, group, note=note, frames=len(frames))
    path = os.path.join(out.root, f'gfx/anim/{stem}.gif')
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
    out.add(f'gfx/anim/{stem}.gif', 'anim', title + ' (GIF)', group, w=frames[0].width, h=frames[0].height)


def export_anim(rom, out):
    from dq5field import field_chr, tile_word
    sets = field_time_sets(rom)
    day = next(p for p, los in sets if 2 in los)
    colors = cgram_colors(field_cgram(rom, 0, day))

    def img(t, raw):
        p = (tile_word(rom, t, False) >> 10) & 7
        return tile_image(planar(raw), colors[p * 16:p * 16 + 16])

    frames = []
    for tiles in field_anim_sets(rom):
        strip = Image.new('RGB', (FIELD_ANIM_COUNT * 8, 8), colors[0])
        for i, raw in enumerate(tiles):
            t = img(FIELD_ANIM_TILE + i, raw)
            strip.paste(t, (i * 8, 0), t)
        frames.append(strip)
    frames_out(out, frames, 'field-454', '필드 타일 454~459 8벌', '1E:D0FF RLE → 7E:C800 → VRAM 워드 3C60', 150)
    chrs = field_chr(rom)
    frames = []
    for k in range(16):
        strip = Image.new('RGB', (32, 8), colors[0])
        for j, (t1, t2) in enumerate(((0x04, 0x05), (0x14, 0x15))):
            a, b = rotate_pair(chrs[t1 * 32:t1 * 32 + 32], chrs[t2 * 32:t2 * 32 + 32], k)
            for q, (t, raw) in enumerate(((t1, a), (t2, b))):
                ti = img(t, raw)
                strip.paste(ti, (j * 16 + q * 8, 0), ti)
        frames.append(strip)
    frames_out(out, frames, 'field-water', '필드 물 타일 4·5·20·21 16단계',
               '두 타일을 줄마다 16비트로 보고 k 픽셀 돌림(01:C790, 세계 0 은 오른쪽)', 120)
    frames = []
    for wave in range(WAVE_STEPS):
        b = field_block_images(rom, field_cgram(rom, 0, day, wave), field_tiles(rom))
        strip = Image.new('RGB', (16 * 8, 16))
        for i in range(8):
            strip.paste(b[i], (i * 16, 0))
        frames.append(strip)
    frames_out(out, frames, 'field-wave', '필드 물결 팔레트 10단계(블록 000~007)',
               '4번 줄 색 1~3 을 01:A0F6 + $1961*6 으로(01:A0CF)', 120)
    export_indoor_anim(rom, out)
    print('anim')


MATRIX_CHARS = '.123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
# 몬스터 EA·EB 는 ミルドラース 최종 모습의 윗몸·아랫몸이라 둘을 같은 원점에 겹쳐 그린다(dq5-graphics-format.md).
MONSTER_NOTES = {0xEA: '윗몸. 게임은 EB(아랫몸)를 같은 원점에 겹쳐 그림', 0xEB: '아랫몸. EA 와 겹쳐 그림'}


def anim_counters(rom, bc, bd):
    """GIF 로 찍을 카운터 값들: 가장 짧은 주기(4 이상)마다 한 장, 192프레임 한 바퀴."""
    import dq5anim
    moving, _ = dq5anim.map_types(rom, bc, bd)
    moving = [t for t in moving if t != 14]
    if not moving:
        return []
    step = max(4, min(dq5anim.kind(rom, t)['period'] for t in moving))
    return list(range(0, 192, step))


def export_indoor_anim(rom, out):
    """움직이는 타일이 있는 실내 맵마다 맵 전체 GIF(gfx/anim/maps/), 종류마다 타일 띠 시트·GIF(gfx/anim/indoor-NN)."""
    import dq5anim
    names = group_names(rom)
    first_map = {}
    for bc, bd, _ in dq5anim.map_list(rom):
        moving, _ = dq5anim.map_types(rom, bc, bd)
        for t in moving:
            first_map.setdefault(t, (bc, bd))
        counters = anim_counters(rom, bc, bd)
        if not counters:
            continue
        dec, w, h, buf, _ = decode_map(rom, bc, bd)
        cg = map_cgram(rom, bc, bd)
        frames = [draw_cells(rom, dec, w, h, buf, cg, override=anim_override(rom, bc, bd, c)) for c in counters]
        stem = map_stem(bc, bd, names)
        path = os.path.join(out.root, f'gfx/anim/maps/{stem}.gif')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        step = counters[1] - counters[0] if len(counters) > 1 else 8
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=max(20, step * 50 // 3), loop=0)
        out.add(f'gfx/anim/maps/{stem}.gif', 'anim', f'{bc:02X}/{bd:02X} 움직이는 맵', '실내 맵', map=f'{bc:02X}/{bd:02X}',
                stem=stem, w=w * 8, h=h * 8, frames=len(frames),
                note=f'종류 {",".join(str(t) for t in moving)}, 카운터 7E:1ECE 를 {step} 씩(03:D4B5)')
    for t in sorted(first_map):
        if t == 14:
            continue
        bc, bd = first_map[t]
        colors = cgram_colors(map_cgram(rom, bc, bd))
        k = dq5anim.kind(rom, t)
        chrs = dq5anim.block_chrs(rom, k['blocks'], bc >= 0x50)[:k['tiles']]
        pal_table = HIGH_CHR_PALETTE if bc >= 0x50 else CHR_PALETTE
        frames = []
        for c in range(0, 192, max(2, k['period'])):
            ov = anim_override(rom, bc, bd, c)
            strip = Image.new('RGB', (len(chrs) * 8, 8), colors[0])
            for i, chr_id in enumerate(chrs):
                nib = rom.u8(pal_table + (chr_id >> 1))
                pal = (((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4) >> 2 & 7
                raw = ov.get(chr_id) or dq5anim.chr_raw(rom, chr_id, bc >= 0x50)
                ti = tile_image(planar(raw), colors[pal * 16:pal * 16 + 16])
                strip.paste(ti, (i * 8, 0), ti)
            if not frames or frames[-1].tobytes() != strip.tobytes() or len(frames) < 2:
                frames.append(strip)
        while len(frames) > 1 and frames[-1].tobytes() == frames[0].tobytes():
            frames.pop()
        title = f'실내 움직이는 타일 종류 {t}'
        note = f'블록 {" ".join(f"{b:03X}" for b in k["blocks"])}, 주기 {k["period"]}, {bc:02X}/{bd:02X} 팔레트'
        frames_out(out, frames, f'indoor-{t:02d}', title, note, max(20, k['period'] * 50 // 3), group='실내')
    print('indoor anim')


def export_monsters(rom, out):
    from dq5mongfx import COUNT, RECORDS, decode, index_image, monster
    from dq5mongfx import render as render_monster
    from dq5monster import NAMES
    from dq5text import string, string_codes, text
    records = []
    for m in range(COUNT):
        g, colors = monster(rom, m)
        name = text(string_codes(rom, string(rom, NAMES, m)))
        d = decode(rom, g)
        grid = index_image(d)
        img = render_monster(rom, m, None)
        file = f'{m:02X}-{name}.png'
        out.save(img, f'monsters/{file}', 'monsters', f'{m:02X} {name}', '몬스터', monster=f'{m:02X}', name=name,
                 pic=f'{g:02X}')
        records.append({'file': file, 'id': m, 'name': name, 'picture': g,
                        'record': f'27:{rom.u16(RECORDS + m * 2):04X}', 'head': f'{d["head"] >> 16:02X}:{d["head"] & 0xFFFF:04X}',
                        'cells': [d['w'], d['h']], 'pieces': len(d['pieces']), 'size': [img.width, img.height],
                        'colors': [f'{c:04X}' for c in colors], 'usable': True, 'note': MONSTER_NOTES.get(m, ''),
                        'matrix': [''.join(MATRIX_CHARS[v] for v in row) for row in grid]})
    out.index['monsters'] = {
        'note': '그림은 1배, 투명 배경. 왼쪽 1픽셀은 반전 조각이 한 픽셀 왼쪽으로 나갈 자리. colors 는 OBJ 팔레트 1번 색부터의 '
                '15비트 BGR, matrix 문자는 색 번호(. 투명, 1~9·A~). record 는 27 뱅크 몬스터 레코드, head 는 그림 머리',
        'monsters': records}
    print('monsters')


def export_battlebg(rom, out):
    import dq5battlebg as bb
    for n in range(bb.COUNT):
        for era in (0, 1, 2):
            stem = f'{n:02X}' + (f'-{era}' if era else '')
            out.save(bb.render(rom, n, era), f'battlebg/{stem}.png', 'battlebg', f'{n:02X} ($1949={era})',
                     f'세계 {era}', number=f'{n:02X}', era=era, note='레코드 밖 팔레트 색은 자홍')
    print('battlebg')


def export_font(rom, out):
    from dq5text import GLYPHS, font_groups, glyph
    groups = font_groups(rom)
    cells = []
    for code in range(GLYPHS):
        w, h, rows = glyph(rom, code, groups)
        img = Image.new('RGB', (16, 16))
        p = img.load()
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v and x < 16 and y < 16:
                    p[x, y] = (255, 255, 255)
        cells.append(scaled(img, 2))
    out.save(sheet(cells, 16, 32, 32, pad=0, bg=(0, 0, 0)), 'gfx/font.png', 'font', f'폰트 글자 {GLYPHS}개', '폰트',
             note='24:A609, 16자씩 한 줄, 2배. n 번째 칸 = 글자 코드 n')
    print('font')


def export_ui(rom, out):
    o = lorom(UI_PALETTE)
    colors = cgram_colors(rom.d[o:o + 32])
    data = ui_tiles(rom)
    tiles = [chr_2bpp(data[t * 16:t * 16 + 16]) for t in range(len(data) // 16)]
    for pal in range(4):
        cells = [scaled(tile_image(px, colors[pal * 4:pal * 4 + 4]), 2) for px in tiles]
        stem = 'window-tiles' + (f'-pal{pal}' if pal else '')
        out.save(sheet(cells, 16, 16, 16, pad=0, bg=colors[0]), f'gfx/screens/{stem}.png', 'screens',
                 f'창·메뉴 타일 {len(tiles)}개 (BG3 팔레트 {pal})', '창', note='04:E528, 2배, n 번째 칸 = 타일 n')
    win = Image.new('RGBA', (len(UI_SAMPLE[0]) * 8, len(UI_SAMPLE) * 8), colors[0] + (255,))
    for y, row in enumerate(UI_SAMPLE):
        for x, w in enumerate(row):
            t = tile_image(tiles[w & 0xFF], colors[0:4], bool(w & 0x400), bool(w & 0x800))
            win.paste(t, (x * 8, y * 8), t)
    out.save(win.convert('RGB'), 'gfx/screens/window.png', 'screens', '창 견본(배 선실의 상태 창)', '창',
             note='타일 8C~90 테두리와 글자 타일')
    print('ui')


def world_screen(rom, world=0):
    """たびびとのちず 화면의 128x120 색 번호 격자. 03:CAC2 를 옮긴 것. 블록은 그때 풀려 있는 세계($1949) 지도에서 읽는다."""
    from dq5field import WORLDS, block_number, rle
    wmap, _ = rle(rom, WORLDS[world][0])
    hib, _ = rle(rom, WORLDS[world][1])
    ce, d0 = 0, 0x10
    chars = bytearray(0x4000)
    for y in range(0x4000):
        b = block_number(wmap, hib, (ce >> 1) & 255, (d0 >> 1) & 255)
        nib = rom.u8(WORLD_SCREEN_BLOCK_COLOR + (b >> 1))
        chars[y] = (nib & 15 if b & 1 else nib >> 4) + 0x20
        x, z = 0, y + 1
        if z & 0x3FF:
            x += 2
            if z & 0x3F:
                x += 2
                if z & 7:
                    x += 2
        ce = (ce + rom.u16(WORLD_SCREEN_STEP_X + x)) & 0x1FF
        d0 = (d0 + rom.u16(WORLD_SCREEN_STEP_Y + x)) & 0x1FF
    grid = [[0] * 128 for _ in range(120)]
    for t in range(240):
        for k in range(64):
            grid[t // 16 * 8 + k // 8][t % 16 * 8 + k % 8] = chars[t * 64 + k]
    return grid


def export_world_screen(rom, out):
    o = lorom(WORLD_SCREEN_COLORS)
    colors = cgram_colors(rom.d[o:o + 32])
    grid = world_screen(rom)
    img = Image.new('RGB', (128, 120))
    p = img.load()
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            p[x, y] = colors[v - 0x20]
    out.save(img, 'gfx/screens/world-map.png', 'screens', 'たびびとのちず 세계 지도(모드 7, $1949=0)', '세계 지도',
             note='03:CAC2 가 필드 블록마다 03:CC48 의 색으로 찍는 128x120, 색 03:CC2C')
    from dq5field import WORLDS, block_number, rle
    for world in (1, 2):
        wmap, _ = rle(rom, WORLDS[world][0])
        hib, _ = rle(rom, WORLDS[world][1])
        img = Image.new('RGB', (256, 256))
        p = img.load()
        for v in range(256):
            for u in range(256):
                b = block_number(wmap, hib, u >> 1, v >> 1)
                nib = rom.u8(WORLD_SCREEN_BLOCK_COLOR + (b >> 1))
                p[u, v] = colors[(nib & 15 if b & 1 else nib >> 4)]
        out.save(img, f'gfx/screens/world-map-{world}.png', 'screens', f'たびびとのちず 세계 지도($1949={world}, 전체)',
                 '세계 지도', note='$1EBE bit7 갈래: 게임은 주인공 필드 좌표($1EC4,$1EC6)를 가운데로 이 그림의 128x120 만 '
                 '보여 줌(1점 = 필드 좌표 1, 03:CD50 걸음 표)')


def credits_tiles(rom):
    from dq5field import rle
    data, _ = rle(rom, CREDITS_FONT)
    data = bytes(16) + data
    return [data[i * 16:i * 16 + 16] for i in range(len(data) // 16)]


def credits_rows(rom, script):
    """글자 문자열을 줄마다 [(x 점, 글자 번호)] 와 글자로 푼 문자열로."""
    p = rom.u24(CREDITS_SCRIPTS + script * 3)
    rows, cur, x, k = [], None, 0, 0
    while k < 0x4000:
        b = rom.u8(p + k)
        k += 1
        if b == 0xF5 or (b == 0x00 and cur is None and script == 1 and rows):
            break
        if b == 0xFC:
            if cur is None:
                cur, x = [], 0
                rows.append(cur)
            elif cur:
                cur.append((x, None))
            x += rom.u8(p + k) * 8
            k += 1
        elif b == 0xFB:
            # 02:FC66: 줄 무늬 칸(1E:F5A8 의 2bpp 타일 위 + 빈 아래) n 개를 지금 자리부터 늘어놓는다(섹션 제목 밑줄).
            if cur is None:
                cur, x = [], 0
                rows.append(cur)
            for _ in range(rom.u8(p + k)):
                cur.append((x, CREDITS_BAND))
                x += 8
            k += 1
        elif b in (0xF7, 0xF6):
            k += 1
        elif b == 0xFE:
            cur = None
        elif b == 0xFD:
            rows.append([])
        elif b < 0x40:
            if cur is None:
                cur, x = [], 0
                rows.append(cur)
            cur.append((x, b))
            width = rom.u8(CREDITS_GLYPHS + b * 3 + 2)
            x += width or 8
    texts = []
    for r in rows:
        t, i = '', 0
        codes = [c for _, c in r]
        while i < len(codes):
            if codes[i] is None:
                t, i = t + ' ', i + 1
                continue
            if codes[i] == CREDITS_BAND:
                t, i = t + '─', i + 1
                continue
            pair = tuple(codes[i:i + 2])
            if pair in CREDITS_PAIRS:
                t, i = t + CREDITS_PAIRS[pair], i + 2
                continue
            c = codes[i]
            t += CREDITS_TEXT[c] if c < len(CREDITS_TEXT) else {0x1D: '.', 0x22: '-'}.get(c, '?')
            i += 1
        texts.append(t)
    return rows, texts


def credits_image(rom, rows, colors):
    tiles = credits_tiles(rom)[1:]
    img = Image.new('RGB', (256, len(rows) * 16), colors[0])
    band = tile_image(chr_2bpp(bytes(rom.u8(CREDITS_BAND_TILE + i) for i in range(16))), colors[0:4])
    for y, r in enumerate(rows):
        for x, c in r:
            if c is None:
                continue
            if c == CREDITS_BAND:
                img.paste(band, (x, y * 16), band)
                continue
            for half in (0, 1):
                t = rom.u8(CREDITS_GLYPHS + c * 3 + half)
                if t < len(tiles):
                    ti = tile_image(chr_2bpp(tiles[t]), colors[0:4])
                    img.paste(ti, (x, y * 16 + half * 8), ti)
    return img


def export_credits(rom, out):
    o = lorom(UI_PALETTE)
    colors = cgram_colors(rom.d[o:o + 8])
    tiles = credits_tiles(rom)
    n = len(tiles) // 2
    img = Image.new('RGB', (n * 8, 16), colors[0])
    for g in range(n):
        for half in (0, 1):
            t = tile_image(chr_2bpp(tiles[g * 2 + half]), colors[0:4])
            img.paste(t, (g * 8, half * 8), t)
    for script, stem, title in ((1, 'title-credits', '타이틀 화면 글자(ENIX PRESENTS ~ DRAGON QUEST V)'),
                                (0, 'staff-roll', '엔딩 스태프 롤')):
        rows, texts = credits_rows(rom, script)
        out.save(credits_image(rom, rows, colors), f'gfx/screens/{stem}.png', 'screens', title, '타이틀·엔딩',
                 script=f'{rom.u24(CREDITS_SCRIPTS + script * 3):06X}', lines=[t for t in texts if t],
                 note='02:FB2B 의 글자 문자열을 줄마다 16점으로 늘어놓음(게임은 화면에 몇 줄씩 띄우거나 올림)')
    out.save(img, 'gfx/screens/credits-font.png', 'screens', f'타이틀 화면 글자 칸 {n}개(8x16)', '타이틀',
             note='1E:D7E3 RLE 타일을 위·아래 짝으로 늘어놓음(글자표 아님, 타일을 나눠 쓰는 글자가 있음). 색은 BG3 팔레트 0(04:98D7)')


# 창 문자열의 자리 표시(B0~) 너비: HP·MP 3칸, 레벨 2칸(상태 창 실측). 나머지는 1칸으로 둔다.
WINDOW_FIELDS = {0xB0: 3, 0xB1: 3, 0xC6: 2, 0xBD: 2}
# 갤러리용 예시 값: 자리 표시마다 오른쪽 맞춤 숫자(타일 02~0B = 0~9), 이름 자리는 「ああああ」(타일 10).
WINDOW_SAMPLES = {0xB0: '999', 0xB1: '999', 0xC6: '99', 0xBD: '99'}
SAMPLE_NAME = (0x10, 0x10, 0x10, 0x10)


def window_grid(rom, n):
    """창 레코드 n(04:EB48)을 BG3 타일 번호 격자로. (격자, X, Y) 또는 못 그리는 창이면 None.
    머리 +0·+1 위치, +2 아래 5비트 너비, +3 아래 4비트 높이·bit7 줄 간격 16점(sfc/dq5/docs/dq5-text-format.md 「창 레코드 머리」).
    목록 창: 첫 FE 부터. FE = 커서 칸 하나 뒤 글자, FF = 다음 줄, 바이트는 BG3 타일 번호 그대로. 84·83 xx 는 글자 xx 위 칸에
    탁점 84·반탁점 83(위 칸이 테두리면 92·93, 04:B258).
    상태 창 꼴(+4 가 D0~D3, 곧 제목 자리 0~3·제목 뒤 3바이트 건너뜀): 뒤 4바이트 자리에 이름, 다음 8x 는 가로줄 하나와 그 뒤 x 줄. 자리 표시는 예시 값(WINDOW_SAMPLES, 이름은 SAMPLE_NAME)으로 채운다.
    커서 없는 글 창(+4 가 0, +6 부터 글): F3 은 이름 넉 자 자리."""
    from dq5text import window
    _, data = window(rom, n)
    if len(data) < 6:
        return None
    w, h, step = data[2] & 0x1F, data[3] & 0x0F, 2 if data[3] & 0x80 else 1
    if w < 3 or h < 3 or data[0] & 0x80:
        return None
    grid = [[0x001] * w for _ in range(h)]
    for x in range(w):
        grid[0][x], grid[h - 1][x] = 0x08D, 0x88D
    for y in range(h):
        grid[y][0], grid[y][w - 1] = 0x08E, 0x48E
    grid[0][0], grid[0][w - 1], grid[h - 1][0], grid[h - 1][w - 1] = 0x08C, 0x48C, 0x88C, 0xC8C

    def put(x, y, t):
        if 0 < x < w - 1 and 0 < y < h - 1:
            grid[y][x] = t

    x, y = 1, 1
    if 0xD0 <= data[4] <= 0xD3:
        step = 2  # 상태 창은 +3 bit7 이 꺼져 있어도 16점 간격(배 선실 덤프)
        for k in range(4):
            put(1 + k, 1, SAMPLE_NAME[k])
        i, y = 9, 2
        if i < len(data) and data[i] & 0x80 and data[i] < 0x84:
            for xx in range(1, w - 1):
                put(xx, y, 0x090)
            grid[y][0], grid[y][w - 1] = 0x08F, 0x48F
            i, y = i + 1, y + 1
        elif i < len(data) and data[i] >= 0x80:
            i += 1
    elif data[4] & 0x0F == 0 and 0xFE in data[5:8]:
        i = data.index(0xFE)
    elif data[4] == 0 and 0xFF in data[6:] and all(b < 0x85 or b in (0xF3, 0xFE, 0xFF) for b in data[6:]):
        # 커서 없는 글 창(이름 칸·말 빠르기 등): +6 부터 글, +5 위 니블만큼 첫 줄을 들여 씀(두 창 덤프로 확인).
        # 자리 표시(85 xx·B0~ 등)가 섞인 창은 뜻을 모르는 제어가 있어 뺀다.
        i, x, step = 6, 1 + (data[5] >> 4), 1
    elif data[4] & 0x0F and 0xFE in data[7 + (data[4] >> 6):10 + (data[4] >> 6)]:
        # 제목 있는 창(dq5text.window_header): +4 아래 니블 제목 자리, +5 제목 번호(04:AD78), 둘째 줄 제목, 셋째 줄 가로줄, 넷째 줄부터 항목.
        from dq5text import window_title
        tx, title, j = data[4] & 0x0F, window_title(rom, data[5]), 0
        while j < len(title):
            if title[j] in (0x92, 0x93) and j + 1 < len(title):
                put(tx, 1, title[j + 1])
                if 0 < tx < w - 1:
                    grid[0][tx] = title[j]
                tx, j = tx + 1, j + 2
                continue
            if title[j] >= 0xE0:
                for k, t in enumerate(SAMPLE_NAME):
                    put(tx + k, 1, t)
                tx, j = tx + len(SAMPLE_NAME), j + 1
                continue
            if title[j] < 0x89:
                put(tx, 1, title[j])
            tx, j = tx + 1, j + 1
        for xx in range(1, w - 1):
            put(xx, 2, 0x090)
        grid[2][0], grid[2][w - 1] = 0x08F, 0x48F
        k = 6 + (data[4] >> 6)  # +4 bit6-7 = 제목 뒤 건너뛸 바이트 수, 그다음이 줄 수(dq5text.window_header)
        i, y = data.index(0xFE, k + 1), 3
        rows = data[k] & 0x7F
        step = 2 if rows and rows * 2 - 1 <= h - 4 else 1
    else:
        return None
    while i < len(data):
        b = data[i]
        if b == 0xFE:
            x += 1
        elif b == 0xFF:
            x, y = 1, y + step
        elif b in (0x83, 0x84) and i + 1 < len(data):
            if data[i + 1] in (0xFE, 0xFF):
                # 뒤 글자 없이 줄 끝에 오면 위 칸에 탁점·반탁점만(이름 입력 창의 ゛゜ 칸)
                if 0 < x < w - 1 and 0 < y < h - 1:
                    grid[y - 1][x] = b
                x, i = x + 1, i + 1
                continue
            put(x, y, data[i + 1])
            if 0 < x < w - 1 and 0 < y < h - 1:
                above = grid[y - 1][x]
                if y - 1 == 0:
                    grid[y - 1][x] = 0x093 if b == 0x83 else 0x092
                elif above == 0x090:
                    grid[y - 1][x] = 0x095 if b == 0x83 else 0x094
                else:
                    grid[y - 1][x] = b
            x, i = x + 1, i + 1
        elif b < 0x89:
            put(x, y, b)
            x += 1
        elif b == 0xF3:
            for k in range(4):
                put(x + k, y, 0x089)  # 이름 입력 칸: 아직 안 넣은 글자는 089(＊)
            x += 4
        elif b in WINDOW_FIELDS:
            digits = WINDOW_SAMPLES[b].rjust(WINDOW_FIELDS[b])
            for k, ch in enumerate(digits):
                if ch != ' ':
                    put(x + k, y, 0x02 + int(ch))
            x += WINDOW_FIELDS[b]
        else:
            x += 1
        if x > w:
            return None  # 줄이 창보다 길면 항목 꼴이 아니다(창 레코드 뒤의 다른 자료로 보임)
        if y >= h - 1:
            break
        i += 1
    return grid, data[0] & 0x1F, data[1] & 0x1F


def export_windows(rom, out):
    from dq5text import WINDOWS
    o = lorom(UI_PALETTE)
    colors = cgram_colors(rom.d[o:o + 8])
    tiles = [chr_2bpp(t) for t in (ui_tiles(rom)[i * 16:i * 16 + 16] for i in range(150))]
    count = 0
    for n in range(0x100):
        try:
            got = window_grid(rom, n)
        except (IndexError, ValueError):
            got = None
        if not got:
            continue
        grid, wx, wy = got
        img = Image.new('RGB', (len(grid[0]) * 8, len(grid) * 8), colors[0])
        for y, row in enumerate(grid):
            for x, word in enumerate(row):
                t = word & 0xFF
                if t < len(tiles):
                    ti = tile_image(tiles[t], colors[0:4], bool(word & 0x400), bool(word & 0x800))
                    img.paste(ti, (x * 8, y * 8), ti)
        out.save(img, f'gfx/screens/windows/{n:02X}.png', 'screens', f'창 {n:02X}', '창 레코드',
                 window=f'{n:02X}', pos=f'{wx},{wy}', record=f'{WINDOWS >> 16:02X}:{rom.u16(WINDOWS + n * 2):04X}',
                 note='04:EB48 레코드의 너비·높이·항목으로 그림(글자 바이트 = BG3 타일). 자리 표시(HP·이름 등)는 예시 값 999·ああああ')
        count += 1
    print(f'windows {count}')


# 타이틀 뒤 모험의 서·이름 입력 화면: 창 레코드를 차례로 겹친 BG3 화면(덤프의 BG3 타일맵과 견줘 확인).
# 겹친 테두리가 만나는 칸(08B 등)과 커서, 뒤 창이 어두워지는 팔레트는 게임이 따로 그려서 넣지 않았다.
MENU_SCREENS = (
    ('book', '모험의 서 첫 메뉴', (0x60,)),
    ('book-new', '모험의 서 만들기(빈 칸 고르기)', (0x60, 0x68)),
    ('name-entry', '이름 입력(히라가나)', (0x60, 0x6B, 0x6C)),
    ('message-speed', '말 빠르기 고르기', (0x60, 0x6B, 0x6C, 0x63)),
    ('sound', '스테레오·모노 고르기', (0x60, 0x6B, 0x6C, 0x63, 0x86)),
)


def menu_screen_map(rom, windows):
    screen = [[0] * 32 for _ in range(28)]
    for n in windows:
        grid, wx, wy = window_grid(rom, n)
        for y, row in enumerate(grid):
            for x, w in enumerate(row):
                if wy + y < 28 and wx + x < 32:
                    screen[wy + y][wx + x] = w
    return screen


def export_menu_screens(rom, out):
    o = lorom(UI_PALETTE)
    colors = cgram_colors(rom.d[o:o + 8])
    tiles = [chr_2bpp(t) for t in (ui_tiles(rom)[i * 16:i * 16 + 16] for i in range(150))]
    for stem, title, windows in MENU_SCREENS:
        img = Image.new('RGB', (256, 224), (0, 0, 0))
        for y, row in enumerate(menu_screen_map(rom, windows)):
            for x, w in enumerate(row):
                t = w & 0xFF
                if w and t < len(tiles):
                    ti = tile_image(tiles[t], colors[0:4], bool(w & 0x400), bool(w & 0x800))
                    img.paste(Image.new('RGB', (8, 8), colors[0]), (x * 8, y * 8))
                    img.paste(ti, (x * 8, y * 8), ti)
        out.save(img, f'gfx/screens/menu-{stem}.png', 'screens', title, '모험의 서·이름 입력',
                 windows=' '.join(f'{n:02X}' for n in windows),
                 note='창 레코드를 적힌 차례로 겹침. 테두리가 만나는 칸·커서·뒤 창 어둡게 하기는 빠짐')


def the_end_tiles(rom):
    from dq5sprite import unpack
    lo, a = unpack(rom, THE_END_TILES, False)
    hi, _ = unpack(rom, a, False)
    out = []
    for i in range(len(lo) // 8):
        t = bytearray(16)
        t[0::2] = lo[i * 8:i * 8 + 8]
        t[1::2] = hi[i * 8:i * 8 + 8] if len(hi) >= i * 8 + 8 else bytes(8)
        out.append(bytes(t))
    return out


def export_the_end(rom, out):
    o = lorom(THE_END_COLORS)
    colors = cgram_colors(bytes(2) + rom.d[o:o + 22])
    tiles = [chr_2bpp(t) for t in the_end_tiles(rom)]
    the_end = the_end_map(rom)
    img = Image.new('RGB', (len(the_end[0]) * 8, len(the_end) * 8), colors[0])
    for y, row in enumerate(the_end):
        for x, w in enumerate(row):
            t = w & 0x3FF
            if t < len(tiles):
                pal = (w >> 10) & 7
                ti = tile_image(tiles[t], colors[pal * 4:pal * 4 + 4], bool(w & 0x4000), bool(w & 0x8000))
                img.paste(ti, (x * 8, y * 8), ti)
    out.save(img, 'gfx/screens/the-end.png', 'screens', '엔딩 「THE END」', '타이틀·엔딩',
             note='타일 03:B459, 색 03:A502, 배치 03:A478(03:A40A)')


def export_battle_windows(rom, out):
    import dq5battlewin
    for name, title, img in dq5battlewin.windows(rom):
        out.save(img, f'gfx/screens/{name}', 'screens', title, '전투 메시지 창',
                 note='24:A4A4 글자 격자 → 24:A5D9 타일맵(dq5battlewin.py). 이름·숫자는 예시 값(ああああ·スライム·4·1·メラ)')


# 오프닝 타이틀(모드 0, BG 넷 모두 2bpp). 타일은 모두 1F:D28B 런 길이 압축의 낮은·높은 바이트 줄기.
# 로고(BG1)·V(BG2)는 02:E840 이 비트맵(한 줄 4바이트 = 32칸, 켜진 칸마다 다음 타일 번호)으로 타일맵을 만든다.
# 로고는 02:EDED 의 타일 12개만 팔레트 1, V 는 02:EDF9 문턱 다섯 개로 줄마다 팔레트 1~5.
# 성(BG4) 타일맵은 낮은 바이트 줄기 하나(0F:E7D4)이고 높은 바이트는 02:EA62 가 타일 번호 문턱표 02:EA84 로 정한다.
# 그 뒤 줄기(0F:E9D1)는 BG3 의 물결 반짝임(타일 52 하나, 색 더하기)이다.
TITLE_LAYERS = {
    'logo': dict(chr=0x0FD97B, bitmap=0x02EDA1, rows=8, colors=0x0FECFB, ncolors=8, at=0x163),
    'v': dict(chr=0x0FDED5, bitmap=0x02EDC1, rows=11, colors=0x0FED1B, ncolors=24, at=0x14B),
}
TITLE_LOGO_PAL1 = 0x02EDED
TITLE_V_STEPS = 0x02EDF9
TITLE_CASTLE_CHR, TITLE_CASTLE_MAP, TITLE_CASTLE_ATTR, TITLE_CASTLE_COLORS = 0x0FE41F, 0x0FE7D4, 0x02EA84, 0x02EE70
# 링은 OBJ 4bpp(VRAM 워드 7000 = 타일 100~). 02:EDFE 의 4바이트 항목 [X][Y][세로 타일 수][속성] 마다 8x8 을
# 아래로 이어 붙이고 타일 번호는 100 부터 차례로, FF 로 끝. 속성 30(우선순위 3)은 로고 앞, 00 은 로고 뒤.
# OBJ 는 OAM Y 보다 한 줄 아래에 그려진다(하드웨어 동작, 덤프 화면과 맞춤).
TITLE_RING_CHR, TITLE_RING_COLORS, TITLE_RING_OAM = 0x0FE13C, 0x0FED4B, 0x02EDFE
TITLE_BACKDROP = 0x1400
# 로고·V 의 자리는 TITLE_LAYERS 의 at(타일맵 칸), 성은 타일맵 왼쪽 위가 화면 왼쪽 위(HDMA ch5 가 0~190줄의
# BG4 가로 스크롤을 0 으로 둠). 이 화면은 overscan 모드라 MesenCE 224줄 화면이 위 8줄을 자르므로 TITLE_Y 만큼 올린다.
TITLE_Y = -8


def title_tiles(rom, a):
    from dq5sprite import unpack
    lo, b = unpack(rom, a, False)
    hi, _ = unpack(rom, b, False)
    out = []
    for i in range(len(lo) // 8):
        t = bytearray(16)
        t[0::2] = lo[i * 8:i * 8 + 8]
        t[1::2] = hi[i * 8:i * 8 + 8]
        out.append(chr_2bpp(t))
    return out


def title_bitmap_map(rom, name):
    """02:E840 의 비트맵 → 32칸 줄 목록(타일맵 낱말)."""
    lay, rows, t = TITLE_LAYERS[name], [], 0
    special = {rom.u8(TITLE_LOGO_PAL1 + i) for i in range(12)}
    steps = [rom.u8(TITLE_V_STEPS + i) for i in range(5)]
    for r in range(lay['rows']):
        row = []
        for k in range(32):
            if rom.u8(lay['bitmap'] + r * 4 + k // 8) & (0x80 >> (k & 7)):
                t += 1
                pal = (1 if t in special else 0) if name == 'logo' else sum(t >= s for s in steps)
                row.append(pal << 10 | t)
            else:
                row.append(0)
        rows.append(row)
    return rows


def title_castle_map(rom):
    from dq5sprite import unpack
    lo, _ = unpack(rom, TITLE_CASTLE_MAP, False)

    def attr(t):
        for y in range(0x12, -1, -2):
            if t < rom.u8(TITLE_CASTLE_ATTR + y):
                return rom.u8(TITLE_CASTLE_ATTR + 1 + y)
        return rom.u8(TITLE_CASTLE_ATTR - 1)
    return [[lo[r * 32 + c] | attr(lo[r * 32 + c]) << 8 for c in range(32)] for r in range(32)]


def draw_words(rows, tiles, colors, size=None, at=(0, 0)):
    img = Image.new('RGBA', size or (len(rows[0]) * 8, len(rows) * 8), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, w in enumerate(row):
            t, pal = w & 0x3FF, (w >> 10) & 7
            if t and t < len(tiles):
                ti = tile_image(tiles[t], colors[pal * 4:pal * 4 + 4], bool(w & 0x4000), bool(w & 0x8000))
                img.paste(ti, (at[0] + x * 8, at[1] + y * 8), ti)
    return img


def title_layer(rom, name):
    lay = TITLE_LAYERS[name]
    o = lorom(lay['colors'])
    colors = cgram_colors(bytes(2) + rom.d[o + 2:o + lay['ncolors'] * 2])
    return draw_words(title_bitmap_map(rom, name), title_tiles(rom, lay['chr']), colors)


def title_castle(rom):
    o = lorom(TITLE_CASTLE_COLORS)
    return draw_words(title_castle_map(rom), title_tiles(rom, TITLE_CASTLE_CHR), cgram_colors(rom.d[o:o + 64]))


def title_ring_tiles(rom):
    """낮은 바이트 줄기는 $2118, 높은 바이트는 $2119 로 가서 2bpp 짝 둘이 4bpp OBJ 타일 하나가 된다."""
    from dq5sprite import unpack
    lo, b = unpack(rom, TITLE_RING_CHR, False)
    hi, _ = unpack(rom, b, False)
    out = []
    for i in range(len(lo) // 16):
        t = bytearray(32)
        t[0::2] = lo[i * 16:i * 16 + 16]
        t[1::2] = hi[i * 16:i * 16 + 16]
        out.append(planar(bytes(t)))
    return out


def title_ring(rom, front):
    o = lorom(TITLE_RING_COLORS)
    colors = cgram_colors(rom.d[o:o + 32])
    tiles = title_ring_tiles(rom)
    img = Image.new('RGBA', (256, 224), (0, 0, 0, 0))
    a, t = TITLE_RING_OAM, 0
    while rom.u8(a) != 0xFF:
        x, y, n, attr = rom.u8(a), rom.u8(a + 1), rom.u8(a + 2), rom.u8(a + 3)
        for k in range(n):
            if bool(attr & 0x30) == front and t < len(tiles):
                ti = tile_image(tiles[t], colors)
                img.paste(ti, (x, y + k * 8 + TITLE_Y + 1), ti)
            t += 1
        a += 4
    return img


def title_screen(rom):
    """오프닝 마지막 타이틀 화면. BG3 반짝임은 뺌. 256x224."""
    img = Image.new('RGB', (256, 224), rgb(TITLE_BACKDROP))
    castle = title_castle(rom)
    img.paste(castle, (0, TITLE_Y), castle)
    back = title_ring(rom, False)
    img.paste(back, (0, 0), back)
    for name in ('v', 'logo'):
        lay = TITLE_LAYERS[name]
        layer = title_layer(rom, name)
        img.paste(layer, (lay['at'] % 32 * 8, lay['at'] // 32 * 8 + TITLE_Y), layer)
    front = title_ring(rom, True)
    img.paste(front, (0, 0), front)
    return img


def export_title(rom, out):
    meta = '02:E840 비트맵 타일맵, 타일 1F:D28B 압축'
    for name, title in (('logo', '타이틀 로고(BG1)'), ('v', '타이틀 「V」(BG2)')):
        lay = TITLE_LAYERS[name]
        out.save(title_layer(rom, name), f'gfx/screens/title-{name}.png', 'screens', title, '타이틀',
                 chr=f'{lay["chr"]:06X}', bitmap=f'{lay["bitmap"]:06X}', colors=f'{lay["colors"]:06X}', note=meta)
    out.save(title_castle(rom), 'gfx/screens/title-castle.png', 'screens', '타이틀 배경 성과 바다(BG4)', '타이틀',
             chr=f'{TITLE_CASTLE_CHR:06X}', map=f'{TITLE_CASTLE_MAP:06X}', colors=f'{TITLE_CASTLE_COLORS:06X}',
             note='타일맵 낮은 바이트 0F:E7D4, 높은 바이트는 02:EA62 가 타일 번호로 정함. 게임은 가로로 흘려 보낸다')
    o = lorom(TITLE_RING_COLORS)
    colors = cgram_colors(rom.d[o:o + 32])
    ring = title_ring_tiles(rom)
    out.save(sheet([tile_image(t, colors) for t in ring], 16, 8, 8, pad=0, bg=rgb(TITLE_BACKDROP)),
             'gfx/screens/title-ring-tiles.png', 'screens', f'타이틀 링 OBJ 타일 {len(ring)}개', '타이틀',
             chr=f'{TITLE_RING_CHR:06X}', colors=f'{TITLE_RING_COLORS:06X}', oam=f'{TITLE_RING_OAM:06X}',
             note='OBJ 두 번째 표(VRAM 워드 7000, 타일 100~)에 올라가는 4bpp 타일')
    out.save(title_screen(rom), 'gfx/screens/title.png', 'screens', '오프닝 타이틀 화면', '타이틀',
             note='성 BG4, 링 뒤쪽, V, 로고, 링 앞쪽 차례로 덤프 실측 자리에 겹침. BG3 물결 반짝임(색 더하기)은 뺌')


# 전투 주문·특기 연출 그림(22:BBBF). 행동 번호(26:8765 와 같은 번호)마다
#   29:8296[행동*2] → 29 뱅크의 조각 주소 목록(FFFF 로 끝). 앞 묶음은 BG3 2bpp 조각, 0000 뒤 묶음은 OBJ 조각
#   29:FACF[행동*2] → 29 뱅크의 색 묶음 [색 수 n][15비트 색 n개]. 첫 묶음이 BG3, 다음 묶음이 OBJ(メラ 실측).
#     22:BBBF 는 그 주소 한 바이트 앞의 위 니블이 0 이 아니면 묶음을 둘 읽는다(앞 묶음 끝 바이트와 겹쳐 둔 꼴).
#     FFFF 인 행동 중 バギ 계열은 22:DEA3 이 22:DEE8 의 두 묶음 중 둘째(22:DEF2)를 썼고, たたかう 는 색을 바꾸지 않아
#     전투 기본 BG3 팔레트 4(24:F987 의 세 색)였다(덤프 실측). ミナデイン 은 띄워 보지 않아 기본 색으로 둔다
# 조각 = [가로-1 위 니블·세로-1 아래 니블][칸 비트맵] 뒤에 칸마다 몬스터 그림과 같은 타일(dq5mongfx.tile).
# OBJ 조각은 비트맵 뒤에 몬스터처럼 칸마다 니블(bit1 16x16, bit2·3 앞 조각 좌우 반전 복사)이 더 있다.
# 조각을 놓는 자리와 차례(움직임)는 아직 읽지 않았다.
EFFECT_CELS, EFFECT_COLORS, EFFECT_COUNT = 0x298296, 0x29FACF, 0xAA
EFFECT_FALLBACK_COLORS, EFFECT_DEFAULT_COLORS = 0x22DEE8, 0x24F987


def effect_lists(rom, n):
    """행동 n 의 (BG3 조각 주소 목록, OBJ 조각 주소 목록). 연출이 없으면 None."""
    p = rom.u16(EFFECT_CELS + n * 2)
    if p == 0xFFFF:
        return None
    a, groups = 0x290000 | p, [[]]
    while True:
        w = rom.u16(a)
        a += 2
        if w == 0xFFFF:
            if rom.u16(a) != 0:
                break
            groups.append([])
            a += 2
            continue
        groups[-1].append(0x290000 | w)
    return groups[0], [c for g in groups[1:] for c in g]


def effect_colors(rom, n):
    p = rom.u16(EFFECT_COLORS + n * 2)
    if p == 0xFFFF:
        if n in (0x0D, 0x0E, 0x0F):
            a = 0x220000 | rom.u16(EFFECT_FALLBACK_COLORS + 2)
            return [[rgb(rom.u16(a + 1 + i * 2)) for i in range(rom.u8(a))]]
        return [[rgb(rom.u16(EFFECT_DEFAULT_COLORS + i * 2)) for i in range(3)]]
    a, out = 0x290000 | p, []
    for _ in range(2 if rom.u8(a - 1) & 0xF0 else 1):
        k = rom.u8(a)
        out.append([rgb(rom.u16(a + 1 + i * 2)) for i in range(k)])
        a += 1 + k * 2
    return out


def effect_cel(rom, a, obj):
    """조각 하나 → (가로 칸, 세로 칸, [(x 점, y 점, 4bpp 타일 32바이트, 좌우 반전)])."""
    from dq5mongfx import Stream, tile
    s = Stream(rom, a)
    b = s.u8(0)
    w, h = (b >> 4) + 1, (b & 15) + 1
    cells = [(i % w, i // w) for i in range(w * h) if s.u8(1 + i // 8) >> (7 - i % 8) & 1]
    nib_at = 1 + (w * h + 7) // 8
    pos = [nib_at + ((len(cells) + 1) // 2 if obj else 0)]
    pieces, out = [], []
    for k, (x, y) in enumerate(cells):
        nib = s.u8(nib_at + k // 2) >> (0 if k & 1 else 4) & 15 if obj else 0
        big = bool(nib & 2)
        if nib & 0xC:
            ref = pieces[s.u8(pos[0])]
            pos[0] += 1
            pieces.append((x * 8 - (0 if nib & 4 else 1), y * 8, ref[2], ref[3], not ref[4]))
        else:
            pieces.append((x * 8, y * 8, big, [tile(s, pos) for _ in range(4 if big else 1)], False))
    for x, y, big, tiles, flip in pieces:
        for i, t in enumerate(tiles):
            dx = (i & 1) * 8
            out.append((x + (8 - dx if flip and big else dx), y + (i >> 1) * 8, t, flip))
    return w, h, out


def effect_image(rom, a, obj, colors):
    w, h, tiles = effect_cel(rom, a, obj)
    img = Image.new('RGBA', (w * 8 + 8, h * 8), (0, 0, 0, 0))
    pal = [(0, 0, 0)] + (colors + [(255, 0, 255)] * 15)[:15]
    for x, y, t, flip in tiles:
        ti = tile_image(planar(t), pal, flip)
        img.paste(ti, (x + 1, y), ti)
    return img


def export_effects(rom, out):
    from dq5spell import name
    count = 0
    for n in range(EFFECT_COUNT):
        got = effect_lists(rom, n)
        if not got:
            continue
        bg, obj = got
        colors = effect_colors(rom, n)
        imgs = ([effect_image(rom, a, False, colors[0]) for a in bg]
                + [effect_image(rom, a, True, colors[-1]) for a in obj])
        labels = [f'{a & 0xFFFF:04X}' for a in bg] + [f'O{a & 0xFFFF:04X}' for a in obj]
        cw, ch = max(i.width for i in imgs), max(i.height for i in imgs)
        title = name(rom, n)
        stem = f'{n:02X}-{title}' if title else f'{n:02X}'
        out.save(sheet(imgs, max(1, min(len(imgs), 480 // (cw + 1))), max(cw, 28), ch, labels, bg=(0, 0, 0),
                       label_h=10), f'gfx/effects/{stem}.png', 'effects', f'{n:02X} {title}', '전투 연출', action=f'{n:02X}',
                 bg=[f'{a:06X}' for a in bg], obj=[f'{a:06X}' for a in obj],
                 note='조각 목록 차례대로(O 는 OBJ 조각). 놓는 자리와 움직임은 빠짐. 색은 29:FACF 의 첫 묶음(BG3)·마지막 묶음(OBJ)')
        count += 1
    print(f'effects {count}')


EXPORTS = {'maps': export_maps, 'chr': export_chr, 'field': export_field, 'anim': export_anim,
           'monsters': export_monsters, 'battlebg': export_battlebg, 'font': export_font, 'ui': export_ui,
           'worldmap': export_world_screen, 'credits': export_credits,
           'windows': export_windows, 'theend': export_the_end, 'battlewin': export_battle_windows,
           'title': export_title, 'menus': export_menu_screens, 'effects': export_effects}
COMMAND = 'uv run --locked python sfc/dq5/tools/dq5gallery.py rom/dq5.sfc --out $OUT'


def export_all(rom, root, only=None, maps=None, rom_sha='', command=COMMAND):
    out = Out(root, rom_sha)
    for k, fn in EXPORTS.items():
        if only and k not in only:
            continue
        if k == 'maps':
            fn(rom, out, maps)
        else:
            fn(rom, out)
    out.finish(command)
    return out.items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/dq5gfx', help='분류 폴더(maps/ field/ …)를 만들 곳')
    ap.add_argument('--only', help='쉼표로: ' + ','.join(EXPORTS))
    ap.add_argument('--maps', help='쉼표로 맵만 골라서: 02/06,51/50')
    ap.add_argument('--check', nargs=2, metavar=('DUMP', 'BC/BD'),
                    help='dq5gfxdump.lua 덤프(경로/fNNNNN)의 BG 화면과 맵 그림을 픽셀째 비교')
    ap.add_argument('--set', type=lambda v: int(v, 16), help='--check 에서 팔레트 세트를 직접(16진)')
    ap.add_argument('--night', action='store_true', help='--check 에서 밤 팔레트')
    args = ap.parse_args()
    data = open(args.rom, 'rb').read()
    rom = Rom(data)
    if args.check:
        bc, bd = (int(v, 16) for v in args.check[1].split('/'))
        x, y, hit, n = check(rom, args.check[0], bc, bd, args.set, args.night)
        print(f'{bc:02X}/{bd:02X}: 화면 왼쪽 위 = 맵 ({x},{y}) 픽셀, 맵 안 BG 픽셀 {hit}/{n} 같음')
        return 0 if hit == n else 1
    only = set(args.only.split(',')) if args.only else None
    maps = {tuple(int(v, 16) for v in m.split('/')) for m in args.maps.split(',')} if args.maps else None
    items = export_all(rom, args.out, only, maps, hashlib.sha1(data).hexdigest(),
                       'uv run --locked python sfc/dq5/tools/dq5gfx.py rom/dq5.sfc --out $OUT')
    print(f'{len(items)} items -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
