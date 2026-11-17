"""3장 사건 자원 예약표(dq4ch3slots)와 등록 장치(dq4ch3event 의 EVENTS·Context·대화 호출 표): 몫끼리·2장 몫과 겹치지
않는지, 등록된 모듈이 몫 안인지, 가짜 모듈 둘을 꽂아도 번호가 이어지고 몫 밖을 쓰면 빌드가 멈추는지."""

import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4ch2slots as ch2slots  # noqa: E402
import dq4ch3event as ev  # noqa: E402
import dq4ch3slots as slots  # noqa: E402

SLOTS = slots.SLOTS
DQ5 = ROOT / 'rom' / 'dq5.sfc'


class SlotTest(unittest.TestCase):
    def test_code_areas_stay_in_one_bank_and_off_each_other_and_chapter_two(self):
        areas = [(k, s.code) for k, s in SLOTS.items()] + [('base', slots.BASE_CODE), ('raft', slots.RAFT_CODE)]
        areas += [(f'ch2.{k}', s.code) for k, s in ch2slots.SLOTS.items()]
        areas += [('ch2.base', ch2slots.BASE_CODE)]
        for k, (lo, hi) in areas:
            self.assertLess(lo, hi, k)
            self.assertEqual(lo >> 16, (hi - 1) >> 16, f'{k}: 뱅크를 넘음')
            self.assertGreaterEqual(lo & 0xFFFF, 0x8000, k)
        for i, (k, (lo, hi)) in enumerate(areas):
            for k2, (lo2, hi2) in areas[i + 1:]:
                self.assertTrue(hi <= lo2 or hi2 <= lo, f'{k} 와 {k2} 의 코드 자리가 겹침')
        self.assertEqual(slots.BASE_CODE, (ev.CODE_AT, ev.CODE_END))
        self.assertEqual(slots.BASE_CODE, ch2slots.CHAPTER3_CODE)
        self.assertTrue(ev.CODE_AT < ev.TABLE_AT < ev.CODE_END)

    def test_flag_bytes_are_owned_once_and_not_by_chapter_two(self):
        seen = {f: 'common' for f in slots.COMMON_FLAGS}
        for k, s in SLOTS.items():
            for f in s.flags:
                self.assertNotIn(f, seen, f'{f + 0x2190:04X} 를 {seen.get(f)} 와 {k} 가 함께 가짐')
                seen[f] = k
        for f in slots.SPARE['flags']:
            self.assertNotIn(f, seen)
        mine = set(seen) | set(slots.SPARE['flags'])
        ch2_flags = {f for s in ch2slots.SLOTS.values() for f in s.flags} | set(ch2slots.SPARE['flags'])
        self.assertFalse(mine & ch2_flags)
        # dq4ch2slots 「flag 자리」: 21F0~220C 가운데 고정 주소로도 쓰이는 바이트와 비트째 쓰는 2208 은 뺀다
        for f in mine:
            self.assertTrue(0x60 <= f <= 0x7C, f'{f + 0x2190:04X}')
            self.assertNotIn(f, {0x65, 0x66, 0x68, 0x69, 0x6A, 0x6B, 0x78}, f'{f + 0x2190:04X}')
        # 2장이 쓰던 예비 13바이트를 남김없이 넘겼다
        self.assertEqual(mine, {0x6F, *range(0x70, 0x78), 0x79, 0x7A, 0x7B, 0x7C})

    def test_common_flags_are_in_the_common_byte(self):
        for f in (ev.RESULT, ev.DOG, ev.SCOTT, ev.LAWRENCE):
            self.assertIn(f[0], slots.COMMON_FLAGS)
        self.assertEqual(len({ev.RESULT, ev.DOG, ev.SCOTT, ev.LAWRENCE}), 4)

    def test_vars_stay_in_the_free_monster_slot(self):
        spans = [('common', slots.COMMON_VARS)] + ([('spare', slots.SPARE['vars'])] if slots.SPARE['vars'] else [])
        spans += [(k, s.vars) for k, s in SLOTS.items() if s.vars]
        used = set()
        for k, (lo, hi) in spans:
            self.assertTrue(0 <= lo < hi <= slots.VARS_SIZE, k)
            span = set(range(lo, hi))
            self.assertFalse(used & span, k)
            used |= span
        self.assertEqual(used, set(range(slots.VARS_SIZE)))
        # 칸 첫 바이트(찬 칸 표시)를 건너뛰고, 3장 넘김이 아리나 일행을 맡기는 칸 앞이다
        self.assertEqual(slots.VARS_AT, ev.MONSTER_SLOTS + slots.VARS_SLOT * ev.MONSTER_SLOT + 1)
        self.assertEqual(slots.VARS_SIZE, ev.MONSTER_SLOT - 1)
        self.assertLess(slots.VARS_SLOT, ev.STASH_FIRST)
        first_stash = min(dst for _, dst, _ in ev.stash_pieces())
        self.assertLessEqual(slots.VARS_AT + slots.VARS_SIZE, first_stash)
        for a in (ev.SCOTT_DAYS, ev.LAWRENCE_DAYS, ev.CLOCK):
            self.assertTrue(slots.VARS_AT + slots.COMMON_VARS[0] <= a < slots.VARS_AT + slots.COMMON_VARS[1])

    def test_borrowed_script_lists_are_owned_once_and_used_by_no_other_tool(self):
        owners = slots.script_lists()
        self.assertEqual(len(owners), sum(len(s.scripts) for s in SLOTS.values()))
        self.assertFalse(set(owners) & set(ch2slots.script_lists()))
        self.assertNotIn(ev.OPENER_SRC['list'], owners)
        modules = {s.module: k for k, s in SLOTS.items()}
        for path in HERE.glob('*.py'):
            if path.stem.startswith('test_') or path.stem == 'dq4ch3slots':
                continue
            text = path.read_text()
            for lst, key in owners.items():
                if f'"{lst}"' in text or f"'{lst}'" in text:
                    self.assertEqual(modules.get(path.stem), key, f'{path.name} 가 {key} 의 목록 {lst} 를 씀')

    def test_list_prefixes_are_distinct_and_miss_the_opening_list(self):
        prefixes = [s.lists for s in SLOTS.values()]
        for p in prefixes:
            self.assertTrue(p.startswith('ch3_') and p.endswith('_'), p)
            self.assertFalse([q for q in prefixes if q != p and q.startswith(p)], p)
            self.assertFalse('ch3_opening'.startswith(p), p)

    def test_no_tool_names_a_reserved_flag_byte_or_the_vars(self):
        # 이 표와 사건 모듈만 이 자리를 쓴다. 다른 도구가 롱 주소로 직접 읽고 쓰면 예약이 깨진다
        mine = {f + 0x2190 for f in slots.COMMON_FLAGS} | {f + 0x2190 for s in SLOTS.values() for f in s.flags} | \
            {f + 0x2190 for f in slots.SPARE['flags']} | set(range(slots.VARS_AT & 0xFFFF,
                                                                    (slots.VARS_AT & 0xFFFF) + slots.VARS_SIZE))
        owners = {s.module for s in SLOTS.values()} | {'dq4ch3slots', 'dq4ch3event'}
        for path in HERE.glob('*.py'):
            if path.stem.startswith('test_') or path.stem in owners:
                continue
            for m in re.finditer(r'0x7E(2[0-9A-Fa-f]{3})\b|7E:(2[0-9A-F]{3})\b', path.read_text()):
                addr = int(m[1] or m[2], 16)
                self.assertNotIn(addr, mine, f'{path.name}: 예약된 자리 {addr:04X}')


