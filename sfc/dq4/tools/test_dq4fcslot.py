from pathlib import Path
import unittest

import dq4fcslot as slot

DQ4 = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'


@unittest.skipUnless(DQ4.is_file(), 'FC 롬이 필요')
class FcSlotDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prg = slot.fc_prg(DQ4)

    def test_screen_is_built_like_fc(self):
        nt, attrs = slot.nametable(self.prg)
        self.assertEqual(len(nt), 32 * slot.FC_ROWS)
        self.assertEqual(len(attrs), 0x40)
        # 「JACKPOT」 줄(17:$A806 목록의 첫 조각, PPU $2048)
        self.assertEqual(nt[2 * 32 + 8:2 * 32 + 20], bytes(range(0x90, 0x9C)))
        # 속성 표 뒤쪽은 행 무늬 31줄째가 채운다(0 이면 배당 표 아래 두 줄 색이 틀림)
        self.assertTrue(any(attrs[0x26:0x30]))

    def test_every_tile_has_a_source(self):
        tiles, words = slot.bg(self.prg)
        self.assertEqual(len(words), 0x800)
        self.assertEqual(len(tiles) % 32, 0)
        self.assertLess(len(tiles) // 32, 0x400)

    def test_reels_lines_and_payout(self):
        md = slot.machine_data(self.prg)
        self.assertEqual(len(md), slot.MACHINES * 97)
        self.assertEqual([md[k * 97] for k in range(slot.MACHINES)], [0x0F] * 4 + [0x1F])
        for k in range(slot.MACHINES):
            self.assertTrue(set(md[k * 97 + 1:(k + 1) * 97]) <= set(range(1, 8)), k)
        # 기계 4 의 세 릴은 777 로 시작
        self.assertEqual([md[4 * 97 + 1 + r * 32] for r in range(3)], [7, 7, 7])
        lines, pay, sympal, xs = slot.tables(self.prg)
        self.assertEqual(lines, bytes((3, 4, 5, 6, 7, 8, 0, 1, 2, 6, 4, 2, 0, 4, 8)))
        self.assertEqual([int.from_bytes(pay[2 * i:2 * i + 2], 'little') for i in range(8)],
                         [5, 10, 20, 50, 100, 200, 500, 1000])
        self.assertEqual(xs, bytes((0x38, 0x68, 0x98)))
        self.assertEqual(len(sympal), 8)


if __name__ == '__main__':
    unittest.main()
