"""DQ5(SFC) 부팅 시험. 원래 롬과 만든 롬을 MesenCE testrunner 로 전원부터 켜 A 를 눌러 가며 새 게임 첫 장면
(배 선실, 맵 17/00)까지 가게 하고, 그 맵에 닿았는지와 정한 프레임의 화면 상태 해시(VRAM·CGRAM·OAM·WRAM)가
원래 롬과 같은지 본다. 화면 PNG 도 남기지만 실행마다 한 프레임 앞뒤가 섞여 찍혀 견주지 않는다.

환경 변수 MESENCE(실행 파일)가 있어야 한다. 롬은 work/boot/ 에 시험 전용 이름으로 복사하고, 그 이름의 SRAM 파일을
지운 뒤 RAM 을 0 으로 켜서 돌린다. SRAM 폴더는 MESENCE_SAVES(기본 macOS 의 MesenCE 설정 폴더 Saves).

  python sfc/dq5/tools/dq5boottest.py rom/dq5.sfc work/build/dq5kr.sfc
  --allow-diff  화면이 원래 롬과 달라도(글자를 바꾼 롬) 첫 장면에 닿으면 통과
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, 'lua', 'dq5boot.lua')
FIRST_SCENE = '17/00'
SAVES = os.environ.get('MESENCE_SAVES') or os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'MesenCE', 'Saves')


def start(mesence, libdir, rom, out):
    os.makedirs(out, exist_ok=True)
    srm = os.path.join(SAVES, os.path.splitext(os.path.basename(rom))[0] + '.srm')
    if os.path.exists(srm):
        os.remove(srm)
    env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=os.path.abspath(out))
    # 설정의 Snes.RamPowerOnState 가 Random 이면 같은 롬도 결과가 달라진다. 이 실행만 0 으로 켠다.
    return subprocess.Popen([mesence, '--testrunner', os.path.abspath(rom), LUA, '--Snes.RamPowerOnState=AllZeros'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def result(out):
    path = os.path.join(out, 'boot.txt')
    hashes, scene = {}, '(boot.txt 없음)'
    if os.path.exists(path):
        for line in open(path):
            frame, rest = line.split(' ', 1)
            if rest.startswith('map '):
                scene = line.strip()
            else:
                hashes[frame] = rest.strip()
    return scene, hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('original')
    ap.add_argument('built')
    ap.add_argument('--work', default='work/boot')
    ap.add_argument('--allow-diff', action='store_true')
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        print('MESENCE 환경 변수가 필요함', file=sys.stderr)
        return 1
    libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    jobs = []
    for tag, src in (('orig', a.original), ('build', a.built)):
        rom = os.path.join(work, f'dq5boot-{tag}.sfc')
        shutil.copyfile(src, rom)
        jobs.append(start(mesence, libdir, rom, os.path.join(work, tag)))
    for p in jobs:
        p.wait()
    (os_, oh), (bs, bh) = result(os.path.join(work, 'orig')), result(os.path.join(work, 'build'))
    print(f'원래: {os_}\n만든: {bs}')
    keys = sorted(set(oh) | set(bh))
    diff = [k for k in keys if oh.get(k) != bh.get(k)]
    for k in keys:
        print(f'{k}  {bh.get(k, "-")}  {"다름" if k in diff else "같음"}')
    reached = f'map {FIRST_SCENE}' in bs
    ok = reached and (a.allow_diff or not diff)
    print(('통과' if ok else '실패') + f': 첫 장면 {"닿음" if reached else "못 닿음"}, 원래 롬과 다른 프레임 {len(diff)}개')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
