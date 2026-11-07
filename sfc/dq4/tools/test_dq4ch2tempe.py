import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2battle as battle  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4ch2tempe as tempe  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402


def _ctx(first=0x1000):
    return next(c for c in ev.contexts(first) if c.module is tempe)


class EventTest(unittest.TestCase):
    def test_registered_after_the_base_messages(self):
        ctx = _ctx()
        self.assertIn('dq4ch2tempe', ev.EVENTS)
        base = ev.message_ids(0x1000)
        # 바구니 서술 다음 번호가 이긴 뒤 서술이다(메시지는 등록 차례로 이어 붙음)
        self.assertEqual(ctx.msg['won'], base['basket'] + 1)
        self.assertEqual(list(ctx.msg), list(tempe.MESSAGES))
        # 대화 본문은 등록한 모듈 모두의 것(텐페 뒤에 다른 사건 모듈이 붙음)
        self.assertEqual(len(ev.talk_scripts(0x1000)),
                         len(ev.TALKS) + sum(len(getattr(m, 'TALKS', ())) for _, m in ev.modules()))
        self.assertEqual(ev.EVENTS[0], 'dq4ch2tempe')

    def test_fight_turns_the_event_off_around_the_battle(self):
        code = tempe._fight()
        self.assertTrue(code.startswith(ENTER) and code.endswith(LEAVE))
        body = code[len(ENTER):-len(LEAVE)]
        off = bytes.fromhex('adae19297f8dae19')
        on = bytes.fromhex('adae1909808dae19')
        far = battle.far(tempe.GROUP)
        # 앞 절반 flag 셋(2208 bit0~2)을 끄고, 이벤트를 끈 뒤 전투, 이기면(2208 bit7) WON 과 이벤트를 켬
        self.assertEqual(body[:10], bytes.fromhex('af08227e29f88f08227e'))
        self.assertLess(body.index(off), body.index(far))
        self.assertLess(body.index(far), body.index(on))
        won = bytes((0xAF, 0xF0, 0x21, 0x7E, 0x09, tempe.WON[1], 0x8F, 0xF0, 0x21, 0x7E))
        self.assertLess(body.index(far), body.index(won))
        branch = body.index(bytes((0x29, 0x80, 0xF0)))
        self.assertEqual(body[branch + 3], len(won) + len(on))

    def test_event_and_hook(self):
        ctx = _ctx()
        code, at = tempe.native(ctx)
        self.assertEqual(at, ctx.at)
        self.assertEqual(at['fight'], ctx.code_at)
        self.assertLessEqual(ctx.code_at + len(code), ctx.slot.code[1])
        event = code[at['event'] - ctx.code_at:]
        warp = bytes((0x90, 0x3D, 0x03, 0x18, 0x07, 0x01, 0x80))
        self.assertEqual(event, warp + b'\xc2' * tempe.PAUSE_STEPS + bytes((0xA0, 0x00, 0xA0, 0x5F)) +
                         bytes((0x60, ctx.msg['won'] & 0xFF, ctx.msg['won'] >> 8)) +
                         bytes((0xA0, *at['morning'].to_bytes(3, 'little'))) + warp + b'\xff')
        # 앞 절반의 바구니 이벤트: 메시지 60 lo hi 뒤의 옮기기를 이 이벤트로 뛰는 C3 으로
        tail = ev.tail_native(0x1000)
        basket = tail[0][tail[1]['altar_event'] - (len(ev.native()[0]) + ev.CODE_AT):][:11]
        self.assertEqual(basket[0], 0x60)
        self.assertEqual(basket[3:10], tempe.BASKET_WARP)
        self.assertEqual(tempe.hooks(ctx), [(tail[1]['altar_event'] + 3, tempe.BASKET_WARP,
                                             bytes((0xC3, *at['event'].to_bytes(3, 'little'))))])
        self.assertEqual(tempe.events(ctx)[0][1], ('msg', ctx.msg['won']))

    def test_battle_and_monsters_stay_in_the_slot(self):
        slot = _ctx().slot
        self.assertEqual({b['group'] for b in tempe.BATTLES}, set(slot.groups))
        self.assertEqual(set(tempe.MONSTERS), set(slot.monsters))
        self.assertEqual(set(tempe.MONSTER_NAMES), set(tempe.MONSTERS))
        self.assertEqual(ev.battle_stubs(), {})
        # 곡 등급 1 立ちはだかる難敵(NDS 조우 레코드 158 의 곡 31)
        self.assertIn(battle.group_doc(0x31, ((tempe.CHAMELEON, 1), (tempe.STATUE, 2)), battle.MIDBOSS_FLAGS),
                      ev.encounter_groups())
        self.assertEqual(battle.MIDBOSS_FLAGS & 3, 1)

    def test_names_reach_the_window_table(self):
        import dq4windowtext
        names = dq4windowtext.numbered_names()[4]
        self.assertEqual(names[tempe.CHAMELEON], '카멜레온 맨')
        self.assertEqual(names[tempe.STATUE], '날뛰는 석상')


