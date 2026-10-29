"""Check the FC people placed by dq4groupbuild.py in MesenCE.

  table  every new map by day and by night (7E:075E = F0): the person table right after the list loader
         (12:803C) equals what the built ROM's list predicts (dq5npc.table_values)
  talk   every standing person: stand on the FC cell next to it, face it, press A; the first message the
         message routine 24:8BAF gets is the person's message (talk + 3C6)

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4npccheck.py --build work/dq4-groups --out work/dq4-groups/npccheck
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4block  # noqa: E402
from dq4environmentmap import block_prop  # noqa: E402
from dq4groupbuild import LINKS, cell  # noqa: E402
from dq5exitcheck import dp86_allowed, warp_exit  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5npc import list_entries, parse, table_values  # noqa: E402
from dq5npcrecordcheck import compare  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

PROBE = DQ5_TOOLS / "lua" / "dq5npcrecordcheck.lua"
NIGHT_POKE = "7E075E=F0;7E075F=00"
SIDES = ((0, 1, "up"), (0, -1, "down"), (1, 0, "left"), (-1, 0, "right"))
# Inputs to talk: turn, A for the command window, A for はなす. A standing party gets the status window and
# the tactics name window after a while (04:B912); an A pressed while those are drawn is lost (30 frames after
# turning, in 37/00 and 37/01), and the command window opens at different speeds. The timings are tried in
# order until a message shows.
TALKS = tuple(f"{{dir}}:20,wait:{turn},a:4,wait:{window},a:4,wait:300"
              for turn, window in ((10, 40), (30, 90), (60, 150), (300, 90)))
TALK_MESSAGE = 0x3C6


def run(mesence, rom, state, out, name, libdir, to, test, night):
    dest = out / name
    dest.mkdir(parents=True)
    group, number = to.split(",")[0].split("/")
    env = {k: v for k, v in os.environ.items()
           if k not in ("ADULT", "ANYWHERE", "BATTLE", "FIELD", "GROUP", "LATESET", "PARTY", "POKE", "ROMPATCH",
                        "SAVE", "SET", "WAGON")}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF="1800", SETTLE="120", TO=to,
               TEST=f"{test},wait:30", CHECK_GROUP=group, CHECK_MAP=number,
               WARPEXIT=f"{warp_exit(rom):X}", DP86OK=dp86_allowed(rom))
    if night:
        env["POKE"] = NIGHT_POKE
    with (dest / "mesen.log").open("w", encoding="utf-8") as log:
        try:
            subprocess.run([str(mesence), "--testrunner", str(rom), str(PROBE), "--Snes.DisableFrameSkipping=true"],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return None, None
    text = (dest / "warp.txt").read_text(encoding="utf-8") if (dest / "warp.txt").exists() else ""
    found = re.search(r"^messages (.*)$", text, re.M)
    messages = [int(v, 16) for v in found[1].split(",") if v] if found else None
    wram = (dest / "npc.bin").read_bytes() if (dest / "npc.bin").exists() else None
    return wram, messages


def walkable(source, x, y):
    return 0 <= x < source.w and 0 <= y < source.h and not block_prop(source, source.cell(x, y) & 31) & 0x80


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", required=True, type=Path, help="dq4groupbuild.py --out folder")
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    libdir = out / "lib"
    shutil.copytree(os.environ["LIBDIR"], libdir)
    shutil.copyfile(DQ5_TOOLS / "lua" / "dq5warp.lua", libdir / "boot.lua")
    rom_path = (args.build / "groups.sfc").resolve()
    built = Rom(rom_path.read_bytes())
    layout = json.loads((args.build / "npc-layout.json").read_text(encoding="utf-8"))
    people = json.loads((args.build / "npc-report.json").read_text(encoding="utf-8"))
    prg = ines.prg(args.dq4.read_bytes())
    state = args.state.resolve()

    jobs = []
    for m, persons in people.items():
        group, number = int(m[:2], 16), int(m[3:], 16)
        source = dq4block.Map(prg, LINKS[group]["fc"], number)
        occupied = {(p["x"], p["y"]) for p in persons}
        start = next((x, y) for y in range(source.h) for x in range(source.w)
                     if walkable(source, x, y) and (x, y) not in occupied)
        for night in (False, True):
            jobs.append(("table", f"table-{m.replace('/', '')}-{'night' if night else 'day'}", m,
                         f"{m},{','.join(map(str, cell(*start)))}", "wait:60", night, None))
        for i, p in enumerate(persons):
            if p["interval"]:
                continue
            side = next(((p["x"] + dx, p["y"] + dy, d) for dx, dy, d in SIDES
                         if walkable(source, p["x"] + dx, p["y"] + dy) and (p["x"] + dx, p["y"] + dy) not in occupied),
                        None)
            if side is None:
                jobs.append(("unreachable", f"talk-{m.replace('/', '')}-{i}", m, None, None, p["night"], None))
                continue
            sx, sy, d = side
            jobs.append(("talk", f"talk-{m.replace('/', '')}-{i}", m, f"{m},{','.join(map(str, cell(sx, sy)))}",
                         d, p["night"], int(p["message"], 16)))

    def scene(kind, name, to, test, night):
        if kind == "unreachable":
            return None, None, None
        if kind == "table":
            return run(mesence, rom_path, state, out, name, libdir, to, test, night) + (None,)
        for n, talk in enumerate(TALKS):
            wram, messages = run(mesence, rom_path, state, out, f"{name}-{n}", libdir, to, talk.format(dir=test), night)
            if messages:
                return wram, messages, n
        return wram, messages, None

    results = {}
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(scene, kind, name, to, test, night): (kind, name, m, night, want)
                   for kind, name, m, to, test, night, want in jobs}
        for future in concurrent.futures.as_completed(futures):
            kind, name, m, night, want = futures[future]
            wram, messages, timing = future.result()
            if kind == "unreachable":
                results[name] = {"ok": False, "error": "no free walkable cell next to the person"}
            elif kind == "table":
                if wram is None:
                    results[name] = {"ok": False, "error": "no npc.bin"}
                    continue
                flags = {0x7E2190 + i: wram[0x2190 + i] for i in range(0x170)}
                at = int(layout["lists"][m].replace(":", ""), 16)
                placed = [(a, f) for a, _ in list_entries(built, at) if (f := parse(built, a, night))]
                bad = compare(wram, table_values(built, placed, flags))
                results[name] = {"ok": not bad, "people": len(placed), "mismatch": bad[:10]}
            else:
                results[name] = {"ok": bool(messages) and messages[0] == want, "want": f"{want:03X}",
                                 "got": [f"{v:03X}" for v in messages or []][:4], "timing": timing}
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"status": report["status"], "scenes": len(results),
                      "failed": {k: v for k, v in results.items() if not v["ok"]}}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
