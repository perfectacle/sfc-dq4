"""FC DQ4 shops, inns and churches of the new DQ5 groups (dq4environmentrom.GROUPS).

People who open a shop in FC (fc/dq4/tools/dq4shop.merchants, on the base person list) get the DQ5 talk
number of the same service (06:DBD2: 01 weapon, 02 item, 03 armor, 04 deposit, 05 church, 06 inn; SERVICE). Every FC group
with a shop list or an inn gets its own key (dq4shopkey: 06:DC37 and 06:F576 read it in place of $BC).
Weapon, item and armor lists go to the DQ5 shop lists (dq5progress/1 `shops`) under that key, with FC items
matched to DQ5 items by name (an FC item DQ5 lacks may take a borrowed DQ5 slot, dq4itemport.fc_name); every item a
list sells gets its FC price (dq4itemport.writes). The inn price table 04:FD6D has no end mark and no room, so it is copied with
the new keys added and the two operands that point at it (06:F567 bank, 06:F56D address) are changed.

  python sfc/dq4/tools/dq4shopport.py --out work/dq4-shops
"""

import argparse
import functools
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4itemport  # noqa: E402
import dq4shop  # noqa: E402
import dq5item  # noqa: E402
import dq4shopkey  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4groupbuild import chapter, fc_map, has_people, placement  # noqa: E402
from kr_patch.fc import ines  # noqa: E402
from dq4ch3slots import SLOTS as _CH3_SLOTS, VARS2_AT as _CH3_VARS2  # noqa: E402

