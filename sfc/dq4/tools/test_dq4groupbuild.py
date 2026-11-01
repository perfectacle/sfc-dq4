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
                **{(0x3A, k): 0x41 for k in range(7)},
                # Chapter 2: 西の塔 (its top 2E/00 and the inn floor 2E/04 have none) and the cave south of フレノール.
                (0x2E, 1): 0x4F, (0x2E, 2): 0x4E, (0x2E, 3): 0x4E, (0x2E, 5): 0x4F, (0x39, 0): 0x4D, (0x39, 1): 0x4C}
        self.assertEqual(zones, want)


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class RecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())

    # FC stairs that do not lead back. きたのどうくつ 3D/02 (3E/05) is the 3D/01 (3E/04) of after the fall: its stairs
    # lead to 3D/00, whose stairs lead to 3D/01 until $62AA bit7 turns them to 3D/02 (08:$B397).
    # モンバーバラ 15/03(41/03)은 밤의 15/02 다. FC 는 15/00 의 계단을 밤이면 15/03 으로 돌리지만(08:$B397) 옮기지 않아
    # 15/00 의 계단은 늘 15/02 로 간다.
    ONE_WAY = {"3E/05", "41/03"}

    def test_stairs_lead_back(self):
        records = {}
        for group in build.LINKS:
            records.update(build.exit_records(self.prg, group))
        for name, rows in records.items():
            group, number = int(name[:2], 16), int(name[3:], 16)
            for i, row in enumerate(rows):
                if row["kind"] in ("special", "position") or name in self.ONE_WAY:
                    continue
                there = row.get("group", group)
                back = records[f"{there:02X}/{row['destination_map']:02X}"][row["exit"]]
                # 출구 표가 정한 칸으로 돌아오는 계단(position)은 같은 맵으로만 오면 된다.
                if back["kind"] == "position":
                    self.assertEqual((back["group"], back["destination_map"]), (group, number), f"{name} exit {i}")
                    continue
                self.assertEqual((back.get("group", there), back["destination_map"], back["exit"]), (group, number, i),
                                 f"{name} exit {i}")

    def test_area_rects_are_one_row(self):
        areas = {}
        for group in build.LINKS:
            areas.update(build.area_records(self.prg, group))
        # エンドール's 04/00 doors to 04/02-04/04 and 04/02's bottom edge back to 04/00 are FC exit-table cells too.
        # ハバリア(43)·キングレオ(44)도 출구 표 칸이 있다. 43/00 (13,08) 은 왼쪽으로 걸어 들어가는 칸이다.
        self.assertEqual(sorted(areas), ["36/00", "36/01", "40/00", "40/02", "40/03", "40/04", "43/00", "43/03",
                                         "43/05", "44/00", "44/01", "44/02", "45/00", "45/02", "45/03", "45/04"])
        for rows in areas.values():
            for row in rows:
                x0, y0, x1, y1 = row["rect"]
                self.assertEqual(y1 - y0, 1)
                self.assertEqual(row["span_raw"], x1 - x0)
        self.assertEqual(areas["43/00"][0]["rect"], [0x13 * 2 + 1, 0x08 * 2 + 1, 0x13 * 2 + 2, 0x08 * 2 + 2])
        # 02/00's castle door is entered walking up (bottom row of its FC cell), 02/01's exit below the
        # map is entered walking down (top row of the first outside FC row).
        self.assertEqual(areas["36/00"][0]["rect"], [36, 21, 39, 22])
        self.assertEqual(areas["36/01"][0]["rect"], [30, 72, 33, 73])


