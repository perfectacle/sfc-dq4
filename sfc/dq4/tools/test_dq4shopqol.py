"""가게 편의 기능(목록 값 G·가진 개수·사기 전 확인)이 빌드 입력에서 빠지지 않았는지 롬 없이 본다."""
import re
import unittest
from pathlib import Path

import dq4sysmsg
import dq4windowname
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
        self.assertRegex(ASM, r'org \$06DDFC\n    JSR ShopBuyEquip')
        body = ASM[ASM.index('ShopBuyConfirm:'):]
        body = body[:body.index('assert pc()')]
        # 창(BRK 95)은 뱅크 06 에서 불러야 돈다. 뱅크 06 코드는 JSR 로 들어와 JSR 로 원래 루틴을 부른다
        self.assertNotIn('JSL', body)
        for need in ('JSR $F602', 'JSR $DFC4', 'JMP $DC37', 'db $00, $95, $32'):
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
        # 장비 갈래도 06:DE77 → 06:DCFF 로 06:DD39 를 지난다. 남은 $0F21(팔기 등의 사람 번호)만큼 더 주지 않게 1 을 둔다
        equip = ASM[ASM.index('ShopBuyEquip:'):]
        self.assertTrue(equip.startswith('ShopBuyEquip:\n    LDA #$01\n    STA.w $0F21\n'))
        tool = ASM[ASM.index('ShopBuyTool:'):]
        self.assertIn('STA.w $0F21', tool[:tool.index('JSL ShopQtyMax')])


class LowBankTest(unittest.TestCase):
    def test_brk_helpers_below_bank_40(self):
        # BRK 처리기는 DB 를 부른 뱅크로 둔다. 뱅크 40 이상(창 코드의 60)에서 부르면 WRAM 대신 열린 버스를 읽는다
        start = ASM.index('org !shop_low_spot')
        end = ASM.index('assert pc() <= !shop_low_end')
        for name in ('ShopHeldCount:', 'ShopQtyMax:', 'ShopQtyTotal:'):
            self.assertTrue(start < ASM.index(name) < end, name)
        self.assertNotIn('org', ASM[start + 4:end])


class SellQtyTest(unittest.TestCase):
    def test_messages_and_hooks(self):
        for n in (0x0C4, 0x0D6, 0x0D7, 0x0D8):
            self.assertIn('몇 개', dq4sysmsg.SPEECH[n])
        self.assertRegex(ASM, r'org \$06DF06\n    JSL ShopSellQty')
        self.assertRegex(ASM, r'org \$06DF35\n    JSL ShopSellExtra')

    def test_sell_code_below_bank_40_and_uses_own_count(self):
        self.assertLess(dq4windowname.SELL_SPOT_END - 1, 0x400000)
        start = ASM.index('org !shop_sell_spot')
        end = ASM.index('assert pc() <= !shop_sell_end')
        body = ASM[start:end]
        self.assertNotIn('org', body[4:])
        for name in ('ShopSellQty:', 'ShopSellCount:', 'ShopSellExtra:'):
            self.assertIn(name, body)
        # 팔기에서 $0F21 은 사람 번호. 개수는 $0F2C 에, 고른 칸보다 앞을 빼면 고른 칸 번호를 줄인다
        self.assertNotIn('STA.w $0F21', body)
        self.assertIn('STA.w $0F2C', body)
        self.assertIn('DEC.w $0F23', body)
        self.assertEqual(body.count('STZ.w $0F2C'), 2)


class SellEquippedTest(unittest.TestCase):
    def test_equipped_line_before_price(self):
        # 이름이 가나로 남은 물건 뒤 조사에서 찍기가 멈추므로 이름·조사를 넣지 않는다(dq4-window-check talk03)
        self.assertEqual(dq4sysmsg.SOURCE[0x03D], '지금 장착하고 있는 물건이다.')
        self.assertEqual(dq4sysmsg.TEXTS[0x03D][-1], dq4sysmsg.END_WAIT)
        body = ASM[ASM.index('ShopSellQty:'):ASM.index('ShopSellCount:')]
        self.assertIn('.done\n    JSR ShopSellWarn\n    RTL', body)
        done = ASM[ASM.index('ShopSellWarn:'):ASM.index('ShopSellExtra:')]
        # 고른 칸의 장비 중 비트($47)를 보고, 창을 닫은 뒤 3D 를 찍는다. 058 은 돌아간 원래 코드가 찍는다
        for need in ('LDX.w $0F23', 'JSR ShopSellSlot', 'LDA.b $47', 'db $00, $95, $00', 'LDA #$003D', 'JSL $248157', 'LDA.w $0F28'):
            self.assertIn(need, done)



class CancelBackTest(unittest.TestCase):
    def test_cancel_returns_to_own_list_without_intro(self):
        # 사기 「아니요」 는 「사시려고요?」(06:DC2F) 를 건너 목록 창(06:DC37)으로
        no = ASM[ASM.index('ShopBuyConfirm:'):ASM.index('ShopBuyEquip:')]
        self.assertIn('JMP $DC37', no)
        self.assertNotIn('JMP $DC2F', no)
        self.assertNotIn('$97, $13', no[no.index('.no'):])
        # 팔기 「아니요」 는 사기/팔기 창(06:DF50) 대신 같은 사람의 팔기 목록(06:DEC6)으로
        self.assertRegex(ASM, r'org \$06DF48\n    JMP ShopSellNo')
        body = ASM[ASM.index('ShopSellNo:'):ASM.index('assert pc() <= !shop_qty_end')]
        self.assertNotIn('$97, $13', body)
        for need in ('STZ.w $0F2C', 'db $00, $95, $00', 'LDA #$18', 'JSR $DFC4', 'JMP $DEC9'):
            self.assertIn(need, body)


class QtyCapTest(unittest.TestCase):
    def test_number_window_hooks(self):
        self.assertRegex(ASM, r'org \$04C970\n    JSL WnQtyUp')
        self.assertRegex(ASM, r'org \$04C995\n    JSL WnQtyDown')
        for name in ('WnQtyUp:', 'WnQtyDown:'):
            body = ASM[ASM.index(name):]
            body = body[:body.index('RTL\n\n') if name == 'WnQtyDown:' else body.index('WnQtyZero:')]
            # $0F2C 가 0 이면 원래처럼 0~9, 아니면 끝 자리(4)만 1~최대
            self.assertIn('LDA.l $7E0F2C', body)
            self.assertIn('CMP #$04', body)

    def test_both_quantity_windows_set_max(self):
        for name, end in (('ShopBuyTool:', 'ShopGiveExtra:'), ('ShopSellQty:', 'ShopSellCount:')):
            body = ASM[ASM.index(name):ASM.index(end)]
            at = body.index('db $00, $95, $5C')
            self.assertIn('LDA $01,S', body[:at])
            self.assertIn('STA.w $0F2C', body[:at])
        buy = ASM[ASM.index('ShopBuyTool:'):ASM.index('ShopGiveExtra:')]
        self.assertIn('STZ.w $0F2C', buy[buy.index('db $00, $95, $5C'):])

class SellPriceTest(unittest.TestCase):
    def test_cannot_sell_phrase(self):
        self.assertEqual(dq4windowtext.FIXED[dq4windowtext.CANNOT_SELL], '판매불가')
        self.assertIn('JSR ShopListRes', ASM)


if __name__ == '__main__':
    unittest.main()