# FC shop kind (dq4shop.KINDS) -> DQ5 shop list kind (04:FBD5: 0 item, 1 armor, 2 weapon).
LIST_KIND = {1: 2, 2: 0, 3: 1}
# FC service (15:$9CBF; 0 and 5 both go to the church 15:$B550) -> DQ5 talk number of the same service.
# FC 7 (a free inn, 15:$A6B0) has no DQ5 counterpart; DQ5 07 is the monster deposit.
SERVICE = {0: 5, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
# Script conditions a seller may have and still be one at the start of chapter 1: talking across the
# counter, the time of day, and Burland's armor seller turning away at Y = 16 (15:$9D2A).
SELLER_CONDITIONS = ("counter", "낮", "밤", "주인공 Y")
# Story-flag person lists (dq4shop.npc_lists) are not the start of chapter 1.
FLAG_LIST = "목록 플래그"
STORY_FLAG = "flag& "
# dq4talk condition 16: $615A == n - 1, so "chapter n" is chapter n.
CHAPTER = "chapter "
# dq4talk 조건 03: 걷는 일행에 FC 인물 n 이 있다. 장 초기화(12:$913E)는 선두 하나만 둔다(86 87 85 83 80):
# 1장 ライアン, 2장 アリーナ, 3장 トルネコ, 4장 マーニャ, 5장 勇者.
PARTY = "party "
START_LEAD = {1: 6, 2: 7, 3: 5, 4: 3, 5: 0}
YES = "yes"
INN, CHURCH = 6, 5
INN_TABLE = 0x04FD6D
INN_ENTRIES = 21
INN_BANK_OPERAND = 0x06F568
INN_ADDR_OPERAND = 0x06F56E
# dq5progresswrite takes 1-6 items: the 7th row is under the comparison window (dq5-build-format 「성장·조우·상점」).
MAX_ITEMS = 6
# FC 3장 떠돌이 상인(18:$9D12 의 たびのしょうにん)의 도구점·여관은 가게 그룹 FE/FE(15:$BEF4). 필드에서 상인이 여는 DQ5
# 가게·여관은 필드의 $BC/$BD(01/00, 실측)로 키를 찾으므로 그 맵 줄에 상인 키를 준다. 이 해킹은 DQ5 01 그룹 맵에 가지
# 않고 필드에서 다른 가게를 열지 않는다. 키는 그룹 줄 뒤에 붙여 앞 키 번호가 그대로다
MERCHANT = (0xFE, 0xFE)
MERCHANT_MAP = (0x01, 0x00)
# 레이크나바 무기점 주인(FC 16/00 대화 054 → 15:$B847)의 목록: 이 맵의 FC 무기 목록 뒤에 파는 손님에게서 산 재고가
# 0 이 아닌 품목을 STOCK 차례로 하나씩 붙인다(15:$B26B, 개수만큼 붙이지 않음. 헤드리스 실측). 재고 조합 비트(STOCK 의
# 순번 k 가 bit k)마다 목록 하나를 한 번 쓰는 키 ONE_SHOT.start + 비트로 두고, 주인 대화(dq4ch3lakanaba)가 고른다
LAKANABA = (0x16, 0x00)
# 엔돌 카지노(FC 04/01)의 경품 6줄(15:$B375, 물건·코인 2바이트)을 DQ5 코인 교환(대화 0C)이 띄우는 よろず屋 목록(종류 3,
# 키 15)과 그 코인 값 표(04:FD5B, 목록 차례로 3바이트)에 둔다. DQ5 에 짝이 없는 경품은 뺀다(report missing_items).
# 코인 판매(대화 0B, 06:EE34)의 한 장 값은 06:EEDB LDA #$0014 의 즉값이고, FC 는 3장이면 200(15:$A884: $615A = 2
# 이면 C8, 1 이면 0A, 그 밖 14). 이 해킹에서 카지노가 열리는 것은 3장뿐이라 200 으로 둔다
CASINO = (0x04, 0x01)
COIN_KIND, COIN_KEY = 3, 0x15
COIN_PRICES = 0x04FD5B
COIN_SALE, COIN_SALE_ORIG, COIN_SALE_PRICE = 0x06EEDC, 0x14, 200
LAKANABA_STOCK = (0x0B, 0x04, 0x23)
# 카지노 몬스터 격투장(FC 04/01 (08,0A) 대화 048 → 18:$A813). FC 는 장마다 시합 수(18:$ADAA,$615A, 3장 20)만큼 앞에서
# 시합 표 18:$ADBA(8바이트: 몬스터 4·배율 4, FF 는 빈 자리)를 쓰고, 배율은 표 값 ± 난수/10(18:$A906, 최소 1.1)이다.
# DQ5 격투장(대화 0E)의 시합 표 23:DA97(8바이트: [몬스터][배율 정수] ×4, 50개)과 레벨 문턱 23:DC27(앞에서부터 문턱이
# 레벨 이하인 마지막 시합까지 고름, 26:8E5A)에 옮긴다. 몬스터가 모두 FC 능력치 번호(dq4monport.field_numbers)에 있고
# 그림이 들어가는(dq4monport.LATER 밖) 시합만 앞에서부터 두고, 문턱은 그 수만큼 0·나머지 FF 라 레벨과 무관하게 그 안에서 고른다
FC_ARENA_BANK, FC_ARENA_TABLE, FC_ARENA_COUNTS, FC_ARENA_CHAPTER = 0x18, 0xADBA, 0xADAA, 2
ARENA_MATCHES, ARENA_LEVELS, ARENA_SIZE = 0x23DA97, 0x23DC27, 50
# 옮기지 않는 FC 시합: 넷의 그림 가로 합이 전투 화면을 넘어 넷째가 놓이지 않는다(dq5monlimits.Pictures.place, 빌드 롬에서
# dq4ch3townscheck --rom 이 옮긴 시합마다 본다). 놓이지 않은 몬스터에도 걸 수 있어 빼 둔다. 그림이 바뀌면 다시 재어
# 놓이는 시합은 이 집합에서 뺀다(차례를 바꿔도 놓이지 않는 것만 남김). 3장 20시합은 NDS 그림·띄움(dq4monport.FLOATING)으로
# 모두 놓인다(6번은 はえおとこ 가 줄 2 로 떠 줄 0 이 23칸)
ARENA_WIDE = set()
ONE_SHOT_AT = _CH3_VARS2 + _CH3_SLOTS['L'].vars2[0]     # 한 번 쓰는 키 바이트(레이크나바 몫)
# Sellers who come only with a chapter's event (dq4shop.npc_lists 「목록 플래그 n&m」): FC map -> the person list that
# brings them. The event that switches the map to that list puts the seller; here its shop list goes under the map's
# key so that the seller's talk number (event_sellers) opens it. テンペ's shop opens once the monster is beaten
# ($627F bit7, dq4flags), フレノール's weapon shop once おうごんのうでわ is handed over ($627B bit6).
EVENT_LISTS = {(0x0E, 0x00): "목록 플래그 04&80", (0x0F, 0x00): "목록 플래그 00&40"}


def _fold(name):
    """Hiragana as katakana: DQ5 writes some item names in katakana (いばらのムチ)."""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in name)


