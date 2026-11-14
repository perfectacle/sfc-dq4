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
# 40(ニセたいこう: 지면 snes9x 에서 멈춤)·ダミー 몬스터·2장 예비(dq4ch2slots.SPARE)·다른 몬스터가 싸우는 도중에 불러내는
# 몬스터(dq5monlimits.SUMMONED: 큰 그림이 싸우는 도중에 풀리면 NMI 몫이 달라 조심으로)는 뺐다.
# 필드 조우에 나오는 FC 몬스터 → DQ5 번호(지금 대역 레코드를 옮김)
PORT = {
    0x00: 0x02, 0x01: 0x13, 0x02: 0x30, 0x03: 0x7C, 0x05: 0x8B, 0x07: 0x37, 0x08: 0x08, 0x0B: 0x1A, 0x0C: 0x35,
    0x0D: 0x15, 0x0E: 0x44, 0x11: 0x0D, 0x14: 0x05, 0x18: 0x58, 0x1A: 0x06, 0x1C: 0x87, 0x1D: 0x33, 0x1F: 0x5C,
    0x20: 0x60, 0x24: 0x3B, 0x25: 0x5F, 0x26: 0x04, 0x28: 0x48, 0x2A: 0x8F, 0x2C: 0xA6, 0x2E: 0x41, 0x33: 0x76,
    0x36: 0x77, 0x38: 0x56, 0x3E: 0xAE, 0x40: 0x34, 0x46: 0x9E, 0x48: 0x83, 0x4D: 0x6C, 0x5C: 0x0C,
}
# 사건 전투의 FC 몬스터 → DQ5 번호. 능력치·이름은 사건 모듈(dq4ch2tempe·dq4ch2endor)이 쓰고 dq4ch2slots 가 예약한다.
# 필드의 あばれこまいぬ(PORT 18)와 텐페 석상은 번호가 달라(예약 번호는 필드에 나오지 않음) 같은 그림을 두 자리에 둔다
EVENT = {0x12: 0x53, 0x18: 0xA3, 0xAF: 0xAA, 0xB0: 0xA4, 0xB1: 0x8E, 0xB2: 0x68, 0xBA: 0x72}
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
        # 같은 그림을 쓰는 다른 DQ5 몬스터는 이 롬에 나오지 않지만, 색 수가 그림보다 적으면 dq5monwrite 가 거부해 같은 색을 준다
        for other in range(dq5mongfx.COUNT):
            if other not in PORT.values() and other not in EVENT.values() and dq5mongfx.monster(rom, other)[0] == g:
                monsters.append({'monster': f'{other:02X}', 'colors': colors})
    d = {'format': 'dq5monster/1', 'pictures': pictures, 'monsters': monsters}
    (out_dir / 'monsters.json').write_text(json.dumps(d, indent=1))
    return out_dir / 'monsters.json'


# FC 몬스터 행동 번호(레코드 바이트 9~14 bit6-0, fc/dq4/docs/dq4-data-format.md 「몬스터 행동 번호」) → DQ5 몬스터 행동
# (26:8765 번호). 주문은 일행 주문(01~38)이 아니라 몬스터용 주문(39~65)이어야 한다: 일행 번호를 몬스터가 쓰면 전투가
# 멈춘다. 사건 모듈의 표(dq4ch1event·dq4ch2tempe·dq4ch2endor .FC_ACTIONS)에 없는 것만 둔다.
# 47 にげだす 는 DQ5 슬라임의 98(필드 68 이 0 이 아니면 주인공 레벨이 구역 레벨 + 4 를 넘을 때만 고름). 48·4B なかまをよぶ
# 는 DQ5 의 부르기(AE~B5)가 정해진 DQ5 몬스터(dq5monlimits.SUMMONED)를 불러 그 그림이 들어오므로, 메시지만 나오는 66 으로
FC_ACTIONS = {0x0A: '45', 0x10: '4B', 0x11: '4C', 0x12: '4D', 0x13: '4E', 0x17: '54', 0x19: '59', 0x1A: '52',
              0x25: '5B', 0x33: '74', 0x36: '77', 0x38: '8B', 0x43: '96', 0x45: 'A3', 0x47: '98', 0x48: '66',
              0x49: '71', 0x4B: '66', 0x5D: 'AA'}


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


