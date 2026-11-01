"""ndsplay(libretro 콜백·RAM 거울·명령 해석)와 ndswarp(장면 요청·좌표·프리셋 표)를 가짜 코어로 검사한다.

가짜 코어는 libretro 함수만 흉내 내고, 게임 쪽은 프레임마다 장면 요청을 받아들이는 작은 흉내다(롬 없음).
"""
import contextlib
import ctypes as C
import io
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

import ndsplay
import ndswarp as W

A_BUTTON = ndsplay.BUTTONS["a"]


class FakeCore:
    def __init__(self, on_run=None):
        self.cb = {}
        self.mem = (C.c_ubyte * ndsplay.RAM_SIZE)()
        self.frames = []          # 프레임마다 (A 눌림, 포인터 x, y, 눌림)
        self.on_run = on_run
        self.state = b"STATE-BYTES"
        self.loaded = None
        self.accept = True
        self.retro_serialize_size = lambda: len(self.state)
        self.retro_get_memory_data = lambda kind: C.addressof(self.mem)
        self.retro_get_memory_size = lambda kind: ndsplay.RAM_SIZE

    def retro_set_environment(self, cb):
        self.cb["env"] = cb

    def retro_set_video_refresh(self, cb):
        self.cb["video"] = cb

    def retro_set_audio_sample(self, cb):
        self.cb["aud"] = cb

    def retro_set_audio_sample_batch(self, cb):
        self.cb["audb"] = cb

    def retro_set_input_poll(self, cb):
        self.cb["poll"] = cb

    def retro_set_input_state(self, cb):
        self.cb["in"] = cb

    def retro_init(self):
        pass

    def retro_reset(self):
        pass

    def retro_load_game(self, gi):
        return self.accept

    def retro_run(self):
        inp = self.cb["in"]
        self.frames.append((inp(0, 1, 0, A_BUTTON), inp(0, 6, 0, 0), inp(0, 6, 0, 1), inp(0, 6, 0, 2)))
        if self.on_run:
            self.on_run(self)

    def retro_serialize(self, buf, n):
        C.memmove(buf, self.state, len(self.state))
        return True

    def retro_unserialize(self, data, n):
        self.loaded = C.string_at(data, n.value)
        return True

    # 게임 흉내가 RAM 을 읽고 쓰는 데 쓴다
    def u32(self, addr):
        o = addr - ndsplay.RAM_BASE
        return struct.unpack("<I", bytes(self.mem[o:o + 4]))[0]

    def w32(self, addr, v):
        o = addr - ndsplay.RAM_BASE
        self.mem[o:o + 4] = list(struct.pack("<I", v & 0xFFFFFFFF))


def make_player(tmp, on_run=None, accept=True):
    core = FakeCore(on_run)
    core.accept = accept
    rom = os.path.join(tmp, "game.nds")
    with open(rom, "wb") as f:
        f.write(b"NDSROM")
    with mock.patch.object(ndsplay, "load_core", return_value=core):
        p = ndsplay.Player("core.dylib", rom, os.path.join(tmp, "out"))
    return p, core


class PlayerCallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p, self.core = make_player(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_environment_answers(self):
        env = self.core.cb["env"]
        fmt = C.c_int(2)
        self.assertTrue(env(10, C.cast(C.pointer(fmt), C.c_void_p)))
        self.assertEqual(self.p.pixfmt, 2)
        var = (C.c_char_p * 2)(b"desmume_pointer_type", None)
        self.assertTrue(env(15, C.cast(var, C.c_void_p)))
        self.assertEqual(var[1], b"touch")
        var = (C.c_char_p * 2)(b"unknown_var", None)
        self.assertFalse(env(15, C.cast(var, C.c_void_p)))
        d = (C.c_char_p * 1)()
        self.assertTrue(env(9 | 0x10000, C.cast(d, C.c_void_p)))     # 위 비트(실험 플래그)는 무시
        self.assertEqual(d[0], os.path.abspath(self.p.out).encode())
        flag = C.c_bool(False)
        self.assertTrue(env(3, C.cast(C.pointer(flag), C.c_void_p)))
        self.assertTrue(flag.value)
        log = ndsplay.LogIface()
        self.assertTrue(env(27, C.cast(C.pointer(log), C.c_void_p)))
        self.assertTrue(log.log)
        self.assertFalse(env(99, None))

    def test_input_buttons_and_touch_scale(self):
        self.p.touch = (128, 96)
        self.p.held = {A_BUTTON}
        self.p.run(1)
        a, x, y, down = self.core.frames[-1]
        self.assertEqual((a, down), (1, 1))
        # 아래 화면 (x, y) 는 위아래로 붙인 256x384 화면의 (x, 192 + y) 를 -0x8000..0x7FFF 로 늘린 값
        self.assertEqual(x, int(128.5 * 0x10000 / 256) - 0x8000)
        self.assertEqual(y, int((192 + 96.5) * 0x10000 / 384) - 0x8000)
        self.assertEqual(self.core.cb["in"](1, 1, 0, A_BUTTON), 0)   # 둘째 패드는 없음
        self.p.touch = None
        self.p.run(1)
        self.assertEqual(self.core.frames[-1][1:], (0, 0, 0))

    def test_video_and_shot(self):
        self.p.pixfmt = 2
        buf = C.create_string_buffer(b"\x1F\x00" * (ndsplay.W * ndsplay.H))
        self.core.cb["video"](C.cast(buf, C.c_void_p), ndsplay.W, ndsplay.H, ndsplay.W * 2)
        self.core.cb["video"](None, 0, 0, 0)          # 프레임 건너뜀(NULL)은 앞 화면을 남긴다
        path = self.p.shot("x")
        self.assertTrue(path.endswith("x.png"))
        img = self.p.image()
        self.assertEqual(img.size, (ndsplay.W, ndsplay.H))
        self.assertEqual(img.getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(self.core.cb["audb"](None, 7), 7)

    def test_rejected_rom(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            make_player(d, accept=False)


class PlayerRamAndCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p, self.core = make_player(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ram_mirror_and_widths(self):
        p = self.p
        p.w32(0x02000010, 0x11223344)
        self.assertEqual(p.u32(0x02400010), 0x11223344)    # 4MB 거울
        self.assertEqual(p.u16(0x02000012), 0x1122)
        self.assertEqual(p.u8(0x02000013), 0x11)
        self.assertEqual(p.read(0x10, 4), struct.pack("<I", 0x11223344))   # RAM_BASE 아래는 오프셋 그대로
        p.w32(0x02000020, -1)
        self.assertEqual(p.u32(0x02000020), 0xFFFFFFFF)

    def test_press_hold_tap_and_frames(self):
        p = self.p
        p.press("a+b", 2, 3)
        self.assertEqual([f[0] for f in self.core.frames], [1, 1, 0, 0, 0])
        self.assertEqual(p.frame, 5)
        p.hold("a", 2)
        self.assertEqual(p.held, set())
        p.tap(10, 20, 1, 1)
        self.assertEqual([f[3] for f in self.core.frames[-2:]], [1, 0])

    def test_freeze_rewrites_before_each_frame(self):
        p = self.p
        seen = []
        self.core.on_run = lambda c: (seen.append(c.u32(0x02000100)), c.w32(0x02000100, 0))
        p.script("freeze 2000100 2a000000; wait 2; unfreeze 2000100; wait 1")
        self.assertEqual(seen, [42, 42, 0])

    def test_until_and_timeout(self):
        p = self.p
        self.core.on_run = lambda c: c.w32(0x02000200, len(c.frames))
        self.assertTrue(p.until(0x02000200, 3, 4, maxf=10))
        self.assertEqual(p.frame, 3)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            p.command("until 2000200 ff 2 1")
        self.assertIn("timeout", err.getvalue())

    def test_commands(self):
        p = self.p
        buf = C.create_string_buffer(ndsplay.W * ndsplay.H * 2)
        self.core.cb["video"](C.cast(buf, C.c_void_p), ndsplay.W, ndsplay.H, ndsplay.W * 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            p.script("# 주석\n\npoke 2000300 0102; poke32 2000304 deadbeef; peek 2000300 8; log 안녕")
            p.command("dump part 2000300 8")
            p.command("a 2 10")
            p.command("mash b 1 6")
            p.command("drag 0 0 10 20 2 1")
            p.command("touch 5 5 1 1")
            p.command("every 4 2 snap")
            p.command("save " + os.path.join(self.tmp.name, "s.state"))
            p.command("load " + os.path.join(self.tmp.name, "s.state"))
        text = out.getvalue()
        self.assertIn("02000300: 01 02 00 00 ef be ad de", text)
        self.assertIn("안녕", text)
        with open(os.path.join(p.out, "part.bin"), "rb") as f:
            self.assertEqual(f.read(), bytes([1, 2, 0, 0, 0xEF, 0xBE, 0xAD, 0xDE]))
        self.assertEqual(self.core.loaded, b"STATE-BYTES")
        snaps = sorted(f for f in os.listdir(p.out) if f.startswith("snap_"))
        self.assertEqual(len(snaps), 2)
        drag = [f for f in self.core.frames if f[3]]
        self.assertGreaterEqual(len(drag), 3)
        with self.assertRaises(SystemExit):
            p.command("fly 1")

    def test_load_runs_one_frame_first(self):
        path = os.path.join(self.tmp.name, "s.state")
        with open(path, "wb") as f:
            f.write(b"abc")
        self.p.load(path)
        self.assertEqual(self.p.frame, 1)          # 코어는 한 프레임을 돈 뒤에야 상태를 받는다
        self.assertEqual(self.core.loaded, b"abc")

    def test_core_path(self):
        with mock.patch.dict(os.environ, {"DESMUME_CORE": "/x/core.so"}):
            self.assertEqual(ndsplay.core_path(), "/x/core.so")
            self.assertEqual(ndsplay.core_path("/y"), "/y")
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            ndsplay.core_path()


# --- ndswarp ------------------------------------------------------------------------------------

class Game:
    """장면 요청을 받아들이는 게임 흉내. bad 의 맵은 실리지 않는다(다른 맵이 됨)."""

    def __init__(self, bad=()):
        self.bad = set(bad)
        self.pos_ptr = 0x02300000

    def __call__(self, c):
        req = c.u32(W.SCENE_REQ)
        if c.u32(W.HERO_OBJ) == 0:
            c.w32(W.HERO_OBJ, 0x02200000)
            c.w32(0x02200000 + 0x70, self.pos_ptr)
            c.w32(W.SCENE_REQ, 0xFFFFFFFF)
            c.w32(W.PRESET, 0xFFFFFFFF)
            return
        if req != 0xFFFFFFFF:
            c.w32(W.SCENE_CUR, req)
            c.w32(W.SCENE_REQ, 0xFFFFFFFF)
            if req == W.SCENE_TOWN:
                o = W.MAP_NAME - ndsplay.RAM_BASE
                name = bytes(c.mem[o:o + 16]).split(b"\0")[0].decode()
                if name in self.bad:
                    c.mem[o:o + 4] = list(b"caf1")
                if c.u32(W.PRESET) != 0xFFFFFFFF:
                    c.w32(W.CHAPTER, 6)
                    c.w32(W.PRESET, 0xFFFFFFFF)
        if c.u32(W.SCENE_CUR) == W.SCENE_FIELD:
            # 필드에서는 HERO_POS 가 x·z 두 칸짜리 그리기용 사본이다(nds/dq4/docs/debug.md)
            c.w32(W.HERO_POS, c.u32(self.pos_ptr))
            c.w32(W.HERO_POS + 4, c.u32(self.pos_ptr + 4))
        if c.u32(W.SCENE_CUR) == W.SCENE_BATTLE_TEST and c.frames[-1][0]:
            c.w32(W.SCENE_CUR, 0x0D)


def write_fs(root):
    d = os.path.join(root, "data", "data")
    for sub in ("MAP", "DEBUG", "PARAM"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    with open(os.path.join(d, "MAP", "_list.txt"), "w", encoding="shift_jis") as f:
        f.write("0,a,caf1\n1,b,hac1\n2,c,bad1\nend\n")
    with open(os.path.join(d, "DEBUG", "flagshop.dat"), "w", encoding="shift_jis") as f:
        f.write("1,0,序章\n331,6,ピサロ\nbroken\n")
    for k in range(1, 5):
        recs = b""
        for n, m in ((331 if k == 1 else 0xFFFF, "hac1"), (1 if k == 1 else 331, "zzz1")):
            r = bytearray(0x9C)
            struct.pack_into("<H", r, 0, n)
            r[0x93:0x93 + len(m)] = m.encode()
            recs += bytes(r)
        with open(os.path.join(d, "PARAM", f"param_player_event{k}.dat"), "wb") as f:
            f.write(b"HEAD" + recs)


class WarpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fs = os.path.join(self.tmp.name, "fs")
        write_fs(self.fs)
        self.game = Game(bad={"bad1"})
        self.p, self.core = make_player(self.tmp.name, self.game)
        self.p.run(1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tables(self):
        self.assertEqual(W.map_names(self.fs), ["caf1", "hac1", "bad1"])
        self.assertEqual(W.preset_names(self.fs), {1: (0, "序章"), 331: (6, "ピサロ")})
        recs = W.preset_records(self.fs)
        self.assertEqual(sorted(recs), [1, 331])                  # 마지막 레코드까지, FFFF 는 뺀다
        self.assertEqual(W.preset_map(recs, 331), "hac1")         # 같은 번호는 앞 파일이 이긴다
        self.assertEqual(W.preset_map(recs, 1), "zzz1")

    def test_enter_writes_request_and_position(self):
        ok = W.enter(self.p, "hac1", preset=331, x=2, z=-1, settle=3, time=4)
        self.assertTrue(ok)
        self.assertEqual(self.p.u32(W.TIME_ZONE), 4)
        self.assertEqual(self.p.u32(W.CHAPTER), 6)
        self.assertEqual(self.p.u32(W.HERO_POS), round(2 * W.TILE))
        self.assertEqual(self.p.u32(W.HERO_POS + 8), round(-1 * W.TILE) & 0xFFFFFFFF)
        self.assertFalse(W.enter(self.p, "bad1", settle=1))
        with self.assertRaises(AssertionError):
            W.enter(self.p, "x" * 16)

    def test_field_wraps_negative_coordinates(self):
        ok = W.field(self.p, -1, 2.5, settle=2)
        self.assertTrue(ok)
        self.assertEqual(self.p.u32(self.game.pos_ptr), W.FIELD_WRAP - W.FIELD_TILE)
        self.assertEqual(self.p.u32(self.game.pos_ptr + 4), round(2.5 * W.FIELD_TILE))

    def test_battle_fills_groups_and_actions(self):
        ok = W.battle(self.p, [(5, 2), (7, 1)], settle=2, act=0x33)
        self.assertTrue(ok)
        rec = W.MONSTER_TABLE + 60 * 7
        self.assertEqual(self.p.read(rec + 6, 2), struct.pack("<H", 999))
        self.assertEqual(self.p.read(rec + 0x12, 12), struct.pack("<6H", *[0x33] * 6))
        groups = [(self.p.u32(W.BATTLE_TEST + 0x20 + 4 * i), self.p.u32(W.BATTLE_TEST + 0x30 + 4 * i))
                  for i in range(4)]
        self.assertEqual(groups, [(5, 2), (7, 1), (0, 0), (0, 0)])

    def test_no_encounter_clears_only_its_bit(self):
        self.p.w32(W.MAP_FLAGS, 0x3FF)
        W.no_encounter(self.p)
        self.assertEqual(self.p.u32(W.MAP_FLAGS), 0x1FF)

    def test_finish_reports_field_or_map(self):
        buf = C.create_string_buffer(ndsplay.W * ndsplay.H * 2)
        self.core.cb["video"](C.cast(buf, C.c_void_p), ndsplay.W, ndsplay.H, ndsplay.W * 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            W.enter(self.p, "hac1", settle=1)
            W.finish(self.p, self.p.out, "m", True, "", noenc=True)
            W.field(self.p, 3, 4, settle=1)
            W.finish(self.p, self.p.out, "f", False, "wait 1")
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("m\tok\tchapter="))
        self.assertIn("map=hac1", lines[0])
        self.assertIn("field=(3.00,4.00)", lines[1])
        self.assertIn("FAIL", lines[1])
        self.assertTrue(os.path.exists(os.path.join(self.p.out, "m.state")))

    def test_boot_and_start(self):
        W.boot(self.p)
        self.assertEqual(self.p.u32(W.SCENE_CUR), W.SCENE_DEBUG)
        path = os.path.join(self.tmp.name, "b.state")
        self.p.save(path)
        W.start(self.p, path)
        self.assertEqual(self.core.loaded, b"STATE-BYTES")

    def test_fixed_clock(self):
        class Mode:
            value = 0
        mode = Mode()
        seen = []
        self.core.on_run = lambda c: seen.append(mode.value)
        with mock.patch.object(W.ctypes.c_int, "in_dll", return_value=mode, create=False):
            W.fixed_clock(self.p)
        self.p.run(2)
        self.assertEqual(seen, [3, 3])               # 도는 동안만 movieMode 3
        self.assertEqual(mode.value, 0)
        q, _ = make_player(self.tmp.name)
        err = io.StringIO()
        with mock.patch.object(W.ctypes.c_int, "in_dll", side_effect=ValueError), contextlib.redirect_stderr(err):
            W.fixed_clock(q)
        self.assertIn("movieMode", err.getvalue())

    def test_screens_retries_from_boot_and_lists_failures(self):
        out = os.path.join(self.tmp.name, "screens")
        game = Game(bad={"bad1"})

        def load_core(_path):
            return FakeCore(game)
        buf = C.create_string_buffer(ndsplay.W * ndsplay.H * 2)
        orig_run = FakeCore.retro_run

        def run_with_video(core):
            core.cb["video"](C.cast(buf, C.c_void_p), ndsplay.W, ndsplay.H, ndsplay.W * 2)
            orig_run(core)
        rom = os.path.join(self.tmp.name, "game.nds")
        with mock.patch.object(ndsplay, "load_core", load_core), \
                mock.patch.object(FakeCore, "retro_run", run_with_video), \
                mock.patch.object(W.ctypes.c_int, "in_dll", side_effect=ValueError), \
                contextlib.redirect_stdout(io.StringIO()) as so, contextlib.redirect_stderr(io.StringIO()):
            failed = W.screens("core", rom, out, self.fs, None, 2)
        self.assertEqual(failed, ["bad1"])
        self.assertEqual(sorted(f for f in os.listdir(out) if f.endswith(".png")),
                         ["000-caf1.png", "001-hac1.png", "002-bad1.png"])
        with open(os.path.join(out, "README.txt"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("머물지 못한 맵: bad1", readme)
        self.assertIn("--settle 2", readme)
        self.assertIn("002\tbad1\tFAIL", so.getvalue())


class WarpCliTests(unittest.TestCase):
    def run_main(self, d, *argv):
        rom = os.path.join(d, "game.nds")
        with open(rom, "wb") as f:
            f.write(b"NDSROM")
        game = Game(bad={"bad1"})
        buf = C.create_string_buffer(ndsplay.W * ndsplay.H * 2)

        def load_core(_path):
            return FakeCore(game)
        orig_run = FakeCore.retro_run

        def run_with_video(core):
            core.cb["video"](C.cast(buf, C.c_void_p), ndsplay.W, ndsplay.H, ndsplay.W * 2)
            orig_run(core)
        out = io.StringIO()
        with mock.patch.object(ndsplay, "load_core", load_core), \
                mock.patch.object(FakeCore, "retro_run", run_with_video), \
                mock.patch.object(sys, "argv", ["ndswarp", *argv, "--rom", rom, "--fs", os.path.join(d, "fs"),
                                                "--core", "x", "--settle", "2"]), \
                contextlib.redirect_stdout(out):
            W.main()
        return out.getvalue()

    def test_commands_leave_state_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            write_fs(os.path.join(d, "fs"))
            out = os.path.join(d, "o")
            text = self.run_main(d, "boot", os.path.join(out, "boot.state"))
            self.assertIn("scene=0x1", text)
            text = self.run_main(d, "map", out, "hac1", "bad1", "--x", "1", "--no-encounter")
            self.assertIn("hac1\tok", text)
            self.assertIn("bad1\tFAIL", text)
            state = os.path.join(out, "hac1.state")
            text = self.run_main(d, "battle", out, "5x2", "7", "--state", state, "--act", "0x10")
            self.assertIn("battle_5x2_7x1\tok", text)
            text = self.run_main(d, "field", out, "1", "2", "3", "4", "--state", state)
            self.assertIn("field_1_2\tok", text)
            self.assertIn("field_3_4\tok", text)
            text = self.run_main(d, "preset", out, "331")
            self.assertIn("preset331\tok\tchapter=6", text)
            self.assertTrue(os.path.exists(os.path.join(out, "_boot.state")))
            with self.assertRaises(SystemExit):
                self.run_main(d, "field", out, "1", "2")    # 일행이 있는 상태가 필요


    def test_list_and_presets(self):
        with tempfile.TemporaryDirectory() as d:
            write_fs(d)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with mock.patch.object(sys, "argv", ["ndswarp", "list", "ha", "--fs", d]):
                    W.main()
                with mock.patch.object(sys, "argv", ["ndswarp", "presets", "ピサ", "--fs", d]):
                    W.main()
        self.assertEqual(out.getvalue().splitlines(), ["  1 hac1", "331  6 hac1     ピサロ"])


if __name__ == "__main__":
    unittest.main()