def dq5_items(rom):
    """Folded name -> DQ5 item, with the borrowed slots under their FC names."""
    out = {}
    for i in range(216):
        name = _fold(dq4itemport.fc_name(rom, i))
        if name in out:
            raise ValueError(f"DQ5 items {out[name]:02X} and {i:02X} share the name {name}")
        out[name] = i
    return out


@functools.cache
def _names(prg):
    return dq4shop.item_names(prg)[0]


def has_goods(prg, kind, fc_group, number, items):
    """Whether an FC service sells anything DQ5 has: a list kind needs one DQ5 item (dq5_items) in its FC list."""
    if kind not in LIST_KIND:
        return True
    names = _names(prg)
    return any(_fold(names[i & 0x7F]) in items for i in dq4shop.lookup(prg, kind, fc_group, number))


def merchants(prg, fc_group, number, items=None):
    """{(x, y, night): FC service kind} for the base person list (no story-flag list). With `items` (dq5_items),
    a seller whose list has no DQ5 item at all only talks: レイクナバ 16/01 sells nothing but うまのふん."""
    out = {}
    for x, y, _, kind, cond, _ in dq4shop.merchants(prg, fc_group, number):
        if any(FLAG_LIST in c for c in cond):
            continue
        if items is not None and not has_goods(prg, kind, fc_group, number, items):
            continue
        # Story flags are all off at the start of a chapter: a seller that needs one is not there yet, and one
        # that needs one off is. The skip comes before the condition check so that the other conditions of a
        # seller who is not there yet (a talk answer, day) do not stop the build.
        if any(c.startswith(STORY_FLAG) for c in cond):
            continue
        cond = [c for c in cond if not c.startswith(f"아님({STORY_FLAG}")]
        # The chapter is the one whose start the FC group shows (dq4groupbuild.chapter).
        here = chapter(fc_group)
        if any(c.startswith(CHAPTER) and int(c[len(CHAPTER):]) != here for c in cond) or \
                any(c.startswith(f"아님({CHAPTER}") and int(c[len(CHAPTER) + 3:-1]) == here for c in cond):
            continue
        cond = [c for c in cond if not c.startswith((CHAPTER, f"아님({CHAPTER}"))]
        # 일행 조건은 그 장 시작의 선두로 본다: コーミズ 17/00 의 판매자는 ミネア·マーニャ 가 없을 때만 있다.
        lead = START_LEAD[here]
        if any(c.startswith(PARTY) and int(c[len(PARTY):], 16) != lead for c in cond) or \
                any(c.startswith(f"아님({PARTY}") and int(c[len(PARTY) + 3:-1], 16) == lead for c in cond):
            continue
        cond = [c for c in cond if not c.startswith((PARTY, f"아님({PARTY}"))]
        # A seller behind a はい/いいえ question (レイクナバ's weapon shop, where chapter 3's job starts) waits for
        # its event; until then the person only talks.
        if YES in cond:
            continue
        # The talk script's own time check (FC condition 14, dq4shop.DAY_CONDS) reads like the block's 낮/밤.
        cond = [{"day": "낮", "아님(not day)": "낮", "not day": "밤", "아님(day)": "밤"}.get(c, c) for c in cond]
        unknown = [c for c in cond if not any(c.startswith(k) for k in SELLER_CONDITIONS)]
        if unknown:
            raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): seller condition {unknown}")
        if kind not in SERVICE:
            raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): FC service {kind} has no DQ5 service")
        times = [n for n, tag in ((False, "낮"), (True, "밤")) if tag in cond] or [False, True]
        for night in times:
            if out.get((x, y, night), SERVICE[kind]) != SERVICE[kind]:
                raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): two services")
            out[x, y, night] = SERVICE[kind]
    return out


