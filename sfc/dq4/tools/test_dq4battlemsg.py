import re
import unittest
from unittest import mock

import dq4battlemsg as bm
import dq4battletexts
import dq4nameentry as ne
import dq5battletext
import dq5battletextwrite


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

    def test_pool_keeps_the_tiles_messages_draw(self):
        drawn = set(bm.TILES.values()) | {b for pair in bm.PAIRS.values() for b in pair}
        self.assertFalse(drawn & set(bm.POOL), sorted(hex(t) for t in drawn & set(bm.POOL)))

    def test_codes_are_not_ends_digits_or_blank(self):
        for c in bm.CODES:
            self.assertFalse(c in bm.ENDS or 0x01 <= c <= 0x0B or c >= 0xE2 or c in (0x83, 0x84, 0x8D), hex(c))

    def test_restored_pools_are_one_block_and_fit_the_shadow(self):
        b0, b1 = bm.restored()
        self.assertEqual(set(bm.POOL[b0:b1]), set(bm.POOL_B + bm.POOL_C))
        self.assertLessEqual((b1 - b0) * 8, bm.SHADOW_BYTES)

    def test_jong(self):
        self.assertEqual(bm.jong('라'), 0)
        self.assertEqual(bm.jong('언'), 1)
        self.assertEqual(bm.jong('알'), 2)


class TokenTests(unittest.TestCase):
    def test_appear_tokens(self):
        toks = bm.tokens(bm.APPEAR, punct())
        self.assertEqual(toks[0], 0xC000 | bm.JOSA_KEYS['이'])
        self.assertEqual(toks[1], 0x8000 | bm.SPACE_PX)

    def test_suffix_tokens_two_per_suffix(self):
        p = punct()
        toks = bm.suffix_tokens(p)
        self.assertEqual(len(toks), bm.SUFFIX_TOKENS * len(bm.SUFFIXES))
        self.assertEqual(toks[0], p['A'][0])
        self.assertEqual(toks[bm.SUFFIX_TOKENS * (len(bm.SUFFIX_LETTERS) - 1)], p['H'][0])
        plural = bm.SUFFIX_TOKENS * bm.SUFFIXES.index('들')
        self.assertEqual(toks[plural:plural + 2], [ne.GLYPHS.index('들'), 0x8000])
        self.assertEqual(bm.PLURAL, bytes((0x1F, 0x20)))

    def test_name_blob_ends_entries_before_appear(self):
        blob, at = bm.name_blob([(b'\x10\x11', [1, 2])], [3])
        self.assertEqual(blob[:3], bytes((2, 0x10, 0x11)))
        self.assertEqual(blob[at - 1], 0)
        self.assertEqual(blob[at:], (3).to_bytes(2, 'little'))


def render(font, ch, tight):
    return [[[1] + [0] * 7 for _ in range(16)]]


FIRST = len(ne.GLYPHS) + 50
NAMES = [(b'\x10\x11', [ne.GLYPHS.index('가'), 0x8000 | bm.SPACE_PX])]


def base():
    d = bytearray(0x400000)
    d[bm.lorom(bm.RUN_TABLE):bm.lorom(bm.RUN_TABLE) + 2] = bytes.fromhex('d386')
    return d


