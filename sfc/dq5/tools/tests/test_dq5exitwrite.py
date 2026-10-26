"""출구 종류·끝 표시, 음수 가장자리 사각형, 고층 공유 목록과 목적지 검사."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5exitwrite import (
    FORMAT,
    decode_trigger,
    encode_exit,
    encode_trigger,
    group_scan,
    patch,
)
from dq5map import Rom

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


if __name__ == '__main__':
    unittest.main()
