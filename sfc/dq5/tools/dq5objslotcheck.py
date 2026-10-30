"""맵 OBJ 물체를 더해 인물 슬롯이 넘칠 때를 MesenCE에서 잰다(dq5objlayout.py 의 슬롯 검사 근거).

19/02(낮·밤 인물 23명, 물체를 다 놓은 뒤 7E:1983 = 1F)에 1x1 물체를 하나·둘 더한 롬을 만든다. 하나는 dq5objlayout.py 가
받고(1983 = 20), 둘은 거부하므로(1983 = 21) 슬롯 검사를 끈 채 같은 함수로 만든다. 원본과 함께 dq5warp.lua 로
19/02 (42,26)에 들어가 700프레임에 덤프하고, 1983·주인공 칸(7E:3020·3080)·보이는 OAM 수, 인물 표 7E:3000~37FF 에서
칸마다 슬롯 0·1 자리가 원본과 다른 바이트를 센다.
  MESENCE=… python sfc/dq5/tools/dq5objslotcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5objlayout as L  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402

HERE = Path(__file__).resolve().parent
MAP, AT = '19/02', '42,26'
DUMP = 700


def doc(rom, extra):
    objects = L.dump(rom)['objects']
    new = [{'map': MAP, 'x': 40 + 2 * i, 'y': 24, 'cond': None, 'palette': 3, 'priority': 2, 'cells': ['00']}
           for i in range(extra)]
    return {'format': L.FORMAT, 'objects': objects + new}


def scratch(rom, extra, path, guard=True):
    if guard:
        manifest = L.patch(rom, doc(rom, extra), L.address('16:FE10'))
    else:
        with mock.patch.object(L, 'check_slots'):
            manifest = L.patch(rom, doc(rom, extra), L.address('16:FE10'))
    path.write_bytes(L.built(rom, manifest).d)


def run(rom, dest, state, mesence, libdir):
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH',
                        'SAVE', 'SET', 'WAGON', 'EVERY', 'FROM')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1200', SETTLE='120', TO=f'{MAP},{AT}',
               DUMPF=f'{DUMP},{DUMP + 1}', TEST='wait:300')
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5gfxdump.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    w = (dest / f'f{DUMP:05d}.wram').read_bytes()
    oam = (dest / f'f{DUMP:05d}.oam').read_bytes()
    return w, sum(1 for i in S.oam_groups(oam) if i)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/objslotcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        rom = Rom(original.read_bytes())
        scratch(rom, 1, out / 'one.sfc')
        try:
            scratch(rom, 2, out / 'two.sfc')
            raise ValueError('물체 둘(1983 = 21)을 dq5objlayout.py 가 받음')
        except ValueError as error:
            if '받음' in str(error):
                raise
            print(f'물체 둘: {error}')
        scratch(rom, 2, out / 'two.sfc', guard=False)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        rows = {name: run(path, out / name, state, mesence, libdir)
                for name, path in (('original', original), ('one', out / 'one.sfc'), ('two', out / 'two.sfc'))}
        base = rows['original'][0]
        result = {}
        for name, (w, visible) in rows.items():
            slot01 = [a for a in range(0x3000, 0x3800) if a & 0x1F in (0, 1) and w[a] != base[a]]
            result[name] = {'1983': w[0x1983], 'hero': (w[0x3020], w[0x3080]), 'oam': visible,
                            'slot01': [f'{a:04X}' for a in slot01]}
            print(f'{name}: 1983={w[0x1983]:02X} 주인공 칸 {w[0x3020]},{w[0x3080]} 보이는 OAM {visible} '
                  f'슬롯 0·1 자리가 원본과 다른 바이트 {len(slot01)} {result[name]["slot01"][:6]}')
        hero = tuple(int(v) for v in AT.split(','))
        checks = {
            'one': result['one']['1983'] == 0x20 and result['one']['hero'] == hero and
            all(int(a, 16) & 0xFFE0 in (0x3280, 0x32E0) for a in result['one']['slot01']),
            'two': result['two']['1983'] == 0x21 and result['two']['hero'] != hero,
        }
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
