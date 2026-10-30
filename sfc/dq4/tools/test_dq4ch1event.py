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
        self.assertEqual(len({ev.NIGHT_TOLD, ev.FLARE_FOLLOWS, ev.REUNITED}), 3)


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
        self.assertEqual([o["list"] for o in self.over], ["new:jail_after", "new:jail_reunion"])
        walkers = [e for lst in self.new if lst["name"] == "jail_reunion" for e in lst["entries"]
                   if e["from"] == ev.WALKER_SRC]
        self.assertEqual(sorted(e["time"] for e in walkers), ["day", "night"])
        # 간격 0 을 받으면 스크립트가 돌지 않으므로 빌린 인물의 움직임을 쓴다
        self.assertTrue(all("interval" not in e["fields"] for e in walkers))

    def test_event_talks_replace_the_ported_ones(self):
        t = ev.talk_numbers(0x904)
        talks = {e["fields"]["talk"] for m in (ev.FRONT, ev.FRONT_NIGHT, ev.IMURU, ev.JAIL) for e in self.entries(m)}
        self.assertLessEqual(set(t.values()), talks)


if __name__ == "__main__":
    unittest.main()
