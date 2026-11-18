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

    def test_pay_rows_blink_and_lamp(self):
        """배당을 셀 때 FC 17:$9E80 이 숨기는 것은 배당 표의 그 무늬 줄(행 4·6…18, 열 24~29)이고, 바탕 칸 8F 는
        색 2 로 찬 칸이다. 램프 0D(흰 램프)는 0C 와 같은 자리의 꽉 찬 색 1."""
        self.assertEqual(slot.pay_rows(self.prg), [(18 - 2 * s, 24) for s in range(8)])
        nt, _ = slot.nametable(self.prg)
        for r, c in slot.pay_rows(self.prg):
            self.assertNotIn(slot.PAY_BLANK, nt[r * 32 + c:r * 32 + c + 2], (r, c))
            self.assertEqual(nt[(r + 1) * 32 + c:(r + 1) * 32 + c + 6], bytes([slot.PAY_BLANK]) * 6, (r, c))
        self.assertEqual(slot.FILLS[slot.PAY_BLANK], bytes(8) + b'\xff' * 8)
        self.assertEqual(slot.pay_cells(self.prg)[:2], bytes((24 * 8, 17 * 8 - 1)))
        sheet = slot.obj(self.prg)
        self.assertEqual(sheet[32 * slot.COVER_NAME:32 * slot.COVER_NAME + 32], slot.snes4(slot.FILLS[slot.PAY_BLANK]))
        lamp = slot.rd(self.prg, slot.SMALL_TILES + 0x0D * 16, 16)
        self.assertEqual(lamp.hex(), '1c' * 8 + '00' * 8)
        self.assertEqual(len(slot.palettes(self.prg)[1]), 32 * 5)


if __name__ == '__main__':
    unittest.main()
