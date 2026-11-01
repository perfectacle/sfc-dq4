"""롬 바이트 검사(에뮬레이터 없음, 수 초): 쓰기 장부(dq4romledger.py)와 결과 롬으로 단계끼리 덮어쓴 곳, 원래 롬을 크게
덮은 곳, 뱅크 경계를 넘는 쓰기, 표 불변식을 본다. 형식과 허용 목록 규칙은 sfc/dq4/docs/dq4-rom-ledger-format.md.

  overlap   뒤 단계가 앞 단계가 쓴 바이트를 다시 씀. 허용 목록 [[overlap]] 에 없으면 실패
  original  원래 롬의 0 아닌 바이트를 BIG 바이트 이상 한 덩어리(틈 GAP 이하는 이음)로 덮음. [[original]] 에 없으면 실패.
            그보다 작은 덮기(훅·표 칸 고치기)는 단계마다 세어 보고만 한다
  cross     뱅크 경계를 넘는 쓰기 덩어리. [[cross]] 에 없으면 실패. 코드 덩어리(dq4brkscan.blobs)가 넘으면 늘 실패
  table     표 불변식(INVARIANTS). 하나라도 어기면 실패

  python sfc/dq4/tools/dq4romledgercheck.py --ledger work/ch1/ledger.json [--rom 롬] [--report work/ledgercheck/report.json]

--rom 을 빼면 장부 마지막 단계의 파일(장부와 같은 폴더)을 본다. 자원 저장소 없이 빌드해 곡·인물 단계가 없으면 그 단계의
허용 항목은 쓰이지 않아 경고만 남는다.
"""
import argparse
import hashlib
import json
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4romledger as L  # noqa: E402

ALLOW = HERE.parent / 'ledger-allow.toml'
# 머리 체크섬(00:FFDC~FFDF)은 단계마다 다시 맞춘다. 롬 크기 바이트(00:FFD7)는 타이틀이 늘리며 고친다
HEADER = (0x7FD7, 0x7FDC, 0x7FDD, 0x7FDE, 0x7FDF)
BIG = 64
GAP = 16
KINDS = {'overlap': ('earlier', 'later'), 'original': ('stage',), 'cross': ('stage',)}


class AllowError(ValueError):
    pass


def parse_at(text):
    """'BB:AAAA~BB:AAAA'(끝 포함) 또는 'BB:AAAA'(한 바이트) → [시작, 끝) 파일 오프셋."""
    lo, sep, hi = text.partition('~')
    s = L.offset(lo.strip())
    e = L.offset(hi.strip()) + 1 if sep else s + 1
    if e <= s:
        raise AllowError(f'{text!r}: 끝이 시작보다 앞')
    return s, e


def load_allow(text, stages):
    """허용 목록 TOML 글 → {종류: [{필드…, 'span': (s, e), 'why'}]}. stages 는 받는 단계 이름."""
    doc = tomllib.loads(text)
    out = {k: [] for k in KINDS}
    for kind, items in doc.items():
        if kind not in KINDS:
            raise AllowError(f'모르는 표 [[{kind}]]')
        for n, item in enumerate(items, 1):
            where = f'[[{kind}]] {n}번째'
            keys = set(KINDS[kind]) | {'at', 'why'}
            if set(item) != keys:
                raise AllowError(f'{where}: 키는 {sorted(keys)} 여야 함(받은 것 {sorted(item)})')
            if not isinstance(item['why'], str) or not item['why'].strip():
                raise AllowError(f'{where}: why 가 비었음')
            for field in KINDS[kind]:
                if item[field] != '*' and item[field] not in stages:
                    raise AllowError(f'{where}: 단계 {item[field]!r} 가 장부에 없음({", ".join(stages)})')
            try:
                span = parse_at(item['at'])
            except ValueError as e:
                raise AllowError(f'{where}: {e}') from None
            out[kind].append({**item, 'span': span, 'used': False})
    return out


