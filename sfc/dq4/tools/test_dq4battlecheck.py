import tempfile
import unittest
from pathlib import Path

import dq4battlecheck as bc
import dq4ch1walkcheck as wc


def writes(patch):
    """force_patch 의 코드를 따라가 7E 뱅크에 쓰는 16비트 값을 {주소: 값} 으로."""
    off, code = patch.split('=')
    code = bytes.fromhex(code)
    out, i = {}, 3
    while code[i] == 0xA9:
        value = code[i + 1] | code[i + 2] << 8
        assert code[i + 3] == 0x8F
        out[int.from_bytes(code[i + 4:i + 7], 'little')] = value
        i += 7
    return int(off, 16), code[:3], code[i:], out


class BattleCheckTests(unittest.TestCase):
    def test_force_patch_writes_group_and_sets_carry(self):
        off, head, tail, out = writes(bc.force_patch([(0x12, 1), (0x1E, 2)]))
        self.assertEqual(off, 0x11E7C2)
        self.assertEqual(head, bytes((0x08, 0xC2, 0x20)))          # PHP / REP #$20
        self.assertEqual(tail, bytes((0x28, 0x38, 0x6B)))          # PLP / SEC / RTL
        self.assertEqual(out, {0x7E1001: 0x1E12, 0x7E1003: 0xFFFF, 0x7E1005: 0x0201, 0x7E1007: 0,
                               0x7E1009: 0, 0x7E100B: 0})
        self.assertEqual(bc.group_bytes([(0x12, 1), (0x1E, 2)]), ('121EFFFF', '01020000'))
        with self.assertRaises(ValueError):
            bc.force_patch([])

    def test_gold_adds_reward_hook(self):
        rom = bytearray(0x200000)
        for n, (low, b8) in {0x00: (1, 0), 0x12: (20, 0), 0x1E: (15, 0x04)}.items():
            rom[wc.MONSTERS + n * 25 + 7], rom[wc.MONSTERS + n * 25 + 8] = low, b8
        self.assertEqual(bc.gold(rom, [(0x00, 2)]), 3)               # 2 + (2 + 1) // 3
        self.assertEqual(bc.gold(rom, [(0x12, 1), (0x1E, 1)]), 20 + 271 + (291 + 1) // 3)

    def test_weak_patch_matches_boss_patch_bytes(self):
        rom = bytearray(0x200000)
        for n in (0xE2, 0x52):
            rom[wc.MONSTERS + n * 25 + 8] = rom[wc.MONSTERS + n * 25 + 10] = 0xFF
        self.assertEqual(sorted(bc.weak_patch(rom, [0xE2, 0x52, 0x52]).split(';')),
                         sorted(wc.boss_patch(rom).split(';')))

    def test_parse_stages(self):
        stages = bc.parse('start f=24 map=36/00 gold=140000\nslots f=144 00\n')
        self.assertEqual(stages['start'], {'f': '24', 'map': '36/00', 'gold': '140000'})

    def test_same_pixels_allows_small_shift(self):
        from PIL import Image
        base = Image.new('RGB', (64, 48))
        for x in range(64):
            for y in range(48):
                base.putpixel((x, y), ((x * 7) % 256, (y * 11) % 256, (x * y) % 256))
        moved = Image.new('RGB', (64, 48))
        moved.paste(base, (0, 2))
        with tempfile.TemporaryDirectory() as d:
            a, b, c = Path(d, 'a.png'), Path(d, 'b.png'), Path(d, 'c.png')
            base.save(a)
            moved.save(b)
            Image.new('RGB', (64, 48)).save(c)
            self.assertEqual(bc.same_pixels(a, b), 1.0)
            self.assertLess(bc.same_pixels(a, c), 0.1)

    def test_scenes_name_walk_segments(self):
        names = [s[0] for s in wc.SEGMENTS]
        for name, scene in bc.SCENES.items():
            self.assertIn(scene['after'], names, name)
            self.assertIn('win', scene['battles'], name)
            self.assertEqual(scene['prep'][0][1], 'warp', name)


if __name__ == '__main__':
    unittest.main()


def tilemap(cells):
    """{(줄, 열): 낱말} 만 채운 BG3 타일맵 2KB(나머지는 빈칸 2C00)."""
    words = [0x2C00] * (32 * 32)
    for (r, c), w in cells.items():
        words[r * 32 + c] = w
    return b''.join(w.to_bytes(2, 'little') for w in words)


class CornerTests(unittest.TestCase):
    def test_status_window_with_right_corner_passes(self):
        # 일행 한 명 전투 상태 창: 왼쪽 모서리 2열, 이름 5칸 3~7열, 오른쪽 모서리(좌우 뒤집음) 8열
        m = tilemap({(2, 2): 0x208C, **{(2, c): 0x218F + c for c in range(3, 8)}, (2, 8): 0x608C})
        self.assertEqual(bc.dq4windowcheck.corners(m, 0), [])

    def test_name_cell_over_right_border_fails(self):
        # 창 너비 6 이면 이름 다섯째 칸(7열)이 오른쪽 모서리 자리를 덮는다
        m = tilemap({(2, 2): 0x208C, **{(2, c): 0x218F + c for c in range(3, 8)}})
        self.assertEqual(bc.dq4windowcheck.corners(m, 0), [(2, 2, '테두리', 0x08C)])

    def test_each_left_corner_needs_its_own_right_corner(self):
        m = tilemap({(20, 1): 0x208C, (20, 10): 0x208C, (20, 20): 0x608C})
        self.assertEqual(bc.dq4windowcheck.corners(m, 0), [(20, 1, '테두리', 0x08C)])
