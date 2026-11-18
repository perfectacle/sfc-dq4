"""Check the ルーラ destinations of dq4fieldtravel.py in a groups ROM of dq4groupbuild.py (MesenCE headless,
dq5warp.lua FIELD).

  ruler    stand outside another destination with only this destination's visited flag (7E:2030~) set, cast
           ルーラ (the hero learns every field spell, 7E:2063 = FF) and take the first row of the list: the party
           lands on the destination's landing cell
  chimera  キメラのつばさ (item A4 in the hero's first slot) with 7E:2193 (the last town entered, 01:8EBD) set to
           the destination's group: the same landing cell
  visit    walk into the destination from its leaving cell: its visited flag and 7E:2193 are set (01:8EB2). An
           extra slot (dq4fieldtravel.EXTRA) sets its own bit and 7E:2193 = 80 | slot; サラン and the other parts
           of its DQ5 group (the tower, the cave) set nothing
  list     the ルーラ window with the four flags set; its screen is <out>/list/end.png
  kimeraN  chapter N (1, 2 with dq4growth.CHAPTER2, 3 with CHAPTER3) with its places visited (CH1_SLOTS, CH2_SLOTS,
           CH3_SLOTS): キメラのつばさ opens
           the ルーラ list window in FC list order (dq4fieldtravel.order_slots) and row k lands on that place;
           B in the window keeps the item and the party where it stood. ruler2-k takes row k of ルーラ's list
  ship     ルーラ as above while the party owns the ship (7E:21A5 bit1): the ship moves to the destination's ship
           cell (dq4fieldtravel, from the FC record's ship block)
  sail     the ship standing there (7E:21B5 bit7): from a land cell next to it walk onto it and on into the sea;
           the party sails ($1954 = 03) and ends on another sea cell

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

import dq4freshstate  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4fieldtravel  # noqa: E402
from dq4groupbuild import LINKS, doors, placement  # noqa: E402
from dq4fieldtravel import FC_GROUPS  # noqa: E402
from dq4groupcheck import field_scene  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

SPELLS = "2063=FF;2044=63;2050=63"
# Command window → じゅもん → ルーラ (seventh spell when 7E:2063 = FF) → the list. A takes its first row.
TO_LIST = "a:8,wait:60,right:8,wait:40,a:8,wait:80," + "down:6,wait:12," * 6 + "a:8,wait:80"
RULER = TO_LIST + ",a:8,wait:600"
# Command window → どうぐ → the first item → つかう.
CHIMERA = "a:8,wait:60,right:8,wait:40,down:8,wait:40,a:8,wait:80,a:8,wait:80,a:8,wait:600"
CHIMERA_ITEM = 0xA4
# 2장에 다녀올 수 있는 곳: サントハイム(칸 1)·エンドール(3)·テンペ(12)·フレノール(13)·사막의 바자(14)
CH2_SLOTS = (1, 3, 12, 13, 14)
# 1장: バトランド(2)·イムル(7). 3장: エンドール(3)·ボンモール(4)·レイクナバ(10)
CH1_SLOTS, CH3_SLOTS = (2, 7), (3, 4, 10)
ROW = "down:6,wait:12,"
VISITED, LAST_TOWN = 0x2030, 0x2193
# 7E:21A5 bit1: the party owns the ship (00:D315), so ルーラ moves it (00:D2EB). 7E:21B5 bit7: the ship stands on the
# field at 7E:21CD/21CF (2B:8367). $1954 = 03 is sailing.
SHIP_OWNED, SHIP_SHOWN = "21A5|02", "21B5|80"
SHIP_X, SHIP_Y, VEHICLE, SHIP_VEHICLE = 0x21CD, 0x21CF, 0x1954, 0x03
SEA = dq4fieldtravel.SEA
STEPS = {(0, -1): "up", (1, 0): "right", (0, 1): "down", (-1, 0): "left"}


def sail_moves(props, ship):
    """(ship cell, land cell next to it, direction onto the ship, direction from the ship on into the sea). The
    party boards vertically when it can (dq4fieldtravel.ship_cell) and sails the way the sea runs longest."""
    sx, sy = ship
    land = [(d, (sx - d[0], sy - d[1])) for d in sorted(STEPS, key=lambda d: d[0] != 0)
            if not props((sx - d[0]) >> 1, (sy - d[1]) >> 1) & 0x80]
    if not land:
        raise ValueError(f"ship {ship}: no land next to it")
    d, start = land[0]

    def run(e):
        n = 0
        while n < 4 and props((sx + e[0] * (n + 1)) >> 1, (sy + e[1] * (n + 1)) >> 1) == SEA:
            n += 1
        return n
    away = max((e for e in STEPS if e != (-d[0], -d[1])), key=run)
    return ship, start, STEPS[d], STEPS[away]


def flags(slots):
    bits = sum(1 << s for s in slots)
    return ";".join(f"{VISITED + i:04X}={bits >> 8 * i & 0xFF:02X}" for i in range(3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    prg = ines.prg(args.dq4.read_bytes())
    _, props = dq4fieldport.fc_field(prg)
    found = doors(prg)
    dests = dq4fieldtravel.destinations(prg, LINKS, found)
    extra = dq4fieldtravel.extras(prg, LINKS, placement(prg))
    listed = dests + [e for e in extra if e["listed"]]
    blocked = [p["fc"] for g in {e["group"] for e in extra} for p in LINKS[g]
               if p["fc"] not in FC_GROUPS and p["fc"] not in {e["fc"] for e in extra} and p["field"]]

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
        town = d["group"] if d["slot"] < len(FC_GROUPS) else dq4fieldtravel.SLOT_MARK | d["slot"]
        # 다녀온 칸이 없으면 목록 없이 7E:2193 의 마을로 바로 난다
        got = field_scene(mesence, rom, state, out, f"chimera-{d['slot']}", *start, CHIMERA,
                          SET=f"{flags([])};2056={CHIMERA_ITEM:02X};{LAST_TOWN:04X}={town:02X}", MAXF="3000")
        return f"chimera-{d['slot']}", {"from": list(start), "got": got, "want": {"field": list(d["land"])},
                                        "ok": got == {"field": list(d["land"])}}

    def run_visit(d):
        name = f"visit-{d['slot']}"
        group, bit, town = d["group"], 1 << d["slot"], d["group"]
        if d["slot"] >= len(FC_GROUPS):
            bit, town = (bit, dq4fieldtravel.SLOT_MARK | d["slot"]) if d["listed"] else (0, 0)
        got = field_scene(mesence, rom, state, out, name, *leave(d), f"{inward(d['fc'])}:40,wait:200",
                          SET=f"{flags([])};{LAST_TOWN:04X}=00", MAXF="3000")
        ram = (out / name / "final.wram").read_bytes()
        bits = int.from_bytes(ram[VISITED:VISITED + 3], "little")
        return name, {"got": got, "visited": f"{bits:06X}", "last_town": f"{ram[LAST_TOWN]:02X}",
                      "ok": got.get("map", "").startswith(f"{group:02X}/") and bits == bit and ram[LAST_TOWN] == town}

    def run_blocked(fc):
        """The tower or the cave of an extra slot's DQ5 group: entering sets no visited bit and leaves 7E:2193."""
        name = f"visit-{fc:02X}"
        group = next(g for g, parts in LINKS.items() for p in parts if p["fc"] == fc)
        got = field_scene(mesence, rom, state, out, name, *found[fc][1], f"{inward(fc)}:40,wait:200",
                          SET=f"{flags([])};{LAST_TOWN:04X}=00", MAXF="3000")
        ram = (out / name / "final.wram").read_bytes()
        bits = int.from_bytes(ram[VISITED:VISITED + 3], "little")
        return name, {"got": got, "visited": f"{bits:06X}", "last_town": f"{ram[LAST_TOWN]:02X}",
                      "ok": got.get("map", "").startswith(f"{group:02X}/") and bits == 0 and ram[LAST_TOWN] == 0}

    def inward(fc):
        """Direction from the leaving cell onto the nearest entrance cell."""
        cells, (lx, ly) = found[fc]
        ex, ey = min(cells, key=lambda c: abs(c[0] - lx) + abs(c[1] - ly))
        return STEPS[((ex > lx) - (ex < lx), (ey > ly) - (ey < ly))] if (ex - lx) * (ey - ly) == 0 else "up"

    def run_ship(d):
        name = f"ship-{d['slot']}"
        start = leave(next(e for e in dests if e is not d))
        got = field_scene(mesence, rom, state, out, name, *start, RULER,
                          SET=f"{SPELLS};{flags([d['slot']])};{SHIP_OWNED};{SHIP_SHOWN}", MAXF="3000")
        ram = (out / name / "final.wram").read_bytes()
        ship = [int.from_bytes(ram[a:a + 2], "little") for a in (SHIP_X, SHIP_Y)]
        return name, {"got": got, "ship": ship, "want": list(d["ship"]),
                      "ok": got == {"field": list(d["land"])} and ship == list(d["ship"])}

    def run_sail(d):
        """Stand on land next to the ship, walk onto it, then on into the sea."""
        name = f"sail-{d['slot']}"
        (sx, sy), (nx, ny), board, away = sail_moves(props, d["ship"])
        place = ";".join(f"{a:04X}={v & 0xFF:02X};{a + 1:04X}={v >> 8:02X}" for a, v in ((SHIP_X, sx), (SHIP_Y, sy)))
        # A short push away: the ship crosses 5-6 cells in 40 frames, and エンドール's inlet has 5 sea cells below the
        # ship before the party would step off onto land.
        got = field_scene(mesence, rom, state, out, name, nx, ny, f"idle:16,{board}:24,{away}:16,wait:30",
                          SET=f"{SHIP_SHOWN};{place}", MAXF="3000")
        ram = (out / name / "final.wram").read_bytes()
        cell = got.get("field", [nx, ny])
        return name, {"from": [nx, ny], "ship": [sx, sy], "got": got, "vehicle": f"{ram[VEHICLE]:02X}",
                      "ok": ram[VEHICLE] == SHIP_VEHICLE and props(cell[0] >> 1, cell[1] >> 1) == SEA
                      and cell != [sx, sy]}

    def run_list():
        got = field_scene(mesence, rom, state, out, "list", *leave(dests[0]), TO_LIST + ",wait:10",
                          SET=f"{SPELLS};{flags([d['slot'] for d in listed])}", MAXF="3000")
        return "list", {"got": got, "ok": got == {"field": list(leave(dests[0]))}}

    import dq4growth
    flag, bit = dq4growth.CHAPTER2
    chapter2 = f"{flag & 0xFFFF:04X}|{bit:02X};{flags(CH2_SLOTS)}"
    by_slot = {d["slot"]: d for d in listed}
    rows = [s for s in dq4fieldtravel.order_slots() if s in CH2_SLOTS]
    away = leave(dests[0])
    # 장마다 (2장·3장 flag 를 켜는 SET, 다녀온 칸): FC 는 장과 상관없이 「どこへ」 목록을 띄운다
    flag3, bit3 = dq4growth.CHAPTER3
    kimera_chapters = {1: ("", CH1_SLOTS), 2: (f"{flag & 0xFFFF:04X}|{bit:02X}", CH2_SLOTS),
                       3: (f"{flag3 & 0xFFFF:04X}|{bit3:02X}", CH3_SLOTS)}

    def run_kimera(chapter, k):
        name = f"kimera{chapter}-{k}"
        chapter_set, slots = kimera_chapters[chapter]
        picks = [s for s in dq4fieldtravel.order_slots() if s in slots]
        moves = CHIMERA.rsplit(",wait:600", 1)[0] + ",wait:80," + ROW * k + "a:8,wait:600"
        sets = ";".join(s for s in (chapter_set, flags(slots), f"2056={CHIMERA_ITEM:02X}", f"{LAST_TOWN:04X}=00") if s)
        got = field_scene(mesence, rom, state, out, name, *away, moves, SET=sets, MAXF="3000")
        want = {"field": list(by_slot[picks[k]]["land"])}
        return name, {"row": k, "slot": picks[k], "got": got, "want": want, "ok": got == want}

    def run_kimera2_cancel():
        moves = CHIMERA.rsplit(",wait:600", 1)[0] + ",wait:80,b:8,wait:200"
        got = field_scene(mesence, rom, state, out, "kimera2-cancel", *away, moves,
                          SET=f"{chapter2};2056={CHIMERA_ITEM:02X};{LAST_TOWN:04X}=00", MAXF="3000")
        ram = (out / "kimera2-cancel" / "final.wram").read_bytes()
        return "kimera2-cancel", {"got": got, "item": f"{ram[0x2056]:02X}", "last_town": f"{ram[LAST_TOWN]:02X}",
                                  "ok": got == {"field": list(away)} and ram[0x2056] == CHIMERA_ITEM
                                  and ram[LAST_TOWN] == 0}

    def run_ruler2(k):
        name = f"ruler2-{k}"
        got = field_scene(mesence, rom, state, out, name, *away, TO_LIST + "," + ROW * k + "a:8,wait:600",
                          SET=f"{SPELLS};{chapter2}", MAXF="3000")
        want = {"field": list(by_slot[rows[k]]["land"])}
        return name, {"row": k, "slot": rows[k], "got": got, "want": want, "ok": got == want}

    jobs = [(f, (d,)) for d in listed for f in (run_ruler, run_chimera, run_visit)] + [(run_list, ())]
    jobs += [(run_kimera, (c, k)) for c, (_, slots) in kimera_chapters.items() for k in range(len(slots))]
    jobs += [(run_kimera2_cancel, ()), (run_ruler2, (len(rows) - 1,))]
    jobs += [(run_visit, (d,)) for d in extra if not d["listed"]] + [(run_blocked, (fc,)) for fc in blocked]
    jobs += [(f, (d,)) for d in listed if d["ship"] for f in (run_ship, run_sail)]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(f, *a) for f, a in jobs])
    ok = all(r["ok"] for r in results.values())
    report = {"status": "passed" if ok else "failed", "destinations": dests + extra,
              "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
