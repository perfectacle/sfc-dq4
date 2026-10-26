"""DQ5(SFC) 실내 맵 배치 컴파일러. 블록 배치 목록(dq5mapsrc/1)을 배치 명령(put·block·fill)으로 바꿔
dq5mapwrite.py 가 싸는 dq5map/1 JSON 을 만든다. 형식은 sfc/dq5/docs/dq5-build-format.md 의 「배치 목록」.

배치 목록은 [x, y, 블록] 을 칠하는 순서대로 적은 것이다. 블록은 01:8ACB 처럼 원점(왼쪽 위)부터 폭×높이 셀을 덮고,
나중 배치가 먼저 배치를 덮는다. 컴파일러는 같은 결과가 나오는 한에서 순서를 바꾼다.
  1. 셀마다 배치가 쓰는 단위(+1 플래그, 아래층 +2~+4, 위층 +5~+7)를 보고, 끝까지 남는 단위가 없는 배치는 버린다.
  2. 같은 단위를 쓰는 남은 배치끼리의 앞뒤만 지키며, 지금 칠할 수 있는 배치가 가장 많은 블록을 골라 한꺼번에 낸다.
  3. 그 묶음을 블록 크기 간격의 직사각형(3개 이상)은 fill, 나머지는 put 으로 낸다. 버린 배치 자리로 직사각형을 메울 수 있다.
CHR 의 VRAM 슬롯은 블록을 처음 쓰는 순서대로 받으므로(01:8C15) 명령 순서가 바뀌면 셀 버퍼의 타일 워드 값은 달라진다.
그래서 결과는 슬롯을 CHR 번호로 되돌려 견준다.

  extract  맵 → 배치 목록(-o). 머리·속성 패스는 그대로 옮긴다
  compile  배치 목록 → dq5map/1(-o)
  check    맵 전부를 extract → compile 하고, 원래 레코드와 셀 버퍼(슬롯을 CHR 로 되돌린 것)를 견준다

사용:
  python sfc/dq5/tools/dq5mapcompile.py rom/dq5.sfc extract 01 05 -o work/map/0105.src.json
  python sfc/dq5/tools/dq5mapcompile.py rom/dq5.sfc compile work/map/0105.src.json -o work/map/0105.json
  python sfc/dq5/tools/dq5mapcompile.py rom/dq5.sfc check
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Decoder, Rom, block_table, high_block_table, lorom, map_pointer  # noqa: E402
from dq5mapwrite import HEADER, all_maps, dumps, encode, parse, pointer_addr  # noqa: E402

FORMAT = 'dq5mapsrc/1'


def block_sizes(rom, high):
    """블록 번호 → (폭, 높이)."""
    table = high_block_table(rom) if high else block_table(rom)
    out = []
    for a in table:
        b0 = rom.u8(a)
        out.append((((b0 >> 3) & 7) + 1, (b0 & 7) + 1))
    return out


def upper_rows(rom, high, n):
    table = high_block_table(rom) if high else block_table(rom)
    return rom.u8(table[n] + 1) >> 4


def placements(commands, width, sizes):
    """배치 명령 → [x, y, 블록] 칠하는 순서. fill 은 게임과 같이 펼친다(01:A858)."""
    out, block = [], None
    for c in commands:
        if c[0] == 'block':
            block = c[1]
        elif c[0] == 'put':
            out.append([c[1], c[2], block])
        elif c[0] == 'fill':
            w, h = sizes[block]
            start, end = c[2] * width + c[1], c[4] * width + c[3]
            span = c[3] - c[1] + w
            if span <= 0 or span % w:
                raise ValueError(f'fill {c[1:]} 의 폭이 블록 폭 {w} 의 배수가 아님(게임은 끝나지 않음)')
            p = start
            while p <= end:
                for i in range(span // w):
                    q = p + i * w
                    out.append([q % width, q // width, block])
                p += h * width
    return out


def units(x, y, blk, width, sizes, rows_of):
    """배치가 쓰는 단위: 셀마다 +1 플래그(셀*3)와 아래층(셀*3+1) 또는 위층(셀*3+2) 하나(01:8ACB 의 place)."""
    w, h = sizes[blk]
    up = rows_of(blk)
    base = y * width + x
    out = []
    for r in range(h):
        for c in range(w):
            cell = base + r * width + c
            out += [cell * 3, cell * 3 + (2 if r < up else 1)]
    return out


def schedule(places, us):
    """배치 순서를 같은 결과가 나오게 다시 짠다. → ([(블록, 살아 있는 원점들, 메워도 되는 원점들)…]).

    단위마다 마지막에 쓰는 배치가 끝까지 남는다. 단위를 하나라도 끝까지 가진 배치(산 배치)끼리는 같은 단위를
    쓰는 앞뒤 순서를 지키고, 산 배치가 하나도 없는 배치는 버린다. 버린 배치는 그 단위를 나중에 쓰는 배치가 아직
    나오지 않았을 때만 같은 블록 묶음의 직사각형을 메우는 데 다시 쓴다.
    """
    n = len(places)
    owner = {}
    for i in range(n):
        for u in us[i]:
            owner[u] = i
    alive = set(owner.values())
    preds = [set() for _ in range(n)]
    succ = [set() for _ in range(n)]
    last = {}
    later = {}
    for i in range(n):
        for u in us[i]:
            if i in alive:
                j = last.get(u)
                if j is not None and j != i:
                    preds[i].add(j)
                    succ[j].add(i)
                last[u] = i
    # 버린 배치 i 를 쓰려면, i 뒤에 같은 단위를 쓰는 산 배치가 아직 나오지 않아야 한다.
    for i in range(n):
        if i not in alive:
            later[i] = {j for u in us[i] for j in [owner[u]] if j > i}
    done = set()
    ready = {i for i in alive if not preds[i]}
    out = []
    cur = None
    while ready:
        by = {}
        for i in ready:
            by.setdefault(places[i][2], []).append(i)
        blk = cur if cur in by and len(by[cur]) * 2 >= max(len(v) for v in by.values()) else \
            max(by, key=lambda b: (len(by[b]), -b))
        group = by[blk]
        # 덮을 산 배치가 이미 나왔거나 이 묶음 안에 있으면(묶음 안 순서는 정해지지 않음) 쓸 수 없다.
        gone = done | set(group)
        spare = [i for i in later if places[i][2] == blk and not later[i] & gone]
        out.append((blk, [tuple(places[i][:2]) for i in group], [tuple(places[i][:2]) for i in spare]))
        cur = blk
        for i in group:
            ready.discard(i)
            done.add(i)
        for i in group:
            for j in succ[i]:
                preds[j].discard(i)
                if not preds[j] and j not in done:
                    ready.add(j)
    if len(done) != len(alive):
        raise ValueError('배치 순서에 고리가 있음')
    return out


def cover(points, spare, w, h):
    """같은 블록의 원점 집합 → fill 직사각형과 put 들. spare 는 넣어도 되고 빼도 되는 원점(나중 배치에 모두 덮이는 것)이다.
    직사각형은 points·spare 로만 이루고 points 를 하나 이상 품으며, 칸이 3개 이상일 때만 fill 로 낸다."""
    left = set(points)
    free = set(spare) - left
    out = []
    for x, y in sorted(points, key=lambda p: (p[1], p[0])):
        if (x, y) not in left:
            continue
        ok = left | free
        # 가로를 먼저 늘린 것과 세로를 먼저 늘린 것 가운데 산 원점을 더 많이 덮는 쪽.
        n = 1
        while (x + n * w, y) in ok:
            n += 1
        rows = 1
        while all((x + i * w, y + rows * h) in ok for i in range(n)):
            rows += 1
        m = 1
        while (x, y + m * h) in ok:
            m += 1
        cols = 1
        while all((x + cols * w, y + r * h) in ok for r in range(m)):
            cols += 1

        def hits(nn, rr):
            return sum((x + i * w, y + r * h) in left for i in range(nn) for r in range(rr))
        if hits(cols, m) > hits(n, rows):
            n, rows = cols, m
        if n * rows >= 3:
            out.append(['fill', x, y, x + (n - 1) * w, y + (rows - 1) * h])
            for r in range(rows):
                for i in range(n):
                    left.discard((x + i * w, y + r * h))
                    free.discard((x + i * w, y + r * h))
        else:
            out.append(['put', x, y])
            left.discard((x, y))
    return out


def compile_places(src, rom, high):
    sizes = block_sizes(rom, high)
    width = src['width']
    places = src['placements']
    for x, y, blk in places:
        if not 0 <= blk < len(sizes):
            raise ValueError(f'블록 번호 {blk} 가 표 0~{len(sizes) - 1} 밖')
        if not (0 <= x < width and 0 <= y < src['height']):
            raise ValueError(f'배치 ({x},{y}) 가 맵 밖')
    us = [units(x, y, blk, width, sizes, lambda k: upper_rows(rom, high, k)) for x, y, blk in places]
    cmds, cur = [], None
    for blk, pts, spare in schedule(places, us):
        if blk != cur:
            cmds.append(['block', blk])
            cur = blk
        cmds += cover(pts, spare, *sizes[blk])
    cmds.append(['end'])
    doc = {'format': 'dq5map/1', 'map': src['map'], **{k: src[k] for k in HEADER}, 'commands': cmds,
           'passes': src['passes']}
    return doc


def extract(rom, bc, bd):
    high = bc >= 0x50
    doc, _ = parse(rom, map_pointer(rom, bc, bd))
    sizes = block_sizes(rom, high)
    return {'format': FORMAT, 'map': f'{bc:02X}/{bd:02X}', **{k: doc[k] for k in HEADER},
            'placements': placements(doc['commands'], doc['width'], sizes), 'passes': doc['passes']}


def cell_buffer(data, bc, bd, record=None):
    """맵을 풀어 셀 버퍼를 셀마다 튜플로 돌려준다. 층 타일 워드는 (CHR 번호, 반전·팔레트 비트)로 되돌린다.
    record 를 주면 그 레코드를 늘린 자리 30:8000 에 두고 포인터를 바꿔 푼다."""
    if record is not None:
        d = bytearray(data) + bytes(max(0, 0x200000 - len(data)))
        d[0x180000:0x180000 + len(record)] = record
        p = lorom(pointer_addr(Rom(data), bc, bd))
        d[p:p + 3] = (0x308000).to_bytes(3, 'little')
        data = bytes(d)
    rom = Rom(data)
    dec = Decoder(rom, 0xBE, bc >= 0x50)
    dec.preload(bc, bd)
    _, _, buf, _ = dec.decode(map_pointer(rom, bc, bd))
    back = {v & 0x3FF: k for k, v in dec.chr_map.items()}
    out = []
    for o in range(0, len(buf), 8):
        cell = list(buf[o:o + 8])
        for t in (2, 5):
            word = buf[o + t] | buf[o + t + 1] << 8
            cell[t:t + 2] = [(back.get(word & 0x3FF), word & 0xFC00) if word else None, None]
        out.append(tuple(cell))
    return out, dec.slot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('extract', 'compile', 'check'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    rom = Rom(data)
    if a.cmd == 'check':
        bad, old_total, new_total = 0, 0, 0
        for bc, bd in all_maps(rom):
            src = extract(rom, bc, bd)
            doc = compile_places(src, rom, bc >= 0x50)
            rec = encode(doc)
            _, old_len = parse(rom, map_pointer(rom, bc, bd))
            old_total += old_len
            new_total += len(rec)
            want, slots0 = cell_buffer(data, bc, bd)
            got, slots1 = cell_buffer(data, bc, bd, rec)
            if want != got:
                bad += 1
                diff = sum(1 for x, y in zip(want, got) if x != y)
                print(f'{bc:02X}/{bd:02X}: 셀 {diff}칸이 다름')
            elif slots1 > slots0:
                print(f'{bc:02X}/{bd:02X}: 슬롯을 더 씀 {slots0:X} → {slots1:X}')
        print(f'맵 {len(all_maps(rom))}개, 셀 버퍼가 다른 맵 {bad}개, 레코드 {old_total} → {new_total}바이트')
        return 1 if bad else 0
    if a.cmd == 'extract':
        src = extract(rom, int(a.args[0], 16), int(a.args[1], 16))
        s = dumps(src)
    else:
        src = json.load(open(a.args[0], encoding='utf-8'))
        if src.get('format') != FORMAT:
            print(f'오류: format 이 {FORMAT!r} 이 아님', file=sys.stderr)
            return 1
        bc = int(src['map'].split('/')[0], 16)
        try:
            doc = compile_places(src, rom, bc >= 0x50)
            rec = encode(doc)
        except ValueError as e:
            print(f'오류: {e}', file=sys.stderr)
            return 1
        print(f'명령 {len(doc["commands"])}개, 레코드 {len(rec)}바이트', file=sys.stderr)
        s = dumps(doc)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        open(a.out, 'w', encoding='utf-8').write(s + '\n')
    else:
        print(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
