"""DQ5(SFC) 실내 맵 디코더. 형식은 sfc/dq5/docs/dq5-map-format.md.

게임의 01:A79A(배치 비트스트림)·01:8ACB(블록 전개)·01:8C15(CHR 슬롯 할당)를 그대로 옮겨,
맵 전환 직후 7EC000- 에 생기는 셀 버퍼(셀당 8바이트)를 만든다.

사용:
  python sfc/dq5/tools/dq5map.py rom/dq5.sfc BC BD [--slot BE] [--compare wram.bin] [--png out.png [--alt] [--cgram cgram.bin]]
--compare 는 01:BA4C(속성 패스 끝)에서 덤프한 WRAM 128KB 와 셀 버퍼를 비교한다.
--png 는 셀 버퍼의 아래층·위층 타일맵을 그린다(Pillow 필요). 팔레트는 10:DE0B 와 같은 방법으로
ROM 에서 만든다. --alt 는 7E:075E >= $F0 일 때의 두 번째 팔레트 목록, --cgram 은 덤프한 CGRAM 을 대신 쓴다.
맵보다 먼저 슬롯을 받는 것들(map_preload)을 거친다. BC 가 50 이상이면 따로 된 포인터·블록·CHR 을 쓴다.
"""
import argparse
import sys

GROUP_TABLE = 0x0F8ED7
# 01:9316 LDY $8ED7,X(DB 0F)와 01:83FB LDA $FD6A,X·01:8400 LDA $FD6B,X(DB 23)의 피연산자. 그룹 표를 옮기면 바뀐다.
POINTER_SITE = 0x019317
ATTR_SITES = (0x0183FC, 0x018401)
ATTR_TABLE = 0x23FD6A
GROUPS = 0x36
BLOCK_BANK = 0x16
# 블록 번호는 늘 11비트(01:ACE5 가 쓰는 1A4D 표는 맵과 무관하게 AC26). 위치 비트 수만 맵 머리 +6 을 따른다.
BLOCK_BITS = 11
# CHR 2개당 1바이트, 니블마다 그 CHR 의 팔레트·우선순위(01:8C43).
CHR_PALETTE = 0x2A8781
CHR_BANK = 0x13
# 10:DE0B 팔레트 로더: [$BC, 기본 세트, ($BD, 세트)..., FF] 표 → 세트마다 목록 2개 → 16색 팔레트 번호 7개.
PALSET_TABLE = 0x10DEBC
PALSET_LISTS = 0x10DFE4
PALETTES = 0x10E5C8
# $BC >= $50 인 맵(01:933D): 그룹 목록 1F:CEB6 + ($BC-$50)*2 → 24비트 포인터 ($BD-$50 번째, 레코드는 뱅크 0F),
# 블록은 17:8369 부터(7E:A000 표, 01:8C72), CHR 은 1F:8000, CHR 팔레트 표는 0F:CF83.
HIGH_GROUPS = 0x1FCEB6
HIGH_BLOCKS = 0x178369
HIGH_CHR_BANK = 0x1F
HIGH_CHR_PALETTE = 0x0FCF83
# 맵을 풀기 전에 CHR 슬롯을 먼저 쓰는 것들(실내 맵 모두). 이 셋을 거친 뒤 맵 블록의 CHR 이 이어서 슬롯을 받는다.
#   04:8131  [BC][BD(bit7 무시, 7F 는 그룹 전체)][플래그(FF 없음)][마스크][24비트][슬롯 수] 8바이트 항목, FF 로 끝. 맞으면 슬롯을 그만큼 건너뜀
#   01:8F06  $BC = 51 이면 02:88A5 의 블록 목록(0 으로 끝)을 먼저 올림(02:8883)
#   03:D3E9  03:D82E [BC][BD][색인] 표에서 맞으면 03:D806+색인 의 16비트 마스크, bit j 마다 03:D786+j*8 의 블록 4개(FFFF 로 끝).
#            표의 첫 항목(17/01)만은 03:D433 이 블록 FD·23D 를 올린다
SLOT_SKIP = 0x04822D
PRELOAD_51 = 0x0288A5
ANIM_MAPS = 0x03D82E
ANIM_MASKS = 0x03D806
ANIM_BLOCKS = 0x03D786
# 01:8F93: 맵을 푼 뒤 셀 +4 에 즉값을 찍는 표. [BC][BD][16비트 목록] 항목(bit7 바이트로 끝),
# 목록은 [셀 주소 24비트(7E:C000-)][칸 수] 를 FF 까지. 2B:BAB5 가 따로 보는 속성이다.
CELL_MARKS = ((0x32, 0x019017), (0x5A, 0x0192A9))


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


