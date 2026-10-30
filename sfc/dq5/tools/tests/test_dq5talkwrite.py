"""대화 스크립트 쓰기의 부호화·검증·배치를 롬 없이 검사한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5build import build  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5talk import ORIGINAL_SITES, SITES, extra_config  # noqa: E402
from dq5talkwrite import (COUNT, FORMAT, REGION, TABLE, bank06, check, dump, edits, encode_script,  # noqa: E402
                          patch, read_op, skip_length)

PAPAS = [{'op': 'if', 'cond': {'code': '1B', 'index': 1, 'mask': 1},
          'then': [{'op': 'msg', 'id': '74F'}, {'op': 'flag-on', 'index': 2, 'mask': 128}],
          'else': {'op': 'msg', 'id': '742'}}]
PAPAS_CODE = bytes.fromhex('07 1b 01 01 06 41 3a 18 02 80 3e 0b 41 2d 3f')


def synthetic(fill_bank_end=False):
    """스크립트 574개를 06:8129 부터 32개 묶음으로 둔 1.5MB 가짜 롬."""
    data = bytearray(0x180000)
    a = REGION[0]
    for n in range(COUNT):
        if n % 32 == 0:
            data[lorom(TABLE + n // 32 * 2):lorom(TABLE + n // 32 * 2) + 2] = (a & 0xFFFF).to_bytes(2, 'little')
        code = PAPAS_CODE if n % 3 == 0 else bytes([0x40 | n >> 8, n & 0xFF, 0x3F])
        data[lorom(a):lorom(a) + len(code)] = code
        a += len(code)
    for name, at in SITES.items():
        raw = bytes.fromhex(ORIGINAL_SITES[name])
        data[lorom(at):lorom(at) + len(raw)] = raw
    if fill_bank_end:
        data[lorom(0x06FFF0)] = 0xEA
    return Rom(data)


def doc(*scripts):
    return {'format': FORMAT, 'scripts': [{'talk': t, 'body': b} for t, b in scripts]}


def apply(rom, writes):
    built, _ = build(rom.d, [('t', 0, writes)], 0)
    return Rom(built)


class EncodeTests(unittest.TestCase):
    def test_papas_bytes(self):
        self.assertEqual(encode_script(PAPAS, 'x'), PAPAS_CODE)

    def test_message_forms(self):
        self.assertEqual(encode_script([{'op': 'msg', 'id': '129'}], 'x'), bytes.fromhex('61 29 3f'))
        self.assertEqual(encode_script([{'op': 'msg', 'id': '615'}], 'x'), bytes.fromhex('40 00 3f'))
        self.assertEqual(encode_script([{'op': 'msg', 'id': 'C7F'}], 'x'), bytes.fromhex('46 6a 3f'))
        # dq5textwrite 가 3200 이상을 덧붙인 롬을 위해 1FFF 까지 받는다(1000 이상은 4자리).
        self.assertEqual(encode_script([{'op': 'msg', 'id': 'C80'}], 'x'), bytes.fromhex('46 6b 3f'))
        self.assertEqual(encode_script([{'op': 'msg', 'id': '1FFF'}], 'x'), bytes.fromhex('59 ea 3f'))

    def test_message_decode_round_trip(self):
        """읽는 쪽도 1FFF 까지: 59 EA 는 bit13 이 꺼져 v + 615 갈래로 1FFF."""
        data = bytearray(0x180000)
        for ident, code in (('615', '40 00'), ('C7F', '46 6a'), ('C80', '46 6b'), ('1FFF', '59 ea'), ('129', '61 29')):
            data[lorom(0x068000):lorom(0x068000) + 2] = bytes.fromhex(code)
            self.assertEqual(read_op(Rom(data), 0x068000), ({'op': 'msg', 'id': ident}, 0x068002))
            self.assertEqual(encode_script([read_op(Rom(data), 0x068000)[0]], 'x'), bytes.fromhex(code + ' 3f'))
        data[lorom(0x068000):lorom(0x068000) + 2] = bytes.fromhex('59 eb')     # 2000: 메시지 번호 끝을 넘음
        with self.assertRaises(ValueError):
            read_op(Rom(data), 0x068000)

    def test_other_ops(self):
        body = [{'op': 'flag-set', 'index': 0x60, 'value': 0x5A}, {'op': 'flag-off', 'index': 1, 'mask': 2},
                {'op': 'call', 'target': 'B3A0'},
                {'op': 'if', 'cond': {'code': '05', 'not': True}, 'then': {'op': 'call', 'target': 'B3A0'}}]
        self.assertEqual(encode_script(body, 'x'), bytes.fromhex('19 60 5a 17 01 02 00 a0 b3 07 85 00 a0 b3 3f'))

    def test_invalid(self):
        msg = {'op': 'msg', 'id': '129'}
        cases = [
            [], [{'op': 'msg', 'id': '2000'}], [{'op': 'msg', 'id': '0C80'}], [{'op': 'msg', 'id': 297}],
            [{'op': 'msg', 'id': '129', 'x': 1}],
            [{'op': 'jump'}], [{'op': 'flag-on', 'index': 256, 'mask': 1}], [{'op': 'flag-on', 'index': True, 'mask': 1}],
            [{'op': 'call', 'target': '7FFF'}],
            [{'op': 'if', 'cond': {'code': '16', 'index': 1}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '1C', 'index': 1, 'mask': 1}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '1B', 'index': 1}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '05', 'not': 1}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '05'}, 'then': []}],
            [{'op': 'if', 'cond': {'code': '05'}, 'then': {'op': 'if', 'cond': {'code': '05'}, 'then': msg}}],
            # 인자 3F 를 06:AFA9 가 끝으로 읽는다.
            [{'op': 'if', 'cond': {'code': '03', 'member': 0x3F}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '05'}, 'then': msg, 'else': {'op': 'if', 'cond': {'code': '05'}, 'then': msg}}],
            [{'op': 'msg', 'id': 'a0f'}], [{'op': 'call', 'target': 'b3a0'}],
            [{'op': 'if', 'cond': {'code': '1b', 'index': 1, 'mask': 1}, 'then': msg}],
            [{'op': 'if', 'cond': {'code': '05', 'not': False}, 'then': msg}],
            [msg] * 128,
        ]
        for body in cases:
            with self.subTest(body=body[:2]), self.assertRaises(ValueError):
                encode_script(body, 'x')
        self.assertEqual(len(encode_script([msg] * 126 + [{'op': 'call', 'target': 'B3A0'}], 'x')), 256)

    def test_nested_if_in_block(self):
        inner = {'op': 'if', 'cond': {'code': '1B', 'index': 3, 'mask': 4}, 'then': {'op': 'msg', 'id': '129'},
                 'else': [{'op': 'msg', 'id': '742'}]}
        body = [{'op': 'if', 'cond': {'code': '05'}, 'then': [inner], 'else': [inner, {'op': 'msg', 'id': '616'}]}]
        code = encode_script(body, 'x')
        self.assertEqual(code[:5], bytes.fromhex('07 05 06 07 1b'))

    def test_skip_length(self):
        self.assertEqual(skip_length(PAPAS_CODE), len(PAPAS_CODE))
        self.assertIsNone(skip_length(bytes.fromhex('41 3f')))
        self.assertEqual(skip_length(bytes.fromhex('07 03 3f 41 2d 3f')), 3)

    def test_at(self):
        self.assertEqual(bank06('06:FE10'), 0x06FE10)
        for at in ('07:8000', '06:7FFF', '0x37E10', '86:FE10'):
            with self.subTest(at=at), self.assertRaises(ValueError):
                bank06(at)


class LayoutTests(unittest.TestCase):
    def test_round_trip(self):
        rom = synthetic()
        self.assertEqual(patch(rom, dump(rom))['writes'], [])
        self.assertEqual(dump(rom, {0x12})['scripts'], [{'talk': '012', 'body': [
            {'op': 'msg', 'id': '616'}]}])
        self.assertEqual(dump(rom, {0x11})['scripts'][0]['body'], PAPAS)

    def test_document_errors(self):
        rom = synthetic()
        for bad in ({'format': 'dq5talk/0', 'scripts': []}, {'format': FORMAT}, {'format': FORMAT, 'scripts': {}},
                    doc(('010', PAPAS)), doc(('24F', PAPAS)), doc(('12', PAPAS)), doc(('011', PAPAS), ('011', PAPAS)),
                    {'format': FORMAT, 'scripts': [{'talk': '011', 'body': PAPAS, 'address': '06:8129'}]}):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                patch(rom, bad)

    def test_in_place(self):
        rom = synthetic()
        writes, starts = edits(rom, doc(('011', [{'op': 'msg', 'id': '129'}]), ('012', PAPAS)))
        self.assertEqual(starts[0], REGION[0])
        self.assertFalse(any(off == lorom(TABLE) for off, _, _, _ in writes))
        moved = apply(rom, writes)
        self.assertEqual(dump(moved, {0x11, 0x12})['scripts'][1]['body'], PAPAS)
        self.assertEqual(dump(moved, {0x13}), dump(rom, {0x13}))

    def test_relocate_group(self):
        rom = synthetic()
        longer = doc(('013', PAPAS + PAPAS))
        with self.assertRaisesRegex(ValueError, '--at'):
            edits(rom, longer)
        writes, starts = edits(rom, longer, 0x06FE10)
        self.assertEqual(starts[0], 0x06FE10)
        self.assertEqual(starts[1], rom.u16(TABLE + 2) | 0x060000)
        moved = apply(rom, writes)
        self.assertEqual(moved.u16(TABLE), 0xFE10)
        self.assertEqual(dump(moved, {0x13})['scripts'][0]['body'], PAPAS + PAPAS)
        self.assertEqual(dump(moved, {0x14, 0x40}), dump(rom, {0x14, 0x40}))
        self.assertEqual(edits(moved, longer, 0x06FE10)[0], [])

    def test_relocate_needs_free_space(self):
        rom = synthetic(fill_bank_end=True)
        with self.assertRaisesRegex(ValueError, '빈 자리'):
            edits(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10)
        with self.assertRaisesRegex(ValueError, '뱅크 06 끝'):
            edits(synthetic(), doc(('013', PAPAS * 9)), 0x06FF00)

    def test_moved_group_is_not_overwritten(self):
        rom = synthetic()
        moved = apply(rom, edits(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10)[0])
        # 묶음 0 은 06:FE10 에 그대로 남으므로 묶음 1 을 같은 자리에 둘 수 없다.
        with self.assertRaisesRegex(ValueError, '빈 자리'):
            edits(moved, doc(('013', PAPAS + PAPAS), ('033', PAPAS + PAPAS)), 0x06FE10)
        self.assertEqual(edits(moved, doc(('013', PAPAS + PAPAS)), 0x06FE10)[0], [])

    def test_moved_group_written_whole(self):
        rom = synthetic()
        writes, starts = edits(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10)
        group = [w for w in writes if w[0] == lorom(0x06FE10)]
        self.assertEqual(len(group[0][1]), sum(len(w[1]) for w in writes if w[3].startswith('묶음 0')))

    def test_check(self):
        rom = synthetic()
        check(rom)
        check(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10)
        check(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10, repack=True)

    def test_repack_needs_at_when_overflowing(self):
        rom = synthetic()
        big = [(f'{t:03X}', PAPAS * 17) for t in range(0x11, 0x11 + 64)]
        with self.assertRaisesRegex(ValueError, '--at'):
            edits(rom, doc(*big), repack=True)

    def test_repack(self):
        rom = synthetic()
        writes, starts = edits(rom, doc(('013', PAPAS + PAPAS)), 0x06FE10, repack=True)
        self.assertEqual(starts[0], REGION[0])
        self.assertEqual(starts[1], (rom.u16(TABLE + 2) | 0x060000) + 2 * len(PAPAS_CODE) - 1 - 3)
        moved = apply(rom, writes)
        for t in (0x11, 0x40, 0x24E):
            self.assertEqual(dump(moved, {t}), dump(rom, {t}))
        self.assertEqual(edits(moved, doc(('013', PAPAS + PAPAS)), 0x06FE10, repack=True)[0], [])


def build_patch(rom, manifest):
    writes = [(int(w['at'][:2], 16) * 0x8000 + int(w['at'][3:], 16) - 0x8000, bytes.fromhex(w['hex']),
               bytes.fromhex(w['orig']) if 'orig' in w else None, '') for w in manifest['writes']]
    size = manifest.get('rom_size', 0)
    built, _ = build(rom.d, [('t', size, writes)], size)
    return Rom(built)


class ExtraTests(unittest.TestCase):
    EXTRA = {'extra_at': 0x3F8000, 'hook_at': 0x06FE10}

    def extras(self, count):
        return doc(*((f'{0x900 + n:03X}', [{'op': 'msg', 'id': f'{0x700 + n:03X}'}]) for n in range(count)))

    def test_needs_places_and_order(self):
        rom = synthetic()
        with self.assertRaisesRegex(ValueError, '--extra-at'):
            patch(rom, self.extras(2))
        with self.assertRaisesRegex(ValueError, '--hook-at'):
            patch(rom, self.extras(2), extra_at=0x3F8000)
        with self.assertRaisesRegex(ValueError, '빈 번호'):
            patch(rom, doc(('901', PAPAS)), **self.EXTRA)
        for bad in ({'extra_at': 0x068000, 'hook_at': 0x06FE10}, {'extra_at': 0x408000, 'hook_at': 0x06FE10},
                    {'extra_at': 0x3F8000, 'hook_at': 0x078000}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                patch(rom, self.extras(2), **bad)
        for talk in ('24F', '8FF', '1000'):
            with self.subTest(talk=talk), self.assertRaises(ValueError):
                patch(rom, doc((talk, PAPAS)), **self.EXTRA)

    def test_round_trip_and_growth(self):
        rom = synthetic()
        source = self.extras(34)
        manifest = patch(rom, source, **self.EXTRA)
        self.assertEqual(manifest['rom_size'], 2)
        after = build_patch(rom, manifest)
        cfg = extra_config(after)
        self.assertEqual((cfg['end'], cfg['table'], cfg['bank'], cfg['hook']), (0x922, 0x3F8000, 0x3F, 0x06FE10))
        self.assertEqual(after.u16(0x3F8002), 0x8004 + 32 * 3)
        self.assertEqual(dump(after, {0x921})['scripts'], [{'talk': '921', 'body': [{'op': 'msg', 'id': '721'}]}])
        self.assertEqual(patch(after, source)['writes'], [])
        self.assertEqual(patch(after, dump(after))['writes'], [])
        grown = doc(('922', PAPAS))
        with self.assertRaisesRegex(ValueError, '--extra-at'):
            patch(after, grown)
        again = build_patch(after, patch(after, grown, extra_at=0x3F8000))
        self.assertEqual(extra_config(again)['end'], 0x923)
        self.assertEqual(dump(again, {0x922})['scripts'][0]['body'], PAPAS)
        self.assertEqual(dump(again, {0x900}), dump(after, {0x900}))
        check(rom, source, extra_at=0x3F8000, hook_at=0x06FE10)

    def test_hook_move_mixed_and_limits(self):
        rom = synthetic()
        after = build_patch(rom, patch(rom, self.extras(3), **self.EXTRA))
        short = [{'op': 'msg', 'id': '129'}]
        moved = build_patch(after, patch(after, doc(('012', short)), hook_at=0x06FF00))
        cfg = extra_config(moved)
        self.assertEqual(cfg['hook'], 0x06FF00)
        self.assertEqual(dump(moved, {0x12})['scripts'][0]['body'], short)
        self.assertEqual(dump(moved, {0x902}), dump(after, {0x902}))
        with self.assertRaisesRegex(ValueError, '뱅크를 넘음'):
            patch(rom, self.extras(3), extra_at=0x3FFFF8, hook_at=0x06FE10)
        data = bytearray(after.d)
        data[lorom(0x3F8050)] = 0x55
        with self.assertRaisesRegex(ValueError, '다른 자료'):
            patch(Rom(data), self.extras(40), extra_at=0x3F8000)
        partial = bytearray(rom.d)
        partial[lorom(SITES['run']):lorom(SITES['run']) + 3] = bytes.fromhex('20 10 fe')
        with self.assertRaises(ValueError):
            extra_config(Rom(partial))

    def test_hooks_need_free_space(self):
        with self.assertRaisesRegex(ValueError, '빈 자리'):
            patch(synthetic(fill_bank_end=True), self.extras(1), **self.EXTRA)


if __name__ == '__main__':
    unittest.main()
