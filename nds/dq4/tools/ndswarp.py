"""NDS DQ4 장면 이동(워프)과 진행도 프리셋. 근거와 RAM 주소는 nds/dq4/docs/debug.md.

    python nds/dq4/tools/ndswarp.py list [접두어]                 맵 이름 목록(data/MAP/_list.txt 순서)
    python nds/dq4/tools/ndswarp.py presets [찾을 말]             진행도 프리셋 목록(DEBUG/flagshop.dat)과 시작 맵
    python nds/dq4/tools/ndswarp.py boot OUT.state                전원 → 부팅 디버그 메뉴 「1:Town Part」 → 조작 가능
    python nds/dq4/tools/ndswarp.py preset OUTDIR N [N ...]       프리셋 N 을 적용하고 그 시작 맵에 들어감
    python nds/dq4/tools/ndswarp.py map OUTDIR MAP [MAP ...]      지금 진행도 그대로 맵만 옮김(--x/--z 로 자리)
    python nds/dq4/tools/ndswarp.py field OUTDIR X Z [X Z ...]    필드(세계 지도)의 (X, Z) 칸으로(--state 필요)
    python nds/dq4/tools/ndswarp.py battle OUTDIR M[xN] ...      전투 테스트 Select 모드로 몬스터 M 을 N 마리씩(무리 4개까지, --state 필요)
    python nds/dq4/tools/ndswarp.py chapters OUTDIR               서장·1~6장 시작 세이브스테이트(dq4ds-chN.state)
    python nds/dq4/tools/ndswarp.py screens OUTDIR                맵 전부의 화면 OUTDIR/NNN-<맵>.png 와 README.txt
                                                                  (--state 없으면 프리셋 331 상태를 만들어 씀, --settle 240)

공통 옵션: --state IN(출발 세이브스테이트, 없으면 boot 와 같은 경로로 전원부터), --rom, --fs(풀어 둔 롬),
--core(없으면 $DESMUME_CORE), --after "ndsplay 명령", --no-encounter(도착한 맵의 조우를 끔), --time N(시간대를 정하고 맵에 들어감).
결과마다 OUTDIR/<이름>.state 와 .png 를 남긴다.
"""
import argparse
import ctypes
import os
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ndsplay import Player, core_path  # noqa: E402

SCENE_CUR = 0x021080AC    # 장면 관리자(0x02108048) +0x64: 지금 장면
SCENE_REQ = 0x021080B4    # +0x6C: 다음 장면 요청(-1 이면 없음)
SCENE_DEBUG = 0x01        # 부팅 디버그 메뉴(Town Part / SSA Viewer Part / Message Debug Part)
SCENE_TOWN = 0x0C         # 맵(마을·던전) 장면
SCENE_FIELD = 0x0E        # 필드(세계 지도) 장면
MAP_FLAGS = 0x020CE100    # 지금 맵의 속성 비트. 0x200 이 서 있어야 조우 판정(0x0201C790)을 함
ENCOUNTER_BIT = 0x200
CHAPTER = 0x020EB9A8      # 장 번호(서장 프리셋도 1, 1~6장)
TIME_ZONE = 0x020CE1B4    # 시간대: 0 없음, 1 아침, 2 낮, 3 저녁, 4 밤. 맵을 다시 실을 때 반영됨
HERO_OBJ = 0x020EC4F0     # 주인공 객체 포인터. 필드에서는 [객체+0x70] 이 가리키는 곳이 x, z(s32)
FIELD_TILE = 0x3000       # 필드 한 칸
FIELD_WRAP = 0x1000000    # 필드 좌표는 이 값으로 돌아감(한 바퀴 1365⅓ 칸)
SCENE_BATTLE_TEST = 0x11  # 전투 테스트(Battle Menu Part)
BATTLE_TEST = 0x020C28BC  # 그 객체: +4 모드(0 Encount, 1 Select), +0x20 무리별 몬스터, +0x30 무리별 마릿수
MAP_NAME = 0x020C4F44     # 지금 맵 이름(ASCII)
PRESET = 0x020B970C       # 적용 대기 중인 진행도 프리셋 번호(-1 이면 없음)
HERO_POS = 0x020EC524     # 주인공 x, y, z (s32, 4096 = 1.0)
TILE = 0x1333             # 한 칸(1.2)

SCREENS_PRESET = 331      # 6장, 피사로가 동료. 맵이 가장 많이 열린 진행도
CHAPTERS = [("ch0", 0), ("ch1", 1), ("ch2", 24), ("ch3", 59), ("ch4", 93), ("ch5", 109), ("ch6", 310), ("ch6-psaro", 331)]


