"""SFC serialization contracts independent of the environment drawings."""

import unittest

from dq4environment import decode_image, encode_image, indexed_canvas


class EnvironmentEncodingTests(unittest.TestCase):
    def setUp(self):
        self.palette = [(0, 0, 0)] * 128
        for bank in range(1, 8):
            for local in range(1, 16):
                value = local * 2
                color = (value << 3) | (value >> 2)
                self.palette[bank * 16 + local] = (color, color, color)

    def image(self, size=(8, 8)):
        return indexed_canvas(size, self.palette)

    def test_known_planar_vector_and_blank_padding(self):
        image = self.image()
        for x, local in enumerate((1, 2, 4, 8)):
            image.putpixel((x, 0), 16 + local)
        data, info = encode_image(image, self.palette)
        expected = bytearray(32)
        expected[0], expected[1], expected[16], expected[17] = 128, 64, 32, 16
        self.assertEqual(data["chr"], bytes(32) + bytes(expected))
        self.assertEqual(data["map"][:2], (1 | 1 << 10).to_bytes(2, "little"))
        self.assertEqual(data["map"][2:], bytes(2046))
        self.assertEqual(info["rgb_roundtrip_differences"], 0)

    def test_bank_selection_and_deduplication(self):
        image = self.image((16, 8))
        image.paste(17, (0, 0, 8, 8))
        image.paste(113, (8, 0, 16, 8))
        data, info = encode_image(image, self.palette)
        self.assertEqual(info["unique_tiles"], 2)
        self.assertEqual(int.from_bytes(data["map"][2:4], "little"), 1 | 7 << 10)
        self.assertEqual(decode_image(data["chr"], data["map"], data["pal"], image.size).tobytes(),
                         image.convert("RGB").tobytes())

    def test_mixed_bank_is_rejected(self):
        image = self.image()
        image.putpixel((0, 0), 17)
        image.putpixel((1, 0), 33)
        with self.assertRaisesRegex(ValueError, "mixed palette"):
            encode_image(image, self.palette)

    def test_reserved_indices_are_rejected(self):
        for index in (1, 15, 16, 32, 128, 255):
            with self.subTest(index=index):
                image = self.image()
                image.putpixel((0, 0), index)
                with self.assertRaisesRegex(ValueError, "reserved palette"):
                    encode_image(image, self.palette)

    def test_palette_precision_and_mismatch_are_rejected(self):
        palette = self.palette.copy()
        palette[17] = (1, 2, 3)
        with self.assertRaisesRegex(ValueError, "expanded BGR555"):
            encode_image(self.image(), palette)
        palette = self.palette.copy()
        palette[17] = (255, 255, 255)
        with self.assertRaisesRegex(ValueError, "does not match"):
            encode_image(self.image(), palette)

    def test_image_bounds_are_rejected(self):
        for size in ((7, 8), (264, 8), (8, 264)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                encode_image(self.image(size), self.palette)

    def test_decoder_rejects_missing_chr(self):
        data, _ = encode_image(self.image(), self.palette)
        tilemap = (1023).to_bytes(2, "little") + data["map"][2:]
        with self.assertRaisesRegex(ValueError, "beyond CHR"):
            decode_image(data["chr"], tilemap, data["pal"], (8, 8))


if __name__ == "__main__":
    unittest.main()
