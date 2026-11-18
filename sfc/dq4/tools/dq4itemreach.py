"""장 빌드 롬이 실제로 주는 DQ5 물건 번호. 창 칸 너비를 재는 검사(dq4windowlint)와 목록을 가장 긴 이름으로 채우는 실측이
「그 장에서 손에 드는 물건」 으로 쓴다.

출처마다 다음을 읽는다. 장 n 빌드 롬은 1~n 장 내용을 모두 담으므로, 시작 소지품·사건 지급도 1~n 장을 더한다.

  가게        이식한 가게 표(dq5progresswrite.shop_records, 3C:E000 으로 옮긴 표)의 종류 0~2 목록 가운데, 가게 키 표(3C:FE00
              훅이 읽음)에서 그 장 이하 새 그룹에 붙은 키와 3장 한 번 덮는 키(F0~F7)
  코인 경품   종류 3 의 키 15 목록(3장 엔돌 코인 교환소라 3장부터)
  상자·조사   상자·タンス·발밑·두 칸 앞·아래층 표(dq5chestreloc.parse, 코드가 가리키는 자리)에서 그 장 이하 새 그룹
              (dq4environmentrom.GROUPS, 장은 dq4groupbuild.LINKS) 맵의 물건
새 그룹의 장은 LINKS 의 chapter 로 가르고(없으면 서장·1장), 4·5장 새 그룹은 3장 집합에도 들지 않는다. 몬스터는 장으로 가르지
않는다(DQ4 몬스터 전부).
  몬스터      DQ4 몬스터(dq4windowtext.numbered_names 의 몬스터 번호) 레코드 23:8000 + n × 25 의 +17(FF 없음). 3장 빌드는
              3장 전투 뒤 물건 16칸(dq4fieldencounter.dq5_drop_items, 뱅크 4E 의 표로 쓰임)도
  시작 소지품 1장 주인공 기록 23:C014 의 물건 12칸(롬), 2장 アリーナ·동료 기록(dq4ch2event), 3장 トルネコ(dq4ch3event.start)
  사건 지급   빌린 자리 물건(dq4itemport.EVENT_ITEMS), 2장 꿀·팔찌·도적의 열쇠, 3장 사건 모듈 CALLS 의 give 인자

  uv run --locked python sfc/dq4/tools/dq4itemreach.py --rom work/ch3/dq4-ch1.sfc --chapter 3
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[1] / 'dq5' / 'tools'))

FC_ROM, DQ5_ROM = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
ITEMS = 0xD8                                   # DQ5 물건 수(dq5shop.ITEMS)
COIN_KEY = 0x15                                # 코인 경품 목록 키(dq4shopport.COIN_KEY)
COIN_CHAPTER = 3                               # 코인 교환소는 3장 엔돌 카지노(dq4ch3towns)
SHOP_KEY_CODE = 0x3CFE00                       # 가게 키 훅 코드와 키 표(dq4groupbuild.SHOP_KEY_AT)
HERO_RECORD, RECORD_ITEMS, ITEM_SLOTS = 0x23C014, 0x16, 12
MONSTER_RECORDS, MONSTER_SIZE, DROP = 0x238000, 25, 0x17
NO_ITEM = 0xFF


def group_chapter(group):
    """새 그룹(36~)이 담은 FC 그룹의 장(dq4groupbuild.LINKS 의 chapter, 없으면 서장·1장 = 1). 새 그룹이 아니면 None."""
    import dq4groupbuild
    parts = dq4groupbuild.LINKS.get(group)
    if parts is None:
        return None
    return min(p.get('chapter') or 1 for p in parts)


def key_rows(rom):
    """가게 키 표 [(DQ5 그룹, 첫 맵, 끝 맵, 키)]. 3C:FE00 의 훅 코드가 LDA long,X 로 읽는 자리(dq4shopkey.table)."""
    code = bytes(rom.u8(SHOP_KEY_CODE + i) for i in range(0x80))
    k = next(i for i in range(len(code) - 3) if code[i] == 0xBF and code[i + 3] == SHOP_KEY_CODE >> 16)
    a = SHOP_KEY_CODE & 0xFF0000 | code[k + 1] | code[k + 2] << 8
    rows = []
    while rom.u8(a) != 0xFF:
        rows.append(tuple(rom.u8(a + i) for i in range(4)))
        a += 4
    return rows


def _shops(rom, chapter):
    import dq5progresswrite
    import dq4shopkey
    chapters = {}
    for group, _, _, key in key_rows(rom):
        c = group_chapter(group)
        chapters[key] = min(chapters.get(key, c or 1), c or 1)   # 새 그룹이 아닌 빌린 맵 키는 모든 장에 넣는다
    # 한 번 덮는 키(F0~F7)는 3장 레이크나바 무기점 주인의 재고 조합(dq4ch3lakanaba)이다
    chapters.update({key: 3 for key in dq4shopkey.ONE_SHOT})
    shops, coins = set(), set()
    for (kind, _), (_, raw) in dq5progresswrite.shop_records(rom).items():
        key, items = raw[0], set(raw[1:-1])
        if kind < 3 and key in chapters and chapters[key] <= chapter:
            shops |= items
        elif kind == 3 and key == COIN_KEY and chapter >= COIN_CHAPTER:
            coins |= items
    return shops, coins


def _chests(rom, chapter):
    import dq4environmentrom
    import dq5chestreloc
    maps = {m for m in dq4environmentrom.GROUPS.values() if (group_chapter(m[0]) or 99) <= chapter}
    doc = dq5chestreloc.parse(rom)
    out, start = set(), 0
    for row in doc['chest_maps']:
        if (row['group'], row['map']) in maps:
            out |= {c['reward'] for c in doc['chests'][start:start + row['count']] if c['reward'] < ITEMS}
        start += row['count']
    for name in ('search', 'foot', 'ahead', 'lower'):
        out |= {r['reward'] for r in doc[name] if (r['group'], r['map']) in maps and r['reward'] < ITEMS}
    return out


def _drops(rom, chapter, prg, dq5):
    import dq4windowtext
    out = {rom.u8(MONSTER_RECORDS + m * MONSTER_SIZE + DROP) for m in dq4windowtext.numbered_names().get(4, {})}
    out.discard(NO_ITEM)
    if chapter >= 3:
        import dq4fieldencounter
        out |= set(dq4fieldencounter.dq5_drop_items(prg, dq5))
    return out


def _starts(rom, chapter, dq5):
    out = {rom.u8(HERO_RECORD + RECORD_ITEMS + k) for k in range(ITEM_SLOTS)} - {NO_ITEM}
    if chapter >= 2:
        import dq4ch2event
        out.add(dq4ch2event.SILK_ROBE)
        out |= {i for r in dq4ch2event.RECRUITS for i in r['items']}
    if chapter >= 3:
        import dq4ch3event
        out |= {item for item, _ in dq4ch3event.start(dq5, FC_ROM)['items']}
    return out


def _events(chapter):
    import dq4itemport
    out = set(dq4itemport.EVENT_ITEMS)
    if chapter >= 2:
        import dq4ch2frenol
        import dq4ch2king
        out |= {dq4ch2king.HONEY, dq4ch2frenol.BRACELET, dq4ch2frenol.THIEF_KEY}
    if chapter >= 3:
        import dq4ch3event
        for _, mod in dq4ch3event.modules():
            out |= {param for routine, param in getattr(mod, 'CALLS', {}).values() if routine == 'give'}
    return out


def given_items(data, chapter, dq4=FC_ROM, dq5=DQ5_ROM):
    """{출처: DQ5 물건 번호 집합}. data 는 그 장 빌드 롬 바이트, chapter 는 1·2·3."""
    from dq5map import Rom
    from kr_patch.fc import ines
    rom = Rom(bytes(data))
    dq5_bytes = Path(dq5).read_bytes()
    prg = ines.prg(Path(dq4).read_bytes())
    shops, coins = _shops(rom, chapter)
    return {'가게': shops, '코인 경품': coins, '상자·조사': _chests(rom, chapter), '몬스터': _drops(rom, chapter, prg, dq5_bytes),
            '시작 소지품': _starts(rom, chapter, dq5_bytes), '사건 지급': _events(chapter)}


def given_union(data, chapter, dq4=FC_ROM, dq5=DQ5_ROM):
    out = set()
    for items in given_items(data, chapter, dq4, dq5).values():
        out |= items
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, type=Path, help='그 장 빌드 롬')
    ap.add_argument('--chapter', required=True, type=int, choices=(1, 2, 3))
    args = ap.parse_args()
    import dq5chest
    from dq5map import Rom
    data = args.rom.read_bytes()
    rom = Rom(data)
    for where, items in given_items(data, args.chapter).items():
        print(f'{where} {len(items)}: ' + ', '.join(f'{n:02X} {dq5chest.item_name(rom, n)}' for n in sorted(items)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
