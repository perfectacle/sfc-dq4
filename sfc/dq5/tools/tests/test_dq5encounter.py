"""전투 조우 표(dq5encounter): 구역 레코드 풀기, 칸별 무리와 확률, 고정·이벤트 무리, 필드 격자, 트레이스·걸음 기록 검사, 명령줄.
구역 레코드 풀기는 합성 롬으로, 나머지는 롬이 있으면 본다."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5encounter as E  # noqa: E402
from dq5field import world_blocks  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def area_rom():
    d = bytearray(0x200000)
    slots = [0x40 | 0x08 | 2, 0x80 | 1, 0xC0, 0x80, 0x80 | 3, 0x80, 0x80 | 0x10 | 1, 0x80, 0x80, 0, 0x10 | 1]
    put(d, E.AREAS + 2 * E.AREA_SIZE, bytes([7, *slots, *range(0x20, 0x2A)]))
    put(d, E.RATE_COEF, bytes(range(0x50, 0x58)))
    put(d, E.COUNT_BASE, bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    put(d, E.COUNT_RANGE, bytes([1, 3, 1, 2, 1, 1, 1, 1, 4, 1]))
    put(d, E.FIXED + 2 * 6, bytes([0x30, 0xFF, 0x31, 0x12, 0, 0x03]))
    put(d, E.EVENT_GROUPS + 3 * E.EVENT_SIZE, bytes([0x81, 0x40, 0xFF, 0x41, 0xFF, 1, 0, 2, 0, 9, 8, 7, 6]))
    put(d, E.FIELD_GRIDS[1][1] + 2 * E.FIELD_WIDTH + 3, b'\x2a')
    return Rom(d)


class AreaTest(unittest.TestCase):
    def setUp(self):
        self.rom = area_rom()

    def test_count_range(self):
        self.assertEqual(E.count_range(self.rom, 0), (1, 1))
        self.assertEqual(E.count_range(self.rom, 1), (2, 4))

    def test_area_fields(self):
        ar = E.area(self.rom, 2)
        self.assertEqual(ar['level'], 7)
        self.assertEqual(ar['weights'], [2, 1, 0, 0, 3, 0, 1, 0, 0, 0, 1])
        self.assertEqual(ar['count_codes'][0], 1)
        self.assertEqual(ar['species_weights'], [1, 2, 3])
        self.assertEqual(ar['coef'], 0x50 + 7)  # 칸 4·5·6 의 bit7 이 모두 켜짐
        self.assertEqual((ar['flag_1000'], ar['flag_1010'], ar['fixed_night_only'], ar['fixed_group']), (2, 1, 1, 2))
        self.assertEqual(ar['monsters'], list(range(0x20, 0x2A)))

    def test_groups(self):
        ar = E.area(self.rom, 2)
        got = E.groups(self.rom, ar)
        self.assertEqual([(s, kind) for s, _, kind, _ in got], [(0, 'mixed'), (1, 'mixed'), (4, 'mixed'), (6, 'single'),
                                                                (10, 'fixed')])
        self.assertAlmostEqual(sum(p for _, p, _, _ in got), 1.0)
        self.assertEqual(got[0][3], [(0x20, E.count_range(self.rom, 1 + 7))])
        self.assertEqual(got[3][3], [(0x26, (3, 3))])
        self.assertEqual(got[4][3], [(0x30, (2, 4)), (0x31, (1, 1))])

    def test_fixed_and_event_groups(self):
        self.assertEqual(E.fixed_group(self.rom, 2), [(0x30, (2, 4), 2), (0x31, (1, 1), 3)])
        self.assertEqual(E.event_group(self.rom, 3), (0x81, [(0x40, 1), (0x41, 2)], [9, 8, 7, 6]))

    def test_field_helpers(self):
        self.assertEqual([E.field_grid_index(a, b) for a, b in ((0, 0), (1, 0), (5, 0), (0, 1), (3, 2))], [0, 1, 2, 3, 4])
        self.assertEqual(E.field_area(self.rom, 1, 3 * 32 + 5, 2 * 32), 0x2A)
        grid = E.field_grid(self.rom, E.FIELD_GRIDS[1][1], 3)
        self.assertEqual((len(grid), len(grid[0]), grid[2][3]), (3, E.FIELD_WIDTH, 0x2A))


def kv(**fields):
    return ' '.join(f'{k}={v:04X}' for k, v in fields.items())


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Rom(ROM.read_bytes())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_map_entries(self):
        entries = list(E.map_entries(self.rom))
        self.assertTrue(all(len(e) == 6 for _, _, e in entries))
        bc, bd, e = entries[5]
        self.assertEqual(E.map_entry(self.rom, bc, bd), e)
        self.assertIsNone(E.map_entry(self.rom, 0x7F, 0))
        self.assertIsNone(E.map_entry(self.rom, 0, 0x7F))

    def trace_line(self, at, area, y, ids, counts):
        words = [ids[0] | ids[1] << 8, ids[2] | ids[3] << 8, counts[0] | counts[1] << 8, counts[2] | counts[3] << 8]
        return (f'100 {at} X={area * E.AREA_SIZE:04X} Y={y:04X} ' +
                ' '.join(f'{k}={w:04X}' for k, w in zip(('7E1001', '7E1003', '7E1005', '7E1007'), words)))

    def test_check_trace(self):
        ar = next(E.area(self.rom, n) for n in range(E.AREA_COUNT)
                  if E.area(self.rom, n)['weights'][5] and sum(1 for w in E.area(self.rom, n)['weights'][:5] if w) >= 2)
        n, s = ar['n'], 5
        lo, _ = E.count_range(self.rom, ar['count_codes'][s])
        mixed = [k for k in range(5) if ar['weights'][k]][:2]
        mons = [ar['monsters'][k] for k in mixed]
        cnts = [E.count_range(self.rom, ar['count_codes'][k] + 7)[0] for k in mixed]
        fixed = E.fixed_group(self.rom, ar['fixed_group'])
        lines = [
            'skip',
            '100 000000 X=0000',
            self.trace_line('23E9B0', n, s, [ar['monsters'][s], 0xFF, 0xFF, 0xFF], [lo, 0, 0, 0]),
            self.trace_line('23EA40', n, 0, mons + [0xFF, 0xFF], cnts + [0, 0]),
            self.trace_line('23E98F', n, 0, [m for m, _, _ in fixed] + [0xFF] * (4 - len(fixed)),
                            [c[0] for _, c, _ in fixed] + [0] * (4 - len(fixed))),
        ]
        path = self.dir / 'trace.txt'
        path.write_text('\n'.join(lines) + '\n')
        code, out = run_main(E, [str(ROM), '--trace', str(path)])
        self.assertEqual(code, 0)
        self.assertIn('3개 중 0개 어긋남', out)
        self.assertEqual(sum(ln.startswith('OK ') for ln in out.splitlines()), 3)
        lines.append(self.trace_line('23E9B0', n, s, [ar['monsters'][s] ^ 1, 0xFF, 0xFF, 0xFF], [lo, 0, 0, 0]))
        path.write_text('\n'.join(lines) + '\n')
        code, out = run_main(E, [str(ROM), '--trace', str(path)])
        self.assertEqual(code, 1)
        self.assertIn('4개 중 1개 어긋남', out)

    def test_check_steps(self):
        bc, bd, e = next((bc, bd, e) for bc, bd, e in E.map_entries(self.rom) if e[0] != 0xFF)
        grid = world_blocks(self.rom, 0)
        x, y = 0x300, 0x280
        a = E.field_area(self.rom, 0, x, y)
        t = E.field_terrain(self.rom, grid, x, y)
        day, night = (self.rom.u8(base + t) for base in (E.FIELD_RATE_DAY, E.FIELD_RATE_NIGHT))
        common = {'7E00B6': x, '7E00B8': y, '7E1948': 0}
        lines = [
            '1 0082AF',
            f'1 0082AF A={e[0]:02X} Y={E.INDOOR_RATE:02X} ' + kv(**{'7E00BC': bd << 8 | bc, '7E00BE': 0x80, '7E00B6': 0,
                                                                    '7E00B8': 0, '7E1948': 0, '7E075E': 0, '7E21C9': 0}),
            f'2 0082AF A={a:02X} Y={day:02X} ' + kv(**{'7E00BC': 0, '7E00BE': 0, **common, '7E075E': 0, '7E21C9': 0}),
            f'3 0082AF A={a:02X} Y={night * 8 & 0xFF:02X} ' + kv(**{'7E00BC': 0, '7E00BE': 0, **common, '7E075E': 0xF0,
                                                                    '7E21C9': 3}),
        ]
        path = self.dir / 'steps.txt'
        path.write_text('\n'.join(lines) + '\n')
        code, out = run_main(E, [str(ROM), '--steps', str(path)])
        self.assertEqual(code, 0)
        self.assertIn('3번 중 0번 어긋남', out)
        self.assertIn(f'실내 {bc:02X}/{bd:02X}: 구역 {e[0]:02X} 조우율 07', out)
        lines.append(f'4 0082AF A={a ^ 1:02X} Y={day:02X} ' + kv(**{'7E00BC': 0, '7E00BE': 0, **common, '7E075E': 0,
                                                                    '7E21C9': 0}))
        path.write_text('\n'.join(lines) + '\n')
        code, out = run_main(E, [str(ROM), '--steps', str(path)])
        self.assertEqual(code, 1)
        self.assertIn(f'NG  필드 격자 $1949=0 $1948=0 칸 ({x >> 5},{y >> 5})', out)

    def test_main_tables(self):
        code, out = run_main(E, [str(ROM)])
        self.assertEqual(code, 0)
        self.assertEqual(sum(ln.startswith('구역 ') for ln in out.splitlines()), E.AREA_COUNT)
        self.assertIn('선제/기습', out)
        _, out = run_main(E, [str(ROM), '--events'])
        self.assertEqual(len(out.splitlines()), E.EVENT_COUNT)
        _, out = run_main(E, [str(ROM), '--maps'])
        self.assertTrue(all('구역($1948=0/1/2)' in ln for ln in out.splitlines()))
        _, out = run_main(E, [str(ROM), '--field'])
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith('지형별 조우율(낮)'))
        self.assertEqual(len(lines), 2 + len(E.FIELD_GRIDS) + sum(r for _, _, r in E.FIELD_GRIDS))

    def test_main_one_map(self):
        bc, bd, e = next((bc, bd, e) for bc, bd, e in E.map_entries(self.rom) if e[0] != 0xFF)
        code, out = run_main(E, [str(ROM), f'{bc:X}', f'{bd:X}'])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(f'{bc:02X}/{bd:02X} 구역($1948=0/1/2) {e[0]:02X}'))
        self.assertEqual(sum(ln.startswith('구역 ') for ln in out.splitlines()), len({x for x in e[:3] if x != 0xFF}))
        code, out = run_main(E, [str(ROM), '7F', '0'])
        self.assertEqual((code, out.strip()), (1, '그런 맵 없음'))


if __name__ == '__main__':
    unittest.main()
