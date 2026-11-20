import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4vblankcheck as m  # noqa: E402

ASM = (HERE / 'dq4windowname.asm').read_text(encoding='utf-8')


def ww(frame, offset, value):
    return f'{frame} W {m.LOG + offset:06X}={value:02X} pc=31:FE00'


class EventTests(unittest.TestCase):
    def test_canvas_and_list_pairs(self):
        lines = [ww(10, 0, 245), ww(10, 1, 0), ww(10, 2, 0), ww(10, 3, 0),
                 ww(11, 4, 245), ww(11, 5, 0), ww(11, 6, 1), ww(11, 7, 0x01)]
        self.assertEqual(m.events('\n'.join(lines)), [(10, 'canvas', 245, 0), (11, 'list', 245, 0x101)])

    def test_late_counts_lines_after_vblank(self):
        self.assertEqual(m.late(257), 0)        # 귀선 안
        self.assertEqual(m.late(0), 0)          # 그리지 않는 줄
        self.assertEqual(m.late(2), 2)
        self.assertEqual(m.late(16), 16)

    def test_judge_uses_known(self):
        evs = [(640, 'list', 245, 1), (643, 'canvas', 245, 0)]
        self.assertEqual(m.judge('give-full', evs), [])
        self.assertEqual(len(m.judge('shopwho', evs)), 1)
        self.assertEqual(len(m.judge('give-full', [(642, 'canvas', 5, 16)])), 1)


class HookTests(unittest.TestCase):
    def test_hook_replaces_both_dma_starts(self):
        text = m.hook_asm(0x31FE00)
        self.assertIn('org $008EC5\n    JSL VA\n    NOP', text)
        self.assertIn('org $008D4E\n    JSL VB\n    NOP\n    NOP', text)
        self.assertEqual(len(m.SITES[0x008EC5]), 4 + 1)
        self.assertEqual(len(m.SITES[0x008D4E]), 4 + 2)

    def test_log_does_not_overlap_window_variables(self):
        # 창 글자 변수는 7E:A921~ABFF. 실험 훅이 적는 8바이트와 겹치면 재는 동안 동작이 바뀐다
        used = {int(a, 16) for a in re.findall(r'^!w[a-z]_\w+\s*=\s*\$(A[9AB][0-9A-F]{2})\b', ASM, re.M)}
        for a in used:
            self.assertFalse(m.LOG & 0xFFFF <= a < (m.LOG & 0xFFFF) + 8, hex(a))

    def test_free_spot_finds_filled_bank_end(self):
        rom = bytearray(b'\x11' * 0x20000)
        o = m.lorom(0x02FE00)
        rom[o:o + 0x80] = b'\xff' * 0x80
        self.assertEqual(m.free_spot(bytes(rom)), 0x02FE00)


class NmiOrderTests(unittest.TestCase):
    def body(self, name):
        start = ASM.index(f'\n{name}:')
        return ASM[start:ASM.index('\n; ', start + 1)]

    def test_queue_builds_entries_with_nmi_on(self):
        # 항목을 짜는 동안 NMI 를 끄면 그 사이 귀선이 온 프레임의 게임 NMI 가 늦게 시작해 캔버스 DMA 가 그리는 줄로 넘었다
        q = self.body('WtQueue')
        room = q.index('.room')
        self.assertNotIn('STA.l $004200', q[:q.index('; 대기열이 차면')])
        self.assertLess(room, q.index('STA.l $004200', room))
        self.assertIn('STA.w !wq_rd', q)

    def test_queue_commits_after_stash(self):
        # NMI 는 !wq_rd 부터 !wq_count 개만 읽으므로 항목 수는 NMI 를 끈 끝에서만 늘린다. 비었으면 rd 를 이 항목 첫 자리로
        # 맞추는 검사는 WhStash 앞에서 해야 한다 — WhStash 가 항목을 묶음으로 빼며 !wq_count 를 줄여, 뒤에서 보면 남은
        # 앞 항목을 버리고 뺀 항목을 보냈다(팔기 목록이 뜨기 전 메시지 창에 이름이 비침)
        q = self.body('WtQueue')
        off = q.index('STA.l $004200', q.index('.room'))
        rd, stash = q.index('STA.w !wq_rd', off), q.index('JSR WhStash', off)
        self.assertLess(rd, stash)
        self.assertLess(stash, q.index('ADC #$02', stash))
        self.assertNotIn('STA.w !wq_count', q[q.index('.room'):off])

    def test_entry_skips_gate_when_game_sends_canvas_or_big_list(self):
        e = self.body('WqNmiEntry')
        self.assertLess(e.index('LDA.l $001947'), e.index('JSL WqNmiGate'))
        self.assertIn('LDA.l $000F59', e)
        self.assertIn('LDA.l $7E4004', e)

    def test_clean_defers_canvas_dma_until_slots_cleaned(self):
        # 남은 슬롯을 비우지 않고 캔버스를 보내면 그 슬롯은 키가 산 채 덮여 장비 목록 이름이 한 줄씩 늦게 찼다
        c = self.body('WqClean')
        self.assertIn('JML $008E9D', c)          # 작업 RTS 로 돌아가 $0F59 를 남김
        self.assertIn('CMP #!wq_cdefer_max', c)
        self.assertIn('INC.w !wq_cdefer', c)
        self.assertIn('STZ.w !wq_cdefer', c)


if __name__ == '__main__':
    unittest.main()
