"""Check where the party comes back after a wipe-out, continuing and the chapter-2 start, with the ルーラ slot hooks
of dq4fieldtravel (MesenCE headless from a start state built from the ROM under test, dq4freshstate; continuing on
the libretro cores of dq4savefixture).

  wipe-*     stand on the field by テンペ with the hero's HP at 1, the saved slot 7E:2033 set, and every step
             fighting (the field check's rates): the party stands again at that slot's church of the start table
             (FC and NDS go back to the church saved last, not to the last town entered). An unsaved record (16)
             goes to バトランド's church, FC chapter 1's start
  transfer   chapter 1's end (the report flags at 36/00, dq4ch2event): chapter 2 starts with 7E:2033 at サラン's
             slot, FC chapter 2's first return place
  save-*     continue at テンペ's church, put another slot in 7E:2033 and record with the priest: 7E:2033 and the
             saved record hold テンペ's slot, not サントハイム's that shares its group. MesenCE is not used: there a
             warp to a priest left the command window with its title alone and no record (dq4-savefixture-format)
  continue-* a saved chapter-2 record (flag 2208 bit4, クリフト and ブライ in the party) at each chapter-2 slot,
             continued on snes9x and bsnes: the party stands at that slot's church with the flags and party loaded

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldsavecheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/fieldsave
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

import dq4ch2event  # noqa: E402
import dq4fieldencountercheck  # noqa: E402
import dq4fieldtravel  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4groupcheck  # noqa: E402
from dq4groupbuild import doors  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

RNG = "075B=00;075C=00;075D=00"
PARTY, RECORD, PARTY_COUNTS = 0x2040, 42, (0x201D, 0x201E, 0x201F)
PLACE = dq4fieldtravel.PLACE_SAVED & 0xFFFF
CHAPTER2 = f"{0x2190 + dq4ch2event.CHAPTER2[0]:04X}|{dq4ch2event.CHAPTER2[1]:02X}"
HERO_HP_1 = "2042=01;2043=00"
# Walk till the fight, then let it go on: the party of one with HP 1 falls in the first round.
WIPE_TEST = ",".join(["left:24,right:24"] * 4 + ["a:4,wait:40"] * 90)
# The report flags of chapter 1's end at 36/00 (dq4-chapter2-format 「검증」): A every 90 frames through the end text,
# the chapter box and the opening.
TRANSFER = dict(TO="36/00,32,72", SET="2197|80;21B9|40;2033=07", TEST=",".join(["a:4,wait:86"] * 20), MAXF="2400")
# テンペ's priest stands above (24,51), where continuing stands the party: face up, open the command window, talk,
# take the church window's first row (record), answer yes and page on.
SAVE_INPUT = [("up", 2), ("wait", 20)] + [("a", 4), ("wait", 60)] * 12
SAVE_FROM = 0x07


def slot(fc):
    return dq4fieldtravel.slot_of_fc(fc)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--no-continue", action="store_true", help="skip the libretro continue scenes")
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom = args.rom.resolve()
    data = rom.read_bytes()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    prg = ines.prg(args.dq4.read_bytes())
    import dq4savefixture as fx
    rows = fx.place_rows(data)
    found = doors(prg)
    field = found[0x0E][1]

    def church(k):
        row = rows[k][1]
        return {"map": f"{row[0]:02X}/{row[1]:02X}", "cell": [row[2], row[3]]}

    wipes = {"wipe-tempe": slot(0x0E), "wipe-frenol": slot(0x0F), "wipe-saran": slot(0x13), "wipe-santeem": slot(0x01),
             "wipe-imuru": slot(0x12), "wipe-unsaved": dq4fieldtravel.UNSAVED}

    def run_wipe(name):
        k = wipes[name]
        want = church(slot(dq4fieldtravel.FIRST_CHURCH_FC) if k >= dq4fieldtravel.UNSAVED else k)
        got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD="{},{}".format(*field), TEST=WIPE_TEST,
                                  MAXF="6000", SET=f"{RNG};{CHAPTER2};{HERO_HP_1};{PLACE:04X}={k:02X}", LATESET=RNG,
                                  ROMPATCH=dq4fieldport_warp(data, field) + ";" + dq4fieldencountercheck.RATES)
        return name, {"saved": f"{k:02X}", "got": got, "want": want, "ok": dq4groupcheck.same_place(got, want)}

    def run_transfer():
        got = dq4groupcheck.scene(mesence, rom, state, out, "transfer", **TRANSFER)
        ram = (out / "transfer" / "final.wram").read_bytes()
        flag = ram[0x2190 + dq4ch2event.CHAPTER2[0]] & dq4ch2event.CHAPTER2[1]
        return "transfer", {"got": got, "place": f"{ram[PLACE]:02X}", "chapter2": bool(flag),
                            "ok": bool(flag) and ram[PLACE] == slot(dq4fieldtravel.CHAPTER2_CHURCH_FC)}

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(run_wipe, n) for n in wipes] + [pool.submit(run_transfer)]
        results = dict(j.result() for j in jobs)
    if not args.no_continue:
        results.update(continue_scenes(rom, out, church))
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


def dq4fieldport_warp(data, cell):
    import dq4fieldport
    return dq4fieldport.warp_patch(data, *cell)


def continue_scenes(rom, out, church):
    """continue-<place>-<core>: a chapter-2 record at each chapter-2 slot, continued from power-on."""
    import dq4compatcheck as cc
    import dq4cores
    import dq4savefixture as fx
    out = out / "continue"
    results = {}
    for core_name in cc.CORES:
        path = dq4cores.core_path(core_name)
        for place in ("santeem", "tempe", "frenol", "saran"):
            name = f"continue-{place}-{core_name}"
            rec = fx.SaveSlot.new_game(rom)
            rec.place = place
            rec.poke(0x2190 + dq4ch2event.CHAPTER2[0], rec._get(0x2190 + dq4ch2event.CHAPTER2[0]) | dq4ch2event.CHAPTER2[1])
            # クリフト·ブライ 의 사람 기록(인물 번호가 +0, dq4ch2event.RECRUITS)과 일행 수 셋
            for k, recruit in enumerate(dq4ch2event.RECRUITS, 1):
                rec.poke(PARTY + RECORD * k, recruit["person"])
            for a in PARTY_COUNTS:
                rec.poke(a, 1 + len(dq4ch2event.RECRUITS))
            want = church(rec.place)
            with fx.closing(fx.open_core(path, rom, out / name, rec.to_sram())) as core:
                at = fx.boot(core, rec.goal)
                ram = bytes(core.wram()[:0x20000])
                core.shot(out / name / "end.png")
            flag = bool(ram[0x2190 + dq4ch2event.CHAPTER2[0]] & dq4ch2event.CHAPTER2[1])
            block = rec.to_block()
            keep = [*range(PARTY, PARTY + RECORD * 3), *PARTY_COUNTS]
            same = all(ram[a] == block[a - 0x2000] for a in keep)
            results[name] = {"arrived": at, "goal": [f"{v:02X}" for v in rec.goal], "want": want, "chapter2": flag,
                             "party": same, "ok": at is not None and flag and same}
        name = f"save-tempe-{core_name}"
        rec = fx.SaveSlot.new_game(rom)
        rec.place = "tempe"
        rec.poke(0x2190 + dq4ch2event.CHAPTER2[0], rec._get(0x2190 + dq4ch2event.CHAPTER2[0]) | dq4ch2event.CHAPTER2[1])
        with fx.closing(fx.open_core(path, rom, out / name, rec.to_sram())) as core:
            at = fx.boot(core, rec.goal)
            core.poke([(0x7E0000 | PLACE, SAVE_FROM)])
            for button, frames in SAVE_INPUT:
                for _ in range(frames):
                    core.run(set() if button == "wait" else {button})
            core.shot(out / name / "end.png")
            place, saved = core.rd(0x7E0000 | PLACE), fx.read_sram(core)[fx.SLOTS[0] + PLACE - 0x2000]
        want = slot(0x0E)
        results[name] = {"arrived": at, "place": f"{place:02X}", "saved": f"{saved:02X}",
                         "ok": at is not None and place & 0x7F == want and saved & 0x7F == want}
    return results


if __name__ == "__main__":
    sys.exit(main())
