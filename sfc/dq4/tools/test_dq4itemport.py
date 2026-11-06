"""FC prices on the DQ5 item table and the borrowed てつのやり slot."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4itemport  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


class PriceTest(unittest.TestCase):
    def test_smallest_scale(self):
        self.assertEqual(dq4itemport.encode_price(30), (30, 0))
        self.assertEqual(dq4itemport.encode_price(880), (88, 1))
        self.assertEqual(dq4itemport.encode_price(9800), (98, 2))
        self.assertEqual(dq4itemport.encode_price(15000), (150, 2))
        self.assertEqual(dq4itemport.encode_price(35000), (35, 3))

    def test_unencodable(self):
        with self.assertRaises(ValueError):
            dq4itemport.encode_price(1234)

    def test_korean_name(self):
        self.assertEqual(dq4itemport.korean_names(), {0x01: "철 창", 0x34: "정의의 주판", 0x4E: "철의 앞치마",
                                                      0x61: "외톨이 메탈 갑옷", 0xC6: "황금의 팔찌", 0xBE: "지저귐의 꿀"})


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class RomTest(unittest.TestCase):
    def test_borrowed_name_reads_back(self):
        import dq5chest
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5.read_bytes())
        writes = dq4itemport.writes(rom, ines.prg(DQ4.read_bytes()), {})
        data = bytearray(DQ5.read_bytes())
        for w in writes:
            bank, addr = (int(v, 16) for v in w["at"].split(":"))
            o = bank * 0x8000 + (addr & 0x7FFF)
            new = bytes.fromhex(w["hex"])
            self.assertEqual(bytes(data[o:o + len(new)]), bytes.fromhex(w["orig"]))
            data[o:o + len(new)] = new
        patched = dq5item.Rom(bytes(data))
        self.assertEqual(dq5chest.item_name(patched, 0x01), "てつのやり")
        self.assertEqual(dq5item.price(patched, 0x01), 880)
        self.assertEqual(dq5item.field(patched, 5, 0x01), 28)
        # 엔돌 가게의 DQ5 에 없는 물건 셋
        self.assertEqual([dq5chest.item_name(patched, i) for i in (0x34, 0x4E, 0x61)],
                         ["せいぎのそろばん", "てつのまえかけ", "はぐれメタルよろい"])
        self.assertEqual([dq5item.field(patched, 5, i) for i in (0x34, 0x4E, 0x61)], [35, 32, 95])

    def _patched(self):
        import dq5item
        from kr_patch.fc import ines
        rom = dq5item.Rom(DQ5.read_bytes())
        data = bytearray(DQ5.read_bytes())
        for w in dq4itemport.writes(rom, ines.prg(DQ4.read_bytes()), {}):
            bank, addr = (int(v, 16) for v in w["at"].split(":"))
            o = bank * 0x8000 + (addr & 0x7FFF)
            data[o:o + len(bytes.fromhex(w["hex"]))] = bytes.fromhex(w["hex"])
        return dq5item.Rom(bytes(data))

    def test_story_items(self):
        """2장 사건 물건: 이름은 FC 것, 물건 표와 필드에서 쓰기는 ゴールドオーブ 것(쓰면 「何も おこらなかった」)."""
        import dq5chest
        rom = self._patched()
        self.assertEqual(dq5chest.item_name(rom, 0xC6), "おうごんのうでわ")
        self.assertEqual(dq5chest.item_name(rom, 0xBE), "さえずりのみつ")
        for item in (0xC6, 0xBE):
            self.assertEqual([rom.u8(t + item) for t in dq4itemport.RECORD], [0x1C, 0x04, 0x53, 0x07])
            self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (item - 0xA1) * 2), 0x8BE4)

    def test_thief_key(self):
        """とうぞくのカギ 는 DQ5 의 B7 그대로, 비어 있던 물건 표를 まほうのカギ 것으로(도구 칸, 팔 수 없음)."""
        import dq5chest
        rom = self._patched()
        self.assertEqual(dq5chest.item_name(rom, 0xB7), "とうぞくのカギ")
        self.assertEqual([rom.u8(t + 0xB7) for t in dq4itemport.RECORD], [0x1C, 0x04, 0xD8, 0x87])
        self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (0xB7 - 0xA1) * 2), 0x8E43)


if __name__ == "__main__":
    unittest.main()
