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
        # the blocks of FC kinds 0-7 get terrains 0-7 in reverse, every other block terrain D. Each rate is three
        # quarters of the FC factor (dq4balance).
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
                self.assertEqual((new[7 - k], new[enc.TERRAINS + 7 - k]),
                                 ((3 * (0x10 + k) + 2) // 4, (3 * (0x20 + k) + 2) // 4))
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
        # A DQ5 step is half an FC step. FC base 10 (caves) and 14 (tower) fight every 19.3 and 16.4 steps, that is
        # 38.6 and 32.7 cells; at the indoor rate 7 coefficient 50 fights every 40.4 cells and 80 every 31.6.
        self.assertAlmostEqual(enc.fc_steps(self.prg, 0x10), 19.32, places=2)
        self.assertAlmostEqual(enc.fc_steps(self.prg, 0x14), 16.37, places=2)
        self.assertAlmostEqual(enc.dq5_steps(0x50, 7), 40.44, places=2)
        self.assertAlmostEqual(enc.dq5_steps(0x80, 7), 31.64, places=2)
        want = {0x40: 4, 0x41: 4, 0x42: 7, 0x43: 7}
        for z in self.dungeon:
            self.assertEqual(self.report[f"{z:02X}"]["rate_index"], want[z])

    def test_field_rate(self):
        import dq4encounter
        # Base 16 on grass (factor 0B by day) fights every 25.5 FC steps, 51.1 cells; with the terrain rate at 0B,
        # coefficient 10 fights every 55.4 cells and 40 (4 x base, the old pick) every 29.0.
        self.assertAlmostEqual(2 * enc.fc_steps(self.prg, 0x10, 0x0B), 51.07, places=2)
        self.assertAlmostEqual(enc.dq5_steps(0x10, 0x0B), 55.40, places=2)
        self.assertAlmostEqual(enc.dq5_steps(0x40, 0x0B), 29.03, places=2)
        # Land zones by base 16, 20, 24, 28 take coefficients 10, 16, 2B, 2B; the sea zones (zone 00, base 16, sea
        # factor 04 / 05) 16.
        want = {0x10: 0, 0x14: 1, 0x18: 2, 0x1C: 2}
        for base, index in want.items():
            self.assertEqual(enc.field_rate_index(self.prg, self.dq5, base), index)
        for z in ("04", "05", "06", "09", "07", "08"):
            self.assertEqual(self.report[z]["rate_index"], want[dq4encounter.zone(self.prg, int(z, 16))["rate"]])
        sea = [r["rate_index"] for r in self.progress["encounters"] if r["index"] in enc.SEA_AREAS]
        self.assertEqual(sea, [1] * len(enc.SEA_AREAS))

    def test_dq5_chance(self):
        # Measured at 23:E8B7 with coefficient 40 on grass (Y 0B) and hill (1A) for $1A9A as given.
        got = {(0x0B, s): c for s, c in ((7, 2), (9, 5), (11, 7), (22, 7), (23, 0x10), (45, 0x10), (46, 0x2C))}
        got |= {(0x1A, s): c for s, c in ((5, 1), (14, 0x27), (24, 0x68))}
        for (rate, s), c in got.items():
            self.assertEqual(enc.dq5_chance(0x40, rate, s), c, (rate, s))

    def test_tower_formations(self):
        # FC zones 42·43 slot 12: formations 00 and 01 as DQ5 fixed groups 0 and 1, the other zones none.
        self.assertEqual(enc.dungeon_fixed(self.prg, self.dungeon), {0x00: 0, 0x01: 1})
        self.assertEqual(self.report["42"]["fixed"]["group"], 0)
        self.assertEqual(self.report["43"]["fixed"]["group"], 1)
        self.assertTrue(self.report["42"]["fixed"]["weight"])
        self.assertEqual(self.report["40"]["fixed"]["weight"], 0)
        groups = {g["index"]: g["members"] for g in self.grids["fixed_groups"]}
        self.assertEqual([m["count_code"] for m in groups[0]], [0, 0, 0])
        self.assertEqual([m["count_code"] for m in groups[1]], [0, 0, 1])
        self.assertNotIn(12, self.report["42"]["dropped_slots"])

    def test_castle_zone(self):
        # FC zone 04 around バトランド: level 1, base rate 16 -> coefficient 10, スライム·バブルスライム kept.
        rec = next(r for r in self.progress["encounters"] if r["index"] == self.report["04"]["zone"])
        self.assertEqual(rec["level"], 1)
        self.assertEqual(rec["rate_index"], 0)
        self.assertIn(0x00, self.report["04"]["monsters"])
        self.assertIn(0x09, self.report["04"]["monsters"])
        grid0 = self.grids["field_grids"][0]["rows"]
        self.assertEqual(grid0[2][10], self.report["04"]["zone"])

    def test_terrain_rates_are_fc_factors(self):
        w = enc.terrain_rates(self.prg, self.dq5)
        new = bytes.fromhex(w["hex"])
        # DQ5 grass (terrain 6) and hill (2): FC grass 0B / 0F, hill 1A / 20, day / night, three quarters each.
        self.assertEqual((new[6], new[enc.TERRAINS + 6]), (8, 11))
        self.assertEqual((new[2], new[enc.TERRAINS + 2]), (20, 24))
        self.assertEqual(new[0x0C], 0)


if __name__ == "__main__":
    unittest.main()
