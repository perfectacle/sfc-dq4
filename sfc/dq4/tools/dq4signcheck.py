"""Read every FC field signpost in the game (MesenCE headless).

For each field sign of dq4signs: warp from the ship cabin (dq5warp.lua FIELD) onto a walkable FC block beside it,
turn to it with the pad and choose はなす or しらべる (dq5chestcheck.lua logs every message 24:8BAF shows). From
below, left or right the game must show 136 「(name) read the sign」 and then the sign's own message; from above
(facing down) 137 and 138, the back of the sign, as FC 031B. Before the fix はなす showed 129 「nobody there」.

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    python sfc/dq4/tools/dq4signcheck.py --rom work/ch1/dq4-ch1.sfc --out work/signcheck
"""

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4fieldport  # noqa: E402
import dq4mesen  # noqa: E402
import dq4signs  # noqa: E402
from dq4groupcheck import scene  # noqa: E402
from dq5progresscheck import environment  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

CHECK = DQ5_TOOLS / "lua" / "dq5chestcheck.lua"
# The field reads the pad every 8 frames, so a turn is held for 10. Against a sign the hero only turns.
TURN = "{}:10,wait:30,"
TALK = "a:8,wait:60,a:8,wait:300,a:4,wait:200,a:4,wait:200,b:4,wait:100"
SEARCH = ("a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,"
          "right:6,wait:25,a:8,wait:300,a:4,wait:200,a:4,wait:200,b:4,wait:220")
COMMANDS = {"talk": TALK, "search": SEARCH}
READ, BACK = (0x136,), (0x137, 0x138)
# Search first shows 12B 「(name) searched at their feet」.
SEARCH_FIRST = 0x12B
# FC block beside the sign -> (side, button that turns to the sign). Below first: FC reads from every side but above.
SIDES = {(0, 1): ("below", "up"), (-1, 0): ("left", "right"), (1, 0): ("right", "left"), (0, -1): ("above", "down")}
MESSAGE = re.compile(r"^message f=\d+ value=([0-9A-F]{4})$", re.M)


def jobs(prg):
    """[(name, DQ5 stand cell, turn button, command, expected messages)] for every sign and walkable side."""
    _, props = dq4fieldport.fc_field(prg)
    out = []
    for (x, y, msg), slot in zip(dq4signs.field_signs(prg), dq4signs.SLOTS):
        for (dx, dy), (side, button) in SIDES.items():
            p = props(x // 2 + dx, y // 2 + dy)
            if p & 0x80 or p in (dq4fieldport.ENTRANCE, dq4fieldport.RIGHT_HALF):
                continue
            want = list(BACK) if side == "above" else [*READ, slot]
            for command in COMMANDS:
                name = f"{msg:03X}-{side}-{command}"
                out.append((name, dq4fieldport.stand(x // 2 + dx, y // 2 + dy), button, command, want))
    return out


def run_job(mesence, rom, state, out, name, at, button, command, want):
    where = scene(mesence, rom, state, out, name, FIELD=f"{at[0]},{at[1]}",
                  ROMPATCH=dq4fieldport.warp_patch(rom.read_bytes(), *at), SAVE="scene.mss", TEST="wait:10")
    saved = out / name / "scene.mss"
    if where.get("field") != list(at) or not saved.is_file():
        return {"passed": False, "error": f"warp ended at {where}"}
    dest = out / name / command
    dest.mkdir()
    env = environment(os.environ["LIBDIR"], saved, dest)
    env["INPUT"] = TURN.format(button) + COMMANDS[command]
    dq4mesen.testrunner(str(mesence), str(rom), str(CHECK), "--Snes.DisableFrameSkipping=true", env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False)
    trace = dest / "trace.txt"
    shown = [int(v, 16) for v in MESSAGE.findall(trace.read_text())] if trace.is_file() else []
    if command == "search" and shown[:1] == [SEARCH_FIRST]:
        shown = shown[1:]
    return {"passed": shown == want, "shown": [f"{m:03X}" for m in shown], "want": [f"{m:03X}" for m in want]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom, state = args.rom.resolve(), args.state.resolve()
    todo = jobs(ines.prg(args.dq4.read_bytes()))
    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(zip((j[0] for j in todo), pool.map(lambda j: run_job(mesence, rom, state, out, *j), todo)))
    failed = {k: v for k, v in results.items() if not v["passed"]}
    (out / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"status": "failed" if failed else "passed", "entries": len(results), "failed": failed},
                     ensure_ascii=False))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
