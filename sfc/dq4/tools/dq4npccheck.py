"""Check the FC people placed by dq4groupbuild.py in MesenCE.

  table  every new map by day and by night (7E:075E = F0): the person table right after the list loader
         (12:803C) equals what the built ROM's list predicts (dq5npc.table_values)
  talk   every standing person: stand on the FC cell next to it, face it, press A; the first message the
         message routine 24:8BAF gets is the person's message (talk + 3C6), or for a church, an inn or the
         deposit the first message of that DQ5 service (an inn also leaves its price for one in 7E:0F28)
  shop   every weapon, item and armor seller: talk, then かう; the items the list window shows
         (dq5progresscheck.lua, MODE=shop) are the group's list from dq4shopport.py

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
SHOP_PROBE = DQ5_TOOLS / "lua" / "dq5progresscheck.lua"
# First message of each DQ5 service (06:DBD2, sfc/dq5/docs/dq5-data-format.md 「가게 종류」). At night the
# inn opens with 071 and the church with 080 (measured on 36/00 and 37/00).
SERVICE_MESSAGE = {1: 0x002, 2: 0x000, 3: 0x001, 4: 0x0B9, 5: 0x07E, 6: 0x070}
NIGHT_MESSAGE = {5: 0x080, 6: 0x071}
SHOPS = {1: "무기", 2: "도구", 3: "방어구"}
INN, INN_PRICE = 6, 0x0F28
# After the shop's greeting: A for the next page and the かう/うる menu, A for かう.
BUY = ",a:4,wait:80,a:4,wait:150"
# The inn sets the price (7E:0F28) for its second message (072). An A while 070 is still printing only
# finishes the text, so wait first and press twice.
STAY = ",wait:150,a:4,wait:150,a:4,wait:120"
NIGHT_POKE = "7E075E=F0;7E075F=00"
SIDES = ((0, 1, "up"), (0, -1, "down"), (1, 0, "left"), (-1, 0, "right"))
# Inputs to talk: turn, A for the command window, A for はなす. A standing party gets the status window and
# the tactics name window after a while (04:B912); an A pressed while those are drawn is lost (30 frames after
# turning, in 37/00 and 37/01), and the command window opens at different speeds. The timings are tried in
# order until a message shows.
TALKS = tuple(f"{{dir}}:20,wait:{turn},a:4,wait:{window},a:4,wait:300"
              for turn, window in ((10, 40), (30, 90), (60, 150), (300, 90)))
TALK_MESSAGE = 0x3C6


def run(mesence, rom, state, out, name, libdir, to, test, night, shop=False):
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
    if shop:
        env.update(MODE="shop", DRIVER=str(DQ5_TOOLS / "lua" / "dq5warp.lua"))
    with (dest / "mesen.log").open("w", encoding="utf-8") as log:
        try:
            subprocess.run([str(mesence), "--testrunner", str(rom), str(SHOP_PROBE if shop else PROBE),
                            "--Snes.DisableFrameSkipping=true"],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return None, None
    if shop:
        text = (dest / "observed.txt").read_text(encoding="utf-8") if (dest / "observed.txt").exists() else ""
        prices = [(int(i, 16), int(v)) for i, v in re.findall(r"price item=([0-9A-F]+) value=(\d+)", text)]
        return None, prices
    text = (dest / "warp.txt").read_text(encoding="utf-8") if (dest / "warp.txt").exists() else ""
    found = re.search(r"^messages (.*)$", text, re.M)
    messages = [int(v, 16) for v in found[1].split(",") if v] if found else None
    final = dest / "final.wram"
    wram = (dest / "npc.bin").read_bytes() if (dest / "npc.bin").exists() else None
    if final.exists() and wram is not None:
        wram = (wram, final.read_bytes())
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
    shop_report = json.loads((args.build / "shop-report.json").read_text(encoding="utf-8"))
    shop_items = {(s["map"], s["kind"]): s["dq5"] for s in shop_report["shops"]}
    inns = {int(g, 16): price for g, price in shop_report["inns"].items()}
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
                # A map with no exit that is no group arrival is entered only by an event (FC 3A/04).
                closed = not dq4block.exit_cells(prg, source) and LINKS[group].get("map", 0) != number
                jobs.append(("closed" if closed else "unreachable", f"talk-{m.replace('/', '')}-{i}", m, None, None,
                             p["night"], None))
                continue
            sx, sy, d = side
            to = f"{m},{','.join(map(str, cell(sx, sy)))}"
            service = p.get("service")
            if service in SHOPS:
                jobs.append(("shop", f"shop-{m.replace('/', '')}-{i}", m, to, d, p["night"],
                             shop_items[m, SHOPS[service]]))
            elif service is not None:
                first = NIGHT_MESSAGE.get(service, SERVICE_MESSAGE[service]) if p["night"] else SERVICE_MESSAGE[service]
                jobs.append(("inn" if service == INN else "talk", f"talk-{m.replace('/', '')}-{i}", m, to, d,
                             p["night"], (first, inns.get(group) if service == INN else None)))
            else:
                jobs.append(("talk", f"talk-{m.replace('/', '')}-{i}", m, to, d, p["night"],
                             (int(p["message"], 16), None)))

    def scene(kind, name, to, test, night):
        if kind in ("unreachable", "closed"):
            return None, None, None
        if kind == "table":
            return run(mesence, rom_path, state, out, name, libdir, to, test, night) + (None,)
        shop = kind == "shop"
        for n, talk in enumerate(TALKS):
            wram, messages = run(mesence, rom_path, state, out, f"{name}-{n}", libdir, to,
                                 talk.format(dir=test) + (BUY if shop else STAY if kind == "inn" else ""), night, shop)
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
            elif kind == "closed":
                results[name] = {"ok": True, "skipped": "map with no exit, entered only by an event"}
            elif kind == "shop":
                items = [item for item, _ in messages or []]
                results[name] = {"ok": items == want, "want": want, "got": messages, "timing": timing}
            elif kind == "table":
                if wram is None:
                    results[name] = {"ok": False, "error": "no npc.bin"}
                    continue
                wram = wram[0] if isinstance(wram, tuple) else wram
                flags = {0x7E2190 + i: wram[0x2190 + i] for i in range(0x170)}
                at = int(layout["lists"][m].replace(":", ""), 16)
                placed = [(a, f) for a, _ in list_entries(built, at) if (f := parse(built, a, night))]
                bad = compare(wram, table_values(built, placed, flags))
                results[name] = {"ok": not bad, "people": len(placed), "mismatch": bad[:10]}
            else:
                message, price = want
                ok = bool(messages) and messages[0] == message
                got_price = None
                if price is not None:
                    got_price = wram[1][INN_PRICE] if isinstance(wram, tuple) else None
                    ok = ok and got_price == price
                results[name] = {"ok": ok, "want": f"{message:03X}", "got": [f"{v:03X}" for v in messages or []][:4],
                                 "timing": timing, **({"price": got_price, "want_price": price} if price is not None else {})}
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"status": report["status"], "scenes": len(results),
                      "failed": {k: v for k, v in results.items() if not v["ok"]}}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
