import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4growth as g  # noqa: E402


def fake_tables(base=0):
    stats = [[base + lv * 10 + k for k in range(g.STAT_COUNT)] for lv in range(g.LEVELS)]
    exp = [base + lv * 1000 + 0x10000 * (lv // 50) for lv in range(g.LEVELS)]
    return stats, exp


def fake_chapters():
    return [fake_tables(), fake_tables(5)]


def jml(addr):
    return bytes((0x5C, *addr.to_bytes(3, 'little')))


def run_gain(data, labels, kind, level, now, nxt):
    """문턱 훅을 명령 하나씩 따라 돈다(이 훅이 쓰는 명령만, M 16). 돌려준 값은 $0997,Y 에 남는 문턱."""
    mem = {g.KIND: kind, g.LEVEL: level, g.NOW: now, g.NEXT: nxt}
    pc, a, carry = labels['gain'] - g.GROWTH_AT, 0, 0
    word = lambda i: data[i] | data[i + 1] << 8  # noqa: E731
    while True:
        op = data[pc]
        if op == 0xC2:
            pc += 2
        elif op == 0xAD:
            a, pc = mem[word(pc + 1)], pc + 3
        elif op == 0xB9:
            a, pc = mem[word(pc + 1)], pc + 3
        elif op == 0x29:
            a, pc = a & word(pc + 1), pc + 3
        elif op == 0xD0:
            pc += 2 + (data[pc + 1] if a else 0)
        elif op == 0x1A:
            a, pc = (a + 1) & 0xFFFF, pc + 1
        elif op == 0x4A:
            a, pc = a >> 1, pc + 1
        elif op == 0x18:
            carry, pc = 0, pc + 1
        elif op in (0x69, 0x79):
            v = word(pc + 1) if op == 0x69 else mem[word(pc + 1)]
            a, carry, pc = (a + v + carry) & 0xFFFF, (a + v + carry) >> 16, pc + 3
        elif op == 0x99:
            mem[word(pc + 1)], pc = a, pc + 3
        elif op == 0x6B:
            return mem[g.NOW]
        else:
            raise AssertionError(f'모르는 명령 {op:02X}')


class CodeTest(unittest.TestCase):
    def test_hooks_return_to_the_original_paths(self):
        data, labels = g.code(fake_chapters())
        self.assertEqual(labels['stat'], g.GROWTH_AT)
        # 원래 첫 명령을 먼저 하고, 사람 0 이 아니면 그 뒤로 돌아간다
        self.assertEqual(data[:4], g.STAT_ORIG)
        o = labels['exp_hook'] - g.GROWTH_AT
        self.assertEqual(data[o:o + 5], g.EXP_ORIG)
        for target in (g.STAT_GO, g.STAT_DONE, g.EXP_GO, g.EXP_RTS, g.REACH_RTS):
            self.assertIn(jml(target), data)
        # 사람 0 레코드로 가른다(CPY #$9E41)
        self.assertEqual(data.count(bytes((0xC0, 0x41, 0x9E))), 2)
        self.assertLessEqual(g.GROWTH_AT + len(data), g.SPACE_END)

    def test_chapter_two_moves_into_the_second_table(self):
        data, labels = g.code(fake_chapters())
        self.assertEqual(labels['stats1'] - labels['stats'], g.table_size())
        self.assertEqual(labels['exp1'] - labels['exp'], g.table_size())
        # 표를 읽는 세 곳마다 2장 flag(7E:2208 bit4)를 보고 X 에 표 크기를 더한다
        (flag, mask), _ = g.CHAPTERS[1]
        test = bytes((0xAF, *flag.to_bytes(3, 'little'), 0x29, mask, 0x00, 0xF0, 6,
                      0x8A, 0x18, 0x69, *g.table_size().to_bytes(2, 'little'), 0xAA))
        self.assertEqual(data.count(test), 3)
        for name in ('stat_pick', 'exp_pick'):
            o = labels[name] - g.GROWTH_AT
            self.assertEqual(data[o - len(test):o], test)
            self.assertEqual(data[o], 0xBF)          # 바로 표를 읽음

    def test_calls(self):
        _, labels = g.code(fake_chapters())
        w = {x['at']: bytes.fromhex(x['hex']) for x in g.calls(labels)}
        self.assertEqual(w['23:F12D'], jml(labels['stat']))
        self.assertEqual(w['23:EDF6'], jml(labels['exp_hook']) + b'\xea')
        # JSL 뒤 BRA 가 원래 13바이트의 끝(23:EC83)으로 넘어간다
        self.assertEqual(w['23:EC76'][:6], bytes((0x22, *labels['gain'].to_bytes(3, 'little'), 0x80, 7)))
        self.assertEqual(len(w['23:EC76']), len(g.GAIN_ORIG))

    def test_tables(self):
        chapters = fake_chapters()
        data, labels = g.code(chapters)
        for k, (stats, exp) in enumerate(chapters):
            for lv in (0, 1, 10, 99, 100):
                for s in range(g.STAT_COUNT):
                    o = labels['stats'] - g.GROWTH_AT + k * g.table_size() + (lv * g.STAT_COUNT + s) * 2
                    self.assertEqual(int.from_bytes(data[o:o + 2], 'little'), stats[lv][s])
                o = labels['exp'] - g.GROWTH_AT + k * g.table_size() + lv * 4
                self.assertEqual(int.from_bytes(data[o:o + 4], 'little'), exp[lv])

    def test_gain_threshold(self):
        data, labels = g.code(fake_chapters())
        # 사람 0: 문턱 = 곡선(새 레벨) + 새 레벨 / 2 + 10(FC 12:$9DB3). 지금 레벨 9 → 새 레벨 10, 곡선 41 → 56
        self.assertEqual(run_gain(data, labels, kind=0, level=9, now=37, nxt=41), 41 + 10 // 2 + 10)
        self.assertEqual(run_gain(data, labels, kind=0, level=0, now=0, nxt=13), 13 + 0 + 10)
        # 그 밖: DQ5 그대로 값(L) × 1.5
        self.assertEqual(run_gain(data, labels, kind=0x85, level=9, now=37, nxt=41), 37 + 18)


@unittest.skipUnless(g.DQ4.exists(), 'rom/dq4.nes 가 없음')
class FcTest(unittest.TestCase):
    def test_table_matches_the_fc_measurement(self):
        stats, exp = g.tables()
        start = g.first_record()
        for lv, (want, nxt) in g.RYAN_MEASURED.items():
            got = list(stats[lv])
            # 실측은 장 시작 표의 최대 HP(27)에서 곡선 증가분대로 오른 값
            got[0] += start['hp'] - stats[1][0]
            self.assertEqual((got, exp[lv + 1]), (want, nxt), lv)

    def test_first_record(self):
        start = g.first_record()
        want, nxt = g.RYAN_MEASURED[1]
        self.assertEqual([start[k] for k in ('hp', 'mp', 'str', 'agi', 'int', 'luck', 'vit')] + [start['next']],
                         want + [nxt])


class RomTest(unittest.TestCase):
    def test_reads_the_hooked_table(self):
        chapters = fake_chapters()
        data, labels = g.code(chapters)
        rom = bytearray(0x400000)
        o = g.lorom(g.GROWTH_AT)
        rom[o:o + len(data)] = data
        o = g.lorom(g.STAT_AT)
        rom[o:o + 4] = jml(labels['stat'])
        self.assertEqual(g.hooked(bytes(rom)), (labels['stats'], labels['exp']))
        self.assertEqual(g.stats_at(bytes(rom), 0, 10), chapters[0][0][10])
        self.assertEqual(g.stats_at(bytes(rom), 0, 10, 1), chapters[1][0][10])
        self.assertEqual(g.exp_at(bytes(rom), 0, 11), chapters[0][1][11])
        self.assertEqual(g.exp_at(bytes(rom), 0, 11, 1), chapters[1][1][11])
        self.assertIsNone(g.hooked(bytes(0x400000)))


if __name__ == '__main__':
    unittest.main()
