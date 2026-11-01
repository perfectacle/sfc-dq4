"""출구 종류·끝 표시, 음수 가장자리 사각형, 고층 공유 목록과 목적지 검사."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5exit import DEST_TABLE
from dq5exitreloc import (
    EXIT_INDEXED, EXIT_INIT, EXIT_SHORT, HIGH_ORIGINAL, HIGH_SITES, INDEX_BANK, INDEX_OPERANDS, RECORD_BANK, RECORD_LOW,
)
from dq5exitwrite import (
    EXIT_END,
    FORMAT,
    HIGH_LISTS,
    check,
    decode_trigger,
    dump,
    encode_exit,
    encode_trigger,
    group_scan,
    layout as read_layout,
    patch,
)
from dq5map import GROUP_TABLE, Rom, lorom
from dq5trigger import INDEX, RECORD_SIZE, RECORDS

EDGE = bytes([0xFF, 6, 0, 12, 1, 0x80, 1, 4, 17, 4, 0xFA, 1])
FIELD = bytes([30, 60, 35, 61, 1, 0xC0, 0x80, 0, 0, 0, 1, 1])
HIGH = bytes([30, 18, 33, 19, 1, 0x40, 5, 1, 32, 46, 3, 1])


def layout():
    known = {(1, 0), (1, 3), (1, 4), (1, 6), (5, 1), (0x50, 0x50), (0x50, 0x51)}
    exits = {(1, 0): [(0x2AED84, bytes([0x49, 1])), (0x2AED86, bytes([0xC3, 0]))],
             (1, 3): [(0x2AED90, bytes([0x80]))],
             (1, 4): [(0x2AED91, bytes([0x20, 0, 1])), (0x2AED94, bytes([0xE0, 9, 9, 2, 1]))]}
    triggers = {(1, 6): [(0x2AD96E, EDGE), (0x2AD97A, FIELD)],
                (0x50, 0x50): [(0x019636, HIGH)], (0x50, 0x51): [(0x019636, HIGH)]}
    references = {0x2AD96E: ['01/06'], 0x2AD97A: ['01/06'], 0x019636: ['50/50', '50/51']}
    return known, exits, triggers, references


def run(*, exits=(), triggers=(), **extra):
    with mock('dq5exitwrite.layout', return_value=layout()):
        return patch(Rom(b''), {'format': FORMAT, 'exits': list(exits), 'triggers': list(triggers), **extra})['writes']


class ExitTests(unittest.TestCase):
    def test_exit_keeps_kind_and_last_bit(self):
        self.assertEqual(encode_exit(bytes([0xC3, 0]), {'destination_map': 4, 'exit': 1}), bytes([0xC4, 1]))
        self.assertEqual(encode_exit(bytes([0xE0, 9, 9, 2, 1]), {'x': 16, 'layer': 1}), bytes([0xE0, 16, 9, 1, 1]))
        self.assertEqual(encode_exit(bytes([0x80]), {'special': 0}), bytes([0x80]))
        for raw, change in ((bytes([0xC3, 0]), {'kind': 'position'}), (bytes([0xC3, 0]), {'group': 1}),
                            (bytes([0xC3, 0]), {'exit': True}), (bytes([0xC3, 0]), {'destination_map': 32}),
                            (bytes([0x80]), {'destination_map': 1}), (bytes([0xE0, 9, 9, 2, 1]), {'x': 255}),
                            (bytes([0xA0, 0, 1]), {'exit': 255})):
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_exit(raw, change)

    def test_exit_destination_must_exist(self):
        writes = run(exits=[{'map': '01/00', 'index': 1, 'destination_map': 4, 'exit': 1}])
        self.assertEqual([(w['at'], w['hex'], w['orig']) for w in writes], [('2A:ED86', 'c4 01', 'c3 00')])
        for row in ({'map': '01/00', 'index': 1, 'destination_map': 7},
                    {'map': '01/00', 'index': 1, 'exit': 1},
                    {'map': '01/04', 'index': 0, 'group': 2},
                    {'map': '01/00', 'index': 2, 'exit': 0},
                    {'map': '02/00', 'index': 0, 'exit': 0}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                run(exits=[row])


    def test_group_scan_stops_at_ff(self):
        data = bytearray(0x200000)
        start = 0x2A * 0x8000 + (0xED61 - 0x8000)
        data[start:start + 9] = bytes([0, 0xC1, 0, 0xFF, 1, 0x80, 0xFF, 0xFF, 0])
        self.assertEqual(group_scan(Rom(data)), {0: 0x2AED62, 1: 0x2AED66})


class TriggerTests(unittest.TestCase):
    def test_negative_edge_and_span_are_preserved(self):
        self.assertEqual(encode_trigger(EDGE, {}), EDGE)
        moved = encode_trigger(EDGE, {'rect': [0xFF, 6, 0, 9]})
        self.assertEqual(moved[:4], bytes([0xFF, 6, 0, 9]))
        self.assertEqual(decode_trigger(moved)['span_raw'], 0xFA)
        for change in ({'rect': [5, 6, 5, 9]}, {'rect': [5, 6, 9]}, {'rect': [5, 6, 9, 256]},
                       {'source_layer': -1}, {'direction': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_trigger(EDGE, change)

    def test_field_destination_skips_map_check(self):
        writes = run(triggers=[{'map': '01/06', 'index': 1, 'x': 3}])
        self.assertEqual(writes[0]['at'], '2A:D97A')
        with self.assertRaisesRegex(ValueError, '목적지'):
            run(triggers=[{'map': '01/06', 'index': 0, 'destination_map': 9}])

    def test_shared_high_list_needs_every_map(self):
        row = {'map': '50/50', 'index': 0, 'destination_group': 1, 'destination_map': 4}
        with self.assertRaisesRegex(ValueError, 'shared_maps'):
            run(triggers=[row])
        with self.assertRaisesRegex(ValueError, 'shared_maps'):
            run(triggers=[row | {'shared_maps': ['50/50']}])
        writes = run(triggers=[row | {'shared_maps': ['50/51', '50/50']}])
        self.assertEqual(writes[0]['at'], '01:9636')
        with self.assertRaisesRegex(ValueError, '두 번'):
            run(triggers=[row | {'shared_maps': ['50/50', '50/51']}, row | {'map': '50/51', 'shared_maps': ['50/50', '50/51']}])
        with self.assertRaisesRegex(ValueError, 'shared_maps'):
            run(triggers=[{'map': '01/06', 'index': 0, 'shared_maps': ['01/06']}])

    def test_noop_and_document_guards(self):
        self.assertEqual(run(triggers=[{'map': '01/06', 'index': 0, **decode_trigger(EDGE)}]), [])
        for kwargs in ({'other': 1}, {'triggers': [{'map': '01/06', 'index': 2}]},
                       {'triggers': [{'map': '01/06', 'index': True}]}, {'exits': [{'map': '1/0', 'index': 0}]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run(**kwargs)


HIGH_COUNTS = {0x50: 2, 0x51: 8, 0x52: 1, 0x53: 3, 0x54: 4}
LOW = [(0, bd) for bd in range(145)] + [(g, 0) for g in range(1, 54)]    # 영역 이동 색인 198칸과 같은 수


def fixed_rom():
    """원래 자리·크기의 출구 표(2A:ED61~F224)와 영역 이동 레코드·색인·고층 목록을 꽉 채운 합성 롬.
    출구는 00/00 이 위치 출구 182개·다른 그룹 출구 하나·특수 출구로 남는 자리를 채우고, 나머지 맵은 특수 출구 하나."""
    data = bytearray(0x180000)

    def put(addr, raw):
        data[lorom(addr):lorom(addr) + len(raw)] = raw

    put(EXIT_INIT, bytes.fromhex('a9 61 85 84 a9 ed 85 85'))
    for at in EXIT_SHORT:
        put(at, b'\xb2\x84')
    for at in EXIT_INDEXED:
        put(at, b'\xb1\x84')
    put(INDEX_BANK, b'\x2a')
    for at, plus in INDEX_OPERANDS:
        put(at, (0xEB0E + plus).to_bytes(2, 'little'))
    put(RECORD_LOW, b'\x12\xd8')
    put(RECORD_BANK, b'\x2a')
    for site, at in zip(HIGH_SITES, HIGH_ORIGINAL):
        put(site, bytes([0xAF, *at.to_bytes(3, 'little'), 0x8D, 0x3D, 0x18, 0xA2,
                         *(at + 1 & 0xFFFF).to_bytes(2, 'little'), 0x8E, 0x3A, 0x18, 0xA9, 0x01]))
    low = GROUP_TABLE & 0xFFFF
    counts = [145] + [1] * 53
    starts = [low - 3 * 198 + 3 * sum(counts[:g]) for g in range(54)]
    put(GROUP_TABLE, b''.join(v.to_bytes(2, 'little') for v in starts))
    starts = [0xCEB6 - 3 * 18 + 3 * sum(list(HIGH_COUNTS.values())[:i]) for i in range(5)]
    put(0x1FCEB6, b''.join(v.to_bytes(2, 'little') for v in starts))
    table = bytearray()
    for bc in range(54):
        table.append(bc)
        for bd in sorted(bd for g, bd in LOW if g == bc):
            if (bc, bd) == (0, 0):
                table += bytes([0x60 | 2, 9, 8, 1, 3]) * 182 + bytes([0x20 | 1, 0, 5])
            table.append(0x80)
        table.append(0xFF)
    assert DEST_TABLE + len(table) == EXIT_END
    put(DEST_TABLE, table)
    counts = [405 - 197] + [1] * 197
    put(INDEX, b''.join(bytes([bc, bd, n]) for (bc, bd), n in zip(LOW, counts)) + b'\xff')
    put(RECORDS, b''.join(bytes([2, 2, 3, 3, 1, 0xC0, 1, 0, 4, 5, 1, k % 4]) for k in range(405)))
    for at, count in HIGH_LISTS:
        put(at, bytes([count]) + EDGE * count)
    return data


class FixedLayoutTests(unittest.TestCase):
    """layout: 고정 슬롯 표를 원래 크기로 끝까지 읽고, 넘치거나 어긋나면 거부한다."""

    def setUp(self):
        self.data = fixed_rom()

    def put(self, addr, raw):
        self.data[lorom(addr):lorom(addr) + len(raw)] = raw

    def test_rows_are_contiguous_and_end_with_the_last_bit(self):
        known, exits, triggers, references = read_layout(Rom(self.data))
        self.assertEqual(len([k for k in known if k[0] < 0x50]), 198)
        self.assertEqual(len(exits), 198)
        self.assertEqual(exits[0, 0][0][0], DEST_TABLE + 1)
        self.assertEqual(len(exits[0, 0]), 184)
        for rows in exits.values():
            self.assertTrue(rows[-1][1][0] & 0x80)
            self.assertFalse(any(raw[0] & 0x80 for _, raw in rows[:-1]))
            for (a, raw), (b, _) in zip(rows, rows[1:]):
                self.assertEqual(a + len(raw), b)
        # 영역 이동은 색인 차례대로 레코드를 이어 받는다
        order = [at for key in LOW for at, _ in triggers[key]]
        self.assertEqual(order, [RECORDS + k * RECORD_SIZE for k in range(405)])
        # 51 그룹 첫 고층 맵의 목록은 다른 맵과 겹치지 않고, 50 그룹 두 맵은 한 목록을 함께 쓴다
        self.assertEqual(triggers[0x50, 0x50], triggers[0x50, 0x51])
        self.assertEqual(references[0x019636], ['50/50', '50/51'])
        self.assertEqual(len(triggers[0x51, 0x50]), 1)

    def test_dump_round_trip_and_check(self):
        rom = Rom(self.data)
        self.assertEqual(patch(rom, dump(rom))['writes'], [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            check(rom)
        self.assertIn('바뀐 레코드 0개', out.getvalue())

    def test_broken_tables_are_rejected(self):
        cases = {
            '그룹 순서': (DEST_TABLE, b'\x01'),
            '그룹 종료자를 만남': (EXIT_END - 2, b'\x00'),
            '중복': (INDEX + 3, bytes([0, 0])),
            '고층 목록': (HIGH_LISTS[1][0], b'\x02'),
            '겹침': (INDEX + 2, b'\xff'),
            '크기나 종료자': (INDEX + 198 * 3, b'\x00'),
        }
        for message, (addr, raw) in cases.items():
            with self.subTest(message=message):
                self.data = fixed_rom()
                self.put(addr, raw)
                with self.assertRaisesRegex(ValueError, message):
                    read_layout(Rom(self.data))

    def test_table_that_runs_past_the_fixed_area_is_rejected(self):
        # 마지막 그룹 종료자를 지우면 출구 표가 F224 를 넘어 읽힌다
        self.put(EXIT_END - 1, b'\x00')
        with self.assertRaisesRegex(ValueError, '고정 영역|종료자'):
            read_layout(Rom(self.data))


if __name__ == '__main__':
    unittest.main()