class Rom:
    def __init__(self, data):
        self.d = data

    def u8(self, a):
        return self.d[lorom(a)]

    def u16(self, a):
        o = lorom(a)
        return self.d[o] | self.d[o + 1] << 8

    def u24(self, a):
        o = lorom(a)
        return self.d[o] | self.d[o + 1] << 8 | self.d[o + 2] << 16


def next_addr(a):
    """LoROM 에서 1바이트 앞으로. 뱅크 끝($FFFF)이면 다음 뱅크 $8000 으로 넘어간다(01:A9C4 와 같음)."""
    if a & 0xFFFF == 0xFFFF:
        return ((a >> 16) + 1) << 16 | 0x8000
    return a + 1


def group_spans(rom, attr=False):
    """그룹 00~35 의 목록 (시작, 끝) 16비트 주소와 그룹 표 자리. 맵 포인터(3바이트) 또는 맵 속성(attr, 6바이트) 표.
    목록은 이어져 있어 다음 그룹의 시작이 끝이다. 마지막 그룹은 원래 표 바로 앞에서 끝나고, 표를 옮긴 롬은
    표 뒤 끝 표시(55번째 16비트)가 끝이다(dq5newmap.py). 코드 자리가 그 명령이 아니면(코드 없는 합성 롬) 원래 표를 본다."""
    original = ATTR_TABLE if attr else GROUP_TABLE
    table = original
    if attr and rom.u8(ATTR_SITES[0] - 1) == rom.u8(ATTR_SITES[1] - 1) == 0xBD:
        table = ATTR_TABLE & 0xFF0000 | rom.u16(ATTR_SITES[0])
        if rom.u16(ATTR_SITES[1]) != (table + 1) & 0xFFFF:
            raise ValueError('01:83FC·8401 의 맵 속성 표 주소가 서로 맞지 않음')
    elif not attr and rom.u8(POINTER_SITE - 1) == 0xBC:
        table = GROUP_TABLE & 0xFF0000 | rom.u16(POINTER_SITE)
    starts = [rom.u16(table + g * 2) for g in range(GROUPS)]
    end = table & 0xFFFF if table == original else rom.u16(table + GROUPS * 2)
    return list(zip(starts, starts[1:] + [end])), table


def map_pointer(rom, bc, bd):
    if bc >= 0x50:
        group = rom.u16(HIGH_GROUPS + (bc - 0x50) * 2)
        return rom.u24(HIGH_GROUPS & 0xFF0000 | (group + (bd - 0x50) * 3))
    group = group_spans(rom)[0][bc][0]
    return rom.u24(0x0F0000 | (group + bd * 3))


def block_table(rom, count=0x800):
    """7EB000 표: 뱅크 $16 의 $8000 부터 블록을 차례로 놓은 포인터."""
    ptrs, a = [], BLOCK_BANK << 16 | 0x8000
    for _ in range(count):
        ptrs.append(a)
        b0 = rom.u8(a)
        w = ((b0 >> 3) & 7) + 1
        h = (b0 & 7) + 1
        a += 3 + 2 * w * h
        if a & 0xFFFF < 0x8000:
            break
    return ptrs


def high_block_table(rom):
    """01:8C72. $BC >= $50 맵의 7EA000 표: 다음 블록의 +2 가 FF 이면 끝."""
    ptrs, a = [], HIGH_BLOCKS
    while True:
        ptrs.append(a)
        b0 = rom.u8(a)
        a += 3 + 2 * (((b0 >> 3) & 7) + 1) * ((b0 & 7) + 1)
        if rom.u8(a + 2) == 0xFF:
            return ptrs


