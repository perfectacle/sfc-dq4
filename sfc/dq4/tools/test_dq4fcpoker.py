import os
from pathlib import Path
import unittest

import dq4fcpoker as poker

ROOT = Path(__file__).resolve().parents[3]
DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'


def card(rank, suit):
    """rank: 'A23456789TJQK' 의 글자, suit 0~3."""
    return 'A23456789TJQK'.index(rank) * 4 + suit


J = poker.JOKER


class FcHandTest(unittest.TestCase):
    """FC 17:$8203 판정의 갈래(코드 읽기를 옮긴 fc_hand). 롬의 판정과는 걷기 검사(towns_poker_*)가 견준다."""

    def hand(self, *cards):
        return poker.fc_hand(list(cards))

    def test_royal_needs_ace_and_king_without_joker(self):
        royal = [card(r, 1) for r in 'TJQKA']
        self.assertEqual(self.hand(*royal), 0)
        # 조커가 든 로열은 스트레이트 플러시
        self.assertEqual(self.hand(card('T', 1), card('J', 1), card('Q', 1), card('K', 1), J), 2)

    def test_five_card_needs_joker(self):
        self.assertEqual(self.hand(card('7', 0), card('7', 1), card('7', 2), card('7', 3), J), 1)

    def test_straights_wrap_only_at_ace(self):
        self.assertEqual(self.hand(card('A', 0), card('2', 1), card('3', 2), card('4', 3), card('5', 0)), 6)
        self.assertEqual(self.hand(card('T', 0), card('J', 1), card('Q', 2), card('K', 3), card('A', 0)), 6)
        self.assertIsNone(self.hand(card('J', 0), card('Q', 1), card('K', 2), card('A', 3), card('2', 0)))
        # 조커가 빈 한 칸을 메움
        self.assertEqual(self.hand(card('4', 0), card('5', 1), card('7', 2), card('8', 3), J), 6)

    def test_full_house_and_pairs(self):
        self.assertEqual(self.hand(card('9', 0), card('9', 1), card('9', 2), card('K', 0), card('K', 1)), 4)
        # 투 페어 + 조커는 풀 하우스
        self.assertEqual(self.hand(card('9', 0), card('9', 1), card('K', 2), card('K', 0), J), 4)
        self.assertEqual(self.hand(card('9', 0), card('9', 1), card('K', 2), card('K', 0), card('2', 0)), 8)
        # 원 페어는 배당 없음
        self.assertIsNone(self.hand(card('9', 0), card('9', 1), card('K', 2), card('5', 0), card('2', 0)))
        # 원 페어 + 조커는 스리 카드
        self.assertEqual(self.hand(card('9', 0), card('9', 1), card('K', 2), card('5', 0), J), 7)

    def test_flush(self):
        self.assertEqual(self.hand(*(card(r, 2) for r in '29TQK')), 5)


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file() and os.environ.get('DQ4_ASSETS') and os.environ.get('DQ4_GALMURI'),
                     'FC·DQ5 롬과 DQ4_ASSETS·DQ4_GALMURI 가 필요')
class FcPokerDataTest(unittest.TestCase):
    def test_tiles_and_tables(self):
        import dq4menupatch
        files, offsets, _ = poker.build(DQ5.read_bytes(), DQ4, dq4menupatch.Font('galmuri7'))
        self.assertLessEqual(len(files['tiles.bin']) // 32, poker.TILE_LIMIT)
        self.assertLessEqual(len(files['tiles.bin']), (poker.TILES_END - poker.TILES_AT) + (poker.CODE_END - poker.CODE_AT))
        self.assertEqual(len(files['cards.bin']), 54 * poker.CELL_W * poker.CELL_H * 2)
        # 배당 표(17:$81D6): 로열 500 … 투 페어 1, 풀 하우스는 8
        pay = [int.from_bytes(files['payout.bin'][2 * i:2 * i + 2], 'little') for i in range(9)]
        self.assertEqual(pay, [500, 100, 50, 20, 8, 5, 4, 2, 1])
        self.assertEqual(set(offsets), {f'text_{k}' for k in poker.TEXTS} | {f'label_{k}' for k, _, _ in poker.LABELS})


if __name__ == '__main__':
    unittest.main()
