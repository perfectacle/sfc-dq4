"""이름 문자열 표의 제자리 다시 채우기·옮기기·입력 검사를 원본 롬 없이 확인한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dq5build import build, parse_at as patch_at  # noqa: E402
from dq5map import lorom  # noqa: E402
from dq5namewrite import (  # noqa: E402
    COUNTS, FORMAT, MAX_NAME, REGIONS, TABLES, compile_tables, decoded_tables, export, overrides, parse_at, patch,
    read_tables, valid_name,
)
from dq5text import STRING_TABLES  # noqa: E402


def source_fixture():
    """원래 자리를 빈틈 없이 채운 표와 21:959B 포인터를 가진 1.5MB 롬과 그 표."""
    data = bytearray(0x180000)
    tables = {}
    for start, end, ts in REGIONS:
        total = sum(COUNTS[t] for t in ts)
        length = (end - start - total) // total
        longer = (end - start - total) % total
        k, a = 0, start
        for t in ts:
            names = []
            for i in range(COUNTS[t]):
                n = length + (k < longer)
                names.append([(t * 16 + i + j) % 0xE0 for j in range(n)])
                k += 1
            tables[t] = names
            off = lorom(STRING_TABLES + t * 3)
            data[off:off + 3] = a.to_bytes(3, 'little')
            for name in names:
                data[lorom(a):lorom(a) + len(name) + 1] = bytes([len(name), *name])
                a += len(name) + 1
        assert a == end
    return bytes(data), tables


def rebuild(data, manifest, mb=None):
    writes = [(patch_at(w['at'])[0], bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None,
               w['note']) for w in manifest['writes']]
    size = manifest.get('rom_size', mb)
    return build(data, [(manifest['name'], size, writes)], size)[0]


class NameWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.tables = source_fixture()

    def test_read_and_unchanged(self):
        self.assertEqual(read_tables(self.data), self.tables)
        self.assertEqual(sum(len(t['names']) for t in export(self.data)['tables']), sum(COUNTS.values()))
        manifest = patch(self.data, {'format': FORMAT, 'tables': []})
        self.assertEqual(manifest['writes'], [])
        self.assertNotIn('rom_size', manifest)

    def test_length_change_in_place(self):
        grow = self.tables[4][0] + [1, 2, 3]
        doc = {'format': FORMAT, 'tables': [{'table': 4, 'names': [{'id': 0, 'bytes': grow}]},
                                            {'table': 5, 'names': [{'id': 1, 'bytes': self.tables[5][1][:-3]}]}]}
        tables = overrides(self.tables, doc)
        manifest = compile_tables(self.data, tables)
        rebuilt = rebuild(self.data, manifest)
        self.assertEqual(decoded_tables(rebuilt), tables)
        changed = {w['note'] for w in manifest['writes']}
        self.assertEqual(changed, {'이름 문자열 표', '이름 표 5 포인터'})
        allowed = set(range(0x7FC0, 0x8000))
        for w in manifest['writes']:
            start = patch_at(w['at'])[0]
            allowed.update(range(start, start + len(bytes.fromhex(w['hex']))))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.data, rebuilt))))

    def test_in_place_overflow(self):
        doc = {'format': FORMAT, 'tables': [{'table': 3, 'names': [{'id': 0, 'bytes': self.tables[3][0] + [9]}]}]}
        with self.assertRaisesRegex(ValueError, '넘침'):
            patch(self.data, doc)
        manifest = patch(self.data, doc, '3C:8000')
        self.assertEqual(manifest['rom_size'], 2)
        self.assertEqual(decoded_tables(rebuild(self.data, manifest))[3][0], self.tables[3][0] + [9])

    def test_relocate_keeps_each_table_in_one_bank(self):
        for at in ('3C:8000', '3C:FF00', '3F:F000'):
            with self.subTest(at=at):
                manifest = patch(self.data, {'format': FORMAT, 'tables': []}, at)
                rebuilt = rebuild(self.data, manifest)
                self.assertEqual(decoded_tables(rebuilt), self.tables)
                for w in manifest['writes']:
                    addr = patch_at(w['at'])[0]
                    self.assertLessEqual(addr % 0x8000 + len(bytes.fromhex(w['hex'])), 0x8000)
                pointers = [w for w in manifest['writes'] if '포인터' in w['note']]
                self.assertEqual(len(pointers), len(TABLES))
        with self.assertRaisesRegex(ValueError, '7D'):
            patch(self.data, {'format': FORMAT, 'tables': []}, '7D:F000')
        with self.assertRaises(ValueError):
            patch(self.data + bytes(0x80000), {'format': FORMAT, 'tables': []}, '3C:8000')

    def test_append_after_last_id(self):
        new = [{'id': COUNTS[3], 'bytes': [1, 2]}, {'id': COUNTS[3] + 1, 'bytes': [3]}]
        doc = {'format': FORMAT, 'tables': [{'table': 3, 'names': new}]}
        with self.assertRaises(ValueError):
            patch(self.data, doc, '3C:8000')
        manifest = patch(self.data, doc, '3C:8000', append=True)
        counts = {**COUNTS, 3: COUNTS[3] + 2}
        decoded = decoded_tables(rebuild(self.data, manifest), counts)
        self.assertEqual(decoded[3][-2:], [[1, 2], [3]])
        self.assertEqual(decoded[3][:-2], self.tables[3])
        for bad in ([{'id': COUNTS[3] + 1, 'bytes': [1]}], [new[0], new[0]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                patch(self.data, {'format': FORMAT, 'tables': [{'table': 3, 'names': bad}]}, '3C:8000', append=True)
        with self.assertRaisesRegex(ValueError, '넘침'):
            patch(self.data, doc, append=True)

    def test_bad_input(self):
        for raw in (None, [0] * (MAX_NAME + 1), [256], [-1], [True], [1.0], '01'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                valid_name(raw)
        self.assertEqual(valid_name([]), [])
        self.assertEqual(len(valid_name([1] * 24)), MAX_NAME)
        full = {t: list(names) for t, names in self.tables.items()}
        full[4] = full[4] + [[1]] * (256 - len(full[4]))
        with self.assertRaises(ValueError):
            overrides(full, {'format': FORMAT, 'tables': [{'table': 4, 'names': [{'id': 256, 'bytes': [1]}]}]}, True)
        self.assertEqual(len(overrides(self.tables, {'format': FORMAT, 'tables': [
            {'table': 4, 'names': [{'id': COUNTS[4], 'bytes': [1]}]}]}, True)[4]), COUNTS[4] + 1)
        cases = [None, {}, {'format': FORMAT}, {'format': FORMAT, 'tables': None}, {'format': 'x', 'tables': []},
                 {'format': FORMAT, 'tables': [], 'x': 1}, {'format': FORMAT, 'tables': [None]}]
        for t in (7, 8, 9, 12, -1, True, '4'):
            cases.append({'format': FORMAT, 'tables': [{'table': t, 'names': []}]})
        cases.append({'format': FORMAT, 'tables': [{'table': 4, 'names': []}] * 2})
        cases.append({'format': FORMAT, 'tables': [{'table': 4}]})
        for i in (-1, COUNTS[4], True):
            cases.append({'format': FORMAT, 'tables': [{'table': 4, 'names': [{'id': i, 'bytes': []}]}]})
        cases.append({'format': FORMAT, 'tables': [{'table': 4, 'names': [{'id': 0, 'bytes': []}] * 2}]})
        cases.append({'format': FORMAT, 'tables': [{'table': 4, 'names': [{'id': 0, 'bytes': [], 'x': 1}]}]})
        for doc in cases:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                overrides(self.tables, doc)
        for at in ('2F:8000', '7E:8000', '3C:7FFF', '3C', None):
            with self.subTest(at=at), self.assertRaises(ValueError):
                parse_at(at)
        with self.assertRaises(ValueError):
            read_tables(bytes(0x180000))


if __name__ == '__main__':
    unittest.main()
