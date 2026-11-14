import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ev  # noqa: E402
import dq4ch2partytalk as pt  # noqa: E402
import dq4ch2partytalkcheck as check  # noqa: E402
import dq4ch2partytalknds as nds  # noqa: E402
import dq4menumsg as mm  # noqa: E402
from dq4ch2slots import SLOTS  # noqa: E402


def _ctx(first=0x1000):
    return next(c for c in ev.contexts(first) if c.module is pt)


class PartyTalkTest(unittest.TestCase):
    def test_registered_in_its_slot(self):
        self.assertIn('dq4ch2partytalk', ev.EVENTS)
        ctx = _ctx()
        self.assertEqual(ctx.key, 'P')
        self.assertEqual(ctx.code_at, SLOTS['P'].code[0])
        self.assertEqual(list(ctx.msg), list(pt.MESSAGES))
        # 마지막으로 고른 줄은 예약된 바이트 값 flag 자리
        self.assertIn(pt.LAST[0], SLOTS['P'].byte_flags)

    def test_every_line_has_a_message_and_every_message_a_line(self):
        self.assertEqual({ln.message for ln in pt.LINES}, set(pt.MESSAGES))

    def test_record_bytes(self):
        line = pt.Line('3D/03', pt.KIRYL, 'x', priority=3, time='night', on=((0x60, 0x01),), lead=pt.ALENA)
        self.assertEqual(pt.record(line, 0x0EF7),
                         bytes((13, 3, pt.KIRYL, 2, 0xF7, 0x0E, 2, pt.ON, 0x60, 0x01, pt.LEAD, pt.ALENA, 0)))

    def test_lists_are_by_map_in_priority_order(self):
        rows = pt.lists(None)
        self.assertIn(pt.FIELD_KEY, rows)
        tempe = rows[(0x3D, 0x03)]
        self.assertEqual([r[1] for r in tempe], sorted(r[1] for r in tempe))

    def _talks(self):
        """줄 표의 talked 묶음마다 겹치지 않는 가짜 대화 번호(빌드의 npc_lists 대신)."""
        tokens = sorted({k for ln in pt.LINES for k in ln.talked})
        return {k: frozenset({0x900 + i}) for i, k in enumerate(tokens)}

    def test_native_table_reads_back(self):
        ctx = _ctx()
        saved, pt._TALKS = pt._TALKS, self._talks()
        try:
            blob, at = pt.native(ctx)
        finally:
            pt._TALKS = saved
        self.assertLessEqual(ctx.code_at + len(blob), SLOTS['P'].code[1])
        self.assertEqual(at, ctx.at)
        data = bytearray(0x400000)
        o = pt.ch1.lorom(ctx.code_at)
        data[o:o + len(blob)] = blob
        table = pt.table(bytes(data), at['maps'])
        ids, groups = pt.talk_tables(self._talks())
        self.assertEqual(pt.talk_ids(bytes(data), at), ids)
        rows = pt.lists(ctx.msg, sets={g: 0 for g in groups})
        for recs in table.values():
            for row in recs:
                for kind, lo, hi in row[4]:
                    if kind == pt.TALKED:
                        self.assertIn(pt.talk_set(bytes(data), at['maps'], lo | hi << 8), list(groups.values()))
        self.assertEqual(set(table), set(rows))
        for key, recs in rows.items():
            self.assertEqual([r[4] | r[5] << 8 for r in recs], [row[3] for row in table[key]])
        self.assertEqual(set(ctx.msg.values()), {row[3] for recs in table.values() for row in recs})

    def test_without_npc_lists_the_talked_lines_are_left_out(self):
        # 주소만 셀 때(롬 없이)는 대화 번호를 모르므로 talked 줄을 쓰지 않는다. 롬에 쓸 때 모르면 멈춘다
        ctx = _ctx()
        blob, at = pt.native(ctx)
        data = bytearray(0x400000)
        o = pt.ch1.lorom(ctx.code_at)
        data[o:o + len(blob)] = blob
        n = sum(len(r) for r in pt.table(bytes(data), at['maps']).values())
        self.assertEqual(n, sum(1 for ln in pt.LINES if not ln.talked))
        saved, pt._TALKS = pt._TALKS, None
        ctx.original = b''
        try:
            with self.assertRaises(SystemExit):
                pt.native(ctx)
        finally:
            pt._TALKS, ctx.original = saved, None

    def test_record_with_talked_condition(self):
        line = pt.Line('3D/04', pt.ALENA, 'x', priority=2, talked=('mdout:0336',))
        self.assertEqual(pt.record(line, 0x0EF7, 0xA123),
                         bytes((10, 2, pt.ALENA, 0, 0xF7, 0x0E, 1, pt.TALKED, 0x23, 0xA1)))

    def test_talk_numbers_by_cell_and_time(self):
        row = {'status': pt.SURE, 'map': '3D/04', 'cell': (54, 41), 'time': 'day'}
        saved, pt.PEOPLE = pt.PEOPLE, {('mdout', '0336'): [row]}
        try:
            e = lambda x, y, t, time='day': {'time': time, 'fields': {'x': x, 'y': y, 'talk': t}}  # noqa: E731
            base = {'3D/04': {'entries': [e(54, 41, 0x9DD), e(54, 41, 0x9F0, 'night'), e(40, 27, 0x9DB),
                                          e(54, 41, 0x006)]}}
            later = {'ch2_frenol_x': {'entries': [e(54, 41, 0xA01)]}, 'ch2_other': {'entries': [e(54, 41, 0xA02)]}}
            over = [{'map': '3D/04', 'list': 'new:ch2_frenol_x'}, {'map': '3D/05', 'list': 'new:ch2_other'}]
            got = pt.talk_numbers(base, later, over)
        finally:
            pt.PEOPLE = saved
        # 밤 인물·다른 칸·다른 맵 목록·가게 번호(SCRIPT_TALK 아래)는 들지 않는다
        self.assertEqual(got, {'mdout:0336': frozenset({0x9DD, 0xA01})})

    def test_talk_tables_skip_empty_sets_and_cap(self):
        tokens = sorted({k for ln in pt.LINES for k in ln.talked})
        ids, groups = pt.talk_tables({tokens[0]: frozenset({0x950, 0x951})})
        self.assertEqual(ids, [0x950, 0x951])
        self.assertTrue(groups)
        self.assertTrue(all(v == [1, 2] for v in groups.values()))
        with self.assertRaises(SystemExit):
            pt.talk_tables({tokens[0]: frozenset(range(0x900, 0x900 + pt.MAX_IDS + 1))})

    def test_talked_hook_keeps_the_two_instructions(self):
        ctx = _ctx()
        blob, at = pt.native(ctx)
        start = at['talked'] - ctx.code_at
        self.assertEqual(blob[start], 0x08)            # PHP
        self.assertEqual(blob[start + pt.IDS_OPERAND], 0xBF)
        end = blob.index(bytes((0x28,)) + pt.TALK_HOOK_ORIG + bytes((0x6B,)), start)
        self.assertLess(end - start, 80)
        # 7E:21FD 에 쓴다(예약된 P 바이트)
        self.assertIn(bytes((0x8F, 0x90 + pt.TALKED_TO[0], 0x21, 0x7E)), blob[start:end])
        self.assertIn(pt.TALKED_TO[0], SLOTS['P'].byte_flags)

    def test_hook_goes_through_a_bank_05_stub(self):
        ctx = _ctx()
        [(stub_at, stub_orig, stub), (addr, orig, new), (talk_at, talk_orig, talk_new)] = pt.hooks(ctx)
        self.assertEqual((talk_at, talk_orig), (pt.TALK_HOOK_AT, pt.TALK_HOOK_ORIG))
        talked = ctx.at['talked']
        self.assertEqual(talk_new, bytes((0x22, talked & 0xFF, talked >> 8 & 0xFF, talked >> 16, 0xEA, 0xEA, 0xEA)))
        self.assertEqual((addr, orig), (0x05D5B9, bytes.fromhex('009500' '009829')))
        self.assertEqual(new, bytes((0x20, 0xE8, 0xFE, 0xEA, 0xEA, 0xEA)))
        # 05:D5BF(기다림)는 05:D817 도 JSR 로 부르므로 훅이 닿지 않아야 한다
        self.assertLessEqual(addr + len(new), 0x05D5BF)
        talk = ctx.at['talk']
        self.assertEqual((stub_at, stub_orig), (0x05FEE8, bytes(8)))
        self.assertEqual(stub, bytes((0x00, 0x95, 0x00, 0x22, talk & 0xFF, talk >> 8 & 0xFF, talk >> 16, 0x60)))
        rom = ROOT / 'rom' / 'dq5.sfc'
        if rom.exists():
            data = rom.read_bytes()
            for at, want in ((addr, orig), (stub_at, stub_orig), (talk_at, talk_orig)):
                o = pt.ch1.lorom(at)
                self.assertEqual(data[o:o + len(want)], want)

    def test_no_brk_in_the_high_bank_code(self):
        # BRK 처리기는 DB 를 BRK 가 놓인 뱅크로 둔다. 뱅크 5C 에는 낮은 WRAM 거울이 없다
        blob, _ = pt.native(_ctx())
        self.assertNotIn(bytes((0x00, 0x09, 0x0A)), blob)
        self.assertNotIn(bytes((0x00, 0x95, 0x00)), blob)


