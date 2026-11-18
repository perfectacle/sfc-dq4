import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4monport  # noqa: E402
import dq4monspecial as S  # noqa: E402

DQ4, DQ5 = ROOT / 'rom' / 'dq4.nes', ROOT / 'rom' / 'dq5.sfc'


class Done(Exception):
    pass


class TableTests(unittest.TestCase):
    def test_fc_actions_use_the_new_numbers(self):
        table = dq4monport.fc_actions()
        for fc, n in S.FC_ACTIONS.items():
            self.assertEqual(table[fc], f'{n:02X}')

    def test_summon_numbers_match_monport(self):
        self.assertEqual((S.SUMMON_SAME, S.SUMMON_FIXED, S.SUMMON_FIXED_FC),
                         (dq4monport.SUMMON_SAME, dq4monport.SUMMON_FIXED, dq4monport.SUMMON_FIXED_FC))

    def test_messages_are_translated(self):
        import dq4battlemsg
        import dq4battletexts
        for n in (S.MSG_HERB, S.MSG_PIORIMU, S.MSG_MAHOSTE, S.MSG_BOOMERANG, S.MSG_BLOCKED):
            self.assertIn(n, dq4battletexts.SOURCE)
            self.assertNotIn(n, dq4battlemsg.UNUSED)


