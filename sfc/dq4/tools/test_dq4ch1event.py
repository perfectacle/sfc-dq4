"""1장 진행 사건: 메시지·대화 번호 차례, 롬이 있으면 고친 인물 목록."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4ch1event as ev  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4 = ROOT / "rom" / "dq4.nes"
DQ5 = ROOT / "rom" / "dq5.sfc"


def _hooked():
    """apply 가 덮는 자리마다 원래 바이트를 둔 빈 롬."""
    data = bytearray(0x400000)
    for addr, orig in ((ev.FLY_AT, ev.FLY_ORIG), (ev.FLY_X_AT, ev.FLY_XY_ORIG[0]), (ev.FLY_Y_AT, ev.FLY_XY_ORIG[1]),
                       (ev.GUEST_AI_AT, ev.GUEST_AI_ORIG), (ev.GUEST_TARGET_AT, ev.GUEST_TARGET_ORIG),
                       (ev.COUNT_AT, ev.COUNT_ORIG), (ev.SOLO_AT, ev.SOLO_ORIG),
                       (ev.GUEST_PICTURE_AT, ev.GUEST_PICTURE_ORIG)):
        data[ev.lorom(addr):ev.lorom(addr) + len(orig)] = orig
    return bytes(data)



def _run_step(code, ram, slot, blocked=()):
    """_old_man_step 이 쓰는 명령만 도는 65816 흉내(M·X 8). 직접 페이지 $90 = slot. 걸음 검사(STEP_CHECK)는 그 자리의
    7E:31E0 방향으로 내디딜 셀(오른쪽 X+2, 왼쪽 X-1, 아래 Y+1, 위 Y-1)이 blocked 에 있으면 막힌 것으로 본다. 돌린 뒤의 ram."""
    ram, pc, a, x, y, carry, z, neg, n, stack = dict(ram), 0, 0, 0, 0, 0, 0, 0, 0, []
    long_ = lambda: code[pc + 1] | code[pc + 2] << 8 | code[pc + 3] << 16  # noqa: E731

    def nz(v):
        return int(v == 0), v & 0x80
    while True:
        op = code[pc]
        if op in (0x08, 0x8B, 0x4B):
            stack.append(carry if op == 0x08 else 0)
            pc += 1
        elif op in (0x28, 0xAB):
            v = stack.pop()
            carry = v if op == 0x28 else carry
            pc += 1
        elif op == 0x6B:
            if stack:
                raise AssertionError(f'스택이 {len(stack)}바이트 남음')
            return ram
        elif op == 0xE2:
            pc += 2
        elif op == 0x48:
            stack.append(a)
            pc += 1
        elif op == 0x5A:
            stack.append(y)
            pc += 1
        elif op == 0x68:
            a = stack.pop()
            (z, neg), pc = nz(a), pc + 1
        elif op == 0x9B:
            y, pc = x, pc + 1
        elif op == 0x62:
            stack += [0, 0]
            pc += 3
        elif op == 0xF4:
            stack += [0, 0]
            pc += 3
        elif op == 0x5C:
            if long_() != ev.STEP_CHECK or y != slot:
                raise AssertionError('검사 호출')
            cx, cy = ram.get(0x7E3020 + slot, 0), ram.get(0x7E3080 + slot, 0)
            dx, dy = {0x10: (2, 0), 0x20: (-1, 0), 0x40: (0, 1), 0x80: (0, -1)}[ram[0x7E31E0 + slot]]
            carry = int((cx + dx, cy + dy) not in blocked)
            del stack[-5:]
            pc += 4
        elif op == 0xA6:
            x, pc = ram.get(code[pc + 1], 0) if code[pc + 1] != 0x90 else slot, pc + 2
        elif op == 0xA2:
            x, pc = code[pc + 1], pc + 2
        elif op == 0xA0:
            y, pc = code[pc + 1], pc + 2
        elif op == 0xA5:
            a, pc = ram.get(code[pc + 1], 0), pc + 2
        elif op == 0x85:
            ram[code[pc + 1]], pc = a, pc + 2
        elif op == 0xB5:
            a, pc = ram.get((code[pc + 1] + x) & 0xFF, 0), pc + 2
        elif op == 0x95:
            ram[(code[pc + 1] + x) & 0xFF], pc = a, pc + 2
        elif op == 0x9D:
            ram[0x7E0000 + (code[pc + 1] | code[pc + 2] << 8) + x], pc = a, pc + 3
        elif op in (0xCA, 0xE8):
            x = (x + (1 if op == 0xE8 else -1)) & 0xFF
            (z, neg), pc = nz(x), pc + 1
        elif op == 0xE0:
            carry, (z, neg), pc = int(x >= code[pc + 1]), nz((x - code[pc + 1]) & 0xFF), pc + 2
        elif op == 0xBF:
            a, pc = ram.get(long_() + x, 0), pc + 4
        elif op == 0x9F:
            ram[long_() + x], pc = a, pc + 4
        elif op == 0xAF:
            a, pc = ram.get(long_(), 0), pc + 4
        elif op == 0x38:
            carry, pc = 1, pc + 1
        elif op == 0x18:
            carry, pc = 0, pc + 1
        elif op == 0xFF:
            v = a - ram.get(long_() + x, 0) - (1 - carry)
            a, carry, pc = v & 0xFF, int(v >= 0), pc + 4
            z, neg = nz(a)
        elif op == 0x7F:
            v = a + ram.get(long_() + x, 0) + carry
            a, carry, pc = v & 0xFF, int(v > 0xFF), pc + 4
        elif op == 0xA9:
            a, pc = code[pc + 1], pc + 2
        elif op == 0x69:
            v = a + code[pc + 1] + carry
            a, carry, pc = v & 0xFF, int(v > 0xFF), pc + 2
        elif op == 0x82:
            pc += 3 + int.from_bytes(code[pc + 1:pc + 3], 'little', signed=True)
        elif op == 0xC9:
            carry, (z, neg), pc = int(a >= code[pc + 1]), nz((a - code[pc + 1]) & 0xFF), pc + 2
        elif op == 0xAD:
            a = ram.get(0x7E0000 + (code[pc + 1] | code[pc + 2] << 8), 0)
            (z, neg), pc = nz(a), pc + 3
        elif op == 0x29:
            a = a & code[pc + 1]
            (z, neg), pc = nz(a), pc + 2
        elif op == 0xE9:
            v = a - code[pc + 1] - (1 - carry)
            a, carry, pc = v & 0xFF, int(v >= 0), pc + 2
            z, neg = nz(a)
        elif op in (0x30, 0x90, 0xB0, 0x10, 0xD0, 0xF0, 0x80):
            take = {0x30: neg, 0x90: not carry, 0xB0: carry, 0x10: not neg, 0xD0: not z, 0xF0: z, 0x80: True}[op]
            d = code[pc + 1] - (0x100 if code[pc + 1] & 0x80 else 0)
            pc += 2 + (d if take else 0)
        else:
            raise AssertionError(f'{op:02X}')
        n += 1
        if n > 2000:
            raise AssertionError('끝나지 않음')


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
        self.assertEqual(got[ev.FRONT, ev.FC_OLD_MAN, False], m['old_man_ask'])

    def test_flags_are_distinct(self):
        flags = (ev.NIGHT_TOLD, ev.FLARE_FOLLOWS, ev.REUNITED, ev.HOIMIN, ev.KIDNAPPED, ev.BOSS_WON, ev.KIDS_FOLLOW,
                 ev.SOLDIER_LEFT, ev.REPORTED, ev.CAVE_TALKED, ev.CAVE_STEP1, ev.CAVE_STEP2, ev.OLD_MAN_TRIED)
        self.assertEqual(len(set(flags)), len(flags))

    def test_old_man_asks_until_he_tried(self):
        m = ev.message_ids(0xD00)
        (top,) = ev.talk_scripts(0xD00)[ev.TALKS.index('old_man')]
        self.assertEqual((top["cond"]["index"], top["cond"]["mask"]), ev.OLD_MAN_TRIED)
        self.assertEqual(top["then"]["id"], f"{m['old_man_tired']:03X}")
        ask, yes_no = top["else"]
        self.assertEqual(ask["id"], f"{m['old_man_ask']:03X}")
        self.assertEqual(yes_no["cond"], {"code": "05"})
        self.assertEqual(yes_no["then"], [ev._flag_on(ev.OLD_MAN_TRIED), ev._msg(m['old_man_yes'])])
        self.assertEqual(yes_no["else"], ev._msg(m['old_man_no']))

    def test_old_man_walks_only_in_the_visit_he_said_yes(self):
        (script,) = [s for s in ev.scripts(0xD00) if s["address"] == ev.OLD_MAN_SCRIPT]
        c = script["commands"]
        self.assertEqual((c[0]["op"], c[0]["args"], c[0]["target"]), ('06', list(ev.OLD_MAN_TRIED), "stay"))
        self.assertEqual(c[1], ev._cmd('09', 0x80 | ev.OLD_MAN_TRIED[0], ev.OLD_MAN_TRIED[1]))
        self.assertIn(ev._cmd('1D', ev.OLD_MAN_INTERVAL), c)
        _, at = ev.native()
        step = next(i for i, x in enumerate(c) if x.get("label") == "follow")
        self.assertEqual(c[step]["args"], ev._long(at['old_man_step']))
        self.assertEqual((c[step + 1]["op"], c[step + 2]["target"]), ('14', "follow"))
        self.assertEqual(c[-1]["label"], "stay")

    def test_old_man_steps_one_tile_toward_the_hero(self):
        def run(man, hero, blocked=()):
            ram = {0x7E3020: hero[0], 0x7E3080: hero[1], 0x7E3020 + 0x10: man[0], 0x7E3080 + 0x10: man[1],
                   **{k: 0x40 + k for k in range(0x10)}, 0x80: 1, 0x81: 2, 0x82: 3}
            target = _run_step(ev._old_man_step(), ram, 0x10, blocked)
            self.assertEqual([target[k] for k in (*range(0x10), 0x80, 0x81, 0x82)],
                             [ram[k] for k in (*range(0x10), 0x80, 0x81, 0x82)])
            return target[0x7E3560 + 0x10], target[0x7E35A0 + 0x10]
        self.assertEqual(run((44, 25), (54, 25)), (46, 25))     # 오른쪽으로 2셀
        self.assertEqual(run((44, 25), (30, 31)), (42, 25))     # X 가 멀면 X 부터
        self.assertEqual(run((44, 25), (45, 35)), (44, 27))     # X 가 붙으면 Y
        self.assertEqual(run((44, 25), (44, 21)), (44, 23))
        self.assertEqual(run((44, 25), (46, 27)), (44, 25))     # 붙어 있으면 그 자리
        self.assertEqual(run((44, 25), (42, 23)), (44, 25))

    def test_old_man_goes_around_a_blocked_cell(self):
        def run(man, hero, blocked):
            ram = {0x7E3020: hero[0], 0x7E3080: hero[1], 0x7E3020 + 0x10: man[0], 0x7E3080 + 0x10: man[1]}
            target = _run_step(ev._old_man_step(), ram, 0x10, blocked)
            self.assertEqual((target[0x7E3020 + 0x10], target[0x7E3080 + 0x10]), man)   # 자리는 되돌려 둠
            return target[0x7E3560 + 0x10], target[0x7E35A0 + 0x10]
        self.assertEqual(run((44, 25), (54, 31), {(46, 25)}), (44, 27))      # 오른쪽이 막히면 아래로
        self.assertEqual(run((44, 25), (30, 19), {(43, 25)}), (44, 23))      # 왼쪽이 막히면 위로
        self.assertEqual(run((44, 25), (54, 25), {(46, 25)}), (44, 25))      # 한 축뿐이고 막히면 그 자리
        self.assertEqual(run((44, 25), (54, 31), {(46, 25), (44, 26)}), (44, 25))   # 둘 다 막히면 그 자리
        self.assertEqual(run((44, 25), (54, 31), {(44, 26)}), (46, 25))      # 앞 축이 열려 있으면 그쪽
        self.assertEqual(run((38, 25), (35, 25), {(36, 25)}), (37, 25))      # 둘째 셀만 막히면 한 셀(왼쪽)
        self.assertEqual(run((44, 25), (49, 25), {(47, 25)}), (45, 25))      # 오른쪽
        self.assertEqual(run((44, 25), (44, 30), {(44, 27)}), (44, 26))      # 아래

    def test_old_man_steps_aside_when_the_hero_walks_into_him(self):
        def run(man, hero, pad, blocked=()):
            ram = {0x7E3020: hero[0], 0x7E3080: hero[1], 0x7E3020 + 0x10: man[0], 0x7E3080 + 0x10: man[1],
                   0x7E0749: pad, **{k: 0x40 + k for k in range(0x10)}}
            target = _run_step(ev._old_man_step(), ram, 0x10, blocked)
            self.assertEqual([target[k] for k in range(0x10)], [ram[k] for k in range(0x10)])
            self.assertEqual((target[0x7E3020 + 0x10], target[0x7E3080 + 0x10]), man)
            return target[0x7E3560 + 0x10], target[0x7E35A0 + 0x10]
        # 성 앞 오른쪽 막다른 열 (70,17)~(70,23) 어귀에 한 셀 어긋나 선 노인(실측)
        self.assertEqual(run((68, 22), (70, 23), 0x02), (66, 22))                       # 주인공이 걷는 쪽으로
        self.assertEqual(run((68, 22), (70, 23), 0x02, {(67, 22)}), (68, 24))           # 막히면 아래
        self.assertEqual(run((68, 22), (70, 23), 0x02, {(67, 22), (68, 23)}), (68, 20))  # 그것도 막히면 위
        self.assertEqual(run((68, 22), (70, 23), 0x02, {(67, 22), (68, 23), (68, 21)}), (68, 22))
        self.assertEqual(run((60, 23), (60, 21), 0x04), (60, 25))
        self.assertEqual(run((60, 23), (60, 25), 0x08), (60, 21))
        self.assertEqual(run((62, 25), (60, 25), 0x01), (64, 25))
        self.assertEqual(run((60, 23), (70, 23), 0x02), (62, 23))       # 붙어 있지 않으면 따라옴
        self.assertEqual(run((68, 23), (70, 23), 0x01), (68, 23))       # 노인 반대쪽을 누르면 그대로
        self.assertEqual(run((68, 23), (70, 23), 0x06), (68, 23))       # 두 방향을 같이 누르면 그대로
        self.assertEqual(run((68, 23), (70, 23), 0x80 | 0x02), (66, 23))   # 패드 아래 니블만 본다


    def test_braggart_jokes_either_way(self):
        m = ev.message_ids(0xD00)
        ask, yes_no = ev.talk_scripts(0xD00)[ev.TALKS.index('braggart')]
        self.assertEqual(ask, ev._msg(m['brag_ask']))
        self.assertEqual((yes_no["cond"], yes_no["then"], yes_no["else"]),
                         ({"code": "05"}, ev._msg(m['brag_joke']), ev._msg(m['brag_joke'])))

    def test_hoimin_fanfare_plays_before_the_join_flag(self):
        m = ev.message_ids(0xD00)
        _, yes_no = ev.talk_scripts(0xD00)[ev.TALKS.index('hoimin')]
        self.assertEqual(yes_no["then"], [ev._msg(m['hoimin_yes']), {"op": "call", "target": f"{ev.FANFARE_AT & 0xFFFF:04X}"},
                                          ev._flag_on(ev.HOIMIN)])
        self.assertEqual(ev.FANFARE_AT >> 16, ev.BATTLE_AT >> 16)
        self.assertLessEqual(ev.BATTLE_AT + len(ev._battle()), ev.FANFARE_AT)
        code = ev._fanfare()
        self.assertEqual(code[3:6], bytes((0x00, 0x0F, ev.JOIN_SONG)))      # BRK 0F 로 틀어야 24:FF0F 가 기다린다
        self.assertIn(bytes((0xAD, 0x4B, 0x19)), code)                      # 맵 곡 $194B 로 돌아감
        self.assertNotIn(bytes((0x22, 0x18, 0x82, 0x20)), code)             # 20:8218(00:CE61)은 팡파르 뒤 멈춤
        self.assertEqual(code[-1], 0x60)

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
        out = ev.apply(_hooked())
        _, at = ev.native()
        o = ev.lorom(ev.FLY_AT)
        self.assertEqual(out[o:o + 5], bytes((0x22, *ev._long(at['fly']), 0xEA)))
        self.assertEqual(out[ev.lorom(ev.FLY_X_AT):][:2], (0x88 * 2).to_bytes(2, 'little'))
        self.assertEqual(out[ev.lorom(ev.FLY_Y_AT):][:2], (0x16 * 2).to_bytes(2, 'little'))
        e = ev.lorom(at['fly_event'])
        self.assertEqual(out[e:e + 8], bytes((0x90, ev.TOWER, 0x00, 18, 25, 0x01, 0x80, 0xFF)))   # FC 30/00 (09,0C)

    def test_guest_ai_hooks_jump_to_the_native(self):
        out = ev.apply(_hooked())
        _, at = ev.native()
        self.assertEqual(out[ev.lorom(ev.GUEST_AI_AT):][:4], bytes((0x5C, *ev._long(at['guest_ai']))))
        self.assertEqual(out[ev.lorom(ev.GUEST_TARGET_AT):][:5], bytes((0x22, *ev._long(at['guest_target']), 0xEA)))
        # 손님이 아니면 덮은 두 ROL 을 하고 원래 고르기로 돌아간다
        code, _, _ = ev._guest_ai(ev.CODE_AT)
        self.assertIn(bytes((0x28, 0x2E, 0x0E, 0x11, 0x2E, 0x0F, 0x11, 0x5C, *ev._long(ev.GUEST_AI_BACK))), code)
        # 가중치 합은 FC 고르는 법 2 의 칸 가중치 합(255)
        self.assertEqual(sum(w for _, w in ev.GUEST_WEIGHTS), 255)

    def test_followers_hook_the_walker_count(self):
        out = ev.apply(_hooked())
        _, at = ev.native()
        self.assertEqual(out[ev.lorom(ev.COUNT_AT):][:5], bytes((0x4C, 0x60, 0xFF, 0xEA, 0xEA)))
        tail = out[ev.lorom(ev.COUNT_TAIL):][:12]
        self.assertEqual(tail, bytes((0x8D, 0x67, 0x19, 0x22, *ev._long(at['followers']), 0x20, 0x5A, 0xCA, 0x28, 0x60)))
        self.assertEqual(out[ev.lorom(ev.SOLO_AT):][:3], bytes((0xEA, 0xEA, 0xEA)))
        self.assertEqual(out[ev.lorom(ev.GUEST_PICTURE_AT):][:2], bytes((0x29, 0x3F)))
        code = ev._followers(ev.CODE_AT)
        # 프레아 하나, 아이 둘을 더하는 부름
        self.assertEqual(code.count(bytes((0xA9, 0x09, 0x20))), 1)
        self.assertEqual(code.count(bytes((0xA9, 0x0B, 0x20))), ev.KIDS_WALKING)
        self.assertEqual(code[-1], 0x60)

    def test_party_changes_redraw_the_walkers(self):
        _, at = ev.native()
        refresh = {'op': '37', 'args': ev._long(at['refresh'])}
        by_address = {s['address']: s['commands'] for s in ev.scripts(0xD00)}
        for script in (ev.FLARE_SCRIPT, ev.THANKS_SCRIPT, ev.KIDS_HOME_SCRIPT):
            self.assertIn(refresh, by_address[script])
        code, _ = ev.native()
        self.assertIn(ev.REFRESH, code[at['join'] - ev.CODE_AT:at['voice0'] - ev.CODE_AT])

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

    def test_level_up_plays_the_song_without_waiting_and_restores_the_map_song(self):
        from dq4chapterbox import ENTER, LEAVE
        body = ev._level_up()[len(ENTER):-len(LEAVE)]
        wait = bytes((0xA9, ev.LEVEL_SONG, 0x22, 0x0F, 0xFF, 0x24))
        play = bytes((0xA9, ev.LEVEL_SONG, 0x22, 0x9A, 0xFE, 0x24))
        restore = bytes((0xAD, 0x4B, 0x19, 0x29, 0x7F, 0x22, 0x9A, 0xFE, 0x24))
        self.assertTrue(body.startswith(wait))                       # 앞 레벨의 곡이 끝나기를 기다림
        self.assertTrue(body.endswith(play))                         # 오른 갈래 끝에서 틀기만
        done = body.index(restore)
        self.assertEqual(body[done - len(wait):done], wait)          # 끝 갈래는 기다린 뒤 맵 곡
        self.assertNotIn(bytes((0x22, 0x18, 0x82, 0x20)), body)      # 20:8218 은 곡이 끝난 뒤 돌아오지 않았다

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
        want = ['walk_in', 'status_count', 'level_up'] + [f'stat_{k}' for k, _ in ev.STATS] + ['level_up', 'walk_back',
                                                                                         'walk_out']
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
            self.assertEqual(m[f'stat_{k}'][-1], ev.LINE_END)
        self.assertEqual(m['line_pause'], [ev.ch1.NARR, ev.WAIT_END])

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

    def test_yes_no_people_take_the_event_talks(self):
        t = ev.talk_numbers(0x904)
        olds = [e for e in self.entries(ev.FRONT) if e["fields"]["talk"] == t['old_man']]
        self.assertEqual([e["from"] for e in olds], [ev.OLD_MAN_SRC])
        self.assertEqual([e["fields"]["gfx"] for e in olds], [ev.OLD_MAN_PICTURE])
        import dq4people
        (sheet,) = [p.sheet for p in dq4people.PEOPLE if ev.OLD_MAN_PICTURE in p.pictures and p.group is None]
        self.assertEqual(sheet, 'h005')     # NDS 가 이 노인에 쓰는 모습 5
        everywhere = [e["from"] for lst in self.lists for e in lst["entries"]] + \
            [e["from"] for lst in self.new for e in lst["entries"]]
        self.assertEqual(everywhere.count(ev.OLD_MAN_SRC), 1)
        old = [p for p in self.report[ev.FRONT] if p["talk"] == ev.FC_OLD_MAN]
        self.assertEqual([p["dq5"]["talk"] != t['old_man'] for p in old], [True])
        self.assertIn(t['old_man'], {e["fields"]["talk"] for e in self.entries(ev.FRONT)})
        (after,) = [lst["entries"] for lst in self.new if lst["name"] == ev.alt_name(ev.AFTER_BOSS, ev.FRONT)]
        self.assertIn(t['braggart'], {e["fields"]["talk"] for e in after})

    def test_event_talks_replace_the_ported_ones(self):
        t = ev.talk_numbers(0x904)
        talks = {e["fields"]["talk"] for m in (ev.FRONT, ev.FRONT_NIGHT, ev.IMURU, ev.JAIL, ev.HOIMIN_ROOM, ev.TOWER_TOP,
                                                ev.CAVE, ev.KING_ROOM, ev.SOLDIER_MAP)
                 for e in self.entries(m)} | {e["fields"]["talk"] for lst in self.new for e in lst["entries"]} | \
            {e["fields"]["talk"] for e in ev.throne_return(0x904)}
        self.assertLessEqual(set(t.values()), talks)


if __name__ == "__main__":
    unittest.main()
