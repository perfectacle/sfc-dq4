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
                                                      0x61: "외톨이 메탈 갑옷", 0x89: "금 머리장식", 0x8C: "깃털 모자",
                                                  0x37: "미소의 지팡이", 0x84: "외톨이 메탈 방패", 0xAE: "운의 씨앗",
                                                      0x6E: "핑크 레오타드", 0xC4: "정적의 구슬", 0xC1: "승선권",
                                                      0xC2: "말똥",
                                                      0xC6: "황금의 팔찌", 0xBE: "지저귐의 꿀",
                                                      0xBB: "도시락", 0xBC: "철 금고", 0xBD: "은의 여신상",
                                                      0xC3: "왕자의 편지", 0xCA: "왕의 편지", 0xCB: "불가사의의 피리"})


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
        """2장 사건 물건: 이름은 FC 것, 물건 표는 ゴールドオーブ 것. 필드에서 쓰면 FC 필드 효과 비트가 꺼진 おうごんのうでわ 는
        いのちのいし 처리기(「아무 일도」 18E), 켜진 さえずりのみつ 는 ゴールドオーブ 것(「여기서는」 1A8)."""
        import dq5chest
        rom = self._patched()
        self.assertEqual(dq5chest.item_name(rom, 0xC6), "おうごんのうでわ")
        self.assertEqual(dq5chest.item_name(rom, 0xBE), "さえずりのみつ")
        for item, handler in ((0xC6, 0x8BB9), (0xBE, 0x8BE4)):
            self.assertEqual([rom.u8(t + item) for t in dq4itemport.RECORD], [0x1C, 0x04, 0x53, 0x07])
            self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (item - 0xA1) * 2), handler)

    def test_chapter_three_story_items(self):
        """3장 사건 물건: BB~BD 는 이름을 한 줄로 다시 써(합 26바이트 그대로) 뒤 물건 이름이 그대로. 금고·여신상·편지 둘은
        물건 표가 ゴールドオーブ 것이고, 필드 쓰기는 FC 필드 효과 비트대로(금고·여신상은 いのちのいし 18E, 편지는
        ゴールドオーブ 1A8). 도시락은 FC 에서 약초와 같은 물건이라 약초 기록·처리기에 10G."""
        import dq5chest
        import dq5item
        rom = self._patched()
        original = dq5item.Rom(DQ5.read_bytes())
        names = {0xBC: ("てつのきんこ", 0x8BB9), 0xBD: ("ぎんのめがみぞう", 0x8BB9), 0xC3: ("おうじのてがみ", 0x8BE4),
                 0xCA: ("おうのてがみ", 0x8BE4)}
        for item, (name, handler) in names.items():
            self.assertEqual(dq5chest.item_name(rom, item), name)
            self.assertEqual([rom.u8(t + item) for t in dq4itemport.RECORD], [0x1C, 0x04, 0x53, 0x07])
            self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (item - 0xA1) * 2), handler)
        self.assertEqual(dq5chest.item_name(rom, dq4itemport.BENTO), "おべんとう")
        self.assertEqual([rom.u8(t + dq4itemport.BENTO) for t in dq4itemport.RECORD[1:]],
                         [original.u8(t + 0xA1) for t in dq4itemport.RECORD[1:]])
        self.assertEqual(rom.u8(dq4itemport.PRICE_SCALE + dq4itemport.BENTO), original.u8(dq4itemport.PRICE_SCALE + 0xA1))
        self.assertEqual(rom.u8(dq4itemport.PRICE_BASE + dq4itemport.BENTO), 10)
        self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (dq4itemport.BENTO - 0xA1) * 2),
                         original.u16(dq4itemport.USE_HANDLERS))
        # あやかしのふえ(CB)는 DQ5 피리 C7 의 기록과 필드 쓰기를 빌린다(FC: 쓰면 「…ふいた。」, 남음)
        self.assertEqual(dq5chest.item_name(rom, dq4itemport.FLUTE), "あやかしのふえ")
        self.assertEqual([rom.u8(t + dq4itemport.FLUTE) for t in dq4itemport.RECORD],
                         [original.u8(t + 0xC7) for t in dq4itemport.RECORD])
        self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (dq4itemport.FLUTE - 0xA1) * 2),
                         original.u16(dq4itemport.USE_HANDLERS + (0xC7 - 0xA1) * 2))
        for item in (0xBA, 0xBF, 0xC5, 0xC9):
            self.assertEqual(dq5chest.item_name(rom, item), dq5chest.item_name(original, item))
        # 4장 셋: 정적의 구슬은 ドラム 자리, 승선권·말똥은 C1·C2 를 한 줄로(7 + 6 = 8 + 5)
        self.assertEqual([dq5chest.item_name(rom, i) for i in (0xC4, 0xC1, 0xC2)],
                         ["せいじゃくのたま", "じょうせんけん", "うまのふん"])
        self.assertEqual(dq4itemport.name_at(rom, 0xBE), dq4itemport.name_at(original, 0xBE))

    def test_thief_key(self):
        """とうぞくのカギ 는 DQ5 의 B7 그대로, 비어 있던 물건 표를 まほうのカギ 것으로(도구 칸, 팔 수 없음)."""
        import dq5chest
        rom = self._patched()
        self.assertEqual(dq5chest.item_name(rom, 0xB7), "とうぞくのカギ")
        self.assertEqual([rom.u8(t + 0xB7) for t in dq4itemport.RECORD], [0x1C, 0x04, 0xD8, 0x87])
        self.assertEqual(rom.u16(dq4itemport.USE_HANDLERS + (0xB7 - 0xA1) * 2), 0x8E43)


if __name__ == "__main__":
    unittest.main()
