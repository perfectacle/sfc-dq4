"""DQ5 보물상자·조사 보상의 고정 표 쓰기.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식(25:FAB0, 12:FB9D·E6BE·FCDD·FD46)과 필드 조사(12:E5F2·01:9FF9).
일반 상자의 좌표와 열림 비트는 맵 셀 순서·상자 번호에서 나온다. chest_maps는
기존 맵 슬롯의 연결/개수만 바꾸며 총 상자 수를 유지한다. 나머지 표는 좌표·보상·
플래그를 직접 바꾼다. 검색 우선순위·목록 길이·미사용 바이트·종료자는 보존한다. field는
조사 코드와 빛 블록 코드에 박힌 칸·보상·열림 플래그 즉시값을 같은 길이로 함께 바꾼다.

  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc dump -o work/chests.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc patch work/chests.json -o work/chests.patch.json
  python sfc/dq5/tools/dq5chestwrite.py rom/dq5.sfc check [work/chests.json]

JSON format=dq5chest/1. chests[{index,reward}], chest_maps[{index,group,map,count}],
search/foot/ahead/lower[{index,group,map,x,y,reward,flag_index,mask}]. foot만 layer를 받는다.
field[{index:0,x,y,width,height,reward,flag_index,mask}]: 필드 8픽셀 칸, x·y 짝수, 크기 2×2 고정.
모든 수치는 JSON 정수, reward는 원본 16비트 부호다. index 외 필드는 생략할 수 있다.
원래 롬에 없는 맵(dq5newmap.py 로 더하는 맵)에 항목을 옮길 때는 patch·check 에 --new-map GG/MM 과 그 맵을 더하는
패치 목록 --with-patch 를 준다(dq5chestreloc.py 와 같은 뜻).
"""
import argparse
import json
import sys
from pathlib import Path

from dq5build import PatchError, build, load
from dq5chest import (AHEAD_TABLE, CHEST_ITEMS, CHEST_MAPS, FOOT_TABLE, LOWER_TABLE,
                      SEARCH_TABLE, chests)
from dq5fieldwrite import world_grid
from dq5gfx import map_ids
from dq5map import Rom, lorom, map_pointer
from dq5palsetwrite import new_map

FORMAT = 'dq5chest/1'
TABLES = {'chests': (CHEST_ITEMS, 161, 2), 'chest_maps': (CHEST_MAPS, 83, 3),
          'search': (SEARCH_TABLE, 86, 9), 'foot': (FOOT_TABLE, 18, 9),
          'ahead': (AHEAD_TABLE, 17, 8), 'lower': (LOWER_TABLE, 11, 8)}
SECTIONS = {*TABLES, 'field'}
FIELD_CALL = 0x12E5A7
# 필드 조사 보상 한 곳을 쓰는 코드 세 조각. 16진은 그대로 있어야 하는 명령 바이트이고, 이름 붙은 자리는
# 즉시값이다(소문자 a·b 도 이름). 같은 이름은 같은 값이어야 한다(x·y 칸, X·Y 끝(미포함), r 보상, i·m 열림 플래그 번호·마스크,
# a 그 플래그의 주소 2190+i, b 빛이 꺼질 때 되돌릴 세계 0 블록). 끝 숫자는 하위·상위 바이트
FIELD_PIECES = (
    # 12:E5F2 조사: 밤 빛(21A5.2)·칸·열림 시험·21AA.0 을 보고 보상과 열림 플래그를 넘김
    (0x12E5F2, 'C2 20 00 0B 04 15 F0 3D A5 B6 C9 x0 x1 90 36 C9 X0 X1 B0 31 A5 B8 C9 y0 y1 90 2A C9 Y0 Y1 '
               'B0 25 00 0B m0 i0 D0 1F 00 0B 01 1A F0 19 A9 r0 r1 8D 73 1E E2 20 A9 i0 8D 80 1E A9 m0 8D 81 1E'),
    # 01:9FF9 필드에 들어갈 때 밤이면 빛 블록 A7 을 놓고(01:A011), 01:A02B 는 끄고 블록 b 로 되돌림
    (0x019FF9, '00 0B m0 i0 D0 0F 00 0B 01 1A F0 09 22 00 80 21 90 03 20 11 A0 AB 28 60 08 C2 30 00 0C 04 15 '
               'A9 A7 00 A2 x0 x1 86 90 A2 y0 y1 86 92 22 50 CF 00 28 60 08 C2 30 00 0D FB 15 A9 b0 b1 80'),
    # 01:A05D 8프레임마다(02:AD3D) 낮밤이 바뀌면 빛을 켜고 끔
    (0x01A05D, 'AF a0 a1 7E 29 m0 D0 25 AF AA 21 7E 29 01 F0 1D'),
    # 12:EFB9 조사 종류 1(12:EF92)이 보상을 준 뒤 그 값이 r 이면 빛 칸을 블록 b 로 되돌림. 칸이 아니라 보상 값만 봄
    (0x12EFB9, 'AD 73 1E C9 r0 r1 D0 11 A9 x0 x1 85 90 A9 y0 y1 85 92 A9 b0 b1 22 50 CF 00'),
)
FIELD_TEMPLATE = [token for _, text in FIELD_PIECES for token in text.split()]
FIELD_ADDRS = [addr + i for addr, text in FIELD_PIECES for i in range(len(text.split()))]
FIELD_CODE = FIELD_PIECES[0][0]
FIELD_LAST = 510
# 12:E5F2 의 조건과 빛 표시. 열림 플래그로 쓰면 보상이 스스로를 막음
FIELD_RESERVED = ((0x15, 0x04), (0x1A, 0x01))

