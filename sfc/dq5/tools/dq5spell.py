"""DQ5(SFC) 주문·행동 표. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「주문과 행동」.

행동 번호(주문 01~38, 몬스터용 주문 39~65, 몬스터 행동 66~AA)는 이름 표 3번(21:959B)과 순서가 같다.
  MP·범위   26:8765[행동] (26:839A·26:83D0). bit0-4 MP(1F 없음, 1E = 36, 1D = 남은 MP 전부), bit5-6 범위, bit7 적 쪽
  실행 루틴 26:8865 + 행동*2 (뱅크 20). 공통 루틴 975F 적 하나, 9771 적 그룹, 97BC 적 전체, 9824 우리 편 하나,
  9829 우리 편 전체가 대상을 돌며 처리 루틴을 부른다. 대상 수는 이 표가 정한다. 나머지는 행동 전용 루틴
  처리 루틴 20:B7F9 + 행동*2. 루틴 첫머리가 LDX #내성 종류 / LDA #표 번호 를 넣고 공통 루틴으로 뛴다
  피해·회복량 27:8071 + (표 번호 & 3F)*2 = [바탕][폭]. 값 = 바탕(FE 이면 300) + 난수(0 ~ 폭-1) (20:AB70)
내성 종류(50~61)는 몬스터 레코드 +0C~+10 의 2비트 칸이다(21:91F9 + 종류*2, sfc/dq5/tools/dq5monster.py).
피해 주문이 몬스터에게: 값 × 27:8055[내성 단계] / 256(FF 면 그대로). 상태 주문 20:AE41 은 몬스터에게 20:AECC 로 가서
내성 단계 0 이면 반드시, 그 밖에는 난수(0~255) < 27:8055[단계] 일 때 걸린다(255 205 84 0). 주인공 레벨 − 10 이
구역 레벨($100F) 이상이면 표가 27:8059(255 255 169 0)로 바뀐다. 우리 쪽에게는 난수(0~7) < LDA # 값(「아군n/8」).

사용:
  python sfc/dq5/tools/dq5spell.py rom/dq5.sfc
  python sfc/dq5/tools/dq5spell.py rom/dq5.sfc --table   (주문 01~65 의 내성 단계별 피해·성공률, 몬스터 주문의 일행 피해)
  python sfc/dq5/tools/dq5spell.py rom/dq5.sfc --armor   (주문 피해를 줄이는 갑옷·방패)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import string, string_codes, text  # noqa: E402

NAMES = 3
COUNT = 0xAB
COSTS = 0x268765
HANDLERS = 0x20B7F9
TARGETS = 0x268865
TARGET_KINDS = {0x975F: '하나', 0x9771: '그룹', 0x97BC: '전체', 0x9824: '우리하나', 0x9829: '우리전체'}
AMOUNTS = 0x278071
RANGES = ('자신', '하나', '그룹', '전체')
# 20:B307(주문)·20:B657(숨)·20:AB70 은 27:8071 의 양을 쓰고, 20:AE41·AEC6·AEFF 는 내성으로 성공을 가른다.
AMOUNT_ROUTINES = (0xB307, 0xB657, 0xAB70)
STATUS_ROUTINES = (0xAE41, 0xAEC6, 0xAEFF)


def name(rom, n):
    return text(string_codes(rom, string(rom, NAMES, n)))


def cost(rom, n):
    """26:839A. (MP, 범위 0~3, 적 쪽인가). MP 가 None 이면 MP 를 쓰지 않는 행동."""
    v = rom.u8(COSTS + n)
    mp = {0x1F: None, 0x1E: 36, 0x1D: 'all'}.get(v & 0x1F, v & 0x1F)
    return mp, (v >> 5) & 3, bool(v & 0x80)


def handler(rom, n):
    """20:B7F9 의 루틴 주소와, 첫머리에서 읽은 (LDA #, LDX #, 뛰는 곳)."""
    a = 0x200000 | rom.u16(HANDLERS + n * 2)
    p, lda, ldx = a, None, None
    if rom.u8(p) == 0xE2:
        p += 2
    for _ in range(4):
        op = rom.u8(p)
        if op == 0xA9:
            lda = rom.u8(p + 1)
        elif op == 0xA2:
            ldx = rom.u8(p + 1)
        elif op == 0x86:
            pass
        elif op in (0x4C, 0x20):
            return a & 0xFFFF, lda, ldx, rom.u16(p + 1)
        else:
            break
        p += 2
    return a & 0xFFFF, lda, ldx, None


def spread(rom, n):
    """26:8865. 실행 루틴 주소와 이름(공통 루틴이 아니면 주소만)."""
    a = rom.u16(TARGETS + n * 2)
    return a, TARGET_KINDS.get(a, f'{a:04X}')


def amount(rom, k):
    """27:8071. 표 번호 k 의 (바탕, 폭)."""
    a = AMOUNTS + (k & 0x3F) * 2
    base = rom.u8(a)
    return 300 if base == 0xFE else base, rom.u8(a + 1)


def describe(rom, n):
    mp, rng, enemy = cost(rom, n)
    addr, lda, ldx, target = handler(rom, n)
    out = [f'{n:02X}', name(rom, n)]
    out.append('MP-' if mp is None else f'MP{mp}')
    out.append(('적 ' if enemy else '편 ') + RANGES[rng])
    out.append('대상' + spread(rom, n)[1])
    out.append(f'루틴{addr:04X}')
    if target in AMOUNT_ROUTINES and lda is not None:
        base, width = amount(rom, lda)
        out.append(f'양{lda:02X}={base}~{base + max(width, 1) - 1}')
    elif target == 0xAE41 and lda is not None:
        out.append(f'아군{lda}/8')
    elif target in STATUS_ROUTINES and lda is not None:
        out.append(f'값{lda:02X}')
    if ldx is not None and ldx >= 0x50 and target is not None:
        out.append(f'내성{ldx:02X}')
    return ' '.join(out)


RESIST = 0x278055       # 내성 단계 0~3 의 배율(/256), 피해와 상태 성공 모두
RESIST_EASY = 0x278059  # 주인공 레벨 - 10 >= 구역 레벨일 때


def resist_rates(rom, easy=False):
    t = RESIST_EASY if easy else RESIST
    return [rom.u8(t + i) for i in range(4)]


def damage_range(rom, n, level, easy=False):
    """피해 주문 n 이 내성 단계 level 인 몬스터에게 주는 (최소, 최대). 피해 주문이 아니면 None (20:AB70·20:AB9E)."""
    addr, lda, ldx, target = handler(rom, n)
    if target not in AMOUNT_ROUTINES or lda is None or ldx is None or ldx < 0x50:
        return None
    base, width = amount(rom, lda)
    lo, hi = base, base + max(width, 1) - 1
    r = resist_rates(rom, easy)[level]
    if r == 0xFF:
        return lo, hi
    return lo * r >> 8, hi * r >> 8


def status_chance(rom, level, easy=False):
    """상태 주문이 내성 단계 level 인 몬스터에게 걸릴 확률(/256). 20:AECC."""
    return 256 if level == 0 else resist_rates(rom, easy)[level]


# 표 밖 처리 루틴의 뜻(코드 읽기, 20:B1AB~B2FA)
SPECIAL = {
    0xB1AB: '대상 값(20:9F41 & 3)이 3 이 아니면 20:AEC6(내성 59), 3 이면 ザキ 판정(내성 56)',
    0xB1D4: '내성 57, 20:AEFF 로 27:8059(255·255·169·0) 판정',
    0xB1F8: '내성 5B 판정 뒤 양 번호 31(5~11)만큼 MP 를 빼앗음(대상 MP 까지)',
    0xB224: '내성 5A, 20:AF05 판정 뒤 수비력을 min(레코드 수비, 지금 수비) 만큼 깎음',
    0xB278: '수비력을 min(기본 수비(필드 13), 2 × 기본 수비(필드 13) − 지금 수비) 만큼 올림',
    0xB256: '내성 5A, 20:AECC(27:8055) 판정 뒤 수비력을 min(레코드 수비 / 2, 지금 수비) 만큼 깎음',
    0xB2A6: '수비력을 min(기본 수비(필드 13) / 2, 2 × 기본 수비 − 지금 수비) 만큼 올림',
    0xB17E: '실행 루틴이 대상 없는 9D18 이라 전투에서는 「となえた」 뒤 아무 일도 없음',
    0xB2D5: '최대 HP − HP 만큼 회복',
    0xB2FA: '우리 쪽 4/8',
}


ELEMENTS = 0x2780E3     # 행동 01~12·39~47 의 원소 비트(행동 - 01 / - 39), 27:80F5 는 숨 8E~94 (20:ABDC)
BREATH_ELEMENTS = 0x2780F5
ARMOR = 0x2780FC        # [원소 비트][갑옷·방패 물건][값] 3바이트 항목, 00 에서 끝. 값 bit7 이면 256 - 값 을 더함
ELEMENT_NAMES = {0x01: 'メラ', 0x02: 'ギラ', 0x40: 'イオ', 0x04: 'ヒャド', 0x08: 'バギ', 0x80: 'デイン', 0x10: '불숨', 0x20: '찬숨'}


def element(rom, n):
    """일행이 맞을 때 갑옷이 보는 원소 비트(없으면 0)."""
    if 0x01 <= n < 0x13:
        return rom.u8(ELEMENTS + n - 1)
    if 0x39 <= n < 0x48:
        return rom.u8(ELEMENTS + n - 0x39)
    if 0x8E <= n < 0x95:
        return rom.u8(BREATH_ELEMENTS + n - 0x8E)
    return 0


def armor_entries(rom):
    out, a = [], ARMOR
    while rom.u8(a):
        v = rom.u8(a + 2)
        out.append((rom.u8(a), rom.u8(a + 1), -(256 - v) if v & 0x80 else v))
        a += 3
    return out


def party_damage(rom, n, armor_items=()):
    """몬스터 주문 n 이 일행에게 주는 (최소, 최대). 갑옷·방패 물건 번호를 주면 27:80FC 값을 뺌(음수는 더함)."""
    addr, lda, ldx, target = handler(rom, n)
    if target not in AMOUNT_ROUTINES or lda is None or ldx is None or ldx < 0x50:
        return None
    base, width = amount(rom, lda)
    cut = sum(v for bit, item, v in armor_entries(rom) if bit & element(rom, n) and item in armor_items)
    return max(base - cut, 0), max(base + max(width, 1) - 1 - cut, 0)


def table(rom):
    for n in list(range(1, 0x39)) + list(range(0x39, 0x66)):
        mp, rng, enemy = cost(rom, n)
        addr, lda, ldx, target = handler(rom, n)
        head = f'{n:02X} {name(rom, n)} ' + ('MP-' if mp is None else f'MP{mp}') + ' ' + ('적 ' if enemy else '편 ') + RANGES[rng]
        if n >= 0x39 and spread(rom, n)[0] == 0x9D18 and addr in SPECIAL:
            print(head + f' 루틴{addr:04X} {SPECIAL[addr]}')
            continue
        if n >= 0x39:
            pd = party_damage(rom, n)
            if pd:
                el = ELEMENT_NAMES.get(element(rom, n), '-')
                print(head + f' 일행에게 {pd[0]}~{pd[1]}(원소 {el}, 갑옷 값을 뺌)')
                continue
        d = [damage_range(rom, n, lv) for lv in range(4)]
        if d[0]:
            print(head + f' 내성{ldx:02X} 단계0~3: ' + ' / '.join(f'{a}~{b}' for a, b in d))
        elif target == 0xAE41 and ldx is not None and ldx >= 0x50:
            ch = ' / '.join(f'{status_chance(rom, lv) * 100 // 256}%' for lv in range(4))
            print(head + (f' 일행에게 {lda}/8' if n >= 0x39 else f' 내성{ldx:02X} 몬스터 {ch}, 우리 {lda}/8'))
        elif target in AMOUNT_ROUTINES and lda is not None:
            base, width = amount(rom, lda)
            print(head + f' 회복 {base}~{base + max(width, 1) - 1}')
        else:
            print(head + f' 루틴{addr:04X}' + (f' {SPECIAL[addr]}' if addr in SPECIAL else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--table', action='store_true', help='주문 01~65 의 내성 단계별 피해·성공률, 몬스터 주문의 일행 피해')
    ap.add_argument('--armor', action='store_true', help='주문 피해를 줄이는 갑옷·방패(27:80FC)')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.table:
        table(rom)
        return 0
    if args.armor:
        from dq5chest import item_name
        for bit, item, v in armor_entries(rom):
            names = '·'.join(nm for b, nm in ELEMENT_NAMES.items() if bit & b)
            print(f'{item:02X} {item_name(rom, item)} {names} {"-" if v >= 0 else "+"}{abs(v)}')
        return 0
    for n in range(COUNT):
        print(describe(rom, n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
