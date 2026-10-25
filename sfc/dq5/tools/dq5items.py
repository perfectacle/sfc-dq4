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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--medals', action='store_true')
    ap.add_argument('--slots', action='store_true')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        check(rom)
    elif args.medals:
        medals(rom)
    elif args.slots:
        slots(rom)
    else:
        for m, kind, (x, y), flag, v, is_chest in all_entries(rom):
            print(f'{m} {kind} ({x},{y}) {flag} {chest.describe(rom, v, chest=is_chest)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
