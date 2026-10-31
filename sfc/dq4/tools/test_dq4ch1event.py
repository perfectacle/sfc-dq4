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

    def test_start_messages_are_the_first_message_or_nobody(self):
        m = ev.message_ids(0xD80)
        got = ev.start_messages(0xD80)
        self.assertEqual(got[ev.JAIL, ev.FC_ALEX_NIGHT, True], m['alex_night'])
        self.assertEqual(got[ev.JAIL, ev.FC_JAIL_FLARE, None], ev.NOBODY)
        self.assertEqual(got[ev.HOIMIN_ROOM, ev.FC_HOIMIN, None], m['hoimin_ask'])

    def test_flags_are_distinct(self):
        self.assertEqual(len({ev.NIGHT_TOLD, ev.FLARE_FOLLOWS, ev.REUNITED, ev.HOIMIN}), 4)

    def test_hoimin_record_comes_from_the_companion_table(self):
        data = bytearray(0x400000)
        o = ev.lorom(ev.COMPANION + ev.HOIMIN_KIND * 9)
        data[o:o + 9] = bytes((1, 99, 2, 3, 4, 5, 6, 7, 0))
        r = ev.companion_record(bytes(data), ev.HOIMIN_KIND)
        self.assertEqual((r[0], r[0x12], r[0x13], r[7:11], r[2], r[0xE], r[4], r[0x10]),
                         (0xC5, 1, 99, bytes((2, 3, 4, 5)), 6, 6, 7, 7))
        code, at = ev.native(bytes(data))
        self.assertEqual(at, ev.native()[1])     # 주소는 롬 자료에 따라 바뀌지 않는다
        self.assertEqual(code[:42], r)




