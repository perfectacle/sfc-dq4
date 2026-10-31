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
        mine = (ev.CHAPTER2, ev.OPENING, ev.KICKED, ev.JOINED, ev.TALKED_GATE, ev.TALKED_BREY, ev.TALKED_KIRYL, ev.READY)
        for flag in mine:
            self.assertNotIn(flag, earlier)
        self.assertEqual(len(set(mine)), len(mine))


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
        data = bytes(k & 0xFF for k in range(0x400000))
        code, at = ev.native(data)
        self.assertEqual(at, ev.native()[1])
        self.assertEqual(code[:42], ev.alena_record(ev.person_record(data, 0)))
        more, tail = ev.tail_native(0xE00, data)
        self.assertEqual(tail, ev.tail_native(0xE00)[1])
        self.assertLess((ev.CODE_AT & 0xFFFF) + len(code) + len(more), 0x10000)

    def test_recruits_start_at_level_one(self):
        data = bytes(0x400000)
        kiryl, brey = ev.recruit_records(data)
        self.assertEqual((kiryl[0x12], kiryl[2], kiryl[4], kiryl[0x16:0x18], kiryl[0x14]), (1, 18, 7, b'\x02\x43', 0x03))
        self.assertEqual((brey[0x12], brey[2], brey[4], brey[0x16:0x18]), (1, 16, 10, b'\x00\x42'))

    def test_hero_picture_hook(self):
        data = bytearray(0x400000)
        o = ev.ch1.lorom(ev.HERO_PICTURE_AT)
        data[o:o + len(ev.HERO_PICTURE_ORIG)] = ev.HERO_PICTURE_ORIG
        s = ev.ch1.lorom(ev.STEP_HOOK_AT)
        data[s:s + 4] = ev.STEP_HOOK_ORIG
        original = bytearray(0x400000)
        out = ev.apply(bytes(data), bytes(original), 0xE00)
        _, at = ev.native()
        a = at['hero_picture']
        self.assertEqual(out[o:o + 5], bytes((0x22, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0x60)))
        step = ev.tail_native(0xE00)[1]['step']
        self.assertEqual(out[s:s + 4], bytes((0x22, step & 0xFF, step >> 8 & 0xFF, step >> 16)))
        with self.assertRaises(SystemExit):
            ev.apply(bytes(0x400000), bytes(original), 0xE00)

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
        def person(cell, time="day"):
            return {"from": {"list": "05:8857", "index": 6}, "time": time,
                    "fields": {"x": cell[0], "y": cell[1], "interval": 4, "talk": 0x100}}
        ported = [{"map": ev.THRONE, "entries": [king, other, person(ev.BREY_AT[1])]},
                  {"map": ev.CASTLE, "entries": [person(ev.GATE[0]), person(ev.GATE[1]), person(ev.KIRYL_AT[1])]},
                  {"map": ev.BEDROOM, "entries": [person(ev.CARPENTER), person((2, 3))]}]
        king["fields"]["talk"] = 0x100
        _, new, over = ev.npc_lists(ported, 0xA00)
        t = ev.talk_numbers(0xA00)
        lists = {n["name"]: n["entries"] for n in new}
        self.assertEqual(lists["ch2_opening"][0]["from"], ev.KING_SRC)
        self.assertEqual(lists["ch2_opening"][1], other)
        self.assertEqual(over[0], {"map": ev.THRONE, "flag": ev.OPENING[0], "when": "on", "mask": ev.OPENING[1],
                                   "list": "new:ch2_opening"})
        # 수리공은 셋과 이야기한 뒤·걷어찬 뒤 목록에서 빠지고, 묻는 인물은 기본 목록에 밤에만
        cells = lambda name: [(e["fields"]["x"], e["fields"]["y"]) for e in lists[name]]  # noqa: E731
        self.assertNotIn(ev.CARPENTER, cells("ch2_ready"))
        self.assertNotIn(ev.CARPENTER, cells("ch2_kicked"))
        room = ported[2]["entries"]
        self.assertEqual([e["time"] for e in room if e["from"] == ev.ASKER_SRC], ["night"])
        # 합류 뒤 브라이·크리프트는 성에서 빠지고 문지기는 비켜선다
        self.assertNotIn(ev.BREY_AT[1], cells("ch2_throne_joined"))
        self.assertNotIn(ev.KIRYL_AT[1], cells("ch2_castle_joined"))
        gate = [e for e in lists["ch2_castle_joined"] if e["fields"]["talk"] == t["gate_back"]]
        self.assertEqual([e["fields"]["x"] for e in gate], [ev.GATE[0][0] - 2, ev.GATE[1][0] + 2])
        self.assertEqual(ported[1]["entries"][0]["fields"]["interval"], 0)

    def test_opening_script_calls_box_then_reveal(self):
        script = ev.scripts(0xE00, {'box2': 0x5F8000, 'reveal': 0x5F9000})[0]
        ops = [c["op"] for c in script["commands"]]
        self.assertEqual(ops, ['3F', '37', '21', '37', '21', '21', '11', '40', '16'])
        self.assertEqual(script["commands"][1]["args"], [0x00, 0x80, 0x5F])
        self.assertEqual(script["commands"][6]["args"], [ev.OPENING[0], ~ev.OPENING[1] & 0xFF])

    def test_ready_needs_all_three_talks(self):
        body = ev.talk_scripts(0xE00)[ev.TALKS.index('gate')]
        flag, ready = body[1], body[2]
        self.assertEqual(flag, {"op": "flag-on", "index": ev.TALKED_GATE[0], "mask": ev.TALKED_GATE[1]})
        seen = []
        while ready["op"] == "if":
            seen.append((ready["cond"]["index"], ready["cond"]["mask"]))
            ready = ready["then"][0] if isinstance(ready["then"], list) else ready["then"]
        self.assertEqual(sorted(seen), sorted([ev.TALKED_GATE, ev.TALKED_BREY, ev.TALKED_KIRYL]))
        self.assertEqual(ready, {"op": "flag-on", "index": ev.READY[0], "mask": ev.READY[1]})


if __name__ == '__main__':
    unittest.main()
