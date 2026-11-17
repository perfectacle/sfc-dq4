"""3장 본몰·여우 마을(dq4ch3bonmalmo): 예약 몫, 다리 훅(w65816 로 돌림), 빈 칸 보기, 대화 갈래, 목록 손질, 빌드 롬의 훅.

빌드 롬 시험(BuiltRomTest)은 DQ4_CH3_ROM 에 dq4build.py --chapter3 의 롬을 주었을 때만 돈다(가드 dq4-ch3-bonmalmo).
"""
import copy
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4ch3bonmalmo as bm  # noqa: E402
import dq4ch3event as ev  # noqa: E402
from dq4ch3slots import SLOTS  # noqa: E402
import dq4itemport  # noqa: E402

DQ4 = ROOT / 'rom' / 'dq4.nes'
BUILT = os.environ.get('DQ4_CH3_ROM')


def _ctx():
    return next(c for c in ev.contexts(0x1000, 0x900) if c.key == 'B')


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def machine(extra=None):
    """(w65816.Cpu, 네이티브 주소): 롬은 이 모듈 네이티브와 extra({주소: 바이트}), WRAM 은 0."""
    from w65816 import Cpu
    code, at = bm.native(_ctx())
    rom = bytearray(0x300000)
    for addr, data in ((_ctx().code_at, code), *(extra or {}).items()):
        rom[lorom(addr):lorom(addr) + len(data)] = data
    return Cpu(bytes(rom), bytearray(0x20000)), at


def flag_at(flag):
    return 0x2190 + flag[0]


class SlotTest(unittest.TestCase):
    def test_flags_scripts_and_lists_are_in_the_slot(self):
        slot = SLOTS['B']
        self.assertTrue(all(i in slot.flags for i, _ in bm.FLAGS))
        allowed = dict(slot.scripts)
        for lst, idx, _ in bm.SCRIPTS.values():
            self.assertIn(idx, allowed[lst])

    def test_flags_are_distinct_bits(self):
        seen = set()
        for i, m in bm.FLAGS:
            self.assertEqual(bin(m).count('1'), 1)
            self.assertNotIn((i, m), seen)
            seen.add((i, m))

    def test_code_fits_the_slot(self):
        code, _ = bm.native(_ctx())
        start, end = SLOTS['B'].code
        self.assertLessEqual(start + len(code), end)

    def test_story_items_are_the_event_items(self):
        self.assertEqual(bm.PRINCE_LETTER, dq4itemport.PRINCE_LETTER)
        self.assertEqual(bm.KING_LETTER, dq4itemport.KING_LETTER)


