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
        self.assertEqual(set(offsets), {f'text_{k}' for k in poker.TEXTS} | {f'label_{k}' for k, _ in poker.LABELS})

    def test_window_inside_is_felt_and_digits_are_fc(self):
        """FC 포커는 글 창·코인 상자 안이 바닥색(테두리만 흰색)이고 배당 표·코인 숫자가 FC 화면 숫자 타일이다."""
        import dq4menupatch
        files, offsets, _ = poker.build(DQ5.read_bytes(), DQ4, dq4menupatch.Font('galmuri7'))
        tiles = files['tiles.bin']

        def colors(n):
            raw = tiles[32 * n:32 * n + 32]
            return {sum((raw[(q // 2) * 16 + y * 2 + (q & 1)] >> (7 - x) & 1) << q for q in range(4))
                    for y in range(8) for x in range(8)}

        def runs(blob):
            names, i = [], 0
            while i < len(blob):
                k, i = blob[i], i + 1
                names += [int.from_bytes(blob[i + 2 * j:i + 2 * j + 2], 'little') for j in range(k)]
                i += 2 * k
            return names
        texts = files['texts.bin']
        text_names, i = [], 0
        while i < len(texts):
            lines, i = texts[i], i + 1
            for _ in range(lines):
                k, i = texts[i], i + 1
                text_names += [int.from_bytes(texts[i + 2 * j:i + 2 * j + 2], 'little') for j in range(k)]
                i += 2 * k
        # 글·이름표·배당 표 글자는 점 3 과 바탕 0(바닥색)만. 검정(2)이 있으면 창 안이 검게 칠해진다
        for n in [n for n in text_names if n != 0xFFFF] + runs(files['labels.bin']) + runs(files['pay.bin']):
            self.assertLessEqual(colors(n), {0, 3}, hex(n))
        self.assertEqual(colors(1) if len(tiles) > 32 else {0}, {0})
        prg = ines_prg()
        for t, fc in poker.BOX_TILES.items():
            self.assertEqual(tiles[32 * t:32 * t + 32], poker.fc_1bpp(prg, poker.FC_BOX, fc - 0x84), hex(t))
        digits = [int.from_bytes(files['digits.bin'][2 * k:2 * k + 2], 'little') for k in range(10)]
        for k, n in enumerate(digits):
            self.assertEqual(tiles[32 * n:32 * n + 32], poker.fc_1bpp(prg, poker.FC_DIGITS, k), k)

    def test_fc_tiles_match_fc_screen(self):
        """FC 포커 화면 CHR 덤프에서 본 타일: 숫자 0 은 3C 66 66 66 66 66 3C, 상자 모서리 86 은 3F 7F 70 60…."""
        prg = ines_prg()
        o = poker.FC_DIGITS[0] * 0x4000 + poker.FC_DIGITS[1] - 0x8000
        self.assertEqual(prg[o:o + 8].hex(), '003c66666666663c')
        o = poker.FC_BOX[0] * 0x4000 + poker.FC_BOX[1] - 0x8000 + 8 * 2
        self.assertEqual(prg[o:o + 8].hex(), '003f7f7060606060')


def ines_prg():
    from kr_patch.fc import ines
    return ines.prg(DQ4.read_bytes())


class PayLayoutTest(unittest.TestCase):
    """배당 표 자리는 FC 포커 화면 네임테이블(행 3~8, 이름 열 2·12, 숫자는 열 21 에서 끝, 패 6~8 한 자리는 열 10)과 같다."""
    def test_pay_columns(self):
        import re
        asm = (Path(poker.__file__).parent / 'dq4fcpoker.asm').read_text()

        def row(name):
            return [int(v) for v in re.search(rf'^{name}:\s+db ([\d, ]+)', asm, re.M).group(1).split(',')]
        hands, rows, cols, nums, lens = (row(n) for n in ('PayRows', 'PayRow', 'PayCol', 'PayNum', 'PayLen'))
        fc = {0: (3, 2, 21), 1: (4, 2, 21), 2: (5, 2, 21), 6: (6, 2, 10), 7: (7, 2, 10), 8: (8, 2, 10),
              3: (6, 12, 21), 4: (7, 12, 21), 5: (8, 12, 21)}
        for h, r, c, n, k in zip(hands, rows, cols, nums, lens):
            self.assertEqual((r, c, n + k - 1), fc[h], h)


if __name__ == '__main__':
    unittest.main()
