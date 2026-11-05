"""저장 데이터·장 시작·귀환 자리·플래그 쓰는 곳·엔딩·이벤트 표의 명령줄 출력을 합성 PRG, 합성 SRAM, 합성 대사로 검사한다."""
import os
import tempfile
import unittest

import dq4data as d
import dq4event as e
import dq4flags
import dq4text as t
import test_dq4text as tt
from test_dq4datamore import run_cli_code
from test_dq4event import event_prg
from test_dq4npcblock import put, word

CLASSES = ['あ', 'い', 'う', 'え', 'お', 'か', 'き', 'く']


def event_world():
    """event_prg 에 이름 목록·대사('12。' 하나)·엔딩·이벤트 표·귀환 자리·플래그 BRK 를 더한 합성 롬."""
    prg = event_prg()
    starts = {w: 0xA000 + 0x40 * i for i, w in enumerate(d.LISTS)}
    put(prg, d.NAMES_BANK, d.NAMES_PTR, [v for w in d.LISTS for v in word(starts[w])])
    put(prg, d.NAMES_BANK, starts['class'], [0] + [v for i in range(8) for v in (1, 0x0B + i)])
    put(prg, d.NAMES_BANK, starts['item'], [0, 1, 0x40, 1, 0x41])
    put(prg, d.NAMES_BANK, starts['place'], [0, 1, 0x0B, 1, 0x0C, 1, 0x0D])
    put(prg, d.NAMES_BANK, starts['spell'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['sex'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['monster'], [0, 1, 0x0B])
    put(prg, d.NAMES_BANK, starts['tactic'], [0, 1, 0x0B])
    base = tt.base_prg()
    o = t.off(*t.CHARS)
    prg[o:o + 128] = base[o:o + 128]
    tt.put(prg, *t.BANK_BOUNDS, [0, 0, 0, 0, 0, 0xFF])
    tt.put(prg, t.WORD_BANK, 0xA500, tt.pack([tt.CODE_A, tt.CODE_B, t.END] * 33))
    tt.put(prg, *t.BLOCKS, b''.join(tt.word(0xA500) for _ in range(t.block_count())))
    tt.put(prg, *t.WORDS, b''.join(tt.word(0xA600) for _ in range(4)))
    tt.put(prg, t.WORD_BANK, 0xA600, [t.WORD_END])
    put(prg, *e.ENDING, word(0x9F00))
    put(prg, e.ENDING[0], 0x9F00, [0x10, 0x01, 2, 3, 0x80, 0x85, 0x00, 0xA0, 2, 0xFF])
    put(prg, e.ENDING[0], 0xA000, [0x13, 0x22])
    put(prg, *e.ENTRY, [1, 2, 3, 0x45, 5, 6, 0xFF])
    put(prg, e.TOWN_BANK, e.TOWN_GROUPS[0], [0x03, 0xFF])
    put(prg, e.TOWN_BANK, e.TOWN_GROUPS[1], [0xFF])
    put(prg, *e.TOWN_PTR, word(0xB000))
    put(prg, e.TOWN_PTR[0], 0xB000 + 7 * 2, [0x81, 5, 6, 0x10, 0x01, 0xAA, 0xBB])
    put(prg, e.TOWN_BANK, e.TOWN_RECORD, [2])
    put(prg, *e.PLACES, [1, 2, 3, 4, 0x09])
    # 뱅크 10: 맵 03/01 을 고르고 플래그 70 의 비트 20 을 켠 뒤 메시지 0134. 뱅크 02(데이터)에는 모양만 같은 두 비트 검사
    put(prg, 0x10, 0x9000, [0xA5, 0x63, 0xC9, 0x03, 0xA5, 0x64, 0xC9, 0x01, 0x00, 0x70, 0xCB, 0x20,
                            0xEA, 0x00, 0x34, 0x1B])
    put(prg, 0x02, 0x9000, [0x00, 0x71, 0xEB, 0x03])
    return prg


def sram_file(tmp, data):
    path = os.path.join(tmp, 'end.sram')
    with open(path, 'wb') as f:
        f.write(bytes(data))
    return path


def poke(s, addr, data):
    s[addr - 0x6000:addr - 0x6000 + len(data)] = bytes(data)


def work_sram():
    s = bytearray(0x2000)
    poke(s, e.CHAPTER, [2])
    poke(s, e.GOLD, [0xD2, 0x04, 0x00])
    poke(s, e.HERO_NAME, [0x0B, 0x0C, 0x00, 0x00])
    poke(s, e.PLACE_NO, [5])
    poke(s, e.PARTY, [0, 1, 2, 0x80])
    poke(s, e.REC, [0x80, 50, 0, 7, 0, 0, 0, 0, 0, 0, 0, 0, 50, 0])      # 인물 0: HP 50, MP 7, 최대HP 50
    poke(s, e.REC + 0x13, [0, 1, 0x81, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])                               # 소지품 ア イ E(イ)
    return s


class SramTests(unittest.TestCase):
    def setUp(self):
        self.prg = event_world()
        s = work_sram()
        body = bytes(s[e.WORK - 0x6000:e.WORK - 0x6000 + e.WORK_LEN])
        self.crc = e.crc(body)
        poke(s, e.SLOTS[0], list(self.crc.to_bytes(2, 'little')) + list(body))
        poke(s, e.SLOTS[1], [e.EMPTY] * 5)
        self.sram = s

    def test_sram_command_prints_work_area_and_three_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, ret = run_cli_code(e.main, self.prg, 'sram', sram_file(tmp, self.sram))
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '== 작업 영역 $6001~$62EE')
        self.assertEqual(out[1], '장 3($615A=02)  골드 1234  주인공 이름 あい(0b 0c 00 00)  귀환 자리 05  $6291=00')
        self.assertEqual(out[2], '일행 $616A: 00 01 02 80  그 밖 $6172: 00 00 00 00 00 00')
        self.assertTrue(out[3].startswith('  0 あ        HP 50 MP 7 레벨 0'))
        self.assertEqual(out[4], '      소지품 ア イ Eイ  +0B=00 +1B~1D=000000')
        slot_lines = [l for l in out if l.startswith('== 모험의 서')]
        self.assertEqual(slot_lines, [
            f'== 모험의 서 1 $62EF: CRC {self.crc:04X} 계산 {self.crc:04X} 맞음  작업 영역과 같음',
            '== 모험의 서 2 $65DF: 빈 칸',
            slot_lines[2]])
        self.assertIn(' 다름  작업 영역과 다름', slot_lines[2])
        self.assertIn('  장 3($615A=02)  골드 1234', out[out.index(slot_lines[0]) + 1])

    def test_flags_command_lists_nonzero_bytes(self):
        s = bytearray(0x2000)
        poke(s, e.FLAGS + 5, [0x41])
        poke(s, e.FLAGS_END, [0x80])
        with tempfile.TemporaryDirectory() as tmp:
            out, ret = run_cli_code(e.main, self.prg, 'flags', sram_file(tmp, s))
        self.assertEqual((out, ret), (['$6280 번호 05 = 41  01000001', '$62EE 번호 73 = 80  10000000'], 0))


class StartTests(unittest.TestCase):
    def setUp(self):
        self.prg = event_world()
        put(self.prg, *e.START, [1, 2, 3, 4] + [5, 6, 7, 8] * 4)
        put(self.prg, e.INIT, e.LEADER, [0x80, 0x82, 0x83, 0x85, 0x80])
        put(self.prg, e.INIT, e.CHAPTER_GOLD, [10, 20, 30, 40, 50])
        put(self.prg, e.INIT, e.CHAPTER_6165, [1, 2, 3, 4, 5])
        put(self.prg, *e.CHAPTER_PLACE, [0, 1, 2, 3, 4])
        put(self.prg, e.INIT, e.CHAR_CHAPTER, [0, 0, 1, 1, 2, 2, 3, 4])

    def test_chapters_command(self):
        out, ret = run_cli_code(e.main, self.prg, 'chapters')
        self.assertEqual(ret, 0)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0], '1장 시작 01/02 (03,04)  선두 80(あ)  골드 10  $6165=01 02 03 04 05  귀환 자리 00  '
                                 '초기화 인물 あ, い')
        self.assertEqual(out[1], '2장 시작 05/06 (07,08)  선두 82(う)  골드 20  $6165=00 00 00 00 00  귀환 자리 01  '
                                 '초기화 인물 う, え')
        self.assertTrue(out[4].endswith('초기화 인물 く'))

    def stat_tables(self):
        put(self.prg, e.INIT, e.CHAR_HP, [33])
        for s in range(6):
            put(self.prg, e.INIT, e.STAT_PTRS + 2 * s, word(0x9800 + 0x40 * s))
            put(self.prg, e.INIT, e.STAT_OFFS + s, [0x06 + s if s < 5 else 0x0E])
            put(self.prg, e.INIT, 0x9800 + 0x40 * s, [0x80, 0x00, 0x80, 0x00, 0x80, 0xFF])     # 인물 0: 0b10101
        put(self.prg, e.INIT, e.CHAR_ITEMS, [1, 0x81, 0xFF, 0, 0, 0, 0, 0])

    def test_chars_command_prints_initial_records(self):
        self.stat_tables()
        out, ret = run_cli_code(e.main, self.prg, 'chars')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '0 あ        1장  HP 33 MP 21 레벨 1 ちから 21 すばやさ 21 たいりょく 21 かしこさ 21 '
                                 'うんのよさ 21 최대HP 33 최대MP 21')
        self.assertEqual(out[1], '      소지품 イ Eイ ア ア ア ア ア')
        self.assertTrue(out[2].startswith('1 い        1장  HP 0 MP 0 레벨 1'))
        self.assertTrue(out[4].startswith('2 う        2장'))

    def test_chars_compare_with_sram(self):
        self.stat_tables()
        s = bytearray(0x2000)
        poke(s, e.CHAPTER, [0])
        for i in (0, 1):
            for o, v in e.init_record(self.prg, i).items():
                poke(s, e.REC + e.REC_LEN * i + o, [v])
        with tempfile.TemporaryDirectory() as tmp:
            out, ret = run_cli_code(e.main, self.prg, 'chars', '--compare', sram_file(tmp, s))
            self.assertEqual(ret, 0)
            self.assertEqual([l for l in out if l.startswith('      비교')], ['      비교: 같음', '      비교: 같음'])
            poke(s, e.REC + 0x06, [99])
            out, ret = run_cli_code(e.main, self.prg, 'chars', '--compare', sram_file(tmp, s))
        self.assertEqual(ret, 1)
        self.assertIn('      비교: 다름 +06', out)


