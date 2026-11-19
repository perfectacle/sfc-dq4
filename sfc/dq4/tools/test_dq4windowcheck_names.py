import struct
import tempfile
import unittest
from pathlib import Path

import dq4windowcheck as wc


def vram_with(cells):
    """BG3 타일맵 자리 0 에 칸 → 타일 번호를 둔 64KB VRAM."""
    vram = bytearray(0x10000)
    for cell, tile in cells.items():
        vram[cell * 2:cell * 2 + 2] = tile.to_bytes(2, 'little')
    return bytes(vram)


class SharedNameTest(unittest.TestCase):
    """이름 렌더러 자리의 첫 칸을 화면 두 곳이 함께 가리키면 한쪽은 남의 이름(상태 → 강함 보기 → 「누구의」 첫 줄이 둘째 사람
    이름으로 보였던 꼴)."""

    def test_two_cells_on_one_position_fail(self):
        first = wc.NAME_FIRST + 7 * 10
        bad = wc.shared_names(vram_with({2 * 32 + 5: first, 4 * 32 + 5: first}), 0)
        self.assertEqual({(r, c, rule) for r, c, rule, _ in bad}, {(2, 5, '겹자리'), (4, 5, '겹자리')})

    def test_distinct_positions_and_inner_cells_pass(self):
        vram = vram_with({2 * 32 + 5: wc.NAME_FIRST, 2 * 32 + 6: wc.NAME_FIRST + 1, 4 * 32 + 5: wc.NAME_FIRST + 10})
        self.assertEqual(wc.shared_names(vram, 0), [])


def winwatch(events):
    """판 5 winwatch.bin: 바뀐 프레임 기록 E(프레임, 모습 번호 또는 -1)만."""
    return b'V' + struct.pack('<H', 5) + b''.join(b'E' + struct.pack('<Ii', f, i) for f, i in events)


class ScreenOffTest(unittest.TestCase):
    """화면이 꺼진 프레임(winwatch 기록의 모습 -1)은 깨짐 판정에서 뺀다. 꺼짐 기준은 dq4winwatch.lua: 강제 끔·밝기 0·주 화면에
    BG3 없음. 밝기 1 이상(어두워지는 중)은 꺼짐이 아니다."""

    def test_frames_after_an_off_event_until_the_next_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'winwatch.bin').write_bytes(winwatch(((10, 1), (20, -1), (30, 2))))
            self.assertEqual(wc.screen_off(Path(tmp), [5, 15, 20, 25, 30, 35]), {20, 25})

    def test_missing_or_broken_record_is_an_error_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                wc.screen_off(Path(tmp), [20])
            (Path(tmp) / 'winwatch.bin').write_bytes(winwatch(((10, 1),))[:-3])
            with self.assertRaises(ValueError):
                wc.screen_off(Path(tmp), [20])

    def test_off_frame_is_skipped_and_lit_frame_is_judged(self):
        first = wc.NAME_FIRST + 7 * 10
        vram = vram_with({2 * 32 + 5: first, 4 * 32 + 5: first})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            lines = []
            for f in (10, 20):
                (folder / f'v{f:05d}.bin').write_bytes(vram)
                for addr, n in ((wc.KEYS, 60), (wc.AGES, 60), (wc.KBASE, 24), (0x0725, 1), (0x1944, 2)):
                    lines.append(f'{f} dump 7E{addr:04X} {bytes(n).hex().upper()}')
            (folder / 'msg.txt').write_text('\n'.join(lines) + '\n')
            (folder / 'winwatch.bin').write_bytes(winwatch(((10, 1), (20, -1))))
            off = wc.screen_off(folder, [10, 20])
            self.assertEqual(off, {20})
            hits = wc.check(folder, bytes(0x40000), ([], []), off)
            self.assertEqual([f for f, _ in hits], [10])
            self.assertEqual([f for f, _ in wc.check(folder, bytes(0x40000), ([], []))], [10, 20])

    def test_off_means_forced_blank_or_brightness_zero(self):
        lua = (Path(wc.__file__).parent / 'lua' / 'dq4winwatch.lua').read_text(encoding='utf-8')
        self.assertIn('s["ppu.forcedBlank"] or (s["ppu.screenBrightness"] or 0) == 0', lua)


if __name__ == '__main__':
    unittest.main()
