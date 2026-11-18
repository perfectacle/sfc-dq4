"""Check the night colours of the replaced maps with MesenCE.

Each case warps from the ship cabin (dq4freshstate) to a replaced map with the time of day $075E held at day (0050) or
night (00F8) from the first frame, dumps CGRAM and compares BG lines 1-7 (colour 0 of each line left out: the engine
sets the backdrop) with the palette the build should give: the map's day variant, or at night its night variant when
FC darkens that map (dq4environmentrom.fc_night) and the day variant otherwise. Cases run in parallel; each starts from
the same state with the same time, so the result does not depend on the order or on the clock.

The event case `tempe-altar` takes the way a player does: it enters テンペ with the substitute flag on, so the priest's
script runs the basket event (night set before the move), and taps through the narration. A ROM patch ends the event
right after its move onto the altar (the first pause becomes FF) so the boss battle does not repaint CGRAM; the BG
lines at the end must be テンペ's night lines. --no-event leaves it out.

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


EVENT_MAP = "3D/03"


def event_patch(data):
    """ROMPATCH that ends the テンペ altar event at its first pause after the move (dq4ch2tempe ALTAR_WARP + C2)."""
    import dq4ch2tempe
    at = data.find(dq4ch2tempe.ALTAR_WARP + b"\xc2")
    if at < 0 or data.find(dq4ch2tempe.ALTAR_WARP + b"\xc2", at + 1) >= 0:
        raise SystemExit("텐페 제단 이벤트의 옮기기 + 쉼이 롬에 하나가 아님")
    return f"{at + len(dq4ch2tempe.ALTAR_WARP):X}=FF"


def event_case(mesence, rom, state, out, want):
    """The basket event (dq4mapsongcheck tempe-basket's flags and taps) ending on the altar: BG lines 1-7 at night."""
    import dq4groupcheck
    import dq4mapsongcheck
    got = dq4groupcheck.scene(mesence, rom, state, out, "tempe-altar", TO=f"{EVENT_MAP},42,77",
                              SET=dq4mapsongcheck.TEMPE_GONE, TEST=f"{dq4mapsongcheck.BASKET_TEST},wait:200",
                              ROMPATCH=event_patch(rom.read_bytes()), MAXF=4000)
    final = out / "tempe-altar"
    if "error" in got:
        return "tempe-altar", {"map": EVENT_MAP, "error": got["error"], "colour_differences": -1}
    wram, cgram = (final / "final.wram").read_bytes(), (final / "final.cgram").read_bytes()
    diff = sum(a != b for a, b in zip(colours(cgram[0x20:0x100]), colours(want)))
    return "tempe-altar", {"map": EVENT_MAP, "where": got, "time": f"{wram[0x075E] | wram[0x075F] << 8:04X}",
                           "colour_differences": diff if got.get("map") == EVENT_MAP else -1}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--maps", nargs="+", default=DEFAULT, help="DQ5 맵(GG/MM), 기본은 2장 맵과 1장 마을 둘")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--no-event", action="store_true", help="テンペ 바구니 이벤트 장면을 빼기")
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
        cases = [pool.submit(run_case, mesence, rom, state, out, *j) for j in jobs]
        if not args.no_event:
            cases.append(pool.submit(event_case, mesence, rom, state, out, expected(prg, by_target[EVENT_MAP])[1]))
        results = dict(c.result() for c in cases)
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
