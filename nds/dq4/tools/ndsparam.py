"""NDS DQ4 PARAM/*.dat 표(몬스터·가게·メダル·보물·동료 대화)와 SCRIPT 의 메시지 참조. 형식은 nds/dq4/docs/param-format.md.

PARAM 파일은 모두 머리 4바이트(파일마다 다른 값) 뒤에 고정 길이 레코드가 이어진다.
FC 쪽 이름·값은 dq4 트랙의 fc/dq4/tools/dq4data.py·dq4shop.py 를 읽기만 한다.

사용:
  python nds/dq4/tools/ndsparam.py monsters JPROOT [FCROM]   몬스터 표(60바이트). FC 를 주면 이름·능력치로 짝을 찾아 가른다
  python nds/dq4/tools/ndsparam.py actions JPROOT [N...]     행동 표(ARM9, 0x48바이트): 효과, 거는 상태 번호, 내성 칸, 등급, 문장
  python nds/dq4/tools/ndsparam.py items JPROOT FCROM        아이템 번호를 FC ID 와 맞대고 「같음·표기만 다름·바뀜·새로 생김」을 가른다
  python nds/dq4/tools/ndsparam.py shops JPROOT [FCROM]      가게 표(ARM9 안, 208바이트)와 맵. FC 를 주면 품목이 가장 많이 겹치는 FC 장소
  python nds/dq4/tools/ndsparam.py casino JPROOT FCROM       카지노·メダル 경품을 FC 와 나란히
  python nds/dq4/tools/ndsparam.py chests JPROOT MAP...      맵의 얻는 물건 표(param_item_<맵>.dat, 24바이트)
  python nds/dq4/tools/ndsparam.py talk JPROOT [장]          동료 대화 표: 맵, 말하는 인물, 메시지 번호+줄 수, 조건, 첫 문장
  python nds/dq4/tools/ndsparam.py scripts JPROOT [B0 B1]    대사 파일 bB0~bB1 을 부르는 SCRIPT/<맵>.bin 과 그 횟수
JPROOT 는 `krpatch nds unpack` 으로 푼 일본판 롬 폴더, FCROM 은 rom/dq4.nes.
"""
import collections
import importlib
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ndstext  # noqa: E402

SMALL = str.maketrans('ァィゥェォッャュョヮ', 'アイウエオツヤユヨワ')
SHOP_SLOTS = (('무기', 0, 6), ('방어구', 6, 12), ('도구', 12, 18), ('카지노', 18, 24), ('다른 여관 값', 24, 26),
              ('밤 무기', 26, 32), ('특별', 32, 50))


def param(root, name):
    return open(os.path.join(root, 'data', 'data', 'PARAM', name + '.dat'), 'rb').read()


def records(data, size):
    return [data[o:o + size] for o in range(4, len(data) - size + 1, size)]


def names(root, table):
    return {n: ndstext.label(s) for n, s in ndstext.read(os.path.join(ndstext.mess(root, 'ja'), table + '.mpt'))}


def key(s):
    """FC·DS 이름 비교 키: 히라가나·가타카나와 작은 글자 차이(FC 폰트에 작은 가나가 없음)를 무시한다."""
    return ndstext.kana_key(s).translate(SMALL).replace('ヴ', 'ウ')


def fc_tools():
    root = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
    sys.path.insert(0, os.path.join(root, 'fc', 'dq4', 'tools'))
    from kr_patch.fc import ines
    return importlib.import_module('dq4data'), ines


def fc_prg(rom):
    dq4data, ines = fc_tools()
    return dq4data, ines.prg(open(rom, 'rb').read())


# 몬스터

