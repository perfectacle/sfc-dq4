"""맵에 상자를 놓고 보상 표를 함께 고치는 도구의 입력 검사와 번호 다시 매기기."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dq5chestplace import FORMAT, check, map_key, patch, plan
from dq5map import Rom
from test_dq5chestwrite import ROM

CHEST_BLOCK = 384


def doc(*boxes, map_name='01/02'):
    return {'format': FORMAT, 'maps': [{'map': map_name, 'chests': [
        {'x': x, 'y': y, 'block': block, 'reward': reward} for x, y, block, reward in boxes]}]}


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
    def test_patch_formats_and_check(self):
        rom = Rom(ROM.read_bytes())
        value = doc((36, 26, CHEST_BLOCK, 0x4BA))
        writes = patch(rom, value, 0x3E8000, {'chests': 0x3F8000})['writes']
        self.assertEqual((writes[0]['at'], writes[0]['note'], 'orig' in writes[0]), ('0x1F0000', 'map 01/02', False))
        self.assertEqual((writes[1]['at'], writes[1]['hex']), ('0F:8AF6', '00 80 3e'))
        self.assertIn('orig', writes[1])
        check(rom, value, 0x3E8000, {'chests': 0x3F8000})

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
