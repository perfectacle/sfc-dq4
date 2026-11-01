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
        self.assertRegex(ASM, r'org \$06DCDF\n    JSR ShopBuyTool')
        self.assertRegex(ASM, r'org \$06DDFC\n    JSR ShopBuyConfirm')
        body = ASM[ASM.index('ShopBuyConfirm:'):]
        body = body[:body.index('assert pc()')]
        # 창(BRK 95)은 뱅크 06 에서 불러야 돈다. 뱅크 06 코드는 JSR 로 들어와 JSR 로 원래 루틴을 부른다
        self.assertNotIn('JSL', body)
        for need in ('JSR $F602', 'JSR $DFC4', 'JMP $DC2F', 'db $00, $95, $32'):
            self.assertIn(need, body)


class MultiBuyTest(unittest.TestCase):
    def test_messages(self):
        for n in (0x09C, 0x09D, 0x0AB, 0x0C3):
            self.assertIn('몇 개', dq4sysmsg.SPEECH[n])
        self.assertIn('dw $009C, $009D, $00AB, $00C3', ASM)

    def test_tool_path_asks_quantity_in_bank_06(self):
        body = ASM[ASM.index('ShopBuyTool:'):]
        body = body[:body.index('assert pc()')]
        # 창(BRK 95)은 뱅크 06 코드에서. 수 창 5C 의 끝 자리 $0B02 를 개수로, 나머지 개수는 물건을 줄 때 더 준다
        for need in ('db $00, $95, $5C', 'JSL ShopQtyMax', '$0B02', 'JMP ShopBuyConfirm', 'ShopGiveExtra:'):
            self.assertIn(need, body)
        self.assertRegex(ASM, r'org \$06DD39\n    JSR ShopGiveExtra')


class LowBankTest(unittest.TestCase):
    def test_brk_helpers_below_bank_40(self):
        # BRK 처리기는 DB 를 부른 뱅크로 둔다. 뱅크 40 이상(창 코드의 60)에서 부르면 WRAM 대신 열린 버스를 읽는다
        start = ASM.index('org !shop_low_spot')
        end = ASM.index('assert pc() <= !shop_low_end')
        for name in ('ShopHeldCount:', 'ShopQtyMax:', 'ShopQtyTotal:'):
            self.assertTrue(start < ASM.index(name) < end, name)
        self.assertNotIn('org', ASM[start + 4:end])


class SellPriceTest(unittest.TestCase):
    def test_cannot_sell_phrase(self):
        self.assertEqual(dq4windowtext.FIXED[dq4windowtext.CANNOT_SELL], '판매불가')
        self.assertIn('JSR ShopListRes', ASM)


if __name__ == '__main__':
    unittest.main()
