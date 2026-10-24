"""NDS DQ4 를 desmume libretro 코어로 돌리며 입력·화면·세이브스테이트·RAM 을 다룬다.

    uv run --locked python nds/dq4/tools/ndsplay.py ROM OUTDIR [--state IN] [--save OUT] [--cmd "..."] [SCRIPT]

코어는 `--core` 나 환경 변수 `DESMUME_CORE`(desmume_libretro.dylib/.so 경로)로 준다. 그래픽 형식 확인에도 쓴다(nds/dq4/docs/graphics-format.md).
명령은 한 줄에 하나, `;` 로도 나눈다. 주소·값은 16진(0x 생략 가능)이다.

    wait N                      N 프레임 그대로
    press BTN[+BTN] [N] [W]     버튼을 N(기본 6) 프레임 누르고 W(기본 20) 프레임 기다림
    hold BTN[+BTN] N            버튼을 누른 채 N 프레임(걷기)
    a K [P]                     A 를 K 번, P(기본 30) 프레임 간격
    touch X Y [N] [W]           아래 화면 (X, Y) 를 N(기본 6) 프레임 누름, 뒤에 W(기본 20) 기다림
    drag X1 Y1 X2 Y2 [N] [W]    끌기
    shot NAME                   OUTDIR/NAME.png (위·아래 화면을 위아래로 붙임, 256x384)
    every N K NAME              N 프레임 동안 K 프레임마다 NAME_<프레임>.png
    poke ADDR HEX               ADDR 부터 바이트열 HEX 를 씀(예: poke 21080b4 0e000000)
    poke32 ADDR VAL             32비트 값 하나를 씀
    freeze ADDR HEX             매 프레임 전에 다시 씀(unfreeze ADDR 로 풂)
    peek ADDR N                 N 바이트를 16진으로 찍음
    dump NAME [ADDR LEN]        OUTDIR/NAME.bin 에 메인 RAM(기본 4MB 전체)을 씀
    until ADDR VAL [MAXF] [W]   ADDR 의 값(VAL 의 자릿수만큼: 2·4·8)이 VAL 이 될 때까지(기본 최대 3600 프레임)
    mash BTN K [P]              BTN 을 K 번, P(기본 20) 프레임 간격
    save PATH / load PATH       세이브스테이트(코어의 retro_serialize 그대로)
    log TEXT                    stdout 에 프레임 번호와 함께 찍음
버튼: a b x y l r start select up down left right
"""
import argparse
import ctypes as C
import os
import sys

from kr_patch.sfc.libretro import (AUD_CB, AUDB_CB, ENV_CB, IN_CB, LOG_CB, POLL_CB, VID_CB, GameInfo, LogIface,
                                    load_core, to_image)

BUTTONS = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
           "a": 8, "x": 9, "l": 10, "r": 11}
VARS = {"desmume_pointer_mouse": "enabled", "desmume_pointer_type": "touch"}
W, H = 256, 384
RAM_BASE, RAM_SIZE = 0x02000000, 0x400000


def core_path(arg=None):
    p = arg or os.environ.get("DESMUME_CORE")
    if not p:
        raise SystemExit("desmume libretro 코어 경로를 --core 나 DESMUME_CORE 로 주세요")
    return p


