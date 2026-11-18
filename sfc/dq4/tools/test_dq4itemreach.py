"""장 빌드 롬이 주는 물건 집합(dq4itemreach)의 장 가르기와 가게 키 표 읽기."""
import unittest

import dq4itemreach as ir


class FakeRom:
    def __init__(self, data):
        self.d = data

    def u8(self, a):
        return self.d.get(a, 0)


class ChapterTest(unittest.TestCase):
    def test_groups_take_the_chapter_of_their_fc_groups(self):
        self.assertEqual(ir.group_chapter(0x36), 1)          # 바트랜드(서장·1장, chapter 없음)
        self.assertEqual(ir.group_chapter(0x3D), 2)          # サントハイム·テンペ·フレノール
        self.assertEqual(ir.group_chapter(0x3E), 3)          # レイクナバ·きたのどうくつ
        self.assertEqual(ir.group_chapter(0x41), 4)
        self.assertEqual(ir.group_chapter(0x46), 5)
        self.assertIsNone(ir.group_chapter(0x01))            # DQ5 그룹(빌린 맵)

    def test_events_grow_with_the_chapter(self):
        import dq4ch2frenol
        one, two, three = ir._events(1), ir._events(2), ir._events(3)
        self.assertIn(dq4ch2frenol.THIEF_KEY, two)
        self.assertTrue(one <= two <= three)


class KeyTableTest(unittest.TestCase):
    def test_rows_follow_the_long_load_in_the_hook(self):
        base = ir.SHOP_KEY_CODE
        data = {base + 3: 0xBF, base + 4: 0x74, base + 5: 0xFE, base + 6: 0x3C}
        rows = [(0x36, 0, 3, 0x60), (0x3D, 3, 3, 0x62)]
        at = 0x3CFE74
        for r in rows:
            for i, b in enumerate(r):
                data[at + i] = b
            at += 4
        data[at] = 0xFF
        self.assertEqual(ir.key_rows(FakeRom(data)), rows)


if __name__ == '__main__':
    unittest.main()
