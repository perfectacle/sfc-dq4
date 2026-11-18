"""상자 이식의 보상 번호 계산과 원본 상자 표 정리를 합성 입력으로 검사한다."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]

import dq4chestport as chestport
from dq4environmentrom import TARGETS
from dq4shopport import _fold


NAMES = ["", "やくそう", "ラックのたね", "じょうせんけん", "うまのふん", "つるぎ"]
ITEMS = {_fold("やくそう"): 0x01, _fold("ふしぎなきのみ"): 0x20, _fold("つるぎ"): 0x30,
         _fold("やみのランプ"): 0x44}


class RewardTests(unittest.TestCase):
    def test_gold_is_forty_times_the_low_seven_bits(self):
        self.assertEqual(chestport._reward(NAMES, ITEMS, 0x80 | 3), 0x100 + 120)
        self.assertEqual(chestport._reward(NAMES, ITEMS, 0xFF), 0x100 + 127 * 40)

    def test_drawer_cannot_hold_gold(self):
        with self.assertRaises(ValueError):
            chestport._reward(NAMES, ITEMS, 0x83, gold=False)

    def test_item_is_matched_by_name_ignoring_kana_type(self):
        self.assertEqual(chestport._reward(NAMES, ITEMS, 5), 0x30)

    def test_item_without_dq5_counterpart_takes_substitute(self):
        # ラックのたね → ふしぎなきのみ, うまのふん → やくそう
        self.assertEqual(chestport._reward(NAMES, ITEMS, 2), 0x20)
        self.assertEqual(chestport._reward(NAMES, ITEMS, 4), 0x01)

    def test_borrowed_slot_item_is_not_substituted(self):
        # サントハイム 의 タンス 의 はねぼうし 는 빌린 자리(dq4itemport.BORROWED)로, きのぼうし 로 바꾸지 않는다
        import dq4itemport
        self.assertNotIn("はねぼうし", chestport.SUBSTITUTE)
        self.assertIn("はねぼうし", dq4itemport.BORROWED.values())

    def test_item_waiting_for_its_event_is_empty(self):
        self.assertEqual(chestport._reward(NAMES, ITEMS, 3), chestport.EMPTY)

    def test_unknown_item_name_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no DQ5 item named"):
            chestport._reward(NAMES, {}, 5)


class BaseTablesTests(unittest.TestCase):
    def setUp(self):
        self.slot = sorted(TARGETS.values())[0]
        other = (0x03, 0x0B)
        self.assertNotIn(other, TARGETS.values())
        self.tables = {
            "chest_maps": [{"group": other[0], "map": other[1], "count": 2},
                           {"group": self.slot[0], "map": self.slot[1], "count": 1},
                           {"group": 0x04, "map": 0x01, "count": 1}],
            "chests": ["a1", "a2", "dropped", "b1"],
            "lower": [{"flag_index": 0}, {"flag_index": 2}],
            "search": [{"group": self.slot[0], "map": self.slot[1]}, {"group": 0x04, "map": 0x01}],
            "extra": "kept",
        }

    def test_replaced_maps_lose_their_chests_and_rows(self):
        out = chestport.base_tables(self.tables)
        self.assertEqual(out["chests"], ["a1", "a2", "b1"])
        self.assertEqual([(r["group"], r["map"]) for r in out["chest_maps"]], [(0x03, 0x0B), (0x04, 0x01)])
        self.assertEqual(out["search"], [{"group": 0x04, "map": 0x01}])

    def test_lower_flags_shift_and_other_keys_pass_through(self):
        out = chestport.base_tables(self.tables)
        self.assertEqual([e["flag_index"] for e in out["lower"]],
                         [chestport.LOWER_SHIFT, 2 + chestport.LOWER_SHIFT])
        self.assertEqual(out["extra"], "kept")
        self.assertEqual(self.tables["lower"][0]["flag_index"], 0)


class PortTests(unittest.TestCase):
    CHESTS = {
        (1, 2): [(0, 3, 4, 1, "herb"), (0, 5, 6, 0xFF, "empty"), (0, 7, 8, 0xE3, "lamp"), (0, 9, 10, 0x82, "gold")],
        (3, 4): [(0, 1, 1, 1, "group 45")],
    }
    PLACEMENT = {(1, 2): (0x40, 0x01), (3, 4): (0x45, 0x02), (5, 6): (0x40, 0x03)}
    SPECIAL_CODE = 0x77

    def run_port(self, chests=None, pots=None, special=()):
        chests = self.CHESTS if chests is None else chests
        pots = [] if pots is None else pots
        with tempfile.TemporaryDirectory() as tmp:
            dq5, dq4 = Path(tmp) / "dq5.sfc", Path(tmp) / "dq4.nes"
            dq5.write_bytes(b"5")
            dq4.write_bytes(b"4")
            with mock.patch.object(chestport.ines, "prg", lambda raw: raw), \
                    mock.patch.object(chestport.dq5item, "Rom", lambda raw: raw), \
                    mock.patch.object(chestport, "dq5_items", lambda rom: ITEMS), \
                    mock.patch.object(chestport.dq4shop, "item_names", lambda prg: (NAMES, None)), \
                    mock.patch.object(chestport, "placement", lambda prg: self.PLACEMENT), \
                    mock.patch.object(chestport.dq4chest, "chests", lambda prg, g, k: chests.get((g, k), [])), \
                    mock.patch.object(chestport.dq4chest, "special_codes", lambda prg, which: set(special)), \
                    mock.patch.object(chestport.dq4block, "pots", lambda prg: pots), \
                    mock.patch.object(chestport.dq4chest, "feet_items", lambda prg: []):
                return chestport.port(dq5, dq4)

    def test_chest_cells_rewards_and_report(self):
        doc, report = self.run_port()
        self.assertEqual(doc["format"], "dq5chestplace/1")
        self.assertEqual(doc["maps"], [{"map": "40/01", "chests": [
            {"x": 7, "y": 9, "reward": 0x01},
            {"x": 11, "y": 13, "reward": chestport.EMPTY},
            {"x": 15, "y": 17, "reward": 0x44},
            {"x": 19, "y": 21, "reward": 0x100 + 2 * 40}]},
            {"map": "45/02", "chests": [{"x": 3, "y": 3, "reward": 0x01}]}])
        self.assertEqual([r["fc"] for r in report],
                         ["01/02 (3,4)", "01/02 (5,6)", "01/02 (7,8)", "01/02 (9,10)", "03/04 (1,1)"])
        self.assertEqual({r["map"] for r in report}, {"40/01", "45/02"})

    def test_special_chest_without_reward_is_an_error(self):
        chests = {(1, 2): [(0, 3, 4, self.SPECIAL_CODE, "mimic")]}
        with self.assertRaisesRegex(ValueError, "special chest mimic"):
            self.run_port(chests=chests, special=[self.SPECIAL_CODE])

    def test_pots_take_open_bits_in_order_across_flag_bytes(self):
        pots = [{"group": 1, "index": 2, "x": i, "y": 0, "item": 1} for i in range(9)]
        pots.append({"group": 9, "index": 9, "x": 0, "y": 0, "item": 1})
        doc, report = self.run_port(chests={}, pots=pots)
        (entry,) = doc["maps"]
        self.assertEqual(entry["map"], "40/01")
        self.assertNotIn("chests", entry)
        furniture = entry["furniture"]
        self.assertEqual(len(furniture), 9)
        self.assertEqual((furniture[0]["flag_index"], furniture[0]["mask"]), (0x0B, 0x80))
        self.assertEqual((furniture[7]["flag_index"], furniture[7]["mask"]), (0x0B, 0x01))
        self.assertEqual((furniture[8]["flag_index"], furniture[8]["mask"]), (0x0D, 0x80))
        self.assertEqual((furniture[3]["x"], furniture[3]["y"]), (7, 1))
        self.assertEqual(report[0]["kind"], "furniture")

    def test_pot_holding_gold_is_an_error(self):
        pots = [{"group": 1, "index": 2, "x": 0, "y": 0, "item": 0x83}]
        with self.assertRaises(ValueError):
            self.run_port(chests={}, pots=pots)


@unittest.skipUnless((ROOT / "rom" / "dq4.nes").is_file() and (ROOT / "rom" / "dq5.sfc").is_file(),
                     "local source ROMs not present")
class Chapter2ChestTests(unittest.TestCase):
    def test_group_45_chests(self):
        """그룹 45(사란·서쪽 탑·남쪽 동굴)의 상자 8개가 들어가고, 남쪽 동굴의 황금의 팔찌는 빌린 자리 C6 이다."""
        _, report = chestport.port(str(ROOT / "rom" / "dq5.sfc"), str(ROOT / "rom" / "dq4.nes"))
        chests = [r for r in report if r["map"].startswith("45/") and r["kind"] == "chest"]
        self.assertEqual(len(chests), 8)
        self.assertEqual([r["reward"] for r in chests if r["fc_item"] == "おうごんのうでわ"], [0xC6])


class MainTests(unittest.TestCase):
    def test_writes_place_json_and_prints_report(self):
        doc, report = {"format": "dq5chestplace/1", "maps": []}, [{"fc": "x"}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "chests"
            buf = io.StringIO()
            argv = ["dq4chestport.py", "--dq5", "a", "--dq4", "b", "--out", str(out)]
            with mock.patch("sys.argv", argv), mock.patch.object(chestport, "port", lambda a, b: (doc, report)), \
                    contextlib.redirect_stdout(buf):
                chestport.main()
            self.assertEqual(json.loads((out / "place.json").read_text()), doc)
        self.assertEqual(json.loads(buf.getvalue()), report)


if __name__ == "__main__":
    unittest.main()


DQ5_ROM, FC_ROM = ROOT / "rom" / "dq5.sfc", ROOT / "rom" / "dq4.nes"


@unittest.skipUnless(DQ5_ROM.is_file() and FC_ROM.is_file(), "rom/dq5.sfc 와 rom/dq4.nes 가 필요")
class FeetTests(unittest.TestCase):
    """FC 발밑 숨은 물건: 그 칸 조사는 덮는 DQ5 발밑 줄로, 「위를 보면」 은 위 가구 칸의 서랍 항목으로."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / "sfc" / "dq5" / "tools"))
        import dq5chestreloc
        from dq5map import Rom
        cls.tables = dq5chestreloc.parse(Rom(DQ5_ROM.read_bytes()))
        cls.feet = chestport.feet(DQ5_ROM, FC_ROM)
        cls.base = chestport.base_tables(cls.tables, cls.feet)
        cls.place, _ = chestport.port(DQ5_ROM, FC_ROM)

    def test_foot_row_lands_on_its_cell(self):
        self.assertEqual(self.feet["foot"], [{"group": 0x3D, "map": 3, "x": 24, "y": 7, "layer": 1, "reward": 0xB1}])

    def test_look_up_item_sits_in_the_pot_above(self):
        row = next(m for m in self.place["maps"] if m["map"] == "38/01")
        self.assertIn(0xAF, [e["reward"] for e in row["furniture"] if (e["x"], e["y"]) == (7, 3)])

    def foot_bits(self):
        out = set()
        for slot in chestport.FREE_FOOT[:len(self.feet["foot"])]:
            r = self.base["foot"][slot]
            out |= {(0x7E2240 + r["flag_index"], 1 << b) for b in range(8) if r["mask"] & 1 << b}
        return out

    def test_new_bits_do_not_meet_other_bits_or_chapter_variables(self):
        import dq4ch2event
        import dq4ch2slots
        import dq4ch3slots
        mine = self.foot_bits()
        others = set()
        for i, r in enumerate(self.base["foot"]):
            if i not in chestport.FREE_FOOT[:len(self.feet["foot"])]:
                others |= {(0x7E2240 + r["flag_index"], 1 << b) for b in range(8) if r["mask"] & 1 << b}
        for r in self.base["lower"] + self.base["ahead"]:
            others |= {(0x7E2190 + (r["flag_index"] | 0x80), 1 << b) for b in range(8) if r["mask"] & 1 << b}
        drawers = {(0x7E222C + e["flag_index"], e["mask"]) for m in self.place["maps"] for e in m.get("furniture", [])}
        self.assertEqual(mine & (others | drawers), set())
        # 장 사건 변수(2·3장 flag 바이트)와 장 넘김이 비우는 맡긴 물건 칸에 닿지 않는다(FC 처럼 주운 것은 장이 바뀌어도 남음)
        slot_bytes = {0x7E2190 + f for mod in (dq4ch2slots, dq4ch3slots) for s in mod.SLOTS.values() for f in s.flags}
        cleared = range(dq4ch2event.BANK_ITEMS_AT, dq4ch2event.BANK_ITEMS_AT + dq4ch2event.BANK_ITEMS)
        for at, _ in mine | drawers:
            self.assertNotIn(at, slot_bytes, f"{at:06X}")
            self.assertNotIn(at, cleared, f"{at:06X}")

    def test_foot_bytes_are_not_read_outside_the_table(self):
        # 2240~2242 를 abs·long 으로 읽는 명령이 원래 롬에 없다(덮은 줄의 비트가 다른 DQ5 코드로 DQ4 에 닿지 않음)
        d = DQ5_ROM.read_bytes()
        for at in (0x2240, 0x2241, 0x2242):
            for op in (0xAD, 0x2D, 0x2C):
                self.assertNotIn(bytes((op, at & 0xFF, at >> 8)), d)
            self.assertNotIn(bytes((0xAF, at & 0xFF, at >> 8, 0x7E)), d)

    def test_only_chapters_one_to_three(self):
        import dq4groupbuild
        for r in self.feet["foot"]:
            self.assertIn(min(p.get("chapter") or 1 for p in dq4groupbuild.LINKS[r["group"]]), chestport.FEET_CHAPTERS)

    def test_overwritten_rows_were_dq5_only(self):
        for slot in chestport.FREE_FOOT[:len(self.feet["foot"])]:
            old = self.tables["foot"][slot]
            self.assertLess(old["reward"], 0xD000)
            self.assertLess(old["group"], 0x36)
