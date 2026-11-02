import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4growth as g  # noqa: E402


def fake_tables():
    stats = [[lv * 10 + k for k in range(g.STAT_COUNT)] for lv in range(g.LEVELS)]
    exp = [lv * 1000 + 0x10000 * (lv // 50) for lv in range(g.LEVELS)]
    return stats, exp


def jml(addr):
    return bytes((0x5C, *addr.to_bytes(3, 'little')))


class CodeTest(unittest.TestCase):
    def test_hooks_return_to_the_original_paths(self):
        stats, exp = fake_tables()
        data, labels = g.code(stats, exp)
        self.assertEqual(labels['stat'], g.GROWTH_AT)
        # 원래 첫 명령을 먼저 하고, 사람 0 이 아니면 그 뒤로 돌아간다
        self.assertEqual(data[:4], g.STAT_ORIG)
        o = labels['exp_hook'] - g.GROWTH_AT
        self.assertEqual(data[o:o + 5], g.EXP_ORIG)
        for target in (g.STAT_GO, g.STAT_DONE, g.EXP_GO, g.EXP_RTS):
            self.assertIn(jml(target), data)
        # 사람 0 레코드로 가른다(CPY #$9E41)
        self.assertEqual(data.count(bytes((0xC0, 0x41, 0x9E))), 2)

    def test_calls(self):
        stats, exp = fake_tables()
        _, labels = g.code(stats, exp)
        w = {x['at']: bytes.fromhex(x['hex']) for x in g.calls(labels)}
        self.assertEqual(w['23:F12D'], jml(labels['stat']))
        self.assertEqual(w['23:EDF6'], jml(labels['exp_hook']) + b'\xea')
        # JSL 뒤 BRA 가 원래 13바이트의 끝(23:EC83)으로 넘어간다
        self.assertEqual(w['23:EC76'][:6], bytes((0x22, *labels['gain'].to_bytes(3, 'little'), 0x80, 7)))
        self.assertEqual(len(w['23:EC76']), len(g.GAIN_ORIG))

    def test_tables(self):
        stats, exp = fake_tables()
        data, labels = g.code(stats, exp)
        for lv in (0, 1, 10, 99, 100):
            for k in range(g.STAT_COUNT):
                o = labels['stats'] - g.GROWTH_AT + (lv * g.STAT_COUNT + k) * 2
                self.assertEqual(int.from_bytes(data[o:o + 2], 'little'), stats[lv][k])
            o = labels['exp'] - g.GROWTH_AT + lv * 4
            self.assertEqual(int.from_bytes(data[o:o + 4], 'little'), exp[lv])
        self.assertEqual(len(data), labels['exp'] - g.GROWTH_AT + 4 * g.LEVELS)

    def test_gain_threshold(self):
        stats, exp = fake_tables()
        data, labels = g.code(stats, exp)
        o = labels['gain'] - g.GROWTH_AT
        # 종류가 0 이 아니면 DQ5 의 값(L) × 1.5, 0 이면 값(새 레벨) + 새 레벨 / 2 + 10
        self.assertEqual(data[o:o + 5], bytes((0xC2, 0x20, 0xAD, 0xA5, 0x09)))
        self.assertIn(bytes((0xAD, 0xA6, 0x09, 0x29, 0xFF, 0x00, 0x1A, 0x4A, 0x18, 0x69, 0x0A, 0x00, 0x18,
                             0x79, 0xA7, 0x09, 0x99, 0x97, 0x09, 0x6B)), data)
        self.assertIn(g.GAIN_ORIG[2:] + b'\x6b', data)


class RomTest(unittest.TestCase):
    def test_reads_the_hooked_table(self):
        stats, exp = fake_tables()
        data, labels = g.code(stats, exp)
        rom = bytearray(0x400000)
        o = g.lorom(g.GROWTH_AT)
        rom[o:o + len(data)] = data
        o = g.lorom(g.STAT_AT)
        rom[o:o + 4] = jml(labels['stat'])
        self.assertEqual(g.hooked(bytes(rom)), (labels['stats'], labels['exp']))
        self.assertEqual(g.stats_at(bytes(rom), 0, 10), stats[10])
        self.assertEqual(g.exp_at(bytes(rom), 0, 11), exp[11])
        self.assertIsNone(g.hooked(bytes(0x400000)))


if __name__ == '__main__':
    unittest.main()
