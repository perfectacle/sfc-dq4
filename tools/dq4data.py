"""DQ4(FC) 이름 목록·아이템·몬스터 표. 형식은 docs/dq4-data-format.md.

사용:
  python tools/dq4data.py rom/dq4.nes names [목록]     spell class sex item place tactic monster
  python tools/dq4data.py rom/dq4.nes items            아이템 ID, 이름, 종류, 강도, 가격, 장비할 수 있는 인물, 플래그, 전투 사용 행동
  python tools/dq4data.py rom/dq4.nes monsters         몬스터 ID, 이름, 능력치, 드롭, 레코드 22바이트, 행동 ID·행동 수·AI·내성
  python tools/dq4data.py rom/dq4.nes spells           주문 ID, 이름, 소비 MP, 대상, 배우는 인물과 레벨
  python tools/dq4data.py rom/dq4.nes levels [인물]    레벨별 경험치와 능력치 기준값(인물 0-7, 생략하면 모두)
  python tools/dq4data.py rom/dq4.nes actions          전투 행동 ID 00-FF: 처리 루틴, 위력, 양(회복·흡수·상승), 성공률

근거: 0B:$B006(이름 목록 포인터), 10:$8BED(가격), 10:$8C3B(강도 $9E17), 10:$8B1E·$8B3B(종류·장비),
18:$8046(몬스터 레코드, 10:$A67C 필드 표), 13:$B953(주문 MP), 12:$9D36(레벨업), 12:$9FC6(성장 곡선),
11:$A3FA(행동 처리 루틴), 13:$B573·$B5E4·$B66B(위력·양·성공률), 10:$A2D7(몬스터 행동 번호), 11:$9069(아이템 사용).
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
MENU_BATTLE, MENU_FIELD = 0x9150, 0x9192         # 뱅크 10: 인물별 주문 목록. 자리 = 레코드 +1B~ 의 비트 번호
ACT_BANK, ACT_HANDLER = 0x11, 0xA3FA              # 행동 ID 256개 → 처리 루틴 주소
ITEM_ACT = (0x907B, 0x90A3, 40)                  # 뱅크 11: 전투에서 쓰는 아이템 40개와 그 행동 ID. 없으면 7F
MON_ACT = (0x10, 0xA2E8, 0x2A)                   # 몬스터 행동 번호 < 2A → 이 표, 2A → F7, 그 위 → 번호 + 11
FX_BANK = 0x13
POWER = 0xB74D                                   # (기본, 폭) 쌍. 편 칸 0-1B, 몬스터 칸 1C-37(+38 바이트)
POWER_MAP = (0xB5CE, 0xB5D9, 11)                 # 행동 ID → 위력 칸(나머지: 4D 미만은 그대로, 4D-6C 는 − 3A)
HEAL = (0xB62F, 0xB64D, 30, 0xB7E3)              # 행동 ID 30개 → 회복 칸 → (기본, 폭). 폭 FF = 전부
SUCCESS, RESIST_SLOT, RESIST_RATE = 0xB80B, 0xB736, 0xB803
RESIST_NAMES = ('イオ', 'ギラ', 'メラ', 'デイン', 'バギ', 'ヒャド', 'マヌーサ', 'ラリホー', 'ザキ', 'ニフラム',
                'マホトラ', 'マホトーン', 'メダパニ', 'ルカニ', 'メガンテ')   # 13:$B80B bit4-0 의 내성 칸 0-E
ITEM_FLAG_NAMES = ('쓰면 없어짐', '저주', '못 버림', '못 팖', '하나만 떨어뜨림', 'bit7')   # $8D1B bit2-7
SELECT = ('확률', '확률', '확률', '차례')            # 몬스터 바이트 9·10 bit7(필드 1F)
COUNT = ('1', '1~2', '2', '3')                    # 바이트 11·12 bit7(필드 20): 한 턴 행동 수
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
        # bit7 둘을 묶은 2비트 값: 앞 바이트 bit7 이 bit0(10:$ACB4·$B121 의 ASL·ROL·ROL)
        'select': r[9] >> 7 | r[10] >> 7 << 1, 'count': r[11] >> 7 | r[12] >> 7 << 1,
        'f21': r[13] >> 7 | r[14] >> 7 << 1,
        'ai': r[20] >> 6, 'f24': r[20] >> 3 & 7, 'f26': r[21] >> 6, 'f27': r[21] >> 3 & 7, 'f28': r[21] & 7,
    }


def monster_action(prg, n):
    """몬스터 레코드의 행동 번호(바이트 9-14 bit6-0) → 행동 ID(10:$A2D7)."""
    if n < MON_ACT[2]:
        return rd(prg, MON_ACT[0], MON_ACT[1] + n)
    return 0xF7 if n == MON_ACT[2] else n + 0x11


def resists(prg, r):
    """내성 칸 0-E 의 2비트 값. 칸 c 는 13:$B736[c] 번 2비트 필드(바이트 15 + i/4, bit 2(i%4))."""
    out = []
    for c in range(len(RESIST_NAMES)):
        i = rd(prg, FX_BANK, RESIST_SLOT + c)
        out.append(r[15 + i // 4] >> (2 * (i % 4)) & 3)
    return out


def action_handler(prg, a):
    return rd(prg, ACT_BANK, ACT_HANDLER + 2 * a) | rd(prg, ACT_BANK, ACT_HANDLER + 2 * a + 1) << 8


def power(prg, a, monster):
    """공격 주문·숨결 같은 처리 루틴 11:$9AD2 행동의 (기본, 폭). 값 = 기본 + ⌊폭 × 난수(0-255) / 256⌋."""
    lo, hi, n = POWER_MAP
    ids = [rd(prg, FX_BANK, lo + k) for k in range(n)]
    if a in ids:
        k = rd(prg, FX_BANK, hi + ids.index(a))
    elif a < 0x4D:
        k = a
    elif a < 0x6D:
        k = a - 0x3A
    else:
        return None
    x = 2 * k + (0x38 if monster else 0)
    base, width = rd(prg, FX_BANK, POWER + x), rd(prg, FX_BANK, POWER + x + 1)
    if x == 0x24:                                # 편의 ミナデイン 은 기본 330(13:$B585)
        base = 0x14A
    return base, width


def heal(prg, a):
    """13:$B5E4 의 양 (기본, 폭): HP 회복, マホトラ 의 MP, 씨앗의 상승치 등. 폭 None 은 최대치까지."""
    ids, idx, n, tab = HEAL
    for k in range(n):
        if rd(prg, FX_BANK, ids + k) == a:
            j = rd(prg, FX_BANK, idx + k)
            w = rd(prg, FX_BANK, tab + 2 * j + 1)
            return rd(prg, FX_BANK, tab + 2 * j), (None if w == 0xFF else w)
    return None


def success(prg, a):
    """13:$B66B. (편이 받을 때 확률/256, 몬스터 쪽: 내성 칸 번호 또는 고정 확률).

    바이트 bit7-5 = 편이 받을 때 확률(E0 이면 늘 맞음), bit4-0 = 몬스터 쪽 칸. 칸 0-E 는 내성 2비트
    값으로 13:$B803 의 확률(ラリホーマ·ルカニ 는 다른 줄), 10 이상은 13:$B736[칸] 고정 확률.
    """
    b = rd(prg, FX_BANK, SUCCESS + a)
    party = 256 if b & 0xE0 == 0xE0 else b & 0xE0
    c = b & 0x1F
    return party, (('내성', c) if c < 0x10 else ('고정', rd(prg, FX_BANK, RESIST_SLOT + c)))


def resist_rates(prg, a):
    """내성 값 0-3 의 성공 확률/256. ラリホーマ(18)·ルカニ(1F)는 둘째 줄."""
    row = 4 if a in (0x18, 0x1F) else 0
    return [rd(prg, FX_BANK, RESIST_RATE + row + k) for k in range(4)]


def item_action(prg, i):
    """전투에서 아이템을 썼을 때의 행동 ID(11:$9069). 표에 없으면 7F(「つかった」→ 아무 일 없음)."""
    lo, hi, n = ITEM_ACT
    for k in range(n):
        if rd(prg, ACT_BANK, lo + k) == i:
            return rd(prg, ACT_BANK, hi + k)
    return 0x7F


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


def spell_menus(prg, who):
    """(전투 목록, 필드 목록) 주문 ID. 레코드 비트 번호는 전투 자리, 필드는 자리 + 16(10:$9123)."""
    if who >= 5:
        return [], []
    a, n = (0, 18) if who == 0 else (6 + 12 * who, 12)
    battle = [rd(prg, ITEM_BANK, MENU_BATTLE + a + i) for i in range(n)]
    field = [rd(prg, ITEM_BANK, MENU_FIELD + 8 * who + i) for i in range(8)]
    return battle, field


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
            names = ','.join(ITEM_FLAG_NAMES[k] for k in range(6) if fl >> k & 1)
            print(f'{i:02X} {nm:<14} {KINDS[item_kind(prg, i)]} 강도 {pw:3d} 가격 {price:6d} {who} '
                  f'8D1B={fl:06b} 8D9A={use >> 6:02b}/{use & 0x3F:02X}' + (' *' if flag else '  ')
                  + f' 행동 {item_action(prg, i):02X} {names}')
    elif cmd == 'monsters':
        item_names = [nm for _, nm, *_ in items(prg)]
        spells = [dq4text.text(n) for n in name_list(prg, 'spell')[1:]]
        for i, nm, exp, hp, r in monsters(prg):
            m = monster_fields(r)
            drop = '-' if m['drop'] == 0x7F else f'{item_names[m["drop"]]} {drop_chance(prg, m["drop_rate"])}'
            acts = ' '.join(f'{a:02X}' + (spells[a] if a < len(spells) else '')
                            for a in (monster_action(prg, n) for n in m['actions']))
            res = ' '.join(f'{RESIST_NAMES[c]}{v}' for c, v in enumerate(resists(prg, r)) if v)
            print(f'{i:02X} {nm:<12} 경험치 {m["exp"]:5d} 골드 {m["gold"]:4d} HP {m["hp"]:4d} MP {m["mp"]:3d} '
                  f'공 {m["atk"]:3d} 수 {m["def"]:3d} 속 {m["agi"]:3d} 드롭 {drop}  {r.hex(" ")}')
            print(f'   행동 {acts} | {SELECT[m["select"]]} {COUNT[m["count"]]}회 AI {m["ai"]} '
                  f'f21={m["f21"]} f24={m["f24"]} f26={m["f26"]} f27={m["f27"]} f28={m["f28"]} | 내성 {res or "-"}')
    elif cmd == 'spells':
        names = [dq4text.text(n) for n in name_list(prg, 'spell')[1:]]
        sets = [learnset(prg, k) for k in range(5)]
        menus = [spell_menus(prg, k) for k in range(5)]
        for i, nm in enumerate(names):
            mp, tgt, foe = spell_mp(prg, i)
            who = []
            for k in range(5):
                if i not in sets[k]:
                    continue
                v = sets[k][i]
                bits = [f'전{menus[k][0].index(i)}'] if i in menus[k][0] else []
                bits += [f'필{16 + menus[k][1].index(i)}'] if i in menus[k][1] else []
                who.append(f'{PARTY[k]} {v & 0x7F}{"*" if v & 0x80 else ""}({",".join(bits)})')
            who = ' '.join(who)
            print(f'{i:02X} {nm:<8} MP {mp:2d} {"적" if foe else "편"} {TARGETS[tgt]}  {who}')
    elif cmd == 'actions':
        spells = [dq4text.text(n) for n in name_list(prg, 'spell')[1:]]
        for a in range(256):
            nm = spells[a] if a < len(spells) else ''
            out = f'{a:02X} {nm:<8} 11:${action_handler(prg, a):04X}'
            if action_handler(prg, a) == 0x9AD2:
                p, q = power(prg, a, False), power(prg, a, True)
                out += f' 위력 편 {p[0]}+{p[1]} 몬스터 {q[0]}+{q[1]}'
            h = heal(prg, a)
            if h:
                out += f' 양 {h[0]}+{h[1]}' if h[1] is not None else ' 양 전부'
            party, (kind, v) = success(prg, a)
            if kind == '내성':
                out += f' 성공 편 {party}/256 몬스터 {RESIST_NAMES[v]} 내성 {resist_rates(prg, a)}'
            elif party != 256 or v != 255:
                out += f' 성공 편 {party}/256 몬스터 {v}/256'
            print(out)
    elif cmd == 'levels':
        for who in ([int(sys.argv[3])] if len(sys.argv) > 3 else range(8)):
            print(f'# {who} {PARTY[who]}  Lv ' + ' '.join(STATS))
            for lv in range(1, 100):
                vals = [curve(prg, who, k, lv)[0] for k in range(8) if k != 7 or who < 5]
                print(f'{lv:2d} ' + ' '.join(str(v) for v in vals))


if __name__ == '__main__':
    main()
