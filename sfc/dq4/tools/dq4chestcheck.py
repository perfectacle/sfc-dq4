"""Open every chest and drawer of the new groups in the game (MesenCE headless).

For each entry of the dq5chestplace input that dq4groupbuild.py made (OUT/chests.json): warp from the ship cabin
to a walkable FC cell beside it (dq5warp.lua), turn the hero to it, and choose しらべる with the controller
(dq5chestcheck.lua). The entry passes when the game looked up the expected reward (12:F43B), showed the chest
(131), タンス (12F) or ツボ (135) message, added the gold of a gold reward, and set one open bit: a chest bit in
7E:2210-2222, or the drawer bit 7E:222C + flag_index & mask of the entry.

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    python sfc/dq4/tools/dq4chestcheck.py --build work/dq4-groups --out work/dq4-chestcheck
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

import dq4block  # noqa: E402
from dq4environmentmap import all_maps, block_prop  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4groupcheck import same_place, scene  # noqa: E402
from dq5chestcheck import environment, gold  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

CHECK = DQ5_TOOLS / "lua" / "dq5chestcheck.lua"
# The command window, then しらべる (dq5chestcheck.INPUT without its first step up).
SEARCH = ("a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,"
          "right:6,wait:25,a:8,wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:220")
# Hero facing byte 7E:31E0 (slot 0 of the people table) for an FC neighbour below, left, right or above.
FACING = {(0, 1): 0x88, (-1, 0): 0x11, (1, 0): 0x22, (0, -1): 0x44}
CHEST_MESSAGE = 0x131
# dq4environmentrom.FURNITURE: FC タンス AB is DQ5 タンス, FC つぼ AA is DQ5 ツボ.
DRAWER_MESSAGE = {0xAB: 0x12F, 0xAA: 0x135}
GOLD = 0x100
OPEN_BITS = range(0x2210, 0x2250)
CHEST_BITS = range(0x2210, 0x2228)
DRAWER_BITS = 0x222C


def fc_maps(prg):
    """DQ5 map "GG/MM" -> FC dq4block.Map of the GROUPS map put there."""
    return {f"{GROUPS[name][0]:02X}/{GROUPS[name][1]:02X}": dq4block.Map(prg, g, k)
            for g, k, _, name in all_maps(prg) if name in GROUPS}


def stand(source, x, y):
    """(hero DQ5 cell, facing byte) from the first walkable FC neighbour, below first."""
    for (dx, dy), facing in FACING.items():
        nx, ny = x + dx, y + dy
        if 0 <= nx < source.w and 0 <= ny < source.h and not block_prop(source, source.cell(nx, ny) & 31) & 0x80:
            return (2 * nx, 2 * ny + 1), facing
    raise ValueError(f"({x},{y}): no walkable FC neighbour")


def opened(before, after):
    """[(address, newly set bits)] in the open-bit bytes."""
    return [(a, after[a] & ~before[a]) for a in OPEN_BITS if after[a] & ~before[a]]


def run_entry(mesence, rom, state, out, name, to, facing, reward, message, drawer):
    where = scene(mesence, rom, state, out, name, TO=to, LATESET=f"31E0={facing:02X}", SAVE="scene.mss")
    saved = out / name / "scene.mss"
    want = {"map": to.split(",")[0], "cell": [int(v) for v in to.split(",")[1:3]]}
    if not saved.is_file() or not same_place(where, want):
        return {"passed": False, "error": f"warp: {where} != {want}"}
    dest = out / name / "search"
    dest.mkdir()
    env = environment(os.environ["LIBDIR"], saved, dest)
    env.update(INPUT=SEARCH)
    try:
        subprocess.run([str(mesence), "--testrunner", str(rom), str(CHECK), "--Snes.DisableFrameSkipping=true"],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "search: MesenCE timed out"}
    if not all((dest / f).is_file() for f in ("trace.txt", "before.wram", "after.wram")):
        return {"passed": False, "error": "search: no trace or WRAM dump"}
    trace = (dest / "trace.txt").read_text(encoding="utf-8")
    rewards = [int(v, 16) for v in re.findall(r"reward .* value=([0-9A-F]+)", trace)]
    before, after = (dest / "before.wram").read_bytes(), (dest / "after.wram").read_bytes()
    added = gold(after) - gold(before)
    want_gold = reward - GOLD if reward >= GOLD else 0
    bits = opened(before, after)
    if drawer is None:
        bit_ok = len(bits) == 1 and bits[0][0] in CHEST_BITS and bin(bits[0][1]).count("1") == 1
    else:
        bit_ok = bits == [(DRAWER_BITS + drawer[0], drawer[1])]
    passed = rewards == [reward] and f"value={message:04X}" in trace and added == want_gold and bit_ok
    return {"passed": passed, "rewards": [f"{v:X}" for v in rewards], "gold": added,
            "message": f"value={message:04X}" in trace, "opened": [f"7E:{a:04X}&{m:02X}" for a, m in bits]}


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
    rom, state = (args.build / "groups.sfc").resolve(), args.state.resolve()
    sources = fc_maps(ines.prg(args.dq4.read_bytes()))
    place = json.loads((args.build / "chests.json").read_text(encoding="utf-8"))
    jobs = []
    for row in place["maps"]:
        source = sources[row["map"]]
        for kind in ("chests", "furniture"):
            for e in row.get(kind, []):
                x, y = e["x"] // 2, e["y"] // 2
                message = CHEST_MESSAGE if kind == "chests" else DRAWER_MESSAGE[block_prop(source, source.cell(x, y) & 31)]
                (hx, hy), facing = stand(source, x, y)
                name = f"{kind}-{row['map'].replace('/', '')}-{e['x']}-{e['y']}"
                drawer = (e["flag_index"], e["mask"]) if kind == "furniture" else None
                jobs.append((name, f"{row['map']},{hx},{hy}", facing, e["reward"], message, drawer))
    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(zip((j[0] for j in jobs),
                           pool.map(lambda j: run_entry(mesence, rom, state, out, *j), jobs)))
    failed = {k: v for k, v in results.items() if not v["passed"]}
    report = {"status": "failed" if failed else "passed", "entries": len(results), "failed": failed}
    (out / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
