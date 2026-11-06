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
    return [fake_tables(k * 5) for k in range(len(g.TABLES))]


def jml(addr):
    return bytes((0x5C, *addr.to_bytes(3, 'little')))


def signed(b):
    return b - 0x100 if b & 0x80 else b


def run_pick(data, labels, name, y, flag_on, x=0):
    """표 고르기(pick)를 명령 하나씩 따라 돈다(M·X 16, 이 루틴이 쓰는 명령만). 이름표 name 에 닿을 때의 X."""
    pc, end = labels[f'{name}_start'] - g.GROWTH_AT, labels[name] - g.GROWTH_AT
    word = lambda i: data[i] | data[i + 1] << 8  # noqa: E731
    a, z, stack = 0, False, []
    while pc != end:
        op = data[pc]
        if op == 0xC0:
            z, pc = y == word(pc + 1), pc + 3
        elif op == 0xAF:
            addr = data[pc + 1] | data[pc + 2] << 8 | data[pc + 3] << 16
            a = (g.CHAPTER2[1] if flag_on else 0) if addr == g.CHAPTER2[0] else 0
            pc += 4
        elif op == 0x29:
            a, pc = a & word(pc + 1), pc + 3
            z = a == 0
        elif op == 0xA9:
            a, pc = word(pc + 1), pc + 3
        elif op in (0xD0, 0xF0, 0x80):
            take = op == 0x80 or (op == 0xF0) == z
            pc += 2 + (signed(data[pc + 1]) if take else 0)
        elif op == 0x48:
            stack.append(a)
            pc += 1
        elif op == 0x8A:
            a, pc = x, pc + 1
        elif op == 0x18:
            pc += 1
        elif op == 0x63:
            a, pc = (a + stack[-1]) & 0xFFFF, pc + 2
        elif op == 0xAA:
            x, pc = a, pc + 1
        elif op == 0x68:
            a, pc = stack.pop(), pc + 1
        else:
            raise AssertionError(f'모르는 명령 {op:02X}')
    return x