class PartyTalkTextTest(unittest.TestCase):
    """대사는 모두 한글이고(가나·한자·빈 칸 없음) 메시지 폰트에 있는 글자이며, 쪽마다 4줄에 든다(줄 폭은 dq4wrap 이 막음)."""

    def test_no_kana_or_kanji_left(self):
        for m, (speaker, text) in {int(r['message']): (r['speaker'], r['text']) for r in pt._rows(pt.TEXT_TSV)}.items():
            self.assertTrue(text.strip(), m)
            self.assertFalse([c for c in text if '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff'
                              or c in '「」～ー\u3000'], m)
            self.assertIn(speaker, {name for _, name in pt.SPEAKERS.values()}, m)

    def test_every_glyph_is_in_the_message_font_and_pages_fit(self):
        known = set(mm.CHARS) | {' '}
        for name, parts in pt.MESSAGES.items():
            lines = 1
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, name)
                elif p == pt.ch1.LINE:
                    lines += 1
                elif p in (pt.ch1.PAGE, pt.ch1.END):
                    self.assertLessEqual(lines, pt.ch1.PAGE_LINES, name)
                    lines = 1
            self.assertEqual(parts[-1], pt.ch1.END, name)
            self.assertEqual(parts.count(pt.ch1.END), 1, name)

    def test_every_line_message_has_a_text(self):
        texts = {int(r['message']) for r in pt._rows(pt.TEXT_TSV)}
        used = {int(m) for r in pt._rows(pt.LINES_TSV) for m in r['messages'].split(',')}
        self.assertEqual(used, texts)

    def test_speaker_says_the_first_page(self):
        texts = {int(r['message']): r['speaker'] for r in pt._rows(pt.TEXT_TSV)}
        for r in pt._rows(pt.LINES_TSV):
            first = int(r['messages'].split(',')[0])
            self.assertEqual(pt.SPEAKERS[r['speaker']][1], texts[first], r['nds'])