def event_merchants(prg, fc_group, number, items):
    """{(x, y, night): FC list kind} of the sellers EVENT_LISTS brings to an FC map: those of a shop list kind, and an
    inn when the map has none at the start."""
    tag = EVENT_LISTS.get((fc_group, number))
    out = {}
    if tag is None:
        return out
    sellers = dq4shop.merchants(prg, fc_group, number)
    # フレノール 은 처음 상태에 여관이 없다(주인이 공주가 묵는다며 거절). 사건 목록의 여관 주인이 그 맵 키의 여관 값을 쓴다
    base_inn = any(kind == INN and not cond for _, _, _, kind, cond, _ in sellers)
    for x, y, _, kind, cond, _ in sellers:
        if tag not in cond or (kind == INN and base_inn):
            continue
        if kind != INN and (kind not in LIST_KIND or not has_goods(prg, kind, fc_group, number, items)):
            continue
        rest = [c for c in cond if c != tag]
        unknown = [c for c in rest if not any(c.startswith(k) for k in SELLER_CONDITIONS)]
        if unknown:
            raise ValueError(f"{fc_group:02X}/{number:02X} ({x:02X},{y:02X}): event seller condition {unknown}")
        for night in [n for n, t in ((False, "낮"), (True, "밤")) if t in rest] or [False, True]:
            out[x, y, night] = kind
    return out


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def keys(place, kinds):
    """dq4shopkey rows (DQ5 group, first DQ5 map, last DQ5 map, key), keys from KEY_FIRST up. kinds[(DQ5 group,
    DQ5 map)]: the list kinds and inn of its sellers. Each FC group with any of them gets one row over all its maps,
    split into consecutive runs where a map brings a kind the run already has: a key has one list per kind and one
    inn price (エンドール sells armour on 04/00 and in 04/09)."""
    spans = {}
    for (fc_group, _), (group, number) in place.items():
        spans.setdefault((group, fc_group), []).append(number)
    rows, key = [], dq4shopkey.KEY_FIRST
    for (group, _), numbers in sorted(spans.items()):
        numbers = sorted(numbers)
        if not any(kinds.get((group, n)) for n in numbers):
            continue
        first, seen = numbers[0], set()
        for n in numbers:
            here = kinds.get((group, n), set())
            if here & seen:
                rows.append((group, first, n - 1, key))
                key, first, seen = key + 1, n, set()
            seen |= here
        rows.append((group, first, numbers[-1], key))
        key += 1
    return rows


