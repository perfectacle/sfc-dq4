"""VRAM 덤프(64KB)에서 BG3 타일맵이 가리키는 타일과 비어 있는 타일 칸을 센다. 결과는 sfc/dq4/docs/dq4-window-names.md.

DQ5 엔진의 BG3 은 글자 바탕 VRAM 워드 1000(타일 000~17F), 타일맵 워드 1C00(32×32)이다(dq5-hangul-format.md).
타일 번호는 타일맵 칸의 아래 10비트다. 타일맵이 가리키지 않는 칸을 「그 순간 빈 칸」 으로 보고, 그 칸의 그림이
모두 0 인지도 함께 적는다. 한 순간의 덤프라 그 장면의 다른 순간에 쓰는 칸은 따로 견줘야 한다.

  python sfc/dq4/tools/dq4bg3tiles.py 장면=v00100.bin ...
"""
import sys

CHR = 0x1000 * 2          # 바이트 오프셋
MAP = 0x1C00 * 2
TILES = 0x180


def referenced(vram):
    out = {}
    for i in range(32 * 32):
        e = vram[MAP + i * 2] | vram[MAP + i * 2 + 1] << 8
        t = e & 0x3FF
        out[t] = out.get(t, 0) + 1
    return out


def blank(vram, t):
    o = CHR + t * 16
    return not any(vram[o:o + 16])


def runs(tiles):
    """정렬된 타일 번호 → [(시작, 끝)] 이어진 구간."""
    out = []
    for t in sorted(tiles):
        if out and t == out[-1][1] + 1:
            out[-1][1] = t
        else:
            out.append([t, t])
    return out


def scene(vram):
    ref = referenced(vram)
    used = {t for t in ref if t < TILES}
    free = [t for t in range(1, TILES) if t not in used]
    return ref, used, free


def fmt(rs):
    return ' '.join(f'{a:03X}' if a == b else f'{a:03X}~{b:03X}' for a, b in rs)


def main():
    for arg in sys.argv[1:]:
        name, path = arg.split('=', 1)
        with open(path, 'rb') as f:
            vram = f.read()
        ref, used, free = scene(vram)
        above = sorted(t for t in ref if t >= TILES)
        print(f'{name}: 쓰는 칸 {len(used)}, 빈 칸 {len(free)}(그림 0 인 칸 {sum(blank(vram, t) for t in free)})')
        print(f'  쓰는 칸 {fmt(runs(used))}')
        print(f'  빈 칸   {fmt(runs(free))}')
        if above:
            print(f'  17F 넘는 번호 {fmt(runs(above))}')


if __name__ == '__main__':
    main()
