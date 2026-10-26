"""전투 메시지의 부호·색인·트리·배치 경계를 원본 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5battletext import COUNT, INDEX, NODES_0, NODES_1, ROOT  # noqa: E402
from dq5battletextwrite import (  # noqa: E402
    DECODER, DECODER_END, FORMAT, INDEX_CALL, MASK_OPERAND, NODES_0_OPERAND, NODES_1_OPERAND, ROOT_OPERAND, STUB,
    compile_messages, copy_errors, decoded_messages, export, overrides, parse_at, patch, read_messages, tree, valid_message,
)
from dq5build import build, parse_at as patch_at  # noqa: E402
from dq5hangul import cpu_to_bytes, encode  # noqa: E402
from dq5map import lorom  # noqa: E402

STREAM = 0x078000


def source_fixture(messages):
    """원래 배치를 흉내 낸 1.5MB 롬: 24:9E47 디코더 머리·피연산자, 24:9C2E·9D18 트리, 07:8000 스트림, 24:AECD 색인."""
    data = bytearray(0x180000)
    start = lorom(DECODER)
    data[start:start + 4] = bytes.fromhex('08 8b 4b ab')
    data[lorom(DECODER_END) - 1] = 0x60
    codes, nodes, root = tree(messages)
    # 원래 표는 117 노드 자리이고 뿌리가 E8(노드 74)이므로, 뿌리가 74 에 오도록 번호를 돌린다.
    renumber = {i: (i - root + ROOT // 2) % 117 for i in range(len(nodes))}
    moved = [None] * 117
    for i, pair in enumerate(nodes):
        moved[renumber[i]] = tuple(v if v & 0x8000 else renumber[v] for v in pair)
    nodes = [pair or (0, 0) for pair in moved]
    for addr, opcode, value in ((NODES_0_OPERAND, 0xBD, NODES_0 & 0xFFFF), (NODES_1_OPERAND, 0xBD, NODES_1 & 0xFFFF),
                                (ROOT_OPERAND, 0xA2, ROOT), (MASK_OPERAND, 0x39, 0x9E8C)):
        off = lorom(addr)
        data[off - 1:off + 2] = bytes([opcode]) + value.to_bytes(2, 'little')
    off = lorom(INDEX_CALL - 1)
    data[off:off + 3] = bytes.fromhex('20 8d 8c')
    for i, (one, zero) in enumerate(nodes):
        data[lorom(NODES_1) + i * 2:lorom(NODES_1) + i * 2 + 2] = one.to_bytes(2, 'little')
        data[lorom(NODES_0) + i * 2:lorom(NODES_0) + i * 2 + 2] = zero.to_bytes(2, 'little')
    blob, starts = encode(codes, messages)
    data[lorom(STREAM):lorom(STREAM) + len(blob)] = blob
    index = b''.join(cpu_to_bytes(((STREAM + (starts[m] >> 3)) << 3) | starts[m] & 7) for m in range(0, COUNT, 16))
    data[lorom(INDEX):lorom(INDEX) + len(index)] = index
    return bytes(data)


def rebuild(data, manifest, mb=None):
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    return build(data, [(manifest['name'], manifest['rom_size'], writes)], mb or manifest['rom_size'])[0]


class BattleTextWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.messages = [[(i * 7) % 100, 0xFF, i % 5, (0xFE, 0xEF, 0xE7)[i % 3]] for i in range(COUNT)]
        cls.data = source_fixture(cls.messages)

    def test_read_and_unchanged_round_trip(self):
        self.assertEqual(read_messages(self.data), self.messages)
        self.assertEqual(len(export(self.data)['messages']), COUNT)
        manifest = patch(self.data, {'format': FORMAT, 'messages': []}, '3B:8000')
        self.assertEqual(manifest['rom_size'], 2)
        rebuilt = rebuild(self.data, manifest)
        self.assertEqual(decoded_messages(rebuilt), self.messages)
        self.assertEqual(copy_errors(self.data, rebuilt), [])
        broken = bytearray(rebuilt)
        base = int.from_bytes(broken[lorom(DECODER) + 1:lorom(DECODER) + 4], 'little')
        broken[lorom(base) + DECODER_END - DECODER - 1] = 0x60
        broken[lorom(base) + 6] ^= 0xFF
        self.assertEqual(copy_errors(self.data, bytes(broken)), [f'{DECODER + 6:06X}', '끝 RTL'])

    def test_partial_overrides_and_original_regions(self):
        doc = {'format': FORMAT, 'messages': [{'id': 15, 'codes': [0xF7, 0x28, 0xFE]},
                                              {'id': 431, 'codes': [0x10] * 127 + [0xE7]}]}
        messages = overrides(self.messages, doc)
        self.assertEqual(messages[14], self.messages[14])
        manifest = patch(self.data, doc, '3B:8000')
        rebuilt = rebuild(self.data, manifest)
        self.assertEqual(decoded_messages(rebuilt), messages)
        allowed = set(range(0x7FC0, 0x8000))
        for w in manifest['writes']:
            if 'orig' in w:
                start = patch_at(w['at'])[0]
                allowed.update(range(start, start + len(bytes.fromhex(w['hex']))))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.data, rebuilt))))
        # 보행 디코더가 읽는 마스크 24:9E8C 는 그대로다.
        self.assertTrue(all(lorom(DECODER_END) + k not in allowed for k in range(8)))

    def test_bank_hook_value_and_cross_bank_stream(self):
        for at, bank_or, size in (('3E:FC00', 0x20, 2), ('4F:FD00', 0x40, 3), ('60:FD00', 0x60, 4)):
            with self.subTest(at=at):
                manifest = compile_messages(self.data, self.messages, at)
                self.assertEqual(manifest['rom_size'], size)
                stub = next(w for w in manifest['writes'] if w['at'] == f'{STUB >> 16:02X}:{STUB & 0xFFFF:04X}')
                self.assertEqual(bytes.fromhex(stub['hex'])[6], bank_or)
                self.assertEqual(len({w['at'][:2] for w in manifest['writes'] if 'orig' not in w}), 2)
                self.assertEqual(decoded_messages(rebuild(self.data, manifest)), self.messages)

    def test_one_leaf(self):
        single = [[0xFE] for _ in range(COUNT)]
        self.assertEqual(tree(single), ({0xFE: '0'}, [(0x80FE, 0x80FE)], 0))
        manifest = compile_messages(self.data, single, '3B:8000')
        self.assertEqual(decoded_messages(rebuild(self.data, manifest)), single)

    def test_bad_message_codes_and_termination(self):
        for codes in (None, [], [0], [0xFE, 0], [0xFE, 0xEF], [True, 0xFE], [1.0, 0xFE], [-1, 0xFE],
                      [0x100, 0xFE], [0] * 128 + [0xFE]):
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                valid_message(codes)
        for codes in ([0xF7, 0xE7], [0] * 127 + [0xEF], [0xFF, 0xFD, 0xE2, 0xFE]):
            self.assertEqual(valid_message(codes), codes)

    def test_bad_overrides(self):
        cases = [None, [], {}, {'format': FORMAT}, {'format': 'dq5text/1', 'messages': []},
                 {'format': FORMAT, 'messages': None}, {'format': FORMAT, 'messages': [], 'x': 1},
                 {'format': FORMAT, 'messages': [None]}]
        for ident in (True, -1, COUNT, '05E'):
            cases.append({'format': FORMAT, 'messages': [{'id': ident, 'codes': [0xFE]}]})
        cases.append({'format': FORMAT, 'messages': [{'id': 0, 'codes': [0xFE]}] * 2})
        cases.append({'format': FORMAT, 'messages': [{'id': 0, 'codes': [0xFE], 'text': 'x'}]})
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                overrides(self.messages, doc)
        with self.assertRaises(ValueError):
            tree([])

    def test_invalid_addresses_and_overflow(self):
        for at in ('2F:8000', '7E:8000', '80:8000', '3B:7FFF', '3B:10000', '3B:8000x', None):
            with self.subTest(at=at), self.assertRaises(ValueError):
                parse_at(at)
        for at in ('3F:FC00', '3F:FF00', '5F:FF00', '7D:FFF0'):
            with self.subTest(at=at), self.assertRaises(ValueError):
                compile_messages(self.data, self.messages, at)
        with self.assertRaises(ValueError):
            compile_messages(self.data + bytes(0x80000), self.messages, '3B:8000')
        with self.assertRaises(ValueError):
            read_messages(bytes(0x180000))

    def test_malformed_tree_does_not_loop(self):
        manifest = compile_messages(self.data, self.messages, '3B:8000')
        rebuilt = bytearray(rebuild(self.data, manifest))
        base = int.from_bytes(rebuilt[lorom(DECODER) + 1:lorom(DECODER) + 4], 'little')
        for operand in (NODES_0_OPERAND, NODES_1_OPERAND):
            off = lorom(base + operand - DECODER)
            addr = (base & 0xFF0000) | int.from_bytes(rebuilt[off:off + 2], 'little')
            rebuilt[lorom(addr):lorom(addr) + 2] = b'\0\0'
        with self.assertRaisesRegex(ValueError, '순환'):
            decoded_messages(bytes(rebuilt))


if __name__ == '__main__':
    unittest.main()
