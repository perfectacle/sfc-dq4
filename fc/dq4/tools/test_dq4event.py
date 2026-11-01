"""저장 데이터(CRC·빈 칸)·장 시작 표·ルーラ 행선지와 이벤트 플래그 쓰는 곳 모으기(BRK 플래그 명령·절대 주소·
대화 스크립트·인물 블록·인물 목록 표)를 합성 PRG 로 검사한다."""
import binascii
import unittest

import dq4event as e
import dq4talk
from test_dq4npcblock import put, word, world_prg


def event_prg():
    prg = world_prg()
    put(prg, *e.NPC_CLEAR, [0x00, 0x00, 0x08, 0x06, 0xFF])
    # 대화 011(맵 00/00 슬롯 6): flag 05 |= 01, if flag& 05 02 → msg 0520
    put(prg, dq4talk.BANK, dq4talk.SCRIPTS + 2 * (0x011 - dq4talk.SCRIPT_FIRST), word(0x9000))
    put(prg, dq4talk.BANK, 0x9000, [0x18, 0x05, 0x01, 0x07, 0x1B, 0x05, 0x02, 0x45, 0x20, 0x3F])
    return prg


class SaveTests(unittest.TestCase):
    def test_crc_is_ccitt_with_3a3a(self):
        data = bytes(range(256)) * 3
        self.assertEqual(e.crc(data), binascii.crc_hqx(data, 0x3A3A))
        self.assertEqual(e.crc(b''), 0x3A3A)

    def test_slots_empty_and_checksum(self):
        sram = bytearray(0x2000)
        body = bytes((i * 7) & 0xFF for i in range(e.WORK_LEN))
        o = e.SLOTS[0] - 0x6000
        c = e.crc(body)
        sram[o:o + 2] = word(c)
        sram[o + 2:o + 2 + e.WORK_LEN] = body
        o1 = e.SLOTS[1] - 0x6000
        sram[o1:o1 + 5] = bytes([e.EMPTY] * 5)
        got = e.slots(sram)
        self.assertEqual([(a, empty, stored == calc) for a, empty, stored, calc, _ in got],
                         [(e.SLOTS[0], False, True), (e.SLOTS[1], True, False), (e.SLOTS[2], False, False)])
        s = e.as_sram(got[0][4])
        self.assertEqual(e.at(s, e.WORK, 2), body[0] | body[1] << 8)

    def test_at_little_endian(self):
        s = bytearray(0x300)
        s[e.GOLD - 0x6000:e.GOLD - 0x6000 + 3] = bytes([0x10, 0x27, 0x00])
        self.assertEqual(e.at(s, e.GOLD, 3), 10000)


class TableTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(32 * 0x4000)

    def test_start_table(self):
        put(self.prg, *e.START, [1, 2, 3, 4] + [5, 6, 7, 8] * 4)
        put(self.prg, e.INIT, e.LEADER, [0x80, 0x82, 0x83, 0x85, 0x80])
        put(self.prg, e.INIT, e.CHAPTER_GOLD, [10, 20, 30, 40, 50])
        put(self.prg, *e.CHAPTER_PLACE, [0, 1, 2, 3, 4])
        t = e.start_table(self.prg)
        self.assertEqual(t[0][:6], (1, 2, 3, 4, 0x80, 10))
        self.assertEqual(t[4][7], 4)

    def test_init_record_collects_five_bits(self):
        i = 1
        put(self.prg, e.INIT, e.CHAR_HP + i, [33])
        for s in range(6):
            put(self.prg, e.INIT, e.STAT_PTRS + 2 * s, word(0x9800 + 0x40 * s))
            put(self.prg, e.INIT, e.STAT_OFFS + s, [0x06 + s if s < 5 else 0x0E])
            put(self.prg, e.INIT, 0x9800 + 0x40 * s + 6 * i, [0x80, 0x00, 0x80, 0x00, 0x80, 0xFF])   # 0b10101
        put(self.prg, e.INIT, e.CHAR_ITEMS + 8 * i, [1, 2, 3, 4, 5, 6, 7, 8])
        w = e.init_record(self.prg, i)
        self.assertEqual((w[0x01], w[0x0C], w[0x06], w[0x0E], w[0x03]), (33, 33, 0b10101, 0b10101, 0b10101))
        self.assertEqual([w[0x13 + k] for k in range(8)], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(e.init_record(self.prg, 6)[0x0E], 0)       # 6·7 은 MP 0

    def test_towns_chapter5_offset(self):
        put(self.prg, *e.TOWN_PTR, word(0xB000))
        put(self.prg, e.TOWN_PTR[0], 0xB000 + 7 * 2, [0x81, 5, 6, 0x10, 0x01, 0, 0])
        put(self.prg, e.TOWN_PTR[0], 0xB000 + 7 * 3, [0x01, 0x22, 0x33, 0, 0, 0, 0])
        put(self.prg, e.TOWN_BANK, e.TOWN_GROUPS[0], [0x07, 0xFF])
        put(self.prg, e.TOWN_BANK, e.TOWN_GROUPS[1], [0x08, 0xFF])
        put(self.prg, e.TOWN_BANK, e.TOWN_RECORD, [2])
        put(self.prg, e.TOWN_BANK, e.TOWN_RECORD + 0x0F, [3])
        self.assertEqual(e.towns(self.prg, False), [(0, 0x07, 2, [0x81, 5, 6, 0x10, 0x01, 0, 0])])
        self.assertEqual(e.towns(self.prg, True)[0][:3], (0, 0x08, 3))
        self.assertEqual(e.town_dest([0x81, 5, 6, 0x10, 0x01]), '맵 10/01 (05,06)')
        self.assertEqual(e.town_dest([0x01, 0x22, 0x33, 0, 0]), '필드 1 (22,33)')

    def test_ending_and_entry_tables(self):
        put(self.prg, *e.ENDING, word(0x9F00))
        put(self.prg, e.ENDING[0], 0x9F00, [0x10, 0x01, 2, 3, 0x80, 0x85, 0x00, 0xA0, 2, 0xFF])
        put(self.prg, e.ENDING[0], 0xA000, [0x13, 0x22])
        self.assertEqual(e.ending_list(self.prg), [('scene', 0x10, 0x01, 2, 3, 0x80), ('pad', 0x85, 0xA000, [0x13, 0x22])])
        put(self.prg, *e.ENTRY, [1, 2, 3, 0x45, 5, 6, 0xFF])
        self.assertEqual(e.entry_table(self.prg), [(1, 2, 3, 4, 5, 5, 6)])


class CodeUseTests(unittest.TestCase):
    def setUp(self):
        self.prg = bytearray(32 * 0x4000)
        # 뱅크 10: LDA $63; CMP #03; LDA $64; CMP #01; BRK 05 CB 40; ...; 메시지 BRK 34 1B
        put(self.prg, 0x10, 0x9000, [0xA5, 0x63, 0xC9, 0x03, 0xA5, 0x64, 0xC9, 0x01, 0x00, 0x05, 0xCB, 0x40,
                                     0xEA, 0x00, 0x34, 0x1B, 0x8D, 0x80, 0x62])
        put(self.prg, 0x02, 0x9000, [0x00, 0x05, 0xEB, 0x03])          # 데이터 뱅크·두 비트: 모양만

    def test_flag_ops_and_likely_code(self):
        ops = e.flag_ops(self.prg)
        self.assertIn((0x10 * 0x4000 + 0x1008, 0x05, 0xCB, 0x40), ops)
        self.assertFalse(e.likely_code(0x02 * 0x4000 + 0x1000, 0xEB, 0x03))
        self.assertTrue(e.likely_code(0x10 * 0x4000, 0xDB, 0xBF))
        self.assertFalse(e.likely_code(0x10 * 0x4000, 0xDB, 0x3F))

    def test_code_uses_find_map_and_message(self):
        uses = {(n, m, kind): rest for n, m, kind, *rest in e.code_uses(self.prg)}
        where, near, msg, ok = uses[0x05, 0x40, 'set']
        self.assertEqual((where, near, msg, ok), ('BRK 10:$9008', (0x03, 0x01), 0x134, True))
        self.assertEqual(uses[0x05, None, 'write'][0], 'STA 10:$9010')
        self.assertFalse(uses[0x05, 0x03, 'test'][3])

    def test_cpu_addr_fixed_banks(self):
        self.assertEqual(e.cpu_addr(0x0F * 0x4000 + 5), (0x0F, 0xC005))
        self.assertEqual(e.cpu_addr(0x10 * 0x4000 + 5), (0x10, 0x8005))

    def test_bit_of(self):
        self.assertEqual(e.bit_of(0xBF, 'clear'), 0x40)
        self.assertEqual(e.bit_of(0x40, 'set'), 0x40)
        self.assertIsNone(e.bit_of(None, 'read'))


class WorldUseTests(unittest.TestCase):
    def setUp(self):
        self.prg = event_prg()

    def test_block_uses_pick_nearest_message(self):
        uses = e.block_uses(self.prg)
        self.assertIn(('npc|=', '', 0x00, 0x00, 6, (0x05, 0x40), 3, 0x510), uses)
        self.assertIn(('event', '', 0x00, 0x00, 6, 0x02, 7, 0x510), uses)
        self.assertIn(('npc&=', '밤 ', 0x00, 0x00, 6, (0x05, 0xBF), 0, None), uses)

    def test_talk_uses(self):
        out, who = e.talk_uses(self.prg)
        self.assertIn((0x05, 0x01, 'set', 0x011, 0x520), out)
        self.assertIn((0x05, 0x02, 'talk&', 0x011, 0x520), out)
        self.assertEqual(who[0x011], [('', 0x00, 0x00, 6)])

    def test_npc_tables(self):
        self.assertEqual(e.npc_tables(self.prg), [('clear', 0, 0, 0x06, 0x08, None), ('alt', 0, 0, 0x05, 0x01, 0xA000)])

    def test_flag_xref_merges_sources(self):
        rows = e.flag_xref(self.prg)
        kinds = sorted({k for _, k, *_ in rows[0x05]})
        self.assertEqual(kinds, ['clear', 'set', 'talk&', 'test'])
        self.assertIn((0x01, 'test', '맵 표 00/00 인물 목록 1C:$A000 로 바꿈', None), rows[0x05])


if __name__ == '__main__':
    unittest.main()
