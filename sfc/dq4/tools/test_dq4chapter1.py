import json
import tempfile
import unittest
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
        saved = dq4groupbuild.RECORDS_AT, dq4groupbuild.FIELD_AT, dq4groupbuild.NPC_AT, dq4groupbuild.TEXT_AT
        try:
            with tempfile.TemporaryDirectory() as out:
                summary = ch.group_build(ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes', Path(out))
                writes = json.loads((Path(out) / 'field.dq5patch.json').read_text(encoding='utf-8'))['writes']
        finally:
            dq4groupbuild.RECORDS_AT, dq4groupbuild.FIELD_AT, dq4groupbuild.NPC_AT, dq4groupbuild.TEXT_AT = saved
        self.assertTrue(summary['rom'])
        talk = int(dq4groupbuild.TALK_AT[1].replace(':', ''), 16)
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
        import dq4josa
        import dq4menupatch
        import dq4msgnames
        import dq4prologue
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
                    mock.patch.object(dq4ch2event, 'apply', step('ch2event')), \
                    mock.patch.object(dq4josa, 'apply', step('josa')), \
                    mock.patch.object(dq4msgnames, 'apply', step('msgnames')), \
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
            'grids.dq5patch.json', 'rates.dq5patch.json', 'chests.dq5patch.json',
            'newmap-1.dq5patch.json', 'npc.dq5patch.json', 'boss.dq5patch.json', 'boss-monsters.dq5patch.json',
            'learn.dq5patch.json'])
        self.assertEqual(self.applied[0].parent.name, 'env')
        # 그룹 빌드 롬과 견줄 때는 그룹 빌드가 낸 패치만 넘긴다(인물·보스 패치는 그룹 빌드 롬에 없다)
        self.assertEqual([p.name for p in self.verify.call_args.args[2]], names[:22])

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
        self.assertEqual(order[:5], ['chapterbox', 'ch1event', 'ch2event', 'josa', 'msgnames'])
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
