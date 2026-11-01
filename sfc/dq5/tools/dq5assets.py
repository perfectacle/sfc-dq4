"""DQ5(SFC) 에셋 전부를 롬 하나로 다시 뽑는다. 결과는 비공개 에셋 저장소 sfc-dq4-assets 의 sfc/dq5/ 와 같은 꼴이다.

세이브스테이트를 받지 않는다. MesenCE 가 필요한 단계(sound·effects·fxframes·motion)는 전원을 켜 새 게임 첫 장면(배 선실
17/00)까지 가서 만든 세이브스테이트(lua/dq5shipstate.lua)에서 출발한다. 같은 결과가 나오게 MesenCE 를 감싼 셸 스크립트를
--work 에 만들어 결과를 바꾸는 설정을 모두 인자로 고정하고(PINNED), 전원부터 켤 때는 그 롬 이름의 SRAM 파일을 지운다.

  uv run --locked python sfc/dq5/tools/dq5assets.py rom/dq5.sfc --out $OUT [--only sound,motion] [--work DIR]

단계(--only, 쉼표로. 빼면 모두. 이 차례로 돈다):
  sprites    sprites/                       dq5sprite.py
  samples    sound/samples/                 dq5brr.py
  sound      sound/songs/·sfx/ (.spc·.wav)   dq5spcfile.py --wav       MesenCE, GME_LIB
  score      sound/songs/·sfx/ (.txt·.mid·.musicxml·쪽별 .svg, index.json 의 score)   dq5score.py
  effects    gfx/effects/anim/              dq5effectgif.py           MesenCE
  fxframes   gfx/effects/frames/            dq5scenes.py 덤프 → dq5fx.py --export   MesenCE
  title      gfx/screens/anim/              dq5titlegif.py            MesenCE
  titlevm    gfx/screens/anim/title-opening-rom.gif   dq5titlevm.py(스냅숏만 MesenCE, 나머지는 롬 코드)   MesenCE
  motion     monsters/motion/               dq5monmotion.py, dq5scenes.py 장면    MesenCE
  soundpage  gallery/sound.html             dq5soundpage.py
  gallery    maps/ field/ monsters/ battlebg/ gfx/… 와 gallery/index.html·sprites.html   dq5gallery.py
gallery 는 --out 에 있는 다른 단계 결과를 링크하므로 마지막에 돈다.
환경 변수: MESENCE(MesenCE 실행 파일), GME_LIB(libgme, sound 의 WAV), MESENCE_SAVES(MesenCE 의 Saves 폴더,
기본 macOS 설정 폴더). 결과는 롬에서 나온 자료라 공개 저장소에 커밋하지 않는다.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import dq5gfx  # noqa: E402
import dq5mesen  # noqa: E402

# 결과를 바꾸는 MesenCE 설정. 사용자 설정 파일과 상관없이 같게 한다.
#   SpcClockSpeedAdjustment 는 SPC700 빠르기라 .spc 의 SPC 레지스터·RAM 이 달라진다(0 과 40 이 다름을 실측).
#   RamPowerOnState 가 Random 이면 전원을 켤 때마다 WRAM·SPC RAM 의 빈 곳이 달라진다.
#   DisableFrameSkipping 을 끄면 화면 버퍼가 시간에 따라 1~3프레임 앞의 그림으로 남는다.
PINNED = ['--Snes.RamPowerOnState=AllZeros', '--Snes.EnableRandomPowerOnState=false',
          '--Snes.DisableFrameSkipping=true', '--Snes.SpcClockSpeedAdjustment=40', '--Snes.Region=Ntsc',
          '--Snes.PpuExtraScanlinesBeforeNmi=0', '--Snes.PpuExtraScanlinesAfterNmi=0',
          '--Emulation.RunAheadFrames=0']
SAVES = os.environ.get('MESENCE_SAVES') or os.path.join(os.path.expanduser('~'), 'Library', 'Application Support',
                                                        'MesenCE', 'Saves')
SHIP_AT = 6800            # 전원부터 A 를 40프레임마다 누르면 6,500프레임 무렵 선실 장면이 끝나 조작할 수 있다(21A1 = 71)
STEPS = ['sprites', 'samples', 'sound', 'score', 'effects', 'fxframes', 'title', 'titlevm', 'motion', 'soundpage', 'gallery']
MESEN_STEPS = {'sound', 'effects', 'fxframes', 'title', 'titlevm', 'motion'}
SHIP_STEPS = {'sound', 'effects', 'fxframes', 'motion'}
FOLDERS = {
    'sprites': ['sprites'],
    'samples': ['sound/samples'],
    'sound': ['sound/songs', 'sound/sfx'],
    'score': ['sound/songs', 'sound/sfx'],
    'effects': ['gfx/effects/anim'],
    'fxframes': ['gfx/effects/frames'],
    'title': ['gfx/screens/anim'],
    'titlevm': ['gfx/screens/anim'],
    'motion': ['monsters/motion'],
}


def py(*args, env=None):
    cmd = ['uv', 'run', '--locked', 'python', *args]
    print('$', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def pinned_mesence(work, real):
    """MesenCE 를 PINNED 인자와 함께 부르는 셸 스크립트. 도구들은 환경 변수 MESENCE 로 이것을 부른다."""
    path = os.path.join(work, 'mesence.sh')
    with open(path, 'w') as f:
        f.write('#!/bin/sh\nexec "$DQ5ASSETS_MESENCE" "$@" ' + ' '.join(PINNED) + '\n')
    os.chmod(path, 0o755)
    return path, dict(os.environ, MESENCE=path, DQ5ASSETS_MESENCE=real)


def ship_state(rom, work, env):
    """전원부터 배 선실 세이브스테이트를 만든다. 롬을 시험용 이름으로 복사하고 그 이름의 SRAM 파일을 지워 빈 SRAM 으로 켠다."""
    out = os.path.join(work, 'ship')
    os.makedirs(out, exist_ok=True)
    # MesenCE 는 SRAM 을 롬 파일 이름으로 Saves 폴더에 둔다. 다른 체크아웃에서 함께 돌려도 겹치지 않게 --work 로 이름을 가른다.
    name = f'dq5assets-ship-{hashlib.sha1(work.encode()).hexdigest()[:8]}'
    rom_path = os.path.join(out, name + '.sfc')
    shutil.copyfile(rom, rom_path)
    srm = os.path.join(SAVES, name + '.srm')
    if os.path.exists(srm):
        os.remove(srm)
    lib = subprocess.run(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                         check=True).stdout.strip()
    dq5mesen.testrunner(env['MESENCE'], rom_path, os.path.join(TOOLS, 'lua', 'dq5shipstate.lua'),
                        env=dict(env, LIBDIR=lib, SHOT_DIR=out, SAVEAT=str(SHIP_AT), SAVE='ship.mss'),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600, check=False)
    if os.path.exists(srm):
        os.remove(srm)
    log = open(os.path.join(out, 'ship.txt')).read() if os.path.exists(os.path.join(out, 'ship.txt')) else ''
    if 'save map 17/00 21A1=71' not in log or not os.path.exists(os.path.join(out, 'ship.mss')):
        raise RuntimeError(f'배 선실 세이브스테이트를 만들지 못함: {log.strip() or "(ship.txt 없음)"}')
    print(f'배 선실 세이브스테이트: {os.path.join(out, "ship.mss")}', flush=True)
    return os.path.join(out, 'ship.mss')


def write_sources(out, step, rom_sha):
    for d in FOLDERS.get(step, []):
        owners = ','.join(s for s in STEPS if d in FOLDERS.get(s, []))
        command = f'uv run --locked python sfc/dq5/tools/dq5assets.py rom/dq5.sfc --out $OUT --only {owners}'
        folder = os.path.join(out, d)
        if os.path.isdir(folder):
            with open(os.path.join(folder, 'SOURCE.txt'), 'w') as f:
                f.write(dq5gfx.source_text(command, rom_sha))


def run_step(step, rom, out, work, ship, env, jobs):
    t = os.path.join(TOOLS, '')
    if step == 'sprites':
        py(t + 'dq5sprite.py', rom, '--out', os.path.join(out, 'sprites'), env=env)
    elif step == 'samples':
        py(t + 'dq5brr.py', rom, '--out', os.path.join(out, 'sound', 'samples'), env=env)
    elif step == 'sound':
        py(t + 'dq5spcfile.py', rom, ship, '--out', os.path.join(out, 'sound'), '--wav', '--jobs', str(jobs),
           '--work', os.path.join(work, 'spc'), env=env)
    elif step == 'score':
        py(t + 'dq5score.py', rom, '--out', os.path.join(out, 'sound'), '--jobs', str(jobs), env=env)
    elif step == 'effects':
        py(t + 'dq5effectgif.py', rom, '--state', ship, '--out', out, '--jobs', str(jobs), env=env)
    elif step == 'fxframes':
        dumps = os.path.join(work, 'fx')
        py(t + 'dq5scenes.py', rom, ship, '--fx-dumps', dumps, '--jobs', str(jobs), env=env)
        py(t + 'dq5fx.py', rom, '--export', os.path.join(out, 'gfx', 'effects', 'frames'),
           *[os.path.join(dumps, k) for k in ('h', 'm', 'm2', 'p')], env=env)
    elif step == 'title':
        py(t + 'dq5titlegif.py', rom, '--out', out, env=env)
    elif step == 'titlevm':
        py(t + 'dq5titlevm.py', rom, '--out', out, env=env)
    elif step == 'motion':
        py(t + 'dq5scenes.py', rom, ship, '--motion', os.path.join(out, 'monsters', 'motion'),
           '--work', os.path.join(work, 'motion'), '--jobs', str(jobs), env=env)
    elif step == 'soundpage':
        py(t + 'dq5soundpage.py', '--root', out, env=env)
    elif step == 'gallery':
        py(t + 'dq5gallery.py', rom, '--out', out, env=env)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--out', required=True, help='에셋 저장소의 sfc/dq5 에 해당하는 폴더')
    ap.add_argument('--only', help='쉼표로 단계: ' + ','.join(STEPS))
    ap.add_argument('--work', default='work/dq5assets', help='세이브스테이트·덤프 같은 중간물을 둘 곳')
    ap.add_argument('--jobs', type=int, default=6, help='MesenCE 를 함께 돌릴 수')
    a = ap.parse_args()
    steps = [s for s in STEPS if not a.only or s in a.only.split(',')]
    unknown = set(a.only.split(',')) - set(STEPS) if a.only else set()
    if unknown:
        print(f'모르는 단계: {",".join(sorted(unknown))}', file=sys.stderr)
        return 1
    rom, out, work = os.path.abspath(a.rom), os.path.abspath(a.out), os.path.abspath(a.work)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    env = dict(os.environ)
    if MESEN_STEPS & set(steps):
        if not os.environ.get('MESENCE'):
            print('MESENCE 환경 변수가 필요함(MesenCE 실행 파일)', file=sys.stderr)
            return 1
        _, env = pinned_mesence(work, os.environ['MESENCE'])
    rom_sha = hashlib.sha1(open(rom, 'rb').read()).hexdigest()
    ship = ship_state(rom, work, env) if SHIP_STEPS & set(steps) else None
    for step in steps:
        start = time.time()
        print(f'== {step}', flush=True)
        run_step(step, rom, out, work, ship, env, a.jobs)
        write_sources(out, step, rom_sha)
        print(f'== {step} {time.time() - start:.0f}초', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
