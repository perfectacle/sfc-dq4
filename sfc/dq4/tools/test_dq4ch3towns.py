"""3장 마을 사람(dq4ch3towns): 등록, 대화 본문과 메시지 이름, 옮긴 대사 키, 글꼴, 다른 모듈 flag, 목록 고치기, FC 3장
엔돌 목록과 견주기(롬이 있을 때), 일본어·창 넘침 검사(dq4ch3townscheck)의 판정."""
import copy
import importlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4ch3event as ev  # noqa: E402
import dq4ch3towns as W  # noqa: E402
import dq4ch3townscheck as check  # noqa: E402
import dq4chapter1 as ch1  # noqa: E402

ROOT = HERE.parents[2]
DQ4 = ROOT / 'rom' / 'dq4.nes'
FIRST = 0x1100


def ctx():
    return next(c for c in ev.contexts(FIRST, 0x900) if c.module is W)


def _msgs(body, acc):
    for op in body:
        if op.get("op") == "msg":
            acc.add(int(op["id"], 16))
        for k in ("then", "else"):
            if isinstance(op.get(k), list):
                _msgs(op[k], acc)
    return acc


class RegisterTest(unittest.TestCase):
    def test_registered_last_with_no_flags_of_its_own(self):
        self.assertIn('dq4ch3towns', ev.EVENTS)
        self.assertEqual(ev.SLOTS['W'].module, 'dq4ch3towns')
        self.assertEqual(W.FLAGS, ())
        # 네이티브는 내보내는 이벤트만: 예약 몫 안
        code, at = W.native(ctx())
        start, end = ev.SLOTS['W'].code
        self.assertLessEqual(start + len(code), end)
        self.assertEqual(set(W.CALLS), {*W.OUT_TO, 'armor_buy'})

    def test_every_talk_has_a_body_and_every_message_is_used(self):
        c = ctx()
        bodies = W.talk_scripts(c)
        self.assertEqual(len(bodies), len(W.TALKS))
        used = set()
        for b in bodies:
            _msgs(b, used)
        native = {c.msg[n] for n in W.ARMOR_MESSAGES}
        self.assertEqual(used | native, set(c.msg.values()))
        code, _ = W.native(c)
        for n in W.ARMOR_MESSAGES:
            self.assertIn(bytes((0xA9, c.msg[n] & 0xFF, c.msg[n] >> 8)), code, n)

    def test_flags_match_the_modules_that_own_them(self):
        for module, names in W.OWNERS.items():
            if not (HERE / f'{module}.py').is_file():
                continue
            mod = importlib.import_module(module)
            for name in names:
                self.assertEqual(getattr(W, name), getattr(mod, name), f'{module}.{name}')

    def test_owner_flags_sit_in_the_owner_bytes(self):
        for module, names in W.OWNERS.items():
            key = next(k for k, s in ev.SLOTS.items() if s.module == module)
            for name in names:
                if getattr(W, name)[0] in (0x13, 0x14):
                    continue            # 맵을 옮기면 지워지는 7E:21A3·21A4(예약 몫 밖, 그 모듈의 맵 안에서만 뜻이 있음)
                self.assertIn(getattr(W, name)[0], ev.SLOTS[key].flags, name)


class TextTest(unittest.TestCase):
    def test_ported_keys_are_new(self):
        import dq4ch1talk
        import dq4ch2talk
        taken = set(dq4ch1talk.TEXTS) | set(ch1.FRONT_TEXTS) | set(dq4ch2talk.TEXTS)
        self.assertFalse(set(W.PORTED) & taken)
        self.assertEqual(ev.ported_texts(), W.PORTED)

    def test_every_character_is_in_the_font(self):
        from dq4menumsg import CHARS
        for parts in (*W.PORTED.values(), *W.MESSAGES.values()):
            for p in parts:
                if isinstance(p, str):
                    self.assertFalse(set(p) - set(' ') - set(CHARS), p)

    def test_lines_fit_the_window(self):
        for name, parts in (*W.MESSAGES.items(), *W.PORTED.items()):
            self.assertEqual(check.window_problems(parts), [], name)


def _entry(time, fc, talk=0x900, gfx=0x10):
    x, y = W.cell(*fc)
    return {"from": {"list": "05:870A", "index": 2}, "time": time,
            "fields": {"x": x, "y": y, "facing": "down", "talk": talk, "gfx": gfx, "layer": 0, "interval": 0}}


