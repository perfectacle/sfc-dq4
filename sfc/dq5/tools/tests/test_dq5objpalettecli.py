"""OBJ 팔레트 쓰기를 실제 롬에서: dump 왕복, 세트 팔레트 표·맵 줄 늘리기를 롬 코드로 확인하는 check, CLI 보고·오류."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5objpalette as P  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'
COLORS = [0x0421 * (i % 31) for i in range(1, 16)]


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq5objpalette.py', str(ROM), *args]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = P.main()
        return code, out.getvalue(), err.getvalue()

    def test_dump_lists_users(self):
        doc = P.dump(self.rom)
        self.assertEqual(doc['format'], P.FORMAT)
        self.assertEqual([p['palette'] for p in doc['palettes']], list(range(8)))
        self.assertEqual(len(doc['map_palettes']), 36)
        self.assertEqual(len(doc['sets']), 147)
        users = [u for p in doc['palettes'] for u in p.get('users', [])]
        self.assertEqual(len(users), 147)
        papas = next(u for u in users if u['set'] == '82')
        self.assertIn('2E', papas['gfx'])
        self.assertEqual(sum(len(u['gfx']) for u in users), sum(1 for _, s in P.pictures(self.rom) if f'{s:02X}' in {u['set'] for u in users}))
        self.assertEqual(len(P.pictures(self.rom)), S.GFX_COUNT)

    def test_check_original(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            P.check(self.rom)
        self.assertEqual(out.getvalue().strip(),
                         'OBJ 팔레트 8개, 맵 팔레트 36→36개, 세트 147개 검사 통과; 칸 목록 147세트·그림 바꾸기 169그림·'
                         '맵 367곳을 롬 코드로 확인; 쓰기 0개')

    def test_check_document_with_table_and_new_line(self):
        doc = {'format': P.FORMAT, 'palettes': [{'palette': 5, 'colors': COLORS}],
               'map_palettes': [{'index': 0, 'colors': COLORS}],
               'new_map_palettes': [{'map': '02/06', 'line': '0D', 'colors': COLORS}],
               'sets': [{'set': '84', 'palette': 5}, {'set': '00', 'palette': 1}]}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            P.check(self.rom, doc, '3B:8000')
        text = out.getvalue().strip()
        self.assertTrue(text.startswith('OBJ 팔레트 8개, 맵 팔레트 36→37개, 세트 147개 검사 통과'))
        self.assertNotIn('쓰기 0개', text)

    def test_patch_reports(self):
        with tempfile.TemporaryDirectory() as d:
            src, target = Path(d, 'doc.json'), Path(d, 'out.json')
            src.write_text(json.dumps({'format': P.FORMAT, 'palettes': [{'palette': 3, 'colors': COLORS}],
                                       'sets': [{'set': '84', 'palette': 6}]}))
            code, out, _ = self.run_main('patch', str(src), '-o', str(target), '--at', '3B:8000')
            writes = json.loads(target.read_text())['writes']
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith('OBJ 팔레트 3 를 쓰는 세트 '))
        self.assertTrue(lines[1].startswith('OBJ 팔레트 3 줄을 맵 팔레트가 덮는 맵(바꾼 색이 안 보임): '))
        self.assertTrue(lines[2].startswith('OBJ 팔레트 6: 세트 84'))
        self.assertEqual(lines[-1], f'patch → {target}')
        self.assertIn('3B:8000', [w['at'] for w in writes])

    def test_main_dump_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d, 'dump.json')
            code, out, _ = self.run_main('dump', '-o', str(target))
            self.assertEqual((code, out.strip()), (0, f'dump → {target}'))
            self.assertEqual(json.loads(target.read_text()), P.dump(self.rom))
            code, out, _ = self.run_main('check', str(target))
        self.assertEqual(code, 0)
        self.assertIn('쓰기 0개', out)

    def test_rejects(self):
        base = {'format': P.FORMAT}
        for doc, at, why in (({'new_map_palettes': [{'map': 'FE/03', 'line': '0D', 'colors': COLORS}]}, '3B:8000', '필드는'),
                             ({'new_map_palettes': [{'map': '7F/00', 'line': '0D', 'colors': COLORS}]}, '3B:8000', '롬에 없음'),
                             ({'new_map_palettes': [{'map': '2/6', 'line': '0D', 'colors': COLORS}]}, '3B:8000', 'BC/BD'),
                             ({'new_map_palettes': [{'map': '02/06', 'line': '0D', 'flag': '05', 'colors': COLORS}]},
                              '3B:8000', 'mask'),
                             ({'new_map_palettes': {}}, '3B:8000', '배열'),
                             ({'sets': {}}, None, 'sets는 배열'),
                             ({'sets': [{'set': '70', 'palette': 1}]}, None, '없거나'),
                             ({'sets': [{'set': '84', 'palette': 6}]}, '40:8000', '뱅크 00~3F'),
                             ({'sets': [{'set': '84', 'palette': 6}]}, '3B8000', 'BB:AAAA'),
                             ({'palettes': {}}, None, 'palettes는 배열'),
                             ({'map_palettes': {}}, None, 'map_palettes는 배열')):
            with self.subTest(doc=doc, at=at), self.assertRaisesRegex(ValueError, why):
                P.patch(self.rom, base | doc, at)
        self.assertEqual(P.map_rows(self.rom, []), [])
        code, _, err = self.run_main('patch', str(ROM.parent / 'none.json'), '-o', 'x.json')
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith('오류: '))


if __name__ == '__main__':
    unittest.main()
