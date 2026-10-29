"""With rom/dq4.nes, the FC text -> DQ5 codes rule; with both ROMs, the ported people and messages."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4npcport as port  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


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


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class PortTest(unittest.TestCase):
    def test_talk_numbers_show_messages(self):
        lists, messages, report = port.port(str(DQ5), str(DQ4))
        ids = {m["id"] for m in messages}
        for entries in lists:
            for e in entries["entries"]:
                talk = e["fields"]["talk"]
                self.assertGreaterEqual(talk, port.TALK_FIRST)
                self.assertIn(talk + port.TALK_MESSAGE, ids)
        self.assertEqual(len(ids), len(messages))


if __name__ == "__main__":
    unittest.main()
