"""대화 스크립트(머리 바이트 → 대화 번호·생김새·자리, 문장 길이 규칙, 조건 풀기, 실행 순서)와 호출 루틴 태그 찾기를
합성 PRG·RAM 으로 검사한다."""
import unittest

import dq4talk as t

PRG_SIZE = 32 * 0x4000


def put(prg, addr, data, bank=t.BANK):
    o = bank * 0x4000 + (addr & 0x3FFF)
    prg[o:o + len(data)] = bytes(data)


def word(v):
    return [v & 0xFF, v >> 8]


class RecordTests(unittest.TestCase):
    def test_talk_id_day_and_night(self):
        rec = [0x10 | 0x01, 0b000_101_10, 0, 0x08, 0x42, 0, 0, 0x77, 0x88]
        self.assertEqual(t.talk_id(rec), 0x542)
        self.assertEqual(t.talk_id(rec, night=True), 0x277)          # bit0 켜짐 → 바이트 7
        rec[0] = 0x10
        self.assertEqual(t.talk_id(rec, night=True), 0x288)          # bit0 꺼짐 → 바이트 8
        rec[0] = 0x12
        self.assertEqual(t.talk_id(rec, night=True), 0x542)          # bit1 켜짐 → 낮과 같음

    def test_look_bits(self):
        rec = [0x80, 0x80, 0, 0x14, 0, 0x00, 0x80, 0x28]
        self.assertEqual(t.look(rec), 0x80 | 0x40 | 0x05)
        self.assertEqual(t.look(rec, night=True), 0x00 | 0x40 | 0x0A)

    def test_pos_uses_night_extra_bytes(self):
        rec = [0x10 | 0x08, 0, 0, 0, 0, 0x85, 0x06, 0x99, 0x98, 0x0A, 0x0B]
        self.assertEqual(t.pos(rec), (5, 6))
        self.assertEqual(t.pos(rec, night=True), (0x0A, 0x0B))
        self.assertEqual(t.pos([0x14] + rec[1:], night=True), (5, 6))

    def test_brk_len(self):
        self.assertEqual(t.brk_len(0x10, 0xCB), 4)
        self.assertEqual(t.brk_len(0x10, 0xFB), 3)
        self.assertEqual(t.brk_len(0x00, 0x83), 5)
        self.assertEqual(t.brk_len(0x00, 0xF3), 3)


def script_prg():
    prg = bytearray(PRG_SIZE)
    script = [0x45, 0x10,                       # msg 0510
              0x07, 0x94,                       # if day
              0x06, 0x45, 0x11, 0x18, 0x02, 0x40, 0x3E,   #   { msg 0511; flag 02 |= 40 }
              0x0B, 0x45, 0x12,                 # else msg 0512
              0x07, 0x9B, 0x02, 0x40,           # if not flag& 02 40
              0x45, 0x13,                       #   msg 0513
              0x07, 0x05, 0x45, 0x14, 0x0B, 0x12, 0x03,   # if yes msg 0514 else service 3
              0x3F]
    put(prg, 0x9000, script)
    put(prg, t.SCRIPTS + 2 * (0x010 - t.SCRIPT_FIRST), word(0x9000))
    put(prg, 0x9100, [0x45, 0x20, 0x07, 0x2F, 0x00])          # 모르는 조건 2F
    put(prg, t.SCRIPTS + 2 * (0x011 - t.SCRIPT_FIRST), word(0x9100))
    return prg


def ram(day=True, flags=None):
    r = bytearray(0x8000)
    r[0x62ED] = 0x10 if day else 0x80
    for k, v in (flags or {}).items():
        r[0x627B + k] = v
    return r


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.prg = script_prg()

    def test_parse_tree_shape_and_end(self):
        kind, a, tree, end = t.classify(self.prg, 0x010)
        self.assertEqual((kind, a, end), ('script', 0x9000, 0x9000 + 28))
        self.assertEqual(tree[0], ('msg', 0x510))
        self.assertEqual(tree[1][:4], ('if', True, 0x14, []))
        self.assertEqual(tree[1][4], [('msg', 0x511), ('flag|=', [0x02, 0x40])])
        self.assertEqual(tree[1][5], [('msg', 0x512)])
        self.assertEqual(tree[-1][0], 'if')          # 맨 끝 3F 는 문장이 아니라 블록 끝
        self.assertEqual(t.messages(tree), [0x510, 0x511, 0x512, 0x513, 0x514])

    def test_run_day_sets_flag_so_later_condition_fails(self):
        st = t.State(ram(day=True))
        out = []
        self.assertEqual(t.run(t.classify(self.prg, 0x010)[2], st, out), True)
        # 0x94 = not day: 낮이면 else 갈래. 플래그를 켜지 않았으니 not flag& 가 참
        self.assertEqual(out[:3], [0x510, 0x512, 0x513])

    def test_run_night_flag_blocks_branch_and_service(self):
        st = t.State(ram(day=False), yes=False)
        out = []
        t.run(t.classify(self.prg, 0x010)[2], st, out)
        self.assertEqual(out, [0x510, 0x511, t.SERVICE | 3])
        self.assertEqual(st.ram[0x627B + 2], 0x40)

    def test_unknown_condition_stops(self):
        p = t.Parser(self.prg)
        kind, _, tree, _ = t.classify(self.prg, 0x011, p)
        self.assertEqual(p.unknown, [('cond', 0x9103, 0x2F)])
        out = []
        self.assertFalse(t.run(tree, t.State(ram()), out))
        self.assertEqual(out, [0x520, None])

    def test_classify_ranges_and_predict(self):
        self.assertEqual(t.classify(self.prg, 3), ('service', 3))
        self.assertEqual(t.classify(self.prg, t.YESNO_FIRST), ('yesno', 0x500, 0x501, 0x502))
        self.assertEqual(t.classify(self.prg, t.MSG_FIRST + 1), ('msg', 0x500 + t.MSG_FIRST - t.YESNO_FIRST + 1))
        self.assertEqual(t.predict(self.prg, t.YESNO_FIRST, t.State(ram(), yes=False)), [0x500, 0x502])
        st = t.State(ram(day=False))
        self.assertEqual(t.predict(self.prg, 0x010, st), [0x510, 0x511, 0x514])
        self.assertEqual(st.ram[0x627B + 2], 0)            # predict 는 RAM 을 바꾸지 않는다

    def test_oracle_overrides_and_counts_mismatch(self):
        st = t.State(ram(day=True), oracle=[True, False, True])
        out = []
        t.run(t.classify(self.prg, 0x010)[2], st, out)
        self.assertEqual(out[:2], [0x510, 0x511])
        self.assertEqual(st.mismatch, 1)

    def test_cond_text(self):
        self.assertEqual(t.cond_text(True, 0x1B, [2, 0x40]), 'not flag& 02 40')


