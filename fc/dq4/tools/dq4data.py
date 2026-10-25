"""DQ4(FC) 이름 목록·아이템·몬스터 표. 형식은 fc/dq4/docs/dq4-data-format.md.

사용:
  python fc/dq4/tools/dq4data.py rom/dq4.nes names [목록]     spell class sex item place tactic monster
  python fc/dq4/tools/dq4data.py rom/dq4.nes items            아이템 ID, 이름, 종류, 강도, 가격, 장비할 수 있는 인물, 플래그, 전투 사용 행동
  python fc/dq4/tools/dq4data.py rom/dq4.nes monsters         몬스터 ID, 이름, 능력치, 드롭, 레코드 22바이트, 행동 ID·행동 수·AI·내성
  python fc/dq4/tools/dq4data.py rom/dq4.nes spells           주문 ID, 이름, 소비 MP, 대상, 배우는 인물과 레벨
  python fc/dq4/tools/dq4data.py rom/dq4.nes levels [인물]    레벨별 경험치와 능력치 기준값(인물 0-7, 생략하면 모두)
  python fc/dq4/tools/dq4data.py rom/dq4.nes actions          전투 행동 ID 00-FF: 처리 루틴, 위력, 양(회복·흡수·상승), 성공률
  python fc/dq4/tools/dq4data.py rom/dq4.nes ai               몬스터 행동 가중치·재생·시작 상태 표, 동료 AI 의 인물별 주문 칸·작전 × 인물 표

근거: 0B:$B006(이름 목록 포인터), 10:$8BED(가격), 10:$8C3B(강도 $9E17), 10:$8B1E·$8B3B(종류·장비),
18:$8046(몬스터 레코드, 10:$A67C 필드 표), 13:$B953(주문 MP), 12:$9D36(레벨업), 12:$9FC6(성장 곡선),
11:$A3FA(행동 처리 루틴), 13:$B573·$B5E4·$B66B(위력·양·성공률), 10:$A2D7(몬스터 행동 번호), 11:$9069(아이템 사용),
18:$9A21(행동 가중치), 11:$AAF6(HP 재생), 12:$8540(시작 상태), 11:$A62E(회심), 13:$8038(동료 AI).
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
SELECT = ('고르게', '앞 칸 많이', '첫 칸 대부분', '차례')   # 몬스터 바이트 9·10 bit7(필드 1F)
WEIGHTS = (0x18, 0x9AA9)                         # 고르는 법 0-2 마다 여섯 칸의 가중치(합 255), 3 은 차례
REGEN = (0x11, 0xAB31)                           # 바이트 13·14 bit7 → 턴마다 HP + rand(폭) + 기본 (폭, 기본) 쌍
START_STATUS = (0x12, 0x85BD)                    # 바이트 21 bit5-3 → 시작 상태 확률 (값+1)/256, 7 은 없음
STATUS_NAMES = ('잠', '마비', '혼란', '없음')       # 바이트 21 bit7-6(메시지 001F + 값)
AI_BANK, AI_SPELLS = 0x13, 0xA68A                # 동료 AI 가 평가하는 주문 칸: クリフト·ミネア·マーニャ·ブライ 12개씩
AI_TACTIC = {0xBA74: '피해×/16', 0xBAD5: '피해×/256', 0xBAA5: '회복 목표 /16'}  # 작전 × 인물 표(13:$938B)
AI_SLOT_FN, AI_ITEM_GROUPS = 0xA626, 0xA747      # 칸마다의 평가 루틴 표(인물별 포인터), 아이템 후보 묶음 4개
AI_TACTIC7 = {0xBB53: '13:$A2DF フバーハ 문턱', 0xBB5A: '13:$A22D ドラゴラム', 0xBB61: '13:$A234 ドラゴラム',
              0xBB68: '13:$A10F バイキルト', 0xBB6F: '13:$A0A1 スカラ', 0xBB76: '13:$A07F スクルト',
              0xBB7D: '13:$A170 バイキルト', 0xBB84: '13:$AADA', 0xBB8B: '13:$AAA9', 0xBB92: '13:$AB8C'}
# 작전 번호($6E80, 0~6)로만 찾는 7바이트 표들과 읽는 곳(코드 읽기). 주문 이름은 그 루틴을 부르는 칸의 주문
AI_ORDER = {1: ((0, 1, 2, 3, 6, 7, 8, 9, 10, 11), (4, 5)), 2: ((0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11), (5,)),
            3: ((0, 1, 2, 3, 4, 5, 6, 7, 8), (9, 10)), 4: ((0, 1, 2, 3, 4, 6), (7, 8, 9, 10))}
# 13:$AFF0·$AF97·$AF10·$AF48 이 평가하는 칸 순서와 13:$9135 를 통과할 때만 보는 칸. マーニャ 는 끝에 칸 11 도 봄
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


def weights(prg, sel):
    """고르는 법 0-2 의 여섯 칸 가중치(18:$9A21). 같은 행동이 여러 칸이면 18:$9A72 가 가중치를 더해 한 칸으로 합친다."""
    return [rd(prg, WEIGHTS[0], WEIGHTS[1] + 6 * sel + k) for k in range(6)]


def regen(prg, v):
    """바이트 13·14 bit7 값 0-3 → 턴 시작마다 회복하는 HP 범위(11:$AAF6). 0 은 없음."""
    w, base = rd(prg, REGEN[0], REGEN[1] + 2 * v), rd(prg, REGEN[0], REGEN[1] + 2 * v + 1)
    return (base, base + w - 1) if w else None


def start_status(prg, r):
    """바이트 21 → (상태 이름, 확률/256) 또는 None. 12:$855D 가 rand(256) ≤ 표 값이면 건다."""
    chance, kind = r[21] >> 3 & 7, r[21] >> 6
    if chance == 7 or kind == 3:
        return None
    return STATUS_NAMES[kind], rd(prg, START_STATUS[0], START_STATUS[1] + chance) + 1


def ai_spells(prg, who):
    """인물 1-4 의 동료 AI 주문 칸 12개(13:$A68A + 12 × 번호, 0번 자리는 쓰지 않음)."""
    return [rd(prg, AI_BANK, AI_SPELLS + 12 * who + k) for k in range(12)]


def ai_slot_fn(prg, who):
    """인물 1-4 의 칸 12개마다 13:$A54D 가 뛰는 평가 루틴 주소(13:$A626 + 2 × 번호 의 포인터가 가리키는 표)."""
    p = rd(prg, AI_BANK, AI_SLOT_FN + 2 * who) | rd(prg, AI_BANK, AI_SLOT_FN + 2 * who + 1) << 8
    return [rd(prg, AI_BANK, p + 2 * k) | rd(prg, AI_BANK, p + 2 * k + 1) << 8 for k in range(12)]


def ai_item_groups(prg):
    """13:$A6D4 가 묶음(0~3)마다 보는 (아이템 ID, 행동 ID, 평가 루틴) 목록. 13:$A747 의 포인터, 4바이트씩, FF 로 끝."""
    out = []
    for g in range(4):
        p, rows = rd(prg, AI_BANK, AI_ITEM_GROUPS + 2 * g) | rd(prg, AI_BANK, AI_ITEM_GROUPS + 2 * g + 1) << 8, []
        while rd(prg, AI_BANK, p) != 0xFF:
            rows.append((rd(prg, AI_BANK, p), rd(prg, AI_BANK, p + 1),
                         rd(prg, AI_BANK, p + 2) | rd(prg, AI_BANK, p + 3) << 8))
            p += 4
        out.append(rows)
    return out


def k_used(who, k):
    """그 인물의 루틴이 칸 k 를 평가하는지(マーニャ 는 칸 11 도 봄)."""
    first, gated = AI_ORDER[who]
    return k in first or k in gated or (who == 3 and k == 11)


def tactic_value(prg, table, tactic, who):
    """작전 × 인물 표의 값. 13:$938B 의 SEC·SBC 뒤 ADC 가 자리올림을 더해 칸은 7 × 작전 + 인물 + 1."""
    return rd(prg, AI_BANK, table + 7 * tactic + who + 1)


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
            rg, st = regen(prg, m['f21']), start_status(prg, r)
            extra = (f' 재생 {rg[0]}~{rg[1]}' if rg else '') + (f' 회심 {4 * m["f24"]}/256' if m['f24'] else '') \
                + (f' 시작 {st[0]} {st[1]}/256' if st else '') + (f' f28={m["f28"]}' if m['f28'] != 7 else '')
            print(f'   행동 {acts} | {SELECT[m["select"]]} {COUNT[m["count"]]}회 AI {m["ai"]}{extra} | 내성 {res or "-"}')
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
    elif cmd == 'ai':
        spells = [dq4text.text(n) for n in name_list(prg, 'spell')[1:]]
        for sel in range(3):
            print(f'가중치 {sel} {SELECT[sel]}: ' + ' '.join(str(w) for w in weights(prg, sel)))
        print('재생: ' + ' '.join(f'{v}={regen(prg, v)}' for v in range(4)))
        print('시작 상태 확률: ' + ' '.join(f'{c}={rd(prg, *START_STATUS[:1], START_STATUS[1] + c) + 1}/256'
                                       for c in range(7)))
        for who in range(1, 5):
            sp = ai_spells(prg, who)
            first, gated = AI_ORDER[who]
            print(f'{PARTY[who]}: ' + ' '.join(spells[sp[k]] for k in first) + ' / 9135 통과 때 '
                  + ' '.join(spells[sp[k]] for k in gated))
            print('  평가 루틴: ' + ' '.join(f'{spells[s]}={a:04X}' for s, a in zip(sp, ai_slot_fn(prg, who))
                                            if k_used(who, sp.index(s))))
        item_names = [dq4text.text(n) for n in name_list(prg, 'item')[1:]]
        for g, rows in enumerate(ai_item_groups(prg)):
            print(f'아이템 후보 {g}: ' + ' '.join(f'{item_names[i]}>{a:02X}@{f:04X}' for i, a, f in rows))
        for table, what in AI_TACTIC7.items():
            print(f'13:${table:04X} {what}  작전 0-6: '
                  + ' '.join(f'{rd(prg, AI_BANK, table + t):02X}' for t in range(7)))
        for table, what in AI_TACTIC.items():
            print(f'13:${table:04X} {what}  작전 0-6 × 인물 1-7')
            for t in range(7):
                print(f'  {t} ' + ' '.join(f'{tactic_value(prg, table, t, w):02X}' for w in range(1, 8)))
    elif cmd == 'levels':
        for who in ([int(sys.argv[3])] if len(sys.argv) > 3 else range(8)):
            print(f'# {who} {PARTY[who]}  Lv ' + ' '.join(STATS))
            for lv in range(1, 100):
                vals = [curve(prg, who, k, lv)[0] for k in range(8) if k != 7 or who < 5]
                print(f'{lv:2d} ' + ' '.join(str(v) for v in vals))


if __name__ == '__main__':
    main()
