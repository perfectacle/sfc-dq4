"""DQ4(FC) 상점 품목·여관 값·가게 종류. 형식은 fc/dq4/docs/dq4-shop-format.md.

사용:
  python fc/dq4/tools/dq4shop.py rom/dq4.nes              무기·방어구·도구 가게 목록 전부와 여관 표
  python fc/dq4/tools/dq4shop.py rom/dq4.nes G K          맵(그룹 $63/순번 $64)의 가게 목록, 여관 값, 가게 인물(스크립트로 여는 가게 포함)
  python fc/dq4/tools/dq4shop.py rom/dq4.nes G K --compare end.ram [end.sram]   seq.lua 의 RAM 덤프로 가게 창 목록($07BD) 비교.
                                                  SRAM 덤프를 주면 그 플래그·시간으로 덧붙임까지 계산해 비교
  python fc/dq4/tools/dq4shop.py rom/dq4.nes people       롬 전체의 「인물 → 가게(종류·품목 줄·여관 값)」 표.
                                                  들어갈 때 숨거나 옮겨지는 조건(1C:$A010)도 붙인다
  python fc/dq4/tools/dq4shop.py rom/dq4.nes hidden [--json]   들어갈 때 장소 루틴(1C:$A010·$AD32)이 인물마다 숨기거나
                                                  옮기는 조건 전부
                                                  조건은 진행 관계(장 ⇔ $6282, 한 곳에서만 켜는 장면 플래그 ⇒ 장)로
                                                  나올 수 없는 조합을 걸러 줄인다. --raw 면 거르지 않는다
  python fc/dq4/tools/dq4shop.py rom/dq4.nes hidden G K --compare DIR   seq.lua·warp.lua 덤프 폴더(또는 atpc.lua 의
                                                  at_*.bin)의 인물 표와 비교: 숨김, 그리고 옮김·방향·간격·상태·그림 열
  python fc/dq4/tools/dq4shop.py rom/dq4.nes order        hidden 이 거르는 앞뒤 비트 관계(뒤 비트 ← 켜져 있어야 하는 앞 비트).
                                                  대화 스크립트의 flag|= 와 뱅크 코드의 BRK n CB m 앞 갈래에서 뽑는다

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
  1C:$A010  맵에 들어갈 때 장소 표 1C:$ABF5(그룹, 순번) → 포인터 1C:$AC8A 의 루틴. 1C:$A035 로 슬롯 X+6 을 숨기고
            1C:$A04A 로 (A, Y) 에 옮긴다. 루틴을 기호로 돌려(갈래 양쪽) 인물마다 조건을 원자의 곱의 합으로 줄인다.
  교회      15:$B550. 메뉴 0 저장 1 おつげ 2 되살리기 3 해독 4 저주 풀기. 그룹 46·0E 와 04/0E 는 2~4 만(창 70).
            되살리기 (L² + 10) // 10 × 10(레코드 0~8), 해독 5, 저주 풀기 L × 30(L = 레벨 +05).
"""
import re
import sys

from kr_patch.fc import ines
from kr_patch.fc.dis6502 import OPS, SIZE

import dq4chest
import dq4data
import dq4flags
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


def hide_notes(prg, g, k, x, y, t, cond, acts):
    """가게 인물이 들어갈 때의 장소 루틴(1C:$A010)에서 숨거나 옮겨지는 조건. acts 는 hide_table 의 결과.
    인물 번호는 그 목록에서 낮·밤 모습이 있는 레코드의 순번이라, 자리·대화 번호가 같은 레코드를 찾아 맞춘다."""
    nights = [n for n in (False, True) if ('밤' if n else '낮') in cond] or [False, True]
    notes = []
    for src, recs in npc_lists(prg, g, k):
        if src and src[0] not in cond:
            continue
        fixed = {NIGHT_ATOM: None}
        if src:
            n, m = (int(v, 16) for v in src[0].split()[-1].split('&'))
            fixed.update({('bit', f'${dq4map.FLAGS + n:04X}', 1 << b): True for b in range(8) if m >> b & 1})
        for night in nights:
            fixed[NIGHT_ATOM] = night
            people = [r for r in recs if r[0] & (0x08 if night else 0x10)]
            for i, r in enumerate(people):
                if dq4talk.pos(r, night) != (x, y) or dq4talk.talk_id(r, night) != t:
                    continue
                for j, what, terms in acts:
                    ts = [c for c in terms if all(dict(c).get(a, v) == v for a, v in fixed.items())]
                    if j == i and ts:
                        notes.append(f'{what} {terms_text(ts)}')
    return list(dict.fromkeys(notes))


def show_people(prg):
    n = 0
    acts = {(g, k): a for g, k, _, a in hidden(prg)}
    for m in dq4chest.all_maps(prg):
        g, k = m[:2]
        for x, y, t, kind, cond, how in merchants(prg, g, k):
            n += 1
            when = ' & '.join(cond)
            notes = hide_notes(prg, g, k, x, y, t, cond, acts.get((g, k), []))
            print(f'{g:02X}/{k:02X} ({x:02X},{y:02X}) 대화 {t:03X} {how}{" [" + when + "]" if when else ""}'
                  f' → {TALK_KINDS[kind]}: {offer(prg, g, k, kind, y)}'
                  + ''.join(f' / 들어갈 때 {note}' for note in notes))
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


