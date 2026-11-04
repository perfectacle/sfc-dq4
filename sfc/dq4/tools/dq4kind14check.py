"""움직이는 타일 종류 14 를 쓰는 실내 맵 열에 순간이동해 명령 창을 열며, 종류 14 사본을 누가 썼는지와 창 글자 대기열
변수, 창 글자 코드가 고른 VRAM 주소를 MesenCE 로 잰다. 형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자 변수 자리」.

사본 자리는 롬에서 읽는다(copy_range): 시작은 종류별 자리 표 03:D9A0 의 14번째 워드, 길이는 03:D965 의 14번째
바이트(돌릴 타일 수) × 32. 원본 DQ5 와 menu.sfc 는 7E:3D14~3E73 이다.

장면은 dq4bg3slotcheck 와 같다(롬으로 만든 출발 상태, (10,10) 도착, 명령 창). lua/dq4kind14probe.lua 가
lua/dq4bg3slotwarp.lua 를 감싸 프레임마다 적는다. 맵마다 같은 명령을 두 번 돌려 두 기록이 같아야 한다(둘 다 가진
프레임까지, same_runs).
--layout 은 대기열 변수 배치를 고른다: old 는 변수가 사본 안(7E:3D5A~)에 있는 배치, new 는 7E:A976~ 배치(지금
dq4windowname.asm). 판정은 new 에만 더한다: 열 맵 모두에서 dq4bg3slotcheck 의 판정(요청한 맵에 도착·자리·보임·창이
버퍼와 같음)이 맞고, 뱅크 03 이 사본을 쓰고, 그 밖의 코드는 CPU 로 사본을 쓰지 않고, 사본을 쓴 뒤로는 WRAM
포트($2180)나 쓰기 콜백에 걸리지 않는 길(unseen)로도 사본이 바뀌지 않아야 한다(judge).

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
KIND = 14
SLOT_TABLE, COUNT_TABLE = 0x03D9A0, 0x03D965      # 종류별 사본 시작 워드, 종류별 돌릴 타일 수(워드의 낮은 바이트)
COPY = (0x3D14, 0x3E73)
ROUNDS = 2
NAMES = ('defer', 'rd', 'count', 'off', 'left', 'head', 'len', 'stale', 'stale2')
LAYOUT = {
    'old': {'defer': (0x3D5A, 1), 'rd': (0x3D5C, 2), 'count': (0x3D62, 1), 'off': (0x3D64, 2), 'left': (0x3D66, 2),
            'head': (0x3D68, 2), 'len': (0x3D6A, 2), 'stale': (0x3DCB, 1), 'stale2': (0x3DCD, 1)},
    'new': {'defer': (0xA976, 1), 'rd': (0xA978, 2), 'count': (0xA97E, 1), 'off': (0xA980, 2), 'left': (0xA982, 2),
            'head': (0xA984, 2), 'len': (0xA986, 2), 'stale': (0xA9E7, 1), 'stale2': (0xA9E9, 1)},
}


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def copy_range(rom):
    """롬의 종류 KIND 사본 (시작, 끝) WRAM 주소."""
    o = lorom(SLOT_TABLE) + KIND * 2
    start = rom[o] | rom[o + 1] << 8
    tiles = rom[lorom(COUNT_TABLE) + KIND * 2]
    return start, start + tiles * 32 - 1


def parse(text):
    """kind14.txt → {frames: [{frame, w03, wother, wport, vars}], unseen: [frame], copies: [(frame, bytes)],
    vmadd: [(frame, [(VRAM 주소, PC)])], entries: [(frame, [(VRAM 주소, Y, 머리)])], tmdiff: [(frame, 수, 첫)]}."""
    out = {'frames': [], 'unseen': [], 'copies': [], 'vmadd': [], 'entries': [], 'tmdiff': []}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        f = int(parts[0])
        if parts[1] == 'copy':
            out['copies'].append((f, bytes.fromhex(parts[2])))
        elif parts[1] == 'unseen':
            out['unseen'].append(f)
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
                                  'wport': int(kv.get('wport', 0)), 'pb': [x for x in kv.get('pb', '').split('/') if x],
                                  'vars': {k: int(v, 16) for k, v in vs.items()}})
    return out


def named(layout, raw):
    """{주소 16진: 값} → {이름: 값}."""
    return {k: raw.get(f'{a:04X}') for k, (a, _) in LAYOUT[layout].items()}


def at_copy(layout, copy, rng=COPY):
    """사본 바이트 가운데 그 layout 의 변수 자리에 든 값(사본 밖 변수는 없음)."""
    got = {}
    for k, (a, n) in LAYOUT[layout].items():
        if rng[0] <= a and a + n - 1 <= rng[1]:
            o = a - rng[0]
            got[k] = int.from_bytes(copy[o:o + n], 'little')
    return got


def judge(rec):
    """new 배치에 더하는 판정: 뱅크 03 이 사본을 쓰고, 뱅크 03 밖 코드는 어느 때든 CPU 로 그 자리를 쓰지 않고,
    사본을 쓴 뒤로는 WRAM 포트($2180)로도 쓰기 콜백에 걸리지 않는 길로도 그 자리가 바뀌지 않음. 사본을 쓰기 전의
    포트 쓰기(맵을 불러오며 WRAM 을 지우는 DMA)는 사본이 덮으므로 판정하지 않는다."""
    bad = []
    if not rec['copies']:
        return ['뱅크 03 이 종류 14 사본을 쓰지 않음']
    start = rec['copies'][0][0]
    other = [r['frame'] for r in rec['frames'] if r['wother']]
    if other:
        bad.append(f'뱅크 03 밖 코드가 사본 자리를 씀(프레임 {other[:4]})')
    port = [r['frame'] for r in rec['frames'] if r['wport'] and r['frame'] > start]
    if port:
        bad.append(f'사본을 쓴 뒤 WRAM 포트 $2180 으로 사본 자리를 씀(프레임 {port[:4]})')
    unseen = [f for f in rec['unseen'] if f > start]
    if unseen:
        bad.append(f'사본을 쓴 뒤 쓰기 콜백에 걸리지 않은 사본 변화(프레임 {unseen[:4]})')
    return bad


def same_runs(texts):
    """두 기록이 둘 다 가진 프레임까지 같은지. dq5warp 가 끝낼 때 emu.stop 이 듣기까지 한 프레임쯤 차이가 나서,
    마지막 프레임 번호가 작은 쪽까지만 견준다."""
    def last(t):
        nums = [int(x.split(None, 1)[0]) for x in t.splitlines() if x.strip()]
        return max(nums, default=0)
    end = min(last(t) for t in texts)
    cut = [[x for x in t.splitlines() if x.strip() and int(x.split(None, 1)[0]) <= end] for t in texts]
    return all(c == cut[0] for c in cut[1:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--layout', choices=tuple(LAYOUT), default='new')
    ap.add_argument('--maps', default=','.join(MAPS))
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--entry', default='', help='대기열 항목 하나를 보내는 $2116 쓰기의 PC 아래 16비트(16진, 뱅크 60). '
                    '주면 항목마다 VRAM 주소·항목 자리·머리를 적는다. 롬마다 다르다')
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
    rng = copy_range(rom.read_bytes())
    state = dq4freshstate.make(mesence, rom, out / 'start')
    vars_ = ','.join(f'{x:04X}:{n}' for x, n in LAYOUT[a.layout].values())
    running, folders = [], {}
    maps = a.maps.split(',')
    for mp in maps:
        for k in range(ROUNDS):
            folder = out / mp.replace('/', '-') / f'r{k}'
            folder.mkdir(parents=True)
            folders[mp, k] = folder
            env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(state), TO=f'{mp},10,10',
                       SETTLE='60', TEST=bc.TEST, MAXF='2400', VARS=vars_, ENTRY=a.entry or '0',
                       COPY=f'{rng[0]:04X}-{rng[1]:04X}',
                       NEXT=str(HERE / 'lua/dq4bg3slotwarp.lua'), WARPLUA=str(ROOT / 'sfc/dq5/tools/lua/dq5warp.lua'))
            running.append(mesen.Runner(mesence, rom, PROBE, folder, tag='kind14',
                                        extra=('--Snes.RamPowerOnState=AllZeros',), env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            if len(running) >= a.jobs:
                running.pop(0).wait()
    for p in running:
        p.wait()
    rows, ok = [], True
    for mp in maps:
        texts = [(folders[mp, k] / 'kind14.txt').read_text() if (folders[mp, k] / 'kind14.txt').exists() else ''
                 for k in range(ROUNDS)]
        folder = folders[mp, 0]
        rec = parse(texts[0])
        records, arrival = bc.records_of(folder), bc.arrival_of(folder)
        slot = records[-1]['0725'] if records else None
        first = rec['copies'][0] if rec['copies'] else None
        row = {'map': mp, 'arrival': arrival[0] if arrival else None, '0725': slot,
               'copy_range': f'{rng[0]:04X}-{rng[1]:04X}',
               'copy_frame': first[0] if first else None,
               'copy_vars': at_copy(a.layout, first[1], rng) if first else {},
               'copy_frames': [f for f, _ in rec['copies']],
               'unseen': rec['unseen'][:8],
               'port': [(r['frame'], r['wport'], r['pb']) for r in rec['frames'] if r['wport']][:8],
               'vmadd': [(f, [f'{x:04X}@{pc:04X}' for x, pc in xs]) for f, xs in rec['vmadd']][:12],
               'vars_after_copy': next((named(a.layout, r['vars']) for r in rec['frames']
                                        if first and r['frame'] == first[0]), None),
               'copy': first[1].hex() if first else None}
        bad = []
        if not texts[0]:
            bad.append('기록 없음')
        elif not same_runs(texts):
            bad.append(f'같은 명령 {ROUNDS}번의 기록이 다름')
        if a.layout == 'new':
            bad += bc.judge(mp, arrival, records) + judge(rec)
        row['problems'] = bad
        ok &= not bad
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'copy'}, ensure_ascii=False))
    (out / 'report.json').write_text(json.dumps({'layout': a.layout, 'status': 'passed' if ok else 'failed',
                                                 'maps': rows}, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(rows)}맵, {"통과" if ok else "실패"}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