def map_preload(rom, bc, bd):
    """맵을 풀기 전에 쓰는 (건너뛸 슬롯 수, 먼저 올리는 블록 목록)."""
    skip, a = 0, SLOT_SKIP
    while rom.u8(a) != 0xFF:
        mbd = rom.u8(a + 1) & 0x7F
        if rom.u8(a) == bc and mbd in (bd, 0x7F):
            skip = rom.u8(a + 7)
            break
        a += 8
    blocks = []
    if bc == 0x51:
        a = PRELOAD_51
        while rom.u8(a):
            blocks.append(rom.u8(a))
            a += 1
    a = ANIM_MAPS
    while rom.u8(a) != 0xFF:
        if rom.u8(a) == bc and rom.u8(a + 1) == bd:
            if a == ANIM_MAPS:
                blocks += [0xFD, 0x23D]
                break
            # 03:D460 은 16비트 전부를 밀어 내며 본다(bit15 도 블록 묶음). 7FFF 로 자른 값은 따로 $1ED0 에 둔다.
            mask = rom.u16(ANIM_MASKS + rom.u8(a + 2))
            for j in range(17):
                if mask >> j & 1:
                    for k in range(4):
                        n = rom.u16(ANIM_BLOCKS + j * 8 + k * 2)
                        if n == 0xFFFF:
                            break
                        blocks.append(n)
            break
        a += 3
    return skip, blocks


def high_marks(rom, bc, bd, buf):
    """01:8F93 을 buf(7E:C000- 셀 버퍼)에 적용한다."""
    for value, a in CELL_MARKS:
        while not rom.u8(a) & 0x80:
            if rom.u8(a) == bc and rom.u8(a + 1) == bd:
                p = a & 0xFF0000 | rom.u16(a + 2)
                while rom.u8(p) != 0xFF:
                    cell, n = rom.u24(p) - 0x7EC000, rom.u8(p + 3)
                    for i in range(n):
                        buf[cell + 4 + i * 8] = value
                    p += 4
                break
            a += 4