# 1C:$A010: 인물 표를 채운 뒤 장소 표 1C:$ABF5(그룹, 순번; 첫 바이트 bit7 로 끝)에서 지금 장소를 찾아
# 같은 자리의 포인터 1C:$AC8A 로 뛴다. 루틴은 장·플래그·시간·자리를 보고 1C:$A035 로 슬롯 X+6 의 자리 네 바이트를
# 80 으로 써서 숨기거나, 1C:$A04A 로 (A, Y) 에 옮긴다. 1C:$9EA6 은 $62A5 bit7 이 꺼져 있을 때만 이것과 1C:$AD32 를 부른다.
HIDE_BANK = 0x1C
HIDE_PLACES, HIDE_PTRS = 0xABF5, 0xAC8A
HIDE_SLOT, PLACE_SLOT, IS_NIGHT = 0xA035, 0xA04A, 0xA044
CHAPTER_HIDE = 0xAD5A          # 1C:$AD32: (그룹, 순번, 장, 인물) 4바이트 줄, bit7 로 끝. 장 $615A 가 다르면 숨김
SLOT_COLS = {0x6F66: 'X', 0x6F86: 'Y', 0x6FA6: 'X2', 0x6FC6: 'Y2', 0x6FE6: '그림', 0x7006: '방향',
             0x7046: '간격', 0x70E6: '상태'}
SYMBOLS = {0x44: '주인공 X', 0x45: '주인공 Y', 0x615A: '장', 0x62ED: '시간'}


def hide_routines(prg):
    """[(그룹, 순번, 루틴 주소)]."""
    out, i = [], 0
    while not (g := rd(prg, HIDE_BANK, HIDE_PLACES + i)) & 0x80:
        p = rd(prg, HIDE_BANK, HIDE_PTRS + i) | rd(prg, HIDE_BANK, HIDE_PTRS + i + 1) << 8
        out.append((g, rd(prg, HIDE_BANK, HIDE_PLACES + i + 1), p))
        i += 2
    return out


def chapter_hides(prg):
    """1C:$AD32 의 줄: [(그룹, 순번, 장 $615A, 인물 번호)]."""
    out, a = [], CHAPTER_HIDE
    while not (g := rd(prg, HIDE_BANK, a)) & 0x80:
        out.append((g, *(rd(prg, HIDE_BANK, a + i) for i in (1, 2, 3))))
        a += 4
    return out


NEG = {'=': '≠', '≠': '=', '≥': '<', '<': '≥', 'bit7': '!bit7', '!bit7': 'bit7', 'bit6': '!bit6', '!bit6': 'bit6'}


def holds(op, v, x):
    return {'=': x == v, '≠': x != v, '≥': x >= v, '<': x < v, 'bit7': bool(x & 0x80), '!bit7': not x & 0x80,
            'bit6': bool(x & 0x40), '!bit6': not x & 0x40}[op]


def add_cond(path, c):
    """조건 (값, 연산, 수) 를 길에 더한 새 길. 이미 참이면 그대로, 어긋나면 None."""
    sym, op, v = c
    if c in path:
        return path
    if (sym, NEG[op], v) in path:
        return None
    eq = [w for s, o, w in path if s == sym and o == '=']
    if eq:
        return path if holds(op, v, eq[0]) else None
    if op == '=' and not all(holds(o, w, v) for s, o, w in path if s == sym):
        return None
    return path + (c,)


def cond_text(c):
    sym, op, v = c
    if sym == '시간' and op in ('≥', '<') and v == dq4map.NIGHT:
        return '밤' if op == '≥' else '낮'
    if sym == '장' and op in ('=', '≠'):
        return f'{v + 1}장' if op == '=' else f'{v + 1}장 아님'
    if '&' in sym and v == 0 and op in ('=', '≠'):
        return f'{sym} {"꺼짐" if op == "=" else "켜짐"}'
    if op.endswith(('bit7', 'bit6')):
        return f'{sym} {op[-4:]} {"꺼짐" if op[0] == "!" else "켜짐"}'
    if sym.startswith('아이템'):
        return f'{sym} {"있음" if op == "=" else "없음"}'
    return f'{sym} {op} {v:02X}'


def sym_name(a):
    return SYMBOLS.get(a, f'${a:04X}' if a >= 0x100 else f'${a:02X}')


