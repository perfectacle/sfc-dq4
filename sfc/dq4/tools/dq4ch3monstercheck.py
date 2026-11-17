"""3장 몬스터 검사(MesenCE 헤드리스): 3장 롬의 몬스터 능력치·구역·밤 칸·3장 전용 전투 뒤 물건이 FC 대로인지.
형식 문서 sfc/dq4/docs/dq4-ch3-monsters-format.md.

롬 바이트(에뮬레이터 없이):
  records  3장 구역(dq4fieldencounter.CH3_ZONES)에 나오는 FC 몬스터 19종의 DQ5 번호(dq4fieldencounter.MONSTERS) 레코드가 FC 값
           (dq4monport.fc_entry: HP·MP·민첩·공격·수비·경험치·금화·행동 여섯·내성·드롭·드롭률)과 같고, 이름이 전투 글 이름
           표·창 이름 표에 있다. records-ch1 은 1장 구역(필드 04~06, 던전 40~43) 14종의 같은 대조
  zones    3장 구역의 DQ5 구역 레코드·고정 무리가 dq4fieldencounter.docs 대로
  table    훅의 3장 전용 표(문턱 16칸·물건 16칸)가 FC 12:$928E·$929E 와 그 물건의 DQ5 짝
장면(서장 끝 출발 상태에서 dq5warp.lua FIELD 로 3장 필드 구역에 서고 3장 flag 를 켬):
  zone-ZZ-day·night  조우 계수를 FF 로 덮어 걸음마다 싸우게 하고 시각($075E)을 낮·밤으로 묶어 걷는다. 첫 무리의 칸 무게
           (23:E918 의 $00~$0A)가 그 구역 레코드 무게에서 FC 첫 무리 마스크로 빠진 칸을 0 으로 한 것과 같고, 둘째 종의
           무게(23:EAC1 의 $00~$04)도 그렇다. 싸운 무리는 그 구역에서 그 때 고를 수 있는 몬스터뿐(낮의 메라 고스트 없음)
  drop-LL  무리를 버블 슬라임 하나(HP 1)로 덮고 걸으며 이겨, 이길 때마다 훅이 굴린 시작 칸·rand(256)·그때 레벨로
           dq4fieldencounter.drop_roll 이 낸 칸과 훅이 얻은 칸(없음 포함)이 같고, 얻었으면 25:89B3 이 그 물건을 받는다.
           LL 은 처음 톨네코 레벨(FC 실측의 01·28·63, 16진). 이겨 오르면 오른 레벨로 견준다. 얻은 물건은 끝에 가진
           물건(7E:2056~)에 그만큼 있어야 한다
  drop-sure  문턱 16칸을 FF 로 덮은 롬 사본: 이길 때마다 시작 칸의 물건을 얻는다
  drop-off  3장 flag 를 끄면 훅이 표를 굴리지 않는다(원래 떨어뜨림 판정)
  merchant-roll  롬 그대로 걸음마다 싸우게 하고, 조우마다 rand(10) 이 0 일 때만 떠돌이 상인 갈래로 간다
  merchant-shop·inn·innnight  rand(10) 을 늘 0 으로(·여관 문턱을 00·FF 로) 덮은 롬 사본: 싸우지 않고 도구점(06:E01F)에서
           약초를 산 만큼 금화가 줄고 가방에 들거나, 여관(06:E384)에서 1인 10G 를 내고 HP 가 차며 필드에 남는다. 첫 메시지가
           도구점 인사 000·여관 낮 070·밤 071(FC 「こんな よふけまで」)이고, 깬 뒤 필드를 다시 그린다(01:A04B, 실내 다시
           부르기 00:C6D8 없음)
  merchant-off  3장 flag 없이는 rand(10) 을 덮어도 상인 갈래에 오지 않고 싸운다

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch3monstercheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3monsters
결과: OUT/results.json.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / 'dq5' / 'tools'
FC_TOOLS = TOOLS.parents[2] / 'fc' / 'dq4' / 'tools'
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4battlecheck  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4encounter  # noqa: E402
import dq4fieldencounter  # noqa: E402
import dq4fieldencountercheck as fec  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4groupbuild  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4monport  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# FC 구역 → 서는 구역 지도 칸(dq4fieldencountercheck.CH3_ZONES: 3장 일행이 걷는 범위 안)
CELLS = {0x14: (0x06, 0x02), 0x15: (0x06, 0x04), 0x16: (0x05, 0x05), 0x17: (0x07, 0x05)}
CLOCK = {'day': '7E075E=50 7E075F=00', 'night': '7E075E=F8 7E075F=00'}
DELAYS = (0, 9)
FIRST, SECOND = '23E918', '23EAC1'          # 첫 무리·둘째 종 칸 무게를 다 읽은 곳(LDA $0F)
WEIGHTS = ','.join(f'7E{k:04X}' for k in range(0, 12, 2))
FIGHT_EXITS = fec.EXITS
DROP_MONSTER = dq4monport.CH3[0x0A][0]       # 버블 슬라임
DROP_LEVELS = (0x01, 0x28, 0x63)
SURE = 0xFF                                  # drop-sure 가 문턱 16칸을 덮는 값: rand(256) 이 FF 일 때만 못 얻음
GIVE = '2589B3'                              # STA $10F7: 떨어뜨린 물건
BAG, BAG_SLOTS = 0x2056, 12                  # 일행 기록 0(7E:2040)의 가진 물건 +16~
FIXED_GROUPS = 0x23B04B
# 떠돌이 상인 장면: 장면마다 A 를 누르는 횟수(가게는 「사기」·약초·개수·확인, 여관은 한 밤), 시작 금화·HP
MERCHANT_PRESSES = {'shop': 25, 'inn': 12, 'innnight': 12, 'roll': 20, 'off': 12}
# 첫 메시지(DQ5 가게·여관 메시지 번호, 글은 FC 공용 대사 dq4sysmsg): 도구점 인사, 여관 낮·밤 인사
MERCHANT_GREET = {'shop': 0x000, 'day': 0x070, 'night': 0x071}
NIGHT_ONCE = ';075E=F8;075F=00'               # 밤으로 한 번만 둠(깬 뒤 아침이 되게)
MESSAGE_PC = '248157'                         # 메시지 띄우기(A = 번호)
RELOAD_PC, REDRAW_PC = '00C6D8', '01A04B'     # 실내 맵 다시 부르기, 필드 다시 그리기
# 대화가 다 끝나게(가게는 금화를 먼저 빼고 「자, 여기요」 뒤에 물건을 넣음) B 로 닫고 기다림
MERCHANT_CLOSE = ','.join(['wait:90,b:2'] * 4) + ',wait:120'
# merchant-roll 은 걷기·전투(주인공 HP 고정)를 되풀이해 rand(10) 을 여러 번 본다
MERCHANT_ROUNDS = 7
MERCHANT_FRAMES = 4000
MERCHANT_GOLD = 1000
MERCHANT_SET = '2019=E8;201A=03;201B=00;2042=05'
MERCHANT_ITEMS = ((0xA1, 8),)                # 도구점 첫 줄 やくそう(DQ5 A1, 8G)
MERCHANT_INN_PRICE = 10
SHOP_PC, INN_PC = '06E01F', '06E384'         # 특수 기능 도구점·여관(06:DBD2 의 02·06)
BATTLE_PC = '01860D'                         # 걸음 전투가 걸림(dq4battlecheck)                      # 고정 무리 6바이트씩(dq5encounterwrite fixed_groups)
# 한 걸음에 전투가 하나 걸리고(조우를 덮음) A 로 이기고 메시지를 넘긴 뒤, B 로 필드에서 열린 명령 창을 닫고 다음 걸음
FIGHT = ','.join(['a:2,wait:14'] * 26 + ['b:2,wait:10'] * 6)
DROP_WALK = 'idle:16,' + ','.join(f'{d}:12,{FIGHT}' for d in ('right', 'left') * 4)


def lorom(a):
    return (a >> 16 & 0x7F) * 0x8000 + (a & 0x7FFF)


# FC 1장 구역: 필드 04~06(バトランド·イムル 둘레)과 던전 40~43(古井戸の底·탑·동굴·우물 아래)
CH1_FIELD, CH1_DUNGEON = (0x04, 0x05, 0x06), (0x40, 0x41, 0x42, 0x43)


def zone_species(prg, field, dungeon):
    """FC 구역에서 낮·밤(던전은 던전 마스크)에 나올 수 있는 FC 몬스터(dq4encounter.zone_monsters, 편성 포함)."""
    out = set()
    for z in field:
        out |= dq4encounter.zone_monsters(prg, z, 'day') | dq4encounter.zone_monsters(prg, z, 'night')
    for z in dungeon:
        out |= dq4encounter.zone_monsters(prg, z, 'dungeon')
    return sorted(out)


def chapter3_species(prg):
    return zone_species(prg, dq4fieldencounter.CH3_FIELD, dq4fieldencounter.CH3_DUNGEON)


def chapter1_species(prg):
    return zone_species(prg, CH1_FIELD, CH1_DUNGEON)


def record_problems(data, prg, dq5, species=None):
    """species(없으면 3장 구역 몬스터)의 레코드가 FC 값과 다른 곳."""
    import dq5tables
    table = dq5tables.TABLES['monsters']
    drop_item = dq4monport.drop_items(prg, dq5)
    species = chapter3_species(prg) if species is None else species
    out, rows = [], {}
    for fc in sorted(species):
        m = dq4fieldencounter.MONSTERS[fc]
        got = dq5tables.decode(table, None, data, m)
        want = dq4monport.fc_entry(prg, fc, drop_item)
        diff = {k: (got[k], v) for k, v in want.items() if k != '내성' and got[k] != v}
        if got['내성'][:15] != want['내성'][:15] and any(got['내성'][k - 0x50] != want['내성'][k - 0x50]
                                                       for k in dq4monport.FC_RESISTS):
            diff['내성'] = (got['내성'], want['내성'])
        rows[f'{fc:02X}'] = {'dq5': f'{m:02X}', 'fields': len(want), 'diff': diff}
        out += [f'FC {fc:02X} → {m:02X} {k}: 롬 {a}, FC {b}' for k, (a, b) in diff.items()]
    return out, rows


def zone_problems(data, records, grid):
    """롬의 구역 레코드·고정 무리가 docs 대로가 아닌 곳."""
    import dq5encounter
    from dq5map import Rom
    rom = Rom(data)
    out = []
    for rec in records:
        got = dq5encounter.area(rom, rec['index'])
        slots = [(s['weight'], s['monster']) for s in rec['slots'] if s['weight']]
        got_slots = [(w, m) for w, m in zip(got['weights'][:10], got['monsters']) if w]
        if slots != got_slots or got['weights'][10] != rec['fixed']['weight']:
            out.append(f"구역 {rec['index']}: 롬 {got['weights']} {got['monsters']}, 기대 {slots} 고정 {rec['fixed']}")
    for g in grid['fixed_groups']:
        o = lorom(FIXED_GROUPS + 6 * g['index'])
        members = [m['monster'] for m in g['members']] + [0xFF] * (3 - len(g['members']))
        if list(data[o:o + 3]) != members:
            out.append(f"고정 무리 {g['index']}: 롬 {data[o:o + 3].hex()}, 기대 {bytes(members).hex()}")
    return out


def name_problems(data, dq5):
    import dq4battlemsg as bm
    import dq4windowtext as wt
    import dq5namewrite
    names = dq5namewrite.read_tables(dq5)[4]
    o, entries = bm.lorom(bm.NAMES_AT), set()
    while data[o]:
        n = data[o]
        entries.add(bytes(data[o + 1:o + 1 + n]))
        o += 1 + n + 1 + 2 * data[o + 1 + n]
    index = bm.lorom(wt.TEXT_BANK << 16 | wt.INDEX + 4 * 0x200)
    out = []
    for m, _ in dq4monport.NUMBERED.values():
        if bytes(names[m]) not in entries:
            out.append(f'몬스터 {m:02X} 가 전투 글 이름 표에 없음')
        if not int.from_bytes(data[index + 2 * m:index + 2 * m + 2], 'little'):
            out.append(f'몬스터 {m:02X} 가 창 이름 표에 없음')
    return out


def table_problems(data, labels, prg, dq5):
    want_t = [t for t, _ in dq4fieldencounter.fc_drop_table(prg)]
    want_i = dq4fieldencounter.dq5_drop_items(prg, dq5)
    got_t = list(data[lorom(labels['thresholds']):][:dq4fieldencounter.DROP_SLOTS])
    got_i = list(data[lorom(labels['items']):][:dq4fieldencounter.DROP_SLOTS])
    out = []
    if got_t != want_t:
        out.append(f'문턱 롬 {got_t}, FC {want_t}')
    if got_i != want_i:
        out.append(f'물건 롬 {got_i}, 기대 {want_i}')
    return out


def masked(weights, mask):
    return [0 if mask >> k & 1 else w for k, w in enumerate(weights)]


def weight_lines(rows, pc, n):
    out = []
    for _, at, kv in rows:
        if at == pc:
            b = b''.join(int(kv[f'7E{k:04X}'], 16).to_bytes(2, 'little') for k in range(0, 12, 2))
            out.append(list(b[:n]))
    return out


def drop_rolls(rows, labels):
    """[{level, start, rolls, hit, given}] 이길 때마다 훅이 표를 굴린 기록."""
    pcs = {f"{labels[k]:06X}": k for k in ('drop', 'start', 'rolled', 'hit', 'none')}
    out, cur = [], None
    for _, at, kv in rows:
        what = pcs.get(at) or ('give' if at == GIVE else None)
        if what == 'drop':
            cur = {'level': int(kv['7E2052'], 16) & 0xFF, 'start': None, 'rolls': [], 'hit': None, 'given': None,
                   'end': None}
            out.append(cur)
        elif cur is None:
            continue
        elif what == 'start':
            cur['start'] = int(kv['A'], 16)
        elif what == 'rolled':
            cur['rolls'].append(int(kv['A'], 16))
        elif what == 'hit':
            cur['hit'], cur['end'] = int(kv['X'], 16) & 0xFF, 'hit'
        elif what == 'none' and cur['end'] is None:
            cur['end'] = 'none'
        elif what == 'give':
            cur['given'] = int(kv['A'], 16) & 0xFF
    return out


def judge_drops(rolls, table, items, sure=False, off=False):
    problems = []
    if off:
        if any(r['start'] is not None for r in rolls):
            problems.append('3장 flag 없이 표를 굴림')
        if not rolls:
            problems.append('전투 뒤 훅에 오지 않음')
        return problems
    rolled = [r for r in rolls if r['start'] is not None]
    if len(rolled) < 2:
        problems.append(f'표를 굴린 전투 {len(rolled)}번(2번 이상이어야 함)')
    if sure:
        table = [(SURE, item) for _, item in table]
    for k, r in enumerate(rolled):
        want = dq4fieldencounter.drop_roll(table, r['level'], r['start'], r['rolls'] + [0x100] * dq4fieldencounter.DROP_SLOTS)
        used = dq4fieldencounter.DROP_SLOTS if want is None else (want - r['start']) % dq4fieldencounter.DROP_SLOTS + 1
        if len(r['rolls']) != used:
            problems.append(f"{k}: 굴림 {len(r['rolls'])}번, 모형 {used}번")
        if r['hit'] != want:
            problems.append(f"{k}: 훅 {r['hit']}, 모형 {want}(레벨 {r['level']} 시작 {r['start']} 굴림 {r['rolls']})")
        if want is not None and r['given'] != items[want]:
            problems.append(f"{k}: 받은 물건 {r['given']}, 기대 {items[want]}")
        if sure and r['rolls'][:1] != [SURE] and want != r['start']:
            problems.append(f"{k}: 문턱을 모두 FF 로 했는데 시작 칸 {r['start']} 이 아니라 {want}")
    return problems


def judge_merchant(mode, events, spent, bag, hp, max_hp, be):
    """떠돌이 상인 장면 판정. events 는 [(무엇, A)]."""
    kinds = [k for k, _ in events]
    problems = []
    if mode == 'roll':
        rolls = [(k, a) for k, a in enumerate(events) if a[0] == 'rolled10']
        if len(rolls) < 3:
            problems.append(f'rand(10) {len(rolls)}번(3번 이상이어야 함)')
        for k, (_, a) in rolls:
            nxt = kinds[k + 1] if k + 1 < len(kinds) else None
            if (a == 0) != (nxt == 'merchant'):
                problems.append(f'rand(10) = {a} 뒤 {nxt}')
        return problems
    if mode == 'off':
        if 'merchant' in kinds or 'rolled10' in kinds:
            problems.append('3장 flag 없이 상인 갈래에 옴')
        if 'battle' not in kinds:
            problems.append('싸우지 않음')
        return problems
    first = kinds.index('merchant') if 'merchant' in kinds else None
    if first is None:
        return ['상인이 나오지 않음']
    if 'battle' in kinds[first:]:
        problems.append('상인 뒤 전투가 걸림')
    want = 'shop' if mode == 'shop' else 'inn'
    if want not in kinds:
        problems.append(f'{want} 처리기에 오지 않음')
    messages = [a for k, a in events[first:] if k == 'msg']
    greet = {'shop': MERCHANT_GREET['shop'], 'inn': MERCHANT_GREET['day'], 'innnight': MERCHANT_GREET['night']}[mode]
    if messages[:1] != [greet]:
        problems.append(f'첫 메시지 {messages[:1]}, 기대 {greet:03X}')
    if mode != 'shop':
        after = kinds[kinds.index('inn'):] if 'inn' in kinds else []
        if 'reload' in after or 'redraw' not in after:
            problems.append('여관에서 깬 뒤 필드를 다시 그리지 않음(실내 다시 부르기 00:C6D8 이거나 필드 그리기 01:A04B 없음)')
    if be & 0x80:
        problems.append(f'끝에 실내($BE {be:02X})')
    if mode == 'shop':
        price = MERCHANT_ITEMS[0][1]
        if spent <= 0 or spent % price or bag.count(MERCHANT_ITEMS[0][0]) != spent // price:
            problems.append(f'쓴 금화 {spent}, 약초 {bag.count(MERCHANT_ITEMS[0][0])}개')
    else:
        if spent <= 0 or spent % MERCHANT_INN_PRICE:
            problems.append(f'쓴 금화 {spent}(1인 {MERCHANT_INN_PRICE}G)')
        if hp != max_hp:
            problems.append(f'자고 난 HP {hp}/{max_hp}')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    ap.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', help='장면 이름 앞부분을 쉼표로(예: drop,merchant). 롬 바이트 검사는 늘 돈다')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    rom = args.rom.resolve()
    data = rom.read_bytes()
    dq5 = args.dq5.read_bytes()
    prg = ines.prg(args.dq4.read_bytes())
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(DQ5_TOOLS / 'dq5encounterwrite.py'), args.dq5, 'dump', '-o',
                    out / 'encounter-orig.json'], check=True, capture_output=True)
    enc = json.loads((out / 'encounter-orig.json').read_text(encoding='utf-8'))
    progress, grid, report = dq4fieldencounter.docs(prg, dq5, enc, dq4groupbuild.dungeon_zones(prg).values())
    table = dq4fieldencounter.fc_drop_table(prg)
    items = dq4fieldencounter.dq5_drop_items(prg, dq5)
    _, labels = dq4fieldencounter.ch3_code(dq4fieldencounter.ch3_zone_masks(prg, report), list(zip((t for t, _ in table), items)))

    results = {}
    problems, rows = record_problems(data, prg, dq5)
    problems += name_problems(data, dq5)
    results['records'] = {'species': rows, 'problems': problems, 'ok': not problems}
    problems, rows = record_problems(data, prg, dq5, chapter1_species(prg))
    results['records-ch1'] = {'species': rows, 'problems': problems, 'ok': not problems}
    ch3_areas = {report[f'{z:02X}']['zone'] for z in dq4fieldencounter.CH3_ZONES}
    problems = zone_problems(data, [r for r in progress['encounters'] if r['index'] in ch3_areas], grid)
    results['zones'] = {'problems': problems, 'ok': not problems}
    problems = table_problems(data, labels, prg, dq5)
    results['table'] = {'problems': problems, 'ok': not problems,
                        'chance': {lv: round(dq4fieldencounter.drop_chance(table, lv), 4) for lv in DROP_LEVELS}}

    state = dq4freshstate.resolve(args.state, mesence, rom, out / 'start')
    dq4groupcheck.WARP = DQ5_TOOLS / 'lua' / 'dq5warptrace.lua'
    flag, bit = dq4fieldencounter.chapter3_flag()
    ch3_set = f'{flag & 0xFFFF:04X}|{bit:02X}'

    def stand(z):
        g, props = dq4fieldport.fc_field(prg, 0)
        x, y = fec.stand(g, props, CELLS[z])
        return dq4fieldport.stand(x, y)

    def zone_scene(z, mode, delay):
        field = stand(z)
        name = f'zone-{z:02X}-{mode}-{delay}'
        patch = dq4fieldport.warp_patch(data, *field)
        # 떠돌이 상인(조우의 1/10)이 걸리면 대화에 걷기가 멈춘다: 무게를 보는 장면에서는 끈다(상인은 merchant-*)
        patch += ';' + dq4fieldencounter.no_merchant_patch(prg, dq5, report)
        got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD='{},{}'.format(*field),
                                  ROMPATCH=f'{patch};{fec.RATES}', TEST=f'wait:{delay},{fec.WALK}', MAXF='2600',
                                  TRACE=','.join([FIRST, SECOND, *FIGHT_EXITS]), LOG=f'{WEIGHTS},{fec.LOG}',
                                  SET=ch3_set, POKE=CLOCK[mode])
        trace = list(fec.lines(out / name / 'trace.txt')) if (out / name / 'trace.txt').exists() else []
        rec = next(r for r in progress['encounters'] if r['index'] == report[f'{z:02X}']['zone'])
        weights = [s['weight'] for s in rec['slots']] + [rec['fixed']['weight']]
        day, night = dq4fieldencounter.ch3_masks(prg, z)
        mask = day if mode == 'day' else night
        want_first, want_second = masked(weights, mask), masked(weights, mask)[:5]
        first, second = weight_lines(trace, FIRST, 11), weight_lines(trace, SECOND, 5)
        allowed = {dq4fieldencounter.MONSTERS[m]
                   for m in dq4encounter.zone_monsters(prg, z, mode)}
        fights = [(FIGHT_EXITS[at], fec.groups(kv)) for _, at, kv in trace if at in FIGHT_EXITS]
        problems = []
        if 'error' in got:
            problems.append(got['error'])
        if not first:
            problems.append('첫 무리 무게를 읽지 않음')
        problems += [f'첫 무리 무게 {w}, 기대 {want_first}' for w in first if w != want_first]
        problems += [f'둘째 종 무게 {w}, 기대 {want_second}' for w in second if w != want_second]
        if not fights:
            problems.append('싸우지 않음')
        problems += [f'{kind} 무리 {g} 에 고를 수 없는 몬스터' for kind, g in fights
                     if not {m for m, _ in g} <= allowed]
        return name, {'fc_zone': f'{z:02X}', 'dq5_zone': rec['index'], 'mode': mode, 'mask': f'{mask:03X}',
                      'first': first[:1], 'second': second[:1], 'fights': fights,
                      'fc_first': fc_first(z, mode), 'dq5_first': dq5_first(want_first),
                      'problems': problems, 'ok': not problems}

    def fc_first(z, mode):
        """FC 첫 무리 칸별 확률(/1)과 DQ5 의 같은 칸 확률: 무게를 3비트로 줄인 차이를 보고만 한다."""
        rec = dq4encounter.zone(prg, z)
        picks = dq4encounter.pick(prg, rec['slots'], rec['row'], dq4encounter.MASK_FIRST[mode])
        total = sum(picks.values()) if isinstance(picks, dict) else None
        return {f'{k}': round(v / total, 3) for k, v in picks.items()} if total else picks

    def dq5_first(weights):
        total = sum(weights)
        return {f'{k}': round(w / total, 3) for k, w in enumerate(weights) if w}

    def drop_scene(name, level, sure=False, off=False):
        field = stand(0x14)
        patch = ';'.join((dq4fieldport.warp_patch(data, *field), dq4battlecheck.force_patch([(DROP_MONSTER, 1)]),
                          dq4battlecheck.weak_patch(data, [DROP_MONSTER])))
        if sure:
            patch += f";{lorom(labels['thresholds']):X}={'FF' * dq4fieldencounter.DROP_SLOTS}"
        pc = [f"{labels[k]:06X}" for k in ('drop', 'start', 'rolled', 'hit', 'none')] + [GIVE]
        got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD='{},{}'.format(*field), ROMPATCH=patch,
                                  TEST=DROP_WALK, MAXF='12000', TRACE=','.join(pc), LOG='7E2052',
                                  SET=f'2052={level:02X}' + ('' if off else f';{ch3_set}'),
                                  POKE=f"{wc.HERO_HP} {CLOCK['day']}")
        trace = list(fec.lines(out / name / 'trace.txt')) if (out / name / 'trace.txt').exists() else []
        rolls = drop_rolls(trace, labels)
        problems = ([got['error']] if 'error' in got else []) + judge_drops(rolls, table, items, sure, off)
        wram = out / name / 'final.wram'
        if wram.exists():
            bag = list(wram.read_bytes()[BAG:BAG + BAG_SLOTS])
            problems += [f'얻은 물건 {m:02X} {n}번, 가진 물건 {bag.count(m)}개' for m in {r['given'] for r in rolls} - {None}
                         if bag.count(m) < (n := sum(r['given'] == m for r in rolls))]
        return name, {'level': level, 'battles': len(rolls), 'rolls': rolls, 'problems': problems, 'ok': not problems}

    def merchant_scene(name, mode):
        field = stand(0x14)
        patch = [dq4fieldport.warp_patch(data, *field), fec.RATES]
        if mode != 'roll':
            patch.append(f"{lorom(labels['found']) + 1:X}=01")              # rand(10) 를 rand(1) 로: 늘 상인
        if mode in ('shop', 'inn', 'innnight'):
            patch.append(f"{lorom(labels['rolled256']) + 1:X}={'00' if mode == 'shop' else 'FF'}")
        pcs = {f'{labels[k]:06X}': k for k in ('rolled10', 'merchant', 'rolled256')}
        pcs.update({f'{dq4fieldencounter.TALK:06X}': 'talk', SHOP_PC: 'shop', INN_PC: 'inn', BATTLE_PC: 'battle',
                    MESSAGE_PC: 'msg', RELOAD_PC: 'reload', REDRAW_PC: 'redraw'})
        presses = ','.join(['wait:60,a:2'] * MERCHANT_PRESSES[mode]) + ',' + MERCHANT_CLOSE
        rounds = MERCHANT_ROUNDS if mode == 'roll' else 1
        test = 'idle:16,' + ','.join(['right:40,left:40,right:40,left:40,right:40,left:40,' + presses] * rounds)
        got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD='{},{}'.format(*field), ROMPATCH=';'.join(patch),
                                  TEST=test, MAXF=str(MERCHANT_FRAMES * rounds), TRACE=','.join(pcs), LOG='7E2019',
                                  SET=('' if mode == 'off' else f'{ch3_set};') + MERCHANT_SET
                                  + (NIGHT_ONCE if mode == 'innnight' else ''),
                                  POKE=f"{'' if mode == 'innnight' else CLOCK['day']} "
                                       f"{wc.HERO_HP if mode in ('roll', 'off') else ''}")
        trace = list(fec.lines(out / name / 'trace.txt')) if (out / name / 'trace.txt').exists() else []
        events = [(pcs[at], int(kv['A'], 16)) for _, at, kv in trace]
        wram = (out / name / 'final.wram').read_bytes() if (out / name / 'final.wram').exists() else bytes(0x10000)
        gold = int.from_bytes(wram[0x2019:0x201C], 'little')
        bag = list(wram[BAG:BAG + BAG_SLOTS])
        problems = [got['error']] if 'error' in got else []
        problems += judge_merchant(mode, events, MERCHANT_GOLD - gold, bag, wram[0x2042], wram[0x204E], wram[0xBE])
        return name, {'events': events[:40], 'spent': MERCHANT_GOLD - gold, 'problems': problems, 'ok': not problems}

    jobs = [(zone_scene, z, mode, d) for z in dq4fieldencounter.CH3_FIELD for mode in ('day', 'night') for d in DELAYS]
    jobs += [(merchant_scene, f'merchant-{m}', m) for m in MERCHANT_PRESSES]
    jobs += [(drop_scene, f'drop-{lv:02X}', lv) for lv in DROP_LEVELS]
    jobs += [(drop_scene, 'drop-sure', 1, True), (drop_scene, 'drop-off', 1, False, True)]
    if args.only:
        jobs = [j for j in jobs if any(j[1].startswith(p) if isinstance(j[1], str) else
                                       f'zone-{j[1]:02X}'.startswith(p) for p in args.only.split(','))]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results.update(dict(f.result() for f in [pool.submit(fn, *a) for fn, *a in jobs]))
    ok = all(r['ok'] for r in results.values())
    result = {'status': 'passed' if ok else 'failed', 'checks': results}
    (out / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: (v['ok'], v['problems'][:3]) for k, v in results.items()}, ensure_ascii=False))
    print(result['status'])
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
