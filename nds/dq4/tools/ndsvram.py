"""desmume 세이브스테이트에서 메인 RAM·VRAM·I/O 레지스터·팔레트·OAM 을 꺼내 2D 화면을 다시 그린다.

nds/dq4/docs/graphics-format.md 의 화면 비교 실험에 쓴다.

    uv run --locked python nds/dq4/tools/ndsvram.py info STATE           레이어 설정(DISPCNT, BGnCNT, VRAMCNT)
    uv run --locked python nds/dq4/tools/ndsvram.py bg STATE OUT.png ENGINE N   BG N 의 전체 화면 맵을 그림(ENGINE a|b)

상태 파일은 ndsplay.py 의 `save`(코어의 retro_serialize) 결과다. 덩어리 4(메모리)의 항목은
이름 4바이트, 원소 크기 u32, 원소 수 u32, 자료 순서이고 `WRAM`(메인 RAM 4MB), `9REG`(ARM9 I/O
0x04000000~), `VMEM`(팔레트 2KB), `OAMS`(OAM 2KB), `LCDM`(VRAM 뱅크 A~I 를 이은 656KB)를 쓴다.
"""
import argparse
import struct

from PIL import Image

# VRAM banks in LCDM order: (name, size)
BANKS = [("A", 0x20000), ("B", 0x20000), ("C", 0x20000), ("D", 0x20000), ("E", 0x10000),
         ("F", 0x4000), ("G", 0x4000), ("H", 0x8000), ("I", 0x4000)]


def chunks(st):
    out, o = {}, 32
    while o + 8 <= len(st):
        cid, sz = struct.unpack_from("<II", st, o)
        if cid == 0xFFFFFFFF:
            break
        out[cid] = (o + 8, sz)
        o += 8 + sz
    return out


