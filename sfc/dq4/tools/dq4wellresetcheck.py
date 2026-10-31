"""Check that the well-bottom switch (dq4wellswitch FLAG) is off after a wipe-out and after loading a game, as FC
clears $6E05 (MesenCE headless, ship cabin savestate).

  wipe   warp into the well bottom with the switch on, the hero's HP at 1 and every step fighting (the dungeon
         check's rates), and let the fight end the party: the switch is on when the wipe-out starts (01:88EF) and
         off once the party stands again. "36" first sets the restart slot $195E to 36, whose way back goes by
         01:899F to バトランド's church; the ship state's own slot 02 goes back without it. "-unhooked" puts
         01:88EF back and keeps the switch on
  load   switch on, save at a church (the cabin's talk number 05), reset and continue: the save slot holds the
         switch on, the continue path (25:824F, 25:8278) runs the hook, and the loaded game has it off. Only FLAG
         differs from the same scene with 25:8278 as before

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4wellresetcheck.py --rom work/ch1/dq4-ch1.sfc --out work/dq4-wellreset
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

import dq4dungeonencountercheck  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4wellswitch  # noqa: E402

FLAG, BIT = dq4wellswitch.FLAG[0] & 0xFFFF, dq4wellswitch.FLAG[1]
WIPE_TEST = ",".join(["left:24,right:24"] * 4 + ["a:4,wait:40"] * 90)
WIPES = {"wipe-36": ";195E=36", "wipe-02": "", "wipe-36-unhooked": ";195E=36"}
# The church's yes/no window: the cabin state has not loaded a map, so the shared window records (60:B400, copied to
# 7E:1AC0 on a map load) are not there yet (dq4-window-text-format.md).
SHARED_JP, SHARED_WRAM, SHARED_SIZE = 0x60B400, 0x1AC0, 48
TALK = "b:4,wait:40,up:3,wait:20," + ",".join(["a:4,wait:60"] * 60)
CONTINUE = ",".join(["start:4,wait:200"] * 3 + ["a:4,wait:120"] * 12)
SAVED, RESET, LOADED = 3950, 4000, 7900
SLOT = 0x700012                       # 25:800E: slot 1 of 7E:2000-2A9F
SAVE_SIZE = 0xAA0


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def wipe(mesence, rom, state, out, name):
    unhooked = name.endswith("-unhooked")
    orig = ";{:X}={}".format(lorom(dq4wellswitch.WIPE), dq4wellswitch.WIPE_ORIG.hex().upper()) if unhooked else ""
    got = dq4groupcheck.scene(mesence, rom, state, out, name, TO="3B/00,6,43", MAXF="6000", TEST=WIPE_TEST,
                              SET=f"{FLAG:04X}|{BIT:02X};2042=01;2043=00{WIPES[name]}",
                              ROMPATCH=dq4dungeonencountercheck.rates(rom.read_bytes()) + orig, TRACE="0188EF,01899F",
                              LOG=f"7E{FLAG:04X}")
    rows = list(dq4dungeonencountercheck.lines(out / name / "trace.txt"))
    start = [int(kv[f"7E{FLAG:04X}"], 16) & BIT for _, pc, kv in rows if pc == "0188EF"]
    ram = (out / name / "final.wram").read_bytes()
    lookup = any(pc == "01899F" for _, pc, _ in rows)
    return name, {"got": got, "on_at_wipe": bool(start and start[0]), "lookup_899F": lookup,
                  "after": ram[FLAG] & BIT, "ok": bool(start and start[0]) and bool(ram[FLAG] & BIT) == unhooked
                  and lookup == name.startswith("wipe-36")}


def load(mesence, rom, state, out, name, patch=""):
    dest = out / name
    dest.mkdir()
    # MesenCE keeps a ROM's battery save by its file name.
    copy = dest / f"{name}-{os.getpid()}.sfc"
    shutil.copyfile(rom, copy)
    shared = rom.read_bytes()[lorom(SHARED_JP):lorom(SHARED_JP) + SHARED_SIZE]
    env = dict(os.environ, STATE=str(state),
               SHOT_DIR=str(dest), NEXT=str(DQ5_TOOLS / "lua" / "dq5msg.lua"), POKE="7E36EB=05;7E370B=00",
               SET=";".join([f"{FLAG:04X}|{BIT:02X}"] + [f"{SHARED_WRAM + i:04X}={b:02X}" for i, b in enumerate(shared)]),
               PRE=f"{TALK},wait:400,{CONTINUE}", RESETAT=str(RESET), MAXF=str(LOADED + 100),
               CALLS="25824F,258278", ROMPATCH=patch,
               DUMP=f"{SAVED - 50}:7E2000:{SAVE_SIZE};{SAVED}:{SLOT:06X}:{SAVE_SIZE};{LOADED}:7E2000:{SAVE_SIZE}")
    subprocess.run([str(mesence), "--testrunner", str(copy), str(DQ5_TOOLS / "lua" / "dq5cdldump.lua"),
                    "--Snes.DisableFrameSkipping=true"], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=600, check=False)
    copy.unlink()
    text = (dest / "msg.txt").read_text(encoding="utf-8")
    dumps = {(int(m[1]), int(m[2], 16)): bytes.fromhex(m[3])
             for m in re.finditer(r"(\d+) dump ([0-9A-F]{6}) ([0-9A-F ]+)", text)}
    calls = sorted({m for m in re.findall(r"^\d+ (25824F|258278) ", text, re.M)})
    before, saved, loaded = (dumps.get(k, b"") for k in ((SAVED - 50, 0x7E2000), (SAVED, SLOT), (LOADED, 0x7E2000)))
    return {"calls": calls, "on_before": bool(before and before[FLAG - 0x2000] & BIT),
            "saved": bool(saved and saved[FLAG - 0x2000] & BIT), "after": bool(loaded and loaded[FLAG - 0x2000] & BIT),
            "loaded": loaded}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--state", default="work/state/ship.mss", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom, state = args.rom.resolve(), args.state.resolve()
    dq4groupcheck.WARP = DQ5_TOOLS / "lua" / "dq5warptrace.lua"
    orig = "{:X}={}".format(lorom(dq4wellswitch.LOAD), dq4wellswitch.LOAD_ORIG.hex().upper())
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        wipes = [pool.submit(wipe, mesence, rom, state, out, name) for name in WIPES]
        loads = {k: pool.submit(load, mesence, rom, state, out, k, p) for k, p in (("load", ""), ("load-unhooked", orig))}
        results = dict(f.result() for f in wipes)
        hooked, plain = (loads[k].result() for k in ("load", "load-unhooked"))
    differ = [f"{0x2000 + i:04X}" for i, (a, b) in enumerate(zip(hooked.pop("loaded"), plain.pop("loaded"))) if a != b]
    results["load"] = {**hooked, "unhooked": plain, "differ": differ,
                       "ok": hooked["calls"] == ["25824F", "258278"] and hooked["on_before"] and hooked["saved"]
                       and not hooked["after"] and plain["after"] and differ == [f"{FLAG:04X}"]}
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": results}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