class BridgeTest(unittest.TestCase):
    CELLS = list(bm.BRIDGE_CELLS)

    def run_hook(self, chapter3=True, bridge=False, world=0):
        cpu, at = machine({bm.SEA_FRAMES: b'\x6b'})
        w = cpu.wram
        for x, y in self.CELLS:
            w[0x10000 + y * 256 + x] = bm.bridge_blocks()[0] & 0xFF
        if chapter3:
            w[flag_at(ev.CHAPTER3)] |= ev.CHAPTER3[1]
        if bridge:
            w[flag_at(bm.BRIDGE)] |= bm.BRIDGE[1]
        w[bm.WORLD & 0xFFFF] = world
        cpu.p = 0x30
        cpu.jsl(at['bridge_hook'], max_steps=500)
        return [w[0x10000 + y * 256 + x] for x, y in self.CELLS], cpu

    def test_blocks_share_the_plane(self):
        bridge, blocked = bm.bridge_blocks()
        self.assertEqual(bridge >> 8, blocked >> 8)
        self.assertNotEqual(bridge & 0xFF, blocked & 0xFF)

    def test_hook_calls_the_sea_frames_first(self):
        code = bm._bridge_hook(bm.SEA_FRAMES, self.CELLS)
        self.assertEqual(code[:4], bytes((0x22, *bm.SEA_FRAMES.to_bytes(3, 'little'))))
        self.assertEqual(code[-2:], b'\x28\x6b')

    def test_chapter3_without_bridge_blocks_the_cells(self):
        got, cpu = self.run_hook()
        self.assertEqual(got, [bm.bridge_blocks()[1] & 0xFF] * len(self.CELLS))
        self.assertEqual(cpu.p & 0x30, 0x30)

    def test_fixed_bridge_other_chapter_or_world_leave_the_cells(self):
        keep = [bm.bridge_blocks()[0] & 0xFF] * len(self.CELLS)
        self.assertEqual(self.run_hook(bridge=True)[0], keep)
        self.assertEqual(self.run_hook(chapter3=False)[0], keep)
        self.assertEqual(self.run_hook(world=1)[0], keep)

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_cells_are_the_fc_bridges(self):
        self.assertEqual(bm.bridge_cells(DQ4), self.CELLS)

    def test_follower_dog_leaves_only_in_the_fox_town(self):
        # 걷는 그림 장치는 맵 안 임시 비트를 이 맵에서만 본다(다른 맵에서는 다른 뜻)
        import dq4ch1event
        self.assertEqual(dq4ch1event.DOG_AWAY_MAP, bm.FOX_TOWN)
        self.assertEqual(bm.DOG_AWAY, dq4ch1event.DOG_AWAY)
        self.assertNotIn(bm.DOG_AWAY, (bm.NANNY_SCOLDED, bm.NANNY_GO))

    def test_enter_hook_goes_before_the_entrance_hook(self):
        (site, orig, new), = [h for h in bm.hooks(_ctx()) if h[0] == bm.ENTER_SITE]
        import dq4groupbuild
        self.assertEqual(orig, bytes((0x5C, *dq4groupbuild.ENTRANCE_HOOK_AT.to_bytes(3, 'little'))))
        code = bm._enter_hook()
        self.assertEqual(code[0], 0x08)
        self.assertEqual(code[-4:], orig)                     # 아니면 원래 훅으로
        back = bytes((0xA5, 0xBC, 0xC9, 0x16, 0x5C, *bm.ENTER_BACK.to_bytes(3, 'little')))
        self.assertIn(back, code)                              # 여우 마을이면 훅이 하던 끝맺음

    def test_hook_replaces_the_sea_call(self):
        (site, orig, new), = [h for h in bm.hooks(_ctx()) if h[0] == bm.FIELD_CALL]
        self.assertEqual(site, bm.FIELD_CALL)
        self.assertEqual(orig, bytes((0x22, *bm.SEA_FRAMES.to_bytes(3, 'little'))))
        self.assertEqual(new, bytes((0x22, *_ctx().at['bridge_hook'].to_bytes(3, 'little'))))


class RoomTest(unittest.TestCase):
    def run_room(self, walking, filled):
        cpu, at = machine()
        w = cpu.wram
        w[0x201E] = walking
        items = ev.PARTY_ITEMS & 0xFFFF
        for r in range(4):
            for k in range(ev.ITEM_SLOTS):
                w[items + r * ev.RECORD + k] = 0x02 if (r, k) in filled else 0xFF
        w[flag_at(ev.RESULT)] = ev.RESULT[1]
        cpu.jsl(at['room'], max_steps=20000)
        return bool(w[flag_at(ev.RESULT)] & ev.RESULT[1])

    def test_room_when_a_walking_record_has_a_free_slot(self):
        everything = {(r, k) for r in range(4) for k in range(ev.ITEM_SLOTS)}
        self.assertTrue(self.run_room(1, set()))
        self.assertFalse(self.run_room(1, {(0, k) for k in range(ev.ITEM_SLOTS)}))
        self.assertTrue(self.run_room(2, {(0, k) for k in range(ev.ITEM_SLOTS)}))
        self.assertFalse(self.run_room(4, everything))
        self.assertTrue(self.run_room(1, {(0, k) for k in range(ev.ITEM_SLOTS - 1)}))


def _walk(body, path=()):
    """대화 본문의 갈래를 모두 펼쳐 [(갈래 경로, op)]."""
    out = []
    for i, op in enumerate(body if isinstance(body, list) else [body]):
        out.append((path, op))
        if op.get('op') == 'if':
            out += _walk(op['then'], path + ((i, 'then'),))
            out += _walk(op.get('else', []), path + ((i, 'else'),))
    return out


