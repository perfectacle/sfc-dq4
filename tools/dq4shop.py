"""DQ4(FC) 상점 품목·여관 값·가게 종류. 형식은 docs/dq4-shop-format.md.

사용:
  python tools/dq4shop.py rom/dq4.nes              무기·방어구·도구 가게 목록 전부와 여관 표
  python tools/dq4shop.py rom/dq4.nes G K          맵(그룹 $63/순번 $64)의 가게 목록, 여관 값, 가게 인물(스크립트로 여는 가게 포함)
  python tools/dq4shop.py rom/dq4.nes G K --compare end.ram [end.sram]   seq.lua 의 RAM 덤프로 가게 창 목록($07BD) 비교.
                                                  SRAM 덤프를 주면 그 플래그·시간으로 덧붙임까지 계산해 비교
  python tools/dq4shop.py rom/dq4.nes people       롬 전체의 「인물 → 가게(종류·품목 줄·여관 값)」 표

근거 루틴(코드 읽기와 실측):
  15:$9962  대화 결과 $00:$01 이 7 미만이면 가게 처리 15:$9CBF 로 간다.
            1 무기($B84A) 2 도구($B858) 3 방어구($B851) → $07C5 에 종류, 4 맡기는 곳($BBF0), 5 교회($B550), 6 여관($BF28).
  15:$B217  목록 표 포인터 18:$802C + 2 × (종류 − 1). 15:$B2CB 가 (그룹, 순번) 을 찾고, 품목을 bit7 이
            켜진 바이트까지 $07BD 에 담는다(개수 $07C4). FF 는 어느 맵에나 맞는 기본 줄(그룹만, 순번 없음).
  15:$B26B  덧붙임: 16/00 무기점은 $62E7~$62E9 가 0 이 아닌 것마다 15:$A4A4 의 품목을 뒤에 붙이고,
            09/00 무기점은 $62ED < $78(낮) 일 때 목록을 06 23 07 10 으로 바꾼다. 표의 09/00 줄은 밤 목록.
  15:$B2F7  가게 창의 값. 그룹 18(はがねのつるぎ 10, うまのふん 2)·22(メダル 수)·04/01(카지노 코인 표 15:$B375)만
            정한 값, 그 밖은 아이템 가격.
  15:$BF71  여관 표 18:$B5CD(BRK 87 8F 가 꺼내는 18 함수 07 의 주소): 그룹, 순번, 1인 값. FF 로 끝남.
            그룹 10 에서 주인공 Y $45 < $14 이면 표 대신 10. 값 × (BRK 62 23 01 이 돌려준 A) 가 요금(0F:$C827).
            A 는 걷는 일행 $616A~$616D(와 $618E bit5 면 마차 $6172~) 가운데 레코드 +00 bit7(살아 있음)이 켜진 사람 수.
  가게 인물  대화 번호 0~6 은 바로 서비스(15:$9962), 7 이상은 dq4talk 가 푼 스크립트의 문장 12 n(서비스 n)과
            호출 문장(00/01)이 부르는 15:$9D2A(방어구점)·$ADB7(인물 X·Y 로 고름)·$B558·$B847·$BF30·$A6B0 을 따라간다.
  교회      15:$B550. 메뉴 0 저장 1 おつげ 2 되살리기 3 해독 4 저주 풀기. 그룹 46·0E 와 04/0E 는 2~4 만(창 70).
            되살리기 (L² + 10) // 10 × 10(레코드 0~8), 해독 5, 저주 풀기 L × 30(L = 레벨 +05).
"""
import sys

from kr_patch.fc import ines

import dq4chest
import dq4data
import dq4map
import dq4talk

TABLE_BANK = 0x18
LIST_PTRS = 0x802C
KINDS = {1: '무기', 2: '도구', 3: '방어구'}
TALK_KINDS = {0: '교회', 1: '무기', 2: '도구', 3: '방어구', 4: '맡기는 곳', 5: '교회', 6: '여관', 7: '무료 숙박'}
FREE_INN = 7                   # 15:$A6B0: 값을 묻지 않고 재움(여관 표를 보지 않음)
INN_TABLE = 0xB5CD
CODE_BANK = 0x15
EXTRA_16 = 0xA4A4              # 16/00 무기점 덧붙임 품목 3개($62E7~$62E9 와 짝)
DAY_09 = (0x06, 0x23, 0x07, 0x10)
FLAGS_16, TIME = 0x62E7, 0x62ED
INN_10_PRICE = 0x0A
INN_10_GROUP, INN_10_Y = 0x10, 0x14   # 15:$BF71: 그룹 10 에서 $45 < $14 이면 10
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


