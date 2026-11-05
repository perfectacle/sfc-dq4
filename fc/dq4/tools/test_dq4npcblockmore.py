"""인물 블록의 명령 설명·다음 주소 예측·기록 대조·명령줄 출력을 합성 PRG 와 합성 기록으로 검사한다."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
import warnings
from unittest import mock

import dq4npcblock as nb
from test_dq4npcblock import PRG_SIZE, put, word, world_prg


def run_main(prg, *args):
    """합성 PRG 를 iNES 파일로 써서 main() 을 돌린다. (출력 줄, 반환값)."""
    head = bytes([0x4E, 0x45, 0x53, 0x1A, 32, 0]) + bytes(10)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'x.nes')
        with open(path, 'wb') as f:
            f.write(head + bytes(prg))
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['x', path, *args]), contextlib.redirect_stdout(out), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)
            ret = nb.main()
    return out.getvalue().splitlines(), ret


def with_block(block):
    """맵 00/00 의 낮 인물 한 명에 이 블록을 단 합성 PRG. 본문은 05:$9008 부터."""
    prg = world_prg()
    put(prg, nb.NPC_BANK, 0x9000, [0x10, 0, 0, 0, 0x11, 5, 6, len(block)] + list(block) + [0])
    return prg


def texts(prg, block):
    return [t for _, _, t, _ in nb.decode(prg, nb.NPC_BANK, 0x9008, len(block))]


class DescribeTests(unittest.TestCase):
    def test_walk_and_place_commands(self):
        block = [0x23, 0x05, 0x23, 0x82, 0x24, 0x80, 0x00, 0x24, 0x05, 0x06, 0x25, 0x03, 0x04]
        self.assertEqual(texts(with_block(block), block),
                         ['방향 1, 그림 칸 5', '방향 2', '목표 = 일행', '목표 (05,06)', '자리 (03,04)'])

    def test_range_wait_and_brk_commands(self):
        block = [0x2D, 0x05, 0x2E, 0x01, 0x02, 0x03, 0x2C, 0x01, 0x02, 0x03, 0x21, 0x07, 0x30, 0x05]
        self.assertEqual(texts(with_block(block), block),
                         ['범위 05 안에서 아무 방향(머묾)', '일행이 (01,02) 에 설 때까지 명령 03',
                          'BRK 1E 함수 09 X=01 A=02 Y=03', '특수 전투 07(BRK 18 함수 01)',
                          'BRK 19 함수 03 (A = 05)'])

    def test_jump_call_and_branch_commands(self):
        block = [0x82, 0x03, 0x84, 0x34, 0x12, 0x85, 0x78, 0x56, 0x86, 0x00, 0x05, 0x86, 0x02, 0x05]
        self.assertEqual(texts(with_block(block), block),
                         ['횟수 03, 되돌아갈 자리 저장', '점프 $1234', '부름 $5678',
                          '일행이 (0A,1E) 에 서면 상대 점프 +05, 아니면 머묾', '갈래 02(처리기 표 1F:$DE98)'])

    def test_flag_assignment_names_the_flag(self):
        block = [0x29, 0x07, 0x7B, 0x62, 0x29, 0x07, 0x00, 0x10]
        self.assertEqual(texts(with_block(block), block), ['$627B(플래그 00) = 07', '$1000 = 07'])

    def test_pattern_command_reads_pattern_table(self):
        prg = with_block([0x22, 0x01, 0x22, 0x09])
        put(prg, *nb.PATTERN_PTR, word(0x8050) + word(0x804E))
        put(prg, nb.PATTERN_PTR[0], 0x804E, [2, 1])
        put(prg, nb.PATTERN_PTR[0], 0x8050, [0x13, 0x82, 0x05])
        self.assertEqual(texts(prg, [0] * 4), ['일행 움직임 패턴 01: 멈춤×5', '일행 움직임 패턴 09: 표 밖'])

    def test_jump_targets(self):
        prg = with_block([0x83, 0xFE, 0x84, 0x08, 0x90, 0x85, 0x08, 0x90, 0x86, 0x00, 0x04])
        cmds = nb.decode(prg, nb.NPC_BANK, 0x9008, 11)
        self.assertEqual(nb.targets(prg, nb.NPC_BANK, 0x9008, cmds),
                         [(0x9008, 0x9006), (0x900A, 0x9008), (0x900D, 0x9008), (0x9010, 0x9014)])


class SuccessorTests(unittest.TestCase):
    def succ(self, code, saved=0x9999):
        prg = bytearray(PRG_SIZE)
        put(prg, nb.NPC_BANK, 0x9010, code)
        return nb.successors(prg, nb.NPC_BANK, 0x9010, saved)

    def test_return_and_counter_use_saved_address(self):
        self.assertEqual(self.succ([0x80]), ({0x9999}, 0x9999))
        self.assertEqual(self.succ([0x81]), ({0x9999, 0x9011}, 0x9999))

    def test_counter_and_call_save_new_address(self):
        self.assertEqual(self.succ([0x82, 0x03]), ({0x9012}, 0x9012))
        self.assertEqual(self.succ([0x85, 0x00, 0xA0]), ({0xA000}, 0x9013))

    def test_jumps(self):
        self.assertEqual(self.succ([0x83, 0xFC]), ({0x900C}, 0x9999))
        self.assertEqual(self.succ([0x84, 0x34, 0x12]), ({0x1234}, 0x9999))
        self.assertEqual(self.succ([0x86, 0x00, 0x05]), ({0x9015}, 0x9999))

    def test_plain_command_falls_through_by_size(self):
        self.assertEqual(self.succ([0x26, 0x10, 0x05]), ({0x9013}, 0x9999))
        self.assertEqual(self.succ([0x2A]), ({0x9011}, 0x9999))
        self.assertEqual(self.succ([0x40]), ({0x9011}, 0x9999))      # 31~7F 는 00 으로 실행


class TraceTests(unittest.TestCase):
    def trace(self, prg, *lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'npcblock.txt')
            with open(path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                ret = nb.cmd_trace(prg, path)
        return ret, out.getvalue().splitlines()

    def test_predicted_steps_match(self):
        prg = world_prg()
        ret, out = self.trace(prg, 't 06 05:9008 -', 't 06 05:900B -', 't 06 05:900F -')
        self.assertEqual(ret, 0)
        self.assertEqual(out, ['기록한 명령 3개 중 디코드한 명령 머리 3개, 이어진 명령 2번 중 예측과 같은 것 2번, '
                               '목표 칸에 닿아 03 을 마친 것 0번 중 그 칸에 선 것 0번'])

    def test_address_inside_a_command_is_not_a_head(self):
        ret, out = self.trace(world_prg(), 't 06 05:9009 -')
        self.assertEqual(ret, 1)
        self.assertEqual(out[1], '  명령 머리가 아님: t 06 05:9009 -')

    def test_unpredicted_jump_is_reported(self):
        ret, out = self.trace(world_prg(), 't 06 05:9008 -', 't 06 05:900F -')
        self.assertEqual(ret, 1)
        self.assertEqual(out[1], '  예측 $900B 과 다름: t 06 05:900F -')

    def test_map_change_forgets_previous_command(self):
        ret, out = self.trace(world_prg(), 't 06 05:9008 -', 't map 05', 't 06 05:900F -')
        self.assertEqual(ret, 0)
        self.assertTrue(out[0].startswith('기록한 명령 2개 중 디코드한 명령 머리 2개, 이어진 명령 0번'))

    def test_arrival_at_goal_is_checked(self):
        prg = with_block([0x24, 0x05, 0x06, 0x03, 0x2A])
        ret, out = self.trace(prg, 't 06 05:9008 -', 't 06 05:900B -', 't 06 pos 5,6 - -', 't 06 05:900C -')
        self.assertEqual(ret, 0)
        self.assertTrue(out[0].endswith('목표 칸에 닿아 03 을 마친 것 1번 중 그 칸에 선 것 1번'))
        ret, out = self.trace(prg, 't 06 05:9008 -', 't 06 05:900B -', 't 06 pos 4,4 - -', 't 06 05:900C -')
        self.assertEqual(ret, 1)
        self.assertEqual(out[1], '  목표 (5, 6) 가 아닌 (4, 4) 에서 03 을 마침: t 06 05:900C -')

    def test_unknown_return_address_is_learned_from_the_first_return(self):
        prg = with_block([0x80, 0x2A])
        ret, out = self.trace(prg, 't 06 05:9008 -', 't 06 05:9009 -')
        self.assertEqual(ret, 0)
        self.assertIn('이어진 명령 0번', out[0])


class CliTests(unittest.TestCase):
    def test_map_listing(self):
        out, ret = run_main(world_prg(), '0', '0')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '== 00/00')
        self.assertEqual(out[1], '  레코드 00 05:$9000 F=10 블록1 05:$9008 길이 9')
        self.assertEqual(out[2], '    +00 26 10 05     메시지 0510')
        self.assertEqual(out[-1], '    +04 83 fc        상대 점프 -4 → $901B')

    def test_missing_map(self):
        out, ret = run_main(world_prg(), '5', '5')
        self.assertEqual((out, ret), (['그런 맵이 없음'], 1))

    def test_alt_listing_marks_problems(self):
        out, ret = run_main(world_prg(), 'alt')
        self.assertEqual(ret, 0)
        self.assertEqual(out[0], '== 00/00 목록 1C:$A000')
        self.assertEqual(out[2], '    +00 8b           모르는 명령  <모름>')
        self.assertEqual(out[3], '    +01 26 00 00     메시지 0000  <넘침>')

    def test_check_reports_unknown_and_overflow(self):
        out, ret = run_main(world_prg(), 'check')
        self.assertEqual(ret, 1)
        self.assertEqual(out[:3], ['블록 4개(본문 주소가 다른 것 4개), 명령 8개', '못 읽은 명령 1개, 블록 끝을 넘는 명령 1개',
                                   '점프·부름 대상: 블록 안 명령 머리 1곳, 그 밖 0곳'])
        self.assertEqual(out[3], '  00/00 목록 1C:$A000 레코드 0 블록1 $A008 8b')

    def test_check_counts_jump_outside_block(self):
        out, ret = run_main(with_block([0x84, 0x00, 0x70, 0x2A]), 'check')
        self.assertEqual(ret, 1)             # 이벤트 목록의 모르는 명령 때문
        self.assertIn('점프·부름 대상: 블록 안 명령 머리 0곳, 그 밖 1곳', out)
        self.assertIn('  00/00 레코드 0 블록1 $9008 → $7000', out)

    def test_stats_counts_commands(self):
        out, ret = run_main(with_block([0x2A, 0x2A, 0x45]), 'stats')
        self.assertEqual(ret, 0)
        self.assertIn('2A      2  멈춤 표시 켜고 쉼(머묾)', out)
        self.assertIn('45      1  멈춤 표시 끔($70E0 bit7) 뒤 쉼', out)

    def test_patterns_listing(self):
        prg = bytearray(PRG_SIZE)
        put(prg, *nb.PATTERN_PTR, word(0x8050) + word(0x804E))
        put(prg, nb.PATTERN_PTR[0], 0x804E, [2, 1])
        put(prg, nb.PATTERN_PTR[0], 0x8050, [0x13, 0x82, 0x05])
        out, ret = run_main(prg, 'patterns')
        self.assertEqual(out, ['00 1C:$8050 위×3 오른쪽×2', '01 1C:$8052 멈춤×5'])

    def test_no_arguments_prints_usage(self):
        out, ret = run_main(world_prg())
        self.assertEqual(ret, 2)
        self.assertTrue(out[0].startswith('DQ4(FC) 인물 블록'))

    def test_trace_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'n.txt')
            with open(path, 'w') as f:
                f.write('t 06 05:9008 -\n')
            out, ret = run_main(world_prg(), 'trace', path)
        self.assertEqual(ret, 0)
        self.assertTrue(out[0].startswith('기록한 명령 1개 중 디코드한 명령 머리 1개'))


class HiddenEntryTests(unittest.TestCase):
    def test_block_with_only_continuing_commands_before_end_is_not_hidden(self):
        rec = bytes([0x10, 0, 0, 0, 0, 0, 0, 3, 0x0F, 0x10, 0x11])
        self.assertFalse(nb.hidden_on_entry(rec))

    def test_hide_after_continuing_commands(self):
        rec = bytes([0x10, 0, 0, 0, 0, 0, 0, 3, 0x0F, 0x12, 0x07])
        self.assertTrue(nb.hidden_on_entry(rec))


if __name__ == '__main__':
    unittest.main()
