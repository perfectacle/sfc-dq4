"""DQ5(SFC) 오프닝 타이틀(로고·성·V·링)을 MesenCE 로 전원부터 띄워 GIF 로 남긴다.

빈 SRAM 으로 전원을 켜고 모험의 서를 새로 만든 뒤 태어나는 장면을 A 로 넘기면 5,000프레임 무렵 타이틀이 나온다. 그 앞뒤를 STEP 프레임마다 찍고(lua/dq5shots.lua), 타이틀 앞의 검은 화면이 끝난
곳부터 다시 검어지는 곳까지를 묶는다. 연출을 정하는 것은 02:E69F 의 순서(sfc/dq5/docs/dq5-graphics-format.md
「오프닝 타이틀 로고」)인데, 팔레트 밝히기(03:A5CE)와 줄마다 바뀌는 스크롤(HDMA)이 프레임마다 얽혀 게임을 그대로 돌린다.

  uv run --locked python sfc/dq5/tools/dq5titlegif.py rom/dq5.sfc --out $OUT
"""
import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageStat

sys.path.insert(0, os.path.dirname(__file__))
from dq5gfx import Out  # noqa: E402

TOOLS = os.path.dirname(os.path.abspath(__file__))
COMMAND = 'uv run --locked python sfc/dq5/tools/dq5titlegif.py rom/dq5.sfc --out $OUT'
# 전원부터의 입력(boot.lua 의 SEQ). 205프레임까지는 40프레임마다 A(PERIOD·TAPUNTIL).
# 빈 SRAM 의 모험의 서 메뉴(つくる 하나)에서 つくる → 1번 칸 → 이름 넣기(あ, START, おわり) → 말 빠르기 → 소리,
# 그 뒤로 40프레임마다 A. SRAM 에 모험의 서가 있으면 메뉴가 달라 입력이 어긋나므로 롬을 시험용 이름으로 복사하고
# 그 이름의 SRAM 파일을 지우고 돌린다(dq5boottest.py 와 같은 방법).
MENU = ['a@331:4', 'a@411:4', 'a@535:4', 'start@569:4', 'a@603:4',
        'up@1199:4', 'left@1213:4', 'a@1237:4', 'a@1391:4', 'a@1545:4', 'a@1699:4']
TAPS = [f'a@{1439 + 40 * k}:4' for k in range(241)]
FROM, TO = 4800, 6800
SAVES = os.environ.get('MESENCE_SAVES') or os.path.join(os.path.expanduser('~'), 'Library', 'Application Support',
                                                        'MesenCE', 'Saves')
TEST_ROM = 'dq5titlegif.sfc'


def raw_image(path):
    """lua/dq5shots.lua 의 sNNNNN.raw(32비트 ARGB) → RGB 그림. 크기는 같은 폴더의 size.txt."""
    w, h = (int(v) for v in open(os.path.join(os.path.dirname(path), 'size.txt')).read().split())
    return Image.frombytes('RGBA', (w, h), open(path, 'rb').read(), 'raw', 'BGRA').convert('RGB')


def dark(path):
    return sum(ImageStat.Stat(raw_image(path).convert('L')).mean) < 1.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/dq5gfx')
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--mesen', default=os.path.expandvars('$MESENCE'))
    args = ap.parse_args()
    data = open(args.rom, 'rb').read()
    lib = subprocess.run(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                         check=True).stdout.strip()
    shots = tempfile.mkdtemp(prefix='dq5title-')
    rom_path = os.path.join(shots, TEST_ROM)
    shutil.copy(args.rom, rom_path)
    srm = os.path.join(SAVES, os.path.splitext(TEST_ROM)[0] + '.srm')
    if os.path.exists(srm):
        os.remove(srm)
    env = dict(os.environ, LIBDIR=lib, PERIOD='40', TAP='a', TAPUNTIL='205', SEQ=','.join(MENU + TAPS), EVERY='0',
               FROM=str(FROM), TO=str(TO), STEP=str(args.step), MAXF=str(TO + 1), SHOT_DIR=shots)
    # 설정의 Snes.RamPowerOnState 가 Random 이면 같은 입력도 결과가 달라져, 이 실행만 RAM 을 0 으로 켠다(인자는 롬·스크립트 뒤에 두어야 먹음).
    subprocess.run([args.mesen, '--testrunner', rom_path, os.path.join(TOOLS, 'lua', 'dq5shots.lua'),
                    '--Snes.RamPowerOnState=AllZeros'], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800, check=False)
    paths = sorted(glob.glob(os.path.join(shots, 's*.raw')))
    flags = [dark(p) for p in paths]
    start = next(i for i in range(1, len(paths)) if flags[i - 1] and not flags[i])
    end = next(i for i in range(start, len(paths)) if flags[i])
    frames, durs = [], []
    for p in paths[start:end]:
        img = raw_image(p)
        if frames and img.tobytes() == frames[-1].tobytes():
            durs[-1] += args.step
            continue
        frames.append(img)
        durs.append(args.step)
    rel = 'gfx/screens/anim/title-opening.gif'
    path = os.path.join(args.out, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[round(d * 1000 / 60) for d in durs],
                   loop=0)
    first = int(os.path.basename(paths[start])[1:6])
    last = int(os.path.basename(paths[end - 1])[1:6])
    out = Out(args.out, hashlib.sha1(data).hexdigest())
    out.add(rel, 'screens', '오프닝 타이틀 연출 (GIF)', '타이틀', w=frames[0].width, h=frames[0].height, frames=len(frames), start=first, end=last,
            note=f'전원부터 {first}~{last} 프레임을 {args.step}프레임마다 찍음(같은 장은 한 장으로)')
    out.finish(COMMAND)
    print(f'{len(frames)}장 {first}~{last} -> {path}')


if __name__ == '__main__':
    main()