def port(dq5_path, dq4_path, inn_at, key_at, with_people=True):
    """(service kinds per person, dq5progress shops, patch writes of the inn table and the key hook, report);
    `with_people` False ports no sellers.
    The inn table bank must show the low WRAM: 06:F563 keeps the table bank in DB and writes $0F28-$0F36 with
    absolute addresses."""
    if not inn_at >> 16 <= 0x3F:
        raise ValueError(f"inn table bank {inn_at >> 16:02X}: needs 00-3F")
    prg = ines.prg(Path(dq4_path).read_bytes())
    rom = dq5item.Rom(Path(dq5_path).read_bytes())
    items = dq5_items(rom)
    names, own_prices = dq4shop.item_names(prg)
    progress = json.loads(_dump_progress(dq5_path))
    counts = {k: sum(1 for s in progress["shops"] if s["kind"] == k) for k in range(4)}
    services, shops, inns, prices = {}, [], {}, {}
    report = {"shops": [], "missing_items": [], "local_prices": [], "inns": {}, "keys": {}, "prices": {},
              "event_sellers": {}}
    maps = sorted(GROUPS.values())
    for group, number in maps:
        fc_group, fc_number = fc_map(prg, group, number)
        services[f"{group:02X}/{number:02X}"] = (merchants(prg, fc_group, fc_number, items)
                                                 if has_people(fc_group, with_people) else {})
    events = {}
    for group, number in maps:
        fc_group, fc_number = fc_map(prg, group, number)
        if has_people(fc_group, with_people):
            found = event_merchants(prg, fc_group, fc_number, items)
            if found:
                events[f"{group:02X}/{number:02X}"] = found
    rows = keys(placement(prg), {(group, number): (set(services[f"{group:02X}/{number:02X}"].values()) & {*LIST_KIND, INN})
                                 | set(events.get(f"{group:02X}/{number:02X}", {}).values())
                                 for group, number in maps})
    for group, number in maps:
        fc_group, fc_number = fc_map(prg, group, number)
        found = services[f"{group:02X}/{number:02X}"]
        key = next((k for g, first, last, k in rows if g == group and first <= number <= last), None)
        event_kinds = set(events.get(f"{group:02X}/{number:02X}", {}).values())
        for kind in sorted(set(found.values()) | event_kinds):
            # A kind only the event list sells joins the key; one a base seller sells already has its list (FC
            # sellers of one map share the map's list of a kind, dq4shop.lookup, as フレノール's item shop in both).
            if kind not in found.values() and kind in LIST_KIND and \
                    any(s["key"] == key and s["kind"] == LIST_KIND[kind] for s in shops):
                continue
            if kind in LIST_KIND:
                if any(s["key"] == key and s["kind"] == LIST_KIND[kind] for s in shops):
                    raise ValueError(f"{group:02X}/{number:02X}: two {dq4shop.KINDS[kind]} lists under key {key:02X}")
                fc_items = dq4shop.lookup(prg, kind, fc_group, fc_number)
                picked = []
                for i in fc_items:
                    item = names[i & 0x7F]
                    price = dq4shop.price(prg, fc_group, fc_number, i & 0x7F)
                    if price != own_prices.get(i & 0x7F):
                        # 장소별 값(여우 마을 18 의 はがねのつるぎ 10G·うまのふん 2G, FC 15:$B2F7): DQ5 는 물건마다 값이
                        # 하나라 그 물건을 목록에서 뺀다
                        report["local_prices"].append(f"{group:02X}/{number:02X} {item} {price}")
                    elif _fold(item) in items:
                        picked.append(items[_fold(item)])
                        if prices.setdefault(picked[-1], price) != price:
                            raise ValueError(f"{item}: FC prices {prices[picked[-1]]} and {price}")
                    else:
                        report["missing_items"].append(f"{group:02X}/{number:02X} {item}")
                if len(picked) > MAX_ITEMS:
                    raise ValueError(f"{group:02X}: more than {MAX_ITEMS} items")
                dq5_kind = LIST_KIND[kind]
                shops.append({"kind": dq5_kind, "index": counts[dq5_kind], "key": key, "items": picked})
                counts[dq5_kind] += 1
                report["shops"].append({"map": f"{group:02X}/{number:02X}", "kind": dq4shop.KINDS[kind],
                                        "fc": [names[i & 0x7F] for i in fc_items], "dq5": picked})
            elif kind == INN:
                price = dq4shop.inn_price(prg, fc_group, fc_number)
                if price is None or price > 0x7F:
                    raise ValueError(f"{fc_group:02X}/{fc_number:02X}: inn price {price}")
                # One key per FC group: its maps share one price.
                if inns.get(key, price) != price:
                    raise ValueError(f"{key:02X}: inn prices {inns[key]} and {price} ({fc_group:02X}/{fc_number:02X})")
                inns[key] = price
                report["inns"][f"{group:02X}/{number:02X}"] = price
    key = max((k for *_, k in rows), default=dq4shopkey.KEY_FIRST - 1) + 1
    rows.append((*MERCHANT_MAP, MERCHANT_MAP[1], key))
    picked = []
    for i in dq4shop.lookup(prg, 2, *MERCHANT):
        item = names[i & 0x7F]
        if dq4shop.price(prg, *MERCHANT, i & 0x7F) != own_prices.get(i & 0x7F) or _fold(item) not in items:
            raise ValueError(f"떠돌이 상인 {item}: 장소별 값이거나 DQ5 짝이 없음")
        picked.append(items[_fold(item)])
        if prices.setdefault(picked[-1], own_prices[i & 0x7F]) != own_prices[i & 0x7F]:
            raise ValueError(f"{item}: FC prices {prices[picked[-1]]} and {own_prices[i & 0x7F]}")
    shops.append({"kind": LIST_KIND[2], "index": counts[LIST_KIND[2]], "key": key, "items": picked})
    counts[LIST_KIND[2]] += 1
    inns[key] = dq4shop.inn_price(prg, *MERCHANT)
    report["merchant"] = {"key": f"{key:02X}", "items": picked, "inn": inns[key]}
    if key >= dq4shopkey.ONE_SHOT.start:
        raise ValueError(f"가게 키 {key:02X} 가 한 번 쓰는 키에 닿음")
    report["lakanaba"] = lakanaba = {}
    # 3장 인물을 옮기지 않는 빌드(with_people False)나 맵 묶음에 레이크나바가 없으면 주인 가게도 없다
    has_lakanaba = any(fc_map(prg, g, n) == LAKANABA and has_people(LAKANABA[0], with_people) for g, n in maps)
    for bits in range(1 << len(LAKANABA_STOCK)) if has_lakanaba else ():
        fc_items = [i & 0x7F for i in dq4shop.lookup(prg, 1, *LAKANABA)]
        fc_items += [i for k, i in enumerate(LAKANABA_STOCK) if bits >> k & 1]
        picked = []
        for i in fc_items:
            if own_prices.get(i) is None or _fold(names[i]) not in items:
                raise ValueError(f"레이크나바 무기점 {names[i]}: 값이 없거나 DQ5 짝이 없음")
            picked.append(items[_fold(names[i])])
            if prices.setdefault(picked[-1], own_prices[i]) != own_prices[i]:
                raise ValueError(f"{names[i]}: FC prices {prices[picked[-1]]} and {own_prices[i]}")
        if len(picked) > MAX_ITEMS:
            raise ValueError(f"레이크나바 무기점: more than {MAX_ITEMS} items")
        shops.append({"kind": LIST_KIND[1], "index": counts[LIST_KIND[1]], "key": dq4shopkey.ONE_SHOT.start + bits,
                      "items": picked})
        counts[LIST_KIND[1]] += 1
        lakanaba[f"{dq4shopkey.ONE_SHOT.start + bits:02X}"] = picked
    # DQ5 롬에 코인 교환 목록이 없으면(목록을 바꿔 끼운 시험) 카지노를 옮기지 않는다
    coin = next((s for s in progress["shops"] if s.get("kind") == COIN_KIND and s.get("key") == COIN_KEY), None)
    picked, coins = [], []
    for k in range(dq4shop.CASINO_ROWS if coin else 0):
        at = dq4shop.CASINO_TABLE + 3 * k
        i = dq4shop.rd(prg, dq4shop.CODE_BANK, at)
        value = dq4shop.rd(prg, dq4shop.CODE_BANK, at + 1) | dq4shop.rd(prg, dq4shop.CODE_BANK, at + 2) << 8
        if _fold(names[i]) in items:
            picked.append(items[_fold(names[i])])
            coins.append(value)
        else:
            report["missing_items"].append(f"카지노 경품 {names[i]}")
    if coin:
        shops.append({"kind": COIN_KIND, "index": coin["index"], "key": COIN_KEY, "items": picked})
        report["casino"] = {"items": picked, "coins": coins, "coin_price": COIN_SALE_PRICE}
    report["keys"] = {f"{g:02X}/{first:02X}-{last:02X}": f"{k:02X}" for g, first, last, k in rows}
    report["event_sellers"] = {m: {f"{x},{y},{'night' if n else 'day'}": SERVICE[k] for (x, y, n), k in e.items()}
                               for m, e in events.items()}
    original = bytes(rom.u8(INN_TABLE + i) for i in range(INN_ENTRIES * 2))
    # New entries keep bit7 off: after sleeping the party lines up behind the hero ($0F36 -> $198E).
    table = original + b"".join(bytes((k, p)) for k, p in sorted(inns.items()))
    writes = [
        {"at": _cpu(inn_at), "hex": table.hex(" ").upper(), "note": "여관 1인 값 표(원래 21항목 + 새 키)"},
        {"at": _cpu(INN_BANK_OPERAND), "hex": f"{inn_at >> 16:02X}", "orig": "04", "note": "여관 표 뱅크(DB)"},
        {"at": _cpu(INN_ADDR_OPERAND), "hex": f"{inn_at & 0xFF:02X} {inn_at >> 8 & 0xFF:02X}", "orig": "6D FD",
         "note": "여관 표 주소"},
        *dq4shopkey.writes(key_at, rows, ONE_SHOT_AT),
        *dq4itemport.writes(rom, prg, prices),
    ]
    if coin:
        writes += [
            {"at": _cpu(COIN_PRICES), "hex": b"".join(v.to_bytes(3, "little") for v in coins).hex(" ").upper(),
             "orig": bytes(rom.u8(COIN_PRICES + k) for k in range(3 * len(coins))).hex(" ").upper(),
             "note": "카지노 경품 코인 값(FC 04/01)"},
            {"at": _cpu(COIN_SALE), "hex": f"{COIN_SALE_PRICE:02X}", "orig": f"{COIN_SALE_ORIG:02X}",
             "note": "코인 한 장 값(FC 3장)"}]
        arena_w, report["arena"] = arena_writes(rom, prg)
        writes += arena_w
    report["prices"] = {f"{i:02X} {dq4itemport.fc_name(rom, i)}": p
                        for i, p in sorted(prices.items())}
    return services, shops, writes, report