class Bits:
    """MSB 먼저 읽는 비트 리더. 01:AC66(1비트)·01:AEA4/ACE5(n비트 수)."""

    def __init__(self, rom, addr):
        self.rom, self.a, self.pos = rom, addr, 0

    def bit(self):
        v = (self.rom.u8(self.a) >> (7 - self.pos)) & 1
        self.pos += 1
        if self.pos == 8:
            self.pos = 0
            self.a = next_addr(self.a)
        return v

    def num(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | self.bit()
        return v


class Nibbles:
    """셀 속성 패스의 리더. 01:B8A8·01:B8DD 를 상태($03 의 bit7 = half)까지 그대로 옮겼다."""

    def __init__(self, rom, addr):
        self.rom, self.a, self.half = rom, addr, False

    def nib(self):
        """01:B8A8. 호출한 쪽이 필요한 비트만 골라 쓴다."""
        if not self.half:
            self.half = True
            return self.rom.u8(self.a)
        nxt = next_addr(self.a)
        v = ((self.rom.u8(self.a) << 8 | self.rom.u8(nxt)) >> 4) & 0xFF
        self.a, self.half = nxt, False
        return v

    def byte(self):
        """01:B8DD."""
        if self.half:
            self.a, self.half = next_addr(self.a), False
        else:
            self.half = True
        return self.nib()


def attribute_passes(rom, addr, width, buf, trace=None):
    """비트스트림 뒤의 셀 속성 패스 셋(01:B7AC, 01:B8FE, 01:B9EA). buf 를 고치고 끝 위치를 돌려준다.

    엔트리 첫 바이트 위 2비트: 00 셀 하나, 1x 같은 값을 n+2 칸 반복(bit6=1 이면 n 은 니블, 0 이면 바이트), 01 끝.
    위치는 첫 바이트 아래 6비트와 둘째 바이트로 x 7비트·y 7비트(01:B846).
    """
    n = Nibbles(rom, addr)
    has_pass3 = False
    for kind in (1, 2, 3):
        if trace is not None:
            trace.append(('start', kind, n.a, n.half))
        stride = width * 8 if n.nib() & 0x80 else 8
        first = True
        while True:
            b = n.byte()
            if b & 0xC0 == 0x40:
                # 01:B83D·01:B938: 반 바이트에서 끝났으면 한 니블 더 읽어 맞춘다. 패스 3(01:BA4C)은 하지 않는다.
                if kind != 3 and n.half:
                    n.nib()
                break
            lo = n.byte()
            x = ((b << 8 | lo) << 1 >> 8) & 0x7F
            pos = (lo & 0x7F) * width + x
            if b & 0x80:
                # LDX 횟수 / INX / ... / DEX / BPL 이라 반복은 횟수+2 칸을 칠한다.
                cells = ((n.nib() & 0x0F) if b & 0x40 else n.byte()) + 2
            else:
                cells = 1
            val = n.nib() & 0x0F
            if kind == 3 and first:
                has_pass3 = True
            first = False
            if trace is not None:
                trace.append((kind, x, lo & 0x7F, cells, 'v' if stride != 8 else 'h', val))
            for k in range(cells):
                o = pos * 8 + k * stride
                if kind == 1:
                    buf[o + 1] = buf[o + 1] & 0xF0 | val
                elif kind == 2:
                    if val & 1:
                        if not (buf[o + 5] | buf[o + 6]) and (buf[o + 2] | buf[o + 3]):
                            buf[o + 5:o + 8] = buf[o + 2:o + 5]
                        buf[o] |= 0x08
                    if val & 2:
                        buf[o + 1] |= 0x40
                    if val & 8:
                        buf[o + 4] = 0x61 if val & 4 else 0x62
                    elif val & 4:
                        buf[o + 1] |= 0x80
                else:
                    buf[o] = buf[o] & 0x0F | val << 4
    return n.a, n.half, has_pass3


class Decoder:
    def __init__(self, rom, slot, high=False):
        self.rom = rom
        self.high = high
        self.blocks = high_block_table(rom) if high else block_table(rom)
        self.chr_palette = HIGH_CHR_PALETTE if high else CHR_PALETTE
        self.slot = slot
        self.chr_map = {}
        self.pass_trace = []

    def chr_entry(self, chr_id):
        """01:8C15: CHR 이 처음 쓰일 때 VRAM 슬롯을 순서대로 주고 팔레트를 붙인다."""
        if chr_id not in self.chr_map:
            nib = self.rom.u8(self.chr_palette + (chr_id >> 1))
            pal = ((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4
            self.chr_map[chr_id] = (self.slot | pal << 8) & 0xFFFF
            self.slot += 1
        return self.chr_map[chr_id]

    def preload(self, bc, bd):
        """맵 블록보다 먼저 슬롯을 받는 것들을 게임 순서대로 거친다."""
        skip, blocks = map_preload(self.rom, bc, bd)
        self.slot += skip
        for n in blocks:
            self.load_block(n)

    def load_block(self, n):
        """01:8ACB. 블록 정의를 (높이, 폭, 위층 줄 수, 속성, [줄별 [(플래그, 타일맵 워드)]]) 로 편다."""
        a = self.blocks[n]
        b0, b1, attr = self.rom.u8(a), self.rom.u8(a + 1), self.rom.u8(a + 2)
        h = (b0 & 7) + 1
        w = ((b0 >> 3) & 7) + 1
        upper = b1 >> 4
        flagged_rows = (b1 & 0x0F) >> 1
        base_flag = (b1 & 1) << 6 | (b0 & 0xC0) >> 2
        a += 3
        rows = []
        for r in range(h):
            flag = base_flag | (0x80 if r >= h - flagged_rows else 0)
            row = []
            for _ in range(w):
                v = self.rom.u16(a)
                a += 2
                row.append((flag, self.chr_entry(v & 0x0FFF) | (v & 0xC000)))
            rows.append(row)
        return h, w, upper, attr, rows

    def decode(self, addr, trace=None, stop_after=None):
        """trace 리스트를 주면 명령마다 (시작 주소, 비트 위치, 명령, 인자) 를 쌓는다.
        stop_after 를 주면 그 수만큼 명령을 처리하고 멈춘다(그려지는 과정 시각화용)."""
        rom = self.rom
        width, height, bits = rom.u8(addr + 1), rom.u8(addr + 2), rom.u8(addr + 6)
        # 블록이 맵 아래·오른쪽 끝을 넘어 찍힐 수 있다(게임도 버퍼 밖에 쓴다). 여유를 두고 마지막에 자른다.
        size = width * height * 8
        buf = bytearray(size + width * 8 * 8 + 64)
        stream = Bits(rom, addr + 9)
        block = None

        def place(pos):
            h, w, upper, attr, rows = block
            for r, row in enumerate(rows):
                for c, (flag, word) in enumerate(row):
                    o = (pos + r * width + c) * 8
                    buf[o + 1] = flag
                    t = o + (5 if r < upper else 2)
                    buf[t] = word & 0xFF
                    buf[t + 1] = word >> 8
                    buf[t + 2] = attr
            last_r, last_c = h - 1, w - 1
            o = (pos + last_r * width + last_c) * 8
            buf[o + (7 if last_r < upper else 4)] = attr | 0x80

        b7 = rom.u8(addr + 7)
        if b7 & 0x80:
            # 01:A93F: 머리의 블록으로 맵 전체를 바둑판처럼 먼저 채운다.
            block = self.load_block((b7 & 7) << 8 | rom.u8(addr + 8))
            h, w = block[0], block[1]
            for r in range(0, height, h):
                for c in range(0, width, w):
                    place(r * width + c)

        done = 0
        while stop_after is None or done < stop_after:
            done += 1
            at = (stream.a, stream.pos)
            if not stream.bit():
                pos = stream.num(bits)
                if trace is not None:
                    trace.append((*at, 'put', (pos,)))
                place(pos)
            elif not stream.bit():
                n = stream.num(BLOCK_BITS)
                if trace is not None:
                    trace.append((*at, 'block', (n,)))
                block = self.load_block(n)
            elif not stream.bit():
                start, end = stream.num(bits), stream.num(bits)
                if trace is not None:
                    trace.append((*at, 'fill', (start, end)))
                h, w = block[0], block[1]
                col0 = start % width
                col1 = end % width
                span = col1 - col0 + w
                p = start
                while p <= end:
                    q, left = p, span
                    while True:
                        place(q)
                        q += w
                        left -= w
                        if left == 0:
                            break
                    p += h * width
            else:
                if trace is not None:
                    trace.append((*at, 'end', ()))
                break
        else:
            return width, height, bytes(buf[:size]), stream

        # 01:93D8: 머리 +5 위 니블이 있으면 +0 에, 아래 니블은 +1 에 OR. 폭×높이+1 칸(DEX/BPL 이라 한 칸 더).
        b5 = rom.u8(addr + 5)
        for c in range(width * height + 1):
            if b5 & 0xF0:
                buf[c * 8] = b5 & 0xF0
            buf[c * 8 + 1] |= b5 & 0x0F
        # 01:A7B3: 비트스트림이 바이트 중간에서 끝났으면 다음 바이트부터 속성 패스.
        start = next_addr(stream.a) if stream.pos else stream.a
        self.attr_start = start
        self.end, self.end_half, self.has_pass3 = attribute_passes(rom, start, width, buf, self.pass_trace)
        return width, height, bytes(buf[:size]), stream


def palette_set(rom, bc, bd):
    a = PALSET_TABLE
    while rom.u8(a) != 0xFF:
        if rom.u8(a) == bc:
            default, a = rom.u8(a + 1), a + 2
            while rom.u8(a) != 0xFF:
                if rom.u8(a) == bd:
                    return rom.u8(a + 1)
                a += 2
            return default
        while rom.u8(a) != 0xFF:
            a += 1
        a += 1
    raise KeyError(f'no palette set for $BC={bc:02X}')


def map_cgram(rom, bc, bd, alt=False):
    """BG 팔레트 1~7번 줄과 배경색(0번 줄 색 0)을 채운 CGRAM 앞 256바이트. 나머지 줄은 0."""
    s = palette_set(rom, bc, bd)
    lst = 0x100000 | rom.u16(PALSET_LISTS + s * 4 + (2 if alt else 0))
    cg = bytearray(0x200)
    for r in range(7):
        o = lorom(PALETTES + (rom.u16(lst + r * 2) & 0x7FF) * 32)
        cg[0x20 + r * 32:0x40 + r * 32] = rom.d[o:o + 32]
    # 10:DE9C: 7번 줄부터 2번 줄까지 내려가며 색 0 이 0 이 아닌 첫 줄의 색 0 을 배경색으로.
    for r in range(7, 1, -1):
        if cg[r * 32] | cg[r * 32 + 1]:
            cg[0:2] = cg[r * 32:r * 32 + 2]
            break
    return cg


def chr_pixels(rom, chr_id, high=False):
    """CHR 하나(4bpp 8x8, 32바이트)를 8x8 색 번호로. 01:8C15 가 DMA 하는 원본 위치."""
    a = ((HIGH_CHR_BANK if high else CHR_BANK) + (chr_id >> 10)) << 16 | 0x8000 + (chr_id & 0x3FF) * 32
    o = lorom(a)
    t = rom.d[o:o + 32]
    return [[((t[y * 2] >> (7 - x)) & 1) | ((t[y * 2 + 1] >> (7 - x)) & 1) << 1
             | ((t[16 + y * 2] >> (7 - x)) & 1) << 2 | ((t[17 + y * 2] >> (7 - x)) & 1) << 3
             for x in range(8)] for y in range(8)]


def render(rom, dec, width, height, buf, cgram, path):
    from PIL import Image
    colors = []
    for i in range(256):
        c = cgram[i * 2] | cgram[i * 2 + 1] << 8
        # 5비트 → 8비트는 MesenCE 화면과 같게 (v << 3) | (v >> 2).
        colors.append(tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31)))
    slot_chr = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    cache = {}
    img = Image.new('RGB', (width * 8, height * 8), colors[0])
    px = img.load()
    for layer in (2, 5):
        for cell in range(width * height):
            o = cell * 8 + layer
            word = buf[o] | buf[o + 1] << 8
            if word == 0:
                continue
            chr_id = slot_chr.get(word & 0x3FF)
            if chr_id is None:
                continue
            if chr_id not in cache:
                cache[chr_id] = chr_pixels(rom, chr_id, dec.high)
            pal = (word >> 10) & 7
            cx, cy = cell % width * 8, cell // width * 8
            for y in range(8):
                for x in range(8):
                    v = cache[chr_id][7 - y if word & 0x8000 else y][7 - x if word & 0x4000 else x]
                    if v:
                        px[cx + x, cy + y] = colors[pal * 16 + v]
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', type=lambda s: int(s, 16))
    ap.add_argument('bd', type=lambda s: int(s, 16))
    ap.add_argument('--slot', type=lambda s: int(s, 16), default=0xBE)
    ap.add_argument('--compare')
    ap.add_argument('--png')
    ap.add_argument('--cgram')
    ap.add_argument('--alt', action='store_true')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    addr = map_pointer(rom, args.bc, args.bd)
    dec = Decoder(rom, args.slot, args.bc >= 0x50)
    dec.preload(args.bc, args.bd)
    width, height, buf, stream = dec.decode(addr)
    if dec.high:
        buf = bytearray(buf)
        high_marks(rom, args.bc, args.bd, buf)
    print(f'map {args.bc:02X}/{args.bd:02X} at {addr:06X}: {width}x{height}, '
          f'stream ends {stream.a:06X} bit {stream.pos}, slots {args.slot:X}-{dec.slot:X}')
    if args.png:
        cgram = open(args.cgram, 'rb').read() if args.cgram else map_cgram(rom, args.bc, args.bd, args.alt)
        render(rom, dec, width, height, buf, cgram, args.png)
    if args.compare:
        wram = open(args.compare, 'rb').read()
        ref = wram[0xC000:0xC000 + len(buf)]
        diff = [i for i in range(len(buf)) if buf[i] != ref[i]]
        print(f'compare: {len(diff)} bytes differ of {len(buf)}')
        for i in diff[:20]:
            cell, off = divmod(i, 8)
            print(f'  cell {cell} ({cell % width},{cell // width}) +{off}: ours {buf[i]:02X} game {ref[i]:02X}')
        return 1 if diff else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
