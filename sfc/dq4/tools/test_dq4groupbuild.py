"""Without a ROM, the FC -> DQ5 cell rule and map layout; with rom/dq4.nes, the exit and area records of the new
groups."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4groupbuild as build  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq4.nes"


class CellTest(unittest.TestCase):
    def test_stands_on_bottom_left_cell(self):
        self.assertEqual(build.cell(0x0F, 0x23), (30, 71))
        self.assertEqual(build.cell(0, 0), (0, 1))


class DungeonAttrsTest(unittest.TestCase):
    def test_dungeon_zones_and_song(self):
        dq5 = ROM.parent / "dq5.sfc"
        if not dq5.exists():
            self.skipTest("rom/dq5.sfc")
        link = {"attrs": "21/02", "music": 0x09, "dungeon": True}
        row = build.map_attrs(dq5, link, 0x2C)["bytes"]
        # 21/02: zones 01 14 14, background 07, ceiling 01, song 09.
        self.assertEqual(row, [0x2C, 0x2C, 0x2C, 0x07, 0x01, 0x09])
        self.assertEqual(build.map_attrs(dq5, link)["bytes"][:3], [0xFF] * 3)
        self.assertEqual(build.map_attrs(dq5, {"attrs": "03/00"}), {"copy": "03/00"})


class SyntheticTablesTest(unittest.TestCase):
    """map_attrs and dungeon_zones on made-up tables in place of the ROM readers."""

    def test_map_attrs_replaces_song_and_dungeon_zones(self):
        attrs = {0x21: {0x02: bytes([1, 2, 3, 4, 5, 6])}}
        with mock.patch("dq5newmap.entries", return_value=(attrs, None)), \
                mock.patch.object(Path, "read_bytes", return_value=b""):
            link = {"attrs": "21/02", "music": 0x09, "dungeon": True}
            self.assertEqual(build.map_attrs(Path("dq5.sfc"), link, 0x2C)["bytes"], [0x2C, 0x2C, 0x2C, 4, 5, 0x09])
            self.assertEqual(build.map_attrs(Path("dq5.sfc"), link)["bytes"][:3], [0xFF] * 3)
            self.assertEqual(build.map_attrs(Path("dq5.sfc"), {"attrs": "21/02", "music": 0x0A})["bytes"],
                             [1, 2, 3, 4, 5, 0x0A])

    def test_dungeon_zones_skip_maps_without_a_zone(self):
        dungeons = {part["fc"] for parts in build.LINKS.values() for part in parts if part.get("dungeon")}
        first = min(dungeons)
        lists = [(fc, [0x40, 0xFF]) for fc in dungeons if fc != first]
        encounter = types.SimpleNamespace(dungeon_lists=lambda prg: [(None, None, lists)])
        with mock.patch.dict(sys.modules, {"dq4encounter": encounter}), \
                mock.patch.object(build, "fc_numbers", return_value=[0, 1, 2]):
            zones = build.dungeon_zones(b"")
        self.assertEqual(zones, {(fc, 0): 0x40 for fc in dungeons if fc != first})


class BundleTest(unittest.TestCase):
    """Two FC groups in one DQ5 group, and one FC group alone."""
    LINKS = {0x40: [{"fc": 0x10, "arrival": (1, 2), "map": 1, "field": (100, 50)},
                    {"fc": 0x11, "arrival": (3, 4), "map": 1, "field": (110, 60)}],
             0x41: [{"fc": 0x12, "arrival": (5, 6), "field": (120, 70)}]}
    FC_MAPS = {0x10: [2, 0, 1], 0x11: [1, 0], 0x12: [0]}

    def setUp(self):
        self.place = build.layout(self.LINKS, self.FC_MAPS)

    def test_maps_follow_one_another(self):
        self.assertEqual([self.place[0x10, k] for k in range(3)], [(0x40, 0), (0x40, 1), (0x40, 2)])
        self.assertEqual([self.place[0x11, k] for k in range(2)], [(0x40, 3), (0x40, 4)])
        self.assertEqual(self.place[0x12, 0], (0x41, 0))

    # Stair cells of each FC destination map, in DQ5 exit order.
    ORDER = {(0x11, 1): [(4, 4), (5, 6)], (0x12, 0): [(3, 3)]}

    def stairs(self, first):
        found = {k: [] for k in self.place}
        found[0x10, 0] = first
        return found

    def test_stairs(self):
        first = [(1, 1, {"group": 0x11, "index": 1, "x": 5, "y": 6}),
                 (2, 2, {"group": 0x12, "index": 0, "x": 3, "y": 3}),
                 (3, 3, {"field": True})]
        records = build.exit_rows(0x40, self.LINKS[0x40], self.place, self.stairs(first),
                                  lambda g, k: self.ORDER[g, k])
        self.assertEqual(records["40/00"], [
            {"kind": "same-group", "destination_map": 4, "exit": 1},
            {"kind": "other-group", "group": 0x41, "destination_map": 0, "exit": 0},
            {"kind": "special", "special": 0}])
        self.assertEqual(sorted(records), [f"40/{n:02X}" for n in range(5)])

    def test_field_stair_of_part_without_entrance(self):
        links = [{**self.LINKS[0x40][0], "field": None}, self.LINKS[0x40][1]]
        with self.assertRaises(ValueError):
            build.exit_rows(0x40, links, self.place, self.stairs([(3, 3, {"field": True})]), self.ORDER.get)

    def test_area_move_across_fc_groups(self):
        # FC 10/00 (1,2) walking down (flag 2) -> FC 11/01 (4,5).
        rows = build.area_rows(0x40, self.place, {(0x10, 0): [(1, 2, 0x11, 1, 4, 5, 2)]})
        self.assertEqual(rows, {"40/00": [{"rect": [2, 4, 3, 5], "source_layer": build.LAYER, "flags": build.AREA_FLAGS,
                                           "destination_group": 0x40, "destination_map": 4, "x": 8, "y": 11,
                                           "span_raw": 1, "destination_layer": build.LAYER}]})
        for dg, dk in ((0x12, 0), (0x11, 5)):
            with self.assertRaises(ValueError):
                build.area_rows(0x40, self.place, {(0x10, 0): [(1, 2, dg, dk, 4, 5, 2)]})

    def test_map_numbers_fit_five_bits(self):
        build.layout({0x40: [{"fc": 0x10}]}, {0x10: range(0x20)})
        with self.assertRaises(ValueError):
            build.layout({0x40: [{"fc": 0x10}, {"fc": 0x11}]}, {0x10: range(0x20), 0x11: [0]})

    def test_hook_rows(self):
        doors = {0x10: ([(100, 50), (101, 50)], (100, 53)), 0x11: ([(110, 60)], (110, 63)),
                 0x12: ([(120, 70)], (118, 71))}
        arrivals, leaving = build.hook_rows(self.LINKS, self.place, doors)
        layer = build.LAYER
        self.assertEqual(arrivals, [(0x40, 100, 50, 1, 2, 5, layer, 0), (0x40, 101, 50, 1, 2, 5, layer, 0),
                                    (0x40, 110, 60, 4, 6, 9, layer, 0), (0x41, 120, 70, 0, 10, 13, layer, 0)])
        self.assertEqual(leaving, [(0x40, 0, 2, 100, 53), (0x40, 3, 4, 110, 63), (0x41, 0, 0x1F, 118, 71)])
        import dq4entrancehook
        dq4entrancehook.tables(arrivals, leaving)

    def test_fall_maps_leave_before_the_group(self):
        # 떨어지는 맵의 나가기 행이 그 그룹의 행보다 앞에 있어야 2A:F425 가 그 행을 고른다
        links = {0x39: [{"fc": 0x30, "field": [(0x88, 0x17)], "arrival": (1, 1)}]}
        place = {(0x30, k): (0x39, k) for k in range(6)}
        _, leaving = build.hook_rows(links, place, {0x30: ([(272, 46)], (270, 47))})
        self.assertEqual(leaving, [(0x39, 0, 2, 0x88 * 2, 0x19 * 2), (0x39, 0, 0x1F, 270, 47)])

    def test_fc_group_in_two_dq5_groups(self):
        with self.assertRaises(ValueError):
            build.layout({0x40: [{"fc": 0x10}], 0x41: [{"fc": 0x10}]}, self.FC_MAPS)
        # Also when the FC group has no ported maps.
        with self.assertRaises(ValueError):
            build.layout({0x40: [{"fc": 0x13}], 0x41: [{"fc": 0x13}]}, self.FC_MAPS)


class RecordAreasTest(unittest.TestCase):
    AREAS = ((0x348000, 0x348010), (0x318000, 0x318008))

    def test_records_go_on_in_the_next_area(self):
        self.assertEqual(build.record_areas([8, 8, 4, 4], self.AREAS), [0, 0, 1, 1])
        # A record that does not fit the rest of an area starts the next one; the next does not go back.
        self.assertEqual(build.record_areas([10, 7, 1], self.AREAS), [0, 1, 1])
        with self.assertRaises(ValueError):
            build.record_areas([10, 7, 4], self.AREAS)

    def test_area_in_one_bank_of_30_3f(self):
        for area in ((0x408000, 0x408010), (0x34F000, 0x358010), (0x340000, 0x340010)):
            with self.assertRaises(ValueError):
                build.record_areas([1], (area,))

    def test_splice_lays_pointers_into_the_first_list(self):
        first = [{"at": "0F:8ED7", "hex": "00 00 00 00 00 00"}]
        rest = build.splice(first, [{"at": "0F:8EDA", "hex": "01 80 31"}, {"at": "31:8000", "hex": "AA"}])
        self.assertEqual(first[0]["hex"], "00 00 00 01 80 31")
        self.assertEqual(rest, [{"at": "31:8000", "hex": "AA"}])
        with self.assertRaises(ValueError):
            build.splice(first, [{"at": "0F:8EDB", "hex": "01 02 03 04 05"}])


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class DungeonZonesTest(unittest.TestCase):
    def test_fc_dungeon_list(self):
        from kr_patch.fc import ines
        zones = build.dungeon_zones(ines.prg(ROM.read_bytes()))
        # The tower's two top floors and 古井戸の底 (1C) have no zone.
        want = {(0x30, 0): 0x42, (0x30, 1): 0x42, (0x30, 2): 0x43, (0x30, 3): 0x43, (0x41, 0): 0x40,
                **{(0x3A, k): 0x41 for k in range(7)}}
        self.assertEqual(zones, want)


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class RecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())

    # FC stairs that do not lead back. きたのどうくつ 3D/02 (3E/05) is the 3D/01 (3E/04) of after the fall: its stairs
    # lead to 3D/00, whose stairs lead to 3D/01 until $62AA bit7 turns them to 3D/02 (08:$B397).
    ONE_WAY = {"3E/05"}

    def test_stairs_lead_back(self):
        records = {}
        for group in build.LINKS:
            records.update(build.exit_records(self.prg, group))
        for name, rows in records.items():
            group, number = int(name[:2], 16), int(name[3:], 16)
            for i, row in enumerate(rows):
                if row["kind"] == "special" or name in self.ONE_WAY:
                    continue
                there = row.get("group", group)
                back = records[f"{there:02X}/{row['destination_map']:02X}"][row["exit"]]
                self.assertEqual((back.get("group", there), back["destination_map"], back["exit"]), (group, number, i),
                                 f"{name} exit {i}")

    def test_area_rects_are_one_row(self):
        areas = {}
        for group in build.LINKS:
            areas.update(build.area_records(self.prg, group))
        # エンドール's 04/00 doors to 04/02-04/04 and 04/02's bottom edge back to 04/00 are FC exit-table cells too.
        self.assertEqual(sorted(areas), ["36/00", "36/01", "40/00", "40/02", "40/03", "40/04"])
        for rows in areas.values():
            for row in rows:
                x0, y0, x1, y1 = row["rect"]
                self.assertEqual(y1 - y0, 1)
                self.assertEqual(row["span_raw"], x1 - x0)
        # 02/00's castle door is entered walking up (bottom row of its FC cell), 02/01's exit below the
        # map is entered walking down (top row of the first outside FC row).
        self.assertEqual(areas["36/00"][0]["rect"], [36, 21, 39, 22])
        self.assertEqual(areas["36/01"][0]["rect"], [30, 72, 33, 73])


if __name__ == "__main__":
    unittest.main()
