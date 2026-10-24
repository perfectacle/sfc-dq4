"""NDS 비트맵 폰트(NFTR) 읽기. 형식은 docs/nds-text-format.md 「폰트」.

블록: FINF(글꼴 정보) · CGLP(글리프 비트맵) · CWDH(글자 폭) · CMAP(코드 → 글리프 번호).
비트맵은 글자마다 셀 폭×높이×bpp 비트를 위 줄부터, 한 바이트 안에서는 높은 비트부터 채운다.

사용:
  python tools/ndsfont.py info FONT.nftr
  python tools/ndsfont.py sheet FONT.nftr OUT.png [--codes 4E00-9FFF]
"""
import struct
import sys


class Font:
    def __init__(self, data):
        if data[:4] != b'RTFN':
            raise ValueError('NFTR 가 아님')
        self.d = data
        hsize, nblocks = struct.unpack_from('<HH', data, 0x0C)
        self.blocks = {}
        o = hsize
        for _ in range(nblocks):
            tag = data[o:o + 4][::-1].decode('ascii')
            size = struct.unpack_from('<I', data, o + 4)[0]
            self.blocks.setdefault(tag, []).append(o)
            o += size
        f = self.blocks['FINF'][0]
        self.line_height = data[f + 9]
        g = self.blocks['CGLP'][0]
        (self.cell_w, self.cell_h, self.glyph_size, self.baseline,
         self.max_w, self.bpp, _) = struct.unpack_from('<BBHBBBB', data, g + 8)
        self.glyph_base = g + 16
        self.count = (struct.unpack_from('<I', data, g + 4)[0] - 16) // self.glyph_size
        self.widths = {}
        for c in self.blocks.get('CWDH', []):
            first, last = struct.unpack_from('<HH', data, c + 8)
            for i in range(first, last + 1):
                self.widths[i] = tuple(data[c + 16 + 3 * (i - first):c + 19 + 3 * (i - first)])
        self.cmap = {}
        for c in self.blocks['CMAP']:
            first, last, kind = struct.unpack_from('<HHI', data, c + 8)
            p = c + 20
            if kind == 0:
                base = struct.unpack_from('<H', data, p)[0]
                for code in range(first, last + 1):
                    self.cmap[code] = base + code - first
            elif kind == 1:
                for code in range(first, last + 1):
                    gi = struct.unpack_from('<H', data, p + 2 * (code - first))[0]
                    if gi != 0xFFFF:
                        self.cmap[code] = gi
            elif kind == 2:
                n = struct.unpack_from('<H', data, p)[0]
                for k in range(n):
                    code, gi = struct.unpack_from('<HH', data, p + 2 + 4 * k)
                    self.cmap[code] = gi
            else:
                raise ValueError(f'CMAP 종류 {kind}')

    def glyph(self, index):
        """글리프 비트맵을 [줄][칸] 값(0 = 빈칸) 목록으로."""
        o = self.glyph_base + index * self.glyph_size
        bits = int.from_bytes(self.d[o:o + self.glyph_size], 'big')
        total = self.glyph_size * 8
        mx = (1 << self.bpp) - 1
        px = []
        i = 0
        for _y in range(self.cell_h):
            row = []
            for _x in range(self.cell_w):
                row.append((bits >> (total - (i + 1) * self.bpp)) & mx)
                i += 1
            px.append(row)
        return px

    def glyph_bytes(self, index):
        o = self.glyph_base + index * self.glyph_size
        return self.d[o:o + self.glyph_size]


def sheet(font, codes, out, cols=32, scale=2):
    from PIL import Image
    codes = [c for c in codes if c in font.cmap]
    w, h = font.cell_w + 1, font.cell_h + 1
    rows = (len(codes) + cols - 1) // cols
    img = Image.new('L', (cols * w, max(1, rows) * h), 60)
    mx = (1 << font.bpp) - 1
    for k, code in enumerate(codes):
        px = font.glyph(font.cmap[code])
        ox, oy = (k % cols) * w, (k // cols) * h
        for y, row in enumerate(px):
            for x, v in enumerate(row):
                img.putpixel((ox + x, oy + y), 255 - v * 255 // mx if v else 230)
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(out)


def main(argv):
    cmd, path = argv[0], argv[1]
    font = Font(open(path, 'rb').read())
    if cmd == 'info':
        print(f'cell {font.cell_w}x{font.cell_h} bpp {font.bpp} glyphs {font.count} '
              f'codes {len(font.cmap)} line {font.line_height} baseline {font.baseline}')
        ranges = {}
        for code in font.cmap:
            ranges.setdefault(code >> 8, 0)
            ranges[code >> 8] += 1
        print(' '.join(f'{k:02X}xx:{v}' for k, v in sorted(ranges.items())))
    elif cmd == 'sheet':
        codes = sorted(font.cmap)
        if '--codes' in argv:
            lo, hi = (int(x, 16) for x in argv[argv.index('--codes') + 1].split('-'))
            codes = [c for c in codes if lo <= c <= hi]
        sheet(font, codes, argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
