"""빌드 롬의 가게 목록·상자 칸·몬스터가 떨어뜨리는 물건을 FC 원작 표의 같은 가게·같은 칸·같은 종과 견준다.

이식 길(이름이 같은 DQ5 물건, 빌린 자리 dq4itemport.BORROWED·EVENT_ITEMS, 상자 대체 dq4chestport.SUBSTITUTE)을 거친 FC
물건이 빌드 롬에 같은 차례로 있어야 한다. 집합만 보면 같은 물건이 다른 가게·다른 칸으로 간 것은 보이지 않아서 따로 본다.

  가게  FC 맵(dq4groupbuild.placement 로 옮긴 새 그룹 맵)마다 그 맵에 판매자가 있는 종류(fc dq4shop.merchants)의 FC 목록
        (dq4shop.lookup)을 DQ5 번호로 바꾼 줄과, 빌드 롬 가게 키 표(dq4itemreach.key_rows)가 그 맵에 주는 키의 목록
  상자  FC 맵마다 상자(fc dq4chest.chests) 내용을 맵 안 차례로 바꾼 줄과, 빌드 롬 상자 표(dq5chestreloc.parse)의 그 맵 상자
  조사  タンス·つぼ(fc dq4block.pots)마다 빌드 롬 조사 표의 같은 칸(2x+1, 2y+1)
  값    가게에 있는 물건마다 FC 값(dq4data.items)과 빌드 롬 값(23:B081 × 배율)
  몬스터 dq4monport 가 옮긴 종(PORT)마다 FC 떨어뜨림과 빌드 롬 레코드 +17

  uv run --locked python sfc/dq4/tools/dq4itemmatch.py --rom work/ch3/dq4-ch1.sfc
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (HERE, HERE.parents[1] / 'dq5' / 'tools', ROOT / 'fc' / 'dq4' / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

FC_ROM, DQ5_ROM = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
# FC 가게 종류(15:$9CBF: 1 무기, 2 도구, 3 방어구) → DQ5 목록 종류(dq4shopport.LIST_KIND)
FC_KINDS = (1, 2, 3)
ITEMS = 0xD8
MONSTER_RECORDS, MONSTER_SIZE, DROP = 0x238000, 25, 0x17
NO_ITEM = 0xFF

# 알려진 다름: (가게·상자·몬스터, 자리) → 까닭. 고치면 지운다. 더 다르지 않은 줄이 남으면 「지난 줄」 로 실패한다
KNOWN = {}


def _fc(dq4):
    from kr_patch.fc import ines
    return ines.prg(Path(dq4).read_bytes())


def to_dq5(dq5_rom):
    """FC 물건 이름 → DQ5 번호(없으면 None). 가게·상자·떨어뜨림 이식이 쓰는 짝(dq4shopport.dq5_items)."""
    import dq4shopport
    known = dq4shopport.dq5_items(dq5_rom)

    def of(name):
        return known.get(dq4shopport._fold(name))
    return of


def shop_rows(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(FC 맵, 종류, FC 이름 목록, 기대 DQ5 목록, 빌드 목록 또는 None)]."""
    import dq4groupbuild
    import dq4itemreach
    import dq4shop
    import dq4shopport
    import dq5progresswrite
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    of = to_dq5(Rom(Path(dq5).read_bytes()))
    items = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names = dq4shop.item_names(prg)[0]
    keys = dq4itemreach.key_rows(rom)
    lists = {(kind, raw[0]): list(raw[1:-1]) for (kind, _), (_, raw) in dq5progresswrite.shop_records(rom).items()}
    out = []
    for (g, k), (g5, m5) in sorted(dq4groupbuild.placement(prg).items()):
        # 그 장 시작에 서 있는 판매자(dq4shopport.merchants: 이야기 flag·장·일행 조건, 물건이 하나도 DQ5 에 없으면 말만 함)
        kinds = {kind for kind in dq4shopport.merchants(prg, g, k, items).values() if kind in FC_KINDS}
        key = next((key for rg, a, b, key in keys if rg == g5 and a <= m5 <= b), None)
        for kind in sorted(kinds):
            fc = dq4shop.lookup(prg, kind, g, k) or []
            fc_names = [names[i] for i in fc]
            want = [of(n) for n in fc_names]
            got = lists.get((dq4shopport.LIST_KIND[kind], key)) if key is not None else None
            out.append(((g, k), kind, fc_names, [w for w in want if w is not None], got))
    return out


