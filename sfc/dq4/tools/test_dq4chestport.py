"""상자 이식의 보상 번호 계산과 원본 상자 표 정리를 합성 입력으로 검사한다."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        (3, 4): [(0, 1, 1, 1, "skipped group")],
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
                    mock.patch.object(chestport.dq4block, "pots", lambda prg: pots):
                return chestport.port(dq5, dq4)

    def test_chest_cells_rewards_and_report(self):
        doc, report = self.run_port()
        self.assertEqual(doc["format"], "dq5chestplace/1")
        self.assertEqual(doc["maps"], [{"map": "40/01", "chests": [
            {"x": 7, "y": 9, "reward": 0x01},
            {"x": 11, "y": 13, "reward": chestport.EMPTY},
            {"x": 15, "y": 17, "reward": 0x44},
            {"x": 19, "y": 21, "reward": 0x100 + 2 * 40}]}])
        self.assertEqual([r["fc"] for r in report], ["01/02 (3,4)", "01/02 (5,6)", "01/02 (7,8)", "01/02 (9,10)"])
        self.assertEqual({r["map"] for r in report}, {"40/01"})

    def test_waiting_group_gets_no_chests(self):
        doc, _ = self.run_port()
        self.assertNotIn("45/02", [m["map"] for m in doc["maps"]])

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