class PartyTalkRangeTest(unittest.TestCase):
    def test_lines_use_known_maps_and_flags(self):
        maps = {s[0] for s in check.SPOTS}
        for ln in pt.LINES:
            self.assertIn(ln.map, maps, ln.nds)
            self.assertIn(pt.ch2.CHAPTER2, ln.on, ln.nds)
            self.assertFalse(set(ln.on) & set(ln.off), ln.nds)

    def test_every_line_map_has_a_check_spot(self):
        self.assertEqual({ln.map for ln in pt.LINES}, {s[0] for s in check.SPOTS})

    def test_stages_add_one_flag_each(self):
        prev = {'CHAPTER2'}
        for name, flags in pt.STAGES:
            self.assertEqual(len(flags - prev), 1, name)
            self.assertLessEqual(prev, flags)
            prev = flags
        self.assertEqual(prev, set(pt.CONDITIONS))
        self.assertEqual([n for n in nds.ORDER if n != 'CHAPTER2'], [next(iter(f - p)) for (_, f), (_, p) in
                                                                      zip(pt.STAGES, [('', {'CHAPTER2'})] + pt.STAGES)])

    def test_every_stage_shows_a_line_somewhere(self):
        for name, flags in pt.STAGES:
            ok = [ln for ln in pt.LINES if all(f in [pt.CONDITIONS[n] for n in flags] for f in ln.on)
                  and not any(f in [pt.CONDITIONS[n] for n in flags] for f in ln.off)]
            self.assertTrue(ok, name)

    def test_check_expected_follows_priority_then_order(self):
        rows = [(3, pt.KIRYL, 2, 0x100, [(pt.ON, *pt.CONDITIONS['WON'])]),
                (3, pt.BREY, 0, 0x101, [(pt.ON, *pt.CONDITIONS['WON'])]),
                (5, pt.BREY, 0, 0x102, [(pt.ON, *pt.CONDITIONS['CHAPTER2'])])]
        won = pt.STAGES[2][1]
        self.assertEqual(check.expected(rows, won, True), 0x100)
        self.assertEqual(check.expected(rows, won, False), 0x101)
        self.assertEqual(check.expected(rows, pt.STAGES[0][1], False), 0x102)
        self.assertEqual(check.expected(rows[:2], pt.STAGES[0][1], False), pt.NOBODY)

    def test_stage_bytes_keep_other_bits(self):
        out = check.stage_bytes({'CHAPTER2', 'WON'})
        i, mask = pt.ch2.CHAPTER2
        self.assertEqual(out[0x2190 + i], (mask, out[0x2190 + i][1]))
        self.assertTrue(all(v & ~k == 0 for v, k in out.values()))


