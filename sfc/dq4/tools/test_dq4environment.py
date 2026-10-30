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


class DoorBankTests(unittest.TestCase):
    """Object entries after the library in the door bank, without a ROM."""

    def code(self, entries):
        import dq4environmentrom as rom
        n = len(rom.MAPS)
        return rom.engine_code(10, (0, 1, 2, 3), [rom.PALETTE_AT] * n, entries, [False] * n, [False] * n)

    def entries(self, objects_per_map):
        import dq4environmentrom as rom
        found = [[[2, 2 * k + 1, rom.DOOR_KIND, 0] for k in range(objects_per_map)] if i % 2 else []
                 for i in range(len(rom.MAPS))]
        return [rom.object_entries(f) for f in found]

    def objects_table(self, lib):
        """Words of the objects table, found through obj's LDA long,X; STA $01,S."""
        import dq4environmentrom as rom
        at = lib.index(bytes((0x83, 0x01))) - 4
        self.assertEqual(lib[at], 0xBF)
        table = int.from_bytes(lib[at + 1:at + 4], "little")
        self.assertEqual(table >> 16, rom.LIB_AT >> 16)
        start = table - rom.LIB_AT
        return [int.from_bytes(lib[start + 2 * i:start + 2 * i + 2], "little") for i in range(len(rom.MAPS))]

    def test_entries_sit_in_the_door_bank_reachable_from_d2fc(self):
        import dq4environmentrom as rom
        entries = self.entries(3)
        lib, _, _ = self.code(entries)
        for offset, data in zip(self.objects_table(lib), entries):
            addr = (rom.OBJECT_TABLE + offset) & 0xFFFF
            self.assertGreaterEqual(addr, rom.OBJECT_TABLE & 0xFFFF)
            self.assertLess(addr + max(len(data), 1), rom.DOOR_TABLES[0] + 1)
            self.assertEqual(lib[addr - (rom.LIB_AT & 0xFFFF):][:max(len(data), 1)], data or b"\x80")

    def test_door_tables_copy_bank_01_fd97_to_the_door_bank(self):
        import dq4environmentrom as rom
        dq5 = bytes(i * 7 & 0xFF for i in range(0x20000))
        data = rom.door_tables(dq5)
        self.assertEqual(len(data), 288)
        self.assertEqual(data, dq5[0xFD97:0xFEB7])
        self.assertEqual(rom.DOOR_BANK, rom.BLOCK_BANK)
        self.assertEqual(rom.DOOR_BANK, rom.LIB_AT >> 16)
        self.assertEqual(rom.DOOR_BANK << 16 | rom.DOOR_TABLES[0], 0x3DFD97)

    def test_built_rom_copy_check(self):
        import dq4environmentrom as rom
        import dq4groupbuild
        built = bytearray(0x200000)
        built[0xFD97:0xFEB7] = bytes(i & 0xFF for i in range(288))
        at = rom.DOOR_BANK * 0x8000 + 0x7D97
        built[at:at + 288] = built[0xFD97:0xFEB7]
        dq4groupbuild.check_door_copy(bytes(built), 0x3B)
        with self.assertRaisesRegex(ValueError, "is the dq4 door bank"):
            dq4groupbuild.check_door_copy(bytes(built), rom.DOOR_BANK)
        built[at + 0x20] ^= 1
        with self.assertRaisesRegex(ValueError, f"{rom.DOOR_BANK:02X}:FDB7 differs from 01:FDB7"):
            dq4groupbuild.check_door_copy(bytes(built), 0x3B)

    def test_obj_sets_the_data_bank_after_the_hit(self):
        import dq4environmentrom as rom
        lib, _, _ = self.code(self.entries(1))
        # STA $01,S; SEP #$20; LDA #bank; PHA; PLB, then the common exit and the replaced LDX #$0009.
        tail = bytes((0x83, 0x01, 0xE2, 0x20, 0xA9, rom.DOOR_BANK, 0x48, 0xAB, *rom._LEAVE, 0xA2, 0x09, 0x00, 0x6B))
        self.assertIn(tail, lib)
        self.assertTrue(0x30 <= rom.DOOR_BANK <= 0x3F)

    def test_bank_01_tail_does_not_grow_with_entries(self):
        import dq4environmentrom as rom
        _, few, _ = self.code(self.entries(1))
        _, many, _ = self.code(self.entries(20))
        self.assertEqual(len(few), len(many))
        self.assertLessEqual(rom.HOOK_AT + len(many), rom.HOOK_END)

    def test_overflow_into_the_table_copy_is_rejected(self):
        import dq4environmentrom as rom
        free = rom.DOOR_TABLES[0] - (rom.LIB_AT & 0xFFFF) - len(self.code(self.entries(0))[0])
        per_map = free // (5 * (len(rom.MAPS) // 2)) + 1
        with self.assertRaisesRegex(ValueError, "overflow into the bank-01 table copy"):
            self.code(self.entries(per_map))


if __name__ == "__main__":
    unittest.main()
