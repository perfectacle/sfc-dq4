"""2장 첫머리: 깃발, 아리나 기록, 네이티브 주소, 주인공 그림 훅, 인물 목록."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch1event  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4prologue  # noqa: E402


def _flag(addr_mask):
    return addr_mask[0] - 0x7E2190, addr_mask[1]


class FlagTest(unittest.TestCase):
    def test_chapter2_flags_do_not_reuse_earlier_ones(self):
        earlier = {v for k, v in vars(dq4ch1event).items() if k.isupper() and isinstance(v, tuple) and len(v) == 2
                   and all(isinstance(x, int) for x in v) and v[0] < 0x80 and v[1] in (1, 2, 4, 8, 16, 32, 64, 128)}
        earlier |= {_flag(f) for f in (dq4prologue.box.PROLOGUE.flag, dq4prologue.box.CHAPTER1.flag)}
        for flag in (ev.CHAPTER2, ev.OPENING):
            self.assertNotIn(flag, earlier)
        self.assertNotEqual(ev.CHAPTER2, ev.OPENING)


class RecordTest(unittest.TestCase):
    def test_alena_starts_at_level_one_in_her_robe(self):
        hero = bytes(range(42))
        r = ev.alena_record(hero)
        self.assertEqual(len(r), 42)
        self.assertEqual(r[0], hero[0])                       # 인물 번호 00(주인공)은 그대로
        self.assertEqual((r[2], r[0xE], r[4], r[0x10], r[0x12]), (16, 16, 0, 0, 1))
        self.assertEqual((r[6], *r[7:0xB]), (7, 12, 8, 4, 1))
        self.assertEqual(r[0xB:0xE], bytes(3))
        self.assertEqual(r[0x14], 0x01)
        self.assertEqual(r[0x16:0x22], bytes((ev.SILK_ROBE,)) + b'\xff' * 11)
        self.assertEqual(r[0x23:0x26], bytes(3))

    def test_name_is_eight_bytes(self):
        b = ev.name_bytes(ev.ALENA_NAME)
        self.assertEqual(len(b), 8)
        self.assertEqual(b[6:], b'\x01\x01')


class NativeTest(unittest.TestCase):
    def test_addresses_do_not_depend_on_the_rom(self):
        code, at = ev.native(bytes(range(42)))
        self.assertEqual(at, ev.native()[1])
        self.assertEqual(code[:42], ev.alena_record(bytes(range(42))))
        self.assertLess((ev.CODE_AT & 0xFFFF) + len(code), 0x10000)

    def test_hero_picture_hook(self):
        data = bytearray(0x400000)
        o = ev.ch1.lorom(ev.HERO_PICTURE_AT)
        data[o:o + len(ev.HERO_PICTURE_ORIG)] = ev.HERO_PICTURE_ORIG
        original = bytearray(0x400000)
        out = ev.apply(bytes(data), bytes(original))
        _, at = ev.native()
        a = at['hero_picture']
        self.assertEqual(out[o:o + 5], bytes((0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0x60)))
        with self.assertRaises(SystemExit):
            ev.apply(bytes(0x400000), bytes(original))

    def test_event_moves_to_the_throne_room(self):
        _, at = ev.native()
        code, _ = ev.native()
        e = code[at['event'] - ev.CODE_AT:]
        g, n = (int(v, 16) for v in ev.THRONE.split('/'))
        self.assertEqual(e[4:12], bytes((0x90, g, n, *ev.START_CELL, 0x01, 0x80, 0xFF)))


class ListTest(unittest.TestCase):
    def test_only_the_king_becomes_the_opening_npc(self):
        king = {"from": {"list": "05:8857", "index": 6}, "time": "day",
                "fields": {"x": ev.KING_CELL[0], "y": ev.KING_CELL[1], "interval": 1}}
        other = {"from": {"list": "05:8857", "index": 6}, "time": "day", "fields": {"x": 2, "y": 3, "interval": 4}}
        new, over = ev.npc_lists([{"map": ev.THRONE, "entries": [king, other]}])
        opening, = new
        self.assertEqual(opening["entries"][0]["from"], ev.KING_SRC)
        self.assertEqual(opening["entries"][1], other)
        self.assertEqual(over, [{"map": ev.THRONE, "flag": ev.OPENING[0], "when": "on", "mask": ev.OPENING[1],
                                 "list": "new:ch2_opening"}])

    def test_opening_script_calls_box_then_reveal(self):
        script = ev.scripts(0xE00, {'box2': 0x5F8000, 'reveal': 0x5F9000})[0]
        ops = [c["op"] for c in script["commands"]]
        self.assertEqual(ops, ['3F', '37', '21', '37', '21', '21', '11', '40', '16'])
        self.assertEqual(script["commands"][1]["args"], [0x00, 0x80, 0x5F])
        self.assertEqual(script["commands"][6]["args"], [ev.OPENING[0], ~ev.OPENING[1] & 0xFF])


if __name__ == '__main__':
    unittest.main()
