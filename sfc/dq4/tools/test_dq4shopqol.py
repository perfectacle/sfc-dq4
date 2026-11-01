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
        self.assertIn('$97, $13', no[no.index('.no'):])
        # 팔기 「아니요」 는 사기/팔기 창(06:DF50) 대신 같은 사람의 팔기 목록(06:DEC6)으로
        self.assertRegex(ASM, r'org \$06DF48\n    JMP ShopSellNo')
        body = ASM[ASM.index('ShopSellNo:'):ASM.index('assert pc() <= !shop_qty_end')]
        for need in ('STZ.w $0F2C', 'db $00, $95, $00', 'LDA #$18', 'JSR $DFC4', 'JMP $DEC6'):
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
        # 수 창을 열기 전에 $0F2C = 최대 | 40(열림), 팔기는 | 80. 사기는 닫자마자 0
        buy = ASM[ASM.index('ShopBuyTool:'):ASM.index('ShopGiveExtra:')]
        at = buy.index('JSL ShopQtyAsk')
        self.assertIn('ORA #$40', buy[:at])
        self.assertIn('STA.w $0F2C', buy[:at])
        self.assertIn('STZ.w $0F2C', buy[buy.index('db $00, $95, $5C'):])
        sell = ASM[ASM.index('ShopSellQty:'):ASM.index('ShopSellCount:')]
        at = sell.index('JSL ShopSellAsk')
        self.assertIn('ORA #$C0', sell[:at])
        self.assertIn('STA.w $0F2C', sell[:at])
        for name in ('ShopQtyAsk:', 'ShopSellAsk:'):
            body = ASM[ASM.index(name):]
            self.assertIn('JSL $248157', body[:body.index('RTL')])


class QtyPreviewTest(unittest.TestCase):
    def test_labels_in_messages(self):
        # 개수 메시지 둘째·셋째 줄이 라벨, 숫자는 QpFrame 이 그 줄 뒤에 쓴다
        for n in (0x09C, 0x09D, 0x0AB, 0x0C3):
            self.assertTrue(dq4sysmsg.SPEECH[n].endswith('/쓰는 돈/남는 돈'), hex(n))
        for n in (0x0C4, 0x0D6, 0x0D7, 0x0D8):
            self.assertTrue(dq4sysmsg.SPEECH[n].endswith('/받는 돈/판 뒤'), hex(n))

    def test_frame_hook_draws_only_while_open(self):
        self.assertRegex(ASM, r'org \$04D16D\n    JSL QpFrame')
        body = ASM[ASM.index('QpFrame:'):ASM.index('\nQpWindow:')]
        plain, shop = body.split('\n.shop\n')
        self.assertIn('AND #$40', plain)         # 수 창이 떠 있을 때만(뒤의 예/아니요 깜박임에서는 쓰지 않음)
        self.assertIn('LDA.w $0AD9\n    CLC\n    RTL', plain)   # 아니면 덮은 LDA $0AD9 / CLC 그대로
        self.assertIn('LDA.l $7E0B02', shop)     # 끝 자리 = 개수
        self.assertIn('JSR QpDraw', shop)
        draw = ASM[ASM.index('QpDraw:'):ASM.index('QpNumber:')]
        for need in ('$7E0F28', '$7E2019', 'BMI .sell', '!qp_row1', '!qp_row2'):
            self.assertIn(need, draw)

    def test_rows_follow_message_lines(self):
        self.assertEqual(dq4windowname.QP_ROWS, (21, 23))


class QtyArrowTest(unittest.TestCase):
    # 개수 창은 ▲ / 숫자 / ▼ 세 줄: 1 부터, 앞자리 0 없음, 깜박이지 않음, 더 갈 수 있는 쪽 화살표만, 끝에서 멈춤
    def test_no_blink(self):
        shop = ASM[ASM.index('QpFrame:'):ASM.index('\nQpWindow:')].split('\n.shop\n')[1]
        self.assertIn('JSR QpWindow', shop)
        self.assertIn('LDA #$00', shop)          # 깜박임 박자를 늘 양수로(숫자 쪽)
        self.assertNotIn('$0AD9', shop)

    def test_window_cells(self):
        body = ASM[ASM.index('\nQpWindow:'):]
        body = body[:body.index('RTS')]
        self.assertIn('INC                     ; 처음 열린 0 을 1 로', body)
        self.assertIn('LDX.w #$A07B', body)      # ▲ = ▼(7B) 상하 반전
        self.assertIn('LDX.w #$207B', body)
        self.assertIn('STA.l $7E0AD7', body)     # 왼쪽·오른쪽으로 옮긴 커서를 끝 자리로
        for col in ('$7E0A56', '$7E0A5C', '$7E0A5E'):
            self.assertIn(col, body)             # 커서 자리 칸 좌표표를 숫자 칸·화면 밖으로
        for need in ('!qp_line', '!qp_up', '!qp_num', '!qp_down'):
            self.assertIn(need, body)
        self.assertEqual((dq4windowname.QP_NUM_X, dq4windowname.QP_NUM_Y), (0x1A, 7))

    def test_tall_record_only_for_shop(self):
        # 가게 개수 창만 높이 5 레코드(▲ / 숫자 / ▼). 5C 는 맡기는 곳과 같이 쓰므로 원래 레코드는 그대로
        rec = ASM[ASM.index('ShopQtyRec:'):ASM.index('ShopSellRec:')]
        self.assertIn('db $16, $05, $08, $25, $00, $01, $01, $FF, $52', rec)   # 52 = 수 창 입력 갈래
        self.assertEqual(dq4windowname.QTY_RECORD[:6], bytes.fromhex('160508230001'))
        for site in dq4windowname.QP_OPEN_SITES:
            self.assertRegex(ASM, rf'org \${site:06X}\n    JSL ShopOpenRes\n    NOP')
        res = ASM[ASM.index('ShopOpenRes:'):]
        res = res[:res.index('RTL')]
        for need in ('CPX.w #$005C*2', 'AND.w #$0040', 'LDA.w #ShopQtyRec', 'STA.b $DA'):
            self.assertIn(need, res)

    def test_stops_at_ends(self):
        up = ASM[ASM.index('WnQtyUp:'):ASM.index('WnQtyZero:')]
        self.assertIn('LDA $01,S               ; 최대에서 멈춘다', up)
        down = ASM[ASM.index('WnQtyDown:'):ASM.index('WnQtyDone:')]
        self.assertIn('LDA #$01                ; 1 에서 멈춘다', down)
        done = ASM[ASM.index('WnQtyDone:'):]
        done = done[:done.index('RTL')]
        self.assertIn('JSR QpWindow', done)      # 누른 그 프레임에 화살표·금액도 새 개수로
        self.assertIn('JSR QpDraw', done)


class SellLinesTest(unittest.TestCase):
    def test_no_appraisal_line(self):
        # 값이 목록에 보이므로 050 을 건너 058 이 바로 묻는다
        self.assertRegex(ASM, r'org \$06DEFE\n    BRA \$06DF06')
        for n in (0x058, 0x059, 0x05A, 0x05B):
            self.assertIn('{N}골드에', dq4sysmsg.SPEECH[n])
            self.assertNotIn('음, ', dq4sysmsg.SPEECH[n])

class SellPriceTest(unittest.TestCase):
    def test_cannot_sell_phrase(self):
        self.assertEqual(dq4windowtext.FIXED[dq4windowtext.CANNOT_SELL], '판매불가')
        self.assertIn('JSR ShopListRes', ASM)


if __name__ == '__main__':
    unittest.main()
