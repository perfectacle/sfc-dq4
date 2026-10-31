"""게임 데이터 표 쓰기: 주문 전투 MP 를 바꾸면 주문 목록 창의 MP 칸(21:9BB4)도 같이 쓰는지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5tables as tb  # noqa: E402
from dq5map import lorom  # noqa: E402

BATTLE = 0x268765


def rom(menu=None):
    """주문마다 전투 MP 바이트(위 3비트 a0)와 그에 맞는 창 MP 칸을 둔 합성 롬. menu 로 칸 하나를 덮는다."""
    d = bytearray(0x200000)
    for n in range(tb.SPELL_COUNT):
        mp = (n % 16) if n < 0x40 else 0x1F
        d[lorom(BATTLE + n)] = 0xA0 | mp
        d[lorom(tb.MENU_MP + n)] = tb.menu_mp(mp)
    for n, v in (menu or {}).items():
        d[lorom(tb.MENU_MP + n)] = v
    return bytes(d)


def doc(*rows):
    return {'format': tb.FORMAT, 'spells': [dict(zip(('id', 'MP'), r)) for r in rows]}


class MenuMpTests(unittest.TestCase):
    def test_menu_follows_battle_mp(self):
        data = rom()
        writes = {tb.cpu(o): (new, old, label) for o, new, old, label in tb.writes_for([doc(('01', 9), ('04', 30),
                                                                                          ('06', 29), ('41', 7))], data)}
        self.assertEqual(writes['21:9BB5'][:2], (9, 1))
        self.assertEqual(writes['21:9BB8'][:2], (36, 4))                 # 1E 는 36
        self.assertEqual(writes['21:9BBA'][:2], (0xFF, 6))               # 1D(남은 MP 전부)는 FF
        self.assertEqual(writes['21:9BF5'][:2], (7, 0))                  # 1F(쓰지 않음)이던 칸
        self.assertEqual(writes['26:8766'][:2], (0xA9, 0xA1))
        self.assertEqual(tb.check([doc(('01', 9), ('06', 29))], data), [])

    def test_range_only_keeps_menu(self):
        data = rom()
        writes = tb.writes_for([{'format': tb.FORMAT, 'spells': [{'id': '01', '범위': 2}]}], data)
        self.assertEqual([tb.cpu(o) for o, *_ in writes], ['26:8766'])

    def test_rejects_rom_whose_menu_already_differs(self):
        data = rom({0x01: 0x63})
        with self.assertRaisesRegex(ValueError, '맞지 않는 롬'):
            tb.writes_for([doc(('01', 9))], data)
        self.assertEqual(len(tb.writes_for([doc(('02', 9))], data)), 2)

    def test_field_mp_warning(self):
        from dq5spellfx import FIELD_MP, FIELD_TABLE
        d = bytearray(rom())
        d[lorom(FIELD_TABLE):lorom(FIELD_TABLE) + 2] = (0x84FA).to_bytes(2, 'little')     # 27 의 필드 처리기
        for site in FIELD_MP[0x84FA]:
            d[lorom(site)] = 3
        data = bytes(d)
        lines = tb.field_mp_warnings(tb.writes_for([doc(('27', 9))], data), data)
        self.assertEqual(len(lines), 1)
        self.assertIn('11:84FA', lines[0])
        self.assertEqual(tb.field_mp_warnings(tb.writes_for([doc(('27', 3))], data), data), [])
        self.assertEqual(tb.field_mp_warnings(tb.writes_for([doc(('01', 9))], data), data), [])


if __name__ == '__main__':
    unittest.main()
