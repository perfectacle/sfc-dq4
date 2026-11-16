"""주문·행동 표(dq5spell): MP·범위 바이트, 처리 루틴 첫머리 읽기, 피해량·내성 배율, 원소와 갑옷 값, 명령줄.
표 풀기는 합성 롬으로, 명령줄은 롬이 있으면 본다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5spell as S  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from test_dq5spc import run_main  # noqa: E402

ROM = Path(__file__).resolve().parents[4] / 'rom' / 'dq5.sfc'


def put(d, addr, raw):
    d[lorom(addr):lorom(addr) + len(raw)] = raw


def spell_rom():
    d = bytearray(0x200000)
    put(d, S.COSTS + 1, bytes([0x80 | 0x20 | 4, 0x1F, 0x1E, 0x1D | 0x60]))
    routines = {1: 0xC000, 2: 0xC010, 3: 0xC020, 0x40: 0xC030}
    for n, a in routines.items():
        put(d, S.HANDLERS + n * 2, a.to_bytes(2, 'little'))
    put(d, 0x20C000, bytes.fromhex('E2 20 A2 52 A9 03 4C 70 AB'))
    put(d, 0x20C010, bytes.fromhex('A9 02 86 10 20 41 AE'))
    put(d, 0x20C020, bytes.fromhex('A9 01 EA'))
    put(d, 0x20C030, bytes.fromhex('A2 55 A9 03 4C 07 B3'))
    put(d, S.TARGETS + 1 * 2, (0x9771).to_bytes(2, 'little'))
    put(d, S.TARGETS + 2 * 2, (0x1234).to_bytes(2, 'little'))
    put(d, S.AMOUNTS + 3 * 2, bytes([20, 8]))
    put(d, S.AMOUNTS + 1 * 2, bytes([0xFE, 0]))
    put(d, S.RESIST, bytes([0xFF, 0x80, 0x40, 0x00, 0xFF, 0xFF, 0xA9, 0x00]))
    put(d, S.ELEMENTS, bytes([0x01, 0x02, 0, 0, 0, 0, 0, 0x01]))
    put(d, S.BREATH_ELEMENTS, bytes([0x10]))
    put(d, S.ARMOR, bytes([0x01, 0x30, 5, 0x03, 0x31, 0xFE, 0x10, 0x32, 9, 0]))
    return Rom(d)


class TableTest(unittest.TestCase):
    def setUp(self):
        self.rom = spell_rom()

    def test_cost(self):
        self.assertEqual(S.cost(self.rom, 1), (4, 1, True))
        self.assertEqual(S.cost(self.rom, 2), (None, 0, False))
        self.assertEqual(S.cost(self.rom, 3), (36, 0, False))
        self.assertEqual(S.cost(self.rom, 4), ('all', 3, False))

    def test_handler_reads_lda_ldx_and_jump(self):
        self.assertEqual(S.handler(self.rom, 1), (0xC000, 3, 0x52, 0xAB70))
        self.assertEqual(S.handler(self.rom, 2), (0xC010, 2, None, 0xAE41))
        self.assertEqual(S.handler(self.rom, 3), (0xC020, 1, None, None))

    def test_spread_and_amount(self):
        self.assertEqual(S.spread(self.rom, 1), (0x9771, '그룹'))
        self.assertEqual(S.spread(self.rom, 2), (0x1234, '1234'))
        self.assertEqual(S.amount(self.rom, 3), (20, 8))
        self.assertEqual(S.amount(self.rom, 0x41), (300, 0))

    def test_describe(self):
        self.assertTrue(S.describe(self.rom, 1).endswith('MP4 적 하나 대상그룹 루틴C000 양03=20~27 내성52'))
        self.assertTrue(S.describe(self.rom, 2).endswith('MP- 편 자신 대상1234 루틴C010 아군2/8'))

    def test_resist_damage_and_status(self):
        self.assertEqual(S.resist_rates(self.rom), [0xFF, 0x80, 0x40, 0x00])
        self.assertEqual(S.resist_rates(self.rom, easy=True), [0xFF, 0xFF, 0xA9, 0x00])
        self.assertEqual([S.damage_range(self.rom, 1, lv) for lv in range(4)], [(20, 27), (10, 13), (5, 6), (0, 0)])
        self.assertIsNone(S.damage_range(self.rom, 2, 0))
        self.assertEqual(S.status_chance(self.rom, 0), 256)
        self.assertEqual(S.status_chance(self.rom, 2, easy=True), 0xA9)

    def test_elements_armor_and_party_damage(self):
        self.assertEqual([S.element(self.rom, n) for n in (1, 2, 0x39, 0x3A, 0x8E, 0x30)], [1, 2, 1, 2, 0x10, 0])
        self.assertEqual(S.armor_entries(self.rom), [(0x01, 0x30, 5), (0x03, 0x31, -2), (0x10, 0x32, 9)])
        self.assertEqual(S.party_damage(self.rom, 0x40), (20, 27))
        self.assertEqual(S.party_damage(self.rom, 0x40, (0x30,)), (15, 22))
        self.assertEqual(S.party_damage(self.rom, 0x40, (0x30, 0x31, 0x32)), (17, 24))
        self.assertIsNone(S.party_damage(self.rom, 2))


@unittest.skipUnless(ROM.exists(), '롬이 없음(rom/dq5.sfc)')
class RomTest(unittest.TestCase):
    def test_main_modes(self):
        code, out = run_main(S, [str(ROM)])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), S.COUNT)
        self.assertTrue(all(ln.split()[0] == f'{n:02X}' for n, ln in enumerate(out.splitlines())))
        code, out = run_main(S, [str(ROM), '--table'])
        lines = out.splitlines()
        self.assertEqual(len(lines), 0x65)
        self.assertTrue(any(' 단계0~3: ' in ln for ln in lines))
        self.assertTrue(any(' 일행에게 ' in ln and '갑옷 값을 뺌' in ln for ln in lines))
        self.assertTrue(any(' 회복 ' in ln for ln in lines))
        self.assertTrue(any(S.SPECIAL[0xB2D5] in ln for ln in lines))
        rom = Rom(ROM.read_bytes())
        code, out = run_main(S, [str(ROM), '--armor'])
        self.assertEqual(len(out.splitlines()), len(S.armor_entries(rom)))


if __name__ == '__main__':
    unittest.main()