class NdsRangeTest(unittest.TestCase):
    """NDS 레코드를 SFC 줄로 옮기는 규칙(dq4ch2partytalknds.convert). NDS 롬 없이 레코드 꼴만 만든다."""

    def _rec(self, **kw):
        f = {'k': 1, 'mapname': 'mcout1', 'place': (0xFF, 0xFF), 'v0': 0, 'codes': (0, 0, 0), 'vals': (0, 0, 0),
             'count': 1, 'msg': 503000, 'story': (87, 104), 'speaker': 'クリフト', 'slots': [], 'prio': 4, 'time': 4}
        f.update(kw)
        return f

    MSGS = {503000: '@a@bクリフト「…', 503001: '@a@bブライ「…'}

    def test_story_flags_become_sfc_flags(self):
        line, why = nds.convert(self._rec(), self.MSGS)
        self.assertIsNone(why)
        self.assertEqual((line['map'], line['on'], line['off'], line['time']),
                         ('3D/03', ['CHAPTER2', 'WON'], ['MESSENGER'], 'night'))

    def test_endor_king_talk_is_before_the_win(self):
        line, _ = nds.convert(self._rec(story=(101, 104), codes=(1, 0, 0), vals=(102, 0, 0)), self.MSGS)
        self.assertEqual((line['on'], line['off']), (['CHAPTER2', 'CURED'], ['CHAMPION', 'MESSENGER']))

    def test_unreachable_range_is_dropped(self):
        line, why = nds.convert(self._rec(story=(97, 98)), self.MSGS)
        self.assertIsNone(line)
        self.assertIn('SFC 에 없는 진행', why)

    def test_people_and_events_are_dropped(self):
        self.assertIn('마을 사람', nds.convert(self._rec(place=(3, 0xFF)), self.MSGS)[1])
        self.assertIn('사건', nds.convert(self._rec(v0=2064), self.MSGS)[1])

    PEOPLE = {('mcout1', '0281'): [{'status': nds.SURE}], ('mcout1', '0282'): [{'status': nds.UNSURE}]}
    OBJECTS = {('mcout1', 2): {'0281'}, ('mcout1', 3): {'0282'}}

    def test_talked_person_is_object_plus_one_and_must_be_paired(self):
        # 직전 대화 값 v 는 오브젝트 v + 1. 짝이 확인된 인물만 조건이 된다
        line, why = nds.convert(self._rec(place=(1, 2)), self.MSGS, self.PEOPLE, self.OBJECTS)
        self.assertIsNone(why)
        self.assertEqual(line['talked'], ['mcout1:0281'])
        line, why = nds.convert(self._rec(place=(2, 0xFF)), self.MSGS, self.PEOPLE, self.OBJECTS)
        self.assertIsNone(line)
        self.assertIn('짝 미확인', why)

    def test_recent_event_is_its_speakers_talk(self):
        heard = {2064: {('mcout1', 2)}}
        line, why = nds.convert(self._rec(v0=2064), self.MSGS, self.PEOPLE, self.OBJECTS, heard)
        self.assertEqual(line['talked'], ['mcout1:0281'])
        self.assertIn('사건', nds.convert(self._rec(v0=2065), self.MSGS, self.PEOPLE, self.OBJECTS, heard)[1])

    def test_unknown_story_flag_is_dropped(self):
        line, why = nds.convert(self._rec(story=(95, 101), codes=(1, 0, 0), vals=(96, 0, 0)), self.MSGS)
        self.assertIsNone(line)
        self.assertIn('짝이 없는', why)
        self.assertIn('임시', nds.convert(self._rec(codes=(3, 0, 0), vals=(5, 0, 0)), self.MSGS)[1])

    def test_co_speaker_must_walk(self):
        line, _ = nds.convert(self._rec(count=14202), self.MSGS)
        self.assertEqual((line['speakers'], line['with']), (['KIRYL', 'BREY'], ['BREY']))


