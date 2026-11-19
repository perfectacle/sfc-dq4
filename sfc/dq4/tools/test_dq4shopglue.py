import unittest
from unittest import mock

import dq4windowname as wn
import dq4windowtext
from test_dq4windowname import ASM, TEXT, FakeAsar, base_rom


class ShopCompareGlueTest(unittest.TestCase):
    """가게 동료 창(3A)에서 이름이 다섯째 칸까지 차고 비교 값이 둘 다 세 자리면 값이 이름에 붙는다. 빌드가 장마다 그런 이름을
    세어 SHOP_FULL_NAMES(2장 크리프트, 1장 이름 입력 주인공) 밖이 생기면 멈춘다. 실제 글꼴 셈은 빌드(DQ4_GALMURI)가 한다."""

    def test_names_come_from_the_chapters(self):
        names = wn.shop_member_names()
        self.assertEqual(sorted(names), [1, 2, 3])
        self.assertIn('크리프트', names[2][0])
        self.assertTrue(names[1][1])
        self.assertFalse(names[2][1] or names[3][1])

    def test_count_uses_name_cells(self):
        def cols(font, text):
            return [b''] * (wn.SHOP_NAME_CELLS if text == '크리프트' else 3)
        with mock.patch.object(dq4windowtext, 'columns', side_effect=cols):
            self.assertEqual(wn.shop_full_names(object()), wn.SHOP_FULL_NAMES)

    def test_build_stops_on_a_new_full_name(self):
        def cols(font, text):
            return [b''] * (wn.SHOP_NAME_CELLS if text in ('크리프트', '브라이') else 2)
        with mock.patch.object(dq4windowtext, 'columns', side_effect=cols), \
                self.assertRaisesRegex(ValueError, '다섯째 칸까지 차는 사람이 늘었음'):
            with mock.patch.object(dq4windowtext, 'build', return_value=(TEXT, {})), \
                    mock.patch.object(wn.subprocess, 'run', FakeAsar()):
                wn.apply(bytes(base_rom()), object(), 'asar')


if __name__ == '__main__':
    unittest.main()
