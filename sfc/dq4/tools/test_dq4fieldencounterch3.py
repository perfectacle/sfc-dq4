import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4fieldencounter as m  # noqa: E402

DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'
# fc/dq4/docs/dq4-chapter3-format.md 「전투 뒤 물건」
DOC_TABLE = [(16, 0x01), (4, 0x02), (2, 0x04), (2, 0x05), (0, 0x06), (4, 0x25), (4, 0x26), (2, 0x27), (0, 0x28),
             (4, 0x3D), (4, 0x3E), (4, 0x46), (4, 0x47), (4, 0x53), (2, 0x54), (4, 0x56)]


class ModelTests(unittest.TestCase):
    def test_roll_walks_from_the_start_slot_and_wraps(self):
        table = [(4, k) for k in range(16)]
        self.assertEqual(m.drop_roll(table, 1, 14, [9, 3]), 15)
        self.assertEqual(m.drop_roll(table, 1, 15, [9, 3]), 0)
        self.assertIsNone(m.drop_roll(table, 1, 0, [4] * 16))

    def test_zero_threshold_is_the_level(self):
        table = DOC_TABLE
        self.assertEqual(m.drop_roll(table, 0x28, 4, [0x27]), 4)
        self.assertEqual(m.drop_roll(table, 0x28, 4, [0x28, 0x03]), 5)

    def test_chance_matches_the_doc(self):
        # 레벨 1·10·20 에서 21.8%·27.2%·33.0%
        for level, want in ((1, 0.218), (10, 0.272), (20, 0.330)):
            self.assertAlmostEqual(m.drop_chance(DOC_TABLE, level), want, places=3)

    def test_code_and_sites(self):
        blob, labels = m.ch3_code([(78, 0x210, 0), (35, 0x210, 0)], [(t, k) for k, (t, _) in enumerate(DOC_TABLE)])
        self.assertLess(len(blob), 0x200)
        self.assertEqual(blob[labels['thresholds'] - m.CH3_CODE_AT:][:16], bytes(t for t, _ in DOC_TABLE))
        zones = blob[labels['zones'] - m.CH3_CODE_AT:labels['thresholds'] - m.CH3_CODE_AT]
        self.assertEqual(zones, bytes((0xB4, 0x06, 0x10, 0x02, 0, 0, 0x02, 0x03, 0x10, 0x02, 0, 0)))
        # 훅 자리는 원래 명령 경계에서 같은 길이로 덮는다
        self.assertEqual(len(m.NIGHT_ORIG), 6)
        self.assertEqual(len(m.WEIGHT_ORIG), 5)
        self.assertEqual(len(m.DROP_ORIG), 7)
        # 25:8966 의 BNE 는 JSL 뒤 두 바이트에서 25:8970 으로 간다
        self.assertEqual(m.DROP_SITE + 4 + 2 + 4, 0x258970)


@unittest.skipUnless(DQ4.is_file() and DQ5.is_file(), 'rom/dq4.nes and rom/dq5.sfc')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()

    def test_fc_table_is_the_doc(self):
        self.assertEqual(m.fc_drop_table(self.prg), DOC_TABLE)

    def fc_roll(self, level, start, rolls):
        """FC 12:$91DE 를 6502 해석기로: rand(16)·톨네코 레벨·rand(256) 을 넣어 얻은 칸(없으면 None)."""
        import dq4cpu
        prg = bytearray(self.prg)
        o = m.FC_BANK * 0x4000
        # BRK 17 0F(rand(16))·BRK 63 73(일행에서 인물 5)·BRK 0F 33(레벨)을 같은 길이의 JSR 로 바꿔 값을 넣는다
        for addr, stub in ((0x91E7, 0xFFF0), (0x91F4, 0xFFF1), (0x91F9, 0xFFF2)):
            self.assertEqual(prg[o + (addr & 0x3FFF)], 0x00)
            prg[o + (addr & 0x3FFF):o + (addr & 0x3FFF) + 3] = bytes((0x20, stub & 0xFF, stub >> 8))
        cpu = dq4cpu.CPU(bytes(prg), m.FC_BANK)
        cpu.wram[0x615A - 0x6000] = 2
        left = list(rolls)

        class Hit(Exception):
            pass

        def put(v):
            def hook(c):
                c.a = v() if callable(v) else v
            return hook
        cpu.hooks.update({0xFFF0: put(start), 0xFFF1: put(0), 0xFFF2: put(level), 0xC891: put(lambda: left.pop(0))})
        cpu.stubs.update({0xFFF0, 0xFFF1, 0xFFF2, 0xC891})

        def hit(c):
            raise Hit(c.x)
        cpu.hooks[0x9246] = hit
        try:
            cpu.call(0x91DE)
        except Hit as e:
            return e.args[0], len(rolls) - len(left)
        return None, len(rolls) - len(left)

    def test_model_matches_the_fc_routine(self):
        table = m.fc_drop_table(self.prg)
        rng = random.Random(273)
        cases = [(level, rng.randrange(16), [rng.randrange(256) for _ in range(16)])
                 for level in (0x01, 0x28, 0x63) for _ in range(91)]
        cases += [(0x63, 4, [0x62]), (0x63, 4, [0x63] + [0xFF] * 15), (0x01, 8, [0x00])]
        for level, start, rolls in cases:
            got, used = self.fc_roll(level, start, rolls)
            want = m.drop_roll(table, level, start, rolls)
            self.assertEqual(got, want, (level, start, rolls))
            self.assertEqual(used, 16 if want is None else (want - start) % 16 + 1)

    def test_items_have_dq5_counterparts(self):
        items = m.dq5_drop_items(self.prg, self.dq5)
        self.assertEqual(len(set(items)), 16)

    def test_masks_take_out_the_night_slots_by_day(self):
        # 구역 15 칸 10(ホイミスライム 한 무리), 16·17 칸 4·10(メラゴースト)은 밤에만. 3장 구역의 칸 0·6 은 비어 밤 마스크 0
        self.assertEqual(m.ch3_masks(self.prg, 0x14), (0, 0))
        self.assertEqual(m.ch3_masks(self.prg, 0x15), (1 << 9, 0))
        self.assertEqual(m.ch3_masks(self.prg, 0x16), (1 << 4 | 1 << 9, 0))
        self.assertEqual(m.ch3_masks(self.prg, 0x17), (1 << 4 | 1 << 9, 0))

    def test_chapter3_zones_are_the_reached_ones(self):
        # dq4fieldencounter.CH3_ZONES 는 FC 3장 일행이 걸어 닿는 필드 구역과 그 입구 던전의 구역
        import dq4encounter
        import dq4fieldencounter
        field, groups = set(), set()
        for bridge in (False, True):
            cells, hits = dq4encounter.ch3_reach(self.prg, bridge)
            field |= {dq4encounter.zone_at(self.prg, 2, x, y) for x, y in cells}
            groups |= {g for g, _ in hits}
        lists = dict(dq4encounter.dungeon_lists(self.prg)[0][2])
        dungeon = {z for g in groups if g in lists for z in lists[g] if z != 0xFF}
        self.assertEqual(set(dq4fieldencounter.CH3_FIELD), field)
        self.assertEqual(set(dq4fieldencounter.CH3_DUNGEON), dungeon)


if __name__ == '__main__':
    unittest.main()
