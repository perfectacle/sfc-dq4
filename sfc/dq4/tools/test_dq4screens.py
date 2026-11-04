import struct
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


if __name__ == '__main__':
    unittest.main()
