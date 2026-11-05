"""흔들림 없는 장면 몇 개의 화면을 기준(sfc/dq4/screens.toml)과 칸 해시로 견준다. 형식은
sfc/dq4/docs/dq4-screen-baseline-format.md.

MesenCE(헤드리스, 화면은 emu.getScreenBuffer):
  title       전원을 켜고 TITLE_FRAME 프레임째의 타이틀
  start-room  1장 시작 방(서장 시작 상태 start.mss 에서 열린 명령 창을 닫은 뒤)
  status      같은 자리에서 명령 → 상태 → 상태 보기 창
  shop-list   이무르 방어구점 카운터 앞(서장 끝 상태에서 순간이동)에서 사기 목록 창
libretro(bsnes·snes9x, 화면은 코어가 넘긴 프레임. 코어 옵션은 dq4cores 가 고정한 커밋의 기본값):
  title       전원을 켜고 TITLE_FRAME 프레임째의 타이틀
MesenCE 설정 확인(settings): dq4screens.VERIFY_ARGS 를 하나씩 더해 타이틀을 다시 찍어, 화면이 기준과 달라지는지 본다.
달라지지 않으면 그 설정 이름을 MesenCE 가 받지 않은 것이라(틀린 이름·값은 아무 말 없이 무시됨) SCREEN_ARGS 도 먹지
않았을 수 있다. 장면마다 넘긴 명령줄은 <출력>/<장면>-mesence/args.txt 에 남긴다.

장면은 전원(RamPowerOnState=AllZeros)이나 같은 롬으로 만든 출발 상태에서 정한 입력만 넣으므로 난수·시각·조우가 늘 같다.
화면이 다르면 다른 칸을 빨갛게 그린 차이 그림을 out 에 남긴다.

  uv run --locked python sfc/dq4/tools/dq4screencheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/screens
  … --write-screens "까닭"     지금 화면으로 기준을 고친다(바뀐 장면에만 그 까닭이 남음)
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4mesen as mesen  # noqa: E402
import dq4readset as rs  # noqa: E402
import dq4screens as sc  # noqa: E402

TITLE_FRAME = 1300
# 서장 시작 상태는 명령 창이 열린 채로 남는다. B 로 닫고 기다린다
CLOSE = 'wait:20,b:6,wait:60'
STATUS = CLOSE + ',a:8,wait:40,down:6,wait:20,a:8,wait:60,down:6,wait:15,down:6,wait:15,a:8,wait:120'
# 카운터 앞에서 위를 보고 말을 걸어 방어구점 주인 말을 넘기고 「사기」 를 고른다
SHOP = 'wait:30,up:6,wait:30,a:4,wait:30,a:4,wait:90,a:4,wait:60,a:4,wait:60,a:4,wait:80'
SHOP_STATE = ('shop', '37/00,34,8', '05')
# (장면, 출발 상태 이름(None 이면 전원), 입력, 찍을 프레임, 가림, 허용 칸 수)
MESEN_SCENES = (
    ('title', None, '', TITLE_FRAME, (), 0),
    ('start-room', 'start', CLOSE, 80, (), 0),
    ('status', 'start', STATUS, 330, (), 0),
    ('shop-list', 'shop', SHOP, 420, (), 0),
)
LIBRETRO_SCENES = (('title', TITLE_FRAME, (), 0),)


def make_states(mesence, rom, out, need):
    """{이름: 세이브스테이트}. 검사 롬으로 그때 만든다(start 는 전원부터, shop 은 서장 끝 상태 캐시에서 순간이동)."""
    import dq4ch1walkcheck as walk
    states = {}
    if 'start' in need:
        states['start'] = walk.prologue_start(mesence, rom, out / 'states')
    if 'shop' in need:
        data = rom.read_bytes()
        base, r = walk.prologue(mesence, rom, data, out / 'states' / 'prologue', walk.SEGMENTS, walk.StateCache(data),
                                readset=True)
        if r['status'] != 'passed':
            raise SystemExit(f'서장 끝 상태를 만들지 못함: {r["problems"]}')
        name, to, party = SHOP_STATE
        r = walk.segment(mesence, rom, base, out / 'states' / name, (name, 'warp', to, {'map': to[:5]}),
                         walk.NO_ENCOUNTERS, '', party, readset=True)
        if r['status'] != 'passed':
            raise SystemExit(f'출발 상태 {name}({to})를 만들지 못함: {r["problems"]}')
        states['shop'] = out / 'states' / name / 'end.mss'
    return states


def mesen_screen(mesence, rom, dest, state, pre, frame, extra=()):
    """MesenCE 로 장면을 돌려 그 프레임의 화면. 사용자 영상 설정과 상관없게 SCREEN_ARGS 로 고정한다."""
    dest.mkdir(parents=True)
    args = (*mesen.ARGS, *rs.FIXED_ARGS, *sc.SCREEN_ARGS, *extra)
    (dest / 'args.txt').write_text('\n'.join(args) + '\n', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k not in ('STATE', 'PRE', 'SET', 'POKE')}
    env.update(SHOT_DIR=str(dest), PRE=pre, SCREENS=str(frame), PNGS=str(frame))
    if state:
        env['STATE'] = str(state)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        mesen.run(mesence, rom, sc.LUA, cwd=dest, env=env, extra=args, stdout=log, stderr=subprocess.STDOUT, timeout=300,
                  check=False)
    path = dest / f'screen-{frame:05d}.rgb'
    if not path.exists():
        raise SystemExit(f'{dest}: 화면을 찍지 못함(mesen.log)')
    return sc.read_rgb(path)


def libretro_screen(core_name, rom, dest, frame):
    import dq4cores
    import dq4libretro
    dest.mkdir(parents=True)
    core = dq4libretro.Core(str(dq4cores.core_path(core_name)), str(rom), str(dest / 'sys'))
    try:
        for _ in range(frame):
            core.run(())
        return core.frame
    finally:
        core.close()


def verify_args(mesence, rom, out, title):
    """VERIFY_ARGS 마다 타이틀을 다시 찍어 화면이 달라지는지. 달라지지 않은 인자 목록."""
    base = sc.digest(title)
    stuck = []
    for i, arg in enumerate(sc.VERIFY_ARGS):
        img = mesen_screen(mesence, rom, out / f'settings-{i:02d}', None, '', TITLE_FRAME, (arg,))
        if img.shape == title.shape and sc.digest(img) == base:
            stuck.append(arg)
    return stuck


def scenes_for(only, no_libretro):
    """(MesenCE 장면, libretro 장면). only 에 모르는 이름이 있으면 ValueError."""
    known = {s[0] for s in MESEN_SCENES} | {s[0] for s in LIBRETRO_SCENES}
    if only:
        bad = sorted(only - known)
        if bad:
            raise ValueError(f'모르는 장면 {bad}(있는 것: {", ".join(sorted(known))})')
    mscenes = [s for s in MESEN_SCENES if not only or s[0] in only]
    lscenes = [] if no_libretro else [s for s in LIBRETRO_SCENES if not only or s[0] in only]
    return mscenes, lscenes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--only', help='이 장면만(쉼표로 여럿)')
    ap.add_argument('--no-libretro', action='store_true', help='MesenCE 장면만')
    ap.add_argument('--write-screens', metavar='까닭', help='지금 화면으로 기준(sfc/dq4/screens.toml)을 고친다')
    a = ap.parse_args()
    if a.write_screens is not None and not a.write_screens.strip():
        ap.error('--write-screens 에 까닭을 주세요(빈 글·공백뿐은 안 됨)')
    only = set(a.only.split(',')) if a.only else None
    out = a.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rom = out / 'c.sfc'
    shutil.copyfile(a.rom.resolve(), rom)
    mesence = Path(os.environ['MESENCE'])
    try:
        mscenes, lscenes = scenes_for(only, a.no_libretro)
    except ValueError as e:
        ap.error(str(e))
    states = make_states(mesence, rom, out, {s[1] for s in mscenes if s[1]})
    shots = []
    for scene, state, pre, frame, masks, tol in mscenes:
        img = mesen_screen(mesence, rom, out / f'{scene}-mesence', states.get(state), pre, frame)
        shots.append((scene, 'mesence', img, masks, tol))
    for scene, frame, masks, tol in lscenes:
        for core in ('bsnes', 'snes9x'):
            shots.append((scene, core, libretro_screen(core, rom, out / f'{scene}-{core}', frame), masks, tol))
    if a.write_screens is not None:
        sc.write_baselines([(s, e, img, m, t) for s, e, img, m, t in shots], a.write_screens)
    baselines = sc.load_baselines()
    results = []
    for scene, emulator, img, masks, tol in shots:
        r = sc.check_screen(img, scene, emulator, out, masks, tol, baselines)
        res = {'name': f'{scene}-{emulator}', **{k: v for k, v in r.items() if k != 'tiles'}, 'tiles': len(r['tiles'])}
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    title = next((img for s, e, img, _, _ in shots if (s, e) == ('title', 'mesence')), None)
    if title is not None and not only:
        stuck = verify_args(mesence, rom, out, title)
        res = {'name': 'settings', 'status': 'failed' if stuck else 'passed',
               'problems': [f'{arg} 로 화면이 바뀌지 않음(MesenCE 가 이 설정 이름을 받지 않음)' for arg in stuck]}
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    # 고른 장면이 하나도 돌지 않았으면(장면 목록이 비는 등) 통과로 치지 않는다
    want = len(mscenes) + 2 * len(lscenes)
    ok = len(shots) == want > 0 and all(r['status'] == 'passed' for r in results)
    print(json.dumps({'status': 'passed' if ok else 'failed'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