def arena(rom, prg):
    """(DQ5 시합 표에 둘 [(DQ5 몬스터, 배율) ×1~4], 빠진 FC 시합 [(순번, 빠진 FC 몬스터)])."""
    import dq4monport
    numbers = dq4monport.field_numbers()

    def fc(a):
        return prg[FC_ARENA_BANK * 0x4000 + a - 0x8000]
    picked, skipped = [], []
    for k in range(fc(FC_ARENA_COUNTS + FC_ARENA_CHAPTER)):
        row = [fc(FC_ARENA_TABLE + 8 * k + i) for i in range(8)]
        slots = [(m, row[4 + i]) for i, m in enumerate(row[:4]) if m != 0xFF]
        # LATER(조우에 아직 없어 NDS 그림을 넣지 않은 번호)는 DQ5 의 같은 이름 몬스터 그림 그대로라 시합에 써도 된다
        missing = [m for m, _ in slots if m not in numbers]
        if k in ARENA_WIDE:
            skipped.append((k, []))
            continue
        if missing:
            skipped.append((k, missing))
            continue
        picked.append([(numbers[m], odds) for m, odds in slots])
    return picked, skipped


def arena_writes(rom, prg):
    picked, skipped = arena(rom, prg)
    table = b"".join(bytes(b for m, odds in match for b in (m, odds)).ljust(8, b"\xFF") for match in picked)
    levels = bytes(len(picked)) + b"\xFF" * (ARENA_SIZE - len(picked))
    orig = lambda at, n: bytes(rom.u8(at + k) for k in range(n)).hex(" ").upper()
    writes = [{"at": _cpu(ARENA_MATCHES), "hex": table.hex(" ").upper(), "orig": orig(ARENA_MATCHES, len(table)),
               "note": "격투장 시합 표(FC 3장 18:$ADBA)"},
              {"at": _cpu(ARENA_LEVELS), "hex": levels.hex(" ").upper(), "orig": orig(ARENA_LEVELS, ARENA_SIZE),
               "note": "격투장 시합 레벨 문턱(옮긴 시합만)"}]
    return writes, {"matches": [[f"{m:02X}x{o}" for m, o in match] for match in picked],
                    "skipped": [f"FC {k}: " + (" ".join(f"{m:02X}" for m in ms) or "폭") for k, ms in skipped]}


def _dump_progress(dq5_path):
    import tempfile
    import dq4buildcache
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "progress.json"
        dq4buildcache.run(DQ5_TOOLS / "dq5progresswrite.py", dq5_path, "dump", "-o", out)
        return out.read_text(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--inn-at", default="3C:F000")
    ap.add_argument("--key-at", default="3C:FE00")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    inn_at, key_at = (int(a.split(":")[0], 16) << 16 | int(a.split(":")[1], 16) for a in (args.inn_at, args.key_at))
    services, shops, writes, report = port(args.dq5, args.dq4, inn_at, key_at)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({**report, "services": {m: {f"{x},{y},{'night' if n else 'day'}": k for (x, y, n), k in s.items()}
                                             for m, s in services.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
