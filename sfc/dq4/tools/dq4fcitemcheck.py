"""DQ5 자리를 빌린 FC 물건(dq4fcitems)을 MesenCE 에서 필드 どうぐ 로 써 FC 효과를 본다.

dq4storyitemcheck 와 같은 자리(산트하임 앞마당)·같은 입력으로 물건 하나만 든 주인공이 どうぐ → 그 물건 → つかう 를
한다. 장면마다 지켜볼 처리기와 쓰기 전·뒤 WRAM 칸(READ)을 보고 판정한다.

- luck: ラックのたね(AE). 처리기 11:89A4 가 돌고, 운(7E:204A)이 1~3 오르고, 물건이 없어진다(7E:2056 = FF).
- dung·orb·ticket: うまのふん(C2)·せいじゃくのたま(C4)·じょうせんけん(C1). FC 「しかし なにも おこらなかった。」 와 같은 글 18E
  를 띄우는 いのちのいし 처리기 11:8BB9 가 돌고(たたかいのドラム·てんしのすず 처리기는 돌지 않음) 물건이 남는다(FC: 셋 다
  쓰면 남음. いのちのいし 기록은 쓰면 없어짐).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fcitemcheck.py --rom work/ch2/dq4-ch1-full.sfc --out work/fcitem
"""

import argparse
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import dq4fcitems  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4storyitemcheck as story  # noqa: E402
from dq4doorcheck import run, warp  # noqa: E402

LUCK, FIRST_ITEM = 0x204A, 0x2056
# 운을 0 에서 시작해 오른 값이 그대로 1~3 이 되게 한다
LUCK_START = 0x00


def _luck(reads, hits):
    before, after = reads[LUCK]
    problems = []
    if hits.get(dq4fcitems.FIELD_AT, 0) == 0:
        problems.append(f"처리기 {dq4fcitems.FIELD_AT:06X} 가 돌지 않음")
    if not 1 <= after - before <= 3:
        problems.append(f"운 {before} → {after}(1~3 올라야 함)")
    if reads[FIRST_ITEM][1] != 0xFF:
        problems.append(f"물건 칸 {reads[FIRST_ITEM][1]:02X}(써서 없어져야 함)")
    return problems


NOTHING = dq4fcitems.NOTHING_USE


def _nothing(item, own):
    def judge(reads, hits):
        problems = []
        if hits.get(NOTHING, 0) == 0:
            problems.append(f"처리기 {NOTHING:06X} 가 돌지 않음")
        if own is not None and hits.get(own, 0):
            problems.append(f"DQ5 처리기 {own:06X} 가 돎")
        if reads[FIRST_ITEM][1] != item:
            problems.append(f"물건 칸 {reads[FIRST_ITEM][1]:02X}(남아야 함)")
        return problems
    return judge


# 원래 DQ5 롬의 그 자리 필드 처리기(11:8F5B 표): てんしのすず·たたかいのドラム. いのちのいし 자리는 처리기를 그대로 쓴다
DQ5_HANDLERS = {dq4fcitems.SHIP_TICKET: 0x118BBD, dq4fcitems.HORSE_DUNG: None, dq4fcitems.SILENCE_ORB: 0x118BC1}


CASES = {"luck": {"item": dq4fcitems.LUCK_SEED, "set": f"{LUCK:04X}={LUCK_START:02X}",
                  "watch": (dq4fcitems.FIELD_AT,), "read": (LUCK, FIRST_ITEM), "judge": _luck},
         **{name: {"item": item, "set": "", "watch": tuple(a for a in (NOTHING, DQ5_HANDLERS[item]) if a),
                   "read": (FIRST_ITEM,), "judge": _nothing(item, DQ5_HANDLERS[item])}
            for name, item in (("dung", dq4fcitems.HORSE_DUNG), ("orb", dq4fcitems.SILENCE_ORB),
                               ("ticket", dq4fcitems.SHIP_TICKET))}}


def one(mesence, rom, state, out, name):
    case = CASES[name]
    dest = out / name
    start = warp(mesence, rom, state, dest / "warp", *story.PLACE)
    if start is None:
        return {"case": name, "ok": False, "problems": ["순간이동 실패"]}
    run(mesence, rom, story.USE, dest, {
        "STATE": str(start), "INPUT": story.INPUT, "SET": ";".join(v for v in (story.items_set(case["item"]), case["set"]) if v),
        "WATCH": ",".join(f"{a:06X}" for a in case["watch"]), "READ": ",".join(f"{a:04X}" for a in case["read"])})
    use, read = dest / "use.txt", dest / "read.txt"
    if not use.exists() or not read.exists():
        return {"case": name, "ok": False, "problems": ["결과 없음"]}
    hits = {int(a, 16): int(n) for a, n in (line.split() for line in use.read_text().splitlines())}
    reads = {int(a, 16): (int(b, 16), int(c, 16)) for a, b, c in (line.split() for line in read.read_text().splitlines())}
    problems = case["judge"](reads, hits)
    return {"case": name, "ok": not problems, "problems": problems,
            "reads": {f"{a:04X}": v for a, v in reads.items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", help="장면 이름(쉼표)")
    args = ap.parse_args()
    mesence = os.environ["MESENCE"]
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    state = dq4freshstate.resolve(args.state, mesence, args.rom, args.out / "fresh")
    names = args.only.split(",") if args.only else list(CASES)
    results = [one(mesence, args.rom.resolve(), state, args.out, n) for n in names]
    status = "passed" if results and all(r["ok"] for r in results) else "failed"
    (args.out / "results.json").write_text(json.dumps({"status": status, "cases": results}, ensure_ascii=False,
                                                      indent=1) + "\n")
    for r in results:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['case']} {r.get('reads', '')} {' / '.join(r['problems'])}")
    print(status)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
