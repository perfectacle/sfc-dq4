import unittest

import dq4romledger as L
import dq4romledgercheck as C


def rom(size=0x10000, **writes):
    """size 바이트 0 롬에 {'o<오프셋 16진>': bytes} 를 써 넣은 것."""
    out = bytearray(size)
    for k, v in writes.items():
        o = int(k[1:], 16)
        out[o:o + len(v)] = v
    return bytes(out)


def stage(name, ranges, cleared=()):
    return {'name': name, 'size': 0x10000, 'sha1': '',
            'ranges': [L.range_doc(s, e) for s, e in ranges], 'cleared': [L.range_doc(s, e) for s, e in cleared]}


class AddressTest(unittest.TestCase):
    def test_cpu_and_offset_round_trip(self):
        self.assertEqual(L.cpu(0x7FDC), '00:FFDC')
        self.assertEqual(L.cpu(0x2F0000), '5E:8000')
        self.assertEqual(L.cpu(0x3F8000), 'FF:8000')
        for text in ('00:FFDC', '5E:8000', '2B:E676'):
            self.assertEqual(L.cpu(L.offset(text)), text)
        self.assertEqual(L.offset('85:8000'), L.offset('05:8000'))
        self.assertEqual(L.offset('0x123'), 0x123)
        for bad in ('00:7FFF', '7E:8000', '05', 'zz:8000'):
            with self.assertRaises(ValueError):
                L.offset(bad)