def light_clash(foot, reward):
    """발밑 항목도 조사 종류 1 로 12:EFB9 를 지나므로, 보상이 필드 조사와 같으면 실내에서도 지금 맵 버퍼의 빛 칸을 덮는다."""
    clash = [row.get('index', i) for i, row in enumerate(foot) if row['reward'] == reward]
    if clash:
        raise ValueError(f'foot {clash[0]}: 보상 {reward:04X} 가 필드 조사와 같아 줍는 곳에서 12:EFB9 가 빛 칸을 되돌림')


def field_reward(rom):
    """필드 조사 코드가 이 도구의 꼴이면 그 보상, 다른 패치로 바뀌었으면 None."""
    try:
        return decode_field(read_field(rom))['reward']
    except ValueError:
        return None


def integer(value, maximum, field):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{field}: 0~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 객체여야 함')


def read(rom, addr, size):
    raw = bytes(rom.d[lorom(addr):lorom(addr) + size])
    if len(raw) != size:
        raise ValueError(f'{addr:06X}: 롬 범위 밖')
    return raw


def named(token):
    if token[0] in 'xXyYrimab' and token[1:] in ('0', '1'):
        return True
    assert all(c in '0123456789ABCDEF' for c in token), token
    return False


def read_field(rom):
    if read(rom, FIELD_CALL, 3) != bytes.fromhex('20 F2 E5'):
        raise ValueError('field: 12:E5A7 이 12:E5F2 를 부르지 않음')
    raw = b''.join(read(rom, addr, len(text.split())) for addr, text in FIELD_PIECES)
    for i, token in enumerate(FIELD_TEMPLATE):
        if not named(token) and raw[i] != int(token, 16):
            raise ValueError(f'field: {FIELD_ADDRS[i] >> 16:02X}:{FIELD_ADDRS[i] & 0xFFFF:04X} 명령 바이트가 다름')
    decode_field(raw)
    return raw


def field_bytes(raw):
    pick = {}
    for token, value in zip(FIELD_TEMPLATE, raw):
        if named(token) and pick.setdefault(token, value) != value:
            raise ValueError(f'field: 같은 값이어야 하는 즉시값 {token[0]}이 조각마다 다름')
    return pick


def decode_field(raw):
    pick = field_bytes(raw)
    word = lambda key: pick[key + '0'] | pick[key + '1'] << 8
    x, y = word('x'), word('y')
    if (word('X'), word('Y')) != (x + 2, y + 2) or x % 2 or y % 2 or word('a') != 0x2190 + pick['i0']:
        raise ValueError('field: 칸이 블록 한 칸(2×2)이 아니거나 열림 플래그 주소가 번호와 다름')
    return {'x': x, 'y': y, 'width': 2, 'height': 2, 'reward': word('r'), 'flag_index': pick['i0'],
            'mask': pick['m0']}


