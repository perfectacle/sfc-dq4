import unittest

import dq4chapter1 as ch
import dq4chapterbox as box
import dq4menumsg as mm
import dq4prologue as pro


class PrologueTests(unittest.TestCase):
    def test_messages_fit_and_do_not_clash(self):
        known = set(mm.CHARS) | {' '}
        self.assertFalse(set(pro.TEXTS) & set(ch.TEXTS))
        self.assertFalse(set(pro.TEXTS) & set(mm.TEXTS))
        for m, parts in pro.TEXTS.items():
            lines = 1
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, f'{m:03X}')
                elif p == ch.LINE:
                    lines += 1
                elif p in (ch.PAGE, ch.END):
                    self.assertLessEqual(lines, ch.PAGE_LINES, f'{m:03X}')
                    lines = 1

    def test_talk_numbers_follow_chapter1(self):
        self.assertEqual(pro.TALK_BASE, ch.TALK_BASE + len(ch._talks))
        for t in range(pro.TALK_BASE, pro.TALK_BASE + len(pro._talks)):
            self.assertIn(t + 0x3C6, pro.TEXTS)
        # 문지기는 묻기 대화(24F~26C): T + 3C6 뒤 예·아니요, +1·+2 가 대답
        for k in range(3):
            self.assertIn(pro.T_GATE + 0x3C6 + k, pro.TEXTS)

    def test_ask_talk_asks_and_sets_the_done_flag(self):
        body = pro.talk_doc()['scripts'][0]['body']
        self.assertEqual(body[0], {'op': 'msg', 'id': f'{pro.M_ASK:03X}'})
        self.assertEqual(body[1]['cond'], {'code': '05'})
        self.assertEqual(body[-1], {'op': 'flag-on', 'index': pro.DONE[0], 'mask': pro.DONE[1]})
        self.assertEqual(0x7E2190 + pro.DONE[0], box.PROLOGUE.flag[0])
        self.assertEqual(pro.DONE[1], box.PROLOGUE.flag[1])

    def test_master_waits_for_the_talk_then_leaves(self):
        lists, _, overrides, scripts = pro.npc_lists()
        ops = [(c['op'], c['args']) for c in scripts[0]['commands']]
        points = box.entry_points((box.PROLOGUE, box.CHAPTER1))
        calls = [a for op, a in ops if op == '37']
        self.assertEqual(calls[:2], [pro._long(points['box0']), pro._long(points['reveal'])])
        wait = ops.index(('09', [0x80 | pro.DONE[0], pro.DONE[1]]))
        self.assertEqual(ops[wait - 1], ('40', []))
        self.assertLess(wait, ops.index(('28', [])))
        self.assertEqual(overrides[0]['map'], pro.CELLAR)
        self.assertEqual(lists[0]['entries'][0]['fields']['talk'], pro.T_ASK)

    def test_villagers_stand_apart(self):
        cells = [(x, y) for x, y, *_ in pro.VILLAGERS] + [pro.SLEEPER_AT]
        self.assertEqual(len(cells), len(set(cells)))

    def test_chapter1_build_keeps_its_lists_without_prologue(self):
        doc = ch.npc_doc({'overrides': []})
        self.assertNotIn(pro.CELLAR, [lst['map'] for lst in doc['lists']])
        with_prologue = ch.npc_doc({'overrides': []}, prologue=True)
        self.assertIn(pro.CELLAR, [lst['map'] for lst in with_prologue['lists']])

    def test_added_talks_are_consecutive_from_900(self):
        # dq5talkwrite 는 덧붙인 대화를 900 부터 빈 번호 없이 받는다
        talks = [int(sc['talk'], 16) for sc in pro.talk_doc()['scripts']]
        self.assertEqual(talks, list(range(0x900, 0x900 + len(talks))))

    def test_flags_are_distinct(self):
        flags = [pro.DONE, pro.FROG_MET, pro.SHINSIA_START, pro.MORPH, pro.MORPH_BACK, pro.SHINSIA_MET, pro.DINNER,
                 pro.SUPPER]
        self.assertEqual(len(flags), len(set(flags)))
        for i, m in flags:
            self.assertEqual(bin(m).count('1'), 1)

    def test_overrides_put_later_story_first(self):
        # 대체 목록은 앞에 둔 것부터 맞춰 본다: 신시아를 만난 뒤 > 개구리를 만난 뒤 > 수련 뒤
        _, _, overrides, _ = pro.npc_lists()
        cellar = [(o['flag'], o['mask']) for o in overrides if o['map'] == pro.CELLAR]
        self.assertEqual(cellar, [pro.SHINSIA_MET, pro.FROG_MET, pro.DONE])
        village = [(o['flag'], o['mask']) for o in overrides if o['map'] == pro.VILLAGE]
        self.assertEqual(village, [pro.SHINSIA_MET, pro.FROG_MET])

    def test_end_event_moves_to_the_throne_room(self):
        code, at = pro.native()
        ev = code[at['end_event'] - pro.CODE_AT:]
        move = ev.index(0x90)
        g, n, x, y = pro.CHAPTER1_AT
        self.assertEqual(ev[move:move + 8], bytes((0x90, g, n, x, y, 0x01, 0x80, 0xFF)))
        self.assertEqual(f'{g:02X}/{n:02X}', ch.THRONE)
        self.assertEqual((x, y), ch.START[1:])
        # 서술을 띄운 뒤 곡 건너뛰기를 켜고 옮긴다
        self.assertLess(ev.index(0x60), move)

    def test_frog_form_clears_its_cell(self):
        # 51 은 안 보이게만 해서 말을 걸 수 있는 채로 남는다. 52 로 자리를 치운다
        form = next(sc for sc in pro.scripts() if sc['address'] == pro.FORM_SCRIPT)
        ops = [c['op'] for c in form['commands']]
        self.assertEqual(ops[ops.index('51') + 1], '52')

    def test_supper_seats_then_talks(self):
        # 대화 903 은 묻고 SUPPER 만 켠다. 저녁 대사는 끝 이벤트가 주인공을 식탁에 앉힌 뒤 띄운다
        body = next(sc for sc in pro.talk_doc()['scripts'] if int(sc['talk'], 16) == pro.T_FATHER_SUPPER)['body']
        self.assertEqual(body[-1], {'op': 'flag-on', 'index': pro.SUPPER[0], 'mask': pro.SUPPER[1]})
        code, at = pro.native()
        ev = code[at['end_event'] - pro.CODE_AT:]
        walk = bytes(b for d, k in pro.HERO_TO_SEAT for b in (d, k)) + bytes((0xC1, 0x40))
        self.assertEqual(ev[:len(walk)], walk)
        self.assertEqual(ev[len(walk)], 0x60)
        father = next(sc for sc in pro.scripts() if sc['address'] == pro.FATHER_SCRIPT)['commands']
        self.assertEqual(father[0], {'op': '09', 'args': [0x80 | pro.SUPPER[0], pro.SUPPER[1]]})


if __name__ == '__main__':
    unittest.main()
