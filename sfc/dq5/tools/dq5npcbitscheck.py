"""인물 엔트리 기타 bit4-6 의 뜻을 MesenCE 선실 장면에서 잰다.

기타 bit4-5 는 7E:32A0 bit4-5, bit6 은 7E:33A0 bit7 로 간다(1E:DB44). 선실 パパス(슬롯 0B)의 값을 첫 프레임에 바꾸고
(dq5msg.lua 의 SET) 아래에서 말을 건다.
  turn-VV   パパス 를 위(31E0 = 88, 3240·3260 = 08)로 돌려 두고 32A0 = 41 | VV. 대화 뒤 31E0·3240·3260
  side-VV   왼쪽(22, 02)으로 돌려 두고 같게. 말을 걸 때 05:82C0 이 05:82FF 로 32A0 bit4-5 에 따라 돌린다
  prio-VV   33A0 = VV(30·B0) 로 두고 100프레임 OAM. bit7 이면 OAM 우선순위를 33A0 bit4-5 로(00:EE9E·00:F567)
  MESENCE=… python sfc/dq5/tools/dq5npcbitscheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5progresscheck import environment, require, run, save_json

HERE = Path(__file__).resolve().parent
SLOT = 0x0B
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4'
AFTER = 300


def scenes():
    out = {}
    for v in (0x00, 0x10, 0x20, 0x30):
        for name, (face, half) in (('turn', (0x88, 0x08)), ('side', (0x22, 0x02))):
            out[f'{name}-{v:02X}'] = {
                'SET': f'31{0xE0 + SLOT:02X}={face:02X};32{0x40 + SLOT:02X}={half:02X};32{0x60 + SLOT:02X}={half:02X};'
                       f'32{0xA0 + SLOT:02X}={0x41 | v:02X}',
                'PRE': TALK, 'MAXF': '400', 'CALLS': '248BAF',
                'DUMP': ','.join(f'{AFTER}:7E{base + SLOT:04X}:1' for base in (0x31E0, 0x3240, 0x3260))}
    for v in (0x30, 0xB0):
        out[f'prio-{v:02X}'] = {'SET': f'33{0xA0 + SLOT:02X}={v:02X}', 'PRE': 'wait:10', 'MAXF': '120', 'OAMDUMP': '100'}
    return out


def scene(name, options, rom, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(options)
    run(mesence, rom, HERE / 'lua/dq5msg.lua', dest, env)
    text = (dest / 'msg.txt').read_text(encoding='utf-8')
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[1] == 'dump':
            values[parts[2]] = int(parts[3], 16)
    oam = dest / 'o00100.bin'
    return {'values': values, 'talked': '248BAF' in text, 'oam': oam.read_bytes().hex() if oam.exists() else None}


def priorities(a, b):
    """두 OAM 에서 다른 칸마다 (칸, 앞 우선순위, 뒤 우선순위, 우선순위 밖도 같은지)."""
    a, b = bytes.fromhex(a), bytes.fromhex(b)
    return [(i, a[i * 4 + 3] >> 4 & 3, b[i * 4 + 3] >> 4 & 3, a[i * 4:i * 4 + 3] == b[i * 4:i * 4 + 3]
             and a[i * 4 + 3] & 0xCF == b[i * 4 + 3] & 0xCF)
            for i in range(128) if a[i * 4:i * 4 + 4] != b[i * 4:i * 4 + 4]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/npcbitscheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        rom, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (rom, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {n: pool.submit(scene, n, o, rom, state, out, mesence, libdir) for n, o in scenes().items()}
            seen = {n: f.result() for n, f in futures.items()}

        def after(name):
            v = seen[name]['values']
            return tuple(v[f'7E{base + SLOT:04X}'] for base in (0x31E0, 0x3240, 0x3260))

        prio = priorities(seen['prio-30']['oam'], seen['prio-B0']['oam'])
        # 대화 뒤 パパス 는 아래(주인공 쪽)를 본다. 31E0 위 니블 4 = 아래, 3240·3260 은 80 | 그 방향 니블.
        checks = {
            'talked': all(r['talked'] for n, r in seen.items() if not n.startswith('prio')),
            'turn-00': after('turn-00') == (0x48, 0x08, 0x08) and after('side-00') == (0x42, 0x02, 0x02),
            'turn-10': after('turn-10') == (0x88, 0x08, 0x08) and after('side-10') == (0x22, 0x02, 0x02),
            'turn-20': after('turn-20') == (0x88, 0x84, 0x84) and after('side-20') == (0x22, 0x02, 0x84),
            'turn-30': after('turn-30') == (0x88, 0x84, 0x84) and after('side-30') == (0x22, 0x84, 0x84),
            'prio': len(prio) > 0 and all((a, b, same) == (2, 3, True) for _, a, b, same in prio),
        }
        results = {n: {k: v for k, v in r.items() if k != 'oam'} for n, r in seen.items()}
        save_json(out / 'results.json', {'scenes': results, 'priority': prio, 'checks': checks})
        for n in seen:
            if not n.startswith('prio'):
                print(f'{n}: 31E0·3240·3260 = ' + ' '.join(f'{x:02X}' for x in after(n)))
        print(f'33A0 30 → B0 에서 바뀐 OAM 칸(칸, 우선순위 앞, 뒤, 나머지 같음): {prio}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}건 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