class PlacesTests(unittest.TestCase):
    def test_places_command(self):
        out, ret = run_cli_code(e.main, event_world(), 'places')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '== 귀환 자리 1E:$A76D ($6290 번호)')
        self.assertEqual(out[1], '00 01/02 (03,04) 방향 1  마을 레코드 02 → $6195~$6198 = 10 01 aa bb')
        self.assertEqual(out[1 + e.PLACE_COUNT], '== ルーラ 행선지 1~4장 ($6165 비트 → 맵 그룹 → 마을 레코드 → 도착)')
        self.assertEqual(out[2 + e.PLACE_COUNT], '  비트 00 ($6165 01)  그룹 03  레코드 02  맵 10/01 (05,06)')
        self.assertEqual(out[3 + e.PLACE_COUNT], '== ルーラ 행선지 5장 ($6165 비트 → 맵 그룹 → 마을 레코드 → 도착)')
        self.assertEqual(len(out), 4 + e.PLACE_COUNT)


class XrefTests(unittest.TestCase):
    def setUp(self):
        self.prg = event_world()

    def xref(self, *args):
        out, ret = run_cli_code(e.main, self.prg, 'flags', '--xref', *args)
        self.assertEqual(ret, 0)
        return out

    def test_xref_merges_code_talk_npc_and_table_uses(self):
        out = self.xref()
        self.assertIn('== $62EB 번호 70', out)
        self.assertIn('  20 set     BRK 10:$9008 맵 03/01  0134 12。', out)
        self.assertIn('  01 set     대화 011 00/00 슬롯 06  0520 12。', out)
        self.assertIn('  BF clear   인물 블록 밤 00/00 슬롯 06', out)
        self.assertIn('  08 test    맵 표 00/00 인물 목록 비움', out)
        self.assertNotIn('== $62EC 번호 71', out)
        self.assertTrue(out[-1].startswith('한 비트 '))

    def test_xref_single_flag_has_no_summary(self):
        out = self.xref('70')
        self.assertEqual(out, ['== $62EB 번호 70', '  20 set     BRK 10:$9008 맵 03/01  0134 12。'])

    def test_all_shapes_adds_data_looking_matches(self):
        out = self.xref('71', '--all')
        self.assertEqual(out, ['== $62EC 번호 71', '  03 test    BRK 02:$9000 (모양만)'])

    def test_ops_lists_brk_flag_commands(self):
        out, ret = run_cli_code(e.main, self.prg, 'ops', '--flag', '70')
        self.assertEqual((out, ret), (['10:$9008  $62EB(번호 70) 켜기 |= 20'], 0))
        out, _ = run_cli_code(e.main, self.prg, 'ops')
        self.assertEqual(out, ['02:$9000  $62EC(번호 71) 검사 & 03', '10:$9008  $62EB(번호 70) 켜기 |= 20'])
        self.assertEqual(run_cli_code(e.main, self.prg, 'ops', '--flag', '05')[0], [])


