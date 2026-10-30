"""1장 진행 사건: 메시지·대화 번호 차례, 롬이 있으면 고친 인물 목록."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch1event as ev  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


class NumberTest(unittest.TestCase):
    def test_messages_follow_the_ported_ones(self):
        ids = ev.message_ids(0xD00)
        self.assertEqual(list(ids.values()), list(range(0xD00, 0xD00 + len(ev.MESSAGES))))
        self.assertEqual(set(ev.texts(0xD00)), set(ids.values()))

    def test_flare_asks_only_after_the_night_story(self):
        m = ev.message_ids(0xD00)
        day = ev.talk_scripts(0xD00)[ev.TALKS.index('flare_day')][0]
        self.assertEqual(day["cond"], {"code": "1B", "index": ev.NIGHT_TOLD[0], "mask": ev.NIGHT_TOLD[1]})
        self.assertEqual(day["then"][0]["id"], f"{m['flare_ask']:03X}")
        self.assertEqual(day["then"][1]["mask"], ev.FLARE_FOLLOWS[1])
        self.assertEqual(day["else"]["id"], f"{m['flare_day']:03X}")

    def test_flags_are_distinct(self):
        self.assertEqual(len({ev.NIGHT_TOLD, ev.FLARE_FOLLOWS, ev.REUNITED, ev.HOIMIN}), 4)

    def test_hoimin_record_comes_from_the_companion_table(self):
        data = bytearray(0x400000)
        o = ev.lorom(ev.COMPANION + ev.HOIMIN_KIND * 9)
        data[o:o + 9] = bytes((1, 99, 2, 3, 4, 5, 6, 7, 0))
        r = ev.companion_record(bytes(data), ev.HOIMIN_KIND)
        self.assertEqual((r[0], r[0x12], r[0x13], r[7:11], r[2], r[0xE], r[4], r[0x10]),
                         (0x85, 1, 99, bytes((2, 3, 4, 5)), 6, 6, 7, 7))
        code, at = ev.native(bytes(data))
        self.assertEqual(at, ev.native()[1])     # 주소는 롬 자료에 따라 바뀌지 않는다
        self.assertEqual(code[:42], r)




class FlyTest(unittest.TestCase):
    def test_shoes_start_the_tower_event_and_fly_to_the_island(self):
        data = bytearray(0x400000)
        for addr, orig in ((ev.FLY_AT, ev.FLY_ORIG), (ev.FLY_X_AT, ev.FLY_XY_ORIG[0]), (ev.FLY_Y_AT, ev.FLY_XY_ORIG[1])):
            data[ev.lorom(addr):ev.lorom(addr) + len(orig)] = orig
        out = ev.apply(bytes(data))
        _, at = ev.native()
        o = ev.lorom(ev.FLY_AT)
        self.assertEqual(out[o:o + 5], bytes((0x22, *ev._long(at['fly']), 0xEA)))
        self.assertEqual(out[ev.lorom(ev.FLY_X_AT):][:2], (0x88 * 2).to_bytes(2, 'little'))
        self.assertEqual(out[ev.lorom(ev.FLY_Y_AT):][:2], (0x16 * 2).to_bytes(2, 'little'))
        e = ev.lorom(at['fly_event'])
        self.assertEqual(out[e:e + 8], bytes((0x90, ev.TOWER, 0x00, 18, 25, 0x01, 0x80, 0xFF)))   # FC 30/00 (09,0C)

    def test_boss_battle_sets_the_flag_only_on_a_win(self):
        code = ev._battle()
        self.assertEqual(code[2:8], bytes((0xA9, ev.BOSS_GROUP, 0x22, 0x8B, 0x86, 0x01)))   # JSL $01868B
        self.assertEqual(code[8:12], bytes((0xC9, 0x80, 0xF0, len(code) - 13)))              # 지면 깃발을 건너뜀
        self.assertEqual(code[-1], 0x60)
        (g,) = ev.encounter_doc()["event_groups"]
        self.assertEqual((g["index"], g["flags"] & 0x40), (ev.BOSS_GROUP, 0x40))

    def test_apply_refuses_other_bytes(self):
        with self.assertRaises(SystemExit):
            ev.apply(bytes(0x400000))


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), "local source ROMs not present")
class ListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dq4npcport
        cls.ported, _, cls.report = dq4npcport.port(str(DQ5), str(DQ4))
        cls.lists, cls.new, cls.over = ev.npc_lists(cls.ported, cls.report, 0x904)

    def entries(self, m):
        return next(lst["entries"] for lst in self.lists if lst["map"] == m)

    def test_jail_starts_with_alex_only(self):
        flares = sum(p["talk"] == ev.FC_JAIL_FLARE for p in self.report[ev.JAIL])
        self.assertEqual(len(self.entries(ev.JAIL)), len(self.report[ev.JAIL]) - flares)

    def test_reunion_is_checked_before_following(self):
        jail = [o["list"] for o in self.over if o["map"] == ev.JAIL]
        self.assertEqual(jail, ["new:jail_after", "new:jail_reunion"])
        walkers = [e for lst in self.new if lst["name"] == "jail_reunion" for e in lst["entries"]
                   if e["from"] == ev.WALKER_SRC]
        self.assertEqual(sorted(e["time"] for e in walkers), ["day", "night"])
        # 간격 0 을 받으면 스크립트가 돌지 않으므로 빌린 인물의 움직임을 쓴다
        self.assertTrue(all("interval" not in e["fields"] for e in walkers))

    def test_hoimin_leaves_the_room_after_joining(self):
        (over,) = [o for o in self.over if o["map"] == ev.HOIMIN_ROOM]
        self.assertEqual(over["list"], "new:hoimin_gone")
        (gone,) = [lst["entries"] for lst in self.new if lst["name"] == "hoimin_gone"]
        self.assertFalse([e for e in gone if e["from"] == ev.HOIMIN_SRC])

    def test_tower_hall_empties_after_the_kidnap(self):
        (over,) = [o for o in self.over if o["map"] == ev.TOWER_HALL]
        self.assertEqual((over["flag"], over["mask"], over["list"]), (*ev.KIDNAPPED, "new:hall_empty"))
        self.assertEqual(sorted(e["from"]["index"] for e in self.entries(ev.TOWER_HALL)), [1, 1, 5, 5])

    def test_tower_top_after_the_boss(self):
        (over,) = [o for o in self.over if o["map"] == ev.TOWER_TOP]
        self.assertEqual((over["flag"], over["mask"]), ev.BOSS_WON)
        (after,) = [lst["entries"] for lst in self.new if lst["name"] == "top_after"]
        srcs = (ev.HIDE_ON_WIN_SRC, ev.RESCUED_SRC, ev.THANKS_SRC)
        self.assertFalse([e for e in after if e["from"] in srcs])
        top = self.entries(ev.TOWER_TOP)
        self.assertEqual(sum(e["from"] == ev.THANKS_SRC for e in top), 2)     # 낮·밤에 하나씩

    def test_after_boss_lists_switch_on_the_boss_flag(self):
        for m in ev.ALT_STATES[0][2]:
            names = [o["list"] for o in self.over if o["map"] == m]
            self.assertIn(f"new:{ev.alt_name(ev.AFTER_BOSS, m)}", names)
        # 병사가 떠난 목록이 보스 뒤 목록보다 먼저
        soldier = [o["list"] for o in self.over if o["map"] == ev.SOLDIER_MAP]
        self.assertEqual(soldier, ["new:soldier_gone", f"new:{ev.alt_name(ev.AFTER_BOSS, ev.SOLDIER_MAP)}"])
        self.assertIn(ev.alt_name(ev.AFTER_BOSS, ev.KIDS_HOME_MAP), self.report)

    def test_event_talks_replace_the_ported_ones(self):
        t = ev.talk_numbers(0x904)
        talks = {e["fields"]["talk"] for m in (ev.FRONT, ev.FRONT_NIGHT, ev.IMURU, ev.JAIL, ev.HOIMIN_ROOM, ev.TOWER_TOP)
                 for e in self.entries(m)} | {e["fields"]["talk"] for lst in self.new for e in lst["entries"]}
        self.assertLessEqual(set(t.values()), talks)


if __name__ == "__main__":
    unittest.main()