class FlyTest(unittest.TestCase):
    def test_shoes_start_the_tower_event_and_fly_to_the_island(self):
        data = bytearray(0x400000)
        for addr, orig in ((ev.FLY_AT, ev.FLY_ORIG), (ev.FLY_X_AT, ev.FLY_XY_ORIG[0]), (ev.FLY_Y_AT, ev.FLY_XY_ORIG[1]),
                           (ev.GUEST_AI_AT, ev.GUEST_AI_ORIG), (ev.GUEST_TARGET_AT, ev.GUEST_TARGET_ORIG)):
            data[ev.lorom(addr):ev.lorom(addr) + len(orig)] = orig
        out = ev.apply(bytes(data))
        _, at = ev.native()
        o = ev.lorom(ev.FLY_AT)
        self.assertEqual(out[o:o + 5], bytes((0x22, *ev._long(at['fly']), 0xEA)))
        self.assertEqual(out[ev.lorom(ev.FLY_X_AT):][:2], (0x88 * 2).to_bytes(2, 'little'))
        self.assertEqual(out[ev.lorom(ev.FLY_Y_AT):][:2], (0x16 * 2).to_bytes(2, 'little'))
        e = ev.lorom(at['fly_event'])
        self.assertEqual(out[e:e + 8], bytes((0x90, ev.TOWER, 0x00, 18, 25, 0x01, 0x80, 0xFF)))   # FC 30/00 (09,0C)

    def test_guest_ai_hooks_jump_to_the_native(self):
        data = bytearray(0x400000)
        for addr, orig in ((ev.FLY_AT, ev.FLY_ORIG), (ev.FLY_X_AT, ev.FLY_XY_ORIG[0]), (ev.FLY_Y_AT, ev.FLY_XY_ORIG[1]),
                           (ev.GUEST_AI_AT, ev.GUEST_AI_ORIG), (ev.GUEST_TARGET_AT, ev.GUEST_TARGET_ORIG)):
            data[ev.lorom(addr):ev.lorom(addr) + len(orig)] = orig
        out = ev.apply(bytes(data))
        _, at = ev.native()
        self.assertEqual(out[ev.lorom(ev.GUEST_AI_AT):][:4], bytes((0x5C, *ev._long(at['guest_ai']))))
        self.assertEqual(out[ev.lorom(ev.GUEST_TARGET_AT):][:5], bytes((0x22, *ev._long(at['guest_target']), 0xEA)))
        # 손님이 아니면 덮은 두 ROL 을 하고 원래 고르기로 돌아간다
        code, _, _ = ev._guest_ai(ev.CODE_AT)
        self.assertIn(bytes((0x28, 0x2E, 0x0E, 0x11, 0x2E, 0x0F, 0x11, 0x5C, *ev._long(ev.GUEST_AI_BACK))), code)
        # 가중치 합은 FC 고르는 법 2 의 칸 가중치 합(255)
        self.assertEqual(sum(w for _, w in ev.GUEST_WEIGHTS), 255)

    def test_boss_battle_sets_the_flag_only_on_a_win(self):
        code = ev._battle()
        self.assertEqual(code[2:8], bytes((0xA9, ev.BOSS_GROUP, 0x22, 0x8B, 0x86, 0x01)))   # JSL $01868B
        self.assertEqual(code[8:12], bytes((0xC9, 0x80, 0xF0, len(code) - 13)))              # 지면 깃발을 건너뜀
        self.assertEqual(code[-1], 0x60)
        (g,) = ev.encounter_doc()["event_groups"]
        self.assertEqual((g["index"], g["flags"] & 0x40), (ev.BOSS_GROUP, 0x40))

    def test_king_checks_report_then_kids(self):
        m = ev.message_ids(0xD00)
        (top,) = ev.talk_scripts(0xD00)[ev.TALKS.index('king')]
        self.assertEqual((top["cond"]["index"], top["cond"]["mask"]), ev.REPORTED)
        self.assertEqual(top["then"]["id"], f"{m['king_farewell']:03X}")
        (kids,) = top["else"]
        self.assertEqual((kids["cond"]["index"], kids["cond"]["mask"]), ev.KIDS_FOLLOW)
        self.assertEqual([o.get("id") for o in kids["else"]], [f"{m['king_praise']:03X}", f"{m['king_farewell']:03X}", None])

    def test_chapter_end_box_comes_after_the_narration(self):
        (end,) = [x for x in ev.scripts(0xD00, 0x5F9000) if x["address"] == ev.ENDER_SCRIPT]
        ops = [c["op"] for c in end["commands"]]
        self.assertLess(ops.index('21'), [i for i, c in enumerate(end["commands"]) if c["args"] == [0x00, 0x90, 0x5F]][0])
        self.assertNotIn('40', ops)          # 1장 끝에서 멈춘다
        self.assertEqual([x for x in ev.scripts(0xD00) if x["address"] == ev.ENDER_SCRIPT], [])

    def test_at_variants(self):
        x, y = ev.ch1_cell(ev.CRY_FROM, ev.CRY_ROW)
        code = ev._at(x, y, x_from=True)
        self.assertEqual(code[3:9], bytes((0xAF, 0x20, 0x30, 0x7E, 0xC9, x)))
        self.assertEqual(code[9], 0x90)                          # X 는 이상이면 지나감(BCC)
        near, away = ev._at(None, y), ev._at(None, y, away=True)
        self.assertEqual((near[-11], near[-4]), (0x00, 0x01))   # 그 줄이면 A = 0
        self.assertEqual((away[-11], away[-4]), (0x01, 0x00))   # 떠나면 A = 0

    def test_level_up_branches_land_on_the_two_paths(self):
        from dq4chapterbox import ENTER, LEAVE
        code = ev._level_up()
        body = code[len(ENTER):-len(LEAVE)]
        bcs = body.index(bytes((0xE2, 0x10, 0xB0))) + 2
        up = bcs + 2 + body[bcs + 1]
        self.assertEqual(body[up:up + 1], b'\xAF')                               # 깃발을 끄는 갈래
        brl = up - 3
        self.assertEqual(body[brl], 0x82)
        self.assertEqual(brl + 3 + int.from_bytes(body[brl + 1:brl + 3], 'little'), len(body))  # 끝(LEAVE)으로
        self.assertIn(bytes((0x22, *ev._long(ev.LEVEL_UP))), body)
        self.assertIn(bytes((0xAF, *ev._long(ev.HERO_LEVEL), 0x1A)), body)      # 레벨은 직접 +1

    def test_cage_copies_each_cell_from_the_floor_beside_it(self):
        code = ev._open_cage()
        x0, y0 = ev.CAGE[0] * 2, ev.CAGE[1] * 2
        for y in range(y0, y0 + 4):
            for x in range(x0, x0 + 4):
                src = bytes((0xA2, x + ev.CAGE_FLOOR_DX * 2, 0xA0, y, 0x22))
                dst = bytes((0xA2, x, 0xA0, y, 0x22))
                self.assertLess(code.index(src), code.index(dst))
        self.assertIn(ev.DP_SAVE, code)
        self.assertLess(code.index(ev.DP_SAVE), code.index(ev.DP_RESTORE))

    def test_king_calls_from_his_row(self):
        (call,) = [x for x in ev.scripts(0xD00) if x["address"] == ev.KING_CALL_SCRIPT]
        cmds = call["commands"]
        _, at = ev.native()
        waits = [c["args"] for c in cmds if c["op"] == '05']
        self.assertEqual(waits[:2], [ev._long(at['lineup_row']), ev._long(at['king_row'])])
        branch = next(c for c in cmds if c["op"] == '06' and c["args"] == [0x80 | ev.KIDS_FOLLOW[0], ev.KIDS_FOLLOW[1]])
        self.assertEqual(branch["target"], "praise")
        calls = [c["args"] for c in cmds if c["op"] == '37']
        want = ['walk_in', 'status_count', 'level_up'] + [f'stat_{k}' for k, _ in ev.STATS] + ['walk_back', 'walk_out']
        self.assertEqual(calls, [ev._long(at[n]) for n in want])
        self.assertIn({"op": "10", "args": list(ev.REPORTED)}, cmds)

    def test_walk_in_lands_in_the_aisle(self):
        for x in (ev.AISLE_X - 2, ev.AISLE_X - 1, ev.AISLE_X, ev.AISLE_X + 1):
            code = ev._walk_in_event(x)
            self.assertEqual(code[:ev.LINEUP_WAIT], bytes((0xC2,)) * ev.LINEUP_WAIT)
            dx = 0
            for d, n in zip(code[ev.LINEUP_WAIT:-1:2], code[ev.LINEUP_WAIT + 1:-1:2]):
                dx += {ev.RIGHT: n, ev.LEFT: -n}.get(d, 0)
            self.assertEqual(x + dx, ev.AISLE_X)
            self.assertEqual(code[-3:], bytes((ev.UP, ev.KING_STEPS, 0xFF)))

    def test_status_window_opens_without_brk(self):
        code = ev._status_count()
        self.assertNotIn(bytes((0x00, 0x95)), code)              # BRK 95 는 DB 가 뱅크 5E 라 롬에 씀
        self.assertIn(bytes((0xA9, ev.STATS_WINDOW, 0x8D, 0x00, 0x0A)), code)
        self.assertIn(bytes((0x22, *ev._long(ev.WINDOW_ONE))), code)
        self.assertIn(bytes((0x22, *ev._long(ev.SEND_ROWS))), code)
        self.assertEqual(ev.GIFT_EXP % ev.GIFT_STEP, 0)

    def test_stat_messages_print_the_number(self):
        m = ev.MESSAGES
        for k, _ in ev.STATS:
            self.assertIn(ev.NUMBER, m[f'stat_{k}'])
            self.assertEqual(m[f'stat_{k}'][-1], ev.WAIT_END)

    def test_throne_return_lines_up_eight_soldiers(self):
        entries = ev.throne_return(0x904)
        soldiers = [e for e in entries if e["from"] in [s for s, _ in ev.SOLDIER_SRCS]]
        self.assertEqual(len(soldiers), 16)                          # 낮·밤
        self.assertEqual(sum(e["from"] == ev.KING_CALL_SRC for e in entries), 2)
        scripts = {x["address"] for x in ev.scripts(0xD00)}
        self.assertLessEqual({a for _, a in ev.SOLDIER_SRCS}, scripts)

    def test_apply_refuses_other_bytes(self):
        with self.assertRaises(SystemExit):
            ev.apply(bytes(0x400000))


