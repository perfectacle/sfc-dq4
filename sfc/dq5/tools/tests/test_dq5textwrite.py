"""보행 메시지의 코드·색인·트리·배치 경계를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5build import build, parse_at as patch_at  # noqa: E402
from dq5hangul import (  # noqa: E402
    DECODER, DECODER_END, MASK_OPERAND, MESSAGES, NODES_0_OPERAND, NODES_1_OPERAND,
    ROOT_OPERAND, WALK_INDEX_CALL,
)
from dq5map import Rom, lorom  # noqa: E402
from dq5text import NODES_0, NODES_1, ROOT  # noqa: E402
from dq5text import FONT_GROUPS, FONT_TABLE_OPERANDS, GLYPHS  # noqa: E402
from dq5textwrite import (  # noqa: E402
    FORMAT, base_package, compile_messages, decoded_messages, overrides, parse_at, patch, tree, valid_message,
)


def source_fixture():
    data = bytearray(0x180000)
    start = lorom(DECODER)
    data[start:start + 4] = bytes.fromhex('08 8b 4b ab')
    data[lorom(DECODER_END) - 1] = 0x60
    for addr, opcode, value in ((NODES_0_OPERAND, 0xBD, NODES_0 & 0xFFFF),
                                (NODES_1_OPERAND, 0xBD, NODES_1 & 0xFFFF),
                                (ROOT_OPERAND, 0xA2, ROOT), (MASK_OPERAND, 0x39, 0x9E8C)):
        off = lorom(addr)
        data[off - 1:off + 2] = bytes([opcode]) + value.to_bytes(2, 'little')
    off = lorom(WALK_INDEX_CALL - 1)
    data[off:off + 3] = bytes.fromhex('20 8d 8c')
    return bytes(data)


def rebuild(data, manifest, mb=2):
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    return build(data, [(manifest['name'], manifest['rom_size'], writes)], mb)[0]


class TextWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = source_fixture()
        cls.messages = [[i % 987, 0x1001] for i in range(MESSAGES)]

    def test_partial_overrides_and_index_groups(self):
        changes = {'format': FORMAT, 'messages': [
            {'id': 15, 'codes': [0x1006, 986, 0x1010]},
            {'id': 16, 'codes': [0x110D, 0x1000, 0, 0x1018]},
            {'id': 3199, 'codes': [0x1001]},
        ]}
        messages = overrides(self.messages, changes)
        self.assertEqual(messages[14], self.messages[14])
        self.assertEqual(messages[17], self.messages[17])
        manifest = compile_messages(self.data, messages)
        rebuilt = rebuild(self.data, manifest)
        self.assertEqual(decoded_messages(rebuilt), messages)
        self.assertEqual(decoded_messages(rebuild(self.data, manifest, 4)), messages)

    def test_unmodified_original_regions(self):
        manifest = compile_messages(self.data, self.messages)
        rebuilt = rebuild(self.data, manifest)
        allowed = set(range(0x7FC0, 0x8000))
        for w in manifest['writes']:
            if 'orig' in w:
                start = patch_at(w['at'])[0]
                allowed.update(range(start, start + len(bytes.fromhex(w['hex']))))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.data, rebuilt))))
        self.assertEqual(overrides(self.messages, {'format': FORMAT, 'messages': []}), self.messages)

    def test_one_leaf_and_cross_bank_stream(self):
        single = [[0x1001] for _ in range(MESSAGES)]
        codes, nodes, root = tree(single)
        self.assertEqual((codes, nodes, root), ({0x1001: '0'}, [(0x9001, 0x9001)], 0))
        manifest = compile_messages(self.data, single, '3F:FE00')
        self.assertEqual(decoded_messages(rebuild(self.data, manifest)), single)
        pair = [[0, 0x1001] for _ in range(MESSAGES)]
        manifest = compile_messages(self.data, pair, '38:FF00')
        self.assertIn('39:8000', [w['at'] for w in manifest['writes']])
        self.assertEqual(decoded_messages(rebuild(self.data, manifest)), pair)

    def test_bad_message_codes_and_termination(self):
        for codes in (None, [], [0], [0x1001, 0], [0x1001, 0x1010], [True, 0x1001],
                      [1.0, 0x1001], [-1, 0x1001], [987, 0x1001], [0xFFF, 0x1001],
                      [0x101E, 0x1001], [0x1119, 0x1001], [0x8001, 0x1001]):
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                valid_message(codes)
        for codes in ([0, 986, 0x1001], [0x1009, 0x1010], [0x1118, 0x1018]):
            self.assertEqual(valid_message(codes), codes)

    def test_bad_overrides(self):
        cases = [None, [], {}, {'format': FORMAT}, {'format': FORMAT, 'messages': None},
                 {'format': FORMAT, 'messages': [], 'text': ''}, {'format': FORMAT, 'messages': [None]}]
        for ident in (True, -1, 3200, '129'):
            cases.append({'format': FORMAT, 'messages': [{'id': ident, 'codes': [0x1001]}]})
        cases.append({'format': FORMAT, 'messages': [{'id': 0, 'codes': [0x1001]}] * 2})
        cases.append({'format': FORMAT, 'messages': [{'id': 0, 'codes': [0x1001], 'text': 'x'}]})
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                overrides(self.messages, doc)
        with self.assertRaises(ValueError):
            tree([])
        with self.assertRaises(ValueError):
            tree([[] for _ in range(MESSAGES)])

    def test_invalid_addresses_and_overflow(self):
        for at in ('2F:8000', '40:8000', '5F:8000', '7E:8000', '38:7FFF', '38:10000', '38:8000x', '038:8000', None):
            with self.subTest(at=at), self.assertRaises(ValueError):
                parse_at(at)
        one = [[0x1001] for _ in range(MESSAGES)]
        for at in ('38:FFFF', '3F:FE20', '7D:FE20'):
            with self.subTest(at=at), self.assertRaises(ValueError):
                compile_messages(self.data, one, at)
        with self.assertRaises(ValueError):
            compile_messages(self.data + bytes(0x80000), one)
        with self.assertRaises(ValueError):
            compile_messages(b'', one)

    def test_high_window_uses_or_60(self):
        manifest = compile_messages(self.data, self.messages, '65:8000')
        self.assertEqual(manifest['rom_size'], 4)
        stub = next(w for w in manifest['writes'] if w['note'] == '보행 색인 뱅크 훅')
        self.assertEqual(bytes.fromhex(stub['hex'])[6], 0x60)
        self.assertEqual(decoded_messages(rebuild(self.data, manifest, 4)), self.messages)
        pair = [[0, 0x1001] for _ in range(MESSAGES)]
        crossing = compile_messages(self.data, pair, '6F:FF00')
        self.assertIn('70:8000', [w['at'] for w in crossing['writes']])
        self.assertEqual(decoded_messages(rebuild(self.data, crossing, 4)), pair)

    def test_base_package_keeps_extra_glyphs_and_font_table(self):
        data = bytearray(self.data)
        groups = bytes((0xDB, 0x03, 0, 0, 0)) + bytes((0x10, 0x00, 0, 0, 0))   # 원래 3DB자 + 늘린 16자
        for at, k in FONT_TABLE_OPERANDS:
            data[lorom(at):lorom(at) + 3] = (FONT_GROUPS + k).to_bytes(3, 'little')
        hangul = [[GLYPHS + i % 16, 0x1001] for i in range(MESSAGES)]
        manifest = compile_messages(bytes(data), hangul, '65:8000', font=groups, glyphs=GLYPHS + 16)
        base = rebuild(bytes(data), manifest, 4)
        messages, font, glyphs, (start, end) = base_package(base)
        self.assertEqual((messages, font, glyphs), (hangul, groups, GLYPHS + 16))
        self.assertEqual(start, lorom(0x658000))
        self.assertEqual(end, start + sum(len(bytes.fromhex(w['hex'])) for w in manifest['writes'] if 'orig' not in w))
        with self.assertRaises(ValueError):
            patch(bytes(data), {'format': FORMAT, 'messages': [{'id': 0, 'codes': [GLYPHS + 16, 0x1001]}]},
                  '66:8000', base=base)
        edited = patch(bytes(data), {'format': FORMAT, 'messages': [{'id': 0, 'codes': [GLYPHS + 15, 0x1001]}]},
                       '30:8000', base=base)
        again = rebuild(bytes(data), edited, 2)
        self.assertEqual(decoded_messages(again)[0], [GLYPHS + 15, 0x1001])
        self.assertEqual(decoded_messages(again)[1:], hangul[1:])
        self.assertEqual(base_package(again)[1], groups)
        with self.assertRaises(ValueError):
            base_package(bytes(data))
        bad = bytearray(base)
        bad[lorom(0x249E07) + 6] = 0x40
        with self.assertRaises(ValueError):
            base_package(bytes(bad))

    def test_malformed_tree_does_not_loop(self):
        manifest = compile_messages(self.data, [[0, 0x1001] for _ in range(MESSAGES)])
        rebuilt = bytearray(rebuild(self.data, manifest))
        rom = Rom(rebuilt)
        base = rom.u24(DECODER + 1)
        for operand in (NODES_0_OPERAND, NODES_1_OPERAND):
            addr = (base & 0xFF0000) | rom.u16(base + operand - DECODER)
            off = lorom(addr)
            rebuilt[off:off + 2] = b'\0\0'
        with self.assertRaisesRegex(ValueError, '순환'):
            decoded_messages(rebuilt)


if __name__ == '__main__':
    unittest.main()
