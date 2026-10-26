"""NDS DQ4 graphics decoder and extractor; nds/dq4/docs/graphics-format.md.

Reads the file system unpacked by `krpatch nds unpack` (default work/nds/jp) and
writes PNG files for reference only. Nothing here writes into the unpacked tree.

    uv run --locked python nds/dq4/tools/ndsgfx.py survey [--root work/nds/jp]
    uv run --locked python nds/dq4/tools/ndsgfx.py export OUT [--root ...] [--only chr,monster]
    uv run --locked python nds/dq4/tools/ndsgfx.py gallery OUT
    uv run --locked python nds/dq4/tools/ndsgfx.py locn MAP [--root ...]     LOCN faces and triggers of MAP/<MAP>.lz
    uv run --locked python nds/dq4/tools/ndsgfx.py motion [--root ...]       battle motion table (overlay 3)
"""

import argparse
import html
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from kr_patch import lz11
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FS = ROOT / "work" / "nds" / "jp"


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def s32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def magic(b, n=16):
    return b[:n].split(b"\0")[0].decode("latin-1")


def unlz(data):
    """Return the payload: LZ10/LZ11-compressed files start with 0x10/0x11."""
    if data[:1] in (b"\x10", b"\x11"):
        try:
            out, _ = lz11.decompress(data)
            return bytes(out)
        except ValueError:
            pass
    return data


# ---------------------------------------------------------------- colours

def bgr555(v):
    r, g, b = v & 31, v >> 5 & 31, v >> 10 & 31
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def palette(b, off=0, n=None):
    n = (len(b) - off) // 2 if n is None else n
    return [bgr555(u16(b, off + 2 * i)) for i in range(n) if off + 2 * i + 2 <= len(b)]


