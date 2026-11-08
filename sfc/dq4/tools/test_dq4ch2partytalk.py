import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ev  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2partytalkcheck as check  # noqa: E402
from dq4ch2slots import SLOTS  # noqa: E402


def _ctx(first=0x1000):
    return next(c for c in ev.contexts(first) if c.module is pt)


class PartyTalkTest(unittest.TestCase):
    def test_registered_in_its_slot(self):
        self.assertIn('dq4ch2partytalk', ev.EVENTS)
        ctx = _ctx()
        self.assertEqual(ctx.key, 'P')
        self.assertEqual(ctx.code_at, SLOTS['P'].code[0])
        self.assertEqual(list(ctx.msg), list(pt.MESSAGES))
        # 마지막으로 고른 줄은 예약된 바이트 값 flag 자리
        self.assertIn(pt.LAST[0], SLOTS['P'].byte_flags)

    def test_every_line_has_a_message_and_every_message_a_line(self):
        self.assertEqual({ln.message for ln in pt.LINES}, set(pt.MESSAGES))

    def test_record_bytes(self):
        line = pt.Line('3D/03', pt.KIRYL, 'x', priority=3, time='night', on=((0x60, 0x01),), lead=pt.ALENA)
        self.assertEqual(pt.record(line, 0x0EF7),
                         bytes((13, 3, pt.KIRYL, 2, 0xF7, 0x0E, 2, pt.ON, 0x60, 0x01, pt.LEAD, pt.ALENA, 0)))

    def test_lists_are_by_map_in_priority_order(self):
        rows = pt.lists(None)
        self.assertIn(pt.FIELD_KEY, rows)
        tempe = rows[(0x3D, 0x03)]
        self.assertEqual([r[1] for r in tempe], sorted(r[1] for r in tempe))

    def test_native_table_reads_back(self):
        ctx = _ctx()
        blob, at = pt.native(ctx)
        self.assertLessEqual(ctx.code_at + len(blob), SLOTS['P'].code[1])
        self.assertEqual(at, ctx.at)
        data = bytearray(0x400000)
        o = pt.ch1.lorom(ctx.code_at)
        data[o:o + len(blob)] = blob
        table = pt.table(bytes(data), at['maps'])
        rows = pt.lists(ctx.msg)
        self.assertEqual(set(table), set(rows))
        for key, recs in rows.items():
            self.assertEqual([r[4] | r[5] << 8 for r in recs], [row[3] for row in table[key]])
        ids = check.expected(bytes(data))
        self.assertEqual(ids, ctx.msg)

    def test_hook_goes_through_a_bank_05_stub(self):
        ctx = _ctx()
        [(stub_at, stub_orig, stub), (addr, orig, new)] = pt.hooks(ctx)
        self.assertEqual((addr, orig), (0x05D5B9, bytes.fromhex('009500' '009829')))
        self.assertEqual(new, bytes((0x20, 0xE8, 0xFE, 0xEA, 0xEA, 0xEA)))
        # 05:D5BF(기다림)는 05:D817 도 JSR 로 부르므로 훅이 닿지 않아야 한다
        self.assertLessEqual(addr + len(new), 0x05D5BF)
        talk = ctx.at['talk']
        self.assertEqual((stub_at, stub_orig), (0x05FEE8, bytes(8)))
        self.assertEqual(stub, bytes((0x00, 0x95, 0x00, 0x22, talk & 0xFF, talk >> 8 & 0xFF, talk >> 16, 0x60)))
        rom = ROOT / 'rom' / 'dq5.sfc'
        if rom.exists():
            data = rom.read_bytes()
            for at, want in ((addr, orig), (stub_at, stub_orig)):
                o = pt.ch1.lorom(at)
                self.assertEqual(data[o:o + len(want)], want)

    def test_no_brk_in_the_high_bank_code(self):
        # BRK 처리기는 DB 를 BRK 가 놓인 뱅크로 둔다. 뱅크 5C 에는 낮은 WRAM 거울이 없다
        blob, _ = pt.native(_ctx())
        self.assertNotIn(bytes((0x00, 0x09, 0x0A)), blob)
        self.assertNotIn(bytes((0x00, 0x95, 0x00)), blob)

    def test_check_cases_name_real_messages(self):
        for name, *_, want in check.CASES:
            for m in want:
                self.assertTrue(m is None or m in pt.MESSAGES, name)


if __name__ == '__main__':
    unittest.main()
