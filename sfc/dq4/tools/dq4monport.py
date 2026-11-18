"""2장 전투 몬스터를 NDS 그림으로: FC 몬스터마다 DQ5 몬스터 번호·그림 번호를 따로 주고, dq4monart 로 15색으로 다듬은
NDS 그림을 dq5monwrite 문서(dq5monster/1)로 쓴다. 형식 문서 sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」.

필드 조우의 대역(dq4fieldencounter.MONSTERS)은 여러 FC 몬스터가 DQ5 몬스터 하나를 같이 써서, 그림을 바꾸려면 번호를
나눠야 한다. 새 번호(PORT)에는 지금 대역의 레코드 25바이트를 바탕으로(내성·행동 거르기 등 FC 에 짝이 없는 칸) FC 능력치·
행동·드롭을 덮어 쓴다(record_writes). 사건 몬스터(텐페 보스·대회 상대)는 사건 모듈이 그 번호에 FC 능력치와 이름을 쓴다.

  python sfc/dq4/tools/dq4monport.py doc rom/dq5.sfc -o work/monport     # 그림 PNG 와 dq5monster/1 문서
"""
import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / 'dq5' / 'tools'
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from PIL import Image  # noqa: E402

import dq4monart  # noqa: E402

# FC 몬스터 → DQ5 몬스터 번호. 그림은 그 번호가 원래 쓰는 DQ5 그림 자리에 덮는다. 몬스터의 그림 번호를 바꾸면
# dq5monwrite 가 새 그림이 원래 그림의 전투 배치 한도(조각·타일·가로·세로·줄 최대 타일) 안이어야 받으므로, 원래 그림이
# NDS 그림을 담을 만큼 크고, 그 그림의 머리를 다른 그림 번호가 같이 쓰지 않으며(같이 쓰는 번호는 dq5monlimits 가
# 세는 조합에 나오지 않아 받지 않음), 그 그림(머리)을 계속 쓰이는 몬스터(다른 FC 몬스터의 대역, 1장 보스)가 쓰지 않으며, DQ5 가나
# 이름이 롬 안에서 하나뿐인(전투 글 이름 표 dq4battlemsg 가 가나 이름 바이트로 한글을 찾음) 번호 01~BF 를 골랐다.
# ダミー 몬스터·2장 예비(dq4ch2slots.SPARE)·다른 몬스터가 싸우는 도중에 불러내는
# 몬스터(dq5monlimits.SUMMONED: 큰 그림이 싸우는 도중에 풀리면 NMI 몫이 달라 조심으로)는 뺐다.
# 필드 조우에 나오는 FC 몬스터 → DQ5 번호(지금 대역 레코드를 옮김)
PORT = {
    0x00: 0x02, 0x01: 0x13, 0x02: 0x30, 0x03: 0x7C, 0x05: 0x8B, 0x07: 0x37, 0x08: 0x08, 0x0B: 0x1A, 0x0C: 0x35,
    0x0D: 0x15, 0x0E: 0x44, 0x11: 0x0D, 0x14: 0x05, 0x18: 0x58, 0x1A: 0x06, 0x1C: 0x87, 0x1D: 0x33, 0x1F: 0x5C,
    0x20: 0x60, 0x24: 0x3B, 0x25: 0x5F, 0x26: 0x04, 0x28: 0x48, 0x2A: 0x8F, 0x2C: 0xA6, 0x2E: 0x41, 0x33: 0x76,
    0x36: 0x77, 0x38: 0x56, 0x3E: 0xAE, 0x40: 0x34, 0x46: 0x9E, 0x48: 0x83, 0x4D: 0x6C, 0x5C: 0x0C,
    0x04: 0x50,
}
# 사건 전투의 FC 몬스터 → DQ5 번호. 능력치·이름은 사건 모듈(dq4ch2tempe·dq4ch2endor)이 쓰고 dq4ch2slots 가 예약한다.
# 필드의 あばれこまいぬ(PORT 18)와 텐페 석상은 번호가 달라(예약 번호는 필드에 나오지 않음) 같은 그림을 두 자리에 둔다
EVENT = {0x12: 0x53, 0x18: 0xA3, 0xAF: 0xAA, 0xB0: 0xA4, 0xB1: 0x8E, 0xB2: 0x68, 0xBA: 0x72}
# 3장 구역에 처음 FC 능력치로 넣은 FC 몬스터 → (DQ5 번호, NDS 그림 번호). 1장 구역에도 이 번호를 쓴다. 번호는 2장 예비
# (dq4ch2slots)에서 왔다. 그림은 아직 옮기지 않아 대역(dq4fieldencounter.PLACEHOLDERS)의 그림 레코드를 가리키게 하고
# (picture_writes), 레코드는 PORT 처럼 대역 바탕에 FC 값을 덮는다(record_writes). NDS 번호는 이름(adopt.tsv)과 뒤에 넣을 그림
CH3 = {0x0A: (0xC5, 9), 0x13: (0xB6, 15), 0x17: (0x9D, 110), 0x19: (0xA5, 6), 0x1E: (0xE3, 7), 0x21: (0x3D, 32)}
# 1장 구역에만 나오던 대역 셋(エアラット·みならいあくま·ピクシー). 번호는 이 해킹이 쓰지 않는 DQ5 몬스터(free_numbers)
CH1 = {0x09: (0x07, 20), 0x10: (0x16, 10), 0x22: (0x21, 26)}
NUMBERED = {**CH3, **CH1}
# 조우에는 없고 합체(がったい, FC 55 → DQ5 6F)로만 나오는 FC 몬스터 → (DQ5 번호, NDS 그림 번호). DQ5 6F 는 무리를 DQ5
# キングスライム 6B 한 마리로 바꾸므로 6B 레코드에 FC キングスライム(30) 값을 둔다. 그림은 DQ5 6B 그대로
MERGED = {0x30: (0x6B, 107)}
# 1·2장 조우·사건 무리에 아직 나오지 않아 빌드가 그림을 넣지 않는 번호(dq4monport.build 의 appear). 그 장을 옮기면
# 여기서 빼고, dq4monartcheck 는 이 밖의 번호가 원래 DQ5 그림이면 실패로 본다
LATER = {0x0C}     # メタルスライム(FC 5C)
GRID = 8
RECORD, RECORD_SIZE = 0x238000, 25      # DQ5 몬스터 표(dq5tables monsters)