def hide_paths(prg, start, limit=4096):
    """루틴을 기호로 돌려 [(조건 길, 효과들)] 을 낸다. 레지스터는 수 또는 기호(문자열),
    플래그는 bool 또는 (참 조건, 거짓 조건). 효과: ('hide', i) · ('pos', i, 열, 값) · ('flag', 주소, |= 또는 &=, 값) ·
    ('call', 설명)."""
    from kr_patch.fc.dis6502 import OPS, SIZE
    out = []
    todo = [(start, None, None, None, {}, (), (), ())]   # pc, a, x, y, 플래그, 길, 효과, 복귀 스택
    steps = 0
    while todo:
        pc, a, x, y, fl, path, eff, stack = todo.pop()
        while True:
            steps += 1
            if steps > limit:
                raise RuntimeError(f'{start:04X}: 길이 너무 많음')
            op = rd(prg, HIDE_BANK, pc)
            b1, b2 = rd(prg, HIDE_BANK, pc + 1), rd(prg, HIDE_BANK, pc + 2)
            if op == 0x00:
                n = dq4talk.brk_len(b1, b2)
                m = rd(prg, HIDE_BANK, pc + 3)
                if b2 == 0xEB:
                    c = (f'${dq4map.FLAGS + b1:04X}&{m:02X}', '=', 0)
                    fl = dict(fl, Z=(c, (c[0], '≠', 0)))
                elif b2 in (0xCB, 0xDB):
                    eff += (('flag', dq4map.FLAGS + b1, '|=' if b2 == 0xCB else '&=', m),)
                elif (b1, b2) == (0x66, 0x73):
                    item = f'{a:02X}' if isinstance(a, int) else a
                    # 찾으면 C = 1(실측: 0F/00 의 1C:$A097)
                    c = (f'아이템 {item}', '=', 1)
                    fl = dict(fl, C=(c, (c[0], '≠', 1)))
                else:
                    eff += (('call', f'BRK {b1:02X} {b2:02X}(A={a if isinstance(a, str) else f"{a:02X}"}'
                                     f' X={x if isinstance(x, str) else f"{x:02X}"})'),)
                pc += n
                continue
            mn, md = OPS[op]
            n = 1 + SIZE[md]
            arg = b1 | b2 << 8 if n == 3 else b1
            nxt = pc + n
            if mn == 'JSR' or (mn == 'JMP' and md == 'abs' and arg in (HIDE_SLOT, PLACE_SLOT)):
                ret = stack + (nxt,) if mn == 'JSR' else stack
                if arg == HIDE_SLOT:
                    eff += (('hide', x),)
                elif arg == PLACE_SLOT:
                    eff += (('pos', x, 'X', a), ('pos', x, 'Y', y))
                elif arg == IS_NIGHT:
                    a = '시간'
                    c = ('시간', '≥', dq4map.NIGHT)
                    fl = dict(fl, C=(c, ('시간', '<', dq4map.NIGHT)))
                elif arg < 0xC000 and arg != 0xAD1E:
                    pc, stack = arg, ret
                    continue
                else:
                    a = f'{arg:04X}()'
                    eff += (('call', f'JSR ${arg:04X}'),)
                if mn == 'JMP' or not ret:
                    if mn == 'JMP' and stack:
                        pc, stack = stack[-1], stack[:-1]
                        continue
                    if mn == 'JMP':
                        break
                pc = nxt
                continue
            if mn == 'RTS':
                if stack:
                    pc, stack = stack[-1], stack[:-1]
                    continue
                break
            if mn == 'JMP':
                pc = arg
                continue
            if md == 'rel':
                flag = {'BEQ': ('Z', True), 'BNE': ('Z', False), 'BCS': ('C', True), 'BCC': ('C', False),
                        'BMI': ('N', True), 'BPL': ('N', False), 'BVS': ('V', True), 'BVC': ('V', False)}[mn]
                dest = (pc + 2 + (b1 - 256 if b1 & 0x80 else b1)) & 0xFFFF
                f = fl.get(flag[0])
                if isinstance(f, bool):
                    pc = dest if f == flag[1] else nxt
                    continue
                if f is None:
                    raise RuntimeError(f'{pc:04X}: 플래그 {flag[0]} 모름')
                on, off = f if flag[1] else (f[1], f[0])
                p2 = add_cond(path, off)
                if p2 is not None:
                    todo.append((nxt, a, x, y, fl, p2, eff, stack))
                path = add_cond(path, on)
                if path is None:
                    break
                pc = dest
                continue
            val = arg if md == 'imm' else None
            if mn in ('LDA', 'LDX', 'LDY'):
                if md == 'imm':
                    v = arg
                else:
                    r = x if md == 'abx' else y if md == 'aby' else 0
                    v = sym_name(arg + r) if isinstance(r, int) else f'${arg:04X}+{r}'
                if mn == 'LDA':
                    a = v
                elif mn == 'LDX':
                    x = v
                else:
                    y = v
                fl = nz(fl, v)
            elif mn == 'STA':
                if md == 'abx':
                    col = SLOT_COLS.get(arg)
                    eff += (('pos', x, col, a),) if col else (('write', arg + x, a),)
                else:
                    eff += (('write', arg, a),)
            elif mn == 'INC':
                eff += (('write', arg, '+1'),)
            elif mn in ('INX', 'DEY'):
                if mn == 'INX':
                    x = (x + 1) & 0xFF
                    fl = nz(fl, x)
                else:
                    y = (y - 1) & 0xFF
                    fl = nz(fl, y)
            elif mn in ('TAX', 'TAY', 'TYA'):
                if mn == 'TAX':
                    x = a
                elif mn == 'TAY':
                    y = a
                else:
                    a = y
                fl = nz(fl, a)
            elif mn in ('AND', 'ORA'):
                if isinstance(a, int):
                    a = a & val if mn == 'AND' else a | val
                else:
                    a = f'{a}{"&" if mn == "AND" else "|"}{val:02X}'
                fl = nz(fl, a)
            elif mn == 'LSR' and md == 'acc':
                if isinstance(a, int):
                    fl, a = dict(fl, C=bool(a & 1)), a >> 1
                else:
                    c = (f'{a}&01', '≠', 0)
                    fl, a = dict(fl, C=(c, (c[0], '=', 0))), f'{a}>>1'
                fl = nz(fl, a)
            elif mn in ('CMP', 'CPX'):
                r = a if mn == 'CMP' else x
                if isinstance(r, int):
                    fl = dict(fl, Z=r == val, C=r >= val, N=bool((r - val) & 0x80))
                else:
                    fl = dict(fl, Z=((r, '=', val), (r, '≠', val)), C=((r, '≥', val), (r, '<', val)), N=None)
            elif mn == 'BIT':
                s = sym_name(arg)
                fl = dict(fl, N=((s, 'bit7', 0), (s, '!bit7', 0)), V=((s, 'bit6', 0), (s, '!bit6', 0)), Z=None)
            else:
                raise RuntimeError(f'{pc:04X}: {mn} 못 다룸')
            pc = nxt
        if path is not None:
            out.append((path, eff))
    return out


def nz(fl, v):
    if isinstance(v, int):
        return dict(fl, Z=v == 0, N=bool(v & 0x80))
    return dict(fl, Z=((v, '=', 0), (v, '≠', 0)), N=((v, 'bit7', 0), (v, '!bit7', 0)))


def atoms_of(c):
    """조건 하나를 원자(참·거짓 하나로 정해지는 것)의 곱의 합 [[(원자, 참?)]] 으로 바꾼다. 원자는 ('bit', 주소, 비트) 나
    ('num', 값 이름, '=' 또는 '≥', 수). $X&M 의 같음 비교는 비트마다 나누고, BIT·BMI 의 bit7·bit6 도 비트 원자로 둔다."""
    sym, op, v = c
    if op.endswith(('bit7', 'bit6')):
        return [[(('bit', sym, 0x80 if op.endswith('7') else 0x40), op[0] != '!')]]
    if '&' in sym and sym.startswith('$') and op in ('=', '≠'):
        base, m = sym.split('&')
        bits = [1 << i for i in range(8) if int(m, 16) >> i & 1]
        if op == '=':
            return [[(('bit', base, b), bool(v & b)) for b in bits]]
        return [[(('bit', base, b), not v & b)] for b in bits]
    if op in ('≠', '<'):
        return [[(('num', sym, '=' if op == '≠' else '≥', v), False)]]
    return [[(('num', sym, op, v), True)]]


