"""걸음 루틴 표의 뱅크 00 밖 루틴(받침 00:C656~)을 MesenCE 에서 밟아 확인한다.

원본에서 롬 둘을 만든다.
  f  dq5stepwrite.py 로 그룹 01 의 걸음 루틴을 3C:B000 으로(찾기 루틴·표는 3C:A000, 받침은 00:C656).
     3C:B000 에는 시험 몸통 `LDA $00 / AND #$02 / BEQ +2 / SEC / RTL / CLC / RTL` 을 둔다. 누른 방향이 왼쪽이면
     캐리를 켜서 걸음을 막고, 아니면 끈다.
  h  찾기 루틴·표만 3C:A000 으로 옮기고 루틴은 원래 그대로(받침 없음). 받침 자리를 아무도 읽거나 실행하지 않는지 본다.
장면은 배 선실 세이브스테이트에서 dq5warp.lua 로 01/00 (40,84) 층 2 에 가서 걷는다. lua/dq5stepprobe.lua 가
00:C656~C686 의 실행 PC·읽기 횟수와 몸통에 들어올 때의 레지스터를 적는다.

  left      f: 왼쪽으로 걸어도 (40,84) 에 남음. $1AAD = C656, 몸통에 들어올 때 $00 = 02
  right     f: 오른쪽으로 걸으면 움직임. 몸통에 들어올 때 $00 = 01
  left-orig 원본: 왼쪽으로 걸으면 움직임(대조)
  left-h    h: 왼쪽으로 걸으면 움직이고 받침 자리의 실행·읽기가 0
  other     f: 03/00 (38,60) 에서 걸은 뒤 $1AAD = C565(옮긴 표가 원래 그룹 03 항목을 지킴)
  event     e: 몸통이 왼쪽에서 대화 창(BRK 95 00)에 메시지 2ED(BRK 99 ED)를 띄우고 BRK 0E 뒤 창을 닫고(BRK 95 FF)
            캐리. 왼쪽을 누르고 A 한 번 뒤 오른쪽으로 걸으면 메시지 2ED 가 한 번 나오고 오른쪽으로 걸음

  MESENCE=… python sfc/dq5/tools/dq5stepcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5exitcheck import command, dp86_allowed, require, warp_exit
from dq5progresscheck import environment

HERE = Path(__file__).resolve().parent
BODY_AT = '3C:B000'
BODY = bytes.fromhex('a5 00 29 02 f0 02 38 6b 18 6b')
# LDA $00 / AND #$02 / BEQ +13 / BRK 95 00 / BRK 99 ED / BRK 0E / BRK 95 FF / SEC / RTL / CLC / RTL
EVENT_BODY = bytes.fromhex('a5 00 29 02 f0 0d 00 95 00 00 99 ed 00 0e 00 95 ff 38 6b 18 6b')
TABLE_AT = ('--table-at', '3C:A000')
START = '01/00,40,84,2'


def build_rom(original, out, key, doc, body=None):
    source, manifest = out / f'{key}-step.json', out / f'{key}-step.dq5patch.json'
    source.write_text(json.dumps(doc, ensure_ascii=False) + '\n', encoding='utf-8')
    command('dq5stepwrite.py', original, 'patch', source, '-o', manifest, *TABLE_AT)
    command('dq5stepwrite.py', original, 'check', source, *TABLE_AT)
    manifests = [manifest]
    if body:
        extra = out / f'{key}-body.dq5patch.json'
        extra.write_text(json.dumps({'format': 'dq5patch/1', 'name': 'step-body', 'rom_size': 2,
                                     'writes': [{'at': BODY_AT, 'hex': body.hex(' '), 'note': '시험 몸통'}]}) + '\n',
                         encoding='utf-8')
        manifests.append(extra)
    built = out / f'{key}.sfc'
    command('dq5build.py', original, 'build', *manifests, '-o', built, '--ips', out / f'{key}.ips')
    return built


def run(rom, name, to, test, state, out, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = environment(libdir, state, dest)
    env.update(TO=to, TEST=f'{test},wait:120', SETTLE='120', MAXF='1500', WARPEXIT=f'{warp_exit(rom):X}',
               DP86OK=dp86_allowed(rom), STEPBODY=BODY_AT.replace(':', ''))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5stepprobe.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    require('timeout' not in (dest / 'warp.txt').read_text(encoding='utf-8'), f'{name}: 장면 이동 시간 초과')
    ram = (dest / 'final.wram').read_bytes()
    text = (dest / 'step.txt').read_text(encoding='utf-8')
    return {'map': f'{ram[0xBC]:02X}/{ram[0xBD]:02X}', 'cell': [ram[0x3020], ram[0x3080]],
            '1AAD': f'{ram[0x1AAE]:02X}{ram[0x1AAD]:02X}',
            'reads': int(re.search(r'reads=(\d+)', text).group(1)),
            'execs': {m[0]: int(m[1]) for m in re.findall(r'exec (\w+) n=(\d+)', text)},
            'entries': re.findall(r'^entry .*$', text, re.M), 'msgs': re.search(r'^msgs (\S+)', text, re.M)[1]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path, help='배 선실 세이브스테이트')
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/stepcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        group01 = {'format': 'dq5step/1', 'groups': [{'group': '01', 'routine': BODY_AT}]}
        far = build_rom(original, out, 'f', group01, BODY)
        event = build_rom(original, out, 'e', group01, EVENT_BODY)
        hooked = build_rom(original, out, 'h', {'format': 'dq5step/1', 'groups': []})
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        jobs = {
            'left': (far, START, 'left:40'),
            'right': (far, START, 'right:40'),
            'left-orig': (original, START, 'left:40'),
            'left-h': (hooked, START, 'left:40'),
            'other': (far, '03/00,38,60,1', 'left:40,right:40'),
            'event': (event, START, 'left:12,wait:200,a:6,wait:120,right:24'),
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = dict(zip(jobs, pool.map(lambda name: run(jobs[name][0], name, *jobs[name][1:], state, out, mesence,
                                                            libdir), jobs)))
        trampoline = {'C656', 'C65A'}
        checks = {
            'left': seen['left']['map'] == '01/00' and seen['left']['cell'] == [40, 84] and seen['left']['1AAD'] == 'C656'
            and bool(seen['left']['entries']) and all(' 00=02 ' in e for e in seen['left']['entries'])
            and {k[2:] for k in seen['left']['execs']} == trampoline,
            'right': seen['right']['cell'][0] > 40 and bool(seen['right']['entries'])
            and all(' 00=01 ' in e for e in seen['right']['entries']),
            'left-orig': seen['left-orig']['cell'][0] < 40 and seen['left-orig']['1AAD'] == 'C385',
            'left-h': seen['left-h']['cell'][0] < 40 and seen['left-h']['1AAD'] == 'C385'
            and not seen['left-h']['execs'] and seen['left-h']['reads'] == 0,
            'other': seen['other']['map'] == '03/00' and seen['other']['1AAD'] == 'C565',
            'event': seen['event']['msgs'] == '2ED' and seen['event']['map'] == '01/00'
            and seen['event']['cell'][0] > 40 and seen['event']['1AAD'] == 'C656',
        }
        (out / 'results.json').write_text(json.dumps({'seen': seen, 'checks': checks}, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8')
        for name, where in seen.items():
            print(f'{name}: {where["map"]} {tuple(where["cell"])} $1AAD={where["1AAD"]} 읽기 {where["reads"]} '
                  f'실행 {where["execs"]} 메시지 {where["msgs"]}{"" if checks[name] else " 불일치"}')
            for line in where['entries'][:2]:
                print(f'  {line}')
        failed = [k for k, v in checks.items() if not v]
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(jobs)}개 장면, 걸음 루틴 받침 검사 통과')
        return 0
    except (OSError, ValueError, KeyError, AttributeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
