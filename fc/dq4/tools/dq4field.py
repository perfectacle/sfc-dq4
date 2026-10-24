"""DQ4(FC) 필드(세계 지도) 풀기. 형식은 fc/dq4/docs/dq4-field-format.md.

사용:
  python fc/dq4/tools/dq4field.py rom/dq4.nes check            필드 3개의 줄마다 X=80·끝 기준점이 맞는지
  python fc/dq4/tools/dq4field.py rom/dq4.nes F [--png out.png] 필드 F 를 글자 격자(또는 회색조 그림)로
  python fc/dq4/tools/dq4field.py rom/dq4.nes compare lk.txt     fc/dq4/tools/lua/fieldlookup.lua 기록과 비교
  python fc/dq4/tools/dq4field.py rom/dq4.nes entrances          필드 → 마을 입구 74개

근거 루틴(뱅크 0F): $D259(좌표 → 타일), $D2AA(좌표 −3, 범위 밖은 0), $D2DC(줄 레코드),
$D326·$D37E(줄 RLE 앞·뒤로 읽기), $D516(이벤트로 바뀌는 한 칸). 데이터는 뱅크 0B.
"""
import sys

from kr_patch.fc import ines

BANK = 0x0B
SIZE_W, SIZE_H = 0xD2D6, 0xD2D9   # 0F: 필드마다 폭·높이


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def size(prg, f):
    return rd(prg, 0x0F, SIZE_W + f), rd(prg, 0x0F, SIZE_H + f)


def row_record(prg, f, y):
    base = rd(prg, BANK, 0x8000 + 2 * f) | rd(prg, BANK, 0x8001 + 2 * f) << 8
    a = base + 4 * y
    return [rd(prg, BANK, a + i) for i in range(4)]


def decode_row(prg, f, y):
    """줄 하나를 앞에서부터 풀어 (타일 목록, X=80 이 시작된 바이트 위치, 끝 바이트 위치)."""
    r = row_record(prg, f, y)
    ptr = r[0] | r[1] << 8
    w, _ = size(prg, f)
    out, i, at80 = [], 0, None
    while len(out) < max(w, 0x100) and len(out) < 0x100:
        if len(out) == 0x80 and at80 is None:
            at80 = i
        b = rd(prg, BANK, ptr + i)
        i += 1
        if b >> 5 != 7:
            out += [b >> 5] * ((b & 0x1F) + 1)
        elif b & 0x1F < 8:
            out += [7] * ((b & 0x1F) + 1)
        else:
            out.append(b & 0x1F)
    return out, r, at80, i


def decode(prg, f):
    w, h = size(prg, f)
    return [decode_row(prg, f, y)[0][:w] for y in range(h)]


def check(prg):
    bad = 0
    for f in range(3):
        w, h = size(prg, f)
        for y in range(h):
            out, r, at80, end = decode_row(prg, f, y)
            if (w > 0x80 and (at80 != r[2] or len(out) != 0x100 or end != r[3])):
                bad += 1
                print(f'필드 {f} 줄 {y}: X=80 위치 {at80} / 표 {r[2]}, 끝 {end} / 표 {r[3]}, 칸 {len(out)}')
        print(f'필드 {f}: {w}×{h}')
    print(f'기준점 다름 {bad}곳')
    return bad == 0


def lookup(grid, w, h, x, y):
    """$D2AA: 좌표에서 3 을 뺀 값이 폭·높이를 넘으면 0, 아니면 원래 좌표의 칸."""
    if (x - 3) & 0xFF >= w or (y - 3) & 0xFF >= h:
        return 0
    return grid[y][x]


def compare(prg, path):
    """fc/dq4/tools/lua/fieldlookup.lua 의 lk.txt(X Y 결과 필드) 와 비교."""
    grids = {}
    n = bad = 0
    for ln in open(path):
        x, y, got, f = (int(v, 16) for v in ln.split())
        if f not in grids:
            grids[f] = (decode(prg, f), *size(prg, f))
        g, w, h = grids[f]
        n += 1
        bad += lookup(g, w, h, x, y) != got
    print(f'조회 {n}번 중 {bad} 다름')
    return bad == 0


ENTRANCE_PTR = (0x0E, 0x8004)   # BRK 82 E7 = 뱅크 0E 함수 2 의 주소(08:$AEE2)
ARRIVE_PTR = (0x08, 0xB7F7)


def entrances(prg):
    """필드 → 마을 입구. 08:$AEE8 이 필드 좌표($42, $43)와 같은 3바이트 레코드(그룹, X, Y)를 찾고,
    08:$B037 이 같은 그룹의 5바이트 도착 레코드(그룹, bit6-5 필드·bit4-0 순번, X, Y, 방향)를 고른다."""
    def ptr(bank, at):
        return rd(prg, bank, at) | rd(prg, bank, at + 1) << 8
    arrive = {}
    a = ptr(*ARRIVE_PTR)
    while (g := rd(prg, 0x08, a)) != 0xFF:
        r = [rd(prg, 0x08, a + i) for i in range(5)]
        arrive.setdefault(g, r)
        a += 5
    out = []
    a = ptr(*ENTRANCE_PTR)
    while (g := rd(prg, 0x0E, a)) != 0xFF:
        fx, fy = rd(prg, 0x0E, a + 1), rd(prg, 0x0E, a + 2)
        r = arrive.get(g)
        out.append((g, fx, fy) + ((r[1] & 0x1F, r[2], r[3], r[4], r[1] >> 5 & 3) if r else (None,) * 5))
        a += 3
    return out


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    if sys.argv[2] == 'check':
        sys.exit(0 if check(prg) else 1)
    if sys.argv[2] == 'entrances':
        for g, fx, fy, k, x, y, d, f in entrances(prg):
            print(f'필드 ({fx:02X},{fy:02X}) → {g:02X}/{k:02X} ({x:02X},{y:02X}) 방향 {d} 필드 {f}' if k is not None
                  else f'필드 ({fx:02X},{fy:02X}) → 그룹 {g:02X} (도착 레코드 없음)')
        return
    if sys.argv[2] == 'compare':
        sys.exit(0 if compare(prg, sys.argv[3]) else 1)
    f = int(sys.argv[2])
    grid = decode(prg, f)
    if '--png' in sys.argv:
        from PIL import Image
        w, h = size(prg, f)
        im = Image.new('L', (w, h))
        im.putdata([v * 8 for row in grid for v in row])
        im.save(sys.argv[sys.argv.index('--png') + 1])
        return
    chars = '0123456789ABCDEFGHIJKLMNOPQRSTUV'
    for row in grid:
        print(''.join(chars[v] for v in row))


if __name__ == '__main__':
    main()
