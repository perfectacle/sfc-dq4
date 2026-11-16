"""3장 전멸 때 금화(dq4ch3safe 의 20:8162 훅)를 MesenCE 헤드리스로 본다.

검사 롬으로 만든 출발 상태(dq4freshstate)에서 금화 1000, 주인공 HP 1 로 북쪽 동굴 입구 층(3E/03, FC 3D/00)에 순간이동해
걸음마다 싸우게(dq4dungeonencountercheck 의 조우율) 두고 전멸시킨 뒤 금화를 본다. 난수는 걷기 검사의 시드 0 으로 묶는다.

  keep   3장 flag, 일행 소지품에 철 금고 → 1000(잃지 않음)
  none   3장 flag, 금고 없음 → 500
  bag    3장 flag, 금고는 맡긴 물건에만 → 500(FC 처럼 맡긴 물건은 보지 않음)
  ch2    3장 flag 없이 소지품에 금고 → 500(다른 장은 그대로)

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch3safecheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/ch3safe
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

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
import dq4ch3safe as safe  # noqa: E402
import dq4dungeonencountercheck  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4wellresetcheck  # noqa: E402
from dq4itemport import IRON_SAFE  # noqa: E402

GOLD = 1000
# 입구 층 도착 계단(FC (0B,03)) 아래. 순간이동은 TO 한 셀 아래에 내린다
TO = f"{safe.ENTRY},22,9"
SLOT = 0x2056 + 1                     # 주인공 물건 칸 1
BAG = 0x2250 + IRON_SAFE              # 맡긴 물건의 금고 개수
CHAPTER3 = f"{0x2190 + ch3.CHAPTER3[0]:04X}|{ch3.CHAPTER3[1]:02X}"
SCENES = {"keep": (f"{CHAPTER3};{SLOT:04X}={IRON_SAFE:02X}", GOLD),
          "none": (CHAPTER3, GOLD // 2),
          "bag": (f"{CHAPTER3};{BAG:04X}=01", GOLD // 2),
          "ch2": (f"{SLOT:04X}={IRON_SAFE:02X}", GOLD // 2)}


def run(mesence, rom, state, out, name):
    sets, want = SCENES[name]
    gold = ";".join(f"{0x2019 + k:04X}={GOLD >> 8 * k & 0xFF:02X}" for k in range(3))
    got = dq4groupcheck.scene(mesence, rom, state, out, name, TO=TO, MAXF="6000", TEST=dq4wellresetcheck.WIPE_TEST,
                              SET=f"{wc.RNG};2042=01;2043=00;{gold};{sets}",
                              ROMPATCH=dq4dungeonencountercheck.rates(rom.read_bytes()), TRACE="0188ED")
    final = out / name / "final.wram"
    if not final.exists():
        return name, {"ok": False, "error": got}
    ram = final.read_bytes()
    left = int.from_bytes(ram[0x2019:0x201C], "little")
    trace = out / name / "trace.txt"
    wiped = trace.exists() and "0188ED" in trace.read_text(encoding="utf-8")
    return name, {"gold": left, "want": want, "wiped": wiped, "end": got, "ok": wiped and left == want}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    dq4groupcheck.WARP = DQ5_TOOLS / "lua" / "dq5warptrace.lua"
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(run, mesence, rom, state, out, n) for n in SCENES])
    ok = all(r["ok"] for r in results.values())
    result = {"status": "passed" if ok else "failed", "scenes": results}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