class TownAfterTest(unittest.TestCase):
    def test_talks(self):
        ctx = _ctx()
        bodies = dict(zip(tempe.TALKS, tempe.talk_scripts(ctx)))
        self.assertEqual(bodies['priest'], [{"op": "msg", "id": f"{ctx.msg['priest']:03X}"}, ev.CHURCH])
        self.assertEqual(bodies['noble'][1]['cond'], {"code": "05"})
        self.assertEqual(bodies['chief'], [{"op": "msg", "id": f"{ctx.msg['chief']:03X}"}])

    def test_list_and_override(self):
        ctx = next(c for c in ev.contexts(first_talk=0x900) if c.module is tempe)
        new, over = tempe.npc_lists({}, ctx)
        self.assertEqual([n['name'] for n in new], [tempe.WON_LIST])
        self.assertTrue(tempe.WON_LIST.startswith(ctx.slot.lists))
        self.assertEqual(over, [{"map": '3D/03', "flag": 0x60, "when": "on", "mask": 0x01,
                                 "list": f"new:{tempe.WON_LIST}"}])
        entries = new[0]['entries']
        self.assertEqual(len(entries), len(tempe.AFTER))
        shop = [e for e in entries if e['fields']['talk'] == 0x02]
        self.assertEqual([(e['time'], e['fields']['x'], e['fields']['y']) for e in shop], [('day', 8, 53)])
        chief = next(e for e, a in zip(entries, tempe.AFTER) if a[5] == 'chief')
        self.assertEqual((chief['fields']['x'], chief['fields']['y']), (24, 69))
        self.assertEqual(chief['fields']['talk'], ctx.talk['chief'])
        # 촌장 위 칸(제단에서 내려오는 길 끝)에서 아래를 보고 말을 건다
        self.assertEqual(tempe.CHIEF_TALK_CELL, (24, 67))


