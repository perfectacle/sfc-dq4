"""대사·창 모듈의 창 레코드 읽기, 뜻 표, 기록 파일 비교, 기호 텍스트 내보내기, 명령줄을 합성 롬과 임시 파일로 검사한다."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dq4data
import dq4text as t
from test_dq4text import base_prg, message_rom, pack, put, word

CALLERS_AT = (0x05, 0x9000)
DEFAULT_REC = [0x22, 0x11, 0x00, 0xC6]       # 폭 4 x 4 y 2, 본문 = 항목 0 + 줄바꿈
CUSTOM_REC = {
    1: [0x03, 0x00, 0xD6, 0xE1],             # 자리 루틴 3, 목록 D6, 모드 E1
    2: [0x13],                               # 별칭: 다음 창의 레코드를 쓴다
    4: [0x34, 0x25, 0x40, 0x01, 0x81, 0xA2, 0x02, 0xC6, 0xC0, 0x05, 0xD3, 0xE1],
    5: [0x22, 0x11, 0xA5, 0x00, 0xA9, 0xB0, 0xB5, 0xC1, 0x02, 0xC2, 0xD0, 0xE3],
}
HANDLER_BASE = 0x8100


def ines(prg):
    return b'NES\x1a' + bytes((len(prg) // 0x4000, 0, 0x10, 0)) + bytes(8) + bytes(prg)


def text_prg():
    """메시지 롬 위에 창 표·창 레코드·뜻 표·제어 처리기·이름 표를 얹는다. 레코드 주소는 RECORD_AT 에 남긴다."""
    prg = bytearray(message_rom().prg)
    put(prg, *t.WINDOW_GROUPS, word(0x9000) + word(0x9200))
    put(prg, *t.WINDOW_LIMITS, [2, 0])
    for g, base in ((0, 0x9000), (1, 0x9200)):
        for n in range(t.WINDOW_COUNTS[g] + 1):
            put(prg, 0x16, base + 2 * n, word({0: 0xB000, 1: 0xA700, 2: 0xA703}.get(n, 0xA707) if g == 0 else 0xA707))
    put(prg, 0x16, 0xA700, [0x01, 0x82, 0x02])
    put(prg, 0x16, 0xA703, [0x10, 0x80, 0x11, 0x81])
    addr, at = 0xA800, {}
    for n in range(t.WINDOW_COUNT + 1):
        rec = CUSTOM_REC.get(n, DEFAULT_REC)
        put(prg, 0x16, t.WINDOW_RECORDS[1] + 2 * n, word(addr))
        put(prg, 0x16, addr, rec)
        at[n] = addr
        addr += len(rec)
    put(prg, *t.ROUTINE_TABLES, word(0xAB00) + word(0xAB80))
    put(prg, *t.ROUTINE_LIMITS, [0x20, 0x0E])
    for i in range(0x20):
        put(prg, 0x16, 0xAB00 + 2 * i, word(0x9000 + i))
        put(prg, 0x16, 0xAB80 + 2 * i, word(0x9400 + i))
    put(prg, 0x16, 0xA72C, b''.join(word(0x9200 + i) for i in range(4)))
    put(prg, 0x16, 0xA734, b''.join(word(0x9100 + i) for i in range(10)))
    put(prg, *t.STAT_TABLE, list(range(0xA0, 0xA0 + len(t.STAT_NAMES))))
    for b in range(t.CONTROL_MIN, 0x100):
        put(prg, *t.HANDLERS, [])
        put(prg, 0x16, t.HANDLERS[1] + 2 * (255 - b), word(HANDLER_BASE + b))
    put(prg, *CALLERS_AT, [0x00, 0x07, 0x6F, 0x04, 0x00, 0x09, 0x6F, 0x04, 0x00, 0x07, 0x6F, 0x01])
    put(prg, dq4data.NAMES_BANK, dq4data.NAMES_PTR, b''.join(word(0xB100 + 0x10 * j) for j in range(7)))
    put(prg, dq4data.NAMES_BANK, 0xB100, [0, 2, 0x0B, 0x0C, 1, 0x0D])
    return prg, at


def capture(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **k)
    return r, out.getvalue().splitlines()


class WindowRecordTests(unittest.TestCase):
    def setUp(self):
        prg, self.at = text_prg()
        self.rom = t.Rom(ines(prg))

    def test_alias_takes_next_windows_record(self):
        addr, bs, alias = t.window_record(self.rom, 2)
        self.assertEqual((addr, bs, alias), (self.at[3], DEFAULT_REC, [(2, 3)]))

    def test_layout_place_routine_and_list(self):
        lay = t.window_layout(self.rom, 1)
        self.assertEqual((lay['w'], lay['x'], lay['width_routine'], lay['cols']), (None, None, 3, 0))
        self.assertEqual(lay['tokens'], [('list', 6), ('mode', 1)])
        self.assertEqual(t.layout_line(lay), f'01 16:${self.at[1]:04X} 자리 루틴 3   열0 [03 00]  [D6 16:$9EC3] E01')

    def test_layout_line_with_position_and_alias(self):
        lay = t.window_layout(self.rom, 2)
        self.assertEqual(t.layout_line(lay), f'02 16:${self.at[3]:04X} x 4 y 2 w 4 열1 [22 11] =02(3)  〈00〉 /')

    def test_every_token_kind_has_a_symbol(self):
        lay = t.window_layout(self.rom, 5)
        self.assertEqual(' '.join(t.token_str(k) for k in lay['tokens']),
                         '그룹1 1: +1 B0 B5 C1(02) {C2} [D0] E03')
        lay = t.window_layout(self.rom, 4)
        self.assertEqual(' '.join(t.token_str(k) for k in lay['tokens']),
                         '0かき1 ?2:01 ?표2 か〈00 16:$B000〉き01 / 곁창05 [D3] E01')

    def test_token_meanings(self):
        m = t.token_meaning
        self.assertEqual(m(('item', 0, 0, '〈00〉')), '동료 이름($F7)')
        self.assertEqual(m(('item', 0, 0, '이름')), '')
        self.assertEqual(m(('cond', 0x01, 0)), '줄 수 = 동료(걸러내기 08)')
        self.assertEqual(m(('list', 6)), '동료 $F7 의 소지품 8칸')
        self.assertEqual(m(('call', 0)), '$F8 → 동료 번호(걸러내기 $03DD)')
        self.assertEqual(m(('flag', 0)), '$F5 |= 41')
        self.assertTrue(m(('flag', 3)).startswith('한 쪽 줄 수 n = 값 - B0'))
        self.assertEqual(m(('mode', 1)), t.MODE_MEANING)
        self.assertEqual(m(('side', 0x0F)), '곁 창 0F 을 함께 엶')
        self.assertEqual(m(('raw', 0xC2)), '')

    def test_routine_address_and_counting(self):
        self.assertEqual(t.routine_address(self.rom, 0, 3), (0x9004, True))
        self.assertEqual(t.routine_address(self.rom, 0, 0x10), (0x9011, False))
        self.assertEqual(t.routine_address(self.rom, 1, 2), (0x9403, True))
        self.assertEqual(t.routine_address(self.rom, 1, 7), (0x9408, False))

    def test_window_callers_by_brk_bytes(self):
        self.assertEqual(t.window_callers(self.rom), {4: [(5, 0x9000), (5, 0x9004)], 1: [(5, 0x9008)]})

    def test_meaning_lines_sections(self):
        out = t.meaning_lines(self.rom)
        self.assertEqual(out[0], '# 루틴 항목(창 문자열 표의 앞쪽 항목, 그룹:번호 주소 뜻)')
        self.assertEqual(out[1], '0:00 16:$B000  동료 이름($F7)')
        self.assertIn('0 A0  ちから', out)
        self.assertIn('1 A1  すばやさ', out)
        self.assertIn('0:80 16:$9001 줄 수  줄 수 = 동료 전원(걸러내기 00)', out)
        self.assertIn('0:90 16:$9011 늘 돎  ' + t.ROUTINE_MEANING[(0, 0x10)], out)
        self.assertIn('D6 16:$9EC3  동료 $F7 의 소지품 8칸', out)
        self.assertIn('C1 00 16:$9101  $F8 → 동료 번호(걸러내기 $03DD)', out)
        self.assertIn('0 16:$9201  HP·MP 표: 사람 수 n(1~5)으로 x·폭 = 16:$B875[n−1], y = v 0 → 4, 1 → 16. '
                      '6명 이상이면 둘로 나눠 둘째 몫을 곁 창 0F 에', out)
        self.assertEqual(out[-1], '# E0~FF: ' + t.MODE_MEANING)

    def test_control_table_counts_messages_using_each_byte(self):
        rows = {b: (h, n) for b, h, n, _ in t.control_table(self.rom)}
        self.assertEqual(len(rows), 0x100 - t.CONTROL_MIN)
        self.assertEqual(rows[0xF9], (HANDLER_BASE + 0xF9, 3))     # 세 메시지 모두 끝 부호 F9 로 끝난다
        self.assertEqual(rows[0xFC], (HANDLER_BASE + 0xFC, 1))
        self.assertEqual(rows[0xF6][1], 0)


class MeasureTests(unittest.TestCase):
    def cell(self, col, row, table=0):
        return 0x2000 + table * 0x400 + row * 32 + col

    def test_frame_size_from_corners(self):
        cells = {self.cell(3, 2): 0x86, self.cell(8, 2): 0x89, self.cell(3, 5): 0x87}
        self.assertEqual(t.measure_window(cells, 0, 0), (3, 2, 6, 4))

    def test_scroll_and_second_nametable(self):
        cells = {self.cell(3, 2): 0x86, self.cell(8, 2): 0x89, self.cell(3, 5): 0x87}
        self.assertEqual(t.measure_window(cells, 8, 8), (2, 1, 6, 4))
        cells = {self.cell(1, 2, table=1): 0x86}
        self.assertEqual(t.measure_window(cells, 0, 0), (33, 2, None, None))

    def test_at_picks_that_corner_and_attribute_cells_are_ignored(self):
        cells = {self.cell(3, 2): 0x86, self.cell(10, 10): 0x86, 0x2000 + 0x3C0: 0x86}
        self.assertEqual(t.measure_window(cells, 0, 0), (3, 2, None, None))
        self.assertEqual(t.measure_window(cells, 0, 0, at=(10, 10)), (10, 10, None, None))
        self.assertIsNone(t.measure_window({0x2000 + 0x3C0: 0x86}, 0, 0))


class TraceTests(unittest.TestCase):
    TRACE = '\n'.join([
        't open W=10', 't top g=0 n=02', '  put 0m3D 0:10 1:0C 2:FF 3:90', 't top g=1 n=03', 't sub n=04',
        't cond b=81 T=0 F5=80', 't => 3D2=5', 't cond b=82 T=1 F5=00', 't => 3D2=2',
        't list n=6', 't place n=1', 't c1 n=2', 't mode n=3', 't init n=0', 'x',
        't open W=11', 't top g=0 n=07',
        't cond b=81 T=0 F5=80', 't => 3D2=5', 't cond b=81 T=0 F5=80', 't => 3D2=5', ''])

    def test_one_row_per_opened_window(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, 'item.txt')
            p.write_text(self.TRACE)
            rows = t.trace_lines(str(p))
        self.assertEqual(rows, ['10 02「がい·{90}」 1:03 <04> ?0:81→5 list6 place1 c12 mode3 init0',
                                '11 07 ?0:81→5'])

    def test_put_text_marks_and_blank_fill(self):
        self.assertEqual(t._put_text(['0m3D', '0:10', '1:0C']), 'がい')
        self.assertEqual(t._put_text(['0:0B', '1:FF', '2:FF']), 'あ')
        self.assertEqual(t._put_text(['1:0C', '0:0B']), 'あい')


class CompareLayoutTests(unittest.TestCase):
    def setUp(self):
        prg, _ = text_prg()
        self.rom = t.Rom(ines(prg))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name

    def files(self, opens, ppu):
        Path(self.d, 'open.txt').write_text('\n'.join(opens) + '\n')
        Path(self.d, 'ppu.txt').write_text('\n'.join(ppu) + '\n')

    def test_matching_frame_is_same(self):
        self.files(['1 open F6=10 scroll=0,0', '2 other x=1'],
                   ['1 2044 86 86', '1 2047 89 89', '1 2084 87 87'])
        res, out = capture(t.compare_layouts, self.rom, self.d)
        self.assertEqual(res, (1, 0))
        self.assertEqual(out, [f'{self.d}: 열기 1 창 10 레코드 x4 y2 w4 / nametable x4 y2 w4 h3 같음'])

    def test_wrong_width_missing_frame_and_out_of_range_window(self):
        self.files(['1 open F6=10 scroll=0,0', '2 open F6=11 scroll=0,0', '3 open F6=FF scroll=0,0'],
                   ['1 2044 86 86', '1 2048 89 89', '1 2084 87 87'])
        res, out = capture(t.compare_layouts, self.rom, self.d)
        self.assertEqual(res, (0, 1))
        self.assertIn('w4 / nametable x4 y2 w5 h3 다름', out[0])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1], f'{self.d}: 열기 2 창 11 틀을 못 찾음')


class DumpCompareTests(unittest.TestCase):
    def setUp(self):
        self.rom = message_rom()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def ram(self, battle=False, line=(0x02, 0x42)):
        ram = bytearray(0x800)
        p = Path(self.tmp.name, 'a.ram')
        if battle:
            ram[t.WIDTH], ram[t.ORIGIN_X], ram[t.LINE_NO] = t.BATTLE_W, 2, 1
            nt = bytearray(0x400)
            y = t.SCREEN_ROW + 1
            nt[y * 32 + 2:y * 32 + 2 + len(line)] = bytes(line)
            Path(self.tmp.name, 'a.nt').write_bytes(nt)
        else:
            ram[t.WIDTH], ram[t.LINE_NO] = t.FIELD_W, 1
            ram[t.LINE_BUF + t.FIELD_W:t.LINE_BUF + t.FIELD_W + len(line)] = bytes(line)
        p.write_bytes(ram)
        return str(p)

    def test_buffer_lines_found_in_message(self):
        p = self.ram()
        ok, out = capture(t.compare, self.rom, [0], p)
        self.assertTrue(ok)
        self.assertEqual(out, [f'{p}: 창 줄 버퍼 1줄 모두 메시지 0000 에 순서대로 있음'])

    def test_battle_window_reads_nametable(self):
        p = self.ram(battle=True)
        ok, out = capture(t.compare, self.rom, [0], p)
        self.assertTrue(ok)
        self.assertEqual(out, [f'{p}: nametable 1줄 모두 메시지 0000 에 순서대로 있음'])

    def test_wrong_text_and_empty_window_fail(self):
        p = self.ram(line=(0x05,))
        ok, out = capture(t.compare, self.rom, [0], p)
        self.assertFalse(ok)
        self.assertEqual(out, [f'{p}: 다름 — 화면 「4」'])
        ok, _ = capture(t.compare, self.rom, [0], self.ram(line=()))
        self.assertFalse(ok)

    def test_line_spans_messages_including_the_inserted_period(self):
        ok, _ = capture(t.compare, self.rom, [0, 1], self.ram(line=(0x02, 0x42, 0x3F, 0x04, 0x21)))
        self.assertTrue(ok)
        ok, _ = capture(t.compare, self.rom, [0, 1], self.ram(line=(0x02, 0x42, 0x04, 0x21)))
        self.assertFalse(ok)

    def test_dump_lines_without_nt_file_falls_back_to_buffer(self):
        ram = bytearray(0x800)
        ram[t.WIDTH], ram[t.LINE_NO] = t.BATTLE_W, 1
        p = Path(self.tmp.name, 'b.ram')
        p.write_bytes(ram)
        lines, where, _ = t.dump_lines(str(p))
        self.assertEqual((lines, where), ([], '창 줄 버퍼'))


class ExportTests(unittest.TestCase):
    def setUp(self):
        prg, _ = text_prg()
        self.rom = t.Rom(ines(prg))

    def test_window_rows_and_symbols(self):
        rows = t.export_windows(self.rom)
        self.assertEqual(len(rows), sum(t.WINDOW_COUNTS))
        self.assertEqual(rows[0], {'group': 0, 'entry': '00', 'kind': 'code', 'addr': '16:$B000'})
        self.assertEqual(rows[1]['sym'], '0{INS:02}1')
        self.assertEqual(rows[1]['text'], '0かき1')
        self.assertEqual(rows[2]['sym'], 'か{CALL:00}き{INS:01}')

    def test_name_rows(self):
        rows = t.export_names(self.rom)
        self.assertEqual(rows, [
            {'list': 'spell', 'id': 0, 'addr': '0B:$B101', 'bytes': '0B 0C', 'sym': 'あい', 'text': 'あい'},
            {'list': 'spell', 'id': 1, 'addr': '0B:$B104', 'bytes': '0D', 'sym': 'う', 'text': 'う'}])

    def test_layout_rows(self):
        rows = t.export_layouts(self.rom)
        self.assertEqual(len(rows), t.WINDOW_COUNT)
        r1, r2, r4 = rows[1], rows[2], rows[4]
        self.assertEqual((r1['place_routine'], r1['w'], r1['place']), (3, None, t.PLACE_MEANING[3]))
        self.assertEqual(r1['body'], [{'op': 'list', 'kind': 6, 'routine': '16:$9EC3', 'meaning': '동료 $F7 의 소지품 8칸'},
                                      {'op': 'mode', 'arg': 1, 'meaning': t.MODE_MEANING}])
        self.assertEqual((r2['alias'], r2['place']), ('02:3', ''))
        self.assertEqual(r4['callers'], '05:$9000 05:$9004')
        self.assertEqual(rows[1]['callers'], '05:$9008')
        self.assertTrue(r4['inset'])
        self.assertEqual(r4['cursor'], 0x40)
        ops = [b['op'] for b in r4['body']]
        self.assertEqual(ops, ['item', 'cond', 'condtable', 'item', 'newline', 'side', 'list', 'mode'])
        self.assertEqual(r4['body'][1], {'op': 'cond', 'arg': 1, 'table': 2})
        self.assertNotIn('meaning', r4['body'][1])
        self.assertEqual(r4['body'][5], {'op': 'side', 'arg': '05', 'meaning': '곁 창 05 을 함께 엶'})

    def test_write_export_files(self):
        msgs, wins = [{'id': '0000', 'codes': 'x', 'bytes': 'y', 'text': 'z', 'sym': 's'}], t.export_windows(self.rom)
        names, lays = t.export_names(self.rom), t.export_layouts(self.rom)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'sub', 'text')
            _, lines = capture(t.write_export, out, msgs, wins, names, lays)
            self.assertEqual(sorted(os.listdir(out)), ['dq4-messages.json', 'dq4-messages.tsv', 'dq4-names.json',
                                                        'dq4-names.tsv', 'dq4-window-layouts.json',
                                                        'dq4-window-layouts.tsv', 'dq4-windows.json', 'dq4-windows.tsv'])
            data = json.loads(Path(out, 'dq4-messages.json').read_text(encoding='utf-8'))
            self.assertEqual(data['rows'], msgs)
            self.assertEqual(data['legend']['controls']['NAME'], {'byte': 'F6', 'meaning': t.CONTROLS[0xF6], 'arg': 'slot'})
            self.assertEqual(data['legend']['controls']['SOUND']['arg'], 'inline')
            self.assertIsNone(data['legend']['controls']['END']['arg'])
            tsv = Path(out, 'dq4-messages.tsv').read_text(encoding='utf-8').splitlines()
            self.assertEqual(tsv, ['id\tsym', '0000\ts'])
        self.assertTrue(lines[0].startswith(out + ': dq4-messages.json/.tsv'))

    def test_check_export_reports_each_kind_of_mismatch(self):
        rom = message_rom()
        msgs = t.export_messages(rom)
        wins = [{'group': 0, 'entry': '05', 'kind': 'str', 'bytes': '01 02', 'sym': '{NOPE}'},
                {'group': 0, 'entry': '06', 'kind': 'code'}]
        names = [{'list': 'spell', 'id': 3, 'bytes': '0B', 'sym': 'い'}]
        ok, out = capture(t.check_export, rom, msgs, wins, names)
        self.assertFalse(ok)
        self.assertIn('창 0 05: 되돌린 바이트가 다름', out)
        self.assertIn('이름 spell 3: 되돌린 바이트가 다름', out)
        self.assertEqual(out[-1], '메시지 3개, 창 문자열 1개, 이름 1개: 다른 것 2개')

    def test_check_export_catches_wrong_rom_bits(self):
        prg = bytearray(message_rom().prg)
        rom = t.Rom(ines(prg))
        msgs = t.export_messages(rom)
        prg[t.off(0x1B, 0xA500)] ^= 0xFC             # 롬 비트열만 바뀌어도 첫 메시지의 부호와 어긋난다
        bad = t.Rom(ines(prg))
        ok, out = capture(t.check_export, bad, msgs, [], [])
        self.assertFalse(ok)
        self.assertTrue(any(ln.startswith('메시지 0000: 롬 비트열과 다름(1B:$A500)') for ln in out))

    def test_unsymbolize_rejects_plain_glyph_without_byte(self):
        with self.assertRaises(ValueError):
            t.unsymbolize('龍')
        self.assertEqual(t.unsymbolize('Ex'), [0x77])
        self.assertEqual(t.symbolize([0x3D, 0x66]), '{3D}{66}')


class ValidMessageEdgeTests(unittest.TestCase):
    def prg(self):
        prg = base_prg()
        put(prg, *t.BANK_BOUNDS, [0, 0, 0, 0, 0, 0xFF])
        return prg

    def test_block_starting_after_the_next_block_yields_nothing(self):
        prg = self.prg()
        put(prg, t.WORD_BANK, 0xA400, pack([t.END] * 40))
        put(prg, t.WORD_BANK, 0xA500, pack([t.END] * 40))
        put(prg, *t.WORDS, word(0xA600))
        put(prg, *t.BLOCKS, word(0xA500) + word(0xA400) + b''.join(word(0xA600) for _ in range(t.block_count() - 2)))
        self.assertEqual(t.valid_messages(t.Rom(ines(prg))), list(range(32, 64)))

    def test_last_block_runs_to_32_messages_when_text_end_is_far(self):
        prg = self.prg()
        put(prg, t.WORD_BANK, 0xA500, pack([t.END] * 40))
        put(prg, *t.WORDS, word(0xBFFF))
        put(prg, *t.BLOCKS, b''.join(word(0xA500) for _ in range(t.block_count())))
        self.assertEqual(t.valid_messages(t.Rom(ines(prg))), list(range(87 * 32, 88 * 32)))

    def test_message_from_0500_gets_the_automatic_quote_when_compared(self):
        prg = self.prg()
        put(prg, t.WORD_BANK, 0xA800, pack([0x01, t.END]))
        put(prg, *t.BLOCKS, b''.join(word(0xA800) for _ in range(0x28 + 1)))
        rom = t.Rom(ines(prg))
        self.assertEqual(t.message_bytes(rom, 0x500), [0x02, 0xF9])
        ram = bytearray(0x800)
        ram[t.WIDTH], ram[t.LINE_NO] = t.FIELD_W, 1
        ram[t.LINE_BUF + t.FIELD_W:t.LINE_BUF + t.FIELD_W + 3] = bytes((0x70, 0x6F, 0x02))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, 'a.ram')
            p.write_bytes(ram)
            ok, _ = capture(t.compare, rom, [0x500], str(p))
        self.assertTrue(ok)

    def test_match_fails_when_substitution_cannot_reach_the_end(self):
        self.assertIsNone(t._match([1, 2], [1], 0, 0))                    # 줄이 더 남았는데 스트림이 끝남
        self.assertIsNone(t._match([1] * (t.SUBST_MAX + 2), [0xF6, 9], 0, 0))   # 치환 하나가 넣는 글자 수 상한을 넘음


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        prg, self.at = text_prg()
        self.rom = os.path.join(self.tmp.name, 'r.nes')
        Path(self.rom).write_bytes(ines(prg))

    def run_main(self, *argv, cwd=None):
        out, err = io.StringIO(), io.StringIO()
        old = os.getcwd()
        if cwd:
            os.chdir(cwd)
        try:
            with mock.patch('sys.argv', ['dq4text.py', self.rom, *argv]), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    t.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
        finally:
            os.chdir(old)
        return code, out.getvalue().splitlines(), err.getvalue()

    def test_message_number_and_count(self):
        _, out, _ = self.run_main('0', '2')
        self.assertEqual(out, ['--- 0000', '1エ。', '--- 0001', '3ぬね。'])
        _, out, _ = self.run_main('2')
        self.assertEqual(out, ['--- 0002', 'かき', '1。'])

    def test_bytes_option(self):
        _, out, _ = self.run_main('1', '--bytes')
        self.assertEqual(out, ['0001: 04 21 22 F9'])

    def test_all_prints_every_valid_message_and_count_on_stderr(self):
        _, out, err = self.run_main('all')
        self.assertEqual(out[:2], ['--- 0000', '1エ。'])
        self.assertEqual(len([ln for ln in out if ln.startswith('--- ')]), 3)
        self.assertIn('# 메시지 3개', err)

    def test_controls_listing(self):
        _, out, _ = self.run_main('controls')
        self.assertEqual(len(out), 0x100 - t.CONTROL_MIN)
        self.assertEqual(out[0xF9 - t.CONTROL_MIN], f'F9 16:${HANDLER_BASE + 0xF9:04X} 메시지    3  {t.CONTROLS[0xF9]}')

    def test_windows_listing(self):
        _, out, _ = self.run_main('windows')
        self.assertEqual(len(out), sum(t.WINDOW_COUNTS))
        self.assertEqual(out[0], '0 00 code 16:$B000  ')
        self.assertEqual(out[1], '0 01 str  16:$A700  0かき1')

    def test_windows_layout_with_callers_and_meaning(self):
        _, out, _ = self.run_main('windows', '--layout')
        self.assertEqual(len(out), t.WINDOW_COUNT)
        self.assertTrue(out[4].endswith('  ← 05:$9000 05:$9004'))
        self.assertTrue(out[1].endswith('  ← 05:$9008'))
        _, out, _ = self.run_main('windows', '--layout', '--meaning')
        i = next(k for k, ln in enumerate(out) if ln.startswith('01 '))
        self.assertEqual(out[i + 1], '     자리: ' + t.PLACE_MEANING[3])
        self.assertEqual(out[i + 2], '     [D6 16:$9EC3]: 동료 $F7 의 소지품 8칸')
        self.assertEqual(out[i + 3], '     E01: ' + t.MODE_MEANING)

    def test_windows_items_and_trace(self):
        _, out, _ = self.run_main('windows', '--items')
        self.assertEqual(out[1], '0:00 16:$B000  동료 이름($F7)')
        p = Path(self.tmp.name, 'item.txt')
        p.write_text('t open W=10\nt top g=0 n=02\n')
        _, out, _ = self.run_main('windows', '--trace', str(p), str(p))
        self.assertEqual(out, ['10 02', '10 02'])

    def test_windows_compare_exit_code(self):
        d = Path(self.tmp.name, 'lay')
        d.mkdir()
        (d / 'open.txt').write_text('1 open F6=10 scroll=0,0\n')
        (d / 'ppu.txt').write_text('1 2044 86 86\n1 2047 89 89\n1 2084 87 87\n')
        code, out, _ = self.run_main('windows', '--compare', str(d))
        self.assertEqual((code, out[-1]), (0, '같음 1, 다름 0'))
        (d / 'ppu.txt').write_text('1 2044 86 86\n1 2048 89 89\n1 2084 87 87\n')
        code, out, _ = self.run_main('windows', '--compare', str(d))
        self.assertEqual((code, out[-1]), (1, '같음 0, 다름 1'))

    def test_compare_dump(self):
        ram = bytearray(0x800)
        ram[t.WIDTH], ram[t.LINE_NO] = t.FIELD_W, 1
        ram[t.LINE_BUF + t.FIELD_W:t.LINE_BUF + t.FIELD_W + 2] = bytes((0x02, 0x42))
        p = Path(self.tmp.name, 'a.ram')
        p.write_bytes(ram)
        code, out, _ = self.run_main('0', '--compare', str(p))
        self.assertEqual(code, 0)
        code, _, _ = self.run_main('1', '--compare', str(p))
        self.assertEqual(code, 1)

    def test_export_check_only_and_write(self):
        code, out, _ = self.run_main('export', '--check')
        self.assertEqual(code, 0)
        self.assertTrue(out[-1].startswith('메시지 3개, 창 문자열 '))
        self.assertTrue(out[-1].endswith('이름 2개: 다른 것 0개'))
        target = os.path.join(self.tmp.name, 'text')
        code, out, _ = self.run_main('export', target)
        self.assertEqual(code, 0)
        self.assertTrue(Path(target, 'dq4-window-layouts.json').exists())
        code, out, _ = self.run_main('export', cwd=self.tmp.name)
        self.assertEqual(code, 0)
        self.assertTrue(Path(self.tmp.name, 'work', 'text', 'dq4-names.tsv').exists())


if __name__ == '__main__':
    unittest.main()
