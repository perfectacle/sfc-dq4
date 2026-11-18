"""ndsgfx 의 인덱스 PNG(`indexed_image`)를 가짜 TextureObject 로 검사한다(롬 없음)."""
import unittest

import numpy as np

import ndsgfx as G


def texture(fmt, w, h, data, pal):
    return dict(fmt=fmt, width=w, height=h, hmax=h, data=bytes(data), pal=pal, extra=[], end=0)


class IndexedImageTest(unittest.TestCase):
    PAL = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]

    def test_4bpp_keeps_indices_and_marks_index0_transparent(self):
        # 4bpp 는 바이트의 낮은 니블이 먼저다.
        t = texture(3, 4, 1, [0x10, 0x32], self.PAL)
        img = G.indexed_image(t)
        self.assertEqual(img.mode, "P")
        self.assertEqual(list(np.asarray(img)[0]), [0, 1, 2, 3])
        self.assertEqual(img.getpalette()[:12], [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255])
        self.assertEqual(img.info["transparency"][0], 0)
        self.assertEqual(np.asarray(img.convert("RGBA"))[0, :, 3].tolist(), [0, 255, 255, 255])

    def test_opaque_when_index0_is_a_color(self):
        img = G.indexed_image(texture(4, 2, 1, [0, 3], self.PAL), transparent0=False)
        self.assertNotIn("transparency", img.info)
        self.assertEqual(np.asarray(img.convert("RGBA"))[0, :, 3].tolist(), [255, 255])

    def test_a3i5_zero_alpha_goes_to_extra_transparent_entry(self):
        # 224 = 알파 7·색 0, 0 = 알파 0
        img = G.indexed_image(texture(1, 2, 1, [224, 0], [(255, 255, 255)]))
        px = np.asarray(img)[0]
        self.assertEqual(px.tolist(), [0, 1])
        self.assertEqual(np.asarray(img.convert("RGBA"))[0, :, 3].tolist(), [255, 0])

    def test_pixels_match_rgba_decoder(self):
        t = texture(4, 4, 1, [0, 1, 2, 3], self.PAL)
        a = np.asarray(G.indexed_image(t).convert("RGBA"))
        b = np.asarray(G.texture_object_image(t))
        self.assertTrue((a == b).all())


if __name__ == "__main__":
    unittest.main()