def spell_mp(prg, dq5, record, mp, actions):
    """FC MP 로 외울 수 있는 횟수를 DQ5 에서도 외우게 하는 MP. DQ5 몬스터용 주문은 FC 보다 MP 가 많은 것이 있어(ヒャド 2 → 3,
    マヌーサ 4 → 5) FC 값 그대로면 FC 에서 한 번은 외우던 몬스터가 한 번도 못 외운다. 주문마다 FC 횟수 × DQ5 MP 의 최댓값과
    FC MP 가운데 큰 것(255 까지). dq5 는 원래 DQ5 롬 바이트."""
    import dq4data
    import dq5spell
    from dq5map import Rom
    rom = Rom(dq5)
    need = mp
    for n in {b & 0x7F for b in record[9:15]}:
        if n >= dq4data.MON_ACT[2]:
            continue
        fc_cost = dq4data.spell_mp(prg, dq4data.monster_action(prg, n))[0]
        if fc_cost:
            need = max(need, mp // fc_cost * dq5spell.cost(rom, int(actions[n], 16))[0])
    return min(need, 0xFF)


def fc_entry(prg, fc, drop_item=None, dq5=None):
    """FC 몬스터의 dq5tables/1 칸(id 없음): dq4ch1event.fc_monster 의 능력치·행동, FC 드롭(드롭률은 FC 등급 그대로,
    물건은 drop_item(FC 물건 번호) → DQ5 번호, 없거나 None 이면 FF). 수비는 DQ5 상한 1FF 로 자른다(메탈 셋의 1023).
    dq5(원래 DQ5 롬 바이트)를 주면 MP 를 spell_mp 로."""
    import dq4ch1event
    import dq4data
    import dq4fieldencounter
    actions = fc_actions()
    e = dq4ch1event.fc_monster(prg, fc, actions)
    record = next(r for i, _, _, _, r in dq4data.monsters(prg) if i == fc)
    _, drop, rate = dq4fieldencounter.fc_monster_fields(record)
    item = None if drop is None or drop_item is None else drop_item(drop)
    e['수비'] = min(e['수비'], dq4fieldencounter.DQ5_DEFENCE_MAX)
    e['드롭'], e['드롭률'] = ('FF', 0) if item is None else (f'{item:02X}', rate)
    if dq5 is not None:
        e['MP'] = spell_mp(prg, dq5, record, e['MP'], actions)
    return e


def drop_items(prg, dq5):
    """FC 물건 번호 → 이 해킹의 DQ5 물건 번호(이름이 같은 DQ5 물건, 없으면 dq4itemport.BORROWED 의 빌린 자리), 없으면 None."""
    import dq4data
    import dq4itemport
    import dq4text
    from dq5chest import item_name
    from dq5map import Rom
    rom = Rom(dq5)
    names = {}
    for k in range(dq4itemport.ITEM_COUNT):
        names.setdefault(item_name(rom, k), k)
    names.update({v: k for k, v in dq4itemport.BORROWED.items()})
    kana = str.maketrans('りべぺへぼ', 'リベペヘボ')
    items = dq4data.name_list(prg, 'item')

    def of(drop):
        name = dq4text.text(items[drop + 1])
        return names.get(name, names.get(name.translate(kana)))
    return of


def record_writes(original, dq5_of, prg):
    """필드 번호(PORT)마다 지금 대역(dq5_of: FC → 대역 DQ5 번호, dq4fieldencounter.PLACEHOLDERS)의 레코드 25바이트에
    FC 능력치·행동·드롭(fc_entry)을 덮은 dq5patch/1 쓰기."""
    import dq5tables
    from dq5map import lorom
    table = dq5tables.TABLES['monsters']
    drop_item = drop_items(prg, original)
    out = []
    for fc, m in PORT.items():
        b = bytearray(original[lorom(RECORD + dq5_of[fc] * RECORD_SIZE):][:RECORD_SIZE])
        for k, v in fc_entry(prg, fc, drop_item, original).items():
            kind, pieces = table.fields[k]
            dq5tables.put(b, pieces, dq5tables.parse(kind, v))
        at = RECORD + m * RECORD_SIZE
        orig = original[lorom(at):lorom(at) + RECORD_SIZE]
        if bytes(b) == orig:
            continue
        out.append({'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': b.hex(' '), 'orig': orig.hex(' '),
                    'note': f'FC {fc:02X} 몬스터 레코드(대역 {dq5_of[fc]:02X} 바탕에 FC 능력치·행동)'})
    return out


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


def records_patch(original, prg, path):
    """record_writes 를 dq5patch/1 파일로. prg 는 FC 롬 PRG."""
    import dq4fieldencounter
    path.write_text(json.dumps({'format': 'dq5patch/1', 'name': 'dq4-monster-records',
                                'writes': record_writes(original, dq4fieldencounter.PLACEHOLDERS, prg)},
                               ensure_ascii=False))
    return path


# 창 몬스터 목록(이름 아홉 열, dq4windowtext.KINDS 4)에 띄어쓰기를 빼도 들지 않는 이름. 전투 글은 원래 이름을 쓴다
SHORT = {0x02: '장난두더지', 0x40: '드래곤나비'}


def korean_names(window=False):
    """필드 번호 → NDS 한글 이름(adopt.tsv 몬스터 표). window 면 SHORT 로 줄인 이름. 사건 몬스터의 이름은 그 모듈의
    MONSTER_NAMES."""
    names = dq4monart.korean_names()
    return {m: SHORT.get(fc) if window and fc in SHORT else names[nds_of(fc)][1] for fc, m in PORT.items()}


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
