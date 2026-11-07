"""Without a ROM, the entrance row order and the ルーラ list writes; with rom/dq4.nes and rom/dq5.sfc, the FC
destinations of the ported groups and their names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4fieldtravel as travel  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ4, DQ5 = ROOT / "rom" / "dq4.nes", ROOT / "rom" / "dq5.sfc"


class OrderTest(unittest.TestCase):
    def test_landing_row_leads_its_group(self):
        rows = [{"group": 0x36, "x": 328, "y": 92}, {"group": 0x36, "x": 329, "y": 92},
                {"group": 0x37, "x": 308, "y": 44}, {"group": 0x36, "x": 328, "y": 93}]
        out = travel.landing_rows(rows, [{"group": 0x36, "row": (328, 93)}])
        self.assertEqual(out[0], {"group": 0x36, "x": 328, "y": 93})
        self.assertEqual(sorted(map(str, out)), sorted(map(str, rows)))

    def test_list_slots(self):
        dq5 = bytearray(0x200000)
        o = travel.lorom(travel.RULER_LIST)
        dq5[o:o + travel.RULER_COUNT] = range(1, travel.RULER_COUNT + 1)
        w, *_ = travel.writes(bytes(dq5), [{"slot": 1, "group": 0x36, "ship": None}])
        self.assertEqual(w["at"], "25:85D5")
        new = bytes.fromhex(w["hex"])
        self.assertEqual(new[1], 0x36)
        self.assertEqual(new[0], 1)
        self.assertEqual(new[2:], bytes(range(3, travel.RULER_COUNT + 1)))

    def test_ship_offsets(self):
        dq5 = bytearray(0x200000)
        for table in travel.SHIP_OFFSETS:
            o = travel.lorom(table)
            dq5[o:o + 2 * travel.SHIP_SLOTS] = b"\x07" * (2 * travel.SHIP_SLOTS)
        dests = [{"slot": 1, "group": 0x36, "land": (328, 94), "ship": (315, 67)},
                 {"slot": 2, "group": 0x37, "land": (308, 46), "ship": None}]
        _, *tables = travel.writes(bytes(dq5), dests)
        self.assertEqual([t["at"] for t in tables], ["23:E41E", "23:E438"])
        for t in tables:
            new = bytes.fromhex(t["hex"])
            self.assertEqual(new[2:4], bytes((-13 & 0xFF, -27 & 0xFF)))
            self.assertEqual(new[4:6], b"\x07\x07")
        with self.assertRaises(ValueError):
            travel.writes(bytes(dq5), [{"slot": 1, "group": 0x36, "name": "x", "land": (0, 0), "ship": (200, 0)}])

    def test_ship_cell_boards_from_above_or_below(self):
        # FC block (10,10) is sea with land only to its left (09,10) and above (10,0F).
        def props(x, y):
            return 0x00 if (x, y) in ((0x09, 0x10), (0x10, 0x0F)) else travel.SEA
        self.assertEqual(travel.ship_cell(props, (0x10, 0x10), (0, 0)), (0x20, 0x20))
        self.assertIsNone(travel.ship_cell(props, (0, 0), (0, 0)))
        with self.assertRaises(ValueError):
            travel.ship_cell(props, (0x09, 0x10), (0, 0))

    def test_names_encode_as_dq5(self):
        # Made-up tables: single bytes 10 ハ, 11 ト, 12 り; mark entry 5 バ (84 + key 10), entry 28 パ (83 + key 10).
        # Every other entry is code 0, the blank, which no name uses. Mark entries 0-3 are also single bytes 7F-82
        # (the tables touch), so バ takes entry 5.
        import dq5text
        from dq5map import lorom
        chars = "".join(dq5text.CHARS)
        dq5 = bytearray(0x200000)

        def code(at, c):
            dq5[lorom(at):lorom(at) + 2] = chars.index(c).to_bytes(2, "little")

        for b, c in ((0x10, "ハ"), (0x11, "ト"), (0x12, "り")):
            code(dq5text.STRING_CODES + b * 2, c)
        for k, c in ((5, "バ"), (0x28, "パ")):
            code(dq5text.MARK_CODES + k * 2, c)
            dq5[lorom(dq5text.MARK_KEYS + k)] = 0x10
        dq5 = bytes(dq5)
        self.assertEqual(travel.name_bytes(dq5, "ハトバ"), bytes([0x10, 0x11, 0x84, 0x10]))
        self.assertEqual(travel.name_bytes(dq5, "パはリ"), bytes([0x83, 0x10, 0x10, 0x12]))
        with self.assertRaises(ValueError):
            travel.name_bytes(dq5, "ラ")

    def test_ship_cell_keeps_sea_on_its_right(self):
        # 바다 블록 (10,10) 은 오른쪽 (11,10)·아래 (10,11) 이 땅이다. 내리는 칸이 오른쪽이어도 왼쪽 칸을 고른다.
        def props(x, y):
            return 0x00 if (x, y) in ((0x11, 0x10), (0x10, 0x11)) else travel.SEA
        self.assertEqual(travel.ship_cell(props, (0x10, 0x10), (0x40, 0x40)), (0x20, 0x21))


EXTRA = [{"slot": 12, "group": 0x3D, "listed": True, "maps": (3, 3), "land": (142, 116), "restart": (3, (24, 51))},
         {"slot": 13, "group": 0x3D, "listed": True, "maps": (4, 5), "land": (192, 82), "restart": (4, (14, 47))},
         {"slot": 14, "group": 0x45, "listed": True, "maps": (5, 5), "land": (128, 148), "restart": None},
         {"slot": 15, "group": 0x45, "listed": False, "maps": (0, 4), "land": None, "restart": (2, (8, 19))}]
MAPS = [(0x3D, 3, 3, 12, 1), (0x3D, 4, 5, 13, 1), (0x45, 0, 4, 15, 0), (0x45, 5, 5, 14, 1), (0x45, 6, 11, 0xFF, 0)]
# 다시 시작 자리 표: 산트하임(3D/00)이 텐페(3D/03) 앞이라, 그룹만 보면 산트하임에 선다.
STARTS = bytes((0x3D, 0, 54, 21, 1, 0x80, 0x3D, 3, 24, 51, 1, 0x80, 0x45, 2, 8, 19, 1, 0x80, 0xFF))
RET = 0xFFFFFE


class HookTest(unittest.TestCase):
    """The ルーラ slot hooks on the w65816 interpreter over a blank ROM: each run stops at a JML target of the hook
    or at the RTL to the caller."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dq5" / "tools"))
        rom = bytearray(0x200000)
        for w in travel.hook_writes(EXTRA, MAPS, at=0x3CF000):
            bank, addr = w["at"].split(":")
            o = travel.lorom(int(bank, 16) << 16 | int(addr, 16))
            data = bytes.fromhex(w["hex"])
            rom[o:o + len(data)] = data
        o = travel.lorom(travel.START_TABLE)
        rom[o:o + len(STARTS)] = STARTS
        o = travel.lorom(travel.RULER_LIST)
        rom[o:o + 22] = bytes(range(0x80, 0x80 + 22))
        cls.rom = bytes(rom)
        cls.labels = travel.hook_code(0x3CF000, EXTRA, MAPS)[1]

    def run_hook(self, entry, a=0, x=0, p=0x30, **wram):
        """Run from `entry` as if called by JSL; stop at a JML target of the hooks or at the return."""
        from w65816 import Cpu
        ram = bytearray(0x20000)
        for name, value in wram.items():
            at = int(name[1:], 16)
            size = 2 if name in ("_B6", "_B8") else 1
            ram[at:at + size] = value.to_bytes(size, "little")
        cpu = Cpu(self.rom, ram)
        cpu.a, cpu.x, cpu.p = a, x, p
        cpu.push(0xFF)
        cpu.push16(0xFFFD)
        cpu.pbr, cpu.pc = entry >> 16, entry & 0xFFFF
        stops = {travel.LAND_BACK, travel.LAND_DONE, travel.IN_LIST, travel.SLOT_OF, travel.SAVE_BACK,
                 travel.SAVE_DONE, travel.WIPE_BACK, travel.WIPE_DONE, travel.CONTINUE_BACK, travel.CONTINUE_DONE, RET}
        while (cpu.pbr << 16 | cpu.pc) not in stops:
            if cpu.steps > 5000:
                raise AssertionError(f"no stop by {cpu.pbr:02X}:{cpu.pc:04X}")
            cpu.step()
        return cpu.pbr << 16 | cpu.pc, cpu

    def test_land_takes_the_slot_cell(self):
        at, cpu = self.run_hook(travel.LAND_SITE, a=12)
        self.assertEqual(at, travel.LAND_DONE)
        self.assertEqual((cpu.r16(0x0B50), cpu.r16(0x0B52), cpu.wram[0x0B54]), (142, 116, 0x3D))
        self.assertEqual((cpu.r16(0x00), cpu.r16(0x02)), (142, 116))
        at, cpu = self.run_hook(travel.LAND_SITE, a=1)
        self.assertEqual((at, cpu.x & 0xFF), (travel.LAND_BACK, 1))

    def test_visit_sets_the_slot_of_the_map(self):
        # $BD 의 위 3비트는 맵 번호가 아니다(2A:F397 AND #$1F).
        at, cpu = self.run_hook(self.labels["visit"], _BC=0x3D, _BD=0x23)
        self.assertEqual((at, cpu.p & 1), (RET, 0))
        self.assertEqual((bytes(cpu.wram[0x2030:0x2033]), cpu.wram[0x2193]), (bytes((0, 0x10, 0)), 0x8C))
        for group, number in ((0x45, 2), (0x45, 7)):
            at, cpu = self.run_hook(self.labels["visit"], _BC=group, _BD=number, _2193=0x36)
            self.assertEqual((at, cpu.p & 1), (RET, 0))
            self.assertEqual((bytes(cpu.wram[0x2030:0x2033]), cpu.wram[0x2193]), (bytes(3), 0x36))
        at, cpu = self.run_hook(self.labels["visit"], _BC=0x3D, _BD=0)
        self.assertEqual((at, cpu.a & 0xFF), (travel.IN_LIST, 0x3D))

    def test_chimera_takes_a_marked_town(self):
        at, cpu = self.run_hook(self.labels["chimera"], a=0x8D)
        self.assertEqual((at, cpu.x & 0xFF), (RET, 13))
        at, cpu = self.run_hook(self.labels["chimera"], a=0x3D)
        self.assertEqual((at, cpu.a & 0xFF, cpu.x & 0xFF), (travel.SLOT_OF, 0x3D, 0))

    def test_ship_finds_the_slot_by_its_landing(self):
        at, cpu = self.run_hook(self.labels["ship"], a=0x3D, _B6=192, _B8=82)
        self.assertEqual((at, cpu.x & 0xFF, cpu.a & 0xFF), (RET, 13, 0x3D))
        at, cpu = self.run_hook(self.labels["ship"], a=0x3D, _B6=78, _B8=148)
        self.assertEqual((at, cpu.x & 0xFF, cpu.a & 0xFF), (travel.SLOT_OF, 0, 0x3D))

    def test_save_keeps_the_slot_of_the_map(self):
        for group, number, slot in ((0x3D, 3, 12), (0x45, 2, 15)):
            at, cpu = self.run_hook(travel.SAVE_SITE, _BC=group, _BD=number)
            self.assertEqual((at, cpu.x & 0xFF, cpu.a & 0xFF), (travel.SAVE_DONE, slot, group))
        for group, number in ((0x45, 7), (0x3D, 0), (0x36, 0)):
            at, cpu = self.run_hook(travel.SAVE_SITE, _BC=group, _BD=number)
            self.assertEqual((at, cpu.x & 0xFF, cpu.a & 0xFF), (travel.SAVE_BACK, 0, group))

    def test_restart_rows_of_the_slots(self):
        for site, done in ((travel.WIPE_SITE, travel.WIPE_DONE), (travel.CONTINUE_SITE, travel.CONTINUE_DONE)):
            # 전멸 쪽은 저장한 칸 바이트에 밤 비트(bit7)가 붙은 채로 온다.
            at, cpu = self.run_hook(site, a=0x8C if site == travel.WIPE_SITE else 0x0C)
            self.assertEqual((at, cpu.x & 0xFF), (done, 6))
            at, cpu = self.run_hook(site, a=15)
            self.assertEqual((at, cpu.x & 0xFF), (done, 12))
        at, cpu = self.run_hook(travel.CONTINUE_SITE, a=12)
        self.assertEqual(cpu.a & 0xFF, 0x3D)
        at, cpu = self.run_hook(travel.WIPE_SITE, a=14)
        self.assertEqual((at, cpu.x & 0xFF, cpu.a & 0xFF), (travel.WIPE_BACK, 14, 0x80 + 14))
        at, cpu = self.run_hook(travel.CONTINUE_SITE, a=2)
        self.assertEqual((at, cpu.x & 0xFF), (travel.CONTINUE_BACK, 2))

    def test_restart_takes_the_saved_slot(self):
        # 마지막에 들어간 그룹(A)이 아니라 저장한 칸. 아직 저장하지 않은 16 은 FC 1장 시작 교회(バトランド)의 칸
        for saved, want in ((0x8C, 0x8C), (0x0F, 0x0F), (0x16, travel.slot_of_fc(travel.FIRST_CHURCH_FC)),
                            (0x96, travel.slot_of_fc(travel.FIRST_CHURCH_FC))):
            at, cpu = self.run_hook(self.labels["restart_slot"], a=0x37, _2033=saved)
            self.assertEqual((at, cpu.a & 0xFF), (RET, want))

    def test_chapter_slot_is_saran(self):
        self.assertEqual(travel.slot_of_fc(0x02), 2)
        self.assertEqual(travel.slot_of_fc(0x13), 15)
        self.assertEqual(travel.chapter_slot_code(), bytes((0xA9, 15, 0x8F, 0x33, 0x20, 0x7E)))
        with self.assertRaises(ValueError):
            travel.slot_of_fc(0x2E)

    def test_rom_restarts_reads_the_hook_table(self):
        self.assertEqual(travel.rom_restarts(self.rom, at=0x3CF000), {12: (0x3D, 3), 13: (0x3D, 4), 15: (0x45, 2)})
        self.assertEqual(travel.rom_restarts(bytes(0x200000)), {})

    def test_restart_rows(self):
        self.assertEqual(travel.restart_rows(EXTRA), [bytes((0x3D, 3, 24, 51, 1, 0x80)), bytes((0x3D, 4, 14, 47, 1, 0x80)),
                                                      bytes((0x45, 2, 8, 19, 1, 0x80))])

    def test_map_rows_block_the_other_parts(self):
        links = {0x3D: [{"fc": 0x01}, {"fc": 0x0E}], 0x45: [{"fc": 0x13}, {"fc": 0x2E}]}
        place = {(0x01, 0): (0x3D, 0), (0x01, 1): (0x3D, 1), (0x0E, 0): (0x3D, 2), (0x13, 0): (0x45, 0),
                 (0x2E, 0): (0x45, 1), (0x2E, 1): (0x45, 2)}
        extra = [{"fc": 0x0E, "group": 0x3D, "slot": 12, "maps": (2, 2), "listed": True},
                 {"fc": 0x13, "group": 0x45, "slot": 15, "maps": (0, 0), "listed": False}]
        self.assertEqual(travel.map_rows(links, place, extra),
                         [(0x3D, 2, 2, 12, 1), (0x45, 0, 0, 15, 0), (0x45, 1, 2, 0xFF, 0)])


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), "rom/dq4.nes and rom/dq5.sfc")
class RomTest(unittest.TestCase):
    def test_destinations_land_below_an_entrance(self):
        import dq4groupbuild
        from kr_patch.fc import ines
        prg = ines.prg(DQ4.read_bytes())
        found = dq4groupbuild.doors(prg)
        dests = travel.destinations(prg, dq4groupbuild.LINKS, found)
        # FC destination order: キングレオ, サントハイム, バトランド, エンドール, ボンモール, ブランカ, ハバリア, イムル,
        # たびだちのむら, モンバーバラ, レイクナバ, コーミズ.
        self.assertEqual([d["group"] for d in dests], [0x44, 0x3D, 0x36, 0x40, 0x3F, 0x46, 0x43, 0x37, 0x3C, 0x41, 0x3E,
                                                          0x42])
        bat = dests[2]
        self.assertEqual((bat["land"], bat["row"]), ((328, 94), (328, 93)))
        for d in dests:
            self.assertIn(d["row"], found[d["fc"]][0])

    def test_names_encode_as_dq5(self):
        dq5 = DQ5.read_bytes()
        # 0B's first name in the original ROM.
        self.assertEqual(travel.name_bytes(dq5, "ラインハット"), bytes([104, 67, 111, 91, 112, 85]))
        self.assertEqual(travel.name_bytes(dq5, "バトランド"), bytes([0x84, 91, 85, 104, 111, 0x84, 85]))
        with self.assertRaises(ValueError):
            travel.name_bytes(dq5, "漢")


if __name__ == "__main__":
    unittest.main()
