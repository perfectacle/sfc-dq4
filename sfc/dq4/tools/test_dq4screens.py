import contextlib
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import dq4screens as sc


def picture(w=32, h=24, seed=0):
    return np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)


class TileTests(unittest.TestCase):
    def test_tiles_and_masks(self):
        img = picture()
        tiles = sc.tile_hashes(img)
        self.assertEqual(len(tiles), 4 * 3)
        changed = img.copy()
        changed[9, 17] ^= 1                      # 칸 (2, 1)
        diff = [i for i, (a, b) in enumerate(zip(tiles, sc.tile_hashes(changed))) if a != b]
        self.assertEqual(diff, [1 * 4 + 2])
        # 칸 하나를 다 가리면 None, 일부만 가리면 가린 픽셀을 0 으로 지우고 해시
        masks = [[16, 8, 8, 8], [0, 0, 4, 4]]
        m = sc.tile_hashes(img, masks)
        self.assertIsNone(m[1 * 4 + 2])
        self.assertNotEqual(m[0], tiles[0])
        self.assertEqual(sc.tile_hashes(changed, masks), m)

    def test_read_rgb(self):
        img = picture(5, 3)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'screen-00001.rgb'
            p.write_bytes(struct.pack('<II', 5, 3) + img.tobytes())
            self.assertTrue((sc.read_rgb(p) == img).all())
            p.write_bytes(struct.pack('<II', 5, 4) + img.tobytes())
            with self.assertRaises(ValueError):
                sc.read_rgb(p)


class MaskTests(unittest.TestCase):
    def test_masks_must_lie_inside_the_screen(self):
        sc.check_masks([[0, 0, 32, 24], [8, 8, 1, 1]], 32, 24)
        for bad in ([[0, 0, 33, 24]], [[-1, 0, 4, 4]], [[0, 0, 0, 4]], [[0, 20, 4, 5]], [[1, 2, 3]]):
            with self.assertRaises(ValueError, msg=bad):
                sc.check_masks(bad, 32, 24)
        with self.assertRaises(ValueError):
            sc.entry('s', 'mesence', picture(), [[30, 0, 8, 8]])


