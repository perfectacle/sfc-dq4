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
RECORD_SPELLS = 0x23             # 일행 기록의 배운 주문 비트 3바이트. 필드 칸 n = bit n, 전투 칸 n = bit 8 + n
# FC 와 DQ5 가 같은 물건을 다르게 적은 것
ITEM_ALIASES = {'いかづちのつえ': 'いかずちのつえ'}
# FC 롬에서 잰 배운 주문 비트(인물 레코드 +1B~+1D, 작은 끝). fc/dq4/tools/dq4levelup.py 로 2장 시작 1레벨 기록을 그
# 레벨까지 올렸다(지혜는 곡선 그대로). 비트 번호는 FC 목록 자리(전투 n = bit n, 필드 n = bit 16 + n)
FC_SPELLS_MEASURED = {
    dq4growth.FC_KIRYL: {1: 0x010002, 5: 0x010003, 10: 0x030007, 15: 0x030057, 20: 0x07015F},
    dq4growth.FC_BREY: {1: 0x000001, 5: 0x000003, 10: 0x03002B, 15: 0x03022F, 20: 0x070A2F},
}

EQUIP_AT = 0x57CE00              # 57:8703~ 빈 자리, 성장 표(dq4growth.GROWTH_AT) 앞
EQUIP_HOOK = 0x21A557            # LDA $23B591,X / LDX $4B / AND $21A632,X(M·X 8, X = 물건, $4B = 사람 & 3F)
EQUIP_ORIG = bytes.fromhex('bf 91 b5 23 a6 4b 3f 32 a6 21')
DQ5_EQUIP, DQ5_PERSON_BIT = 0x23B591, 0x21A632
ITEM_COUNT = 0xD8
# DQ5 사람 → (FC 표를 쓰는 조건 flag, FC 인물). 사람 0 은 2장일 때만(1장 라이안은 DQ5 주인공 비트 그대로)
EQUIP_PEOPLE = {0x00: (dq4growth.CHAPTER2, dq4growth.FC_ALENA), 0x09: (None, dq4growth.FC_KIRYL),
                0x05: (None, dq4growth.FC_BREY)}


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
    """{가타카나 이름: DQ5 주문 번호}(주인공 쪽 01~38)."""
    return {_kata(n): i for i, n in enumerate(_names(rom, SPELL_NAMES, SPELL_LAST + 1)) if i}


def learn_level(b):
    """FC 배우는 레벨 바이트 → DQ5 습득 레벨. bit7 이면 지혜 보정 B 만큼 늦어지고, 곡선 그대로의 지혜면 B = 1 이라
    레벨에서는 반쯤의 확률, 레벨 + 1 에서 반드시 배운다(12:$9ED2·$9F59)."""
    return (b & 0x7F) + (1 if b & 0x80 else 0)


def plan(prg, rom, who):
    """FC 인물 who 의 주문을 DQ5 목록으로. {'battle': [DQ5 번호], 'field': [...], 'learn': [dq5learn 항목, 레벨 2~],
    'start': 1레벨 배운 주문 비트(24비트), 'dropped': [(목록, FC 이름, 까닭)], 'fc': {DQ5 목록 자리: FC 주문 번호}}."""
    import dq4data
    import dq4text
    import dq5learnwrite
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
            elif kind == 'field' and ids[name] not in dq5learnwrite.FIELD_SPELLS:
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
        doc['characters'].append({'kind': 'person', 'index': person, 'learn': p['learn'],
                                  'field': p['field'], 'battle': p['battle']})
    return doc


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
    return bytes(d)


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
    flag, who = EQUIP_PEOPLE[0]
    a.b(0xAF, *flag[0].to_bytes(3, 'little'), 0x29, flag[1]).rel(0xF0, 'dq5')
    a.b(0xA9, 1 << who).rel(0x80, 'fc')
    a.label('other')
    for person, (flag, who) in EQUIP_PEOPLE.items():
        if person == 0:
            continue
        if flag is not None:
            raise ValueError('사람 0 밖에는 flag 조건을 두지 않는다')
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
    if at + len(data) > dq4growth.GROWTH_AT:
        raise ValueError(f'장비 표가 {dq4growth.GROWTH_AT:06X} 를 넘음')
    call = bytes((0x22, *labels['equip'].to_bytes(3, 'little'))) + b'\xea' * (len(EQUIP_ORIG) - 4)
    hexs = lambda b: bytes(b).hex(' ').upper()  # noqa: E731
    cpu = lambda x: f'{x >> 16:02X}:{x & 0xFFFF:04X}'  # noqa: E731
    return [{'at': cpu(at), 'hex': hexs(data), 'orig': hexs(bytes(len(data))), 'note': '2장 일행 장비: FC 장비 비트 표와 훅'},
            {'at': cpu(EQUIP_HOOK), 'hex': hexs(call), 'orig': hexs(EQUIP_ORIG), 'note': '장비 판정(21:A557)을 2장 일행 훅으로'}]


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