def with_extras(prg, kind, g, k, items, sram):
    """15:$B26B 의 덧붙임을 sram(seq.lua 의 end.sram, $6000~)의 값으로 적용한 목록."""
    if kind != 1 or items is None:
        return items
    if (g, k) == (0x16, 0x00):
        return items + [rd(prg, CODE_BANK, EXTRA_16 + i) for i in range(3) if sram[FLAGS_16 - 0x6000 + i]]
    if (g, k) == (0x09, 0x00) and sram[TIME - 0x6000] < 0x78:
        return list(DAY_09)
    return items


def inns(prg):
    """[(그룹, 순번, 1인 값)]."""
    out = []
    a = INN_TABLE
    while (g := rd(prg, TABLE_BANK, a)) != 0xFF:
        out.append((g, rd(prg, TABLE_BANK, a + 1), rd(prg, TABLE_BANK, a + 2)))
        a += 3
    return out


def adb7_kind(x, y):
    """15:$ADB7: 말을 건 인물의 X($6F60) 가 1C 면 교회, 1D 면 Y($6F80) 12 일 때 도구점·아니면 방어구점, 그 밖은 무기점."""
    return 5 if x == 0x1C else (2 if y == 0x12 else 3) if x == 0x1D else 1


# 스크립트 호출 문장(00/01)이 부르는 루틴 가운데 가게로 가는 것. 값: (X, Y) → (종류, 덧붙는 조건)
CALL_SERVICES = {
    0x9D2A: lambda x, y: (3, '주인공 Y($45) ≠ 16'),    # 16 이면 인자의 메시지(15:$A695)
    0xADB7: lambda x, y: (adb7_kind(x, y), f'인물 자리 ({x:02X},{y:02X})'),
    0xB558: lambda x, y: (5, None),                  # 교회 인사말 다음부터
    0xB847: lambda x, y: (1, None),                  # 무기점($B84D), 가게 인사 창 없이
    0xBF30: lambda x, y: (6, None),                  # 여관 인사말 다음부터
    0xA6B0: lambda x, y: (FREE_INN, None),
}


def services(tree, x, y, path=()):
    """스크립트 나무에서 가게로 가는 곳: [(종류, 조건 목록, 경로)]. 경로는 '스크립트' 또는 '호출 15:XXXX'."""
    out = []
    for s in tree:
        if s[0] == 'service':
            out.append((s[1][0], list(path), '스크립트'))
        elif s[0] in ('call', 'call+2'):
            a = s[1][1] << 8 | s[1][0]
            if a in CALL_SERVICES:
                kind, cond = CALL_SERVICES[a](x, y)
                out.append((kind, [*path, cond] if cond else list(path), f'호출 15:{a:04X}'))
        elif s[0] == 'if':
            _, neg, op, args, then, other = s
            c = dq4talk.cond_text(neg, op, args)
            out += services(then, x, y, (*path, c))
            if other:
                out += services(other, x, y, (*path, f'아님({c})'))
    return out


DAY_CONDS = {'day': False, '아님(not day)': False, 'not day': True, '아님(day)': True}   # 조건 14($62ED < 78) → 밤이어야 하는지


def possible(cond, night):
    """낮·밤 모습과 스크립트의 낮 조건이 어긋나는 길(밤 모습인데 day 갈래 등)이면 False."""
    return all(DAY_CONDS.get(c, night) == night for c in cond)


def npc_lists(prg, g, k):
    """[(덧붙일 조건, 레코드들)]: 보통 목록과, 진행 플래그로 바뀌는 목록(1C:$9D0E 줄)마다 「목록 플래그 n&m」."""
    lists = [([], dq4map.npc_records(prg, g, k))]
    lists += [([f'목록 플래그 {i:02X}&{m:02X}'], dq4map.records_at(prg, dq4map.EVENT_LISTS[0], a)[0])
              for eg, ek, m, i, a in dq4map.event_entries(prg) if (eg, ek) == (g, k)]
    return lists


