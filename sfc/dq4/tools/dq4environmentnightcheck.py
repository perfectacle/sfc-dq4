"""Check the night colours of the replaced maps with MesenCE.

Each case warps from the ship cabin (dq4freshstate) to a replaced map with the time of day $075E held at day (0050) or
night (00F8) from the first frame, dumps CGRAM and compares BG lines 1-7 (colour 0 of each line left out: the engine
sets the backdrop) with the palette the build should give: the map's day variant, or at night its night variant when
FC darkens that map (dq4environmentrom.fc_night) and the day variant otherwise. Cases run in parallel; each starts from
the same state with the same time, so the result does not depend on the order or on the clock.

  python sfc/dq4/tools/dq4environmentnightcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/nightcheck [--maps 3D/03 …]
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kr_patch.fc import ines

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import dq4environmentnight  # noqa: E402
import dq4freshstate  # noqa: E402
from dq4environmentart import palette_variant  # noqa: E402
from dq4environmentmap import MAPS as NAMED, dq4block, map_palette  # noqa: E402
from dq4environmentrom import MAPS, _bgr555, fc_night  # noqa: E402
from dq4environmentromcheck import _arrival, dump, warp  # noqa: E402

DAY, NIGHT = 0x0050, 0x00F8
# Chapter 2's maps with a map FC keeps the same at night (the south cave 45/0C), and chapter 1's two towns.
DEFAULT = ("3D/00", "3D/01", "3D/02", "3D/03", "3D/04", "3D/05", "45/00", "45/05", "45/06", "45/0C", "36/00", "37/00")


def fc_source(prg, name):
    named = {n: (g, k) for g, k, _, n in NAMED}
    g, k = named.get(name) or (int(name[:2], 16), int(name[3:], 16))
    return dq4block.Map(prg, g, k)


def lines(flat):
    """CGRAM bytes of BG lines 1-7 as the build writes them."""
    return b"".join(_bgr555(flat[i * 3:i * 3 + 3]).to_bytes(2, "little") for i in range(16, 128))


def colours(data):
    """Colours 1-15 of each of the seven lines, as 16-bit words."""
    return [data[0x20 * r + 2 * c] | data[0x20 * r + 2 * c + 1] << 8 for r in range(7) for c in range(1, 16)]


def expected(prg, name):
    source = fc_source(prg, name)
    day = palette_variant(map_palette(name, source.t))
    dark = fc_night(prg, source)
    return lines(day), lines(dq4environmentnight.night_flat(day)) if dark else lines(day), dark


def arrival(prg, name):
    return _arrival(fc_source(prg, name))


def run_case(mesence, rom, state, out, name, target, time, want, cell):
    label = f"{target.replace('/', '')}-{'night' if time == NIGHT else 'day'}"
    hold = f"075E={time & 0xFF:02X};075F={time >> 8:02X}"
    saved, _ = warp(mesence, rom, state, f"{target},{cell[0]},{cell[1]}", out / label, label, SET=hold)
    cgram = dump(mesence, rom, saved, out / label / "dump")[2]
    got = colours(cgram[0x20:0x100])
    diff = sum(a != b for a, b in zip(got, colours(want)))
    return label, {"map": name, "target": target, "time": f"{time:04X}", "colour_differences": diff}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--maps", nargs="+", default=DEFAULT, help="DQ5 맵(GG/MM), 기본은 2장 맵과 1장 마을 둘")
    ap.add_argument("--jobs", type=int, default=6)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    mesence = os.environ["MESENCE"]
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    prg = ines.prg(args.dq4.read_bytes())
    by_target = {f"{g:02X}/{m:02X}": name for name, (g, m) in MAPS.items()}
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    jobs = []
    for target in args.maps:
        name = by_target[target]
        day, night, dark = expected(prg, name)
        cell = arrival(prg, name)
        jobs += [(name, target, DAY, day, cell), (name, target, NIGHT, night, cell)]
    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(pool.map(lambda j: run_case(mesence, rom, state, out, *j), jobs))
    for target in args.maps:
        name = by_target[target]
        results[f"{target.replace('/', '')}-night"]["fc_night"] = fc_night(prg, fc_source(prg, name))
    ok = all(r["colour_differences"] == 0 for r in results.values())
    report = {"status": "passed" if ok else "failed", "cases": results}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
