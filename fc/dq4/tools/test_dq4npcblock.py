"""인물 블록(레코드 길이·명령 길이·넘침·점프 대상·이벤트 번호·슬롯 순번)을 합성 PRG 로 검사한다."""
import unittest

import dq4map
import dq4npcblock as nb

PRG_SIZE = 32 * 0x4000


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


DAY = [0x26, 0x10, 0x05, 0x27, 0x40, 0x80, 0x62, 0x88, 0x02]       # 메시지 0510, $6280 |= 40, 이벤트 02
NIGHT = [0x28, 0xBF, 0x80, 0x62, 0x83, 0xFC]                        # $6280 &= BF, 상대 점프 −4


def world_prg():
    """맵 03/00(낮 인물 2명 중 하나는 밤에도)과 이벤트 목록 하나."""
    prg = bytearray(PRG_SIZE)
    put(prg, *dq4map.GROUPS, word(0xA000) + [0xFF, 0xFF])
    put(prg, 0x17, 0xA000, [0x10, 0x00, 0x90, 0xFF])                 # 그룹 0 순번 0 만
    put(prg, nb.NPC_BANK, 0x8000, word(0x9000))
    r1 = [0x10, 0, 0, 0, 0x11, 0x05, 0x06] + [len(DAY)] + DAY
    r2 = [0x18 | 0x07, 0, 0, 0, 0x12, 0x07, 0x08] + [1, 0x2A] + [len(NIGHT)] + NIGHT
    put(prg, nb.NPC_BANK, 0x9000, r1 + r2 + [0x00])
    put(prg, *dq4map.EVENT_LISTS, word(0x9800))
    put(prg, 0x1C, 0x9800, [0x00, 0x00, 0x01, 0x05, 0x00, 0xA0, 0xFF])
    put(prg, 0x1C, 0xA000, [0x10, 0, 0, 0, 0x13, 1, 1, 2, 0x8B, 0x26, 0x00])  # 모르는 명령 8B, 넘치는 26
    put(prg, nb.EVENTS[0], nb.EVENTS[1] + 2 * 2, word(0xB123))
    return prg


class RecordTests(unittest.TestCase):
    def test_record_lengths(self):
        prg = world_prg()
        self.assertEqual(nb.record_len(prg, nb.NPC_BANK, 0x9000), (8 + len(DAY), [(0x9008, len(DAY))]))
        n, blocks = nb.record_len(prg, nb.NPC_BANK, 0x9000 + 8 + len(DAY))
        self.assertEqual(n, 7 + 2 + 1 + len(NIGHT))           # F bit0·1·2 다 켜져 덧붙은 바이트 없음
        self.assertEqual([ln for _, ln in blocks], [1, len(NIGHT)])

    def test_records_stop_at_zero(self):
        recs, end = nb.records(world_prg(), nb.NPC_BANK, 0x9000)
        self.assertEqual([f for _, f, _ in recs], [0x10, 0x1F])
        self.assertEqual(end, 0x9000 + 8 + len(DAY) + 7 + 2 + 1 + len(NIGHT) + 1)

    def test_all_blocks_slots_count_day_and_night_separately(self):
        rows = list(nb.all_blocks(world_prg()))
        self.assertEqual([(name, i, j, ln, slot) for name, _, i, j, _, ln, slot in rows],
                         [('00/00', 0, 1, len(DAY), 6), ('00/00', 1, 1, 1, 7), ('00/00', 1, 2, len(NIGHT), 6),
                          ('00/00 목록 1C:$A000', 0, 1, 2, 6)])


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()

    def test_command_sizes_and_descriptions(self):
        out = nb.decode(self.prg, nb.NPC_BANK, 0x9008, len(DAY))
        self.assertEqual([p - 0x9008 for p, *_ in out], [0, 3, 7])
        self.assertEqual(out[0][2], '메시지 0510')
        self.assertEqual(out[1][2], '$6280(플래그 05) |= 40')
        self.assertEqual(out[2][2], '이벤트 02 → 1D:$B123')
        self.assertTrue(all(bad is None for *_, bad in out))

    def test_unknown_and_overflow(self):
        out = nb.decode(self.prg, 0x1C, 0xA008, 2)
        self.assertEqual([bad for *_, bad in out], ['모름', '넘침'])

    def test_31_to_7f_run_as_00(self):
        put(self.prg, 0x05, 0xB000, [0x45])
        out = nb.decode(self.prg, 0x05, 0xB000, 1)
        self.assertEqual((len(out[0][1]), out[0][3]), (1, None))
        self.assertTrue(out[0][2].startswith('45 = 00'))

    def test_targets(self):
        cmds = [(0x9000, bytes([0x83, 0xFC]), '', None), (0x9002, bytes([0x84, 0x34, 0x92]), '', None),
                (0x9005, bytes([0x86, 0x00, 0x05]), '', None), (0x9008, bytes([0x86, 0x01, 0x05]), '', None)]
        self.assertEqual(nb.targets(self.prg, 0x05, 0x9000, cmds), [(0x9000, 0x8FFC), (0x9002, 0x9234), (0x9005, 0x900A)])

    def test_event_out_of_table(self):
        self.assertEqual(nb.describe(self.prg, 0x88, bytes([0x88, nb.EVENT_COUNT]), 0, ''), f'이벤트 {nb.EVENT_COUNT:02X}(표 밖)')

    def test_direction_and_target_text(self):
        self.assertEqual(nb.describe(self.prg, 0x23, bytes([0x23, 0x0D]), 0, ''), '방향 1, 그림 칸 7')
        self.assertEqual(nb.describe(self.prg, 0x24, bytes([0x24, 0x80, 0]), 0, ''), '목표 = 일행')


class PatternTests(unittest.TestCase):
    def test_patterns_split_by_length_table(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *nb.PATTERN_PTR, word(0x8050) + word(0x804E))
        put(prg, nb.PATTERN_PTR[0], 0x804E, [2, 1])
        put(prg, nb.PATTERN_PTR[0], 0x8050, [0x13, 0x82, 0x05])
        self.assertEqual(nb.patterns(prg), [(0x8050, [0x13, 0x82]), (0x8052, [0x05])])
        self.assertEqual(nb.pad_text(0x93), '위+오른쪽×3')
        self.assertEqual(nb.pad_text(0x05), '멈춤×5')


if __name__ == '__main__':
    unittest.main()