def map_names(fs):
    path = os.path.join(fs, "data", "data", "MAP", "_list.txt")
    return [ln.strip().split(",")[2] for ln in open(path, encoding="shift_jis") if ln.count(",") >= 2]


def preset_names(fs):
    path = os.path.join(fs, "data", "data", "DEBUG", "flagshop.dat")
    out = {}
    for ln in open(path, encoding="shift_jis"):
        p = ln.rstrip("\r\n").split(",", 2)
        if len(p) == 3:
            out[int(p[0])] = (int(p[1]), p[2])
    return out


def preset_records(fs):
    """PARAM/param_player_event1~4.dat: 머리 4바이트 + 0x9C 바이트 레코드. +0 프리셋 번호, +0x93 시작 맵 이름."""
    recs = {}
    for k in range(1, 5):
        d = open(os.path.join(fs, "data", "data", "PARAM", f"param_player_event{k}.dat"), "rb").read()
        for o in range(4, len(d) - 0x9B, 0x9C):
            n = struct.unpack_from("<H", d, o)[0]
            if n != 0xFFFF and n not in recs:
                recs[n] = d[o:o + 0x9C]
    return recs


def preset_map(recs, n):
    return recs[n][0x93:0x9C].split(b"\0")[0].decode()


def boot(p):
    """전원을 켜고 부팅 디버그 메뉴의 「1:Town Part」로 맵 장면에 들어간다(이름 ソロ, 맵 caf1)."""
    p.run(300)
    p.w32(SCENE_REQ, SCENE_DEBUG)
    p.run(120)
    p.press("a", 1, 10)
    p.run(300)


def enter(p, name, preset=None, x=None, z=None, settle=300, time=None):
    assert len(name) < 16
    if time is not None:
        p.w32(TIME_ZONE, time)
    if preset is not None:
        p.w32(PRESET, preset)
    p.write(MAP_NAME, name.encode().ljust(16, b"\0"))
    p.w32(SCENE_REQ, SCENE_TOWN)
    p.run(settle)
    if x is not None:
        p.w32(HERO_POS, round(x * TILE))
    if z is not None:
        p.w32(HERO_POS + 8, round(z * TILE))
    if x is not None or z is not None:
        p.run(30)
    got = p.read(MAP_NAME, 16).split(b"\0")[0].decode()
    return got == name and p.u32(SCENE_CUR) == SCENE_TOWN and (preset is None or p.u32(PRESET) == 0xFFFFFFFF)


def no_encounter(p):
    p.w32(MAP_FLAGS, p.u32(MAP_FLAGS) & ~ENCOUNTER_BIT)


def field(p, x, z, settle=300):
    """필드 장면을 요청하고 주인공을 (x, z) 칸에 세운다. 필드 좌표의 원본은 주인공 객체가 가리키는 칸이다."""
    p.w32(SCENE_REQ, SCENE_FIELD)
    p.run(settle)
    pos = p.u32(p.u32(HERO_OBJ) + 0x70)
    rx, rz = round(x * FIELD_TILE) % FIELD_WRAP, round(z * FIELD_TILE) % FIELD_WRAP
    p.w32(pos, rx)
    p.w32(pos + 4, rz)
    p.run(60)
    return p.u32(SCENE_CUR) == SCENE_FIELD and p.u32(HERO_POS) == rx


def battle(p, groups, settle=300):
    """전투 테스트를 열고 Select 모드의 무리 칸을 채운 뒤 A 로 전투를 시작한다. groups: [(몬스터, 마릿수)] 최대 4개."""
    p.w32(SCENE_REQ, SCENE_BATTLE_TEST)
    p.run(100)
    p.press("right", 1, 20)
    for i in range(4):
        m, n = groups[i] if i < len(groups) else (0, 0)
        p.w32(BATTLE_TEST + 0x20 + 4 * i, m)
        p.w32(BATTLE_TEST + 0x30 + 4 * i, n)
    p.run(10)
    p.press("a", 1, 10)
    p.run(settle)
    return p.u32(SCENE_CUR) == 0x0D


def start(p, state):
    p.load(state)
    p.run(2)


