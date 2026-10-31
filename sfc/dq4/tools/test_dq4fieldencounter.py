"""Without a ROM, the grid row layout; with rom/dq4.nes and rom/dq5.sfc, the zone records, grids and terrain
rates of the FC field zones."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldencounter as enc  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4, DQ5 = ROOT / "rom" / "dq4.nes", ROOT / "rom" / "dq5.sfc"


class GridTest(unittest.TestCase):
    def test_world0_rows_past_grid0_read_grid1(self):
        # 01:854F does not clamp the row: with $1948 = 0, row r >= 7 is grid 1's row r - 7.
        _, rows0, src0 = enc.GRIDS[0]
        _, _, src1 = enc.GRIDS[1]
        self.assertEqual(src0 + src1[:16 - rows0], list(range(16)))
        _, _, src2 = enc.GRIDS[2]
        self.assertEqual(src2[:16], list(range(16)))

    def test_grid_sizes_stay(self):
        self.assertEqual([enc.GRIDS[i][1] for i in range(5)], [7, 17, 17, 5, 4])
        for _, count, source in enc.GRIDS.values():
            self.assertTrue(source is None or len(source) == count)


class TerrainRateTest(unittest.TestCase):
    def test_terrain_rates_are_fc_factors(self):
        # Made-up FC factors, kind k day 10 + k / night 20 + k, and a made-up DQ5 terrain of each borrowed block:
        # the blocks of FC kinds 0-7 get terrains 0-7 in reverse, every other block terrain D.
        from unittest import mock
        import dq4encounter
        import dq4fieldport
        prg = bytearray(0x80000)
        for k in range(enc.FC_TERRAINS):
            prg[dq4encounter.BANK * 0x4000 + (dq4encounter.TERRAIN_DAY & 0x3FFF) + k] = 0x10 + k
            prg[dq4encounter.BANK * 0x4000 + (dq4encounter.TERRAIN_NIGHT & 0x3FFF) + k] = 0x20 + k
        dq5 = bytearray(0x120000)
        o = enc._lorom(enc.TERRAIN_RATES)
        dq5[o:o + 2 * enc.TERRAINS] = b"\xEE" * (2 * enc.TERRAINS)
        terrains = {dq4fieldport.BLOCKS[k]: 7 - k for k in range(enc.FC_TERRAINS)}
        with mock.patch("dq5field.terrain", lambda rom, block: terrains.get(block, 0x0D)):
            w = enc.terrain_rates(bytes(prg), bytes(dq5))
            self.assertEqual(w["at"], "23:F1E0")
            new = bytes.fromhex(w["hex"])
            for k in range(enc.FC_TERRAINS):
                self.assertEqual((new[7 - k], new[enc.TERRAINS + 7 - k]), (0x10 + k, 0x20 + k))
            self.assertEqual((new[0x0D], new[enc.TERRAINS + 0x0D]), (0, 0))   # only kinds 8 and up
            self.assertEqual(new[0x0A], 0xEE)                                  # no kind borrows it
            terrains[dq4fieldport.BLOCKS[1]] = terrains[dq4fieldport.BLOCKS[2]]
            with self.assertRaises(ValueError):
                enc.terrain_rates(bytes(prg), bytes(dq5))


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), "rom/dq4.nes and rom/dq5.sfc")
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        import tempfile
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "enc.json"
            subprocess.run([sys.executable, str(enc.DQ5_TOOLS / "dq5encounterwrite.py"), str(DQ5), "dump", "-o",
                            str(path)], check=True, capture_output=True)
            cls.orig = json.loads(path.read_text(encoding="utf-8"))
        cls.dungeon = (0x40, 0x41, 0x42, 0x43)
        cls.progress, cls.grids, cls.report = enc.docs(cls.prg, cls.dq5, cls.orig, cls.dungeon)

    def test_every_monster_has_a_placeholder(self):
        import dq4encounter
        for z in (*enc.fc_zones(self.prg), *self.dungeon):
            slots = dq4encounter.zone(self.prg, z)["slots"]
            for i in (*enc.GROUP_SLOTS, *enc.SOLO_SLOTS, *enc.ONE_SLOTS):
                if slots[i] != 0xFF:
                    self.assertIn(slots[i], enc.MONSTERS, f"zone {z:02X} slot {i}")

    def test_zones_take_field_only_dq5_zones(self):
        used = {a for m in self.orig["maps"] for a in m["areas"]}
        areas = [r["index"] for r in self.progress["encounters"]]
        self.assertEqual(len(areas), len(set(areas)))
        self.assertFalse(set(areas) & used)
        self.assertEqual(areas[-4:], list(enc.SEA_AREAS))

    def test_dungeon_zones_are_out_of_the_grids(self):
        dungeon = {self.report[f"{z:02X}"]["zone"] for z in self.dungeon}
        self.assertEqual(len(dungeon), len(self.dungeon))
        in_grids = {a for g in self.grids["field_grids"] for row in g["rows"] for a in row}
        self.assertFalse(dungeon & in_grids)

    def test_dungeon_rate(self):
        # FC base 10 and 14 in a dungeon are 15/256 and 18.75/256 a step; DQ5's highest coefficient 80 x 7 >> 6
        # is 14/256, the nearest.
        for z in self.dungeon:
            self.assertEqual(self.report[f"{z:02X}"]["rate_index"], 7)
        self.assertEqual(enc.rate_index(self.dq5, 0x10), 3)

    def test_castle_zone(self):
        # FC zone 04 around バトランド: level 1, base rate 16 -> coefficient 40, スライム·バブルスライム kept.
        rec = next(r for r in self.progress["encounters"] if r["index"] == self.report["04"]["zone"])
        self.assertEqual(rec["level"], 1)
        self.assertEqual(rec["rate_index"], 3)
        self.assertIn(0x00, self.report["04"]["monsters"])
        self.assertIn(0x09, self.report["04"]["monsters"])
        grid0 = self.grids["field_grids"][0]["rows"]
        self.assertEqual(grid0[2][10], self.report["04"]["zone"])

    def test_terrain_rates_are_fc_factors(self):
        w = enc.terrain_rates(self.prg, self.dq5)
        new = bytes.fromhex(w["hex"])
        # DQ5 grass (terrain 6) and hill (2): FC grass 0B / 0F, hill 1A / 20, day / night.
        self.assertEqual((new[6], new[enc.TERRAINS + 6]), (0x0B, 0x0F))
        self.assertEqual((new[2], new[enc.TERRAINS + 2]), (0x1A, 0x20))
        self.assertEqual(new[0x0C], 0)


if __name__ == "__main__":
    unittest.main()
