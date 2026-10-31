"""맵에 상자를 놓고 보상 표를 함께 고치는 도구의 입력 검사와 번호 다시 매기기.
맵을 풀어 칸을 세는 시험은 실제 인코더로 싼 맵을 넣은 합성 롬(mapped())에서 돌리고, 롬이 있으면 원본 롬에서도 돌린다."""
import functools
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chestplace import FORMAT, LOWER_FURNITURE, check, map_key, patch, plan
from dq5build import build, parse_at
from dq5chest import CHEST_ATTR, LOWER_TABLE
from dq5chestcheck import NUMBERS, grow_chests, number_build
from dq5chestreloc import FORMAT as TABLES_FORMAT, ORIGINAL, address, cpu, parse, serialize
from dq5exit import HOOK_TABLE
from dq5map import ANIM_MAPS, BLOCK_BANK, GROUPS, LOAD_TAIL, LOAD_TAIL_ORIGINAL, SLOT_SKIP, Rom, lorom
from dq5mapcompile import compile_places
from dq5mapwrite import HEADER, all_maps, encode, pointer_addr
from test_dq5blockhook import blank
from test_dq5chestwrite import ROM, fixture
from test_dq5newmap import original_rom

CHEST_BLOCK = 384
FURNITURE_BLOCK = 204
# 합성 롬의 블록 384 는 2×2 상자, 204 는 2×3 タンス(아래층). 속성은 오른쪽 아래 칸에만 bit7 이 붙어 84·93 이 된다.
# 나머지 블록은 속성 없는 1×1
BLOCKS = {CHEST_BLOCK: (2, 2, CHEST_ATTR & 0x7F), FURNITURE_BLOCK: (2, 3, min(LOWER_FURNITURE) & 0x7F)}
RECORDS = 0x0E8000


def chest(x, y):
    """상자 칸이 (x, y) 가 되는 블록 384 배치."""
    return [x - 1, y - 1, CHEST_BLOCK]


def jar(x, y):
    """가구 칸이 (x, y) 가 되는 블록 204 배치."""
    return [x - 1, y - 2, FURNITURE_BLOCK]


# 맵마다 (폭, 높이, 배치). 원본 롬의 시험이 쓰는 칸을 같은 좌표에 두어, 같은 시험이 두 롬에서 돈다.
# 00/01 은 표를 원래 크기로 채우는 상자 76개와 서랍 칸 83개, 00/02~00/50 은 상자 하나씩이다. 적지 않은 맵은 빈 8×8
BIG = ([chest(2 * k + 1, 2 * r + 1) for r in range(4) for k in range(19)]
       + [jar(2 * k + 1, 26 + 3 * r) for r in range(4) for k in range(21)][:83])
LAYOUT = {(0x01, 0x02): (64, 48, [chest(35, 29), chest(50, 40)]),
          (0x17, 0x00): (12, 8, [jar(4, 4), jar(2, 4)]),
          (0x19, 0x00): (16, 48, [chest(3, 5), chest(7, 5), chest(11, 5), chest(5, 20), chest(12, 45)]),
          (0x31, 0x03): (54, 38, [chest(8, 17), chest(10, 17), jar(8, 21), jar(10, 21)]),
          (0x00, 0x01): (64, 40, BIG)}
LAYOUT[(0x00, 0x00)] = LAYOUT[(0x31, 0x03)]
LAYOUT |= {(0x00, b): (8, 8, [chest(1, 1)]) for b in range(2, 0x51)}
# 그룹마다 맵 수
COUNTS = [{0x00: 0x51, 0x01: 3, 0x0E: 3, 0x31: 5}.get(g, 1) for g in range(GROUPS)]