def merchants(prg, g, k):
    """가게를 여는 인물: [(X, Y, 대화 번호, 종류, 조건 목록, 경로)]. 레코드마다 낮(F bit4)·밤(F bit3) 모습을 따로 풀고
    (dq4talk.talk_id·pos 의 night), 이벤트 플래그로 바뀌는 목록(1C:$9D0E)도 돈다. 낮·밤이 같으면 한 줄로 합친다."""
    out = []
    for src, recs in npc_lists(prg, g, k):
        for r in recs:
            got = {}
            for night in (False, True):
                if not r[0] & (0x08 if night else 0x10):
                    continue
                t, (x, y) = dq4talk.talk_id(r, night), dq4talk.pos(r, night)
                c = dq4talk.classify(prg, t)
                found = [(c[1], [], '직접')] if c[0] == 'service' else services(c[2], x, y) if c[0] == 'script' else []
                got[night] = [(x, y, t, kind, cond, how) for kind, cond, how in found if possible(cond, night)]
            if len(got) == 2 and got[False] == got[True]:
                del got[True]
                tags = {False: []}
            else:
                tags = {False: ['낮'], True: ['밤']}
            for night, rows in got.items():
                out += [(x, y, t, kind, src + cond + tags[night], how) for x, y, t, kind, cond, how in rows]
    return out


def inn_price(prg, g, k):
    """15:$BF71 의 1인 값. 그룹 FE 는 10, 표에 없으면 None. 그룹 10 은 $45 < $14 이면 10(여기서는 표 값)."""
    if g == 0xFE:
        return INN_10_PRICE
    return next((p for ig, ik, p in inns(prg) if (ig, ik) == (g, k)), None)


def church_menu(g, k):
    """15:$B573: 그룹 46·0E 와 04/0E 는 되살리기·해독·저주 풀기만 있는 창 70, 나머지는 저장·おつげ 까지 있는 창 41."""
    return '되살리기·해독·저주' if g in (0x46, 0x0E) or (g, k) == (0x04, 0x0E) else '저장·おつげ·되살리기·해독·저주'


def offer(prg, g, k, kind, y=None):
    """가게 종류가 이 장소에서 내놓는 것(덧붙임 전). y 는 인물 Y: 그룹 10 여관은 말을 거는 주인공 Y 가 14 미만이면 10."""
    if kind in KINDS:
        items = lookup(prg, kind, g, k)
        names, _ = item_names(prg)
        return ' '.join(names.get(i, f'{i:02X}') for i in items)
    if kind == 6:
        p = inn_price(prg, g, k)
        if g == INN_10_GROUP and y is not None and y + 1 < INN_10_Y:
            return f'1인 {INN_10_PRICE}G(주인공 Y < {INN_10_Y:02X}, 표 값 {p}G)'
        return '표에 없음' if p is None else f'1인 {p}G'
    if kind in (0, 5):
        return church_menu(g, k)
    if kind == FREE_INN:
        return '값 없음'
    return '골드 1000G 단위·물건 맡기기'


def show_people(prg):
    n = 0
    for m in dq4chest.all_maps(prg):
        g, k = m[:2]
        for x, y, t, kind, cond, how in merchants(prg, g, k):
            n += 1
            when = ' & '.join(cond)
            print(f'{g:02X}/{k:02X} ({x:02X},{y:02X}) 대화 {t:03X} {how}{" [" + when + "]" if when else ""}'
                  f' → {TALK_KINDS[kind]}: {offer(prg, g, k, kind, y)}')
    print(f'가게 인물 {n}곳')


# 15:$B2F7(뱅크 15 함수 3): 가게 창·카지노·メダル 왕이 쓰는 값. 장소에 따라 아이템 가격 대신 정한 값을 쓴다.
PRICE_18 = {0x06: 10, 0x79: 2}                 # 그룹 18: はがねのつるぎ 10, うまのふん 2 (15:$B302~)
PRICE_22 = {0x17: 1, 0x4E: 4, 0x1C: 6}         # 그룹 22(メダル 왕): 메달 수. 그 밖은 20 (15:$B320~)
PRICE_22_OTHER = 20
CASINO_TABLE = 0xB375                          # 장소 04/01: (아이템, 값 2바이트) 6줄, 카지노 코인
CASINO_ROWS = 6


