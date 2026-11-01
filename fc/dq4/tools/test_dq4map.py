"""맵 블록 배치 해제(채우기·사각형·점·길·갈림길·2×2·위 3비트 패스·뱅크 넘김)와 맵·출구·인물 표 읽기를
합성 비트열로 검사한다."""
import unittest

import dq4map as m

PRG_SIZE = 32 * 0x4000


class Writer:
    """MSB 부터 비트를 쌓는다. 테스트 쪽 독립 구현."""

    def __init__(self):
        self.bits = ''

    def __call__(self, v, n):
        self.bits += f'{v:0{n}b}' if n else ''
        return self

    def bytes(self):
        b = self.bits + '0' * (-len(self.bits) % 8)
        return bytes(int(b[i:i + 8], 2) for i in range(0, len(b), 8))


def end(w, tb):
    """블록 값 명령(00 값 00) 뒤 1 = 이번 패스 끝."""
    return w(0, 2)(0, tb)(0, 2)(1, 1)


def decode(w, width, height, tb, quad=False):
    prg = bytearray(PRG_SIZE)
    data = w.bytes()
    prg[0x09 * 0x4000 + 0x100:0x09 * 0x4000 + 0x100 + len(data)] = data
    pb = (width * height - 1).bit_length()
    return m.decode(prg, 0x09, 0x8100, width, height, pb, tb, quad)


def grid(rows):
    return bytes(v for r in rows for v in r)


