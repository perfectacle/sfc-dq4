"""DQ4(FC) 필드(세계 지도) 풀기. 형식은 fc/dq4/docs/dq4-field-format.md.

사용:
  python fc/dq4/tools/dq4field.py rom/dq4.nes check            필드 3개의 줄마다 X=80·끝 기준점이 맞는지
  python fc/dq4/tools/dq4field.py rom/dq4.nes F [--png out.png] 필드 F 를 글자 격자(또는 회색조 그림)로
  python fc/dq4/tools/dq4field.py rom/dq4.nes compare lk.txt     fc/dq4/tools/lua/fieldlookup.lua 기록과 비교
  python fc/dq4/tools/dq4field.py rom/dq4.nes entrances          필드 → 마을 입구 74개
  python fc/dq4/tools/dq4field.py rom/dq4.nes places             ルーラ 목적지 레코드 32개와 장소 이름·그룹

근거 루틴(뱅크 0F): $D259(좌표 → 타일), $D2AA(좌표 −3, 범위 밖은 0), $D2DC(줄 레코드),
$D326·$D37E(줄 RLE 앞·뒤로 읽기), $D516(이벤트로 바뀌는 한 칸). 데이터는 뱅크 0B.
"""
import sys

from kr_patch.fc import ines

BANK = 0x0B
FIELDS = (0, 1, 3)               # $65 에 쓰이는 값(08:$AF96·1E:$AE59 의 표, 그 밖은 0·1 상수). 2 는 쓰이지 않는다
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


def read(prg, addr):
    """뱅크 0B 를 끼운 CPU 주소의 바이트. $C000 위는 고정 뱅크 0F, $8000 아래(RAM·레지스터)는 None."""
    if addr >= 0xC000:
        return rd(prg, 0x0F, addr)
    if addr >= 0x8000:
        return rd(prg, BANK, addr)
    return None


def cell(prg, f, x, y):
    """$D259 를 그대로 따른 칸 하나(이벤트로 바뀌는 $D516 은 빼고). 롬 밖을 읽으면 None.
    $D2AA: X−3·Y−3 이 폭·높이 이상이면 0. $D2DC: X 가 00~3F 면 줄 처음부터, 40~BF 는 X=80 기준점,
    C0~FF 는 줄 끝 기준점부터. $D326 은 앞으로, X 의 bit6 이 켜진 40~7F·C0~FF 는 $D37E 가 기준점에서 거꾸로 읽는다.
    셈은 게임처럼 8비트로 돈다."""
    w, h = size(prg, f)
    if (x - 3) & 0xFF >= w or (y - 3) & 0xFF >= h:
        return 0
    base = (rd(prg, BANK, 0x8000 + 2 * f) | rd(prg, BANK, 0x8001 + 2 * f) << 8) + 4 * y
    rec = [read(prg, base + i) for i in range(4)]
    if None in rec:
        return None
    ptr = rec[0] | rec[1] << 8
    off = 0 if x < 0x40 else rec[2] if x < 0xC0 else rec[3]
    if not x & 0x40:                       # $D326: 앞으로
        pos = (0x80 if x & 0x80 else 0) - 1 & 0xFF
        while True:
            b = read(prg, ptr + off)
            if b is None:
                return None
            off += 1
            if b >> 5 == 7 and b & 0x1F >= 8:
                pos = pos + 1 & 0xFF
                tile = b & 0x1F
            else:
                pos = pos + (b & 0x1F) + 1 & 0xFF
                tile = 7 if b >> 5 == 7 else b >> 5
            if pos >= x:
                return tile
    pos = (0 if x & 0x80 else 0x80) - 1 & 0xFF   # $D37E: 기준점 바로 앞 칸부터 거꾸로
    while True:
        off -= 1
        b = read(prg, ptr + off)
        if b is None:
            return None
        single = b >> 5 == 7 and b & 0x1F >= 8
        pos = pos - (1 if single else (b & 0x1F) + 1) & 0xFF
        if pos < x:
            return b & 0x1F if single else 7 if b >> 5 == 7 else b >> 5


def decode(prg, f):
    """게임이 찾을 수 있는 칸 전부: 줄 0~(높이+2), 칸 0~(폭+2). $D2AA 가 좌표 −3 으로 범위를 보므로 가장자리 +2 칸까지
    줄 데이터를 읽고, 0~2 번째 줄·칸은 0 이다. 롬 밖을 읽는 칸(쓰이지 않는 필드 2)은 0 으로 채운다."""
    w, h = size(prg, f)
    return [[cell(prg, f, x, y) or 0 for x in range(min(w + 3, 0x100))] for y in range(min(h + 3, 0x100))]


