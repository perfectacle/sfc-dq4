"""DQ5 실내 맵에 보물상자·가구를 놓고, 그 내용물을 보상 표에 함께 넣는다.

sfc/dq5/docs/dq5-build-format.md 의 「보물상자 놓기」. 맵마다 상자 블록 배치를 더해 맵 레코드를 다시 싸고
(dq5mapcompile·dq5mapwrite), 그 롬에서 셀 버퍼를 다시 풀어 상자 칸(+7 = 84) 순서를 센다. 상자 번호는 맵 셀 순서로
정해지므로(25:FAB0), 기존 상자의 내용물은 좌표로 따라가게 상자 내용물·맵 연결 표를 다시 짜서 dq5chestreloc 로 쓴다.
가구(タンス·ツボ·タル)는 블록 안에 새로 생긴 가구 칸(+4 = 93, +7 = A7·B9 등)을 찾아 서랍 표 끝에 항목을 더한다.
결과는 맵 레코드와 상자 표를 함께 담은 dq5patch/1 하나다.

  python sfc/dq5/tools/dq5chestplace.py rom/dq5.sfc patch work/place.json -o work/place.dq5patch.json \\
      --map-at BB:AAAA [--chests-at BB:AAAA] [--chest-maps-at BB:AAAA]
  python sfc/dq5/tools/dq5chestplace.py rom/dq5.sfc check work/place.json --map-at … [같은 자리 선택]
--tables 로 dq5chestreloc.py dump 를 고친 표(표에 없던 맵의 상자 연결, 옮긴 열림 비트 등)를 바탕으로 줄 수 있다.

입력 format=dq5chestplace/1, maps[{map:"GG/MM", chests[{x,y,block,reward}],
furniture[{x,y,block,reward,flag_index,mask[,unused]}]}]. x·y 는 블록 원점(왼쪽 위), block 은 실내 맵 블록 번호다.
블록이 놓인 칸 안에 상자 칸(가구 칸)이 하나 새로 생겨야 한다.
원래 롬에 없는 맵(dq5newmap.py 로 더하는 맵)은 --new-map GG/MM 과 그 맵을 더하는 패치 목록 --with-patch 로 알린다.
그 맵의 레코드는 그 패치가 쓰므로 블록을 놓지 않고, block 없이 x·y 에 레코드에 이미 있는 상자 칸·가구 칸을 적는다.
기존 맵(새 맵을 이미 붙인 롬의 새 맵 포함)도 모든 항목에 block 을 빼면 같이 적는다. 상자는 그 맵의 상자 칸을 모두
적어야 하고, 블록을 놓는 맵이 없으면 --map-at 은 주지 않아도 된다. --with-patch 를 주면 기존 맵의 칸·블록도 그 패치를
붙인 롬에서 읽는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import dq5chestreloc as reloc
from dq5build import PatchError, build, cpu as file_cpu, parse_at
from dq5chest import chests
from dq5chestwrite import NO_NEW_MAPS, NewMaps, fields, integer, map_dimensions
from dq5map import Rom, lorom, map_pointer
from dq5mapcompile import block_sizes, cell_buffer, compile_places, extract
from dq5mapwrite import all_maps, encode, pointer_addr, to_cpu

FORMAT = 'dq5chestplace/1'
# 서랍 표 86항목이 놓인 칸의 속성. タンス 는 아래층(+4) 93, ツボ·タル 는 위층(+7) A7·B9 였다. D3·D4 는 위층에만 있는
# タル·ツボ 칸으로, 게임에서 149·135 메시지를 확인했다(dq5-map-format.md)
LOWER_FURNITURE = {0x93}
UPPER_FURNITURE = {0xA7, 0xB9, 0xD3, 0xD4}
# 아래층 상자 표는 12:ED62 가 $BC 32 이상일 때만 찾는다. 그보다 앞 그룹에서는 항목이 있어도 읽히지 않는다
LOWER_FIRST = 0x32
BOX_FIELDS = {'x', 'y', 'block', 'reward'}
FURNITURE_FIELDS = BOX_FIELDS | {'flag_index', 'mask'}
# 블록 없이 적는 맵(새 맵 등)은 레코드에 이미 있는 칸을 적는다
NEW_BOX_FIELDS = BOX_FIELDS - {'block'}
NEW_FURNITURE_FIELDS = FURNITURE_FIELDS - {'block'}


def map_key(text, label):
    if not isinstance(text, str) or not re.fullmatch(r'[0-9A-Fa-f]{2}/[0-9A-Fa-f]{2}', text):
        raise ValueError(f'{label}: map 은 GG/MM 이어야 함')
    return tuple(int(v, 16) for v in text.split('/'))


def chest_cells(rom, bc, bd):
    return [xy for _, xy, _ in chests(rom, bc, bd, 0)]


def new_map_rows(item, label, view, key):
    """블록 없이 적은 맵 항목의 chests·furniture. 레코드에 있는 칸 좌표와 보상만 받는다."""
    width, height = map_dimensions(view, *key)
    for kind, need in (('chests', NEW_BOX_FIELDS), ('furniture', NEW_FURNITURE_FIELDS)):
        for k, box in enumerate(item.get(kind, [])):
            where = f'{label}.{kind}[{k}]'
            fields(box, need | ({'unused'} if kind == 'furniture' else set()), where)
            if need - set(box):
                raise ValueError(f'{where}: {sorted(need)} 를 모두 적어야 함')
            if integer(box['x'], 255, 'x') >= width or integer(box['y'], 255, 'y') >= height:
                raise ValueError(f'{where}: 칸이 맵 {width}×{height} 밖')
            if kind == 'chests':
                reloc.row_encode('chests', {'reward': box['reward']}, f'{where}.reward')


def map_writes(rom, doc, at, new_maps=NO_NEW_MAPS):
    """맵마다 상자 블록을 더한 레코드를 늘린 자리 at(파일 위치)부터 놓는다. (쓰기, 맵별 새 상자 목록, 끝 위치, 새 맵 항목).
    블록 없이 적은 맵(새 맵은 늘)은 레코드를 쓰지 않고 [(맵, 상자, 가구)] 로 따로 돌려준다."""
    fields(doc, {'format', 'maps'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('maps'), list) or not doc['maps']:
        raise ValueError(f'format={FORMAT} 과 비지 않은 maps 배열이 필요함')
    known, writes, placed, fresh, seen = set(all_maps(rom)), [], [], [], set()
    for i, item in enumerate(doc['maps']):
        label = f'maps[{i}]'
        fields(item, {'map', 'chests', 'furniture'}, label)
        bc, bd = map_key(item.get('map'), label)
        if (bc, bd) not in known | new_maps.keys or bc >= 0x50:
            raise ValueError(f'{label}: 일반 실내 맵(그룹 50 미만)만 받음(새 맵은 --new-map 으로 알림)')
        if (bc, bd) in seen:
            raise ValueError(f'{label}: 같은 맵을 두 번 적음')
        seen.add((bc, bd))
        boxes, furniture = item.get('chests', []), item.get('furniture', [])
        if not isinstance(boxes, list) or not isinstance(furniture, list) or not boxes + furniture:
            raise ValueError(f'{label}: chests·furniture 는 배열이고 둘 중 하나는 비지 않아야 함')
        blocks = [isinstance(box, dict) and 'block' in box for box in boxes + furniture]
        # 블록 없이 적은 맵은 레코드에 이미 있는 칸에 보상을 단다. 새 맵은 레코드를 --with-patch 의 패치가 쓰므로 늘 이렇다
        if (bc, bd) in new_maps.keys or not any(blocks):
            if any(blocks) and (bc, bd) in new_maps.keys:
                raise ValueError(f'{label}: 새 맵의 레코드는 --with-patch 의 패치가 쓰므로 block 을 놓지 않음(칸 x·y 만 적음)')
            new_map_rows(item, label, new_maps.rom_for(rom, (bc, bd)), (bc, bd))
            fresh.append(((bc, bd), boxes, furniture))
            continue
        if not all(blocks):
            raise ValueError(f'{label}: 한 맵에 block 을 적은 항목과 적지 않은 항목을 섞지 않음')
        if at is None:
            raise ValueError(f'{label}: 기존 맵에 블록을 놓으려면 --map-at 이 필요함')
        # 블록과 레코드는 --with-patch 를 붙인 롬에서 읽는다(환경 패치가 블록을 바꿀 수 있음). 포인터는 원래 롬 자리에
        # 쓰므로, 그 패치가 맵 포인터 목록을 옮겼거나 이 맵의 포인터를 바꿨으면 이 패치가 읽히지 않는다
        view = new_maps.rom_for(rom, (bc, bd))
        pointer = lorom(pointer_addr(rom, bc, bd))
        if view is not rom and (lorom(pointer_addr(view, bc, bd)) != pointer
                                or view.d[pointer:pointer + 3] != rom.d[pointer:pointer + 3]):
            raise ValueError(f'{label}: --with-patch 의 패치가 맵 {bc:02X}/{bd:02X} 의 포인터 자리나 값을 바꿈'
                             '(맵 포인터 목록을 옮긴 새 맵 패치와는 기존 맵에 블록을 놓을 수 없음)')
        src = extract(view, bc, bd)
        sizes = block_sizes(view, False)
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
        record = encode(compile_places(src, view, False))
        writes.append((at, record, None, f'map {bc:02X}/{bd:02X}'))
        writes.append((pointer, to_cpu(at).to_bytes(3, 'little'), bytes(rom.d[pointer:pointer + 3]),
                       f'map {bc:02X}/{bd:02X} 포인터'))
        placed.append(((bc, bd), boxes, furniture, sizes))
        at += len(record)
    return writes, placed, at, fresh


def cell_rewards(rom, tables, new_maps=NO_NEW_MAPS):
    """(BC, BD, 칸) → 내용물. 맵의 상자 칸 수가 등록 개수와 다르면 번호가 어긋나므로 거부한다."""
    out, start = {}, 0
    for row in tables['chest_maps']:
        cells = chest_cells(new_maps.rom_for(rom, (row['group'], row['map'])), row['group'], row['map'])
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


def changed_cells(before, after, bc, bd):
    width = map_dimensions(Rom(before), bc, bd)[0]
    old, _ = cell_buffer(before, bc, bd)
    new, _ = cell_buffer(after, bc, bd)
    return {(i % width, i // width) for i, (a, b) in enumerate(zip(old, new)) if a != b}


def mb_for(end):
    return 4 if end > 0x300000 else 3 if end > 0x200000 else 2


def plan(rom, doc, map_at, at=None, base=None, new_maps=NO_NEW_MAPS):
    """→ (맵 쓰기, 상자 표 쓰기, 롬 크기, 상자 표 문서, 놓은 상자 [(BC, BD, 칸, 내용물)])."""
    start = None if map_at is None else lorom(map_at)
    if map_at is not None and (start < 0x180000 or (map_at >> 16) > 0x7D):
        raise ValueError('--map-at 은 늘린 롬(뱅크 30~7D) 자리여야 함')
    maps, placed, end, fresh = map_writes(rom, doc, start, new_maps)
    # 4MB 롬의 파일 3F0000~ 은 뱅크 FE·FF 로만 보여, 레코드를 이어 읽는 리더가 뱅크 7E(WRAM)로 넘어간다
    if maps and end > 0x3F0000:
        raise ValueError('맵 레코드가 뱅크 7D 끝(파일 3F0000)을 넘음')
    if maps and not reloc.unused(rom.d, start, end):
        raise ValueError(f'--map-at: 늘린 롬의 {file_cpu(start)}~ 에 이미 다른 자료가 있음')
    mb = max(mb_for(end), reloc.rom_mb(rom)) if maps else 0
    middle = Rom(build(rom.d, [('chest-place maps', mb, maps)], mb)[0]) if maps else rom
    # 칸은 --with-patch 를 붙인 롬(view)에서 세고, 레코드를 다시 싼 뒤는 그 롬에 맵 쓰기까지 붙인 롬(seen)에서 센다
    view = new_maps.rom_for(rom, None)
    seen = new_maps.merged(rom, [('chest-place maps', mb, maps)], mb) if new_maps.keys and maps else \
        view if new_maps.keys else middle
    if base is not None:
        # 바탕 표는 원래 롬의 맵 칸과 맞아야 상자 내용물을 칸으로 따라가게 할 수 있다
        reloc.serialize(rom, base, new_maps)
        reloc.check_cells(rom, base, new_maps)
    tables = json.loads(json.dumps(base)) if base is not None else reloc.parse(rom)
    rewards = cell_rewards(rom, tables, new_maps)
    rows = {(row['group'], row['map']): row for row in tables['chest_maps']}
    new_cells = []
    added = []
    for (bc, bd), boxes, furniture, sizes in placed:
        before, after = set(chest_cells(view, bc, bd)), chest_cells(seen, bc, bd)
        if boxes and (bc, bd) not in rows and before:
            raise ValueError(f'{bc:02X}/{bd:02X}: 표에 없는 맵인데 상자 칸 {len(before)}개가 이미 있음. 그 칸들의 '
                             '내용물을 정할 입력이 없어 받지 않음')
        footprint = {(box['x'] + i, box['y'] + j) for box in boxes + furniture
                     for i in range(sizes[box['block']][0]) for j in range(sizes[box['block']][1])}
        changed = changed_cells(view.d, seen.d, bc, bd) - footprint
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
        old_furniture, new_furniture = furniture_cells(view.d, bc, bd), furniture_cells(seen.d, bc, bd)
        # 블록이 기존 서랍 항목의 칸을 덮으면 그 항목은 다른 그림 밑의 고아가 된다. 덮은 칸의 아래층 93 은 남을 수
        # 있어(17/00 (4,4)) 속성만으로는 못 가린다
        lost = sorted(xy for row in tables['search'] if (row['group'], row['map']) == (bc, bd)
                      for xy in [(row['x'], row['y'])] if xy in footprint or xy not in new_furniture or xy in after)
        if lost:
            raise ValueError(f'{bc:02X}/{bd:02X}: 블록이 기존 서랍 항목의 가구 칸 {lost} 을 덮거나 지움')
        # 발밑·두 칸 앞·아래층 상자는 칸 속성이 아니라 좌표로 찾으므로, 블록이 덮으면 보상이 그림 밑에 묻힌다
        names = ('foot', 'ahead', 'lower') if bc >= LOWER_FIRST else ('foot', 'ahead')
        buried = sorted((name, row['x'], row['y']) for name in names for row in tables[name]
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
            integer(box['flag_index'], 255, 'flag_index')
            row = {'group': bc, 'map': bd, 'x': new[0][0], 'y': new[0][1], 'unused': box.get('unused', 1),
                   'reward': box['reward'], 'flag_index': box['flag_index'], 'mask': box['mask']}
            added.append(row)
    for (bc, bd), boxes, furniture in fresh:
        cells = chest_cells(seen, bc, bd)
        given = [(box['x'], box['y']) for box in boxes]
        # 상자는 맵 연결 하나에 그 맵의 상자 칸 전부를 셀 순서로 매기므로, 적으면 모두 적는다. 새 맵은 상자 칸이 있으면
        # 늘 적어야 한다. 가구만 적으면 기존 상자 연결·서랍 항목은 그대로 두고 서랍 표 끝에 붙인다
        if boxes or (bc, bd) in new_maps.keys:
            if (bc, bd) in rows:
                raise ValueError(f'{bc:02X}/{bd:02X}: 바탕 표에 이미 상자 연결이 있는 맵. 블록 없이 적는 맵의 상자는 '
                                 '한 입력에 모두 적음')
            if len(set(given)) != len(given) or set(given) != set(cells):
                raise ValueError(f'{bc:02X}/{bd:02X}: 맵의 상자 칸 {cells} 을 모두 한 번씩 적어야 함(적은 칸 {given})')
            for box in boxes:
                rewards[(bc, bd, (box['x'], box['y']))] = box['reward']
            # 상자 번호는 셀 순서로 매기므로 적은 순서가 아니라 칸 순서로 둔다
            new_cells += [(bc, bd, xy, rewards[(bc, bd, xy)]) for xy in cells]
            if cells:
                tables['chest_maps'].append({'group': bc, 'map': bd, 'count': len(cells)})
        listed = {(row['x'], row['y']) for row in tables['search'] if (row['group'], row['map']) == (bc, bd)}
        open_cells, used = furniture_cells(seen.d, bc, bd) - set(cells), set()
        for k, box in enumerate(furniture):
            xy = (box['x'], box['y'])
            if xy not in open_cells:
                raise ValueError(f'{bc:02X}/{bd:02X} furniture[{k}]: 칸 {xy} 이 상자 아닌 가구 칸(+4 = 93 이나 +7 = '
                                 'A7·B9·D3·D4)이 아님')
            if xy in used or xy in listed:
                raise ValueError(f'{bc:02X}/{bd:02X} furniture[{k}]: 가구 칸 {xy} 을 두 번 적거나 이미 서랍 항목이 있음')
            used.add(xy)
            integer(box['flag_index'], 255, 'flag_index')
            added.append({'group': bc, 'map': bd, 'x': xy[0], 'y': xy[1], 'unused': box.get('unused', 1),
                          'reward': box['reward'], 'flag_index': box['flag_index'], 'mask': box['mask']})
    tables['chests'] = []
    for row in tables['chest_maps']:
        cells = chest_cells(seen, row['group'], row['map'])
        tables['chests'] += [{'reward': rewards[(row['group'], row['map'], xy)]} for xy in cells]
    taken = set(reloc.flag_bits(tables))
    for k, row in enumerate(added):
        reloc.row_encode('search', row, f'furniture {k}')
        addr = reloc.FLAG_BASE['search'][0] + row['flag_index']
        bits = {(addr, bit) for bit in (1, 2, 4, 8, 16, 32, 64, 128) if row['mask'] & bit}
        if bits & taken:
            raise ValueError(f'{row["group"]:02X}/{row["map"]:02X} ({row["x"]},{row["y"]}): 열림 비트 '
                             f'7E:{addr:04X} & {row["mask"]:02X} 를 다른 보상이 이미 씀')
        taken |= bits
    tables['search'] += added
    chest_writes, chest_mb = reloc.writes_for(middle, tables, at, new_maps.viewing(seen) if new_maps.keys else new_maps,
                                              rom)
    for addr, data, _, note in chest_writes if maps else ():
        off = lorom(addr)
        if off < end and off + len(data) > start:
            raise ValueError(f'{note}: {reloc.cpu(addr)} 가 맵 레코드 자리와 겹침')
    return maps, chest_writes, max(mb, chest_mb), tables, new_cells


def manifest_writes(manifest):
    return [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
             w['note']) for w in manifest['writes']]


def patch(rom, doc, map_at, at=None, base=None, new_maps=NO_NEW_MAPS):
    maps, chest_writes, mb, _, _ = plan(rom, doc, map_at, at, base, new_maps)
    writes = [{'at': f'0x{off:X}' if off >= 0x180000 else file_cpu(off), 'hex': data.hex(' '),
               **({'orig': old.hex(' ')} if old is not None else {}), 'note': note} for off, data, old, note in maps]
    writes += [{'at': reloc.cpu(addr), 'hex': data.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}),
                'note': note} for addr, data, old, note in chest_writes]
    result = {'format': 'dq5patch/1', 'name': 'chest-place', 'rom_size': mb, 'writes': writes}
    if new_maps.keys:
        new_maps.merged(rom, [('chest-place', mb, manifest_writes(result))], mb)
    return result


def check(rom, doc, map_at, at=None, base=None, new_maps=NO_NEW_MAPS):
    manifest = patch(rom, doc, map_at, at, base, new_maps)
    writes = manifest_writes(manifest)
    # 새 맵은 --with-patch 와 함께 빌드한 롬에만 있으므로, 그 롬에서 다시 읽는다
    built = new_maps.merged(rom, [('chest-place', manifest['rom_size'], writes)], manifest['rom_size'])
    _, _, _, tables, new_cells = plan(rom, doc, map_at, at, base, new_maps)
    if reloc.parse(built) != tables:
        raise ValueError('만든 롬의 상자 표가 계획과 다름')
    reloc.check_cells(built, tables)
    # 원본에서 칸으로 모은 내용물과 만든 롬에서 칸으로 다시 모은 내용물이 같아야 한다(놓은 상자만 더해짐)
    old = base if base is not None else reloc.parse(rom)
    want = cell_rewards(rom, old, new_maps) | {(bc, bd, xy): reward for bc, bd, xy, reward in new_cells}
    if cell_rewards(built, tables) != want:
        raise ValueError('만든 롬에서 칸마다 모은 상자 내용물이 원본과 놓은 상자를 합친 것과 다름')
    placed = len(new_cells)
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
          f'쓰기 {len(writes)}개, 롬 {manifest["rom_size"] or 1.5}MB 검사 통과')


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
        p.add_argument('--map-at', type=reloc.address, help='맵 레코드를 놓을 늘린 롬 자리(기존 맵에 블록을 놓을 때)')
        p.add_argument('--tables', type=Path, help='롬의 표 대신 바탕으로 삼을 dq5chesttables/1(dq5chestreloc.py dump 를 고친 것)')
        for name in reloc.ORIGINAL:
            p.add_argument(f'--{name.replace("_", "-")}-at', dest=f'{name}_at', type=reloc.address)
        p.add_argument('--new-map', action='append', default=[], type=reloc.new_map,
                       help='dq5newmap.py 로 함께 더하는 새 맵 GG/MM(여럿이면 되풀이)')
        p.add_argument('--with-patch', action='append', default=[], type=Path,
                       help='새 맵을 더하는 패치 목록(dq5patch/1). 새 맵을 이 목록들을 붙인 롬에서 읽음')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8'))
        at = {k: getattr(args, f'{k}_at') for k in reloc.ORIGINAL}
        base = json.loads(args.tables.read_text(encoding='utf-8')) if args.tables else None
        new_maps = NewMaps(rom, args.new_map, args.with_patch)
        if args.command == 'check':
            check(rom, doc, args.map_at, at, base, new_maps)
        else:
            result = patch(rom, doc, args.map_at, at, base, new_maps)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f'patch → {args.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError, PatchError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
