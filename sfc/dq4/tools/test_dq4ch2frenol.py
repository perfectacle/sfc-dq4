"""2장 프레놀 가짜 공주·남쪽 동굴(dq4ch2frenol)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch2event as ev  # noqa: E402
import dq4ch2frenol as fr  # noqa: E402
import dq4ch2slots as slots  # noqa: E402

DQ4 = ROOT / 'rom' / 'dq4.nes'
DQ5 = ROOT / 'rom' / 'dq5.sfc'


def context(message=0x1000, talk=0x0B00):
    ctx = next(c for c in ev.contexts(message, talk) if c.module is fr)
    return ctx


class ModuleTest(unittest.TestCase):
    def test_registered_with_its_slot(self):
        self.assertIn('dq4ch2frenol', ev.EVENTS)
        ctx = context()
        self.assertEqual(ctx.key, 'E2')
        self.assertEqual({i for i, _ in fr.FLAGS}, set(slots.SLOTS['E2'].flags))
        masks = [m for _, m in fr.FLAGS]
        self.assertEqual(len(masks), len(set(masks)))
        self.assertEqual(sum(masks), 0xFF)
        self.assertEqual(fr.SCENE_BITS & (fr.KIDNAPPED[1] | fr.LEFT[1] | fr.RESCUED[1]), 0)

    def test_native_fits_and_does_not_move_with_message_numbers(self):
        a, b = context(0x1000), context(0x1400)
        code_a, at_a = fr.native(a)
        code_b, at_b = fr.native(b)
        self.assertEqual(at_a, at_b)
        start, end = slots.SLOTS['E2'].code
        self.assertEqual(at_a['cry'], start)
        self.assertLessEqual(start + len(code_a), end)
        self.assertNotEqual(code_a, code_b)          # 끝 서술의 메시지 번호만 다름
        self.assertEqual(len(code_a), len(code_b))

    def test_end_event_loads_the_town_in_the_morning(self):
        ctx = context()
        tokens = fr.events(ctx)[0]
        self.assertEqual(tokens[0], ('msg', ctx.msg['end']))
        self.assertEqual(tokens[1], bytes((0x90, 0x3D, 0x04, *fr.MORNING_CELL, 0x01, 0x80, 0xFF)))
        before = fr._end_before()
        self.assertIn(bytes((0x29, ~fr.SCENE_BITS & 0xFF, 0x09, fr.RESCUED[1])), before)

    def test_item_routines(self):
        # 일행 기록마다 12칸을 보고, 맡긴 물건 자리까지 본다
        gate, swap = fr._gate(), fr._swap()
        for code in (gate, swap):
            self.assertIn(bytes((0xC9, fr.BRACELET)), code)
            self.assertIn(bytes((0xAD, *(fr.BAG + fr.BRACELET).to_bytes(2, 'little'))), code)
        self.assertIn(bytes((0xA9, fr.THIEF_KEY, 0x9D, 0x00, 0x00)), swap)
        self.assertIn(bytes((0xEE, *(fr.BAG + fr.THIEF_KEY).to_bytes(2, 'little'))), swap)

    def test_scripts_use_only_the_borrowed_slots_and_encode(self):
        import dq5npcwrite
        ctx = context()
        lst, owned = slots.SLOTS['E2'].scripts[0]
        self.assertEqual(lst, fr.SCRIPT_LIST)
        self.assertEqual(len(fr.SCRIPTS), len(owned))
        self.assertTrue(set(fr.USE.values()) <= set(owned))
        made = fr.scripts(ctx)
        self.assertEqual(len({s['address'] for s in made}), len(made))
        for s in made:
            self.assertIn(s['address'], fr.SCRIPTS)
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': s['commands']})
            self.assertLessEqual(len(code), 255)

    def test_talks(self):
        ctx = context()
        bodies = fr.talk_scripts(ctx)
        self.assertEqual(len(bodies), len(fr.TALKS))
        self.assertTrue(set(fr.TALKS) <= set(fr.MESSAGES))
        deal = bodies[fr.TALKS.index('deal')]
        self.assertEqual(deal[0], {"op": "msg", "id": f"{ctx.msg['deal']:03X}"})
        self.assertEqual(deal[1]["cond"], {"code": "05"})
        # 아니요면 0364 를 띄운 뒤 다시 묻는다
        self.assertEqual(deal[1]["else"][0], {"op": "msg", "id": f"{ctx.msg['refuse']:03X}"})
        self.assertEqual(deal[1]["else"][1]["cond"], {"code": "05"})

    def test_start_messages_and_absent(self):
        ctx = context()
        self.assertEqual(fr.start_messages(ctx)[(fr.INN, fr.FC_INN_BREY, None)], ctx.msg['brey_scene'])
        gone = ev.absent()
        self.assertIn((fr.TOWN, *fr.TRIO[0], False), gone)
        self.assertIn((fr.TOWN, *fr.NIGHT_MEI, True), gone)
        self.assertNotIn((fr.TOWN, *fr.NIGHT_MEI, False), gone)


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 없음')
class FcTest(unittest.TestCase):
    """FC 롬의 목록·블록과 견준다."""

    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def test_after_lists_are_fc_lists_of_rescue(self):
        import dq4npcport as port
        for m, fc in ((fr.TOWN, 0), (fr.INN, 1)):
            for night in (False, True):
                want = [((p['x'], p['y']), p['facing'], p['interval'], p['picture'], p['shows'][0])
                        for p in port.fc_people(self.prg, 0x0F, fc, night, {0x627B: 0x70})]
                got = [(xy, facing, interval, pic, who) for mp, t, xy, facing, interval, pic, who in fr.AFTER
                       if mp == m and t == ('night' if night else 'day')]
                # FC 0F/01 밤의 (22,03)은 대화 008(아무도 없음): 자는 사람이라 옮기지 않았다
                want = [w for w in want if not (m == fr.INN and night and w[4] == 0x2F0)]
                self.assertEqual([w[:4] for w in want], [g[:4] for g in got], (m, night))
                for w, g in zip(want, got):
                    who = g[4]
                    if isinstance(who, int):
                        self.assertEqual(w[4], 0x10000 + who, (m, night, g))
                    elif who != 'dog':
                        self.assertEqual(w[4], fr.FC_FIRST[who], (m, night, g))

    def test_people_cells_are_fc_records(self):
        import dq4npcport as port
        day = {(p['x'], p['y']) for p in port.fc_people(self.prg, 0x0F, 0, False)}
        night = {(p['x'], p['y']) for p in port.fc_people(self.prg, 0x0F, 0, True)}
        cell = lambda c: (c[0] // 2, c[1] // 2)  # noqa: E731
        for c in (*fr.TRIO, fr.GIRL_INN, fr.DOG, fr.GIRL_WALKER, fr.BOY, fr.MAN, fr.INNKEEPER, fr.MERCHANT, fr.AUNT):
            self.assertIn(cell(c), day)
        for c in (fr.NIGHT_MEI, fr.NIGHT_CLOAK, *fr.NIGHT_PARKED):
            self.assertIn(cell(c), night)
        inn = {(p['x'], p['y']) for p in port.fc_people(self.prg, 0x0F, 1, False)}
        for c in (fr.INN_DUMMY, fr.INN_CLOAK_A, fr.INN_CLOAK_B, fr.INN_PRINCESS, fr.INN_BREY, fr.INN_KIRYL,
                  fr.INN_HOBBIT):
            self.assertIn(cell(c), inn)

    def _goals(self, m, record):
        import dq4npcblock
        name, bank, recs = next(x for x in dq4npcblock.map_lists(self.prg) if x[0] == m)
        (a, ln), *_ = recs[record][2]
        return [fr.cell(bs[1], bs[2]) for _, bs, _, _ in dq4npcblock.decode(self.prg, bank, a, ln) if bs[0] == 0x24]

    def test_paths_are_fc_blocks(self):
        # 0F/00 레코드 02(셋이 같은 블록)·0F/01 레코드 02·06 의 목표 칸(명령 24)
        self.assertEqual(self._goals('0F/00', 2), list(fr.TRIO_PATH))
        self.assertEqual(self._goals('0F/01', 2), list(fr.STAIRS))
        self.assertEqual(self._goals('0F/01', 6), list(fr.STAIRS))
        # 0F/00 레코드 14(메이)는 (06,0B)→(04,0B) 로 온다(떠나는 길 (03,0B)~ 는 일행 칸이라 옮기지 않음)
        self.assertEqual(self._goals('0F/00', 14)[:2], list(fr.MEI_PATH))
        self.assertEqual(self._goals('0F/00', 18)[0], fr.KIRYL_STAND)


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), '롬 없음')
class ListsTest(unittest.TestCase):
    """옮긴 목록에 사건 목록을 얹은 결과."""

    @classmethod
    def setUpClass(cls):
        import dq4npcport
        ported, _, _ = dq4npcport.port(str(DQ5), str(DQ4))
        cls.base = {lst['map']: lst for lst in ported if 'map' in lst}
        import copy
        lists = copy.deepcopy(cls.base)
        cls.new, cls.over = fr.npc_lists(lists, context())
        cls.lists = lists

    def test_overrides_put_later_states_first(self):
        town = [o['list'] for o in self.over if o['map'] == fr.TOWN]
        self.assertEqual(town, [f'new:{fr.TOWN_AFTER}', f'new:{fr.TOWN_LEFT}', f'new:{fr.TOWN_KID}'])
        names = {lst['name'] for lst in self.new}
        self.assertTrue(all(n.startswith(slots.SLOTS['E2'].lists) for n in names))
        self.assertEqual({o['list'][4:] for o in self.over}, names)

    def test_start_lists_leave_out_what_fc_hides(self):
        cells = {(e['fields']['x'], e['fields']['y'], e['time']) for e in self.lists[fr.TOWN]['entries']}
        for c in fr.TRIO:
            self.assertNotIn((*c, 'day'), cells)
        self.assertNotIn((*fr.NIGHT_MEI, 'night'), cells)
        self.assertIn((*fr.GIRL_WALKER, 'day'), cells)
        inn = {(e['fields']['x'], e['fields']['y']): e for e in self.lists[fr.INN]['entries']}
        self.assertNotIn(fr.INN_DUMMY, inn)
        self.assertEqual(inn[fr.INN_CLOAK_A]['from'], {'list': fr.SCRIPT_LIST, 'index': fr.USE['inn_cloak_a']})

    def test_scene_lists(self):
        new = {lst['name']: lst['entries'] for lst in self.new}
        walkers = [e for e in new[fr.TOWN_KID] if e['from'] == {'list': fr.SCRIPT_LIST, 'index': fr.USE['trio']}]
        self.assertEqual(len(walkers), 2 * len(fr.TRIO))
        left = new[fr.TOWN_LEFT]
        scene = [e for e in left if e['from'].get('list') == fr.SCRIPT_LIST]
        self.assertTrue(all(e['time'] == 'night' for e in scene))
        self.assertEqual(sorted(e['from']['index'] for e in scene),
                         sorted([fr.USE['mei'], fr.USE['cloaks'], fr.USE['cloaks'], fr.USE['kiryl'], fr.USE['brey'],
                                 fr.USE['deal']]))
        self.assertTrue(all(e['fields']['interval'] for e in scene))
        after = new[fr.TOWN_AFTER]
        self.assertEqual(len(after), sum(1 for a in fr.AFTER if a[0] == fr.TOWN))
        self.assertIn(6, [e['fields']['talk'] for e in after])          # 여관이 열림


if __name__ == '__main__':
    unittest.main()
