"""Without a ROM, the grid row layout; with rom/dq4.nes and rom/dq5.sfc, the zone records, grids and terrain
rates of the FC field zones."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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


PRG = b"synthetic-fc"
AFTER_BATTLE, TERRAIN_DAY, TERRAIN_NIGHT = 0x10, 0x100, 0x200
# 필드 지형 배수는 100, 전투 직후 배수는 255 로 두어, 기본 구역(기본율 255)은 첫 걸음에 싸운다.
RD = {**{AFTER_BATTLE + n: 255 for n in range(3)},
      **{base + k: 100 for base in (TERRAIN_DAY, TERRAIN_NIGHT) for k in range(8)}}
ZONE_ROW = {0x20: 255}
MAP_ROWS = [[0] + [3] * 15] + [[3] * 16 for _ in range(6)] + [[4 | 0x40] * 16 for _ in range(9)]


def formation_slots(formation=0xFF, **slots):
    out = [0xFF] * 14
    out[12] = formation
    for i, monster in slots.items():
        out[int(i[1:])] = monster
    return out


def weights(**w):
    out = [0] * 18
    for key, value in w.items():
        out[int(key[1:])] = value
    return out


ZONES = {
    "field": {"slots": formation_slots(0x20, s0=0x00, s1=0x0A, s5=0x04, s6=0x0C), "row": 1, "b1": 9, "rate": 255},
    "crowded": {"slots": formation_slots(s0=0x00, s5=0x04, s6=0x0C, s11=0x04), "row": 2, "b1": 3, "rate": 255},
}
WEIGHTS = {
    1: weights(w0=8, w1=4, w5=1, w6=2, w12=2, w14=1, w16=0x02),
    2: weights(w0=8, w5=1, w6=2, w11=0),
}
FORMATIONS = {0x20: [(0x00, 1, 1), (0x0A, 2, 3), (0xFF, 0, 0)]}


def fake_fc(zone_key="field", rows=None):
    return SimpleNamespace(
        AFTER_BATTLE=AFTER_BATTLE, TERRAIN_DAY=TERRAIN_DAY, TERRAIN_NIGHT=TERRAIN_NIGHT,
        rd=lambda prg, addr: RD.get(addr, 0),
        zone_map=lambda prg, field: (None, MAP_ROWS if rows is None else rows),
        zone=lambda prg, z: ZONES[zone_key],
        weights=lambda prg, row: WEIGHTS[row],
        formation=lambda prg, f: FORMATIONS[f])


def dq5_tables(coefs=(10, 10, 10, 10, 10, 255, 10, 10)):
    dq5 = bytearray(0x120000)
    at = enc._lorom(enc.RATE_COEF)
    dq5[at:at + 8] = bytes(coefs)
    # 개수 코드 0: 1~1, 1: 2~3, 2: 4~4
    for code, (low, width) in enumerate(((1, 1), (2, 2), (4, 1))):
        dq5[enc._lorom(enc.COUNT_BASE) + code] = low
        dq5[enc._lorom(enc.COUNT_WIDTH) + code] = width
    return bytes(dq5)


class PatchedFC(unittest.TestCase):
    zone_key = "field"

    def setUp(self):
        patcher = mock.patch.object(enc, "_fc", lambda prg: fake_fc(self.zone_key))
        patcher.start()
        self.addCleanup(patcher.stop)


class ZoneAssignmentTests(PatchedFC):
    ENC = {"maps": [{"areas": [1, 2]}],
           "field_grids": [{"rows": [[1, 5, 6, 81, 82, 7, 8, 9, 10, 11, 12, 13]]}]}

    def test_fc_zones_are_the_map_values_and_the_two_single_zone_fields(self):
        self.assertEqual(enc.fc_zones(PRG), [0, 3, 4, 0x34, 0x35, 0x36])

    def test_zones_take_field_only_dq5_zones_in_order(self):
        self.assertEqual(enc.zones(PRG, self.ENC), {0: 5, 3: 6, 4: 7, 0x34: 8, 0x35: 9, 0x36: 10})

    def test_too_few_dq5_zones_is_an_error(self):
        short = {"maps": [], "field_grids": [{"rows": [[5, 6, 7]]}]}
        with self.assertRaisesRegex(ValueError, "6 FC zones, 3 field-only"):
            enc.zones(PRG, short)

    def test_dungeon_zones_use_the_zones_left_over(self):
        self.assertEqual(enc.dungeon_zones(PRG, self.ENC, [0x50, 0x50, 0x51]), {0x50: 11, 0x51: 12})

    def test_too_many_dungeon_zones_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "4 FC dungeon zones, 3 DQ5 zones left"):
            enc.dungeon_zones(PRG, self.ENC, [0x50, 0x51, 0x52, 0x53])


class GridBuildTests(PatchedFC):
    def test_five_grids_follow_the_zone_map_and_sea(self):
        assign = {enc.SEA_ZONE: 100, 3: 103, 4: 104, enc.FIELD1_TOP: 135, enc.FIELD1: 134, enc.FIELD3: 136}
        out = enc.grids(PRG, assign)
        self.assertEqual([g["index"] for g in out], [0, 1, 2, 3, 4])
        grid0, grid1, grid2, grid3, grid4 = (g["rows"] for g in out)
        row0 = [100] + [103] * 15 + [100]
        self.assertEqual(grid0, [row0] + [[103] * 16 + [100]] * 6)
        self.assertEqual(grid1[:9], [[104] * 16 + [100]] * 9)
        self.assertEqual(grid1[9:16], [[104] * 16 + [100]] * 7)
        self.assertEqual(grid1[16], [100] * 17)
        self.assertEqual(grid2[:7], [row0] + [[103] * 16 + [100]] * 6)
        self.assertEqual(grid2[16], [100] * 17)
        self.assertEqual(grid3, [[135] * 17] + [[134] * 17] * 4)
        self.assertEqual(grid4, [[136] * 17] * 4)


class RateTests(PatchedFC):
    def test_mean_steps(self):
        self.assertEqual(enc._mean([256]), 1.0)
        self.assertEqual(enc._mean([0, 256]), 2.0)
        self.assertEqual(enc._mean([128, 128]), 1.0)
        self.assertEqual(enc._mean([999]), 1.0)

    def test_dq5_chance_steps_up_with_steps_since_the_last_fight(self):
        # 비율 7: n = 36. y 는 s<3 이면 7>>8, s<5 면 7>>6, s<7 이면 7>>4, s<9 면 7>>2, s<11 이면 7>>1,
        # 그 뒤 n 전까지 (7>>1)+(7>>2), 2n 전까지 7+(7>>1), 그 뒤 4x7. 계수 64 면 확률 = y.
        got = [enc.dq5_chance(64, 7, s) for s in (1, 4, 6, 8, 10, 11, 40, 100, 1000)]
        self.assertEqual(got, [0, 0, 0, 1, 3, 4, 10, 28, 28])

    def test_dq5_chance_caps_y_at_ff(self):
        # 비율 100: n = 2. s=2 는 100+50=150, s=4 는 400 → FF
        self.assertEqual(enc.dq5_chance(64, 100, 2), 150)
        self.assertEqual(enc.dq5_chance(64, 100, 4), 255)
        self.assertEqual(enc.dq5_chance(128, 100, 2), 300)

    def test_dq5_steps(self):
        self.assertEqual(enc.dq5_steps(0, 100), 0.0)
        self.assertEqual(enc.dq5_steps(128, 100), 2.0)

    def test_fc_steps(self):
        self.assertEqual(enc.fc_steps(PRG, 255), 1.0)
        self.assertEqual(enc.fc_steps(PRG, 0), 0.0)
        self.assertEqual(enc.fc_steps(PRG, 255, 100), 1.0)

    def test_dungeon_rate_picks_the_coefficient_with_the_fewest_steps(self):
        # 실내 비율 7 은 FC 의 두 걸음보다 늘 길어서, 가장 센 계수가 가장 가깝다
        dq5 = dq5_tables((10, 50, 30, 255, 40, 60, 70, 80))
        self.assertEqual(enc.dungeon_rate_index(PRG, dq5, 255), 3)

    def test_field_rate_picks_the_coefficient_matching_two_cells_per_step(self):
        self.assertEqual(enc.field_rate_index(PRG, dq5_tables(), 255), 5)

    def test_field_rate_ignores_kinds_without_a_factor(self):
        # 바다 종류(0)만 보면 배수 100 하나뿐이라 같은 결과
        self.assertEqual(enc.field_rate_index(PRG, dq5_tables(), 255, kinds=enc.SEA_KINDS), 5)


class FixedGroupTests(PatchedFC):
    def test_formations_are_numbered_in_order_and_zero_is_skipped(self):
        # 구역 0x20 의 12번 칸 편성이 0x20, 나머지는 FF
        self.assertEqual(enc.dungeon_fixed(PRG, [0x20, 0x20]), {0x20: 0})

    def test_too_many_formations_is_an_error(self):
        many = [dict(ZONES["field"], slots=formation_slots(n)) for n in range(10)]
        fc = fake_fc()
        fc.zone = lambda prg, z: many[z]
        with mock.patch.object(enc, "_fc", lambda prg: fc):
            with self.assertRaisesRegex(ValueError, "10 FC formations"):
                enc.dungeon_fixed(PRG, range(10))

    def test_members_take_placeholder_monster_and_matching_count_code(self):
        out = enc.fixed_groups(PRG, dq5_tables(), {0x20: 0})
        self.assertEqual(out, [{"index": 0, "members": [{"monster": 0x00, "count_code": 0},
                                                        {"monster": 0x09, "count_code": 1}]}])

    def test_formation_with_too_many_groups_is_an_error(self):
        with mock.patch.dict(FORMATIONS, {0x21: [(0, 1, 1)] * 4}):
            with self.assertRaisesRegex(ValueError, "4 groups"):
                enc.fixed_groups(PRG, dq5_tables(), {0x21: 0})

    def test_unknown_count_range_is_an_error(self):
        with mock.patch.dict(FORMATIONS, {0x21: [(0, 5, 6)]}):
            with self.assertRaisesRegex(ValueError, "count range"):
                enc.fixed_groups(PRG, dq5_tables(), {0x21: 0})


class RecordTests(PatchedFC):
    def test_field_record_scales_weights_and_fills_free_solo_slot(self):
        rec, dropped = enc.record(PRG, dq5_tables(), 0x01)
        by_index = {s["index"]: s for s in rec["slots"]}
        # 가중치 최대 8 → 7. 8→7, 4→round(3.5)=4, 2→round(1.75)=2, 1→round(0.875)=1
        self.assertEqual(by_index[0], {"index": 0, "weight": 7, "count_code": enc.GROUP_COUNT, "monster": 0x00})
        self.assertEqual(by_index[1], {"index": 1, "weight": 4, "count_code": enc.GROUP_COUNT, "monster": 0x09})
        self.assertEqual(by_index[5], {"index": 5, "weight": 2, "count_code": 2, "monster": 0x0B})
        self.assertEqual(by_index[6], {"index": 6, "weight": 1, "count_code": 0, "monster": 0x00})
        self.assertEqual(len(rec["slots"]), 10)
        self.assertEqual((rec["level"], rec["rate_index"]), (9, 5))
        self.assertEqual(rec["species_weights"], [3, 1, 0])
        self.assertEqual(rec["fixed"], {"weight": 0, "group": 0})
        self.assertEqual(dropped, [12])

    def test_dungeon_record_turns_the_formation_slot_into_a_fixed_group(self):
        rec, dropped = enc.record(PRG, dq5_tables((10, 50, 30, 255, 40, 60, 70, 80)), 0x01, dungeon={0x20: 4})
        self.assertEqual(rec["fixed"], {"weight": 2, "group": 4})
        self.assertEqual(rec["rate_index"], 3)
        self.assertEqual(dropped, [])

    def test_one_monster_slot_without_weight_or_room_is_dropped(self):
        self.zone_key = "crowded"
        rec, dropped = enc.record(PRG, dq5_tables(), 0x02)
        self.assertIn(11, dropped)
        self.assertEqual(sum(1 for s in rec["slots"] if s["weight"]), 3)


class DocsTests(PatchedFC):
    ENC = ZoneAssignmentTests.ENC

    def test_documents_cover_field_dungeon_and_sea_zones(self):
        progress, grid, report = enc.docs(PRG, dq5_tables(), self.ENC, dungeon=[0x50])
        self.assertEqual(progress["format"], "dq5progress/1")
        indexes = [r["index"] for r in progress["encounters"]]
        self.assertEqual(indexes, [5, 6, 7, 8, 9, 10, 11, 81, 82, 83, 84])
        self.assertEqual(grid["format"], "dq5encounter/1")
        self.assertEqual(len(grid["field_grids"]), 5)
        self.assertEqual(grid["fixed_groups"], [{"index": 0, "members": [{"monster": 0, "count_code": 0},
                                                                         {"monster": 9, "count_code": 1}]}])
        self.assertEqual(sorted(report), ["00", "03", "04", "34", "35", "36", "50"])
        self.assertEqual((report["03"]["kind"], report["03"]["zone"]), ("field", 6))
        self.assertEqual((report["50"]["kind"], report["50"]["zone"]), ("dungeon", 11))
        self.assertEqual(report["50"]["fixed"], {"weight": 2, "group": 0})
        self.assertEqual(report["50"]["monsters"], [0, 9, 11])
        self.assertEqual(report["03"]["dropped_slots"], [12])


class MainTests(unittest.TestCase):
    def test_writes_three_documents_and_prints_the_report(self):
        docs = ({"p": 1}, {"g": 2}, {"r": 3})
        calls = []

        def fake_run(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_text(json.dumps({"maps": []}), encoding="utf-8")
            calls.append(cmd)

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "dq4.nes").write_bytes(b"nes")
            (tmp / "dq5.sfc").write_bytes(b"sfc")
            argv = ["dq4fieldencounter.py", "--dq4", str(tmp / "dq4.nes"), "--dq5", str(tmp / "dq5.sfc"),
                    "-o", str(tmp / "out" / "sub")]
            buf = io.StringIO()
            with mock.patch("sys.argv", argv), mock.patch.object(subprocess, "run", fake_run), \
                    mock.patch("kr_patch.fc.ines.prg", lambda raw: raw + b"!"), \
                    mock.patch.object(enc, "docs", lambda prg, dq5, found: docs) as patched, \
                    contextlib.redirect_stdout(buf):
                enc.main()
            out = tmp / "out" / "sub"
            self.assertEqual(json.loads((out / "progress.json").read_text(encoding="utf-8")), {"p": 1})
            self.assertEqual(json.loads((out / "encounter.json").read_text(encoding="utf-8")), {"g": 2})
            self.assertEqual(json.loads((out / "report.json").read_text(encoding="utf-8")), {"r": 3})
        self.assertEqual(json.loads(buf.getvalue()), {"r": 3})
        self.assertEqual(len(calls), 1)
        self.assertIn("dump", calls[0])


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
