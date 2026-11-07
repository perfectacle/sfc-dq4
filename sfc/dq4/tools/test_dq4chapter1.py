import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import dq4chapter1 as ch
import dq4menumsg as mm


class MessageTests(unittest.TestCase):
    def test_every_glyph_is_in_the_message_font(self):
        known = set(mm.CHARS) | {' '}
        for m, parts in ch.TEXTS.items():
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, f'{m:03X}')

    def test_lines_and_pages_fit_the_window(self):
        # 줄 너비는 dq4wrap 이 막는다. 여기서는 쪽마다 4줄을 넘지 않는지 본다.
        for m, parts in ch.TEXTS.items():
            lines = 1
            for p in parts:
                if p == ch.LINE:
                    lines += 1
                elif p in (ch.PAGE, ch.END):
                    self.assertLessEqual(lines, ch.PAGE_LINES, f'{m:03X}')
                    lines = 1

    def test_messages_do_not_touch_menu_messages(self):
        self.assertFalse(set(ch.TEXTS) & set(mm.TEXTS))
        # DQ5 메시지(000~C7F)를 덮지 않고 그 뒤에 이어 쓴다
        self.assertEqual(min(ch.TEXTS), mm.MESSAGES)

    def test_talk_numbers_show_their_message(self):
        # 대화 번호 26D~8FF 는 스크립트 없이 메시지 T + 3C6(900~ 는 덧붙인 대화 스크립트)
        for t in range(ch.TALK_BASE, ch.TALK_BASE + len(ch._talks)):
            self.assertLess(t, 0x900)
            self.assertIn(t + 0x3C6, ch.TEXTS)

    def test_name_is_spliced_as_a_code(self):
        self.assertEqual(ch._codes('@ 공.'), [ch.HERO, ' 공.'])
        self.assertEqual(ch._codes('하자고, @.'), ['하자고, ', ch.HERO, '.'])
        self.assertEqual(ch._codes('걸까요……'), ['걸까요', ch.DOTS, ch.DOTS])

    def test_narration_repeats_code_after_each_page(self):
        parts = ch.TEXTS[ch.MSG_NARRATION]
        self.assertEqual(parts[0], ch.NARR)
        for i, p in enumerate(parts):
            if p == ch.PAGE:
                self.assertEqual(parts[i + 1], ch.NARR)

    def test_too_long_line_is_refused(self):
        with self.assertRaises(ValueError):
            ch.say('가' * (ch.LINE_COLS + 1))


class LayoutTests(unittest.TestCase):
    def test_scripts_fit_a_length_byte(self):
        doc = ch.npc_doc({'overrides': []})
        for s in doc['scripts']:
            size = sum(1 + len(c['args']) for c in s['commands'])
            self.assertLess(size, 256, s['address'])

    def test_lineup_walks_out_in_two_lanes(self):
        self.assertEqual(ch.EXIT_LEFT[-1], (0x0F, 0x23))
        self.assertEqual(ch.EXIT_RIGHT[-1], (0x10, 0x23))

    def test_guards_stand_off_the_exit_lanes(self):
        # 인물끼리는 가로 2칸(FC 1블록) 안으로 다가가지 못해, 문지기 줄을 지나는 줄과 한 블록 떨어져야 한다
        guards = [x for x, y, g, _, _ in ch.STAFF if g == ch.GUARD and y == 0x1F and 0x0D <= x <= 0x12]
        lanes = {ch.EXIT_LEFT[-1][0], ch.EXIT_RIGHT[-1][0]}
        self.assertEqual(len(guards), 2)
        for gx in guards:
            self.assertTrue(all(gx != x for x in lanes))

    def test_king_calls_box_then_reveal(self):
        import dq4chapterbox
        doc = ch.npc_doc({'overrides': []})
        ops = [(c['op'], c['args']) for c in doc['scripts'][0]['commands']]
        calls = [a for op, a in ops if op == '37']
        want = dq4chapterbox.entry_points(ch.scenes(False))
        self.assertEqual(calls, [[v & 0xFF, v >> 8 & 0xFF, v >> 16] for v in (want['box'], want['reveal'])])
        self.assertLess(ops.index(('37', calls[0])), ops.index(('21', [ch.MSG_NARRATION & 0xFF, ch.MSG_NARRATION >> 8])))

    def test_king_leaves_the_stair_after_the_speech(self):
        # (10,0D) 는 2층 36/02 로 오르는 계단 칸이라, 연출 뒤 목록의 왕이 거기 서면 계단이 막힌다
        doc = ch.npc_doc({'overrides': []})
        after = next(n['entries'] for n in doc['new_lists'] if n['name'] == 'after')
        spots = {(e['fields']['x'], e['fields']['y']) for e in after}
        self.assertNotIn((ch.KING_AT[0] * 2, ch.KING_AT[1] * 2), spots)
        self.assertIn((ch.KING_DOWN[0] * 2, ch.KING_DOWN[1] * 2), spots)

    def test_night_bed_guards_lie_like_the_ported_sleepers(self):
        # FC 침대 (01,1C)·(01,1F) 의 병사는 누워 있다. 옮긴 FC 누운 인물과 같은 견본·반 블록 오른쪽 자리·오른쪽 방향
        import dq4npcport
        doc = ch.npc_doc({'overrides': []})
        after = next(n['entries'] for n in doc['new_lists'] if n['name'] == 'after')
        beds = [e for e in after if e['from'] == dq4npcport.LIE]
        self.assertEqual([(e['time'], e['fields']['x'], e['fields']['y'], e['fields']['facing']) for e in beds],
                         [('night', 3, 56, 'right'), ('night', 3, 62, 'right')])
        standing = {(e['fields']['x'], e['fields']['y']) for e in after if e['from'] != dq4npcport.LIE}
        self.assertFalse(standing & {(2, 56), (2, 62)})

    def test_rom_title_fills_the_header_field(self):
        self.assertEqual(len(ch.TITLE), 21)
        self.assertEqual(len(ch.TITLE_ORIG), 21)
        self.assertTrue(ch.TITLE.startswith(b'DRAGONQUEST4 '))

    def test_override_comes_first(self):
        doc = ch.npc_doc({'overrides': [{'map': '01/00', 'flag': 0, 'when': 'on', 'mask': 128, 'list': '10:8674'}]})
        self.assertEqual(doc['overrides'][0]['map'], ch.THRONE)
        self.assertEqual(doc['overrides'][0]['list'], 'new:after')


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless((ROOT / 'rom' / 'dq5.sfc').is_file() and (ROOT / 'rom' / 'dq4.nes').is_file(),
                     'local source ROMs not present')
