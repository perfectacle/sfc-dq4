"""3장 동료 대화(dq4ch3partytalk): 줄·대사 표, NDS 3장 레코드를 옮기는 규칙(dq4ch2partytalknds.convert3), 말 상대 이름
풀기, 2장 모듈 표에 합친 3장 줄을 조건 평가 루틴(w65816 로 돌림)이 고르는지."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ev  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2partytalkcheck as model  # noqa: E402
import dq4ch2partytalknds as nds  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3partytalk as c3  # noqa: E402
import dq4ch3slots as slots  # noqa: E402


class TableTest(unittest.TestCase):
    def test_registered_last_without_code_or_flags(self):
        self.assertEqual(list(slots.SLOTS)[-1], 'P')
        self.assertEqual(slots.SLOTS['P'].module, 'dq4ch3partytalk')
        self.assertEqual((slots.SLOTS['P'].code, slots.SLOTS['P'].flags), ((), ()))
        self.assertIn('dq4ch3partytalk', ch3.EVENTS)
        self.assertIs(pt.chapter3(), c3)

    def test_every_line_has_a_message_and_every_message_a_line(self):
        self.assertEqual({ln.message for ln in c3.LINES}, set(c3.MESSAGES))

    def test_lines_are_chapter_three_and_spoken_by_companions(self):
        for ln in c3.LINES:
            self.assertIn(ch3.CHAPTER3, ln.on, ln)
            self.assertIn(ln.speaker, set(c3.SPEAKERS.values()), ln)
            if ln.speaker == c3.TORNEKO:
                # 톨네코 줄은 개 토마스의 말뿐이다(톨네코 혼자일 때 동료 대화가 없음)
                self.assertIn(ch3.DOG, ln.on, ln)

    def test_mercenaries_are_monster_guest_records(self):
        import dq4mercenary as merc
        self.assertEqual(c3.SPEAKERS['SCOTT'], 0xE8)
        self.assertEqual(c3.SPEAKERS['LAWRENCE'], 0xE9)
        self.assertEqual(c3.SPEAKERS['SCOTT'], merc.GUEST | merc.KINDS['scott'])

    def test_texts_use_only_window_characters(self):
        from dq4menumsg import CHARS
        for name, parts in c3.MESSAGES.items():
            for p in parts:
                if isinstance(p, str):
                    self.assertFalse(set(p) - set(CHARS) - {' '}, f'{name}: {p}')

    def test_merged_table_keeps_chapter_two_lines_first(self):
        lines = pt.all_lines()
        self.assertEqual(lines[:len(pt.LINES)], pt.LINES)
        self.assertEqual(lines[len(pt.LINES):], c3.LINES)
        self.assertFalse(set(pt.MESSAGES) & set(c3.MESSAGES))

    def test_chapter_three_messages_follow_chapter_two(self):
        # 3장 모듈 메시지 번호는 dq4chapter1.chapter3_message 와 같은 셈이어야 롬 표가 맞는 메시지를 가리킨다
        import dq4chapter1
        first = 0x1000
        ctx2 = next(c for c in ev.contexts(dq4chapter1.chapter2_message(first)) if c.module is pt)
        mine = pt._chapter3_messages(ctx2.msg)
        want = next(c for c in ch3.contexts(dq4chapter1.chapter3_message(first)) if c.module is c3).msg
        self.assertEqual(mine, want)


class ConvertTest(unittest.TestCase):
    """dq4ch2partytalknds.convert3: NDS 롬 없이 레코드 꼴만 만든다."""
    MSGS = {1: '@a@bスコット「ほう。@c2@', 2: '@a@bトーマス「ワン！@c2@', 3: '@a@bロレンス「ええ。@c2@'}

    def _rec(self, **kw):
        f = {'k': 999, 'mapname': 'hcout', 'speaker': 'スコット', 'msg': 1, 'count': 1, 'v0': 0, 'place': (0xFF, 0xFF),
             'codes': (0, 0, 0), 'vals': (0, 0, 0), 'story': (140, 0xFFFF), 'time': 0, 'prio': 7, 'slots': []}
        f.update(kw)
        return f

    def test_plain_line(self):
        line, why = nds.convert3(self._rec(), self.MSGS)
        self.assertIsNone(why)
        self.assertEqual((line['maps'], line['speaker'], line['on'], line['off']),
                         (('40/00',), 'SCOTT', ['CHAPTER3', 'FOXED'], []))

    def test_thomas_speaks_through_torneko_with_the_dog(self):
        line, _ = nds.convert3(self._rec(speaker='トーマス', msg=2), self.MSGS)
        self.assertEqual(line['speaker'], 'TORNEKO')
        self.assertIn('DOG', line['on'])

    def test_statue_and_days(self):
        line, _ = nds.convert3(self._rec(codes=(7, 0, 0), vals=(140, 0, 0)), self.MSGS)
        self.assertEqual(line['have'], ['STATUE'])
        line, _ = nds.convert3(self._rec(codes=(8, 0, 0), vals=(140, 0, 0)), self.MSGS)
        self.assertEqual(line['lack'], ['STATUE'])
        line, _ = nds.convert3(self._rec(mapname='#544', codes=(14, 0, 0), vals=(3, 0, 0), story=(143, 0xFFFF),
                                         speaker='ロレンス', msg=3), self.MSGS)
        self.assertEqual((line['maps'], line['days'], line['on']), (('field',), ['LAWRENCE_DAYS=3'],
                                                                    ['CHAPTER3', 'LAWRENCE']))

    def test_dropped_conditions(self):
        self.assertIn('임시', nds.convert3(self._rec(codes=(5, 0, 0), vals=(2, 0, 0)), self.MSGS)[1])
        self.assertIn('사건', nds.convert3(self._rec(v0=31023), self.MSGS)[1])
        self.assertIn('155', nds.convert3(self._rec(codes=(1, 0, 0), vals=(155, 0, 0)), self.MSGS)[1])
        self.assertIn('마을 사람', nds.convert3(self._rec(place=(2, 0xFF)), self.MSGS)[1])
        self.assertIn('예/아니오', nds.convert3(self._rec(count=211), self.MSGS)[1])

    def test_talked_person_and_cave_maps(self):
        line, _ = nds.convert3(self._rec(mapname='ccf2', place=(2, 0xFF)), self.MSGS)
        self.assertEqual(line['talked'], ['E.king'])
        line, _ = nds.convert3(self._rec(mapname='deb2a'), self.MSGS)
        self.assertEqual(line['maps'], ('48/03', '48/04'))

    def test_water_drained_line_goes_to_the_drained_map(self):
        rec = self._rec(k=40, mapname='deb2a', codes=(5, 0, 0), vals=(60, 0, 0))
        line, why = nds.convert3(rec, self.MSGS)
        self.assertIsNone(why)
        self.assertEqual(line['maps'], ('48/04',))

    def test_committed_table_is_what_the_tool_makes_from_its_rules(self):
        # 줄 표의 talked 이름은 모두 OBJECTS3·FIXES3 에서 나온다(손으로 고친 줄이 없음)
        names = {t for v in nds.OBJECTS3.values() for t in v} | \
            {t for f in nds.FIXES3.values() for t in f.get('talked', ())}
        self.assertLessEqual({t for ln in c3.LINES for t in ln.talked}, names)


class ResolveTest(unittest.TestCase):
    class Ctx:
        def __init__(self, made=None, overrides=()):
            self.made_all, self.overrides = made or {}, list(overrides)

    @staticmethod
    def entry(x, y, talk, time='day'):
        return {"time": time, "fields": {"x": x, "y": y, "talk": talk}}

    def test_module_talk_must_stand_in_some_list(self):
        lists = {'40/06': {"entries": [self.entry(22, 21, 0x97C)]}}
        self.assertEqual(c3.resolve('E.king', lists, self.Ctx(), {'E.king': 0x97C}), frozenset({0x97C}))
        with self.assertRaises(SystemExit):
            c3.resolve('E.king', lists, self.Ctx(), {'E.king': 0x97D})

    def test_cell_name_collects_base_and_override_lists(self):
        lists = {'40/0B': {"entries": [self.entry(22, 7, 0x950, 'night'), self.entry(22, 7, 0x951, 'day')]}}
        made = {'ch3_towns_400B': {"entries": [self.entry(22, 7, 0x960, 'night')]}}
        over = [{"map": '40/0B', "list": "new:ch3_towns_400B"}]
        self.assertEqual(c3.resolve('40/0B:11-3:night', lists, self.Ctx(made, over), {}), frozenset({0x950, 0x960}))


def _machine(talks):
    """2장 모듈 native 를 롬에 넣은 w65816. 받은 메시지는 got 에 쌓인다. 밤 시험은 낮(캐리 0)."""
    from w65816 import Cpu
    ctx = next(c for c in ev.contexts(0x1000) if c.module is pt)
    saved = pt._TALKS, c3.TALKS_FOUND
    ch2_tokens = {k for ln in pt.LINES for k in ln.talked}
    pt._TALKS = {k: v for k, v in talks.items() if k in ch2_tokens}
    c3.TALKS_FOUND = {k: v for k, v in talks.items() if k not in ch2_tokens}
    try:
        blob, at = pt.native(ctx)
        _, labels = pt._code(ctx.code_at).assemble({'maps': 0, 'ids': 0})
    finally:
        pt._TALKS, c3.TALKS_FOUND = saved
    rom = bytearray(0x400000)
    o = pt.ch1.lorom(ctx.code_at)
    rom[o:o + len(blob)] = blob
    msg = {**ctx.msg, **pt._chapter3_messages(ctx.msg)}
    return bytes(rom), Cpu, at, msg


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import w65816  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('w65816 없음')
        tokens = sorted({k for ln in pt.all_lines() for k in ln.talked})
        cls.talks = {k: frozenset({0x900 + i}) for i, k in enumerate(tokens)}
        cls.rom, cls.Cpu, cls.at, cls.msg = _machine(cls.talks)
        data = bytearray(cls.rom)
        cls.table = pt.table(bytes(data), cls.at['maps'])

    def run_talk(self, key, party, flags=(), days=(0, 0), items=(), bag=()):
        """party: [(인물 번호, 물건들)], 첫 사람이 기록 0. 받은 메시지 번호들."""
        w = bytearray(0x20000)
        if key == pt.FIELD_KEY:
            w[0xBE] = 0x00
        else:
            w[0xBE], w[0xBC], w[0xBD] = 0x80, key[0], key[1]
        w[0x201D] = w[0x201E] = len(party)
        for k, (who, held) in enumerate(party):
            w[0x2020 + k] = k
            rec = 0x2040 + 42 * k
            w[rec], w[rec + 2] = who, 10
            for s in range(12):
                w[rec + 0x16 + s] = held[s] if s < len(held) else 0xFF
        for i, mask in flags:
            w[0x2190 + i] |= mask
        w[(c3.ch3.SCOTT_DAYS & 0xFFFF)], w[(c3.ch3.LAWRENCE_DAYS & 0xFFFF)] = days
        for item in bag:
            w[(pt.BAG & 0xFFFF) + item] = 1
        c = self.Cpu(self.rom, w)
        got = []

        def message(cpu):
            got.append(cpu.a & 0xFFFF)
            lo, hi, bank = cpu.pull(), cpu.pull(), cpu.pull()
            cpu.pbr, cpu.pc = bank, ((hi << 8 | lo) + 1) & 0xFFFF
            return True

        def daytime(cpu):
            cpu.p &= ~0x01
            lo, hi, bank = cpu.pull(), cpu.pull(), cpu.pull()
            cpu.pbr, cpu.pc = bank, ((hi << 8 | lo) + 1) & 0xFFFF
            return True
        c.hooks[pt.MESSAGE_AT] = message
        c.hooks[pt.NIGHT_TEST] = daytime
        c.jsl(self.at['talk'], max_steps=200_000)
        return got

    def want(self, key, party, flags, days=(0, 0), items=()):
        values = {}
        for i, mask in flags:
            values[0x2190 + i] = values.get(0x2190 + i, 0) | mask
        var = {c3.VARS['SCOTT_DAYS']: days[0], c3.VARS['LAWRENCE_DAYS']: days[1]}
        return model.pick(self.table.get(key, []), values, {who for who, _ in party}, party[0][0], False,
                          items=set(items), var=var)[0]

    def test_days_pick_the_matching_field_line(self):
        scott = (c3.SPEAKERS['SCOTT'], ())
        flags = (ch3.CHAPTER3, ch3.SCOTT)
        seen = set()
        for d in range(5):
            got = self.run_talk(pt.FIELD_KEY, [(c3.TORNEKO, ()), scott], flags, days=(d, 0))
            want = self.want(pt.FIELD_KEY, [(c3.TORNEKO, ()), scott], flags, days=(d, 0))
            self.assertEqual(got, [want], d)
            seen.add(want)
        self.assertEqual(len(seen), 5)
        self.assertNotIn(pt.NOBODY, seen)

    def test_torneko_alone_gets_nobody(self):
        flags = (ch3.CHAPTER3, ch3.SCOTT)
        self.assertEqual(self.run_talk(pt.FIELD_KEY, [(c3.TORNEKO, ())], flags), [pt.NOBODY])

    def test_statue_counts_in_any_record_or_the_bag(self):
        key = (0x48, 0x07)
        party = [(c3.TORNEKO, (0x10,)), (c3.SPEAKERS['SCOTT'], ())]
        flags = (ch3.CHAPTER3, c3.CONDITIONS['FOXED'], ch3.SCOTT)
        lack = self.want(key, party, flags)
        have = self.want(key, party, flags, items=(c3.ITEMS['STATUE'],))
        self.assertNotEqual(lack, have)
        self.assertEqual(self.run_talk(key, party, flags), [lack])
        self.assertEqual(self.run_talk(key, party, flags, bag=(c3.ITEMS['STATUE'],)), [have])
        held = [(c3.TORNEKO, (0x10, 0x11)), (c3.SPEAKERS['SCOTT'], (0x12, c3.ITEMS['STATUE']))]
        self.assertEqual(self.run_talk(key, held, flags), [have])


if __name__ == '__main__':
    unittest.main()
