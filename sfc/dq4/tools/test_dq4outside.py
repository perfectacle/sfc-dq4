import unittest
from types import SimpleNamespace

import dq4outside as o


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
