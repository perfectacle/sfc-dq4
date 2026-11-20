"""커서 사라짐 규칙: 고르던 창이 그대로인데 ▶ 가 깜박임보다 오래 안 보이면 건다."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4winwatch as ww  # noqa: E402
import dq4winrule_cursor as cur  # noqa: E402
import dq4winrule_cursorlost as lost  # noqa: E402
from test_dq4winwatch import draw, fake_rom, planes, vram_chr  # noqa: E402

TRIANGLE = [0x00, 0x20, 0x30, 0x38, 0x30, 0x20, 0x00, 0x00]
LIST = (3, 15, 27, 27)
WHO = (4, 2, 12, 13)


def rom():
    data = bytearray(fake_rom())
    o = cur.lorom(cur.ROM_FONT) + (cur.CURSOR - 1) * 8
    data[o:o + 8] = bytes(TRIANGLE)
    return bytes(data)


def chr_():
    data = bytearray(vram_chr())
    rows = ['22222222' if not b else ''.join('1' if b >> (7 - x) & 1 else '2' for x in range(8)) for b in TRIANGLE]
    p0, p1 = planes(rows)
    data[cur.CURSOR * 16:cur.CURSOR * 16 + 16] = bytes(x for pair in zip(p0, p1) for x in pair)
    return bytes(data)


def shot(i, cursors):
    m = [0x2C00] * 1024
    draw(m, *WHO)
    draw(m, *LIST)
    for r, c in cursors:
        m[r * 32 + c] = 0x2000 | cur.CURSOR
    return ww.Shot(i, 0, tuple(m), chr_(), 0, 0)


def judge(events, shots):
    rec = ww.Record(shots=shots, events=events, draws=[(1, 0x0E, WHO), (2, 0x0F, LIST)], oam=[], obj=[], maps=[],
                    objvram=[])
    return lost.check_run(SimpleNamespace(record=rec, ref=ww.Ref(rom()), scene='시험'))


ON, OFF, BACK = 1, 2, 3
SHOTS = {ON: shot(ON, [(5, 16)]), OFF: shot(OFF, []), BACK: shot(BACK, [(6, 3)])}


class CursorLostTest(unittest.TestCase):
    def test_blinking_cursor_passes(self):
        events = [(f, ON if (f // 16) % 2 == 0 else OFF) for f in range(10, 200, 16)] + [(200, ON)]
        self.assertEqual(judge(events, SHOTS), [])

    def test_cursor_gone_longer_than_a_blink_fails(self):
        hits = judge([(10, ON), (26, OFF), (80, ON)], SHOTS)
        self.assertEqual(len(hits), 1)
        self.assertIn('54프레임', hits[0][1])

    def test_cursor_moved_back_to_the_lower_window_passes(self):
        # B 로 한 단계 돌아가 목록은 남은 채 아래 「누구」 창이 고른다
        self.assertEqual(judge([(10, ON), (26, BACK), (80, BACK), (120, ON)], SHOTS), [])


if __name__ == '__main__':
    unittest.main()
