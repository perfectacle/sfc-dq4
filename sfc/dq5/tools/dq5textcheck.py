"""보행 메시지 쓰기 결과를 MesenCE 디코더의 실제 반환 코드와 비교한다.

원본 롬과 선실 상태는 읽기만 하며 JSON·패치·IPS·게임 로그는 --out의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5textcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dq5text import CHARS
from dq5textwrite import read_messages

HERE = Path(__file__).resolve().parent


def decoder_codes(rom, msg, ret, dest, state, mesence, libdir):
    """선실에서 메시지 msg 를 띄워 디코더가 ret(디코더 사본의 RTL)에서 돌려준 첫 64코드와 스트림 주소."""
    dest.mkdir()
    env = os.environ.copy()
    for key in ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'WW', 'WWRANGE', 'WRAMWATCH', 'COVER',
                'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), MESSAGE=str(msg), RETURN_PC=ret,
               DRIVER=str(HERE / 'lua/dq5msg.lua'), MAXF='500', ROMPATCH=f'30139={0x6000 | msg:04X}',
               PRE='b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150')
    with (dest / 'mesen.log').open('w') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5textcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=90)
    lines = (dest / 'decoded.txt').read_text().splitlines()
    return int(lines[0].split('=')[1], 16), [int(code, 16) for code in lines[1:]]


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/textcheck')
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
        messages = read_messages(original.read_bytes())
        changed = [0x1006, *[CHARS.index(c) for c in 'あいうえお'], 0x1001]
        edited = messages.copy()
        edited[0x129] = edited[0xC70] = changed
        for name, rows in [('repacked', []), ('edited', [
                {'id': 0x129, 'codes': changed}, {'id': 0xC70, 'codes': changed}])]:
            source, patch = out / f'{name}.json', out / f'{name}.patch.json'
            source.write_text(json.dumps({'format': 'dq5text/1', 'messages': rows}) + '\n')
            command('dq5textwrite.py', original, 'patch', source, '-o', patch)
            command('dq5build.py', original, 'build', patch, '--size', '4' if name == 'edited' else '2',
                    '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True,
                                text=True, timeout=30).stdout.strip()
        results = []
        for name, rom, msg, expected_messages, ret in [
                ('original', original, 0x129, messages, '249E46'),
                ('repacked', out / 'repacked.sfc', 0x129, messages, '388044'),
                ('edited', out / 'edited.sfc', 0x129, edited, '388044'),
                ('far', out / 'edited.sfc', 0xC70, edited, '388044')]:
            stream, actual = decoder_codes(rom, msg, ret, out / name, state, mesence, libdir)
            expected = [code for row in expected_messages[msg:] for code in row][:64]
            if len(actual) != 64 or actual != expected:
                raise ValueError(f'{name}: 실제 코드 불일치 {actual[:12]}, 기대 {expected[:12]}')
            if name == 'far' and stream >> 16 <= 0x38:
                raise ValueError('뒤쪽 메시지가 다음 스트림 뱅크에 있지 않음')
            results.append({'case': name, 'message': msg, 'stream': f'{stream:06X}', 'codes_equal': 64})
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
