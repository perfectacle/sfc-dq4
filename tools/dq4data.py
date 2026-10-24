"""DQ4(FC) 이름 목록·아이템·몬스터 표. 형식은 docs/dq4-data-format.md.

사용:
  python tools/dq4data.py rom/dq4.nes names [목록]     spell class sex item place tactic monster
  python tools/dq4data.py rom/dq4.nes items            아이템 ID, 이름, 종류, 강도, 가격, 장비할 수 있는 인물, 플래그
  python tools/dq4data.py rom/dq4.nes monsters         몬스터 ID, 이름, 능력치, 떨어뜨리는 아이템, 레코드 22바이트
  python tools/dq4data.py rom/dq4.nes spells           주문 ID, 이름, 소비 MP, 대상, 배우는 인물과 레벨
  python tools/dq4data.py rom/dq4.nes levels [인물]    레벨별 경험치와 능력치 기준값(인물 0-7, 생략하면 모두)

근거: 0B:$B006(이름 목록 포인터), 10:$8BED(가격), 10:$8C3B(강도 $9E17), 10:$8B1E·$8B3B(종류·장비),
18:$8046(몬스터 레코드, 10:$A67C 필드 표), 13:$B953(주문 MP), 12:$9D36(레벨업), 12:$9FC6(성장 곡선).
"""
import sys

from kr_patch.fc import ines

import dq4text

NAMES_BANK, NAMES_PTR = 0x0B, 0xB006
LISTS = ('spell', 'class', 'sex', 'item', 'monster', 'place', 'tactic')   # 0B:$B006 의 순서(뒤에 monster 한 번 더)
ITEM_BANK = 0x10
ITEM_POWER, ITEM_PRICE, ITEM_SCALE = 0x9E17, 0x8E19, 0x8D1B
ITEM_FLAGS, ITEM_USE = 0x8D1B, 0x8D9A
EQUIP_MASK, EQUIP_KIND = 0x8C9C, 0x8B37          # 인물 비트 표(아이템 0-52), 종류 경계 4바이트
DRESSES = (0x30, 0x31, 0x3B, 0x4D)               # 여자만: ミネア·マーニャ·アリーナ, 勇者는 $615C bit0 일 때
KINDS = ('무기', '갑옷', '방패', '투구', '기타')
MON_BANK, MON_TABLE, MON_SIZE = 0x18, 0x8046, 22
DROP_RATE = (0x12, 0x9286)                       # 바이트 20 bit2-0 → 256 분의 이 값(0 은 항상, 7 은 다시 1/16)
SPELL_BANK, SPELL_MP = 0x13, 0xB967
TARGETS = ('고정', '하나', '그룹', '모두')
GROW_BANK = 0x12
GROW_PTR, GROW_RATE = 0xA108, 0xA266             # 인물마다 경험치 5바이트, 능력치 6바이트 레코드
LEARN_MASK, LEARN_LEVEL = 0xA118, 0xA124         # 인물 0-4: 주문 64비트 마스크, 배우는 레벨 바이트들
PARTY = ('勇者', 'クリフト', 'ミネア', 'マーニャ', 'ブライ', 'トルネコ', 'ライアン', 'アリーナ')
STATS = ('exp', 'str', 'agi', 'vit', 'int', 'luck', 'hp', 'mp')   # 12:$9F89 의 $0B 번호


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def name_list(prg, which):
    """길이 바이트 + 글자 바이트 이름들. 다음 목록 시작에서 끝난다. 0번은 빈 이름이라 ID = 순번 − 1."""
    i = LISTS.index(which)
    ptrs = [rd(prg, NAMES_BANK, NAMES_PTR + 2 * j) | rd(prg, NAMES_BANK, NAMES_PTR + 2 * j + 1) << 8
            for j in range(len(LISTS))]
    a = ptrs[i]
    end = min([p for p in ptrs if p > a] or [0xBFFF])
    out = []
    while a < end:
        n = rd(prg, NAMES_BANK, a)
        if n > 0x10:
            break
        out.append([rd(prg, NAMES_BANK, a + 1 + k) for k in range(n)])
        a += 1 + n
    while out and all(b == 0 for b in out[-1]):
        out.pop()
    return out