class DecodeTests(unittest.TestCase):
    def test_fill_rectangle_and_point(self):
        w = Writer()(1, 2)                       # 바탕 1
        w(0, 2)(2, 2)                            # 값 2
        w(1, 2)(5, 4)(10, 4)                     # 사각형 (1,1)-(2,2)
        w(3, 2)(0, 4)                            # 점 0
        end(w, 2)(0, 2)                          # 위 3비트 패스 없음
        self.assertEqual(decode(w, 4, 3, 2), grid([[2, 1, 1, 1], [1, 2, 2, 1], [1, 2, 2, 1]]))
        self.assertEqual(m.decode.end[:2], (0x09, 0x8100 + len(w.bits) // 8))

    def test_path_turns_right(self):
        w = Writer()(0, 2)(0, 2)(1, 2)
        w(2, 2)(0, 4)(1, 2)                      # 길: 0 에서 오른쪽
        w(0, 1)(0, 1)(1, 1)(0, 2)(0, 1)          # 두 칸, 오른쪽으로 돌아 한 칸, 한 칸
        w(1, 1)(3, 2)(1, 1)                      # 쌓인 것 없으면 끝
        end(w, 2)(0, 2)
        out = decode(w, 4, 4, 2)
        self.assertEqual([i for i, v in enumerate(out) if v], [0, 1, 2, 6, 10])

    def test_branch_returns_to_pushed_point(self):
        w = Writer()(0, 2)(0, 2)(1, 2)
        w(2, 2)(4, 4)(1, 2)(0, 1)                # (1,0) 에서 오른쪽, 한 칸 → 5
        w(1, 1)(2, 2)(0, 1)                      # 갈림길(왼쪽 아님 = 시계 방향): 5 를 쌓고 아래로 → 9
        w(1, 1)(3, 2)(1, 1)                      # 되돌아가 5, 오른쪽
        w(0, 1)                                  # → 6
        w(1, 1)(3, 2)(1, 1)
        end(w, 2)(0, 2)
        out = decode(w, 4, 4, 2)
        self.assertEqual(sorted(i for i, v in enumerate(out) if v), [4, 5, 6, 9])

    def test_new_path_jumps(self):
        w = Writer()(0, 2)(0, 2)(1, 2)
        w(2, 2)(0, 4)(1, 2)
        w(1, 1)(3, 2)(0, 1)(15, 4)(3, 2)         # 새 길: 15 에서 왼쪽
        w(0, 1)
        w(1, 1)(3, 2)(1, 1)
        end(w, 2)(0, 2)
        out = decode(w, 4, 4, 2)
        self.assertEqual(sorted(i for i, v in enumerate(out) if v), [0, 14, 15])

    def test_quad_rectangle_tiles_2x2(self):
        w = Writer()(0, 2)
        w(0, 2)(1, 2)(0, 2)(0, 1)(2, 2)(3, 2)(0, 2)   # 2×2 값 1 2 / 3 0
        w(1, 2)(0, 4)(10, 4)                          # (0,0)-(2,2) → 2×2 블록 넷
        end(w, 2)(0, 2)
        self.assertEqual(decode(w, 4, 4, 2), grid([[1, 2, 1, 2], [3, 0, 3, 0]] * 2))

    def test_attribute_pass_keeps_low_bits(self):
        w = Writer()(0x1F, 5)
        end(w, 5)
        w(1, 2)                                   # 위 3비트 패스, 1 비트 값
        w(0, 2)(1, 1)(3, 2)(1, 2)                 # 점 1 에 위 비트 1
        end(w, 1)
        out = decode(w, 2, 2, 5)
        self.assertEqual(out, bytes((0x1F, 0x3F, 0x1F, 0x1F)))

    def test_out_of_range_writes_are_dropped(self):
        w = Writer()(0, 2)(0, 2)(1, 2)(2, 2)(0, 2)(0, 2)   # 길: 0 에서 위로
        w(0, 1)(1, 1)(3, 2)(1, 1)
        end(w, 2)(0, 2)
        self.assertEqual(decode(w, 2, 2, 2), bytes((1, 0, 0, 0)))


class BitsTests(unittest.TestCase):
    def test_bank_end_continues(self):
        prg = bytearray(PRG_SIZE)
        prg[0x09 * 0x4000 + 0x3FD7] = 0x80
        prg[0x0A * 0x4000] = 0x80
        b = m.Bits(prg, 0x09, 0xBFD7)
        self.assertEqual(b.read(9), 0x101)
        self.assertEqual((b.bank, b.ptr, b.pos), (0x0A, 0x8000, 1))

    def test_bank_0b_starts_after_its_header(self):
        prg = bytearray(PRG_SIZE)
        prg[0x0B * 0x4000 + 0x1A] = 0xFF
        b = m.Bits(prg, 0x0A, 0xBFD7)
        b.read(8)
        self.assertEqual((b.bank, b.ptr), (0x0B, 0x801A))
        self.assertEqual(b.read(8), 0xFF)


def put(prg, bank, addr, data):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


class TableTests(unittest.TestCase):
    def test_maps_count_by_next_group_and_ff_for_last(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *m.GROUPS, [0x00, 0xA0, 0x06, 0xA0, 0xFF, 0xFF])
        put(prg, 0x17, 0xA000, [0x10, 0x00, 0x90, 0x11, 0x34, 0x92, 0x12, 0x00, 0x88, 0xFF])
        self.assertEqual(m.maps(prg), [(0, 0, 0x10, 0x09, 0x9000), (0, 1, 0x11, 0x09, 0x9234),
                                       (1, 0, 0x12, 0x09, 0x8800)])

    def test_data_bank_boundaries(self):
        self.assertEqual([m.data_bank(*gk) for gk in ((0x2C, 7), (0x2C, 8), (0x45, 3), (0x45, 4))],
                         [0x09, 0x0A, 0x0A, 0x0B])

    def test_header_bits(self):
        prg = bytearray(PRG_SIZE)
        put(prg, 0x09, 0x9000, [0x20, 0x10, 0xC5])
        self.assertEqual(m.header(prg, 0x09, 0x9000), (0x20, 0x10, 9, 5, 0x05))

    def test_exits_both_ways_with_step_and_special_group(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *m.LINKS_PTR, [0x00, 0x90])
        put(prg, 0x1B, 0x9000, [0x01, 0x00, 5, 6, 0x00, 0x40, 0x03, 7, 8, 0x05,
                                0x02, 0x00, 1, 1, 0x00, 0x03, 0x00, 2, 2, 0xC0, 0xFF])
        self.assertEqual(m.exits(prg, 0x01, 0x00), [(5, 6, 0x40, 0x03, 8, 8, 0x01)])
        self.assertEqual(m.exits(prg, 0x01, 0x00, flags=0x20), [(5, 6, 0x40, 0x04, 8, 8, 0x01)])
        self.assertEqual(m.exits(prg, 0x40, 0x03), [(7, 8, 0x01, 0x00, 5, 6, 0x00)])
        self.assertEqual(m.exits(prg, 0x03, 0x00), [(2, 2, 0x02, 0x00, 1, 1, 0x00)])

    def test_special_group(self):
        self.assertEqual(m.special_group(0x45, 5, 0x02), 7)
        self.assertEqual(m.special_group(0x45, 4, 0x10), 6)
        self.assertEqual(m.special_group(0x45, 4, 0x00), 4)
        self.assertEqual(m.special_group(0x32, 1, 0xFF), 1)


class NpcTests(unittest.TestCase):
    def setUp(self):
        self.prg = prg = bytearray(PRG_SIZE)
        put(prg, m.NPC_BANK, 0x8000 + 2 * 3, [0x00, 0x90])
        day = [0x10, 1, 2, 0x02, 4, 0x85, 0x06, 1, 0x55]            # 머리 7 + 낮 블록(길이 1)
        # 낮·밤 둘 다: bit0 이 켜져 방향 바이트가 없고, bit1·bit2 가 꺼져 1 + 2(밤 X·Y) 바이트가 붙는다
        day_night = [0x19, 1, 2, 0x01, 4, 0x07, 0x08, 0x99, 0x0A, 0x0B, 1, 0xAA, 1, 0xBB]
        put(prg, m.NPC_BANK, 0x9000, [0x00] + day + day_night + [0x00])   # 순번 0 은 빈 목록
        self.day, self.day_night = day, day_night
        # 진행 플래그 목록: 그룹 3 순번 1, 플래그 5 bit1 이면 1C:A000
        put(prg, *m.EVENT_LISTS, [0x00, 0x98])
        put(prg, m.EVENT_LISTS[0], 0x9800, [0x03, 0x01, 0x02, 0x05, 0x00, 0xA0, 0xFF])
        put(prg, m.EVENT_LISTS[0], 0xA000, day + [0x00])

    def test_records_sizes_follow_flags(self):
        recs = m.npc_records(self.prg, 3, 1)
        self.assertEqual([len(r) for r in recs], [9, 14])
        self.assertEqual(recs[1], bytes(self.day_night))

    def test_end_address_after_terminator(self):
        recs, a = m.records_at(self.prg, m.NPC_BANK, 0x9000)
        self.assertEqual((recs, a), ([], 0x9001))

    def test_day_and_night_positions(self):
        self.assertEqual([(n['x'], n['y'], n['dir']) for n in m.npcs(self.prg, 3, 1)], [(5, 6, 2), (7, 8, 1)])
        self.assertEqual([(n['x'], n['y'], n['dir']) for n in m.npcs(self.prg, 3, 1, night=True)], [(0x0A, 0x0B, 1)])

    def test_progress_flag_picks_event_list(self):
        flags = bytearray(0x100)
        self.assertEqual(len(m.place_records(self.prg, 3, 1, lambda i: flags[i])), 2)
        flags[5] = 0x02
        self.assertEqual(m.pick_list(self.prg, 3, 1, lambda i: flags[i]), 0xA000)
        self.assertEqual(len(m.place_records(self.prg, 3, 1, lambda i: flags[i])), 1)

    def test_withdrawn(self):
        flags = bytearray(0x100)
        f = flags.__getitem__
        self.assertFalse(m.withdrawn(0x04, 0x01, f))
        flags[0x07] = 0x10
        self.assertTrue(m.withdrawn(0x04, 0x01, f))
        self.assertTrue(m.withdrawn(0x02, 0x00, f))
        self.assertFalse(m.withdrawn(0x02, 0x03, f))
        self.assertFalse(m.withdrawn(0x15, 0x02, f))
        flags[0x1A] = 0x02
        self.assertTrue(m.withdrawn(0x15, 0x02, f))
        flags[0x2A] = 0x80
        self.assertFalse(m.withdrawn(0x04, 0x01, f))


if __name__ == '__main__':
    unittest.main()