class TalkTest(unittest.TestCase):
    def setUp(self):
        self.ctx = _ctx()
        self.bodies = dict(zip(bm.TALKS, bm.talk_scripts(self.ctx)))

    def msgs(self, name):
        return [int(op['id'], 16) for _, op in _walk(self.bodies[name]) if op.get('op') == 'msg']

    def test_every_message_is_used(self):
        used = {m for name in bm.TALKS for m in self.msgs(name)}
        used |= {c['args'][0] | c['args'][1] << 8 for s in bm.scripts(self.ctx) for c in s['commands'] if c['op'] == '21'}
        self.assertEqual(set(self.ctx.msg.values()) - used, set())

    def test_first_day_meeting_marks_the_scolding(self):
        ops = [op for _, op in _walk(self.bodies['prince'])]
        self.assertIn(self.ctx.flag_on(bm.NANNY_SCOLDED), ops)
        self.assertEqual(bm.NANNY_SCOLDED[0], 0x13)          # 7E:21A3: 맵을 옮기면 지워지는 자리

    def test_letter_branch_comes_before_the_bridge(self):
        king = self.bodies['king'][0]
        self.assertEqual(king['cond'], self.ctx.flag(bm.LETTER2))
        inner = king['else'][0]
        self.assertEqual(inner['cond'], self.ctx.has(bm.KING_LETTER))
        self.assertEqual(inner['else'][0]['cond'], self.ctx.flag(bm.FOXED))

    def test_yes_no_repeats_until_yes(self):
        son = self.bodies['son']
        asks = [op for _, op in _walk(son) if op.get('op') == 'if' and op['cond'] == bm.YES]
        self.assertEqual(len(asks), bm.ASK_DEPTH)
        please = self.ctx.msg['son_please']
        self.assertEqual(self.msgs('son').count(please), bm.ASK_DEPTH)

    def test_fox_always_answers(self):
        fox = self.bodies['fox']
        self.assertEqual(fox[-1], self.ctx.flag_on(bm.ANSWERED))

    def test_monica_is_left_on_the_base_list(self):
        # 기본 40/06 은 2장에도 쓰이고 2장 동료 대화가 대화 번호로 사람을 찾는다(dq4-ch2-partytalk)
        lists = _lists()
        before = lists[bm.ENDOR_THRONE]["entries"][0]["fields"]["talk"]
        bm.npc_lists(lists, self.ctx)
        self.assertEqual(lists[bm.ENDOR_THRONE]["entries"][0]["fields"]["talk"], before)

    def test_monica_talk_is_the_module_talk(self):
        first = min(self.ctx.talk.values()) - sum(len(getattr(m, 'TALKS', ())) for k, m in ev.modules()
                                                   if list(ev.SLOTS).index(k) < list(ev.SLOTS).index('B'))
        self.assertEqual(bm.monica_talk(first), self.ctx.talk['monica'])

    def test_monica_swaps_the_letters(self):
        calls = [op['args'][0] for _, op in _walk(self.bodies['monica']) if op.get('op') == 'call']
        c = self.ctx.calls
        self.assertEqual(calls[:2], [c['take_prince_letter'], c['give_king_letter']])

    def test_chief_with_the_dog_goes_to_the_forest(self):
        chief = self.bodies['chief'][0]
        self.assertEqual(chief['cond'], self.ctx.flag(ev.DOG))
        self.assertEqual(chief['then'][-1], self.ctx.call('fox_go'))


def _lists():
    def person(x, y, time='day', talk=1):
        return {"from": {"list": "05:870A", "index": 2}, "time": time,
                "fields": {"x": x, "y": y, "facing": "down", "talk": talk, "gfx": 1, "layer": 0, "interval": 0}}
    return {
        bm.CASTLE: {"map": bm.CASTLE, "entries": [person(*bm.PRINCE['day']), person(*bm.PRINCE['night'], 'night'),
                                                   person(*bm.KING), person(*bm.KING, 'night'), person(*bm.NANNY),
                                                   person(*bm.SECOND_NANNY)]},
        bm.PRISON: {"map": bm.PRISON, "entries": [person(*bm.SON)]},
        bm.FOX_TOWN: {"map": bm.FOX_TOWN, "entries": [person(*bm.CORNER_DOG), person(*bm.CORNER_DOG, 'night'),
                                                       person(*bm.CHIEF), person(*bm.CHIEF, 'night')]},
        bm.FOREST: {"map": bm.FOREST, "entries": [person(*bm.FOX), person(*bm.GAADE)]},
        bm.ENDOR_THRONE: {"map": bm.ENDOR_THRONE, "entries": [person(*bm.MONICA)]},
    }