def flag(i, first=0):
    return {'flag_index': first + i // 8, 'mask': 0x80 >> i % 8}


def chest_tables():
    """원래 행 수(상자 161·맵 연결 83·서랍 86·발밑 18·두 칸 앞 17·아래층 11)를 채운 상자 표. 열림 비트는 겹치지 않고,
    7E:223C & 01 은 두 칸 앞 0E/02 (6,6) 이, 2243 은 아무도 쓰지 않는다."""
    jars = [(x + 1, y + 2) for x, y, block in BIG if block == FURNITURE_BLOCK]
    rows = [(0x31, 3, 8, 21), (0x31, 3, 10, 21), (0x17, 0, 4, 4)] + [(0, 1, x, y) for x, y in jars]
    places = ('group', 'map', 'x', 'y')
    return {'format': TABLES_FORMAT,
            'chests': [{'reward': reward} for reward in [0x100, 0x101, 0x33, 0x88, *range(0x104, 0x100 + 161)]],
            'chest_maps': [{'group': g, 'map': m, 'count': n} for g, m, n in
                           [(0, 0, 2), (1, 2, 2), (0x31, 3, 2), (0, 1, 76)] + [(0, b, 1) for b in range(2, 0x51)]],
            'search': [dict(zip(places, row)) | {'unused': 1, 'reward': 0x200 + i} | flag(i) for i, row in enumerate(rows)],
            'foot': [dict(zip(places, row)) | {'layer': 1, 'reward': 0x300 + i} | flag(i)
                     for i, row in enumerate([(0, 1, 31, 14)] + [(0, 1, x, 10) for x in range(17)])],
            'ahead': [{'group': 0x0E, 'map': 2, 'x': 6, 'y': 6, 'reward': 0x400, 'flag_index': 0x2C, 'mask': 1}]
            + [{'group': 0, 'map': 1, 'x': x, 'y': 12, 'reward': 0x401 + x} | flag(x, 0x34) for x in range(16)],
            'lower': [{'group': 0, 'map': 1, 'x': x, 'y': 16, 'reward': 0x500 + x} | flag(x, 0x18) for x in range(11)]}


@functools.cache
def mapped():
    """맵을 실제로 풀 수 있는 1.5MB 합성 롬. 상자 표 코드 자리(test_dq5chestwrite.fixture)와 그룹·속성·들어가는 곳·문 표
    (test_dq5newmap.original_rom) 위에, 뱅크 16 의 블록 정의, LAYOUT 을 dq5mapcompile·dq5mapwrite 로 싼 맵 레코드와
    그 포인터, chest_tables() 를 직렬화한 상자 표 여섯을 둔다. 맵을 풀 때 보는 훅·슬롯 표(15:F907·04:822D·03:D82E)는 비운다."""
    data = original_rom(COUNTS, bytearray(fixture().d)).d
    code = blank()
    for site, size in ((0x0192F4, 5), (0x018CDE, 4), (0x018CE6, 3)):
        data[lorom(site):lorom(site) + size] = code[lorom(site):lorom(site) + size]
    data[lorom(LOAD_TAIL):lorom(LOAD_TAIL) + 3] = LOAD_TAIL_ORIGINAL
    for table in (HOOK_TABLE, SLOT_SKIP, ANIM_MAPS):
        data[lorom(table)] = 0xFF
    at = lorom(BLOCK_BANK << 16 | 0x8000)
    for n in range(0x800):
        width, height, attr = BLOCKS.get(n, (1, 1, 0))
        data[at:at + 3] = bytes(((width - 1) << 3 | height - 1, 0, attr))
        at += 3 + 2 * width * height
    rom = Rom(data)
    at, records = RECORDS, {}
    # 그룹 50 이상 맵은 읽지 않으므로 포인터를 그대로 둔다
    for bc, bd in [key for key in all_maps(rom) if key[0] < 0x50]:
        width, height, places = LAYOUT.get((bc, bd), (8, 8, []))
        key = (width, height, tuple(map(tuple, places)))
        if key not in records:
            src = {'map': f'{bc:02X}/{bd:02X}', **dict.fromkeys(HEADER, 0), 'width': width, 'height': height,
                   'bits': (width * height - 1).bit_length(), 'placements': places,
                   'passes': [{'vertical': False, 'entries': []} for _ in range(3)]}
            record = encode(compile_places(src, rom, False))
            data[lorom(at):lorom(at) + len(record)] = record
            records[key] = at
            at += len(record)
        pointer = lorom(pointer_addr(rom, bc, bd))
        data[pointer:pointer + 3] = records[key].to_bytes(3, 'little')
    for name, blob in serialize(rom, chest_tables()).items():
        data[lorom(ORIGINAL[name]):lorom(ORIGINAL[name]) + len(blob)] = blob
    return Rom(bytes(data))


def doc(*boxes, map_name='01/02'):
    return {'format': FORMAT, 'maps': [{'map': map_name, 'chests': [
        {'x': x, 'y': y, 'block': block, 'reward': reward} for x, y, block, reward in boxes]}]}


def furniture(x, y, **change):
    return {'x': x, 'y': y, 'block': FURNITURE_BLOCK, 'reward': 0x3FD, 'flag_index': 0x0B, 'mask': 2} | change


class ChestPlaceTests(unittest.TestCase):
    def test_map_key(self):
        self.assertEqual(map_key('1d/03', 'm'), (0x1D, 3))
        for text in ('1D03', '1D/3', None, 'GG/00'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                map_key(text, 'm')


class ChestPlaceMapTests(unittest.TestCase):
    def setUp(self):
        self.rom = mapped()

    def test_new_chest_shifts_numbers_and_keeps_rewards_by_cell(self):
        rom = self.rom
        _, _, mb, tables, new = plan(rom, doc((36, 26, CHEST_BLOCK, 0x4BA)), 0x3E8000, {'chests': 0x3F8000})
        self.assertEqual(mb, 2)
        self.assertEqual(new, [(1, 2, (37, 27), 0x4BA)])
        self.assertEqual(len(tables['chests']), 162)
        self.assertEqual([c['reward'] for c in tables['chests'][2:5]], [0x4BA, 0x33, 0x88])
        row = next(r for r in tables['chest_maps'] if (r['group'], r['map']) == (1, 2))
        self.assertEqual(row['count'], 3)

    def test_new_map_entry_is_appended(self):
        rom = self.rom
        _, _, _, tables, new = plan(rom, doc((10, 4, CHEST_BLOCK, 0x200), map_name='17/00'), 0x3E8000,
                                    {'chests': 0x3F8000, 'chest_maps': 0x1EEE4E})
        self.assertEqual(tables['chest_maps'][-1], {'group': 0x17, 'map': 0, 'count': 1})
        self.assertEqual(tables['chests'][-1], {'reward': 0x200})
        self.assertEqual(new[0][:2], (0x17, 0))

    def test_patch_formats_and_check(self):
        rom = self.rom
        value = doc((36, 26, CHEST_BLOCK, 0x4BA))
        writes = patch(rom, value, 0x3E8000, {'chests': 0x3F8000})['writes']
        self.assertEqual((writes[0]['at'], writes[0]['note'], 'orig' in writes[0]), ('0x1F0000', 'map 01/02', False))
        self.assertEqual((writes[1]['at'], writes[1]['hex']), (cpu(pointer_addr(rom, 1, 2)), '00 80 3e'))
        self.assertIn('orig', writes[1])
        check(rom, value, 0x3E8000, {'chests': 0x3F8000})

    def test_furniture_appends_search_row_at_attribute_cell(self):
        rom = self.rom
        value = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [
            {'x': 40, 'y': 24, 'block': 204, 'reward': 0x3FD, 'flag_index': 0x0B, 'mask': 2}]}]}
        _, _, _, tables, new = plan(rom, value, 0x3E8000, {'search': 0x3F9000})
        self.assertEqual(new, [])
        self.assertEqual(tables['search'][-1], {'group': 1, 'map': 2, 'x': 41, 'y': 26, 'unused': 1, 'reward': 0x3FD,
                                                'flag_index': 0x0B, 'mask': 2})
        check(rom, value, 0x3E8000, {'search': 0x3F9000})
        for change in ({'flag_index': 4, 'mask': 0x80}, {'block': CHEST_BLOCK}, {'mask': 0}, {'reward': 0xD00A}):
            bad = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [value['maps'][0]['furniture'][0] | change]}]}
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan(rom, bad, 0x3E8000, {'search': 0x3F9000})

    def test_chest_and_two_furniture_in_one_map(self):
        rom = self.rom
        value = {'format': FORMAT, 'maps': [{'map': '01/02', 'chests': [{'x': 36, 'y': 26, 'block': CHEST_BLOCK,
                                                                         'reward': 0x4BA}],
                                             'furniture': [furniture(40, 24), furniture(30, 18, mask=4)]}]}
        at = {'chests': 0x3F8000, 'search': 0x3F9000}
        _, _, _, tables, new = plan(rom, value, 0x3E8000, at)
        self.assertEqual(new, [(1, 2, (37, 27), 0x4BA)])
        self.assertEqual([(r['x'], r['y'], r['mask']) for r in tables['search'][-2:]], [(41, 26, 2), (31, 20, 4)])
        check(rom, value, 0x3E8000, at)

    def test_patched_rom_is_not_patched_again(self):
        rom = self.rom
        first = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [furniture(40, 24)]}]}
        manifest = patch(rom, first, 0x3E8000, {'search': 0x3F9000})
        writes = [(parse_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
                   w['note']) for w in manifest['writes']]
        built = Rom(build(rom.d, [('first', manifest['rom_size'], writes)], manifest['rom_size'])[0])
        check(rom, first, 0x3E8000, {'search': 0x3F9000})
        # 표를 옮긴 롬 위에 다시 쌓지 않는다. 가구를 더하려면 원래 롬에서 입력 하나에 모두 적는다
        second = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [furniture(30, 18, mask=4)]}]}
        with self.assertRaisesRegex(ValueError, '표를 옮긴 롬'):
            plan(built, second, 0x3EC000, {'search': 0x3FA000})

    def test_rejects_furniture(self):
        rom = self.rom
        at = {'search': 0x3F9000, 'chests': 0x3F8000, 'chest_maps': 0x1EEE4E}

        def one(*rows, map_name='01/02'):
            return {'format': FORMAT, 'maps': [{'map': map_name, 'furniture': list(rows)}]}

        bad = [
            (one(furniture(3, 3), map_name='17/00'), at),            # 기존 서랍 (4,4) 를 덮음
            ({'format': FORMAT, 'maps': [{'map': '17/00', 'chests': [{'x': 3, 'y': 3, 'block': CHEST_BLOCK,
                                                                      'reward': 1}]}]}, at),  # 상자가 (4,4) 를 덮음
            (one(furniture(40, 24), furniture(40, 24, mask=4)), at),  # 같은 칸에 두 번
            (one(furniture(40, 24)), {}),                             # 늘어난 서랍 표가 원래 자리에 들지 않음
            (one(furniture(40, 24, unused=256)), at),
            (one(furniture(40, 24, unused='1')), at),
            (one(furniture(40, 24, flag_index=0x14, mask=1)), at),   # 7E:2240 은 발밑 표의 비트
            (one(furniture(40, 24, flag_index=0x10, mask=1)), at),   # 7E:223C & 01 은 두 칸 앞·아래층 상자가 씀
            (one(furniture(40, 24, flag_index=0x0C, mask=1)), at),   # 7E:2238 은 전투 0C 의 21:8C2F 가 읽음
            (one(furniture(40, 24, flag_index=0x24, mask=1)), at),   # 7E:2250 은 상자 비트 자리 밖
            (one(furniture(30, 12), map_name='00/01'), at),            # 발밑 항목 (31,14) 를 덮음
            (one(furniture(5, 4), map_name='0E/02'), at),              # 두 칸 앞 항목 (6,6) 을 덮음
            ({'format': FORMAT, 'maps': [{'map': '00/01', 'chests': [{'x': 30, 'y': 13, 'block': CHEST_BLOCK,
                                                                      'reward': 1}]}]}, at),  # 상자가 발밑 (31,14) 를 덮음
        ]
        for value, places in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                plan(rom, value, 0x3E8000, places)

    def test_furniture_flag_limit_follows_area_not_search_range(self):
        # 서랍 범위(222C~223F) 밖이라도 비어 있는 상자 비트(7E:2243)면 받는다
        rom = self.rom
        value = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [furniture(40, 24, flag_index=0x17, mask=1)]}]}
        _, _, _, tables, _ = plan(rom, value, 0x3E8000, {'search': 0x3F9000})
        self.assertEqual(tables['search'][-1]['flag_index'], 0x17)

    def test_lower_row_buried_only_where_engine_reads_it(self):
        def moved(group, number, x, y):
            data = bytearray(self.rom.d)
            data[lorom(LOWER_TABLE):lorom(LOWER_TABLE) + 4] = bytes([group, number, x, y])
            return Rom(bytes(data))

        at = {'chests': 0x3F8000, 'chest_maps': 0x1EEE4E}
        with self.assertRaisesRegex(ValueError, "'lower', 2, 2"):
            plan(moved(0x32, 0, 2, 2), doc((2, 2, CHEST_BLOCK, 1), map_name='32/00'), 0x3E8000, at)
        plan(moved(0x01, 2, 36, 26), doc((36, 26, CHEST_BLOCK, 1)), 0x3E8000, at)

    def test_rejects(self):
        rom = self.rom
        at = {'chests': 0x3F8000}
        bad = [
            (doc((34, 28, CHEST_BLOCK, 1)), 0x3E8000, at),          # 기존 상자 자리: 새 칸이 생기지 않음
            (doc((36, 26, 904, 1)), 0x3E8000, at),                  # 상자가 아닌 블록
            (doc((91, 26, CHEST_BLOCK, 1)), 0x3E8000, at),          # 맵 밖
            (doc((36, 26, CHEST_BLOCK, 0xD00A)), 0x3E8000, at),      # 지원하지 않는 내용물
            (doc((36, 26, CHEST_BLOCK, 1), map_name='51/51'), 0x3E8000, at),
            (doc((36, 26, CHEST_BLOCK, 1)), 0x1E8000, at),          # 늘린 롬이 아닌 맵 자리
            (doc((36, 26, CHEST_BLOCK, 1)), 0x3F8000, at),          # 맵 레코드와 상자 표가 겹침
            ({'format': FORMAT, 'maps': []}, 0x3E8000, at),
            ({'format': FORMAT, 'maps': [{'map': '01/02', 'chests': [], 'furniture': []}]}, 0x3E8000, at),
            ({'format': FORMAT, 'maps': [doc((36, 26, CHEST_BLOCK, 1))['maps'][0]] * 2}, 0x3E8000, at),
            (doc((36, 26, CHEST_BLOCK, 1)), 0x3E8000, {}),           # 상자 표가 원래 자리에 들지 않음
            (doc((2, 44, CHEST_BLOCK, 1), map_name='19/00'), 0x3E8000, at),  # 표에 없는 맵의 기존 상자 칸
            (doc((36, 26, CHEST_BLOCK, 1)), 0x7DFFF0, at),          # 레코드가 파일 3F0000 을 넘음
        ]
        for value, map_at, places in bad:
            with self.subTest(value=value, map_at=hex(map_at)), self.assertRaises(ValueError):
                plan(rom, value, map_at, places)


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class RealRomChestPlaceMapTests(ChestPlaceMapTests):
    def setUp(self):
        self.rom = Rom(ROM.read_bytes())