def _lists():
    out = {}
    for (m, time, fc) in W.RETALK:
        for t in ((time,) if time else ('day', 'night')):
            out.setdefault(m, []).append(_entry(t, fc))
    for (m, time, fc) in W.ENDOR:
        out.setdefault(m, []).append(_entry(time, fc))
    for m, gone in W.ENDOR_GONE.items():
        out.setdefault(m, []).extend(_entry(t, fc) for t, fc in gone)
    for m, t, _, _, like in W.ENDOR_ADDED:
        if not any(e["time"] == t and (e["fields"]["x"], e["fields"]["y"]) == W.cell(*like) for e in out[m]):
            out[m].append(_entry(t, like))
    for m in W.ENDOR_MAPS:
        out.setdefault(m, [])
    out[W.CASINO] = [_entry(t, fc) for fc in W.CASINO_PEOPLE for t in ('day', 'night')]
    for (m, t, fc) in W.ENDOR_MOVED:
        if not any(e["time"] == t and (e["fields"]["x"], e["fields"]["y"]) == W.cell(*fc) for e in out[m]):
            out[m].append(_entry(t, fc))
    m, t, fc = W.EMPTY_SHOP
    out.setdefault(m, []).append(_entry(t, fc))
    return {m: {"map": m, "entries": e} for m, e in out.items()}


class ListTest(unittest.TestCase):
    def _run(self, lists, made=None, overrides=()):
        c = ctx()
        c.made_all = made or {}
        c.overrides = list(overrides)
        return c, W.npc_lists(lists, c)

    def test_retalk_and_own_endor_lists_when_no_other_module_has_one(self):
        lists = _lists()
        base = copy.deepcopy(lists)
        c, (new, over) = self._run(lists)
        t = c.talk
        for (m, time, fc), name in W.RETALK.items():
            hit = [e for e in lists[m]["entries"] if (e["fields"]["x"], e["fields"]["y"]) == W.cell(*fc)
                   and time in (None, e["time"])]
            self.assertTrue(hit and all(e["fields"]["talk"] == t[name] for e in hit), (m, fc))
        names = {lst["name"]: lst for lst in new}
        self.assertEqual({o["map"] for o in over}, {*W.ENDOR_MAPS, W.CASINO})
        self.assertTrue(all(o["flag"] == ev.CHAPTER3[0] and o["mask"] == ev.CHAPTER3[1] for o in over
                            if o["list"] != "new:ch3_towns_4001_open"))
        hall = names['ch3_towns_4002']["entries"]
        cells = {(e["time"], (e["fields"]["x"], e["fields"]["y"])): e["fields"]["talk"] for e in hall}
        for t_, fc in W.ENDOR_GONE[W.ENDOR_HALL]:
            self.assertNotIn((t_, W.cell(*fc)), cells)
        self.assertEqual(cells[('day', W.cell(0x11, 0x08))], t['arena_closed'])
        # 엔돌 기본 목록(2장도 씀)은 그대로
        for m in W.ENDOR_MAPS:
            self.assertEqual(lists[m], base[m])
        m, t_, fc = W.EMPTY_SHOP
        # 빼지 않고 말만 바꾼다(그림 배치가 바뀌지 않게)
        shop = [e for e in lists[m]["entries"] if (e["time"], (e["fields"]["x"], e["fields"]["y"])) == (t_, W.cell(*fc))]
        self.assertEqual([e["fields"]["talk"] for e in shop], [t['empty_shop']])
        # 공사 재개 뒤의 열린 카지노가 닫힌 카지노보다 앞 줄이고, 장치 사람의 대화가 바뀌어 있다
        casino = [o for o in over if o["map"] == W.CASINO]
        self.assertEqual([o["list"] for o in casino], ["new:ch3_towns_4001_open", "new:ch3_towns_4001"])
        opened = {(e["time"], (e["fields"]["x"], e["fields"]["y"])): e["fields"]["talk"]
                  for e in names['ch3_towns_4001_open']["entries"]}
        for fc, name in W.CASINO_DEVICES.items():
            self.assertEqual(opened[('night', W.cell(*fc))], t[name])
        for fc, service in W.CASINO_SERVICES.items():
            self.assertEqual(opened[('day', W.cell(*fc))], service)
        # 엔돌 밤 사람 한 칸 옮김, 왕좌의 방 대신은 섬
        town = {(e["time"], (e["fields"]["x"], e["fields"]["y"])): e for e in names['ch3_towns_4000']["entries"]}
        self.assertIn(('night', W.cell(0x17, 0x1E)), town)
        self.assertNotIn(('night', W.cell(0x16, 0x1E)), town)
        throne = {(e["time"], (e["fields"]["x"], e["fields"]["y"])): e for e in names['ch3_towns_4006']["entries"]}
        self.assertEqual(throne[('day', W.cell(0x0D, 0x0B))]["fields"]["interval"], 0)
        ryan = names['ch3_towns_4001']["entries"]
        self.assertEqual({e["time"] for e in ryan}, {'day', 'night'})
        self.assertTrue(all(e["fields"]["talk"] == t['ryan'] for e in ryan))

    def test_edits_an_earlier_modules_chapter3_list_in_place_of_its_own(self):
        lists = _lists()
        theirs = {"name": "ch3_endor_4000", "entries": lists['40/00']["entries"]}
        over = [{"map": '40/00', "flag": ev.CHAPTER3[0], "when": "on", "mask": ev.CHAPTER3[1],
                 "list": "new:ch3_endor_4000"}]
        base = copy.deepcopy(lists['40/00'])
        c, (new, more) = self._run(lists, {'ch3_endor_4000': theirs}, over)
        self.assertNotIn('ch3_towns_4000', {lst["name"] for lst in new})
        self.assertNotIn('40/00', {o["map"] for o in more})
        talks = {(e["time"], (e["fields"]["x"], e["fields"]["y"])): e["fields"]["talk"] for e in theirs["entries"]}
        self.assertEqual(talks[('day', W.cell(0x16, 0x0A))], c.talk['gate'])
        self.assertEqual(lists['40/00'], base)

    def test_absent_and_start_tables_cover_the_changed_people(self):
        c = ctx()
        gone = W.absent(c)
        moved = sum(1 for to, _ in W.ENDOR_MOVED.values() if to not in [fc for (_, _, fc) in W.ENDOR_MOVED])
        self.assertEqual(len(gone), 2 * len(W.CASINO_PEOPLE) + 3 + moved)
        start = W.start_messages(c)
        for (m, time, fc) in (*W.RETALK, *W.ENDOR):
            key = (m, W.cell(*fc), None if time is None else time == 'night')
            if W.RETALK.get((m, time, fc)) == 'safe_man':
                key = (m, W.cell(*fc), False)
            self.assertIn(key, start)
        states = W.state_messages(c)
        for name, (sets, table, *late) in states.items():
            # 맵에 들 때 켜거나(SET) 든 뒤에 켠다(셋째 값 LATESET)
            self.assertRegex(late[0] if late else sets, r'^[0-9A-F]{4}\|[0-9A-F]{2}(;[0-9A-F]{4}\|[0-9A-F]{2})*$', name)
            self.assertTrue(table)