def path_dnf(path):
    out = [[]]
    for c in path:
        out = [t + alt for t in out for alt in atoms_of(c)]
    return out


# 진행 관계. 장 시작 루틴이 $6282 를 장마다 00·80·C0·E0·F0 으로 쓰고 장 끝은 비트를 더하기만 하므로,
# $6282 의 bit7~4 는 「$615A ≥ 1~4」 와 같다(dq4-save-format.md 「1~5장 시작 표」).
CHAPTER_BITS = {0x80: 1, 0x40: 2, 0x20: 3, 0x10: 4}
# 맵·필드를 오가면 지워지는 바이트(dq4-story-format.md 「맵을 나가면 지워지는 바이트」)는 장과 묶지 않는다.
TRANSIENT = {0x6285, 0x6289, 0x628B}
# 장 끝 1A:$B92C~ 가 끄는 비트: 그 장 안에서만 켜져 있다.
CHAPTER_END_CLEAR = {(0x6291, 0x80), (0x6288, 0x80), (0x6286, 0x04), (0x6285, 0xC0), (0x6281, 0x40)}


def progress_rules(prg):
    """{('$ADDR', 비트): (장 $615A, 그 장에서만인지)}. dq4flags.STORY 의 장면 플래그 가운데 롬에서 그 비트를 켤 수 있는
    곳(set·store·절대 주소 쓰기)이 하나뿐인 것만 쓴다. 그 곳이 그 장의 장면이므로 켜져 있으면 그 장 이후다."""
    import dq4event
    writers = {}
    for n, rows in dq4event.flag_xref(prg).items():
        for m, kind, *_ in rows:
            if kind in ('store', 'write') or (kind == 'set' and m):
                for b in (0x80 >> j for j in range(8)):
                    if kind != 'set' or m & b:
                        writers[(n, b)] = writers.get((n, b), 0) + 1
    out = {}
    for c, scenes in dq4flags.STORY.items():
        for _, fl in scenes:
            for n, m in fl:
                a = dq4map.FLAGS + n
                if a in TRANSIENT or a == 0x6282 or writers.get((n, m)) != 1:
                    continue
                out[(f'${a:04X}', m)] = (c - 1, any(a == ca and m & cm for ca, cm in CHAPTER_END_CLEAR))
    return out


def flag_writers(prg):
    """({(번호, 비트): 켜는 곳 수}, {끄는 곳이 있는 (번호, 비트)}). 켜기·쓰기는 flag_xref 의 set·store·절대 주소 쓰기."""
    import dq4event
    sets, clears = {}, set()
    for n, rows in dq4event.flag_xref(prg).items():
        for m, kind, *_ in rows:
            if kind in ('set', 'store', 'write'):
                for b in (0x80 >> j for j in range(8)):
                    if m is None or kind != 'set' or m & b:
                        sets[(n, b)] = sets.get((n, b), 0) + 1
            if kind in ('clear', 'store', 'write'):
                for b in (0x80 >> j for j in range(8)):
                    if m is None or kind != 'clear' or not m & b:
                        clears.add((n, b))
    return sets, clears


def one_bit(args):
    """조건 1B 의 (번호, 마스크) 가 한 비트면 {(번호, 비트)}, 아니면 빈 집합."""
    bits = {(args[0], b) for b in (0x80 >> j for j in range(8)) if args[1] & b}
    return frozenset(bits) if len(bits) == 1 else frozenset()


def script_needs(tree, pick, out, need=frozenset()):
    """대화 나무에서 pick(문장) 이 키를 돌려주는 문장마다 그곳에 닿는 갈래가 켜져 있어야 하는 비트(조건 1B)를 모은다.
    out[키] 는 그 키의 문장 모두에 공통인 비트."""
    for s in tree:
        if s[0] == 'if':
            _, neg, op, args, then, other = s
            bits = one_bit(args) if op == 0x1B else frozenset()
            script_needs(then, pick, out, need if neg else need | bits)
            script_needs(other or [], pick, out, need | bits if neg else need)
            continue
        for k in pick(s):
            out[k] = out[k] & need if k in out else need


def talk_rules(prg, sets):
    """{(번호, 비트): 앞 비트}: 그 비트를 켜는 곳이 롬 전체에서 대화 스크립트의 「flag|=」 하나뿐일 때 그 문장의 조건."""
    import dq4event
    out, seen = {}, set()

    def pick(s):
        if s[0] != 'flag|=':
            return ()
        n, v = s[1]
        return [(n, b) for b in (0x80 >> j for j in range(8)) if v & b and sets.get((n, b)) == 1]

    for _, _, _, night, recs in dq4event.npc_lists(prg):
        for r in recs:
            tid = dq4talk.talk_id(r, night)
            if tid in seen:
                continue
            seen.add(tid)
            c = dq4talk.classify(prg, tid)
            if c[0] == 'script':
                script_needs(c[2], pick, out)
    return out


# 뱅크 함수 가운데 BRK 뒤 바이트를 더 읽고 복귀 주소를 넘기는 것(스택의 복귀 주소에 INC $01xx,X).
# 뱅크 16 의 창 열기 07·09 와 01·29 가 한 바이트씩 읽는다(16:$8976·$89A3).
def inline_bytes(prg, bank, func):
    import dq4bank
    t = dq4bank.entry(prg, bank, func)
    if not 0x8000 <= t < 0xC000:
        return 0
    code = prg[bank * 0x4000 + (t & 0x3FFF):][:24]
    return sum(code[i] == 0xFE and code[i + 2] == 0x01 and code[i + 3] == 0xD0 for i in range(len(code) - 3))