@unittest.skipUnless(DQ4.is_file(), "local source ROM not present")
class BossMonsterTest(unittest.TestCase):
    def test_fc_boss_records(self):
        from kr_patch.fc import ines
        doc = ev.monster_doc(ines.prg(DQ4.read_bytes()))
        tesaki, medama = doc["monsters"]
        self.assertEqual((tesaki["id"], tesaki["HP"], tesaki["공격"], tesaki["수비"], tesaki["경험치"]), ("E2", 250, 52, 36, 73))
        self.assertEqual([tesaki[f"행동{k}"] for k in range(1, 7)], ["39", "73", "8E", "3C", "73", "8E"])
        self.assertEqual((medama["id"], medama["HP"], medama["경험치"]), ("52", 42, 27))
        self.assertEqual(ev.BOSS_MEMBERS, ((0xE2, 1), (0x52, 1)))


@unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
class LearnTest(unittest.TestCase):
    def test_hero_learns_nothing_and_others_keep_theirs(self):
        sys.path.insert(0, str(ROOT / "sfc" / "dq5" / "tools"))
        import dq5learnwrite as lw
        from dq5map import Rom, lorom
        data = bytearray(DQ5.read_bytes())
        before = lw.dump(Rom(bytes(data)))["characters"]
        for w in lw.patch(Rom(bytes(data)), ev.learn_doc())["writes"]:
            bank, addr = (int(v, 16) for v in w["at"].split(":"))
            o = lorom(bank << 16 | addr)
            new = bytes.fromhex(w["hex"])
            data[o:o + len(new)] = new
        after = lw.dump(Rom(bytes(data)))["characters"]
        self.assertTrue(before[0]["learn"])
        self.assertEqual(after[0]["learn"], [])
        self.assertEqual(before[1:], after[1:])


