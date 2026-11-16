"""3장 북쪽 동굴과 철 금고(dq4ch3safe): 맵 번호·셀, 훅 바이트, 네이티브(w65816 로 돌림), 대화·인물 스크립트, 상자 보상."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ev  # noqa: E402
import dq4ch3safe as safe  # noqa: E402
import dq4itemport  # noqa: E402

DQ5, DQ4 = ROOT / 'rom' / 'dq5.sfc', ROOT / 'rom' / 'dq4.nes'


def _ctx():
    return next(c for c in ev.contexts(0x1000, 0x900) if c.key == 'S')


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def machine(extra=None):
    """(w65816.Cpu, 네이티브 주소): 롬은 이 모듈 코드(5C)와 extra({주소: 바이트}), WRAM 은 0."""
    from w65816 import Cpu
    code, at = safe.native(_ctx())
    rom = bytearray(0x300000)
    for addr, data in ((at['chest_bit'], code), *(extra or {}).items()):
        rom[lorom(addr):lorom(addr) + len(data)] = data
    return Cpu(bytes(rom), bytearray(0x20000)), at


class PlaceTest(unittest.TestCase):
    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_maps_are_the_placed_fc_cave(self):
        from kr_patch.fc import ines
        from dq4groupbuild import placement
        place = placement(ines.prg(DQ4.read_bytes()))
        for fc, name in ((0, safe.ENTRY), (1, safe.GATES), (2, safe.DRY), (3, safe.PIT), (6, safe.VAULT)):
            self.assertEqual(place[0x3D, fc], (safe.GROUP, safe._map(name)), name)

    @unittest.skipUnless(DQ4.exists(), 'FC 롬 없음')
    def test_gates_and_chest_are_the_fc_cells(self):
        from kr_patch.fc import ines
        import dq4block
        import dq4chest
        prg = ines.prg(DQ4.read_bytes())
        m = dq4block.Map(prg, 0x3D, 1)
        prop = lambda x, y: m.blocks["prop"].get(m.buf[y * m.w + x] & 0x1F, 0)  # noqa: E731
        for x, y in ((0x14, 0x0A), (0x08, 0x0E)):
            self.assertEqual(prop(x, y), 0x00)            # 바닥, 바로 위가 수문(B0)
            self.assertEqual(prop(x, y - 1), 0xB0)
        self.assertEqual(safe.RIGHT['rect'], (0x28, 0x15, 0x29, 0x16))
        self.assertEqual(safe.LEFT['rect'], (0x10, 0x1D, 0x11, 0x1E))
        # 물살이 멈추는 줄 바로 아래가 계단·구덩이
        self.assertEqual(prop(0x14, safe.RIGHT['stop'] + 1), 0x08)
        self.assertIn(prop(0x08, safe.LEFT['stop'] + 1), (0x05, 0x0B))
        self.assertEqual([(x, y, c) for _, x, y, c, _ in dq4chest.chests(prg, 0x3D, 6)], [(4, 3, 0xEE)])
        self.assertEqual(safe.CHEST, (8, 7, 9, 8))

    @unittest.skipUnless(DQ4.exists() and DQ5.exists(), '롬 없음')
    def test_the_chest_gives_the_iron_safe(self):
        import dq4chestport
        doc, report = dq4chestport.port(DQ5, DQ4)
        row = next(r for r in report if r['map'] == safe.VAULT)
        self.assertEqual(row['reward'], dq4itemport.IRON_SAFE)


class HookTest(unittest.TestCase):
    def test_hooks_replace_the_whole_sites_and_jump_back(self):
        ctx = _ctx()
        (ea, eo, en), (wa, wo, wn) = safe.hooks(ctx)
        self.assertEqual((ea, eo), (safe.EXIT_SITE, safe.EXIT_ORIG))
        self.assertEqual(len(en), len(eo))
        self.assertEqual(en[:4], bytes((0x22, *safe._al(ctx.at['exit']))))
        self.assertEqual(ea + 6 + en[5], safe.EXIT_DONE)
        self.assertEqual(len(wn), len(wo))
        self.assertEqual(wn[:4], bytes((0x22, *safe._al(ctx.at['wipe']))))
        self.assertEqual(wa + 6 + wn[5], wa + len(wo))

    @unittest.skipUnless(DQ5.exists(), 'DQ5 롬 없음')
    def test_sites_hold_the_original_bytes(self):
        data = DQ5.read_bytes()
        for addr, orig, _ in safe.hooks(_ctx()):
            self.assertEqual(data[lorom(addr):lorom(addr) + len(orig)], orig, f'{addr:06X}')
        # 출구 번호를 읽는 명령과 상자 표 즉값 자리
        self.assertEqual(data[lorom(safe.EXIT_READ):lorom(safe.EXIT_READ) + 2], bytes((0xB1, 0x84)))
        self.assertEqual(data[lorom(safe.CHEST_BANK) - 1], 0xA9)
        self.assertEqual(data[lorom(safe.CHEST_TABLE) - 1], 0xBC)
        self.assertEqual(data[lorom(safe.CHEST_MASKS):lorom(safe.CHEST_MASKS) + 8], bytes(0x80 >> k for k in range(8)))

    def test_code_fits_the_slot(self):
        code, at = safe.native(_ctx())
        start, end = ev.SLOTS['S'].code
        self.assertLessEqual(start + len(code), end)
        self.assertEqual(at['chest_bit'], start)


class RunTest(unittest.TestCase):
    """네이티브를 w65816 로 돌린다."""

    def exit_case(self, group, target, number, drained, relocated=False):
        table = 0x2A9000
        cpu, at = machine({0x2AF7D6: bytes((0xB7 if relocated else 0xB1, 0x84)), table: bytes((0x40 | target, number))})
        w = cpu.wram
        w[0x84], w[0x85], w[0x86] = table & 0xFF, table >> 8 & 0xFF, table >> 16
        w[0x01], w[0xBC], w[0x00BD] = target, group, 0x1F
        w[0x2190 + safe.DRAINED[0]] = safe.DRAINED[1] if drained else 0
        cpu.dbr, cpu.y = 0x2A, 0
        cpu.jsl(at['exit'], max_steps=2000)
        return w[0xBD], cpu.a & 0xFF

    def test_exit_turns_the_gates_into_the_dry_floor_once_drained(self):
        g, gates, dry, pit = safe.GROUP, safe._map(safe.GATES), safe._map(safe.DRY), safe._map(safe.PIT)
        self.assertEqual(self.exit_case(g, gates, 0, False), (gates, 0))
        self.assertEqual(self.exit_case(g, gates, 2, False), (gates, 2))
        self.assertEqual(self.exit_case(g, gates, 0, True), (dry, 0))
        for n in (1, 2, 3):
            self.assertEqual(self.exit_case(g, gates, n, True), (dry, n + 1))
            self.assertEqual(self.exit_case(g, gates, n, True, relocated=True), (dry, n + 1))
        self.assertEqual(self.exit_case(g, pit, 1, True), (pit, 1))
        self.assertEqual(self.exit_case(0x3D, gates, 1, True), (gates, 1))

    def wipe_case(self, chapter3, items, count=1, record=0, gold=1001):
        cpu, at = machine()
        w = cpu.wram
        w[safe.CHAPTER3_AT & 0xFFFF] = 0x08 if chapter3 else 0
        w[safe.PARTY_COUNT & 0xFFFF] = count
        for r in range(4):
            base = (ch2.PARTY_AT & 0xFFFF) + 0x16 + 42 * r
            w[base:base + 12] = b'\xFF' * 12
        base = (ch2.PARTY_AT & 0xFFFF) + 0x16 + 42 * record
        w[base:base + len(items)] = bytes(items)
        w[0x46:0x49] = gold.to_bytes(3, 'little')
        cpu.jsl(at['wipe'], max_steps=5000)
        return int.from_bytes(w[0x43:0x46], 'little')

    def test_wipe_loses_nothing_only_with_the_safe_in_chapter_three(self):
        s = dq4itemport.IRON_SAFE
        self.assertEqual(self.wipe_case(True, [0x42, s]), 0)
        self.assertEqual(self.wipe_case(True, [0x42]), 500)
        self.assertEqual(self.wipe_case(False, [s]), 500)
        self.assertEqual(self.wipe_case(True, [0x01] * 11 + [s]), 0)
        self.assertEqual(self.wipe_case(True, [s], count=2, record=1), 0)
        self.assertEqual(self.wipe_case(True, [s], count=1, record=1), 500)
        self.assertEqual(self.wipe_case(True, [0x42], gold=0x123457), 0x091A2B)

    def test_wipe_keeps_x_and_y(self):
        for items in ([dq4itemport.IRON_SAFE], [0x42]):
            cpu, at = machine()
            cpu.wram[safe.CHAPTER3_AT & 0xFFFF] = 0x08
            cpu.wram[safe.PARTY_COUNT & 0xFFFF] = 1
            cpu.wram[(ch2.PARTY_AT & 0xFFFF) + 0x16] = items[0]
            cpu.p, cpu.x, cpu.y = 0x00, 0x1234, 0x5678
            cpu.jsl(at['wipe'], max_steps=5000)
            self.assertEqual((cpu.x, cpu.y, cpu.p), (0x1234, 0x5678, 0x00))

    def chest_case(self, before, rows):
        table = b''.join(bytes(r) for r in rows) + b'\xFF\xFF'
        cpu, at = machine({0x25FAB5: bytes((0x3C,)), 0x25FAC4: bytes((0x00, 0x88)), 0x3C8800: table,
                           0x25FAE9: bytes(0x80 >> k for k in range(8))})
        cpu.wram[0x2210:0x2210 + len(before)] = before
        cpu.p = 0x00
        cpu.jsl(at['reclose'], max_steps=20000)
        return bytes(cpu.wram[0x2210:0x2210 + len(before)]), cpu.p

    def test_reclose_clears_only_the_vault_chest_bit(self):
        rows = [(0x01, 0x00, 5), (0x3E, 0x08, 4), (0x3E, 0x09, 1), (0x40, 0x00, 3)]
        self.assertEqual(self.chest_case(b'\xFF\xFF', rows), (b'\xFF\xBF', 0x00))     # n = 9
        self.assertEqual(self.chest_case(b'\xFF\xFF', rows[1:])[0], b'\xF7\xFF')     # n = 4
        self.assertEqual(self.chest_case(b'\xFF\xFF', [(0x01, 0x00, 5)])[0], b'\xFF\xFF')

    def on_chest(self, x, y, opened):
        rows = [(0x01, 0x00, 5), (0x3E, 0x09, 1)]
        table = b''.join(bytes(r) for r in rows) + b'\xFF\xFF'
        cpu, at = machine({0x25FAB5: bytes((0x3C,)), 0x25FAC4: bytes((0x00, 0x88)), 0x3C8800: table,
                           0x25FAE9: bytes(0x80 >> k for k in range(8))})
        cpu.wram[0x3020], cpu.wram[0x3080] = x, y
        cpu.wram[0x2210] = 0x04 if opened else 0
        cpu.jsl(at['on_chest'], max_steps=20000)
        return cpu.a & 0xFFFF

    def test_on_chest_needs_the_cell_and_the_open_bit(self):
        self.assertEqual(self.on_chest(8, 7, True), 0)
        self.assertEqual(self.on_chest(9, 8 | 0x80, True), 0)
        self.assertEqual(self.on_chest(8, 7, False), 1)
        self.assertEqual(self.on_chest(10, 7, True), 1)
        self.assertEqual(self.on_chest(8, 9, True), 1)


class ScriptTest(unittest.TestCase):
    def test_talks_and_scripts(self):
        ctx = _ctx()
        bodies = safe.talk_scripts(ctx)
        self.assertEqual(len(bodies), len(safe.TALKS))
        scripts = {s['address']: s['commands'] for s in safe.scripts(ctx)}
        self.assertEqual(set(scripts), {a for a, _ in safe.SCRIPTS.values()})
        talk_here = ch2.native()[1]['talk_here']
        for name in ('right', 'left'):
            cmds = scripts[safe.SCRIPTS[name][0]]
            calls = [c['args'] for c in cmds if c['op'] == '37']
            self.assertEqual(calls[0], list(safe._al(talk_here)))
            self.assertEqual(calls[-1], list(safe._al(ctx.at[f'push_{name}'])))

    def test_floods_end_with_a_warp_to_the_fc_place(self):
        code, at = safe.native(_ctx())
        for side, spec in (('right', safe.RIGHT), ('left', safe.LEFT)):
            o = at[f'flood_{side}'] - at['chest_bit']
            body = code[o:o + 13]
            if side == 'left':
                self.assertEqual(body[:3], bytes((0x10, *safe.DRAINED)))
                body = body[3:]
            mp, (x, y) = spec['to']
            self.assertEqual(body[:2], bytes((safe.DOWN, 2 * spec['stop'] + 1 - spec['rect'][3])))
            self.assertEqual(body[2:10], bytes((0x90, safe.GROUP, safe._map(mp), x, y, 0x01, 0x80, 0xFF)))

    def test_flags_are_in_the_slot(self):
        self.assertTrue(all(f[0] in ev.SLOTS['S'].flags for f in safe.FLAGS))
        self.assertEqual(len({f[1] for f in safe.FLAGS}), len(safe.FLAGS))

    def test_messages_fit_the_window(self):
        import dq4ch1event
        for name, parts in safe.MESSAGES.items():
            self.assertTrue(parts, name)
        self.assertIn('button', safe.MESSAGES)
        del dq4ch1event


if __name__ == '__main__':
    unittest.main()
