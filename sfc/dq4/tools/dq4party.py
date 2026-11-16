"""2장 일행(아리나·크리프트·브라이)의 주문과 장비를 FC 로. 형식은 sfc/dq4/docs/dq4-growth-format.md 「2장 일행」.

크리프트·브라이는 DQ5 사람 칸 09(ヘンリー)·05(サンチョ)를 빌린다(dq4ch2event.RECRUITS). 레벨업 성장은 dq4growth 가
FC 곡선 표로 바꾸고, 이 모듈은 나머지 둘을 맡는다.

- 주문: FC 의 전투·필드 주문 목록(10:$9150·$9192)과 배우는 레벨(12:$A118·$A124)을 DQ5 사람 9·5 의 습득 표와 목록으로
  옮긴다(dq5learnwrite 의 dq5learn/1). DQ5 에 없는 주문(ヒャダイン·ピオリム)과 DQ5 필드에서 쓰지 못하는 주문
  (ベホマラー)은 그 목록에서 뺀다. 목록 칸은 배우는 레벨 차례다(아래 plan). 지혜에 따라 늦어지는 주문(레벨 바이트
  bit7)은 곡선 그대로의 지혜에서 FC 가 반드시 배우는 레벨(레벨 + 1)로 둔다. 1레벨 주문은 합류 기록의 배운 주문 비트(+23~+25)로 준다: DQ5 는 사람이 일행에
  들 때 습득 표를 보지 않는다(21:8042, dq5-data-format 「일행에 들 때」).
- 장비: DQ5 장비 판정(21:A53B)은 사람이면 23:B591[물건] & 21:A632[사람] 이라 사람 0 인 아리나가 DQ5 주인공 비트를
  쓴다(きぬのローブ 를 못 입음). 그 두 표를 읽는 21:A557 을 훅으로 바꿔, 2장의 사람 0·사람 9·사람 5 는 FC 장비 비트
  (10:$8C9C, 인물 번호 = 비트)를 DQ5 물건 번호로 옮긴 표에서 읽는다. 1장 라이안은 그대로 DQ5 주인공 비트다.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
for p in (TOOLS, ROOT / 'sfc' / 'dq5' / 'tools', ROOT / 'fc' / 'dq4' / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dq4environmentrom import _Asm  # noqa: E402
import dq4growth  # noqa: E402

DQ5, DQ4 = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'
# DQ5 사람 번호 → FC 인물 번호. dq4ch2event.RECRUITS 의 'person' 과 같아야 한다(test_dq4party 가 봄)
RECRUITS = {0x09: dq4growth.FC_KIRYL, 0x05: dq4growth.FC_BREY}
SPELL_NAMES, ITEM_NAMES = 3, 5   # dq5text 이름 표 번호
SPELL_LAST = 0x38                # 주인공 쪽 주문 01~38(dq5-data-format 「주문과 행동」)
# DQ5 주인공 쪽 주문 가운데 FC 에 없는 두 칸(マホキテ·シャナク)을 FC 주문에 빌려준다. 몬스터 쪽(39~65)은 몬스터가 같은
# 번호를 쓰면 전투가 멈추므로 빌리지 않는다. 이 해킹에서 두 칸을 쓰던 것은 ダークシールド(1D)뿐이고 그 물건은 나오지 않는다
# 번호: (FC 이름, FC 주문 번호(dq4data.spell_mp 의 i), 표 값을 베낄 DQ5 주문)
BORROWED_SPELLS = {0x38: ('ヒャダイン', 0x0B, 0x0C), 0x1D: ('ピオリム', 0x23, 0x22)}
HYADAIN, PIORIMU = 0x38, 0x1D
HYADAIN_AMOUNT = 0x1C            # 27:8071 의 쓰지 않는 양 칸(바탕 0, 폭 0)
FC_HYADAIN = (60, 21)            # FC 일행 ヒャダイン 바탕·폭(13:$B74D 칸 0B), 값 = 바탕 + 0~폭-1
ICE = 0x53                       # 내성 종류(ヒャド 계열)
BEHOMARA = 0x2A
# dq5learnwrite 는 필드 목록에 2A 를 받지 않는다(원래 롬에서 필드 처리기가 제자리에서 돔). 그 자리에 크리프트가 배우지
# 않는 필드 주문을 두고 패치를 얹은 뒤 apply_recruits 가 2A 로 바꾼다
FIELD_PLACEHOLDER = 0x36         # トラマナ
# 습득 표(23:B819~BD52)는 브라이의 두 주문을 더하면 4바이트 넘친다. DQ4 의 몬스터 동료는 호이민뿐이고 그 기록은 레벨이
# 오르지 않으므로(dq4ch1event.companion_record) DQ5 몬스터 동료 표 하나(41, 8항목)를 비워 자리를 만든다. 호이민(ホイミスライム)은
# 표 5 다
SPARE_MONSTER = 41
RECORD_SPELLS = 0x23             # 일행 기록의 배운 주문 비트 3바이트. 필드 칸 n = bit n, 전투 칸 n = bit 8 + n
# FC 와 DQ5 가 같은 물건을 다르게 적은 것
ITEM_ALIASES = {'いかづちのつえ': 'いかずちのつえ'}
# FC 롬에서 잰 배운 주문 비트(인물 레코드 +1B~+1D, 작은 끝). fc/dq4/tools/dq4levelup.py 로 2장 시작 1레벨 기록을 그
# 레벨까지 올렸다(지혜는 곡선 그대로). 비트 번호는 FC 목록 자리(전투 n = bit n, 필드 n = bit 16 + n)
FC_SPELLS_MEASURED = {
    dq4growth.FC_KIRYL: {1: 0x010002, 5: 0x010003, 10: 0x030007, 15: 0x030057, 20: 0x07015F},
    dq4growth.FC_BREY: {1: 0x000001, 5: 0x000003, 10: 0x03002B, 15: 0x03022F, 20: 0x070A2F},
}

EQUIP_AT = 0x57CE00              # 성장 표(dq4growth.SPACE_END) 뒤 빈 자리
PARTY_END = 0x57D000             # 장비 표·주문 코드가 넘지 않을 끝
EQUIP_HOOK = 0x21A557            # LDA $23B591,X / LDX $4B / AND $21A632,X(M·X 8, X = 물건, $4B = 사람 & 3F)
EQUIP_ORIG = bytes.fromhex('bf 91 b5 23 a6 4b 3f 32 a6 21')
DQ5_EQUIP, DQ5_PERSON_BIT = 0x23B591, 0x21A632
ITEM_COUNT = 0xD8
# DQ5 사람 → ((FC 표를 쓰는 조건 flag, FC 인물), …). 앞 줄부터 맞는 것을 쓴다. 사람 0 은 2장·3장일 때만(1장 라이안은 DQ5
# 주인공 비트 그대로)
EQUIP_PEOPLE = {0x00: ((dq4growth.CHAPTER2, dq4growth.FC_ALENA), (dq4growth.CHAPTER3, dq4growth.FC_TORNEKO)),
                0x09: ((None, dq4growth.FC_KIRYL),), 0x05: ((None, dq4growth.FC_BREY),)}


def _kata(text):
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in text)


def _fc(dq4=DQ4):
    from kr_patch.fc import ines
    return ines.prg(Path(dq4).read_bytes())


def _dq5(dq5=DQ5):
    from dq5map import Rom
    return Rom(Path(dq5).read_bytes())


def _names(rom, table, count):
    import dq5text
    return [dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, table, i))) for i in range(count)]


def dq5_spells(rom):
    """{가타카나 이름: DQ5 주문 번호}(주인공 쪽 01~38, BORROWED_SPELLS 칸은 빌려준 FC 이름)."""
    names = _names(rom, SPELL_NAMES, SPELL_LAST + 1)
    for n, (fc_name, _, _) in BORROWED_SPELLS.items():
        names[n] = fc_name
    return {_kata(n): i for i, n in enumerate(names) if i}


def field_spells():
    """필드 목록에 둘 수 있는 DQ5 주문: dq5learnwrite 가 받는 것과 이 모듈이 처리기를 단 ベホマラー."""
    import dq5learnwrite
    return set(dq5learnwrite.FIELD_SPELLS) | {BEHOMARA}


def korean_names():
    """{주문 번호: 한글 이름}: 빌려준 칸(롬의 이름 표에는 아직 DQ5 이름이 있어 번호로 덮는다)."""
    import dq4windowtext
    adopted = dq4windowtext.adopted(dq4windowtext.KINDS[SPELL_NAMES][0])
    return {n: adopted[dq4windowtext.kana_key(name)] for n, (name, _, _) in BORROWED_SPELLS.items()}


def learn_level(b):
    """FC 배우는 레벨 바이트 → DQ5 습득 레벨. bit7 이면 지혜 보정 B 만큼 늦어지고, 곡선 그대로의 지혜면 B = 1 이라
    레벨에서는 반쯤의 확률, 레벨 + 1 에서 반드시 배운다(12:$9ED2·$9F59)."""
    return (b & 0x7F) + (1 if b & 0x80 else 0)


def plan(prg, rom, who):
    """FC 인물 who 의 주문을 DQ5 목록으로. {'battle': [DQ5 번호], 'field': [...], 'learn': [dq5learn 항목, 레벨 2~],
    'start': 1레벨 배운 주문 비트(24비트), 'dropped': [(목록, FC 이름, 까닭)], 'fc': {DQ5 목록 자리: FC 주문 번호}}."""
    import dq4data
    import dq4text
    names = [_kata(dq4text.text(n)) for n in dq4data.name_list(prg, 'spell')]
    ids = dq5_spells(rom)
    fc_battle, fc_field = dq4data.spell_menus(prg, who)
    out = {'battle': [], 'field': [], 'dropped': [], 'fc_battle': [], 'fc_field': []}
    for kind, menu in (('battle', fc_battle), ('field', fc_field)):
        for sp in menu:
            if sp == 0xFF:
                continue
            name = names[sp + 1]
            if name not in ids:
                out['dropped'].append((kind, name, 'DQ5 에 없는 주문'))
            elif kind == 'field' and ids[name] not in field_spells():
                out['dropped'].append((kind, name, 'DQ5 필드에서 쓰지 못함'))
            else:
                out[kind].append(ids[name])
                out[f'fc_{kind}'].append(sp)
    # 칸을 배우는 레벨 차례로 둔다(같은 레벨은 FC 목록 차례). DQ5 주문 창은 칸 0 부터 빈틈없이 배운다고 보는 듯하다:
    # FC 차례 그대로(크리프트 전투 칸 0 スカラ, 칸 1 ホイミ)에서 칸 1 만 배운 크리프트가 ホイミ 를 고르자 행동이 FF 가 되어
    # 「멍하니 있다」, ホイミ 를 칸 0 으로 옮기자 행동 27 이 되어 MP 가 3 줄었다
    levels = {sp: learn_level(b) for sp, b in dq4data.learnset(prg, who).items()}
    for kind in ('battle', 'field'):
        order = sorted(range(len(out[kind])), key=lambda k: levels.get(out[f'fc_{kind}'][k], 99))
        out[kind] = [out[kind][k] for k in order]
        out[f'fc_{kind}'] = [out[f'fc_{kind}'][k] for k in order]
    by_level = {}
    for sp, b in dq4data.learnset(prg, who).items():
        f = [k for k, s in enumerate(out['fc_field']) if s == sp]
        bt = [k for k, s in enumerate(out['fc_battle']) if s == sp]
        if f or bt:
            e = by_level.setdefault(learn_level(b), {'field_slots': [], 'battle_slots': []})
            e['field_slots'] += f
            e['battle_slots'] += bt
    first = by_level.pop(1, {'field_slots': [], 'battle_slots': []})
    out['start'] = sum(1 << k for k in first['field_slots']) | sum(1 << 8 + k for k in first['battle_slots'])
    out['learn'] = [{'level': lv, 'field_slots': sorted(e['field_slots']), 'battle_slots': sorted(e['battle_slots'])}
                    for lv, e in sorted(by_level.items())]
    return out


def learned_by(p, level):
    """plan p 로 레벨 level 까지 배운 FC 주문 번호."""
    got = set()
    slots = [({'field_slots': [k for k in range(8) if p['start'] >> k & 1],
               'battle_slots': [k for k in range(12) if p['start'] >> 8 + k & 1]})]
    slots += [e for e in p['learn'] if e['level'] <= level]
    for e in slots:
        got |= {p['fc_field'][k] for k in e['field_slots']} | {p['fc_battle'][k] for k in e['battle_slots']}
    return got


def fc_learned(prg, who, bits):
    """FC 배운 주문 비트(+1B~+1D) → FC 주문 번호."""
    import dq4data
    battle, field = dq4data.spell_menus(prg, who)
    got = {battle[k] for k in range(len(battle)) if bits >> k & 1}
    return got | {field[k] for k in range(len(field)) if bits >> 16 + k & 1 and field[k] != 0xFF}


def learn_doc(dq5=DQ5, dq4=DQ4):
    """dq5learnwrite 입력: 1장 라이안(사람 0, 습득 없음)과 크리프트·브라이."""
    import dq4ch1event
    prg, rom = _fc(dq4), _dq5(dq5)
    doc = dq4ch1event.learn_doc()
    for person, who in RECRUITS.items():
        p = plan(prg, rom, who)
        if FIELD_PLACEHOLDER in p['field']:
            raise ValueError(f'사람 {person:02X} 필드 목록에 자리 표시 주문 {FIELD_PLACEHOLDER:02X} 가 이미 있음')
        field = [FIELD_PLACEHOLDER if n == BEHOMARA else n for n in p['field']]
        doc['characters'].append({'kind': 'person', 'index': person, 'learn': p['learn'],
                                  'field': field, 'battle': p['battle']})
    doc['characters'].append({'kind': 'monster', 'index': SPARE_MONSTER, 'learn': []})
    return doc


FIELD_LISTS = 0x23BD53           # [사람*2] → 뱅크 23 의 [개수][주문 …](21:9C92)


def apply_field_lists(data, dq5=DQ5, dq4=DQ4):
    """dq5learnwrite 패치를 얹은 롬에서 learn_doc 이 둔 자리 표시 주문을 ベホマラー 로. 목록마다 자리 표시가 plan 의
    ベホマラー 수만큼이어야 한다."""
    d = bytearray(data)
    prg, rom = _fc(dq4), _dq5(dq5)
    for person, who in RECRUITS.items():
        want = plan(prg, rom, who)['field']
        o = dq4growth.lorom(FIELD_LISTS + person * 2)
        at = dq4growth.lorom(0x230000 | d[o] | d[o + 1] << 8)
        n = d[at]
        got = list(d[at + 1:at + 1 + n])
        if [FIELD_PLACEHOLDER if s == BEHOMARA else s for s in want] != got:
            raise SystemExit(f'사람 {person:02X} 필드 목록이 예상과 다름: {bytes(got).hex(" ")}')
        d[at + 1:at + 1 + n] = bytes(want)
    return bytes(d)


def start_spells(dq5=DQ5, dq4=DQ4):
    """{DQ5 사람 번호: 1레벨 배운 주문 비트 3바이트}."""
    prg, rom = _fc(dq4), _dq5(dq5)
    return {person: plan(prg, rom, who)['start'].to_bytes(3, 'little') for person, who in RECRUITS.items()}


def apply_recruits(data, dq5=DQ5, dq4=DQ4):
    """dq4ch2event.apply 뒤: 합류 기록(dq4ch2event.native 의 recruits)의 배운 주문 비트를 1레벨 주문으로. 그 자리는
    dq4ch2event.level_one 이 0 으로 둔 것이어야 한다(다른 값이면 누가 이미 고친 것이라 멈춤)."""
    import dq4ch2event as ev
    d = bytearray(data)
    _, at = ev.native()
    spells = start_spells(dq5, dq4)
    for k, r in enumerate(ev.RECRUITS):
        o = dq4growth.lorom(at['recruits'] + 42 * k)
        if d[o] != r['person'] or any(d[o + RECORD_SPELLS:o + RECORD_SPELLS + 3]):
            raise SystemExit(f"{r['name']} 합류 기록이 예상과 다름: {bytes(d[o:o + 42]).hex(' ')}")
        d[o + RECORD_SPELLS:o + RECORD_SPELLS + 3] = spells[r['person']]
    return apply_field_lists(bytes(d), dq5, dq4)


def equip_table(prg, rom):
    """DQ5 물건 번호마다 FC 장비 비트(bit = FC 인물 번호). 같은 이름의 FC 물건이 없으면 0. dq4itemport.BORROWED 로
    FC 물건 이름을 빌린 DQ5 칸은 그 FC 물건."""
    import dq4data
    import dq4itemport
    fc = {_kata(ITEM_ALIASES.get(n, n)): i for i, n, *_ in dq4data.items(prg) if i < 0x53}
    names = [_kata(n) for n in _names(rom, ITEM_NAMES, ITEM_COUNT)]
    for item, fc_name in dq4itemport.BORROWED.items():
        names[item] = _kata(fc_name)
    return [sum(1 << w for w in range(8) if dq4data.can_equip(prg, fc[n], w)) if n in fc else 0 for n in names]


def equip_code(table, at=EQUIP_AT):
    """21:A557 에서 JSL 로 부르는 훅(M·X 8). Z 가 그대로 남아 부른 곳의 BEQ 가 장비 못 함을 가른다."""
    a = _Asm(at)
    a.label('equip').b(0xA5, 0x4B).rel(0xD0, 'other')
    for k, (flag, who) in enumerate(EQUIP_PEOPLE[0]):
        a.b(0xAF, *flag[0].to_bytes(3, 'little'), 0x29, flag[1]).rel(0xF0, f'hero{k}')
        a.b(0xA9, 1 << who).rel(0x80, 'fc')
        a.label(f'hero{k}')
    a.rel(0x80, 'dq5')
    a.label('other')
    for person, rows in EQUIP_PEOPLE.items():
        if person == 0:
            continue
        if len(rows) != 1 or rows[0][0] is not None:
            raise ValueError('사람 0 밖에는 flag 조건을 두지 않는다')
        who = rows[0][1]
        a.b(0xA5, 0x4B, 0xC9, person).rel(0xD0, f'not{person}')
        a.b(0xA9, 1 << who).rel(0x80, 'fc')
        a.label(f'not{person}')
    a.label('dq5').b(0xBF, *DQ5_EQUIP.to_bytes(3, 'little'), 0xA6, 0x4B, 0x3F, *DQ5_PERSON_BIT.to_bytes(3, 'little'), 0x6B)
    # 비트를 스택에 두고 표 값과 AND, 결과를 PLA 로 꺼내 Z 를 세운다
    a.label('fc').b(0x48).long(0xBF, 'table').b(0x23, 0x01, 0x83, 0x01, 0x68, 0x6B)
    a.label('table').b(*table)
    return a.assemble()


def equip_writes(dq5=DQ5, dq4=DQ4, at=EQUIP_AT):
    """dq5patch/1 쓰기: 장비 훅·표와 21:A557 의 호출."""
    rom = _dq5(dq5)
    data, labels = equip_code(equip_table(_fc(dq4), rom), at)
    if at + len(data) > PARTY_END:
        raise ValueError(f'장비 표가 {PARTY_END:06X} 를 넘음')
    call = bytes((0x22, *labels['equip'].to_bytes(3, 'little'))) + b'\xea' * (len(EQUIP_ORIG) - 4)
    hexs = lambda b: bytes(b).hex(' ').upper()  # noqa: E731
    cpu = lambda x: f'{x >> 16:02X}:{x & 0xFFFF:04X}'  # noqa: E731
    return [{'at': cpu(at), 'hex': hexs(data), 'orig': hexs(bytes(len(data))), 'note': '2장 일행·톨네코 장비: FC 장비 비트 표와 훅'},
            {'at': cpu(EQUIP_HOOK), 'hex': hexs(call), 'orig': hexs(EQUIP_ORIG), 'note': '장비 판정(21:A557)을 2장 일행 훅으로'}]



SPELL_AT = 0x57CF40              # 장비 표 뒤 빈 자리, PARTY_END 앞
BANK20_AT = 0x20FFD9             # 뱅크 20 끝 빈 자리(39바이트). 처리·적용 루틴은 뱅크 20 의 JSR 표라 여기서 넘긴다
FIELD_AT = 0x11FFA0              # 뱅크 11 끝 빈 자리(96바이트). 필드 주문 표(11:8024)도 뱅크 안 JSR
# 행동 번호로 색인하는 표(dq5spellgrow.WIDE·MENU_MP·FX 와 같은 자리)
FLAGS, EXECUTOR, EXECUTOR_ALT, HANDLER = 0x268765, 0x268865, 0x268565, 0x20B7F9
MENU_MP, FX_PARTY, FX_MONSTER = 0x219BB4, 0x268BE0, 0x268C75
AMOUNTS, AI_ACTIONS = 0x278071, 0x21BC86   # 양 [바탕][폭], 작전 AI 행동 레코드 5바이트
# 스카라·스쿠르토의 적용(20:F6BF: $10EC 를 수비력 필드 15 에 더하고 메시지 08E). 첫 JSR $A0A1 을 뱅크 20 스텁으로
# 돌려 행동이 ピオリム 이면 같은 꼴로 전투 すばやさ(필드 1A, FF 에서 멈춤)에 더하고 메시지 0F4 를 띄운다
APPLY_HOOK, APPLY_ORIG, APPLY_NEXT = 0x20F6BF, bytes.fromhex('20 a1 a0'), 0x20F6C2
TAIL_WAIT, TAIL_RTS = 0x20F6E1, 0x20F6E4    # 20:F6BF 끝의 JSR $9DD6 / RTS 와 RTS
B307 = 0x20B307                  # 주문 피해(LDX #내성 / LDA #양 번호 뒤)
FIELD_TABLE = 0x118024           # 필드 주문 처리기 [(주문 - 27)*2], 2A 는 제자리에서 도는 8022
FIELD_HANG = 0x8022
# 필드 처리기가 쓰는 뱅크 11 루틴(キアリク 11:86C7·ホイミ 11:84FA 와 같은 차례)
MP_CHECK, MP_TAKE, CAST, NO_MP, HEALED = 0x87DF, 0x87F4, 0x87C1, 0x856E, 0x8557
PARTY_LAST = 0x04D97B            # JSL: 일행 수 - 1
RAND = 0x00953A                  # JSL: 0 ~ A-1
FC_BEHOMARA = (75, 21)           # FC ベホマラー 양(13:$B7E3, ベホイミ 와 같은 칸)


def _cpu(x):
    return f'{x >> 16:02X}:{x & 0xFFFF:04X}'


def _hex(b):
    return bytes(b).hex(' ').upper()


def spell_code(at=SPELL_AT, bank20=None):
    """ピオリム 의 처리 루틴(양 = min(기록 すばやさ, 255 - 전투 すばやさ))·적용 루틴과 ヒャダイン 처리 루틴. 뱅크 20 에서
    JML 로 들어와 뱅크 20 으로 JML 해 돌아간다. 메시지 BRK(A4·16)는 부른 뱅크를 데이터 뱅크로 두고 돌아 뱅크 57 에서
    부르면 전투가 멈췄다(필드 BRK 89 는 됨). 그래서 메시지는 뱅크 20 의 bank20['message'] 에서 띄운다."""
    bank20 = bank20 or {'message': TAIL_WAIT}
    a = _Asm(at)
    long = lambda op, x: a.b(op, *x.to_bytes(3, 'little'))  # noqa: E731
    a.label('handler').b(0xE2, 0x30, 0xAD, 0xF6, 0x10).rel(0x30, 'h_done')
    a.b(0x29, 0x0F, 0x85, 0x42)
    a.b(0x00, 0x89, 0x80, 0x19, 0xA5, 0x46, 0x85, 0x71)       # 전투 すばやさ → $71
    a.b(0x00, 0x89, 0x80, 0x17)                               # 기록 すばやさ → $46
    a.b(0xA9, 0xFF, 0x38, 0xE5, 0x71, 0xC5, 0x46).rel(0x90, 'h_store').b(0xA5, 0x46)
    a.label('h_store').b(0x8D, 0xEC, 0x10, 0x9C, 0xED, 0x10)
    a.label('h_done')
    long(0x5C, TAIL_RTS)
    # 20:A0A1·A08D 와 같게 $43 과 $F6 에 양, 그다음 20:F6C5 와 같은 꼴
    a.label('apply').b(0xC2, 0x30, 0x64, 0x44, 0xAD, 0xEC, 0x10, 0x85, 0x43, 0x64, 0xF7, 0x85, 0xF6, 0xE2, 0x30)
    a.b(0xAD, 0xF6, 0x10, 0x85, 0xF5).rel(0x30, 'a_out').b(0x85, 0x42)
    a.b(0x00, 0x89, 0x80, 0x1A)
    long(0x5C, bank20['message'])
    a.label('a_out')
    long(0x5C, TAIL_RTS)
    a.label('hyadain').b(0xE2, 0x30, 0xA2, ICE, 0xA9, HYADAIN_AMOUNT)   # ヒャダルコ(20:B13F)와 같은 꼴
    long(0x5C, B307)
    return a.assemble()


def bank20_code(far, at=BANK20_AT):
    """적용 훅 스텁, ピオリム·ヒャダイン 처리 루틴 스텁, ピオリム 메시지(0F4, 20:F6DA 의 BRK 둘과 같은 꼴)."""
    a = _Asm(at)
    long = lambda op, x: a.b(op, *x.to_bytes(3, 'little'))  # noqa: E731
    a.label('apply').b(0xAD, 0xF7, 0x10, 0xC9, PIORIMU).rel(0xD0, 'apply_dq5')
    long(0x5C, far['apply'])
    a.label('apply_dq5').b(0x20, *APPLY_ORIG[1:], 0x4C, *(APPLY_NEXT & 0xFFFF).to_bytes(2, 'little'))
    a.label('piorimu')
    long(0x5C, far['handler'])
    a.label('hyadain')
    long(0x5C, far['hyadain'])
    a.label('message').b(0x00, 0xA4, 0xF4, 0x00, 0x16, 0x46, 0x04, 0x4C, *(TAIL_WAIT & 0xFFFF).to_bytes(2, 'little'))
    data, labels = a.assemble()
    if at + len(data) > 0x210000:
        raise ValueError('뱅크 20 스텁이 뱅크 끝을 넘음')
    return data, labels


def field_code(mp, at=FIELD_AT):
    """필드 ベホマラー: キアリク(11:86C7)처럼 일행을 돌며 죽지 않은 사람(필드 3E bit7 꺼짐)의 HP 를 FC 양만큼 올리고
    ホイミ 의 메시지(11:8557)를 띄운다."""
    base, width = FC_BEHOMARA
    a = _Asm(at)
    w = lambda op, x: a.b(op, x & 0xFF, x >> 8 & 0xFF)  # noqa: E731
    a.label('behomara').b(0xA9, mp)
    w(0x20, MP_CHECK)
    a.rel(0x90, 'ok')
    w(0x4C, NO_MP)
    a.label('ok').b(0x22, *PARTY_LAST.to_bytes(3, 'little'), 0x8D, 0x52, 0x0B)
    w(0x20, CAST)
    a.b(0xA9, mp)
    w(0x20, MP_TAKE)
    a.b(0x9C, 0x50, 0x0B)
    a.label('loop').b(0xAD, 0x50, 0x0B, 0x85, 0xF5, 0x85, 0x42, 0x64, 0x43, 0x00, 0x89, 0x80, 0x3E, 0x24, 0x46)
    a.rel(0x30, 'next')
    a.b(0xA9, width, 0x22, *RAND.to_bytes(3, 'little'), 0x18, 0x69, base, 0x85, 0x43, 0x64, 0x44)
    a.b(0xAD, 0x50, 0x0B, 0x85, 0x42, 0x00, 0x89, 0x80, 0x01)   # HP 필드 01 에 더함
    a.b(0x00, 0x97, 0x13)
    w(0x20, HEALED)
    a.label('next').b(0xEE, 0x50, 0x0B, 0xCE, 0x52, 0x0B).rel(0x10, 'loop')
    a.b(0x00, 0x0E, 0x00, 0x95, 0xFF, 0x60)
    data, labels = a.assemble()
    if at + len(data) > 0x120000:
        raise ValueError('필드 ベホマラー 가 뱅크 11 끝을 넘음')
    return data, labels


def spell_writes(dq5=DQ5, dq4=DQ4):
    """dq5patch/1 쓰기: 빌린 주문 칸 둘(ヒャダイン·ピオリム)과 필드 ベホマラー."""
    import dq4data
    rom, prg = _dq5(dq5), _fc(dq4)
    raw = rom.d
    far_labels = spell_code()[1]
    stub, stub_labels = bank20_code(far_labels)
    far, far_labels2 = spell_code(bank20=stub_labels)
    if far_labels2 != far_labels:
        raise ValueError('주문 코드 자리가 두 번 셈에서 다름')
    if SPELL_AT < EQUIP_AT + len(equip_code(equip_table(prg, rom))[0]) or SPELL_AT + len(far) > PARTY_END:
        raise ValueError('주문 코드 자리가 장비 표나 성장 표와 겹침')
    out = []

    def put(addr, new, note):
        o = dq4growth.lorom(addr)
        old = raw[o:o + len(new)] if o < len(raw) else bytes(len(new))   # 늘린 뱅크(57)는 빈 자리
        out.append({'at': _cpu(addr), 'hex': _hex(new), 'orig': _hex(old), 'note': note})

    def word(table, n):
        o = dq4growth.lorom(table + 2 * n)
        return raw[o:o + 2]

    def byte(table, n):
        return bytes((raw[dq4growth.lorom(table + n)],))

    put(SPELL_AT, far, 'ピオリム 처리·적용 루틴')
    put(BANK20_AT, stub, 'ピオリム·ヒャダイン 뱅크 20 스텁')
    put(APPLY_HOOK, bytes((0x4C, *(stub_labels['apply'] & 0xFFFF).to_bytes(2, 'little'))), '20:F6BF 적용을 스텁으로')
    handler = {HYADAIN: stub_labels['hyadain'], PIORIMU: stub_labels['piorimu']}
    for n, (name, fc, src) in sorted(BORROWED_SPELLS.items()):
        mp, rng, enemy = dq4data.spell_mp(prg, fc)
        put(FLAGS + n, bytes((mp | rng << 5 | enemy << 7,)), f'{name} MP·범위(FC)')
        put(EXECUTOR + 2 * n, word(EXECUTOR, src), f'{name} 실행 루틴({src:02X} 와 같음)')
        put(EXECUTOR_ALT + 2 * n, word(EXECUTOR_ALT, src), f'{name} 둘째 실행 루틴')
        put(HANDLER + 2 * n, (handler[n] & 0xFFFF).to_bytes(2, 'little'), f'{name} 처리 루틴')
        put(MENU_MP + n, bytes((mp,)), f'{name} 주문 창 MP')
        put(FX_PARTY + n, byte(FX_PARTY, src), f'{name} 연출(우리 편)')
        put(FX_MONSTER + n, byte(FX_MONSTER, src), f'{name} 연출(몬스터)')
    base, width = FC_HYADAIN
    put(AMOUNTS + 2 * HYADAIN_AMOUNT, bytes((base, width)), 'ヒャダイン 양(FC 일행 값)')
    # 작전 AI: ヒャダイン 은 マヒャド 레코드에 값(양 가운데)·MP·범위 전체를, ピオリム 은 고르지 않는 레코드(11 00 30)
    mp = dq4data.spell_mp(prg, BORROWED_SPELLS[HYADAIN][1])[0]
    o = dq4growth.lorom(AI_ACTIONS + 5 * BORROWED_SPELLS[HYADAIN][2])
    rec = bytearray(raw[o:o + 5])
    rec[1], rec[3], rec[4] = base + (width - 1) // 2, mp, 0x40 | ICE - 0x50
    put(AI_ACTIONS + 5 * HYADAIN, bytes(rec), 'ヒャダイン 작전 AI')
    put(AI_ACTIONS + 5 * PIORIMU, bytes((0x11, 0x00, 0x30, dq4data.spell_mp(prg, BORROWED_SPELLS[PIORIMU][1])[0], 0xFF)),
        'ピオリム 작전 AI(고르지 않음)')
    field_mp = dq4data.spell_mp(prg, 0x2C)[0]
    fdata, flabels = field_code(field_mp)
    put(FIELD_AT, fdata, '필드 ベホマラー')
    put(FIELD_TABLE + 2 * (BEHOMARA - 0x27), (flabels['behomara'] & 0xFFFF).to_bytes(2, 'little'), '필드 주문 표 2A')
    return out


def writes(dq5=DQ5, dq4=DQ4):
    """dq5patch/1 쓰기 전부: 장비 훅·표, 빌린 주문 칸, 필드 ベホマラー."""
    return equip_writes(dq5, dq4) + spell_writes(dq5, dq4)

def main():
    import argparse
    import json
    from kr_patch.fc import ines  # noqa: F401
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', choices=('spells', 'equip', 'learn'))
    args = ap.parse_args()
    prg, rom = _fc(), _dq5()
    if args.what == 'learn':
        print(json.dumps(learn_doc(), ensure_ascii=False, indent=1))
    elif args.what == 'spells':
        names = {v: k for k, v in dq5_spells(rom).items()}
        for person, who in RECRUITS.items():
            p = plan(prg, rom, who)
            print(f'사람 {person:02X}: 1레벨 비트 {p["start"].to_bytes(3, "little").hex(" ")}')
            print('  전투', ' '.join(names[i] for i in p['battle']))
            print('  필드', ' '.join(names[i] for i in p['field']))
            for e in p['learn']:
                got = [names[p['field'][k]] for k in e['field_slots']] + [names[p['battle'][k]] for k in e['battle_slots']]
                print(f"  레벨 {e['level']:2d}", ' '.join(dict.fromkeys(got)))
            for kind, name, why in p['dropped']:
                print(f'  뺌({kind}) {name}: {why}')
    else:
        names = _names(rom, ITEM_NAMES, ITEM_COUNT)
        for i, bits in enumerate(equip_table(prg, rom)):
            if bits:
                print(f'{i:02X} {names[i]} {bits:08b}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
