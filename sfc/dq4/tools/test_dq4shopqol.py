"""가게 편의 기능(목록 값 G·가진 개수·사기 전 확인)이 빌드 입력에서 빠지지 않았는지 롬 없이 본다."""
import re
import unittest
from pathlib import Path

import dq4sysmsg
import dq4windowtext

ASM = (Path(__file__).resolve().parent / 'dq4windowname.asm').read_text()


class HeldCountTest(unittest.TestCase):
    def test_numbers_are_consecutive_bytes(self):
        # ShopHeldCount 는 첫 번호 + 개수 − 1 로 문구를 고른다
        numbers = {}
        for k, (jp, _, w) in enumerate(dq4windowtext.phrases()):
            if w is None:
                numbers.setdefault(jp, k)
        held = [numbers[k] for k in dq4windowtext.HELD_COUNT]
        self.assertEqual(held, list(range(held[0], held[0] + 12)))
        self.assertLess(held[-1], dq4windowtext.FIXED_PREFIX_LIMIT)
        self.assertLessEqual(len(dq4windowtext.phrases()), dq4windowtext.FIXED_PREFIX_LIMIT)

    def test_hooks_both_sites(self):
        for site in ('$04C3B1', '$04C508'):
            self.assertRegex(ASM, rf'org {re.escape(site)}\n    JML ShopHeldCount')


class BuyConfirmTest(unittest.TestCase):
    def test_messages(self):
        for n in range(0x064, 0x068):
            self.assertIn('{N}골드', dq4sysmsg.SPEECH[n])
        # 확인 앞 메시지가 산 것처럼 말하지 않는다
        self.assertNotIn('알겠습니다', dq4sysmsg.SPEECH[0x008])
        self.assertNotIn('감사합니다', dq4sysmsg.SPEECH[0x009])

    def test_hooks_both_buy_paths_in_bank_06(self):
        for site in ('$06DCDF', '$06DDFC'):
            self.assertRegex(ASM, rf'org {re.escape(site)}\n    JSR ShopBuyConfirm')
        body = ASM[ASM.index('ShopBuyConfirm:'):]
        body = body[:body.index('warnpc')]
        # 창(BRK 95)은 뱅크 06 에서 불러야 돈다. 뱅크 06 코드는 JSR 로 들어와 JSR 로 원래 루틴을 부른다
        self.assertNotIn('JSL', body)
        for need in ('JSR $F602', 'JSR $DFC4', 'JMP $DC2F', 'db $00, $95, $32'):
            self.assertIn(need, body)


class SellPriceTest(unittest.TestCase):
    def test_cannot_sell_phrase(self):
        self.assertEqual(dq4windowtext.FIXED[dq4windowtext.CANNOT_SELL], '판매불가')
        self.assertIn('JSR ShopListRes', ASM)


if __name__ == '__main__':
    unittest.main()
