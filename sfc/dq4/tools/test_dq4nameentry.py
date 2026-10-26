import unittest

import dq4nameentry as ne


class CompositionTests(unittest.TestCase):
    def assert_composed(self, keys, expected):
        actual = ''.join(ne.GLYPHS[n] for n in ne.compose(keys))
        self.assertEqual(actual, expected)

    def test_character_names(self):
        for keys, expected in [('ㄹㅏㅇㅣㅇㅏㄴ', '라이안'), ('ㅇㅏㄹㅣㄴㅏ', '아리나'),
                               ('ㅌㅗㄹㄴㅔㅋㅗ', '톨네코')]:
            with self.subTest(name=expected):
                self.assert_composed(keys, expected)

    def test_compound_vowels(self):
        for keys, expected in [('ㄱㅗㅏㄴ', '관'), ('ㅇㅜㅓㄴ', '원'), ('ㅇㅡㅣ', '의'),
                               ('ㅗㅏ', 'ㅘ'), ('ㅜㅔ', 'ㅞ')]:
            with self.subTest(keys=keys):
                self.assert_composed(keys, expected)

    def test_final_consonant_moves_to_next_syllable(self):
        for keys, expected in [('ㄱㅏㄴㅏ', '가나'), ('ㄷㅏㄹㄱㅏ', '달가'),
                               ('ㅇㅏㄴㅎㅏ', '안하'), ('ㄱㅏㅆㅏ', '가싸')]:
            with self.subTest(keys=keys):
                self.assert_composed(keys, expected)

    def test_fourth_character_can_still_take_a_final_consonant(self):
        self.assert_composed('ㄱㅏㄴㅏㄷㅏㄹㅏㄱ', '가나다락')

    def test_fifth_character_rejection_preserves_fourth_syllable(self):
        self.assert_composed('ㄱㅏㄴㅏㄷㅏㄹㅏㄱㅏ', '가나다락')

    def test_unsupported_syllable_keeps_previous_composition(self):
        self.assertNotIn('뺴', ne.KS)
        self.assert_composed('ㅃㅒ', 'ㅃ')
        self.assert_composed('ㅃㅒㅏ', '빠')

    def test_empty_input(self):
        self.assertEqual(ne.compose(''), [])


class NameEncodingTests(unittest.TestCase):
    def test_known_saved_name(self):
        encoded = b''.join(ne.code_bytes(n) for n in ne.compose('ㄹㅏㅇㅣㅇㅏㄴ'))
        self.assertEqual(encoded, bytes.fromhex('8b 2f 93 3c 91 5a'))
        self.assertEqual(ne.decode_name(encoded + b'\x01\x01'), '라이안')

    def test_legacy_untagged_name_decodes_only_as_legacy(self):
        legacy = bytes.fromhex('16 2f 1e 3c 1c 5a 01 01')
        self.assertEqual(ne.decode_name(legacy, ne.LEGACY_HI_BASE), '라이안')
        with self.assertRaises(ValueError):
            ne.decode_name(legacy)

    def test_every_supported_character_round_trips_without_control_bytes(self):
        self.assertEqual(len(ne.KS), 2350)
        codes = set()
        for char in ne.JAMO + ne.KS:
            with self.subTest(char=char):
                encoded = ne.code_bytes(ne.GLYPHS.index(char))
                self.assertEqual(len(encoded), 2)
                # 첫 바이트는 원래 이름에 없는 85~9A, 둘째는 가나 범위. 이름 끝 01·탁점 83/84·창 접두 9F·자리 표시 B0~ 와 안 겹침
                self.assertTrue(0x85 <= encoded[0] <= 0x9A)
                self.assertTrue(0x10 <= encoded[1] <= 0x7E)
                self.assertEqual(ne.decode_name(encoded + b'\x01' * 6), char)
                self.assertNotIn(encoded, codes)
                codes.add(encoded)

    def test_full_name_uses_all_eight_bytes(self):
        encoded = b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in '가나다라')
        self.assertEqual(len(encoded), 8)
        self.assertEqual(ne.decode_name(encoded), '가나다라')

    def test_terminator_ignores_unused_name_slots(self):
        self.assertEqual(ne.decode_name(b'\x01' * 8), '')
        encoded = ne.code_bytes(ne.GLYPHS.index('가'))
        self.assertEqual(ne.decode_name(encoded + b'\x01\x01' + b'\xff' * 4), '가')


if __name__ == '__main__':
    unittest.main()
