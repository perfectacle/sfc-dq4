from pathlib import Path
import unittest
from types import SimpleNamespace

import dq4outside as o

ROM = Path(__file__).resolve().parents[3] / 'rom' / 'dq4.nes'


def fc_map(w, h, buf, outside):
    return SimpleNamespace(w=w, h=h, buf=buf, outside=outside)


class CellTests(unittest.TestCase):
    def test_first_zone0_outside_block_as_dq5_cell(self):
        # zone bits are the top 3: 0x21 is block 1 in zone 1 and does not count
        m = fc_map(3, 2, [0x05, 0x21, 0x05, 0x05, 0x01, 0x05], 0x01)
        self.assertEqual(o.cell(m), (2, 2))

    def test_no_zone0_outside_block_keeps_black(self):
        m = fc_map(2, 1, [0x21, 0x05], 0x01)
        self.assertIsNone(o.cell(m))
        self.assertEqual(o.way((0x36, 0), m), 0)

    def test_only_chapter1_and_prologue_groups(self):
        m = fc_map(1, 1, [0x01], 0x01)
        self.assertEqual(o.way((0x36, 0), m), o.OUTSIDE_WAY)
        self.assertEqual(o.way((0x3C, 1), m), o.OUTSIDE_WAY)
        self.assertEqual(o.way((0x3D, 0), m), 0)


class ReachTests(unittest.TestCase):
    def test_walls_split_zones_and_doors_join_them(self):
        # a ring of zone-1 walls (0x23) round zone-0 floor (0x01) and zone-1 floor (0x21); prop 80 = wall, 94 = door
        props = {0x01: 0x00, 0x03: 0x80, 0x04: 0x94}
        w = 0x23
        m = SimpleNamespace(w=5, h=3, buf=[w, w, w, w, w, w, 0x01, w, 0x21, w, w, w, w, w, w], blocks={'prop': props})
        self.assertEqual(o.reachable_zones(m, {(3, 1)}), {1})
        m.buf[7] = 0x24
        self.assertEqual(o.reachable_zones(m, {(3, 1)}), {0, 1})

    def test_reaching_the_edge_reaches_zone0(self):
        # off the edge is the zone-0 outside block, and 3A/03 wraps its corridor into zone-0 cells there
        props = {0x01: 0x00, 0x03: 0x80}
        m = SimpleNamespace(w=3, h=1, buf=[0x23, 0x21, 0x21], blocks={'prop': props})
        self.assertEqual(o.reachable_zones(m, {(1, 0)}), {0, 1})

    def test_only_fc_maps_hide_zone0(self):
        m = fc_map(1, 1, [0x01], 0x01)
        self.assertFalse(o.zone0_hidden(m))
        self.assertEqual(o.hidden_cells(m), set())


@unittest.skipUnless(ROM.is_file(), 'local source ROM not present')
class RomZoneTests(unittest.TestCase):
    """FC draws zone 0 and the map outside black while the party stands in another zone (0F:$D4E6). The prologue
    cellar 14/01 has zone-0 floor only in the corners beside its stair walls, which no one reaches, so FC never shows
    its outside block there; filling the outside with it painted the whole screen around the cellar with floor."""

    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())

    def map(self, g, k):
        return o.dq4block.Map(self.prg, g, k)

    def test_cellar_outside_stays_black(self):
        cellar = self.map(0x14, 0x01)
        self.assertEqual(o.cell(cellar), (0, 0))
        self.assertTrue(o.zone0_hidden(cellar))
        self.assertEqual(o.way((0x3C, 0x01), cellar), 0)
        self.assertEqual(len(o.hidden_cells(cellar)), 18)

    def test_reached_zone0_keeps_the_outside_block(self):
        # 3A/03: ホイミン stands in zone 0, reached round the map edge
        for g, k, target in ((0x14, 0x00, (0x3C, 0x00)), (0x02, 0x00, (0x36, 0x00)), (0x12, 0x00, (0x37, 0x00)),
                             (0x3A, 0x03, (0x3B, 0x03))):
            with self.subTest(map=f'{g:02X}/{k:02X}'):
                m = self.map(g, k)
                self.assertFalse(o.zone0_hidden(m))
                self.assertEqual(o.way(target, m), o.OUTSIDE_WAY)

    def test_ported_maps_with_hidden_zone0(self):
        import dq4environmentmap as em
        import dq4environmentrom as er
        fc = {name: (g, k) for g, k, _, name in em.all_maps(self.prg)}
        hidden = sorted(f'{er.GROUPS[name][0]:02X}/{er.GROUPS[name][1]:02X}' for name in er.GROUPS
                        if o.hidden_cells(self.map(*fc[name])))
        self.assertEqual(hidden, ['3C/01', '40/01', '40/05', '42/02', '42/03', '42/04', '43/04', '44/04'])


class PatchTests(unittest.TestCase):
    def test_rows_from_the_environment_report(self):
        report = {"burland": {"map": "36/00", "outside": [34, 36]}, "12-02": {"map": "37/02", "outside": None}}
        self.assertEqual(o.rows(report), [(0x36, 0x00, 34, 36)])

    def test_writes_fit_and_point_the_way_at_the_stub(self):
        writes = o.writes([(0x36, 0x00, 34, 36), (0x3C, 0x01, 0, 0)])
        by_at = {w["at"]: bytes.fromhex(w["hex"]) for w in writes}
        self.assertEqual(by_at["01:98C4"], (o.STUB_AT & 0xFFFF).to_bytes(2, "little"))
        stub = by_at["00:FFA8"]
        self.assertEqual(stub[:4], bytes((0x22, *o.ROUTINE_AT.to_bytes(3, "little"))))
        self.assertEqual(stub[4:], bytes((0x4C, 0xC3, 0xBA)))
        code = by_at["57:FC00"]
        self.assertTrue(code.endswith(bytes((0x36, 0x00, 34, 36, 0x3C, 0x01, 0, 0, 0xFF))))
        self.assertEqual(code[:7], bytes((0x08, 0xC2, 0x10, 0xDA, 0x5A, 0xE2, 0x30)))


if __name__ == "__main__":
    unittest.main()
