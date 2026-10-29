"""DQ5 실내 맵에 보물상자·가구를 놓고, 그 내용물을 보상 표에 함께 넣는다.

sfc/dq5/docs/dq5-build-format.md 의 「보물상자 놓기」. 맵마다 상자 블록 배치를 더해 맵 레코드를 다시 싸고
(dq5mapcompile·dq5mapwrite), 그 롬에서 셀 버퍼를 다시 풀어 상자 칸(+7 = 84) 순서를 센다. 상자 번호는 맵 셀 순서로
정해지므로(25:FAB0), 기존 상자의 내용물은 좌표로 따라가게 상자 내용물·맵 연결 표를 다시 짜서 dq5chestreloc 로 쓴다.
가구(タンス·ツボ·タル)는 블록 안에 새로 생긴 가구 칸(+4 = 93, +7 = A7·B9 등)을 찾아 서랍 표 끝에 항목을 더한다.
결과는 맵 레코드와 상자 표를 함께 담은 dq5patch/1 하나다.

  python sfc/dq5/tools/dq5chestplace.py rom/dq5.sfc patch work/place.json -o work/place.dq5patch.json \\
      --map-at BB:AAAA [--chests-at BB:AAAA] [--chest-maps-at BB:AAAA]
  python sfc/dq5/tools/dq5chestplace.py rom/dq5.sfc check work/place.json --map-at … [같은 자리 선택]

입력 format=dq5chestplace/1, maps[{map:"GG/MM", chests[{x,y,block,reward}],
furniture[{x,y,block,reward,flag_index,mask[,unused]}]}]. x·y 는 블록 원점(왼쪽 위), block 은 실내 맵 블록 번호다.
블록이 놓인 칸 안에 상자 칸(가구 칸)이 하나 새로 생겨야 한다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import dq5chestreloc as reloc
from dq5build import PatchError, build, cpu as file_cpu, parse_at
from dq5chest import chests
from dq5chestwrite import fields, integer, map_dimensions
from dq5map import Rom, lorom, map_pointer
from dq5mapcompile import block_sizes, cell_buffer, compile_places, extract
from dq5mapwrite import all_maps, encode, pointer_addr, to_cpu

FORMAT = 'dq5chestplace/1'
# 서랍 표 86항목이 놓인 칸의 속성. タンス 는 아래층(+4) 93, ツボ·タル 는 위층(+7) A7·B9 였다. D3·D4 는 위층에만 있는
# タル·ツボ 칸으로, 게임에서 149·135 메시지를 확인했다(dq5-map-format.md)
LOWER_FURNITURE = {0x93}
UPPER_FURNITURE = {0xA7, 0xB9, 0xD3, 0xD4}
# 서랍 열림 비트는 7E:222C + flag_index. 2240 부터는 발밑 표의 비트다
SEARCH_FLAGS = 0x2240 - 0x222C
BOX_FIELDS = {'x', 'y', 'block', 'reward'}
FURNITURE_FIELDS = BOX_FIELDS | {'flag_index', 'mask'}


def map_key(text, label):
    if not isinstance(text, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}/[0-9A-Fa-f]{2}', text):
        raise ValueError(f'{label}: map 은 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in text.split('/'))


def chest_cells(rom, bc, bd):
    return [xy for _, xy, _ in chests(rom, bc, bd, 0)]


def map_writes(rom, doc, at):
    """맵마다 상자 블록을 더한 레코드를 늘린 자리 at(파일 위치)부터 놓는다. (쓰기, 맵별 새 상자 목록, 끝 위치)."""
    fields(doc, {'format', 'maps'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('maps'), list) or not doc['maps']:
        raise ValueError(f'format={FORMAT} 과 비지 않은 maps 배열이 필요함')
    known, writes, placed, seen = set(all_maps(rom)), [], [], set()
    for i, item in enumerate(doc['maps']):
        label = f'maps[{i}]'
        fields(item, {'map', 'chests', 'furniture'}, label)
        bc, bd = map_key(item.get('map'), label)
        if (bc, bd) not in known or bc >= 0x50:
            raise ValueError(f'{label}: 일반 실내 맵(그룹 00~35)만 받음')
        if (bc, bd) in seen:
            raise ValueError(f'{label}: 같은 맵을 두 번 적음')
        seen.add((bc, bd))
        boxes, furniture = item.get('chests', []), item.get('furniture', [])
        if not isinstance(boxes, list) or not isinstance(furniture, list) or not boxes + furniture:
            raise ValueError(f'{label}: chests·furniture 는 배열이고 둘 중 하나는 비지 않아야 함')
        src = extract(rom, bc, bd)
        sizes = block_sizes(rom, False)
        for kind, rows, need in (('chests', boxes, BOX_FIELDS), ('furniture', furniture, FURNITURE_FIELDS)):
            for k, box in enumerate(rows):
                where = f'{label}.{kind}[{k}]'
                fields(box, need | ({'unused'} if kind == 'furniture' else set()), where)
                if need - set(box):
                    raise ValueError(f'{where}: {sorted(need)} 를 모두 적어야 함')
                integer(box['block'], len(sizes) - 1, 'block')
                width, height = sizes[box['block']]
                if integer(box['x'], 255, 'x') + width > src['width'] or integer(box['y'], 255, 'y') + height > src['height']:
                    raise ValueError(f'{where}: 블록이 맵 {src["width"]}×{src["height"]} 밖으로 나감')
                if kind == 'chests':
                    reloc.row_encode('chests', {'reward': box['reward']}, f'{where}.reward')
                src['placements'].append([box['x'], box['y'], box['block']])
        record = encode(compile_places(src, rom, False))
        pointer = lorom(pointer_addr(rom, bc, bd))
        writes.append((at, record, None, f'map {bc:02X}/{bd:02X}'))
        writes.append((pointer, to_cpu(at).to_bytes(3, 'little'), bytes(rom.d[pointer:pointer + 3]),
                       f'map {bc:02X}/{bd:02X} 포인터'))
        placed.append(((bc, bd), boxes, furniture, sizes))
        at += len(record)
    return writes, placed, at


def cell_rewards(rom, tables):
    """(BC, BD, 칸) → 내용물. 맵의 상자 칸 수가 등록 개수와 다르면 번호가 어긋나므로 거부한다."""
    out, start = {}, 0
    for row in tables['chest_maps']:
        cells = chest_cells(rom, row['group'], row['map'])
        if len(cells) != row['count']:
            raise ValueError(f'{row["group"]:02X}/{row["map"]:02X}: 상자 칸 {len(cells)}개와 등록 개수 {row["count"]}가 다름')
        for k, xy in enumerate(cells):
            out[(row['group'], row['map'], xy)] = tables['chests'][start + k]['reward']
        start += row['count']
    return out


def furniture_cells(data, bc, bd):
    width = map_dimensions(Rom(data), bc, bd)[0]
    cells, _ = cell_buffer(data, bc, bd)
    return {(i % width, i // width) for i, cell in enumerate(cells)
            if cell[4] in LOWER_FURNITURE or cell[7] in UPPER_FURNITURE}


def flag_bits(tables):
    """표마다의 열림 비트 → {(WRAM 주소, 마스크)}. 새 서랍 항목이 다른 보상과 비트를 나눠 쓰지 않게 본다."""
    out = set()
    for n in range(len(tables['chests'])):
        out.add((0x2210 + (n >> 3), 0x80 >> (n & 7)))
    bases = {'search': 0x222C, 'foot': 0x2240}
    for name in ('search', 'foot', 'ahead', 'lower'):
        for row in tables[name]:
            addr = bases[name] + row['flag_index'] if name in bases else 0x2210 + (row['flag_index'] & 0x7F)
            out |= {(addr, bit) for bit in (1, 2, 4, 8, 16, 32, 64, 128) if row['mask'] & bit}
    return out


def changed_cells(before, after, bc, bd):
    width = map_dimensions(Rom(before), bc, bd)[0]
    old, _ = cell_buffer(before, bc, bd)
    new, _ = cell_buffer(after, bc, bd)
    return {(i % width, i // width) for i, (a, b) in enumerate(zip(old, new)) if a != b}


def mb_for(end):
    return 4 if end > 0x300000 else 3 if end > 0x200000 else 2


def plan(rom, doc, map_at, at=None):
    """→ (맵 쓰기, 상자 표 쓰기, 롬 크기, 상자 표 문서, 놓은 상자 [(BC, BD, 칸, 내용물)])."""
    start = lorom(map_at)
    if start < 0x180000 or (map_at >> 16) > 0x7D:
        raise ValueError('--map-at 은 늘린 롬(뱅크 30~7D) 자리여야 함')
    maps, placed, end = map_writes(rom, doc, start)
    # 4MB 롬의 파일 3F0000~ 은 뱅크 FE·FF 로만 보여, 레코드를 이어 읽는 리더가 뱅크 7E(WRAM)로 넘어간다
    if end > 0x3F0000:
        raise ValueError('맵 레코드가 뱅크 7D 끝(파일 3F0000)을 넘음')
    mb = mb_for(end)
    middle, _ = build(rom.d, [('chest-place maps', mb, maps)], mb)
    middle = Rom(middle)
    tables = reloc.parse(rom)
    rewards = cell_rewards(rom, tables)
    rows = {(row['group'], row['map']): row for row in tables['chest_maps']}
    new_cells = []
    added = []
    for (bc, bd), boxes, furniture, sizes in placed:
        before, after = set(chest_cells(rom, bc, bd)), chest_cells(middle, bc, bd)
        if boxes and (bc, bd) not in rows and before:
            raise ValueError(f'{bc:02X}/{bd:02X}: 표에 없는 맵인데 상자 칸 {len(before)}개가 이미 있음. 그 칸들의 '
                             '내용물을 정할 입력이 없어 받지 않음')
        footprint = {(box['x'] + i, box['y'] + j) for box in boxes + furniture
                     for i in range(sizes[box['block']][0]) for j in range(sizes[box['block']][1])}
        changed = changed_cells(rom.d, middle.d, bc, bd) - footprint
        if changed:
            raise ValueError(f'{bc:02X}/{bd:02X}: 놓은 블록 밖의 칸 {sorted(changed)[:8]} 이 바뀜(배치를 다시 짠 결과)')
        if before - set(after):
            raise ValueError(f'{bc:02X}/{bd:02X}: 블록이 기존 상자 칸 {sorted(before - set(after))} 을 지움')
        for k, box in enumerate(boxes):
            width, height = sizes[box['block']]
            new = [xy for xy in after if xy not in before
                   and box['x'] <= xy[0] < box['x'] + width and box['y'] <= xy[1] < box['y'] + height]
            if len(new) != 1:
                raise ValueError(f'{bc:02X}/{bd:02X} chests[{k}]: 블록 안에 새 상자 칸이 {len(new)}개(1개여야 함)')
            rewards[(bc, bd, new[0])] = box['reward']
            new_cells.append((bc, bd, new[0], box['reward']))
        if len(after) != len(before) + len(boxes):
            raise ValueError(f'{bc:02X}/{bd:02X}: 새 상자 칸 수가 놓은 블록 수와 다름')
        if (bc, bd) in rows:
            rows[(bc, bd)]['count'] = len(after)
        elif boxes:
            tables['chest_maps'].append({'group': bc, 'map': bd, 'count': len(after)})
        old_furniture, new_furniture = furniture_cells(rom.d, bc, bd), furniture_cells(middle.d, bc, bd)
        # 블록이 기존 서랍 항목의 칸을 덮으면 그 항목은 다른 그림 밑의 고아가 된다. 덮은 칸의 아래층 93 은 남을 수
        # 있어(17/00 (4,4)) 속성만으로는 못 가린다
        lost = sorted(xy for row in tables['search'] if (row['group'], row['map']) == (bc, bd)
                      for xy in [(row['x'], row['y'])] if xy in footprint or xy not in new_furniture or xy in after)
        if lost:
            raise ValueError(f'{bc:02X}/{bd:02X}: 블록이 기존 서랍 항목의 가구 칸 {lost} 을 덮거나 지움')
        # 발밑·두 칸 앞·아래층 상자는 칸 속성이 아니라 좌표로 찾으므로, 블록이 덮으면 보상이 그림 밑에 묻힌다
        buried = sorted((name, row['x'], row['y']) for name in ('foot', 'ahead', 'lower') for row in tables[name]
                        if (row['group'], row['map']) == (bc, bd) and (row['x'], row['y']) in footprint)
        if buried:
            raise ValueError(f'{bc:02X}/{bd:02X}: 블록이 기존 조사 항목 {buried} 의 칸을 덮음')
        used = set()
        for k, box in enumerate(furniture):
            width, height = sizes[box['block']]
            new = [xy for xy in new_furniture - old_furniture
                   if box['x'] <= xy[0] < box['x'] + width and box['y'] <= xy[1] < box['y'] + height]
            if len(new) != 1:
                raise ValueError(f'{bc:02X}/{bd:02X} furniture[{k}]: 블록 안에 새 가구 칸이 {len(new)}개(1개여야 함)')
            if new[0] in used:
                raise ValueError(f'{bc:02X}/{bd:02X} furniture[{k}]: 새 가구 칸 {new[0]} 을 다른 항목이 이미 씀')
            used.add(new[0])
            if integer(box['flag_index'], 255, 'flag_index') >= SEARCH_FLAGS:
                raise ValueError(f'{bc:02X}/{bd:02X} furniture[{k}]: flag_index 는 {SEARCH_FLAGS - 1:02X} 이하여야 함'
                                 f'(7E:222C~223F)')
            row = {'group': bc, 'map': bd, 'x': new[0][0], 'y': new[0][1], 'unused': box.get('unused', 1),
                   'reward': box['reward'], 'flag_index': box['flag_index'], 'mask': box['mask']}
            added.append(row)
    tables['chests'] = []
    for row in tables['chest_maps']:
        cells = chest_cells(middle, row['group'], row['map'])
        tables['chests'] += [{'reward': rewards[(row['group'], row['map'], xy)]} for xy in cells]
    taken = flag_bits(tables)
    for k, row in enumerate(added):
        reloc.row_encode('search', row, f'furniture {k}')
        bits = {(0x222C + row['flag_index'], bit) for bit in (1, 2, 4, 8, 16, 32, 64, 128) if row['mask'] & bit}
        if bits & taken:
            raise ValueError(f'{row["group"]:02X}/{row["map"]:02X} ({row["x"]},{row["y"]}): 열림 비트 '
                             f'7E:{0x222C + row["flag_index"]:04X} & {row["mask"]:02X} 를 다른 보상이 이미 씀')
        taken |= bits
    tables['search'] += added
    chest_writes, chest_mb = reloc.writes_for(middle, tables, at)
    record = (lorom(map_at), end)
    for addr, new, _, note in chest_writes:
        off = lorom(addr)
        if off < record[1] and off + len(new) > record[0]:
            raise ValueError(f'{note}: {reloc.cpu(addr)} 가 맵 레코드 자리와 겹침')
    return maps, chest_writes, max(mb, chest_mb), tables, new_cells


def patch(rom, doc, map_at, at=None):
    maps, chest_writes, mb, _, _ = plan(rom, doc, map_at, at)
    writes = [{'at': f'0x{off:X}' if off >= 0x180000 else file_cpu(off), 'hex': new.hex(' '),
               **({'orig': old.hex(' ')} if old is not None else {}), 'note': note} for off, new, old, note in maps]
    writes += [{'at': reloc.cpu(addr), 'hex': new.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}),
                'note': note} for addr, new, old, note in chest_writes]
    return {'format': 'dq5patch/1', 'name': 'chest-place', 'rom_size': mb, 'writes': writes}


def check(rom, doc, map_at, at=None):
    manifest = patch(rom, doc, map_at, at)
    writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    built, _ = build(rom.d, [('chest-place', manifest['rom_size'], writes)], manifest['rom_size'])
    built = Rom(built)
    _, _, _, tables, new_cells = plan(rom, doc, map_at, at)
    if reloc.parse(built) != tables:
        raise ValueError('만든 롬의 상자 표가 계획과 다름')
    reloc.check_cells(built, tables)
    # 원본에서 칸으로 모은 내용물과 만든 롬에서 칸으로 다시 모은 내용물이 같아야 한다(놓은 상자만 더해짐)
    want = cell_rewards(rom, reloc.parse(rom)) | {(bc, bd, xy): reward for bc, bd, xy, reward in new_cells}
    if cell_rewards(built, tables) != want:
        raise ValueError('만든 롬에서 칸마다 모은 상자 내용물이 원본과 놓은 상자를 합친 것과 다름')
    placed = len(new_cells)
    old = reloc.parse(rom)
    if tables['search'][:len(old['search'])] != old['search']:
        raise ValueError('기존 서랍 표 항목이 바뀜')
    open_cells = {}
    for row in tables['search']:
        key = (row['group'], row['map'])
        if key not in open_cells:
            open_cells[key] = furniture_cells(built.d, *key) - set(chest_cells(built, *key))
        if (row['x'], row['y']) not in open_cells[key]:
            raise ValueError(f'{key[0]:02X}/{key[1]:02X} ({row["x"]},{row["y"]}): 만든 롬에서 가구 칸이 아님')
    print(f'상자 {len(old["chests"])} → {len(tables["chests"])}개(놓은 {placed}개), '
          f'서랍 {len(old["search"])} → {len(tables["search"])}개, 맵 {len(doc["maps"])}곳; '
          f'쓰기 {len(writes)}개, 롬 {manifest["rom_size"]}MB 검사 통과')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    write = sub.add_parser('patch')
    write.add_argument('source', type=Path)
    write.add_argument('-o', '--out', type=Path, required=True)
    verify = sub.add_parser('check')
    verify.add_argument('source', type=Path)
    for p in (write, verify):
        p.add_argument('--map-at', type=reloc.address, required=True, help='맵 레코드를 놓을 늘린 롬 자리')
        for name in reloc.ORIGINAL:
            p.add_argument(f'--{name.replace("_", "-")}-at', dest=f'{name}_at', type=reloc.address)
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8'))
        at = {k: getattr(args, f'{k}_at') for k in reloc.ORIGINAL}
        if args.command == 'check':
            check(rom, doc, args.map_at, at)
        else:
            result = patch(rom, doc, args.map_at, at)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f'patch → {args.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
