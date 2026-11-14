"""Night colours of the replaced maps: the FC-style colour rules, which maps turn to night, and the palette hook."""

import colorsys
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4environmentnight as night  # noqa: E402
import dq4environmentrom as rom  # noqa: E402
from dq4environmentart import palette_variant  # noqa: E402


def hsv(hex_or_rgb):
    rgb = tuple(int(hex_or_rgb[i:i + 2], 16) for i in (0, 2, 4)) if isinstance(hex_or_rgb, str) else hex_or_rgb
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return h * 360, s, v


def at_night(hex_colour):
    return hsv(night.night_rgb(tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))))


class ColourRuleTests(unittest.TestCase):
    """Each kind of colour changes the way FC's night sets change it."""

    def test_warm_grey_wall_turns_teal(self):
        # 9d8e84 is a warm grey of the stone walls (saturation 0.16); FC turns its greys 00 and 10 into teal 0C and 1C.
        hue, sat, _ = at_night("9d8e84")
        self.assertTrue(170 <= hue <= 200, hue)
        self.assertGreater(sat, 0.6)

    def test_grass_turns_towards_teal_and_darker(self):
        hue, _, value = at_night("2dff39")
        self.assertTrue(150 <= hue <= 185, hue)
        self.assertLess(value, hsv("2dff39")[2] * 0.6)

    def test_cream_road_turns_olive_not_blue(self):
        # The cream road once took the white rule and went pale blue; FC's road 38 goes to olive 28.
        hue, _, value = at_night("f7f7d6")
        self.assertTrue(40 <= hue < 70, hue)
        self.assertLess(value, 0.7)

    def test_white_turns_pale_blue(self):
        hue, _, _ = at_night("ffffef")
        self.assertTrue(190 <= hue <= 215, hue)

    def test_floor_keeps_its_hue(self):
        day_hue, _, day_value = hsv("b3177f")
        hue, _, value = at_night("b3177f")
        self.assertAlmostEqual(hue, day_hue, delta=4)
        self.assertLess(value, day_value)
        self.assertGreater(value, day_value * 0.5)

    def test_water_stays_blue(self):
        day_hue, _, day_value = hsv("0042ff")
        hue, _, value = at_night("0042ff")
        self.assertAlmostEqual(hue, day_hue, delta=4)
        self.assertTrue(0.3 < value / day_value < 0.6)

    def test_flat_keeps_transparent_colours_and_other_lines(self):
        day = palette_variant("normal")
        out = night.night_flat(day)
        for line in range(16):
            first = line * 16
            self.assertEqual(out[first * 3:first * 3 + 3], day[first * 3:first * 3 + 3])
        self.assertEqual(out[:48], day[:48])
        self.assertEqual(out[128 * 3:], day[128 * 3:])
        self.assertNotEqual(out[16 * 3:128 * 3], day[16 * 3:128 * 3])

    def test_flat_colours_are_sfc_colours(self):
        out = night.night_flat(palette_variant("normal"))
        for c in out[16 * 3:128 * 3]:
            self.assertEqual(c, (c >> 3) << 3 | c >> 5)


class HookTests(unittest.TestCase):
    def test_pal_asks_dq5_night_test_and_reads_the_night_table(self):
        n = len(rom.MAPS)
        lib, _, _, table = rom.engine_code(10, (0, 1, 2, 3), [rom.PALETTE_AT] * n, [[]] * n, [False] * n,
                                           [False] * n, [0x9000] + [0] * (n - 1))
        jsl = bytes((0x22, 0x00, 0x80, 0x21))
        read = bytes((0xBF, rom.NIGHTS_AT & 0xFF, rom.NIGHTS_AT >> 8, rom.GFX_BANK))
        self.assertIn(jsl, lib)
        self.assertIn(read, lib)
        # BCC to the day read right after the JSL, so a day keeps the day palette even when the map has a night one.
        at = lib.index(jsl) + 4
        self.assertEqual(lib[at], 0x90)
        self.assertEqual(lib[at + 2:at + 6], read)
        self.assertEqual(table[:2], bytes((0x00, 0x90)))
        self.assertEqual(table[2:], bytes(2 * (n - 1)))

    def test_night_table_fits_before_the_water_frames(self):
        self.assertLessEqual((rom.GFX_BANK << 16 | rom.NIGHTS_AT) + 2 * len(rom.MAPS), rom.WATER_AT)


@unittest.skipUnless((ROOT / "rom" / "dq4.nes").is_file(), "local source ROM not present")
class FcNightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        from dq4environmentmap import dq4block
        cls.prg = ines.prg((ROOT / "rom" / "dq4.nes").read_bytes())
        cls.map = lambda cls, g, k: dq4block.Map(cls.prg, g, k)

    def test_tempe_darkens_and_the_south_cave_does_not(self):
        self.assertTrue(rom.fc_night(self.prg, self.map(0x0E, 0x00)))
        self.assertFalse(rom.fc_night(self.prg, self.map(0x39, 0x00)))

    def test_place_exceptions(self):
        # 04/01 stays day at night (0E:$BBB1 entry 11 and up); burland darkens.
        self.assertFalse(rom.fc_night(self.prg, self.map(0x04, 0x01)))
        self.assertTrue(rom.fc_night(self.prg, self.map(0x02, 0x00)))


if __name__ == "__main__":
    unittest.main()