def items(prg):
    """(ID, 이름, 강도, 가격). 가격 = ($8E19 & 7F) × 10^($8D1B & 3)(코드 읽기)."""
    out = []
    for i, nm in enumerate(name_list(prg, 'item')[1:]):
        price = (rd(prg, ITEM_BANK, ITEM_PRICE + i) & 0x7F) * 10 ** (rd(prg, ITEM_BANK, ITEM_SCALE + i) & 3)
        out.append((i, dq4text.text(nm), rd(prg, ITEM_BANK, ITEM_POWER + i), price,
                    rd(prg, ITEM_BANK, ITEM_PRICE + i) >> 7))
    return out


def item_kind(prg, i):
    """10:$8B1E: 경계 24·3D·46·50 보다 작은 첫 자리. 0 무기, 1 갑옷, 2 방패, 3 투구, 4 기타."""
    for k in range(4):
        if i < rd(prg, ITEM_BANK, EQUIP_KIND + k):
            return k
    return 4


def can_equip(prg, i, who, heroine=False):
    """10:$8B3B. who = 인물 0-7, heroine = 勇者 가 여자($615C bit0)."""
    if who >= 8 or i >= 0x53:
        return False
    if i in DRESSES and who not in (2, 3, 7) and not (who == 0 and heroine):
        return False
    return bool(rd(prg, ITEM_BANK, EQUIP_MASK + i) >> who & 1)


