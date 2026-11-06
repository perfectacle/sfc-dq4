"""2장 사건 전투 진입(dq4ch2battle)과 사건 등록 장치(dq4ch2event.EVENTS)."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1event  # noqa: E402
import dq4ch2battle as battle  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4ch2slots as slots  # noqa: E402
import dq4chapter1 as ch1  # noqa: E402


class BattleTest(unittest.TestCase):
    def test_common_routine(self):
        code = battle.common()
        won = (0x2190 + slots.BATTLE_WON[0]).to_bytes(2, 'little') + b'\x7e'
        self.assertEqual(code.hex(), (
            '08e2308b4bab48'                          # PHP / SEP #$30 / PHB / PHK / PLB / PHA
            f'af{won.hex()}297f8f{won.hex()}'          # 이김 flag 끄기
            '000e68228b8601'                          # BRK 0E / PLA / JSL 01:868B
            f'c980f00aaf{won.hex()}09808f{won.hex()}'  # 전멸(80)이 아니면 켜기
            'ab286b'))                                # PLB / PLP / RTL
        self.assertEqual(len(code), battle.STUBS_AT - battle.COMMON_AT)

    def test_same_battle_call_as_chapter_one(self):
        # 1장 탑 위 보스(dq4ch1event._battle)와 같은 BRK 0E / LDA / JSL 01:868B / CMP #$80
        one = dq4ch1event._battle()
        self.assertTrue(one.startswith(bytes((0x00, 0x0E, 0xA9))))
        self.assertIn(bytes((0x22, 0x8B, 0x86, 0x01, 0xC9, 0x80)), one)
        self.assertIn(bytes((0x00, 0x0E, 0x68, 0x22, 0x8B, 0x86, 0x01, 0xC9, 0x80)), battle.common())

    def test_stubs_fit_before_the_window_name_spot(self):
        import dq4windowname
        self.assertEqual(battle.END, dq4windowname.BUY_SPOT)
        self.assertLessEqual(battle.stub_at(battle.STUB_COUNT - 1) + battle.STUB_SIZE, battle.END)
        self.assertGreaterEqual(battle.COMMON_AT, dq4ch1event.FANFARE_AT + len(dq4ch1event._fanfare()))
        with self.assertRaises(ValueError):
            battle.stub_at(battle.STUB_COUNT)

    def test_stub_and_far_call(self):
        self.assertEqual(battle.stub(0x31).hex(), 'e220a93122' + '58ff06' + '60')
        self.assertEqual(len(battle.stub(0x31)), battle.STUB_SIZE)
        self.assertEqual(battle.far(0x32).hex(), 'e220a93222' + '58ff06')
        self.assertEqual(battle.talk_call(1), {"op": "call", "target": f"{battle.STUBS_AT + 9 & 0xFFFF:04X}"})
        self.assertEqual(battle.won_cond(), {"code": "1B", "index": 0x78, "mask": 0x80})

    def test_writes(self):
        w = battle.writes({0: 0x31, 2: 0x33})
        self.assertEqual([a for a, _ in w], [battle.COMMON_AT, battle.STUBS_AT, battle.STUBS_AT + 18])
        self.assertEqual(battle.group_doc(0x31, [(0xE0, 1), (0xE1, 2)]),
                         {"index": 0x31, "flags": 0x42, "members": [{"monster": 0xE0, "count": 1},
                                                                     {"monster": 0xE1, "count": 2}]})


def _fake():
    """E1 몫을 쓰는 시험용 사건 모듈."""
    m = types.ModuleType('dq4ch2tempe')
    m.FLAGS = ((0x60, 0x01),)
    m.MESSAGES = {'a': ch1.say('하나'), 'b': ch1.say('둘')}
    m.TALKS = ('t',)
    m.BATTLES = ({"group": 0x31, "members": ((0xE0, 1),), "stub": 0},)
    m.MONSTERS = {0xE0: 0x00}

    def native(ctx):
        code = bytearray(ev.ENTER + battle.far(0x31) + ev.LEAVE)
        return bytes(code), {'go': ctx.code_at}
    m.native = native
    m.hooks = lambda ctx: []
    m.talk_scripts = lambda ctx: [[{"op": "msg", "id": f"{ctx.msg['a']:03X}"}, battle.talk_call(0),
                                   {"op": "if", "cond": battle.won_cond(), "then": {"op": "msg", "id": f"{ctx.msg['b']:03X}"}}]]
    m.scripts = lambda ctx: [{"address": "05:9C32", "commands": [{"op": "37", "args": list(ctx.at['go'].to_bytes(3, 'little'))}]}]
    m.npc_lists = lambda lists, ctx: ([{"name": "ch2_tempe2_after", "entries": []}],
                                      [{"map": ev.TEMPE, "flag": 0x60, "when": "on", "mask": 1, "list": "new:ch2_tempe2_after"}])
    m.events = lambda ctx: [[('msg', ctx.msg['b']), b'\xff']]
    m.start_messages = lambda ctx: {(ev.TEMPE, 0x777, None): ctx.msg['a']}
    return m


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.fake = _fake()
        p1 = mock.patch.dict(sys.modules, {'dq4ch2tempe': self.fake})
        p2 = mock.patch.object(ev, 'EVENTS', ('dq4ch2tempe',))
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_nothing_registered_keeps_the_old_numbers(self):
        with mock.patch.object(ev, 'EVENTS', ()):
            self.assertEqual(ev.contexts(0x1000), [])
            self.assertEqual(len(ev.texts(0x1000)), len(ev.MESSAGES))
            self.assertEqual(ev.talk_names(), list(ev.TALKS))
            self.assertEqual(len(ev.talk_scripts(0x1000)), len(ev.TALKS))

    def test_messages_and_talks_follow_the_base_ones(self):
        ctx, = ev.contexts(0x1000, 0x950)
        self.assertEqual(ctx.msg, {'a': 0x1000 + len(ev.MESSAGES), 'b': 0x1001 + len(ev.MESSAGES)})
        self.assertEqual(ctx.talk, {'t': 0x950 + len(ev.TALKS)})
        self.assertEqual(sorted(ev.texts(0x1000))[-2:], [ctx.msg['a'], ctx.msg['b']])
        self.assertEqual(ev.talk_names()[-1], 'E1.t')
        self.assertEqual(len(ev.talk_scripts(0x1000)), len(ev.TALKS) + 1)
        self.assertIn(self.fake.events(ctx)[0], ev.event_tokens(0x1000))
        self.assertIn((ev.TEMPE, 0x777, None), ev.start_messages(0x1000))

    def test_unknown_module_is_refused(self):
        with mock.patch.object(ev, 'EVENTS', ('dq4nosuch',)), self.assertRaises(SystemExit):
            ev.modules()

    def test_battles_and_monsters(self):
        self.assertEqual(ev.battle_stubs(), {0: 0x31})
        self.assertEqual(ev.encounter_groups(), [battle.group_doc(0x31, ((0xE0, 1),))])
        with mock.patch.object(dq4ch1event, 'fc_monster', return_value={'HP': 1}):
            self.assertEqual(ev.monster_entries(b''), [{"id": "E0", "HP": 1}])

    def test_npc_lists_take_the_prefix(self):
        new, over = ev.module_lists({}, 0x950)
        self.assertEqual([n["name"] for n in new], ['ch2_tempe2_after'])
        self.assertEqual(over[0]["list"], 'new:ch2_tempe2_after')
        self.fake.npc_lists = lambda lists, ctx: ([{"name": "tempe_after", "entries": []}], [])
        with self.assertRaisesRegex(SystemExit, '앞머리|시작하지 않음'):
            ev.module_lists({}, 0x950)

    def test_apply_writes_module_code_and_battle_entries(self):
        size = 0x400000
        data = bytearray(size)
        o = ch1.lorom(ev.HERO_PICTURE_AT)
        data[o:o + len(ev.HERO_PICTURE_ORIG)] = ev.HERO_PICTURE_ORIG
        o = ch1.lorom(ev.STEP_HOOK_AT)
        data[o:o + len(ev.STEP_HOOK_ORIG)] = ev.STEP_HOOK_ORIG
        with mock.patch.object(ev, 'person_record', return_value=bytes(42)), \
                mock.patch.object(ev, 'alena_record', return_value=bytes(42)), \
                mock.patch.object(ev, 'recruit_records', return_value=[bytes(42)] * 2):
            out = ev.apply(bytes(data), bytes(size), 0x1000)
        o = ch1.lorom(slots.SLOTS['E1'].code[0])
        code, _ = self.fake.native(ev.contexts(0x1000)[0])
        self.assertEqual(out[o:o + len(code)], code)
        o = ch1.lorom(battle.COMMON_AT)
        self.assertEqual(out[o:o + len(battle.common())], battle.common())
        o = ch1.lorom(battle.stub_at(0))
        self.assertEqual(out[o:o + battle.STUB_SIZE], battle.stub(0x31))

    def test_code_over_the_slot_is_refused(self):
        self.fake.native = lambda ctx: (bytes(0x2000), {})
        data = bytearray(0x400000)
        for addr, orig in ((ev.HERO_PICTURE_AT, ev.HERO_PICTURE_ORIG), (ev.STEP_HOOK_AT, ev.STEP_HOOK_ORIG)):
            o = ch1.lorom(addr)
            data[o:o + len(orig)] = orig
        with mock.patch.object(ev, 'person_record', return_value=bytes(42)), \
                mock.patch.object(ev, 'alena_record', return_value=bytes(42)), \
                mock.patch.object(ev, 'recruit_records', return_value=[bytes(42)] * 2), \
                self.assertRaisesRegex(SystemExit, '예약'):
            ev.apply(bytes(data), bytes(0x400000), 0x1000)


if __name__ == '__main__':
    unittest.main()
