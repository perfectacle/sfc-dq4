import unittest

import dq4chapter1 as ch
import dq4chapterbox as box
import dq4menumsg as mm
import dq4prologue as pro
from dq4chapter1 import lorom
from w65816 import Cpu


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
        self.assertLessEqual(pro.TALK_END, 0x900)

    def test_gate_asks_in_an_appended_talk(self):
        scripts = {s['talk']: s['body'] for s in pro.talk_doc()['scripts']}
        self.assertEqual(scripts[f'{pro.T_GATE:03X}'], pro._yes_no(pro.M_GATE_ASK, pro.M_GATE_YES, pro.M_GATE_NO))
        talks = [int(t, 16) for t in scripts]
        self.assertEqual(talks, list(range(0x900, 0x900 + len(talks))))

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
        points = box.entry_points(box.GAME_SCENES)
        calls = [a for op, a in ops if op == '37']
        _, at = pro.native()
        # 무음 곡 → 상자 → 검은 화면의 칼 여섯 합 → 느린 밝히기(NDS 0x0E 90)
        self.assertEqual(calls[:4], [pro._long(at['quiet']), pro._long(points['box0']), pro._long(at['spar']),
                                     pro._long(at['reveal_slow'])])
        wait = ops.index(('09', [0x80 | pro.DONE[0], pro.DONE[1]]))
        # 말을 걸기 전에 저절로 대화를 연다(37 → 이벤트 A0 → 06:AF1C)
        self.assertEqual(ops[wait - 1], ('37', pro._long(at['talk_here'])))
        self.assertLess(wait, ops.index(('28', [])))
        self.assertEqual(overrides[0]['map'], pro.CELLAR)
        self.assertEqual(lists[0]['entries'][0]['fields']['talk'], pro.T_ASK)

    def test_reveal_and_hold_are_one_call(self):
        # 인물 스크립트는 37 마다 다음 차례를 기다리므로 밝히기와 기다리기를 한 루틴에 둔다
        code = pro._reveal_hold()
        self.assertTrue(code.endswith(b''.join(box.wait(f) for f in pro.REVEAL_HOLD) + box.LEAVE))
        self.assertLess(len(box.reveal_code(pro.REVEAL_STEP, song_wait=False)), len(box.reveal_code(pro.REVEAL_STEP)))

    def test_morph_spin_turns_fast_then_walks_at_old_speed(self):
        for script in pro.scripts()[1:3]:
            ops = [(c['op'], c['args']) for c in script['commands']]
            first = ops.index(('1E', [pro.SPIN_SPEED]))
            self.assertEqual([op for op, _ in ops[first + 1:first + 17]], ['2F', '37'] * 8)
            self.assertEqual(ops[first + 17], ('1E', [pro.WALK_SPEED]))
            self.assertNotIn(('1E', [pro.SPIN_SPEED]), ops[first + 1:])

    def test_supper_father_runs_every_turn(self):
        _, new_lists, _, _ = pro.npc_lists()
        supper = next(lst for lst in new_lists if lst['name'] == 'village_supper')
        father = next(e for e in supper['entries'] if e['fields']['talk'] == pro.T_FATHER_SUPPER)
        self.assertEqual(father['fields']['interval'], 1)

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

    def test_talk_event_calls_the_field_talk(self):
        code, at = pro.native()
        ev = code[at['talk_event'] - pro.CODE_AT:][:5]
        self.assertEqual(ev, bytes((0xA0, *pro._long(at['talk_slot']), 0xFF)))
        slot = code[at['talk_slot'] - pro.CODE_AT:]
        self.assertIn(bytes((0x22, *pro.TALK_TO.to_bytes(3, 'little'))), slot)

    def test_inside_is_a_rectangle(self):
        # 65816 을 흉내 내지 않고 비교·분기만 따라가 사각형 안이면 LDA #0, 밖이면 LDA #1 에 닿는지 본다
        def run(x, y):
            code, pc, a = pro._inside(34, 8, 35, 10), 3, 0
            while True:
                op = code[pc]
                if op == 0xAF:
                    a = {0x3020: x, 0x3080: y}[code[pc + 1] | code[pc + 2] << 8]
                    pc += 4
                elif op == 0x29:
                    a &= code[pc + 1]
                    pc += 2
                elif op == 0xC9:
                    carry = a >= code[pc + 1]
                    pc += 2
                elif op in (0x90, 0xB0):
                    pc += 2 + (code[pc + 1] if (op == 0xB0) == carry else 0)
                elif op == 0xC2:
                    return code[pc + 3]
        for x, y, want in ((34, 9, 0), (35, 8, 0), (35, 10, 0), (33, 9, 1), (36, 9, 1), (34, 7, 1), (34, 11, 1)):
            self.assertEqual(run(x, y), want, (x, y))

    def test_frog_waits_hidden_and_triggers_in_order(self):
        _, at = pro.native()
        frog = next(s for s in pro.scripts() if s["address"] == pro.FROG_SCRIPT)["commands"]
        self.assertEqual(frog[0]["op"], '27')
        calls = [c["args"] for c in frog if c["op"] == '05']
        want = [at[n] for n in ('voice_hut', 'voice_bridge', 'frog_call')]
        self.assertEqual([a[0] | a[1] << 8 | a[2] << 16 for a in calls], want)
        self.assertEqual(frog[-1]["op"], '16')
        lists = pro.npc_lists()[0]
        village = next(x for x in lists if x["map"] == pro.VILLAGE)["entries"]
        self.assertEqual(village[-1]["fields"]["interval"], 1)


if __name__ == '__main__':
    unittest.main()


class FaceHeroTests(unittest.TestCase):
    def facing(self, hero, npc):
        at = 0x3E8000
        rom = bytearray(0x400000)
        code = pro._face_hero()
        rom[lorom(at):lorom(at) + len(code)] = code
        cpu = Cpu(bytes(rom), bytearray(0x20000))
        cpu.wram[0x90] = 3
        cpu.wram[0x3020], cpu.wram[0x3080] = hero
        cpu.wram[0x3023], cpu.wram[0x3083] = npc[0] | 0x80, npc[1]
        cpu.jsl(at)
        return cpu.wram[0x31E3], cpu.wram[0x3243], cpu.wram[0x3263], cpu.wram[0x31E0]

    def test_turns_to_the_larger_axis(self):
        self.assertEqual(self.facing((12, 10), (10, 11)), (0x11, 0x01, 0x01, 0))
        self.assertEqual(self.facing((8, 10), (10, 10)), (0x22, 0x02, 0x02, 0))
        self.assertEqual(self.facing((10, 14), (10, 11)), (0x44, 0x04, 0x04, 0))
        self.assertEqual(self.facing((11, 6), (10, 11)), (0x88, 0x08, 0x08, 0))