def extent(prg, f):
    """줄 데이터가 실제로 있는 범위 (칸 수, 줄 수). 줄 포인터가 앞 줄 바로 뒤를 잇는 데까지를 줄로, 그 줄들이 제 바이트로
    푸는 칸 수의 최솟값을 칸으로 친다. 폭·높이 +3 을 넘지 않는다. 필드 3 은 폭·높이 자리($D2D9·$D2DC)가 코드 바이트라
    범위 검사가 넓고, 그 밖은 다음 줄 데이터를 읽는다."""
    w, h = size(prg, f)
    base = rd(prg, BANK, 0x8000 + 2 * f) | rd(prg, BANK, 0x8001 + 2 * f) << 8
    ptrs = []
    for y in range(min(h + 3, 0x100) + 1):
        lo, hi = read(prg, base + 4 * y), read(prg, base + 4 * y + 1)
        if lo is None or hi is None:
            break
        ptrs.append(lo | hi << 8)
    rows, cols = 1, 0x100
    while rows < len(ptrs) and 0 < ptrs[rows] - ptrs[rows - 1] < 0x100:
        n = 0
        for a in range(ptrs[rows - 1], ptrs[rows]):
            b = read(prg, a)
            n += 1 if b >> 5 == 7 and b & 0x1F >= 8 else (b & 0x1F) + 1
        cols = min(cols, n)
        rows += 1
    return min(w + 3, cols), min(h + 3, rows)


def check(prg):
    bad = 0
    for f in FIELDS:
        w, h = size(prg, f)
        cols, rows = extent(prg, f)
        for y in range(rows):
            out, r, at80, end = decode_row(prg, f, y)
            if (cols > 0x80 and (at80 != r[2] or len(out) != 0x100 or end != r[3])):
                bad += 1
                print(f'필드 {f} 줄 {y}: X=80 위치 {at80} / 표 {r[2]}, 끝 {end} / 표 {r[3]}, 칸 {len(out)}')
        print(f'필드 {f}: {w}×{h}, 데이터 {extent(prg, f)}')
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


RULA_AT = (0x1E, 0xAF00)   # 1E:$AE2E: 목적지 번호 × 7 + $AEFE 의 워드(1E:$AF00)


def places(prg):
    """ルーラ·キメラのつばさ 목적지로 보이는 레코드 32개(1E:$AE19~, 코드 읽기). 목적지 번호 A 를 받아(FF→1F, FE→1E)
    7바이트 레코드를 읽는다. 바이트 0 bit7 이 꺼져 있으면 필드: bit1-0 → $65, 1·2 → $42·$43, 3·4 → $6195·$6196,
    5·6 → $6197·$6198(5 가 FF 면 그대로). 켜져 있으면 맵: 1·2 → $44·$45, 3·4 → $63·$64.
    번호 0~1B 는 장소 이름표(0B:$B634, ID = 목록 순번 − 1)와 같은 순서다. 필드 레코드의 그룹은 같은 필드에서
    가장 가까운 입구(2칸 이내)의 그룹으로 잇는다."""
    from dq4data import name_list
    from dq4text import text
    names = [text(n) for n in name_list(prg, 'place')[1:]]
    ents = entrances(prg)
    out = []
    for i in range(0x20):
        r = [rd(prg, RULA_AT[0], RULA_AT[1] + 7 * i + j) for j in range(7)]
        e = {'index': i, 'name': names[i] if i < len(names) else '', 'raw': r}
        if r[0] & 0x80:
            e.update(kind='map', x=r[1], y=r[2], group=r[3], map=r[4])
        else:
            f = r[0] & 3
            near = sorted((abs(fx - r[1]) + abs(fy - r[2]), g) for g, fx, fy, *_, ff in entrances_on(ents, f))
            e.update(kind='field', field=f, x=r[1], y=r[2], ship=r[3:5], balloon=None if r[5] == 0xFF else r[5:7],
                     group=near[0][1] if near and near[0][0] <= 2 else None)
        out.append(e)
    return out


def entrances_on(ents, f):
    """도착 레코드의 필드 번호가 f 인 입구(도착 레코드가 없는 입구는 필드 0)."""
    return [e for e in ents if (e[7] or 0) == f]


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    if sys.argv[2] == 'check':
        sys.exit(0 if check(prg) else 1)
    if sys.argv[2] == 'entrances':
        for g, fx, fy, k, x, y, d, f in entrances(prg):
            print(f'필드 ({fx:02X},{fy:02X}) → {g:02X}/{k:02X} ({x:02X},{y:02X}) 방향 {d} 필드 {f}' if k is not None
                  else f'필드 ({fx:02X},{fy:02X}) → 그룹 {g:02X} (도착 레코드 없음)')
        return
    if sys.argv[2] == 'places':
        for e in places(prg):
            to = (f"맵 {e['group']:02X}/{e['map']:02X} ({e['x']:02X},{e['y']:02X})" if e['kind'] == 'map' else
                  f"필드 {e['field']} ({e['x']:02X},{e['y']:02X}) → " + ('그룹 ?' if e['group'] is None else f"그룹 {e['group']:02X}"))
            print(f"{e['index']:02X} {e['name'] or '-':<10} {to}")
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
