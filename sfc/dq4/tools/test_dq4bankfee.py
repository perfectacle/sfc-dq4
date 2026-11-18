import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools')]

import dq4bankfee as m  # noqa: E402
import dq4sysmsg  # noqa: E402

DQ5 = ROOT / 'rom' / 'dq5.sfc'


class CodeTests(unittest.TestCase):
    def test_code_fits_its_free_space_below_bank_40(self):
        # BRK 처리기는 BRK 가 놓인 뱅크를 DB 로 둔다: 40 이상 뱅크에서는 낮은 WRAM 이 보이지 않는다
        data, labels = m.code()
        self.assertLessEqual(m.CODE_AT + len(data), m.CODE_END)
        self.assertLess(m.CODE_AT >> 16, 0x40)
        self.assertLessEqual({'deposit', 'withdraw', 'pay', 'cancel'}, set(labels))

    def test_sites_keep_their_length(self):
        writes = m.writes()
        for w in writes[1:]:
            self.assertEqual(len(bytes.fromhex(w['hex'])), len(bytes.fromhex(w['orig'])), w['at'])
            self.assertEqual(bytes.fromhex(w['hex'])[0], 0x22)

    def test_messages_have_text(self):
        # 원래 빈 메시지 자리에 글을 넣고, 0C2 는 다음 글(0E4·0CD) 앞에서 기다림
        self.assertIn(m.NOTICE, dq4sysmsg.SPEECH)
        self.assertIn(m.SHORT, dq4sysmsg.SPEECH)
        self.assertIn('10골드', dq4sysmsg.SPEECH[m.NOTICE])
        self.assertIn(m.SHORT, dq4sysmsg.WAIT)
        self.assertNotIn(m.NOTICE, dq4sysmsg.WAIT)


@unittest.skipUnless(DQ5.is_file(), 'rom/dq5.sfc')
class RomTests(unittest.TestCase):
    def test_sites_are_the_original_bytes_and_the_code_space_is_free(self):
        rom = DQ5.read_bytes()

        def at(addr, n):
            o = (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)
            return rom[o:o + n]
        for site, orig in ((m.DEPOSIT_SITE, m.DEPOSIT_ORIG), (m.WITHDRAW_SITE, m.WITHDRAW_ORIG), (m.PAY_SITE, m.PAY_ORIG)):
            self.assertEqual(at(site, len(orig)), orig, hex(site))
        self.assertEqual(set(at(m.CODE_AT, m.CODE_END - m.CODE_AT)), {0x00})


if __name__ == '__main__':
    unittest.main()