class State:
    def __init__(self, path):
        st = open(path, "rb").read()
        o, sz = chunks(st)[4]
        end = o + sz
        self.mem = {}
        while o < end:
            name = st[o:o + 4].decode("latin-1")
            esz, cnt = struct.unpack_from("<II", st, o + 4)
            self.mem[name] = st[o + 12:o + 12 + esz * cnt]
            o += 12 + esz * cnt
        self.ram = self.mem["WRAM"]
        self.io = self.mem["9REG"]
        self.pal = self.mem["VMEM"]
        self.oam = self.mem["OAMS"]
        lcd = self.mem["LCDM"]
        self.bank, p = {}, 0
        for name, size in BANKS:
            self.bank[name] = lcd[p:p + size]
            p += size

    def r16(self, a):
        return struct.unpack_from("<H", self.io, a - 0x04000000)[0]

    def r32(self, a):
        return struct.unpack_from("<I", self.io, a - 0x04000000)[0]

    def vramcnt(self):
        return {name: self.io[0x240 + i + (1 if i >= 7 else 0)] for i, (name, _) in enumerate(BANKS)}

    def bg_vram(self, engine):
        """Bytes of the BG VRAM window of an engine, built from the bank mapping."""
        size = 0x80000 if engine == "a" else 0x20000
        out = bytearray(size)
        for name, cnt in self.vramcnt().items():
            if not cnt & 0x80:
                continue
            mst, ofs = cnt & 7, cnt >> 3 & 3
            data = self.bank[name]
            if engine == "a" and mst == 1:
                if name in "ABCD":
                    base = ofs * 0x20000
                elif name == "E":
                    base = 0
                else:  # F, G
                    base = (ofs & 1) * 0x4000 + (ofs >> 1) * 0x10000
            elif engine == "b" and mst == 4 and name == "C":
                base = 0
            elif engine == "b" and name in "HI" and mst == 1:
                base = 0 if name == "H" else 0x8000
            else:
                continue
            out[base:base + len(data)] = data[:max(0, min(len(data), size - base))]
        return bytes(out)

    def info(self):
        lines = []
        for eng, base in (("a", 0x04000000), ("b", 0x04001000)):
            disp = self.r32(base)
            lines.append(f"engine {eng} DISPCNT {disp:08X} mode {disp & 7} BG0-3/OBJ on {disp >> 8 & 31:05b} BG0 3D {disp >> 3 & 1}")
            for n in range(4):
                cnt = self.r16(base + 8 + 2 * n)
                lines.append(f"  BG{n}CNT {cnt:04X} pri {cnt & 3} char {(cnt >> 2 & 15) * 0x4000:#x} 8bpp {cnt >> 7 & 1} "
                             f"screen {(cnt >> 8 & 31) * 0x800:#x} size {cnt >> 14} hofs {self.r16(base + 0x10 + 4 * n)} "
                             f"vofs {self.r16(base + 0x12 + 4 * n)}")
        lines.append("VRAMCNT " + " ".join(f"{k}:{v:02X}" for k, v in self.vramcnt().items()))
        return "\n".join(lines)

    def bg_text(self, engine, n):
        """Text BG N as an image of its whole screen map, with the engine's BG palette (or extended)."""
        base = 0x04000000 if engine == "a" else 0x04001000
        disp = self.r32(base)
        cnt = self.r16(base + 8 + 2 * n)
        vram = self.bg_vram(engine)
        char = (cnt >> 2 & 15) * 0x4000 + (disp >> 24 & 7) * 0x10000 * (engine == "a")
        scr = (cnt >> 8 & 31) * 0x800 + (disp >> 27 & 7) * 0x10000 * (engine == "a")
        bpp8 = cnt >> 7 & 1
        wtiles, htiles = [(32, 32), (64, 32), (32, 64), (64, 64)][cnt >> 14]
        palbase = 0 if engine == "a" else 0x400
        pal = [struct.unpack_from("<H", self.pal, palbase + 2 * i)[0] for i in range(256)]
        img = Image.new("RGBA", (wtiles * 8, htiles * 8))
        px = img.load()
        for ty in range(htiles):
            for tx in range(wtiles):
                blk = (ty // 32) * (2 if wtiles == 64 else 1) + tx // 32
                e = struct.unpack_from("<H", vram, scr + blk * 0x800 + ((ty % 32) * 32 + tx % 32) * 2)[0]
                t, hf, vf, pn = e & 0x3FF, e >> 10 & 1, e >> 11 & 1, e >> 12
                for y in range(8):
                    for x in range(8):
                        sx, sy = (7 - x if hf else x), (7 - y if vf else y)
                        if bpp8:
                            c = vram[char + t * 64 + sy * 8 + sx]
                            col = pal[c]
                        else:
                            c = vram[char + t * 32 + sy * 4 + sx // 2] >> (sx % 2 * 4) & 15
                            col = pal[pn * 16 + c]
                        r, g, b = col & 31, col >> 5 & 31, col >> 10 & 31
                        px[tx * 8 + x, ty * 8 + y] = (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 0 if c == 0 else 255)
        return img

    def screen_map(self, engine, n):
        """[(tile, hflip, vflip, palette)] of a text BG, row-major over the whole map."""
        base = 0x04000000 if engine == "a" else 0x04001000
        disp = self.r32(base)
        cnt = self.r16(base + 8 + 2 * n)
        vram = self.bg_vram(engine)
        scr = (cnt >> 8 & 31) * 0x800 + (disp >> 27 & 7) * 0x10000 * (engine == "a")
        wtiles, htiles = [(32, 32), (64, 32), (32, 64), (64, 64)][cnt >> 14]
        out = []
        for ty in range(htiles):
            for tx in range(wtiles):
                blk = (ty // 32) * (2 if wtiles == 64 else 1) + tx // 32
                e = struct.unpack_from("<H", vram, scr + blk * 0x800 + ((ty % 32) * 32 + tx % 32) * 2)[0]
                out.append((e & 0x3FF, e >> 10 & 1, e >> 11 & 1, e >> 12))
        return out, wtiles, htiles


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info")
    s.add_argument("state")
    b = sub.add_parser("bg")
    b.add_argument("state")
    b.add_argument("out")
    b.add_argument("engine", choices=["a", "b"])
    b.add_argument("n", type=int)
    a = ap.parse_args()
    st = State(a.state)
    if a.cmd == "info":
        print(st.info())
    else:
        st.bg_text(a.engine, a.n).save(a.out)


if __name__ == "__main__":
    main()