class FakeTools:
    """_run 자리의 가짜 도구. dump·patch 는 -o 파일을 쓰고, 부른 차례와 그때 있던 파일을 남긴다."""
    POINTERS = "3C:9200"

    def __init__(self, out, fail=None):
        self.out, self.fail, self.calls, self.lock = out, fail, [], __import__("threading").Lock()

    def __call__(self, tool, *args):
        import json
        name, args = Path(tool).name, [str(a) for a in args]
        with self.lock:
            self.calls.append((name, args))
        if self.fail and self.fail(name, args):
            raise RuntimeError(f"{name} failed")
        if name == "dq4environmentrom.py":
            env = Path(args[args.index("--out") + 1])
            env.mkdir(parents=True, exist_ok=True)
            (env / "dq4-environment.dq5patch.json").write_text('{"format": "dq5patch/1", "writes": []}')
            return json.dumps({"group_maps": {}, "records_end": "3E:FFFF", "bank01_bytes": 1})
        o = Path(args[args.index("-o") + 1]) if "-o" in args else None
        if name == "dq5build.py":
            # 얹는 패치가 모두 만들어진 뒤여야 한다
            missing = [a for a in args[2:] if a.endswith(".json") and not Path(a).is_file()]
            if missing:
                raise AssertionError(f"dq5build before {missing}")
            o.write_bytes(b"rom")
        elif "dump" in args:
            doc = {"exits-orig.json": {"exits": [{"map": "36/00", "records": ["old"]}, {"map": "03/00", "records": ["dq5"]}],
                                       "triggers": [{"map": "36/01", "records": ["old"]}]},
                   "fieldtables-orig.json": {"arrivals": [{"group": 0}], "entrances": [{"table": "main", "n": 1},
                                                                                   {"table": "aux", "n": 2}]}}
            o.write_text(json.dumps(doc.get(o.name, {})))
        elif "patch" in args:
            # dq5newmap 의 뒤 호출은 첫 호출의 포인터 목록 안을 다시 쓴다(splice 가 첫 목록에 얹어야 한다)
            writes = []
            if name == "dq5newmap.py":
                first = o.name == "newmap.dq5patch.json"
                writes = [{"at": self.POINTERS, "hex": "00 " * 15 + "00"} if first else
                          {"at": "3C:9204", "hex": "AA BB"}, {"at": "34:8000" if first else "31:8000", "hex": "01"}]
            o.write_text(json.dumps({"format": "dq5patch/1", "writes": writes}))
        return ""


