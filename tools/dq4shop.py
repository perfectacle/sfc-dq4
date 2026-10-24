"""DQ4(FC) 상점 품목·여관 값·가게 종류. 형식은 docs/dq4-shop-format.md.

사용:
  python tools/dq4shop.py rom/dq4.nes              무기·방어구·도구 가게 목록 전부와 여관 표
  python tools/dq4shop.py rom/dq4.nes G K          맵(그룹 $63/순번 $64)의 가게 목록, 여관 값, 대화 번호가 0~6 인 가게 인물
  python tools/dq4shop.py rom/dq4.nes G K --compare end.ram   seq.lua 의 RAM 덤프로 가게 창 목록($07BD) 비교

근거 루틴(코드 읽기와 실측):
  15:$9962  대화 결과 $00:$01 이 7 미만이면 가게 처리 15:$9CBF 로 간다.
            1 무기($B84A) 2 도구($B858) 3 방어구($B851) → $07C5 에 종류, 4 맡기는 곳($BBF0), 5 교회($B550), 6 여관($BF28).
  15:$B217  목록 표 포인터 18:$802C + 2 × (종류 − 1). 15:$B2CB 가 (그룹, 순번) 을 찾고, 품목을 bit7 이
            켜진 바이트까지 $07BD 에 담는다(개수 $07C4). FF 는 어느 맵에나 맞는 기본 줄(그룹만, 순번 없음).
  15:$B26B  덧붙임: 16/00 무기점은 $62E7~$62E9 가 0 이 아닌 만큼 15:$A4A4 의 품목을 뒤에 붙이고,
            09/00 무기점은 $62ED < $78 일 때 목록을 06 23 07 10 으로 바꾼다.
  15:$BF71  여관 표 18:$B5CD(BRK 87 8F 가 꺼내는 18 함수 07 의 주소): 그룹, 순번, 1인 값. FF 로 끝남.
            그룹 10 에서 $45 < $14 이면 표 대신 10. 값 × (BRK 62 23 01 이 돌려준 A) 가 요금(0F:$C827).
"""
import sys

from kr_patch.fc import ines

import dq4data
import dq4map
import dq4talk

TABLE_BANK = 0x18
LIST_PTRS = 0x802C
KINDS = {1: '무기', 2: '도구', 3: '방어구'}
TALK_KINDS = {0: '교회', 1: '무기', 2: '도구', 3: '방어구', 4: '맡기는 곳', 5: '교회', 6: '여관'}
INN_TABLE = 0xB5CD
CODE_BANK = 0x15
EXTRA_16 = 0xA4A4              # 16/00 무기점 덧붙임 품목 3개($62E7~$62E9 와 짝)
NIGHT_09 = (0x06, 0x23, 0x07, 0x10)
INN_10_PRICE = 0x0A
SHOP_RAM, COUNT_RAM, KIND_RAM = 0x07BD, 0x07C4, 0x07C5


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def list_start(prg, kind):
    return rd(prg, TABLE_BANK, LIST_PTRS + 2 * (kind - 1)) | rd(prg, TABLE_BANK, LIST_PTRS + 2 * kind - 1) << 8


def shop_lists(prg, kind):
    """[(그룹, 순번 또는 None, [품목 ID])]. 15:$B2CB 처럼 읽되, 다른 종류의 목록이 시작하는 곳이나 FF 줄에서 멈춘다."""
    starts = {list_start(prg, k) for k in KINDS}
    a = list_start(prg, kind)
    out = []
    while True:
        g = rd(prg, TABLE_BANK, a)
        a += 1
        k = None
        if g != 0xFF:
            k = rd(prg, TABLE_BANK, a)
            a += 1
        items = []
        while True:
            b = rd(prg, TABLE_BANK, a)
            a += 1
            items.append(b & 0x7F)
            if b & 0x80:
                break
        out.append((g, k, items))
        if g == 0xFF or a in starts:
            return out