def find_allow(allow, kind, s, e, **names):
    """[s, e) 를 통째로 덮고 단계 이름이 맞는(또는 '*') 첫 항목. 없으면 None."""
    for item in allow[kind]:
        lo, hi = item['span']
        if lo <= s and e <= hi and all(item[k] in ('*', v) for k, v in names.items()):
            item['used'] = True
            return item
    return None


def subtract(ranges, holes):
    """[시작, 끝) 목록 ranges 에서 holes 를 뺀 것. 둘 다 정렬돼 있다고 본다."""
    out, holes = [], sorted(holes)
    j = 0
    for s, e in ranges:
        while j < len(holes) and holes[j][1] <= s:
            j += 1
        k, cur = j, s
        while k < len(holes) and holes[k][0] < e:
            if holes[k][0] > cur:
                out.append((cur, holes[k][0]))
            cur = max(cur, holes[k][1])
            k += 1
        if cur < e:
            out.append((cur, e))
    return out


def written(stage):
    """단계가 쓴 바이트: 바뀐 곳에서 거울을 0 으로 지운 곳을 뺀 [시작, 끝) 목록."""
    return subtract([L.range_of(r) for r in stage['ranges']], [L.range_of(r) for r in stage.get('cleared', ())])


def overlaps(stages, size):
    """[(앞 단계, 뒤 단계, 시작, 끝)]. 바이트마다 마지막으로 쓴 단계를 들고 간다. 거울을 지운 바이트는 주인을 비운다."""
    owner = bytearray(size)
    out = []
    for i, st in enumerate(stages, 1):
        for s, e in written(st):
            seg = owner[s:e]
            if seg.count(0) != len(seg):
                j = s
                while j < e:
                    k = j + 1
                    while k < e and owner[k] == owner[j]:
                        k += 1
                    if owner[j]:
                        out.append((stages[owner[j] - 1]['name'], st['name'], j, k))
                    j = k
            owner[s:e] = bytes([i]) * (e - s)
        for r in st.get('cleared', ()):
            s, e = L.range_of(r)
            owner[s:e] = bytes(e - s)
    return out


def original_blocks(stage, dq5):
    """단계가 원래 롬(1.5MB)의 0 아닌 바이트를 덮은 곳을 GAP 이하 틈은 이어 [시작, 끝) 목록으로. 머리는 뺀다."""
    hits = []
    for s, e in written(stage):
        start = None
        for i in range(s, min(e, len(dq5))):
            if dq5[i] and i not in HEADER:
                if start is None:
                    start = i
            elif start is not None:
                hits.append((start, i))
                start = None
        if start is not None:
            hits.append((start, min(e, len(dq5))))
    return L.merge(hits, GAP)


def fmt(s, e):
    return f'{L.cpu(s)}~{L.cpu(e - 1)}' if e - s > 1 else L.cpu(s)


def check_overlaps(stages, allow, size):
    rows, bad = [], []
    merged = defaultdict(list)
    for a, b, s, e in overlaps(stages, size):
        merged[a, b].append((s, e))
    for (a, b), spans in merged.items():
        for s, e in L.merge(spans):
            item = find_allow(allow, 'overlap', s, e, earlier=a, later=b)
            rows.append({'earlier': a, 'later': b, 'at': fmt(s, e), 'bytes': e - s, 'why': item and item['why']})
            if not item:
                bad.append(f'겹침 {a} → {b} {fmt(s, e)}({e - s}바이트)가 허용 목록에 없음')
    return rows, bad


def check_original(stages, allow, dq5):
    rows, small, bad = [], {}, []
    for st in stages:
        blocks = original_blocks(st, dq5)
        small[st['name']] = {'blocks': sum(1 for s, e in blocks if e - s < BIG),
                             'bytes': sum(e - s for s, e in blocks if e - s < BIG)}
        for s, e in blocks:
            if e - s < BIG:
                continue
            item = find_allow(allow, 'original', s, e, stage=st['name'])
            rows.append({'stage': st['name'], 'at': fmt(s, e), 'bytes': e - s, 'why': item and item['why']})
            if not item:
                bad.append(f'{st["name"]}: 원래 롬 {fmt(s, e)}({e - s}바이트)를 덮는데 허용 목록에 없음')
    return rows, small, bad