@unittest.skipUnless(DQ4.exists() and DQ5.exists(), 'rom/dq4.nes and rom/dq5.sfc')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq5map import lorom
        from kr_patch.fc import ines
        cls.prg = ines.prg(DQ4.read_bytes())
        cls.dq5 = DQ5.read_bytes()
        same = dq4monport.summon_code()[1]['same']
        cls.writes = S.writes(cls.dq5, cls.prg, same)
        rom = bytearray(cls.dq5) + bytes(max(0, 0x400000 - len(cls.dq5)))
        for w in cls.writes:
            at = int(w['at'][:2], 16) << 16 | int(w['at'][3:], 16)
            data = bytes.fromhex(w['hex'])
            rom[lorom(at):lorom(at) + len(data)] = data
        cls.rom = bytes(rom)
        cls.labels = S.far_code(same)[1]

    def fc(self, bank, addr, n=1):
        o = bank * 0x4000 + (addr & 0x3FFF)
        return bytes(self.prg[o:o + n])

    def test_fc_record_numbers_are_these_actions(self):
        # 레코드 번호 → 행동 ID(dq4data.monster_action), ID → 처리 루틴(11:$A3FA)
        import dq4data
        want = {0x5F: (0x70, 0x9FDD), 0x1E: (0x23, 0x9FB6), 0x49: (0x5A, 0xA104), 0x1B: (0x1D, 0x9CFA),
                0x64: (0x75, 0xB16C)}
        for rec, (ident, handler) in want.items():
            self.assertEqual(dq4data.monster_action(self.prg, rec), ident)
            self.assertEqual(int.from_bytes(self.fc(0x11, 0xA3FA + 2 * ident, 2), 'little'), handler)
        self.assertEqual(self.fc(0x11, 0xB16C, 4), bytes((0x20, 0xCB, 0x96, 0x60)))    # ブーメラン: 보통 공격 하나
        self.assertEqual(dq4data.spell_mp(self.prg, 0x23)[0], 3)
        self.assertEqual(dq4data.spell_mp(self.prg, 0x1D)[0], 2)

    def test_herb_amount_is_fc(self):
        # FC 11:$9FDD 의 양(13:$B573)은 ID 70 이 위력 표 칸에 없어 칸 70 의 몬스터 쪽 색인 (70 + 1C) × 2 가 8비트로
        # 넘쳐 18, 곧 13:$B74D 일행 칸 0C(바탕 88·폭 25)를 읽는다. DQ5 27:8071 칸 06 도 바탕 88·폭 25
        import dq4data
        at = ((0x70 + 0x1C) * 2) & 0xFF
        self.assertEqual(tuple(self.fc(dq4data.FX_BANK, dq4data.POWER + at, 2)), (88, 25))
        from dq5map import lorom
        o = lorom(0x278071 + 2 * S.HERB_AMOUNT)
        self.assertEqual(tuple(self.dq5[o:o + 2]), (88, 25))

    def test_gates_are_unused_summon_handlers(self):
        import dq5monlimits
        from dq5map import Rom
        rom = Rom(self.dq5)
        gates = {0xAE + (g - dq4monport.SUMMON_HANDLERS) // 4 for g in (S.EXEC_GATE, S.HANDLER_GATE)}
        self.assertEqual(gates, {0xAF, 0xB1})
        for m in dq4monport.used_numbers():
            acts = {rom.u8(dq5monlimits.MONSTER_RECORDS + m * dq5monlimits.MONSTER_SIZE + 0x11 + i) for i in range(6)}
            self.assertFalse(gates & acts, hex(m))
        self.assertLess(S.CODE_AT >> 16, 0x40)
        self.assertEqual(self.dq5[S.RTL_20 & 0x7FFF | 0x20 << 15], 0x6B)
        self.assertEqual(self.dq5[S.RTL_22 & 0x7FFF | 0x22 << 15], 0x6B)

    def cpu(self):
        import w65816
        c = w65816.Cpu(self.rom, bytearray(0x20000))
        c.p, c.dbr = 0x30, 0x7E
        return c

    def brk_sites(self, start, end):
        """먼 코드 안 BRK 88 nn 자리 → nn."""
        data = bytes.fromhex(self.writes[0]['hex'])
        return {S.CODE_AT + i: data[i + 2] for i in range(start - S.CODE_AT, end - S.CODE_AT)
                if data[i:i + 2] == bytes((0x00, 0x88))}

    def test_piorimu(self):
        # 살아 있는 칸마다 민첩 += min(기록 민첩, 255 - 지금), 외운 쪽이 아닌 상태 44 칸은 막힘 메시지
        c = self.cpu()
        alive = {0: True, 1: True, 2: False, 3: True}
        mahoste = {3}
        base = {0: 30, 1: 34, 3: 20}
        now = {0: 15, 1: 240, 3: 9}
        wrote, shown = {}, []

        def brk(field):
            def f(cpu):
                slot = cpu.wram[0x42]
                if field == 0x79:
                    on = alive.get(slot, False) if cpu.wram[0x43] == S.STATUS_ALIVE else slot in mahoste
                    cpu.wram[0x49] = 1 if on else 0
                elif field == 0x5F:
                    cpu.wram[0x46] = base[slot]
                elif field == 0x5C:
                    cpu.wram[0x46] = now[slot]
                elif field == 0x5D:
                    wrote[slot] = cpu.wram[0x43]
                cpu.pc += 3
                return True
            return f
        for at, field in self.brk_sites(self.labels['piorimu'], self.labels['handler']).items():
            c.hooks[at] = brk(field)
        data = bytes.fromhex(self.writes[0]['hex'])
        for i in range(self.labels['piorimu'] - S.CODE_AT, self.labels['handler'] - S.CODE_AT):
            if data[i] == 0x00 and data[i + 1] in (0xA2, 0xA4, 0x16):
                def msg(cpu, n=data[i + 1] << 8 | data[i + 2], size=4 if data[i + 1] == 0x16 else 3):
                    shown.append((n, cpu.wram[0xF5], cpu.wram[0xF6]))
                    cpu.pc += size
                    return True
                c.hooks[S.CODE_AT + i] = msg

        def wait(cpu):
            cpu.rts()
            return True

        def done(cpu):
            raise Done()
        c.hooks[S.WAIT] = wait
        c.hooks[S.CLC_RTS] = done
        c.wram[0x10F5] = 0x80
        with self.assertRaises(Done):
            c.jsl(self.labels['piorimu'])
        self.assertEqual(wrote, {0: 45, 1: 255})
        self.assertEqual([f for k, f, _ in shown if k == 0xA200 | S.MSG_BLOCKED & 0xFF], [0x83])
        speeds = [(f, n) for k, f, n in shown if k == 0xA400 | S.MSG_SPEED]
        self.assertEqual(speeds, [(0x80, 30), (0x81, 15)])

    def cond(self, wram, hooks=None):
        c = self.cpu()
        for a, v in wram.items():
            c.wram[a] = v
        for at, f in (hooks or {}).items():
            c.hooks[at] = f
        c.jsl(self.labels['cond'])
        return c.wram[0x10F6], c.wram[0x110E]

    def test_guard_condition(self):
        # 살아 있는 몬스터 8 이상이면 고르지 않음, 쓴 칸 16 이면 고르지 않음
        yes, no = (0x00, 0xFF), (0xFF, 0x00)
        slots = lambda n: {0x7CA + 16 * k: 0xC0 for k in range(n)}  # noqa: E731
        base = {0x10F7: S.GUARD, 0x10F5: 0x80, 0x7C0: 0x77, 0x117C: 0x77, 0x117D: 0xFF, 0x117E: 0xFF, 0x117F: 0xFF}
        self.assertEqual(self.cond({**base, **slots(8)}), no)
        self.assertEqual(self.cond({**base, **slots(2), 0x0D0C: 0x10}), no)

        def free(ok):
            def f(cpu):
                cpu.p = cpu.p | 1 if ok else cpu.p & ~1
                cpu.rts()
                return True
            return f
        room = {**base, **slots(2), 0x0D0C: 5, 0x0D0D: 40, 0x0C29: 8, 0x60: 0x11, 0x0CA3: 0x22}
        self.assertEqual(self.cond(room, {S.TILE_FREE: free(True)}), yes)
        self.assertEqual(self.cond(room, {S.TILE_FREE: free(False)}), no)
        self.assertEqual(self.cond({**room, 0x0D0D: 95}, {S.TILE_FREE: free(True)}), no)
        # 같은 몬스터 부르기 B5 도 같은 검사
        self.assertEqual(self.cond({**room, 0x10F7: S.SUMMON_SAME}, {S.TILE_FREE: free(True)}), yes)
        self.assertEqual(self.cond({**room, 0x10F7: S.SUMMON_SAME}, {S.TILE_FREE: free(False)}), no)
        self.assertEqual(self.cond({**base, 0x10F7: S.SUMMON_SAME, **slots(8)}), no)
        # ホイミスライム 부르기 B4: 그림이 없으면 새 그림 칸(쓴 칸 < 16, 그림 칸 < 4 이거나 빈 그림 칸)
        new = {**room, 0x10F7: S.SUMMON_FIXED}
        self.assertEqual(self.cond({**new, 0x0D0E: 1}), yes)
        self.assertEqual(self.cond({**new, 0x0D0E: 4, 0x0C1A: 1, 0x0C1B: 1, 0x0C1C: 1, 0x0C1D: 1}), no)
        self.assertEqual(self.cond({**new, 0x0D0E: 4, 0x0C1A: 1, 0x0C1B: 0, 0x0C1C: 1, 0x0C1D: 1}), yes)
        self.assertEqual(self.cond({**new, 0x0D0E: 1, 0x0D0C: 0x10}), no)
        import dq4fieldencounter
        hoimi = dq4fieldencounter.MONSTERS[S.SUMMON_FIXED_FC]
        self.assertEqual(self.cond({**new, 0x117D: hoimi}, {S.TILE_FREE: free(False)}), no)   # 그림이 있으면 자리 검사

    def test_mahoste_condition(self):
        def status(on):
            def f(cpu):
                self.assertEqual(cpu.wram[0x43], S.STATUS_MAHOSTE)
                cpu.wram[0x49] = 1 if on else 0
                cpu.pc += 3
                return True
            return f
        site = next(a for a, f in self.brk_sites(self.labels['cond'], self.labels['c_guard']).items() if f == 0x79)
        base = {0x10F7: S.MAHOSTE, 0x10F5: 0x81, 0x1110: 0x80}
        self.assertEqual(self.cond(base, {site: status(False)}), (0x00, 0xFF))
        self.assertEqual(self.cond(base, {site: status(True)}), (0xFF, 0x00))


if __name__ == '__main__':
    unittest.main()