@unittest.skipUnless(ROM.is_file(), '롬 없음')
class RealRomOnlyTests(unittest.TestCase):
    """dq5chestcheck 의 실측 빌드 입력(원본 맵의 상자 칸 좌표)을 그대로 쓰는 시험."""
    def test_base_tables_grow_past_192(self):
        rom = Rom(ROM.read_bytes())
        base = parse(rom)
        grow_chests(base)
        boxes = [(x, 22, CHEST_BLOCK, 0x100 + x) for x in range(30, 44, 2)]
        at = {'chests': 0x3F8000, 'chest_maps': 0x3FC000, 'lower': 0x3FD000}
        # 194개가 되면 상자 192·193 이 원래 아래층 상자 비트 2228 & 80·40 과 겹친다
        with self.assertRaisesRegex(ValueError, '2228'):
            plan(rom, doc(*boxes), 0x3E8000, at, base)
        for row in base['lower']:
            row['flag_index'] += 1
        _, writes, _, tables, _ = plan(rom, doc(*boxes), 0x3E8000, at, base)
        self.assertEqual(len(tables['chests']), 194)
        self.assertEqual(tables['chests'][192], {'reward': 0x100 + 987})
        sites = {addr: new for addr, new, _, _ in writes}
        self.assertEqual(sites[0x1FFC7E], b'\x3f')
        check(rom, doc(*boxes), 0x3E8000, at, base)
        # 바탕 표의 상자 수가 맵 칸과 다르면 거부
        wrong = json.loads(json.dumps(base))
        wrong['chest_maps'][-1]['count'] += 1
        wrong['chests'].append({'reward': 1})
        with self.assertRaises(ValueError):
            plan(rom, doc(*boxes), 0x3E8000, at, wrong)

    def test_wide_number_builds_put_chest_n_at_last_cell(self):
        # dq5chestcheck 의 widenum_* 롬: 19/00 의 마지막 칸 (12,45) 가 상자 n 이고 내용물은 금화 n
        rom = Rom(ROM.read_bytes())
        for n in NUMBERS:
            place_doc, edit, places = number_build(n)
            base = parse(rom)
            edit(base)
            at = {places[k][2:-3].replace('-', '_'): address(places[k + 1]) for k in range(0, len(places), 2)}
            map_at = at.pop('map')
            with self.subTest(n=n):
                _, _, _, tables, _ = plan(rom, place_doc, map_at, at, base)
                self.assertEqual(tables['chest_maps'][-1], {'group': 0x19, 'map': 0, 'count': 5})
                self.assertEqual(len(tables['chests']), n + 1)
                self.assertEqual(tables['chests'][n], {'reward': 0x100 + n})


if __name__ == '__main__':
    unittest.main()