class StateTests(unittest.TestCase):
    def party_ram(self):
        r = ram()
        r[0x616A], r[0x616B] = 0x80 | 2, 0x80 | 5     # ミネア, トルネコ 걷는 중
        r[0x6172] = 0x80 | 7                           # アリーナ 마차
        r[0x6001 + 30 * 2] = 0x80                      # ミネア 살아 있음
        r[0x6001 + 30 * 5 + 0x13 + 3] = 0x80 | 0x21    # トルネコ 소지품
        r[0x6001 + 30 * 7 + 0x13] = 0x45
        return r

    def test_party_alive_dead(self):
        st = t.State(self.party_ram())
        self.assertTrue(st.cond(0x03, [2]))
        self.assertFalse(st.cond(0x03, [5]))           # 죽어 있음
        self.assertTrue(st.cond(0x13, [5]))
        self.assertFalse(st.cond(0x03, [1]))

    def test_items_walk_and_wagon_rule(self):
        r = self.party_ram()
        st = t.State(r)
        self.assertTrue(st.cond(0x11, [0x21]))
        self.assertFalse(st.cond(0x11, [0x45]))        # 마차 없음
        r[0x618E] = 0x20
        self.assertTrue(st.cond(0x11, [0x45]))
        r[0x618E] = 0x21                               # 1: 그룹이 같고 $41 bit7
        self.assertFalse(st.cond(0x11, [0x45]))
        r[0x41], r[0x618F], r[0x63] = 0x80, 0x04, 0x04
        self.assertTrue(st.cond(0x11, [0x45]))
        r[0x07BA] = 4
        self.assertFalse(st.cond(0x11, [0x45]))

    def test_lead_sex_chapter_flags(self):
        r = self.party_ram()
        st = t.State(r)
        self.assertFalse(st.cond(0x1E, []))            # ミネア 는 여자
        r[0x616A] = 0x80 | 0
        self.assertTrue(st.cond(0x1E, []))
        r[0x615C] = 1
        self.assertFalse(st.cond(0x1E, []))
        r[0x615A] = 2
        self.assertTrue(st.cond(0x16, [3]))
        r[0x627B + 4] = 0x11
        self.assertTrue(st.cond(0x1A, [4, 0x10]))
        self.assertFalse(st.cond(0x1A, [4, 0x11]))

    def test_guest_record_and_char_id(self):
        r = ram()
        st = t.State(r)
        self.assertEqual(st.record(10), 0x610F + 6)
        r[0x610F + 6 + 5] = 0xC6
        self.assertEqual(st.char_id(10), 0x09)
        r[0x610F + 6 + 5] = 0xCB
        self.assertTrue(st.female(10))
        self.assertEqual(st.items(10), set())


class CallTagTests(unittest.TestCase):
    def test_tags_follow_branches_and_known_leaves(self):
        prg = bytearray(PRG_SIZE)
        put(prg, 0x9000, [0xA9, 0x05, 0x20, 0xFF, 0xB0,          # LDA #5; JSR 이벤트
                          0xA9, 0x00, 0xD0, 0x0B,                # LDA #0; BNE(→ RTS)
                          0x8D, 0x45, 0x70,                      # STA $7045 (인물)
                          0x85, 0x63,                            # STA $63 (자리 옮김)
                          0x00, 0x2E, 0x73,                      # 아이템
                          0x20, 0x00, 0x91,
                          0x60])
        put(prg, 0x9100, [0x00, 0x07, 0xCF, 0x4C, 0x4A, 0xB8])
        tags = t.call_tags(prg, 0x9000)
        self.assertEqual(tags, [('event', 0x05), ('npc', None), ('move', None), ('item', None),
                                ('event', None), ('service', None)])


if __name__ == '__main__':
    unittest.main()
