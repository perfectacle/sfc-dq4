import unittest

import dq4battlemsg as bm
import dq4battletexts


def punct():
    return {ch: (0x900 + k, 4) for k, ch in enumerate(bm.PUNCT)}


class EncodeTests(unittest.TestCase):
    def setUp(self):
        self.punct = punct()
        self.chars = bm.charset(self.punct)

    def test_every_message_fits_a_line_and_the_buffer(self):
        for n, text in dq4battletexts.SOURCE.items():
            codes, lines = bm.encode(text, 0xFE, self.punct, self.chars)
            self.assertLessEqual(max(lines), bm.LINE_CELLS, f'{n:03X}')
            self.assertLessEqual(len(codes), bm.BUFFER, f'{n:03X}')

    def test_no_end_code_inside_a_message(self):
        # 24:8C39 는 끝 부호를 세어 앞 메시지를 건너뛰므로 구간 바이트에 끝 부호가 있으면 안 된다
        for n, text in dq4battletexts.SOURCE.items():
            codes, _ = bm.encode(text, 0xFE, self.punct, self.chars)
            self.assertFalse(set(codes[:-1]) & set(bm.ENDS), f'{n:03X}')

    def test_run_has_length_and_tokens(self):
        codes, lines = bm.encode('{F7}의 공격!', 0xFE, self.punct, self.chars)
        self.assertEqual(codes[0], 0xF7)
        self.assertEqual(codes[1], bm.RUN)
        self.assertEqual(len(codes), 4 + codes[2])     # 이름, E3, 길이, 구간, 끝
        self.assertEqual(codes[-1], 0xFE)

    def test_josa_and_tiles(self):
        codes, _ = bm.encode('{F7}{은} MP 2', 0xFE, self.punct, self.chars)
        self.assertEqual(codes[1:4], [bm.RUN, 4, bm.JOSA_TOKEN])
        self.assertIn(0xAC, codes)
        self.assertIn(0x04, codes)

    def test_charset_skips_end_codes(self):
        for token in self.chars.values():
            self.assertFalse(set(token) & set(bm.ENDS))


class TableTests(unittest.TestCase):
    def test_codes_map_to_pool_tiles(self):
        blob, at = bm.tables(bm.charset(punct()))
        index = blob[at['index'] - bm.TABLE_AT:][:256]
        for k, c in enumerate(bm.CODES):
            self.assertEqual(index[c], k)
        self.assertEqual(index[0x01], 0xFF)
        self.assertEqual(len(bm.CODES), len(bm.POOL))

    def test_pool_tiles_avoid_status_names_and_attack_effect(self):
        # 180~1CF 는 상태 창 이름, B0~122 는 공격 연출, 096~098 은 전투 화면이 쓴다
        for t in bm.POOL:
            self.assertFalse(0x180 <= t < 0x1D0 or 0xB0 <= t <= 0x122 or t < 0x99, hex(t))
        self.assertEqual(bm.POOL[:len(bm.POOL_A)], bm.POOL_A)

    def test_codes_are_not_ends_digits_or_blank(self):
        for c in bm.CODES:
            self.assertFalse(c in bm.ENDS or 0x01 <= c <= 0x0B or c >= 0xE2 or c in (0x83, 0x84, 0x8D), hex(c))

    def test_pool_b_is_one_block(self):
        b0 = bm.POOL.index(bm.POOL_B[0])
        self.assertEqual(bm.POOL[b0:b0 + len(bm.POOL_B)], bm.POOL_B)

    def test_jong(self):
        self.assertEqual(bm.jong('라'), 0)
        self.assertEqual(bm.jong('언'), 1)
        self.assertEqual(bm.jong('알'), 2)


class TokenTests(unittest.TestCase):
    def test_appear_tokens(self):
        toks = bm.tokens(bm.APPEAR, punct())
        self.assertEqual(toks[0], 0xC000 | bm.JOSA_KEYS['이'])
        self.assertEqual(toks[1], 0x8000 | bm.SPACE_PX)

    def test_name_blob_ends_entries_before_appear(self):
        blob, at = bm.name_blob([(b'\x10\x11', [1, 2])], [3])
        self.assertEqual(blob[:3], bytes((2, 0x10, 0x11)))
        self.assertEqual(blob[at - 1], 0)
        self.assertEqual(blob[at:], (3).to_bytes(2, 'little'))


if __name__ == '__main__':
    unittest.main()
