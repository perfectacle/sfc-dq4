"""1장 라이안의 성장을 FC ライアン 곡선으로. 형식은 sfc/dq4/docs/dq4-growth-format.md.

DQ5 는 일행 기록 +0(종류)으로 성장 레코드를 고르고(23:EDCD, 사람 0 = 23:9E41), 능력치 값은 23:F12D, 경험치는
23:EDF6 이 그 레코드에서 셈한다. 1장 라이안은 사람 0 이다. FC 곡선(fc/dq4/docs/dq4-data-format.md 「성장 곡선」)은
능력치마다 꺾이는 레벨이 따로이고 경험치를 레벨마다 정수로 버리며 곱해, 꺾이는 레벨을 모두가 나눠 쓰는 DQ5 레코드로는
같은 값을 낼 수 없다. 그래서 레벨 0~100 의 값 표를 두고 세 곳에 훅을 건다(레코드가 사람 0 일 때만 표, 아니면 원래 길).

  23:F12D  능력치 값(A 레벨, X 능력치 0~6, Y 레코드) → $00. 표 STATS 에서 읽고 23:F1B9(PLX PLY RTS)로
  23:EDF6  경험치(X = 0: A 레벨 → $00·$02, X ≠ 0: $00·$02 경험치 → A 그 경험치로 닿는 레벨). 표 EXP 에서
  23:EC76  오르는 양을 1 로 줄이는 문턱. DQ5 는 지금 값 ≥ 값(L) × 1.5 이면 난수 0·1, FC 는 지금 값 ≥ 곡선(새 레벨)
           + 새 레벨/2 + 10 이면 rand(2)(12:$9DB3). 사람 0 은 FC 문턱을 쓴다. DQ5 문턱이면 かしこさ 처럼 곡선이 1 인
           구간에서 지금 값 1 ≥ 1 + 0 이라 늘 난수로 가 곡선을 벗어난다

능력치 대응(dq5growth.STATS 차례): 최대 HP ← 2 × たいりょく 곡선(FC 와 같은 셈, 999 까지), 최대 MP ← 0(FC 는 0~4번만
MP 가 오름), ちから·すばやさ·かしこさ·うんのよさ ← 같은 이름, みのまもり ← たいりょく(1장 레벨업 메시지·2장 기록과 같은
자리). 능력치는 255 까지. 1레벨 기록(23:C014 칸 0)도 FC 장 시작 값으로 둔다: 최대 HP 는 곡선이 아니라 12:$A296 표.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

FC_RYAN = 6                     # FC 인물 번호 ライアン(dq4data.PARTY)
HERO_GROWTH = 0x9E41            # 사람 0 성장 레코드(23:EDCD 의 Y)
LEVELS = 101                    # 표 줄: 레벨 0~100. 23:EB50 이 레벨 99 에서 100 의 값도 셈한다
STAT_COUNT = 7
STAT_CAP, HP_CAP, EXP_CAP = 255, 999, 9999999
# 57:8000 던전 걸음(dq4dungeonrate)과 57:F000 보상(dq4balance) 사이의 빈 자리
GROWTH_AT = 0x57E000

STAT_AT, STAT_ORIG, STAT_GO, STAT_DONE = 0x23F12D, bytes.fromhex('5a da 85 0f'), 0x23F131, 0x23F1B9
EXP_AT, EXP_ORIG, EXP_GO = 0x23EDF6, bytes.fromhex('85 09 8e bb 09'), 0x23EDFB
EXP_RTS = 0x23EEF1              # 원래 X = 0 갈래 끝의 RTS(M 16)
GAIN_AT = 0x23EC76
GAIN_ORIG = bytes.fromhex('c2 20 b9 97 09 4a 18 79 97 09 99 97 09')
# 23:EB50 이 둔 값: 종류(일행 기록 +0), 지금 레벨, 능력치마다 값(L)·값(L+1)(16비트씩)
KIND, LEVEL, NOW, NEXT = 0x09A5, 0x09A6, 0x0997, 0x09A7

PERSON_TABLE = 0x23C014         # 새 게임의 일행 기록 틀(42바이트, 칸 0 이 주인공)
FIRST_FIELDS = ((0x02, 2, 'hp'), (0x0E, 2, 'hp'), (0x04, 2, 'mp'), (0x10, 2, 'mp'), (0x06, 1, 'agi'),
                (0x07, 1, 'str'), (0x08, 1, 'vit'), (0x09, 1, 'int'), (0x0A, 1, 'luck'), (0x26, 3, 'next'))


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


FC_TOOLS = ROOT / 'fc' / 'dq4' / 'tools'
DQ4 = ROOT / 'rom' / 'dq4.nes'


def _fc(dq4=DQ4):
    from kr_patch.fc import ines
    if str(FC_TOOLS) not in sys.path:
        sys.path.insert(0, str(FC_TOOLS))
    import dq4data
    return dq4data, ines.prg(Path(dq4).read_bytes())


def fc_stats(dq4data, prg, level, who=FC_RYAN):
    """FC 곡선 기준값을 dq5growth.STATS 차례로(최대 HP, 최대 MP, ちから, すばやさ, かしこさ, うんのよさ, みのまもり)."""
    c = lambda stat: dq4data.curve(prg, who, stat, max(level, 1))[0]  # noqa: E731
    stat = lambda v: min(v, STAT_CAP)  # noqa: E731
    mp = c(7) if who < 5 else 0
    return [min(c(6), HP_CAP), min(mp, HP_CAP), stat(c(1)), stat(c(2)), stat(c(4)), stat(c(5)), stat(c(3))]


def fc_exp(dq4data, prg, level, who=FC_RYAN):
    """그 레벨이 되는 누적 경험치."""
    return min(dq4data.curve(prg, who, 0, max(level, 1))[0], EXP_CAP)


def tables(dq4=DQ4, who=FC_RYAN):
    """(능력치 표 [레벨][능력치], 경험치 표 [레벨]), 레벨 0~100."""
    dq4data, prg = _fc(dq4)
    return ([fc_stats(dq4data, prg, lv, who) for lv in range(LEVELS)],
            [fc_exp(dq4data, prg, lv, who) for lv in range(LEVELS)])


def first_record(dq4=DQ4, who=FC_RYAN):
    """1레벨 기록 값: FC 장 시작 루틴(12:$8EAE)과 같게 능력치는 곡선 1레벨, 최대 HP 는 12:$A296 표."""
    dq4data, prg = _fc(dq4)
    import dq4event
    c = lambda stat: dq4data.curve(prg, who, stat, 1)[0]  # noqa: E731
    return {'hp': dq4data.rd(prg, dq4event.INIT, dq4event.CHAR_HP + who), 'mp': 0, 'str': c(1), 'agi': c(2),
            'vit': c(3), 'int': c(4), 'luck': c(5), 'next': fc_exp(dq4data, prg, 2, who)}


def code(stats, exp, at=GROWTH_AT):
    """훅 세 개와 표. (바이트, 이름표)."""
    a = _Asm(at)
    top = (LEVELS - 1).to_bytes(2, 'little')
    # 능력치(M 8, X 16, DB 23). 원래 앞 네 바이트(PHY PHX STA $0F)를 먼저 한다
    a.label('stat').b(0x5A, 0xDA, 0x85, 0x0F, 0xC0, *HERO_GROWTH.to_bytes(2, 'little')).rel(0xF0, 'stat_hero')
    a.b(0x5C, *STAT_GO.to_bytes(3, 'little'))
    a.label('stat_hero').b(0xC2, 0x20, 0x29, 0xFF, 0x00, 0xC9, LEVELS, 0x00).rel(0x90, 'stat_row')
    a.b(0xA9, *top)
    # 줄 = 레벨 × 7(8L - L) + 능력치, 칸 2바이트. $02 는 F12D 가 쓰는 임시 자리라 덮어도 된다
    a.label('stat_row').b(0x85, 0x02, 0x0A, 0x0A, 0x0A, 0x38, 0xE5, 0x02, 0x85, 0x02, 0x8A, 0x18, 0x65, 0x02, 0x0A, 0xAA)
    a.long(0xBF, 'stats').b(0x85, 0x00, 0xE2, 0x20, 0x5C, *STAT_DONE.to_bytes(3, 'little'))

    # 경험치(M 16, X 16). 원래 앞 다섯 바이트(STA $09, STX $09BB)를 먼저 한다
    a.label('exp_hook').b(0x85, 0x09, 0x8E, 0xBB, 0x09, 0xC0, *HERO_GROWTH.to_bytes(2, 'little')).rel(0xF0, 'exp_hero')
    a.b(0x5C, *EXP_GO.to_bytes(3, 'little'))
    a.label('exp_hero').b(0xE0, 0x00, 0x00).rel(0xD0, 'reach')
    a.b(0x29, 0xFF, 0x00, 0xC9, LEVELS, 0x00).rel(0x90, 'exp_row').b(0xA9, *top)
    a.label('exp_row').b(0x48, 0x0A, 0x0A, 0xAA).long(0xBF, 'exp').b(0x85, 0x00).long(0xBF, 'exp', 2)
    a.b(0x85, 0x02, 0x68, 0x5C, *EXP_RTS.to_bytes(3, 'little'))
    # 경험치 → 레벨: 레벨 2 부터 표 값이 $02:$00 보다 큰 첫 레벨 - 1(원래처럼 같으면 그 레벨까지). 99 에서 멈춘다
    a.label('reach').b(0xA0, 0x02, 0x00, 0xA2, 0x08, 0x00)
    a.label('reach_loop').long(0xBF, 'exp', 2).b(0xC5, 0x02).rel(0x90, 'reach_next').rel(0xD0, 'reach_done')
    a.long(0xBF, 'exp').b(0xC5, 0x00).rel(0xF0, 'reach_next').rel(0xB0, 'reach_done')
    a.label('reach_next').b(0xE8, 0xE8, 0xE8, 0xE8, 0xC8, 0xC0, LEVELS - 1, 0x00).rel(0x90, 'reach_loop')
    a.label('reach_done').b(0x88, 0x98, 0x5C, *EXP_RTS.to_bytes(3, 'little'))

    # 문턱(JSL, M 8 로 들어와 M 16 으로 RTL: 원래 자리의 REP #$20 을 대신함. Y = 능력치 × 2, DB 23)
    a.label('gain').b(0xC2, 0x20, 0xAD, *KIND.to_bytes(2, 'little'), 0x29, 0xFF, 0x00).rel(0xD0, 'gain_dq5')
    a.b(0xAD, *LEVEL.to_bytes(2, 'little'), 0x29, 0xFF, 0x00, 0x1A, 0x4A, 0x18, 0x69, 10, 0x00, 0x18)
    a.b(0x79, *NEXT.to_bytes(2, 'little'), 0x99, *NOW.to_bytes(2, 'little'), 0x6B)
    a.label('gain_dq5').b(0xB9, *NOW.to_bytes(2, 'little'), 0x4A, 0x18, 0x79, *NOW.to_bytes(2, 'little'))
    a.b(0x99, *NOW.to_bytes(2, 'little'), 0x6B)

    a.label('stats').b(*b''.join(v.to_bytes(2, 'little') for row in stats for v in row))
    a.label('exp').b(*b''.join(v.to_bytes(4, 'little') for v in exp))
    return a.assemble()


def _cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def _hex(b):
    return bytes(b).hex(' ').upper()


def calls(labels):
    """원래 루틴 세 자리를 훅으로 돌리는 쓰기."""
    gain = bytes((0x22, *labels['gain'].to_bytes(3, 'little'), 0x80, len(GAIN_ORIG) - 6)) + b'\xea' * (len(GAIN_ORIG) - 6)
    return [
        {'at': _cpu(STAT_AT), 'hex': _hex((0x5C, *labels['stat'].to_bytes(3, 'little'))), 'orig': _hex(STAT_ORIG),
         'note': '능력치 값(23:F12D)을 성장 훅으로'},
        {'at': _cpu(EXP_AT), 'hex': _hex((0x5C, *labels['exp_hook'].to_bytes(3, 'little'), 0xEA)),
         'orig': _hex(EXP_ORIG), 'note': '경험치 곡선(23:EDF6)을 성장 훅으로'},
        {'at': _cpu(GAIN_AT), 'hex': _hex(gain), 'orig': _hex(GAIN_ORIG), 'note': '오르는 양 문턱을 성장 훅으로'},
    ]


def writes(dq5, dq4=DQ4, at=GROWTH_AT):
    """dq5patch/1 쓰기: 훅·표, 세 자리의 훅 호출, 1레벨 기록."""
    stats, exp = tables(dq4)
    data, labels = code(stats, exp, at)
    if at >> 16 != (at + len(data) - 1) >> 16:
        raise ValueError('성장 표가 뱅크를 넘음')
    o = lorom(PERSON_TABLE)
    orig = dq5[o:o + 42]
    rec = bytearray(orig)
    first = first_record(dq4)
    for off, n, k in FIRST_FIELDS:
        rec[off:off + n] = first[k].to_bytes(n, 'little')
    return [{'at': _cpu(at), 'hex': _hex(data), 'note': '라이안 성장: FC ライアン 곡선 표와 훅'}, *calls(labels),
            {'at': _cpu(PERSON_TABLE), 'hex': _hex(rec), 'orig': _hex(orig), 'note': '라이안 1레벨 기록을 FC 장 시작 값으로'}]


def hooked(rom):
    """롬에 이 훅이 걸렸으면 (능력치 표 주소, 경험치 표 주소), 아니면 None."""
    o = lorom(STAT_AT)
    if rom[o] != 0x5C:
        return None
    stat = int.from_bytes(rom[o + 1:o + 4], 'little')
    o = lorom(stat)
    if rom[o:o + 4] != STAT_ORIG:
        return None
    _, labels = code([[0] * STAT_COUNT] * LEVELS, [0] * LEVELS, stat)
    return labels['stats'], labels['exp']


def stats_at(rom, kind, level):
    """롬이 레벨 level 에 주는 능력치 값(dq5growth.STATS 차례). 사람 0 이고 훅이 걸렸으면 표, 아니면 DQ5 레코드."""
    import dq5growth
    from dq5map import Rom
    at = hooked(rom) if kind == 0 else None
    if at is None:
        r = Rom(rom)
        return dq5growth.stats_at(r, dq5growth.record_address(kind), level)
    o = lorom(at[0]) + level * STAT_COUNT * 2
    return [int.from_bytes(rom[o + 2 * k:o + 2 * k + 2], 'little') for k in range(STAT_COUNT)]


def exp_at(rom, kind, level):
    import dq5growth
    from dq5map import Rom
    at = hooked(rom) if kind == 0 else None
    if at is None:
        return dq5growth.exp_at(Rom(rom), dq5growth.record_address(kind), level)
    o = lorom(at[1]) + min(level, LEVELS - 1) * 4
    return int.from_bytes(rom[o:o + 4], 'little')


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, help='빌드한 롬(주면 그 롬의 값, 없으면 FC 곡선)')
    ap.add_argument('--levels', default='1-20')
    args = ap.parse_args()
    lo, hi = (int(v) for v in args.levels.split('-'))
    if args.rom:
        rom = args.rom.read_bytes()
        rows = [(lv, stats_at(rom, 0, lv), exp_at(rom, 0, lv)) for lv in range(lo, hi + 1)]
    else:
        stats, exp = tables()
        rows = [(lv, stats[lv], exp[lv]) for lv in range(lo, hi + 1)]
    print('레벨  최대HP 최대MP ちから すばやさ かしこさ うんのよさ みのまもり  경험치')
    for lv, s, e in rows:
        print(f'{lv:4d} ' + ' '.join(f'{v:6d}' for v in s) + f' {e:8d}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
