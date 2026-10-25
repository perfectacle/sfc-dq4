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
  python sfc/dq5/tools/dq5tactics.py rom/dq5.sfc --score 3 6 10   (대상 값, MP, 최대 MP 로 작전마다 점수)
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


def word(rec, i):
    return rec[i] | rec[i + 1] << 8


def mp_factor(rec, mp, max_mp):
    """21:E9DD. MP 가 문턱(+2 × 최대 MP / 256) 이상이면 +10 비율로 깎음(+11 bit7 이면 더함), 256 이 1배."""
    if max_mp == 0 or mp < (rec[2] * max_mp) >> 8:
        return 0x100
    pen = ((word(rec, 0x10) & 0x7FFF) * mp) >> 8
    return 0x100 + pen if word(rec, 0x10) & 0x8000 else max(0, 0x100 - pen)


def target_value(tactic_no, damage, hp, worth, kill):
    """21:D26D. worth = 1 + 대상 위협 7워드 합, kill = 7E:4039[대상](0~3). 작전 0 은 쓰러뜨릴 때 피해 + worth."""
    if damage < hp:
        return worth * damage // hp + 1
    return damage + worth if tactic_no == 0 else kill + worth


def metal_score(kinds):
    """21:FBB2. 살아 있는 적 종류마다 メタルスライム 1, はぐれメタル 2, メタルキング 3. 작전 +A 보다 크면 ドラゴラム."""
    return sum({0x2D: 1, 0x4B: 2, 0xA2: 3}.get(k, 0) for k in kinds)


def attack_score(rec, value, mp, max_mp, incoming):
    """21:E98C. value = 21:D26D 의 대상 값, incoming = 행동자가 받을 예상 피해(7E:4138+413A)."""
    div = mp + ((incoming * 0x16) >> 8) + 1
    return (value * rec[0] // div + value * rec[1]) * mp_factor(rec, mp, max_mp)


def heal_score(rec, power, mp, hp, max_hp, incoming, danger, critical):
    """21:EA94. 위급 표시(danger 7E:4136 bit6, critical bit7)가 없으면 0."""
    if not (danger or critical):
        return 0
    s = min(power, max_hp - hp) * rec[3] + incoming * rec[5] + ((999 - hp) << 8) - mp * rec[4] * 12
    if s < 0:
        return 0
    return s + (10 << 8 if danger or critical else 0) + (300 << 8 if critical else 0)


# 실측(PARTY=05,04 슬라임 셋, 21:E9DB·7E:4019 에서 읽음): (작전, 식, 인자, 값)
MEASURED = (
    (0, attack_score, (1, 0, 10, 0), 0x011100),
    (0, attack_score, (3, 4, 10, 0), 0x030700),
    (1, attack_score, (3, 6, 10, 0), 0x029630),
    (1, attack_score, (3, 10, 10, 0), 0x022024),
    (2, attack_score, (1, 2, 10, 0), 0x009345),
    (2, attack_score, (3, 4, 10, 0), 0x011CE2),
    (4, attack_score, (3, 6, 10, 0), 0x0292F0),
    (0, heal_score, (35, 3, 2, 24, 0, True, False), 0x03F6DA),
    (4, heal_score, (35, 3, 2, 24, 0, True, False), 0x03EA32),
)


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
    ok = sum(f(tactic(rom, t), *args) == want for t, f, args, want in MEASURED)
    print(f'점수 식 실측 {len(MEASURED)}개 중 {ok}개 같음')
    vals = ((0, 12, 5, 2, 3, 14), (0, 8, 5, 2, 3, 10), (0, 12, 200, 2, 3, 1))
    ok = sum(target_value(*v[:5]) == v[5] for v in vals)
    print(f'대상 값 실측 {len(vals)}개 중 {ok}개 같음')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--actions', action='store_true', help='행동·물건 AI 레코드')
    ap.add_argument('--check', action='store_true', help='행동 레코드를 주문 표와, 점수 식을 실측 값과 견줌')
    ap.add_argument('--score', nargs=3, type=int, metavar=('값', 'MP', '최대MP'), help='작전마다 공격·주문 점수')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        check(rom)
        return 0
    if args.score:
        for t in range(TACTIC_COUNT):
            print(f'{t} {NAMES[t]} {attack_score(tactic(rom, t), *args.score, 0):06X}')
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