def world_block(rom, x, y):
    # 세계 지도 쓰기가 덩어리를 옮겼을 수 있으므로 불러오기 루틴(01:A5C2)이 가리키는 곳과 10번째 비트 평면을 읽는다
    return world_grid(rom, 0)[(y // 2) * 256 + x // 2]


def encode_field(raw, changes, block_at):
    """block_at(x, y) 는 그 칸의 세계 0 블록(빛이 꺼질 때 되돌릴 값)."""
    old = decode_field(raw)
    fields(changes, set(old), 'field')
    value = old | changes
    for key in ('x', 'y'):
        if integer(value[key], FIELD_LAST, key) % 2:
            raise ValueError(f'field: {key}는 블록 경계(짝수)여야 함')
    if (value['width'], value['height']) != (2, 2):
        raise ValueError('field: width·height는 빛 블록 한 칸인 2만 받음')
    if integer(value['reward'], 65535, 'reward') > 0xCFFF:
        raise ValueError('field: reward는 물건(0000~00FF)·금화(0100~CFFF)만 받음')
    # 7E:2210 부터는 상자·서랍 열림 비트라, 이야기 플래그 자리(2190~220F)만 받는다
    integer(value['flag_index'], 0x7F, 'flag_index')
    if integer(value['mask'], 255, 'mask') == 0:
        raise ValueError('field: mask는 1~255여야 함')
    if any(value['flag_index'] == i and value['mask'] & m for i, m in FIELD_RESERVED):
        raise ValueError('field: 열림 플래그가 조건 21A5.2·21AA.0 과 겹침')
    # 칸을 옮기지 않아도 세계 지도 쓰기가 그 자리 블록을 바꿨을 수 있으므로 늘 다시 읽는다
    block = block_at(value['x'], value['y'])
    # 빛이 꺼질 때 00:CF50 이 되돌리는 블록은 9번째 비트까지라(10번째 비트 평면은 롬) 512 이상 칸은 되돌리지 못한다
    if block >= 512:
        raise ValueError(f'field: ({value["x"]},{value["y"]}) 의 세계 0 블록 {block} 이 512 이상이라 빛 칸으로 쓸 수 없음')
    words = {'x': value['x'], 'X': value['x'] + 2, 'y': value['y'], 'Y': value['y'] + 2, 'r': value['reward'],
             'i': value['flag_index'], 'm': value['mask'], 'a': 0x2190 + value['flag_index'], 'b': block}
    return bytes(words[token[0]] >> (8 * int(token[1])) & 0xFF if named(token) else raw[i]
                 for i, token in enumerate(FIELD_TEMPLATE))


def layout(rom):
    # 표를 옮긴 롬의 원래 자리는 엔진이 읽지 않으므로, 고정 표 쓰기가 그 자리를 고치면 아무 효과가 없다
    from dq5chestreloc import ORIGINAL, locate
    if locate(rom) != ORIGINAL:
        raise ValueError('표를 옮긴 롬임. dq5chestreloc.py 로 고쳐야 함')
    for name, (start, count, size) in TABLES.items():
        read(rom, start, count * size)
        if name == 'chests':
            continue
        if read(rom, start + count * size, 2) != b'\xff\xff':
            raise ValueError(f'{name}: 고정 종료자가 FFFF가 아님')
        if any(read(rom, start + i * size, 2) == b'\xff\xff' for i in range(count)):
            raise ValueError(f'{name}: 표 안에 이른 종료자가 있음')


def decode(name, raw):
    if name == 'chests':
        return {'reward': int.from_bytes(raw, 'little')}
    if name == 'chest_maps':
        return dict(zip(('group', 'map', 'count'), raw))
    v = dict(zip(('group', 'map', 'x', 'y'), raw[:4]))
    offset = 5 if len(raw) == 9 else 4
    if name == 'foot':
        v['layer'] = raw[4]
    v.update(reward=int.from_bytes(raw[offset:offset + 2], 'little'),
             flag_index=raw[-2], mask=raw[-1])
    return v


def encode(name, raw, changes):
    value = decode(name, raw) | changes
    fields(changes, set(decode(name, raw)), name)
    for key, v in value.items():
        integer(v, 65535 if key == 'reward' else 255, key)
    if 'reward' in value and not (value['reward'] <= 0xD009 or value['reward'] >= 0xFFFC):
        raise ValueError('reward: D00A~FFFB는 보상 처리기가 지원하지 않음')
    if 'mask' in value and value['mask'] == 0:
        raise ValueError('mask: 열림을 기록할 비트가 필요함')
    out = bytearray(raw)
    if name == 'chests':
        return value['reward'].to_bytes(2, 'little')
    out[0:2] = bytes([value['group'], value['map']])
    if name == 'chest_maps':
        out[2] = value['count']
        return bytes(out)
    out[2:4] = bytes([value['x'], value['y']])
    offset = 5 if len(raw) == 9 else 4
    if name == 'foot':
        out[4] = value['layer']
    out[offset:offset + 2] = value['reward'].to_bytes(2, 'little')
    out[-2:] = bytes([value['flag_index'], value['mask']])
    return bytes(out)


def dump(rom, field=True):
    layout(rom)
    # 필드 코드가 다른 패치로 바뀐 롬에서도 표만 고치는 입력은 받도록, field 를 쓰지 않으면 읽지 않는다
    doc = {'format': FORMAT, **{name: [{'index': i, **decode(name, read(rom, start + i * size, size))}
                                       for i in range(count)] for name, (start, count, size) in TABLES.items()}}
    if field:
        doc['field'] = [{'index': 0, **decode_field(read_field(rom))}]
    return doc


def map_dimensions(rom, group, map_number):
    addr = map_pointer(rom, group, map_number)
    return tuple(read(rom, addr + 1, 2))


class NewMaps:
    """--new-map 으로 알린 원래 롬에 없는 맵과, 그 맵을 읽을 롬. 새 맵 레코드는 다른 도구(dq5newmap.py)의 패치가 쓰므로
    그 패치 목록(--with-patch)을 원래 롬에 붙여 빌드한 롬에서 크기·상자 칸을 읽는다. 그 목록의 다른 패치(환경 패치 등)가
    기존 맵의 블록을 바꿀 수 있으므로 기존 맵의 칸도 그 롬에서 읽는다. 상자 도구의 패치도 그 목록과
    한 빌드로 합쳐 보아(merged) 겹침을 거부한다."""

    def __init__(self, rom, keys=(), patches=()):
        keys, patches = list(keys), list(patches)
        self.keys, self.lists, self.view = set(keys), [], rom
        if len(self.keys) != len(keys):
            raise ValueError('--new-map 에 같은 맵을 두 번 적음')
        if bool(keys) != bool(patches):
            raise ValueError('--new-map 과 그 맵을 더하는 패치 목록 --with-patch 는 함께 줌')
        if not keys:
            return
        known = set(map_ids(rom))
        for bc, bd in sorted(self.keys):
            label = f'--new-map {bc:02X}/{bd:02X}'
            if bc >= 0x50:
                raise ValueError(f'{label}: 그룹 50 미만만 받음')
            if (bc, bd) in known:
                raise ValueError(f'{label}: 이미 롬에 있는 맵(원래 롬에 없는 맵만 알림)')
        try:
            self.lists = [load(str(path)) for path in patches]
        except (KeyError, ValueError, PatchError) as error:
            raise ValueError(f'--with-patch: {error}') from None
        self.view = self.merged(rom, [], 0)
        missing = sorted(self.keys - set(map_ids(self.view)))
        if missing:
            raise ValueError(f'--new-map {missing[0][0]:02X}/{missing[0][1]:02X}: --with-patch 를 붙인 롬에도 없는 맵')

    def rom_for(self, rom, key):
        return self.view if self.keys else rom

    def viewing(self, view):
        """같은 새 맵·목록에 칸을 읽을 롬만 view 로 바꾼 것(상자 놓기가 레코드를 다시 싼 뒤)."""
        out = NewMaps(None)
        out.keys, out.lists, out.view = self.keys, self.lists, view
        return out

    def merged(self, rom, lists, mb):
        """원래 롬에 --with-patch 목록과 lists([(이름, 롬 크기 MB, [(파일 위치, 바이트, orig, 설명)])])를 함께 빌드한 롬."""
        lists = self.lists + list(lists)
        # 이미 늘린 롬이 바탕이면 그 크기보다 작게 빌드하지 않는다(빌더가 롬을 줄이려다 실패함)
        grown = len(rom.d) // 0x100000 if len(rom.d) > 0x180000 else 0
        mb = max([mb, grown, *(size for _, size, _ in lists)])
        try:
            return Rom(build(rom.d, lists, mb)[0])
        except PatchError as error:
            raise ValueError(f'--with-patch 와 한 빌드로 합치지 못함: {error}') from None


NO_NEW_MAPS = NewMaps(None)


def validate_tables(rom, doc, check_cells=False, new_maps=NO_NEW_MAPS):
    available = set(map_ids(rom)) | new_maps.keys
    for name in TABLES.keys() - {'chests'}:
        seen = set()
        for row in doc[name]:
            if (row['group'], row['map']) not in available:
                raise ValueError(f'{name} {row["index"]}: 존재하지 않는 맵(새 맵은 --new-map 으로 알림)')
            if name == 'chest_maps' and row['group'] >= 0x50:
                raise ValueError('chest_maps: 일반 실내 맵(그룹 50 미만)만 지원함')
            key = (row['group'], row['map'])
            if name != 'chest_maps':
                key += (row['x'], row['y'])
            if name == 'foot':
                key += (row['layer'],)
            if key in seen:
                raise ValueError(f'{name}: 먼저 나오는 항목에 가려지는 중복 위치 {key}')
            seen.add(key)
    if sum(row['count'] for row in doc['chest_maps']) != TABLES['chests'][1]:
        raise ValueError('chest_maps: count 합계는 161이어야 함')
    # 표 옮기기와 같은 열림 비트 규칙(7E:2210~224F 안, 겹침·고정 코드가 보는 비트 거부)
    from dq5chestreloc import flag_bits
    flag_bits(doc)
    if check_cells:
        start = 0
        for row in doc['chest_maps']:
            cells = chests(new_maps.rom_for(rom, (row['group'], row['map'])), row['group'], row['map'], start)
            if len(cells) != row['count']:
                raise ValueError(f'chest_maps {row["index"]}: 맵 상자 셀 {len(cells)}개와 count가 다름')
            start += row['count']


def edits(rom, doc, new_maps=NO_NEW_MAPS):
    fields(doc, {'format', *SECTIONS}, '문서')
    if doc.get('format') != FORMAT:
        raise ValueError(f'format={FORMAT}이 필요함')
    current = dump(rom, 'field' in doc)
    out, positions, map_changed = [], [], False
    for name, (start, count, size) in TABLES.items():
        rows = doc.get(name, [])
        if not isinstance(rows, list):
            raise ValueError(f'{name}: 배열이어야 함')
        seen = set()
        for row in rows:
            allowed = {'index', *decode(name, bytes(size))}
            fields(row, allowed, name)
            i = integer(row.get('index'), count - 1, 'index')
            if i in seen:
                raise ValueError(f'{name}: 중복 index {i}')
            seen.add(i)
            addr = start + i * size
            old = read(rom, addr, size)
            new = encode(name, old, {k: v for k, v in row.items() if k != 'index'})
            current[name][i] = {'index': i, **decode(name, new)}
            if name not in ('chests', 'chest_maps') and old[:4] != new[:4]:
                positions.append(current[name][i])
            map_changed |= name == 'chest_maps' and new != old
            out.append((addr, new, old, f'{name} {i}'))
    out += field_edits(rom, doc.get('field', []))
    validate_tables(rom, current, map_changed, new_maps)
    rows = doc.get('field') or [{}]
    reward = rows[0].get('reward', current['field'][0]['reward']) if 'field' in doc else field_reward(rom)
    if reward is not None:
        light_clash(current['foot'], reward)
    dimensions = {}
    for row in positions:
        key = row['group'], row['map']
        if key not in dimensions:
            dimensions[key] = map_dimensions(new_maps.rom_for(rom, key), *key)
        width, height = dimensions[key]
        if row['x'] >= width or row['y'] >= height:
            raise ValueError(f'좌표가 맵 {width}×{height} 밖')
    return out


def field_edits(rom, rows):
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError('field: 항목 하나까지의 배열이어야 함')
    if not rows:
        return []
    fields(rows[0], {'index', *decode_field(read_field(rom))}, 'field')
    integer(rows[0].get('index'), 0, 'index')
    old = read_field(rom)
    new = encode_field(old, {k: v for k, v in rows[0].items() if k != 'index'},
                       lambda x, y: world_block(rom, x, y))
    out, i = [], 0
    while i < len(new):
        if new[i] == old[i]:
            i += 1
            continue
        j = i
        while j < len(new) and new[j] != old[j] and FIELD_ADDRS[j] == FIELD_ADDRS[i] + j - i:
            j += 1
        out.append((FIELD_ADDRS[i], new[i:j], old[i:j], 'field 0'))
        i = j
    return out


def patch(rom, doc, new_maps=NO_NEW_MAPS):
    rows = [row for row in edits(rom, doc, new_maps) if row[1] != row[2]]
    if new_maps.keys:
        new_maps.merged(rom, [('chest-rewards', 0, [(lorom(addr), data, old, note) for addr, data, old, note in rows])], 0)
    return {'format': 'dq5patch/1', 'name': 'chest-rewards', 'writes': [
        {'at': f'{addr >> 16:02X}:{addr & 0xFFFF:04X}', 'hex': data.hex(' '), 'orig': old.hex(' '), 'note': note}
        for addr, data, old, note in rows]}


def check(rom, doc=None, new_maps=NO_NEW_MAPS):
    source = dump(rom) if doc is None else doc
    rows = edits(rom, source, new_maps)
    data = bytearray(rom.d)
    for addr, value, _, _ in rows:
        data[lorom(addr):lorom(addr) + len(value)] = value
    # 새 맵은 --with-patch 와 함께 빌드한 롬에만 있으므로, 그 롬을 다시 읽는다
    built = new_maps.merged(rom, [('chest-rewards', 0, [(lorom(a), v, o, n) for a, v, o, n in rows if v != o])], 0) \
        if new_maps.keys else Rom(data)
    result = dump(built, 'field' in source)
    for name in SECTIONS:
        for row in source.get(name, []):
            if any(result[name][row['index']][key] != value for key, value in row.items()):
                raise ValueError(f'{name}: 쓴 뒤 읽은 값이 다름')
    validate_tables(built, result, True)
    if doc is None and data != rom.d:
        raise ValueError('원본을 다시 쓴 바이트가 다름')
    print(f'고정 항목 {sum(t[1] for t in TABLES.values())}개, '
          f'{sum(t[1] * t[2] for t in TABLES.values())}바이트와 필드 조사 1곳; 다시 읽기 일치, '
          f'맵 {len(result["chest_maps"])}개 상자 수 일치' + (f', 새 맵 {len(new_maps.keys)}개' if new_maps.keys else ''))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('rom', type=Path)
    subs = p.add_subparsers(dest='command', required=True)
    d = subs.add_parser('dump')
    d.add_argument('-o', '--out', type=Path, required=True)
    w = subs.add_parser('patch')
    w.add_argument('source', type=Path)
    w.add_argument('-o', '--out', type=Path, required=True)
    c = subs.add_parser('check')
    c.add_argument('source', type=Path, nargs='?')
    for sub in (w, c):
        sub.add_argument('--new-map', action='append', default=[], type=new_map,
                         help='dq5newmap.py 로 함께 더하는 새 맵 GG/MM(여럿이면 되풀이)')
        sub.add_argument('--with-patch', action='append', default=[], type=Path,
                         help='새 맵을 더하는 패치 목록(dq5patch/1). 새 맵을 이 목록들을 붙인 롬에서 읽음')
    args = p.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if getattr(args, 'source', None):
            fields(doc, {'format', *SECTIONS}, '문서')
        new_maps = NewMaps(rom, getattr(args, 'new_map', []), getattr(args, 'with_patch', []))
        if args.command == 'check':
            check(rom, doc, new_maps)
        else:
            result = dump(rom) if args.command == 'dump' else patch(rom, doc, new_maps)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError, IndexError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
