"""DQ5(SFC) 전투 주문·특기 연출을 MesenCE 로 띄워 GIF 로 남긴다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 「전투 주문·특기 연출」.

슬라임 셋 이벤트 전투(sfc/dq5/journal/2026-10-25-10-spell.md 의 틀)에서 행동 번호 n 을
  n < 39: 손님 파파스의 행동 여섯 칸(파일 오프셋 11958D)에, n ≥ 39: 슬라임의 행동 여섯 칸(118011)에 넣고
1차로 전투 메시지 프레임(dq5battle.lua 의 battle.txt)을 얻은 뒤, 그 행동의 메시지부터 다음 메시지까지를
2차로 STEP 프레임마다 찍어(dq5shots.lua) GIF 로 묶는다. 연출의 움직임은 22:D8FE 의 스크립트와 그것이 부르는
네이티브 루틴이 정하는데, 네이티브가 몬스터 배치를 읽어 롬만으로는 재현되지 않으므로 게임을 그대로 돌린다.

  uv run --locked python sfc/dq5/tools/dq5effectgif.py rom/dq5.sfc --state work/state/ship.mss --out $OUT [--only 01,8E]
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from dq5gfx import EFFECT_COUNT, Out, effect_lists  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5spell import name  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
PRE = 'b:4,wait:40,b:4,wait:40'
WAYPOINTS = '3,11;3,24;7,24;7,22;37,66;37,72;down:90'
BASE_PATCH = '156FF5=E0253C0103;118003=C8'
PAPAS_ACTIONS, SLIME_ACTIONS = 0x11958D, 0x118011
MIN_CHANGE = 2000
# 화면 버퍼 239줄 기준 몬스터 줄(MesenCE 224줄 화면의 y 40~150 에 해당)
MONSTER_BAND = (0, 48, 256, 158)
COMMAND = 'uv run --locked python sfc/dq5/tools/dq5effectgif.py rom/dq5.sfc --state work/state/ship.mss --out $OUT'


def raw_image(path):
    """lua/dq5shots.lua 의 sNNNNN.raw(32비트 ARGB) → RGB 그림. 크기는 같은 폴더의 size.txt."""
    w, h = (int(v) for v in open(os.path.join(os.path.dirname(path), 'size.txt')).read().split())
    return Image.frombytes('RGBA', (w, h), open(path, 'rb').read(), 'raw', 'BGRA').convert('RGB')


def driver_dir(root):
    """dq5battle.lua 를 boot.lua 로 둔 LIBDIR(프로브가 끝에서 부르는 드라이버)."""
    lib = subprocess.run(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                         check=True).stdout.strip()
    os.makedirs(root, exist_ok=True)
    shutil.copy(os.path.join(lib, 'lib.lua'), os.path.join(root, 'lib.lua'))
    shutil.copy(os.path.join(TOOLS, 'lua', 'dq5battle.lua'), os.path.join(root, 'boot.lua'))
    return root


def run(mesen, rom_path, script, env, shot_dir):
    os.makedirs(shot_dir, exist_ok=True)
    # 설정의 Snes.RamPowerOnState 가 Random 이면 같은 입력도 결과가 달라져, 이 실행만 RAM 을 0 으로 켠다(인자는 롬·스크립트 뒤에 두어야 먹음).
    # 프레임 건너뛰기를 끄지 않으면 빠르게 돌 때 PPU 가 몇 프레임을 그리지 않아, 화면 버퍼가 시간에 따라 1~3프레임 앞의 그림으로 남는다.
    subprocess.run([mesen, '--testrunner', rom_path, script, '--Snes.RamPowerOnState=AllZeros',
                    '--Snes.DisableFrameSkipping=true'], env=dict(os.environ, SHOT_DIR=shot_dir, **env),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)


def window(log, papas):
    """battle.txt → (첫 프레임, 끝 프레임). 파파스는 첫 「となえた」(070), 슬라임은 주인공 첫 공격 피해(069) 다음 메시지부터."""
    msgs = [(int(f[1:]), m) for f, _, m in (line.split()[:3] for line in log if line.startswith('f'))]
    if papas:
        k = next((i for i, (f, m) in enumerate(msgs) if f >= 1990 and m == '070'), None)
    else:
        k = next((i + 1 for i, (f, m) in enumerate(msgs) if m == '069'), None)
    if k is None or k + 1 >= len(msgs):
        return None
    return msgs[k][0], msgs[k + 1][0] + 10


def capture(args, n, work):
    papas = n < 0x39
    patch = f'{BASE_PATCH};{PAPAS_ACTIONS if papas else SLIME_ACTIONS:06X}={f"{n:02X}" * 6}'
    env = dict(LIBDIR=work['lib'], STATE=os.path.abspath(args.state), PRE=PRE, WAYPOINTS=WAYPOINTS, ROMPATCH=patch,
               MAXF='2400' if papas else '1500')
    d = os.path.join(work['tmp'], f'{n:02X}')
    run(args.mesen, args.rom, os.path.join(TOOLS, 'lua', 'dq5battle.lua'), env, os.path.join(d, 'log'))
    with open(os.path.join(d, 'log', 'battle.txt')) as f:
        win = window(f.readlines(), papas)
    if not win:
        return n, None
    env.update(FROM=str(win[0]), TO=str(win[1]), STEP=str(args.step), MAXF=str(win[1] + 1))
    run(args.mesen, args.rom, os.path.join(TOOLS, 'lua', 'dq5shots.lua'), env, os.path.join(d, 'shots'))
    return n, (win, sorted(glob.glob(os.path.join(d, 'shots', 's*.raw'))))


def changed(paths):
    """몬스터 줄(MONSTER_BAND)에서 첫 장과 가장 많이 다른 점 수. 물결 배경과 글자만 바뀌면 1,700 아래였다."""
    from PIL import ImageChops
    first = raw_image(paths[0]).crop(MONSTER_BAND)
    return max(ImageChops.difference(first, raw_image(p).crop(MONSTER_BAND))
               .convert('L').point(lambda v: 255 if v > 16 else 0).histogram()[255] for p in paths)


def gif(paths, step):
    frames, durs = [], []
    for p in paths:
        img = raw_image(p)
        if frames and img.tobytes() == frames[-1].tobytes():
            durs[-1] += step
            continue
        frames.append(img)
        durs.append(step)
    return frames, [round(d * 1000 / 60) for d in durs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--state', required=True, help='배 선실 세이브스테이트(work/state/ship.mss)')
    ap.add_argument('--out', default='work/dq5gfx')
    ap.add_argument('--only', help='쉼표로 행동 번호(16진)')
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--mesen', default=os.path.expandvars('$MESENCE'))
    args = ap.parse_args()
    data = open(args.rom, 'rb').read()
    rom = Rom(data)
    todo = [int(x, 16) for x in args.only.split(',')] if args.only else \
        [n for n in range(EFFECT_COUNT) if effect_lists(rom, n)]
    tmp = tempfile.mkdtemp(prefix='dq5effect-')
    work = dict(tmp=tmp, lib=driver_dir(os.path.join(tmp, 'lib')))
    import hashlib
    out = Out(args.out, hashlib.sha1(data).hexdigest())
    with ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(lambda n: capture(args, n, work), todo))
    for n, got in results:
        title = name(rom, n)
        if not got or not got[1]:
            print(f'{n:02X} {title}: 연출을 띄우지 못함')
            continue
        (start, end), paths = got
        moved = changed(paths)
        if moved < MIN_CHANGE:
            print(f'{n:02X} {title}: 몬스터 줄에 연출이 드러나지 않음({moved}점)')
            continue
        frames, durs = gif(paths, args.step)
        stem = f'{n:02X}-{title}' if title else f'{n:02X}'
        path = os.path.join(args.out, 'gfx', 'effects', 'anim', f'{stem}.gif')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0)
        out.add(f'gfx/effects/anim/{stem}.gif', 'effects', f'{n:02X} {title} (GIF)', '전투 연출', action=f'{n:02X}',
                frames=len(frames), w=frames[0].width, h=frames[0].height, start=start, end=end,
                note=('파파스가' if n < 0x39 else '슬라임이') + f' 쓴 장면, 메시지 프레임 {start}~{end - 10}')
        print(f'{n:02X} {title}: {len(frames)}장 {start}~{end}')
    out.finish(COMMAND)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
