"""움직이는 타일 종류 14 를 쓰는 실내 맵 열에 순간이동해 명령 창을 열며, 종류 14 사본(7E:3D14~3E73)을 누가 썼는지와
창 글자 대기열 변수, 창 글자 코드가 고른 VRAM 주소를 MesenCE 로 잰다. 형식은 sfc/dq4/docs/dq4-window-text-format.md
「창 글자 변수 자리」.

장면은 dq4bg3slotcheck 와 같다(롬으로 만든 출발 상태, (10,10) 도착, 명령 창). lua/dq4kind14probe.lua 가
lua/dq4bg3slotwarp.lua 를 감싸 프레임마다 적는다. --layout 은 변수 자리를 고른다: old 는 변수를 사본 안 7E:3D5A~에 두던
롬, new 는 7E:A976~ 로 옮긴 롬. 판정은 new 롬에만 한다: 열 맵 모두에서 dq4bg3slotcheck 의 판정(도착·자리·보임·창이
버퍼와 같음)이 맞고, 뱅크 03 이 사본을 쓰고, 사본 자리를 쓴 그 밖의 코드가 없어야 한다.

  MESENCE=... uv run --locked python sfc/dq4/tools/dq4kind14check.py --rom work/ch1/menu.sfc --out 새폴더 \\
      [--layout new|old] [--maps 1E/00,20/06] [--jobs 2] [--entry D843]
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools')]

import dq4bg3slotcheck as bc  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4mesen as mesen  # noqa: E402

PROBE = HERE / 'lua' / 'dq4kind14probe.lua'
# 종류 마스크(03:D806) bit14 가 켜진 맵(원본 DQ5 와 menu.sfc 가 같음)
MAPS = ['1E/00', '20/06', '03/01', '03/02', '04/00', '0D/00', '31/00', '32/00', '34/00', '35/03']
COPY = (0x3D14, 0x3E73)
NAMES = ('defer', 'rd', 'count', 'off', 'left', 'head', 'len', 'stale', 'stale2')
LAYOUT = {
    'old': {'defer': (0x3D5A, 1), 'rd': (0x3D5C, 2), 'count': (0x3D62, 1), 'off': (0x3D64, 2), 'left': (0x3D66, 2),
            'head': (0x3D68, 2), 'len': (0x3D6A, 2), 'stale': (0x3DCB, 1), 'stale2': (0x3DCD, 1)},
    'new': {'defer': (0xA976, 1), 'rd': (0xA978, 2), 'count': (0xA97E, 1), 'off': (0xA980, 2), 'left': (0xA982, 2),
            'head': (0xA984, 2), 'len': (0xA986, 2), 'stale': (0xA9E7, 1), 'stale2': (0xA9E9, 1)},
}


def parse(text):
    """kind14.txt → {frames: [{frame, w03, wother, vars}], copies: [(frame, bytes)], vmadd: [(frame, [(VRAM 주소, PC)])],
    entries: [(frame, [(VRAM 주소, Y, 머리)])], tmdiff: [(frame, 수, 첫)]}."""
    out = {'frames': [], 'copies': [], 'vmadd': [], 'entries': [], 'tmdiff': []}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        f = int(parts[0])
        if parts[1] == 'copy':
            out['copies'].append((f, bytes.fromhex(parts[2])))
        elif parts[1] == 'entry':
            out['entries'].append((f, [tuple(int(y, 16) for y in x.split(':')) for x in parts[2].split(',')]))
        elif parts[1] == 'tmdiff':
            out['tmdiff'].append((f, int(parts[2]), int(parts[3], 16)))
        elif parts[1] == 'vmadd':
            out['vmadd'].append((f, [tuple(int(y, 16) for y in x.split('@')) for x in parts[2].split(',')]))
        else:
            kv = dict(p.split('=', 1) for p in parts[1:])
            vs = dict(x.split(':') for x in kv['vars'].split(',') if x)
            out['frames'].append({'frame': f, 'w03': int(kv['w03']), 'wother': int(kv['wother']),
                                  'vars': {k: int(v, 16) for k, v in vs.items()}})
    return out


def named(layout, raw):
    """{주소 16진: 값} → {이름: 값}."""
    return {k: raw.get(f'{a:04X}') for k, (a, _) in LAYOUT[layout].items()}


def at_copy(layout, copy):
    """사본 352바이트 가운데 그 layout 의 변수 자리에 든 값(사본 밖 변수는 없음)."""
    got = {}
    for k, (a, n) in LAYOUT[layout].items():
        if COPY[0] <= a and a + n - 1 <= COPY[1]:
            o = a - COPY[0]
            got[k] = int.from_bytes(copy[o:o + n], 'little')
    return got


def judge(rec):
    """new 롬에 더하는 판정: 뱅크 03 이 사본을 쓰고, 그 밖의 코드는 사본 자리를 쓰지 않음."""
    bad = []
    if not rec['copies']:
        bad.append('뱅크 03 이 종류 14 사본을 쓰지 않음')
    other = [r['frame'] for r in rec['frames'] if r['wother']]
    if other:
        bad.append(f'뱅크 03 밖 코드가 사본 자리를 씀(프레임 {other[:4]})')
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--layout', choices=tuple(LAYOUT), default='new')
    ap.add_argument('--maps', default=','.join(MAPS))
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--entry', default='', help='대기열 항목 하나를 보내는 $2116 쓰기의 PC 아래 16비트(16진, 뱅크 60). '
                    '주면 항목마다 VRAM 주소·항목 자리·머리를 적는다(고치기 전 menu.sfc 는 D843)')
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists():
        ap.error('--out 은 아직 없는 폴더를 주세요')
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    rom = a.rom.resolve()
    state = dq4freshstate.make(mesence, rom, out / 'start')
    vars_ = ','.join(f'{x:04X}:{n}' for x, n in LAYOUT[a.layout].values())
    running, folders = [], {}
    for mp in a.maps.split(','):
        folder = out / mp.replace('/', '-')
        folder.mkdir(parents=True)
        folders[mp] = folder
        env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(state), TO=f'{mp},10,10',
                   SETTLE='60', TEST=bc.TEST, MAXF='2400', VARS=vars_, ENTRY=a.entry or '0',
                   NEXT=str(HERE / 'lua/dq4bg3slotwarp.lua'), WARPLUA=str(ROOT / 'sfc/dq5/tools/lua/dq5warp.lua'))
        running.append(mesen.Runner(mesence, rom, PROBE, folder, tag='kind14',
                                    extra=('--Snes.RamPowerOnState=AllZeros',), env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if len(running) >= a.jobs:
            running.pop(0).wait()
    for p in running:
        p.wait()
    rows, ok = [], True
    for mp, folder in folders.items():
        p = folder / 'kind14.txt'
        rec = parse(p.read_text() if p.exists() else '')
        records, arrival = bc.records_of(folder), bc.arrival_of(folder)
        slot = records[-1]['0725'] if records else None
        first = rec['copies'][0] if rec['copies'] else None
        row = {'map': mp, 'arrival': arrival[0] if arrival else None, '0725': slot,
               'copy_frame': first[0] if first else None,
               'copy_vars': at_copy(a.layout, first[1]) if first else {},
               'copy_frames': [f for f, _ in rec['copies']],
               'vmadd': [(f, [f'{x:04X}@{pc:04X}' for x, pc in xs]) for f, xs in rec['vmadd']][:12],
               'vars_after_copy': next((named(a.layout, r['vars']) for r in rec['frames']
                                        if first and r['frame'] == first[0]), None),
               'copy': first[1].hex() if first else None}
        bad = bc.judge(mp, arrival, records)
        if a.layout == 'new':
            bad += judge(rec)
        row['problems'] = bad
        ok &= a.layout == 'old' or not bad
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'copy'}, ensure_ascii=False))
    (out / 'report.json').write_text(json.dumps({'layout': a.layout, 'status': 'passed' if ok else 'failed',
                                                 'maps': rows}, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(rows)}맵, {"통과" if ok else "실패"}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
