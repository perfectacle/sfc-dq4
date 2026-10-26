"""인물 스크립트의 분기 기준과 슬롯 경계를 검사한다."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5map import Rom, lorom  # noqa: E402
from dq5npcwrite import FORMAT, address, encode, patch, validate_flow  # noqa: E402


def document(commands):
    return {'format': FORMAT, 'commands': commands}


class NpcWriteTests(unittest.TestCase):
    def test_branch_bases(self):
        code = encode(document([
            {'label': 'start', 'op': '1A'},
            {'op': '03', 'target': 'end'},
            {'op': '06', 'args': [15, 1], 'target': 'start'},
            {'op': '07', 'args': [1, 2, 3, 4], 'target': 'start'},
            {'label': 'end', 'op': '16'},
        ]))
        self.assertEqual(code, bytes.fromhex('1a 03 0b 06 0f 01 fd 07 01 02 03 04 f9 16'))

    def test_walk_and_absolute(self):
        self.assertEqual(encode(document([{'op': '85', 'args': [13]}, {'op': '04', 'args': [0, 144]}])),
                         bytes.fromhex('85 0d 04 00 90'))

    def test_relative_limits(self):
        prefix = [{'op': '03', 'target': 'end'}]
        code = encode(document(prefix + [{'op': '1A'}] * 126 + [{'label': 'end', 'op': '16'}]))
        self.assertEqual(code[:2], bytes.fromhex('03 7f'))
        with self.assertRaises(ValueError):
            encode(document(prefix + [{'op': '1A'}] * 127 + [{'label': 'end', 'op': '16'}]))
        code = encode(document([{'label': 'start', 'op': '1A'}] + [{'op': '1A'}] * 126 + [{'op': '03', 'target': 'start'}]))
        self.assertEqual(code[-2:], bytes.fromhex('03 80'))

    def test_invalid_commands(self):
        cases = [[], [{'op': '+1'}], [{'op': ' 1'}], [{'op': '57'}], [{'op': '85'}], [{'op': '03', 'args': [0]}],
                 [{'op': '1D', 'args': [256]}], [{'op': '1D', 'args': [True]}],
                 [{'op': '03', 'target': 'missing'}], [{'op': '16', 'target': 'x'}],
                 [{'label': 'x', 'op': '16'}, {'label': 'x', 'op': '16'}],
                 [{'op': '1A'}] * 256]
        for commands in cases:
            with self.subTest(commands=commands[:3]), self.assertRaises(ValueError):
                encode(document(commands))

    def test_flow(self):
        validate_flow(bytes.fromhex('2b 05 0d 00'), 0x05A851)
        validate_flow(bytes.fromhex('03 ff'), 0x05A851)
        with self.assertRaises(ValueError):
            validate_flow(bytes.fromhex('2b 05 0d'), 0x05A851)
        with self.assertRaises(ValueError):
            validate_flow(bytes.fromhex('04 52 a8'), 0x05A851)

    def test_slot_patch(self):
        at = 0x058000
        raw = bytearray(0x30000)
        raw[lorom(at):lorom(at) + 5] = bytes.fromhex('04 2b 01 02 16')
        rom = Rom(raw)
        doc = dict(document([{'op': '1A'}]), address='05:8000', length=4)
        with mock_patch('dq5npcwrite.slots', return_value={at: [{'time': 'day'}, {'time': 'night'}]}):
            result, refs = patch(rom, doc)
            self.assertEqual(result['writes'][0]['hex'], '04 1a 00 00 00')
            self.assertEqual(result['writes'][0]['orig'], '04 2b 01 02 16')
            self.assertEqual(len(refs), 2)
            with self.assertRaises(ValueError):
                patch(rom, dict(doc, length=5))
            with self.assertRaises(ValueError):
                patch(rom, dict(doc, address='05:8001'))
            with self.assertRaises(ValueError):
                patch(rom, dict(doc, commands=[{'op': '1A'}] * 5))
            with self.assertRaises(ValueError):
                patch(rom, dict(doc, commands=[{'op': '1A'}] * 4))

    def test_nonobject_patch(self):
        for doc in (None, [], 1):
            with self.assertRaises(ValueError):
                patch(Rom(b''), doc)

    def test_bad_addresses(self):
        for value in ('05:0000', '7E:8000', '05:10000', 'bad', 0x058000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                address(value)


if __name__ == '__main__':
    unittest.main()
