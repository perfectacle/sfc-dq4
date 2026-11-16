"""인물 스프라이트 쓰기 CLI: 주소 인자, 세트를 PNG 로 내보내기, 원본 왕복 검사, 새 세트 문서의 빌드 확인, VRAM 보고."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dq5sprite as S  # noqa: E402
import dq5spritewrite as W  # noqa: E402
from dq5map import Rom  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


class ArgumentTests(unittest.TestCase):
    def test_address(self):
        self.assertEqual(W.address('3A:8000'), 0x3A8000)
        self.assertEqual(W.address('00:ffff'), 0x00FFFF)
        for bad, why in (('3A8000', 'BB:AAAA'), (None, 'BB:AAAA'), ('40:8000', '00~3F'), ('3A:7FFF', '00~3F')):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, why):
                W.address(bad)

    def test_hexbyte(self):
        self.assertEqual(W.hexbyte('a5', 'set'), 0xA5)
        with self.assertRaisesRegex(ValueError, 'set: 두 자리'):
            W.hexbyte('100', 'set')

    def test_image_grid_rejects_large_color_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, 'big.png')
            image = Image.new('P', W.SIMPLE_SIZE)
            image.putpalette([c for i in range(32) for c in (i * 8, i * 8, i * 8)])
            image.putdata([16] * (W.SIMPLE_SIZE[0] * W.SIMPLE_SIZE[1]))
            image.save(path)
            with self.assertRaisesRegex(ValueError, '0~15'):
                W.image_grid(path, 'simple')


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())
        cls.dir = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.dir, ignore_errors=True)
        for s in (0x00, 0x82):
            W.dump_image(cls.rom, s, cls.dir / f'{s:02X}.png')
        # 그림 1E 는 세트 00 을 쓴다. 같은 그림을 새 세트 70 으로 옮겨도 타일 수가 같아 VRAM 셈이 늘지 않는다.
        cls.doc = {'format': W.FORMAT, 'sets': [{'set': '82', 'image': '82.png', 'palette': 1}],
                   'new_sets': [{'set': '70', 'image': '00.png', 'palette': 2}], 'gfx': [{'gfx': '1E', 'set': '70'}]}
        (cls.dir / 'doc.json').write_text(json.dumps(cls.doc))

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq5spritewrite.py', str(ROM), *args]), \
                redirect_stdout(out), redirect_stderr(err):
            code = W.main()
        return code, out.getvalue(), err.getvalue()

    def test_dump_image(self):
        with Image.open(self.dir / '00.png') as simple, Image.open(self.dir / '82.png') as overlap:
            self.assertEqual((simple.mode, simple.size, overlap.size), ('P', W.SIMPLE_SIZE, W.OVERLAP_SIZE))
            self.assertLessEqual(max(simple.tobytes()), 15)
        grid = W.image_grid(self.dir / '82.png', 'overlap')
        tiles, refs = W.deduplicate(W.cell_tiles(grid, 'overlap'))
        rec = S.decode_set(self.rom, 0x82)
        self.assertEqual(W.decoded(refs, tiles, 'overlap'), W.decoded(rec['cells'], rec['tile_data'], 'overlap'))
        with self.assertRaisesRegex(ValueError, '세트 70 가 없음'):
            W.dump_image(self.rom, 0x70, self.dir / 'none.png')

    def test_check_original_and_document(self):
        out = io.StringIO()
        with redirect_stdout(out):
            W.check(self.rom, self.doc, self.dir, at=0x3A8000, workdir=self.dir / 'check')
        first, second = out.getvalue().splitlines()
        self.assertTrue(first.startswith('세트 147개, 모양 2604개 다시 인코딩 일치; 원본 문서 쓰기 0개'))
        self.assertRegex(second, r'^문서: 쓰기 \d+개, 바꾼 세트 2개·그림 연결 1개를 빌드한 롬에서 확인$')
        self.assertEqual(len(list((self.dir / 'check').glob('*.png'))), 147)

    def test_patch_new_set(self):
        manifest = W.patch(self.rom, self.doc, self.dir, at=0x3A8000)
        built = W.apply(self.rom, manifest)
        self.assertEqual(S.gfx_set(built, 0x1E), 0x70)
        new = S.decode_set(built, 0x70)
        old = S.decode_set(self.rom, 0x00)
        self.assertEqual((new['palette'], new['data']), (2, 0x3A8000))
        self.assertEqual(new['frames'], old['frames'])
        self.assertEqual(S.set_record(built, 0x82)['palette'], 1)
        notes = [w['note'] for w in manifest['writes']]
        self.assertIn('새 세트 70 레코드', notes)
        self.assertIn('세트 70 레코드 포인터', notes)

    def test_vram_report(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rows = W.vram_report(self.rom, self.doc, self.dir, top=3)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(('낮:' in line or '밤:' in line) and '남는 타일' in line for line in lines[:3]))
        self.assertTrue(lines[3].startswith(f'목록 {len(rows)}줄, 가장 큰 7E:1995 {rows[0][2]:03X}'))
        self.assertEqual(rows, sorted(rows, key=lambda r: (-r[2], -r[1], r[0][0])))

    def test_main_commands(self):
        code, out, _ = self.run_main('dump', '82', '-o', str(self.dir / 'main.png'))
        self.assertEqual((code, out.strip()), (0, f'세트 82 overlap 팔레트 {S.set_record(self.rom, 0x82)["palette"]} 타일 34 → {self.dir / "main.png"}'))
        target = self.dir / 'out' / 'patch.json'
        code, out, _ = self.run_main('patch', str(self.dir / 'doc.json'), '-o', str(target), '--at', '3A:8000')
        manifest = json.loads(target.read_text())
        self.assertEqual((code, out.strip()), (0, f'patch → {target} (쓰기 {len(manifest["writes"])}개)'))
        self.assertEqual(manifest, W.patch(self.rom, self.doc, self.dir, at=0x3A8000))
        code, out, _ = self.run_main('vram', '--top', '1')
        self.assertEqual((code, len(out.splitlines())), (0, 2))
        with mock.patch.object(W, 'check') as check:
            code, _, _ = self.run_main('check', str(self.dir / 'doc.json'), '--at', '3A:8000', '--sets-at', '3B:8000')
        self.assertEqual(code, 0)
        self.assertEqual(check.call_args.args[2:], (self.dir, 0x3A8000))
        self.assertEqual(check.call_args.kwargs, {'records_at': 0x1FFE30, 'sets_at': 0x3B8000})

    def test_main_errors(self):
        code, _, err = self.run_main('patch', str(self.dir / 'doc.json'), '-o', str(self.dir / 'x.json'), '--records-at', '1E:8000')
        self.assertEqual((code, err.strip()), (1, '오류: --records-at 은 1F:FE30~1F:FFFF 안이어야 함'))
        code, _, err = self.run_main('patch', str(self.dir / 'doc.json'), '-o', str(self.dir / 'x.json'))
        self.assertEqual(code, 1)
        self.assertIn('--at 이 필요함', err)
        code, _, err = self.run_main('dump', 'zz', '-o', str(self.dir / 'x.png'))
        self.assertEqual((code, err.strip()), (1, '오류: set: 두 자리 16진 문자열이어야 함'))


if __name__ == '__main__':
    unittest.main()
