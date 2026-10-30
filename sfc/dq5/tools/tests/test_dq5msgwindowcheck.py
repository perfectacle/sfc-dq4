"""전투 메시지 창 실측 도구의 기록 읽기: 두 롬의 실행 기록을 어디까지 견주는지, 효과 층 전송·OBJ·HDMA·화면 테두리."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402

from dq5msgwindowcheck import (WINDOW_WHITE, border_gaps, complete, effect_log, hdma_ranges, obj_boxes,  # noqa: E402
                               same_until, transfer_sizes)


class SameUntilTests(unittest.TestCase):
    def test_same_records(self):
        calls = ['600 248C39 5', '', '610 24A519 1']
        self.assertEqual(same_until(calls, list(calls)), 1 << 30)
        self.assertEqual(same_until([], []), 1 << 30)

    def test_first_difference(self):
        self.assertEqual(same_until(['600 248C39 5', '640 24A519 1'], ['600 248C39 5', '630 24A519 2']), 630)

    def test_one_record_ends_first(self):
        short = ['600 248C39 5', '610 24A519 1']
        long = short + ['610 24880A 0', '700 24A569 0']
        self.assertEqual(same_until(short, long), 610)
        self.assertEqual(same_until(long + ['', '900 EFF 0'], short), 610)
        self.assertEqual(same_until(short[:1], ['600 248C39 5', '650 24A519 1']), 650)
        self.assertEqual(same_until([], ['', '600 248C39 5']), 600)
        # 짧은 기록이 610 에서 끝나도 긴 기록의 다음 줄이 700 이면 699 까지는 둘이 같다
        self.assertEqual(same_until(short, short + ['700 24A569 0']), 700)


class EffectTransferTests(unittest.TestCase):
    CALLS = ['555 FX 0CC0 0380 -', '1100 FXID 06', '1102 EFF', '1102 FX 1CE0 0380 17 20', '1104 FX 18E0 0380 -',
             '1106 FX 1CE0 0380 -', '']

    def test_effect_log(self):
        self.assertEqual(effect_log(self.CALLS), [(555, 0x0CC0, 0x380, None, None, None),
                                                  (1102, 0x1CE0, 0x380, 17, 20, '06'),
                                                  (1104, 0x18E0, 0x380, None, None, '06'),
                                                  (1106, 0x1CE0, 0x380, None, None, '06')])

    def test_original_sizes(self):
        got = transfer_sizes('s', 'original', 21, self.CALLS)
        self.assertEqual(got['transfers'], {'0CC0': 1, '1CE0': 2, '18E0': 1})
        self.assertEqual(got['fxid'], ['06'])

    def test_raised_window_cuts_only_effect_layer(self):
        calls = [line.replace('1CE0 0380', '1CE0 0280') for line in self.CALLS]
        self.assertEqual(transfer_sizes('s', 'tall', 17, calls)['effect_size'], 0x280)
        with self.assertRaises(ValueError):
            transfer_sizes('s', 'tall', 17, self.CALLS)
        with self.assertRaises(ValueError):
            transfer_sizes('s', 'tall', 17, calls + ['1200 FX 0CC0 0280 -'])


class ObjTests(unittest.TestCase):
    def test_boxes(self):
        oam = bytearray(0x221)
        for i in range(128):
            oam[i * 4 + 1] = 0xF0
        oam[0:4] = bytes([0x40, 0x60, 0, 0])
        oam[4:8] = bytes([0xF8, 0x70, 0, 0])
        oam[0x200] = 0b1110          # 0: 큰 OBJ, 1: x 9비트 켜고 큰 OBJ
        oam[0x220] = 3                # 16·32
        self.assertEqual(obj_boxes(bytes(oam)), [(0x40, 0x60, 32), (-8, 0x70, 32)])


class HdmaTests(unittest.TestCase):
    def test_effect_registers_minus_battle(self):
        calls = ['1000 248C39 05E', '1050 FXID 0F', '1060 248C39 070', '1120 248C39 069', '1200 248C39 05E']
        text = '\n'.join(['990 2111 1 1 1', '1001 210E 51 168 4', '1055 210E 51 168 4', '1055 2111 55 167 226',
                           '1100 2132 54 168 4', '1130 2111 60 61 2', ''])
        self.assertEqual(hdma_ranges(calls, text), {'0F': {'2111': [55, 167], '2132': [54, 168]}})


class ScreenTests(unittest.TestCase):
    @staticmethod
    def dump(x, y, w, h, bottom=0x97):
        data = bytearray(0x800)
        for col in (x, x + w - 1):
            for r, tile in zip(range(y, y + h), [0x8C] + [0x8E] * (h - 2) + [bottom]):
                data[(r * 32 + col) * 2] = tile
        return bytes(data)

    def test_complete(self):
        self.assertTrue(complete(self.dump(2, 17, 28, 11), 2, 17, 28, 11))
        self.assertFalse(complete(self.dump(2, 17, 28, 11, bottom=0), 2, 17, 28, 11))
        self.assertFalse(complete(self.dump(2, 17, 28, 9), 2, 17, 28, 11))

    def test_border_gaps(self):
        image = Image.new('RGB', (256, 224))
        for row in range(21 * 8 - 7, 27 * 8 - 7 + 2):
            image.putpixel((17, row), WINDOW_WHITE)
        self.assertEqual(border_gaps(image, 2, 21, 7), 0)
        image.putpixel((17, 180), (0, 0, 0))
        self.assertEqual(border_gaps(image, 2, 21, 7), 1)


if __name__ == '__main__':
    unittest.main()
