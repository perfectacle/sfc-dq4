"""대화 스크립트 나무 찍기·실행(끝/플래그 문장)·조건 나머지 갈래·호출 표·이벤트 루틴 따라가기·기록 비교·명령줄을
합성 맵 표·인물 목록·스크립트가 든 PRG 와 합성 기록 파일로 검사한다. 대사 글자는 롬이 있어야 읽혀서 first_line 만 바꿔 끼운다."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4map
import dq4talk as t
from test_dq4talk import put, ram, script_prg, word


def fake_line(rom, m):
    return f'M{m:04X}'


def day_rec(tid, x=3, y=4, look=0):
    """낮 레코드: 머리 7바이트(F=10) + 길이 0 블록. 대화 번호 = (바이트 1 bit4-2) << 8 | 바이트 4."""
    return [0x10, (tid >> 8) << 2, 0, look << 2, tid & 0xFF, x, y, 0]


def night_rec(tid, x=5, y=6):
    """밤 전용 레코드: F=08 이면 대화 번호는 길이 바이트 뒤 첫 본문 바이트(바이트 8)."""
    return [0x08, tid >> 8, 0, 0, 0, x, y, 1, tid & 0xFF]


def world_prg():
    prg = script_prg()
    # 스크립트 포인터가 비어 있으면 풀기가 끝나지 않으므로 빈 칸은 한 문장짜리 기본 스크립트로 채운다
    put(prg, 0x9F00, [0x45, 0x00, 0x3F])
    for tid in range(t.SCRIPT_FIRST, t.YESNO_FIRST):
        o = t.SCRIPTS + 2 * (tid - t.SCRIPT_FIRST)
        if not (prg[t.BANK * 0x4000 + (o & 0x3FFF)] or prg[t.BANK * 0x4000 + (o & 0x3FFF) + 1]):
            put(prg, o, word(0x9F00))
    # 0x012: 호출 문장 둘(인자 없음 / 인자 둘)
    put(prg, 0x9400, [0x00, 0x00, 0x92, 0x01, 0x00, 0x93, 0xAA, 0xBB, 0x3F])
    put(prg, t.SCRIPTS + 2 * (0x012 - t.SCRIPT_FIRST), word(0x9400))
    put(prg, 0x9200, [0xA9, 0x05, 0x20, 0xFF, 0xB0, 0x60])      # LDA #5; JSR 이벤트
    put(prg, 0x9300, [0x60])                                    # 아무것도 하지 않는 호출 대상
    put(prg, 0x9500, [0xA9, 0x0A, 0x20, 0xF6, 0xB0, 0x60])      # 스크립트가 안 부르는 이벤트 입구
    # 0x013: 조건 갈래마다 호출 문장 하나씩
    put(prg, 0x9600, [0x07, 0x14, 0x00, 0x00, 0x92, 0x0B, 0x00, 0x00, 0x93, 0x3F])
    put(prg, t.SCRIPTS + 2 * (0x013 - t.SCRIPT_FIRST), word(0x9600))
    # 맵 표(뱅크 17): 그룹 0 에 맵 1개, 그룹 1(마지막)에 맵 1개
    put(prg, dq4map.GROUPS[1], word(0xB200) + word(0xB203) + word(0xFFFF), bank=0x17)
    put(prg, 0xB200, [0x05, 0x00, 0x80, 0x06, 0x00, 0x81, 0xFF], bank=0x17)
    # 인물 목록(뱅크 05): 그룹 0 의 순번 0 = 낮 3명 + 밤 1명, 그룹 1 의 순번 0 = 낮 1명
    put(prg, 0x8000, word(0x8010) + word(0x8040), bank=0x05)
    g0 = day_rec(0x179, look=2) + day_rec(0x161) + day_rec(0x010) + night_rec(0x010) + [0]
    put(prg, 0x8010, g0, bank=0x05)
    put(prg, 0x8040, day_rec(0x179, look=2) + [0], bank=0x05)
    # 진행 목록 표(뱅크 1C): 01/00 에서 플래그 2 bit0 이 켜지면 쓰는 목록 하나
    put(prg, dq4map.EVENT_LISTS[1], word(0x9D20), bank=0x1C)
    put(prg, 0x9D20, [0x01, 0x00, 0x01, 0x02, 0x40, 0x9D, 0xFF], bank=0x1C)
    put(prg, 0x9D40, day_rec(0x161) + night_rec(0x010) + [0], bank=0x1C)
    return prg


def out_of(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **kw)
    return r, buf.getvalue().splitlines()


class ScriptEdgeTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()

    def test_bare_end_statement(self):
        put(self.prg, 0x9700, [0x3F])
        p = t.Parser(self.prg)
        tree, end = p.block(0x9700)
        self.assertEqual((tree, end, p.unknown), ([('end',)], 0x9701, []))
        out = []
        self.assertEqual(t.run(tree, t.State(ram()), out), 'end')
        self.assertEqual(out, [])

    def test_unknown_statement_is_recorded(self):
        put(self.prg, 0x9700, [0x45, 0x01, 0x20, 0x3F])      # msg 0501, 모르는 문장 20
        p = t.Parser(self.prg)
        tree, _ = p.block(0x9700)
        self.assertEqual(tree, [('msg', 0x501), ('unknown', 0x9702, 0x20)])
        self.assertEqual(p.unknown, [('stmt', 0x9702, 0x20)])
        out = []
        self.assertFalse(t.run(tree, t.State(ram()), out))
        self.assertEqual(out, [0x501, None])

    def test_condition_the_state_cannot_solve_stops_run(self):
        tree = [('msg', 0x501), ('if', False, 0x2F, [], [('msg', 0x502)], None), ('msg', 0x503)]
        out = []
        self.assertFalse(t.run(tree, t.State(ram()), out))
        self.assertEqual(out, [0x501, None])

    def test_predict_service_number(self):
        self.assertEqual(t.predict(self.prg, 3, t.State(ram())), [t.SERVICE | 3])

    def test_flag_statements_change_ram(self):
        put(self.prg, 0x9700, [0x17, 3, 0x30, 0x19, 3, 0x07, 0x18, 3, 0x80, 0x3F])
        tree, _ = t.Parser(self.prg).block(0x9700)
        self.assertEqual([s[0] for s in tree], ['flag&=', 'flag=', 'flag|='])
        for stmt, want in zip(tree, (0x30, 0x07, 0xF0 | 0x80)):
            st = t.State(ram(flags={3: 0xF0}))
            t.run([stmt], st, [])
            self.assertEqual(st.ram[0x627B + 3], want)

    def test_show_prints_each_statement_kind(self):
        tree = [('unknown', 0x9702, 0x20), ('end',), ('call', [0x00, 0x92]),
                ('call+2', [0x00, 0x93, 0xAA, 0xBB]), ('flag&=', [3, 0x30])]
        _, lines = out_of(t.show, tree, None, 1)
        self.assertEqual(lines, ['  ?? 20 @15:9702', '  end', '  call 15:9200', '  call+2 15:9300 AA BB',
                                 '  flag&= 03 30'])


class StateBranchTests(unittest.TestCase):
    def test_day_counter_and_flag_or(self):
        st = t.State(ram(day=True))
        self.assertTrue(st.cond(0x14, []))
        self.assertFalse(t.State(ram(day=False)).cond(0x14, []))
        self.assertFalse(st.cond(0x02, []))
        self.assertTrue(t.State(ram(), counter=True).cond(0x02, []))
        self.assertFalse(st.cond(0x1C, [1, 0x00]))                    # 플래그 0 | 마스크 0
        self.assertTrue(t.State(ram(flags={1: 1})).cond(0x1C, [1, 0x00]))
        self.assertTrue(st.cond(0x05, []))
        self.assertIsNone(st.cond(0x2F, []))

    def test_dead_member_in_wagon_needs_wagon_and_early_chapter(self):
        r = ram()
        r[0x6172] = 0x80 | 7                    # 마차 자리에 레코드 7(죽어 있음)
        st = t.State(r)
        self.assertFalse(st.cond(0x13, [7]))    # 마차가 없다
        r[0x618E] = 0x20
        self.assertTrue(st.cond(0x13, [7]))
        r[0x6001 + 30 * 7] = 0x80               # 살려 두면 죽어 있다는 조건은 거짓
        self.assertFalse(st.cond(0x13, [7]))
        r[0x6001 + 30 * 7] = 0
        r[0x615A] = 4                           # 5장부터는 마차 자리를 보지 않는다
        self.assertFalse(st.cond(0x13, [7]))
        self.assertFalse(st.cond(0x13, [3]))    # 일행에 없는 인물

    def test_item_in_wagon_depends_on_wagon(self):
        r = ram()
        r[0x6172] = 0x80 | 7
        r[0x6001 + 30 * 7 + 0x13] = 0x45
        st = t.State(r)
        self.assertFalse(st.cond(0x11, [0x45]))
        r[0x618E] = 0x20
        self.assertTrue(st.cond(0x11, [0x45]))
        self.assertFalse(st.cond(0x11, [0x46]))

    def test_wagon_rules(self):
        r = ram()
        st = t.State(r)
        self.assertFalse(st.wagon())            # bit5 꺼짐
        r[0x618E] = 0xA0
        self.assertFalse(st.wagon())            # bit7
        r[0x618E] = 0x22                        # 2: $41 bit7 과 $6193 == 그룹
        self.assertFalse(st.wagon())
        r[0x41], r[0x6193], r[0x63] = 0x80, 5, 5
        self.assertTrue(st.wagon())
        r[0x6193] = 6
        self.assertFalse(st.wagon())
        r[0x618E] = 0x23                        # 3 이상은 세지 않는다
        self.assertFalse(st.wagon())


class TableWalkTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()

    def test_call_sites_walk_both_branches(self):
        self.assertEqual(t.call_sites(self.prg),
                         [(0x9200, 0x12, []), (0x9300, 0x12, [0xAA, 0xBB]),
                          (0x9200, 0x13, []), (0x9300, 0x13, [])])

    def test_show_calls_table(self):
        _, lines = out_of(t.show_calls, self.prg)
        self.assertEqual(lines, ['15:9200  이벤트(1C:$BF74 표) 이벤트 05  ← 012 013',
                                 '15:9300  -  ← 012+AABB 013',
                                 '호출 4곳, 루틴 2개: 이벤트(1C:$BF74 표) 1, 그 밖 1'])

    def test_event_callers_from_scripts_and_other_banks(self):
        put(self.prg, 0x8100, [0xA9, 0x09, 0x00, 0x07, 0xCF], bank=0x03)
        put(self.prg, 0xC200, [0xA9, 0x0B, 0x00, 0x07, 0xCF], bank=0x1F)
        put(self.prg, 0xA300, [0xA9, 0x07, 0x4C, 0x5F, 0xAD], bank=0x1C)
        cb = t.event_callers(self.prg)
        self.assertEqual(cb[5], {'012', '013'})                  # 스크립트가 부르는 이벤트
        self.assertEqual(cb[9], {'03:8102'})
        self.assertEqual(cb[0x0B], {'1F:C202'})
        self.assertEqual(cb[7], {'1C:A302'})
        # 15:$B0F6 로 들어가는 입구는 다른 부르는 곳이 없는 번호에만 붙는다(5 는 스크립트가 부름)
        self.assertEqual(cb[0x0A], {'15:9502'})
        self.assertNotIn('15:9202', cb[5])

    def test_event_table_reads_words(self):
        put(self.prg, 0xBF74, word(0xA000) + word(0xA100) + [0, 0] * 0x30, bank=0x1C)
        tab = t.event_table(self.prg)
        self.assertEqual((len(tab), tab[0], tab[1], tab[2]), (0x32, 0xA000, 0xA100, 0))

    def test_check_all_counts_and_unknown(self):
        ok, lines = out_of(t.check_all, self.prg)
        self.assertFalse(ok)
        self.assertEqual(lines, ['인물 낮 4명·밤 1명, 이벤트 목록 1개 2명, 대화 번호 3가지: msg 1, script 1, yesno 1',
                                 f'스크립트 {t.YESNO_FIRST - t.SCRIPT_FIRST}개를 풀어 못 읽은 명령 1개',
                                 '  cond 2F @15:9103'])
        put(self.prg, t.SCRIPTS + 2 * (0x011 - t.SCRIPT_FIRST), word(0x9F00))
        ok, lines = out_of(t.check_all, self.prg)
        self.assertTrue(ok)
        self.assertEqual(lines[1], f'스크립트 {t.YESNO_FIRST - t.SCRIPT_FIRST}개를 풀어 못 읽은 명령 0개')

    def test_npc_list_picks_day_or_night_and_event_list(self):
        day = t.npc_list(self.prg, 0, 0)
        self.assertEqual([t.talk_id(r) for r in day], [0x179, 0x161, 0x010])
        night = t.npc_list(self.prg, 0, 0, night=True)
        self.assertEqual([t.talk_id(r, True) for r in night], [0x010])
        self.assertEqual([t.talk_id(r) for r in t.npc_list(self.prg, 1, 0)], [0x179])
        # 플래그 2 bit0 이 켜지면 01/00 은 진행 목록의 인물로 바뀐다
        self.assertEqual([t.talk_id(r) for r in t.npc_list(self.prg, 1, 0, ram=ram(flags={2: 1}))], [0x161])

    def test_is_night_and_fmt(self):
        self.assertFalse(t.is_night(ram(day=True)))
        self.assertTrue(t.is_night(ram(day=False)))
        self.assertEqual(t.fmt(None), '?')
        self.assertEqual(t.fmt(t.SERVICE | 3), '서비스3')
        self.assertEqual(t.fmt(0x518), '0518')

    def test_sprite_number_and_high_bit(self):
        rec = day_rec(0x179, look=2)
        self.assertEqual(t.sprite(rec), 0x11)             # (look & 7F) + 0F
        rec[1] |= 0x40
        self.assertEqual(t.sprite(rec), 0x91)
        self.assertEqual(t.sprite(rec, night=True), 0x0F)   # 밤은 바이트 1 bit5 와 덧붙은 바이트 7 로 정한다

    def test_first_line_flattens_one_message(self):
        import test_dq4text
        line = t.first_line(test_dq4text.message_rom(), 2)
        self.assertNotIn('\n', line)
        self.assertTrue(0 < len(line) <= 60)


class CallTagWalkTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()

    def tags(self, addr, code):
        put(self.prg, addr, code)
        return t.call_tags(self.prg, addr)

    def test_map_event_brk(self):
        self.assertEqual(self.tags(0x9800, [0x00, 0x07, 0xDF, 0x60]), [('mapevent', None)])

    def test_illegal_opcode_ends_walk(self):
        self.assertEqual(self.tags(0x9800, [0x02, 0x00, 0x07, 0xCF, 0x60]), [])

    def test_alu_op_forgets_loaded_number(self):
        self.assertEqual(self.tags(0x9800, [0xA9, 0x05, 0x69, 0x01, 0x20, 0xFF, 0xB0, 0x60]), [('event', None)])

    def test_jump_keeps_number_and_continues(self):
        put(self.prg, 0x9A10, [0x20, 0xFF, 0xB0, 0x60])
        self.assertEqual(self.tags(0x9A00, [0xA9, 0x06, 0x4C, 0x10, 0x9A]), [('event', 6)])

    def test_branch_on_known_number_goes_one_way(self):
        # LDA #0; BEQ 은 늘 건너뛴다. 건너뛴 자리의 BRK 는 보지 않는다
        self.assertEqual(self.tags(0x9B00, [0xA9, 0x00, 0xF0, 0x03, 0x00, 0x07, 0xDF, 0x20, 0xFF, 0xB0, 0x60]),
                         [('event', 0)])


class EventOpsTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        put(self.prg, 0x8008, word(0x8028), bank=0x16)     # 16 번 뱅크 함수 4 = 메시지 출력(X:A)

    def ops(self, code, addr=0xA000):
        put(self.prg, addr, code, bank=0x1C)
        return t.event_ops(self.prg, addr)

    def test_battle_with_and_without_known_number(self):
        self.assertEqual(self.ops([0xA9, 0x03, 0x00, 0x01, 0x8F, 0x60]), [('battle', 3)])
        self.assertEqual(self.ops([0x00, 0x01, 0x8F, 0x60]), [('battle', None)])

    def test_flag_brk_statements_and_message(self):
        self.assertEqual(self.ops([0x00, 0x05, 0xCB, 0x40, 0x00, 0x06, 0xDB, 0x80, 0x00, 0x07, 0xEB, 0x01,
                                   0x00, 0x34, 0x1B, 0x60]),
                         [('flag+', (0x6280, 0x40)), ('flag-', (0x6281, 0x80)), ('flag?', (0x6282, 0x01)),
                          ('msg', 0x134)])

    def test_message_through_x_and_a(self):
        self.assertEqual(self.ops([0xA2, 0x01, 0xA9, 0x34, 0x00, 0x04, 0x6F, 0x60]), [('msg', 0x134)])
        self.assertEqual(self.ops([0xA9, 0x34, 0x00, 0x04, 0x6F, 0x60]), [('msg', 0x34)])

    def test_read_modify_write_flag(self):
        self.assertEqual(self.ops([0xAD, 0x7C, 0x62, 0x09, 0x10, 0x8D, 0x7C, 0x62, 0x60]),
                         [('flag+', (0x627C, 0x10))])
        self.assertEqual(self.ops([0xAD, 0x7D, 0x62, 0x29, 0xEF, 0x8D, 0x7D, 0x62, 0x60]),
                         [('flag-', (0x627D, 0xEF))])
        # 다른 자리에 저장하면 켜고 끄기가 아니다
        self.assertEqual(self.ops([0xAD, 0x7D, 0x62, 0x09, 0x10, 0x8D, 0x7E, 0x62, 0x60]), [])

    def test_place_writes_with_known_and_unknown_value(self):
        self.assertEqual(self.ops([0xA9, 0x07, 0x85, 0x63, 0x8D, 0xED, 0x62, 0x60]),
                         [('place', (0x63, 7)), ('place', (0x62ED, 7))])
        self.assertEqual(self.ops([0xAD, 0x34, 0x12, 0x85, 0x64, 0x60]), [('place', (0x64, None))])

    def test_hide_needs_known_x(self):
        self.assertEqual(self.ops([0xA2, 0x02, 0x20, 0x5C, 0xBF, 0x60]), [('hide', 8)])
        self.assertEqual(self.ops([0x20, 0x5C, 0xBF, 0x60]), [])
        self.assertEqual(self.ops([0xA2, 0x02, 0x20, 0x4E, 0xBF, 0x60]), [])      # 자리 두기 도우미는 따라가지 않는다

    def test_subroutine_depth_stops_at_two_levels(self):
        put(self.prg, 0xA100, [0x20, 0x10, 0xA1, 0x00, 0x34, 0x1B, 0x60], bank=0x1C)
        put(self.prg, 0xA110, [0x20, 0x20, 0xA1, 0x00, 0x35, 0x1B, 0x60], bank=0x1C)
        put(self.prg, 0xA120, [0x00, 0x36, 0x1B, 0x60], bank=0x1C)
        self.assertEqual(self.ops([0x20, 0x00, 0xA1, 0x60]), [('msg', 0x135), ('msg', 0x134)])

    def test_jump_continues_in_target(self):
        put(self.prg, 0xA200, [0x00, 0x34, 0x1B, 0x60], bank=0x1C)
        self.assertEqual(self.ops([0x4C, 0x00, 0xA2, 0x00, 0x35, 0x1B]), [('msg', 0x134)])

    def test_unknown_branch_follows_both_known_branch_one(self):
        # LDA $0300; BNE → A009. 두 갈래 모두 따라간다
        self.assertEqual(self.ops([0xAD, 0x00, 0x03, 0xD0, 0x04, 0x00, 0x34, 0x1B, 0x60,
                                   0x00, 0x35, 0x1B, 0x60]),
                         [('msg', 0x134), ('msg', 0x135)])
        # LDA #0; BEQ → A007: 늘 건너뛴다
        self.assertEqual(self.ops([0xA9, 0x00, 0xF0, 0x03, 0x00, 0x34, 0x1B, 0x00, 0x35, 0x1B, 0x60], 0xA300),
                         [('msg', 0x135)])

    def test_jump_out_of_bank_ends_walk(self):
        self.assertEqual(self.ops([0x4C, 0x00, 0xC0, 0x00, 0x34, 0x1B]), [])

    def test_illegal_opcode_stops(self):
        self.assertEqual(self.ops([0x02, 0x00, 0x34, 0x1B]), [])


class EventSummaryTests(unittest.TestCase):
    def test_parts_in_order(self):
        ops = [('battle', 3), ('battle', None), ('flag+', (0x6280, 0x40)), ('flag-', (0x6281, 0x80)),
               ('flag?', (0x6282, 1)), ('msg', 0x134), ('msg', 0x135), ('place', (0x63, 7)),
               ('place', (0x62ED, None)), ('hide', 9), ('hide', 8), ('hide', 8)]
        self.assertEqual(t.event_summary(ops),
                         ['전투 03 ?', '플래그 켬 $6280&40', '플래그 끔(&) $6281&80', '플래그 봄 $6282&01',
                          '메시지 0134 0135', '자리 $63=07 $62ED=?', '인물 숨김 08 09'])
        self.assertEqual(t.event_summary([]), [])


class EventsLogTests(unittest.TestCase):
    def write(self, d, lines, before=None):
        Path(d, 'talk_1.bin').write_bytes(bytes(before or bytearray(0x8000)))
        Path(d, 'talk.txt').write_text('\n'.join(lines) + '\n')

    def test_keeps_changed_values_until_next_event(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, ['0 talk 06 1', '1 ev1C 05', '2 battle 0A', '3 msg 0134', '4 w 627C 40',
                           '4 w 627C 41', '5 w 627D 00', '6 w 616A 82', '7 w 7000 41', '8 ev1C 06', '9 battle 01'])
            ev, battles, flags, msgs, party = t.events_log(d)
        self.assertEqual((ev, battles, msgs), (5, [0x0A], [0x134]))
        self.assertEqual(flags, {0x627C: 0x41, 0x7000: 0x41})        # 마지막 값, 바뀐 것만
        self.assertEqual(party, {0x616A: 0x82})

    def test_no_event_line(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, ['0 talk 06 1', '1 battle 0A'])
            self.assertEqual(t.events_log(d), (None, [], {}, [], {}))


class ShowEventsTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        put(self.prg, 0xBF74, word(0xA000) + word(0xA100), bank=0x1C)
        put(self.prg, 0xA000, [0xA9, 0x03, 0x00, 0x01, 0x8F, 0x60], bank=0x1C)
        put(self.prg, 0xA100, [0x00, 0x05, 0xCB, 0x40, 0x00, 0x34, 0x1B, 0x60], bank=0x1C)
        # 5 번 이벤트는 표의 다른 칸과 겹치지 않게 칸 5 도 같은 루틴으로
        put(self.prg, 0xBF74 + 2 * 5, word(0xA000), bank=0x1C)

    def log(self, d, lines):
        Path(d, 'talk_1.bin').write_bytes(bytes(0x8000))
        Path(d, 'talk.txt').write_text('\n'.join(lines) + '\n')

    def test_table_lines_without_logs(self):
        ok, lines = out_of(t.show_events, self.prg, None)
        self.assertTrue(ok)
        self.assertEqual(len(lines), 0x32)
        self.assertEqual(lines[0], '00 1C:A000  전투 03  ← -')
        self.assertEqual(lines[1], '01 1C:A100  플래그 켬 $6280&40; 메시지 0134  ← -')
        self.assertEqual(lines[5], '05 1C:A000  전투 03  ← 012 013')
        self.assertEqual(lines[0x0A], '0A 1C:0000  -  ← 15:9502')

    def test_log_matches_or_flags_battle_mismatch(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e, tempfile.TemporaryDirectory() as f:
            self.log(d, ['1 ev1C 05', '2 battle 03', '3 w 627C 40', '4 w 7000 41', '5 w 616A 82', '6 msg 0134',
                         '7 msg 0134'])
            self.log(e, ['1 ev1C 05', '2 battle 0A'])
            self.log(f, ['1 battle 0A'])
            ok, lines = out_of(t.show_events, self.prg, None, [d, f])
            self.assertTrue(ok)
            i = lines.index('05 1C:A000  전투 03  ← 012 013')
            self.assertEqual(lines[i + 1], '   실행: 전투 03; 플래그 $627C=40; 자리 $7000=41; 일행 $616A=82; 메시지 0134')
            self.assertEqual(lines[-1], '기록 1개, 전투 번호 다름 0')
            ok, lines = out_of(t.show_events, self.prg, None, [e])
            self.assertFalse(ok)
            i = lines.index('05 1C:A000  전투 03  ← 012 013')
            self.assertEqual(lines[i + 1], '   실행: 전투 0A  (전투 번호 다름)')
            self.assertEqual(lines[-1], '기록 1개, 전투 번호 다름 1')


class MapPrintTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()
        p = mock.patch.object(t, 'first_line', fake_line)
        p.start()
        self.addCleanup(p.stop)

    def test_describe_every_kind(self):
        _, lines = out_of(t.describe, self.prg, None, 3)
        self.assertEqual(lines, ['  서비스 3 (15:B851)'])
        _, lines = out_of(t.describe, self.prg, None, t.MSG_FIRST)
        self.assertEqual(lines, ['  msg 0518  M0518'])
        _, lines = out_of(t.describe, self.prg, None, t.YESNO_FIRST)
        self.assertEqual(lines, ['  msg 0500  M0500', '  if yes: msg 0501  M0501', '  else:   msg 0502  M0502'])
        _, lines = out_of(t.describe, self.prg, None, 0x010)
        self.assertEqual(lines, ['  스크립트 15:9000-901B', '    msg 0510  M0510', '    if not day',
                                 '      msg 0511  M0511', '      flag|= 02 40', '    else', '      msg 0512  M0512',
                                 '    if not flag& 02 40', '      msg 0513  M0513', '    if yes',
                                 '      msg 0514  M0514', '    else', '      service 03'])

    def test_show_looks_groups_by_sprite(self):
        _, lines = out_of(t.show_looks, self.prg, None)
        self.assertEqual(lines, ['그림 0F: 인물   5  장소  4 (00/00 00/00밤 01/00* 01/00*밤)  ',
                                 '그림 11: 인물   2  장소  2 (00/00 01/00)  M0518'])


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.prg = world_prg()

    def dump(self, d, n, night=False, g=0, k=0):
        r = ram(day=not night)
        r[0x63], r[0x64] = g, k
        Path(d, f'talk_{n}.bin').write_bytes(bytes(r))

    def test_same_different_missing_and_overridden(self):
        with tempfile.TemporaryDirectory() as d:
            self.dump(d, 1)
            Path(d, 'talk.txt').write_text('\n'.join([
                'a talk 06 1', 'a cond 1', 'a msg 0518',            # 같음(풀 수 있는 조건이라 cond 기록은 안 쓴다)
                'a talk 07 1', 'a msg 0500', 'a msg 0502',          # 예 를 골랐다고 보는데 아니오 쪽 기록
                'a talk 20 1', 'a msg 0123',                        # 인물 없음
                'a talk 06 1', 'a tid 161', 'a msg 0500', 'a msg 0501',   # 대화 번호를 바꿔 기록
                'bad', '']))
            ok, lines = out_of(t.compare, self.prg, d)
        self.assertFalse(ok)
        self.assertEqual(lines, ['00/00 슬롯 06 대화 179: 기록 0518 / 예측 0518 → 같음',
                                 '00/00 슬롯 07 대화 161: 기록 0500 0502 / 예측 0500 0501 → 다름',
                                 '00/00 슬롯 20: 인물 없음, 기록 0123',
                                 '00/00 슬롯 06 (대화 번호를 161 로 바꿈) 대화 161: 기록 0500 0501 / 예측 0500 0501 → 같음',
                                 '4번 중 1 다름, 그중 0번은 풀지 못한 조건을 기록대로 따름'])

    def test_no_answer_and_night_service_trim(self):
        with tempfile.TemporaryDirectory() as d:
            self.dump(d, 1)
            self.dump(d, 2, night=True)
            Path(d, 'talk.txt').write_text('\n'.join([
                'a talk 07 1', 'a msg 0500', 'a msg 0502',
                'a talk 06 2', 'a msg 0510', 'a msg 0511', 'a svc 03', 'a msg 0777', '']))
            ok, lines = out_of(t.compare, self.prg, d, False)
        self.assertTrue(ok)
        self.assertEqual(lines[0], '00/00 슬롯 07 대화 161: 기록 0500 0502 / 예측 0500 0502 → 같음')
        self.assertEqual(lines[1], '00/00 밤 슬롯 06 대화 010: 기록 0510 0511 서비스3 / 예측 0510 0511 서비스3 → 같음')

    def test_counter_flag_of_log_line(self):
        with tempfile.TemporaryDirectory() as d:
            self.dump(d, 1)
            put(self.prg, 0x9700, [0x07, 0x02, 0x45, 0x30, 0x0B, 0x45, 0x31, 0x3F])   # if counter msg 530 else msg 531
            put(self.prg, t.SCRIPTS + 2 * (0x010 - t.SCRIPT_FIRST), word(0x9700))
            # 인물 슬롯 8 이 대화 010 (낮 목록 세 번째)
            Path(d, 'talk.txt').write_text('a talk 08 1 0\na msg 0530\na talk 08 1 1\na msg 0531\n')
            ok, lines = out_of(t.compare, self.prg, d)
        self.assertTrue(ok)
        self.assertEqual(lines[0], '00/00 슬롯 08 대화 010: 기록 0530 / 예측 0530 → 같음')
        self.assertEqual(lines[1], '00/00 슬롯 08 대화 010: 기록 0531 / 예측 0531 → 같음')


class MainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rom = Path(cls.tmp.name, 'synthetic.nes')
        cls.rom.write_bytes(b'NES\x1a' + bytes((32, 0, 0x10, 0)) + bytes(8) + bytes(world_prg()))
        cls.ram_day = Path(cls.tmp.name, 'day.ram')
        cls.ram_day.write_bytes(bytes(ram()))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        p = mock.patch.object(t, 'first_line', fake_line)
        p.start()
        self.addCleanup(p.stop)

    def run_main(self, *args):
        code, buf = 0, io.StringIO()
        with mock.patch.object(sys, 'argv', ['dq4talk.py', str(self.rom), *args]), contextlib.redirect_stdout(buf):
            try:
                t.main()
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue().splitlines()

    def test_all_fails_while_a_command_is_unread(self):
        code, lines = self.run_main('all')
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], '  cond 2F @15:9103')

    def test_calls_and_id(self):
        code, lines = self.run_main('calls')
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], '호출 4곳, 루틴 2개: 이벤트(1C:$BF74 표) 1, 그 밖 1')
        _, lines = self.run_main('id', '179')
        self.assertEqual(lines, ['  msg 0518  M0518'])

    def test_map_people_day_night_and_predictions(self):
        _, lines = self.run_main('00', '00')
        self.assertEqual(lines[:2], [' 0 슬롯 06 (03,04) 겉모습 82 대화 179', '  msg 0518  M0518'])
        _, lines = self.run_main('00', '00', '--night')
        self.assertEqual(lines[0], ' 0 슬롯 06 (05,06) 겉모습 80 대화 010')
        _, lines = self.run_main('00', '00', '--ram', str(self.ram_day))
        self.assertEqual(lines[:3], [' 0 슬롯 06 (03,04) 겉모습 82 대화 179', '  → 0518', '  msg 0518  M0518'])

    def test_looks_events_and_compare(self):
        _, lines = self.run_main('looks')
        self.assertEqual(lines[0], '그림 0F: 인물   5  장소  4 (00/00 00/00밤 01/00* 01/00*밤)  ')
        code, lines = self.run_main('events')
        self.assertEqual((code, len(lines)), (0, 0x32))
        with tempfile.TemporaryDirectory() as d:
            r = ram()
            Path(d, 'talk_1.bin').write_bytes(bytes(r))
            Path(d, 'talk.txt').write_text('a talk 06 1\na msg 0518\n')
            code, lines = self.run_main('compare', d)
            self.assertEqual(code, 0)
            self.assertEqual(lines[0], '00/00 슬롯 06 대화 179: 기록 0518 / 예측 0518 → 같음')
            Path(d, 'talk.txt').write_text('a talk 07 1\na msg 0500\na msg 0502\n')
            code, lines = self.run_main('compare', d)
            self.assertEqual(code, 1)
            code, lines = self.run_main('compare', d, '--no')
            self.assertEqual(code, 0)
            code, _ = self.run_main('events', '--compare', d)
            self.assertEqual(code, 0)


if __name__ == '__main__':
    unittest.main()
