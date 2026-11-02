import unittest

import dq4windowcheck as wc


def canvas_bytes(t, canvas):
    o = (t - wc.CANVAS.start) * 8
    return bytes(x for r in range(8) for x in (canvas[o + r], 0xFF))


class CanvasTileTest(unittest.TestCase):
    def setUp(self):
        self.canvas = bytes(range(256)) * ((len(wc.CANVAS) * 8) // 256 + 1)

    def test_message_canvas_tile_is_plane0_buffer_and_plane1_ff(self):
        t = wc.CANVAS.start + 5
        self.assertTrue(wc.canvas_tile_bytes(canvas_bytes(t, self.canvas), self.canvas, t))

    def test_name_picture_is_not_the_canvas(self):
        t = wc.CANVAS.start + 5
        art = bytearray(canvas_bytes(t, self.canvas))
        art[1] = 0x00
        self.assertFalse(wc.canvas_tile_bytes(bytes(art), self.canvas, t))

    def test_tiles_outside_the_canvas_or_without_a_dump_never_match(self):
        t = wc.CANVAS.start - 1
        self.assertFalse(wc.canvas_tile_bytes(bytes(16), self.canvas, t))
        self.assertFalse(wc.canvas_tile_bytes(canvas_bytes(wc.CANVAS.start, self.canvas), None, wc.CANVAS.start))


if __name__ == '__main__':
    unittest.main()