class CompareTests(unittest.TestCase):
    def test_tolerance_masks_and_size(self):
        img = picture()
        want = sc.entry('s', 'mesence', img)
        self.assertEqual(sc.compare(img, want)['status'], 'passed')
        changed = img.copy()
        changed[1, 1] ^= 1
        changed[20, 30] ^= 1
        r = sc.compare(changed, want)
        self.assertEqual((r['status'], sorted(r['tiles'])), ('failed', [(0, 0), (3, 2)]))
        self.assertEqual(sc.compare(changed, {**want, 'tolerance': 2}, tolerance=2)['status'], 'passed')
        # 가림이 기준과 같으면 가린 곳의 차이는 보지 않는다
        masks = [[0, 0, 8, 8], [24, 16, 8, 8]]
        masked_want = sc.entry('s', 'mesence', img, masks)
        self.assertEqual(sc.compare(changed, masked_want, masks)['status'], 'passed')
        # 가림·허용치가 기준과 다르면 실패(기준을 다시 만들 것)
        r = sc.compare(img, want, masks)
        self.assertIn('가림', r['problems'][0])
        r = sc.compare(picture(40, 24), want)
        self.assertIn('화면 크기', r['problems'][0])

    def test_diff_image_marks_tiles(self):
        img = np.zeros((16, 16, 3), np.uint8)
        out = sc.diff_image(img, [(1, 0)])
        self.assertEqual(tuple(out[0, 8]), (255, 0, 0))
        self.assertEqual(tuple(out[8, 0]), (0, 0, 0))
        side = sc.diff_image(img, [(1, 0)], base=img)
        self.assertEqual(side.shape, (16, 48, 3))


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / 'screens.toml'
        self.patch = mock.patch.object(sc, 'cache_dir', return_value=self.dir / 'cache')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_write_keeps_reason_of_unchanged_and_detects_hand_edits(self):
        a, b = picture(seed=1), picture(seed=2)
        sc.write_baselines([('a', 'mesence', a, (), 0), ('b', 'bsnes', b, (), 0)], '처음', self.path)
        self.assertTrue((self.dir / 'cache' / f'{sc.digest(a)}.png').exists())
        b2 = b.copy()
        b2[0, 0] ^= 1
        got = sc.write_baselines([('a', 'mesence', a, (), 0), ('b', 'bsnes', b2, (), 0)], '타일 고침', self.path)
        self.assertEqual(got[('a', 'mesence')]['reason'], '처음')
        self.assertEqual(got[('b', 'bsnes')]['reason'], '타일 고침')
        loaded = sc.load_baselines(self.path)
        self.assertEqual(sc.compare(b2, loaded[('b', 'bsnes')])['status'], 'passed')
        with self.assertRaises(ValueError):
            sc.write_baselines([('a', 'mesence', a, (), 0)], '  ', self.path)
        text = self.path.read_text(encoding='utf-8')
        # 칸 해시나 까닭을 손으로 고치면 표지가 맞지 않는다
        tiles = loaded[('a', 'mesence')]['tiles']
        self.path.write_text(text.replace(tiles, sc.pack_tiles(sc.tile_hashes(b))), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'check'):
            sc.load_baselines(self.path)
        self.path.write_text(text.replace('reason = "처음"', 'reason = "바꿈"'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'check'):
            sc.load_baselines(self.path)
        self.path.write_text(text.replace('reason = "처음"', 'reason = ""'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'reason'):
            sc.load_baselines(self.path)

    def test_write_recovers_a_hand_edited_file(self):
        """손으로 고친 기준은 검사에서는 멈추지만, 다시 쓰면 고친 항목을 빼고 새로 쓴다(--write-screens 로 되돌릴 수 있음)."""
        a, b = picture(seed=4), picture(seed=5)
        sc.write_baselines([('a', 'mesence', a, (), 0), ('b', 'mesence', b, (), 0)], '처음', self.path)
        text = self.path.read_text(encoding='utf-8')
        self.path.write_text(text.replace('reason = "처음"', 'reason = "손"'), encoding='utf-8')
        with self.assertRaises(ValueError):
            sc.load_baselines(self.path)
        got = sc.write_baselines([('a', 'mesence', a, (), 0)], '되돌림', self.path)
        self.assertEqual(set(got), {('a', 'mesence')})       # 손댄 b 는 빠져 다시 써야 한다
        self.assertEqual(got[('a', 'mesence')]['reason'], '되돌림')
        self.assertEqual(set(sc.load_baselines(self.path)), {('a', 'mesence')})

    def test_check_screen_writes_diff_with_cached_baseline(self):
        a = picture(seed=3)
        sc.write_baselines([('a', 'mesence', a, (), 0)], '처음', self.path)
        changed = a.copy()
        changed[3, 3] ^= 1
        r = sc.check_screen(changed, 'a', 'mesence', self.dir / 'out', baselines=sc.load_baselines(self.path))
        self.assertEqual(r['status'], 'failed')
        from PIL import Image
        with Image.open(r['diff']) as im:
            self.assertEqual(im.size, (32 * 3, 24))
        r = sc.check_screen(a, 'missing', 'mesence', self.dir / 'out', baselines={})
        self.assertIn('기준 없음', r['problems'][0])


class CheckScriptTests(unittest.TestCase):
    def test_unknown_scene_is_an_error(self):
        import dq4screencheck as c
        with self.assertRaisesRegex(ValueError, '모르는 장면'):
            c.scenes_for({'titel'}, False)
        m, lib = c.scenes_for({'title'}, False)
        self.assertEqual(([s[0] for s in m], [s[0] for s in lib]), (['title'], ['title']))

    def test_main_writes_over_a_hand_edited_file_and_needs_every_scene(self):
        """--write-screens 는 손으로 고친 기준 파일이 있어도 다시 쓴다. 장면이 모자라게 찍히면 통과가 아니다."""
        import dq4screencheck as c
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            base = d / 'screens.toml'
            base.write_text('[[screen]]\nscene = "title"\nemulator = "mesence"\nreason = "손"\ncheck = "x"\n',
                            encoding='utf-8')
            rom = d / 'r.sfc'
            rom.write_bytes(b'rom')
            shots = {}

            def screen(name):
                return shots.setdefault(name, picture(seed=len(shots) + 10))
            argv = ['dq4screencheck.py', '--rom', str(rom), '--out', str(d / 'out')]
            with mock.patch.object(sc, 'BASELINES', base), mock.patch.object(sc, 'cache_dir', return_value=d / 'cache'), \
                    mock.patch.dict('os.environ', {'MESENCE': '/x/Mesen'}), \
                    mock.patch.object(c, 'make_states', return_value={'start': d / 's', 'shop': d / 'h'}), \
                    mock.patch.object(c, 'mesen_screen', side_effect=lambda m, r, dest, *a: screen(dest.name)), \
                    mock.patch.object(c, 'libretro_screen', side_effect=lambda core, r, dest, f: screen(dest.name)), \
                    mock.patch.object(c, 'verify_args', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.object(sys, 'argv', argv + ['--write-screens', '다시 씀']):
                    self.assertEqual(c.main(), 0)
                self.assertEqual(len(sc.load_baselines(base)), 6)
                with mock.patch.object(sys, 'argv', argv):
                    self.assertEqual(c.main(), 0)
                with mock.patch.object(sys, 'argv', argv), mock.patch.object(c, 'verify_args', return_value=['--x=1']):
                    self.assertEqual(c.main(), 1)
                with mock.patch.object(sys, 'argv', argv), mock.patch.object(c, 'LIBRETRO_SCENES', ()), \
                        mock.patch.object(c, 'scenes_for', return_value=([], [])):
                    self.assertEqual(c.main(), 1)



class ShopHoldTests(unittest.TestCase):
    def test_shop_state_holds_every_person_slot(self):
        """가게 출발 상태의 순간이동은 인물 슬롯 08~1F 의 걸음 간격을 모두 0 으로 묶는다(떠도는 마을 사람이 화면을 흔듦)."""
        import dq4screencheck as c
        held = dict(p.split('=') for p in c.SHOP_HOLD.split(';'))
        self.assertEqual(held, {f'7E{0x3300 + s:04X}': '00' for s in range(0x08, 0x20)})

if __name__ == '__main__':
    unittest.main()