def finish(p, out, name, ok, after, noenc=False):
    if noenc:
        no_encounter(p)
    p.script(after)
    p.save(os.path.join(out, name + ".state"))
    p.shot(name)
    if p.u32(SCENE_CUR) == SCENE_FIELD:
        x, z = struct.unpack("<2i", p.read(HERO_POS, 8))
        where = f"field=({x / FIELD_TILE:.2f},{z / FIELD_TILE:.2f})"
    else:
        x, y, z = struct.unpack("<3i", p.read(HERO_POS, 12))
        where = f"map={p.read(MAP_NAME, 16).split(b'\0')[0].decode()}\tpos=({x / TILE:.2f},{y / TILE:.2f},{z / TILE:.2f})"
    print(f"{name}\t{'ok' if ok else 'FAIL'}\tchapter={p.u32(CHAPTER)}\t{where}")


def fixed_clock(p):
    """프레임을 돌리는 동안만 코어의 movieMode 를 MOVIEMODE_FINISHED(3)로 둔다.

    desmume 의 RTC(rtc.cpp rtcGetTime)는 movieMode 가 0 이면 호스트 시계를, 아니면 2009-01-01 + 프레임 수를
    준다. 호스트 시계면 부팅할 때마다 맵 인물의 걸음·물 애니메이션이 달라져 같은 명령이 다른 화면을 낸다.
    세이브스테이트를 쓰고 읽을 때는 0 으로 돌려 둔다. 0 이 아니면 상태에 영상 기록(MOVI)이 붙고 읽기가 거부된다.
    """
    try:
        mode = ctypes.c_int.in_dll(p.core, "movieMode")
    except ValueError:
        print("코어에 movieMode 가 없어 호스트 시계로 돌립니다(화면이 실행마다 다를 수 있음)", file=sys.stderr)
        return
    run = p.run

    def fixed(n=1):
        mode.value = 3
        try:
            run(n)
        finally:
            mode.value = 0
    p.run = fixed


