"""DQ5(SFC) 일행 작전 AI 의 표. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「작전 AI」.

  작전 값      7E:2034 (0 ガンガンいこうぜ … 4 いのちだいじに, 5 めいれいさせろ)
  작전 레코드  21:D8BD + 작전*32, 0~4 만 (21:D853 이 $126F~$1278·$1237~$123A 로 펼침)
  행동 레코드  21:BC86 + 행동*5 (물건은 21:C136 + 물건*5)
  배율 표      27:8254 (작전 2 는 27:82B4, 쉬운 전투는 27:8284), 갈래 21:D25B
  학습         7E:2A26 + 몬스터 종류/4, 2비트씩(만난 라운드 수, 최대 3)

사용:
  python sfc/dq5/tools/dq5tactics.py rom/dq5.sfc
  python sfc/dq5/tools/dq5tactics.py rom/dq5.sfc --actions
  python sfc/dq5/tools/dq5tactics.py rom/dq5.sfc --check
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import dq5spell  # noqa: E402
from dq5chest import item_name  # noqa: E402
from dq5map import Rom  # noqa: E402

TACTICS = 0x21D8BD
TACTIC_COUNT = 5
# 작전 레코드 바이트 → 펼치는 WRAM(21:D853). +10·+12 는 16비트.
TACTIC_FIELDS = ((0, 0x126F), (1, 0x1270), (2, 0x1273), (3, 0x1274), (4, 0x1275), (5, 0x1276), (6, 0x1277),
                 (7, 0x1237), (8, 0x1238), (9, 0x1239), (0xA, 0x123A))
TACTIC_WORDS = ((0x10, 0x1271), (0x12, 0x1278))
ACTIONS = 0x21BC86
ITEMS = ACTIONS + 0x4B0
ITEM_COUNT = 0xD8
ODDS = {'보통': 0x278254, '작전 2': 0x2782B4, '쉬운 전투': 0x278284}
ODDS_GROUP = 0x21D25B
ODDS_GROUPS = 0x12
NAMES = ('ガンガンいこうぜ', 'みんながんばれ', 'じゅもんせつやく', 'じゅもんつかうな', 'いのちだいじに', 'めいれいさせろ')
RANGES = {0x00: '적 하나', 0x20: '적 그룹', 0x40: '적 전체', 0x60: '우리 하나', 0x80: '우리 전체'}


def tactic(rom, t):
    return [rom.u8(TACTICS + t * 32 + i) for i in range(32)]


def heal_line(rom, t, max_hp):
    """위급 회복 문턱(21:EC17): HP ≤ 최대/2 이고 HP − 예상 피해 < 최대 × +6 / 256."""
    return (max_hp * tactic(rom, t)[6]) >> 8


def action(rom, n, item=False):
    """(+0 종류 비트, +1 기대 값, +2 평가 갈래, +3 MP, +4 범위·내성)."""
    base = ITEMS if item else ACTIONS
    return [rom.u8(base + n * 5 + i) for i in range(5)]


def describe(rec):
    kind, value, cls, mp, r = rec
    rng = RANGES.get(r & 0xE0, f'{r & 0xE0:02X}')
    res = '' if r & 0x1F == 0x1F else f' 내성{(r & 0x1F) + 0x50:02X}'
    return f'종류{kind:02X} 값{value} 갈래{cls:02X} MP{mp} {rng}{res}'


def check(rom):
    """+3 과 26:839A 의 MP, +4 하위 5비트 + 50 과 실행 루틴의 내성 칸을 견줌."""
    same = [0, 0, 0, 0]
    for n in range(dq5spell.COUNT):
        rec = action(rom, n)
        mp = dq5spell.cost(rom, n)[0]
        mp = 0 if mp is None else mp
        if isinstance(mp, int):
            same[0 if rec[3] == mp else 1] += 1
        _, _, ldx, target = dq5spell.handler(rom, n)
        if ldx is not None and ldx >= 0x50 and target is not None:
            same[2 if (rec[4] & 0x1F) + 0x50 == ldx else 3] += 1
    print(f'MP 같음 {same[0]} 다름 {same[1]}, 내성 같음 {same[2]} 다름 {same[3]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--actions', action='store_true', help='행동·물건 AI 레코드')
    ap.add_argument('--check', action='store_true', help='행동 레코드를 주문 표와 견줌')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        check(rom)
        return 0
    if args.actions:
        for n in range(dq5spell.COUNT):
            print(f'{n:02X} {dq5spell.name(rom, n)} {describe(action(rom, n))}')
        for n in range(ITEM_COUNT):
            rec = action(rom, n, item=True)
            if any(rec):
                print(f'물건 {n:02X} {item_name(rom, n)} {describe(rec)}')
        return 0
    for t in range(TACTIC_COUNT):
        rec = tactic(rom, t)
        bytes_ = ' '.join(f'${w:04X}={rec[i]:02X}' for i, w in TACTIC_FIELDS)
        words = ' '.join(f'${w:04X}={rec[i] | rec[i + 1] << 8:04X}' for i, w in TACTIC_WORDS)
        print(f'{t} {NAMES[t]} {bytes_} {words} 위급회복 HP-예상피해 < 최대×{rec[6]}/256')
    print(f'5 {NAMES[5]} 레코드 없음(동료에게 명령)')
    print('배율 표 [갈래*16 + 만난 수*4 + 내성 단계]:')
    for label, a in ODDS.items():
        for g in range(3):
            row = [rom.u8(a + g * 16 + i) for i in range(16)]
            print(f'  {label} 갈래{g}: ' + ' | '.join(' '.join(f'{v:02X}' for v in row[c * 4:c * 4 + 4]) for c in range(4)))
    print('내성 칸 50~61 의 갈래: ' + ' '.join(f'{rom.u8(ODDS_GROUP + i)}' for i in range(ODDS_GROUPS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
