"""Check the dungeon encounters and songs of dq4groupbuild.py's "dungeon" parts in a ROM (MesenCE headless,
dq5warp.lua with dq5warptrace.lua).

Each scene comes into a dungeon the way the game does (from the field entrance, by an FC stair, or by the warp's
own map move, which sets $194A from the group arrival too) and walks back and forth. The warped scenes make every
step fight (RATES); the field scenes keep the ROM's rates, or the field walk to the entrance fights first. Per dungeon map walked (indoors, $BE bit7):

  zone   every step's 00:82AF A (01:84CF's zone) is the DQ5 zone of the map's FC zone, or FF for a map FC
         leaves without
  fight  every group 23:E7C2 picks in a map is made of the monsters its zone's record weighs (a fixed group only
         where the record has one), a map without a zone meets none, and in a warped scene the map it ends in
         meets one when it has a zone
  well   in the DQ5 group of FC group 3A (dq4wellswitch), the switch bit after each step is what FC's table
         makes of the bit before and the step's FC cell (dq4encounter.toggle_after), and while it is off the
         zone is FF and no group is picked; a scene whose switch ends off need not fight
  song   00:CEA2 (the map's song request on arrival) gets the LINKS "music" slot, and in a field scene the song
         playing ($1D8B) on the dungeon's steps is that slot. A warped scene starts from the ship state's SPC,
         whose song table is not this ROM's (dq4soundstate.lua), and its first map's song may not start

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4dungeonencountercheck.py --rom work/ch1/dq4-ch1.sfc \\
      --out work/dq4-dungeoncheck
"""

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4fieldencounter  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4groupbuild  # noqa: E402
import dq4wellswitch  # noqa: E402
from dq4groupbuild import LINKS, dungeon_zones, placement  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Scene set-up, not what is checked: every coefficient FF and the indoor rate 01:8522 LDY #7 at 40, so
# 255 x 40 >> 6 fights on every step past the engine's first three.
RATES = "11EA44=FFFFFFFFFFFFFFFF;8523=40"
CALM = "11EA44=0000000000000000"
SIDEWAYS = ",".join(["left:24,right:24"] * 16)
UPDOWN = ",".join(["up:24,down:24"] * 16)
TRACE = "0082AF,23E9B0,23EA40,23E98F,00CEA2"
FLAG = f"7E{dq4wellswitch.FLAG[0] & 0xFFFF:04X}"
LOG = f"7E1001,7E1003,7E1005,7E1007,7E00BC,7E00BD,7E00BE,7E194A,7E1D8B,{FLAG},7E3020,7E3080"
SWITCH_ON = f"{dq4wellswitch.FLAG[0] & 0xFFFF:04X}|{dq4wellswitch.FLAG[1]:02X}"
EXITS = {"23E9B0": "single", "23EA40": "mixed", "23E98F": "fixed"}
# Scene -> (how it comes in, walk): ("field", DQ5 group) walks in from the group's first field entrance, ("to", warp
# TO) warps there, ("stair", warp TO, input) warps beside an FC stair (dq4groupcheck stair_scenes) and takes it.
# The walk keeps off the stair beside the warp. A third item: "on" sets the well's switch before the warp, "calm"
# warps with every coefficient 0 (CALM) to walk the switch cells without a fight stopping the walk.
SCENES = {
    "38-00-field": (("field", 0x38), SIDEWAYS), "38-01": (("to", "38/01,12,9"), SIDEWAYS),
    "39-03-field": (("field", 0x39), SIDEWAYS), "39-00-stair": (("stair", "39/01,30,31", "up:32"), SIDEWAYS),
    "39-01": (("to", "39/01,30,31"), SIDEWAYS), "39-02": (("to", "39/02,50,11"), SIDEWAYS),
    "39-04": (("to", "39/04,10,39"), SIDEWAYS), "39-05": (("to", "39/05,14,31"), UPDOWN),
    "3A-00-field": (("field", 0x3A), UPDOWN), "3A-00": (("to", "3A/00,8,11"), UPDOWN),
    "3B-02-stair": (("stair", "38/01,4,9", "up:32"), "down:48," + SIDEWAYS),
    "3B-02-stair-on": (("stair", "38/01,4,9", "up:32"), "down:48," + SIDEWAYS, "on"),
    "3B-00": (("to", "3B/00,6,43"), SIDEWAYS, "on"), "3B-03": (("to", "3B/03,10,83"), SIDEWAYS, "on"),
    "3B-05": (("to", "3B/05,10,7"), SIDEWAYS, "on"), "3B-06": (("to", "3B/06,54,7"), SIDEWAYS, "on"),
    "3B-01-off": (("to", "3B/01,10,7"), SIDEWAYS),
    # Down through the switch rows of 3B/00 (FC (02,18) on, (02,19) off), and left along 3B/03's row 10 across
    # (15,10) on and (14,10) off. The walks keep from facing up on (02,19) and right on (14,10), where the well's
    # voices (dq4ch1event) open a window.
    "3B-00-switch": (("to", "3B/00,4,43"), "down:88", "calm"),
    "3B-03-switch": (("to", "3B/03,46,33"), "left:56", "calm"),
}


