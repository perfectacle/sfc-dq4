"""Without a ROM, the FC block -> DQ5 block map, the map file, entrance cells and parking; with rom/dq4.nes, FC
field 0 and the entrances of the ported groups."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldport as port  # noqa: E402

ROM = Path(__file__).resolve().parents[3] / "rom" / "dq4.nes"


class MapTest(unittest.TestCase):
    def test_blocks_follow_fc_and_the_rest_is_sea(self):
        grid = port.world([[0x00, 0x02, 0x06], [0x04, 0x10, 0x16]])
        self.assertEqual(grid[0:3], [port.SEA, 2, port.MOUNTAIN])
        self.assertEqual(grid[port.SIZE:port.SIZE + 3], [354, 18, 22])
        self.assertEqual(grid[3], port.SEA)
        self.assertEqual(grid[2 * port.SIZE], port.SEA)
        self.assertEqual(len(grid), port.SIZE * port.SIZE)

    def test_parking_island(self):
        grid = port.world([[0x02]])
        x, y = port.ISLAND
        island = [grid[(y + dy) * port.SIZE + x + dx] for dy in range(3) for dx in range(3)]
        self.assertEqual(island, [port.MOUNTAIN] * 9)
        self.assertEqual((port.PARK[0] >> 1, port.PARK[1] >> 1), (x + 1, y + 1))
        with self.assertRaises(ValueError):
            port.world([[0x02] * (x + 1)])

    def test_unknown_block(self):
        with self.assertRaises(ValueError):
            port.world([[0x18]])

    def test_blocks_stay_below_512(self):
        # dq5fieldwrite needs --planes-at and the chest patch's glow cell from 512 up.
        self.assertLess(max(port.BLOCKS.values()), 512)

    def test_pack(self):
        grid = [0] * (port.SIZE * port.SIZE)
        grid[1], grid[port.SIZE] = 366, 9
        raw = port.pack(grid)
        self.assertEqual(len(raw), 131072)
        self.assertEqual(raw[2:4], bytes((0x6E, 0x01)))
        self.assertEqual(raw[port.SIZE * 2:port.SIZE * 2 + 2], bytes((9, 0)))
        with self.assertRaises(ValueError):
            port.pack(grid[:-1])


class DoorTest(unittest.TestCase):
    # A two-block castle (06, 07) at (10,10)-(11,10) with sea below and grass around.
    PROPS = {(10, 10): 0x06, (11, 10): 0x07, (10, 11): 0x83}

    def props(self, x, y):
        return self.PROPS.get((x, y), 0x00)

    def test_cells_of_a_block(self):
        self.assertEqual(port.cells(10, 10), [(20, 20), (21, 20), (20, 21), (21, 21)])
        self.assertEqual(port.stand(10, 10), (20, 21))

    def test_right_half_enters_too(self):
        self.assertEqual(port.entrance_blocks(self.props, [(10, 10)]), [(10, 10), (11, 10)])

    def test_door_leaves_onto_the_first_walkable_neighbour(self):
        found, leave = port.door(self.props, [(10, 10)])
        self.assertEqual(found, port.cells(10, 10) + port.cells(11, 10))
        # Below is sea, so the left neighbour.
        self.assertEqual(leave, port.stand(9, 10))

    def test_door_with_no_way_out(self):
        props = lambda x, y: 0x00 if (x, y) == (10, 10) else 0x80  # noqa: E731
        with self.assertRaises(ValueError):
            port.door(props, [(10, 10)])


class ParkTest(unittest.TestCase):
    ARRIVALS = {0x01: {"world_code": 1}, 0x09: {"world_code": 2}, 0x0E: {"world_code": 0}}

    def test_world_of(self):
        self.assertEqual(port.world_of(0x01, self.ARRIVALS), 0)
        self.assertEqual(port.world_of(0x09, self.ARRIVALS), 1)
        self.assertIsNone(port.world_of(0x0E, self.ARRIVALS))
        self.assertEqual(port.world_of(0x05, self.ARRIVALS), 0)
        self.assertEqual(port.world_of(0x52, self.ARRIVALS), 0)
        self.assertIsNone(port.world_of(0x54, self.ARRIVALS))

    def test_only_world_zero_moves(self):
        rows = [{"table": "main", "index": 0, "group": 0x01, "x": 331, "y": 67},
                {"table": "main", "index": 1, "group": 0x09, "x": 22, "y": 93}]
        self.assertEqual(port.park(rows, self.ARRIVALS), [{"group": 0x01, "x": port.PARK[0], "y": port.PARK[1]},
                                                          {"group": 0x09, "x": 22, "y": 93}])


class WarpPatchTest(unittest.TestCase):
    def test_finds_the_group_row_of_the_moved_table(self):
        sys.path.insert(0, str(port.DQ5_TOOLS))
        from dq5map import lorom
        rom = bytearray(0x200000)
        ref = lorom(port.MAIN_TABLE_REF)
        rom[ref:ref + 3] = (0x3C8000).to_bytes(3, "little")
        table = lorom(0x3C8000)
        rom[table:table + 11] = bytes((0x02, 1, 0, 2, 0, 0x01, 3, 0, 4, 0, 0xFF))
        self.assertEqual(port.warp_patch(bytes(rom), 328, 95), f"{table + 6:X}=48015F00")


@unittest.skipUnless(ROM.is_file(), "local source ROM not present")
class FieldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(ROM.read_bytes())

    def test_field_zero_fits(self):
        grid, _ = port.fc_field(self.prg)
        self.assertEqual((len(grid[0]), len(grid)), (253, 253))
        world = port.world(grid)
        self.assertEqual(world[0x2E * port.SIZE + 0xA4], port.BLOCKS[0x12])

    def test_port_entrances(self):
        import dq4groupbuild
        doors = dq4groupbuild.doors(self.prg)
        # 02's castle enters from both halves; 41 from both caves, each two blocks wide.
        self.assertEqual(doors[0x02][0], port.cells(0xA4, 0x2E) + port.cells(0xA5, 0x2E))
        self.assertEqual(len(doors[0x41][0]), 16)
        # 30's tower is on an islet with sea below: it leaves onto the grass on its left.
        self.assertEqual(doors[0x30][1], port.stand(0x87, 0x17))


if __name__ == "__main__":
    unittest.main()