def price_rows(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(FC 맵, FC 이름, FC 값, DQ5 번호, 빌드 값)]. 가게에 판매자가 있는 맵의 FC 목록 물건마다. 빌드 값은 그 맵 가게 키의
    장소별 값(dq4localprice)이 있으면 그것, 없으면 물건 값."""
    import dq4groupbuild
    import dq4itemreach
    import dq4localprice
    import dq4shop
    import dq4shopport
    import dq5shop
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    items = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names = dq4shop.item_names(prg)[0]
    keys, local = dq4itemreach.key_rows(rom), dq4localprice.parse(rom)
    out = []
    for (g, k), (g5, m5) in sorted(dq4groupbuild.placement(prg).items()):
        key = next((key for rg, a, b, key in keys if rg == g5 and a <= m5 <= b), None)
        for kind in sorted(set(dq4shopport.merchants(prg, g, k, items).values()) & set(FC_KINDS)):
            for i in dq4shop.lookup(prg, kind, g, k) or []:
                n = items.get(dq4shopport._fold(names[i]))
                if n is not None:
                    out.append(((g, k), names[i], dq4shop.price(prg, g, k, i), n,
                                local.get((key, n), dq5shop.price(rom, n))))
    return out


def chest_rows(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(FC 맵, FC 내용 목록, 기대 DQ5 목록, 빌드 목록)]. 상자만(맵 안 차례로 번호가 매겨짐)."""
    import dq4chest
    import dq4chestport
    import dq4groupbuild
    import dq5chestreloc
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    doc = dq5chestreloc.parse(rom)
    built, start = {}, 0
    for row in doc['chest_maps']:
        built[row['group'], row['map']] = [c['reward'] for c in doc['chests'][start:start + row['count']]]
        start += row['count']
    import dq4shop
    import dq4shopport
    items = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names, _ = dq4shop.item_names(prg)
    special = dq4chest.special_codes(prg, dq4chest.SPECIAL_CHEST)
    out = []
    for (g, k), there in sorted(dq4groupbuild.placement(prg).items()):
        fc = dq4chest.chests(prg, g, k)
        if not fc:
            continue
        want = []
        for _, _, _, content, _ in fc:
            # 이식 규칙(dq4chestport.port): 특수 내용 → SPECIAL·SPECIAL_ITEMS, 금화 = 40 배, 이름이 같은 DQ5 물건(대체 표)
            if content in dq4chestport.SPECIAL:
                want.append(dq4chestport.SPECIAL[content])
            elif content in dq4chestport.SPECIAL_ITEMS:
                want.append(items[dq4shopport._fold(dq4chestport.SPECIAL_ITEMS[content])])
            elif content in special:
                want.append(None)
            else:
                want.append(dq4chestport._reward(names, items, content))
        out.append(((g, k), [desc for *_, desc in fc], want, built.get(there)))
    return out