class DiffTest(unittest.TestCase):
    def test_changed_bytes_become_ranges(self):
        before = rom()
        after = rom(o10=b'\1\2\3', o20=b'\5', o1FF=b'\7\7')     # 1FF~200 은 BLOCK 경계를 넘는 한 범위
        self.assertEqual(L.diff_ranges(before, after), [(0x10, 0x13), (0x20, 0x21), (0x1FF, 0x201)])

    def test_same_value_is_not_a_write(self):
        before = rom(o10=b'\1\2\3')
        self.assertEqual(L.diff_ranges(before, rom(o10=b'\x01\x09\x03')), [(0x11, 0x12)])
        self.assertEqual(L.diff_ranges(before, before), [])

    def test_longer_rom_compares_against_zero(self):
        before = rom(0x100)
        after = rom(0x200, o150=b'\1', o1FF=b'\2')
        self.assertEqual(L.diff_ranges(before, after), [(0x150, 0x151), (0x1FF, 0x200)])
        with self.assertRaises(ValueError):
            L.diff_ranges(after, before)

    def test_run_to_the_end(self):
        self.assertEqual(L.diff_ranges(rom(0x300), rom(0x300, o2FE=b'\1\1')), [(0x2FE, 0x300)])

    def test_merge_and_bank_cross(self):
        self.assertEqual(L.merge([(10, 12), (0, 2), (14, 15)], gap=2), [(0, 2), (10, 15)])
        self.assertEqual(L.merge([(0, 2), (3, 4)]), [(0, 2), (3, 4)])
        self.assertTrue(L.crosses_bank(0x7FFF, 0x8001))
        self.assertFalse(L.crosses_bank(0x7000, 0x8000))

    def test_expanded_original_mirrors_banks_20_to_2f(self):
        dq5 = bytes(range(256)) * (L.ORIGINAL_SIZE // 256)
        base = L.expanded_original(dq5)
        self.assertEqual(len(base), L.EXPANDED_SIZE)
        self.assertEqual(base[L.ORIGINAL_SIZE:L.MIRROR_END], dq5[L.MIRROR_FROM:])
        self.assertEqual(base[L.MIRROR_END:], bytes(L.EXPANDED_SIZE - L.MIRROR_END))

    def test_cleared_is_a_long_zero_run_over_untouched_mirror(self):
        s = L.ORIGINAL_SIZE
        mirror = bytearray(L.MIRROR_END)
        mirror[s:s + 100] = b'\x11\x00' * 50                  # 거울 자체에 0 이 섞임
        before = bytearray(mirror)
        before[s + 60] = 0x22                                   # 앞 단계가 쓴 자료
        after = bytearray(before)
        after[s:s + 100] = bytes(100)
        after[s + 40:s + 44] = b'\x33\x00\x00\x33'            # 새 자료(속의 0 은 짧음)
        ranges = L.diff_ranges(before, after)
        got = L.cleared_ranges(ranges, mirror, before, after)
        # s+44~s+59 는 16바이트라 짧고, s+60 은 앞 단계 자료를 지운 것이라 끊김. 지운 것은 값이 바뀐(짝수) 칸뿐
        self.assertEqual(L.merge(got, gap=1), [(s, s + 39), (s + 62, s + 99)])
        self.assertEqual(L.intersect([(0, 10), (20, 30)], [(5, 25)]), [(5, 10), (20, 25)])

    def test_short_zero_run_at_bank_end_is_cleared(self):
        s = L.ORIGINAL_SIZE + L.BANK
        mirror = bytearray(L.MIRROR_END)
        mirror[s - 8:s + 8] = b'\x11' * 16
        after = bytearray(mirror)
        after[s - 8:s] = bytes(8)
        after[s] = 0x09
        ranges = L.diff_ranges(mirror, after)
        self.assertEqual(ranges, [(s - 8, s + 1)])
        self.assertEqual(L.cleared_ranges(ranges, mirror, mirror, after), [(s - 8, s)])

    def test_build_ledger(self):
        dq5 = bytes(L.ORIGINAL_SIZE)
        a = bytearray(L.EXPANDED_SIZE)
        a[0x100] = 1
        b = bytearray(a)
        b[0x100:0x102] = b'\2\2'
        doc = L.build(dq5, [('a', bytes(a)), ('b', bytes(b))])
        self.assertEqual(doc['format'], L.FORMAT)
        self.assertEqual([s['name'] for s in doc['stages']], ['a', 'b'])
        self.assertEqual(doc['stages'][1]['ranges'], [{'off': '000100', 'end': '000101', 'cpu': '00:8100~00:8101',
                                                       'bytes': 2}])
        self.assertEqual(L.range_of(doc['stages'][1]['ranges'][0]), (0x100, 0x102))


class BuildStagesTest(unittest.TestCase):
    def test_build_names_its_stages_from_the_known_list(self):
        import re
        from pathlib import Path
        text = (Path(L.__file__).parent / 'dq4build.py').read_text(encoding='utf-8')
        self.assertEqual(tuple(re.findall(r"stage\('(\w+)'", text)), L.STAGES)


class AllowTest(unittest.TestCase):
    STAGES = ['title', 'menu', 'chapter1']

    def test_parse_at(self):
        self.assertEqual(C.parse_at('00:FFDC~00:FFDF'), (0x7FDC, 0x7FE0))
        self.assertEqual(C.parse_at('00:A70C'), (0x270C, 0x270D))
        with self.assertRaises(C.AllowError):
            C.parse_at('00:FFDF~00:FFDC')

    def test_load_and_match(self):
        allow = C.load_allow('''
[[overlap]]
earlier = "*"
later = "menu"
at = "00:8000~00:80FF"
why = "x"
[[original]]
stage = "chapter1"
at = "01:8000"
why = "y"
''', self.STAGES)
        self.assertTrue(C.find_allow(allow, 'overlap', 0x10, 0x20, earlier='title', later='menu'))
        self.assertIsNone(C.find_allow(allow, 'overlap', 0x10, 0x20, earlier='title', later='chapter1'))
        self.assertIsNone(C.find_allow(allow, 'overlap', 0xF0, 0x110, earlier='title', later='menu'))   # 범위 밖으로 삐져나옴
        self.assertTrue(C.find_allow(allow, 'original', 0x8000, 0x8001, stage='chapter1'))
        self.assertTrue(allow['overlap'][0]['used'])

    def test_bad_entries(self):
        for text in ('[[nope]]\nat = "00:8000"\nwhy = "x"',
                     '[[cross]]\nstage = "menu"\nat = "00:8000"\nwhy = " "',
                     '[[cross]]\nstage = "sound"\nat = "00:8000"\nwhy = "x"',
                     '[[cross]]\nstage = "menu"\nat = "00:8000"\nwhy = "x"\nextra = 1',
                     '[[cross]]\nstage = "menu"\nat = "00:1000"\nwhy = "x"'):
            with self.subTest(text), self.assertRaises(C.AllowError):
                C.load_allow(text, self.STAGES)

    def test_repo_allow_list_parses(self):
        allow = C.load_allow(C.ALLOW.read_text(encoding='utf-8'), L.STAGES)
        self.assertTrue(all(item['why'].strip() for items in allow.values() for item in items))


class OverlapTest(unittest.TestCase):
    def test_subtract(self):
        self.assertEqual(C.subtract([(0, 10), (20, 30)], [(2, 4), (8, 22), (29, 40)]), [(0, 2), (4, 8), (22, 29)])
        self.assertEqual(C.subtract([(0, 10)], []), [(0, 10)])

    def test_later_stage_rewriting_earlier_bytes(self):
        stages = [stage('a', [(0x10, 0x20)]), stage('b', [(0x30, 0x40)]), stage('c', [(0x18, 0x34)])]
        self.assertEqual(C.overlaps(stages, 0x100), [('a', 'c', 0x18, 0x20), ('b', 'c', 0x30, 0x34)])

    def test_cleared_bytes_are_free_for_later_stages(self):
        stages = [stage('a', [(0x10, 0x20)], cleared=[(0x10, 0x18)]), stage('b', [(0x10, 0x1C)])]
        self.assertEqual(C.overlaps(stages, 0x100), [('a', 'b', 0x18, 0x1C)])

    def test_clearing_later_releases_owner(self):
        stages = [stage('a', [(0x10, 0x20)]), stage('b', [(0x10, 0x20)], cleared=[(0x10, 0x20)]),
                  stage('c', [(0x10, 0x20)])]
        self.assertEqual(C.overlaps(stages, 0x100), [])

    def test_check_overlaps_reports_unallowed(self):
        allow = C.load_allow('[[overlap]]\nearlier = "a"\nlater = "b"\nat = "00:8010~00:8013"\nwhy = "x"', ['a', 'b'])
        rows, bad = C.check_overlaps([stage('a', [(0x10, 0x20)]), stage('b', [(0x10, 0x14), (0x1E, 0x20)])],
                                     allow, 0x100)
        self.assertEqual([r['at'] for r in rows], ['00:8010~00:8013', '00:801E~00:801F'])
        self.assertEqual(len(bad), 1)
        self.assertIn('00:801E~00:801F', bad[0])


class OriginalTest(unittest.TestCase):
    def test_blocks_only_cover_nonzero_original_bytes(self):
        dq5 = rom(0x9000, o100=b'\1' * 40, o140=b'\1' * 40, o7FDC=b'\1\1\1\1')
        blocks = C.original_blocks(stage('a', [(0xF0, 0x200), (0x7FDC, 0x7FE0), (0x8F00, 0x9100)]), dq5)
        self.assertEqual(blocks, [(0x100, 0x128), (0x140, 0x168)])     # 틈 24바이트는 GAP 보다 커서 둘
        dq5 = rom(0x9000, o100=b'\1' * 40, o138=b'\1' * 40)
        self.assertEqual(C.original_blocks(stage('a', [(0xF0, 0x200)]), dq5), [(0x100, 0x160)])

    def test_gap_splits(self):
        dq5 = rom(0x1000, o100=b'\1' * 70, o200=b'\1' * 10)
        rows, small, bad = C.check_original([stage('a', [(0x100, 0x210)])], C.load_allow('', ['a']), dq5)
        self.assertEqual(small['a'], {'blocks': 1, 'bytes': 10})
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(bad), 1)