def screens(core, rom, out, fs, state, settle):
    """_list.txt 순서로 맵마다 출발 상태를 다시 읽고 들어가 위·아래 화면을 NNN-<맵>.png 로 저장한다.

    출발 상태에서 맵에 머물지 못한 맵은 부팅 상태에서 한 번 더 들어간다. fk01 은 6장 상태에서
    스크립트가 곧 ckout 으로 넘기지만(debug.md), 부팅 상태에서는 그 맵이 그대로 보인다.
    """
    # 세이브스테이트와 코어가 쓰는 세이브 파일(.dsv)은 OUT 에 두지 않는다. OUT 은 그대로 에셋 저장소로 동기화된다.
    tmp = tempfile.mkdtemp(prefix="ndswarp-")
    os.makedirs(out, exist_ok=True)
    p = Player(core, rom, tmp)
    fixed_clock(p)
    boot_state = os.path.join(tmp, "boot.state")
    boot(p)
    p.save(boot_state)
    if not state:
        start(p, boot_state)
        recs = preset_records(fs)
        if not enter(p, preset_map(recs, SCREENS_PRESET), SCREENS_PRESET):
            raise SystemExit(f"프리셋 {SCREENS_PRESET} 을 적용하지 못했습니다")
        state = os.path.join(tmp, f"preset{SCREENS_PRESET}.state")
        p.save(state)
    names = map_names(fs)
    retried, failed = [], []
    for i, name in enumerate(names):
        start(p, state)
        ok = enter(p, name, settle=settle)
        if not ok:
            start(p, boot_state)
            ok = enter(p, name, settle=settle)
            (retried if ok else failed).append(name)
        p.shot(os.path.abspath(os.path.join(out, f"{i:03d}-{name}.png")))
        print(f"{i:03d}\t{name}\t{'ok' if ok else 'FAIL'}" + ("\tboot" if name in retried else ""), flush=True)
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
        f.write(f"NDS DQ4 맵 화면 {len(names)}장(번호 = data/MAP/_list.txt 순서, 이름 = 맵 이름).\n"
                "위 256x192 = 위 화면, 아래 256x192 = 아래 화면(맵). 맵 기본 자리에 선 주인공.\n"
                "에뮬레이터 시계는 2009-01-01 + 프레임 수로 고정(같은 롬·코어면 실행마다 같은 화면).\n"
                f"진행도는 프리셋 {SCREENS_PRESET}(6장, 피사로가 동료). 맵마다 그 상태를 다시 읽고 맵 이름을 바꿔 "
                f"장면 0x0C 를 요청한 뒤 {settle}프레임 기다려 저장했다.\n"
                f"롬: {os.path.basename(rom)}\n"
                "명령(sfc-dq4 저장소 최상위에서): uv run --locked python nds/dq4/tools/ndswarp.py screens OUT"
                + (f" --settle {settle}" if settle != 240 else "") + "\n"
                "부팅 상태(전원 → 디버그 메뉴 Town Part)에서 다시 들어간 맵: " + (" ".join(retried) or "없음") + "\n"
                "어느 상태에서도 그 맵에 머물지 못한 맵: " + (" ".join(failed) or "없음") + "\n")
    shutil.rmtree(tmp, ignore_errors=True)
    return failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "presets", "boot", "preset", "map", "field", "battle", "chapters",
                                      "screens"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--state")
    ap.add_argument("--rom", default="rom/dq4ds.nds")
    ap.add_argument("--fs", default="work/nds/jp", help="krpatch nds unpack 으로 푼 일본판 롬")
    ap.add_argument("--core")
    ap.add_argument("--x", type=float, help="맵이 실린 뒤 주인공 x(칸)")
    ap.add_argument("--z", type=float, help="맵이 실린 뒤 주인공 z(칸)")
    ap.add_argument("--after", default="", help="끝에 실행할 ndsplay 명령(; 로 나눔)")
    ap.add_argument("--settle", type=int, help="맵을 요청하고 기다릴 프레임(기본 300, screens 는 240)")
    ap.add_argument("--time", type=int, choices=range(5), help="시간대(0 없음, 1 아침, 2 낮, 3 저녁, 4 밤)")
    ap.add_argument("--no-encounter", action="store_true", help="도착한 맵의 조우 비트(0x020CE100 의 0x200)를 지움")
    a = ap.parse_args()

    if a.cmd == "list":
        for i, n in enumerate(map_names(a.fs)):
            if not a.args or n.startswith(a.args[0]):
                print(f"{i:3d} {n}")
        return
    if a.cmd == "presets":
        recs = preset_records(a.fs)
        for n, (grp, title) in sorted(preset_names(a.fs).items()):
            if not a.args or a.args[0] in title:
                print(f"{n:3d} {grp:2d} {preset_map(recs, n) if n in recs else '-':8s} {title}")
        return

    out = os.path.dirname(a.args[0]) or "." if a.cmd == "boot" else a.args[0]
    if a.cmd == "screens":
        failed = screens(core_path(a.core), a.rom, out, a.fs, a.state, a.settle or 240)
        if failed:
            raise SystemExit("머물지 못한 맵: " + " ".join(failed))
        return
    p = Player(core_path(a.core), a.rom, out)
    if a.cmd == "boot":
        boot(p)
        p.script(a.after)
        p.save(a.args[0])
        p.shot(os.path.abspath(os.path.splitext(a.args[0])[0] + ".png"))
        print(f"boot\tmap={p.read(MAP_NAME, 16).split(b'\0')[0].decode()}\tscene={p.u32(SCENE_CUR):#x}")
        return
    if a.settle is None:
        a.settle = 300
    if a.cmd in ("field", "battle") and not a.state:
        raise SystemExit(f"{a.cmd} 는 일행이 있는 상태(--state)가 필요합니다")
    state = a.state
    if not state:
        # 작업마다 같은 출발점에서 시작해야 한다. 앞 작업의 장면·진행도가 남으면 다음 맵이 검게 실린다.
        boot(p)
        state = os.path.join(out, "_boot.state")
        p.save(state)
    if a.cmd == "map":
        for name in a.args[1:]:
            start(p, state)
            ok = enter(p, name, None, a.x, a.z, a.settle, a.time)
            finish(p, out, name, ok, a.after, a.no_encounter)
    elif a.cmd == "battle":
        groups = [tuple(int(v) for v in (g.split("x") + ["1"])[:2]) for g in a.args[1:5]]
        start(p, state)
        ok = battle(p, groups, a.settle)
        finish(p, out, "battle_" + "_".join(f"{m}x{n}" for m, n in groups), ok, a.after)
    elif a.cmd == "field":
        xs = [float(v) for v in a.args[1:]]
        for x, z in zip(xs[0::2], xs[1::2]):
            start(p, state)
            ok = field(p, x, z, a.settle)
            finish(p, out, f"field_{x:g}_{z:g}", ok, a.after, a.no_encounter)
    else:
        recs = preset_records(a.fs)
        jobs = CHAPTERS if a.cmd == "chapters" else [(f"preset{int(n):03d}", int(n)) for n in a.args[1:]]
        for name, n in jobs:
            start(p, state)
            ok = enter(p, preset_map(recs, n), n, a.x, a.z, a.settle, a.time)
            finish(p, out, ("dq4ds-" + name) if a.cmd == "chapters" else name, ok, a.after, a.no_encounter)


if __name__ == "__main__":
    main()