class WindowTest(unittest.TestCase):
    def test_counts_columns_and_lines(self):
        ok = ch1.say('가' * ch1.LINE_COLS)
        self.assertEqual(check.window_problems(ok), [])
        long = ['가' * (ch1.LINE_COLS + 1), ch1.END]
        self.assertEqual(check.window_problems(long), [(0, 0, ch1.LINE_COLS + 1, ch1.LINE_COLS)])
        five = ['가', ch1.LINE, '가', ch1.LINE, '가', ch1.LINE, '가', ch1.LINE, '가', ch1.END]
        self.assertTrue(check.window_problems(five))
        named = [ch1.SPEAK, '네네', ch1.Q, '가' * ch1.LINE_COLS, ch1.END]
        self.assertTrue(check.window_problems(named))

    def test_talk_messages_follow_every_branch(self):
        body = [{"op": "if", "cond": {}, "then": [{"op": "msg", "id": "A01"}],
                 "else": [{"op": "msg", "id": "A02"}]}]
        self.assertEqual(check.talk_messages(0x950, {0x950: body}), [0xA01, 0xA02])
        self.assertEqual(check.talk_messages(0x8BA, {}), [0x8BA + ch1.MESSAGE_OF_TALK])
        self.assertIsNone(check.talk_messages(0x003, {}))

    def test_pending_people_count_once_their_module_exists(self):
        prince = ('3F/01', 'day', W.cell(0x01, 0x0B))
        self.assertTrue(check.allowed(*prince, have=lambda name: False))
        self.assertIsNone(check.allowed(*prince, have=lambda name: True))
        self.assertTrue(check.allowed('47/01', 'night', (0, 0), have=lambda name: False))
        self.assertIsNone(check.allowed('3E/00', 'day', W.cell(0x05, 0x0F), have=lambda name: False))

    def test_lists_stop_at_the_chapter3_override(self):
        import dq4ch2event
        doc = {"lists": [{"map": "40/05", "entries": ["base"]}],
               "new_lists": [{"name": "a", "entries": ["a"]}, {"name": "b", "entries": ["b"]},
                             {"name": "c", "entries": ["c"]}],
               "overrides": [{"map": "40/05", "flag": dq4ch2event.CHAPTER2[0], "mask": dq4ch2event.CHAPTER2[1],
                              "when": "on", "list": "new:a"},
                             {"map": "40/05", "flag": 0x75, "mask": 1, "when": "on", "list": "new:b"},
                             {"map": "40/05", "flag": ev.CHAPTER3[0], "mask": ev.CHAPTER3[1], "when": "on",
                              "list": "new:c"}]}
        self.assertEqual(check.candidate_lists(doc, ["40/05"])["40/05"], [("b", ["b"]), ("c", ["c"])])
        doc["overrides"].pop()
        self.assertEqual(check.candidate_lists(doc, ["40/05"])["40/05"], [("b", ["b"]), ("기본", ["base"])])


