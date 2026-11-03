"""롬 없이: 누운 인물 찾기 훅의 바이트와 자리. 원본 DQ5 롬이 있으면 덮는 자리의 원래 바이트."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dq4sleepertalk as st  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DQ5 = ROOT / "rom" / "dq5.sfc"


def lorom(addr):
    return (addr >> 16) * 0x8000 + (addr & 0x7FFF)


PUSH = {"PHA", "PHX", "PHY", "PHP", "PHB", "PHD", "PHK", "PEA", "PEI", "PER"}
PULL = {"PLA", "PLX", "PLY", "PLP", "PLB", "PLD"}
BRANCH = {"BCC", "BCS", "BEQ", "BNE", "BMI", "BPL", "BVC", "BVS"}
# Anything that leaves without RTS, reads or sets the stack pointer, or jumps where the walk cannot follow
REFUSED = {"RTL", "RTI", "JML", "BRK", "COP", "TSC", "TSX", "TCS", "TXS", "STP", "WAI", "BRL"}


def walk(rom, start):
    """Every path from start in bank 05 to an RTS, with the push/pull depth. Fails on REFUSED, an indirect jump or a
    jump to another bank, a depth that differs where paths meet, or an RTS reached with the stack not level."""
    from kr_patch.sfc import dis65816
    depth, todo, out = {}, [(start, 0, True, True)], {"rts": set(), "seen": set(), "calls": set(), "long": set()}
    while todo:
        a, d, m8, x8 = todo.pop()
        if a in depth:
            if depth[a] != d:
                raise AssertionError(f"{a:06X}: stack depth {d} and {depth[a]} meet")
            continue
        depth[a] = d
        out["seen"].add(a)
        text, size, m8_next, x8_next = dis65816.decode(rom, a, m8, x8)
        parts = text.split()
        op = next(p for p in parts[1:] if p.isalpha() and p.isupper() and len(p) == 3)
        arg = parts[-1] if parts[-1].startswith("$") else ""
        if op in REFUSED or (op in ("JMP", "JSR") and not arg):
            raise AssertionError(f"{a:06X}: {op}")
        nxt = a + size
        d2 = d + (op in PUSH) - (op in PULL)
        if d2 < 0:
            raise AssertionError(f"{a:06X}: pulls below the entry")
        if op == "RTS":
            if d:
                raise AssertionError(f"{a:06X}: RTS with {d} bytes pushed")
            out["rts"].add(a)
        elif op == "JMP":
            todo.append(((a & 0xFF0000) | int(arg[1:], 16), d2, m8_next, x8_next))
        elif op == "BRA":
            todo.append((int(arg[1:], 16), d2, m8_next, x8_next))
        elif op in BRANCH:
            todo += [(int(arg[1:], 16), d2, m8_next, x8_next), (nxt, d2, m8_next, x8_next)]
        else:
            if op == "JSR":
                out["calls"].add((a & 0xFF0000) | int(arg[1:], 16))
            elif op == "JSL":
                out["long"].add(int(arg[1:], 16))
            todo.append((nxt, d2, m8_next, x8_next))
    return out


class HookTest(unittest.TestCase):
    """The bytes checked here are the ones dq4sleepertalk writes, so this only guards against an edit that changes
    them by mistake. That the ROM answers from the foot is shown by the -foot scenes of dq4npccheck (dq4-npc-talk)."""

    def test_checks_the_cell_to_the_right_only_when_the_first_misses(self):
        code = st.code()
        self.assertEqual(code[:4], bytes((0x7B, 0x20, 0x03, 0x85)))       # TDC / JSR $8503 at ($00, $01)
        branch = code.index(0xB0)
        self.assertEqual(branch + 2 + code[branch + 1], len(code) - 1)    # BCS to the RTS
        self.assertEqual(code[branch + 2:branch + 4], bytes((0xE6, 0x00)))  # INC $00: one cell right
        self.assertEqual(code[-3:], bytes((0xC6, 0x00, 0x60)))           # DEC $00 back, RTS (C kept)

    def test_writes_jump_from_the_lying_check(self):
        hook, jump = st.writes()
        self.assertEqual(hook["at"], "05:FEF0")
        self.assertEqual(jump["at"], "05:84FE")
        self.assertEqual(jump["hex"], "4C F0 FE")
        self.assertEqual(jump["orig"], "7B 80 02")
        with self.assertRaises(ValueError):
            st.writes(0x06FEF0)

    def test_the_chapter_1_build_takes_the_patch(self):
        # dq4groupbuild writes the manifest; the chapter-1 ROM gets only the group patches dq4chapter1 lists.
        import dq4chapter1
        self.assertIn("sleeper-talk.dq5patch.json", dq4chapter1.GROUP_PATCHES)

    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_original_bytes(self):
        rom = DQ5.read_bytes()
        # lorom() reads a ROM without a copier header (README); a headed one would shift every offset by 512
        self.assertEqual(len(rom), 0x180000, "rom/dq5.sfc must be the 1.5MB ROM without a copier header")
        self.assertEqual(rom[lorom(st.LYING_CHECK):lorom(st.LYING_CHECK) + 3], st.LYING_CHECK_ORIG)
        self.assertEqual(rom[lorom(0x058501):lorom(0x058501) + 4], bytes.fromhex("A9 01 85 A2"))
        self.assertEqual(set(rom[lorom(st.HOOK_AT):lorom(st.HOOK_AT) + len(st.code())]), {0})


    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_callers_read_only_carry(self):
        # The hook's second path ends with DEC $00, so N/Z differ from what 05:8503 left. Each facing calls 05:84FE
        # twice: JSR / BCS found / DEC $00 or $01 / JSR / BCS found / LDA #$FF / RTS, and "found" is an RTS. Nothing
        # between reads N/Z, and the RTS goes back through 05:8370 to 05:82DC, which pushes A and compares it again.
        rom = DQ5.read_bytes()
        bank = rom[lorom(0x058000):lorom(0x058000) + 0x8000]

        def at(a, n=1):
            return bank[a - 0x8000:a - 0x8000 + n]

        jsr = bytes((0x20, 0xFE, 0x84))
        sites = [0x8000 + i for i in range(len(bank) - 2) if bank[i:i + 3] == jsr]
        self.assertEqual(sites, [0x83DF, 0x83E6, 0x842B, 0x8432, 0x8476, 0x847D, 0x84DC, 0x84E3])
        for first, second in zip(sites[::2], sites[1::2]):
            self.assertEqual(second - first, 7, f"05:{first:04X}")
            self.assertEqual(at(first + 5), b"\xC6", f"05:{first:04X}")             # DEC dp
            self.assertIn(at(first + 6), (b"\x00", b"\x01"), f"05:{first:04X}")
            self.assertEqual(at(second + 5, 3), bytes.fromhex("A9 FF 60"), f"05:{second:04X}")   # LDA #$FF / RTS
            for site in (first, second):
                self.assertEqual(at(site + 3), b"\xB0", f"05:{site:04X}")        # BCS
                found = site + 5 + int.from_bytes(at(site + 4), "little", signed=True)
                self.assertEqual(at(found), b"\x60", f"05:{site:04X} -> 05:{found:04X}")
        self.assertEqual(at(0x82DC, 6), bytes.fromhex("20 70 83 48 C9 FF"))    # JSR $8370 / PHA / CMP #$FF

    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_the_check_body_keeps_00_01_and_the_stack(self):
        # 05:8503 pushes $00 and $01 first and pulls them back just before its one RTS, so the hook can call it twice
        # and the INC/DEC around the second call leave $00 as the caller set it. X and Y are not kept, as with one
        # call in the original. Walked instruction by instruction over every branch: one RTS, every jump stays
        # inside, the stack is level at the RTS and the same wherever two paths meet. Bank-05 routines it calls are
        # walked the same way (any number of RTS); the JSL to bank 00 is taken to return level.
        rom = DQ5.read_bytes()
        body = walk(rom, 0x058503)
        self.assertEqual(body["rts"], {0x05859F})
        self.assertTrue(all(0x058503 <= a < 0x0585A0 for a in body["seen"]), "a jump leaves 05:8503~859F")
        self.assertEqual(rom[lorom(0x058503):lorom(0x058503) + 8], bytes.fromhex("85 A2 A5 00 48 A5 01 48"))
        self.assertEqual(rom[lorom(0x058597):lorom(0x058597) + 9], bytes.fromhex("AA 68 85 01 68 85 00 8A 60"))
        self.assertEqual(body["calls"], {0x0585A0, 0x0585F8})
        self.assertFalse(body["long"])
        inner = [walk(rom, call) for call in sorted(body["calls"])]
        self.assertTrue(all(w["rts"] and not w["calls"] for w in inner))
        self.assertEqual(set().union(*(w["long"] for w in inner)), {0x00D0A2})

    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_hook_space_is_free_and_kept_apart(self):
        # 05:FEF0~ lies in dq5build's free map (bank 05 end), before the shop helper at 05:FF00 (dq4windowname). The
        # dq5 placers (dq5exitreloc, dq5chestreloc) only take addresses they are given, and dq5build refuses two
        # writes on one byte, so this range stays the hook's as long as no fixed address here moves into it.
        sys.path.insert(0, str(ROOT / "sfc" / "dq5" / "tools"))
        import dq4windowname
        from dq5build import free_ranges
        start, end = lorom(st.HOOK_AT), lorom(st.HOOK_AT) + len(st.code())
        self.assertTrue(any(s <= start and end <= s + n for s, n in free_ranges(DQ5.read_bytes())))
        self.assertLessEqual(st.HOOK_AT + len(st.code()), dq4windowname.LOW_SPOT)


class ReachTest(unittest.TestCase):
    """dq4sleepertalk.lying_target follows 05:84FE as the code reads; the emulator scenes are the proof."""

    def test_foot_is_reached_only_with_the_hook(self):
        sleeper = {(27, 40)}                                       # FC bed foot (13,20), lying at (2x+1, 2y)
        for hero, d in (((26, 43), 'up'), ((24, 41), 'right'), ((26, 39), 'down')):
            self.assertIsNone(st.lying_target(*hero, d, sleeper, hooked=False), (hero, d))
            self.assertEqual(st.lying_target(*hero, d, sleeper), (27, 40), (hero, d))
        # the head side answers either way
        self.assertEqual(st.lying_target(28, 43, 'up', sleeper, hooked=False), (27, 40))
        self.assertEqual(st.lying_target(28, 43, 'up', sleeper), (27, 40))

    def test_beds_side_by_side_keep_their_own_sleeper(self):
        # FC beds at (13,20)-(14,20) and (15,20)-(16,20): sleepers at (27,40) and (31,40)
        sleepers = {(27, 40), (31, 40)}
        self.assertEqual(st.lying_target(26, 43, 'up', sleepers), (27, 40))   # foot of the left bed
        self.assertEqual(st.lying_target(28, 43, 'up', sleepers), (27, 40))   # head of the left bed
        self.assertEqual(st.lying_target(30, 43, 'up', sleepers), (31, 40))   # foot of the right bed
        self.assertEqual(st.lying_target(32, 43, 'up', sleepers), (31, 40))   # head of the right bed
        self.assertEqual(st.lying_target(24, 41, 'right', sleepers), (27, 40))  # left of the left bed
        self.assertEqual(st.lying_target(34, 41, 'left', sleepers), (31, 40))   # right of the right bed


if __name__ == "__main__":
    unittest.main()