class MeaningTests(unittest.TestCase):
    def test_meaning_uses_confirmed_text_and_guesses_the_rest(self):
        prg = event_world()
        self.assertNotIn((0x70, 0x20), dq4flags.CONFIRMED)
        self.assertNotIn((0x70, 0x20), e.KNOWN)
        out, ret = run_cli_code(e.main, prg, 'flags', '--meaning')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '번호 비트 주소     쓰기 검사  뜻')
        guess = next(l for l in out if l.startswith('70   20'))
        self.assertEqual(guess, '70   20   $62EB    1    0  [추정] 쓰는 곳 BRK 10:$9008 맵 03/01 う 「12。」')
        confirmed = next(l for l in out if l.startswith('05   01'))
        self.assertTrue(confirmed.endswith('[확인] ' + dq4flags.CONFIRMED[(0x05, 0x01)]))
        self.assertIn('05   01   $6280    1    1  ', confirmed)

    def test_place_names_follow_town_records(self):
        self.assertEqual(e.place_names(event_world()), {3: 'う'})


class EventTableTests(unittest.TestCase):
    def test_events_command(self):
        out, ret = run_cli_code(e.main, event_world(), 'events')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '== 인물 블록의 이벤트 명령(88~8A n) → 1D:$B639 표의 루틴')
        self.assertEqual(out[1], '00/00 슬롯 06 블록+07  이벤트 02 → 1D:$B123')
        self.assertEqual(out[2], '== 맵 이벤트 표 1D:$B8CA (그룹/순번, 장, 셋째 바이트, 넷째 아래 4비트, 다섯째, 여섯째)')
        self.assertEqual(out[3], '01/02 5장  셋째 03  넷째 아래 5  05 06')

    def test_ending_command(self):
        out, ret = run_cli_code(e.main, event_world(), 'ending')
        self.assertEqual(ret, 0)
        self.assertEqual(out[1], '  맵 10/01 (02,03)   $62ED=80(밤) 머묾 00')
        self.assertEqual(out[2], '    일행 움직임 1A:$A000 $0530=85: 위×3 아래×2')

    def test_ending_names_the_place_of_a_known_group(self):
        prg = event_world()
        put(prg, e.ENDING[0], 0x9F00, [0x03, 0x01, 2, 3, 0x10, 0xFF])
        out, _ = run_cli_code(e.main, prg, 'ending')
        self.assertEqual(out[1], '  맵 03/01 (02,03) う  $62ED=10(낮) 머묾 10')

    def test_unknown_command_prints_usage(self):
        out, ret = run_cli_code(e.main, event_world(), 'nothing')
        self.assertEqual(ret, 2)
        self.assertTrue(out[0].startswith('DQ4(FC) 저장 데이터'))


if __name__ == '__main__':
    unittest.main()