class Player:
    def __init__(self, core, rom, out="."):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.core = load_core(core)
        self.held, self.touch = set(), None
        self.pixfmt, self.last = 0, None
        self.frame = 0
        self.frozen = {}
        sysdir = C.c_char_p(os.path.abspath(out).encode())
        vars_ = {k: C.c_char_p(v.encode()) for k, v in VARS.items()}
        log_fn = LOG_CB(lambda level, fmt: None)
        log_iface = LogIface(C.cast(log_fn, C.c_void_p))

        def env(cmd, data):
            cmd &= 0xFFFF
            if cmd in (9, 31):
                C.cast(data, C.POINTER(C.c_char_p))[0] = sysdir
                return True
            if cmd == 10:
                self.pixfmt = C.cast(data, C.POINTER(C.c_int))[0]
                return True
            if cmd == 27:
                C.cast(data, C.POINTER(LogIface))[0] = log_iface
                return True
            if cmd == 15:
                key = C.cast(data, C.POINTER(C.c_char_p))[0].decode()
                if key in vars_:
                    C.cast(data, C.POINTER(C.c_char_p))[1] = vars_[key]
                    return True
                return False
            if cmd == 3:
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
            if device == 6 and self.touch:   # RETRO_DEVICE_POINTER
                x, y = self.touch
                if id_ == 0:
                    return int((x + 0.5) * 0x10000 / W) - 0x8000
                if id_ == 1:
                    return int((192 + y + 0.5) * 0x10000 / H) - 0x8000
                if id_ == 2:
                    return 1
            return 0

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
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        self._ram = None

    # --- RAM ---------------------------------------------------------------
    def ram(self):
        """메인 RAM 4MB(0x02000000~)를 가리키는 ctypes 배열. 코어가 쓰는 메모리 그 자체다."""
        if self._ram is None:
            p = self.core.retro_get_memory_data(2)
            self._ram = (C.c_ubyte * RAM_SIZE).from_address(p)
        return self._ram

    @staticmethod
    def _off(addr):
        off = (addr - RAM_BASE) & (RAM_SIZE - 1) if addr >= RAM_BASE else addr
        return off

    def read(self, addr, n):
        o = self._off(addr)
        return bytes(self.ram()[o:o + n])

    def write(self, addr, data):
        o = self._off(addr)
        self.ram()[o:o + len(data)] = list(data)

    def u8(self, addr):
        return self.read(addr, 1)[0]

    def u16(self, addr):
        return int.from_bytes(self.read(addr, 2), "little")

    def u32(self, addr):
        return int.from_bytes(self.read(addr, 4), "little")

    def w32(self, addr, v):
        self.write(addr, (v & 0xFFFFFFFF).to_bytes(4, "little"))

    # --- 실행 ----------------------------------------------------------------
    def run(self, n=1):
        for _ in range(n):
            for a, d in self.frozen.items():
                self.write(a, d)
            self.core.retro_run()
            self.frame += 1

    def load(self, path):
        if not self.frame:
            self.run(1)
        data = open(path, "rb").read()
        if not self.core.retro_unserialize(C.c_char_p(data), C.c_size_t(len(data))):
            raise SystemExit(f"cannot load {path}")

    def save(self, path):
        n = self.core.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.core.retro_serialize(buf, C.c_size_t(n)):
            raise SystemExit("serialize failed")
        open(path, "wb").write(buf.raw)

    def image(self):
        data, w, h, pitch = self.last
        return to_image(data, w, h, pitch, self.pixfmt)

    def shot(self, name):
        path = name if os.path.isabs(name) else os.path.join(self.out, name + ".png")
        self.image().save(path)
        return path

    def press(self, buttons, n=6, w=20):
        self.held = {BUTTONS[b] for b in buttons.split("+")}
        self.run(n)
        self.held = set()
        self.run(w)

    def hold(self, buttons, n):
        self.held = {BUTTONS[b] for b in buttons.split("+")}
        self.run(n)
        self.held = set()

    def tap(self, x, y, n=6, w=20):
        self.touch = (x, y)
        self.run(n)
        self.touch = None
        self.run(w)

    def until(self, addr, val, width, maxf=3600):
        for _ in range(maxf):
            if int.from_bytes(self.read(addr, width), "little") == val:
                return True
            self.run(1)
        return False

    def command(self, line):
        p = line.split()
        if not p or p[0].startswith("#"):
            return
        op, a = p[0], p[1:]
        num = lambda i, d: int(a[i]) if len(a) > i else d
        hx = lambda s: int(s, 16)
        if op == "wait":
            self.run(int(a[0]))
        elif op == "press":
            self.press(a[0], num(1, 6), num(2, 20))
        elif op == "hold":
            self.hold(a[0], int(a[1]))
        elif op == "a":
            for _ in range(int(a[0])):
                self.press("a", 4, num(1, 30) - 4)
        elif op == "mash":
            for _ in range(int(a[1])):
                self.press(a[0], 4, num(2, 20) - 4)
        elif op == "touch":
            self.tap(int(a[0]), int(a[1]), num(2, 6), num(3, 20))
        elif op == "drag":
            x1, y1, x2, y2 = (int(v) for v in a[:4])
            n = num(4, 20)
            for k in range(n + 1):
                self.touch = (round(x1 + (x2 - x1) * k / n), round(y1 + (y2 - y1) * k / n))
                self.run(1)
            self.touch = None
            self.run(num(5, 20))
        elif op == "shot":
            self.shot(a[0])
        elif op == "poke":
            self.write(hx(a[0]), bytes.fromhex(a[1]))
        elif op == "poke32":
            self.w32(hx(a[0]), hx(a[1]))
        elif op == "freeze":
            self.frozen[hx(a[0])] = bytes.fromhex(a[1])
        elif op == "unfreeze":
            self.frozen.pop(hx(a[0]), None)
        elif op == "peek":
            print(f"{self.frame:6d} {hx(a[0]):08x}: {self.read(hx(a[0]), int(a[1], 0)).hex(' ')}")
        elif op == "dump":
            addr, n = (hx(a[1]), hx(a[2])) if len(a) > 2 else (RAM_BASE, RAM_SIZE)
            open(os.path.join(self.out, a[0] + ".bin"), "wb").write(self.read(addr, n))
        elif op == "until":
            width = max(1, (len(a[1]) + 1) // 2)
            ok = self.until(hx(a[0]), hx(a[1]), width, num(2, 3600))
            if not ok:
                print(f"{self.frame:6d} until {a[0]}=={a[1]}: timeout", file=sys.stderr)
            self.run(num(3, 0))
        elif op == "save":
            self.save(a[0])
        elif op == "load":
            self.load(a[0])
        elif op == "every":
            n, k = int(a[0]), int(a[1])
            for _ in range(n // k):
                self.run(k)
                self.shot(f"{a[2]}_{self.frame:05d}")
        elif op == "log":
            print(f"{self.frame:6d} {' '.join(a)}")
        else:
            raise SystemExit(f"unknown command {op!r}")

    def script(self, text):
        for line in text.replace(";", "\n").splitlines():
            self.command(line.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("script", nargs="?")
    ap.add_argument("--core")
    ap.add_argument("--state")
    ap.add_argument("--save")
    ap.add_argument("--cmd", default="")
    a = ap.parse_args()
    pl = Player(core_path(a.core), a.rom, a.out)
    if a.state:
        pl.load(a.state)
    if a.script:
        pl.script(open(a.script).read())
    pl.script(a.cmd)
    if a.save:
        pl.save(a.save)
    if pl.last:
        pl.shot("last")


if __name__ == "__main__":
    main()
