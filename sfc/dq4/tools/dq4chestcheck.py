"""Open every chest and drawer of the new groups in the game (MesenCE headless).

For each entry of the dq5chestplace input that dq4groupbuild.py made (OUT/chests.json): warp from the start state
built from the ROM under test (dq4freshstate: the ship cabin on a groups ROM) to a walkable FC cell beside it
(dq5warp.lua), turn the hero to it, and choose しらべる with the controller (dq5chestcheck.lua). The entry passes when
the game looked up the expected reward (12:F43B), showed the chest (131), タンス (12F) or ツボ (135) message, added the
gold of a gold reward, and set one open bit: a chest bit in 7E:2210-2222, or the drawer bit 7E:222C + flag_index &
mask of the entry.

  MESENCE=... LIBDIR=$(uv run krpatch sfc lua) \\
    python sfc/dq4/tools/dq4chestcheck.py --build work/dq4-groups --out work/dq4-chestcheck
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4freshstate  # noqa: E402
import dq4block  # noqa: E402
from dq4environmentmap import block_prop  # noqa: E402
from dq4groupbuild import placement  # noqa: E402
from dq4groupcheck import same_place, scene  # noqa: E402
from dq5chestcheck import environment, gold  # noqa: E402
from kr_patch.fc import ines  # noqa: E402
import dq4readset  # noqa: E402

CHECK = DQ5_TOOLS / "lua" / "dq5chestcheck.lua"
# The command window, then しらべる (dq5chestcheck.INPUT without its first step up).
SEARCH = ("a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,"
          "right:6,wait:25,a:8,wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:220")
# DQ5 item B5 ちいさなメダル shows one more message (0167) after the reward, and the open bit is set only after it.
MEDAL = 0xB5
SEARCH_MEDAL = SEARCH.replace("a:4,wait:150,b:4", "a:4,wait:150,a:4,wait:150,b:4")
# Hero facing byte 7E:31E0 (slot 0 of the people table) for an FC neighbour below, left, right or above.
FACING = {(0, 1): 0x88, (-1, 0): 0x11, (1, 0): 0x22, (0, -1): 0x44}
CHEST_MESSAGE = 0x131
# dq4environmentrom.FURNITURE: FC タンス AB is DQ5 タンス, FC つぼ AA is DQ5 ツボ.
DRAWER_MESSAGE = {0xAB: 0x12F, 0xAA: 0x135}
# Rewards 0100-CFFF are gold (value - 100); D000- are special (FFFF the empty chest) and add none.
GOLD, SPECIAL = 0x100, 0xD000
OPEN_BITS = range(0x2210, 0x2250)
CHEST_BITS = range(0x2210, 0x222C)
DRAWER_BITS = 0x222C
# FC 가 그리지만 걸어서 닿을 칸이 옆에 없는 상자 (DQ5 맵, FC X, Y): 그 이유. 같은 상자(같은 FC 열림 번호)는 다른 맵에서 연다.
UNREACHABLE = {("48/03", 3, 8): "은의 여신상 동굴 40/01: 단추가 여는 방 안(같은 상자를 40/02 에서 염)",
               ("48/06", 36, 19): "은의 여신상 동굴 40/04: 벽 사이(같은 상자를 40/03 (7,16) 에서 염)"}


def fc_maps(prg):
    """DQ5 map "GG/MM" -> FC dq4block.Map put there (dq4groupbuild.placement)."""
    return {f"{group:02X}/{number:02X}": dq4block.Map(prg, g, k) for (g, k), (group, number) in placement(prg).items()}


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


def run_entry(mesence, rom, state, out, preset, name, to, facing, reward, message, drawer):
    extra = {"SET": preset} if preset else {}
    where = scene(mesence, rom, state, out, name, TO=to, LATESET=f"31E0={facing:02X}", SAVE="scene.mss", **extra)
    saved = out / name / "scene.mss"
    want = {"map": to.split(",")[0], "cell": [int(v) for v in to.split(",")[1:3]]}
    if not saved.is_file() or not same_place(where, want):
        return {"passed": False, "error": f"warp: {where} != {want}"}
    dest = out / name / "search"
    dest.mkdir()
    env = environment(os.environ["LIBDIR"], saved, dest)
    env.update(INPUT=SEARCH_MEDAL if reward == MEDAL else SEARCH)
    if dq4readset.run(mesence, rom, CHECK, dest, env, timeout=300)["timed_out"]:
        return {"passed": False, "error": "search: MesenCE timed out"}
    if not all((dest / f).is_file() for f in ("trace.txt", "before.wram", "after.wram")):
        return {"passed": False, "error": "search: no trace or WRAM dump"}
    trace = (dest / "trace.txt").read_text(encoding="utf-8")
    rewards = [int(v, 16) for v in re.findall(r"reward .* value=([0-9A-F]+)", trace)]
    before, after = (dest / "before.wram").read_bytes(), (dest / "after.wram").read_bytes()
    added = gold(after) - gold(before)
    want_gold = reward - GOLD if GOLD <= reward < SPECIAL else 0
    bits = opened(before, after)
    if drawer is None:
        bit_ok = len(bits) == 1 and bits[0][0] in CHEST_BITS and bin(bits[0][1]).count("1") == 1
    else:
        bit_ok = bits == [(DRAWER_BITS + drawer[0], drawer[1])]
    passed = rewards == [reward] and f"value={message:04X}" in trace and added == want_gold and bit_ok
    return {"passed": passed, "rewards": [f"{v:X}" for v in rewards], "gold": added,
            "message": f"value={message:04X}" in trace, "opened": [f"7E:{a:04X}&{m:02X}" for a, m in bits]}


# FC 발밑 숨은 물건(dq4chestport.feet). 조사 메시지는 12B「足もとを　調べた！」, 열림 비트는 발밑 7E:2240 + flag_index.
# 한 번 더 조사해도 보상이 다시 나오지 않아야 한다(FC 의 주웠음 플래그). 「위를 보면」 물건은 위 가구 칸의 서랍 항목이라
# 위의 상자·서랍 장면이 연다
FOOT_MESSAGE = 0x12B
FOOT_BITS = 0x2240
DOWN = 0x44                                    # 7E:31E0 방향(FACING 과 같은 값)
SEARCH_TWICE = SEARCH + "," + SEARCH


def feet_jobs(rom_bytes):
    """[(이름, TO, 방향, 기대 보상 목록, 기대 열림 비트 또는 None)]. 새 그룹 맵의 발밑 줄마다 FC 와 같은 칸에서 두 번
    조사(보상 한 번)와, 옆 FC 칸에서 한 번 조사(그 줄 보상 없음)."""
    import dq5chestreloc
    from dq5map import Rom
    doc = dq5chestreloc.parse(Rom(rom_bytes))
    jobs = []
    for r in doc["foot"]:
        if r["group"] < 0x36:
            continue
        at, x, y = f"{r['group']:02X}/{r['map']:02X}", r["x"], r["y"]
        bit = (FOOT_BITS + r["flag_index"], r["mask"])
        jobs.append((f"foot-{at.replace('/', '')}-{x}-{y}", f"{at},{x},{y}", DOWN, [r["reward"]], bit))
        jobs.append((f"foot-{at.replace('/', '')}-{x}-{y}-beside", f"{at},{x + 2},{y}", DOWN, [], None))
    return jobs


def run_foot(mesence, rom, state, out, preset, name, to, facing, rewards, bit):
    extra = {"SET": preset} if preset else {}
    where = scene(mesence, rom, state, out, name, TO=to, LATESET=f"31E0={facing:02X}", SAVE="scene.mss", **extra)
    saved = out / name / "scene.mss"
    want = {"map": to.split(",")[0], "cell": [int(v) for v in to.split(",")[1:3]]}
    if not saved.is_file() or not same_place(where, want):
        if not rewards:
            # 걸릴 수 없어야 하는 자리에 설 수 없으면(벽) 그 자리에서는 FC 처럼 조사할 수도 없다
            return {"passed": True, "skipped": f"설 수 없는 칸: {where}"}
        return {"passed": False, "error": f"warp: {where} != {want}"}
    dest = out / name / "search"
    dest.mkdir()
    env = environment(os.environ["LIBDIR"], saved, dest)
    env.update(INPUT=SEARCH_TWICE if rewards else SEARCH)
    if dq4readset.run(mesence, rom, CHECK, dest, env, timeout=300)["timed_out"]:
        return {"passed": False, "error": "search: MesenCE timed out"}
    if not all((dest / f).is_file() for f in ("trace.txt", "before.wram", "after.wram")):
        return {"passed": False, "error": "search: no trace or WRAM dump"}
    trace = (dest / "trace.txt").read_text(encoding="utf-8")
    got = [int(v, 16) for v in re.findall(r"reward .* value=([0-9A-F]+)", trace)]
    before, after = (dest / "before.wram").read_bytes(), (dest / "after.wram").read_bytes()
    bits = opened(before, after)
    reward = rewards[0] if rewards else None
    added = gold(after) - gold(before)
    want_gold = reward - GOLD if reward is not None and GOLD <= reward < SPECIAL else 0
    # 12B 는 조사하면 늘 뜨고(없으면 12C 가 이어짐), 보상이 있을 때만 그 뒤 물건·금화 메시지가 나온다
    message = f"value={FOOT_MESSAGE:04X}" in trace
    if not rewards:
        # 옆 칸에는 다른 조사 칸(가구 등)이 있을 수 있어, 이 줄의 비트가 켜지지 않았는지만 본다. 다만 조사가 실제로 돌아
        # 메시지가 하나라도 떠야 한다: 명령 입력이 빗나가 조사하지 않은 실행도 비트는 켜지지 않기 때문이다
        mine = name.rsplit("-beside", 1)[0]
        own = next((j[4] for j in feet_jobs(Path(rom).read_bytes()) if j[0] == mine), None)
        searched = re.findall(r"^message f=\d+ value=([0-9A-F]+)", trace, re.M)
        return {"passed": own not in bits and bool(searched), "rewards": [f"{v:X}" for v in got], "messages": searched,
                "opened": [f"7E:{a:04X}&{m:02X}" for a, m in bits]}
    passed = got == rewards and bits == [bit] and added == want_gold and message
    return {"passed": passed, "rewards": [f"{v:X}" for v in got], "gold": added, "message": message,
            "opened": [f"7E:{a:04X}&{m:02X}" for a, m in bits]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", required=True, type=Path, help="dq4groupbuild.py --out folder")
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--set", default="", help="WRAM writes before the warp (dq5warp.lua SET), e.g. 2199|01")
    ap.add_argument("--maps", help="only these comma-separated maps, e.g. 36/01")
    ap.add_argument("--feet-only", action="store_true", help="발밑·두 칸 앞 장면만")
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rom = (args.build / "groups.sfc").resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    sources = fc_maps(ines.prg(args.dq4.read_bytes()))
    place = json.loads((args.build / "chests.json").read_text(encoding="utf-8"))
    jobs, skipped = [], {}
    only = set(args.maps.split(",")) if args.maps else None
    for row in [] if args.feet_only else place["maps"]:
        if only and row["map"] not in only:
            continue
        source = sources[row["map"]]
        for kind in ("chests", "furniture"):
            for e in row.get(kind, []):
                x, y = e["x"] // 2, e["y"] // 2
                message = CHEST_MESSAGE if kind == "chests" else DRAWER_MESSAGE[block_prop(source, source.cell(x, y) & 31)]
                name = f"{kind}-{row['map'].replace('/', '')}-{e['x']}-{e['y']}"
                if (row["map"], x, y) in UNREACHABLE:
                    skipped[name] = UNREACHABLE[row["map"], x, y]
                    continue
                (hx, hy), facing = stand(source, x, y)
                drawer = (e["flag_index"], e["mask"]) if kind == "furniture" else None
                jobs.append((name, f"{row['map']},{hx},{hy}", facing, e["reward"], message, drawer))
    feet = [j for j in feet_jobs(rom.read_bytes()) if not only or j[1].split(",")[0] in only]
    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(zip((j[0] for j in jobs),
                           pool.map(lambda j: run_entry(mesence, rom, state, out, args.set, *j), jobs)))
        results.update(zip((j[0] for j in feet), pool.map(lambda j: run_foot(mesence, rom, state, out, args.set, *j), feet)))
    failed = {k: v for k, v in results.items() if not v["passed"]}
    if not results:
        # 상자·발밑 목록은 빌드 결과에서 뽑으므로, 비면 아무것도 조사하지 않고 통과하게 된다
        failed["empty"] = {"passed": False, "error": "조사할 장면이 하나도 없음"}
    report = {"status": "failed" if failed else "passed", "entries": len(results), "failed": failed, "skipped": skipped}
    (out / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
