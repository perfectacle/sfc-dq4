"""Check the FC encounter zones of dq4fieldencounter.py in a groups ROM of dq4groupbuild.py (MesenCE headless,
dq5warp.lua FIELD with dq5warptrace.lua).

  zone   stand in an FC zone (ZONES) on two walkable FC blocks side by side and walk right and left with every
         DQ5 rate coefficient at FF (23:EA44, so nearly every step fights): every step 23:E7C2 gets the DQ5 zone
         of that FC zone, and every group is made of the monsters the FC zone can form (row_monsters). The
         walk stops at the first fight, so each zone is walked after three different waits (DELAYS). The group
         forming hook (dq4fieldencounter.ch3_code pick) is traced with the random state 23:EAFD steps
         ($0993~$0996), the clock ($075E) and the chapter flags: every group it forms (monsters and counts) is the
         one dq4fieldencounter.fc_formation gives from that state, chapter and clock (pick_problems)
  rate   the same walk at the ROM's own rates: every step 23:E7C2's Y is the day or night FC terrain factor of
         the FC block times dq4balance.ENCOUNTER, the zone's coefficient is the one dq4fieldencounter.field_rate_index picks, and the chance
         23:E8B7 gets is dq4fieldencounter.dq5_chance of the coefficient, Y and the steps since the last fight
         ($1A9A). The report gives each walked kind's mean cells to a fight in DQ5 (dq5_steps) and twice FC's mean
         steps (fc_steps)

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldencountercheck.py --rom work/dq4-groups/groups.sfc \\
      --out work/dq4-encountercheck
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

import dq4freshstate  # noqa: E402
import dq4balance  # noqa: E402
import dq4encounter  # noqa: E402
import dq4fieldencounter  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4groupbuild  # noqa: E402
import dq4groupcheck  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Scene -> (FC field, FC zone-map cell (column, row) to stand in). The first two have DQ5 namesakes (スライム,
# バブルスライム), 0E is a zone-map row past grid 0's seven, 09 and 08 have base rates 20 and 28 (the others 16),
# w1-34 and w2-36 are fields 1 and 3.
ZONES = {"castle-04": (0, (0x0A, 0x02)), "imuru-05": (0, (0x09, 0x01)), "south-0E": (0, (0x03, 0x0C)),
         "west-09": (0, (0x05, 0x02)), "west-08": (0, (0x03, 0x03)),
         "w1-34": (1, (0x01, 0x02)), "w2-36": (3, (0x02, 0x02)),
         # 2장 무대: サントハイム·サラン 07, 사막의 바자·탑 0B, 사막 0A, エンドール 0C(기본 24)
         "santeem-07": (0, (0x02, 0x04)), "bazaar-0B": (0, (0x03, 0x04)), "desert-0A": (0, (0x04, 0x04)),
         "endor-0C": (0, (0x06, 0x05))}
# 3장 flag(dq4fieldencounter.chapter3_flag())를 켜고 서는 칸: 격자 훅이 고른 3장 지도의 구역 14~17. 모두 3장 일행이 걷는
# 범위 안이고 1·2·4장 지도에서는 다른 구역인 칸이다(14 ← 09, 15 ← 0A, 16 ← 0C, 17 ← 0C).
CH3_ZONES = {"ch3-14": (0, (0x06, 0x02)), "ch3-15": (0, (0x06, 0x04)), "ch3-16": (0, (0x05, 0x05)),
             "ch3-17": (0, (0x07, 0x05))}
ZONES.update(CH3_ZONES)
RATE_SCENES = ("castle-04", "imuru-05", "west-09", "west-08", "santeem-07", "endor-0C", "ch3-16")
# Frames waited before the walk: each starts the random numbers elsewhere, for another fight.
DELAYS = (0, 7, 13)
RATES = "11EA44=FFFFFFFFFFFFFFFF"
# Five cells each way keeps the party on its two blocks' neighbours, inside the zone-map cell.
WALK = "idle:16," + ",".join(["right:40,left:40"] * 8)
TRACE = "23E7C2,23E9B0,23EA40,23E98F"
LOG = "7E1001,7E1003,7E1005,7E1007,7E00B6,7E00B8,7E0000,7E1A9A"
RATE_TRACE = "23E7C2,23E8B7"
EXITS = {"23E9B0": "single", "23EA40": "mixed", "23E98F": "fixed"}
TERRAIN_DAY, TERRAIN_NIGHT = dq4encounter.TERRAIN_DAY, dq4encounter.TERRAIN_NIGHT
GRASS = 0x02


def stand(grid, props, cell):
    """(x, y) FC blocks: a walkable block and its walkable right neighbour inside zone-map cell (column, row),
    grass first, nearest the cell's centre."""
    c, r = cell
    best = None
    for y in range(16 * r, 16 * r + 16):
        for x in range(16 * c, 16 * c + 15):
            if y >= len(grid) or x + 1 >= len(grid[y]):
                continue
            if any(props(x + d, y) & 0x80 or props(x + d, y) in (dq4fieldport.ENTRANCE, dq4fieldport.RIGHT_HALF)
                   for d in (0, 1)):
                continue
            score = (grid[y][x] != GRASS or grid[y][x + 1] != GRASS, abs(x - 16 * c - 7) + abs(y - 16 * r - 8))
            if best is None or score < best[0]:
                best = (score, (x, y))
    if best is None:
        raise ValueError(f"zone-map cell {cell}: no two walkable blocks side by side")
    return best[1]