def code_blobs():
    """[(이름, 시작 CPU 주소, 길이)]: 높은 뱅크 사건 코드 덩어리(dq4brkscan 이 훑는 것)."""
    import dq4brkscan
    return [(name, base, len(blob)) for name, base, blob, _ in dq4brkscan.blobs()]


def check_cross(stages, allow, blobs):
    rows, bad = [], []
    for st in stages:
        for s, e in written(st):
            if not L.crosses_bank(s, e):
                continue
            item = find_allow(allow, 'cross', s, e, stage=st['name'])
            rows.append({'stage': st['name'], 'at': fmt(s, e), 'bytes': e - s, 'why': item and item['why']})
            if not item:
                bad.append(f'{st["name"]}: 뱅크 경계를 넘는 쓰기 {fmt(s, e)}({e - s}바이트)가 허용 목록에 없음')
    for name, base, n in blobs:
        if base >> 16 != (base + n - 1) >> 16:
            bad.append(f'코드 덩어리 {name} {base:06X}+{n} 이 뱅크 경계를 넘음(PC 는 뱅크를 넘지 않음)')
    return rows, bad


# --- 표 불변식. 함수마다 (요약, [문제]) 를 돌려준다. 롬 읽기는 DQ5 디코더를 그대로 쓴다.

def inv_checksum(rom, dq5):
    from dq4romassets import set_checksum
    ok = set_checksum(rom) == bytes(rom)
    return f'체크섬 {rom[0x7FDE] | rom[0x7FDF] << 8:04X}', [] if ok else ['머리 체크섬(00:FFDC~FFDF)이 롬 합과 맞지 않음']


VECTORS = {0xFFE4: 'COP', 0xFFE6: 'BRK', 0xFFEA: 'NMI', 0xFFEE: 'IRQ', 0xFFF4: 'COP(에뮬)', 0xFFFA: 'NMI(에뮬)',
           0xFFFC: 'RESET', 0xFFFE: 'IRQ/BRK(에뮬)'}


def inv_vectors(rom, dq5):
    """원래 롬에서 쓰던 벡터가 뱅크 00 의 0 아닌 바이트를 가리키는지. 원래 롬에서 0 인 벡터(ABORT 등)는 보지 않는다."""
    bad, seen = [], []
    for at, name in VECTORS.items():
        o = at - 0x8000
        v = rom[o] | rom[o + 1] << 8
        seen.append(f'{name} {v:04X}')
        if v < 0x8000:
            bad.append(f'{name} 벡터 00:{at:04X} = {v:04X}: 롬 밖')
        elif rom[v - 0x8000] in (0x00, 0xFF):
            bad.append(f'{name} 벡터 00:{at:04X} → 00:{v:04X} 의 첫 바이트가 {rom[v - 0x8000]:02X}')
    return ', '.join(seen), bad


def inv_hooks(rom, dq5, stages):
    """원래 롬 자리에 새로 쓴 JSL(22)·JML(5C): 쓴 덩어리의 첫 바이트(또는 첫 바이트가 원래와 같아 한 바이트 앞)가 그
    명령이고 피연산자 셋이 모두 그 단계가 쓴 바이트이면 훅으로 본다. 대상이 롬 안의 8000~FFFF 이고, 0 이 아닌 바이트라야 한다."""
    bad, count = [], 0
    for st in stages:
        for s, e in written(st):
            if s >= len(dq5):
                continue
            for at in (s, s - 1):
                if at < 0:
                    continue
                op = rom[at]
                if op not in (0x22, 0x5C) or at + 4 > e:
                    continue
                target = rom[at + 1] | rom[at + 2] << 8 | rom[at + 3] << 16
                bank, addr = target >> 16, target & 0xFFFF
                if bank in (0x7E, 0x7F) or addr < 0x8000:
                    break
                count += 1
                t = L.offset(f'{bank:02X}:{addr:04X}')
                if t >= len(rom):
                    bad.append(f'{st["name"]} {L.cpu(at)}: {"JSL" if op == 0x22 else "JML"} {bank:02X}:{addr:04X} 롬 밖')
                elif rom[t] == 0x00:
                    bad.append(f'{st["name"]} {L.cpu(at)}: {"JSL" if op == 0x22 else "JML"} {bank:02X}:{addr:04X} 이 0 바이트(BRK)를 가리킴')
                break
    return f'훅 {count}개', bad