class PeopleTableTest(unittest.TestCase):
    """짝 표(dq4ch2partytalk-people.tsv)와 줄 표가 서로 맞는지."""

    def test_every_talked_token_is_a_sure_pair_in_its_line_map(self):
        for ln in pt.LINES:
            for token in ln.talked:
                mp, who = token.split(':')
                rows = [r for r in pt.PEOPLE[mp, who] if r['status'] == pt.SURE]
                self.assertTrue(rows, token)
                self.assertTrue(all(r['map'] == ln.map for r in rows), (token, ln.nds))

    def test_sure_rows_have_a_cell_and_time(self):
        for (mp, who), rows in pt.PEOPLE.items():
            for r in rows:
                if r['status'] == pt.SURE:
                    self.assertEqual(len(r['cell']), 2, (mp, who))
                    self.assertIn(r['time'], ('day', 'night'), (mp, who))
                    self.assertIn(r['map'], {s[0] for s in check.SPOTS}, (mp, who))

    def test_sure_word_is_shared(self):
        self.assertEqual(pt.SURE, nds.SURE)

    def test_kana_similarity(self):
        self.assertEqual(nds.kana('@a0190  老人@b＊「もし　姫さまが　旅に出た@c2@'), 'もしさまがにた')
        self.assertEqual(nds.similarity('ここはさんとはいむ', 'ここはさんとはいむのおしろ'), 1.0)
        self.assertEqual(nds.similarity('すやすや', 'わんわん'), 0.0)


if __name__ == '__main__':
    unittest.main()