def monster_table(root):
    """param_monster_monster.dat: 머리 4바이트 + 60바이트 레코드 315개. 이름은 b1002000 의 +00 번."""
    nm = names(root, 'b1002000')
    out = []
    for r in records(param(root, 'param_monster_monster'), 60):
        num, lv, exp, mp, hp, atk, df, gold = struct.unpack_from('<8H', r)
        out.append({'num': num, 'name': nm.get(num, ''), 'lv': lv, 'exp': exp, 'mp': mp, 'hp': hp, 'atk': atk,
                    'df': df, 'gold': gold, 'agi': r[0x1E], 'drop': struct.unpack_from('<H', r, 0x10)[0],
                    'drop_rate': r[0x1F], 'acts': struct.unpack_from('<6H', r, 0x12), 'ai': r[0x20],
                    'count': r[0x22], 'crit': r[0x24], 'start': r[0x26], 'select': r[0x27], 'raw': r})
    return out


def fc_monsters(rom):
    dq4data, prg = fc_prg(rom)
    out = []
    for i, nm, _exp, _hp, r in dq4data.monsters(prg):
        f = dq4data.monster_fields(r)
        out.append({'id': i, 'name': nm, 'exp': f['exp'], 'gold': f['gold'], 'hp': f['hp'], 'mp': f['mp'],
                    'atk': f['atk'], 'df': f['def'], 'agi': f['agi']})
    return out


STATS = ('exp', 'gold', 'hp', 'mp', 'atk', 'df', 'agi')
STAT_NAMES = dict(zip(STATS, ('경험치', '골드', 'HP', 'MP', '공격', '수비', '민첩')))


def classify_monsters(ds, fc):
    """DS 레코드마다 (판정, FC 짝). 이름이 같으면 능력치를 견주고, 이름이 없으면 경험치·HP·공격·수비가 같은 FC 몬스터를 찾는다."""
    by_name = collections.defaultdict(list)
    for m in fc:
        by_name[key(m['name'])].append(m)
    named = {key(m['name']) for m in ds if m['name']}
    out = []
    for m in ds:
        if not m['name']:
            out.append(('이름 없음', None))
            continue
        cands = by_name.get(key(m['name']))
        if cands:
            same = [c for c in cands if all(c[s] == m[s] for s in STATS)]
            if same:
                out.append(('같음', same[0]))
            else:
                c = min(cands, key=lambda c: sum(c[s] != m[s] for s in STATS))
                diff = ', '.join(f'{STAT_NAMES[s]} {c[s]}→{m[s]}' for s in STATS if c[s] != m[s])
                out.append((f'능력치 다름({diff})', c))
            continue
        twin = [c for c in fc if key(c['name']) not in named and c['hp']
                and (c['exp'], c['hp'], c['atk'], c['df']) == (m['exp'], m['hp'], m['atk'], m['df'])]
        out.append(('이름만 다름', twin[0]) if twin else ('새로 생김', None))
    return out


