"""2장 왕의 병·서쪽 탑의 꿀·여행의 문 사당(dq4ch2king)."""

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch2event as ev  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2slots as slots  # noqa: E402

DQ4 = ROOT / 'rom' / 'dq4.nes'
DQ5 = ROOT / 'rom' / 'dq5.sfc'


def context(message=0x1000, talk=0x0B00):
    return next(c for c in ev.contexts(message, talk) if c.module is king)


class ModuleTest(unittest.TestCase):
    def test_registered_with_its_slot(self):
        self.assertIn('dq4ch2king', ev.EVENTS)
        ctx = context()
        self.assertEqual(ctx.key, 'E3')
        self.assertTrue({i for i, _ in king.FLAGS} <= set(slots.SLOTS['E3'].flags))
        masks = [m for _, m in king.FLAGS]
        self.assertEqual(len(masks), len(set(masks)))
        self.assertEqual(slots.SLOTS['E3'].lists, 'ch2_king_')
        self.assertTrue(king.SHRINE_OPEN.startswith(slots.SLOTS['E3'].lists))

    def test_native_fits_and_does_not_move_with_message_numbers(self):
        code_a, at_a = king.native(context(0x1000))
        code_b, at_b = king.native(context(0x1400))
        self.assertEqual((code_a, at_a), (code_b, at_b))
        start, end = slots.SLOTS['E3'].code
        self.assertEqual(min(at_a.values()), start)
        self.assertLessEqual(start + len(code_a), end)

    def test_give_puts_the_honey_in_the_first_empty_slot_or_the_bag(self):
        code = king._give(king.HONEY)
        self.assertIn(bytes((0xC9, king.EMPTY)), code)                       # 빈 칸(FF)을 찾는다
        self.assertIn(bytes((0xA9, king.HONEY, 0x9D, 0x00, 0x00)), code)       # 그 칸에 꿀
        self.assertIn(bytes((0xEE, *(king.BAG + king.HONEY).to_bytes(2, 'little'))), code)   # 아니면 맡긴 물건
        self.assertIn(bytes((0x69, king.RECORD - king.SLOTS_PER, 0x00)), code)  # 다음 일행 기록

    def test_outside_swaps_the_two_answers(self):
        import dq4prologue
        rect = king.HONEY_RECT
        inside, outside = dq4prologue._inside(*rect), king._outside(rect)
        self.assertEqual(len(inside), len(outside))
        self.assertEqual(inside[:-14], outside[:-14])
        self.assertEqual(inside[-14:-7], outside[-7:])

    def test_rects_cover_the_fc_cells(self):
        # 주인공 셀 (2x 또는 2x+1, 2y+1 또는 2y+2) 이 FC 칸 (x, y)
        x0, y0, x1, y1 = king.BAZAAR_RECT
        self.assertEqual((x0, x1), (0x09 * 2, 0x09 * 2 + 1))
        self.assertEqual((y0, y1), (0x0A * 2 + 1, 0x0E * 2 + 2))
        x0, y0, x1, y1 = king.HONEY_RECT
        for x, y in king.ELVES:
            self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1)

    def test_scripts_use_only_the_borrowed_slots_and_encode(self):
        import dq5npcwrite
        ctx = context()
        lst, owned = slots.SLOTS['E3'].scripts[0]
        self.assertEqual(lst, king.SCRIPT_LIST)
        self.assertEqual(len(king.SCRIPTS), len(owned))
        self.assertTrue(set(king.USE.values()) <= set(owned))
        made = king.scripts(ctx)
        self.assertEqual(len({s['address'] for s in made}), len(made))
        for s in made:
            self.assertIn(s['address'], king.SCRIPTS)
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': s['commands']})
            self.assertLessEqual(len(code), 255)

    def test_talks(self):
        ctx = context()
        bodies = king.talk_scripts(ctx)
        self.assertEqual(len(bodies), len(king.TALKS))
        msg = lambda k: {"op": "msg", "id": f"{ctx.msg[k]:03X}"}  # noqa: E731
        body = dict(zip(king.TALKS, bodies))
        # 왕: 나았으면 그 뒤 말, 아니고 들었으면 꿀이 있을 때 먹이고 CURED 를 켠다
        top = body['king'][0]
        self.assertEqual(top['cond'], {"code": "1B", "index": king.CURED[0], "mask": king.CURED[1]})
        self.assertEqual(top['then'], msg('king_after'))
        heard = top['else'][0]
        has = heard['then'][0]
        self.assertEqual(has['cond'], {"code": "11", "item": king.HONEY})
        self.assertEqual(has['then'], [msg('honey_use'), {"op": "flag-on", "index": king.CURED[0],
                                                          "mask": king.CURED[1]}, msg('king_cure')])
        # 바자 병사는 말을 걸어도 BAZAAR 를 켠다
        self.assertIn({"op": "flag-on", "index": king.BAZAAR[0], "mask": king.BAZAAR[1]}, body['bazaar_soldier'][0]['else'])

    def test_king_ask_is_the_chapter_start_one(self):
        self.assertEqual(king.MESSAGES['king_ask'], ev.MESSAGES['king_ask'])

    def test_start_messages_and_absent(self):
        ctx = context()
        out = king.start_messages(ctx)
        self.assertEqual(out[(ev.THRONE, ev.FC_KING, False)], ctx.msg['king_ask'])
        self.assertEqual(out[(king.TOWER_TOP, king.FC_ELF, None)], ctx.msg['elves'])
        # 엘프 옆 칸은 모두 줄 0C 위다(말을 걸기 전에 달아나는 장면이 뜬다)
        for x, y in king.ELVES:
            self.assertLessEqual(y + 3, king.ELF_RECT[3])
        self.assertEqual(king.absent(ctx), {(king.SHRINE, *king.SHRINE_SOLDIER, n) for n in (False, True)})


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 없음')
class FcTest(unittest.TestCase):
    """FC 롬의 인물·대화·출구와 견준다."""

    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def _people(self, g, k, night=False, flags=None):
        import dq4npcport as port
        return {(p['x'], p['y']): p for p in port.fc_people(self.prg, g, k, night, flags)}

    def test_people_are_fc_records(self):
        fc = lambda c: (c[0] // 2, c[1] // 2)  # noqa: E731
        for (g, k), night, where, talk in (
                ((0x0C, 0), False, king.BAZAAR_SOLDIER, king.FC_BAZAAR_SOLDIER),
                ((0x0C, 0), True, king.SHOP_NIGHT, king.FC_SHOP),
                ((0x01, 1), False, king.THRONE_SOLDIER, king.FC_THRONE_SOLDIER),
                ((0x01, 1), False, king.MINISTER, king.FC_MINISTER),
                ((0x01, 1), False, king.GUARD, king.FC_GUARD),
                ((0x01, 0), False, king.GON['day'], king.FC_GON),
                ((0x01, 0), True, king.GON['night'], king.FC_GON),
                ((0x13, 0), False, king.MARONI, king.FC_MARONI),
                ((0x2E, 0), False, king.ELVES[0], king.FC_ELF),
                ((0x1E, 0), False, king.SHRINE_SOLDIER, king.FC_SHRINE_SOLDIER)):
            people = self._people(g, k, night)
            self.assertIn(fc(where), people, (g, k, where))
            self.assertEqual(people[fc(where)]['talk'], talk, (g, k, where))

    def test_fc_messages_by_flag(self):
        # FC 대화 스크립트가 $6283 bit3(BAZAAR)·bit1(CURED)로 고르는 메시지
        throne = self._people(0x01, 1, flags={0x6283: 0x08})
        self.assertEqual(throne[(0x0A, 0x10)]['shows'][0], 0x34F)
        self.assertEqual(throne[(0x0C, 0x0A)]['shows'][0], 0x7E3)
        cured = self._people(0x01, 1, flags={0x6283: 0x02})
        self.assertEqual(cured[(0x09, 0x07)]['shows'][0], 0x7E8)
        self.assertEqual(self._people(0x1E, 0, flags={0x6283: 0x02})[(0x03, 0x08)]['shows'][0], 0x7E1)

    def test_travel_doors_pair_the_two_shrines(self):
        import dq4block
        a = dq4block.exit_links(self.prg, 0x1E, 0, {})
        b = dq4block.exit_links(self.prg, 0x1F, 0, {})
        self.assertEqual([(e['x'], e['y'], e['prop'] & 0x7F) for e in a], [(*king.SHRINE_DOOR, 0x0A)])
        self.assertEqual([(e['x'], e['y'], e['prop'] & 0x7F) for e in b], [(*king.FAR_DOOR, 0x0A)])
        self.assertEqual((a[0]['to']['group'], a[0]['to']['index'], a[0]['to']['x'], a[0]['to']['y']),
                         (0x1F, 0, *king.FAR_DOOR))

    def test_shrines_are_the_last_maps_of_group_45(self):
        import dq4groupbuild as gb
        place = gb.placement(self.prg)
        self.assertEqual(place[0x1E, 0], (0x45, int(king.SHRINE[3:], 16)))
        self.assertEqual(place[0x1F, 0], (0x45, int(king.SHRINE_FAR[3:], 16)))


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), '롬 없음')
class ListsTest(unittest.TestCase):
    """옮긴 목록에 사건 목록을 얹은 결과."""

    @classmethod
    def setUpClass(cls):
        import dq4npcport
        ported, _, _ = dq4npcport.port(str(DQ5), str(DQ4))
        cls.base = {lst['map']: lst for lst in ported if 'map' in lst}
        cls.lists = copy.deepcopy(cls.base)
        cls.ctx = context()
        cls.new, cls.over = king.npc_lists(cls.lists, cls.ctx)

    def _at(self, m, where, time='day'):
        return [e for e in self.lists[m]['entries'] if king._at(e) == where and e['time'] == time]

    def test_scripted_people(self):
        for m, where, name in ((king.BAZAAR_MAP, king.BAZAAR_SOLDIER, 'bazaar_soldier'),
                               (ev.THRONE, king.THRONE_SOLDIER, 'throne_soldier'),
                               (king.TOWER_TOP, king.ELVES[0], 'elf_a'), (king.TOWER_TOP, king.ELVES[1], 'elf_b')):
            got = self._at(m, where)
            self.assertTrue(got, (m, where))
            self.assertEqual(got[0]['from'], {"list": king.SCRIPT_LIST, "index": king.USE[name]})
            self.assertGreaterEqual(got[0]['fields']['interval'], 1)
        self.assertEqual(self._at(king.TOWER_TOP, king.ELVES[0])[0]['fields']['gfx'], king.ELF_PICTURE)
        honey = [e for e in self.lists[king.TOWER_TOP]['entries']
                 if e['from'] == {"list": king.SCRIPT_LIST, "index": king.USE['honey']}]
        self.assertEqual(sorted(e['time'] for e in honey), ['day', 'night'])

    def test_retalked_people(self):
        t = self.ctx.talk
        self.assertEqual(self._at(ev.THRONE, ev.KING_CELL)[0]['fields']['talk'], t['king'])
        self.assertEqual(self._at(ev.THRONE, king.MINISTER)[0]['fields']['talk'], t['minister'])
        self.assertEqual(self._at(ev.CASTLE, king.GON['night'], 'night')[0]['fields']['talk'], t['gon'])
        self.assertEqual(self._at(king.SARAN, king.MARONI, 'night')[0]['fields']['talk'], t['maroni'])
        self.assertEqual(self._at(king.BAZAAR_MAP, king.SHOP_NIGHT, 'night')[0]['fields']['talk'], t['shop_night'])

    def test_shrine_soldier_blocks_until_the_king_is_cured(self):
        self.assertFalse(self._at(king.SHRINE, king.SHRINE_SOLDIER))
        block = self._at(king.SHRINE, king.SHRINE_BLOCK)
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]['fields']['interval'], 0)
        (opened,) = self.new
        self.assertEqual(opened['name'], king.SHRINE_OPEN)
        stand = [e for e in opened['entries'] if king._at(e) == king.SHRINE_SOLDIER]
        self.assertEqual(stand[0]['fields']['talk'], self.ctx.talk['shrine_pass'])
        self.assertEqual(self.over, [{"map": king.SHRINE, "flag": king.CURED[0], "when": "on", "mask": king.CURED[1],
                                      "list": f"new:{king.SHRINE_OPEN}"}])

    def test_edits_reach_the_joined_throne_list(self):
        # 대체 목록이 같은 엔트리를 담으므로 제자리 고침이 합류 뒤 목록에도 든다
        lists = copy.deepcopy(self.base)
        joined = [e for e in lists[ev.THRONE]['entries']]
        king.npc_lists(lists, self.ctx)
        soldier = [e for e in joined if king._at(e) == king.THRONE_SOLDIER]
        self.assertEqual(soldier[0]['from']['index'], king.USE['throne_soldier'])

    def test_script_addresses_are_the_list_slots(self):
        import dq5npc
        import dq5npcrelocate as r
        rom = r.Rom(DQ5.read_bytes())
        entries = r.list_entries(rom, int(king.SCRIPT_LIST.replace(':', ''), 16))
        got = tuple(r.cpu(dq5npc.script_address(rom, e, False)) for e, _ in entries[:len(king.SCRIPTS)])
        self.assertEqual(got, king.SCRIPTS)


if __name__ == '__main__':
    unittest.main()
