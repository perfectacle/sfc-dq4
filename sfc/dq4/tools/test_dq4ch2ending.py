"""2장 끝: 빈 산트하임 성·「다음에 계속」·사건 뒤 마을 사람의 말(dq4ch2ending)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch1event  # noqa: E402
import dq4ch2event as ev  # noqa: E402
import dq4ch2ending as en  # noqa: E402
import dq4ch2endor as endor  # noqa: E402
import dq4ch2king as king  # noqa: E402
import dq4ch2slots as slots  # noqa: E402
import dq4chapterbox as box  # noqa: E402

DQ4 = ROOT / 'rom' / 'dq4.nes'
POINTS = {'box2': 0x5F8100, 'reveal': 0x5F8200, en.END_SCENE: 0x5F8300}


def context(message=0x1000, talk=0x0B00, points=POINTS):
    return next(c for c in ev.contexts(message, talk, points=points) if c.module is en)


def _flag(cond):
    return (cond['index'], cond['mask'])


class SlotTest(unittest.TestCase):
    def test_registered_with_its_slot(self):
        self.assertIn('dq4ch2ending', ev.EVENTS)
        self.assertEqual(context().slot, slots.SLOTS['E5'])
        self.assertTrue(all(i in slots.SLOTS['E5'].flags for i, _ in en.FLAGS))

    def test_scripts_use_only_the_borrowed_slots_and_fit(self):
        import dq5npcwrite
        owned = dict(slots.SLOTS['E5'].scripts)
        self.assertTrue(all(k in owned[en.SCRIPT_LIST] for k, _, _ in en.SCRIPTS.values()))
        made = en.scripts(context())
        by_address = {a: n for _, a, n in en.SCRIPTS.values()}
        self.assertEqual({s['address'] for s in made}, set(by_address))
        for s in made:
            code = dq5npcwrite.encode({'format': dq5npcwrite.FORMAT, 'commands': s['commands']})
            self.assertLessEqual(len(code), by_address[s['address']], s['address'])

    def test_end_box_is_a_game_scene_and_stays_before_the_event_code(self):
        self.assertIn(box.ENDING2, box.GAME_SCENES)
        self.assertEqual(box.ENDING2.subtitle, box.ENDING.subtitle)
        lay = box.Layout(box.CODE_AT, box.GAME_SCENES, bytes(32 * 80),
                         [bytes(box.BOX_W * box.rows(s.subtitle) * 2) for s in box.GAME_SCENES], box.palettes())
        first = min(s.code[0] for s in slots.SLOTS.values() if s.code[0] >> 16 == box.CODE_AT >> 16)
        self.assertLess(box.CODE_AT + len(lay.blob), first)

    def test_chapter_three_title_is_the_adopted_one(self):
        rows = (ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv').read_text(encoding='utf-8').splitlines()
        adopted = next(r.split('\t')[3] for r in rows if '\t第三章　' in r)
        self.assertEqual(box.ENDING2.title.split(), adopted.replace('３', '3').split())


class ScriptTest(unittest.TestCase):
    def test_ender_darkens_narrates_and_shows_the_end_box(self):
        ctx = context()
        ender = next(s for s in en.scripts(ctx) if s['address'] == en.SCRIPTS['ender'][1])['commands']
        ops = [c['op'] for c in ender]
        self.assertEqual(ops, ['28', '52', '3F', '37', '21', '37', '16'])
        darken = dq4ch1event.native()[1]['darken']
        self.assertEqual(ender[3]['args'], [darken & 0xFF, darken >> 8 & 0xFF, darken >> 16])
        self.assertEqual(ender[4]['args'], [ctx.msg['end'] & 0xFF, ctx.msg['end'] >> 8])
        end = POINTS[en.END_SCENE]
        self.assertEqual(ender[5]['args'], [end & 0xFF, end >> 8 & 0xFF, end >> 16])

    def test_voices_say_their_line_and_turn_on_their_flag(self):
        ctx = context()
        made = {s['address']: s['commands'] for s in en.scripts(ctx)}
        for name, flag in (('brey', en.SEEN_BREY), ('kiryl', en.SEEN_KIRYL)):
            cmds = made[en.SCRIPTS[name][1]]
            say = next(c for c in cmds if c['op'] == '21')
            self.assertEqual(say['args'], [ctx.msg[name] & 0xFF, ctx.msg[name] >> 8])
            self.assertIn({'op': '10', 'args': list(flag)}, cmds)

    def test_talk_bodies(self):
        ctx = context()
        bodies = dict(zip(en.TALKS, en.talk_scripts(ctx)))
        self.assertEqual(len(bodies), len(en.TALKS))
        maid = bodies['maid'][0]
        self.assertEqual(_flag(maid['cond']), king.CURED)
        self.assertEqual(maid['then'], {"op": "msg", "id": f"{ctx.msg['maid_cured']:03X}"})
        inner = maid['else'][0]
        self.assertEqual(_flag(inner['cond']), king.BAZAAR)
        self.assertEqual(inner['then']['id'], f"{ctx.msg['maid_ill']:03X}")
        self.assertEqual(inner['else']['id'], f"{ctx.msg['maid_start']:03X}")
        self.assertEqual(bodies['congrats'], [{"op": "msg", "id": f"{ctx.msg['congrats']:03X}"}])


class ListTest(unittest.TestCase):
    def lists(self):
        def person(m, time, fc):
            x, y = en.cell(*fc)
            return {"from": {}, "time": time, "fields": {"x": x, "y": y, "talk": 1}}
        out = {m: {"entries": []} for m in (ev.CASTLE, ev.THRONE, ev.BEDROOM, en.ENDOR_CASTLE,
                                            *{m for m, _, _ in en.WON_TALK})}
        for (m, time, fc), _ in en.WON_TALK.items():
            out[m]["entries"].append(person(m, time, fc))
        for m, fc, time, _ in (en.MINISTER_NIGHT, en.MAID, en.GUARD_NIGHT, en.KING_NIGHT):
            out[m]["entries"].append(person(m, time, fc))
        for time, fc, _, _, _, who in en.CASTLE_WON:
            if who is None:
                out[en.ENDOR_CASTLE]["entries"].append(person(en.ENDOR_CASTLE, time, fc))
        # 우승 뒤에는 없는 사람(FC 1C:$877D 에 없음)
        out[en.ENDOR_CASTLE]["entries"].append(person(en.ENDOR_CASTLE, 'day', (0x02, 0x21)))
        return out

    MESSENGER = {"from": {}, "time": "day", "fields": {"x": 52, "y": 21, "talk": 2}}

    def made(self, lists):
        town = [dict(e) for e in lists[endor.TOWN]["entries"]]
        return {endor.TOWN_MESSENGER: {"name": endor.TOWN_MESSENGER, "entries": [self.MESSENGER] + list(town)},
                endor.TOWN_SEEN: {"name": endor.TOWN_SEEN, "entries": list(town)}}

    def test_lists_flags_order_and_prefix(self):
        lists = self.lists()
        ctx = context()
        ctx.made = self.made(lists)
        new, over = en.npc_lists(lists, ctx)
        self.assertTrue(all(n['name'].startswith(slots.SLOTS['E5'].lists) for n in new))
        self.assertEqual({o['list'][4:] for o in over}, {n['name'] for n in new})
        # 산트하임 성은 2장 첫머리의 합류 뒤 목록보다, 엔돌은 2장 엔돌 목록보다 앞에 둔다
        self.assertTrue(all(o.get('first') for o in over))
        castle = [(o['flag'], o['mask'], o['list'][4:]) for o in over if o['map'] == ev.CASTLE]
        self.assertEqual(castle, [(*en.SEEN_BREY, en.ENDER), (*en.SEEN_KIRYL, en.ENDER), (*en.EMPTY, en.EMPTY_CASTLE)])
        by_name = {n['name']: n['entries'] for n in new}
        self.assertEqual(by_name[en.EMPTY_CASTLE], [])
        # 엔돌 마을은 앞 모듈의 우승·사자 목록을 고치고, 사자는 맨 앞 그대로
        msg = ctx.made[endor.TOWN_MESSENGER]['entries']
        self.assertIs(msg[0], self.MESSENGER)
        talks = {(e['fields']['x'], e['fields']['y']): e['fields']['talk'] for e in msg[1:]}
        self.assertEqual(talks[en.cell(0x0B, 0x1B)], ctx.talk['barmaid'])
        # 엔돌 성 1층은 FC 목록으로: 우승 뒤에 없는 사람은 빠지고 새로 선 병사가 들어온다
        hall = by_name[f'ch2_ending_{en.ENDOR_CASTLE.replace("/", "")}']
        self.assertEqual(len(hall), len(en.CASTLE_WON))
        self.assertNotIn(en.cell(0x02, 0x21), [(e['fields']['x'], e['fields']['y']) for e in hall])
        # 산트하임 사람은 제자리에서 대화만
        bedroom = {(e['fields']['x'], e['time']): e['fields']['talk'] for e in lists[ev.BEDROOM]['entries']}
        self.assertEqual(bedroom[en.cell(*en.MAID[1])[0], 'day'], ctx.talk['maid'])

    def test_state_tables_name_only_known_messages(self):
        ctx = context()
        states = en.state_messages(ctx)
        self.assertEqual(set(states), {'king_ill', 'king_cured', 'champion'})
        known = set(ctx.msg.values())
        for name, (sets, table) in states.items():
            self.assertTrue(sets)
            self.assertTrue(set(table.values()) <= known, name)
        self.assertEqual(states['king_ill'][1][(ev.BEDROOM, en.MAID[1], False)], ctx.msg['maid_ill'])


class MessageTest(unittest.TestCase):
    def test_reused_lines_are_the_same_parts(self):
        import dq4ch2talk
        self.assertEqual(en.MESSAGES['maid_start'], dq4ch2talk.TEXTS[(0x7AF, 0x7B0)])
        self.assertEqual(en.MESSAGES['guard_ill'], king.MESSAGES['guard_ill'])

    def test_message_names_cover_talks(self):
        self.assertTrue(set(en._ENDOR_TALKS) <= set(en.MESSAGES))
        self.assertTrue(set(en.FC_SHOWS) <= set(en.MESSAGES))


@unittest.skipUnless(DQ4.exists(), 'rom/dq4.nes 없음')
class FcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())

    def state(self, night, flags):
        import dq4talk
        ram = bytearray(0x8000)
        ram[0x615A] = 1
        ram[0x62ED] = 0x78 if night else 0
        for a, v in flags.items():
            ram[a] = v
        return dq4talk.State(ram)

    # 2장 우승 뒤(일행 합류·텐페·프레놀·왕 회복을 마친 상태)
    WON = {0x627E: 0x8E, 0x627F: 0x83, 0x627B: 0x72, 0x6283: 0x06, 0x6286: 0x02, 0x6284: 0x40}

    def records(self, fc_map, night, flags):
        import dq4talk
        return dq4talk.npc_list(self.prg, *fc_map, night, ram=self.state(night, flags).ram)

    def shows(self, rec, night, flags):
        import dq4talk
        return tuple(dq4talk.predict(self.prg, dq4talk.talk_id(rec, night), self.state(night, flags)))

    def test_endor_after_winning_says_the_fc_lines(self):
        import dq4talk
        for (m, time, fc), name in en.WON_TALK.items():
            night = time == 'night'
            got = [self.shows(r, night, self.WON) for r in self.records((0x04, int(m[3:], 16)), night, self.WON)
                   if dq4talk.pos(r, night) == fc]
            self.assertEqual(got, [en.FC_SHOWS[name]], (m, time, fc))

    def test_endor_castle_list_after_winning_is_the_fc_list(self):
        import dq4npcport
        import dq4talk
        want = []
        for night in (False, True):
            for r in self.records((0x04, 0x02), night, self.WON):
                x, y = dq4talk.pos(r, night)
                if max(en.cell(x, y)) > dq4npcport.MAX_CELL:
                    continue
                facing = r[7] if night and not r[0] & 1 else r[3]
                step = r[2] & 0x0F if night else r[2] >> 4
                want.append(('night' if night else 'day', (x, y), dq4npcport.FACING[facing & 3], step,
                             dq4talk.sprite(r, night) & 0x7F, self.shows(r, night, self.WON)))
        got = [(t, fc, f, i, p) for t, fc, f, i, p, _ in en.CASTLE_WON]
        self.assertEqual(got, [w[:5] for w in want])
        for (time, fc, *_, who), w in zip(en.CASTLE_WON, want):
            if who:
                self.assertEqual(w[5], en.FC_SHOWS[who], (time, fc))

    def test_santeem_people_follow_the_fc_flags(self):
        import dq4talk
        start = {0x627E: 0x8E, 0x627F: 0x03}
        ill = {**start, 0x6283: 0x08}
        cured = {**start, 0x6283: 0x02, 0x627B: 0x02}
        first = {(0x7A6,): 'minister_night', (0x7E3,): 'minister_ill', (0x7E9,): 'minister_cured',
                 (0x7AF, 0x7B0): 'maid_start', (0x7E5,): 'maid_ill', (0x7EA,): 'maid_cured',
                 (0x7AD,): 'guard_night', (0x7E4,): 'guard_ill', (0x551,): 'king_sleep', (0x7E2,): 'king_silent'}
        for _, (m, fc, time, talk), names in en.SANTEEM:
            night = time == 'night'
            fc_map = (0x01, int(m[3:], 16))
            for flags, want in zip((start, ill, cured), names):
                recs = [r for r in self.records(fc_map, night, flags) if dq4talk.pos(r, night) == fc]
                self.assertEqual([dq4talk.talk_id(r, night) for r in recs], [talk], (m, fc))
                self.assertEqual(first[self.shows(recs[0], night, flags)], want, (m, fc, flags))

    def test_empty_castle_lists_are_the_fc_ones(self):
        import dq4npcblock
        import dq4talk
        flags = {0x6284: 0x40}
        throne = self.records((0x01, 0x01), False, flags)
        self.assertEqual([dq4talk.pos(r) for r in throne], [(0x08, 0x00), en.CAT])
        cat = throne[1]
        self.assertEqual((dq4talk.sprite(cat) & 0x7F, cat[2] >> 4), (en.CAT_PICTURE, en.CAT_INTERVAL))
        self.assertEqual(self.shows(cat, False, flags), en.FC_SHOWS['cat'])
        bedroom = self.records((0x01, 0x02), False, flags)
        self.assertEqual([dq4talk.pos(r) for r in bedroom], [(0x08, 0x00)])
        # 보이지 않는 인물의 블록: 메시지 0388·0389 뒤 $6287 |= 08·10
        for rec, message, bit in ((throne[0], 0x388, 0x08), (bedroom[0], 0x389, 0x10)):
            block = dq4npcblock.record_block(rec, False)
            self.assertEqual(block[:7], bytes((0x26, message & 0xFF, message >> 8, 0x27, bit, 0x87, 0x62)))

    def test_chapter_end_check_is_any_map_00_with_either_seen_bit(self):
        # 1A:$B855: BCS / LDA $64 / CMP #00 / BNE / BRK 0C EB 18($6287 & 18) / BEQ … / LDX #03 / LDA #8B
        o = 0x1A * 0x4000 + 0xB855 - 0x8000
        code = self.prg[o:o + 0x18]
        self.assertEqual(code[2:6], bytes.fromhex('a564c900'))
        self.assertEqual(code[8:11], bytes.fromhex('000ceb'))
        self.assertEqual(code[11], en.SEEN_BREY[1] << 3 | en.SEEN_KIRYL[1] << 3)
        self.assertEqual(code[17:21], bytes.fromhex('a203a98b'))


if __name__ == '__main__':
    unittest.main()
