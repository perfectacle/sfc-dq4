"""맵에 상자를 놓고 보상 표를 함께 고치는 도구의 입력 검사와 번호 다시 매기기."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chestplace import FORMAT, check, map_key, patch, plan
from dq5build import build, parse_at
from dq5chest import LOWER_TABLE
from dq5chestcheck import grow_chests
from dq5chestreloc import parse
from dq5map import Rom, lorom
from test_dq5chestwrite import ROM

CHEST_BLOCK = 384


def doc(*boxes, map_name='01/02'):
    return {'format': FORMAT, 'maps': [{'map': map_name, 'chests': [
        {'x': x, 'y': y, 'block': block, 'reward': reward} for x, y, block, reward in boxes]}]}


def furniture(x, y, **change):
    return {'x': x, 'y': y, 'block': 204, 'reward': 0x3FD, 'flag_index': 0x0B, 'mask': 2} | change


class ChestPlaceTests(unittest.TestCase):
    def test_map_key(self):
        self.assertEqual(map_key('1d/03', 'm'), (0x1D, 3))
        for text in ('1D03', '1D/3', None, 'GG/00'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                map_key(text, 'm')

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_new_chest_shifts_numbers_and_keeps_rewards_by_cell(self):
        rom = Rom(ROM.read_bytes())
        _, _, mb, tables, new = plan(rom, doc((36, 26, CHEST_BLOCK, 0x4BA)), 0x3E8000, {'chests': 0x3F8000})
        self.assertEqual(mb, 2)
        self.assertEqual(new, [(1, 2, (37, 27), 0x4BA)])
        self.assertEqual(len(tables['chests']), 162)
        self.assertEqual([c['reward'] for c in tables['chests'][2:5]], [0x4BA, 0x33, 0x88])
        row = next(r for r in tables['chest_maps'] if (r['group'], r['map']) == (1, 2))
        self.assertEqual(row['count'], 3)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_new_map_entry_is_appended(self):
        rom = Rom(ROM.read_bytes())
        _, _, _, tables, new = plan(rom, doc((10, 4, CHEST_BLOCK, 0x200), map_name='17/00'), 0x3E8000,
                                    {'chests': 0x3F8000, 'chest_maps': 0x1EEE4E})
        self.assertEqual(tables['chest_maps'][-1], {'group': 0x17, 'map': 0, 'count': 1})
        self.assertEqual(tables['chests'][-1], {'reward': 0x200})
        self.assertEqual(new[0][:2], (0x17, 0))

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
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

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_patch_formats_and_check(self):
        rom = Rom(ROM.read_bytes())
        value = doc((36, 26, CHEST_BLOCK, 0x4BA))
        writes = patch(rom, value, 0x3E8000, {'chests': 0x3F8000})['writes']
        self.assertEqual((writes[0]['at'], writes[0]['note'], 'orig' in writes[0]), ('0x1F0000', 'map 01/02', False))
        self.assertEqual((writes[1]['at'], writes[1]['hex']), ('0F:8AF6', '00 80 3e'))
        self.assertIn('orig', writes[1])
        check(rom, value, 0x3E8000, {'chests': 0x3F8000})

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_furniture_appends_search_row_at_attribute_cell(self):
        rom = Rom(ROM.read_bytes())
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

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_chest_and_two_furniture_in_one_map(self):
        rom = Rom(ROM.read_bytes())
        value = {'format': FORMAT, 'maps': [{'map': '01/02', 'chests': [{'x': 36, 'y': 26, 'block': CHEST_BLOCK,
                                                                         'reward': 0x4BA}],
                                             'furniture': [furniture(40, 24), furniture(30, 18, mask=4)]}]}
        at = {'chests': 0x3F8000, 'search': 0x3F9000}
        _, _, _, tables, new = plan(rom, value, 0x3E8000, at)
        self.assertEqual(new, [(1, 2, (37, 27), 0x4BA)])
        self.assertEqual([(r['x'], r['y'], r['mask']) for r in tables['search'][-2:]], [(41, 26, 2), (31, 20, 4)])
        check(rom, value, 0x3E8000, at)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_patched_rom_is_not_patched_again(self):
        rom = Rom(ROM.read_bytes())
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

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_rejects_furniture(self):
        rom = Rom(ROM.read_bytes())
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

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_furniture_flag_limit_follows_area_not_search_range(self):
        # 서랍 범위(222C~223F) 밖이라도 비어 있는 상자 비트(7E:2243)면 받는다
        rom = Rom(ROM.read_bytes())
        value = {'format': FORMAT, 'maps': [{'map': '01/02', 'furniture': [furniture(40, 24, flag_index=0x17, mask=1)]}]}
        _, _, _, tables, _ = plan(rom, value, 0x3E8000, {'search': 0x3F9000})
        self.assertEqual(tables['search'][-1]['flag_index'], 0x17)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_lower_row_buried_only_where_engine_reads_it(self):
        def moved(group, number, x, y):
            data = bytearray(ROM.read_bytes())
            data[lorom(LOWER_TABLE):lorom(LOWER_TABLE) + 4] = bytes([group, number, x, y])
            return Rom(bytes(data))

        at = {'chests': 0x3F8000, 'chest_maps': 0x1EEE4E}
        with self.assertRaisesRegex(ValueError, "'lower', 2, 2"):
            plan(moved(0x32, 0, 2, 2), doc((2, 2, CHEST_BLOCK, 1), map_name='32/00'), 0x3E8000, at)
        plan(moved(0x01, 2, 36, 26), doc((36, 26, CHEST_BLOCK, 1)), 0x3E8000, at)

    @unittest.skipUnless(ROM.is_file(), '롬 없음')
    def test_rejects(self):
        rom = Rom(ROM.read_bytes())
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


if __name__ == '__main__':
    unittest.main()
