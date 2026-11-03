"""Talk to every sleeper of the ported maps from beside the foot and beside the head of the bed, in MesenCE.

FC answers beside the foot (the FC cell the person stands on); DQ5 answers a sleeper laid half a block right beside
the head; dq4sleepertalk makes the ROM answer on both sides (a user decision). For each sleeper (an entry dq4npcport
laid down: DQ5 cell (2x+1, 2y)) and each side, the hero stands on a free walkable FC cell next to that block, faces
it and talks; the first message must be the sleeper's.

The arrival is checked: after a warp the hero must stand on the cell asked for, read from the person table
(7E:3020/3080). The chapter-1 ROM puts the party one cell lower than the cell a same-group warp asks for, so each
scene asks for that cell and the one above it and keeps the warp that lands on the cell.

--chapter1 is for the chapter-1 ROM: every warp first sets the throne-room opening flag as done, and the throne room's
sleepers are taken from dq4chapter1 (its own night list, NIGHT_ABED) instead of npc-report.json. Its start state
stands in the throne room, and dq5warp.lua sees the arrival as the map number changing to the destination, so a warp
to the throne room never arrives; those scenes start from the state the first scene saved on arriving (the first
try that saved one). That relies on the order of scenes(): maps sorted, so a 36/00 scene runs before the throne room
(36/01); a throne-room scene with no saved state stops the check.

Each scene starts from the same random state (dq4pins.RNG, at the start and again on arrival) and holds every person
slot still from the frame the map is loaded (lua/dq4holdwalk.lua clears the step interval, the high nibble of
7E:3300+slot, every frame and keeps the low nibble), so a wanderer never steps between the hero and the sleeper and the
result does not hang on the random walk. The arrival frame 90 frames after loading (LATESET) would be too late.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4sleepercheck.py --rom work/ch1/dq4-ch1-full.sfc \\
      --build work/dq4-groups --chapter1 --out work/sleepercheck

--build is a dq4groupbuild.py --out folder (its npc-report.json says where the sleepers are). Format:
sfc/dq4/docs/dq4-environment-format.md 「인물」.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4block  # noqa: E402
import dq4chapter1  # noqa: E402
import dq4chapterbox  # noqa: E402
from dq4pins import RNG  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4npccheck  # noqa: E402
from dq4groupbuild import cell, fc_map  # noqa: E402
from dq5map import Rom  # noqa: E402
from kr_patch.fc import ines  # noqa: E402


def sleepers(report):
    """(map, index, person) of every person laid down."""
    for m, people in sorted(report.items()):
        if "/" not in m or len(m) != 5:
            continue
        for i, p in enumerate(people):
            if (p["dq5"]["x"], p["dq5"]["y"]) != cell(p["x"], p["y"]):
                yield m, i, p


# Person slots from here on are townspeople (7E:1994 on arrival, read back in every scene); below are the party's.
FIRST_PERSON = 0x08
SLOTS = 0x20
HOLD = f"{FIRST_PERSON:02X}-{SLOTS - 1:02X}"


def chapter1_throne():
    """npc-report.json-shaped night people of the chapter-1 throne room after its opening (dq4chapter1.npc_doc)."""
    def person(x, y, dq5=None, message=None):
        return {"x": x, "y": y, "night": True, "message": message, "dq5": dq5 or dict(zip("xy", cell(x, y)))}
    out = [person(x, y) for x, y, *_ in dq4chapter1.NIGHT_STAFF]
    for x, y, gfx, talk in dq4chapter1.NIGHT_ABED:
        e = dq4chapter1.lying(x, y, gfx, talk)["fields"]
        out.append(person(x, y, {"x": e["x"], "y": e["y"]}, f"{talk + dq4chapter1.MESSAGE_OF_TALK:03X}"))
    return out


def scenes(prg, report):
    """(name, map, (x, y) hero cell, direction, night, message) for both sides of every sleeper."""
    out = []
    for m, i, p in sleepers(report):
        group, number = (int(v, 16) for v in m.split("/"))
        source = dq4block.Map(prg, *fc_map(prg, group, number))
        taken = {(q["x"], q["y"]) for q in report[m] if q["night"] == p["night"]}
        for side, block in (("foot", (p["x"], p["y"])), ("head", dq4npccheck.talk_cell(p))):
            spot = dq4npccheck.talk_side(source, *block, taken)
            if spot is None:
                raise ValueError(f"{m} sleeper {i}: no free walkable cell beside the {side}")
            sx, sy, d = spot
            out.append((f"{m.replace('/', '')}-{i}-{side}", m, cell(sx, sy), d, p["night"], int(p["message"], 16)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--build", required=True, type=Path, help="dq4groupbuild.py --out folder")
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--chapter1", action="store_true", help="the ROM is the chapter-1 build (see above)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    libdir = out / "lib"
    shutil.copytree(os.environ["LIBDIR"], libdir)
    shutil.copyfile(DQ5_TOOLS / "lua" / "dq5warp.lua", libdir / "boot.lua")
    rom = args.rom.resolve()
    ret = dq4npccheck.decoder_return(Rom(rom.read_bytes()))
    report = json.loads((args.build / "npc-report.json").read_text(encoding="utf-8"))
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    sets = RNG
    if args.chapter1:
        flag, mask = dq4chapterbox.CHAPTER1.flag
        sets += f";{flag & 0xFFFF:04X}|{mask:02X}"
        report = {**report, dq4chapter1.THRONE: chapter1_throne()}
    late = RNG
    via = None
    results = {}
    for name, m, (x, y), d, night, want in scenes(ines.prg(args.dq4.read_bytes()), report):
        got, at = None, None
        start, save = state, None
        if args.chapter1 and m == dq4chapter1.THRONE:
            if via is None or not via.exists():
                raise SystemExit(f"{name}: no state saved in another map to warp into the throne room from")
            start = via
        elif args.chapter1 and via is None:
            save = "via.mss"
        for k, ask in enumerate((y, y - 1)):
            for n, talk in enumerate(dq4npccheck.TALKS):
                wram, messages = dq4npccheck.run(mesence, rom, start, out, f"{name}-{k}{n}", libdir, f"{m},{x},{ask}",
                                                 talk.format(dir=d), night, False, ret, sets, late, save, HOLD)
                if save and (out / f"{name}-{k}{n}" / save).exists():
                    via, save = out / f"{name}-{k}{n}" / save, None
                final = wram[1] if isinstance(wram, tuple) else None
                if final and final[0x1994] != FIRST_PERSON:
                    raise SystemExit(f"{name}: first person slot 7E:1994 = {final[0x1994]:02X}, not {FIRST_PERSON:02X}")
                at = (final[0x3020], final[0x3080]) if final else None
                messages = (messages or (None, []))[0]
                if at != (x, y):
                    break
                if messages:
                    got = messages[0]
                    break
            if at == (x, y):
                break
        results[name] = {"ok": at == (x, y) and got == want, "at": at, "want": [x, y], "message": f"{want:03X}",
                         "got": None if got is None else f"{got:03X}"}
    ok = bool(results) and all(r["ok"] for r in results.values())
    report_out = {"status": "passed" if ok else "failed", "rom": str(args.rom), "scenes": results}
    (out / "results.json").write_text(json.dumps(report_out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"status": report_out["status"], "scenes": len(results),
                      "failed": {k: v for k, v in results.items() if not v["ok"]}}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
