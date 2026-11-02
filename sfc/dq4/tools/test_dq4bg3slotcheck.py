import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(TOOLS), str(TOOLS.parents[1] / "dq5" / "tools")]

import dq4bg3slotcheck as check  # noqa: E402


def line(mp, slot, shown=None, nz=342, vsbuf=0):
    return check.parse_bg3(f"f00630 map {mp} 0725={slot:02X} shown={slot if shown is None else shown:02X} "
                           f"nz={nz} vsbuf={vsbuf} old=660")


class JudgeTest(unittest.TestCase):
    def test_expected_slot(self):
        self.assertEqual(check.expected_slot("02/00"), 0x3C)
        self.assertEqual(check.expected_slot("01/01"), 0x7C)
        self.assertEqual(check.expected_slot("00/0A"), 0x78)
        self.assertEqual(check.expected_slot("19/00"), 0x48)
        self.assertEqual(check.expected_slot("19/02"), 0x4C)

    def test_moved_slot_passes(self):
        self.assertEqual(check.judge("01/00", ("01/00", "cell"), [line("01/00", 0x7C)]), [])
        self.assertEqual(check.judge("17/00", ("17/00", "cell"), [line("17/00", 0x3C)]), [])

    def test_field_like_map_takes_the_field_slot(self):
        self.assertEqual(check.judge("04/0B", ("04/0B", "field"), [line("04/0B", 0x78)]), [])
        self.assertTrue(check.judge("04/0B", ("04/0B", "field"), [line("04/0B", 0x3C)]))

    def test_map_the_game_moves_on_to(self):
        records = [line("33/01", 0x3C), line("33/00", 0x3C)]
        self.assertEqual(check.judge("33/01", ("33/00", "cell"), records), [])

    def test_unmoved_or_broken_slot_fails(self):
        # A ROM without the move keeps the menu's 1C, as the overture stage does.
        here = ("02/00", "cell")
        self.assertTrue(check.judge("02/00", here, [line("02/00", 0x1C)]))
        self.assertTrue(check.judge("02/00", here, [line("02/00", 0x3C, shown=0x1C)]))
        self.assertTrue(check.judge("02/00", here, [line("02/00", 0x3C, nz=0)]))

    def test_buffer_mismatch_in_last_record_fails(self):
        here = ("02/00", "cell")
        self.assertTrue(check.judge("02/00", here, [line("02/00", 0x3C), line("02/00", 0x3C, vsbuf=1)]))
        self.assertEqual(check.judge("02/00", here, [line("02/00", 0x3C, vsbuf=1155), line("02/00", 0x3C)]), [])

    @staticmethod
    def screen(tile):
        """BG1 타일맵(워드 0800) 첫 칸만 tile 을 가리키는 모드 1 화면. 나머지 칸·BG2 는 타일 0, OBJ 는 화면 밖."""
        vram = bytearray(0x10000)
        vram[0x1000:0x1002] = tile.to_bytes(2, "little")
        oam = bytes([0, 240, 0, 0] * 128) + bytes(32)
        ppu = {"ppu.bgMode": "1", "ppu.oamMode": "0", "ppu.oamBaseAddress": "24576", "ppu.oamAddressOffset": "4096"}
        for layer, tm in ((0, 0x0800), (1, 0x0000)):
            key = f"ppu.layers[{layer}]."
            ppu.update({key + "tilemapAddress": str(tm), key + "chrAddress": "8192", key + "doubleWidth": "false",
                        key + "doubleHeight": "false", key + "largeTiles": "false"})
        return vram, oam, ppu

    def test_screen_damage_in_used_tiles_only(self):
        new, old = self.screen(0x256), self.screen(0x256)
        self.assertEqual(check.screen_damage(new, old), [])
        # 쓰지 않는 타일 300 의 차이는 앞 장면이 남긴 것일 수 있어 보지 않는다
        new[0][(0x2000 + 0x300 * 16) * 2] = 1
        self.assertEqual(check.screen_damage(new, old), [])
        # 화면 칸이 가리키는 타일 256 의 마지막 워드(전투 배경에서 0 으로 남던 자리)
        new[0][(0x2000 + 0x256 * 16 + 15) * 2] = 1
        self.assertEqual(check.screen_damage(new, old), [(0x456F, 0x456F, 1)])

    def test_unknown_mode_is_not_compared(self):
        new, old = self.screen(0x256), self.screen(0x256)
        new[2]["ppu.bgMode"] = "7"
        self.assertIsNone(check.screen_damage(new, old))

    def test_known_failures_must_keep_failing(self):
        self.assertEqual(check.verdict({"02/00": [], "1E/00": ["x"]}, ["1E/00"]), (True, []))
        ok, notes = check.verdict({"02/00": [], "1E/00": []}, ["1E/00"])
        self.assertFalse(ok)
        self.assertTrue(notes)
        self.assertFalse(check.verdict({"02/00": ["x"]}, [])[0])
        self.assertFalse(check.verdict({"02/00": []}, ["1E/00"])[0])

    def test_not_arrived_fails(self):
        self.assertEqual(check.judge("17/00", None, [line("17/00", 0x3C)]), ["도착 못 함"])
        self.assertTrue(check.judge("17/00", ("17/00", "cell"), [line("01/01", 0x7C)]))
        self.assertTrue(check.judge("17/00", ("17/00", "cell"), []))

    def test_start_map_goes_through_another_slot(self):
        mp = check.HOP.split(",")[0]
        self.assertNotEqual(check.expected_slot(mp), check.expected_slot(check.START_MAP["ship"]))


if __name__ == "__main__":
    unittest.main()