def nds_of(fc):
    return next(nds for f, nds, _ in dq4monart.TARGETS if f == fc)




def picture_image(fc):
    """색 번호 PNG(팔레트 모드, 0 투명, 1~15)와 색 목록(BGR555). 불투명 상자를 8픽셀 칸으로 늘려 가운데에 둔다."""
    src = Image.open(dq4monart.pose_path(nds_of(fc))).convert('RGBA')
    red, pal, _ = dq4monart.reduce(src, nds_of(fc))
    box = red.getbbox()
    red = red.crop(box)
    w, h = -(-red.width // GRID) * GRID, -(-red.height // GRID) * GRID
    colors = [c for _, c in pal]
    index = {c: i + 1 for i, c in enumerate(colors)}
    img = Image.new('P', (w, h), 0)
    ox, oy = (w - red.width) // 2, h - red.height        # 발이 칸 바닥에 닿게
    for y in range(red.height):
        for x in range(red.width):
            p = red.getpixel((x, y))
            if p[3]:
                img.putpixel((ox + x, oy + y), index[p[:3]])
    img.putpalette([0, 0, 0] + [v for c in colors for v in c] + [0, 0, 0] * (255 - len(colors)))
    return img, [(c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10 for c in colors]


def doc(rom, out_dir, only=None):
    """dq5monster/1 문서를 out_dir/monsters.json 으로, 그림 PNG 를 그 옆에 쓴다. rom 은 원래 DQ5(dq5map.Rom).
    only 는 넣을 DQ5 번호(없으면 모두)."""
    import dq5mongfx
    out_dir.mkdir(parents=True, exist_ok=True)
    pictures, monsters = [], []
    for fc, m in [*PORT.items(), *EVENT.items()]:
        if only is not None and m not in only:
            continue
        g = dq5mongfx.monster(rom, m)[0]
        img, colors = picture_image(fc)
        name = f'{g:02X}.png'
        img.save(out_dir / name)
        w, h = img.width // GRID, img.height // GRID
        pictures.append({'picture': f'{g:02X}', 'image': name,
                         'header': {'float': False, 'raise': 0, 'hit_x': w // 2, 'hit_y': h // 2}})
        monsters.append({'monster': f'{m:02X}', 'colors': colors})
        # 같은 그림을 쓰는 다른 DQ5 몬스터는 이 롬에 나오지 않지만, 색 수가 그림보다 적으면 dq5monwrite 가 거부해 같은 색을 준다.
        # NUMBERED 번호는 빌드 롬에서 대역의 그림 레코드를 가리켜(picture_writes) 원래 그림을 쓰지 않는다
        taken = {*PORT.values(), *EVENT.values(), *(m for m, _ in NUMBERED.values())}
        for other in range(dq5mongfx.COUNT):
            if other not in taken and dq5mongfx.monster(rom, other)[0] == g:
                monsters.append({'monster': f'{other:02X}', 'colors': colors})
    d = {'format': 'dq5monster/1', 'pictures': pictures, 'monsters': monsters}
    (out_dir / 'monsters.json').write_text(json.dumps(d, indent=1))
    return out_dir / 'monsters.json'


# FC 몬스터 행동 번호(레코드 바이트 9~14 bit6-0, fc/dq4/docs/dq4-data-format.md 「몬스터 행동 번호」) → DQ5 몬스터 행동
# (26:8765 번호). 주문은 일행 주문(01~38)이 아니라 몬스터용 주문(39~65)이어야 한다: 일행 번호를 몬스터가 쓰면 전투가
# 멈춘다. 사건 모듈의 표(dq4ch1event·dq4ch2tempe·dq4ch2endor .FC_ACTIONS)에 없는 것만 둔다.
# 47 にげだす 는 DQ5 슬라임의 98(필드 68 이 0 이 아니면 주인공 레벨이 구역 레벨 + 4 를 넘을 때만 고름). 48·4B なかまをよぶ
# 는 고쳐 쓴 DQ5 부르기 칸 B5·B4(summon_writes).
# 55 がったい(행동 ID 66, 11:$A292: AI 평가 10:$BBAF 가 같은 편 8마리 이상일 때만 남기고, 모두를 キングスライム 30 한 마리로)는
# 같은 일을 하는 DQ5 がったいだ 6F(조건 12: 같은 몬스터 8마리 이상, 필드 68 ≥ 1)로. 합체한 キングスライム 의 1B マホステ 는 DQ5
# 몬스터용 주문에 없어 66.
# DQ5 몬스터 スカラ 는 55·56 둘이 주문 표(범위·대상 루틴·MP)가 같아 앞의 것. ピオリム(1E, 1장 ピクシー)은 DQ5 에 몬스터용도
# 일행용도 없어 부르기처럼 66
FC_ACTIONS = {0x0A: '45', 0x10: '4B', 0x11: '4C', 0x12: '4D', 0x13: '4E', 0x16: '53', 0x17: '54', 0x19: '59',
              0x1A: '52', 0x1C: '55', 0x1E: '66', 0x25: '5B', 0x33: '74', 0x36: '77', 0x38: '8B', 0x43: '96', 0x45: 'A3',
              0x47: '98', 0x48: 'B5', 0x49: '71', 0x4B: 'B4', 0x5D: 'AA', 0x55: '6F', 0x1B: '66'}
# FC 내성 칸 0~E(fc dq4data.RESIST_NAMES 차례: イオ ギラ メラ デイン バギ ヒャド マヌーサ ラリホー ザキ ニフラム マホトラ
# マホトーン メダパニ ルカニ メガンテ) → DQ5 내성 종류(50~61, dq5-data-format 「동료가 되는 몬스터」 앞 내성 표). DQ5 에만 있는
# 5F(쓰는 곳 없음)·60 どくのいき·61 なめまわし 등은 FC 에 짝이 없어 바탕 값을 둔다
FC_RESISTS = (0x52, 0x51, 0x50, 0x55, 0x54, 0x53, 0x58, 0x57, 0x56, 0x59, 0x5B, 0x5C, 0x5D, 0x5A, 0x5E)


def fc_actions():
    """FC 몬스터 행동 번호 → DQ5 몬스터 행동(16진 문자열). 사건 모듈의 표와 FC_ACTIONS 를 합친 것."""
    import dq4ch1event
    import dq4ch2endor
    import dq4ch2tempe
    tables = (dq4ch1event.FC_ACTIONS, dq4ch2tempe.FC_ACTIONS, dq4ch2endor.FC_ACTIONS, FC_ACTIONS)
    out = {}
    for t in tables:
        for k, v in t.items():
            if out.setdefault(k, v) != v:
                raise ValueError(f'FC 행동 {k:02X} 가 {out[k]} 와 {v} 로 갈림')
    return out


# DQ5 몬스터용 주문 번호(26:8765 의 39~65). 일행이 외우는 주문(dq4party.dq5_spells)은 01~38 이고 전투 도구의 효과 행동도
# 01~38 과 MP 를 쓰지 않는 3F(らいじんのヤリ)뿐이라, 이 칸의 MP 를 바꿔도 일행 주문 MP 는 그대로다
MONSTER_SPELLS = range(0x39, 0x66)


def spell_entries(prg):
    """dq5tables/1 의 spells: FC 몬스터 주문이 옮겨 가는 DQ5 몬스터용 주문(fc_actions 가운데 39~65)의 전투 MP 를 FC 값으로.
    FC 주문 둘이 MP 가 다른데 같은 DQ5 번호로 가면 ValueError."""
    import dq4data
    out = {}
    for n, a in sorted(fc_actions().items()):
        d = int(a, 16)
        if n >= dq4data.MON_ACT[2] or d not in MONSTER_SPELLS:
            continue
        mp = dq4data.spell_mp(prg, dq4data.monster_action(prg, n))[0]
        if out.setdefault(d, mp) != mp:
            raise ValueError(f'DQ5 주문 {d:02X} 에 FC MP {out[d]} 와 {mp} 가 옴')
    return [{'id': f'{d:02X}', 'MP': mp} for d, mp in sorted(out.items())]


def fc_resists(prg, record, base='0' * 18):
    """FC 레코드의 내성 15칸을 DQ5 내성 18칸 문자열(dq5tables 「내성」)로. FC 에 짝이 없는 칸은 base 의 것.
    값 0~3 은 그대로 옮긴다(FC 성공률 FF·D8·66·00, DQ5 피해 배율 255·205·84·0 으로 단계가 같음)."""
    import dq4data
    out = list(base)
    for kind, v in zip(FC_RESISTS, dq4data.resists(prg, record)):
        out[kind - 0x50] = str(v)
    return ''.join(out)


def fc_entry(prg, fc, drop_item=None, resist_base='0' * 18):
    """FC 몬스터의 dq5tables/1 칸(id 없음): dq4ch1event.fc_monster 의 능력치·행동, FC 내성(fc_resists, DQ5 에만 있는 칸은
    resist_base), FC 드롭(드롭률은 FC 등급 그대로, 물건은 drop_item(FC 물건 번호) → DQ5 번호, 없거나 None 이면 FF).
    수비는 DQ5 상한 1FF 로 자른다(메탈 셋의 1023). MP 는 FC 그대로이고, 주문 한 번의 MP 는 spell_entries 가 FC 값으로 맞춘다."""
    import dq4ch1event
    import dq4data
    import dq4fieldencounter
    actions = fc_actions()
    e = dq4ch1event.fc_monster(prg, fc, actions)
    record = next(r for i, _, _, _, r in dq4data.monsters(prg) if i == fc)
    _, drop, rate = dq4fieldencounter.fc_monster_fields(record)
    item = None if drop is None or drop_item is None else drop_item(drop)
    e['수비'] = min(e['수비'], dq4fieldencounter.DQ5_DEFENCE_MAX)
    e['내성'] = fc_resists(prg, record, resist_base)
    e['드롭'], e['드롭률'] = ('FF', 0) if item is None else (f'{item:02X}', rate)
    return e


def drop_items(prg, dq5):
    """FC 물건 번호 → 이 해킹의 DQ5 물건 번호, 없으면 None. 가게·상자와 같이 찾는다(dq4shopport.dq5_items: 히라가나를
    가타카나로 접은 이름이 같은 DQ5 물건, 빌린 자리 dq4itemport.BORROWED 는 FC 이름으로)."""
    import dq4data
    import dq4shopport
    import dq4text
    from dq5map import Rom
    names = dq4shopport.dq5_items(Rom(dq5))
    items = dq4data.name_list(prg, 'item')

    def of(drop):
        return names.get(dq4shopport._fold(dq4text.text(items[drop + 1])))
    return of


def field_numbers():
    """FC 능력치를 넣는 필드 번호: {FC 몬스터: DQ5 번호}(PORT·NUMBERED·MERGED)."""
    return {**PORT, **{fc: m for fc, (m, _) in {**NUMBERED, **MERGED}.items()}}


def record_writes(original, dq5_of, prg):
    """필드 번호(field_numbers)마다 지금 대역(dq5_of: FC → 대역 DQ5 번호, dq4fieldencounter.PLACEHOLDERS)의 레코드
    25바이트에 FC 능력치·행동·내성·드롭(fc_entry)을 덮은 dq5patch/1 쓰기. DQ5 에만 있는 내성 칸은 대역 것."""
    import dq5tables
    from dq5map import lorom
    table = dq5tables.TABLES['monsters']
    drop_item = drop_items(prg, original)
    out = []
    for fc, m in field_numbers().items():
        base_of = dq5_of.get(fc, m)       # MERGED 는 대역이 없어 제 레코드 바탕
        b = bytearray(original[lorom(RECORD + base_of * RECORD_SIZE):][:RECORD_SIZE])
        base = ''.join(str(dq5tables.get(b, [dq5tables.resist_piece(i)])) for i in range(dq5tables.RESISTS))
        for k, v in fc_entry(prg, fc, drop_item, base).items():
            if k == '내성':
                for i, c in enumerate(v):
                    dq5tables.put(b, [dq5tables.resist_piece(i)], int(c))
                continue
            kind, pieces = table.fields[k]
            dq5tables.put(b, pieces, dq5tables.parse(kind, v))
        at = RECORD + m * RECORD_SIZE
        orig = original[lorom(at):lorom(at) + RECORD_SIZE]
        if bytes(b) == orig:
            continue
        out.append({'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': b.hex(' '), 'orig': orig.hex(' '),
                    'note': f'FC {fc:02X} 몬스터 레코드({base_of:02X} 바탕에 FC 능력치·행동)'})
    return out


# 빈 DQ5 몬스터 번호를 셀 때 빼는 것: 격투장 시합 표(23:DA97, 시합 50개 × [몬스터][倍率] 넷), 몬스터 레코드(23:8000)
COLOSSEUM, COLOSSEUM_MATCHES = 0x23DA97, 50


def free_numbers(dq5, prg, taken=None):
    """새 FC 몬스터에 줄 수 있는 DQ5 몬스터 번호(01~E6): 이 해킹이 쓰는 번호(taken, 없으면 used_numbers), 다른 몬스터가
    싸우는 도중에 부르는 몬스터(dq5monlimits.SUMMONED), 격투장에 나오는 몬스터(나중 장 카지노), 동료가 되는 몬스터(동료확률),
    능력치가 빈 레코드, 가나 이름이 롬 안에서 겹치는 번호(전투 글이 이름 바이트로 한글을 찾음, dq4battlemsg), FC 몬스터와
    이름이 같은 번호(뒷 장이 그 DQ5 몬스터를 그대로 쓸 수 있음)를 뺀 것."""
    from collections import Counter
    import dq4data
    import dq4windowtext as wt
    import dq5monlimits
    import dq5namewrite
    import dq5tables
    from dq5map import lorom
    taken = used_numbers() if taken is None else taken
    names_raw = dq5namewrite.read_tables(dq5)[4]
    names = wt.rom_names(dq5, 4, len(names_raw))
    count = Counter(bytes(n) for n in names_raw)
    colosseum = {dq5[lorom(COLOSSEUM) + i * 8 + 2 * k] for i in range(COLOSSEUM_MATCHES) for k in range(4)}
    table = dq5tables.TABLES['monsters']
    kana = str.maketrans(''.join(map(chr, range(0x3041, 0x3097))), ''.join(chr(c + 0x60) for c in range(0x3041, 0x3097)))
    fc_names = {str(n).translate(kana) for _, n, *_ in dq4data.monsters(prg)}
    out = []
    for m in range(1, 0xE7):
        record = dq5[lorom(RECORD) + m * RECORD_SIZE:][:17]
        if (m in taken or m in dq5monlimits.SUMMONED or m in colosseum or not any(record)
                or dq5tables.decode(table, None, dq5, m).get('동료확률') or count[bytes(names_raw[m])] != 1
                or names[m].translate(kana) in fc_names):
            continue
        out.append(m)
    return out


def used_numbers():
    """이 해킹이 쓰는 DQ5 몬스터 번호: 필드 조우(dq4fieldencounter.MONSTERS, 뒷 장 대역 포함)·필드 번호·사건 번호·1장 보스·
    2장 사건 예약."""
    import dq4ch1event
    import dq4ch2slots
    import dq4fieldencounter
    return (set(dq4fieldencounter.MONSTERS.values()) | set(field_numbers().values()) | set(EVENT.values())
            | set(dq4ch1event.BOSS_MONSTERS) | {m for s in dq4ch2slots.SLOTS.values() for m in s.monsters})


# dq5monwrite 의 옮긴 그림(24비트 머리 포인터 표 뒤, 뱅크를 넘으면 다음 뱅크로)과 늘린 몬스터 레코드 자리. 빌드 롬에서
# 통째로 0 인 뱅크 48~4B 가운데. 빌드가 쓰기 전에 0 인지 본다(dq4chapter1.apply_writes)
PICTURES_AT, RECORDS_AT = '48:8000', '4B:8000'


def reachable(zone_report, event_groups):
    """(구역 번호 집합, 이벤트 무리 「나온 곳」 집합): 이 롬에서 나올 수 있는 DQ5 구역(그룹 빌드 zone-report.json 의
    zone 과 배의 SEA_AREAS)과 이 해킹의 사건 무리. 나머지 DQ5 구역·무리는 닿지 않는데, 새 번호의 원래 DQ5 몬스터나 그림을
    같이 쓰는 DQ5 몬스터가 거기 남아 있어 세면 덜 놓인다고 거부된다."""
    import dq4fieldencounter
    areas = {v['zone'] for v in json.loads(zone_report.read_text()).values()} | set(dq4fieldencounter.SEA_AREAS)
    return areas, {f'이벤트 무리 {g:02X}' for g in event_groups}


def build(dq5, rom, work, zone_report, event_groups):
    """빌드 중인 롬(무리·구역·사건 무리가 들어간 것)으로 그림·색 패치 목록을 만들어 경로를 돌려준다. 무리 조합 검사
    (dq5monlimits)는 이 롬의 무리 가운데 나올 수 있는 것(reachable)만 센다."""
    import dq5monlimits
    import dq5monwrite
    from dq5map import Rom
    work.mkdir(parents=True, exist_ok=True)
    areas, groups = reachable(zone_report, event_groups)
    counted, area = dq5monlimits.compositions, dq5monlimits.area

    def scoped_area(r, n, *rest):
        # 닿지 않는 구역은 칸 가중치를 0 으로 읽게 해 세지 않는다. 「나온 곳」 으로 거르면 같은 조합이 닿지 않는 구역에서
        # 먼저 나왔을 때(첫 곳만 남음) 사건 무리의 것까지 빠진다
        ar = area(r, n, *rest)
        return ar if n in areas else {**ar, 'weights': [0] * len(ar['weights'])}

    def scoped(r, n_areas=None):
        dq5monlimits.area = scoped_area
        try:
            found, skipped = counted(r, n_areas)
        finally:
            dq5monlimits.area = area
        return {k: w for k, w in found.items() if w.startswith('구역 ') or w in groups}, skipped
    # 이 롬의 조우에 아직 나오지 않는 몬스터(뒷 장 구역에만 나옴)는 한도를 셀 수 없어 그 장을 옮길 때 넣는다
    appear = {m for found in scoped(Rom(bytes(rom)))[0] for m, _, _ in found}
    source = doc(Rom(dq5.read_bytes()), work / 'pictures', appear)
    later = sorted(m for m in [*PORT.values(), *EVENT.values()] if m not in appear)
    if later:
        print('dq4monport: 조우에 아직 없어 그림을 넣지 않은 번호 ' + ' '.join(f'{m:02X}' for m in later), file=sys.stderr)
    dq5monlimits.compositions = scoped
    try:
        manifest = dq5monwrite.patch(Rom(bytes(rom)), json.loads(source.read_text()), source.parent,
                                     at=dq5monwrite.address(PICTURES_AT),
                                     records_at=dq5monwrite.address(RECORDS_AT))
    finally:
        dq5monlimits.compositions = counted
    out = work / 'monsters.dq5patch.json'
    out.write_text(json.dumps(manifest, ensure_ascii=False))
    return out


def picture_writes(original, dq5_of):
    """NUMBERED 번호마다 그림 레코드 포인터(dq5mongfx.record_table 의 2바이트)를 대역(dq5_of)의 것으로: 그림·색이 지금
    대역과 같아 무리 조합 한도(dq5monlimits)도 대역과 같다."""
    import dq5mongfx
    from dq5map import Rom, lorom
    table, bank = dq5mongfx.record_table(Rom(original))
    out = []
    for fc, (m, _) in NUMBERED.items():
        at, src = table + m * 2, table + dq5_of[fc] * 2
        new, orig = original[lorom(src):lorom(src) + 2], original[lorom(at):lorom(at) + 2]
        out.append({'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': orig.hex(' '),
                    'note': f'FC {fc:02X} 몬스터 그림을 대역 {dq5_of[fc]:02X} 의 것으로'})
    return out


# 부르기(FC 11:$A0F8·$A151, 빈 전투원 칸과 그림 자리가 있을 때 한 마리): 48(행동 ID 59)은 부른 몬스터의 무리와 같은
# 몬스터, 4B(ID 5C)는 14:$8646 첫 칸 0F 를 14:$B2D5 로 찾은 몬스터 14 ホイミスライム. DQ5 부르기 AE~B5 의 처리기
# (20:D9D6 + 4 × n: LDA #몬스터 / BRA 20:DA4B)는 정해진 몬스터를 부르므로, 이 해킹이 쓰는 DQ5 몬스터(used_numbers)가
# 쓰지 않는 칸 둘을 고쳐 쓴다(B4: 원래 DQ5 B0 만, B5: D0·D9 만). 20:DA4B 는 A 의 몬스터가 이미 무리에 있으면 그 무리에
# 더하고, 그림 자리(22:D2FE)·빈 무리가 없으면 부르지 못한다
SUMMON_HANDLERS, SUMMON_COMMON = 0x20D9D6, 0x20DA4B
SUMMON_SAME, SUMMON_FIXED = 0xB5, 0xB4
SUMMON_FIXED_FC = 0x14
# 같은 몬스터 부르기 코드: BRK 88 7D(전투원 칸 $42 → 무리 $46)를 쓰므로 40 아래 뱅크. 원래 롬 빈 자리 16:FE10~ 가운데
# 맡기는 곳 수수료(dq4bankfee) 뒤
SUMMON_CODE_AT = 0x16FF00
ACTOR, GROUP_MONSTERS = 0x10F6, 0x1001          # 행동하는 전투원(bit7 몬스터), 무리마다 몬스터


def summon_code(at=SUMMON_CODE_AT):
    """(바이트, 라벨): 20:D9F2(B5 의 처리기)에서 JML 로 와서, 행동하는 몬스터의 무리 몬스터를 A 로 20:DA4B 에. M·X 8비트."""
    from dq4environmentrom import _Asm
    a = _Asm(at)
    a.label('same').b(0x8B, 0x4B, 0xAB, 0xA5, 0x42, 0x48, 0xA5, 0x46, 0x48)   # PHB PHK PLB / $42·$46 쌓기
    a.b(0xAD, *ACTOR.to_bytes(2, 'little'), 0x29, 0x7F, 0x85, 0x42)           # $42 = 몬스터 칸
    a.b(0x00, 0x88, 0x7D, 0xA6, 0x46)                                         # BRK 88 7D / LDX $46(무리)
    a.b(0xBD, *GROUP_MONSTERS.to_bytes(2, 'little'), 0x85, 0x71)              # $71 = 그 무리의 몬스터
    a.b(0x68, 0x85, 0x46, 0x68, 0x85, 0x42, 0xA5, 0x71, 0xAB)                 # 되돌리기 / A = 몬스터 / PLB
    a.b(0x5C, *SUMMON_COMMON.to_bytes(3, 'little'))                           # JML 20:DA4B
    return a.assemble()


def summon_writes(original):
    """dq5patch/1 쓰기: B4 처리기의 몬스터를 ホイミスライム 의 DQ5 번호로, B5 처리기를 같은 몬스터 부르기로."""
    from dq5map import lorom
    import dq4fieldencounter
    data, labels = summon_code()

    def handler(action):
        at = SUMMON_HANDLERS + 4 * (action - 0xAE)
        return at, original[lorom(at):lorom(at) + 4]
    fixed_at, fixed_orig = handler(SUMMON_FIXED)
    same_at, same_orig = handler(SUMMON_SAME)
    for orig in (fixed_orig, same_orig):
        if orig[0] != 0xA9 or orig[2] != 0x80:
            raise ValueError(f'부르기 처리기가 LDA # / BRA 가 아님: {orig.hex()}')
    fixed = bytes((0xA9, dq4fieldencounter.MONSTERS[SUMMON_FIXED_FC], *fixed_orig[2:]))
    same = bytes((0x5C, *labels['same'].to_bytes(3, 'little')))

    def put(at, new, orig, note):
        return {'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': new.hex(' '), 'orig': orig.hex(' '), 'note': note}
    return [{'at': f'{SUMMON_CODE_AT >> 16:02X}:{SUMMON_CODE_AT & 0xFFFF:04X}', 'hex': data.hex(' '),
             'note': '부르기: 행동하는 몬스터와 같은 몬스터(FC 48)'},
            put(fixed_at, fixed, fixed_orig, '부르기 B4 는 ホイミスライム(FC 4B)'),
            put(same_at, same, same_orig, '부르기 B5 는 같은 몬스터(FC 48)')]


# つうこん(FC 33, 행동 ID 44, 11:$98D2): rand(4) = 0 이면 공격력 × (64 + rand(11)) / 64(11:$9906, 수비 무시)와
# 「つうこんの いちげき」, 아니면 보통 공격. DQ5 かいしん１ 74 의 피해 루틴 20:B579(표 20:B7F9[74])도 rand(4) = 0 이면 수비 무시
# 회심이지만 폭이 공격력 + rand(공격력 × 5 / 100 + 1) 이다. 같은 루틴을 쓰는 みなごろし 8A(20:B62B)는 그대로 두고 행동이 74 일
# 때만 회심 값을 FC 식(공격력 + ⌊공격력 × r / 64⌋, r = rand(11))으로 바꾼다. 74 는 FC 33 만 쓴다(이 해킹의 DQ5 대역은 쓰지 않음)
CRIT_SITE, CRIT_ORIG = 0x20B587, bytes((0xA5, 0x46, 0x85, 0x71))     # 회심 갈래: LDA $46(공격력) / STA $71
CRIT_STORE = 0x20B5B1           # JSR $AF85 / CLC / RTS: $10EC·$10ED 의 피해를 쓰는 곳
CRIT_ACTION, CRIT_SPREAD = 0x74, 11
ACTION = 0x7E10F7
RAND = 0x00953A                 # A = n → 0~n-1(M·X 8비트)
DAMAGE = 0x7E10EC
CRIT_CODE_AT = 0x16FF30


def crit_code(at=CRIT_CODE_AT):
    """(바이트, 라벨): 20:B587 에서 JSL. M·X 8비트. 74 가 아니면 원래 두 명령."""
    from dq4environmentrom import _Asm
    a = _Asm(at)
    a.label('crit').b(0xAF, *ACTION.to_bytes(3, 'little'), 0xC9, CRIT_ACTION).rel(0xF0, 'fc')
    a.b(0xA5, 0x46, 0x85, 0x71, 0x6B)                                        # 원래 명령 / RTL
    a.label('fc').b(0xA9, CRIT_SPREAD, 0x22, *RAND.to_bytes(3, 'little'), 0x48)  # r = rand(11) / PHA
    a.b(0xA5, 0x46, 0x8F, 0x02, 0x42, 0x00, 0xA3, 0x01, 0x8F, 0x03, 0x42, 0x00)   # 공격력 아래 바이트 × r(4202·4203)
    a.b(0xEA, 0xEA, 0xEA, 0xEA, 0xC2, 0x20, 0xAF, 0x16, 0x42, 0x00, 0x85, 0x71, 0xE2, 0x20)  # $71·$72 = 곱
    a.b(0xA5, 0x47, 0x8F, 0x02, 0x42, 0x00, 0xA3, 0x01, 0x8F, 0x03, 0x42, 0x00)   # 위 바이트 × r(999 × 10 이라 8비트)
    a.b(0xEA, 0xEA, 0xEA, 0xEA, 0xAF, 0x16, 0x42, 0x00, 0x18, 0x65, 0x72, 0x85, 0x72, 0x68)  # $72 += 곱 / PLA
    a.b(0xC2, 0x20, 0xA5, 0x71, *([0x4A] * 6))                               # 공격력 × r >> 6
    a.b(0x18, 0x65, 0x46, 0x8F, *DAMAGE.to_bytes(3, 'little'), 0xE2, 0x20)   # + 공격력 → 피해
    a.b(0x68, 0x68, 0x68, 0x5C, *CRIT_STORE.to_bytes(3, 'little'))           # 돌아갈 곳 버림 / JML 20:B5B1
    return a.assemble()


def crit_writes(original):
    from dq5map import lorom
    data, labels = crit_code()
    orig = original[lorom(CRIT_SITE):lorom(CRIT_SITE) + len(CRIT_ORIG)]
    if orig != CRIT_ORIG:
        raise ValueError(f'20:B587 이 {orig.hex()}')
    return [{'at': f'{CRIT_CODE_AT >> 16:02X}:{CRIT_CODE_AT & 0xFFFF:04X}', 'hex': data.hex(' '),
             'note': 'つうこん(74)의 회심 피해를 FC 식으로'},
            {'at': '20:B587', 'hex': bytes((0x22, *labels['crit'].to_bytes(3, 'little'))).hex(' '),
             'orig': orig.hex(' '), 'note': '회심 갈래를 FC つうこん 식 훅으로'}]


def records_patch(original, prg, path):
    """record_writes·picture_writes·summon_writes·crit_writes 를 dq5patch/1 파일로. prg 는 FC 롬 PRG."""
    import dq4fieldencounter
    writes = record_writes(original, dq4fieldencounter.PLACEHOLDERS, prg)
    writes += picture_writes(original, dq4fieldencounter.PLACEHOLDERS)
    writes += summon_writes(original)
    writes += crit_writes(original)
    path.write_text(json.dumps({'format': 'dq5patch/1', 'name': 'dq4-monster-records', 'writes': writes},
                               ensure_ascii=False))
    return path


# 창 몬스터 목록(이름 아홉 열, dq4windowtext.KINDS 4)에 띄어쓰기를 빼도 들지 않는 이름. 전투 글은 원래 이름을 쓴다
SHORT = {0x02: '장난두더지', 0x40: '드래곤나비'}


def korean_names(window=False):
    """필드 번호(PORT·NUMBERED) → NDS 한글 이름(adopt.tsv 몬스터 표). window 면 SHORT 로 줄인 이름. 사건 몬스터의 이름은
    그 모듈의 MONSTER_NAMES."""
    names = dq4monart.korean_names()
    out = {m: SHORT.get(fc) if window and fc in SHORT else names[nds_of(fc)][1] for fc, m in PORT.items()}
    out.update({m: names[nds][1] for m, nds in {**NUMBERED, **MERGED}.values()})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('doc')
    s.add_argument('rom', type=Path)
    s.add_argument('-o', '--out', type=Path, required=True)
    a = ap.parse_args(argv)
    from dq5map import Rom
    print(doc(Rom(a.rom.read_bytes()), a.out))


if __name__ == '__main__':
    sys.exit(main())