class GroupBuildTests(unittest.TestCase):
    def test_group_build_at_integrated_places_does_not_overlap(self):
        # dq5build inside dq4groupbuild.build refuses overlapping writes (new-map records, field map, prologue room).
        import dq4groupbuild
        saved = (dq4groupbuild.RECORDS_AT, dq4groupbuild.FIELD_AT, dq4groupbuild.NPC_AT, dq4groupbuild.TEXT_AT,
                 dq4groupbuild.TALK_AT)
        try:
            with tempfile.TemporaryDirectory() as out:
                summary = ch.group_build(ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes', Path(out))
                writes = json.loads((Path(out) / 'field.dq5patch.json').read_text(encoding='utf-8'))['writes']
        finally:
            (dq4groupbuild.RECORDS_AT, dq4groupbuild.FIELD_AT, dq4groupbuild.NPC_AT, dq4groupbuild.TEXT_AT,
             dq4groupbuild.TALK_AT) = saved
        self.assertTrue(summary['rom'])
        talk = int(ch.TALK_AT[1].replace(':', ''), 16)
        import dq4fieldport
        planes = int(dq4fieldport.GFX_AT['planes'][:2], 16)
        for w in writes:
            at = int(w['at'].replace(':', ''), 16)
            if at >> 16 >= 0x40:
                # The block number planes, outside the 30-3F the field loader's DB needs: the hook bank and one
                # bank per world.
                self.assertIn(at >> 16, range(planes, planes + 1 + len(dq4fieldport.WORLDS)))
            elif at >> 16 >= 0x30:
                self.assertEqual(at >> 16, 0x34)
                self.assertLessEqual(at + len(bytes.fromhex(w['hex'])), 0x350000)
                self.assertNotEqual(at >> 16, talk >> 16)



def patch_file(folder, name, writes):
    path = Path(folder) / name
    path.write_text(json.dumps({'format': 'dq5patch/1', 'name': name, 'writes': writes}), encoding='utf-8')
    return path


class ClearMirrorTests(unittest.TestCase):
    def test_zeroes_mirror_bytes_and_empty_bytes_in_the_ranges_only(self):
        original = bytes(range(1, 256)) * 3000
        data = bytearray(len(original))
        lo = 0x90000
        data[lo], data[lo + 1], data[lo + 2] = original[lo - 0x80000], 0, original[lo + 2 - 0x80000]
        data[lo + 10] = original[lo + 10 - 0x80000]
        data[lo + 100] = original[lo + 100 - 0x80000]
        out = ch.clear_mirror(bytes(data), original, [(lo, lo + 50)])
        self.assertEqual(out[lo:lo + 3], bytes(3))
        self.assertEqual(out[lo + 10], 0)
        self.assertEqual(out[lo + 100], original[lo + 100 - 0x80000])
        self.assertEqual(data[lo], original[lo - 0x80000])

    def test_other_data_in_a_range_stops_the_build(self):
        original = bytes(range(1, 256)) * 3000
        data = bytearray(len(original))
        data[0x90005] = original[0x90005 - 0x80000] ^ 0xFF
        with self.assertRaisesRegex(SystemExit, '그룹 빌드 자리에 다른 자료'):
            ch.clear_mirror(bytes(data), original, [(0x90000, 0x90010)])

    def test_group_ranges_cover_group_banks_npc_bank_and_loose_record_areas(self):
        ranges = ch.group_ranges()
        for bank in (*ch.GROUP_BANKS, ch.NPC_BANK, ch.TALK_BANK, 0x37):
            self.assertIn((bank * 0x8000, (bank + 1) * 0x8000), ranges)
        # 3A 안의 레코드 자리는 뱅크 전체에 이미 들어 있어 다시 더하지 않는다
        loose = [(lo, hi) for lo, hi in ch.RECORDS_AT if lo >> 16 not in ch.GROUP_BANKS]
        self.assertEqual(len(ranges), len(ch.GROUP_BANKS) + 3 + len(loose))
        self.assertIn((ch.lorom(0x309000), ch.lorom(0x309FFF) + 1), ranges)
        self.assertEqual(len(ch.RECORDS_AT) - len(loose), 1)

    def test_talk_and_second_alt_bank_are_not_record_areas(self):
        # 덧붙인 대화 스크립트와 넘친 대체 목록이 쓰는 뱅크에 새 맵 레코드가 들어오면 서로 덮는다
        banks = {b for lo, hi in ch.RECORDS_AT for b in range(lo >> 16, ((hi - 1) >> 16) + 1)}
        self.assertNotIn(ch.TALK_BANK, banks)
        self.assertFalse(banks & set(ch.NPC_ALT_BANKS))
        self.assertEqual(ch.NPC_ALT, ','.join(f'{b:02X}:8000' for b in ch.NPC_ALT_BANKS))


class ApplyWritesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original = bytes(range(1, 256)) * 8200
        self.data = bytes(len(self.original))

    def apply(self, writes, data=None):
        path = patch_file(self.tmp.name, 'p.dq5patch.json', writes)
        return ch.apply_writes(self.data if data is None else data, self.original, [path])

    def test_writes_land_at_the_lorom_position(self):
        out = self.apply([{'at': '30:8010', 'hex': 'AA BB'}])
        self.assertEqual(out[0x180010:0x180012], b'\xaa\xbb')
        self.assertEqual(sum(1 for a, b in zip(out, self.data) if a != b), 2)

    def test_original_bytes_are_checked_when_given(self):
        data = bytearray(self.data)
        data[0x180000:0x180002] = b'\x01\x02'
        out = self.apply([{'at': '30:8000', 'hex': '09 09', 'orig': '01 02'}], bytes(data))
        self.assertEqual(out[0x180000:0x180002], b'\x09\x09')
        with self.assertRaisesRegex(SystemExit, '원래 바이트가 아님 0000'):
            self.apply([{'at': '30:8000', 'hex': '09 09', 'orig': '01 02'}])

    def test_without_orig_only_empty_same_or_mirror_bytes_may_be_overwritten(self):
        data = bytearray(self.data)
        data[0x180000] = 0x77                                # 같은 값
        data[0x180001] = self.original[0x180001 - 0x80000]  # 30~3F 의 거울
        data[0x180002] = 0x55                                # 다른 자료
        out = self.apply([{'at': '30:8000', 'hex': '77 AA'}], bytes(data))
        self.assertEqual(out[0x180000:0x180002], b'\x77\xaa')
        with self.assertRaisesRegex(SystemExit, '비어 있지 않은 자리 0x180002'):
            self.apply([{'at': '30:8002', 'hex': '66'}], bytes(data))

    def test_mirror_rule_does_not_apply_outside_banks_30_to_3f(self):
        data = bytearray(self.data)
        data[0x20000] = 0x55
        with self.assertRaisesRegex(SystemExit, '비어 있지 않은 자리 0x20000'):
            self.apply([{'at': '04:8000', 'hex': '66'}], bytes(data))


class NpcBaseTests(unittest.TestCase):
    def test_base_follows_the_environment_records_in_the_npc_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            end = ch.NPC_BANK * 0x8000 + 0x1234
            path = patch_file(tmp, 'env.dq5patch.json', [
                {'at': f'0x{end - 4:X}', 'hex': '01 02 03 04'}, {'at': '30:8000', 'hex': '01'}])
            # 뱅크 시작 + 0x1234 에서 끝나는 쓰기 뒤의 다음 0x100 경계(0x1300)
            self.assertEqual(ch.npc_base(path), '35:9300')

    def test_base_starts_at_the_bank_start_without_writes_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = patch_file(tmp, 'env.dq5patch.json', [{'at': '30:8000', 'hex': '01'}])
            self.assertEqual(ch.npc_base(path), '35:8000')


class ReturnPlacesTests(unittest.TestCase):
    ROWS = [(0x05, 0x01), (0x06, 0x02), (0x36, 0x03)]

    def rom(self, slots_now, slots_before, rows):
        out = bytearray(0x400000)
        original = bytearray(0x400000)
        o = ch.lorom(ch.SLOT_TABLE)
        out[o:o + ch.SLOT_COUNT], original[o:o + ch.SLOT_COUNT] = bytes(slots_now), bytes(slots_before)
        o = ch.lorom(ch.START_TABLE)
        for i, (group, number) in enumerate(rows):
            out[o + 6 * i:o + 6 * i + 6] = bytes((group, number, 1, 1, 1, 0x80))
        out[o + 6 * len(rows)] = 0xFF
        return out, bytes(original)

    def run_places(self, out, original, place, extra=()):
        import dq4fieldtravel
        import dq4groupbuild
        prg = bytearray(0x1E * 0x4000 + 0x4000)
        a = ch.FC_PLACES[1] - 0x8000 + ch.FC_PLACES[0] * 0x4000
        prg[a:a + 4] = bytes((1, 2, 3, 4))
        with unittest.mock.patch('kr_patch.fc.ines.prg', lambda raw: bytes(prg)), \
                unittest.mock.patch.object(dq4groupbuild, 'placement', lambda prg: place), \
                unittest.mock.patch.object(dq4groupbuild, 'cell', lambda x, y: (2 * x + 1, 2 * y + 1)), \
                unittest.mock.patch.object(dq4fieldtravel, 'extras', lambda prg, links, place: list(extra)):
            return ch.return_places(out, original, b'dq4')

    def test_a_new_group_takes_a_free_row_with_its_first_fc_return_place(self):
        out, original = self.rom([0x36] * 11 + [0x37] * 11, [0x05] * 11 + [0x06] * 11, self.ROWS)
        result = self.run_places(out, original, {(1, 2): (0x37, 9)})
        o = ch.lorom(ch.START_TABLE)
        # 칸 표에서 빠진 DQ5 그룹(05·06)의 첫 항목이 새 그룹 37 의 [맵 9][X 7][Y 9][층 1][80] 로
        self.assertEqual(bytes(result[o:o + 6]), bytes((0x37, 9, 7, 9, 1, 0x80)))
        self.assertEqual(bytes(result[o + 6:o + 12]), bytes((0x06, 2, 1, 1, 1, 0x80)))
        self.assertEqual(bytes(result[o + 12:o + 18]), bytes((0x36, 3, 1, 1, 1, 0x80)))

    def test_groups_already_in_the_table_or_without_a_place_are_left_alone(self):
        out, original = self.rom([0x36] * 11 + [0x37] * 11, [0x05] * 11 + [0x06] * 11, self.ROWS)
        before = bytes(out)
        self.assertEqual(bytes(self.run_places(out, original, {(9, 9): (0x37, 9)})), before)

    def test_an_extra_slot_church_takes_its_own_row_after_the_group_rows(self):
        # 그룹 37 의 첫 항목과 같은 그룹의 둘째 교회(맵 4)는 따로 줄을 받고, 이미 있는 줄은 다시 넣지 않는다
        rows = [(0x05, 0x01), (0x06, 0x02), (0x36, 0x03)]
        out, original = self.rom([0x36] * 11 + [0x37] * 11, [0x05] * 11 + [0x06] * 11, rows)
        extra = [{'group': 0x37, 'restart': (4, (24, 51))}, {'group': 0x36, 'restart': (3, (1, 1))},
                 {'group': 0x37, 'restart': None}]
        result = self.run_places(out, original, {(1, 2): (0x37, 9)}, extra)
        o = ch.lorom(ch.START_TABLE)
        self.assertEqual(bytes(result[o:o + 6]), bytes((0x37, 9, 7, 9, 1, 0x80)))
        self.assertEqual(bytes(result[o + 6:o + 12]), bytes((0x37, 4, 24, 51, 1, 0x80)))
        self.assertEqual(bytes(result[o + 12:o + 18]), bytes((0x36, 3, 1, 1, 1, 0x80)))

    def test_no_free_row_stops_the_build(self):
        out, original = self.rom([0x36] * 11 + [0x37] * 11, [0x05] * 11 + [0x06] * 11, [(0x36, 3)])
        with self.assertRaisesRegex(SystemExit, '빈 항목이 모자람: 1 > 0'):
            self.run_places(out, original, {(1, 2): (0x37, 9)})


class MessageAssemblyTests(unittest.TestCase):
    def test_ported_and_chapter_texts_are_merged_without_gaps(self):
        import dq4npcport
        ported = [{'id': dq4npcport.FIRST_MESSAGE, 'codes': [1, 2]},
                  {'id': dq4npcport.FIRST_MESSAGE + 1, 'codes': [3]}]
        found = ch.messages(ported, {})
        self.assertTrue(set(ch.TEXTS) <= set(found))
        self.assertIn(dq4npcport.FIRST_MESSAGE, found)
        self.assertIn(dq4npcport.FIRST_MESSAGE + 1, found)

    def test_a_person_is_given_the_korean_text_of_the_matching_fc_messages(self):
        import dq4ch1talk
        key = next(iter(dq4ch1talk.TEXTS))
        report = {'36/00': [{'shows': list(key) + [None], 'message': '3C6'}],
                  ch.THRONE: [{'shows': list(key), 'message': '3C7'}]}
        found = ch.messages([], report)
        strings = lambda parts: [p for p in parts if isinstance(p, str)]  # noqa: E731
        self.assertEqual(strings(found[0x3C6]), strings(dq4ch1talk.TEXTS[key]))
        self.assertNotEqual(strings(found.get(0x3C7, [])), strings(dq4ch1talk.TEXTS[key]))

    def test_a_ported_message_on_a_chapter_number_is_refused(self):
        clash = next(iter(ch.TEXTS))
        with self.assertRaisesRegex(ValueError, '1장 메시지와 겹치는 번호'):
            ch.messages([{'id': clash, 'codes': [1]}], {})

    def test_messages_doc_lists_hex_numbers_in_order(self):
        with unittest.mock.patch.object(ch, 'port', lambda dq5, dq4: (None, [], {})), \
                unittest.mock.patch.object(ch, 'messages', lambda ported, report: {0x10: ['b'], 0x9: ['a']}):
            self.assertEqual(ch.messages_doc('a', 'b'), {'format': 'dq4messages/1',
                                                         'messages': {'009': ['a'], '010': ['b']}})

    def test_talk_and_message_numbers_chain_chapter_after_chapter(self):
        import dq4ch1event
        import dq4npcport
        self.assertEqual(ch.chapter2_talk() - ch.event_talk(), len(dq4ch1event.TALKS))
        self.assertGreater(ch.event_talk(), dq4npcport.SCRIPT_TALK)
        self.assertEqual(ch.chapter2_message(100) - 100, len(dq4ch1event.MESSAGES))

    def test_message_flow_gathers_talks_scripts_events_and_pauses(self):
        flow = ch.message_flow(3300)
        self.assertEqual(sorted(flow), ['events', 'pauses', 'scripts', 'talks'])
        self.assertEqual(len(flow['scripts']), len(ch.npc_scripts(3300)))
        import dq4ch2event
        # 서장 끝·합류·바구니 셋 뒤에 등록한 2장 사건 모듈(EVENTS)의 이벤트
        self.assertEqual(len(flow['events']), 3 + len(dq4ch2event.event_tokens(ch.chapter2_message(3300))))
        self.assertEqual(ch.npc_scripts(3300)[0]['address'], '05:A84F')


class NpcDocPrologueTests(unittest.TestCase):
    def test_prologue_adds_its_lists_overrides_and_scripts(self):
        plain = ch.npc_doc({'overrides': []})
        with_prologue = ch.npc_doc({'overrides': []}, prologue=True)
        self.assertEqual([l['name'] for l in plain['new_lists']], ['after'])
        self.assertEqual([l['name'] for l in with_prologue['new_lists']][0], 'after')
        self.assertGreater(len(with_prologue['new_lists']), 1)
        self.assertGreater(len(with_prologue['scripts']), len(plain['scripts']))
        self.assertEqual(plain['overrides'][0]['list'], 'new:after')
        self.assertEqual(with_prologue['overrides'][-1]['list'], 'new:after')
        self.assertGreater(len(with_prologue['lists']), len(plain['lists']))
        self.assertEqual(with_prologue['format'], 'dq5npcrelocate/1')

    def test_scenes_drop_the_prologue_box_when_there_is_no_prologue(self):
        import dq4chapterbox
        self.assertIn(dq4chapterbox.PROLOGUE, ch.scenes(True))
        self.assertNotIn(dq4chapterbox.PROLOGUE, ch.scenes(False))
        self.assertEqual(len(ch.scenes(True)) - len(ch.scenes(False)), 1)


class WrapperTests(unittest.TestCase):
    def test_group_build_moves_the_places_to_the_integrated_rom(self):
        import dq4groupbuild
        seen = {}

        def build(dq5, dq4, out):
            seen.update(dq5=dq5, dq4=dq4, out=out, records=dq4groupbuild.RECORDS_AT, field=dq4groupbuild.FIELD_AT,
                        npc=dq4groupbuild.NPC_AT, text=dq4groupbuild.TEXT_AT, talk=dq4groupbuild.TALK_AT)
            return {'ok': 1}
        with unittest.mock.patch.multiple(dq4groupbuild, build=build, RECORDS_AT=(), FIELD_AT='', NPC_AT=(), TEXT_AT=(),
                                          TALK_AT=()):
            self.assertEqual(ch.group_build('a', 'b', 'c'), {'ok': 1})
        self.assertEqual(seen, {'dq5': 'a', 'dq4': 'b', 'out': 'c', 'records': ch.RECORDS_AT, 'field': ch.FIELD_AT,
                                'npc': ('--base', '33:8000', '--alt', '38:8000'), 'text': ('--at', '60:8000'),
                                'talk': ('--extra-at', '36:8000', '--hook-at', '06:FE10')})

    def test_run_tool_echoes_stderr(self):
        import dq4buildcache
        calls = []
        with unittest.mock.patch.object(dq4buildcache, 'run', lambda *a, **k: calls.append((a, k))):
            ch.run_tool('tool.py', 'x', 'y')
        self.assertEqual(calls, [(('tool.py', 'x', 'y'), {'echo_stderr': True})])

    def test_port_delegates_to_the_npc_port(self):
        import dq4npcport
        with unittest.mock.patch.object(dq4npcport, 'port', lambda a, b: ('ported', a, b)):
            self.assertEqual(ch.port('d5', 'd4'), ('ported', 'd5', 'd4'))


class MainTests(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with unittest.mock.patch('sys.argv', ['dq4chapter1.py', *argv]), contextlib.redirect_stdout(out):
            ch.main()
        return out.getvalue()

    def test_messages_writes_the_json_and_counts_the_messages(self):
        doc = {'format': 'dq4messages/1', 'messages': {'001': [1], '002': [2]}}
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.object(ch, 'messages_doc', lambda a, b: doc):
            target = Path(tmp) / 'sub' / 'm.json'
            text = self.run_main('messages', '-o', str(target))
            self.assertEqual(json.loads(target.read_text()), doc)
        self.assertEqual(text.strip(), f'{target} 메시지 2개')

    def test_build_writes_rom_and_ips_with_the_chosen_options(self):
        calls = []

        def fake_build(rom, dq5, dq4, work, prologue, chapter2):
            calls.append((rom, Path(dq5).name, Path(dq4).name, work.is_dir(), prologue, chapter2))
            return bytes(range(16))
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.object(ch, 'build', fake_build):
            tmp = Path(tmp)
            (tmp / 'menu.sfc').write_bytes(bytes(16))
            out = tmp / 'x' / 'ch1.sfc'
            text = self.run_main('build', '--rom', str(tmp / 'menu.sfc'), '--out', str(out), '--no-prologue',
                                 '--chapter2', '--keep', str(tmp / 'keep'))
            self.assertEqual(out.read_bytes(), bytes(range(16)))
            ips = out.with_suffix('.ips').read_bytes()
            self.assertTrue((tmp / 'keep').is_dir())
            self.run_main('build', '--rom', str(tmp / 'menu.sfc'), '--out', str(out))
        self.assertEqual(calls[0], (bytes(16), 'dq5.sfc', 'dq4.nes', True, False, True))
        self.assertEqual(calls[1][4:], (True, False))
        self.assertTrue(ips.startswith(b'PATCH') and ips.endswith(b'EOF'))
        self.assertEqual(text.strip(), f'{out} sha1={hashlib.sha1(bytes(range(16))).hexdigest()}')


class Chapter1TalkTests(unittest.TestCase):
    def test_talk_texts_fit_and_use_known_glyphs(self):
        import dq4ch1talk
        known = set(mm.CHARS) | {' '}
        for key, parts in dq4ch1talk.TEXTS.items():
            lines = 1
            for p in parts:
                if isinstance(p, str):
                    self.assertLessEqual(set(p), known, key)
                elif p == ch.LINE:
                    lines += 1
                elif p in (ch.PAGE, ch.END):
                    self.assertLessEqual(lines, ch.PAGE_LINES, key)
                    lines = 1
            self.assertEqual(parts[-1], ch.END)
            self.assertEqual(parts.count(ch.END), 1, key)

    def test_talk_keys_do_not_overlap_the_front(self):
        import dq4ch1talk
        self.assertFalse(set(dq4ch1talk.TEXTS) & set(ch.FRONT_TEXTS))


class PrologueEntryTest(unittest.TestCase):
    def test_prologue_calls_the_built_box(self):
        # 서장 스크립트가 부르는 상자 주소가 서장 빌드의 장면 목록과 같아야 한다(2장 상자를 더해 어긋났음)
        import dq4chapterbox
        import dq4prologue
        want = dq4chapterbox.entry_points(ch.scenes(True))
        head = dq4prologue.master_script(dq4chapterbox.entry_points(dq4chapterbox.GAME_SCENES))['commands'][:4]
        calls = [c['args'] for c in head if c.get('op') == '37']
        self.assertIn([want['box0'] & 0xFF, want['box0'] >> 8 & 0xFF, want['box0'] >> 16], calls)


class BuildFlowTests(unittest.TestCase):
    """롬 없이 build 의 순서와 마지막 롬 고치기를 본다. 도구 실행·그룹 빌드·바이트 덮기 단계는 기록하는 가짜로 바꾼다."""

    def run_build(self, prologue=True, rom=None):
        from unittest import mock
        import dq4ch1event
        import dq4ch2event
        import dq4growth
        import dq4josa
        import dq4menupatch
        import dq4party
        import dq4msgnames
        import dq4prologue
        import dq4signs
        calls, order = [], []

        def run_tool(tool, *args):
            calls.append((Path(tool).name, *map(str, args)))
            if Path(tool).name == 'dq5npcrecord.py':
                Path(args[list(args).index('-o') + 1]).write_text('{"records": 1}')

        def group_build(dq5, dq4, out):
            out.mkdir(parents=True)
            (out / 'groups.sfc').write_bytes(b'groups')
            return {'record_patches': ['newmap-1.dq5patch.json']}

        def step(name):
            def apply(out, *args):
                order.append(name)
                return bytes(out)
            return apply

        def apply_writes(data, original, paths):
            self.applied = [Path(p) for p in paths]
            return data

        if rom is None:
            rom = self.menu_rom()
        with tempfile.TemporaryDirectory() as t:
            work, dq5, dq4 = Path(t) / 'work', Path(t) / 'dq5.sfc', Path(t) / 'dq4.nes'
            dq5.write_bytes(b'dq5')
            dq4.write_bytes(b'NES\x1a\x01\x00' + bytes(10) + bytes(0x4000))
            self.verify = mock.Mock()
            self.npc_doc = mock.Mock(return_value={'format': 'dq5npcrelocate/1'})
            with mock.patch.multiple(ch, run_tool=run_tool, group_build=group_build,
                                     port=lambda a, b: (['ported'], ['m1', 'm2'], {'report': 1}),
                                     npc_doc=self.npc_doc, npc_base=lambda p: '35:8100',
                                     clear_mirror=lambda data, original, ranges: data, apply_writes=apply_writes,
                                     return_places=step('return_places'), verify_groups=self.verify,
                                     scenes=lambda p: ['scene']), \
                    mock.patch.object(ch.dq4chapterbox, 'apply', step('chapterbox')), \
                    mock.patch.object(dq4menupatch, 'Font', lambda name: name), \
                    mock.patch.multiple(dq4ch1event, apply=step('ch1event'),
                                        monster_doc=lambda prg: {'format': 'test-monsters', 'prg': len(prg)}), \
                    mock.patch.multiple(dq4ch2event, apply=step('ch2event'), monster_entries=lambda prg: []), \
                    mock.patch.object(dq4growth, 'writes', lambda dq5, dq4: []), \
                    mock.patch.multiple(dq4party, learn_doc=lambda dq5, dq4: {'format': 'dq5learn/1', 'characters': []},
                                        equip_writes=lambda dq5, dq4: [], apply_recruits=step('party')), \
                    mock.patch.object(dq4josa, 'apply', step('josa')), \
                    mock.patch.object(dq4msgnames, 'apply', step('msgnames')), \
                    mock.patch.object(dq4signs, 'apply', step('signs')), \
                    mock.patch.object(dq4prologue, 'apply', step('prologue')):
                out = ch.build(rom, dq5, dq4, work, prologue=prologue)
            self.files = {p.name: json.loads(p.read_text()) for p in work.glob('*.json')}
        return out, calls, order

    @staticmethod
    def menu_rom():
        data = bytearray(0x400000)
        o = ch.lorom(ch.START_TABLE)
        data[o:o + 6] = ch.START_ORIG
        o = ch.lorom(ch.TIME_FREEZE)
        data[o:o + 4] = ch.TIME_FREEZE_ORIG
        data[ch.TITLE_OFFSET:ch.TITLE_OFFSET + 21] = ch.TITLE_ORIG
        return bytes(data)

    def test_patches_go_on_in_the_group_build_order(self):
        self.run_build()
        names = [p.name for p in self.applied]
        # 그룹 빌드가 겹침을 본 차례대로(환경 맵이 맨 앞, 상자가 맨 끝), 그 뒤에 그룹 빌드가 낸 레코드 패치, 인물·보스·학습 패치
        self.assertEqual(names, [
            'dq4-environment.dq5patch.json', 'doors.dq5patch.json', 'outside.dq5patch.json', 'newmap.dq5patch.json',
            'exits.dq5patch.json', 'entrances.dq5patch.json', 'shops.dq5patch.json', 'inn.dq5patch.json',
            'entrance-hook.dq5patch.json', 'field-gfx.dq5patch.json', 'field-blocks.dq5patch.json',
            'field.dq5patch.json', 'talk.dq5patch.json', 'travel.dq5patch.json', 'names.dq5patch.json',
            'companion-names.dq5patch.json', 'person-names.dq5patch.json', 'zones.dq5patch.json',
            'grids.dq5patch.json', 'rates.dq5patch.json', 'sleeper-talk.dq5patch.json', 'chests.dq5patch.json',
            'newmap-1.dq5patch.json', 'npc.dq5patch.json', 'boss.dq5patch.json', 'boss-monsters.dq5patch.json',
            'learn.dq5patch.json', 'growth.dq5patch.json', 'party.dq5patch.json'])
        self.assertEqual(self.applied[0].parent.name, 'env')
        # 그룹 빌드 롬과 견줄 때는 그룹 빌드가 낸 패치만 넘긴다(인물·보스 패치는 그룹 빌드 롬에 없다)
        self.assertEqual([p.name for p in self.verify.call_args.args[2]], names[:names.index('newmap-1.dq5patch.json') + 1])

    def test_side_documents_feed_the_tools_that_write_the_applied_patches(self):
        _, calls, _ = self.run_build(prologue=False)
        boss, learn, monsters, npc = (self.files[n] for n in ('boss.json', 'learn.json', 'boss-monsters.json', 'npc.json'))
        self.assertEqual(boss['format'], 'dq5encounter/1')
        self.assertTrue(boss['event_groups'])
        for g in boss['event_groups']:
            self.assertTrue(0 <= g['index'] <= 0xFF and g['members'])
            self.assertTrue(all(m['count'] >= 1 for m in g['members']))
        self.assertEqual(learn['format'], 'dq5learn/1')
        # 몬스터 문서는 iNES 머리를 뗀 PRG(16KB 한 뱅크) 를 읽는다
        self.assertEqual(monsters, {'format': 'test-monsters', 'prg': 0x4000})
        self.assertEqual(npc, {'format': 'dq5npcrelocate/1'})
        self.assertEqual(self.npc_doc.call_args.args, ({'records': 1}, ['ported'], False, {'report': 1}, ['m1', 'm2'],
                                                      False))
        # 각 문서를 읽는 도구의 출력이 곧 덮어 쓰는 패치다
        outs = {c[0]: (Path(c[c.index('patch') + 1]).name, Path(c[c.index('-o') + 1]).name)
                for c in calls if 'patch' in c}
        self.assertEqual(outs, {'dq5encounterwrite.py': ('boss.json', 'boss.dq5patch.json'),
                                'dq5tables.py': ('boss-monsters.json', 'boss-monsters.dq5patch.json'),
                                'dq5learnwrite.py': ('learn.json', 'learn.dq5patch.json'),
                                'dq5npcrelocate.py': ('npc.json', 'npc.dq5patch.json')})

    def test_npc_patch_uses_the_free_base_and_the_new_maps(self):
        _, calls, _ = self.run_build()
        (npc,) = [c for c in calls if c[0] == 'dq5npcrelocate.py']
        self.assertEqual(npc[npc.index('--base') + 1], '35:8100')
        self.assertEqual(npc[npc.index('--alt') + 1], ch.NPC_ALT)
        self.assertIn('--allow-growth', npc)
        new_maps = [npc[i + 1] for i, a in enumerate(npc) if a == '--new-map']
        self.assertEqual(new_maps, [f'{g:02X}/{n:02X}' for g, n in sorted(ch.GROUPS.values())])
        # 인물 문서는 그룹 빌드와 함께 돈 기록 덤프를 읽는다
        self.assertEqual(self.npc_doc.call_args.args[0], {'records': 1})

    def test_new_game_starts_on_the_chapter_or_the_prologue(self):
        import dq4prologue
        for prologue, start in ((False, ch.START), (True, dq4prologue.START)):
            with self.subTest(prologue=prologue):
                out, _, order = self.run_build(prologue)
                o = ch.lorom(ch.START_TABLE)
                group, number = (int(v, 16) for v in start[0].split('/'))
                self.assertEqual(out[o:o + 6], bytes((group, number, start[1], start[2])) + ch.START_ORIG[4:])
                self.assertEqual('prologue' in order, prologue)
                self.assertEqual(order[-1], 'return_places')

    def test_time_freeze_title_and_checksum(self):
        out, _, order = self.run_build()
        o = ch.lorom(ch.TIME_FREEZE)
        self.assertEqual(out[o:o + 4], b'\xea' * 4)
        self.assertEqual(out[ch.TITLE_OFFSET:ch.TITLE_OFFSET + 21], ch.TITLE)
        checksum = int.from_bytes(out[0x7FDE:0x7FE0], 'little')
        self.assertEqual(checksum ^ int.from_bytes(out[0x7FDC:0x7FDE], 'little'), 0xFFFF)
        self.assertEqual(checksum, sum(out) & 0xFFFF)
        self.assertEqual(order[:7], ['chapterbox', 'ch1event', 'ch2event', 'party', 'josa', 'msgnames', 'signs'])
        # 그룹 빌드 롬과 견주는 것은 체크섬까지 끝낸 롬이다
        self.assertEqual(self.verify.call_args.args[:2], (bytes(out), b'groups'))

    def test_unexpected_bytes_stop_the_build(self):
        for at, size in ((ch.lorom(ch.START_TABLE), 6), (ch.lorom(ch.TIME_FREEZE), 4), (ch.TITLE_OFFSET, 21)):
            with self.subTest(at=hex(at)):
                rom = bytearray(self.menu_rom())
                rom[at + size - 1] ^= 0xFF
                with self.assertRaises(SystemExit):
                    self.run_build(rom=bytes(rom))


if __name__ == '__main__':
    unittest.main()
