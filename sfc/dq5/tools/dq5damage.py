"""DQ5(SFC) 보통 공격 피해 계산. 형식은 sfc/dq5/docs/dq5-data-format.md 의 「전투 계산식」.

보통 공격(たたかう, 처리 루틴 20:AF6C → 20:B030):
  공격력 = 공격하는 쪽 필드 10(일행, 7E:0760+칸*12 +0) / 38(몬스터), 수비력 = 맞는 쪽 필드 14(일행 +2) / 64(몬스터, 7E:07C0+칸*16 +8)
  h = (공격력 - 수비력/2) / 2   (나머지 버림)
  h 가 0 이하            → 난수 0~1
  맞는 쪽이 일행이고 공격력/16 ≥ h → 난수 0~공격력/16
  h < 8                  → h - 1 + 난수 0~2 (음수면 0)
  그 밖                  → h*7/8 + 난수(0~255) * (h/4 + 1) / 256
회심(일행이 공격할 때 20:C697, 1/32): 수비력을 보지 않고 공격력 * (55~65) * 4 / 256 (20:AB04)
방어 상태(20:AF85): 1 이면 절반, 2·3 이면 1/5. 주문이 몬스터에게: 양 × 27:8055[내성] / 256(255 면 그대로),
주인공 레벨 - 10 ≥ 무리 레벨이면 27:8059(20:AB9E).

잠(20:8944): 턴마다 카운터(일행 칸 +8 bit4-5, 처음 3)를 하나 줄이고 난수(0~3) < 20:8A49[카운터] = 4,3,2,1 이면 깸.
몬스터 행동 칸 고르기(21:B4D1, 필드 69): 0 고르게, 1~4 는 28:82BB 의 무게 표, 5·6 차례대로, 7 은 고르지 않음.
전투 도구(20:BA4C): 27:819A 의 물건 53개 → 20:C162 의 처리기. 처리기 안의 LDA #행동 / STA $10F7 이 효과 주문이다.

사용:
  python sfc/dq5/tools/dq5damage.py --items rom/dq5.sfc   # 전투 도구 53개와 효과 행동
  python sfc/dq5/tools/dq5damage.py 200 5            # 공격력 200, 수비력 5: 피해 범위와 회심 범위
  python sfc/dq5/tools/dq5damage.py 64 120 --party   # 맞는 쪽이 일행
"""
import argparse
import sys


def normal_range(attack, defense, target_party=False):
    """(최소, 최대) 피해. 20:B030."""
    diff = attack - defense // 2
    if diff < 0:
        return 0, 1
    h = diff >> 1
    if h == 0:
        return 0, 1
    if target_party and attack >> 4 >= h:
        return 0, attack >> 4
    if h < 8:
        return max(h - 1, 0), h + 1
    base = h * 7 // 8
    return base, base + (255 * ((h >> 2) + 1) >> 8)


def critical_range(attack):
    """20:AB04. 회심 피해(수비력 무시)."""
    return attack * 55 * 4 >> 8, attack * 65 * 4 >> 8


RESIST = (255, 205, 84, 0)
RESIST_HIGH = (255, 255, 169, 0)


def spell_on_monster(amount, resist, hero_level=1, group_level=0):
    """20:AB9E. 주문 양을 몬스터 내성 0~3 으로 줄인 값."""
    table = RESIST_HIGH if hero_level >= 10 and hero_level - 10 >= group_level else RESIST
    m = table[resist]
    return amount if m == 255 else amount * m >> 8


def guarded(damage, state):
    """20:AF85. 방어 상태 1 은 절반, 2·3 은 1/5."""
    return damage if state == 0 else damage >> 1 if state == 1 else damage // 5


WAKE = (4, 3, 2, 1)
AI_WEIGHTS = ((68, 58, 48, 38, 27, 17), (210, 29, 10, 4, 2, 1), (64, 64, 64, 21, 21, 21), (64, 64, 32, 32, 32, 32))
BATTLE_ITEMS, ITEM_HANDLERS = 0x27819A, 0x20C162


def wake_chance(counter):
    """줄인 뒤의 잠 카운터 0~3 에서 깰 확률(4분의)."""
    return WAKE[counter] / 4


def battle_items(rom):
    """[(물건, 처리기 주소, 효과 행동 또는 None)]. 효과 행동은 처리기 안(다음 처리기 앞까지)의 첫 LDA #n / STA $10F7."""
    entries, k = [], 0
    while rom.u8(BATTLE_ITEMS + k) != 0xFF:
        entries.append((rom.u8(BATTLE_ITEMS + k), 0x200000 | rom.u16(ITEM_HANDLERS + 2 * k)))
        k += 1
    starts = sorted({h for _, h in entries})
    out = []
    for item, handler in entries:
        end = min([h for h in starts if h > handler] + [handler + 0x20])
        action = None
        for a in range(handler, end - 4):
            if rom.u8(a) == 0xA9 and rom.u8(a + 2) == 0x8D and rom.u16(a + 3) == 0x10F7:
                action = rom.u8(a + 1)
                break
        out.append((item, handler, action))
    return out


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--items':
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from dq5chest import item_name
        from dq5map import Rom
        from dq5text import string, string_codes, text
        rom = Rom(open(sys.argv[2], 'rb').read())
        for item, handler, action in battle_items(rom):
            act = f'{action:02X} {text(string_codes(rom, string(rom, 3, action)))}' if action is not None else '-'
            print(f'{item:02X} {item_name(rom, item)}  {handler >> 16:02X}:{handler & 0xFFFF:04X}  {act}')
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument('attack', type=int)
    ap.add_argument('defense', type=int)
    ap.add_argument('--party', action='store_true', help='맞는 쪽이 일행')
    args = ap.parse_args()
    lo, hi = normal_range(args.attack, args.defense, args.party)
    print(f'보통 공격 {lo}~{hi}')
    if not args.party:
        lo, hi = critical_range(args.attack)
        print(f'회심 {lo}~{hi}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