class ApplyTests(unittest.TestCase):
    def run_apply(self, d, writes=(), clash=frozenset()):
        self.compiled = None

        def compile_messages(head, msgs, at):
            self.compiled = (head, msgs, at)
            return {'writes': list(writes)}
        original = [[0x20, 0xFE] for _ in range(432)]
        with mock.patch.object(bm, 'original_bytes', return_value={0x01, *clash}), \
                mock.patch.object(dq5battletextwrite, 'read_messages', return_value=original), \
                mock.patch.object(dq5battletextwrite, 'compile_messages', compile_messages), \
                mock.patch.object(bm, 'messages', return_value={3: [0x30, 0xFE]}), \
                mock.patch.object(bm, 'name_entries', return_value=NAMES):
            return bm.apply(d, object(), render, FIRST)

    def test_tables_names_and_defs_agree(self):
        d = base()
        defs = dict(re.findall(r'^(!\w+) = (.+)$', self.run_apply(d), re.M))
        p = punct_of(FIRST)
        blob, at = bm.tables(bm.charset(p))
        o = bm.lorom(bm.TABLE_AT)
        self.assertEqual(bytes(d[o:o + len(blob)]), blob)
        for name in ('index', 'tile', 'josa', 'jong', 'charset', 'codes'):
            self.assertEqual(int(defs[f'!bm_{name}'][1:], 16), at[name], name)
        appear = bm.tokens(bm.APPEAR, p)
        names, appear_at = bm.name_blob(NAMES, appear)
        o = bm.lorom(bm.NAMES_AT)
        self.assertEqual(bytes(d[o:o + len(names)]), names)
        self.assertEqual(int(defs['!bm_appear'][1:], 16), bm.NAMES_AT + appear_at)
        self.assertEqual(int(defs['!bm_appear_count']), len(appear))
        suffix = b''.join(t.to_bytes(2, 'little') for t in bm.suffix_tokens(p))
        at = bm.lorom(int(defs['!bm_suffix'][1:], 16))
        self.assertEqual(bytes(d[at:at + len(suffix)]), suffix)
        self.assertEqual(int(defs['!bm_suffix_plural']), bm.SUFFIXES.index('들'))
        self.assertEqual(int(defs['!bm_plural'][1:], 16), 0x201F)
        self.assertEqual(int(defs['!bm_digit0']), FIRST + bm.PUNCT.index('0'))
        self.assertEqual(int(defs['!bm_count']), len(bm.POOL))
        self.assertEqual((int(defs['!bm_b0']), int(defs['!bm_b1'])), bm.restored())

    def test_punct_glyphs_follow_first_glyph(self):
        d = base()
        self.run_apply(d)
        for k in range(len(bm.PUNCT)):
            n = FIRST + k
            o = bm.lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32)
            self.assertEqual(bytes(d[o:o + 32]), b'\x80' * 16 + bytes(16))
        n = FIRST + len(bm.PUNCT)
        o = bm.lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32)
        self.assertEqual(bytes(d[o:o + 32]), bytes(32))

    def test_translated_messages_replace_only_their_numbers(self):
        self.run_apply(base())
        head, msgs, at = self.compiled
        self.assertEqual(at, bm.STREAM_AT)
        self.assertEqual(len(head), 0x200000)
        self.assertEqual(msgs[3], [0x30, 0xFE])
        self.assertEqual(msgs[2], [0x20, 0xFE])

    def test_writes_check_original_bytes(self):
        d = base()
        d[bm.lorom(0x248000)] = 0xAA
        ok = [{'at': '24:8000', 'hex': 'bbcc', 'orig': 'aa00'}, {'at': '4C:8000', 'hex': '0102'}]
        self.run_apply(d, ok)
        self.assertEqual(d[bm.lorom(0x248000):bm.lorom(0x248000) + 2], b'\xbb\xcc')
        self.assertEqual(d[bm.lorom(0x4C8000):bm.lorom(0x4C8000) + 2], b'\x01\x02')
        for bad in ({'at': '24:8000', 'hex': 'bbcc', 'orig': 'ab00'}, {'at': '24:8000', 'hex': '01'}):
            with self.subTest(bad=bad):
                d = base()
                d[bm.lorom(0x248000)] = 0xAA
                with self.assertRaisesRegex(ValueError, '예상과 다름'):
                    self.run_apply(d, [bad])

    def test_rejects(self):
        with self.assertRaisesRegex(ValueError, '풀 코드'):
            self.run_apply(base(), clash={bm.CODES[5]})
        d = base()
        d[bm.lorom(bm.RUN_TABLE)] = 0
        with self.assertRaisesRegex(ValueError, '빈 처리기'):
            self.run_apply(d)
        for at in (bm.TABLE_AT + 0x100, bm.NAMES_AT + 1, FIRST):
            d = base()
            if at == FIRST:
                at = (ne.GLYPH_BANK + at // 1024) << 16 | 0x8000 + at % 1024 * 32
            d[bm.lorom(at)] = 1
            with self.subTest(at=hex(at)), self.assertRaisesRegex(ValueError, '비어 있지 않'):
                self.run_apply(d)


def punct_of(first):
    return {ch: (first + k, 2) for k, ch in enumerate(bm.PUNCT)}


class MessagesTests(unittest.TestCase):
    def test_end_and_sound_code_follow_the_original(self):
        p = punct()
        chars = bm.charset(p)
        with mock.patch.object(dq5battletext, 'message', return_value=[0x10, 0xF2, 0xEF]):
            out = bm.messages(bytes(16), p, chars)
        self.assertEqual(set(out), set(dq4battletexts.SOURCE))
        for n, codes in out.items():
            self.assertEqual(codes[-2:], [0xF2, 0xEF], f'{n:03X}')
        with mock.patch.object(dq5battletext, 'message', return_value=[0x10, 0xFE]):
            plain = bm.messages(bytes(16), p, chars)
        n = next(iter(plain))
        self.assertEqual(plain[n][-1], 0xFE)
        self.assertEqual(len(out[n]), len(plain[n]) + 1)

    def test_too_long_message_is_rejected(self):
        p = punct()
        long = {0x10: '가' * 40}
        with mock.patch.object(bm, 'SOURCE', long), \
                mock.patch.object(dq5battletext, 'message', return_value=[0x10, 0xFE]), \
                self.assertRaisesRegex(ValueError, '칸을 넘음'):
            bm.messages(bytes(16), p, bm.charset(p))


class OriginalBytesTests(unittest.TestCase):
    def test_only_untranslated_used_messages_count(self):
        def message(rom, n):
            if n in dq4battletexts.SOURCE:
                return [0x50, 0xFE]
            if n in bm.UNUSED:
                return [0x51, 0xFE]
            return [0x52, 0xE2, 0xFE]
        with mock.patch.object(dq5battletext, 'message', message):
            used = bm.original_bytes(bytes(16))
        self.assertIn(0x52, used)
        self.assertFalse({0x50, 0x51, 0xE2, 0xFE} & used)
        self.assertTrue({0x01, 0x8D, *range(0x02, 0x0C)} <= used)


class NameEntriesTests(unittest.TestCase):
    def test_dedup_known_glyphs_and_group_name(self):
        import dq4windowtext as wt
        import dq5namewrite
        raw = {3: [b'\x10', b'\x11'], 4: [b'\x10', b'\x12', b''], 5: [b'\x13']}
        texts = {3: ['いぬ', 'ねこ'], 4: ['いぬ', 'とり', 'から'], 5: ['ほし']}
        adopted = {'いぬ': '개', 'ねこ': '고양이', 'とり': '새 떼', 'から': '빈'}
        d = bytearray(0x400000)
        group = b'\x20\x21\x22\x23\x24\x25'
        d[bm.lorom(bm.GROUP_NAME):bm.lorom(bm.GROUP_NAME) + 6] = group
        with mock.patch.object(dq5namewrite, 'read_tables', return_value=raw), \
                mock.patch.object(wt, 'rom_names', lambda d, t, n: texts[t][:n]), \
                mock.patch.object(wt, 'adopted', lambda table: adopted), \
                mock.patch.object(wt, 'numbered_names', return_value={5: {0: '별☆'}}):
            entries = bm.name_entries(d)
        names = [n for n, _ in entries]
        # 같은 이름 바이트는 한 번, 빈 이름과 글리프에 없는 글자(☆)는 뺀다
        self.assertEqual(names, [b'\x10', b'\x11', b'\x12', group])
        g = ne.GLYPHS.index
        self.assertEqual(entries[2][1], [g('새'), 0x8000 | bm.SPACE_PX, g('떼')])
        self.assertEqual(entries[-1][1], [g('마'), g('물'), 0x8000 | bm.SPACE_PX, g('무'), g('리')])


if __name__ == '__main__':
    unittest.main()
