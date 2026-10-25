"""DQ5(SFC) 상점 품목과 물건 가격. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「상점」.

대화 번호 000~010 은 06:DBD2 가 06:DBDB 점프 표로 처리한다(01 무기점, 02 도구점, 03 방어구점, 08 よろず屋 …).
가게 처리기가 목록 종류를 7E:0F20 에, 찾을 키를 7E:0F25 에 두면 06:F49C 가 04:FBD5[종류] 에서
[키][물건 번호 …][FF] 목록을 키가 같은 것이 나올 때까지 찾는다. 무기·도구·방어구점의 키는 맵 그룹 $BC 다(06:DC37).
같은 키의 목록이 둘 이상이면 06:F4CB 가 이야기 진행 플래그(7E:2190 & 40 등)나 주인공 Y 좌표로 뒤의 목록을 고른다(코드 읽기).
가격은 21:A447 이 물건마다 두 표로 계산한다.
작은 메달(09)과 코인 교환(0C)은 よろず屋 목록 키 16·15 를 띄우고, 값은 04:FD55(메달 수)·04:FD5B(코인 24비트)에서
목록 안 순번으로 읽는다(06:EC8D, 06:F06A). 여관(06·10)은 04:FD6D 의 [BC][1인 값] 에서 맵 그룹을 찾는다(06:F563).

사용:
  python sfc/dq5/tools/dq5shop.py rom/dq5.sfc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

LISTS = 0x04FBD5
# 21:A447. 가격 = 23:B081[물건] × 21:A47B[23:B159[물건] & 3](1, 10, 100, 1000). 물건은 216개(23:B081~B158).
PRICE_BASE = 0x23B081
PRICE_SCALE = 0x23B159
SCALES = (1, 10, 100, 1000)
ITEMS = 0xD8
# 종류 0~3 의 목록은 빈틈없이 이어지고, 종류 3 은 메달 값 표 앞에서 끝난다.
KINDS = ('도구점', '방어구점', '무기점', 'よろず屋')
END = 0x04FD55
MEDAL_KEY, MEDAL_PRICES = 0x16, 0x04FD55
COIN_KEY, COIN_PRICES = 0x15, 0x04FD5B
# 끝 표시가 없다. 06:F563 은 맵 그룹이 나올 때까지 훑는다. 22·01·21 은 이야기 진행 플래그(7E:2190 & 40,
# 21 은 & 20 도)가 켜지면 둘째 항목을 쓴다. 값 bit7 은 $0F36 으로 가는 미확인 플래그다.
INNS = 0x04FD6D
INN_COUNT = 21
# 26:8E5A. 시합 = 23:DC27 문턱 50개 중 주인공 레벨 이하인 것의 수 - 1 까지에서 난수, 23:DA97 + 시합*8 = [몬스터][倍率] x4.
ARENA_MATCHES, ARENA_LEVELS, ARENA_COUNT = 0x23DA97, 0x23DC27, 50
# 11:DDD5. 슬라임 레이스 다섯 값의 바탕 줄 5개(넷은 90~110% 난수, 다섯째 = 256 - 합). 11:E02F 는 쌍의 순서.
SLIME_ROWS = 0x11E0B5
SLIME_PAIRS = 0x11E02F


def monster_name(rom, n):
    return text(string_codes(rom, string(rom, 4, n)))


def price(rom, item):
    return rom.u8(PRICE_BASE + item) * SCALES[rom.u8(PRICE_SCALE + item) & 3]


def shop_lists(rom):
    """[(종류, 키, [물건 번호])]."""
    starts = [0x040000 | rom.u16(LISTS + 2 * k) for k in range(len(KINDS))] + [END]
    out = []
    for kind in range(len(KINDS)):
        a = starts[kind]
        while a < starts[kind + 1]:
            key, a = rom.u8(a), a + 1
            items = []
            while rom.u8(a) != 0xFF:
                items.append(rom.u8(a))
                a += 1
            a += 1
            out.append((kind, key, items))
    return out


def prize_lists(rom):
    """[(이름, [(물건 번호, 값)])]. 작은 메달은 메달 수, 코인 교환은 코인 수."""
    lists = {key: items for kind, key, items in shop_lists(rom) if kind == 3}
    medals = [(i, rom.u8(MEDAL_PRICES + k)) for k, i in enumerate(lists[MEDAL_KEY])]
    coins = [(i, rom.u16(COIN_PRICES + 3 * k) | rom.u8(COIN_PRICES + 3 * k + 2) << 16)
             for k, i in enumerate(lists[COIN_KEY])]
    return [('작은 메달', medals), ('코인 교환', coins)]


def inns(rom):
    """04:FD6D. [(맵 그룹, 1인 값, bit7)]."""
    return [(rom.u8(INNS + 2 * k), rom.u8(INNS + 2 * k + 1) & 0x7F, rom.u8(INNS + 2 * k + 1) >> 7)
            for k in range(INN_COUNT)]


def arena(rom):
    """[(문턱 레벨, [(몬스터, 倍率)])]. 몬스터 FF 는 빈 자리라 뺀다."""
    out = []
    for k in range(ARENA_COUNT):
        a = ARENA_MATCHES + k * 8
        fighters = [(rom.u8(a + 2 * i), rom.u8(a + 2 * i + 1)) for i in range(4) if rom.u8(a + 2 * i) != 0xFF]
        out.append((rom.u8(ARENA_LEVELS + k), fighters))
    return out


def slime_odds(rom, weights):
    """다섯 값 → 쌍 10개의 倍率(11:DF49, 11:DD7B)."""
    out = []
    for k in range(10):
        i, j = rom.u8(SLIME_PAIRS + 2 * k), rom.u8(SLIME_PAIRS + 2 * k + 1)
        a, b = weights[i] * 16 // 14 & 0xFF, weights[j] * 16 // 14 & 0xFF
        ra, rb = -a & 0xFF, -b & 0xFF
        # 256·(256-a)(256-b) 을 a·b·((256-a)+(256-b)) 로 나눈 몫 + 1, 몫이 2 미만이면 2. 8비트로 넘친다.
        q = ra * rb * 256 // (a * b * (ra + rb))
        odds = (2 if q < 2 else q + 1) & 0xFF
        if odds >= 31:
            odds = odds * 7 // 10
        elif odds >= 11:
            odds = odds * 9 // 10
        out.append((i + 1, j + 1, odds))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    for kind, key, items in shop_lists(rom):
        print(f'{KINDS[kind]} {key:02X}: ' + ', '.join(f'{item_name(rom, i)} {price(rom, i)}G' for i in items))
    for name, items in prize_lists(rom):
        print(f'{name}: ' + ', '.join(f'{item_name(rom, i)} {v}' for i, v in items))
    for k, (level, fighters) in enumerate(arena(rom)):
        print(f'격투장 {k:2d} (레벨 {level}~): ' + ', '.join(f'{monster_name(rom, m)} {odds}' for m, odds in fighters))
    for r in range(5):
        print(f'슬라임 레이스 줄 {r}: ' + ' '.join(str(rom.u8(SLIME_ROWS + 5 * r + i)) for i in range(5)))
    print('여관(1인): ' + ', '.join(f'{bc:02X} {v}G' + ('*' if flag else '') for bc, v, flag in inns(rom)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
