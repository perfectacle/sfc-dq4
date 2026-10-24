"""맵 통행 격자를 글자로 찍는다(경로 잡기용). . 바닥(1) # 벽(8) ^ 가려진 바닥(9) o 가구(+1 bit7) E 출구 셀.

사용: python sfc/dq5/tools/attrgrid.py rom/dq5.sfc BC BD
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5exit import exit_attrs, exit_cells  # noqa: E402
from dq5map import Decoder, Rom, map_pointer  # noqa: E402


def main():
    rom = Rom(open(sys.argv[1], 'rb').read())
    bc, bd = int(sys.argv[2], 16), int(sys.argv[3], 16)
    dec = Decoder(rom, 0xBE)
    w, h, buf, _ = dec.decode(map_pointer(rom, bc, bd))
    exits = set(exit_cells(buf, w, h, exit_attrs(rom)))
    print(f'{bc:02X}/{bd:02X} {w}x{h}')
    print('   ' + ''.join(str(x // 10 % 10) for x in range(w)))
    print('   ' + ''.join(str(x % 10) for x in range(w)))
    for y in range(h):
        row = ''
        for x in range(w):
            c = buf[(y * w + x) * 8 + 1]
            row += 'E' if (x, y) in exits else 'o' if c & 0x80 else {1: '.', 8: '#', 9: '^'}.get(c & 15, '%X' % (c & 15))
        print(f'{y:02d} {row}')


if __name__ == '__main__':
    main()
