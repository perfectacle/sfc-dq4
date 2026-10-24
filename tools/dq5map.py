"""DQ5(SFC) 실내 맵 디코더. 형식은 docs/dq5-map-format.md.

게임의 01:A79A(배치 비트스트림)·01:8ACB(블록 전개)·01:8C15(CHR 슬롯 할당)를 그대로 옮겨,
맵 전환 직후 7EC000- 에 생기는 셀 버퍼(셀당 8바이트)를 만든다.

사용:
  python tools/dq5map.py rom/dq5.sfc BC BD [--slot BE] [--compare wram.bin] [--png out.png --cgram cgram.bin]
--compare 는 01:A833(디코더 끝)에서 덤프한 WRAM 128KB 와 셀 버퍼를 비교한다.
--png 는 셀 버퍼의 아래층·위층 타일맵을 그린다(Pillow 필요). 팔레트는 아직 ROM 위치를 몰라
그 맵을 띄운 상태의 CGRAM 덤프(512바이트)를 받는다.
"""
import argparse
import sys

GROUP_TABLE = 0x0F8ED7
BLOCK_BANK = 0x16
# 블록 번호는 늘 11비트(01:ACE5 가 쓰는 1A4D 표는 맵과 무관하게 AC26). 위치 비트 수만 맵 머리 +6 을 따른다.
BLOCK_BITS = 11
# CHR 2개당 1바이트, 니블마다 그 CHR 의 팔레트·우선순위(01:8C43).
CHR_PALETTE = 0x2A8781
CHR_BANK = 0x13


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


def map_pointer(rom, bc, bd):
    group = rom.u16(GROUP_TABLE + bc * 2)
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


class Decoder:
    def __init__(self, rom, slot):
        self.rom = rom
        self.blocks = block_table(rom)
        self.slot = slot
        self.chr_map = {}

    def chr_entry(self, chr_id):
        """01:8C15: CHR 이 처음 쓰일 때 VRAM 슬롯을 순서대로 주고 팔레트를 붙인다."""
        if chr_id not in self.chr_map:
            nib = self.rom.u8(CHR_PALETTE + (chr_id >> 1))
            pal = ((nib & 0x0F) + 1) * 4 if chr_id & 1 else ((nib & 0xF0) >> 2) + 4
            self.chr_map[chr_id] = (self.slot | pal << 8) & 0xFFFF
            self.slot += 1
        return self.chr_map[chr_id]

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
        return width, height, bytes(buf[:size]), stream


def chr_pixels(rom, chr_id):
    """CHR 하나(4bpp 8x8, 32바이트)를 8x8 색 번호로. 01:8C15 가 DMA 하는 원본 위치."""
    a = (CHR_BANK + (chr_id >> 10)) << 16 | 0x8000 + (chr_id & 0x3FF) * 32
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
                cache[chr_id] = chr_pixels(rom, chr_id)
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
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    addr = map_pointer(rom, args.bc, args.bd)
    dec = Decoder(rom, args.slot)
    width, height, buf, stream = dec.decode(addr)
    print(f'map {args.bc:02X}/{args.bd:02X} at {addr:06X}: {width}x{height}, '
          f'stream ends {stream.a:06X} bit {stream.pos}, slots {args.slot:X}-{dec.slot:X}')
    if args.png:
        render(rom, dec, width, height, buf, open(args.cgram, 'rb').read(), args.png)
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
