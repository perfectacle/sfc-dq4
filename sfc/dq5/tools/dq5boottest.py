"""DQ5(SFC) 부팅 시험. 원래 롬과 만든 롬을 MesenCE testrunner 로 전원부터 켜 A 를 눌러 가며 새 게임 첫 장면
(배 선실, 맵 17/00)까지 가게 하고, 그 맵에 닿았는지와 정한 프레임의 화면 상태 해시(VRAM·CGRAM·OAM·WRAM)가
원래 롬과 같은지 본다. 화면 PNG 도 남긴다(견주지는 않는다).

환경 변수 MESENCE(실행 파일)가 있어야 한다. 롬은 work/boot/ 에 시험 전용 이름으로 복사하고, 그 이름의 SRAM 파일을
지운 뒤 RAM 을 0 으로 켜서 돌린다. SRAM 폴더는 MESENCE_SAVES(기본 macOS 의 MesenCE 설정 폴더 Saves).

  python sfc/dq5/tools/dq5boottest.py rom/dq5.sfc work/build/dq5kr.sfc
  --allow-diff  화면이 원래 롬과 달라도(글자를 바꾼 롬) 첫 장면에 닿으면 통과
  --scenes ST   첫 장면 뒤 단계도 돈다. 배 선실 세이브스테이트 ST(sfc/dq5/handoff.md)에서 두 롬 모두 dq5warp.lua 로
                필드 걷기·첫 필드 이벤트 전투·명령 창 열고 닫기·サンタローズ(01/00) 도구 가게와 대화(보행 모드 메시지·물건 창)를 돌려, 정한 프레임의 해시와 끝 상태(warp.txt 의 end 줄)를
                견준다. --allow-diff 면 끝 상태만 같으면 통과
"""
import argparse
import os
import shutil
import subprocess
import sys
import dq5mesen

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
    # 프레임 건너뛰기를 끄지 않으면 화면 PNG 가 시간에 따라 1~3프레임 앞의 그림으로 찍힌다.
    return dq5mesen.testrunner_popen(mesence, os.path.abspath(rom), LUA, '--Snes.RamPowerOnState=AllZeros',
                                     '--Snes.DisableFrameSkipping=true',
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


WARP = os.path.join(HERE, 'lua', 'dq5warp.lua')
SCENE_LUA = os.path.join(HERE, 'lua', 'dq5scenehash.lua')
TAPS = ','.join(['a:8,wait:40'] * 15)
# (이름, dq5warp 변수, 해시를 남길 프레임). 프레임은 장면 이동(약 410프레임)과 SETTLE(150) 뒤 TEST 안에 둔다.
SCENES = [
    ('walk', {'FIELD': '174,110', 'TEST': 'left:60,up:60,right:60,down:60'}, '600,660,720,780'),
    ('battle', {'FIELD': '341,56', 'BATTLE': '00:1', 'TEST': TAPS}, '600,700,800,900,1000,1100,1200'),
    ('menu', {'FIELD': '341,56', 'TEST': 'a:6,wait:30,down:6,wait:20,a:6,wait:40,b:6,wait:20,b:6,wait:30'},
     '580,620,660,700'),
    ('talk', {'TO': '01/00,12,80,2', 'TEST': 'up:20,wait:20,a:6,wait:30,a:6,wait:60,a:6,wait:60,a:6,wait:60,b:6,wait:30,b:6,wait:30'},
     '660,720,780,840'),
]


def scenes(mesence, krlua, state, roms, work):
    """두 롬으로 장면들을 돌려 [(장면, 해시가 같은지, 끝 줄이 같은지, 원래 끝 줄, 만든 끝 줄, 다른 프레임 수)]."""
    lib = os.path.join(work, 'warplib')
    os.makedirs(lib, exist_ok=True)
    for name in ('lib.lua', 'probe'):
        dst = os.path.join(lib, name)
        if not os.path.lexists(dst):
            os.symlink(os.path.join(krlua, name), dst)
    shutil.copyfile(WARP, os.path.join(lib, 'boot.lua'))
    procs = []
    for name, env, shots in SCENES:
        for tag, rom in roms.items():
            out = os.path.join(work, f'scene-{name}', tag)
            os.makedirs(out, exist_ok=True)
            e = dict(os.environ, LIBDIR=lib, SHOT_DIR=out, STATE=os.path.abspath(state), SHOTS=shots, **env)
            procs.append(dq5mesen.testrunner_popen(mesence, rom, SCENE_LUA, env=e,
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait()
    res = []
    for name, _, _ in SCENES:
        got = {}
        for tag in roms:
            out = os.path.join(work, f'scene-{name}', tag)
            hs = open(os.path.join(out, 'scene.txt')).read().split('\n') if os.path.exists(os.path.join(out, 'scene.txt')) else []
            warp = open(os.path.join(out, 'warp.txt')).read() if os.path.exists(os.path.join(out, 'warp.txt')) else ''
            end = next((ln.split(' ', 1)[1] for ln in warp.split('\n') if ' end ' in ln), '(끝 줄 없음)')
            got[tag] = ([h for h in hs if h], end)
        (oh, oe), (bh, be) = got['orig'], got['build']
        ndiff = sum(x != y for x, y in zip(oh, bh)) + abs(len(oh) - len(bh))
        res.append((name, ndiff == 0 and bool(oh), oe == be and not oe.startswith('('), oe, be, ndiff))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('original')
    ap.add_argument('built')
    ap.add_argument('--work', default='work/boot')
    ap.add_argument('--allow-diff', action='store_true')
    ap.add_argument('--scenes', metavar='STATE')
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        print('MESENCE 환경 변수가 필요함', file=sys.stderr)
        return 1
    libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    jobs, roms = [], {}
    for tag, src in (('orig', a.original), ('build', a.built)):
        rom = os.path.join(work, f'dq5boot-{tag}.sfc')
        shutil.copyfile(src, rom)
        roms[tag] = rom
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
    if a.scenes:
        for name, same, end_same, oe, be, ndiff in scenes(mesence, libdir, a.scenes, roms, work):
            good = end_same and (a.allow_diff or same)
            ok = ok and good
            print(f'장면 {name}: {"통과" if good else "실패"} — 해시 {"같음" if same else f"다른 프레임 {ndiff}개"}, '
                  f'끝 {"같음" if end_same else "다름"} ({be})')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
