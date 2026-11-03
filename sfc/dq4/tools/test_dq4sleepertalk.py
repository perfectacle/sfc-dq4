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


BRANCH = {"BCC", "BCS", "BEQ", "BNE", "BMI", "BPL", "BVC", "BVS"}
# Anything that leaves without RTS, reads or sets the stack pointer, swaps emulation mode, or jumps where the walk
# cannot follow
REFUSED = {"RTL", "RTI", "JML", "BRK", "COP", "TSC", "TSX", "TCS", "TXS", "STP", "WAI", "BRL", "XCE"}


def pushed(op, m8, x8):
    """Bytes a push puts on the stack (accumulator by M, index by X), 0 if op is no push."""
    return {"PHA": 1 if m8 else 2, "PHX": 1 if x8 else 2, "PHY": 1 if x8 else 2, "PHB": 1, "PHK": 1, "PHD": 2,
            "PEA": 2, "PEI": 2, "PER": 2}.get(op, 0)


def pulled(op, m8, x8):
    return {"PLA": 1 if m8 else 2, "PLX": 1 if x8 else 2, "PLY": 1 if x8 else 2, "PLB": 1, "PLD": 2}.get(op, 0)


def walk(rom, start, m8=True, x8=True):
    """Every path from start to an RTS, in the bank of start. The stack is followed byte by byte: PHP pushes the M/X
    widths it saw and PLP brings them back (a PLP of anything else fails). Where two paths meet, the stack and the
    widths must be the same; an RTS must find the stack as it was on entry. Fails on REFUSED, an indirect jump or a
    jump to another bank. Calls are assumed to come back level and are listed with the widths at the call. The CPU
    is taken to be in native mode (E = 0) on entry, as the game runs; XCE is refused, so it cannot change on the way."""
    from kr_patch.sfc import dis65816
    state, todo = {}, [(start, (), m8, x8)]
    out = {"rts": set(), "seen": set(), "calls": {}, "long": set()}
    while todo:
        a, stack, m, x = todo.pop()
        if a in state:
            if state[a] != (stack, m, x):
                raise AssertionError(f"{a:06X}: paths meet with {state[a]} and {(stack, m, x)}")
            continue
        state[a] = (stack, m, x)
        out["seen"].add(a)
        text, size, m_next, x_next = dis65816.decode(rom, a, m, x)
        parts = text.split()
        op = next(p for p in parts[1:] if p.isalpha() and p.isupper() and len(p) == 3)
        arg = parts[-1] if parts[-1].startswith("$") else ""
        if op in REFUSED or (op in ("JMP", "JSR") and not arg):
            raise AssertionError(f"{a:06X}: {op}")
        nxt = a + size
        if op == "PHP":
            stack = stack + (("P", m, x),)
        elif op == "PLP":
            if not stack or not isinstance(stack[-1], tuple):
                raise AssertionError(f"{a:06X}: PLP of a byte PHP did not push")
            stack, (_, m_next, x_next) = stack[:-1], stack[-1]
        else:
            stack = stack + ("b",) * pushed(op, m, x)
            n = pulled(op, m, x)
            if n > len(stack) or any(isinstance(t, tuple) for t in stack[len(stack) - n:]):
                raise AssertionError(f"{a:06X}: {op} pulls below the entry or a pushed P")
            stack = stack[:len(stack) - n]
        if op == "RTS":
            if stack:
                raise AssertionError(f"{a:06X}: RTS with {len(stack)} bytes pushed")
            out["rts"].add(a)
        elif op == "JMP":
            todo.append(((a & 0xFF0000) | int(arg[1:], 16), stack, m_next, x_next))
        elif op == "BRA":
            todo.append((int(arg[1:], 16), stack, m_next, x_next))
        elif op in BRANCH:
            todo += [(int(arg[1:], 16), stack, m_next, x_next), (nxt, stack, m_next, x_next)]
        else:
            if op == "JSR":
                out["calls"].setdefault((a & 0xFF0000) | int(arg[1:], 16), set()).add((m, x))
            elif op == "JSL":
                out["long"].add(int(arg[1:], 16))
            todo.append((nxt, stack, m_next, x_next))
    return out


def bank05(code):
    """A ROM image with code at 05:8000 and nothing else, for walk()."""
    rom = bytearray(lorom(0x060000))
    rom[lorom(0x058000):lorom(0x058000) + len(code)] = code
    return bytes(rom)


# PHA / LDA $00 / BEQ +2 / BRA +0 / PLA / RTS: two paths meet at the PLA
LEVEL = bytes.fromhex("48 A5 00 F0 02 80 00 68 60")