class RegisteredModuleTest(unittest.TestCase):
    """EVENTS(있는 모듈 파일)가 몫 안인지. 견본 dq4ch3lakanaba 가 늘 있다."""

    def test_events_follow_the_slot_order_and_files(self):
        order = [s.module for s in SLOTS.values()]
        self.assertEqual(list(ev.EVENTS), [m for m in order if (HERE / f'{m}.py').is_file()])
        self.assertIn('dq4ch3lakanaba', ev.EVENTS)
        # 사건 모듈처럼 보이는 3장 파일은 모두 예약표에 있다(오타로 등록이 빠지지 않게)
        tools = {'dq4ch3event', 'dq4ch3slots', 'dq4ch3opencheck'}
        for path in HERE.glob('dq4ch3*.py'):
            if path.stem not in tools and not path.stem.endswith('check'):
                self.assertIn(path.stem, order, f'{path.name}: dq4ch3slots.SLOTS 에 없는 3장 모듈')

    def test_modules_stay_in_their_slots(self):
        for ctx in ev.contexts(0x1000):
            for idx, _ in getattr(ctx.module, 'FLAGS', ()):
                self.assertIn(idx, ctx.slot.flags, ctx.key)
            if hasattr(ctx.module, 'native'):
                code, at = ctx.module.native(ctx)
                self.assertLessEqual(ctx.code_at + len(code), ctx.slot.code[1], ctx.key)
                self.assertEqual(at, ctx.at, f'{ctx.key}: 주소가 롬에 따라 바뀜')

    def test_talks_encode(self):
        import dq5talkwrite
        for k, body in enumerate(ev.talk_scripts(0x1000)):
            dq5talkwrite.encode_script(body, f'3장 대화 {k}')


