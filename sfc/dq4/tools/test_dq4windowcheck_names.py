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


class GlyphTest(unittest.TestCase):
    """필드 캔버스 슬롯은 이름의 평면 0 을 메시지 캔버스에도 쓰므로, VRAM 이 「캔버스 그대로」 인지로는 이름이 올라갔는지 알 수
    없다. asm 이 적은 !wt_csum(열 수 << 12 | 글자 줄 평면 0 합의 낮은 12비트)과 VRAM 글자 줄을 견준다."""

    def vram_with_glyph(self, lo, rows):
        vram = bytearray(0x10000)
        for k, row in enumerate(rows):
            for r, b in enumerate(row):
                vram[(0x1000 + (lo + k) * 8) * 2 + 2 * r] = b
                vram[(0x1000 + (lo + k) * 8) * 2 + 2 * r + 1] = 0xFF
        return bytes(vram)

    def csum(self, i, cols, rows):
        words = bytearray(36)
        total = sum(sum(row) for row in rows) & 0xFFF
        words[2 * (i - wc.KANA_ENTRIES):2 * (i - wc.KANA_ENTRIES) + 2] = (cols << 12 | total).to_bytes(2, 'little')
        return bytes(words)

    def test_matching_glyph_is_ok_and_blank_is_not(self):
        rows = [bytes([1, 2, 3, 4, 5, 6, 7, 8]), bytes([9] * 8)]
        cs = self.csum(20, 2, rows)
        self.assertTrue(wc.glyph_ok(self.vram_with_glyph(0x122, rows), cs, 20, 0x122))
        self.assertFalse(wc.glyph_ok(self.vram_with_glyph(0x122, [bytes(8), bytes(8)]), cs, 20, 0x122))

    def test_mirrored_means_canvas_buffer_holds_the_name(self):
        rows = [bytes([1, 2, 3, 4, 5, 6, 7, 8]), bytes([9] * 8)]
        cs = self.csum(20, 2, rows)
        canvas = bytearray(len(wc.CANVAS) * 8)
        o = (0x122 - wc.CANVAS.start) * 8
        canvas[o:o + 16] = rows[0] + rows[1]
        self.assertTrue(wc.mirrored(bytes(canvas), cs, 20, 0x122))
        self.assertFalse(wc.mirrored(bytes(len(wc.CANVAS) * 8), cs, 20, 0x122))
        self.assertFalse(wc.mirrored(bytes(canvas), None, 20, 0x122))

    def test_no_record_or_outside_canvas_is_none(self):
        vram = bytes(0x10000)
        self.assertIsNone(wc.glyph_ok(vram, None, 20, 0x122))
        self.assertIsNone(wc.glyph_ok(vram, bytes(36), 20, 0x122))
        self.assertIsNone(wc.glyph_ok(vram, self.csum(13, 2, [bytes(8)] * 2), 13, 0x1E4))
        self.assertIsNone(wc.glyph_ok(vram, bytes(36), 3, 0x40))


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