SHOP_BANKS = (0x06F4AE, 0x06F54E)       # LDA #뱅크 / PHA / PLB (목록 키 찾기·품목 읽기)
SHOP_TABLES = (0x06F4BA, 0x06F50D)      # LDA abs,X / ADC abs,X 의 포인터 표 주소
SHOP_KINDS = 4
ITEMS = 0xD8
INN_BANK, INN_ADDR = 0x06F568, 0x06F56E
INN_ORIGINAL, INN_COUNT = 0x04FD6D, 21


def _u16(rom, a):
    o = L.offset(f'{a >> 16:02X}:{a & 0xFFFF:04X}')
    return rom[o] | rom[o + 1] << 8


def _u8(rom, a):
    return rom[L.offset(f'{a >> 16:02X}:{a & 0xFFFF:04X}')]


def inv_shops(rom, dq5):
    """가게 목록(06:F49C·06:F545 가 읽음): 두 루틴의 뱅크·표 주소가 같고, 뱅크가 낮은 WRAM 이 보이는 00~3F, 종류마다
    [키][품목…][FF] 가 뱅크 안에서 끝나고 품목 번호가 물건 수 안. 마지막 종류는 키 자리의 FF(옮긴 표) 또는 원래 끝에서 끝난다."""
    bad = []
    banks = {_u8(rom, a) for a in SHOP_BANKS}
    tables = {_u16(rom, a) for a in SHOP_TABLES}
    if len(banks) != 1 or len(tables) != 1:
        return '', [f'가게 뱅크 {sorted(banks)}·표 {[f"{t:04X}" for t in sorted(tables)]} 가 두 루틴에서 다름']
    bank, table = banks.pop(), tables.pop()
    if bank > 0x3F or table < 0x8000:
        return '', [f'가게 표 {bank:02X}:{table:04X}: 뱅크 00~3F, 8000~ 이어야 함']
    starts = [_u16(rom, bank << 16 | table + 2 * k) for k in range(SHOP_KINDS)]
    end = 0xFD55 if (bank, table) == (0x04, 0xFBD5) else 0x10000
    if any(s < 0x8000 for s in starts) or starts != sorted(starts):
        return '', [f'가게 종류 포인터 {" ".join(f"{s:04X}" for s in starts)} 가 8000~ 에서 앞으로 가지 않음']
    lists = 0
    for k in range(SHOP_KINDS):
        a, stop = starts[k], starts[k + 1] if k + 1 < SHOP_KINDS else end
        while a < stop:
            key = _u8(rom, bank << 16 | a)
            if k + 1 == SHOP_KINDS and key == 0xFF:
                break
            a += 1
            while a < 0x10000 and (item := _u8(rom, bank << 16 | a)) != 0xFF:
                if item >= ITEMS:
                    bad.append(f'가게 종류 {k} 키 {key:02X}: 품목 {item:02X} 가 물건 수 {ITEMS:02X} 밖({bank:02X}:{a:04X})')
                a += 1
            if a >= 0x10000:
                bad.append(f'가게 종류 {k} 키 {key:02X}: 뱅크 끝까지 FF 가 없음')
                break
            a += 1
            lists += 1
    return f'가게 {bank:02X}:{table:04X} 목록 {lists}개', bad


