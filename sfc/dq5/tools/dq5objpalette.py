"""DQ5 필드 OBJ 팔레트 색과 인물 세트의 팔레트 배정 쓰기.

맵을 불러올 때 01:93AE 가 1F:D45F 를 불러 04:96D6 의 256바이트(OBJ 팔레트 0~7, 16색씩)를 CGRAM 사본 7E:3A14 로
옮기고, 이어 01:93B2 → 01:996A 가 맵마다 덮는 16색 줄(01:9A12, 0x23바이트 항목)을 적용한다.
인물 세트는 레코드(1F:D63D) +2 bit6-7 로 OBJ 팔레트 0~3 중 하나를 쓴다. 입력 형식은
sfc/dq5/docs/dq5-build-format.md 의 「OBJ 팔레트·세트 팔레트 배정」.
dump 의 users·map·line 은 보기용이라 쓰기에서 읽지 않는다(map·line 은 바꾸면 거부).

  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc dump -o work/objpalette.json
  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc patch work/objpalette.json -o work/objpalette.dq5patch.json
  python sfc/dq5/tools/dq5objpalette.py rom/dq5.sfc check [work/objpalette.json]

문서(dq5objpalette/1):
  {"format": "dq5objpalette/1",
   "palettes": [{"palette": 1, "colors": [15개]}],             # OBJ 팔레트 0~7 의 색 1~15(0 번은 투명이라 두지 않음)
   "map_palettes": [{"index": 3, "colors": [15개]}],           # 01:9A12 의 기존 항목 색 1~15(맵·조건·줄은 그대로)
   "sets": [{"set": "84", "palette": 2}]}                      # 인물 세트가 쓰는 OBJ 팔레트(0~3)
dump 는 팔레트마다 그 팔레트를 쓰는 세트와 그림 번호를 함께 적는다(users). 쓰기에서는 읽지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5objpalette/1'
PALETTES = 8                    # 1F:D463 이 256바이트를 옮긴다
MAP_ENTRY = 0x23


def cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def keys(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 키 {sorted(allowed)}만 있는 객체여야 함')


def colors15(value, name):
    if not isinstance(value, list) or len(value) != 15 or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in value):
        raise ValueError(f'{name}: 0~7FFF 정수 15개(색 1~15)여야 함')
    return value


def palette_colors(rom, p):
    return [rom.u16(S.OBJ_PALETTES + (p * 16 + i) * 2) for i in range(1, 16)]


def users(rom):
    """팔레트마다 (세트, 그 세트를 쓰는 그림 번호들)."""
    gfx = {}
    for g in range(S.GFX_COUNT):
        gfx.setdefault(S.gfx_set(rom, g), []).append(g)
    out = {p: [] for p in range(4)}
    for s in range(S.SET_COUNT):
        rec = S.set_record(rom, s)
        if rec is not None:
            out[rec['palette']].append({'set': f'{s:02X}', 'gfx': [f'{g:02X}' for g in gfx.get(s, [])]})
    return out


def dump(rom):
    who = users(rom)
    return {'format': FORMAT,
            'palettes': [{'palette': p, 'colors': palette_colors(rom, p),
                          **({'users': who[p]} if p < 4 else {})} for p in range(PALETTES)],
            'map_palettes': [{'index': i, 'map': f'{e["bc"]:02X}/{e["bd"]:02X}', 'line': f'{e["line"]:02X}',
                              'colors': e['colors'][1:]} for i, e in enumerate(S.map_palettes(rom))],
            'sets': [{'set': f'{s:02X}', 'palette': S.set_record(rom, s)['palette']}
                     for s in range(S.SET_COUNT) if S.set_record(rom, s) is not None]}


def edits(rom, doc):
    """[(주소, 새 바이트, 원본 바이트, 설명)]."""
    keys(doc, {'format', 'palettes', 'map_palettes', 'sets'}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    out = []
    entries = S.map_palettes(rom)
    for section, count in (('palettes', PALETTES), ('map_palettes', len(entries))):
        rows = doc.get(section, [])
        if not isinstance(rows, list):
            raise ValueError(f'{section}는 배열이어야 함')
        seen = set()
        field = 'palette' if section == 'palettes' else 'index'
        for i, row in enumerate(rows):
            label = f'{section}[{i}]'
            # dump 가 붙이는 설명 키(users·map·line)는 받되 쓰지 않는다. 바꿀 수 있는 것은 색뿐이다.
            keys(row, {field, 'colors', *(('users',) if section == 'palettes' else ('map', 'line'))}, label)
            n = row.get(field)
            if type(n) is not int or not 0 <= n < count or n in seen:
                raise ValueError(f'{label}.{field}: 0~{count - 1} 정수이고 한 번만 지정함')
            seen.add(n)
            new = b''.join(c.to_bytes(2, 'little') for c in colors15(row.get('colors'), f'{label}.colors'))
            if section == 'palettes':
                at, note = S.OBJ_PALETTES + (n * 16 + 1) * 2, f'OBJ 팔레트 {n} 색 1~15'
            else:
                e = entries[n]
                if row.get('map', f'{e["bc"]:02X}/{e["bd"]:02X}') != f'{e["bc"]:02X}/{e["bd"]:02X}' or \
                        row.get('line', f'{e["line"]:02X}') != f'{e["line"]:02X}':
                    raise ValueError(f'{label}: map·line 은 바꿀 수 없음(원본 {e["bc"]:02X}/{e["bd"]:02X} 줄 {e["line"]:02X})')
                at, note = e['entry'] + 5, f'맵 팔레트 {n}({e["bc"]:02X}/{e["bd"]:02X} 줄 {e["line"]:02X}) 색 1~15'
            out.append((at, new, bytes(rom.d[lorom(at):lorom(at) + 30]), note))
    rows = doc.get('sets', [])
    if not isinstance(rows, list):
        raise ValueError('sets는 배열이어야 함')
    seen = set()
    for i, row in enumerate(rows):
        label = f'sets[{i}]'
        keys(row, {'set', 'palette'}, label)
        name = row.get('set')
        if not isinstance(name, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}', name):
            raise ValueError(f'{label}.set: 두 자리 16진 문자열')
        s = int(name, 16)
        rec = S.set_record(rom, s) if s < S.SET_COUNT else None
        if rec is None or s in seen:
            raise ValueError(f'{label}: 세트 {name}가 없거나 두 번 지정함')
        seen.add(s)
        p = row.get('palette')
        if type(p) is not int or not 0 <= p <= 3:
            raise ValueError(f'{label}.palette: 0~3 정수(레코드 +2 bit6-7)')
        at = rec['record'] + 2
        old = rom.u8(at)
        out.append((at, bytes([old & 0x3F | p << 6]), bytes([old]), f'세트 {s:02X} 팔레트 {rec["palette"]} → {p}'))
    return out


def patch(rom, doc):
    return {'format': 'dq5patch/1', 'name': 'obj-palettes', 'writes': [
        {'at': cpu(at), 'hex': new.hex(' '), 'orig': old.hex(' '), 'note': note}
        for at, new, old, note in edits(rom, doc) if new != old]}


def overridden(rom, doc):
    """바꾼 OBJ 팔레트 줄을 맵마다 덮는 01:9A12 항목. 그 맵에서는 바꾼 색이 보이지 않는다."""
    changed = {row['palette'] for row in doc.get('palettes', []) if row['colors'] != palette_colors(rom, row['palette'])}
    return {p: [f'{e["bc"]:02X}/{e["bd"]:02X}' for e in S.map_palettes(rom) if e['line'] == 8 + p] for p in sorted(changed)}


def affected(rom, doc):
    """바꾼 OBJ 팔레트 0~3 을 쓰는 세트(새 배정 포함)."""
    after = {s: rec['palette'] for s in range(S.SET_COUNT) if (rec := S.set_record(rom, s)) is not None}
    for row in doc.get('sets', []):
        after[int(row['set'], 16)] = row['palette']
    changed = {row['palette'] for row in doc.get('palettes', []) if row['colors'] != palette_colors(rom, row['palette'])}
    return {p: sorted(f'{s:02X}' for s, q in after.items() if q == p) for p in sorted(changed) if p < 4}


def check(rom, doc=None):
    from dq5build import build, parse_at
    original = dump(rom)
    source = original if doc is None else doc
    writes = patch(rom, source)['writes']
    if doc is None and writes:
        raise ValueError('원본 왕복 쓰기가 0개가 아님')
    data, _ = build(rom.d, [('obj-palettes', 0, [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']),
                                                   w['note']) for w in writes])], 0)
    moved = Rom(data)
    if patch(moved, source)['writes'] or patch(moved, dump(moved))['writes']:
        raise ValueError('빌드한 롬을 다시 읽어 패치하면 쓰기가 남음')
    for s in range(S.SET_COUNT):
        a, b = S.set_record(rom, s), S.set_record(moved, s)
        if (a is None) != (b is None) or a and (a['cells'], a['data'], a['tiles']) != (b['cells'], b['data'], b['tiles']):
            raise ValueError(f'세트 {s:02X}: 팔레트 밖 레코드가 달라짐')
    print(f'OBJ 팔레트 {PALETTES}개, 맵 팔레트 {len(original["map_palettes"])}개, 세트 {len(original["sets"])}개 검사 통과; '
          f'쓰기 {len(writes)}개')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path, nargs='?')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc)
            return 0
        result = dump(rom) if args.command == 'dump' else patch(rom, doc)
        if args.command == 'patch':
            for p, sets in affected(rom, doc).items():
                print(f'OBJ 팔레트 {p} 를 쓰는 세트 {len(sets)}개: {" ".join(sets)}')
            for p, maps in overridden(rom, doc).items():
                if maps:
                    print(f'OBJ 팔레트 {p} 줄을 맵 팔레트가 덮는 맵(바꾼 색이 안 보임): {" ".join(maps)}')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError, KeyError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
