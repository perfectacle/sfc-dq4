"""Check the ルーラ destinations of dq4fieldtravel.py in a groups ROM of dq4groupbuild.py (MesenCE headless,
dq5warp.lua FIELD).

  ruler    stand outside another destination with only this destination's visited flag (7E:2030~) set, cast
           ルーラ (the hero learns every field spell, 7E:2063 = FF) and take the first row of the list: the party
           lands on the destination's landing cell
  chimera  キメラのつばさ (item A4 in the hero's first slot) with 7E:2193 (the last town entered, 01:8EBD) set to
           the destination's group: the same landing cell
  visit    walk into the destination from its leaving cell: its visited flag and 7E:2193 are set (01:8EB2)
  list     the ルーラ window with the four flags set; its screen is <out>/list/end.png

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldtravelcheck.py --rom work/dq4-groups/groups.sfc --out work/travelcheck
"""

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4fieldtravel  # noqa: E402
from dq4groupbuild import LINKS, doors  # noqa: E402
from dq4groupcheck import field_scene  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

SPELLS = "2063=FF;2044=63;2050=63"
# Command window → じゅもん → ルーラ (seventh spell when 7E:2063 = FF) → the list. A takes its first row.
TO_LIST = "a:8,wait:60,right:8,wait:40,a:8,wait:80," + "down:6,wait:12," * 6 + "a:8,wait:80"
RULER = TO_LIST + ",a:8,wait:600"
# Command window → どうぐ → the first item → つかう.
CHIMERA = "a:8,wait:60,right:8,wait:40,down:8,wait:40,a:8,wait:80,a:8,wait:80,a:8,wait:600"
CHIMERA_ITEM = 0xA4
VISITED, LAST_TOWN = 0x2030, 0x2193


def flags(slots):
    bits = sum(1 << s for s in slots)
    return ";".join(f"{VISITED + i:04X}={bits >> 8 * i & 0xFF:02X}" for i in range(3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    prg = ines.prg(args.dq4.read_bytes())
    found = doors(prg)
    dests = dq4fieldtravel.destinations(prg, LINKS, found)

    def leave(d):
        return found[d["fc"]][1]

    def run_ruler(d):
        start = leave(next(e for e in dests if e is not d))
        got = field_scene(mesence, rom, state, out, f"ruler-{d['slot']}", *start, RULER,
                          SET=f"{SPELLS};{flags([d['slot']])}", MAXF="3000")
        return f"ruler-{d['slot']}", {"from": list(start), "got": got, "want": {"field": list(d["land"])},
                                      "ok": got == {"field": list(d["land"])}}

    def run_chimera(d):
        start = leave(next(e for e in dests if e is not d))
        got = field_scene(mesence, rom, state, out, f"chimera-{d['slot']}", *start, CHIMERA,
                          SET=f"2056={CHIMERA_ITEM:02X};{LAST_TOWN:04X}={d['group']:02X}", MAXF="3000")
        return f"chimera-{d['slot']}", {"from": list(start), "got": got, "want": {"field": list(d["land"])},
                                        "ok": got == {"field": list(d["land"])}}

    def run_visit(d):
        name = f"visit-{d['slot']}"
        got = field_scene(mesence, rom, state, out, name, *leave(d), "up:40,wait:200",
                          SET=f"{flags([])};{LAST_TOWN:04X}=00", MAXF="3000")
        ram = (out / name / "final.wram").read_bytes()
        bits = int.from_bytes(ram[VISITED:VISITED + 3], "little")
        return name, {"got": got, "visited": f"{bits:06X}", "last_town": f"{ram[LAST_TOWN]:02X}",
                      "ok": got.get("map", "").startswith(f"{d['group']:02X}/") and bits == 1 << d["slot"]
                      and ram[LAST_TOWN] == d["group"]}

    def run_list():
        got = field_scene(mesence, rom, state, out, "list", *leave(dests[0]), TO_LIST + ",wait:10",
                          SET=f"{SPELLS};{flags([d['slot'] for d in dests])}", MAXF="3000")
        return "list", {"got": got, "ok": got == {"field": list(leave(dests[0]))}}

    jobs = [(f, (d,)) for d in dests for f in (run_ruler, run_chimera, run_visit)] + [(run_list, ())]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(f, *a) for f, a in jobs])
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "destinations": dests, "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
