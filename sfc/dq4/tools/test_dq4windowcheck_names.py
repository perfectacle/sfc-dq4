import tempfile
import unittest
from pathlib import Path

from PIL import Image

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


class DarkFrameTest(unittest.TestCase):
    def test_all_black_shot_is_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            black, lit = Path(tmp) / 'b.png', Path(tmp) / 'l.png'
            Image.new('RGB', (8, 8)).save(black)
            im = Image.new('RGB', (8, 8))
            im.putpixel((3, 3), (40, 40, 40))
            im.save(lit)
            self.assertTrue(wc.dark(black))
            self.assertFalse(wc.dark(lit))
            self.assertFalse(wc.dark(Path(tmp) / 'none.png'))


if __name__ == '__main__':
    unittest.main()