class LearnLayoutTest(unittest.TestCase):
    def test_hero_learns_nothing_and_others_keep_theirs(self):
        # 지어낸 습득 표·목록. 사람 표는 원래 자리(23:B819~B978)를 꼭 채워야 줄어든 표를 그 자리에 다시 쓴다.
        sys.path.insert(0, str(ROOT / "sfc" / "dq5" / "tools"))
        import dq5learnwrite as lw
        from dq5map import Rom, lorom
        data = bytearray(0x180000)

        def put(address, raw):
            data[lorom(address):lorom(address) + len(raw)] = raw

        put(lw.LDY_AT, lw.LDY)
        for kind, (_, base, _, _) in lw.GROUPS.items():
            put(lw.BASE_AT[kind], (base & 0xFFFF).to_bytes(2, "little"))
        for at in lw.BANK_AT.values():
            put(at, b"\x23")
        rows = [[(2, 0x000101), (5, 0x000202)], [(3, 0x000101)]] + [[]] * 8 + [[(n, 1) for n in range(2, 84)]]
        address = lw.GROUPS["person"][1]
        for row in rows:
            put(address, bytes([len(row)]) + b"".join(bytes([level]) + mask.to_bytes(3, "little") for level, mask in row))
            address += 1 + 4 * len(row)
        self.assertEqual(address, lw.GROUPS["person"][2])
        # 목록 표의 칸(사람 0~10, 몬스터 11~52)은 모두 빈 목록을 가리키고, 주인공과 사람 1 만 제 목록을 둔다.
        empty = at = lw.LIST_REGION[0]
        at += 1
        for table in lw.TABLES.values():
            for index in range(53):
                put(table + index * 2, (empty & 0xFFFF).to_bytes(2, "little"))
        for index, pair in {0: (b"\x02\x27\x29", b"\x02\x05\x09"), 1: (b"\x01\x2C", b"\x01\x11")}.items():
            for name, raw in zip(lw.TABLES, pair):
                put(at, raw)
                put(lw.TABLES[name] + index * 2, (at & 0xFFFF).to_bytes(2, "little"))
                at += len(raw)
        before = lw.dump(Rom(bytes(data)))["characters"]
        for w in lw.patch(Rom(bytes(data)), ev.learn_doc())["writes"]:
            bank, addr = (int(v, 16) for v in w["at"].split(":"))
            put(bank << 16 | addr, bytes.fromhex(w["hex"]))
        after = lw.dump(Rom(bytes(data)))["characters"]
        self.assertEqual([r["level"] for r in before[0]["learn"]], [2, 5])
        self.assertEqual(after[0]["learn"], [])
        self.assertEqual((after[0]["field"], after[0]["battle"]), ([0x27, 0x29], [0x05, 0x09]))
        self.assertEqual(after[1]["learn"], [{"level": 3, "field_slots": [0], "battle_slots": [0]}])
        self.assertEqual(before[1:], after[1:])


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
        srcs = (ev.RESCUED_SRC, ev.RESCUED2_SRC, ev.THANKS_SRC, ev.CRY_SRC)
        self.assertFalse([e for e in after if e["from"] in srcs])
        # 다시 들어오면 보이지 않는 인물 하나가 철창만 연다
        opener = [e for e in after if e["from"] == ev.HIDE_ON_WIN_SRC]
        self.assertEqual([(e["fields"]["gfx"], e["time"]) for e in opener], [(1, "day"), (1, "night")])
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

    def test_imuru_kids_walk_home_instead_of_the_fc_walkers(self):
        (imuru,) = [lst["entries"] for lst in self.new if lst["name"] == ev.alt_name(ev.AFTER_BOSS, ev.KIDS_HOME_MAP)]
        srcs = [e["from"] for e in imuru]
        for src, _ in ev.HOME_KID_SRCS:
            self.assertEqual(srcs.count(src), 1)
        walkers = [p for p in self.report[ev.alt_name(ev.AFTER_BOSS, ev.KIDS_HOME_MAP)]
                   if (p["x"], p["y"]) in ev.KIDS_FC_WALKERS]
        self.assertEqual(len(imuru), len(self.report[ev.alt_name(ev.AFTER_BOSS, ev.KIDS_HOME_MAP)]) - len(walkers) + 2)

    def test_event_talks_replace_the_ported_ones(self):
        t = ev.talk_numbers(0x904)
        talks = {e["fields"]["talk"] for m in (ev.FRONT, ev.FRONT_NIGHT, ev.IMURU, ev.JAIL, ev.HOIMIN_ROOM, ev.TOWER_TOP,
                                                ev.CAVE, ev.KING_ROOM, ev.SOLDIER_MAP)
                 for e in self.entries(m)} | {e["fields"]["talk"] for lst in self.new for e in lst["entries"]} | \
            {e["fields"]["talk"] for e in ev.throne_return(0x904)}
        self.assertLessEqual(set(t.values()), talks)


if __name__ == "__main__":
    unittest.main()
