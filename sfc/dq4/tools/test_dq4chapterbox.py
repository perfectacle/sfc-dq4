import os
from pathlib import Path
import unittest

import dq4chapterbox as box

NES = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'


def branch_target(code, at):
    """at 의 BNE/BRA 가 가는 곳."""
    d = code[at + 1]
    return at + 2 + (d - 256 if d > 127 else d)


class CodeTests(unittest.TestCase):
    def test_if_pending_branches_reach_other(self):
        then, other = bytes((0xA9, 0x04)), bytes((0xA9, 0x17))
        code = box.if_pending((box.CHAPTER1,), then, other)
        skips = [i for i in range(len(code) - len(then) - len(other) - 2) if code[i] == 0xD0]
        self.assertEqual(len(skips), 3)
        other_at = len(code) - len(other)
        for at in skips:
            self.assertEqual(branch_target(code, at), other_at)
        bra = other_at - 2
        self.assertEqual(code[bra], 0x80)
        self.assertEqual(branch_target(code, bra), len(code))

    def test_if_pending_without_other_falls_to_end(self):
        then = bytes((0xA9, 0xA3, 0x8F, 0xDF, 0x21, 0x7E))
        code = box.if_pending((box.CHAPTER1,), then)
        for at in [i for i in range(len(code) - len(then)) if code[i] == 0xD0]:
            self.assertEqual(branch_target(code, at), len(code))

    def test_if_pending_tries_each_scene(self):
        # 장면마다 검사 셋. 맞지 않으면 다음 장면으로, 마지막 장면이 맞지 않으면 other. 앞 장면이 맞으면 BRA 로 then
        then, other = bytes((0xA9, 0x04)), bytes((0xA9, 0x17))
        code = box.if_pending((box.PROLOGUE, box.CHAPTER1), then, other)
        then_at = len(code) - len(other) - 2 - len(then)
        other_at = len(code) - len(other)
        block = 6 + 1 + 6 + 1 + 7 + 1                       # LDA/CMP/BNE ×2, LDA long/AND/BNE
        first = [6, 13, 21]                                  # 첫 장면 BNE 자리
        for at in first:
            self.assertEqual(code[at - 1], 0xD0)
            self.assertEqual(branch_target(code, at - 1), block + 2)
        self.assertEqual(code[block], 0x80)
        self.assertEqual(branch_target(code, block), then_at)
        for at in (block + 2 + 6, block + 2 + 13, block + 2 + 21):
            self.assertEqual(branch_target(code, at - 1), other_at)
        self.assertEqual(code[1:3], bytes((0xBC, 0x00)))
        self.assertEqual(code[4], box.PROLOGUE.where[0])
        self.assertEqual(code[block + 2 + 4], box.CHAPTER1.where[0])

    def test_fade_loop_jumps_back_to_store(self):
        code = box.fade(1, 15, 1)
        self.assertEqual(code[:2], bytes((0xA9, 1)))
        self.assertEqual(branch_target(code, len(code) - 2), 2)
        self.assertEqual(code[-4:-2], bytes((0xC9, 16)))
        self.assertEqual(box.fade(14, 0, 1)[-4:-2], bytes((0xC9, 0xFF)))

    def test_entry_points_do_not_depend_on_data(self):
        blank = bytes(box.BOX_W * box.BOX_H * 2)
        for scenes in ((box.CHAPTER1,), (box.PROLOGUE, box.CHAPTER1)):
            a = box.Layout(box.CODE_AT, scenes, b'', [blank] * len(scenes), box.palettes())
            b = box.Layout(box.CODE_AT, scenes, bytes(16 * 40), [blank] * len(scenes), box.palettes())
            self.assertEqual((a.box_at, a.reveal_at), (b.box_at, b.reveal_at))
            self.assertEqual(box.entry_points(scenes), {**a.box_at, 'reveal': a.reveal_at})

    def test_code_bank_is_not_a_sound_bank(self):
        # 사운드 세트는 이 롬 위에 얹으며 자기 뱅크가 비어 있어야 한다
        import dq4soundpatch
        self.assertNotIn(box.CODE_AT >> 16, dq4soundpatch.DATA_BANKS)

    def test_snes_tile_planes(self):
        rows = [[3, 1, 2, 0, 0, 0, 0, 0]] + [[0] * 8] * 7
        t = box.snes_tile(rows)
        self.assertEqual(t[:2], bytes((0b11000000, 0b10100000)))


@unittest.skipUnless(NES.exists() and os.environ.get('DQ4_GALMURI'), 'rom/dq4.nes 와 DQ4_GALMURI 가 있어야 함')
class BoxTests(unittest.TestCase):
    def setUp(self):
        import dq4menupatch
        self.nes = NES.read_bytes()
        self.font = dq4menupatch.Font('galmuri11')

    def test_border_tiles_have_no_shadow_plane(self):
        for n in box.FC_BORDER.values():
            self.assertTrue(all(v in (0, 1) for row in box.fc_tile(self.nes, n) for v in row), f'{n:02X}')

    def test_fill_is_blue(self):
        self.assertEqual({v for row in box.fc_tile(self.nes, box.FC_FILL) for v in row}, {2})

    def test_box_fits_canvas(self):
        # 서장과 1장 상자가 캔버스를 함께 쓴다
        tiles, maps = box.box_data(self.nes, self.font, [box.PROLOGUE.title, box.CHAPTER1.title])
        self.assertLessEqual(box.CANVAS + len(tiles) // 16, box.CANVAS_END)
        self.assertEqual([len(w) for w in maps], [box.BOX_W * box.BOX_H * 2] * 2)


if __name__ == '__main__':
    unittest.main()


class EndBoxTest(unittest.TestCase):
    def test_a_box_without_a_map_never_darkens_a_map(self):
        import dq4chapterbox as b
        self.assertEqual(b.if_pending((b.CHAPTER1, b.CHAPTER2), b'T', b'O'), b.if_pending((b.CHAPTER1,), b'T', b'O'))
        self.assertIn('box2', b.entry_points((b.CHAPTER1, b.CHAPTER2)))