def cmd_monsters(root, rom=None):
    ds = monster_table(root)
    marks = classify_monsters(ds, fc_monsters(rom)) if rom else [('', None)] * len(ds)
    items = ds_items(root)
    print('| 레코드 | 번호 | 이름 | Lv | 경험치 | 골드 | HP | MP | 공격 | 수비 | 민첩 | 드롭 | 행동 | FC | 판정 |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for k, (m, (mark, f)) in enumerate(zip(ds, marks)):
        fcs = f"{f['id']:02X} {f['name']}" if f else ''
        print(f"| {k} | {m['num']} | {m['name']} | {m['lv']} | {m['exp']} | {m['gold']} | {m['hp']} | {m['mp']} | "
              f"{m['atk']} | {m['df']} | {m['agi']} | {items.get(m['drop'], '')} {m['drop_rate']} | "
              f"{' '.join(f'{a:X}' for a in m['acts'])} | {fcs} | {mark} |")
    if rom:
        print('\n' + ' '.join(f'{k} {v}' for k, v in collections.Counter(mk.split('(')[0] for mk, _ in marks).most_common()))


# 행동(주문·특기·몬스터 행동·도구 사용) 표

# ARM9 안의 0x48바이트 레코드. 레코드 n 이 행동 번호 n(+24 도 n). 주문 n 의 이름은 b1003000 의 n−1 번이고,
# 몬스터 표 +12 의 여섯 칸과 아이템 표 +0A(つかう)도 같은 번호를 쓴다.
ACTION_TABLE, ACTION_COUNT = 0x020A8294, 595
# +37 내성 갈래 → 몬스터 내성 2비트 칸(1부터, 0 은 내성 없음). 0x020151F4 의 갈래 표
RESIST_SLOT = (3, 2, 1, 6, 5, 4, 9, 15, 10, 7, 13, 8, 12, 11, 14, 0x18, 0x19, 0x15, 0x1B, 0x1A, 0x1C, 0x17, 0x16)
RESIST_NAMES = {1: 'イオ', 2: 'ギラ', 3: 'メラ', 4: 'デイン', 5: 'バギ', 6: 'ヒャド', 7: 'マヌーサ', 8: 'ラリホー',
                9: 'ザキ', 10: 'ニフラム', 11: 'マホトラ', 12: 'マホトーン', 13: 'メダパニ', 14: 'ルカニ',
                15: 'メガンテ', 0x15: 'どくのいき', 0x18: '불 숨결', 0x19: '찬 숨결', 0x1A: '돌', 0x1B: 'やけつくいき'}
# +38 효과 → 상태 칸(0x0201E494). 이 밖의 효과(피해·회복 등)는 상태 칸을 켜지 않음
EFFECT_STATUS = {**{e: e for e in range(8, 0x17)}, 0x18: 0x18, 0x19: 0x19, 0x1A: 0x1A, 0x1C: 0x0B, 0x27: 0x1B, 0x29: 0x1E}


def action_table(root):
    with open(os.path.join(root, 'arm9.bin'), 'rb') as fh:
        d = fh.read()
    out = []
    for n in range(ACTION_COUNT):
        r = d[ACTION_TABLE - 0x02000000 + 0x48 * n:][:0x48]
        effect = 0x27 if n in (0x4B, 0x9B, 0x9C) else r[0x38]
        cat = r[0x37]
        out.append({'num': n, 'valid': struct.unpack_from('<H', r, 0x24)[0] == n, 'msgs': struct.unpack_from('<7I', r),
                    'effect': effect, 'cat': cat, 'slot': RESIST_SLOT[cat] if cat < len(RESIST_SLOT) else 0,
                    'grade': (r[0x43] >> 2) & 7, 'status': EFFECT_STATUS.get(effect)})
    return out


def cmd_actions(root, nums):
    spells = names(root, 'b1003000')
    msgs = ndstext.messages(root)
    for a in action_table(root):
        if (nums and a['num'] not in nums) or (not nums and not a['valid']):
            continue
        slot = f"{a['slot']:X}({RESIST_NAMES.get(a['slot'], '?')})" if a['slot'] else '-'
        st = f"{a['status']:02X}" if a['status'] is not None else '-'
        text = next((msgs[m] for m in a['msgs'] if m in msgs and m != 801080), '').replace('\n', '/')[:40]
        print(f"{a['num']}\t{spells.get(a['num'] - 1, '')}\t효과 {a['effect']:02X}\t상태 {st}\t내성 {slot}\t"
              f"등급 {a['grade']}\t{text}")


# 아이템·가게

# 게임이 쓰는 가게 표는 ARM9 안의 것(PARAM 파일은 second 레코드 30~35 가 없는 사본). (ARM9 주소, 레코드 수)
SHOP_TABLES = {'first': (0x020945F8, 19), 'second': (0x02099A30, 36)}
# 맵 이름 앞 두 글자(ss 는 셋째 글자까지) → 레코드(0x0201D2BC·0x0200CCCC·0x0200CB10, 목록에 없으면 0)
SHOP_MAPS = {'first': ['ma', 'mb', 'mc', 'md', 'me', 'sb', 'hc', 'cc', 'tb', 'mf', 'mg', 'cd', 'mh', 'mi', 'ce', 'mj', 'mk'],
             'second': ['hc', 'sb', 'cd', 'mf', 'se', 'mm', 'mn', 'mo', 'cg', 'mj', 'mk', 'mi', 'mh', 'hh', 'mb', 'mc', 'md', 'tb', 'ma', 'ha', 'mq', 'mp', 'ci', 'td', 'sh', 'ms', 'ck', 'sm', 'dp', 'mr', 'ss1', 'ss2', 'ss3', 'ss4', 'ss5']}


def shop_table(root):
    """가게 표: 208바이트 레코드. +2 여관 1인 값, +6 교회 종류, +8 부터 (아이템, 값) 50칸.
    표는 장 번호 4 이하면 first, 5 이상이면 second(0x020CE3EC)."""
    with open(os.path.join(root, 'arm9.bin'), 'rb') as fh:
        d = fh.read()
    out = []
    for f, (addr, n) in SHOP_TABLES.items():
        for k in range(n):
            r = d[addr - 0x02000000 + 208 * k:][:208]
            w = struct.unpack_from('<104H', r)
            slots = [(w[4 + 2 * j], w[5 + 2 * j]) for j in range(50)]
            maps = '그 밖' if not k else SHOP_MAPS[f][k - 1] if k <= len(SHOP_MAPS[f]) else '-'
            out.append({'file': f, 'idx': k, 'head': w[:4], 'slots': slots, 'maps': maps})
    return out


def medal_table(root):
    """param_map_medal.dat: 머리 4바이트 + (아이템, 메달 수) u16 쌍."""
    d = param(root, 'param_map_medal')
    return [struct.unpack_from('<2H', d, o) for o in range(4, len(d) - 3, 4)]


def ds_items(root):
    """DS 아이템 번호 n(가게·보물 표의 값) → 이름. 이름 표 b1000000 의 n−1 번."""
    return {n + 1: s for n, s in names(root, 'b1000000').items()}


def ds_prices(root):
    """가게 표에 나온 아이템 값(G). 카지노 칸은 코인이라 뺀다.
    ARM9 에만 있는 second 30~35(mr·이민 마을)는 같은 값의 품목을 늘려 FC 짝짓기를 흐리므로 뺀다."""
    out = {}
    for s in shop_table(root):
        if s['file'] == 'second' and s['idx'] >= 30:
            continue
        for j, (it, v) in enumerate(s['slots']):
            if it and not 18 <= j < 24:
                out.setdefault(it, v)
    return out


def classify_items(root, rom):
    """(DS 번호, DS 이름, FC ID, FC 이름, 판정). FC ID 0~35 는 DS 1~36, 그 뒤는 DS 에 무기 6개가 끼어 번호가 밀린다."""
    dq4data, prg = fc_prg(rom)
    fc = {i: (nm, price) for i, nm, _pw, price, _f in dq4data.items(prg)}
    ds = ds_items(root)
    dsp = ds_prices(root)
    by_key = {key(v): n for n, v in ds.items()}
    used = set()
    rows = []
    for i, (nm, price) in sorted(fc.items()):
        n = by_key.get(key(nm))
        if n:
            used.add(n)
            rows.append((n, ds[n], i, nm, price, '같음' if ds[n] == nm or key(ds[n]) == key(nm) else '표기만 다름'))
        else:
            rows.append((None, '', i, nm, price, '' if nm.strip() else 'FC 빈 칸'))
    # 이름이 안 맞는 FC 아이템은 같은 가게 칸(같은 값)에 선 DS 아이템과 짝짓는다
    for k, (n, _d, i, nm, price, mark) in enumerate(rows):
        if n is None:
            twin = [m for m in ds if m not in used and dsp.get(m) == price and price]
            if len(twin) == 1:
                used.add(twin[0])
                rows[k] = (twin[0], ds[twin[0]], i, nm, price, '바뀜(같은 자리·같은 값)')
            elif nm.strip():
                near = [m for m in ds if m not in used and edit1(key(ds[m]), key(nm))]
                if near:
                    used.add(near[0])
                    rows[k] = (near[0], ds[near[0]], i, nm, price, '표기만 다름')
                else:
                    rows[k] = (None, '', i, nm, price, 'DS 에 없음')
    fc_keys = {key(nm) for nm, _p in fc.values()}
    for n in sorted(set(ds) - used):
        if ds[n]:
            rows.append((n, ds[n], None, '', None, '같은 이름 다른 번호' if key(ds[n]) in fc_keys else '새로 생김'))
    return rows, dsp


def edit1(a, b):
    """한 글자만 다름(바꿈)."""
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


ITEM_TABLE, ITEM_SIZE, ITEM_COUNT = 0x02095594, 32, 162
ITEM_KINDS = {0: '도구', 1: '무기', 2: '방어구', 3: '장신구', 4: '장신구', 5: '장신구', 6: '장신구'}
# +14 장비 비트: 비트 n 이 인물 번호 n+1(ソロ, ソフィア, ライアン, …, マーニャ, ピサロ)
EQUIP_BITS = ('ソロ', 'ソフィア', 'ライアン', 'アリーナ', 'クリフト', 'ブライ', 'トルネコ', 'ミネア', 'マーニャ', 'ピサロ')


def item_table(root):
    """ARM9 0x02095594 부터 32바이트 레코드(아이템 n 은 + 32×(n−1)).
    +0 값, +2 팔 값, +6 강도, +10 아이템 번호, +12 종류, +14 장비 비트."""
    with open(os.path.join(root, 'arm9.bin'), 'rb') as fh:
        d = fh.read()
    out = {}
    for n in range(1, ITEM_COUNT + 1):
        r = d[ITEM_TABLE - 0x02000000 + (n - 1) * ITEM_SIZE:][:ITEM_SIZE]
        price, sell = struct.unpack_from('<HH', r, 0)
        equip = struct.unpack_from('<H', r, 0x14)[0]
        out[n] = {'no': r[0x10], 'kind': r[0x12], 'price': price, 'sell': sell, 'power': r[6], 'equip': equip,
                  'who': [nm for b, nm in enumerate(EQUIP_BITS) if equip >> b & 1], 'raw': r}
    return out


def cmd_items(root, rom):
    rows, _dsp = classify_items(root, rom)
    table = item_table(root)
    print('| DS 번호 | DS 이름 | 종류 | 강도 | DS 값 | 장비 | FC ID | FC 이름 | FC 값 | 판정 |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for n, d, i, nm, price, mark in sorted(rows, key=lambda r: (r[0] or 999, r[2] or 0)):
        fid = f'{i:02X}' if i is not None else ''
        t = table.get(n, {})
        kind = ITEM_KINDS.get(t.get('kind'), '') if t else ''
        who = '·'.join(t['who']) if t and t['kind'] else ''
        print(f"| {n or ''} | {d} | {kind} | {t.get('power', '')} | {t.get('price', '')} | {who} | {fid} | {nm.strip()} | "
              f"{price if price else ''} | {mark} |")
    print('\n' + ' '.join(f'{k} {v}' for k, v in collections.Counter(r[5] for r in rows).most_common()))


def fc_shop_output(rom):
    """FC dq4shop.py 의 가게 목록 출력(dq4 트랙 도구, 읽기만)."""
    root = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
    sys.path.insert(0, os.path.join(root, 'fc', 'dq4', 'tools'))
    import contextlib
    import io
    dq4shop = importlib.import_module('dq4shop')
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = ['dq4shop.py', rom]
    try:
        with contextlib.redirect_stdout(buf):
            dq4shop.main()
    finally:
        sys.argv = argv
    return buf.getvalue().splitlines()


def fc_shops(root, rom):
    """FC 장소(그룹/순번)마다 무기·방어구·도구 품목(DS 번호로 바꿈)과 여관 1인 값."""
    rows, _dsp = classify_items(root, rom)
    to_ds = {r[2]: r[0] for r in rows if r[0] and r[2] is not None}
    shops = collections.defaultdict(lambda: {'무기': set(), '방어구': set(), '도구': set()})
    inn, kind = {}, None
    for line in fc_shop_output(rom):
        if line.startswith('# '):
            kind = line.split()[1]
            continue
        m = re.match(r'([0-9A-F]{2}/[0-9A-F]{2})\s+(.*)', line)
        if m and kind in shops.default_factory():
            for it in re.findall(r'\b([0-9A-F]{2}) \S+ \d+G', m.group(2)):
                shops[m.group(1)][kind].add(to_ds.get(int(it, 16)))
        if kind == '여관':
            inn.update((g, int(v)) for g, v in re.findall(r'([0-9A-F]{2}/[0-9A-F]{2})=(\d+)', line))
    return shops, inn


def match_shop(s, shops):
    """DS 가게 레코드와 품목이 가장 많이 겹치는 FC 장소와 겹침 비율."""
    mine = {'무기': {i for i, _v in s['slots'][0:6] if i}, '방어구': {i for i, _v in s['slots'][6:12] if i},
            '도구': {i for i, _v in s['slots'][12:18] if i}}
    if not any(mine.values()):
        return None, 0
    best = max(((sum(len(mine[k] & f[k]) for k in mine) / sum(len(mine[k] | f[k]) for k in mine), g)
                for g, f in shops.items()))
    return best[1], best[0]


def cmd_shops(root, rom=None):
    it = ds_items(root)
    shops, inn = fc_shops(root, rom) if rom else ({}, {})
    for s in shop_table(root):
        h = s['head']
        parts = []
        for label, a, b in SHOP_SLOTS:
            got = [f'{it.get(i, i)} {v}' for i, v in s['slots'][a:b] if i or v]
            if got:
                parts.append(f'{label}: ' + ', '.join(got))
        fc = ''
        if shops:
            g, score = match_shop(s, shops)
            fc = f'FC {g} 겹침 {score:.2f} 여관 {inn.get(g, "-")}  ' if g else 'FC -  '
        print(f"{s['file']}[{s['idx']:2d}] {s['maps']} 여관 {h[1]}G 교회 {h[3]}  {fc}" + ' / '.join(parts))


def fc_casino(rom):
    """FC dq4shop.py 의 카지노(04/01)·メダル 왕(22/00) 줄."""
    return [line for line in fc_shop_output(rom) if line.startswith(('04/01', '22/00'))]


def cmd_casino(root, rom):
    it = ds_items(root)
    for s in shop_table(root):
        c = [f'{it.get(i, i)} {v}' for i, v in s['slots'][18:24] if i]
        if c:
            print(f"DS 카지노 {s['file']}[{s['idx']}]: " + ', '.join(c))
    print('DS メダル: ' + ', '.join(f'{it.get(i, i)} {n}' for i, n in medal_table(root)))
    for line in fc_casino(rom):
        print('FC ' + line)


# 얻는 물건 종류 → 같은 번호의 FMAP 배치(+0x2C)가 쓰는 모델 이름(맵 전체 통계)
CHEST_KINDS = {0x00: '문·침대 등(물건 없음)', 0x01: '책장(hondana)', 0x02: '게시판(msgkb)', 0x04: '무덤(haka)',
               0x07: '보물상자(tbox)', 0x09: '슬롯머신', 0x0B: '마신상', 0x0D: '석상(mgmzou)', 0x11: '서랍(hikidashi)',
               0x13: '경대(kyodai)', 0x14: '칼 장식(ken)', 0x15: '도끼 장식(ono)', 0x16: '방패 장식(tate)',
               0x17: '갑옷 장식(yoroi)', 0x18: '갑옷 장식(yoroi)', 0x1A: '찬장(bkdana)', 0x1B: '술 선반(sakadana)',
               0x1C: '옷장(tansu)', 0x1F: '옷장(tansu)', 0x22: '그림(e)', 0x25: '통(taru)', 0x27: '항아리(tubo)'}


def cmd_chests(root, maps):
    it = ds_items(root)
    for m in maps:
        d = param(root, f'param_item_{m}')
        print(m)
        for r in records(d, 24):
            num, item, gold = struct.unpack_from('<3H', r, 4)
            flag, kind, seq = struct.unpack_from('<HBB', r, 0x12)
            if item or gold:
                what = it.get(item, f'#{item}') if item else f'{gold}G'
                print(f'  {num:5d} 칸 {seq:2d} 종류 {kind:02X}({CHEST_KINDS.get(kind, "?")}) {what}  플래그 {flag}')


# 동료 대화

# 조건 종류(+1E·+1F·+20)와 값(+04·+08·+0C). ARM9 0x0203694C 의 갈래 표
TALK_CODES = {1: '이야기 플래그 #{} 켜짐', 2: '이야기 플래그 #{} 꺼짐', 3: '플래그B #{} 켜짐', 4: '플래그B #{} 꺼짐',
              5: '플래그C #{} 켜짐', 6: '플래그C #{} 꺼짐', 7: '아이템 {} 가짐', 8: '아이템 {} 없음',
              9: '선두 인물 {}', 10: '선두 +50 = 0', 11: '선두 +50 = 1', 12: '이동 값(0x020B91C8) = {}',
              13: 'スコット 고용 경과 {}', 14: 'ロレンス 고용 경과 {}', 15: '변장 중',
              16: '변장 아님', 17: '변장 아님', 18: '방금 얻은 열쇠 아이템 {}'}
# 일행 칸 조건: (바이트, 비트 자리, 인물 번호들). 값 1~5 는 TALK_SLOT_MODES
TALK_SLOTS = ((0x22, 3, '주인공'), (0x23, 0, 'ソロ'), (0x23, 3, 'ソフィア'), (0x24, 0, 'ライアン'),
              (0x24, 3, 'アリーナ'), (0x25, 0, 'クリフト'), (0x25, 3, 'ブライ'), (0x26, 0, 'トルネコ'),
              (0x26, 3, 'ミネア'), (0x27, 0, 'マーニャ'), (0x27, 3, 'ピサロ'), (0x28, 0, 'パノン'))
TALK_SLOT_MODES = {1: '걷는 줄·살아 있음', 2: '걷는 줄 밖이거나 쓰러짐', 3: '일행에 없거나 걷는 줄 밖·쓰러짐',
                   4: '살아 있음', 5: '걷는 줄·쓰러짐'}
TIMES = {2: '낮', 4: '밤'}


def talk_fields(r):
    return {'v0': struct.unpack_from('<I', r, 0)[0], 'vals': struct.unpack_from('<3I', r, 4),
            'msg': struct.unpack_from('<I', r, 0x10)[0], 'story': struct.unpack_from('<2H', r, 0x14),
            'map': struct.unpack_from('<H', r, 0x18)[0], 'count': struct.unpack_from('<H', r, 0x1A)[0],
            'place': (r[0x1C], r[0x1D]), 'codes': (r[0x1E], r[0x1F], r[0x20]), 'who': r[0x21],
            'time': r[0x22] & 7, 'prio': (r[0x28] & 0x78) >> 3,
            'slots': [(name, (r[off] >> sh) & 7) for off, sh, name in TALK_SLOTS if (r[off] >> sh) & 7]}


def talk_conditions(f):
    """ARM9 0x02036530 이 보는 차례대로 조건을 말로. 이야기 플래그는 RAM 0x020CE7DC 의 비트(낮은 비트부터)."""
    on, off = f['story']
    out = [f'#{on} 켜짐' + ('' if off == 0xFFFF else f' & #{off} 꺼짐')]
    if f['time']:
        out.append(TIMES.get(f['time'], f"시간 {f['time']}"))
    if f['place'][0] != 0xFF:
        out.append('직전 대화 값 ' + '/'.join(str(x) for x in f['place'] if x != 0xFF))
    if f['v0']:
        out.append(f"최근 이벤트 값 {f['v0']}")
    for code, v in zip(f['codes'], f['vals']):
        if not code:
            break
        out.append(TALK_CODES.get(code, f'종류 {code} 값 {{}}').format(v))
    out += [f'{name} {TALK_SLOT_MODES.get(m, m)}' for name, m in f['slots']]
    return ' & '.join(out)


def cmd_talk(root, chapters):
    maps = map_list(root)
    people = names(root, 'b1001000')
    msgs = ndstext.messages(root)
    for ch in chapters:
        for k, r in enumerate(records(param(root, f'param_player_talk{ch}'), 44)):
            f = talk_fields(r)
            mp = maps[f['map']] if f['map'] < len(maps) else f"#{f['map']}"
            who = people.get(f['who'] - 1, f['who'])
            text = msgs.get(f['msg'], '-').replace('\n', '/')
            print(f"{ch}\t{k}\t{mp}\t우선 {f['prio']}\t{who}\t{f['msg']}+{f['count']}\t{talk_conditions(f)}\t{text}")


def map_list(root):
    path = os.path.join(root, 'data', 'data', 'MAP', '_list.txt')
    return [line.strip().split(',')[2] for line in open(path, encoding='shift_jis') if line.count(',') >= 2]


# SCRIPT 의 메시지 참조

def script_refs(root):
    """SCRIPT/<맵>.bin 의 4바이트 정렬 u32 가운데 대사 파일의 번호 범위(MPT0 머리 +08~+0C)에 드는 값을 파일별로 센다."""
    ranges = []
    mdir = ndstext.mess(root, 'ja')
    for f in sorted(os.listdir(mdir)):
        if f.endswith('.mpt'):
            with open(os.path.join(mdir, f), 'rb') as fh:
                first, last = struct.unpack_from('<2I', fh.read(16), 8)
            ranges.append((first, last, int(f[1:5])))
    base = os.path.join(root, 'data', 'data', 'SCRIPT')
    ref = collections.defaultdict(collections.Counter)
    for f in sorted(os.listdir(base)):
        with open(os.path.join(base, f), 'rb') as fh:
            d = fh.read()
        for v in struct.unpack_from(f'<{len(d) // 4}I', d):
            if 100000 <= v < 1100000:
                for first, last, b in ranges:
                    if first <= v <= last:
                        ref[b][f[:-4]] += 1
                        break
    return ref


def cmd_scripts(root, lo=0, hi=9999):
    ref = script_refs(root)
    msgs = os.path.join(ndstext.mess(root, 'ja'))
    for b in range(lo, hi + 1):
        p = os.path.join(msgs, f'b{b:04d}000.mpt')
        if os.path.exists(p):
            print(f'b{b:04d}\t{len(ndstext.read(p))}\t' + ' '.join(f'{m}:{n}' for m, n in ref[b].most_common()))


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    cmd, root, rest = argv[0], argv[1], argv[2:]
    if cmd == 'monsters':
        cmd_monsters(root, rest[0] if rest else None)
    elif cmd == 'actions':
        cmd_actions(root, {int(a, 0) for a in rest})
    elif cmd == 'items':
        cmd_items(root, rest[0])
    elif cmd == 'shops':
        cmd_shops(root, rest[0] if rest else None)
    elif cmd == 'casino':
        cmd_casino(root, rest[0])
    elif cmd == 'chests':
        cmd_chests(root, rest)
    elif cmd == 'talk':
        cmd_talk(root, [int(a) for a in rest] or range(1, 7))
    elif cmd == 'scripts':
        cmd_scripts(root, *(int(a) for a in rest[:2]))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