class WalkTest(unittest.TestCase):
    """walk() on small made-up routines, so the checks it relies on run without a ROM."""

    def test_a_level_routine_passes(self):
        self.assertEqual(walk(bank05(LEVEL), 0x058000)["rts"], {0x058008})

    def test_it_catches_a_changed_routine(self):
        for name, at, byte in (("PLA→NOP", 7, 0xEA), ("RTS in the middle", 1, 0x60), ("RTL", 8, 0x6B),
                               ("TSX", 1, 0xBA), ("XCE", 1, 0xFB), ("PLP without PHP", 7, 0x28)):
            code = bytearray(LEVEL)
            code[at] = byte
            with self.subTest(name), self.assertRaises(AssertionError):
                walk(bank05(bytes(code)), 0x058000)

    def test_paths_must_meet_with_the_same_stack_and_widths(self):
        for name, branch in (("one more push", "48 EA"), ("16-bit A", "C2 20")):
            code = bytearray(LEVEL)
            code[5:7] = bytes.fromhex(branch)
            with self.subTest(name), self.assertRaises(AssertionError):
                walk(bank05(bytes(code)), 0x058000)

    def test_bytes_follow_the_widths(self):
        # REP #$20 / PHA (2 bytes) / SEP #$20 / PLA (1 byte) / RTS leaves one byte behind
        with self.assertRaises(AssertionError):
            walk(bank05(bytes.fromhex("C2 20 48 E2 20 68 60")), 0x058000)
        walk(bank05(bytes.fromhex("C2 20 48 68 E2 20 60")), 0x058000)

    def test_plp_brings_back_the_widths_php_saw(self):
        # PHP / REP #$30 / PLP / PHA / PEA $0000 / PLD / PLB / RTS is level only if A is 8-bit again after PLP:
        # with A left 16-bit the PHA pushes 2 and one byte stays at the RTS
        walk(bank05(bytes.fromhex("08 C2 30 28 48 F4 00 00 2B AB 60")), 0x058000)
        with self.assertRaises(AssertionError):
            walk(bank05(bytes.fromhex("08 C2 30 EA 48 F4 00 00 2B AB 60")), 0x058000)   # PLP → NOP

    def test_index_pushes_follow_x(self):
        walk(bank05(bytes.fromhex("C2 10 DA 7A E2 10 60")), 0x058000)       # REP #$10 / PHX / PLY / SEP #$10
        for code in ("C2 10 DA E2 10 FA 60", "C2 10 5A E2 10 7A 60"):     # 16-bit push, 8-bit pull
            with self.subTest(code), self.assertRaises(AssertionError):
                walk(bank05(bytes.fromhex(code)), 0x058000)

    def test_two_byte_pushes(self):
        for push in ("0B", "F4 00 00", "D4 00", "62 00 00"):              # PHD, PEA, PEI, PER
            with self.subTest(push):
                walk(bank05(bytes.fromhex(push + " 68 68 60")), 0x058000)
                with self.assertRaises(AssertionError):
                    walk(bank05(bytes.fromhex(push + " 68 60")), 0x058000)

    def test_refused_instructions(self):
        for code in ("40", "5C 00 80 05", "00 00", "02 00", "DB", "CB", "82 00 00", "1B", "9A", "3B",
                     "6C 00 80", "7C 00 80", "FC 00 80", "DC 00 80"):
            with self.subTest(code), self.assertRaises(AssertionError):
                walk(bank05(bytes.fromhex(code + " 60")), 0x058000)


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
        # call in the original. Walked over every branch (walk()); the bank-05 routines it calls are walked the same
        # way (any number of RTS), and the JSL to bank 00 is taken to come back level.
        rom = DQ5.read_bytes()
        body = walk(rom, 0x058503)
        self.assertEqual(body["rts"], {0x05859F})
        self.assertTrue(all(0x058503 <= a < 0x0585A0 for a in body["seen"]), "a jump leaves 05:8503~859F")
        self.assertEqual(rom[lorom(0x058503):lorom(0x058503) + 8], bytes.fromhex("85 A2 A5 00 48 A5 01 48"))
        self.assertEqual(rom[lorom(0x058597):lorom(0x058597) + 9], bytes.fromhex("AA 68 85 01 68 85 00 8A 60"))
        self.assertEqual(set(body["calls"]), {0x0585A0, 0x0585F8})
        self.assertFalse(body["long"])
        inner = [walk(rom, call) for call in sorted(body["calls"])]
        self.assertTrue(all(w["rts"] and not w["calls"] for w in inner))
        self.assertEqual(set().union(*(w["long"] for w in inner)), {0x00D0A2})

    @unittest.skipUnless(DQ5.is_file(), "local source ROM not present")
    def test_the_lying_check_runs_with_8_bit_a_and_index(self):
        # walk() starts 05:8503 with M = X = 1. 05:82C6 SEP #$30 is the last width change before 05:82D5~82DC (the
        # BMI at 05:82CA leads there; the REP #$30 at 05:82CE is on the other way out), and from 05:8370 down to
        # every JSR $84FE the widths do not change.
        from kr_patch.sfc import dis65816
        rom = DQ5.read_bytes()
        self.assertEqual(rom[lorom(0x0582C6):lorom(0x0582C6) + 2], bytes.fromhex("E2 30"))
        self.assertEqual(rom[lorom(0x0582CA):lorom(0x0582CA) + 2], bytes.fromhex("30 09"))   # BMI $82D5
        a = 0x0582D5
        while a < 0x0582DC:
            text, size, _, _ = dis65816.decode(rom, a)
            self.assertFalse({"REP", "SEP", "PLP", "XCE"} & set(text.split()), text)
            a += size
        sites = {}
        for facing, w in walk(rom, 0x058370)["calls"].items():
            self.assertEqual(w, {(True, True)}, f"{facing:06X}")
            for target, widths in walk(rom, facing)["calls"].items():
                sites.setdefault(target, set()).update(widths)
        self.assertEqual(sites[0x0584FE], {(True, True)})

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
