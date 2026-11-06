"""Use each chapter 2 story item from どうぐ in MesenCE and expect its DQ5 field-use handler.

For each item of dq4itemport (おうごんのうでわ and さえずりのみつ on borrowed key-item slots, とうぞくのカギ on DQ5's B7)
the hero warps (dq4doorcheck.warp, from the ROM's dq4freshstate start) to the Santeem castle courtyard, holds that
item alone in its first item slot (7E:2056, the rest FF, equip bits 7E:2054 off), and opens the command window →
どうぐ → the item → つかう. The case passes when the item's own handler ran (11:8F5B[item - A1]: 11:8BE4 「しかし
ここでは 何も おこらなかった！」 for the story items, 11:8E43 the key-level-1 door use for B7) and no other watched
handler did. A screenshot is kept each time the window number (7E:0A00) changes, as the evidence of the item names.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4storyitemcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/storyitem
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
import dq4itemport  # noqa: E402
from dq4doorcheck import run, warp  # noqa: E402

USE = TOOLS / "lua" / "dq4itemuse.lua"
# The Santeem castle courtyard, an open floor cell with no door or person in front.
PLACE = ("3D/00", 30, 40)
NOTHING, KEY_USE = 0x118BE4, 0x118E43
HANDLER = {**{item: NOTHING for item in dq4itemport.EVENT_ITEMS}, dq4itemport.THIEF_KEY: KEY_USE}
# Command window → どうぐ (right of つよさ), the only item, つかう.
INPUT = "wait:30,a:6,wait:60,down:6,wait:25,right:6,wait:25,a:6,wait:90,a:6,wait:60,a:6,wait:200,a:6,wait:150"


def items_set(item):
    """dq4itemuse SET: the item alone in the hero's 12 item slots, nothing equipped."""
    slots = ";".join(f"{0x2056 + i:04X}={item if i == 0 else 0xFF:02X}" for i in range(12))
    return f"{slots};2054=00;2055=00"


def judge(item, hits):
    want = HANDLER[item]
    ok = hits.get(want, 0) > 0 and all(n == 0 for a, n in hits.items() if a != want)
    return ok


def one(mesence, rom, state, out, item):
    dest = out / f"{item:02X}"
    start = warp(mesence, rom, state, dest / "warp", *PLACE)
    if start is None:
        return {"item": f"{item:02X}", "ok": False, "problem": "순간이동 실패"}
    watch = ",".join(f"{a:06X}" for a in sorted(set(HANDLER.values())))
    run(mesence, rom, USE, dest, {"STATE": str(start), "INPUT": INPUT, "SET": items_set(item), "WATCH": watch})
    text = (dest / "use.txt").read_text() if (dest / "use.txt").exists() else ""
    hits = {int(a, 16): int(n) for a, n in (line.split() for line in text.splitlines())}
    if not hits:
        return {"item": f"{item:02X}", "ok": False, "problem": "결과 없음"}
    return {"item": f"{item:02X}", "name": dq4itemport.korean_names().get(item, "도적의 열쇠"),
            "hits": {f"{a:06X}": n for a, n in hits.items()}, "ok": judge(item, hits)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=3)
    args = ap.parse_args()
    mesence = os.environ["MESENCE"]
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    state = dq4freshstate.resolve(args.state, mesence, args.rom, args.out / "fresh")
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda i: one(mesence, args.rom.resolve(), state, args.out, i), sorted(HANDLER)))
    status = "passed" if results and all(r["ok"] for r in results) else "failed"
    (args.out / "results.json").write_text(json.dumps({"status": status, "cases": results}, ensure_ascii=False,
                                                      indent=1) + "\n")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['item']} {r.get('name', '')} {r.get('hits', '')} {r.get('problem', '')}")
    print(status)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