def pot_rows(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(FC 자리, FC 이름, 기대 DQ5 물건, 빌드 물건 또는 None)]. タンス·つぼ(fc dq4block.pots)는 DQ5 조사 표의
    (새 그룹, 맵, 2x+1, 2y+1) 칸으로 간다(dq4chestport.port)."""
    import dq4block
    import dq4chestport
    import dq4groupbuild
    import dq4shop
    import dq4shopport
    import dq5chestreloc
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    items = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names, _ = dq4shop.item_names(prg)
    target = dq4groupbuild.placement(prg)
    built = {(r['group'], r['map'], r['x'], r['y']): r['reward'] for r in dq5chestreloc.parse(rom)['search']}
    out = []
    for e in dq4block.pots(prg):
        if (e['group'], e['index']) not in target:
            continue
        g5, m5 = target[e['group'], e['index']]
        want = dq4chestport._reward(names, items, e['item'], gold=False)
        out.append((f"{e['group']:02X}/{e['index']:02X} ({e['x']},{e['y']})", names[e['item']], want,
                    built.get((g5, m5, 2 * e['x'] + 1, 2 * e['y'] + 1))))
    return out


# 발밑 특수 내용 가운데 물건을 주는 것(fc dq4chest.FEET_SPECIAL 「위를 보면 …」, 1E:$B917·B94B·B964·B97D). 금화는 GOLD + 값
FEET_GIFTS = {0xE9: 'すばやさのたね', 0xE7: 'かわのよろい', 0xE6: 'やくそう', 0xE5: 50}


def foot_rows(data, dq4=FC_ROM, dq5=DQ5_ROM, chapter=3):
    """[(FC 자리, FC 설명, 기대 보상, 빌드 보상 또는 None)]. FC 발밑 숨은 물건(fc dq4chest.feet_items) 가운데 물건·금화를
    주는 것을, 그 장 이하 새 그룹 맵의 빌드 표와 견준다: 그 칸에서 조사는 발밑 표의 일행 칸 (2x, 2y+1), 「위를 보면」 은 바로
    위 FC 칸(빈 가구)의 서랍 표 칸 (2x+1, 2y−1)(dq4chestport.feet·look_up_feet)."""
    import dq4chest
    import dq4chestport
    import dq4groupbuild
    import dq4itemreach
    import dq4shop
    import dq4shopport
    import dq5chestreloc
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    items = dq4shopport.dq5_items(Rom(Path(dq5).read_bytes()))
    names, _ = dq4shop.item_names(prg)
    target = dq4groupbuild.placement(prg)
    doc = dq5chestreloc.parse(rom)
    foot = {(r['group'], r['map'], r['x'], r['y']): r['reward'] for r in doc['foot']}
    search = {(r['group'], r['map'], r['x'], r['y']): r['reward'] for r in doc['search']}
    out = []
    for g, k, x, y, c, desc, _ in dq4chest.feet_items(prg):
        there = target.get((g, k))
        if there is None or (dq4itemreach.group_chapter(there[0]) or 99) > chapter:
            continue
        at, table = (2 * x, 2 * y + 1), foot
        if c < 0x80:
            want = dq4chestport._reward(names, items, c)
        elif 0xA0 <= c < 0xAB:
            it = dq4chest.rd(prg, dq4chest.CHEST_BANK, dq4chest.FLAG_ITEMS + (c & 0x0F))
            want = dq4chestport.GOLD + (it & 0x7F) * 40 if it & 0x80 else dq4chestport._reward(names, items, it)
        elif c in FEET_GIFTS:
            gift = FEET_GIFTS[c]
            want = dq4chestport.GOLD + gift if isinstance(gift, int) else items[dq4shopport._fold(gift)]
            at, table = (2 * x + 1, 2 * y - 1), search
        else:
            continue                    # 사건(탈옥·벽 단추·금고 등)은 사건 모듈이 옮긴다
        out.append((f'{g:02X}/{k:02X} ({x},{y})', desc, want, table.get((*there, *at))))
    return out


def drop_rows(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(FC 몬스터, DQ5 번호, 기대 물건, 빌드 물건)]."""
    import dq4monport
    from dq5map import Rom
    prg = _fc(dq4)
    rom = Rom(bytes(data))
    of = dq4monport.drop_items(prg, Path(dq5).read_bytes())
    import dq4data
    import dq4fieldencounter
    records = {i: r for i, _, _, _, r in dq4data.monsters(prg)}
    out = []
    for fc, m in sorted(dq4monport.field_numbers().items()):
        _, drop, _ = dq4fieldencounter.fc_monster_fields(records[fc])
        want = NO_ITEM if drop is None else of(drop)
        got = rom.u8(MONSTER_RECORDS + m * MONSTER_SIZE + DROP)
        out.append((fc, m, NO_ITEM if want is None else want, got))
    return out


def differences(data, dq4=FC_ROM, dq5=DQ5_ROM):
    """[(곳, 자리, FC, 빌드)]. 빈 목록이어야 한다."""
    out = []
    for where, kind, fc_names, want, got in shop_rows(data, dq4, dq5):
        if got != want:
            out.append(('가게', f'{where[0]:02X}/{where[1]:02X} 종류 {kind}', ' '.join(fc_names) or '-',
                        '없음' if got is None else ' '.join(f'{i:02X}' for i in got)))
    for where, name, fc_price, n, price in price_rows(data, dq4, dq5):
        if fc_price != price:
            out.append(('값', f'{where[0]:02X}/{where[1]:02X} {name}', f'{fc_price}G', f'{n:02X} {price}G'))
    for where, fc_names, want, got in chest_rows(data, dq4, dq5):
        if got != want:
            out.append(('상자', f'{where[0]:02X}/{where[1]:02X}', ' '.join(str(n) for n in fc_names),
                        '없음' if got is None else ' '.join(f'{i:04X}' for i in got)))
    for at, name, want, got in pot_rows(data, dq4, dq5):
        if got != want:
            out.append(('조사', at, name, '없음' if got is None else f'{got:04X}'))
    for at, desc, want, got in foot_rows(data, dq4, dq5):
        if got != want:
            out.append(('발밑', at, desc, '없음' if got is None else f'{got:04X}'))
    for fc, m, want, got in drop_rows(data, dq4, dq5):
        if got != want:
            out.append(('몬스터', f'FC {fc:02X} → {m:02X}', f'{want:02X}', f'{got:02X}'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, type=Path)
    args = ap.parse_args()
    found = differences(args.rom.read_bytes())
    fail = 0
    for where, at, fc, got in found:
        why = KNOWN.get((where, at))
        print(f'{where} {at}: FC {fc} / 빌드 {got}' + (f' [알려짐: {why}]' if why else ''))
        fail += not why
    stale = sorted(set(KNOWN) - {(w, a) for w, a, _, _ in found})
    for w, a in stale:
        print(f'{w} {a}: 지난 줄 — 더 다르지 않으니 KNOWN 에서 지울 것')
    fail += len(stale)
    print(f'다름 {fail}건, 알려짐 {len(found) - fail + len(stale)}건')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
