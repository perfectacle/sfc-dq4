import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / 'dq5' / 'tools'))

import dq4localprice as L  # noqa: E402

DQ5_ROM = TOOLS.parents[2] / 'rom' / 'dq5.sfc'


class Patched:
    """원래 롬 위에 쓰기를 얹은 롬(u8 만)."""

    def __init__(self, rom, writes):
        self.rom, self.bytes = rom, {}
        for w in writes:
            bank, addr = w['at'].split(':')
            at = int(bank, 16) << 16 | int(addr, 16)
            for k, b in enumerate(bytes.fromhex(w['hex'])):
                self.bytes[at + k] = b

    def u8(self, addr):
        return self.bytes.get(addr, 0) if addr >> 16 >= 0x40 else self.bytes.get(addr, self.rom.u8(addr))


class TableTest(unittest.TestCase):
    def test_rows_end_with_ff(self):
        self.assertEqual(L.table([(0x71, 0x0C, 10)]), bytes((0x71, 0x0C, 0x0A, 0x00, 0xFF)))

    def test_refuses_bad_rows(self):
        for rows in ([(0xFF, 0x0C, 10)], [(0x71, 0x0C, 10), (0x71, 0x0C, 20)], [(0x71, 0x0C, 0x10000)]):
            with self.assertRaises(ValueError):
                L.table(rows)

    def test_price_keeps_registers_like_brk(self):
        # PHX / PHY / PHP 로 시작해 PLP / PLY / PLX 로 끝나고, 값 루틴은 디스패처 입구(X = 4)로 부른다
        data, labels = L.code(L.AT, [(0x71, 0x0C, 10)])
        price = labels['price'] - L.AT
        self.assertEqual(data[price:price + 10], bytes((0xDA, 0x5A, 0x08, 0xE2, 0x10, 0xA2, 0x04, 0x22, 0xF8, 0xA3)))
        done = labels['done'] - L.AT
        self.assertEqual(data[done:done + 7], bytes((0xC2, 0x20, 0x68, 0x28, 0x7A, 0xFA, 0x60)))

    def test_no_rows_no_writes(self):
        self.assertEqual(L.writes(None, []), [])


@unittest.skipUnless(DQ5_ROM.is_file(), 'rom/dq5.sfc 가 필요')
class RomTest(unittest.TestCase):
    def setUp(self):
        import dq5item
        self.rom = dq5item.Rom(DQ5_ROM.read_bytes())

    def test_sites_are_the_buy_reads(self):
        writes = L.writes(self.rom, [(0x71, 0x0C, 10)])
        _, labels = L.code(L.AT, [(0x71, 0x0C, 10)])
        at = {w['at']: w['hex'] for w in writes}
        self.assertEqual(at['04:B6DC'], f"22 {labels['list'] & 0xFF:02X} {labels['list'] >> 8 & 0xFF:02X} 57 EA EA EA")
        for site in ('06:DCD7', '06:DDF4'):
            self.assertEqual(at[site], f"22 {labels['buy'] & 0xFF:02X} {labels['buy'] >> 8 & 0xFF:02X} 57 EA EA")
        # 팔기(06:DF5C SEP #$30 / BRK 94 02)는 DQ5 값 그대로: FC 도 팔 때는 물건 값(15:$B387)
        self.assertNotIn('06:DF5E', at)

    def test_parse_reads_back_the_rows(self):
        rows = [(0x71, 0x0C, 10), (0x72, 0xA1, 300)]
        self.assertEqual(L.parse(Patched(self.rom, L.writes(self.rom, rows))), {(0x71, 0x0C): 10, (0x72, 0xA1): 300})
        self.assertEqual(L.parse(self.rom), {})


if __name__ == '__main__':
    unittest.main()