def inv_inns(rom, dq5):
    """여관 1인 값 표(06:F563 이 DB 를 표 뱅크로 두고 읽음): 뱅크 00~3F, 원래 21항목이 앞에 그대로."""
    bank, addr = _u8(rom, INN_BANK), _u16(rom, INN_ADDR)
    if bank > 0x3F or addr < 0x8000:
        return '', [f'여관 표 {bank:02X}:{addr:04X}: 뱅크 00~3F, 8000~ 이어야 함']
    o, src = L.offset(f'{bank:02X}:{addr:04X}'), L.offset('04:FD6D')
    same = rom[o:o + 2 * INN_COUNT] == dq5[src:src + 2 * INN_COUNT]
    return f'여관 {bank:02X}:{addr:04X}', [] if same else ['여관 표 앞 21항목이 원래 표와 다름']


def inv_exits(rom, dq5):
    """출구·영역 이동 표(dq5exitreloc.parse 가 엔진 순서로 따라감)가 끝까지 읽히고, 목적지가 있는 맵 또는 필드(FF)."""
    import dq5exitreloc as x
    from dq5map import Rom
    r = Rom(rom)
    try:
        known = x.known_maps(r)
        doc = x.parse(r, known=known)
    except (ValueError, IndexError) as e:
        return '', [f'출구 표를 읽지 못함: {e}']
    bad = []
    for e in doc['exits']:
        bc = int(e['map'][:2], 16)
        for row in e['records']:
            if row['kind'] != 'special' and (row.get('group', bc), row['destination_map']) not in known:
                bad.append(f'{e["map"]} 출구 → {row.get("group", bc):02X}/{row["destination_map"]:02X} 맵이 없음')
    for e in doc['triggers'] + doc['high_triggers']:
        for row in e['records']:
            g, m = row['destination_group'], row['destination_map']
            if g != 0xFF and (g, m) not in known:
                bad.append(f'{e.get("map", e.get("maps"))} 영역 이동 → {g:02X}/{m:02X} 맵이 없음')
    return f'맵 {len(known)}개, 출구 맵 {len(doc["exits"])}개, 영역 이동 맵 {len(doc["triggers"])}개', bad


def inv_messages(rom, dq5):
    """보행 메시지: 옮긴 디코더·색인(24:9E02 호출, 24:8BC3 색인 읽기)으로 전부 풀리고 글자·제어 코드가 묶음 표 안."""
    import dq5textwrite
    try:
        messages, _, glyphs, extents, _ = dq5textwrite.base_package(bytes(rom))
    except (ValueError, IndexError) as e:
        return '', [f'보행 메시지를 읽지 못함: {e}']
    bad = [f'메시지 구간 {s:06X}~{e:06X} 이 롬 밖' for s, e in extents if e > len(rom)]
    return f'메시지 {len(messages)}개, 글자 {glyphs}', bad


def inv_people(rom, dq5):
    """인물 목록(12:8020 이 읽는 그룹 포인터)과 인물마다 낮·밤 스크립트가 명령 길이로 읽혀 길이 바이트와 맞음."""
    import contextlib
    import io
    import dq5npc
    from dq5map import Rom
    r = Rom(rom)
    out = io.StringIO()
    try:
        lists = len(dq5npc.all_lists(r))
        with contextlib.redirect_stdout(out):
            bad = dq5npc.check_scripts(r)
    except (ValueError, IndexError) as e:
        return '', [f'인물 목록을 읽지 못함: {e}']
    lines = [ln for ln in out.getvalue().splitlines() if not ln.startswith('scripts ')]
    return f'목록 {lists}개, {out.getvalue().splitlines()[-1]}', lines if bad else []


def inv_brkscan(rom, dq5):
    """높은 뱅크 사건 코드가 확인한 BRK 명령만 부름(dq4brkscan, COMPAT-01)."""
    import dq4brkscan
    all_blobs = dq4brkscan.blobs()
    spans = [(b, b + len(blob)) for _, b, blob, _ in all_blobs]
    bad = []
    for name, base, blob, entries in all_blobs:
        bad += [f'{name}: {p}' for p in dq4brkscan.scan(base, blob, entries, spans)[1]]
    return f'덩어리 {len(all_blobs)}개', bad