def price(prg, g, k, item):
    """15:$B2F7 의 값. 그룹 18 에서 06·79 가 아니면 A 가 아이템인 채로 아래 비교로 떨어지는 것까지 그대로 따른다."""
    a = g
    if g == 0x18:
        if item in PRICE_18:
            return PRICE_18[item]
        a = item
    if a == 0x22:
        return PRICE_22.get(item, PRICE_22_OTHER)
    if a == 0x04 and k == 0x01:
        rows = [(rd(prg, CODE_BANK, CASINO_TABLE + 3 * i), rd(prg, CODE_BANK, CASINO_TABLE + 3 * i + 1)
                 | rd(prg, CODE_BANK, CASINO_TABLE + 3 * i + 2) << 8) for i in range(CASINO_ROWS + 1)]
        return next((v for it, v in rows[:CASINO_ROWS] if it == item), rows[CASINO_ROWS][1])
    return item_names(prg)[1].get(item, 0)


def item_names(prg):
    names = {i: n for i, n, *_ in dq4data.items(prg)}
    prices = {i: p for i, _, _, p, _ in dq4data.items(prg)}
    return names, prices


def fmt_items(prg, items, g=None, k=None):
    names, prices = item_names(prg)
    cost = (lambda i: prices.get(i, 0)) if g is None else (lambda i: price(prg, g, k, i))
    unit = '메달' if g == 0x22 else '코인' if (g, k) == (0x04, 0x01) else 'G'
    return ', '.join(f'{i:02X} {names.get(i, "?")} {cost(i)}{unit}' for i in items)


def place(g, k):
    return 'FF(기본)' if g == 0xFF else f'{g:02X}/{k:02X}'


def show_all(prg):
    for kind, label in KINDS.items():
        print(f'# {label} (18:${list_start(prg, kind):04X})')
        for g, k, items in shop_lists(prg, kind):
            print(f'{place(g, k)}  {fmt_items(prg, items, g, k)}')
    print('# 덧붙임(15:$B26B)')
    extra = [rd(prg, CODE_BANK, EXTRA_16 + i) for i in range(3)]
    print(f'16/00 무기  $62E7~$62E9 가 0 이 아니면 차례로 {fmt_items(prg, extra)}')
    print(f'09/00 무기  $62ED < $78(낮) 이면 목록 대신 {fmt_items(prg, DAY_09)}')
    print(f'# 여관 (18:${INN_TABLE:04X}, 1인 값)')
    print(' '.join(f'{g:02X}/{k:02X}={p}' for g, k, p in inns(prg)))
    print(f'그룹 10 에서 $45 < $14 이면 {INN_10_PRICE}')


def show(prg, g, k, ram=None, sram=None):
    for kind, label in KINDS.items():
        rows = [items for rg, rk, items in shop_lists(prg, kind) if (rg, rk) == (g, k)]
        if rows:
            print(f'{label}  {fmt_items(prg, rows[0], g, k)}')
    for ig, ik, p in inns(prg):
        if (ig, ik) == (g, k):
            print(f'여관  1인 {p}G')
    for x, y, t, kind, cond, how in merchants(prg, g, k):
        when = ' & '.join(cond)
        print(f'인물 ({x:02X},{y:02X}) 대화 번호 {t:03X} {how}{" [" + when + "]" if when else ""} → {TALK_KINDS[kind]}')
    if ram is not None:
        kind = ram[KIND_RAM]
        n = ram[COUNT_RAM]
        got = list(ram[SHOP_RAM:SHOP_RAM + n])
        want = lookup(prg, kind, g, k) if kind in KINDS else None
        if sram is not None:
            want = with_extras(prg, kind, g, k, want, sram)
        same = want == got
        print(f'RAM $07C5={kind:02X} $07C4={n} $07BD={" ".join(f"{b:02X}" for b in got)}'
              f' — 표 {"같음" if same else "다름: " + str(want)}')


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    a = sys.argv[2:]
    if not a:
        show_all(prg)
    elif a[0] == 'people':
        show_people(prg)
    else:
        g, k = int(a[0], 16), int(a[1], 16)
        ram = open(a[3], 'rb').read() if len(a) > 3 and a[2] == '--compare' else None
        sram = open(a[4], 'rb').read() if ram is not None and len(a) > 4 else None
        show(prg, g, k, ram, sram)


if __name__ == '__main__':
    main()