class CrossTest(unittest.TestCase):
    def test_crossing_data_and_code(self):
        allow = C.load_allow('[[cross]]\nstage = "a"\nat = "00:FF00~01:80FF"\nwhy = "자료"', ['a'])
        rows, bad = C.check_cross([stage('a', [(0x7FF0, 0x8010), (0xFFF0, 0x10010)])], allow,
                                  [('ok', 0x5E8000, 0x100), ('bad', 0x5EFFF0, 0x20)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(bad), 2)
        self.assertIn('01:FFF0', bad[0])
        self.assertIn('bad', bad[1])


class InvariantTest(unittest.TestCase):
    def test_vectors(self):
        data = bytearray(0x8000)
        for at in C.VECTORS:
            data[at - 0x8000:at - 0x7FFE] = (0x8100).to_bytes(2, 'little')
        data[0x100] = 0x78
        self.assertEqual(C.inv_vectors(data, data)[1], [])
        data[0x100] = 0x00
        self.assertEqual(len(C.inv_vectors(data, data)[1]), len(C.VECTORS))

    def test_hooks(self):
        dq5 = bytearray(0x10000)
        data = bytearray(0x18000)
        data[0x100:0x104] = bytes((0x22, 0x00, 0x80, 0x02))      # JSL 02:8000 → 파일 10000(자료 있음)
        data[0x10000] = 0x08
        data[0x200:0x204] = bytes((0x5C, 0x10, 0x80, 0x02))      # JML 02:8010 → 0
        dq5[0x300] = 0x22                                         # 원래 JSL 의 대상만 바꿈
        data[0x300:0x304] = bytes((0x22, 0x00, 0x80, 0x09))       # 09:8000 은 롬 밖
        stages = [stage('a', [(0x100, 0x104), (0x200, 0x204), (0x301, 0x304)])]
        summary, bad = C.inv_hooks(data, dq5, stages)
        self.assertEqual(summary, '훅 3개')
        self.assertEqual(len(bad), 2)
        self.assertIn('0 바이트', bad[0])
        self.assertIn('롬 밖', bad[1])

    def test_shops(self):
        data = bytearray(0x38000)
        put = lambda a, b: data.__setitem__(slice(L.offset(a), L.offset(a) + len(b)), b)  # noqa: E731
        put('06:F4AE', b'\x02')
        put('06:F54E', b'\x02')
        put('06:F4BA', b'\x00\x90')
        put('06:F50D', b'\x00\x90')
        put('02:9000', bytes.fromhex('0890 0b90 0e90 1190'))
        put('02:9008', bytes.fromhex('01 05 ff 01 06 ff 01 07 ff 01 08 ff ff'))
        self.assertEqual(C.inv_shops(data, data), ('가게 02:9000 목록 4개', []))
        put('02:900F', b'\xE0')
        self.assertIn('품목 E0', C.inv_shops(data, data)[1][0])
        put('06:F54E', b'\x03')
        self.assertIn('두 루틴', C.inv_shops(data, data)[1][0])


if __name__ == '__main__':
    unittest.main()