@unittest.skipUnless((ROOT / 'rom' / 'dq4.nes').is_file(), 'local source ROM not present')
class FcRomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path[:0] = [str(ROOT / 'fc' / 'dq4' / 'tools')]
        from kr_patch.fc import ines
        cls.prg = ines.prg((ROOT / 'rom' / 'dq4.nes').read_bytes())

    def test_after_list_is_the_fc_one(self):
        import dq4npcport
        got = []
        for night in (False, True):
            for p in dq4npcport.fc_people(self.prg, 0x0E, 0x00, night, {0x627F: 0x80}):
                first = next(m for m in p['shows'] if m is not None)
                got.append(('night' if night else 'day', (p['x'], p['y']), p['facing'], p['interval'], p['picture'],
                            first))
        want = [(t, cell, f, i, pic, (0x10000 + who) if isinstance(who, int) else tempe.FC_FIRST[who])
                for t, cell, f, i, pic, who in tempe.AFTER]
        self.assertEqual(got, want)

    def test_fc_battle_two(self):
        import dq4encounter
        _, members, _ = dq4encounter.bosses(self.prg)[2]
        self.assertEqual(sorted(m for m, _ in members), sorted((tempe.FC_STATUE, tempe.FC_CHAMELEON, tempe.FC_STATUE)))

    def test_monster_doc(self):
        doc = {m['id']: m for m in tempe.monster_doc(self.prg)}
        self.assertEqual(set(doc), {f'{tempe.CHAMELEON:02X}', f'{tempe.STATUE:02X}'})
        cham = doc[f'{tempe.CHAMELEON:02X}']
        self.assertIn('5B', [cham[f'행동{k}'] for k in range(1, 7)])
        # 몬스터 ホイミ 는 DQ5 몬스터 표의 5B(ホイミスライム). 일행 주문 번호 27 을 쓰는 몬스터는 DQ5 에 없다
        self.assertNotIn('27', [cham[f'행동{k}'] for k in range(1, 7)])
        self.assertEqual({doc[f'{tempe.STATUE:02X}'][f'행동{k}'] for k in range(1, 7)}, {'73'})

    def test_altar_cell_is_on_the_altar_and_the_old_one_in_the_trees(self):
        import dq4block
        from dq4environmentmap import block_prop
        source = dq4block.Map(self.prg, 0x0E, 0x00)
        walk = lambda x, y: not block_prop(source, source.cell(x, y) & 31) & 0x80  # noqa: E731
        ax, ay = tempe.ALTAR_CELL[0] // 2, tempe.ALTAR_CELL[1] // 2
        self.assertEqual((ax, ay), (0x0C, 0x03))
        self.assertTrue(walk(ax, ay))
        ox, oy = ev.ALTAR_CELL[0] // 2, ev.ALTAR_CELL[1] // 2
        self.assertFalse(any(walk(ox + dx, oy + dy) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))))
        # 제단에서 촌장 위 칸까지 곧장 내려오는 열(교회 북문·남문을 지남)
        doors = (0x94, 0x95, 0x96, 0x9C, 0x9D, 0xA0, 0xA2)
        for y in range(ay, tempe.CHIEF_TALK_CELL[1] // 2 + 1):
            prop = block_prop(source, source.cell(ax, y) & 31)
            self.assertTrue(not prop & 0x80 or prop in doors, f'(0C,{y:02X}) {prop:02X}')


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file(), 'local source ROM not present')
class WalkPatchTest(unittest.TestCase):
    def test_mapped_fc_actions_are_monster_actions_in_dq5(self):
        # 몬스터 행동 표에 옮긴 값은 DQ5 몬스터가 실제로 쓰는 행동이어야 한다(일행 주문 번호 27 을 넣으면 전투가 멈췄다)
        import dq4ch1event
        import dq4ch1walkcheck as wc
        data = (ROOT / 'rom' / 'dq5.sfc').read_bytes()
        used = {f'{b:02X}' for n in range(236) for b in data[wc.MONSTERS + n * 25 + 17:wc.MONSTERS + n * 25 + 23]}
        for k, v in {**dq4ch1event.FC_ACTIONS, **tempe.FC_ACTIONS}.items():
            self.assertIn(v, used, f'FC 행동 {k:02X}')

    def test_battle_patch_targets_the_module_monsters(self):
        import dq4ch1walkcheck as wc
        import dq4ch2walkcheck as cw
        data = (ROOT / 'rom' / 'dq5.sfc').read_bytes()
        # 선택에 몬스터를 적지 않으면 등록한 사건 모듈 모두의 사건 전투 몬스터를 덮는다
        every = {m for _, mod in cw.ch2.modules() for b in getattr(mod, 'BATTLES', ()) for m, _ in b['members']}
        self.assertTrue(set(tempe.MONSTERS) <= every)
        for kind in ('win', 'lose'):
            offs = {int(t.split('=')[0], 16) for t in cw.battle_patch(data, kind).split(';')}
            self.assertEqual({(o - wc.MONSTERS) // 25 for o in offs}, every, kind)
        with self.assertRaises(ValueError):
            cw.battle_patch(data, 'draw')


if __name__ == '__main__':
    unittest.main()
