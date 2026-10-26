"""이벤트 인코더의 주소·표 교체 경계. 원본 롬 없이 실행한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5eventwrite import FORMAT, encode, parse, patch  # noqa: E402
from dq5event import EVENTS, NUMBERED  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402


def document(commands, **extra):
    return {'format': FORMAT, 'commands': commands, **extra}


class EventWriteTests(unittest.TestCase):
    def test_forward_backward_labels(self):
        doc = document([
            {'op': 'C3', 'target': 'end', 'label': 'start'},
            {'op': 'C7', 'args': [12]},
            {'op': 'C8', 'args': [13]},
            {'op': 'C9'},
            {'op': 'C3', 'target': 'start', 'label': 'end'},
        ])
        self.assertEqual(encode(doc, 0x60A000), bytes.fromhex('c3 09 a0 60 c7 0c c8 0d c9 c3 00 a0 60'))

    def test_reject_invalid_commands(self):
        bad = [[], [{'op': '50'}], [{'op': '10', 'args': [1]}, {'op': 'FF'}],
               [{'op': '10', 'args': [True, 0]}, {'op': 'FF'}],
               [{'op': '10', 'args': [256, 0]}, {'op': 'FF'}],
               [{'op': 'C2'}], [{'op': 'C3', 'target': 'missing'}],
               [{'op': 'C3', 'target': -1}],
               [{'op': 'C2', 'label': 'x'}, {'op': 'FF', 'label': 'x'}]]
        for commands in bad:
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                encode(document(commands), 0x608000)

    def test_bank_end_and_truncation(self):
        self.assertEqual(encode(document([{'op': 'FF'}]), 0x60FFFF), b'\xff')
        with self.assertRaises(ValueError):
            encode(document([{'op': 'C2'}, {'op': 'FF'}]), 0x60FFFF)
        with self.assertRaises(ValueError):
            parse(Rom(bytes(BANK - 1) + b'\x10'), 0x00FFFF)
        with self.assertRaises(ValueError):
            parse(Rom(b'\x50'), 0x008000)
        with self.assertRaises(ValueError):
            parse(Rom(b'\xc2'), 0x008000)

    def test_patch_tables_and_bank_alignment(self):
        data = bytes(0x180000)
        first = document([{'op': 'C3', 'target': 'again', 'label': 'again'}],
                         binding={'kind': 'event', 'index': 8, 'x': 26, 'y': 15})
        second = document([{'op': 'FF'}], binding={'kind': 'number', 'index': 0x41})
        result = patch(data, [first, second], 0x60FFFD)
        self.assertEqual(result['rom_size'], 4)
        writes = result['writes']
        self.assertEqual(writes[0]['at'], '61:8000')
        self.assertEqual(bytes.fromhex(writes[0]['hex']), bytes.fromhex('c3 00 80 61'))
        self.assertEqual(writes[1]['at'], '23:E2EA')
        self.assertEqual(bytes.fromhex(writes[1]['hex']), bytes.fromhex('1a 0f 00 80 61'))
        self.assertEqual(bytes.fromhex(writes[1]['orig']), data[lorom(EVENTS + 40):lorom(EVENTS + 40) + 5])
        self.assertEqual(writes[2]['at'], '61:8004')
        self.assertEqual(writes[3]['at'], '23:E3E8')
        self.assertEqual(bytes.fromhex(writes[3]['orig']), data[lorom(NUMBERED + 0x41 * 3):lorom(NUMBERED + 0x41 * 3) + 3])
        self.assertEqual(len(writes), 4)

    def test_patch_rejects_original_area_duplicates_and_overflow(self):
        data = bytes(0x180000)
        doc = document([{'op': 'FF'}], binding={'kind': 'number', 'index': 0})
        for docs, at in [([None], 0x608000), ([[]], 0x608000), ([doc], 0x158000), ([doc, doc], 0x608000), ([doc, doc], 0xFFFFFF)]:
            with self.subTest(at=at), self.assertRaises(ValueError):
                patch(data, docs, at)
        long = document([{'op': 'C2'}, {'op': 'FF'}], binding={'kind': 'number', 'index': 0})
        with self.assertRaises(ValueError):
            patch(data, [long], 0xFFFFFF)


BANK = 0x8000

if __name__ == '__main__':
    unittest.main()