def grey(n):
    return [(i * 255 // max(1, n - 1),) * 3 for i in range(n)]


# ---------------------------------------------------------------- textures

# NDS 3D texture formats (GBATEK "DS 3D Texture Formats").
TEX_BPP = {1: 8, 2: 2, 3: 4, 4: 8, 5: 2, 6: 8, 7: 16}
TEX_NAME = {1: "A3I5", 2: "4색", 3: "16색", 4: "256색", 5: "4x4압축", 6: "A5I3", 7: "직접색"}


def texture(data, fmt, width, height, pal, transparent0=True, pidx=b""):
    """RGBA image of a NDS texture. `pidx` is the palette-index block of format 5."""
    img = Image.new("RGBA", (width, height))
    px = []
    pal = list(pal) + [(255, 0, 255)] * max(0, 256 - len(pal))
    if fmt in (2, 3, 4):
        bpp = TEX_BPP[fmt]
        per = 8 // bpp
        mask = (1 << bpp) - 1
        for i in range(width * height):
            byte = data[i // per] if i // per < len(data) else 0
            c = byte >> (i % per * bpp) & mask
            a = 0 if (c == 0 and transparent0) else 255
            px.append(pal[c] + (a,))
    elif fmt in (1, 6):
        ibits = 5 if fmt == 1 else 3
        for i in range(width * height):
            v = data[i] if i < len(data) else 0
            c = v & ((1 << ibits) - 1)
            a = v >> ibits
            a = (a * 4 + a // 2) if fmt == 1 else a
            a = a * 255 // (7 * 4 + 3 if fmt == 1 else 31)
            px.append(pal[c] + (a,))
    elif fmt == 7:
        for i in range(width * height):
            v = u16(data, 2 * i) if 2 * i + 2 <= len(data) else 0
            px.append(bgr555(v) + (255 if v & 0x8000 else 0,))
    elif fmt == 5:
        return texture4x4(data, pidx, width, height, pal)
    else:
        raise ValueError(f"texture format {fmt}")
    img.putdata(px)
    return img


def _mix(a, b, wa, wb):
    return tuple((x * wa + y * wb) // (wa + wb) for x, y in zip(a, b))


def texture4x4(data, pidx, width, height, pal):
    img = Image.new("RGBA", (width, height))
    pix = img.load()
    bw = width // 4
    for blk in range(width * height // 16):
        if blk * 4 + 4 > len(data):
            break
        bits = u32(data, blk * 4)
        info = u16(pidx, blk * 2) if blk * 2 + 2 <= len(pidx) else 0
        base = (info & 0x3FFF) * 2
        mode = info >> 14
        p = [pal[(base + k) % len(pal)] if base + k < len(pal) else (0, 0, 0) for k in range(4)]
        cols = [p[0] + (255,), p[1] + (255,)]
        if mode == 0:
            cols += [p[2] + (255,), (0, 0, 0, 0)]
        elif mode == 1:
            cols += [_mix(p[0], p[1], 1, 1) + (255,), (0, 0, 0, 0)]
        elif mode == 2:
            cols += [p[2] + (255,), p[3] + (255,)]
        else:
            cols += [_mix(p[0], p[1], 5, 3) + (255,), _mix(p[0], p[1], 3, 5) + (255,)]
        bx, by = blk % bw * 4, blk // bw * 4
        for k in range(16):
            pix[bx + k % 4, by + k // 4] = cols[bits >> (2 * k) & 3]
    return img


# ---------------------------------------------------------------- custom containers

def texture_object(b, off=0):
    """`TextureObject` (Arte Piazza engine): one texture with its palettes.

    +0x20 format, +0x24/+0x28 log2(width/8)/log2(height/8), +0x30 size,
    +0x34 offset, +0x38 palette size, +0x3C palette offset, +0x18 count of
    extra palette blocks listed as (size, offset) from +0x58. Offsets are
    relative to the object. Rows = size / bytes per row (the stored height
    is the power-of-two texture size; data may be shorter).
    """
    fmt = u32(b, off + 0x20)
    width = 8 << u32(b, off + 0x24)
    hmax = 8 << u32(b, off + 0x28)
    size, doff = u32(b, off + 0x30), u32(b, off + 0x34)
    psize, poff = u32(b, off + 0x38), u32(b, off + 0x3C)
    rows = min(hmax, size * 8 // TEX_BPP[fmt] // width)
    pal = palette(b, off + poff, psize // 2)
    extra = []
    for i in range(u32(b, off + 0x18)):
        es, eo = u32(b, off + 0x58 + 8 * i), u32(b, off + 0x5C + 8 * i)
        extra.append(palette(b, off + eo, es // 2))
    return dict(fmt=fmt, width=width, height=rows, hmax=hmax,
                data=b[off + doff: off + doff + size], pal=pal, extra=extra,
                end=off + max(doff + size, poff + psize))


def texture_object_image(t, pal=None, transparent0=True):
    return texture(t["data"], t["fmt"], t["width"], t["height"], pal or t["pal"], transparent0)


def pack_entries(b, off=0):
    """Entries of the engine's packs (`TexturePack`, `MapPackData`, `EffectPack`,
    `MonsterAnimation`, `PaletteAnimation`): +0x10 count, +0x14 data start,
    (offset, size) pairs from +0x20 with offsets relative to the data start.
    Returns [(absolute offset, size)]; empty slots have size 0."""
    n, base = u32(b, off + 0x10), off + u32(b, off + 0x14)
    return [(base + u32(b, off + 0x20 + 8 * i), u32(b, off + 0x24 + 8 * i)) for i in range(n)]


def texture_pack(b, off=0):
    return [texture_object(b, eo) for eo, es in pack_entries(b, off)
            if es and b[eo:eo + 13] == b"TextureObject"]


# ---------------------------------------------------------------- Nitro BMD0 / BTX0

def nitro_dict(b, off):
    """Nitro info block: [(name, entry bytes)]."""
    n = b[off + 1]
    unk = u16(b, off + 6)
    eoff = off + unk
    esize, _ = u16(b, eoff), u16(b, eoff + 2)
    entries = [b[eoff + 4 + i * esize: eoff + 4 + (i + 1) * esize] for i in range(n)]
    noff = eoff + 4 + n * esize
    names = [b[noff + 16 * i: noff + 16 * i + 16].split(b"\0")[0].decode("latin-1") for i in range(n)]
    return list(zip(names, entries))


def nitro_blocks(b, off=0):
    """{tag: offset} of the blocks of a Nitro file (BMD0, BTX0, ...)."""
    nblk = u16(b, off + 0xE)
    out = {}
    for i in range(nblk):
        bo = off + u32(b, off + 0x10 + 4 * i)
        out[b[bo:bo + 4].decode("latin-1")] = bo
    return out


def tex0(b, off):
    """Textures and palettes of a TEX0 block: ({name: tex}, {name: palette bytes})."""
    tdata = off + u32(b, off + 0x14)
    tinfo = off + u16(b, off + 0x0E)
    cdata = off + u32(b, off + 0x24)
    cidx = off + u32(b, off + 0x28)
    psize = u32(b, off + 0x30) << 3
    pinfo = off + u32(b, off + 0x34)
    pdata = off + u32(b, off + 0x38)
    texs = {}
    for name, e in nitro_dict(b, tinfo):
        toff = u16(e, 0) << 3
        par = u16(e, 2)
        w, h = 8 << (par >> 4 & 7), 8 << (par >> 7 & 7)
        fmt, c0 = par >> 10 & 7, par >> 13 & 1
        if fmt == 0:
            continue
        nbytes = w * h * TEX_BPP[fmt] // 8
        if fmt == 5:
            data = b[cdata + toff: cdata + toff + nbytes]
            pidx = b[cidx + toff // 2: cidx + toff // 2 + nbytes // 2]
        else:
            data, pidx = b[tdata + toff: tdata + toff + nbytes], b""
        texs[name] = dict(fmt=fmt, width=w, height=h, c0=c0, data=data, pidx=pidx)
    pals = {}
    for name, e in nitro_dict(b, pinfo):
        poff = u16(e, 0) << 3
        pals[name] = b[pdata + poff: pdata + psize]
    return texs, pals


def mdl0_pairs(b, off):
    """[(texture, palette)] used by the materials of every model in a MDL0 block."""
    pairs = []
    for _, e in nitro_dict(b, off + 8):
        mo = off + u32(e, 0)
        mat = mo + u32(b, mo + 8)
        tex_dict = mat + u16(b, mat)
        pal_dict = mat + u16(b, mat + 2)
        tmat, pmat = {}, {}
        for dct, dest in ((tex_dict, tmat), (pal_dict, pmat)):
            for name, ent in nitro_dict(b, dct):
                lo, cnt = u16(ent, 0), ent[2]
                for k in range(cnt):
                    dest[b[mat + lo + k]] = name
        for m, t in sorted(tmat.items()):
            pairs.append((t, pmat.get(m)))
    return pairs


def nitro_textures(b, off=0):
    """[(name, RGBA image)] of every texture in a BMD0/BTX0 at `off`, paired by material."""
    blocks = nitro_blocks(b, off)
    if "TEX0" not in blocks:
        return []
    texs, pals = tex0(b, blocks["TEX0"])
    pairs = []
    if "MDL0" in blocks:
        try:
            pairs = mdl0_pairs(b, blocks["MDL0"])
        except (struct.error, IndexError):
            pairs = []
    pal_of = {}
    for t, p in pairs:
        pal_of.setdefault(t, p)
    out = []
    for name, t in texs.items():
        pname = pal_of.get(name)
        if pname not in pals:
            pname = name + "_pl" if name + "_pl" in pals else (next(iter(pals)) if pals else None)
        pal = palette(pals[pname]) if pname else grey(256)
        if not pal:
            pal = grey(256)
        img = texture(t["data"], t["fmt"], t["width"], t["height"], pal, bool(t["c0"]), t["pidx"])
        out.append((name, img))
    return out


def texture_data(b):
    """`TextureData` / `Texture Data`: 8bpp linear, offsets relative to +0x38.

    +0x24 data offset, +0x2C size, +0x30 palette offset, +0x34 palette size,
    +0x38/+0x3A width/height.
    """
    base = 0x38
    doff, size = base + u32(b, 0x24), u32(b, 0x2C)
    poff, psize = base + u32(b, 0x30), u32(b, 0x34)
    w, h = u16(b, 0x38), u16(b, 0x3A)
    pal = palette(b, poff, psize // 2)
    return texture(b[doff:doff + size], 4, w, min(h, size // w), pal)


# ---------------------------------------------------------------- 2D (G2D)

def tiles(data, pal, bpp, cols=32, transparent0=False):
    """8x8 tile sheet of raw character data (4 or 8 bpp, no screen map)."""
    tsize = 8 * bpp
    n = len(data) // tsize
    rows = max(1, (n + cols - 1) // cols)
    img = Image.new("RGBA", (cols * 8, rows * 8))
    pal = list(pal) + [(255, 0, 255)] * max(0, 256 - len(pal))
    pix = img.load()
    for t in range(n):
        tx, ty = t % cols * 8, t // cols * 8
        for i in range(64):
            if bpp == 4:
                c = data[t * 32 + i // 2] >> (i % 2 * 4) & 15
            else:
                c = data[t * 64 + i]
            pix[tx + i % 8, ty + i // 8] = pal[c] + (0 if (c == 0 and transparent0) else 255,)
    return img


def mpt0(b):
    """`MPT0` resource pack: [(id, payload)]. +0x10 count, +0x14 table offset,
    +0x18 table size; entries are u16 id, u16 size, u16 order; data follows the table."""
    n, toff, tsize = u32(b, 0x10), u32(b, 0x14), u32(b, 0x18)
    pos = toff + tsize
    out = []
    for i in range(n):
        rid, size = u16(b, toff + 6 * i), u16(b, toff + 6 * i + 2)
        out.append((rid, b[pos:pos + size]))
        pos += size
    return out


def icon_sheet(b, side, cols=16):
    """Icons of a G2D/ICON `.mpt`: 8bpp `side`x`side` icons stored as 8x8 tiles
    (OBJ order), palette in the 512-byte entry with id 9998 or 9999."""
    ents = mpt0(b)
    pal = next((palette(d) for rid, d in ents if rid >= 9998), grey(256))
    icons = [d for rid, d in ents if rid < 9998]
    rows = max(1, (len(icons) + cols - 1) // cols)
    sheet = Image.new("RGBA", (cols * (side + 2), rows * (side + 2)))
    for i, d in enumerate(icons):
        img = tiles(d, pal, 8, side // 8, transparent0=True)
        sheet.alpha_composite(img, (i % cols * (side + 2), i // cols * (side + 2)))
    return sheet, len(icons)


def tim(b):
    """`.tim` snapshot: +0x10 u16 width, u16 height, then BGR555 pixels from +0x14."""
    w, h = u16(b, 0x10), u16(b, 0x12)
    img = Image.new("RGBA", (w, h))
    img.putdata([bgr555(u16(b, 0x14 + 2 * i)) + (255,) for i in range(w * h)])
    return img


def nftr(b, cols=32):
    """Nitro font: (glyph sheet, glyph count). Glyphs in index order, MSB-first bits."""
    blocks = {}
    o = u16(b, 0xC)
    while o + 8 <= len(b):
        tag, size = b[o:o + 4], u32(b, o + 4)
        blocks[tag] = o
        if size == 0:
            break
        o += size
    g = blocks[b"PLGC"]
    cw, ch, gsize, bpp = b[g + 8], b[g + 9], u16(b, g + 10), b[g + 14]
    n = (u32(b, g + 4) - 16) // gsize
    mx = (1 << bpp) - 1
    rows = (n + cols - 1) // cols
    img = Image.new("L", (cols * (cw + 1) + 1, rows * (ch + 1) + 1), 96)
    pix = img.load()
    for k in range(n):
        bits = int.from_bytes(b[g + 16 + k * gsize: g + 16 + (k + 1) * gsize], "big")
        total = gsize * 8
        for i in range(cw * ch):
            v = bits >> (total - (i + 1) * bpp) & mx
            pix[1 + k % cols * (cw + 1) + i % cw, 1 + k // cols * (ch + 1) + i // cw] = 255 - v * 255 // mx
    return img, n


# ---------------------------------------------------------------- DSSA sprite animation

def dssa(b, off=0, size=None):
    """`DSSA` cut-out animation over one texture atlas.

    +0x10 cell count; cells from +0x20, 16 bytes: u32 flags, u16 top, left,
    bottom, right, pivot y, pivot x (pixels in the atlas; cell 0 is a 1x1
    dummy). Frames are `FRAM` blocks: u32 index, u32 record count, then
    16-byte records from +0x10: u16 cell (low 8 bits the cell; bits 8-11 the record
    kind, 0 part, 1 frame header, 2 not drawn; 0x1000 mirror left-right, 0x2000
    mirror top-bottom, 0x4000 translucent, see `translucent_atlas`), u16 -, s16 x,
    s16 y, u16 scale x, u16 scale y (4.12), u16 rotation, u8 alpha (0-31), u8 order.
    """
    n = u32(b, off + 0x10)
    cells = []
    for i in range(n):
        c = off + 0x20 + 16 * i
        cells.append(dict(top=u16(b, c + 4), left=u16(b, c + 6), bottom=u16(b, c + 8),
                          right=u16(b, c + 10), py=struct.unpack_from("<h", b, c + 12)[0],
                          px=struct.unpack_from("<h", b, c + 14)[0]))
    frames = []
    pos = off + 0x20 + 16 * n
    end = off + size if size else len(b)
    while True:
        f = b.find(b"FRAM", pos, end)
        if f < 0:
            break
        nxt = b.find(b"FRAM", f + 4, end)
        cnt = u32(b, f + 8)
        recs = []
        for k in range(cnt):
            r = f + 0x10 + 16 * k
            if r + 16 > len(b) or (nxt > 0 and r + 16 > nxt):
                break
            recs.append(dict(cell=b[r], kind=b[r + 1] & 0xF, flags=u16(b, r) >> 12, x=struct.unpack_from("<h", b, r + 4)[0],
                             y=struct.unpack_from("<h", b, r + 6)[0],
                             sx=struct.unpack_from("<h", b, r + 8)[0] / 4096,
                             sy=struct.unpack_from("<h", b, r + 10)[0] / 4096,
                             rot=u16(b, r + 12), alpha=b[r + 14], order=b[r + 15]))
        frames.append(recs)
        pos = f + 4
    return cells, frames


def translucent_atlas(t):
    """The atlas as the battle draws parts flagged 0x4000, or None.

    The game rebinds the same texels as A3I5 with the first attached palette when
    the texture's +0x18 is 1 (A5I3 for 2, which no file uses). Without an attached
    palette it rebinds nothing and the part looks like any other.
    """
    if t["fmt"] != 4 or not t["extra"]:
        return None
    return texture(t["data"], 1, t["width"], t["height"], t["extra"][0])


def dssa_frame(atlas, cells, recs, reverse=False, alpha_atlas=None):
    """Compose one frame. Returns (image, (min x, min y)) in sprite space."""
    parts = []
    for r in (reversed(recs) if reverse else recs):
        if r.get("kind") or r["cell"] == 0 or r["cell"] >= len(cells) or not r["sx"] or not r["sy"]:
            continue
        c = cells[r["cell"]]
        w, h = c["right"] - c["left"], c["bottom"] - c["top"]
        if w <= 0 or h <= 0:
            continue
        src = alpha_atlas if alpha_atlas is not None and r.get("flags", 0) & 4 else atlas
        im = src.crop((c["left"], c["top"], c["right"], c["bottom"]))
        sx, sy = r["sx"], r["sy"]
        if r.get("flags", 0) & 1:  # 0x1000 in the cell word: mirror left-right
            sx = -sx
        if r.get("flags", 0) & 2:  # 0x2000: mirror top-bottom
            sy = -sy
        if sx < 0:
            im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if sy < 0:
            im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        nw, nh = max(1, round(w * abs(sx))), max(1, round(h * abs(sy)))
        if (nw, nh) != (w, h):
            im = im.resize((nw, nh), Image.Resampling.NEAREST)
        px, py = c["px"] * abs(sx), c["py"] * abs(sy)
        if sx < 0:
            px = nw - px
        if sy < 0:
            py = nh - py
        if r["rot"]:
            ang = r["rot"] * 360 / 65536
            im = im.rotate(ang, Image.Resampling.NEAREST, expand=True, center=(px, py))
            # expand keeps the pivot near the centre; re-derive it.
            px, py = im.width / 2, im.height / 2
        if r["alpha"] < 31:
            a = im.getchannel("A").point(lambda v, k=r["alpha"]: v * k // 31)
            im.putalpha(a)
        parts.append((im, round(r["x"] - px), round(r["y"] - py)))
    if not parts:
        return None, (0, 0)
    x0 = min(p[1] for p in parts)
    y0 = min(p[2] for p in parts)
    x1 = max(p[1] + p[0].width for p in parts)
    y1 = max(p[2] + p[0].height for p in parts)
    out = Image.new("RGBA", (x1 - x0, y1 - y0))
    for im, x, y in parts:
        out.alpha_composite(im, (x - x0, y - y0))
    return out, (x0, y0)


# ---------------------------------------------------------------- LOCN collision

LOCN_KINDS = {0: "floor", 1: "wall", 2: "object"}


def locn(b):
    """`LOCN` collision block of a `MapPackData` (the third entry).

    +0x10 u16 face count, floors, walls, object faces, triggers; +0x34 ten u32
    offsets (from +0x10): faces, triggers, six sorted key lists (x min, x max,
    y max, y min, z min, z max as s16 coordinate*32 with u16 face), two per-face
    byte arrays the game fills while walking. A face is 96 bytes: fx32 quad,
    normal, u8 flag (1 on all but 2,326 faces), u8 kind (0 floor, 1 wall, 2 object), u16 trigger id,
    u16 0, u16 FMAP placement (objects), two fx32 xyz end points, u16 FMAP +0x2C.
    """
    n, nf, nw, no, nt = struct.unpack_from("<5H", b, 0x10)
    offs = [u32(b, 0x34 + 4 * i) + 0x10 for i in range(10)]
    faces = []
    for i in range(n):
        o = offs[0] + 96 * i
        v = struct.unpack_from("<15i", b, o)
        faces.append(dict(quad=[tuple(x / 4096 for x in v[k:k + 3]) for k in range(0, 12, 3)],
                          normal=tuple(x / 4096 for x in v[12:15]), flag=b[o + 0x3C], kind=b[o + 0x3D],
                          trigger=u16(b, o + 0x3E), placement=u16(b, o + 0x42),
                          ends=[tuple(s32(b, o + 0x44 + 12 * k + 4 * j) / 4096 for j in range(3)) for k in range(2)],
                          search=u16(b, o + 0x5C)))
    triggers = [struct.unpack_from("<2H", b, offs[1] + 4 * i) for i in range(nt)]
    return dict(counts=(n, nf, nw, no, nt), faces=faces, triggers=triggers)


def cmd_locn(root, name):
    b = unlz((Path(root) / "data" / "data" / "MAP" / f"{name}.lz").read_bytes())
    eo, es = pack_entries(b)[2]
    lc = locn(b[eo:eo + es])
    print("faces %d  floor %d  wall %d  object %d  trigger %d" % lc["counts"])
    trig = {f: t for t, f in lc["triggers"]}
    for i, f in enumerate(lc["faces"]):
        extra = f"  trigger {trig[i]:#06x}" if i in trig else ""
        if f["kind"] == 2:
            extra += f"  placement {f['placement']}  search {f['search']:#06x}"
        ends = " ".join("(%.2f, %.2f, %.2f)" % e for e in f["ends"])
        print(f"{i:4d} {LOCN_KINDS.get(f['kind'], f['kind']):6s} flag {f['flag']}  ends {ends}{extra}")


# ---------------------------------------------------------------- battle motion table

MOTION_TABLE = 0x114DC   # overlay 3 (battle) file offset; loaded at 0x0212EA1C
MOTION_COUNT = 0x463


def motions(ov3):
    """(monster, action, variant, slot) rows of the battle motion table.

    24-byte records: +4 u16 monster (1000 repeats the one above), +6 u16 action
    (DEBUG/action.dat), +0x10 u8 variant (monster table +0x28 for the chosen act
    slot), +0x12 u8 MonsterAnimation slot (255 none).
    """
    out, cur = [], None
    for k in range(MOTION_COUNT):
        r = MOTION_TABLE + 24 * k
        m = u16(ov3, r + 4)
        cur = cur if m == 1000 else m
        out.append((cur, u16(ov3, r + 6), ov3[r + 0x10], ov3[r + 0x12]))
    return out


def cmd_motion(root):
    root = Path(root)
    names = {}
    for line in (root / "data" / "data" / "DEBUG" / "action.dat").read_bytes().decode("shift_jis").splitlines():
        k, _, v = line.partition(",")
        if k.isdigit():
            names[int(k)] = v
    for m, act, var, slot in motions((root / "overlay9" / "overlay_0003.bin").read_bytes()):
        print(f"m{m:03d} {act:4d} {names.get(act, '?'):12s} variant {var:3d} slot {slot}")


# ---------------------------------------------------------------- export

def stack(images, vertical=True, gap=0, cols=None):
    """Pack images into one sheet: a column (or rows of `cols`)."""
    images = [i for i in images if i is not None]
    if not images:
        return None
    if cols:
        rows = [images[i:i + cols] for i in range(0, len(images), cols)]
        w = max(sum(i.width for i in r) + gap * (len(r) - 1) for r in rows)
        hs = [max(i.height for i in r) for r in rows]
        sheet = Image.new("RGBA", (w, sum(hs) + gap * (len(rows) - 1)))
        y = 0
        for r, h in zip(rows, hs):
            x = 0
            for i in r:
                sheet.alpha_composite(i.convert("RGBA"), (x, y))
                x += i.width + gap
            y += h + gap
        return sheet
    if vertical:
        sheet = Image.new("RGBA", (max(i.width for i in images),
                                   sum(i.height for i in images) + gap * (len(images) - 1)))
        y = 0
        for i in images:
            sheet.alpha_composite(i.convert("RGBA"), (0, y))
            y += i.height + gap
        return sheet
    return stack(images, cols=len(images), gap=gap)


def shelf(named, width=512, gap=2):
    """Pack [(name, image)] left to right, wrapping at `width` (texture atlases of a map)."""
    rows, row, x = [], [], 0
    for name, im in sorted(named, key=lambda t: (-t[1].height, t[0])):
        if row and x + im.width > width:
            rows.append(row)
            row, x = [], 0
        row.append(im)
        x += im.width + gap
    if row:
        rows.append(row)
    return stack([stack(r, vertical=False, gap=gap) for r in rows], gap=gap)


class Exporter:
    def __init__(self, fs, out):
        self.fs = Path(fs)
        self.data = self.fs / "data" / "data"
        self.out = Path(out)
        self.stats = defaultdict(lambda: [0, 0])  # format -> [decoded, failed]
        self.fail = defaultdict(list)
        self.items = defaultdict(list)  # category -> [(rel path, label)]

    def read(self, rel):
        b = (self.data / rel).read_bytes()
        return unlz(b) if rel.endswith(".lz") else b

    def files(self, sub, suffix=""):
        base = self.data / sub
        if not base.exists():
            return []
        return sorted(p.relative_to(self.data).as_posix() for p in base.rglob("*")
                      if p.is_file() and p.name.endswith(suffix))

    def save(self, cat, name, img, label=None):
        if img is None:
            return
        path = self.out / cat / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".webp":
            frames = img
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=33,
                           loop=0, lossless=True, method=4)
        else:
            img.save(path, optimize=True)
        self.items[cat].append((f"{cat}/{name}", label or Path(name).stem))

    def ok(self, fmt, rel, fn):
        try:
            fn()
            self.stats[fmt][0] += 1
        except Exception as e:  # noqa: BLE001 - record and continue with the rest
            self.stats[fmt][1] += 1
            self.fail[fmt].append(f"{rel}: {type(e).__name__}: {e}")

    # ---- categories

    def chr(self):
        for rel in self.files("CHR", ".pack"):
            def one(rel=rel):
                ts = texture_pack(self.read(rel))
                if not ts:
                    raise ValueError("no texture")
                self.save("chr/field", Path(rel).stem + ".png", stack([texture_object_image(t) for t in ts]))
            self.ok("TexturePack", rel, one)
        for rel in self.files("FIELD/symbol", ".pack"):
            def sym(rel=rel):
                ts = texture_pack(self.read(rel))
                for k, t in enumerate(ts):
                    self.save("chr/symbol", f"{Path(rel).stem}_{k:02d}.png", texture_object_image(t))
            self.ok("TexturePack", rel, sym)
        for rel in self.files("CHR", ".nsbmd"):
            def mdl(rel=rel):
                ts = nitro_textures(self.read(rel))
                self.save("chr/model", Path(rel).stem + ".png", shelf(ts, 512))
            self.ok("BMD0", rel, mdl)

    def anim(self, cat, name, atlas, b, off, label=None, still=None, size=None, alpha_atlas=None):
        """Write frame 0 (to `still`) and the animation of the DSSA at `off`."""
        cells, frames = dssa(b, off, size)
        imgs = [dssa_frame(atlas, cells, f, alpha_atlas=alpha_atlas) for f in frames]
        imgs = [(i, o) for i, o in imgs if i is not None]
        if not imgs:
            return False
        if still:
            self.save(still[0], still[1], imgs[0][0], label)
        x0 = min(o[0] for _, o in imgs)
        y0 = min(o[1] for _, o in imgs)
        x1 = max(o[0] + i.width for i, o in imgs)
        y1 = max(o[1] + i.height for i, o in imgs)
        seq = []
        # One DSSA frame lasts two video frames (1/30 s) in battle.
        for i, o in imgs:
            c = Image.new("RGBA", (x1 - x0, y1 - y0))
            c.alpha_composite(i, (o[0] - x0, o[1] - y0))
            seq.append(c)
        self.save(cat, name, seq, label)
        return True

    def monster(self):
        self.stats["MonsterAnimation(짝 없음)"]  # always reported, also when zero
        tex, anm = {}, {}
        for rel in self.files("MONSTER", ".tex.lz"):
            name = Path(rel).name.split(".")[0]
            def one(rel=rel, name=name):
                t = texture_object(self.read(rel))
                tex[name] = t
                self.save("monster/atlas", name + ".png", texture_object_image(t))
            self.ok("TextureObject", rel, one)
        for rel in self.files("MONSTER", ".anm.lz"):
            anm[Path(rel).name.split(".")[0]] = self.read(rel)

        def mask(t):
            return bytes(1 if v else 0 for v in t["data"])
        masks = {k: mask(t) for k, t in tex.items()}
        for name in sorted(tex):
            base = name if name in anm else None
            if base is None:
                best = second = 0.0
                for a in anm:
                    if a in tex and len(masks[a]) == len(masks[name]):
                        s = sum(x == y for x, y in zip(masks[a], masks[name])) / len(masks[name])
                        if s > best:
                            best, second, base = s, best, a
                        elif s > second:
                            second = s
                # Palette swaps share the atlas layout. A few variants redraw some parts,
                # so below 0.97 take the best match only when it clearly beats the runner-up.
                if not (best >= 0.97 or (best >= 0.9 and best - second >= 0.1)):
                    base = None
            if base is None:
                self.stats["MonsterAnimation(짝 없음)"][1] += 1
                self.fail["MonsterAnimation(짝 없음)"].append(name)
                continue
            atlas = texture_object_image(tex[name])
            alpha = translucent_atlas(tex[name])
            b = anm[base]

            def one(name=name, base=base, b=b, atlas=atlas, alpha=alpha):
                n = 0
                for slot, (eo, es) in enumerate(pack_entries(b)):
                    if es and b[eo:eo + 4] == b"DSSA":
                        label = f"{name} 동작{slot}" + (f" ({base} 공유)" if base != name else "")
                        still = ("monster/pose", f"{name}.png") if n == 0 else None
                        if self.anim("monster/anim", f"{name}_{slot:02d}.webp", atlas, b, eo, label, still, es,
                                     alpha):
                            n += 1
                if not n:
                    self.stats["MonsterAnimation(빈 파일)"][0] += 1
                    return
            self.ok("MonsterAnimation+DSSA", name, one)

    def textures(self, cat, sub, suffix=".tex", strip=None):
        for rel in self.files(sub, suffix):
            if strip and any(rel.startswith(x) for x in strip):
                continue
            b = self.read(rel)
            fmt = "TextureObject" if b.startswith(b"TextureObject") else "TextureData"

            def one(rel=rel, b=b, fmt=fmt):
                if fmt == "TextureObject":
                    img = texture_object_image(texture_object(b))
                elif b.startswith(b"TextureData") or b.startswith(b"Texture Data"):
                    img = texture_data(b)
                else:
                    raise ValueError("unknown texture header " + b[:16].hex())
                name = rel[len(sub):].strip("/").replace("/", "_").split(".")[0] + ".png"
                self.save(cat, name, img)
            self.ok(fmt, rel, one)

    def maps(self):
        for sub, cat, fmt in (("MAP", "map/tex", "MapPackData"), ("BTLMAP", "battle/3d", "MapPackData")):
            for rel in self.files(sub, ".lz"):
                def one(rel=rel, cat=cat):
                    b = self.read(rel)
                    if not b.startswith(b"MapPackData"):
                        raise ValueError("not MapPackData")
                    eo, es = pack_entries(b)[0]
                    if not es:
                        self.stats["MapPackData(빈 팩)"][0] += 1
                        return
                    ts = nitro_textures(b, eo)
                    if not ts:
                        raise ValueError("no TEX0")
                    self.save(cat, Path(rel).stem + ".png", shelf(ts, 512))
                self.ok(fmt, rel, one)

    def render(self):
        for sub, cat in (("MAP", "map/render"), ("BTLMAP", "battle/render")):
            for rel in self.files(sub, ".lz"):
                def one(rel=rel, cat=cat):
                    b = self.read(rel)
                    if not b.startswith(b"MapPackData"):
                        raise ValueError("not MapPackData")
                    ents = pack_entries(b)
                    if not ents[0][1]:
                        return
                    inst = []
                    for eo, es in ents[1:]:
                        if es and b[eo:eo + 4] == b"PAMN":
                            inst = fmap_instances(b, eo)
                    img = render_top(b, ents[0][0], inst)
                    if img is None:
                        raise ValueError("no triangle")
                    self.save(cat, Path(rel).stem + ".png", img, f"{Path(rel).stem} ({len(inst)}개 배치)")
                self.ok("MapPackData 렌더", rel, one)

    def field(self):
        """Illustrated world map (FIELD/large), its patches and the animated field chips."""
        import numpy as np
        base = "FIELD/large/"
        pal = np.array(texture_object(self.read(base + "largemap.tex"))["pal"], np.uint8)

        def tiled(rel, side):
            d = np.frombuffer(self.read(rel), np.uint8)
            n = side // 32
            return Image.fromarray(pal[d.reshape(n, n, 32, 32).transpose(0, 2, 1, 3).reshape(side, side)])
        self.ok("largemap.bin", base + "largemap.bin",
                lambda: self.save("field/large", "largemap.png", tiled(base + "largemap.bin", 1024), "largemap (1024x1024)"))
        for rel in self.files("FIELD/large", ".bin"):
            if rel.endswith("largemap.bin"):
                continue
            self.ok("large 64x64", rel, lambda rel=rel: self.save("field/large", Path(rel).stem + ".png", tiled(rel, 64)))
        fpal = texture_object(self.read("FIELD/field.tex"))["pal"]
        ypal = texture_object(self.read("FIELD/yamifield.tex"))["pal"]
        for rel in self.files("FIELD/texture", ".pack"):
            def one(rel=rel):
                b = self.read(rel)
                pal = ypal if Path(rel).name.startswith("y") else fpal
                ents = [b[eo:eo + es] for eo, es in pack_entries(b) if es]
                frames = [texture(d, 4, 256, len(d) // 256, pal, False) for d in ents]
                if "24" in rel:  # sea: only the four chips at the left of each 256x16 strip
                    frames = [f.crop((0, 0, 64, 16)) for f in frames]
                stem = Path(rel).stem
                self.save("field/pattern", stem + ".png", frames[0], f"{stem} 첫 프레임")
                self.save("field/pattern", stem + ".webp", [f.convert("RGBA") for f in frames], f"{stem} ({len(frames)}프레임)")
            self.ok("field pattern", rel, one)

    def world(self):
        """The field rendered from FIELD/bin (16 px per cell, first animation frames, symbols)."""
        import numpy as np
        sym = texture_pack(self.read("FIELD/symbol/symbol.pack"))
        pictures = [texture_object_image(t) for t in sym]
        base = self.read("FIELD/bin/worldmap.bin")
        for rel, tex, pat in (("FIELD/bin/worldmap.bin", "field", "pattern"),
                              ("FIELD/bin/worldmap_scene0.bin", "field", "pattern"),
                              ("FIELD/bin/worldmap_scene1.bin", "field", "pattern"),
                              ("FIELD/bin/worldmap_scene2.bin", "field", "pattern"),
                              ("FIELD/bin/gotmap.bin", "field", "pattern"),
                              ("FIELD/bin/yamimap.bin", "yamifield", "ypattern")):
            def one(rel=rel, tex=tex, pat=pat):
                ft = texture_object(self.read(f"FIELD/{tex}.tex"))
                pal = ft["pal"]
                f_img = np.asarray(texture_object_image(ft, transparent0=False).convert("RGB"))
                pb = self.read(f"FIELD/texture/{pat}8.pack")
                eo, es = pack_entries(pb)[0]
                p_img = np.asarray(texture(pb[eo:eo + es], 4, 256, es // 256, pal, False).convert("RGB"))
                sb = self.read(f"FIELD/texture/{pat}24.pack")
                eo, es = pack_entries(sb)[0]
                s_img = np.asarray(texture(sb[eo:eo + es], 4, 256, 16, pal, False).convert("RGB"))
                b = self.read(rel)
                chunks = wmap_chunks(b)
                table = wtex(b if "WTEX" in chunks else base)
                symbols = sdat(b) if "SDAT" in chunks else sdat(base)
                img = render_field(wmap(b), table, f_img, p_img, s_img, symbols, pictures)
                side = img.width
                self.save("field/world", Path(rel).stem + ".png", img, f"{Path(rel).stem} ({side}x{side})")
            self.ok("WMAP", rel, one)

    def model_anim(self):
        """CHR 3D models played with their BCA0 animations, front orthographic view."""
        for rel in self.files("CHR", ".nsbca"):
            stem = Path(rel).stem
            model = stem.rsplit("_", 1)[0]
            if not (self.data / "CHR" / (model + ".nsbmd")).exists():
                continue

            def one(rel=rel, stem=stem, model=model):
                mdl, bca = self.read(f"CHR/{model}.nsbmd"), self.read(rel)
                for k in range(len(bca_anims(bca))):
                    frames, anim = model_anim_frames(mdl, bca, k, step=2, max_frames=300)
                    self.save("chr/model_anim", f"{stem}_{k}.webp", frames,
                              f"{model} {anim['name']} ({anim['frames']}프레임)")
            self.ok("BCA0", rel, one)

    def g2d(self):
        for rel in self.files("G2D/BATTLEBG", ".bgc"):
            def one(rel=rel):
                c = self.read(rel)
                p = palette(self.read(rel[:-1] + "p"))
                self.save("battle/upper", Path(rel).stem + ".png", tiles(c, p, 8, 32))
            self.ok("bgc/bgp(8bpp)", rel, one)
        for rel in self.files("G2D/SYSTEM", ".bgc"):
            def sysbg(rel=rel):
                c = self.read(rel)
                p = palette(self.read(rel[:-1] + "p"))
                self.save("ui/system", Path(rel).stem + ".png", tiles(c, p, 4, 32))
            self.ok("bgc/bgp(4bpp)", rel, sysbg)
        for rel in self.files("G2D/ICON", ".mpt"):
            def icon(rel=rel):
                stem = Path(rel).stem
                side = int("".join(ch for ch in stem if ch.isdigit()))
                sheet, n = icon_sheet(self.read(rel), side)
                self.save("ui/icon", stem + ".png", sheet, f"{stem} ({n})")
            self.ok("MPT0 아이콘", rel, icon)
        for rel in self.files("G2D/SNAP", ".tim"):
            self.ok("tim", rel, lambda rel=rel: self.save("ui/snap", Path(rel).stem + ".png", tim(self.read(rel))))
        for rel in self.files("G2D/FONT", ".nftr"):
            def font(rel=rel):
                img, n = nftr(self.read(rel))
                self.save("font", Path(rel).stem + ".png", img, f"{Path(rel).stem} ({n}자)")
            self.ok("NFTR", rel, font)

    def effects(self):
        names = defaultdict(list)
        lst = self.data / "EFFECT" / "_list.txt"
        if lst.exists():
            for line in lst.read_bytes().decode("latin-1").splitlines():
                parts = line.split(",")
                if len(parts) >= 2 and parts[1].strip().isdigit():
                    names["effect" + parts[1].strip()].append(parts[0].strip())
        for rel in self.files("EFFECT", ".lz"):
            def one(rel=rel):
                b = self.read(rel)
                ents = pack_entries(b)
                stem = Path(rel).stem
                label = stem + (" " + "/".join(dict.fromkeys(names[stem[:9]])) if names.get(stem[:9]) else "")
                texs = [texture_object(b, eo) for eo, es in ents if es and b[eo:eo + 13] == b"TextureObject"]
                if texs:
                    atlas = texture_object_image(texs[0])
                    self.save("effect/atlas", stem + ".png", atlas, label)
                    for eo, es in ents:
                        if es and b[eo:eo + 4] == b"DSSA":
                            self.anim("effect/anim", stem + ".webp", atlas, b, eo, label, size=es)
                            break
                    return
                bmd = [eo for eo, es in ents if es and b[eo:eo + 4] == b"BMD0"]
                ts = [t for eo in bmd for t in nitro_textures(b, eo)]
                if not ts:
                    raise ValueError("no TextureObject or BMD0 texture")
                self.save("effect/atlas", stem + ".png", shelf(ts, 256), label + " (3D)")

                def pick(tag):
                    return next((b[eo:eo + es] for eo, es in ents if es and b[eo:eo + 4] == tag), None)
                if pick(b"BCA0"):
                    frames, _ = model_anim_frames(pick(b"BMD0"), pick(b"BCA0"), 0, step=2, blend=True,
                                                  srt=pick(b"BTA0"), mat=pick(b"BMA0"))
                    self.save("effect/anim", stem + ".webp", frames, label + " (3D, 앞에서 본 직교)")
            self.ok("EffectPack", rel, one)

    def dssa_files(self):
        jobs = [("TRANS", "trans/anim", lambda rel: "TRANS/" + Path(rel).stem.split("_")[0] + ".tex"),
                ("OPENING", "title/anim", lambda rel: "OPENING/" + ("staff" if "staff" in rel else "logo") + ".tex.lz")]
        for sub, cat, texof in jobs:
            for rel in self.files(sub, ".dssa"):
                def one(rel=rel, cat=cat, texof=texof):
                    atlas = texture_object_image(texture_object(self.read(texof(rel))))
                    if not self.anim(cat, Path(rel).stem + ".webp", atlas, self.read(rel), 0):
                        raise ValueError("no frame")
                self.ok("DSSA", rel, one)

    def banner(self):
        def one():
            b = (self.data / "dq4banner.bnr").read_bytes()
            img = tiles(b[0x20:0x220], palette(b, 0x220, 16), 4, 4, transparent0=True)
            self.save("title", "banner.png", img, "DS 메뉴 아이콘")
        self.ok("banner", "dq4banner.bnr", one)

    def kr(self, root):
        """Graphics the Korean fan patch replaced (fonts, title logo), under kr/."""
        kr = Path(root) / "data" / "data"
        for rel in ("G2D/FONT/han10.nftr", "G2D/FONT/han12.nftr", "G2D/FONT/zen10.nftr", "G2D/FONT/zen12.nftr"):
            def font(rel=rel):
                img, n = nftr((kr / rel).read_bytes())
                self.save("kr", "font_" + Path(rel).stem + ".png", img, f"한글패치 {Path(rel).stem} ({n}자)")
            self.ok("NFTR(한글패치)", rel, font)

        def logo():
            t = texture_object(unlz((kr / "OPENING/logo.tex.lz").read_bytes()))
            self.save("kr", "logo.png", texture_object_image(t), "한글패치 타이틀 로고")
        self.ok("TextureObject(한글패치)", "OPENING/logo.tex.lz", logo)

    def run(self, only=None):
        steps = dict(
            chr=self.chr, monster=self.monster, map=self.maps, g2d=self.g2d,
            effect=self.effects, dssa=self.dssa_files, banner=self.banner, render=self.render,
            field=self.field, world=self.world, model_anim=self.model_anim,
            tex=lambda: [
                self.textures("title", "2D", strip=["2D/MAP", "2D/FACE"]),
                self.textures("ui/face", "2D/FACE"),
                self.textures("map/town2d", "2D/MAP"),
                self.textures("endroll", "ENDROLL"),
                self.textures("field", "FIELD"),
                self.textures("ui/mask", "MASK"),
                self.textures("ui/minigame", "MINIGAME"),
                self.textures("ui/rise", "RISE"),
                self.textures("ui/act", "ACT"),
                self.textures("title", "OPENING", ".tex.lz"),
                self.textures("trans/atlas", "TRANS"),
                [self.textures("ui/misc", "", s) for s in ("common.tex", "temp.tex", "toruneko00.tex")],
            ],
        )
        for name, fn in steps.items():
            if only and name not in only:
                continue
            print("export", name, file=sys.stderr)
            fn()
        return self.stats


# ---------------------------------------------------------------- survey / gallery / CLI

def survey(fs):
    """Count files by top folder and header magic (after LZ decompression)."""
    data = Path(fs) / "data" / "data"
    count = Counter()
    for p in sorted(data.rglob("*")):
        if not p.is_file():
            continue
        b = p.read_bytes()
        b = unlz(b) if p.suffix == ".lz" else b
        m = magic(b)
        if not (len(m) >= 3 and m.isprintable() and m.isascii()):
            m = b[:4].hex()
        top = p.relative_to(data).parts[0]
        count[(top, p.suffix if p.suffix != ".lz" else "".join(p.suffixes[-2:]), m)] += 1
    for (top, ext, m), n in sorted(count.items()):
        print(f"{n:5d}  {top:12s} {ext:10s} {m}")


CATEGORY_TITLES = {
    "chr/field": "인물(필드 스프라이트 팩)",
    "chr/symbol": "필드 심벌",
    "chr/model": "3D 인물·소품 모델 텍스처",
    "chr/model_anim": "3D 인물 모델 애니메이션(BCA0, 앞에서 본 직교)",
    "monster/pose": "몬스터(조립한 첫 프레임)",
    "monster/anim": "몬스터 동작(애니메이션 WebP)",
    "monster/atlas": "몬스터 부품 아틀라스",
    "map/town2d": "마을·성 지도(2D)",
    "map/tex": "맵 텍스처(3D 맵마다 한 장)",
    "map/render": "맵 위에서 본 렌더링",
    "field": "필드(세계 지도) 텍스처",
    "field/world": "필드 세계 지도 렌더링(칸 16픽셀)",
    "field/large": "일러스트 세계 지도와 덧그림",
    "field/pattern": "필드 물가·바다 애니메이션 칩",
    "battle/render": "전투 배경 위에서 본 렌더링",
    "battle/3d": "전투 배경(3D) 텍스처",
    "battle/upper": "전투 상단 배경(8×8 타일, 배치 미상)",
    "ui/system": "창·커서(BG/OBJ 타일)",
    "ui/icon": "아이콘",
    "ui/face": "얼굴",
    "ui/rise": "말풍선 아이콘",
    "ui/act": "행동 아이콘",
    "ui/minigame": "미니게임(포커)",
    "ui/mask": "마스크",
    "ui/snap": "스냅샷 자리",
    "ui/misc": "기타",
    "font": "글꼴",
    "title": "타이틀·로고",
    "title/anim": "타이틀 애니메이션",
    "effect/atlas": "효과 아틀라스",
    "effect/anim": "효과 애니메이션",
    "trans/atlas": "변신·연출 아틀라스",
    "trans/anim": "변신·연출 애니메이션",
    "endroll": "엔딩 그림",
    "kr": "한글 팬패치가 바꾼 글꼴·로고",
}


SIBLING_TITLES = {"sound": "소리(곡·효과음·샘플)", "screens": "맵 화면"}


def sibling_links(out):
    """Pages of other sessions' folders: */gallery/index.html, else the folder's README.txt."""
    links = []
    for d in sorted(p for p in Path(out).iterdir() if p.is_dir()):
        if (d / "gallery" / "index.html").exists():
            links.append(f"{d.name}/gallery/index.html")
        elif d.name in SIBLING_TITLES and (d / "README.txt").exists():
            links.append(f"{d.name}/README.txt")
    return links


def gallery(out, manifest):
    """Static index.html: one section per category, thumbnails link to the full image."""
    out = Path(out)
    items = manifest["items"]
    order = [c for c in CATEGORY_TITLES if c in items] + sorted(c for c in items if c not in CATEGORY_TITLES)
    nav = " · ".join(f'<a href="#{html.escape(c)}">{html.escape(CATEGORY_TITLES.get(c, c))} ({len(items[c])})</a>'
                     for c in order)
    # Other sessions keep their own folders next to ours (sound/ with its gallery, screens/ with
    # map screenshots); link them so regenerating this page does not drop them.
    extra = "".join(f'<p>{html.escape(SIBLING_TITLES.get(t.split("/")[0], t.split("/")[0]))}: '
                    f'<a href="{html.escape(t)}">{html.escape(t)}</a></p>' for t in sibling_links(out))
    secs = []
    for c in order:
        cards = "".join(
            f'<a class="c" href="{html.escape(p)}" title="{html.escape(lbl)}"><img loading="lazy" src="{html.escape(p)}">'
            f'<span>{html.escape(lbl)}</span></a>' for p, lbl in sorted(items[c]))
        secs.append(f'<h2 id="{html.escape(c)}">{html.escape(CATEGORY_TITLES.get(c, c))} '
                    f'<small>{html.escape(c)}/ · {len(items[c])}</small></h2><div class="g">{cards}</div>')
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NDS DQ4 그래픽</title>
<style>
body{{margin:0 16px;font:14px sans-serif;background:#1d1f24;color:#ddd}}
a{{color:#9cf}} h2{{margin-top:2em;border-bottom:1px solid #444}} small{{color:#888;font-weight:normal}}
.g{{display:flex;flex-wrap:wrap;gap:8px}}
.c{{display:flex;flex-direction:column;align-items:center;width:136px;text-decoration:none;color:#bbb;
   background:repeating-conic-gradient(#2a2d33 0 25%,#33363d 0 50%) 0 0/16px 16px;padding:4px;border-radius:4px}}
.c img{{max-width:128px;max-height:128px;min-width:48px;image-rendering:pixelated;object-fit:contain}}
.c span{{font-size:11px;word-break:break-all;text-align:center;margin-top:2px}}
nav{{line-height:1.8}}
</style></head><body>
<h1>NDS 「ドラゴンクエストIV 導かれし者たち」 그래픽</h1>
<p>참고용 추출본입니다. 배포하지 않습니다. 만든 방법은 <a href="README.md">README.md</a>.</p>
{extra}
<nav>{nav}</nav>
{''.join(secs)}
</body></html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey", help="파일 수를 폴더·헤더별로 셈")
    s.add_argument("--root", default=DEFAULT_FS)
    e = sub.add_parser("export", help="PNG/WebP 로 내보내고 manifest.json 을 씀")
    e.add_argument("out")
    e.add_argument("--root", default=DEFAULT_FS)
    e.add_argument("--kr", help="한글 팬패치 롬을 푼 폴더(바뀐 글꼴·로고를 kr/ 에)")
    e.add_argument("--only", help="쉼표로 단계 이름(chr,monster,map,g2d,effect,dssa,banner,tex,render,field,world,model_anim)")
    g = sub.add_parser("gallery", help="manifest.json 으로 index.html 을 씀")
    g.add_argument("out")
    lo = sub.add_parser("locn", help="맵의 LOCN 면·트리거를 찍음")
    lo.add_argument("map")
    lo.add_argument("--root", default=DEFAULT_FS)
    mo = sub.add_parser("motion", help="전투 동작 표(오버레이 3)를 찍음")
    mo.add_argument("--root", default=DEFAULT_FS)
    a = ap.parse_args(argv)
    if a.cmd == "locn":
        cmd_locn(a.root, a.map)
        return
    if a.cmd == "motion":
        cmd_motion(a.root)
        return
    if a.cmd == "survey":
        survey(a.root)
        return
    if a.cmd == "export":
        ex = Exporter(a.root, a.out)
        only = set(a.only.split(",")) if a.only else None
        stats = ex.run(only)
        if a.kr:
            ex.kr(a.kr)
        mpath = Path(a.out) / "manifest.json"
        old = json.loads(mpath.read_text()) if mpath.exists() and only else {"items": {}, "stats": {}, "fail": {}}
        for k, v in ex.items.items():
            # A partial run may write only part of a category (e.g. the banner into
            # title/); keep the entries other steps wrote there.
            merged = {p: lbl for p, lbl in old["items"].get(k, [])}
            merged.update({p: lbl for p, lbl in v})
            old["items"][k] = sorted(merged.items())
        old["stats"].update({k: v for k, v in stats.items()})
        for k in stats:
            old["fail"][k] = ex.fail.get(k, [])
        old["fail"] = {k: v for k, v in old["fail"].items() if v}
        mpath.write_text(json.dumps(old, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        for k, (n_ok, n_bad) in sorted(stats.items()):
            print(f"{k:28s} 성공 {n_ok:5d}  실패 {n_bad:4d}")
        return
    if a.cmd == "gallery":
        gallery(a.out, json.loads((Path(a.out) / "manifest.json").read_text()))



# ---------------------------------------------------------------- MDL0 top-down render

GX_ARGS = {0x10: 1, 0x11: 0, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 0, 0x16: 16, 0x17: 12, 0x18: 16,
           0x19: 12, 0x1A: 9, 0x1B: 3, 0x1C: 3, 0x20: 1, 0x21: 1, 0x22: 1, 0x23: 2, 0x24: 1,
           0x25: 1, 0x26: 1, 0x27: 1, 0x28: 1, 0x29: 1, 0x2A: 1, 0x2B: 1, 0x30: 1, 0x31: 1,
           0x32: 1, 0x33: 1, 0x34: 32, 0x40: 1, 0x41: 0, 0x50: 1, 0x60: 1, 0x70: 3, 0x71: 2, 0x72: 1}


def _fx(v, bits=12):
    return v / (1 << bits)


def _s(v, n):
    return v - (1 << n) if v & (1 << (n - 1)) else v


def node_trs(b, o):
    """(translation, 3x3 rotation, scale) of a MDL0 node transform."""
    import numpy as np
    flags = u16(b, o)
    m0 = struct.unpack_from("<h", b, o + 2)[0]
    p = o + 4
    t = np.zeros(3)
    if not flags & 1:
        t = np.array([s32(b, p + 4 * i) / 4096 for i in range(3)])
        p += 12
    r = np.eye(3)
    if not flags & 2:
        if flags & 8:
            a = struct.unpack_from("<h", b, p)[0] / 4096
            bb = struct.unpack_from("<h", b, p + 2)[0] / 4096
            p += 4
            r = pivot_matrix(flags >> 4 & 15, flags >> 8 & 15, a, bb)
        else:
            v = [m0 / 4096] + [struct.unpack_from("<h", b, p + 2 * i)[0] / 4096 for i in range(8)]
            p += 16
            r = np.array(v).reshape(3, 3)
    sc = np.ones(3)
    if not flags & 4:
        sc = np.array([s32(b, p + 4 * i) / 4096 for i in range(3)])
    return t, r, sc


def pivot_matrix(sel, neg, a, bb):
    """Pivot-compressed rotation: a ±1 at (sel // 3, sel % 3), the remaining 2x2
    block is [a b; c d] with c = ±b, d = ±a and the signs from `neg`."""
    import numpy as np
    one = -1.0 if neg & 1 else 1.0
    c = -bb if neg & 2 else bb
    d = -a if neg & 4 else a
    m = np.zeros((3, 3))
    prow, pcol = sel // 3, sel % 3
    m[prow, pcol] = one
    rr = [k for k in range(3) if k != prow]
    cc = [k for k in range(3) if k != pcol]
    m[rr[0], cc[0]], m[rr[0], cc[1]] = a, bb
    m[rr[1], cc[0]], m[rr[1], cc[1]] = c, d
    return m


def trs_matrix(t, r, sc):
    import numpy as np
    m = np.eye(4)
    # Nitro uses row vectors: v' = v * M.
    m[:3, :3] = r * np.asarray(sc)[:, None]
    m[3, :3] = t
    return m


def node_matrix(b, o):
    """4x4 local matrix of a MDL0 node transform (translation, rotation, scale)."""
    return trs_matrix(*node_trs(b, o))


def mdl0_models(b, off):
    """[(name, model offset)] of a MDL0 block."""
    return [(n, off + u32(e, 0)) for n, e in nitro_dict(b, off + 8)]


def model_nodes(b, mo):
    """Offsets of the node transforms of a model, in node index order."""
    return [mo + 0x40 + u32(e, 0) for _, e in nitro_dict(b, mo + 0x40)]


def model_triangles(b, mo, local=None):
    """Triangles of one model: list of (material index, [(xyz, st)] * 3) in world units.
    `local` replaces the node matrices (animation)."""
    import numpy as np
    rcmd = mo + u32(b, mo + 4)
    meshes = mo + u32(b, mo + 0xC)
    pos_scale = s32(b, mo + 0x1C) / 4096
    if local is None:
        local = [node_matrix(b, o) for o in model_nodes(b, mo)]
    mesh_list = []
    for _, e in nitro_dict(b, meshes):
        mh = meshes + u32(e, 0)
        mesh_list.append((mh + u32(b, mh + 8), u32(b, mh + 12)))
    stack = {}
    cur = np.eye(4)
    mat = 0
    tris = []
    p = rcmd
    end = mo + u32(b, mo + 8)
    while p < end:
        op = b[p]
        if op == 0x01:
            break
        if op == 0x00:
            p += 1
        elif op == 0x02:
            p += 3
        elif op == 0x03:
            cur = stack.get(b[p + 1], np.eye(4))
            p += 2
        elif op in (0x04, 0x24, 0x44):
            mat = b[p + 1]
            p += 2
        elif op == 0x05:
            dl, dsize = mesh_list[b[p + 1]]
            tris += [(mat, t) for t in display_list(b, dl, dsize, cur, stack, pos_scale)]
            p += 2
        elif op in (0x06, 0x26, 0x46, 0x66):
            node = b[p + 1]  # b[p + 2] is the parent node; the matrix stack already chains it
            q = p + 4
            src = dst = None
            if op == 0x26:
                dst = b[q]
                q += 1
            elif op == 0x46:
                src = b[q]
                q += 1
            elif op == 0x66:
                dst, src = b[q], b[q + 1]
                q += 2
            if src is not None:
                cur = stack.get(src, np.eye(4))
            cur = local[node] @ cur if node < len(local) else cur
            if dst is not None:
                stack[dst] = cur
            p = q
        elif op in (0x07, 0x08):
            p += 2
        elif op == 0x09:
            n = b[p + 2]
            p += 3 + 3 * n
        elif op in (0x0B, 0x2B):
            p += 1
        elif op in (0x0C, 0x0D):
            p += 3
        else:
            break
    return tris


def display_list(b, p, size, base, stack, pos_scale):
    """Triangles of a GX display list (positions transformed by the matrix stack)."""
    import numpy as np
    end = p + size
    mtx = base
    v = [0.0, 0.0, 0.0]
    st = (0.0, 0.0)
    prim, buf, out = 0, [], []

    def emit():
        x = np.array([v[0], v[1], v[2], 1.0]) @ mtx
        buf.append(((x[0] * pos_scale, x[1] * pos_scale, x[2] * pos_scale), st))
        if prim == 0 and len(buf) == 3:
            out.append(buf[:])
            buf.clear()
        elif prim == 1 and len(buf) == 4:
            out.append([buf[0], buf[1], buf[2]])
            out.append([buf[0], buf[2], buf[3]])
            buf.clear()
        elif prim == 2 and len(buf) >= 3:
            n = len(buf)
            tri = [buf[-3], buf[-2], buf[-1]] if n % 2 else [buf[-2], buf[-3], buf[-1]]
            out.append(tri)
        elif prim == 3 and len(buf) >= 4 and len(buf) % 2 == 0:
            a, bb, c, d = buf[-4], buf[-3], buf[-1], buf[-2]
            out.append([a, bb, c])
            out.append([a, c, d])

    while p + 4 <= end:
        ops = b[p:p + 4]
        p += 4
        for op in ops:
            n = GX_ARGS.get(op, 0)
            args = [u32(b, p + 4 * i) for i in range(n)] if p + 4 * n <= len(b) else [0] * n
            p += 4 * n
            if op == 0x14:
                mtx = stack.get(args[0] & 31, base)
            elif op == 0x22:
                st = (_s(args[0] & 0xFFFF, 16) / 16, _s(args[0] >> 16, 16) / 16)
            elif op == 0x23:
                v = [_s(args[0] & 0xFFFF, 16) / 4096, _s(args[0] >> 16, 16) / 4096,
                     _s(args[1] & 0xFFFF, 16) / 4096]
                emit()
            elif op == 0x24:
                v = [_s(args[0] & 0x3FF, 10) / 64, _s(args[0] >> 10 & 0x3FF, 10) / 64,
                     _s(args[0] >> 20 & 0x3FF, 10) / 64]
                emit()
            elif op == 0x25:
                v = [_s(args[0] & 0xFFFF, 16) / 4096, _s(args[0] >> 16, 16) / 4096, v[2]]
                emit()
            elif op == 0x26:
                v = [_s(args[0] & 0xFFFF, 16) / 4096, v[1], _s(args[0] >> 16, 16) / 4096]
                emit()
            elif op == 0x27:
                v = [v[0], _s(args[0] & 0xFFFF, 16) / 4096, _s(args[0] >> 16, 16) / 4096]
                emit()
            elif op == 0x28:
                v = [v[0] + _s(args[0] & 0x3FF, 10) / 4096 / 8,
                     v[1] + _s(args[0] >> 10 & 0x3FF, 10) / 4096 / 8,
                     v[2] + _s(args[0] >> 20 & 0x3FF, 10) / 4096 / 8]
                emit()
            elif op == 0x40:
                prim = args[0] & 3
                buf = []
    return out


def material_info(b, mdl_mo):
    """[(texture name, palette name, repeat/flip bits)] per material index of a model."""
    mat = mdl_mo + u32(b, mdl_mo + 8)
    tex_dict = mat + u16(b, mat)
    pal_dict = mat + u16(b, mat + 2)
    mats = nitro_dict(b, mat + 4)
    info = [[None, None, 0] for _ in mats]
    for k, (_, e) in enumerate(mats):
        mp = mat + u32(e, 0)
        info[k][2] = u32(b, mp + 0x14) >> 16 & 15
    for dct, slot in ((tex_dict, 0), (pal_dict, 1)):
        for name, ent in nitro_dict(b, dct):
            lo, cnt = u16(ent, 0), ent[2]
            for k in range(cnt):
                m = b[mat + lo + k]
                if m < len(info):
                    info[m][slot] = name
    return info


def fmap_instances(b, off):
    """Model placements of a `PAMN` block: [(model index, 4x4 row-vector matrix)].

    `FMAP` +8 count, records of 0x50 bytes from +0x20: fx32 x, y, z;
    u32 id; s32 rotation x, y, z (0x10000 = one turn); u16 model index at
    +0x1C; fx32 scale x, y, z at +0x20.
    """
    import numpy as np
    f = b.find(b"FMAP", off)
    if f < 0:
        return []
    out = []
    for i in range(u32(b, f + 8)):
        r = f + 0x20 + 0x50 * i
        if r + 0x50 > len(b):
            break
        pos = [s32(b, r + 4 * k) / 4096 for k in range(3)]
        ang = [s32(b, r + 0x10 + 4 * k) / 65536 * 2 * np.pi for k in range(3)]
        sc = [s32(b, r + 0x20 + 4 * k) / 4096 for k in range(3)]
        model = u16(b, r + 0x1C)
        cx, sx_ = np.cos(ang[0]), np.sin(ang[0])
        cy, sy_ = np.cos(ang[1]), np.sin(ang[1])
        cz, sz_ = np.cos(ang[2]), np.sin(ang[2])
        rx = np.array([[1, 0, 0], [0, cx, sx_], [0, -sx_, cx]])
        ry = np.array([[cy, 0, -sy_], [0, 1, 0], [sy_, 0, cy]])
        rz = np.array([[cz, sz_, 0], [-sz_, cz, 0], [0, 0, 1]])
        m = np.eye(4)
        m[:3, :3] = np.diag(sc) @ rx @ ry @ rz
        m[3, :3] = pos
        out.append((model, m))
    return out


def render_top(b, off, instances=None, max_side=2048, max_scale=32):
    """Orthographic top-down render (looking down -Y) of the BMD0 at `off`.

    `instances` is [(model index, matrix)] (see `fmap_instances`); without it
    only model 0 is drawn at the origin.
    """
    import numpy as np
    blocks = nitro_blocks(b, off)
    models = mdl0_models(b, blocks["MDL0"])
    if not instances:
        instances = [(0, np.eye(4))]
    texs, pals = tex0(b, blocks["TEX0"]) if "TEX0" in blocks else ({}, {})
    per_model = {}
    tris = []
    for mi, m in instances:
        if mi >= len(models):
            continue
        if mi not in per_model:
            mo = models[mi][1]
            try:
                per_model[mi] = (model_triangles(b, mo), material_info(b, mo))
            except (struct.error, IndexError, KeyError):
                per_model[mi] = ([], [])
        mt, info = per_model[mi]
        for mat, t in mt:
            q = [(tuple((np.array([*p, 1.0]) @ m)[:3]), st) for p, st in t]
            tris.append(((mi, mat), q))
    if not tris:
        return None
    cache = {}

    def tex_rgba(key):
        mi, m = key
        info = per_model[mi][1]
        if key not in cache:
            t, pn, flags = info[m] if m < len(info) else (None, None, 0)
            if t in texs:
                tt = texs[t]
                pal = palette(pals[pn]) if pn in pals else grey(256)
                img = texture(tt["data"], tt["fmt"], tt["width"], tt["height"], pal or grey(256),
                              bool(tt["c0"]), tt["pidx"])
                cache[key] = (np.asarray(img), flags)
            else:
                cache[key] = (None, flags)
        return cache[key]

    xyz = np.array([[p[0] for p in t] for _, t in tris])  # (n, 3, 3)
    lo, hi = xyz.reshape(-1, 3).min(0), xyz.reshape(-1, 3).max(0)
    # texel density: pixels per world unit so that textures land near 1:1
    dens = []
    for (m, t), q in zip(tris[:4000], xyz[:4000]):
        a_w = abs(np.cross(q[1] - q[0], q[2] - q[0])[1])
        st = np.array([s for _, s in t])
        a_t = abs(np.cross(np.append(st[1] - st[0], 0), np.append(st[2] - st[0], 0))[2])
        if a_w > 1e-6 and a_t > 0:
            dens.append((a_t / a_w) ** 0.5)
    scale = float(np.percentile(dens, 90)) if dens else 16.0
    span = max(hi[0] - lo[0], hi[2] - lo[2], 1e-3)
    scale = min(scale, max_scale, max_side / span)
    return raster(tris, tex_rgba, "top", scale, lo, hi)


VIEWS = {
    # image x axis, image y axis (sign), depth axis: larger depth is nearer.
    "top": (0, 2, 1, 1),     # looking down -Y: x right, z down
    "front": (0, 1, -1, 2),  # looking down -Z: x right, y up
}


def raster(tris, tex_rgba, view, scale, lo, hi, blend=False):
    """Orthographic textured z-buffer raster of [(key, [(xyz, st)] * 3)] onto RGBA.
    blend=True draws translucent texels over what is below (effects) instead of an alpha test."""
    import numpy as np
    ax, ay, sy_, az = VIEWS[view]
    w = int((hi[ax] - lo[ax]) * scale) + 1
    h = int((hi[ay] - lo[ay]) * scale) + 1
    color = np.zeros((h, w, 4), np.uint8)
    depth = np.full((h, w), -1e9)
    for m, t in tris:
        q = np.array([p for p, _ in t])
        img, flags = tex_rgba(m)
        px = (q[:, ax] - lo[ax]) * scale
        py = ((q[:, ay] - lo[ay]) if sy_ > 0 else (hi[ay] - q[:, ay])) * scale
        x0, x1 = int(max(0, np.floor(px.min()))), int(min(w - 1, np.ceil(px.max())))
        y0, y1 = int(max(0, np.floor(py.min()))), int(min(h - 1, np.ceil(py.max())))
        if x1 < x0 or y1 < y0:
            continue
        den = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(den) < 1e-9:
            continue  # face seen edge-on
        # Back-face cull with the model's winding: the face normal must point at the viewer.
        # Without it the inside of a battle sky dome hides the whole scene from above.
        e1, e2 = q[1] - q[0], q[2] - q[0]
        n = np.cross(e1, e2)
        if n[az] <= 0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l0 = ((py[1] - py[2]) * (gx - px[2]) + (px[2] - px[1]) * (gy - py[2])) / den
        l1 = ((py[2] - py[0]) * (gx - px[2]) + (px[0] - px[2]) * (gy - py[2])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not inside.any():
            continue
        z = l0 * q[0, az] + l1 * q[1, az] + l2 * q[2, az]
        if img is None:
            rgba = np.zeros(gx.shape + (4,), np.uint8)
            rgba[...] = (128, 128, 128, 255)
        else:
            th, tw = img.shape[:2]
            st = np.array([s for _, s in t])
            s = l0 * st[0, 0] + l1 * st[1, 0] + l2 * st[2, 0]
            tt = l0 * st[0, 1] + l1 * st[1, 1] + l2 * st[2, 1]
            si = np.floor(s).astype(int)
            ti = np.floor(tt).astype(int)
            if flags & 4:  # flip s on odd repeats
                si = np.where((si // tw) % 2 == 1, tw - 1 - si % tw, si % tw)
            else:
                si = si % tw if flags & 1 else np.clip(si, 0, tw - 1)
            if flags & 8:
                ti = np.where((ti // th) % 2 == 1, th - 1 - ti % th, ti % th)
            else:
                ti = ti % th if flags & 2 else np.clip(ti, 0, th - 1)
            rgba = img[ti, si]
        sub_d = depth[y0:y1 + 1, x0:x1 + 1]
        if blend:
            draw = inside & (rgba[..., 3] > 0) & (z >= sub_d - 1e-6)
            sub_c = color[y0:y1 + 1, x0:x1 + 1]
            a = rgba[..., 3:4].astype(np.float32) / 255
            mixed = rgba[..., :3] * a + sub_c[..., :3] * (1 - a)
            sub_c[..., :3][draw] = mixed[draw].astype(np.uint8)
            sub_c[..., 3][draw] = np.maximum(sub_c[..., 3], rgba[..., 3])[draw]
        else:
            draw = inside & (rgba[..., 3] >= 128) & (z >= sub_d)
            sub_d[draw] = z[draw]
            color[y0:y1 + 1, x0:x1 + 1][draw] = rgba[draw]
    return Image.fromarray(color, "RGBA")


# ---------------------------------------------------------------- field (world map)

def wmap_chunks(b):
    """{tag: bytes} of a FIELD/bin `WMAP` file: `WSYN` (u8 blocks x, y, u8 block width,
    height in cells), `WCHA`, `WMAP` (u16 cells, row-major), `WCMA`, `WTEX` (cell value
    table), `SDAT` (symbols). A file without the `WMAP` header is bare 256x256 cells."""
    if b[:4] != b"WMAP":
        return {"WMAP": b}
    out, o = {}, 0x10
    while o + 8 <= len(b):
        tag, size = b[o:o + 4], u32(b, o + 4)
        if tag == b"\0\0\0\0":
            break
        out[tag.decode("latin-1")] = b[o + 8:o + 8 + size]
        o += 8 + size
    return out


def wmap(b):
    """Cells of a FIELD/bin file as a square u16 array."""
    import numpy as np
    cells = np.frombuffer(wmap_chunks(b)["WMAP"], "<u2")
    side = int(len(cells) ** 0.5)
    return cells[:side * side].reshape(side, side)


def wtex(b):
    """`WTEX`: 6 bytes per cell value from 1: u8 terrain, u8 flags, u16 animated chip,
    u16 still chip. Flag 8: animated chip of the coast pattern (pattern8), 8|16: of the
    sea pattern (pattern24); otherwise the still chip of the field texture (16x16 cells
    of field.tex in row order)."""
    t = wmap_chunks(b)["WTEX"]
    return [struct.unpack_from("<BBHH", t, 6 * i) for i in range(len(t) // 6)]


def sdat(b):
    """`SDAT` symbols: 10 bytes each: u8 0, u8 symbol picture (FIELD/symbol/symbol.pack),
    u16 place number (PARAM/param_map_field_symbol.dat, DEBUG/fieldsymbol.dat), u16 x,
    u16 y (field pixels, bottom centre of the symbol box), u8 box width, u8 height.
    The picture's top-left sits at (x - width // 2 - 1, y - height - 1); measured on
    61 symbols, all within one pixel."""
    t = wmap_chunks(b).get("SDAT", b"")
    return [struct.unpack_from("<BBHHHBB", t, 10 * i) for i in range(len(t) // 10)]


def render_field(cells, table, field_tex, pattern8, sea, symbols=(), pictures=()):
    """Field at 16 px per cell: each cell value v is looked up in `table` (WTEX, entry
    v - 1) on its low 10 bits; cells with higher bits mark symbol places and are drawn
    from their low bits (the ground under the symbol). `symbols` (SDAT) are then drawn
    from `pictures` (symbol.pack images)."""
    import numpy as np
    out = np.zeros((cells.shape[0] * 16, cells.shape[1] * 16, 3), np.uint8)
    for y in range(cells.shape[0]):
        for x in range(cells.shape[1]):
            w = int(cells[y, x]) & 0x3FF
            if not 1 <= w <= len(table):
                continue
            _, flags, anim, still = table[w - 1]
            if flags & 8:
                src, c = (sea if flags & 16 else pattern8), anim
            else:
                src, c = field_tex, still
            chip = src[c // 16 * 16:c // 16 * 16 + 16, c % 16 * 16:c % 16 * 16 + 16]
            if chip.shape[:2] == (16, 16):
                out[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = chip
    img = Image.fromarray(out).convert("RGBA")
    for _, pic, _, sx, sy, bw, bh in sorted(symbols, key=lambda r: r[4]):
        if pic < len(pictures) and pictures[pic] is not None:
            img.alpha_composite(pictures[pic], (sx - bw // 2 - 1, sy - bh - 1))
    return img

# ---------------------------------------------------------------- BCA0 joint animation

def _sext(v, n):
    return v - (1 << n) if v & (1 << (n - 1)) else v


def basis_matrix(b, o):
    """10-byte compressed rotation: five u16 whose top 13 bits are m00 m01 m02 m10 m11
    (1.12 fixed); the low 3 bits of c4 c0 c1 c2 c3 in that order build m12 (13-bit
    signed, upper 2 bits unused here). Row 2 = row 0 x row 1."""
    import numpy as np
    c = struct.unpack_from("<5H", b, o)
    top = [_sext(x >> 3, 13) / 4096 for x in c]
    raw = (c[4] & 7) << 12 | (c[0] & 7) << 9 | (c[1] & 7) << 6 | (c[2] & 7) << 3 | (c[3] & 7)
    r0 = np.array(top[:3])
    r1 = np.array([top[3], top[4], _sext(raw & 0x1FFF, 13) / 4096])
    return np.vstack([r0, r1, np.cross(r0, r1)])


def bca_anims(b, off=0):
    """[(name, frames, objects)] of a BCA0 file. Each object is (node, flags, tracks)."""
    out = []
    jo = nitro_blocks(b, off)["JNT0"]
    for name, e in nitro_dict(b, jo + 8):
        ao = jo + u32(e, 0)
        if b[ao:ao + 4] != b"J\0AC":
            continue
        nf, no = u16(b, ao + 4), u16(b, ao + 6)
        objs = [ao + u16(b, ao + 20 + 2 * i) for i in range(no)]
        out.append(dict(name=name, frames=nf, ao=ao, pivot=ao + u32(b, ao + 12),
                        basis=ao + u32(b, ao + 16), objs=objs))
    return out


def _track(b, ao, p, const, width_const):
    """A track at p: (value or None, samples info, next p). const -> one value."""
    if const:
        return ("c", p), p + width_const
    info, off = u32(b, p), u32(b, p + 4)
    return ("a", info, ao + off), p + 8


def _sample(b, tr, frame, kind):
    """Value of a track at a frame. kind: 't' (fx), 'r' (rotation index), 's' (scale fx)."""
    if tr[0] == "c":
        p = tr[1]
        if kind == "r":
            return u16(b, p)
        return s32(b, p) / 4096
    info, p = tr[1], tr[2]
    start, end = info & 0xFFFF, info >> 16 & 0xFFF
    half = info >> 28 & 3  # 0: fx32 samples, otherwise fx16 (bit 29 seen in the data)
    rate = info >> 30 & 3
    f = min(max(frame, start), max(start, end - 1)) - start
    i = f >> rate
    if kind == "r":
        return u16(b, p + 2 * i)
    if half:
        return struct.unpack_from("<h", b, p + (4 if kind == "s" else 2) * i)[0] / 4096
    return s32(b, p + (8 if kind == "s" else 4) * i) / 4096


def bca_pose(b, anim, frame, rest):
    """Local node matrices at `frame`; `rest` is [(t, r, s)] of the model nodes.

    Object: u16 flags, u8 -, u8 node, then translation x y z, rotation, scale x y z.
    Flags: 0 no transform (rest), 1 translation zero, 2 rest translation, 3-5 x/y/z
    constant, 6 rotation identity, 7 rest rotation, 8 rotation constant, 9 scale one,
    10 rest scale, 11-13 x/y/z constant. A rotation value with bit 15 set indexes the
    pivot table (6 bytes), otherwise the basis table (10 bytes)."""
    import numpy as np
    local = [trs_matrix(*r) for r in rest]
    ao = anim["ao"]
    for o in anim["objs"]:
        flags, node = u16(b, o), b[o + 3]
        if node >= len(rest) or flags & 1:
            continue
        t0, r0, s0 = rest[node]
        p = o + 4
        if flags & 2:
            t = np.zeros(3)
        elif flags & 4:
            t = t0
        else:
            t = []
            for k in range(3):
                tr, p = _track(b, ao, p, flags >> (3 + k) & 1, 4)
                t.append(_sample(b, tr, frame, "t"))
            t = np.array(t)
        if flags & 0x40:
            r = np.eye(3)
        elif flags & 0x80:
            r = r0
        else:
            tr, p = _track(b, ao, p, flags >> 8 & 1, 4)
            idx = _sample(b, tr, frame, "r")
            if idx & 0x8000:
                q = anim["pivot"] + 6 * (idx & 0x7FFF)
                mode, a, bb = struct.unpack_from("<Hhh", b, q)
                r = pivot_matrix(mode & 15, mode >> 4 & 15, a / 4096, bb / 4096)
            else:
                r = basis_matrix(b, anim["basis"] + 10 * idx)
        if flags & 0x200:
            sc = np.ones(3)
        elif flags & 0x400:
            sc = s0
        else:
            sc = []
            for k in range(3):
                tr, p = _track(b, ao, p, flags >> (11 + k) & 1, 8)
                sc.append(_sample(b, tr, frame, "s"))
            sc = np.array(sc)
        local[node] = trs_matrix(t, r, sc)
    return local


def material_anims(blk):
    """Per-material texture animation of a BTA0 (`SRT0`) or BMA0 (`MAT0`) file.

    Returns (frames, {material: {track: value or [samples]}}). SRT0 `M\\0AT`: per material
    five 8-byte tracks (scale S, scale T, rotation, translation S, T): u16 frames, u8 0,
    u8 flags, u32 value; flag 0x10 alone means u32 is the offset of s16 1.12 samples,
    one per frame (translation 1.0 = one texture). MAT0 `M\\0AM`: per material five
    4-byte tracks (diffuse, ambient, specular, emission, alpha): u16 value,
    u8 frames, u8 flags; flag 0 means the value is the offset of u8 samples (alpha 0-31).
    """
    blocks = nitro_blocks(blk)
    tag = "SRT0" if "SRT0" in blocks else "MAT0"
    o = blocks[tag]
    _, e = nitro_dict(blk, o + 8)[0]
    ao = o + u32(e, 0)
    frames = u16(blk, ao + 4)
    out = {}
    for name, ent in nitro_dict(blk, ao + 8):
        tracks = {}
        if tag == "SRT0":
            for k, key in enumerate(("ss", "st", "rot", "ts", "tt")):
                _, _, flags, v = struct.unpack_from("<HBBI", ent, 8 * k)
                if flags & 0x30 == 0x10:
                    tracks[key] = [struct.unpack_from("<h", blk, ao + v + 2 * f)[0] / 4096 for f in range(frames)]
                elif key in ("ts", "tt"):
                    tracks[key] = s32(ent, 8 * k + 4) / 4096
        else:
            v, _, flags = struct.unpack_from("<HBB", ent, 4 * 4)
            tracks["alpha"] = list(blk[ao + v:ao + v + frames]) if flags == 0 else (v & 31)
        out[name] = tracks
    return frames, out


def _track_at(t, f):
    return t[min(f, len(t) - 1)] if isinstance(t, list) else t


def model_anim_frames(mdl, bca, anim_index=0, step=2, view="front", scale=None, max_frames=240, blend=False,
                      srt=None, mat=None):
    """Frames of a BMD0 model played with a BCA0 animation, rendered orthographically.
    `srt`/`mat` are BTA0/BMA0 files: texture scrolling and material alpha per frame."""
    import numpy as np
    blocks = nitro_blocks(mdl)
    mo = mdl0_models(mdl, blocks["MDL0"])[0][1]
    rest = [node_trs(mdl, o) for o in model_nodes(mdl, mo)]
    anim = bca_anims(bca)[anim_index] if bca else dict(name="-", frames=1)
    texs, pals = tex0(mdl, blocks["TEX0"]) if "TEX0" in blocks else ({}, {})
    info = material_info(mdl, mo)
    mat_names = [n for n, _ in nitro_dict(mdl, mo + u32(mdl, mo + 8) + 4)]
    srt_tr = material_anims(srt)[1] if srt else {}
    mat_tr = material_anims(mat)[1] if mat else {}
    base = {}

    def base_img(m):
        if m not in base:
            t, pn, flags = info[m] if m < len(info) else (None, None, 0)
            if t in texs:
                tt = texs[t]
                pal = palette(pals[pn]) if pn in pals else grey(256)
                img = texture(tt["data"], tt["fmt"], tt["width"], tt["height"], pal or grey(256),
                              bool(tt["c0"]), tt["pidx"])
                base[m] = (np.asarray(img), flags)
            else:
                base[m] = (None, flags)
        return base[m]

    frames = list(range(0, anim["frames"], step))[:max_frames]
    tris = [model_triangles(mdl, mo, bca_pose(bca, anim, f, rest) if bca else None) for f in frames]
    pts = np.array([p for ts in tris for _, t in ts for p, _ in t])
    lo, hi = pts.min(0), pts.max(0)
    if scale is None:
        scale = 160 / max(hi[0] - lo[0], hi[1] - lo[1], 1e-3)
    out = []
    for f, ts in zip(frames, tris):
        cache = {}

        def tex_rgba(m, f=f, cache=cache):
            if m not in cache:
                img, flags = base_img(m)
                name = mat_names[m] if m < len(mat_names) else None
                if img is not None and name in srt_tr:
                    tr = srt_tr[name]
                    h, w = img.shape[:2]
                    img = np.roll(img, (round(_track_at(tr.get("tt", 0), f) * h),
                                        round(_track_at(tr.get("ts", 0), f) * w)), axis=(0, 1))
                if img is not None and name in mat_tr:
                    a = _track_at(mat_tr[name]["alpha"], f) / 31
                    img = img.copy()
                    img[..., 3] = (img[..., 3] * a).astype(np.uint8)
                cache[m] = (img, flags)
            return cache[m]
        out.append(raster(ts, tex_rgba, view, scale, lo, hi, blend))
    return out, anim

if __name__ == "__main__":
    main()