def brk_size(prg, b1, b2, cache):
    n = dq4talk.brk_len(b1, b2)
    if b2 & 0x0F not in (0x03, 0x0B) and not b1 & 0x80:
        key = ((b2 >> 4) | (b2 & 0x08) << 1, b1)
        if key not in cache:
            cache[key] = inline_bytes(prg, *key)
        n += cache[key]
    return n


NO_FLAGS = {'STA', 'STX', 'STY', 'CLC', 'SEC', 'CLI', 'SEI', 'CLD', 'SED', 'CLV', 'PHA', 'PHP', 'TXS', 'NOP', 'JMP'}


def guard_walk(prg, bank, start, pre, found, cache, limit=3000000):
    """bank 의 루틴 start 를 갈래 양쪽, 같은 뱅크 JSR 안까지 따라가며 BRK 플래그 켜기(n CB m)마다 그 길에서 켜져 있다고
    아는 비트를 found[(뱅크, 주소)] 에 더한다. 아는 비트는 pre 와, 길에서 지난 검사(BRK n EB m, LDA/AND/BIT $62xx 뒤
    BEQ·BNE·BMI·BPL)와 켜기·끄기. 고정 뱅크 JSR 은 결과를 모르는 호출로 넘기고, 간접 JMP·RTI·모르는 명령에서 길을 끝낸다."""
    import dq4event
    lo, hi = dq4map.FLAGS, dq4event.FLAGS_END
    seen = set()
    todo = [(start, (), frozenset((k, True) for k in pre), None, None, None)]
    steps = 0
    while todo:
        pc, stack, known, z, nf, acc = todo.pop()
        while 0x8000 <= pc < 0xC000 and (key := (pc, stack, known, z, nf, acc)) not in seen:
            steps += 1
            if steps > limit:
                raise RuntimeError(f'{bank:02X}:{start:04X}: 길이 너무 많음')
            seen.add(key)
            op = rd(prg, bank, pc)
            if op == 0x00:
                b1, b2 = rd(prg, bank, pc + 1), rd(prg, bank, pc + 2)
                if b2 & 0x0F == 0x0B and 0xCB <= b2 < 0xFB and b1 <= hi - lo:
                    m = rd(prg, bank, pc + 3)
                    if b2 == 0xEB:
                        z = (b1, m) if m.bit_count() == 1 else None
                    else:
                        if b2 == 0xCB:
                            found.setdefault((bank, pc), []).append(frozenset(k for k, v in known if v))
                        hit = m if b2 == 0xCB else ~m & 0xFF
                        known = frozenset((k, v) for k, v in known if not (k[0] == b1 and k[1] & hit)) | \
                            {((b1, b), b2 == 0xCB) for b in (1 << i for i in range(8)) if hit & b}
                        z = None
                else:
                    z = nf = acc = None
                pc += brk_size(prg, b1, b2, cache)
                continue
            if op not in OPS:
                break
            mn, md = OPS[op]
            n = 1 + SIZE[md]
            arg = (rd(prg, bank, pc + 1) | (rd(prg, bank, pc + 2) << 8 if n == 3 else 0)) if n > 1 else 0
            nxt = pc + n
            if md == 'rel':
                tgt = (pc + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF
                k, taken = {'BEQ': (z, False), 'BNE': (z, True), 'BMI': (nf, True), 'BPL': (nf, False)}.get(mn, (None, None))
                if k is None:
                    todo.append((tgt, stack, known, z, nf, acc))
                    pc = nxt
                    continue
                have = dict(known).get(k)
                if have in (None, taken):
                    todo.append((tgt, stack, known | {(k, taken)}, z, nf, acc))
                if have not in (None, not taken):
                    break
                known, pc = known | {(k, not taken)}, nxt
                continue
            if mn == 'JSR':
                z = nf = acc = None
                if 0x8000 <= arg < 0xC000 and len(stack) < 8 and nxt not in stack:
                    stack, pc = stack + (nxt,), arg
                else:
                    pc = nxt
                continue
            if mn == 'JMP':
                if md != 'abs':
                    break
                pc = arg
                continue
            if mn == 'RTS' and stack:
                pc, stack = stack[-1], stack[:-1]
                continue
            if mn in ('RTS', 'RTI'):
                break
            if mn == 'LDA' and md == 'abs' and lo <= arg <= hi:
                acc, z, nf = (arg - lo, 0xFF), None, (arg - lo, 0x80)
            elif mn == 'AND' and md == 'imm' and acc is not None:
                m = acc[1] & arg
                acc = (acc[0], m)
                z = acc if m.bit_count() == 1 else None
                nf = (acc[0], 0x80) if m & 0x80 else None
            elif mn == 'BIT' and md == 'abs' and lo <= arg <= hi:
                z, nf = None, (arg - lo, 0x80)
            elif mn not in NO_FLAGS:
                z = nf = acc = None
            pc = nxt


def code_entries(prg):
    """[(뱅크, 주소, 처음부터 켜져 있는 비트)]: 코드 뱅크의 BRK 일반 호출이 부르는 함수, 1C 이벤트 표, 1D 블록 이벤트 표,
    대화 호출 문장이 부르는 뱅크 15 루틴. 마지막 것은 그 주소를 부르는 문장 모두에 공통인 대화 조건(1B)을 갖고 시작한다."""
    import dq4bank
    import dq4event
    ent = set()
    for p in range(len(prg) - 3):
        b1, b2 = prg[p + 1], prg[p + 2]
        if prg[p] or p // 0x4000 in dq4event.DATA_BANKS or b2 & 0x0F in (0x03, 0x0B) or b1 & 0x80:
            continue
        bank = (b2 >> 4) | (b2 & 0x08) << 1
        t = dq4bank.entry(prg, bank, b1)
        if bank not in dq4event.DATA_BANKS and 0x8000 <= t < 0xC000:
            ent.add((bank, t))
    ent |= {(0x1C, a) for a in dq4talk.event_table(prg)}
    ent |= {(0x1D, dq4event.event_addr(prg, i)) for i in range(dq4event.EVENT_COUNT)}
    calls = {}
    for t in range(dq4talk.SCRIPT_FIRST, dq4talk.YESNO_FIRST):
        script_needs(dq4talk.classify(prg, t)[2], lambda s: [s[1][1] << 8 | s[1][0]] if s[0] in ('call', 'call+2') else (),
                     calls)
    ent |= {(CODE_BANK, a) for a in calls if 0x8000 <= a < 0xC000}
    return [(b, a, calls.get(a, frozenset()) if b == CODE_BANK else frozenset()) for b, a in sorted(ent)]


def code_guards(prg):
    """{(뱅크, 주소): 그 BRK 플래그 켜기에 닿는 모든 길에서 켜져 있는 비트}. 진입점에서 닿지 않는 켜기는 빠진다."""
    found, cache = {}, {}
    for bank, a, pre in code_entries(prg):
        guard_walk(prg, bank, a, pre, found, cache)
    return {k: frozenset.intersection(*v) for k, v in found.items()}


def order_rules(prg):
    """{(뒤 비트): {(앞 비트)}}. 뒤 비트를 켜는 곳이 롬 전체에서 하나뿐이고, 그곳에 닿는 모든 길이 앞 비트가 켜져 있음을
    거치며, 앞 비트를 끄는 곳이 롬에 없을 때만 「뒤가 켜져 있으면 앞도 켜져 있다」. 켜는 곳은 대화 스크립트의 「flag|=」
    (조건 1B)와 뱅크 코드의 BRK n CB m(앞의 플래그 검사 갈래, 같은 길에서 먼저 켠 비트, 부르는 대화 문장의 조건).
    장면 차례만으로는 이 관계가 서지 않는다(대화 021 은 $627E bit1 을 켤 때 다른 비트를 보지 않음). 관계는 이어 붙여 닫는다."""
    sets, clears = flag_writers(prg)
    need = talk_rules(prg, sets)
    for (bank, a), bits in code_guards(prg).items():
        o = bank * 0x4000 + (a & 0x3FFF)
        n, m = prg[o + 1], prg[o + 3]
        for b in (0x80 >> j for j in range(8)):
            if m & b and sets.get((n, b)) == 1:
                need[(n, b)] = need.get((n, b), frozenset()) | bits
    rules = {}
    for (n, b), bits in need.items():
        a = dq4map.FLAGS + n
        keep = {(f'${dq4map.FLAGS + e:04X}', eb) for e, eb in bits
                if (e, eb) != (n, b) and (e, eb) not in clears and dq4map.FLAGS + e not in TRANSIENT
                and (dq4map.FLAGS + e, eb) not in CHAPTER_END_CLEAR}
        if keep and a not in TRANSIENT:
            rules[(f'${a:04X}', b)] = keep
    grew = True
    while grew:
        grew = False
        for k, v in rules.items():
            more = set().union(*(rules.get(x, set()) for x in v)) - v - {k}
            if more:
                v |= more
                grew = True
    return rules


def show_order(prg):
    for (a, b), need in sorted(order_rules(prg).items()):
        print(f'{a}&{b:02X} ← ' + ', '.join(f'{e}&{eb:02X}' for e, eb in sorted(need)))


RULES = None      # hidden() 이 progress_rules 로 채운다. None 이면 관계를 보지 않음
ORDER = {}        # hidden() 이 order_rules 로 채운다


def chapters_ok(atoms, bits):
    """원자 값들과 함께 설 수 있는 장 $615A(0~4) 가 하나라도 있는지."""
    cs = set(range(5))
    for (kind, sym, *rest), on in zip(atoms, bits):
        if kind == 'num' and sym == '장':
            cs = {c for c in cs if holds(rest[0], rest[1], c) == on}
        elif kind == 'bit' and sym == '$6282' and rest[0] in CHAPTER_BITS:
            cs = {c for c in cs if (c >= CHAPTER_BITS[rest[0]]) == on}
        elif kind == 'bit' and on and (sym, rest[0]) in RULES:
            c0, only = RULES[(sym, rest[0])]
            cs = {c for c in cs if (c == c0 if only else c >= c0)}
    return bool(cs)


def consistent(atoms, bits):
    """수 원자들이 값 하나로 함께 설 수 있는지(값마다 0~FF 를 다 해 봄). RULES 가 있으면 진행 관계도 본다."""
    by = {}
    for (kind, sym, *rest), on in zip(atoms, bits):
        if kind == 'num':
            by.setdefault(sym, []).append((rest[0], rest[1], on))
    if not all(any(all(holds(op, v, w) == on for op, v, on in cs) for w in range(256)) for cs in by.values()):
        return False
    if RULES is None:
        return True
    on = {(sym, rest[0]) for (kind, sym, *rest), v in zip(atoms, bits) if kind == 'bit' and v}
    off = {(sym, rest[0]) for (kind, sym, *rest), v in zip(atoms, bits) if kind == 'bit' and not v}
    if any(ORDER.get(k, set()) & off for k in on):
        return False
    return chapters_ok(atoms, bits)


def primes_cover(n, on, dc):
    """Quine–McCluskey: on 을 덮는 주항들을 [(값, 빈칸 마스크)] 로. dc 는 상관없는 칸."""
    terms, primes = {(m, 0) for m in on | dc}, set()
    while terms:
        nxt, used = set(), set()
        for v, mk in terms:
            for i in range(n):
                b = 1 << i
                if not (mk | v) & b and (v | b, mk) in terms:
                    nxt.add((v, mk | b))
                    used |= {(v, mk), (v | b, mk)}
        primes |= terms - used
        terms = nxt
    cover, rest = [], set(on)
    while rest:
        best = max(sorted(primes), key=lambda p: (sum(m & ~p[1] == p[0] for m in rest), bin(p[1]).count('1')))
        cover.append(best)
        rest = {m for m in rest if m & ~best[1] != best[0]}
    return cover


def minimize(paths, keys_of):
    """길마다의 효과 키(keys_of(효과들) → 집합)로 키마다 조건을 원자의 곱의 합으로 줄인다. {키: [[(원자, 참?)]]}."""
    dnfs = [(path_dnf(path), keys_of(eff)) for path, eff in paths]
    atoms = sorted({a for d, _ in dnfs for t in d for a, _ in t}, key=str)
    n = len(atoms)
    idx = {a: i for i, a in enumerate(atoms)}
    keys = sorted({k for _, ks in dnfs for k in ks}, key=str)
    on, off = {k: set() for k in keys}, {k: set() for k in keys}
    for m in range(1 << n):
        bits = [bool(m >> i & 1) for i in range(n)]
        if not consistent(atoms, bits):
            continue
        hit = next((ks for d, ks in dnfs if any(all(bits[idx[a]] == t for a, t in conj) for conj in d)), None)
        if hit is None:
            continue
        for k in keys:
            (on if k in hit else off)[k].add(m)
    out = {}
    for k in keys:
        dc = set(range(1 << n)) - on[k] - off[k]
        out[k] = [[(atoms[i], bool(v >> i & 1)) for i in range(n) if not mk >> i & 1]
                  for v, mk in primes_cover(n, on[k], dc)]
    return out


def atom_text(a, on):
    if a[0] == 'bit':
        return f'{a[1]}&{a[2]:02X} {"켜짐" if on else "꺼짐"}'
    _, sym, op, v = a
    return cond_text((sym, op if on else NEG[op], v))


def terms_text(terms):
    if terms == [[]]:
        return '늘'
    return ' 또는 '.join('[' + ' & '.join(atom_text(a, t) for a, t in conj) + ']' for conj in terms)


def value_text(v):
    return f'{v:02X}' if isinstance(v, int) else str(v)


def hide_keys(eff):
    """한 길의 효과를 (인물 번호 또는 None, 하는 일) 집합으로. 자리 네 바이트가 모두 80 이면 숨김."""
    keys, moves = set(), {}
    for e in eff:
        if e[0] == 'hide':
            keys.add((e[1], '숨김'))
        elif e[0] == 'pos':
            moves.setdefault(e[1], {})[e[2]] = e[3]
        elif e[0] == 'flag':
            keys.add((None, f'${e[1]:04X} {e[2]} {e[3]:02X}'))
        elif e[0] == 'write':
            keys.add((None, f'${e[1]:04X} = {value_text(e[2])}'))
        else:
            keys.add((None, e[1]))
    for i, cols in moves.items():
        if 'X' in cols and all(v == 0x80 for c, v in cols.items() if c in ('X', 'Y', 'X2', 'Y2')):
            keys.add((i, '숨김'))
        else:
            keys.add((i, ' '.join(f'{c}={value_text(v)}' for c, v in cols.items() if c not in ('X2', 'Y2'))))
    return keys


def hide_table(prg, start):
    """루틴이 하는 일마다 [(인물 번호 또는 None, 하는 일, 조건 합)]."""
    got = minimize(hide_paths(prg, start), hide_keys)
    return [(i, what, terms) for (i, what), terms in sorted(got.items(), key=lambda t: (t[0][0] is None,
                                                                                      t[0][0] or 0, t[0][1]))]


NIGHT_ATOM = ('num', '시간', '≥', dq4map.NIGHT)


def slot_people(prg, g, k, night):
    """보통 목록에서 낮(F bit4)·밤(F bit3) 모습이 있는 레코드를 차례로: 인물 번호 i 는 슬롯 i+6(1C:$98ED)."""
    return [r for r in dq4map.npc_records(prg, g, k) if r[0] & (0x08 if night else 0x10)]


def person_text(prg, g, k, i, terms):
    """인물 번호 i 의 자리·대화 번호. 조건이 모두 낮이나 밤이면 그쪽 목록만 보인다. 진행 플래그로 바뀐 목록은 보지 않는다."""
    if not isinstance(i, int):
        return f'인물 {i}'
    when = {dict(conj).get(NIGHT_ATOM) for conj in terms}
    out = []
    for night in (False, True):
        if when in ({True}, {False}) and when != {night}:
            continue
        recs = slot_people(prg, g, k, night)
        if i < len(recs):
            x, y = dq4talk.pos(recs[i], night)
            out.append(f'{"밤" if night else "낮"} ({x:02X},{y:02X}) 대화 {dq4talk.talk_id(recs[i], night):03X}')
    if len(out) == 2 and out[0][1:] == out[1][1:]:
        out = [out[0][2:]]
    return f'인물 {i}(' + (', '.join(out) or '보통 목록에 없음') + ')'


def hidden(prg, story=True):
    """[(그룹, 순번, 루틴, [(인물 번호, 하는 일, 조건 합)])]: 1C:$A010 장소 루틴 전부와 1C:$AD32 의 장 줄.
    story 면 진행 관계로 나올 수 없는 조합을 거른다."""
    global RULES, ORDER
    RULES = progress_rules(prg) if story else None
    ORDER = order_rules(prg) if story else {}
    out = [(g, k, p, hide_table(prg, p)) for g, k, p in hide_routines(prg)]
    for g, k, c, i in chapter_hides(prg):
        out.append((g, k, CHAPTER_HIDE, [(i, '숨김', [[(('num', '장', '=', c), False)]])]))
    return out


SYM_ADDRS = {v: k for k, v in SYMBOLS.items()}


def sym_value(sym, mem):
    """조건의 값 이름을 메모리 덤프로 셈. 셀 수 없으면(아이템 소지 등) None."""
    base, _, mask = sym.partition('&')
    a = SYM_ADDRS.get(base)
    if a is None and base.startswith('$') and all(ch in '0123456789ABCDEF' for ch in base[1:]):
        a = int(base[1:], 16)
    if a is None:
        return None
    return mem[a] & (int(mask, 16) if mask else 0xFF)


def predict_hidden(prg, start, mem):
    """덤프의 플래그·장·시간·자리로 맞는 길을 골라 (숨기는 인물 번호들, 맞는 길 수)."""
    hits = []
    for path, eff in hide_paths(prg, start):
        vals = [(c, sym_value(c[0], mem)) for c in path]
        if all(v is None or holds(c[1], c[2], v) for c, v in vals):
            hits.append({i for i, what in hide_keys(eff) if what == '숨김'})
    return (hits[0] if len(hits) == 1 else set.intersection(*hits) if hits else set()), len(hits)


COL_ADDRS = {v: a for a, v in SLOT_COLS.items()}
SYM_EXPR = re.compile(r'\$([0-9A-F]{4})((?:[&|][0-9A-F]{2})*)$')


def expect_value(v, mem):
    """옮김 효과 값 → (아는 비트 마스크, 값). '$7006&FC|02' 는 루틴 앞 값의 일부만 정하므로 정한 비트만 안다.
    덤프로 셀 수 없으면 None."""
    if isinstance(v, int):
        return 0xFF, v
    if v in SYM_ADDRS:
        return 0xFF, mem[SYM_ADDRS[v]]
    m = SYM_EXPR.match(v)
    if not m:
        return None
    ops = re.findall(r'([&|])([0-9A-F]{2})', m.group(2))
    if not ops:
        return 0xFF, mem[int(m.group(1), 16)]
    known = val = 0
    for o, x in ops:
        x = int(x, 16)
        if o == '&':
            known, val = known | ~x & 0xFF, val & x
        else:
            known, val = known | x, val | x
    return known, val


def predict_moves(prg, start, mem):
    """덤프의 플래그·장·시간·자리로 맞는 길들이 모두 같게 정하는 {(인물 번호, 열): (마스크, 값)}."""
    got = None
    for path, eff in hide_paths(prg, start):
        if not all(v is None or holds(c[1], c[2], v) for c in path for v in [sym_value(c[0], mem)]):
            continue
        want = {}
        for e in eff:
            if e[0] == 'pos' and e[2] and isinstance(e[1], int):
                want[(e[1], e[2])] = expect_value(e[3], mem)
        want = {key: v for key, v in want.items() if v is not None}
        got = want if got is None else {key: v for key, v in got.items() if want.get(key) == v}
    return got or {}


def compare_hidden(prg, g, k, path):
    """seq.lua·warp.lua 덤프(폴더) 또는 atpc.lua 덤프의 인물 표에서 자리가 (80,80) 인 슬롯과 장소 루틴의 예측을 비교하고,
    옮김·방향·간격·상태·그림 열도 예측과 비교한다."""
    mem = dq4map.cpu_dump(path)
    night = mem[TIME] >= dq4map.NIGHT
    recs = [r for r in dq4map.place_records(prg, g, k, dq4map.ram_flags(mem)) if r[0] & (0x08 if night else 0x10)]
    got = {i for i in range(len(recs)) if mem[0x6F66 + i] == 0x80 and mem[0x6F86 + i] == 0x80}
    want, n = set(), 0
    for rg, rk, p in hide_routines(prg):
        if (rg, rk) == (g, k):
            want, n = predict_hidden(prg, p, mem)
    for cg, ck, c, i in chapter_hides(prg):
        if (cg, ck) == (g, k) and mem[0x615A] != c:
            want.add(i)
    want = {i for i in want if i < len(recs)}
    print(f'{g:02X}/{k:02X} {"밤" if night else "낮"} 인물 {len(recs)}명, 맞는 길 {n}개')
    print(f'덤프 (80,80): {sorted(got)}  예측 숨김: {sorted(want)} — {"같음" if got == want else "다름"}')
    moves = {}
    for rg, rk, p in hide_routines(prg):
        if (rg, rk) == (g, k):
            moves = predict_moves(prg, p, mem)
    bad = 0
    for (i, col), (mask, val) in sorted(moves.items()):
        if i in want:
            continue
        now = mem[COL_ADDRS[col] + i]
        ok = now & mask == val & mask
        bad += not ok
        print(f'  인물 {i} {col} ${COL_ADDRS[col] + i:04X} = {now:02X}  예측 {val:02X}'
              f'{"" if mask == 0xFF else f"(마스크 {mask:02X})"} — {"같음" if ok else "다름"}')
    if moves:
        print(f'옮김 열 {len(moves)}개 중 다름 {bad}')


def show_hidden(prg, as_json=False, story=True):
    rows = hidden(prg, story)
    if as_json:
        import json
        print(json.dumps([{'group': g, 'index': k, 'routine': f'1C:{p:04X}',
                           'acts': [{'person': i, 'act': what, 'when': [[atom_text(a, t) for a, t in conj] for conj in terms]}
                                    for i, what, terms in acts]} for g, k, p, acts in rows],
                         ensure_ascii=False, indent=1))
        return
    for g, k, p, acts in rows:
        print(f'{g:02X}/{k:02X} 1C:{p:04X}')
        for i, what, terms in acts:
            who = person_text(prg, g, k, i, terms) if i is not None else '그 밖'
            print(f'  {who} {what}: {terms_text(terms)}')
    print(f'장소 {len(rows)}곳')


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    a = sys.argv[2:]
    if not a:
        show_all(prg)
    elif a[0] == 'people':
        show_people(prg)
    elif a[0] == 'order':
        show_order(prg)
    elif a[0] == 'hidden' and '--compare' in a:
        compare_hidden(prg, int(a[1], 16), int(a[2], 16), a[a.index('--compare') + 1])
    elif a[0] == 'hidden':
        show_hidden(prg, '--json' in a, '--raw' not in a)
    else:
        g, k = int(a[0], 16), int(a[1], 16)
        ram = open(a[3], 'rb').read() if len(a) > 3 and a[2] == '--compare' else None
        sram = open(a[4], 'rb').read() if ram is not None and len(a) > 4 else None
        show(prg, g, k, ram, sram)


if __name__ == '__main__':
    main()
