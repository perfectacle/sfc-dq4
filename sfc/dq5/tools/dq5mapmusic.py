"""DQ5(SFC) 맵 곡 표(23:FD6A +5)를 맵마다 들어가 실측으로 견준다. 형식은 sfc/dq5/docs/dq5-sound-format.md 「맵 곡」.

맵마다 들어갈 칸은 모든 맵 출구의 도착 칸(dq5exit.py)에서, 없으면 통행 격자(attrgrid.py)의 가운데에 가장 가까운 `o` 칸에서 고른다.
MesenCE 로 선실 세이브스테이트에서 dq5warp.lua 의 TO 로 들어가 lua/dq5sndlog.lua 가 적은 00:CEA2 의 명령 01 인자를 표와 견준다.

사용(MESENCE 는 MesenCE 실행 파일, LIBDIR 은 seqlib.sh 로 만든 dq5warp 드라이버):
  python sfc/dq5/tools/dq5mapmusic.py rom/dq5.sfc work/state/ship.mss work/mm --libdir work/warplib
  python sfc/dq5/tools/dq5mapmusic.py rom/dq5.sfc work/state/ship.mss work/mm-night --libdir work/warplib --set "075E=90;075F=01"
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dq5map import Rom  # noqa: E402
from dq5sound import map_songs  # noqa: E402

ARRIVAL = re.compile(r"([0-9A-F]{2})/([0-9A-F]{2}) 의 출구 \d+ → 도착 \((\d+), (\d+)\)")


def _tool(rom, name, *args):
    return subprocess.run([sys.executable, os.path.join(HERE, name), rom, *args],
                          capture_output=True, text=True, timeout=120).stdout


def entry_cells(rom_path, maps, jobs=8):
    """{맵: (x, y)}. 출구 도착 칸을 먼저 쓰고, 없는 맵은 통행 격자 가운데의 `o` 칸."""
    cells = {}
    with ThreadPoolExecutor(jobs) as ex:
        for out in ex.map(lambda m: _tool(rom_path, "dq5exit.py", *m.split("/")), maps):
            for a in ARRIVAL.finditer(out):
                cells.setdefault(f"{a.group(1)}/{a.group(2)}", (int(a.group(3)), int(a.group(4))))

    def grid(m):
        rows = [ln for ln in _tool(rom_path, "attrgrid.py", *m.split("/")).splitlines()
                if len(ln) > 3 and ln[:2].strip().isdigit() and ln[2] == " "]
        free = [(x, y) for y, ln in enumerate(rows) for x, c in enumerate(ln[3:]) if c == "o"]
        if not free:
            return m, None
        w = max(len(ln) - 3 for ln in rows)
        return m, min(free, key=lambda c: (c[0] - w / 2) ** 2 + (c[1] - len(rows) / 2) ** 2)
    with ThreadPoolExecutor(jobs) as ex:
        for m, c in ex.map(grid, [m for m in maps if m not in cells]):
            if c:
                cells[m] = c
    return cells


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("state")
    ap.add_argument("out")
    ap.add_argument("--libdir", required=True)
    ap.add_argument("--set", default="", help="dq5warp.lua 의 SET(예: 밤 075E=90;075F=01)")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", help="이 맵들만(쉼표로, 예: 21/00,03/02)")
    a = ap.parse_args()
    rom = Rom(open(a.rom, "rb").read())
    table = {f"{bc:02X}/{bd:02X}": s for bc, bd, s in map_songs(rom)}
    if a.only:
        table = {m: table[m] for m in a.only.split(",")}
    cells = {m: c for m, c in entry_cells(a.rom, list(table), a.jobs).items() if m in table}
    mesen = os.environ["MESENCE"]
    probe = os.path.join(HERE, "lua", "dq5sndlog.lua")

    def run(m):
        x, y = cells[m]
        d = os.path.abspath(os.path.join(a.out, m.replace("/", "_")))
        os.makedirs(d, exist_ok=True)
        env = dict(os.environ, LIBDIR=os.path.abspath(a.libdir), STATE=os.path.abspath(a.state), TO=f"{m},{x},{y}",
                   SETTLE="60", TEST="wait:200", MAXF="640", SHOT_DIR=d)
        if a.set:
            env["SET"] = a.set
        subprocess.run([mesen, "--testrunner", os.path.abspath(a.rom), probe], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        try:
            snd = open(os.path.join(d, "snd.txt")).read()
            arrived = re.search(r"arrived map (\S+)", open(os.path.join(d, "warp.txt")).read())
        except OSError:
            return m, None, None
        songs = re.findall(r"cmd=01 arg=(..) from=00:CEA2", snd)
        return m, arrived.group(1) if arrived else None, int(songs[-1], 16) if songs else None
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(run, sorted(cells)))
    same = [r for r in res if r[1] == r[0] and r[2] == table[r[0]]]
    for m, arrived, song in res:
        if (m, arrived, song) not in same:
            print(f"{m}: table {table[m]:02X}, arrived {arrived}, song {song if song is None else f'{song:02X}'}")
    print(f"{len(table)} maps, {len(cells)} entered, {len(same)} same as table, no cell: "
          f"{' '.join(m for m in sorted(table) if m not in cells)}")
    json.dump({m: [arrived, song] for m, arrived, song in res}, open(os.path.join(a.out, "result.json"), "w"))


if __name__ == "__main__":
    main()
