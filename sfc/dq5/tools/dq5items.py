"""DQ5(SFC) 맵에 숨은 물건 전부, 작은 메달 자리, 카지노 슬롯 기계. 형식은 sfc/dq5/docs/dq5-map-format.md 의
「보물상자와 タンス·ツボ·タル」, sfc/dq5/docs/dq5-data-format.md 의 「작은 메달」「교회·코인 판매·맡기는 곳·카지노」.

표 넷(상자 1E:EF90·1E:EE4E, タンス 류 1F:F5CB, 발밑 1E:F08B, 두 칸 앞 1E:F435)은 dq5chest.py 가 읽고, 여기서는
맵별로 합치고 필드의 숨은 물건(12:E5F2 에 박힌 ルラムーンそう 한 곳)을 더한다.
--check 는 모든 실내 맵의 셀 버퍼(맵별 루틴 반영)에서 상자·タンス·ツボ·タル 칸을 세어 표와 맞춰 본다.

사용:
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc            # 맵별 전부
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc --check    # 칸과 표 맞추기
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc --medals   # ちいさなメダル 자리
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc --slots    # 슬롯 기계 9대
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc --slot-odds          # 기계마다 배당 확률과 코인 한 장당 기대 수익
  python sfc/dq5/tools/dq5items.py rom/dq5.sfc --slot-stop 1 0,24,24,216,288 0,1,1,6,0
                                                          # 기계 1, 시작 $1294 다섯, 릴마다 난수 → 멈출 $1294 와 배당
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import dq5chest as chest  # noqa: E402
from dq5exit import apply_hook  # noqa: E402
from dq5gfx import map_ids  # noqa: E402
from dq5map import Decoder, Rom, map_pointer  # noqa: E402

MEDAL = 0xB5
# 셀 속성(+4 또는 +7) → 종류. 12:E4C9 의 검사 목록.
KINDS = {0x84: '상자', 0x93: 'タンス', 0xA7: 'ツボ', 0xD4: 'ツボ', 0xB9: 'タル', 0xD3: 'タル'}
# 12:E5F2. 필드 (22~23, 166~167) 에서 7E:21A5&04·7E:21AA&01 이 켜져 있고 7E:21B3&10 이 꺼져 있으면 물건 CA 를 주고
# 7E:21B3 에 10 을 켠다.
FIELD_ITEM = ('필드', (22, 166), '7E:21B3&10', 0xCA)
# 11:908A. 슬롯 기계 9대의 레코드 포인터. 레코드 22바이트 = 릴 다섯의 그림 줄 포인터, 한 번에 거는 코인 수, 릴마다 도는 프레임.
SLOT_RECORDS = 0x11908A
SLOT_COUNT = 9
# 25:FD35. 카지노 19/02 의 슬롯 칸 (X, Y) 8개. k 번째 칸이 기계 k+1(12:ED19). 기계 0(100 코인)은 속성 $D8 칸(12:ED3D).
SLOT_CELLS = 0x25FD35
# 11:9044. 그림 6종 × 같은 그림 3·4·5개의 배당(3바이트).
SLOT_PAYOUT = 0x119044
# 11:907A. 릴이 느려질 때 속도(픽셀/프레임) 1~7 마다 그 속도로 도는 프레임 수(2바이트).
SLOT_SLOW = 0x11907A
SLOT_CELL_PX = 24
SYMBOLS = ('7', 'BAR', '셋째', '넷째', '다섯째', '체리')


def all_entries(rom):
    """[(맵 이름, 종류, (x, y), 열림, 내용물 값, 상자인가)]."""
    out = []
    for bc, bd, start, _ in chest.chest_maps(rom):
        for n, xy, v in chest.chests(rom, bc, bd, start):
            flag = f'7E:{(chest.CHEST_FLAGS + (n >> 3)) & 0xFFFF:04X}&{chest.BIT_MASKS[n & 7]:02X}'
            out.append((f'{bc:02X}/{bd:02X}', f'상자 {n}', xy, flag, v, True))
    for bc, bd, x, y, _, v, idx, mask in chest.search_entries(rom):
        out.append((f'{bc:02X}/{bd:02X}', 'タンス류', (x, y), f'7E:{(chest.SEARCH_FLAGS + idx) & 0xFFFF:04X}&{mask:02X}', v, False))
    for bc, bd, x, y, floor, v, idx, mask in chest.foot_entries(rom):
        out.append((f'{bc:02X}/{bd:02X}', f'발밑 층 {floor}', (x, y), f'7E:{(chest.FOOT_FLAGS + idx) & 0xFFFF:04X}&{mask:02X}',
                    v, False))
    for bc, bd, x, y, v, flag, mask in chest.ahead_entries(rom):
        out.append((f'{bc:02X}/{bd:02X}', '두 칸 앞', (x, y), f'7E:{flag & 0xFFFF:04X}&{mask:02X}', v, False))
    name, xy, flag, v = FIELD_ITEM
    out.append((name, '필드 발밑', xy, flag, v, False))
    return sorted(out, key=lambda e: (e[0] != '필드', e[0], e[2][1], e[2][0]))


def container_cells(rom):
    """{(bc, bd): [(x, y, 종류)]}. 그룹 $50 이상 맵 가운데 Decoder 가 풀지 못하는 것은 건너뛴다."""
    out, skipped = {}, []
    for bc, bd in map_ids(rom):
        try:
            w, h, buf, _ = Decoder(rom, 0xBE).decode(map_pointer(rom, bc, bd))
        except IndexError:
            skipped.append((bc, bd))
            continue
        buf = bytearray(buf)
        apply_hook(rom, bc, bd, buf, w)
        for i in range(w * h):
            for off in (4, 7):
                if buf[i * 8 + off] in KINDS:
                    out.setdefault((bc, bd), []).append((i % w, i // w, KINDS[buf[i * 8 + off]], off))
    return out, skipped


def check(rom):
    cells, skipped = container_cells(rom)
    print(f'맵 {len(map_ids(rom)) - len(skipped)}개를 셈(풀지 못한 맵 {len(skipped)}개)')
    print('칸:', dict(Counter(c[2] for v in cells.values() for c in v)))
    table = {(bc, bd): n for bc, bd, _, n in chest.chest_maps(rom)}
    for key, v in sorted(cells.items()):
        found = [c for c in v if c[2] == '상자']
        if len(found) != table.get(key, 0):
            print(f'{key[0]:02X}/{key[1]:02X} 상자 칸 {len(found)}개, 표 {table.get(key, 0)}개:',
                  ' '.join(f'({x},{y}){"+7" if off == 7 else "+4"}' for x, y, _, off in found))
    search = {(e[0], e[1], e[2], e[3]) for e in chest.search_entries(rom)}
    jars = [(key, c) for key, v in cells.items() for c in v if c[2] != '상자']
    filled = [j for j in jars if (*j[0], j[1][0], j[1][1]) in search]
    print(f'タンス·ツボ·タル 칸 {len(jars)}개 중 표 항목이 있는 칸 {len(filled)}개(표 {len(search)}개). '
          f'빈 칸: {dict(Counter(j[1][2] for j in jars if j not in filled))}')
    stray = [e for e in search if not any((*j[0], j[1][0], j[1][1]) == e for j in jars)]
    print('표 항목이 놓였는데 그 종류 칸이 아닌 곳:', stray or '없음')


def medals(rom):
    rows = [e for e in all_entries(rom) if e[4] == MEDAL]
    for m, kind, (x, y), flag, _, _ in rows:
        print(f'{m} {kind} ({x},{y}) {flag}')
    print(f'모두 {len(rows)}개:', dict(Counter(e[1].split()[0] for e in rows)))


def slots(rom):
    cells = [(rom.u8(SLOT_CELLS + k * 2), rom.u8(SLOT_CELLS + k * 2 + 1)) for k in range(8)]
    for m in range(SLOT_COUNT):
        rec = rom.u16(SLOT_RECORDS + m * 2) | 0x110000
        strips = [rom.u16(rec + i * 2) | 0x110000 for i in range(5)]
        bet = rom.u16(rec + 10)
        where = f'({cells[m - 1][0]},{cells[m - 1][1]})' if m else '속성 D8 칸'
        print(f'기계 {m} 19/02 {where} {bet}코인 그림 줄 {strips[0] & 0xFFFF:04X}~')
        for s in strips:
            reel = [rom.u8(s + 1 + i) for i in range(rom.u8(s))]
            print('   ', ' '.join(f'{SYMBOLS[k]}×{reel.count(k)}' for k in range(len(SYMBOLS))))


def slot_machine(rom, m):
    """(그림 줄 다섯, 한 번에 거는 코인 수, 릴마다 일정하게 도는 프레임 다섯)."""
    rec = rom.u16(SLOT_RECORDS + m * 2) | 0x110000
    strips = []
    for i in range(5):
        s = rom.u16(rec + i * 2) | 0x110000
        strips.append([rom.u8(s + 1 + k) for k in range(rom.u8(s))])
    return strips, rom.u16(rec + 10), [rom.u16(rec + 12 + i * 2) for i in range(5)]


def slot_reel_stop(rom, pos, run, r, length):
    """11:B69D(상태)와 11:B7B4(이동)를 프레임마다 그대로 돌려 릴 하나가 멈출 $1294 를 낸다.
    pos 는 돌기 전 $1294, run 은 상태 1 의 프레임 수, r 은 11:B6F3 의 난수(0~7)."""
    slow = [rom.u16(SLOT_SLOW + k * 2) for k in range(8)]
    px = length * SLOT_CELL_PX
    state, speed, timer = 0, 0, 0
    while state < 4:
        if state == 0:
            speed += 1
            if speed >= 8:
                state, timer = 1, run
        elif state == 1:
            timer -= 1
            if timer == 0:
                state, timer = 2, (r + 1) * 3
        elif state == 2:
            timer -= 1
            if timer == 0:
                if speed == 1:
                    state = 3
                else:
                    speed -= 1
                    timer = slow[speed]
        elif pos % SLOT_CELL_PX == 0:
            state, speed = 4, 0
        pos = (pos - speed) % px
    return pos


def slot_pay(rom, strips, idx, lines):
    """멈춘 칸 번호(= $1294 / 24) 다섯과 건 줄 수(1~3)로 11:B82E~B8B1 의 배당 합(표 값, 코인 수를 곱하기 전)."""
    # 줄 1·2·3 = 칸 번호 +1, +0, +2 의 그림(11:B7D2 가 칸마다 세 칸을 $121C 에 늘어놓음).
    total = 0
    for row in (1, 0, 2)[:lines]:
        line = [strips[i][(idx[i] + row) % len(strips[i])] for i in range(5)]
        run, best = 1, None
        for i in range(1, 5):
            run = run + 1 if line[i] == line[i - 1] else 1
            if run >= 3:
                best = (line[i], run)
        if best:
            total += rom.u24(SLOT_PAYOUT + best[0] * 9 + (best[1] - 3) * 3)
    return total


def slot_stop(rom, m, starts, rs):
    strips, bet, runs = slot_machine(rom, m)
    stops = [slot_reel_stop(rom, starts[i], runs[i], rs[i], len(strips[i])) for i in range(5)]
    idx = [p // SLOT_CELL_PX for p in stops]
    print('멈출 $1294:', ' '.join(map(str, stops)), ' 배당(줄 1·2·3):',
          ' '.join(str(slot_pay(rom, strips, idx, n)) for n in (1, 2, 3)))


def slot_odds(rom):
    """릴마다 멈출 칸이 시작 칸에서 「상수 + 난수 + 1」 칸 앞이라, 여러 판을 이어 돌리면 칸 16개가 고르게 나온다고 보고
    16^5 가지를 모두 센다."""
    done, shown = {}, []
    for m in range(SLOT_COUNT):
        strips, bet, runs = slot_machine(rom, m)
        key = tuple(map(tuple, strips))
        if key not in done:
            lens = [len(s) for s in strips]
            counts = [Counter() for _ in range(3)]
            n = 1
            for L in lens:
                n *= L
            for c in range(n):
                idx, k = [], c
                for L in lens:
                    idx.append(k % L)
                    k //= L
                for row in range(3):
                    line = [strips[i][(idx[i] + (1, 0, 2)[row]) % lens[i]] for i in range(5)]
                    run, best = 1, None
                    for i in range(1, 5):
                        run = run + 1 if line[i] == line[i - 1] else 1
                        if run >= 3:
                            best = (line[i], run)
                    counts[row][best] += 1
            done[key] = (counts, n)
        counts, n = done[key]
        first = list(done).index(key)
        ev = sum(rom.u24(SLOT_PAYOUT + b[0] * 9 + (b[1] - 3) * 3) * c for b, c in counts[0].items() if b) / n
        print(f'기계 {m} ({bet}코인) 그림 줄 묶음 {first}: 줄 하나 맞을 확률 {1 - counts[0][None] / n:.4f}, '
              f'코인 한 장당 기대 수익 {ev:.4f}장')
        if not any(o[1] == first for o in shown):
            for sym in range(len(SYMBOLS)):
                print(f'    {SYMBOLS[sym]}', '  '.join(f'×{k} {counts[0][(sym, k)] / n:.6f}' for k in (3, 4, 5)))
        shown.append((m, first))
    print('(줄 1·2·3 은 칸이 한 칸씩 어긋난 같은 분포라 확률이 같음. 여러 줄은 기대 수익이 줄 수에 비례)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--medals', action='store_true')
    ap.add_argument('--slots', action='store_true')
    ap.add_argument('--slot-odds', action='store_true')
    ap.add_argument('--slot-stop', nargs=3, metavar=('MACHINE', 'STARTS', 'RANDS'))
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        check(rom)
    elif args.medals:
        medals(rom)
    elif args.slots:
        slots(rom)
    elif args.slot_odds:
        slot_odds(rom)
    elif args.slot_stop:
        m, starts, rs = args.slot_stop
        slot_stop(rom, int(m), [int(v) for v in starts.split(',')], [int(v) for v in rs.split(',')])
    else:
        for m, kind, (x, y), flag, v, is_chest in all_entries(rom):
            print(f'{m} {kind} ({x},{y}) {flag} {chest.describe(rom, v, chest=is_chest)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