# 무리 짓기 훅(dq4fieldencounter.ch3_code 의 pick)에 들어올 때 난수 상태·시계·장 flag 바이트(7E:2208, 2장·3장 flag 가 함께 듦)
PICK_LOG = "7E0993,7E0995,7E075E,7E2208"
PICK_LABELS = ("pick", "pick_none", "f_done")
NIGHT_CLOCK = 0xF0      # 21:8000: $075E 가 이 값 이상이면 밤


def pick_trace(labels):
    """무리 짓기 훅 자리(TRACE 에 붙임)."""
    return ",".join(f"{labels[k]:06X}" for k in PICK_LABELS)


def chapter_k(flags):
    """장 flag 바이트 → FC $615A(1장 0, 2장 1, 3장 2)."""
    import dq4ch2event
    f3, b3 = dq4fieldencounter.chapter3_flag()
    f2, b2 = dq4fieldencounter.FLAG_BASE + dq4ch2event.CHAPTER2[0], dq4ch2event.CHAPTER2[1]
    if f2 != f3:
        raise ValueError("2장·3장 flag 가 다른 바이트")
    return 2 if flags & b3 else 1 if flags & b2 else 0


def pick_problems(rows, labels, picks, tables):
    """(지은 횟수 {pick}, 문제): 훅에 들어올 때의 난수 상태·시계·장으로 dq4fieldencounter.fc_formation 모형이 지은
    무리와 훅이 7E:1001~1008 에 지은 무리(f_done)·조우 없음(pick_none)이 다른 곳. picks 는 pick_rows, tables 는 fc_tables."""
    at = {f"{labels[k]:06X}": k for k in PICK_LABELS}
    table = {row[0]: row for row in picks}
    seen, problems = {"pick": 0}, []
    want = None
    for _, pc, kv in rows:
        k = at.get(pc)
        if k is None:
            continue
        if k == "pick":
            zone = (int(kv["X"], 16) & 0xFFFF) // dq4fieldencounter.CH3_ZONE_RECORD
            row = table.get(zone)
            if row is None:
                problems.append(f"구역 {zone} 이 표에 없음")
                want = None
                continue
            state = int(kv["7E0995"], 16) << 16 | int(kv["7E0993"], 16)
            night = int(kv["7E075E"], 16) >= NIGHT_CLOCK
            want = dq4fieldencounter.fc_formation(row, tables, chapter_k(int(kv["7E2208"], 16) & 0xFF), night, state)[0]
        elif want is None:
            continue
        else:
            seen["pick"] += 1
            got = groups(kv) if k == "f_done" else []
            if got != want:
                problems.append(f"무리 {got}, 기대 {want}")
            want = None
    return seen, problems


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
    data = rom.read_bytes()
    prg = ines.prg(args.dq4.read_bytes())
    import subprocess
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(DQ5_TOOLS / "dq5encounterwrite.py"), args.dq5, "dump", "-o",
                    out / "encounter-orig.json"], check=True, capture_output=True)
    # 던전 구역도 빌드와 같이 넘겨야 그 뒤에 받는 3장 필드 구역의 DQ5 번호가 빌드와 같다
    _, _, report = dq4fieldencounter.docs(prg, args.dq5.read_bytes(),
                                          json.loads((out / "encounter-orig.json").read_text(encoding="utf-8")),
                                          dq4groupbuild.dungeon_zones(prg).values())
    dq4groupcheck.WARP = DQ5_TOOLS / "lua" / "dq5warptrace.lua"
    labels = dq4fieldencounter.ch3_labels(prg, args.dq5.read_bytes(), report)
    picks = dq4fieldencounter.pick_rows(prg, report)

    def place(field, cell, key=dq4fieldencounter.FC_MAP):
        grid, props = dq4fieldport.fc_field(prg, field)
        x, y = stand(grid, props, cell)
        if field == 0:
            _, rows = dq4encounter.zone_map(prg, key)
            fc = rows[cell[1]][cell[0]] & 0x3F
        else:
            fc = dq4fieldencounter.FIELD3 if field == 3 else \
                dq4fieldencounter.FIELD1_TOP if cell[1] == 0 else dq4fieldencounter.FIELD1
        return (x, y), grid, props, fc

    def run(name, rates, delay=0):
        field, cell = ZONES[name]
        ch3 = name in CH3_ZONES
        (x, y), grid, props, fc = place(field, cell, dq4fieldencounter.FC_MAP3 if ch3 else dq4fieldencounter.FC_MAP)
        world = dq4fieldport.WORLDS[field]
        extra = {"POKE": f"7E1949={world:02X}"} if world else {}
        patch = dq4fieldport.warp_patch(data, *dq4fieldport.stand(x, y))
        if ch3:
            flag, bit = dq4fieldencounter.chapter3_flag()
            extra["SET"] = f"{flag & 0xFFFF:04X}|{bit:02X}"
            # 3장 조우의 1/10 은 떠돌이 상인이라 대화에 걷기가 멈춘다. 상인은 dq4ch3monstercheck 가 본다
            patch += ";" + dq4fieldencounter.no_merchant_patch(prg, args.dq5.read_bytes(), report)
        scene = f"{name}-rate" if rates else f"{name}-zone{delay}"
        got = dq4groupcheck.scene(mesence, rom, state, out, scene, FIELD="{},{}".format(*dq4fieldport.stand(x, y)),
                                  ROMPATCH=patch if rates else f"{patch};{RATES}", TEST=f"wait:{delay},{WALK}" if delay else WALK, MAXF="2600",
                                  TRACE=RATE_TRACE if rates else f"{TRACE},{pick_trace(labels)}",
                                  LOG=LOG if rates else f"{LOG},{PICK_LOG}", **extra)
        ram = (out / scene / "final.wram").read_bytes()
        want = report[f"{fc:02X}"]
        rows = list(lines(out / scene / "trace.txt"))
        base = {"fc_zone": f"{fc:02X}", "dq5_zone": want["zone"], "blocks": [[x, y], [x + 1, y]], "got": got,
                "1948": ram[0x1948]}
        if rates:
            return scene, {**base, **rate_report(data, prg, grid, fc, want["zone"], rows)}
        zones_seen = sorted({int(kv["A"], 16) & 0xFF for _, pc, kv in rows if pc == "23E7C2"})
        fights = [(EXITS[pc], groups(kv)) for _, pc, kv in rows if pc in EXITS]
        allowed = dq4fieldencounter.row_monsters(next(r for r in picks if r[0] == want["zone"]))
        seen, problems = pick_problems(rows, labels, picks, dq4fieldencounter.fc_tables(prg))
        return scene, {**base, "zones": zones_seen, "fights": fights, "picks": seen, "pick_problems": problems,
                       "ok": zones_seen == [want["zone"]] and bool(fights) and seen["pick"] > 0 and not problems
                       and all({m for m, _ in g} <= allowed for _, g in fights)}

    def rate_report(data, prg, grid, fc, zone, rows):
        """Per walked FC block kind: 23:E7C2's Y and FC's day and night factors, the steps, and the mean cells to a
        fight in DQ5 and FC; ok when every step's Y is a factor of its kind times dq4balance.ENCOUNTER and its chance
        at 23:E8B7 is dq5_chance."""
        import dq5encounter
        from dq5map import Rom
        coef = dq5encounter.area(Rom(data), zone)["coef"]
        base = dq4encounter.zone(prg, fc)["rate"]
        want = dq4fieldencounter._coefs(args.dq5.read_bytes())[report[f"{fc:02X}"]["rate_index"]]
        seen, wrong, step = {}, [], None
        for _, pc, kv in rows:
            if pc == "23E7C2":
                step = kv if int(kv["A"], 16) & 0xFF == zone else None
                continue
            if pc != "23E8B7" or step is None:
                continue
            kind = grid[int(step["7E00B8"], 16) >> 1][int(step["7E00B6"], 16) >> 1]
            y, s = int(step["Y"], 16) & 0xFF, int(step["7E1A9A"], 16) & 0xFF
            factors = [dq4encounter.rd(prg, t + kind) for t in (TERRAIN_DAY, TERRAIN_NIGHT)]
            ours = [dq4balance.chance(f) for f in factors]
            fc_factor = factors[ours.index(y)] if y in ours else y
            row = seen.setdefault(f"{kind:02X}", {"y": y, "fc_day": factors[0], "fc_night": factors[1], "steps": 0,
                                                  "dq5_cells": round(dq4fieldencounter.dq5_steps(coef, y), 1),
                                                  "fc_cells": round(2 * dq4fieldencounter.fc_steps(prg, base, fc_factor),
                                                                    1)})
            row["steps"] += 1
            chance = int(kv["7E0000"], 16) & 0xFF
            if y not in ours or y != row["y"] or chance != dq4fieldencounter.dq5_chance(coef, y, s):
                wrong.append({"kind": kind, "y": y, "1A9A": s, "chance": chance})
            step = None
        return {"coefficient": coef, "fc_base": base, "chances": seen, "wrong": wrong[:10],
                "ok": bool(seen) and coef == want and not wrong}

    jobs = [(name, False, d) for name in ZONES for d in DELAYS] + [(name, True) for name in RATE_SCENES]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(run, *j) for j in jobs])
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": dict(sorted(results.items()))}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