class SyntheticBuildTest(unittest.TestCase):
    """롬 없이 _build 의 도구 차례: 패치 목록, --with-patch, 레코드 나누기, 검사 롬. FC 표 읽기는 가짜로 바꾼다."""

    def run_build(self, fail=None):
        import json
        import tempfile
        groups = {f"m{g:02X}{n:02X}": (g, n) for g, n in [(g, n) for g in build.LINKS for n in range(5)]}
        place = {(part["fc"], part.get("map", 0)): (g, k) for g, parts in build.LINKS.items()
                 for k, part in enumerate(parts)}
        first_fc = {g: parts[0]["fc"] for g, parts in build.LINKS.items()}
        doors = {part["fc"]: ([(1, 2)], "leave") for parts in build.LINKS.values() for part in parts}
        empty = lambda *a, **k: []  # noqa: E731
        self.tmp = tempfile.TemporaryDirectory()
        out, dq5, dq4 = Path(self.tmp.name) / "out", Path(self.tmp.name) / "dq5.sfc", Path(self.tmp.name) / "dq4.nes"
        dq5.write_bytes(b"dq5")
        dq4.write_bytes(b"dq4")
        self.tools = FakeTools(out, fail)
        self.check_records = mock.Mock()
        import dq4balance
        import dq4chestport
        import dq4door
        import dq4dungeonrate
        import dq4fieldencounter
        import dq4fieldtravel
        import dq4npcport
        import dq4outside
        import dq4shopport
        import dq4wellswitch
        patches = [
            mock.patch.multiple(build, GROUPS=groups, _run=self.tools, placement=lambda prg: place,
                                fc_map=lambda prg, g, n: (first_fc[g], n), dungeon_zones=lambda prg: {},
                                map_attrs=lambda dq5, part, zone: {"copy": part["attrs"]},
                                new_map_records=lambda env: {(g, n): bytes(0x300) for g, n in groups.values()},
                                exit_records=lambda prg, g: {f"{g:02X}/00": ["new"]},
                                area_records=lambda prg, g: {f"{g:02X}/01": ["area"], f"{g:02X}/02": ["area2"]},
                                fall_records=lambda prg, g: {}, doors=lambda prg: doors, entrance_doors=lambda prg: {},
                                hook_rows=lambda *a: ([], []), companion_names=lambda d: {}, person_names=lambda d: {},
                                check_door_copy=mock.Mock(), check_records=self.check_records),
            mock.patch.object(build.ines, "prg", lambda data: b"prg"),
            mock.patch.object(build.dq4fieldport, "park", lambda rows, worlds: [dict(r, parked=1) for r in rows]),
            mock.patch.object(build.dq4fieldport, "patch",
                              lambda dq5, prg, path, at: [build._save(path, {"format": "dq5patch/1", "writes": []})]),
            mock.patch.object(build.dq4entrancehook, "writes", empty),
            mock.patch.object(dq4door, "writes", empty),
            mock.patch.multiple(dq4outside, writes=empty, rows=empty),
            mock.patch.multiple(dq4fieldencounter, dungeon_zones=lambda *a: {}, docs=lambda *a: ({}, {}, {}),
                                terrain_rates=lambda *a: {"at": "00:0000", "hex": "00"}),
            mock.patch.multiple(dq4npcport, port=lambda *a: ([{"map": "36/00", "entries": []}, {"name": "alt", "entries": []}],
                                                            [{"id": dq4npcport.FIRST_MESSAGE, "codes": [1]}], {}),
                                nothing_codes=lambda: [0], talk_doc=lambda m: {"format": "dq5talk/1"}),
            mock.patch.object(dq4shopport, "port", lambda *a: ({}, [{"kind": 0}], [], {})),
            mock.patch.multiple(dq4fieldtravel, destinations=lambda *a: {}, landing_rows=lambda *a: [{"landing": 1}],
                                writes=empty, names_doc=lambda *a: {"format": "dq5names/1"}),
            mock.patch.object(dq4wellswitch, "writes", empty),
            mock.patch.object(dq4dungeonrate, "writes", empty),
            mock.patch.object(dq4balance, "writes", empty),
            mock.patch.multiple(dq4chestport, port=lambda *a: ({"format": "dq5chest/1"}, {}), base_tables=lambda d: {}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.out = out
        summary = build.build(dq5, dq4, out)
        self.newmap = json.loads((out / "newmap.json").read_text())
        return summary

    def calls(self, name, verb=None):
        return [a for n, a in self.tools.calls if n == name and (verb is None or verb in a)]

    def test_records_spill_into_later_areas_and_pointers_splice_into_the_first_list(self):
        import json
        summary = self.run_build()
        n = len(build.GROUPS)
        per_area = (build.RECORDS_AT[0][1] - build.RECORDS_AT[0][0]) // 0x300
        self.assertEqual(summary["record_patches"], [f"newmap-{k}.dq5patch.json" for k in (1, 2)])
        sources = [m["record"] for m in self.newmap["maps"]]
        self.assertEqual(sum("source" in r for r in sources), per_area)
        self.assertTrue(all(r == {"copy": build.RECORD_PLACEHOLDER} for r in sources[per_area:]))
        self.assertEqual(len(sources), n)
        first = json.loads((self.out / "newmap.dq5patch.json").read_text())["writes"]
        self.assertEqual(first[0]["hex"].split()[4:6], ["AA", "BB"])
        for k in (1, 2):
            later = json.loads((self.out / f"newmap-{k}.dq5patch.json").read_text())["writes"]
            self.assertEqual([w["at"] for w in later], ["31:8000"])
        # 뒤 호출은 앞 호출까지 얹은 롬에서 자기 자리(RECORDS_AT[k])에 레코드를 쓴다
        later = [a for a in self.calls("dq5newmap.py", "patch") if "newmap-" in a[2]]
        self.assertEqual([a[a.index("--records-at") + 1] for a in later], ["31:8000", "3F:8000"])

    def test_group_entrances_and_dungeon_step_counting(self):
        self.run_build()
        for row in self.newmap["groups"]:
            group = int(row["group"], 16)
            part = build.LINKS[group][0]
            x, y = build.cell(*part["arrival"])
            indoor = build.INDOOR_ENCOUNTERS << 2 if any(p.get("dungeon") for p in build.LINKS[group]) else 0
            self.assertEqual(row["entrance"]["bytes"], [build.WORLD_CODE << 5, x, y, build.LAYER, indoor])

    def test_final_rom_takes_every_patch_and_chests_see_all_before_them(self):
        summary = self.run_build()
        (final,) = [a for a in self.calls("dq5build.py") if a[a.index("-o") + 1].endswith("groups.sfc")]
        manifests = [Path(a).name for a in final[2:final.index("--size")]]
        self.assertEqual(manifests[:5], ["dq4-environment.dq5patch.json", "doors.dq5patch.json", "outside.dq5patch.json",
                                         "newmap.dq5patch.json", "newmap-1.dq5patch.json"])
        self.assertEqual(manifests[-1], "field.dq5patch.json")
        self.assertEqual(len(manifests), len(set(manifests)))
        (chests,) = self.calls("dq5chestplace.py", "patch")
        with_patch = [Path(chests[i + 1]).name for i, a in enumerate(chests) if a == "--with-patch"]
        self.assertEqual(with_patch, manifests[:manifests.index("chests.dq5patch.json")])
        self.assertEqual(summary["rom"], str(self.out / "groups.sfc"))

    def test_checks_run_on_the_built_rom_only_for_dq5newmap(self):
        self.run_build()
        checks = self.calls("dq5newmap.py", "check") + [a for n, a in self.tools.calls if "check" in a and n != "dq5newmap.py"]
        self.assertTrue(checks)
        for name, args in self.tools.calls:
            if "check" in args:
                self.assertEqual(Path(args[0]).name, "groups.sfc" if name == "dq5newmap.py" else "dq5.sfc", name)
        self.assertEqual({n for n, a in self.tools.calls if "check" in a},
                         {"dq5newmap.py", "dq5textwrite.py", "dq5talkwrite.py", "dq5exitreloc.py", "dq5namewrite.py",
                          "dq5chestplace.py"})
        self.assertEqual(len(self.check_records.call_args.args[1]), len(build.GROUPS))

    def test_exit_records_replace_ours_and_add_new_trigger_maps(self):
        import json
        self.run_build()
        exits = json.loads((self.out / "exits.json").read_text())
        rows = {r["map"]: r["records"] for r in exits["exits"]}
        self.assertEqual((rows["36/00"], rows["03/00"]), (["new"], ["dq5"]))
        triggers = {r["map"]: r["records"] for r in exits["triggers"]}
        self.assertEqual(triggers["36/01"], ["area"])
        self.assertEqual([r["map"] for r in exits["triggers"]].count("36/01"), 1)
        self.assertEqual(triggers["37/02"], ["area2"])
        entrances = json.loads((self.out / "entrances.json").read_text())["entrance_tables"]
        self.assertEqual(entrances["main"], [{"table": "main", "n": 1, "parked": 1}])
        self.assertEqual(entrances["aux"][-1], {"landing": 1})

    def test_failure_cancels_the_rest_and_names_other_failures(self):
        import time

        def fail(name, args):
            if name == "dq4environmentrom.py":
                # 원래 롬 덤프 넷이 먼저 실패해 끝난 뒤에 앞 단계가 실패한다
                while sum("dump" in a for _, a in self.tools.calls) < 4:
                    time.sleep(0.001)
                time.sleep(0.05)
                return True
            return "dump" in args

        with self.assertRaisesRegex(RuntimeError, "dq4environmentrom.py failed") as caught:
            self.run_build(fail=fail)
        notes = sorted(caught.exception.__notes__)
        self.assertEqual(notes, sorted(f"also failed: {t} failed" for t in
                                       ("dq5exitreloc.py", "dq5fieldtables.py", "dq5encounterwrite.py", "dq5chestreloc.py")))
        self.assertFalse(self.calls("dq5newmap.py"))

if __name__ == "__main__":
    unittest.main()