def lookup(prg, kind, g, k):
    """15:$B2CB 의 검색 결과(덧붙임 전). 맞는 줄이 없으면 다음 종류의 목록으로 넘어가 찾으므로 그대로 따른다."""
    order = sorted(KINDS, key=lambda x: list_start(prg, x))
    seq = [row for x in order[order.index(kind):] for row in shop_lists(prg, x)]
    for rg, rk, items in seq:
        if rg == 0xFF or (rg, rk) == (g, k):
            return items
    return None


def inns(prg):
    """[(그룹, 순번, 1인 값)]."""
    out = []
    a = INN_TABLE
    while (g := rd(prg, TABLE_BANK, a)) != 0xFF:
        out.append((g, rd(prg, TABLE_BANK, a + 1), rd(prg, TABLE_BANK, a + 2)))
        a += 3
    return out


def merchants(prg, g, k):
    """대화 번호(dq4talk.talk_id)가 0~6 인 인물: [(X, Y, 번호)]. 7 이상이 스크립트로 여는 가게는 빠진다."""
    return [(r[5] & 0x7F, r[6] & 0x7F, t) for r in dq4map.npc_records(prg, g, k)
            if (t := dq4talk.talk_id(r)) < 7]


def item_names(prg):
    names = {i: n for i, n, *_ in dq4data.items(prg)}
    prices = {i: p for i, _, _, p, _ in dq4data.items(prg)}
    return names, prices


def fmt_items(prg, items):
    names, prices = item_names(prg)
    return ', '.join(f'{i:02X} {names.get(i, "?")} {prices.get(i, 0)}G' for i in items)


def place(g, k):
    return 'FF(기본)' if g == 0xFF else f'{g:02X}/{k:02X}'


def show_all(prg):
    for kind, label in KINDS.items():
        print(f'# {label} (18:${list_start(prg, kind):04X})')
        for g, k, items in shop_lists(prg, kind):
            print(f'{place(g, k)}  {fmt_items(prg, items)}')
    print('# 덧붙임(15:$B26B)')
    extra = [rd(prg, CODE_BANK, EXTRA_16 + i) for i in range(3)]
    print(f'16/00 무기  $62E7~$62E9 가 0 이 아니면 차례로 {fmt_items(prg, extra)}')
    print(f'09/00 무기  $62ED < $78 이면 목록 대신 {fmt_items(prg, NIGHT_09)}')
    print(f'# 여관 (18:${INN_TABLE:04X}, 1인 값)')
    print(' '.join(f'{g:02X}/{k:02X}={p}' for g, k, p in inns(prg)))
    print(f'그룹 10 에서 $45 < $14 이면 {INN_10_PRICE}')


def show(prg, g, k, ram=None):
    for kind, label in KINDS.items():
        rows = [items for rg, rk, items in shop_lists(prg, kind) if (rg, rk) == (g, k)]
        if rows:
            print(f'{label}  {fmt_items(prg, rows[0])}')
    for ig, ik, p in inns(prg):
        if (ig, ik) == (g, k):
            print(f'여관  1인 {p}G')
    for x, y, v in merchants(prg, g, k):
        print(f'인물 ({x:02X},{y:02X}) 대화 번호 {v:03X} → {TALK_KINDS[v]}')
    if ram is not None:
        kind = ram[KIND_RAM]
        n = ram[COUNT_RAM]
        got = list(ram[SHOP_RAM:SHOP_RAM + n])
        want = lookup(prg, kind, g, k) if kind in KINDS else None
        same = want == got
        print(f'RAM $07C5={kind:02X} $07C4={n} $07BD={" ".join(f"{b:02X}" for b in got)}'
              f' — 표 {"같음" if same else "다름: " + str(want)}')


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    a = sys.argv[2:]
    if not a:
        show_all(prg)
    else:
        g, k = int(a[0], 16), int(a[1], 16)
        ram = open(a[3], 'rb').read() if len(a) > 3 and a[2] == '--compare' else None
        show(prg, g, k, ram)


if __name__ == '__main__':
    main()
