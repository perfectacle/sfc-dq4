"""Message allocation; with rom/dq4.nes, the FC text -> DQ5 codes rule; with both ROMs, the ported people and
messages."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
        events = ch1 + len(dq4ch2event.TALKS)
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


class PlantedPeopleTest(unittest.TestCase):
    def test_night_facing_from_picture_byte(self):
        # Made-up list 02/00 in bank 05: two day-and-night records (head 8 or 7 bytes, then two empty blocks).
        # F 1E has bit0 off, so at night the facing is byte 7 (03 = left), not byte 3 (02 = down); F 1F has bit0
        # on and keeps byte 3 (01 = right). Talk 01 is a service, so no script is read.
        sys.path.insert(0, str(ROOT / "fc" / "dq4" / "tools"))
        import dq4map
        prg = bytearray(0x80000)
        bank = dq4map.NPC_BANK * 0x4000
        prg[bank + 4:bank + 6] = (0x8100).to_bytes(2, "little")
        records = bytes.fromhex("1E 00 35 02 01 12 34 03 00 00" "1F 00 47 01 01 13 35 00 00" "00")
        prg[bank + 0x100:bank + 0x100 + len(records)] = records
        people = port.fc_people(bytes(prg), 0x02, 0, True)
        self.assertEqual([(p["x"], p["y"], p["facing"], p["interval"]) for p in people],
                         [(0x12, 0x34, "left", 5), (0x13, 0x35, "right", 7)])
        day = port.fc_people(bytes(prg), 0x02, 0, False)
        self.assertEqual([(p["facing"], p["interval"]) for p in day], [("down", 3), ("right", 4)])


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


if __name__ == "__main__":
    unittest.main()
