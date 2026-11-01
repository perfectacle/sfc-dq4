"""전투 메시지·이름 표 쓰기 결과를 MesenCE 전투에서 디코더가 푼 버퍼와 글자 격자로 확인한다.

선실 상태에서 dq5warp.lua 로 スライム 하나와 전투를 붙이고 A 를 눌러 공격·피해 메시지를 띄운다. 원본 롬과
원문을 다시 넣은 롬, 메시지 05E 와 몬스터 이름 0 을 바꾼 롬(제자리·옮긴 자리)을 견준다.
원본 롬과 선실 상태는 읽기만 하며 JSON·패치·롬·게임 기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5battletextcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dq5battletextwrite import read_messages
import dq5mesen

HERE = Path(__file__).resolve().parent
TAPS = ','.join(['a:8,wait:40'] * 15)
ATTACK = 0x05E
# 「{F7}の　テストこうげき！」 과 「テストスライム」. 바이트는 이름 문자열 부호(テ 54, ス 4E, ト 55).
EDITED = [0xF7, 0x28, 0x01, 0x54, 0x4E, 0x55, 0x19, 0x12, 0x84, 0x18, 0x16, 0x7A, 0xFE]
SLIME = [0x4E, 0x68, 0x43, 0x62]
NAME = [0x54, 0x4E, 0x55, *SLIME]


def command(tool, rom, *args):
    subprocess.run([sys.executable, str(HERE / tool), str(rom), *map(str, args)],
                   check=True, capture_output=True, text=True, timeout=120)


def grid_text(name, message):
    """글자 격자 줄에 놓이는 바이트: 이름 뒤에 메시지의 F7 다음부터 끝 앞까지(탁점 84 는 윗줄에 가므로 뺀다)."""
    return bytes(name + [c for c in message[1:-1] if c not in (0x83, 0x84)]).hex().upper()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/battletextcheck')
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
        edited = messages.copy()
        edited[ATTACK] = EDITED
        text_edit = {'format': 'dq5battletext/1', 'messages': [{'id': ATTACK, 'codes': EDITED}]}
        # 원래 자리는 빈틈이 없으므로 늘린 3바이트만큼 물건 0(ひのきのぼう)을 ひのき 로 줄인다.
        name_edit = {'format': 'dq5names/1', 'tables': [{'table': 4, 'names': [{'id': 0, 'bytes': NAME}]},
                                                       {'table': 5, 'names': [{'id': 0, 'bytes': [0x2A, 0x28, 0x16]}]}]}
        empty_text = {'format': 'dq5battletext/1', 'messages': []}
        empty_names = {'format': 'dq5names/1', 'tables': []}
        builds = {'repacked': (empty_text, '3B:8000', empty_names, None),
                  'edited': (text_edit, '3B:8000', name_edit, None),
                  'moved': (text_edit, '4F:FD00', name_edit, '4E:8000')}
        for name, (text_doc, text_at, name_doc, name_at) in builds.items():
            sources = []
            for kind, doc in (('text', text_doc), ('names', name_doc)):
                source = out / f'{name}.{kind}.json'
                source.write_text(json.dumps(doc) + '\n')
                sources.append(source)
            text_patch, name_patch = out / f'{name}.text.patch.json', out / f'{name}.names.patch.json'
            command('dq5battletextwrite.py', original, 'patch', sources[0], '--at', text_at, '-o', text_patch)
            command('dq5namewrite.py', original, 'patch', sources[1], '-o', name_patch,
                    *(['--at', name_at] if name_at else []))
            command('dq5build.py', original, 'build', text_patch, name_patch, '--size', '4',
                    '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True,
                                text=True, timeout=30).stdout.strip()
        results = []
        for name, rom, expected_messages, monster, bank in [
                ('original', original, messages, SLIME, 0x07),
                ('repacked', out / 'repacked.sfc', messages, SLIME, 0x3B),
                ('edited', out / 'edited.sfc', edited, NAME, 0x3B),
                ('moved', out / 'moved.sfc', edited, NAME, None)]:
            dest = out / name
            dest.mkdir()
            env = os.environ.copy()
            for key in ('ROMPATCH', 'SET', 'POKE', 'TO', 'GROUP', 'PARTY', 'ADULT', 'WAGON', 'LATESET', 'SAVE',
                        'ANYWHERE', 'PRE'):
                env.pop(key, None)
            env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua/dq5warp.lua'),
                       FIELD='341,56', BATTLE='00:1', TEST=TAPS, MAXF='2000')
            with (dest / 'mesen.log').open('w') as log:
                dq5mesen.testrunner(str(mesence), str(rom), str(HERE / 'lua/dq5battletextcheck.lua'),
                                    '--Snes.DisableFrameSkipping=true', env=env, stdout=log,
                                    stderr=subprocess.STDOUT, check=True, timeout=180)
            lines = [line.split() for line in (dest / 'battletext.txt').read_text().splitlines()]
            buffers = [(int(w[2], 16), bytes.fromhex(w[3])) for w in lines if w[1] == 'buffer']
            streams = {int(w[2], 16): int(w[4].split('.')[0], 16) for w in lines if w[1] == 'msg'}
            grids = [bytes.fromhex(w[3]).hex().upper() for w in lines if w[1] == 'grid' and int(w[2], 16) == ATTACK]
            if not any(msg == ATTACK for msg, _ in buffers):
                raise ValueError(f'{name}: 메시지 {ATTACK:03X} 버퍼를 잡지 못함')
            for msg, buffer in buffers:
                expected = bytes([c for row in expected_messages[msg:] for c in row][:128])
                if buffer[:len(expected)] != expected:
                    raise ValueError(f'{name}: 메시지 {msg:03X} 버퍼 불일치 {buffer[:16].hex()} / {expected[:16].hex()}')
            line = grid_text(monster, expected_messages[ATTACK])
            if not any(line in g for g in grids):
                raise ValueError(f'{name}: 몬스터 공격 줄 {line} 이 격자에 없음')
            stream_bank = streams[ATTACK] >> 16
            if bank is not None and stream_bank != bank:
                raise ValueError(f'{name}: 메시지 {ATTACK:03X} 스트림 뱅크 {stream_bank:02X}, 기대 {bank:02X}')
            if bank is None and stream_bank not in (0x4F, 0x50):
                raise ValueError(f'{name}: 메시지 {ATTACK:03X} 스트림이 4F·50 뱅크가 아님')
            results.append({'case': name, 'buffers_equal': len(buffers),
                            'messages': sorted(f'{m:03X}' for m in {m for m, _ in buffers}),
                            'stream': f'{streams[ATTACK]:06X}', 'grid': line})
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