class ArmorBuyTest(unittest.TestCase):
    def test_fc_samples_fit_the_common_branch(self):
        # FC 실측: かわのよろい(180)의 매입 값
        reachable = {W.armor_buy_price(180, 0, r) for r in range(256)}
        self.assertLessEqual({180, 163, 222, 191}, reachable)
        self.assertEqual((min(reachable), max(reachable)), (151, 225))


@unittest.skipUnless(DQ4.is_file(), 'local source ROM not present')
class FcTest(unittest.TestCase):
    """FC 3장 엔돌 목록($6282 = C0: 1·2장 끝 flag)과 기본 목록을 견준다."""

    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        import dq4npcport
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.people = {}
        for m in (*W.ENDOR_MAPS, W.CASINO):
            for night in (False, True):
                fc = (0x04, int(m[3:], 16))
                cls.people[m, night] = (
                    {(p["x"], p["y"]): p for p in dq4npcport.fc_people(cls.prg, *fc, night)},
                    {(p["x"], p["y"]): p for p in dq4npcport.fc_people(cls.prg, *fc, night, flags={0x6282: 0xC0})})

    def test_changed_cells_are_ours_or_owned_by_another_module(self):
        # 다른 모듈 몫(스콧 (05,13)·네네·납품·안내·왕·모니카)과, 대화 번호만 다르고 3장에 띄우는 말이 같은 칸
        # (성 1층 (0C,1C) 0645, 부엌 밤 (05,02) 055C), 밤에 한 칸 옮긴 (16,1E)→(17,1E)
        owned = {('40/00', 'day', (0x05, 0x13)), ('40/00', 'day', (0x06, 0x1C)),
                 ('40/02', 'day', (0x0C, 0x1C)), ('40/02', 'day', (0x11, 0x12)), ('40/02', 'day', (0x12, 0x12)),
                 ('40/06', 'day', (0x0B, 0x0A)), ('40/06', 'day', (0x0F, 0x0A)), ('40/05', 'night', (0x05, 0x02)),
                 ('40/00', 'night', (0x16, 0x1E)), ('40/00', 'night', (0x17, 0x1E))}
        mine = set(W.ENDOR) | {(m, t, fc) for m, gone in W.ENDOR_GONE.items() for t, fc in gone} | \
            {(m, t, fc) for m, t, fc, _, _ in W.ENDOR_ADDED}
        for m in W.ENDOR_MAPS:
            for night in (False, True):
                base, ch3 = self.people[m, night]
                t = 'night' if night else 'day'
                for c in set(base) | set(ch3):
                    b, a = base.get(c), ch3.get(c)
                    if b and a and b["talk"] == a["talk"]:
                        continue
                    self.assertTrue((m, t, c) in mine or (m, t, c) in owned, (m, t, c))
                    if (m, t, c) in W.ENDOR and b and a:
                        self.assertEqual((b["picture"], b["facing"]), (a["picture"], a["facing"]), (m, t, c))

    def test_casino_is_ryan_alone(self):
        for night in (False, True):
            base, ch3 = self.people[W.CASINO, night]
            self.assertEqual(sorted(base), sorted(W.CASINO_PEOPLE))
            (c, p), = ch3.items()
            self.assertEqual((c, p["picture"], p["facing"], p["interval"]), W.RYAN)

    def test_added_soldier_looks_like_the_one_it_copies(self):
        for m, t, fc, _, like in W.ENDOR_ADDED:
            base, ch3 = self.people[m, t == 'night']
            self.assertNotIn(fc, base)
            self.assertEqual(ch3[fc]["picture"], base[like]["picture"])


if __name__ == '__main__':
    unittest.main()