INVARIANTS = {
    'checksum': inv_checksum,
    'vectors': inv_vectors,
    'shops': inv_shops,
    'inns': inv_inns,
    'exits': inv_exits,
    'messages': inv_messages,
    'people': inv_people,
    'brkscan': inv_brkscan,
}


def run(ledger, rom, dq5, allow_text):
    """(보고 dict, [실패]). 경고는 보고의 warnings."""
    stages = ledger['stages']
    fails, warnings = [], []
    if hashlib.sha1(dq5).hexdigest() != ledger['base']['sha1']:
        fails.append('원래 롬 SHA-1 이 장부의 base 와 다름')
    if not stages or hashlib.sha1(rom).hexdigest() != stages[-1]['sha1']:
        fails.append('롬 SHA-1 이 장부 마지막 단계와 다름(빌드를 다시 하거나 맞는 장부를 줌)')
    allow = load_allow(allow_text, sorted(set(L.STAGES) | {s['name'] for s in stages}))
    size = max(len(rom), *(s['size'] for s in stages))
    report = {'rom_sha1': hashlib.sha1(rom).hexdigest(),
              'stages': [{'name': s['name'], 'ranges': len(written(s)), 'bytes': sum(e - b for b, e in written(s)),
                          'cleared': sum(r['bytes'] for r in s.get('cleared', ()))} for s in stages]}
    report['overlap'], bad = check_overlaps(stages, allow, size)
    fails += bad
    report['original'], report['original_small'], bad = check_original(stages, allow, dq5)
    fails += bad
    report['cross'], bad = check_cross(stages, allow, code_blobs())
    fails += bad
    report['invariants'] = {}
    for name, f in INVARIANTS.items():
        summary, bad = f(rom, dq5)
        report['invariants'][name] = {'summary': summary, 'problems': bad}
        fails += [f'{name}: {p}' for p in bad]
    summary, bad = inv_hooks(rom, dq5, stages)
    report['invariants']['hooks'] = {'summary': summary, 'problems': bad}
    fails += [f'hooks: {p}' for p in bad]
    for kind, items in allow.items():
        for item in items:
            if not item['used']:
                warnings.append(f'[[{kind}]] {item["at"]} 에 맞는 쓰기가 없음(지워도 되는지 확인)')
    report['warnings'] = warnings
    return report, fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ledger', type=Path, default=Path('work/ch1/ledger.json'))
    ap.add_argument('--rom', type=Path, help='결과 롬(기본: 장부 마지막 단계의 파일)')
    ap.add_argument('--dq5', type=Path, default=Path('rom/dq5.sfc'))
    ap.add_argument('--allow', type=Path, default=ALLOW)
    ap.add_argument('--report', type=Path, help='보고를 JSON 으로 쓸 곳')
    args = ap.parse_args()
    ledger = L.load(args.ledger)
    rom = args.rom or args.ledger.parent / ledger['stages'][-1]['file']
    report, fails = run(ledger, rom.read_bytes(), args.dq5.read_bytes(), args.allow.read_text(encoding='utf-8'))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for st in report['stages']:
        print(f"단계 {st['name']}: 쓴 범위 {st['ranges']}개 {st['bytes']}바이트, 거울 지움 {st['cleared']}바이트")
    print(f"겹침 {len(report['overlap'])}곳, 원래 롬 큰 덮기 {len(report['original'])}곳, 뱅크 넘기 {len(report['cross'])}곳")
    for name, small in report['original_small'].items():
        if small['blocks']:
            print(f"  {name}: 원래 롬 작은 덮기 {small['blocks']}곳 {small['bytes']}바이트(보고만)")
    for name, inv in report['invariants'].items():
        print(f"불변식 {name}: {'통과' if not inv['problems'] else '실패'} — {inv['summary']}")
    for w in report['warnings']:
        print(f'경고: {w}')
    for f in fails:
        print(f'실패: {f}')
    print('통과' if not fails else f'실패 {len(fails)}개')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
