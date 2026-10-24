"""Drive the desmume libretro core headless and save screenshots; nds/dq4/docs/graphics-format.md.

    uv run --locked python nds/dq4/tools/ndsplay.py ROM OUTDIR [--core $DESMUME_CORE] [--state IN] [--save OUT] --cmd "..."

Commands (one per line or separated by ;):
    wait N                     run N frames
    press BTN[+BTN] [N] [W]    hold for N frames (default 6), then wait W (default 20)
    a K [P]                    press A K times, every P frames (default 30)
    touch X Y [N] [W]          touch the lower screen at (X, Y)
    shot NAME                  OUTDIR/NAME.png (upper screen above lower screen, 256x384)
    every N K NAME             run N frames, saving NAME_<frame>.png every K frames
Buttons: a b x y l r start select up down left right
"""

import argparse
import ctypes as C
import os

from kr_patch.sfc.libretro import (AUD_CB, AUDB_CB, ENV_CB, IN_CB, LOG_CB, POLL_CB, VID_CB, GameInfo,
                                   LogIface, load_core, to_image)

BUTTONS = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
           "a": 8, "x": 9, "l": 10, "r": 11}
VARS = {"desmume_pointer_mouse": "enabled", "desmume_pointer_type": "touch"}
W, H = 256, 384


class Player:
    def __init__(self, core_path, rom, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.core = load_core(core_path)
        self.held, self.touch = set(), None
        self.pixfmt, self.last, self.frame = 0, None, 0
        sysdir = C.c_char_p(os.path.abspath(out).encode())
        vars_ = {k: C.c_char_p(v.encode()) for k, v in VARS.items()}
        log_fn = LOG_CB(lambda level, fmt: None)
        log_iface = LogIface(C.cast(log_fn, C.c_void_p))

        def env(cmd, data):
            cmd &= 0xFFFF
            if cmd in (9, 31):  # system / save directory
                C.cast(data, C.POINTER(C.c_char_p))[0] = sysdir
                return True
            if cmd == 10:  # pixel format
                self.pixfmt = C.cast(data, C.POINTER(C.c_int))[0]
                return True
            if cmd == 27:  # log interface
                C.cast(data, C.POINTER(LogIface))[0] = log_iface
                return True
            if cmd == 15:  # core option
                key = C.cast(data, C.POINTER(C.c_char_p))[0].decode()
                if key in vars_:
                    C.cast(data, C.POINTER(C.c_char_p))[1] = vars_[key]
                    return True
                return False
            if cmd == 3:  # can dupe
                C.cast(data, C.POINTER(C.c_bool))[0] = True
                return True
            return False

        def video(data, w, h, pitch):
            if data:
                self.last = (C.string_at(data, pitch * h), w, h, pitch)

        def inp(port, device, index, id_):
            if port:
                return 0
            if device == 1:
                return int(id_ in self.held)
            if device == 6 and self.touch:
                x, y = self.touch
                if id_ == 0:
                    return int((x + 0.5) * 0x10000 / W) - 0x8000
                if id_ == 1:
                    return int((192 + y + 0.5) * 0x10000 / H) - 0x8000
                if id_ == 2:
                    return 1
            return 0

        # ctypes callbacks must stay referenced for the life of the core.
        self._keep = (sysdir, vars_, log_fn, log_iface, ENV_CB(env), VID_CB(video), AUD_CB(lambda l, r: None),
                      AUDB_CB(lambda d, n: n), POLL_CB(lambda: None), IN_CB(inp))
        c = self.core
        c.retro_set_environment(self._keep[4])
        c.retro_set_video_refresh(self._keep[5])
        c.retro_set_audio_sample(self._keep[6])
        c.retro_set_audio_sample_batch(self._keep[7])
        c.retro_set_input_poll(self._keep[8])
        c.retro_set_input_state(self._keep[9])
        c.retro_init()
        data = open(rom, "rb").read()
        self._rom = C.create_string_buffer(data, len(data))
        gi = GameInfo(os.path.abspath(rom).encode(), C.cast(self._rom, C.c_void_p), len(data), None)
        if not c.retro_load_game(C.byref(gi)):
            raise SystemExit("core rejected the ROM")
        c.retro_serialize_size.restype = C.c_size_t

    def run(self, n):
        for _ in range(n):
            self.core.retro_run()
            self.frame += 1

    def load(self, path):
        data = open(path, "rb").read()
        if not self.core.retro_unserialize(C.c_char_p(data), C.c_size_t(len(data))):
            raise SystemExit(f"cannot load {path}")

    def save(self, path):
        n = self.core.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.core.retro_serialize(buf, C.c_size_t(n)):
            raise SystemExit("serialize failed")
        open(path, "wb").write(buf.raw)

    def shot(self, name):
        data, w, h, pitch = self.last
        to_image(data, w, h, pitch, self.pixfmt).save(os.path.join(self.out, name + ".png"))

    def command(self, line):
        p = line.split()
        if not p or p[0].startswith("#"):
            return
        op, a = p[0], p[1:]

        def num(i, d):
            return int(a[i]) if len(a) > i else d
        if op == "wait":
            self.run(int(a[0]))
        elif op == "press":
            self.held = {BUTTONS[b] for b in a[0].split("+")}
            self.run(num(1, 6))
            self.held = set()
            self.run(num(2, 20))
        elif op == "a":
            for _ in range(int(a[0])):
                self.held = {BUTTONS["a"]}
                self.run(4)
                self.held = set()
                self.run(num(1, 30) - 4)
        elif op == "touch":
            self.touch = (int(a[0]), int(a[1]))
            self.run(num(2, 6))
            self.touch = None
            self.run(num(3, 20))
        elif op == "shot":
            self.shot(a[0])
        elif op == "every":
            n, k = int(a[0]), int(a[1])
            for _ in range(n // k):
                self.run(k)
                self.shot(f"{a[2]}_{self.frame:05d}")
        else:
            raise SystemExit(f"unknown command {op!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--core", default=os.environ.get("DESMUME_CORE"))
    ap.add_argument("--state")
    ap.add_argument("--save")
    ap.add_argument("--cmd", default="")
    a = ap.parse_args()
    if not a.core:
        raise SystemExit("--core 또는 DESMUME_CORE 로 desmume_libretro 경로를 주세요")
    pl = Player(a.core, a.rom, a.out)
    if a.state:
        pl.run(1)
        pl.load(a.state)
    for line in a.cmd.split(";"):
        pl.command(line.strip())
    if a.save:
        pl.save(a.save)
    if pl.last:
        pl.shot("last")


if __name__ == "__main__":
    main()