def monster_fields(r):
    """22바이트 레코드를 10:$A67C 의 필드 표대로 푼다. 9비트 이상 값은 바이트 15-18 의 bit1-0 이 위 비트."""
    return {
        'exp': r[0] | r[1] << 8, 'agi': r[2], 'mp': r[3],
        'hp': r[4] | (r[15] & 3) << 8, 'atk': r[5] | (r[16] & 3) << 8,
        'def': r[6] | (r[17] & 3) << 8, 'gold': r[7] | (r[18] & 3) << 8,
        'drop': r[8] & 0x7F, 'drop_rate': r[20] & 7,
        'actions': [b & 0x7F for b in r[9:15]],
        'resist': [r[15 + j // 4] >> (2 * (j % 4)) & 3 for j in range(20) if j % 4],
    }


def drop_chance(prg, rate):
    """떨어뜨릴 확률(분수 문자열). 12:$922D."""
    if rate == 0:
        return '1'
    n = rd(prg, DROP_RATE[0], DROP_RATE[1] + rate)
    return f'{n}/4096' if rate == 7 else f'{n}/256'


def spell_mp(prg, i):
    """13:$B967 바이트: bit4-0 소비 MP, bit6-5 대상 범위, bit7 적에게 거는 주문."""
    b = rd(prg, SPELL_BANK, SPELL_MP + i)
    return b & 0x1F, b >> 5 & 3, b >> 7


def learnset(prg, who):
    """{주문 ID: 배우는 레벨 바이트}. bit7 이 서면 지혜에 따라 늦어지거나 반쯤 확률로 배운다(12:$9ED2)."""
    if who >= 5:
        return {}
    w = lambda a: rd(prg, GROW_BANK, a) | rd(prg, GROW_BANK, a + 1) << 8
    mask, lv = w(LEARN_MASK + 2 * who), w(LEARN_LEVEL + 2 * who)
    out, k = {}, 0
    for sp in range(64):
        if rd(prg, GROW_BANK, mask + sp // 8) >> (sp % 8) & 1:
            out[sp] = rd(prg, GROW_BANK, lv + k)
            k += 1
    return out


def curve(prg, who, stat, level):
    """성장 곡선 값과 그 레벨의 증가분 (값, 증가분). stat 은 STATS 번호.

    경험치(0)는 그 레벨이 되는 데 필요한 누계, 능력치는 그 레벨의 기준값이다. HP(6)는 체력 곡선의 두 배다.
    레코드 바이트 0-4 의 bit7 다섯 개가 초깃값, 바이트 0 bit4-0 과 1-4 bit6-0 이 구간 경계 레벨,
    바이트 0 bit6-5 가 비율 표의 줄을 고른다. 경계를 하나 넘을 때마다 비율 표의 다음 칸을 쓴다.
    능력치는 레벨마다 (바이트 5 × 비율 + 8) >> 4 를 더하고, 경험치는 앞 증가분 × 비율 >> 4 를 더한다.
    """
    if stat == 6:
        v, d = curve(prg, who, 3, level)
        return 2 * v, 2 * d
    g = lambda a: rd(prg, GROW_BANK, a)
    size = 5 if stat == 0 else 6
    base = (g(GROW_PTR + 2 * stat) | g(GROW_PTR + 2 * stat + 1) << 8) + who * size
    b = [g(base + i) for i in range(size)]
    init = sum((b[i] >> 7) << i for i in range(5))
    row = (b[0] & 0x60) >> 3
    ri = row + (row >> 1) + (0x18 if stat else 0)
    edges = [b[0] & 0x1F] + [x & 0x7F for x in b[1:5]]
    total = d = init
    if stat == 0:
        if level <= 2:
            return (0, 0) if level <= 1 else (init, init)
        first = 3
    else:
        if level <= 1:
            return init, init
        first = 2
    ti = 0
    for lv in range(first, level + 1):
        while ti < 5 and edges[ti] < lv:
            ri += 1
            ti += 1
        rate = g(GROW_RATE + ri)
        d = (b[5] * rate + 8) >> 4 if stat else (d * rate) >> 4
        total += d
    return total, d


def monsters(prg):
    """(ID, 이름, 경험치(바이트 0-1), 최대 HP(바이트 4), 레코드)."""
    out = []
    for i, nm in enumerate(name_list(prg, 'monster')[1:]):
        r = bytes(rd(prg, MON_BANK, MON_TABLE + MON_SIZE * i + k) for k in range(MON_SIZE))
        out.append((i, dq4text.text(nm), r[0] | r[1] << 8, r[4], r))
    return out


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    cmd = sys.argv[2]
    if cmd == 'names':
        for which in (sys.argv[3:] or LISTS):
            ns = name_list(prg, which)
            print(f'# {which} {len(ns) - 1}')
            for i, nm in enumerate(ns[1:]):
                print(f'{i:02X} {dq4text.text(nm)}')
    elif cmd == 'items':
        for i, nm, pw, price, flag in items(prg):
            who = ''.join(PARTY[k][0] if can_equip(prg, i, k, True) else '.' for k in range(8))
            fl = rd(prg, ITEM_BANK, ITEM_FLAGS + i) >> 2
            use = rd(prg, ITEM_BANK, ITEM_USE + i)
            print(f'{i:02X} {nm:<14} {KINDS[item_kind(prg, i)]} 강도 {pw:3d} 가격 {price:6d} {who} '
                  f'8D1B={fl:06b} 8D9A={use >> 6:02b}/{use & 0x3F:02X}' + (' *' if flag else ''))
    elif cmd == 'monsters':
        item_names = [nm for _, nm, *_ in items(prg)]
        for i, nm, exp, hp, r in monsters(prg):
            m = monster_fields(r)
            drop = '-' if m['drop'] == 0x7F else f'{item_names[m["drop"]]} {drop_chance(prg, m["drop_rate"])}'
            print(f'{i:02X} {nm:<12} 경험치 {m["exp"]:5d} 골드 {m["gold"]:4d} HP {m["hp"]:4d} MP {m["mp"]:3d} '
                  f'공 {m["atk"]:3d} 수 {m["def"]:3d} 속 {m["agi"]:3d} 드롭 {drop}  {r.hex(" ")}')
    elif cmd == 'spells':
        names = [dq4text.text(n) for n in name_list(prg, 'spell')[1:]]
        sets = [learnset(prg, k) for k in range(5)]
        for i, nm in enumerate(names):
            mp, tgt, foe = spell_mp(prg, i)
            who = ' '.join(f'{PARTY[k]} {v & 0x7F}{"*" if v & 0x80 else ""}' for k in range(5)
                           for sp, v in sets[k].items() if sp == i)
            print(f'{i:02X} {nm:<8} MP {mp:2d} {"적" if foe else "편"} {TARGETS[tgt]}  {who}')
    elif cmd == 'levels':
        for who in ([int(sys.argv[3])] if len(sys.argv) > 3 else range(8)):
            print(f'# {who} {PARTY[who]}  Lv ' + ' '.join(STATS))
            for lv in range(1, 100):
                vals = [curve(prg, who, k, lv)[0] for k in range(8) if k != 7 or who < 5]
                print(f'{lv:2d} ' + ' '.join(str(v) for v in vals))


if __name__ == '__main__':
    main()