def byte(kv, key):
    return int(kv[key], 16) & 0xFF


def lines(path):
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) >= 3:
            yield int(f[0]), f[1], dict(x.split("=") for x in f[2:] if "=" in x)


def groups(kv):
    b = b"".join(int(kv[k], 16).to_bytes(2, "little") for k in ("7E1001", "7E1003", "7E1005", "7E1007"))
    return [(m, c) for m, c in zip(b[:4], b[4:]) if m != 0xFF]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom, state = args.rom.resolve(), args.state.resolve()
    data = rom.read_bytes()
    prg = ines.prg(args.dq4.read_bytes())
    import subprocess
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5encounterwrite.py"), args.dq5, "dump", "-o",
                    out / "encounter-orig.json"], check=True, capture_output=True)
    enc = json.loads((out / "encounter-orig.json").read_text(encoding="utf-8"))
    fc_zones = dungeon_zones(prg)
    dq5_zone = dq4fieldencounter.dungeon_zones(prg, enc, fc_zones.values())
    _, _, report = dq4fieldencounter.docs(prg, args.dq5.read_bytes(), enc, fc_zones.values())
    part_of = {part["fc"]: part for parts in LINKS.values() for part in parts}
    want_of = {}
    for (fc_group, k), (group, number) in placement(prg).items():
        part = part_of[fc_group]
        if part.get("dungeon"):
            fc = fc_zones.get((fc_group, k))
            want_of[f"{group:02X}/{number:02X}"] = {"fc_zone": None if fc is None else f"{fc:02X}",
                                                    "zone": dq5_zone.get(fc), "song": part["music"]}
    dq4groupcheck.WARP = DQ5_TOOLS / "lua" / "dq5warptrace.lua"
    _, props = dq4fieldport.fc_field(prg)

    well_group = dq4wellswitch.group(placement(prg))
    switch_maps = {placement(prg)[dq4wellswitch.FC_GROUP, k][1]: k for k in dq4wellswitch.FC_MAPS}
    import dq4encounter

    def run(name):
        how, walk, *option = SCENES[name]
        extra = {"MAXF": "3600", "TRACE": TRACE, "LOG": LOG}
        switch = option == ["on"]
        if switch:
            extra["SET"] = SWITCH_ON
        calm = option == ["calm"]
        if how[0] == "field":
            link = LINKS[how[1]][0]
            blocks = dq4fieldport.entrance_blocks(props, [link["field"][0]])
            (sx, sy), d = next(dq4groupcheck.enter_starts(props, blocks))
            got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD=f"{sx},{sy}",
                                      ROMPATCH=dq4fieldport.warp_patch(data, sx, sy),
                                      TEST=f"{d}:{dq4groupcheck.PRESS},wait:60,{walk}", **extra)
        else:
            test = f"{how[2]},wait:60,{walk}" if how[0] == "stair" else f"wait:60,{walk}"
            got = dq4groupcheck.scene(mesence, rom, state, out, name, TO=how[1], ROMPATCH=CALM if calm else RATES,
                                      TEST=test, **extra)
        maps, here = {}, None
        well = {"steps": 0, "on_steps": 0, "flips": [], "bad": []}
        for _, pc, kv in lines(out / name / "trace.txt"):
            if not byte(kv, "7E00BE") & 0x80:
                here = None
                continue
            group, number = byte(kv, "7E00BC"), byte(kv, "7E00BD")
            here = f"{group:02X}/{number:02X}"
            seen = maps.setdefault(here, {"steps": 0, "zones": set(), "y": set(), "fights": [], "songs": set(),
                                          "194A": set(), "playing": set(), "off_zones": set(), "off_fights": 0})
            seen["194A"].add(byte(kv, "7E194A"))
            got_on = bool(byte(kv, FLAG) & dq4wellswitch.FLAG[1])
            if pc == "0082AF":
                if group == well_group:
                    x, y = byte(kv, "7E3020") >> 1, (byte(kv, "7E3080") - 1) >> 1
                    k = switch_maps.get(number)
                    want_on = dq4encounter.toggle_after(prg, k, x, y, switch) if k is not None else switch
                    well["steps"] += 1
                    well["on_steps"] += got_on
                    if want_on != switch:
                        well["flips"].append([here, x, y, want_on])
                    if got_on != want_on:
                        well["bad"].append([here, x, y, got_on])
                    switch = got_on
                if group == well_group and not got_on:
                    seen["off_zones"].add(byte(kv, "A"))
                    continue
                seen["steps"] += 1
                seen["zones"].add(byte(kv, "A"))
                seen["y"].add(byte(kv, "Y"))
                seen["playing"].add(byte(kv, "7E1D8B"))
            elif pc == "00CEA2":
                seen["songs"].add(byte(kv, "A"))
            elif group == well_group and not got_on:
                seen["off_fights"] += 1
            else:
                seen["fights"].append((EXITS[pc], groups(kv)))
        report_maps, ok = {}, bool(maps)
        for m, seen in sorted(maps.items()):
            want = want_of.get(m)
            if want is None:
                continue
            zone = report[want["fc_zone"]] if want["fc_zone"] else None
            allowed = set(zone["monsters"]) if zone else set()
            fixed = bool(zone and zone["fixed"]["weight"])
            # A well map walked with the switch off has no steps that count; it must still meet nothing.
            counted = seen["steps"] > 0
            if want["zone"] is None:
                good = seen["zones"] <= {0xFF} and not seen["fights"]
            else:
                good = (not counted or seen["zones"] == {want["zone"]}) and \
                    (how[0] == "field" or calm or m != got.get("map") or not counted or bool(seen["fights"])) and \
                    all((kind != "fixed" or fixed) and {mon for mon, _ in g} <= allowed for kind, g in seen["fights"])
            good = good and seen["off_zones"] <= {0xFF} and not seen["off_fights"]
            good = good and seen["songs"] <= {want["song"]} and seen["194A"] == {dq4groupbuild.INDOOR_ENCOUNTERS}
            if how[0] == "field":
                good = good and seen["playing"] == {want["song"]}
            ok = ok and good
            report_maps[m] = {**{k: sorted(v) if isinstance(v, set) else v for k, v in seen.items()},
                              "want": want, "ok": good}
        # Every scene's first dungeon map is the one it came to: its arrival must ask for the song.
        first = next((m for m in maps if m in want_of), None)
        ok = ok and first is not None and bool(maps[first]["songs"]) and not well["bad"]
        if name.endswith("-switch"):
            ok = ok and len(well["flips"]) >= 2 and well["on_steps"] > 0 and well["steps"] > well["on_steps"]
        if name.endswith("-off"):
            ok = ok and well["steps"] > 0 and well["on_steps"] == 0
        return name, {"got": got, "maps": report_maps, "well": well, "ok": ok}

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(pool.map(run, SCENES))
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items())),
              "zones": {k: v for k, v in report.items() if v["kind"] == "dungeon"}}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