class ListTest(unittest.TestCase):
    def test_people_get_the_talks_and_scripts(self):
        ctx = _ctx()
        lists = _lists()
        new, over = bm.npc_lists(lists, ctx)
        t = ctx.talk
        castle = lists[bm.CASTLE]["entries"]
        self.assertEqual([e["fields"]["talk"] for e in castle], [t['prince'], t['prince'], t['king'], t['king'], 1])
        self.assertEqual(castle[-1]["from"], bm._src('nanny'))
        self.assertNotIn(bm.SECOND_NANNY, [bm._at(e) for e in castle])
        son = lists[bm.PRISON]["entries"][0]
        self.assertEqual(son["from"], bm._src('son'))
        town = lists[bm.FOX_TOWN]["entries"]
        dogs = [e for e in town if bm._at(e) == bm.CORNER_DOG]
        self.assertEqual([(e["from"], e["fields"]["talk"]) for e in dogs],
                         [(bm._src('village_dog'), t['dog']), (bm._src('village_dog_night'), t['dog'])])
        forest = lists[bm.FOREST]["entries"]
        self.assertEqual([e["from"] for e in forest], [bm._src('fox'), bm._src('gaade')])
        self.assertEqual((new, over), ([], []))

    def test_missing_person_stops_the_build(self):
        lists = _lists()
        lists[bm.PRISON]["entries"] = []
        with self.assertRaises(SystemExit):
            bm.npc_lists(lists, _ctx())

    def test_lists_without_people_are_left_alone(self):
        self.assertEqual(bm.npc_lists({}, _ctx()), ([], []))

    def test_absent_are_the_second_nanny_and_the_hidden_dog_and_fox(self):
        self.assertEqual(bm.absent(), {(bm.FOX_TOWN, *bm.CORNER_DOG, False), (bm.FOX_TOWN, *bm.CORNER_DOG, True),
                                       (bm.FOREST, *bm.FOX, False), (bm.CASTLE, *bm.SECOND_NANNY, False)})
        self.assertLessEqual(bm.absent(), ev.absent())

    def test_start_messages_are_module_messages(self):
        ctx = _ctx()
        self.assertTrue(set(bm.start_messages(ctx).values()) <= set(ctx.msg.values()))


class ScriptTest(unittest.TestCase):
    def test_scripts_go_to_the_borrowed_slots(self):
        out = bm.scripts(_ctx())
        self.assertEqual([s["address"] for s in out], [v[2] for v in bm.SCRIPTS.values()])

    def test_fox_hides_outside_the_scene(self):
        fox = next(s for s in bm.scripts(_ctx()) if s["address"] == bm.SCRIPTS['fox'][2])["commands"]
        hide = {"op": "06", "args": [0x80 | bm.FOX_SCENE[0], bm.FOX_SCENE[1]], "target": "gone"}
        self.assertIn(hide, fox[:3])


@unittest.skipUnless(BUILT and Path(BUILT).is_file(), 'DQ4_CH3_ROM(3장 빌드 롬) 없음')
class BuiltRomTest(unittest.TestCase):
    def setUp(self):
        self.rom = Path(BUILT).read_bytes()
        self.ctx = _ctx()

    def test_field_call_goes_through_the_bridge_hook(self):
        o = lorom(bm.FIELD_CALL)
        hook = self.ctx.at['bridge_hook']
        self.assertEqual(self.rom[o:o + 4], bytes((0x22, *hook.to_bytes(3, 'little'))))
        # 환경 훅 wrap 자리(01:9FD6)는 그대로
        w = lorom(0x019FD6)
        self.assertEqual(self.rom[w], 0x22)
        self.assertNotEqual(int.from_bytes(self.rom[w + 1:w + 4], 'little'), hook)

    def test_entrance_goes_through_the_fox_forest_hook(self):
        o = lorom(bm.ENTER_SITE)
        self.assertEqual(self.rom[o:o + 4], bytes((0x5C, *self.ctx.at['enter_hook'].to_bytes(3, 'little'))))
        code = bm._enter_hook()
        self.assertEqual(code[-4:], bytes((0x5C, *bm._entrance_hook_at().to_bytes(3, 'little'))))

    def test_native_is_in_place(self):
        code, _ = bm.native(self.ctx)
        o = lorom(self.ctx.code_at)
        self.assertEqual(self.rom[o:o + len(code)], code)


if __name__ == '__main__':
    unittest.main()
