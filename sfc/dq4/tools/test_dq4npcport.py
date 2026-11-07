"""Message allocation; with rom/dq4.nes, the FC text -> DQ5 codes rule; with both ROMs, the ported people and
messages."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch1event  # noqa: E402
import dq4npcport as port  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


class AllocationTest(unittest.TestCase):
    def test_lines_get_new_ids_in_order_of_first_use(self):
        texts = {}
        made = []
        ids = [port.allocate(texts, key, lambda key=key: made.append(key) or [port.END])
               for key in ((1,), (2, 3), (1,), (), (2, 3))]
        f = port.FIRST_MESSAGE
        self.assertEqual(ids, [f, f + 1, f, f + 2, f + 1])
        self.assertEqual(made, [(1,), (2, 3), ()])  # codes are made once per line

    def test_talk_scripts_follow_the_prologue_gap_free(self):
        import dq4ch1event
        import dq4prologue
        prologue = dq4prologue.talk_doc()["scripts"]
        import dq4ch2event
        ch1 = len(dq4ch1event.TALKS)
        events = ch1 + len(dq4ch2event.talk_scripts(port.FIRST_MESSAGE))   # 등록한 사건 모듈(EVENTS)의 대화까지
        f = port.FIRST_MESSAGE
        messages = [{"id": f + k, "codes": [port.END]} for k in range(3)]
        scripts = port.talk_doc(messages)["scripts"]
        talks = [int(s["talk"], 16) for s in scripts]
        self.assertEqual(talks, list(range(port.SCRIPT_TALK, port.SCRIPT_TALK + len(prologue) + events + 3)))
        self.assertEqual(scripts[:len(prologue)], prologue)
        self.assertEqual([s["body"] for s in scripts[len(prologue):len(prologue) + ch1]],
                         dq4ch1event.talk_scripts(f + 3))   # 사건 메시지는 옮긴 메시지 바로 뒤
        self.assertEqual([s["body"] for s in scripts[len(prologue) + ch1:len(prologue) + events]],
                         dq4ch2event.talk_scripts(f + 3 + len(dq4ch1event.MESSAGES)))   # 2장은 1장 사건 뒤
        first = port.first_talk()
        for k, s in enumerate(scripts[len(prologue) + events:]):
            # Talk first_talk() + k shows message FIRST_MESSAGE + k, as port gives the people.
            self.assertEqual(int(s["talk"], 16), first + k)
            self.assertEqual(s["body"], [{"op": "msg", "id": f"{f + k:03X}"}])

    def test_talk_scripts_refuse_a_gap(self):
        with self.assertRaises(ValueError):
            port.talk_doc([{"id": port.FIRST_MESSAGE, "codes": [port.END]}, {"id": port.FIRST_MESSAGE + 2, "codes": [port.END]}])
        with self.assertRaises(ValueError):
            port.talk_doc([{"id": 0xC7F, "codes": [port.END]}])


CODE = port.CODE_OF


class PiecesTest(unittest.TestCase):
    def test_controls_are_names_and_characters_are_tagged(self):
        self.assertEqual(port._pieces("あ{LINE}い{NAME:0}"),
                         [("char", "あ"), "LINE", ("char", "い"), "NAME:0"])

    def test_speaker_mark_and_its_line_break_are_skipped(self):
        marked = [("char", "＊"), ("char", "「"), "LINE", ("char", "あ")]
        self.assertEqual(port._skip_speaker(marked, 0), 3)
        self.assertEqual(port._skip_speaker(marked[:3], 0), 3)
        self.assertEqual(port._skip_speaker([("char", "＊"), ("char", "あ")], 0), 0)
        self.assertEqual(port._skip_speaker(marked, 3), 3)

    def test_code_falls_back_to_nfkc_and_fullwidth_digits(self):
        self.assertEqual(port._code(0, "あ"), CODE["あ"])
        self.assertEqual(port._code(0, "1"), CODE["１"])
        self.assertEqual(port._code(0, "Ａ"), CODE["A"] if "A" in CODE else port._code(0, "Ａ"))

    def test_character_without_a_dq5_code_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "FC message 0007: no DQ5 character for"):
            port._code(7, "\U0001F600")

    def test_nothing_placeholder_has_a_code_per_character_and_the_end(self):
        codes = port.nothing_codes()
        self.assertEqual(codes[-1], port.END)
        self.assertEqual(len(codes), len(port.NOTHING) + 1)


class Dq5CodesTest(unittest.TestCase):
    def codes(self, *texts):
        with mock.patch.object(port.dq4text, "message_bytes", lambda rom, m: m), \
                mock.patch.object(port.dq4text, "symbolize", lambda m: texts[m]):
            return port.dq5_codes(None, range(len(texts)))

    def test_line_breaks_and_the_end_mark(self):
        self.assertEqual(self.codes("あ{LINE}い{END}"), [CODE["あ"], port.LINE, CODE["い"], port.END])

    def test_messages_join_with_one_page_between(self):
        self.assertEqual(self.codes("あ{END}", "い{END}"), [CODE["あ"], port.PAGE, CODE["い"], port.END])

    def test_speaker_marks_and_noindent_are_dropped_at_the_start_of_a_message_and_a_page(self):
        self.assertEqual(self.codes("{NOINDENT}＊「あ{WAIT}＊「{LINE}い{END}"),
                         [CODE["あ"], port.PAGE, CODE["い"], port.END])

    def test_a_page_is_neither_doubled_nor_left_at_the_end(self):
        self.assertEqual(self.codes("あ{WAIT}{WAIT}い{END}"), [CODE["あ"], port.PAGE, CODE["い"], port.END])
        self.assertEqual(self.codes("あ{WAIT}{END}"), [CODE["あ"], port.END])

    def test_pause_and_hero_name_have_their_own_codes(self):
        self.assertEqual(self.codes("あ{PAUSE}{NAME:0}い{END}"),
                         [CODE["あ"], port.PAUSE, port.HERO, CODE["い"], port.END])

    def test_dakuten_mark_joins_the_next_kana(self):
        self.assertEqual(self.codes("{3D}か{END}"), [CODE["が"], port.END])
        with self.assertRaisesRegex(ValueError, "dakuten mark without a character"):
            self.codes("{3D}{END}")

    def test_sound_controls_drop_and_a_stop_may_only_end_the_message(self):
        self.assertEqual(self.codes("{SOUND:01}あ{STOP}{END}"), [CODE["あ"], port.END])
        with self.assertRaisesRegex(ValueError, r"\{STOP\} before more text"):
            self.codes("{STOP}あ{END}")

    def test_unknown_control_is_an_error(self):
        with self.assertRaisesRegex(ValueError, r"FC message 0000: no DQ5 code for \{FOO\}"):
            self.codes("{FOO}")


def block_source(w, h, cells):
    from types import SimpleNamespace
    return SimpleNamespace(w=w, h=h, t=0x10, cell=lambda x, y: cells[y][x])


class FcStateAndBedsTest(unittest.TestCase):
    def test_state_holds_the_chapter_and_time_of_day(self):
        night = port.fc_state(True, {0x6300: 5}, 2)
        self.assertEqual((night.ram[0x615A], night.ram[0x62ED], night.ram[0x6300]), (1, port.NIGHT, 5))
        day = port.fc_state(False)
        self.assertEqual((day.ram[0x615A], day.ram[0x62ED]), (0, 0))

    def test_a_bed_is_a_left_half_beside_a_right_half(self):
        source = block_source(3, 2, [[1, 2, 0], [0, 1, 2]])
        art = {1: ("bed_left", ""), 2: ("bed_right", "")}
        with mock.patch.object(port.dq4block, "Map", lambda prg, g, n: source), \
                mock.patch.object(port, "edit_cells", lambda src, g, n: None), \
                mock.patch.object(port, "sheet_art", lambda prg, t: art):
            self.assertEqual(port.bed_cells(b"", 0x10, 1), {(0, 0), (1, 1)})

    def test_edit_cells_runs_before_the_art_is_read(self):
        order = []
        source = block_source(2, 1, [[0, 0]])
        with mock.patch.object(port.dq4block, "Map", lambda prg, g, n: source), \
                mock.patch.object(port, "edit_cells", lambda src, g, n: order.append(("edit", g, n))), \
                mock.patch.object(port, "sheet_art", lambda prg, t: order.append("art") or {}):
            self.assertEqual(port.bed_cells(b"", 0x11, 2), set())
        self.assertEqual(order, [("edit", 0x11, 2), "art"])


class FcPeopleTest(unittest.TestCase):
    NIGHT_REC = bytes([0x00, 0, 0x32, 1, 0, 0, 0, 3])
    HIDDEN = bytes([0x00, 0, 0x00, 0, 9, 9, 9, 9])

    def people(self, night, flags=None):
        seen = {}

        def npc_list(prg, group, number, night, ram=None):
            seen["ram"] = ram
            return [self.NIGHT_REC, self.HIDDEN]
        patches = (mock.patch.object(port.dq4talk, "npc_list", npc_list),
                   mock.patch.object(port.dq4talk, "pos", lambda rec, night: (4, 5)),
                   mock.patch.object(port.dq4talk, "talk_id", lambda rec, night: 77),
                   mock.patch.object(port.dq4talk, "sprite", lambda rec, night: 0x94),
                   mock.patch.object(port.dq4talk, "predict", lambda prg, talk, state: [talk, None]),
                   mock.patch.object(port.dq4npcblock, "hidden_on_entry", lambda rec, night: rec == self.HIDDEN),
                   mock.patch.object(port, "fc_blocks", lambda prg, g, n, night, ram: [(5, 0x8000), (5, 0x8000)]),
                   mock.patch.object(port.dq4npcblock, "walk_interval", lambda prg, bank, body, step: step),
                   mock.patch.object(port, "chapter", lambda group: 2))
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return port.fc_people(b"", 0x10, 1, night, flags), seen

    def test_day_record_reads_step_from_the_high_nibble_and_facing_from_byte_three(self):
        people, seen = self.people(False)
        self.assertEqual(people, [{"x": 4, "y": 5, "facing": "right", "interval": 3, "picture": 0x14, "talk": 77,
                                   "shows": [77, None]}])
        self.assertIsNone(seen["ram"])

    def test_night_record_reads_step_from_the_low_nibble_and_facing_from_byte_seven(self):
        people, _ = self.people(True)
        self.assertEqual((people[0]["facing"], people[0]["interval"]), ("left", 2))

    def test_event_flags_pick_the_list_for_that_state(self):
        _, seen = self.people(False, {0x6283: 0x80})
        self.assertEqual(seen["ram"][0x6283], 0x80)
        self.assertEqual(seen["ram"][0x615A], 1)

    def test_hidden_people_are_listed_by_dq5_map_and_time(self):
        groups = {"a": (0x36, 1), "b": (0x36, 0), "c": (0x37, 0)}
        recs = {False: [self.HIDDEN, self.NIGHT_REC], True: [self.NIGHT_REC, self.HIDDEN]}
        with mock.patch.object(port, "GROUPS", groups), \
                mock.patch.object(port, "fc_map", lambda prg, g, n: (g + 0x10, n)), \
                mock.patch.object(port, "has_people", lambda fc_group: fc_group != 0x47), \
                mock.patch.object(port.dq4talk, "npc_list", lambda prg, g, n, night: recs[night]), \
                mock.patch.object(port.dq4talk, "talk_id", lambda rec, night: 9 if night else 8), \
                mock.patch.object(port.dq4talk, "pos", lambda rec, night: (1, 2)), \
                mock.patch.object(port.dq4npcblock, "hidden_on_entry", lambda rec, night: rec == self.HIDDEN):
            found = port.hidden_people(b"")
        self.assertEqual(found, [("36/00", False, 8, 1, 2), ("36/00", True, 9, 1, 2),
                                 ("36/01", False, 8, 1, 2), ("36/01", True, 9, 1, 2)])


class PortWithMocksTest(unittest.TestCase):
    A = {"x": 3, "y": 4, "facing": "down", "interval": 2, "picture": 0x14, "talk": 1, "shows": [100, None]}
    B = {"x": 5, "y": 6, "facing": "up", "interval": 0, "picture": 0x11, "talk": 2, "shows": [200]}
    FAR = {"x": 70, "y": 1, "facing": "up", "interval": 0, "picture": 0x11, "talk": 3, "shows": [300]}
    SELLER = {"x": 8, "y": 8, "facing": "left", "interval": 3, "picture": 0x17, "talk": 4, "shows": [400]}
    SLEEPER = {"x": 10, "y": 10, "facing": "down", "interval": 3, "picture": 0x12, "talk": 5, "shows": [500]}
    MERCHANT = {"x": 12, "y": 12, "facing": "down", "interval": 0, "picture": 0x17, "talk": 6,
                "shows": [600, port.dq4talk.SERVICE + 1]}
    GROUPS = {"town": (0x36, 1)}

    def run_port(self, people, goods=True, shops=None, with_people=True, alt=(), groups=None, picture_table=None):
        by_time = people if isinstance(people, dict) else {False: people, True: people[:1]}
        calls = {}

        def fc_people(prg, group, number, night, flags=None):
            calls.setdefault("flags", []).append(flags)
            return by_time[night]
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            dq5, dq4 = Path(tmp) / "dq5.sfc", Path(tmp) / "dq4.nes"
            dq5.write_bytes(b"5")
            dq4.write_bytes(b"4")
            stack.enter_context(mock.patch.object(port, "GROUPS", groups or self.GROUPS))
            stack.enter_context(mock.patch.object(port.dq4shopport.dq5item, "Rom", lambda raw: raw))
            stack.enter_context(mock.patch.object(port.dq4shopport, "dq5_items", lambda rom: {"items": 1}))
            stack.enter_context(mock.patch.object(port.ines, "prg", lambda raw: raw))
            stack.enter_context(mock.patch.object(port.dq4text, "Rom", lambda raw: raw))
            stack.enter_context(mock.patch.object(port, "first_talk", lambda: 0x900))
            stack.enter_context(mock.patch.object(port, "fc_map", lambda prg, g, n: (0x10 + g, n)))
            stack.enter_context(mock.patch.object(port, "has_people", lambda fc_group, with_people=True: with_people))
            stack.enter_context(mock.patch.object(port, "merchants", lambda prg, g, n, items: shops or {}))
            stack.enter_context(mock.patch.object(port, "bed_cells", lambda prg, g, n: {(10, 10)}))
            stack.enter_context(mock.patch.object(port, "fc_people", fc_people))
            stack.enter_context(mock.patch.object(port.dq4shopport, "has_goods", lambda *a: goods))
            stack.enter_context(mock.patch.object(port, "dq5_codes", lambda rom, shows: [sum(shows)]))
            stack.enter_context(mock.patch.object(dq4ch1event, "ALT_STATES", alt))
            if picture_table is not None:
                stack.enter_context(mock.patch.object(port, "PICTURES", picture_table))
            lists, messages, report = port.port(dq5, dq4, with_people)
        return lists, messages, report, calls

    def test_each_person_becomes_an_entry_of_its_time_with_the_matching_template(self):
        lists, messages, report, _ = self.run_port([self.A, self.B, self.FAR])
        (listing,) = lists
        self.assertEqual(listing["map"], "36/01")
        day = [e for e in listing["entries"] if e["time"] == "day"]
        night = [e for e in listing["entries"] if e["time"] == "night"]
        self.assertEqual([e["from"] for e in day], [port.WALK, port.STAND])
        self.assertEqual(day[0]["fields"], {"x": 6, "y": 9, "facing": "down", "talk": 0x900, "gfx": port.PICTURES[0x14],
                                            "layer": 0, "interval": port.WALK_FASTEST})
        self.assertEqual(day[1]["fields"]["talk"], 0x901)
        self.assertEqual(day[1]["fields"]["gfx"], port.PICTURES[0x11])
        self.assertEqual(len(night), 1)

    def test_same_lines_share_one_message_numbered_in_order_of_first_use(self):
        _, messages, report, _ = self.run_port([self.A, self.B, self.FAR])
        f = port.FIRST_MESSAGE
        self.assertEqual(messages, [{"id": f, "codes": [100]}, {"id": f + 1, "codes": [200]}])
        self.assertEqual([m["id"] for m in messages], [f, f + 1])
        day_a, night_a = [p for p in report["36/01"] if p["talk"] == 1]
        self.assertEqual((day_a["night"], night_a["night"]), (False, True))
        self.assertEqual(day_a["message"], night_a["message"])
        self.assertEqual(day_a["message"], f"{f:03X}")

    def test_far_off_people_are_left_out(self):
        _, _, report, _ = self.run_port([self.A, self.FAR])
        self.assertNotIn(3, [p["talk"] for p in report["36/01"]])

    def test_a_seller_takes_the_service_talk_and_stands_still(self):
        lists, messages, report, _ = self.run_port([self.SELLER], shops={(8, 8, False): 5, (8, 8, True): 5})
        entry = lists[0]["entries"][0]
        self.assertEqual((entry["from"], entry["fields"]["talk"], entry["fields"]["interval"]), (port.STAND, 5, 0))
        self.assertEqual(messages, [])
        self.assertEqual((report["36/01"][0]["service"], report["36/01"][0]["message"]), (5, None))

    def test_a_person_with_a_service_line_and_goods_uses_the_service_talk(self):
        lists, _, report, _ = self.run_port([self.MERCHANT], goods=True)
        self.assertEqual(lists[0]["entries"][0]["fields"]["talk"], port.dq4shopport.SERVICE[1])

    def test_a_seller_without_goods_keeps_the_lines_before_the_service(self):
        _, messages, report, _ = self.run_port([self.MERCHANT], goods=False)
        self.assertEqual(messages, [{"id": port.FIRST_MESSAGE, "codes": [600]}])
        self.assertIsNone(report["36/01"][0]["service"])

    def test_a_person_with_no_lines_says_the_placeholder(self):
        silent = {**self.B, "shows": [None]}
        _, messages, _, _ = self.run_port([silent])
        self.assertEqual(messages, [{"id": port.FIRST_MESSAGE, "codes": port.nothing_codes()}])

    def test_a_person_on_a_bed_lies_half_a_block_right_and_one_cell_up(self):
        lists, _, _, _ = self.run_port([self.SLEEPER])
        entry = lists[0]["entries"][0]
        self.assertEqual(entry["from"], port.LIE)
        self.assertEqual(entry["fields"]["x"], 21)
        self.assertEqual(entry["fields"]["y"], 20)
        self.assertEqual((entry["fields"]["facing"], entry["fields"]["interval"]), ("right", 0))

    def test_beds_only_count_in_the_prologue_and_chapter_one_groups(self):
        lists, _, _, _ = self.run_port([self.SLEEPER], groups={"far": (0x40, 1)})
        entry = lists[0]["entries"][0]
        self.assertEqual((entry["from"], entry["fields"]["x"], entry["fields"]["y"]), (port.WALK, 20, 21))

    def test_a_picture_without_a_dq5_counterpart_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "FC picture 12 has no DQ5 picture"):
            self.run_port([self.SLEEPER], picture_table={0x14: 0x29})

    def test_nds_looks_override_the_picture_by_map_and_first_line(self):
        person = {**self.B, "shows": [1932]}
        lists, _, _, _ = self.run_port([person], groups={"36/00": (0x36, 0)})
        self.assertEqual(lists[0]["entries"][0]["fields"]["gfx"], 0x9C)

    def test_without_people_no_entry_is_made(self):
        lists, messages, report, _ = self.run_port([self.A], with_people=False)
        self.assertEqual((lists[0]["entries"], messages, report["36/01"]), ([], [], []))

    def test_later_state_lists_are_named_and_reported_with_their_flags(self):
        alt = (("late", {0x6283: 0x80}, ("36/00",)),)
        lists, _, report, calls = self.run_port([self.A], alt=alt)
        self.assertEqual([l.get("map") or l.get("name") for l in lists], ["36/01", "late-3600"])
        self.assertIn("late-3600", report)
        self.assertIn({0x6283: 0x80}, calls["flags"])


class MainTest(unittest.TestCase):
    def test_main_writes_lists_messages_and_report_and_prints_counts(self):
        out = io.StringIO()
        result = ([{"map": "36/00", "entries": []}], [{"id": 1, "codes": [2]}], {"36/00": [{"a": 1}, {"a": 2}]})
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out), \
                mock.patch.object(port, "port", lambda dq5, dq4: result), \
                mock.patch("sys.argv", ["dq4npcport.py", "--out", str(Path(tmp) / "a" / "b")]):
            port.main()
            folder = Path(tmp) / "a" / "b"
            self.assertEqual(json.loads((folder / "npc-lists.json").read_text()), result[0])
            self.assertEqual(json.loads((folder / "messages.json").read_text()),
                             {"format": "dq5text/1", "messages": result[1]})
            self.assertEqual(json.loads((folder / "report.json").read_text()), result[2])
        self.assertEqual(json.loads(out.getvalue()), {"36/00": 2, "messages": 1})


class PlantedPeopleTest(unittest.TestCase):
    def test_night_facing_from_picture_byte(self):
        # Made-up list 02/00 in bank 05: two day-and-night records (head 8 or 7 bytes, then two one-byte blocks
        # 2B: wander, so the record's step interval is the walking one).
        # F 1E has bit0 off, so at night the facing is byte 7 (03 = left), not byte 3 (02 = down); F 1F has bit0
        # on and keeps byte 3 (01 = right). Talk 01 is a service, so no script is read.
        sys.path.insert(0, str(ROOT / "fc" / "dq4" / "tools"))
        import dq4map
        prg = bytearray(0x80000)
        bank = dq4map.NPC_BANK * 0x4000
        prg[bank + 4:bank + 6] = (0x8100).to_bytes(2, "little")
        records = bytes.fromhex("1E 00 35 02 01 12 34 03 01 2B 01 2B" "1F 00 47 01 01 13 35 01 2B 01 2B" "00")
        prg[bank + 0x100:bank + 0x100 + len(records)] = records
        people = port.fc_people(bytes(prg), 0x02, 0, True)
        self.assertEqual([(p["x"], p["y"], p["facing"], p["interval"]) for p in people],
                         [(0x12, 0x34, "left", 5), (0x13, 0x35, "right", 7)])
        day = port.fc_people(bytes(prg), 0x02, 0, False)
        self.assertEqual([(p["facing"], p["interval"]) for p in day], [("down", 3), ("right", 4)])

    def test_a_person_whose_block_never_walks_stands(self):
        # Day-only records with interval 1: an event wait then a message and 2A (stand), and an empty block.
        # FC keeps them in place; ported they used to wander at DQ5 interval 1, a step every few frames.
        sys.path.insert(0, str(ROOT / "fc" / "dq4" / "tools"))
        import dq4map
        prg = bytearray(0x80000)
        bank = dq4map.NPC_BANK * 0x4000
        prg[bank + 4:bank + 6] = (0x8100).to_bytes(2, "little")
        records = bytes.fromhex("10 00 10 02 01 12 34 06 8A 22 26 06 03 2A" "10 00 10 02 01 13 34 00"
                                "10 00 40 02 01 14 34 01 2B" "00")
        prg[bank + 0x100:bank + 0x100 + len(records)] = records
        people = port.fc_people(bytes(prg), 0x02, 0, False)
        self.assertEqual([p["interval"] for p in people], [0, 0, 4])


@unittest.skipUnless(DQ4.is_file(), "local source ROM not present")
class CodesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "fc" / "dq4" / "tools"))
        import dq4text
        cls.rom = dq4text.Rom(DQ4.read_bytes())

    def test_dakuten_and_pages(self):
        # 05E1: 「バトラン{3D}トおうは …{WAIT}＊「{LINE}しかし …」: ド from the mark, one page for {WAIT}＊「{LINE}.
        codes = port.dq5_codes(self.rom, [0x05E1])
        text = "".join(port.REVERSE.get(c, "|") for c in codes[:12])
        self.assertTrue(text.startswith("バトランドおうは"), text)
        self.assertEqual(codes[-1], port.END)
        first_page = codes.index(port.PAGE)
        self.assertEqual(port.REVERSE[codes[first_page + 1]], "し")

    def test_joined_messages_get_one_page(self):
        # 05E3 then 05E4, which starts with {NOINDENT}{WAIT}＊「.
        codes = port.dq5_codes(self.rom, [0x05E3, 0x05E4])
        self.assertEqual(codes.count(port.PAGE), 1)
        self.assertNotIn(port.PAGE, (codes[0], codes[-2]))

    def test_no_empty_page(self):
        # 0785 ends with a page, then 060A follows.
        codes = port.dq5_codes(self.rom, [0x0785, 0x060A])
        self.assertFalse(any(a == b == port.PAGE for a, b in zip(codes, codes[1:])))

    def test_leading_speaker_mark_dropped(self):
        # 048D starts with ＊「; DQ5 adds the mark itself (24:8AF9).
        codes = port.dq5_codes(self.rom, [0x048D])
        self.assertNotEqual(port.REVERSE.get(codes[0]), "＊")
        self.assertEqual(port.REVERSE[codes[0]], "せ")


@unittest.skipUnless(DQ4.is_file(), "local source ROM not present")
class NightFacingTest(unittest.TestCase):
    def test_night_facing_from_picture_byte(self):
        sys.path.insert(0, str(ROOT / "fc" / "dq4" / "tools"))
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        people = port.fc_people(prg, 0x02, 0, True)
        # Night record 1A 05 80 26 16 93 97 25 21 25 (F bit0 off) stands at (21,25): facing from byte 7
        # (25 & 3 = right), not byte 3 (26 & 3 = down).
        person = next(p for p in people if (p["x"], p["y"]) == (0x21, 0x25))
        self.assertEqual(person["facing"], "right")


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class PortTest(unittest.TestCase):
    def test_talk_numbers_show_messages(self):
        lists, messages, report = port.port(str(DQ5), str(DQ4))
        ids = [m["id"] for m in messages]
        self.assertEqual(ids, list(range(port.FIRST_MESSAGE, port.FIRST_MESSAGE + len(ids))))
        shows = {int(s["talk"], 16): s["body"][0].get("id") for s in port.talk_doc(messages)["scripts"]}
        for entries in lists:
            for e in entries["entries"]:
                talk = e["fields"]["talk"]
                if talk <= 6:  # a DQ5 shop, inn, church or deposit (06:DBD2)
                    self.assertEqual(e["fields"]["interval"], 0)
                    continue
                self.assertGreaterEqual(talk, port.first_talk())
                self.assertIn(int(shows[talk], 16), ids)
        for people in report.values():
            for p in people:
                if p["message"] is not None:
                    self.assertEqual(shows[p["dq5"]["talk"]], p["message"])

    def test_without_people(self):
        # dq4groupbuild.py --no-people: the ROM dq4groupcheck walks, where wandering people would block stairs.
        lists, messages, report = port.port(str(DQ5), str(DQ4), with_people=False)
        self.assertEqual(messages, [])
        self.assertTrue(lists and all(not e["entries"] for e in lists))
        self.assertTrue(report and all(not people for people in report.values()))


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class HiddenPeopleTest(unittest.TestCase):
    def test_people_fc_hides_on_entry_are_not_ported(self):
        # エンドール's colosseum stands (FC 04/07): six records hide at once and stay hidden. Ported as wanderers
        # they would walk onto the stair (22,11), the only way down to 04/0E.
        _, _, report = port.port(str(DQ5), str(DQ4))
        stands = {(0x15, 0x09), (0x16, 0x09), (0x17, 0x0A), (0x17, 0x0B), (0x16, 0x0C), (0x15, 0x0C)}
        self.assertFalse(stands & {(p["x"], p["y"]) for p in report["40/07"] if not p["night"]})
        self.assertTrue(report["40/07"])

    def test_no_ported_event_looks_for_a_left_out_person(self):
        # FC shows such a person only from event code (it clears $7020 bit7 of the slot); ported, it is not in the
        # DQ5 list at all. An event port that touches its map must first bring it back as a list of its own.
        import re
        from kr_patch.fc import ines
        left_out = port.hidden_people(ines.prg(DQ4.read_bytes()))
        self.assertEqual({m for m, *_ in left_out}, {"3D/04", "40/07", "41/03"})
        tools = Path(__file__).resolve().parent
        touched = set()
        for name in ("dq4ch1event.py", "dq4ch2event.py", "dq4chapter1.py"):
            touched |= set(re.findall(r"['\"]([0-9A-F]{2}/[0-9A-F]{2})['\"]", (tools / name).read_text(encoding="utf-8")))
        self.assertFalse(touched & {m for m, *_ in left_out}, sorted(touched & {m for m, *_ in left_out}))


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class SleeperTalkTest(unittest.TestCase):
    """A sleeper lies half a block right and up of its FC cell. DQ5 answers beside the bed's right block (the head)
    and, with dq4sleepertalk, beside the left block (the foot) where FC talks to it. Every sleeper must have a free
    walkable FC cell beside each, and dq4npccheck must talk from both."""

    def test_every_sleeper_can_be_talked_to(self):
        import dq4block
        import dq4npccheck
        from dq4groupbuild import cell, fc_map
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        _, _, report = port.port(str(DQ5), str(DQ4))
        sleepers = 0
        for m, people in report.items():
            if "/" not in m:
                continue
            group, number = (int(v, 16) for v in m.split("/"))
            for p in people:
                d = p["dq5"]
                if (d["x"], d["y"]) == cell(p["x"], p["y"]):
                    self.assertEqual(dq4npccheck.talk_cell(p), (p["x"], p["y"]))
                    continue
                sleepers += 1
                self.assertEqual((d["x"], d["y"]), (2 * p["x"] + 1, 2 * p["y"]), (m, p))
                self.assertEqual(dq4npccheck.talk_cell(p), (p["x"] + 1, p["y"]))
                source = dq4block.Map(prg, *fc_map(prg, group, number))
                now = {(q["x"], q["y"]) for q in people if q["night"] == p["night"]}
                self.assertIsNotNone(dq4npccheck.talk_side(source, p["x"] + 1, p["y"], now), (m, p))
                self.assertIsNotNone(dq4npccheck.talk_side(source, p["x"], p["y"], now), (m, p))
        self.assertGreater(sleepers, 0)


    def test_the_hook_adds_exactly_the_fc_foot_sides(self):
        # Over every ported map, every free walkable hero cell and facing: the cells where the hook makes 05:84FE
        # find a sleeper (dq4sleepertalk.lying_target, a model of the code) are the FC cells beside the foot,
        # facing it, and each finds the sleeper of that bed. dq4npccheck's -foot scenes check it in the ROM.
        import dq4block
        import dq4npccheck
        import dq4sleepertalk
        from dq4groupbuild import cell, fc_map
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        _, _, report = port.port(str(DQ5), str(DQ4))
        step = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        sleepers = 0
        for m, people in report.items():
            if "/" not in m:
                continue
            group, number = (int(v, 16) for v in m.split("/"))
            source = None
            for night in (False, True):
                now = [p for p in people if p["night"] == night]
                lying = {(p["dq5"]["x"], p["dq5"]["y"]): p for p in now
                         if (p["dq5"]["x"], p["dq5"]["y"]) != cell(p["x"], p["y"])}
                if not lying:
                    continue
                sleepers += len(lying)
                source = source or dq4block.Map(prg, *fc_map(prg, group, number))
                taken = {(p["x"], p["y"]) for p in now}
                gained, want = set(), set()
                for fy in range(source.h):
                    for fx in range(source.w):
                        if not dq4npccheck.walkable(source, fx, fy) or (fx, fy) in taken:
                            continue
                        for d, (dx, dy) in step.items():
                            before = dq4sleepertalk.lying_target(*cell(fx, fy), d, lying, hooked=False)
                            after = dq4sleepertalk.lying_target(*cell(fx, fy), d, lying)
                            foot = next((c for c, p in lying.items() if (p["x"], p["y"]) == (fx + dx, fy + dy)), None)
                            if foot is not None:
                                want.add((fx, fy, d, foot))
                            if before is not None:
                                self.assertEqual(after, before, (m, fx, fy, d))
                            elif after is not None:
                                gained.add((fx, fy, d, after))
                self.assertEqual(gained, want, (m, night))
        self.assertGreater(sleepers, 0)


class Dq5IntervalTest(unittest.TestCase):
    def test_walkers_keep_to_dq5_townsfolk_intervals(self):
        self.assertEqual([port.dq5_interval(n) for n in (0, 1, 2, 4, 5, 8, 15)], [0, 8, 8, 8, 10, 15, 15])


@unittest.skipUnless(DQ4.is_file(), "local source ROM not present")
class SantheimThroneRoomTest(unittest.TestCase):
    """FC 01/01(2장 3D/01): 병사 둘(레코드 01·04)은 이벤트를 기다리며 서 있고 레코드 간격만 1 이다."""

    def test_fc_walking_intervals(self):
        prg = port.ines.prg(DQ4.read_bytes())
        day = port.fc_people(prg, 0x01, 0x01, False)
        self.assertEqual([((p["x"], p["y"]), p["interval"]) for p in day],
                         [((13, 13), 4), ((10, 16), 0), ((20, 4), 2), ((12, 10), 8), ((9, 7), 0), ((22, 9), 0)])
        night = port.fc_people(prg, 0x01, 0x01, True)
        self.assertEqual([p["interval"] for p in night], [4, 0, 2, 8])

    def test_no_ported_person_walks_faster_than_dq5_townsfolk(self):
        prg = port.ines.prg(DQ4.read_bytes())
        for g, n in ((0x01, 0x00), (0x01, 0x01), (0x02, 0x00), (0x02, 0x01)):
            for night in (False, True):
                for p in port.fc_people(prg, g, n, night):
                    self.assertIn(port.dq5_interval(p["interval"]),
                                  {0, *range(port.WALK_FASTEST, port.WALK_SLOWEST + 1)}, (g, n, night, p))


if __name__ == "__main__":
    unittest.main()