def run_gain(data, labels, kind, level, now, nxt):
    """문턱 훅을 명령 하나씩 따라 돈다(이 훅이 쓰는 명령만, M 16). 돌려준 값은 $0997,Y 에 남는 문턱."""
    mem = {g.KIND: kind, g.LEVEL: level, g.NOW: now, g.NEXT: nxt}
    pc, a, carry, z = labels['gain'] - g.GROWTH_AT, 0, 0, False
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
        elif op == 0xC9:
            z, pc = a == word(pc + 1), pc + 3
        elif op == 0xF0:
            pc += 2 + (data[pc + 1] if z else 0)
        elif op == 0x80:
            pc += 2 + data[pc + 1]
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
        # 원래 첫 명령을 먼저 하고, 표를 쓰는 사람이 아니면 그 뒤로 돌아간다
        self.assertEqual(data[:4], g.STAT_ORIG)
        o = labels['exp_hook'] - g.GROWTH_AT
        self.assertEqual(data[o:o + 5], g.EXP_ORIG)
        for target in (g.STAT_GO, g.STAT_DONE, g.EXP_GO, g.EXP_RTS, g.REACH_RTS):
            self.assertIn(jml(target), data)
        # 표를 쓰는 사람의 레코드(CPY #레코드)로 가른다: 사람 0·9·5
        for person in (0, 9, 5):
            self.assertGreaterEqual(data.count(bytes((0xC0, *g.record_of(person).to_bytes(2, 'little')))), 2)
        self.assertLessEqual(g.GROWTH_AT + len(data), g.SPACE_END)

    def test_tables_follow_one_another(self):
        _, labels = g.code(fake_chapters())
        for k in range(1, len(g.TABLES)):
            self.assertEqual(labels[f'stats{k}'] - labels['stats'], k * g.table_size())
            self.assertEqual(labels[f'exp{k}'] - labels['exp'], k * g.table_size())

    def test_pick_moves_x_into_the_person_table(self):
        data, labels = g.code(fake_chapters())
        cases = {(0, False): 0, (0, True): 1, (9, False): 2, (9, True): 2, (5, False): 3, (5, True): 3}
        for name in ('stat_pick', 'exp_pick', 'reach_pick'):
            self.assertEqual(data[labels[name] - g.GROWTH_AT] in (0xBF, 0xA0), True, name)
            for (person, on), k in cases.items():
                with self.subTest(name=name, person=person, chapter2=on):
                    got = run_pick(data, labels, name, g.record_of(person), on, x=0x24)
                    self.assertEqual(got, 0x24 + k * g.table_size())
                    self.assertEqual(g.table_index(person, int(on)), k)
        self.assertIsNone(g.table_index(3))
        self.assertIsNone(g.table_index(0x85))

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
        # 표를 쓰는 사람(0·9·5): 문턱 = 곡선(새 레벨) + 새 레벨 / 2 + 10(FC 12:$9DB3). 레벨 9 → 10, 곡선 41 → 56
        for kind in (0, 9, 5):
            self.assertEqual(run_gain(data, labels, kind=kind, level=9, now=37, nxt=41), 41 + 10 // 2 + 10)
        self.assertEqual(run_gain(data, labels, kind=0, level=0, now=0, nxt=13), 13 + 0 + 10)
        # 그 밖: DQ5 그대로 값(L) × 1.5
        for kind in (0x85, 0x09 | 0x80, 3):
            self.assertEqual(run_gain(data, labels, kind=kind, level=9, now=37, nxt=41), 37 + 18)


@unittest.skipUnless(g.DQ4.exists(), 'rom/dq4.nes 가 없음')
class FcTest(unittest.TestCase):
    def test_tables_match_the_fc_measurement(self):
        """FC 롬을 돌려 잰 값(fc/dq4/tools/dq4levelup.py)과 표. 최대 HP 는 장 시작 표에서 곡선 증가분대로 오른 값."""
        sets = g.chapter_tables()
        for k, (_, _, who) in enumerate(g.TABLES):
            stats, exp = sets[k]
            start = g.first_record(who=who)
            for lv, (want, nxt) in g.MEASURED[who].items():
                with self.subTest(who=who, level=lv):
                    got = list(stats[lv])
                    got[0] += start['hp'] - stats[1][0]
                    self.assertEqual((got, exp[lv + 1]), (want, nxt))

    def test_first_record(self):
        start = g.first_record()
        want, nxt = g.RYAN_MEASURED[1]
        self.assertEqual([start[k] for k in ('hp', 'mp', 'str', 'agi', 'int', 'luck', 'vit')] + [start['next']],
                         want + [nxt])

    def test_recruit_records_are_the_fc_start(self):
        """합류 기록(dq4ch2event.RECRUITS)의 1레벨 값이 FC 실측 1레벨과 같다. MP 는 FC 곡선 1레벨."""
        import dq4ch2event as ev
        for r in ev.RECRUITS:
            who = dict(((9, g.FC_KIRYL), (5, g.FC_BREY)))[r['person']]
            hp, mp, st, agi, it, luck, vit = g.MEASURED[who][1][0]
            self.assertEqual((r['hp'], r['mp'], r['agility'], r['stats']), (hp, mp, agi, (st, vit, it, luck)), r['name'])
        hp, mp, st, agi, it, luck, vit = g.ALENA_MEASURED[1][0]
        s = ev.ALENA_STATS
        self.assertEqual((s['hp'], s['mp'], s['agility'], s['stats'], s['next']),
                         (hp, mp, agi, (st, vit, it, luck), g.ALENA_MEASURED[1][1]))


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
        for kind, k in ((9, 2), (5, 3)):
            self.assertEqual(g.stats_at(bytes(rom), kind, 10, 1), chapters[k][0][10])
            self.assertEqual(g.exp_at(bytes(rom), kind, 11), chapters[k][1][11])
        self.assertIsNone(g.hooked(bytes(0x400000)))


if __name__ == '__main__':
    unittest.main()