def _fake(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


class FakeModuleTest(unittest.TestCase):
    """예약표의 두 자리에 가짜 모듈을 꽂아 번호 매기기와 몫 검사를 본다."""

    def plug(self, a, b):
        mods = {SLOTS['S'].module: a, SLOTS['T'].module: b}
        events = (SLOTS['S'].module, SLOTS['T'].module)
        return mock.patch.multiple(ev, EVENTS=events), mock.patch.dict(sys.modules, mods)

    def test_two_modules_number_messages_talks_and_calls_in_order(self):
        msg = {'a': ['x'], 'b': ['y']}
        a = _fake('fa', MESSAGES=msg, TALKS=('t1', 't2'), CALLS={'give': ('give', 0xBB), 'pay': ('pay', 35000)},
                  talk_scripts=lambda ctx: [[ctx.say('a')], [ctx.call('pay'), ctx.when(ctx.paid(), [ctx.say('b')])]])
        b = _fake('fb', MESSAGES={'c': ['z']}, TALKS=('t',), CALLS={'take': ('take', 0xBD)},
                  talk_scripts=lambda ctx: [[ctx.call('take'), ctx.say('c')]])
        p1, p2 = self.plug(a, b)
        with p1, p2:
            ctxs = ev.contexts(0x1000, 0x900)
            self.assertEqual([c.key for c in ctxs], ['S', 'T'])
            first = 0x1000 + len(ev.MESSAGES)
            self.assertEqual(ctxs[0].msg, {'a': first, 'b': first + 1})
            self.assertEqual(ctxs[1].msg, {'c': first + 2})
            self.assertEqual(ctxs[0].talk, {'t1': 0x900, 't2': 0x901})
            self.assertEqual(ctxs[1].talk, {'t': 0x902})
            self.assertEqual(ctxs[0].calls, {'give': 0, 'pay': 1})
            self.assertEqual(ctxs[1].calls, {'take': 2})
            self.assertEqual(ev.talk_names(), ['S.t1', 'S.t2', 'T.t'])
            self.assertEqual(sorted(ev.texts(0x1000)), list(range(0x1000, 0x1000 + ev.message_count())))
            base = ev.native()[1]
            table = ev.call_table()
            self.assertEqual(table, ev._al(base['give']) + b'\xbb' + ev._al(base['pay']) + bytes((ev.AMOUNTS.index(35000),)) +
                             ev._al(base['take']) + b'\xbd')
            import dq5talkwrite
            for k, body in enumerate(ev.talk_scripts(0x1000)):
                dq5talkwrite.encode_script(body, f'가짜 {k}')

    def test_flag_outside_the_slot_stops_the_build(self):
        # 'S' 몫(21F2)의 모듈이 'T' 몫(21F7)을 적으면 두 모듈이 같은 바이트를 덮게 된다
        a = _fake('fa', FLAGS=((SLOTS['T'].flags[0], 0x01),))
        b = _fake('fb', FLAGS=((SLOTS['T'].flags[0], 0x01),))
        p1, p2 = self.plug(a, b)
        with p1, p2, self.assertRaises(SystemExit):
            ev.contexts()

    def test_unknown_amount_and_unknown_routine_stop_the_build(self):
        a = _fake('fa', CALLS={'pay': ('pay', 12345)})
        b = _fake('fb', CALLS={'go': ('nowhere', 0)})
        p1, p2 = self.plug(a, b)
        with p1, p2:
            with self.assertRaises(SystemExit):
                ev.call_table()
        p1, p2 = self.plug(_fake('fa'), b)
        with p1, p2, self.assertRaises(SystemExit):
            ev.contexts()

    def test_list_name_outside_the_prefix_stops_the_build(self):
        a = _fake('fa', npc_lists=lambda lists, ctx: ([{"name": "ch3_other", "entries": []}], []))
        p1, p2 = self.plug(a, _fake('fb'))
        with p1, p2, self.assertRaises(SystemExit):
            ev.module_lists({}, 0x900)


class CommonDeviceTest(unittest.TestCase):
    def test_stub_fits_before_the_talk_hook_and_calls_dispatch(self):
        stub = ev.stub()
        self.assertLessEqual(ev.STUB_AT + len(stub), ev.STUB_END)
        self.assertEqual(stub[:7], bytes((0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A, 0x22)))
        self.assertEqual(stub[7:10], ev._al(ev.native()[1]['dispatch']))
        self.assertEqual(stub[-5:], bytes((0x7A, 0xFA, 0x68, 0x28, 0x60)))

    def test_call_op_skips_as_five_bytes_for_any_table_index(self):
        # 06:AFA9 는 01 을 한 바이트로, 00(입구 주소 아래 바이트)을 세 바이트로 센다. 표 칸 번호는 그 세 바이트 안이다
        import dq5talkwrite
        ctx = ev.Context('L', types.ModuleType('x'))
        for k in range(256):
            ctx.calls = {'c': k}
            code = dq5talkwrite.encode_script([ctx.call('c')], 'call')
            self.assertEqual(code, bytes((0x01, 0x00, 0xFE, k, 0x01, 0x3F)))

    def test_amounts_are_the_fc_chapter_three_sums(self):
        _, at = ev.native()
        blob, _ = ev.native()
        o = at['amounts'] - ev.CODE_AT
        self.assertEqual([int.from_bytes(blob[o + 3 * k:o + 3 * k + 3], 'little') for k in range(len(ev.AMOUNTS))],
                         [35000, 25000, 60000, 400, 600, 10])

    def test_common_routines_start_with_php_and_end_with_rtl(self):
        blob, at = ev.native()
        for name in (*ev.COMMON_ROUTINES, 'dispatch'):
            self.assertEqual(blob[at[name] - ev.CODE_AT], 0x08, name)
        self.assertLessEqual(ev.CODE_AT + len(blob), ev.TABLE_AT)


@unittest.skipUnless(DQ5.is_file(), 'local source ROM not present')
class Dq5RomTest(unittest.TestCase):
    def test_dq5_names_no_reserved_flag_byte(self):
        import dq5flags
        from dq5map import Rom
        rom = Rom(DQ5.read_bytes())
        refs = dq5flags.by_bit(dq5flags.collect(rom, ['talk', 'npc', 'list', 'hook', 'event', 'code', 'long', 'short']))
        used = {addr for addr, _ in refs}
        mine = {f + 0x2190 for f in (*slots.COMMON_FLAGS, *slots.SPARE['flags'])} | \
            {f + 0x2190 for s in SLOTS.values() for f in s.flags}
        self.assertFalse(used & mine, sorted(f'{a:04X}' for a in used & mine))

    def test_stub_place_is_empty_in_dq5(self):
        data = DQ5.read_bytes()
        o = (ev.STUB_AT >> 16) * 0x8000 + (ev.STUB_AT & 0x7FFF)
        self.assertEqual(data[o - 8:o + ev.STUB_END - ev.STUB_AT], bytes(8 + ev.STUB_END - ev.STUB_AT))

    def test_borrowed_lists_have_one_time_script_slots_at_the_reserved_entries(self):
        # 낮·밤 두 벌 레코드는 dq5npcrelocate 가 빌리지 못하게 한다
        import dq5npcrecord
        import dq5npcrelocate as R
        from dq5map import Rom
        rom = Rom(DQ5.read_bytes())
        times = {(e['list'], e['index']): e['time'] for e in dq5npcrecord.dump(rom)['entries']}
        for k, s in SLOTS.items():
            for lst, idx in s.scripts:
                entries = R.list_entries(rom, int(lst.replace(':', ''), 16))
                for i in idx:
                    self.assertIsNotNone(R.script_address(rom, entries[i][0], False), f'{k} {lst} 칸 {i}')
                    self.assertIn(times[lst, i], ('day', 'night'), f'{k} {lst} 칸 {i}')


if __name__ == '__main__':
    unittest.main()
