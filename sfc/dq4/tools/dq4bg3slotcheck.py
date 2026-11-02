"""BG3 타일맵 옮기기(dq4bg3slot.py)를 MesenCE 로 검사한다. 롬으로 만든 출발 상태(dq4freshstate)에서 실내 맵마다
순간이동해 명령 창을 열고, 맵마다 다음이 모두 맞으면 통과다.

  도착     dq5warp 가 도착을 적음. 게임이 도착하자마자 다른 맵으로 옮기면(33/01 → 33/00) 도착한 맵으로 판정
  자리     끝에서 BG3SC 그림자 $0725 가 dq4bg3slot 의 자리(필드꼴 맵($BE bit7 = 0)은 FIELD, MAP_SLOTS, 나머지 실내
           맵은 INTERIOR)
  보임     $2109 에 든 자리(7E:1ABC ^ 1C)가 $0725 와 같음
  창       그 자리 VRAM 타일맵이 0 아닌 바이트를 갖고, 끝 VSBUF_RECORDS 기록 가운데 하나에서 게임의 타일맵 버퍼
           7E:5000 과 한 바이트도 다르지 않음(게임이 버퍼를 고친 프레임과 NMI 가 보내는 프레임 사이에 잰 기록은
           몇 바이트 다를 수 있다. 다른 곳이 자리를 덮으면 계속 다름)

출발 상태가 서 있는 맵(배 선실 상태면 17/00)은 같은 맵으로 순간이동하면 맵 번호가 바뀌지 않아 도착을 알 수 없다.
그래서 HOP 맵에 먼저 가서 세이브스테이트를 남기고, 거기서 「어디서나」(ANYWHERE) 로 그 맵에 간다.

--old 를 주면 그 롬도 같은 맵에 돌려 끝 화면이 다른 영역을 적는다(판정에는 쓰지 않음). menu 패치를 얹은 롬과 얹기 전
롬은 명령 창 글자를 한글로 바꿨고 상태 창 이름을 다른 길로 찍으므로 창 화면이 늘 다르다.

  MESENCE=... uv run --locked python sfc/dq4/tools/dq4bg3slotcheck.py --rom 롬 --out 새폴더 \\
      [--old 비교롬] [--maps 01/00,17/00] [--jobs 2]

맵 목록은 DQ5 트랙 dq5hangul.py slots(실내 맵 364개), 도착 칸은 (10,10) 이다(DQ5 트랙 실측과 같은 방법).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools')]

import dq4bg3slot  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4mesen as mesen  # noqa: E402

TEST = 'wait:90,a:4,wait:90'
START_MAP = {'ship': '17/00'}
# 출발 맵으로 가기 전에 들르는 맵과 칸. 자리가 INTERIOR 가 아니라 돌아올 때 자리를 다시 골라야 하고, 「어디서나」 가
# 발밑 트리거를 밟도록 아래 칸이 트여 있어야 한다.
HOP = '01/01,13,8'
VSBUF_RECORDS = 3
ARRIVED = re.compile(r'arrived map (\S+) (field|cell)')


def interior_maps():
    import dq5hangul
    return [f'{bc:02X}/{bd:02X}' for bc, bd, _ in dq5hangul.slot_table((ROOT / 'rom' / 'dq5.sfc').read_bytes())]


def expected_slot(mp):
    bc, bd = (int(x, 16) for x in mp.split('/'))
    return next((slot for b, d, slot in dq4bg3slot.MAP_SLOTS if (b, d) == (bc, bd)), dq4bg3slot.INTERIOR)


def parse_bg3(line):
    """dq4bg3slotwarp.lua 의 한 줄 → {'map', '0725', 'shown', 'nz', 'vsbuf', 'old'}(숫자는 int)."""
    f = line.split()
    kv = dict(x.split('=') for x in f if '=' in x)
    return {'map': f[2], '0725': int(kv['0725'], 16), 'shown': int(kv['shown'], 16), 'nz': int(kv['nz']),
            'vsbuf': int(kv['vsbuf']), 'old': int(kv['old'])}


def judge(mp, arrival, records):
    """맵 mp 의 문제 목록(빈 목록이면 통과). arrival 은 (도착한 맵, 'field'|'cell') 또는 None, records 는 bg3.txt 기록
    (parse_bg3) 목록."""
    if arrival is None:
        return ['도착 못 함']
    here, kind = arrival
    tail = [r for r in records if r['map'] == here][-VSBUF_RECORDS:]
    if not tail or records[-1]['map'] != here:
        return [f'끝 기록이 {here} 가 아님({records[-1]["map"] if records else None})']
    last = tail[-1]
    want = dq4bg3slot.FIELD if kind == 'field' else expected_slot(here)
    bad = []
    if last['0725'] != want:
        bad.append(f'$0725={last["0725"]:02X}, 바라는 자리 {want:02X}')
    if last['shown'] != last['0725']:
        bad.append(f'보이는 자리 {last["shown"]:02X} ≠ $0725 {last["0725"]:02X}')
    if last['nz'] == 0:
        bad.append('타일맵이 비어 있음')
    if min(r['vsbuf'] for r in tail):
        bad.append(f'타일맵이 버퍼와 {last["vsbuf"]}바이트 다름')
    return bad


def records_of(folder):
    p = folder / 'bg3.txt'
    return [parse_bg3(x) for x in p.read_text().split('\n') if x] if p.exists() else []


def arrival_of(folder):
    p = folder / 'warp.txt'
    found = ARRIVED.findall(p.read_text()) if p.exists() else []
    return found[-1] if found else None


def run(mesence, libdir, rom, state, target, folder, **extra):
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(state),
               TO=target if target.count(',') else f'{target},10,10',
               SETTLE='60', TEST=TEST, MAXF='2400', WARPLUA=str(ROOT / 'sfc/dq5/tools/lua/dq5warp.lua'))
    env.update(extra)
    return mesen.Runner(mesence, rom, HERE / 'lua/dq4bg3slotwarp.lua', folder, tag='bg3',
                        extra=('--Snes.RamPowerOnState=AllZeros',), env=env, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)


def hop_state(mesence, libdir, rom, state, folder):
    """HOP 에 도착해 남긴 세이브스테이트. 만들지 못하면 None."""
    save = folder / 'hop.mss'
    # dq5warp 의 SAVE 는 SHOT_DIR 안의 파일 이름이다
    run(mesence, libdir, rom, state, HOP, folder, TEST='', SAVE=save.name).wait()
    return save if save.exists() and arrival_of(folder) else None


def run_all(mesence, libdir, roms, maps, out, jobs):
    """roms {종류: 롬} 마다 maps 를 돌린다. 출발 맵은 HOP 를 거쳐 간다."""
    queue = []
    for kind, rom in roms.items():
        state = dq4freshstate.make(mesence, rom, out / f'start-{kind}')
        start = START_MAP.get(dq4freshstate.kind_of(rom.read_bytes()))
        for mp in maps:
            folder = out / mp.replace('/', '-') / kind
            if mp == start:
                hop = hop_state(mesence, libdir, rom, state, out / mp.replace('/', '-') / f'{kind}-hop')
                if hop:
                    queue.append((rom, hop, mp, folder, {'ANYWHERE': '1'}))
            else:
                queue.append((rom, state, mp, folder, {}))
    running = []
    for rom, state, mp, folder, extra in queue:
        running.append(run(mesence, libdir, rom, state, mp, folder, **extra))
        if len(running) >= jobs:
            running.pop(0).wait()
    for p in running:
        p.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True, help='BG3 타일맵을 옮긴 롬(menu.sfc 이후 단계)')
    ap.add_argument('--old', type=Path, help='끝 화면을 견줄 롬(판정에 쓰지 않음)')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--maps')
    ap.add_argument('--jobs', type=int, default=2)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists():
        ap.error('--out 은 아직 없는 폴더를 주세요')
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    maps = a.maps.split(',') if a.maps else interior_maps()
    roms = {'new': a.rom.resolve(), **({'old': a.old.resolve()} if a.old else {})}
    run_all(mesence, libdir, roms, maps, out, a.jobs)
    from PIL import Image, ImageChops
    rows, failed = [], 0
    for mp in maps:
        d = out / mp.replace('/', '-')
        records, arrival = records_of(d / 'new'), arrival_of(d / 'new')
        last = records[-1] if records else None
        bad = judge(mp, arrival, records)
        if arrival and arrival[0] != mp and not bad:
            bad_note = f' ({arrival[0]} 로 이어짐)'
        else:
            bad_note = ''
        failed += bool(bad)
        screen = ''
        if a.old and (d / 'old/end.png').exists() and (d / 'new/end.png').exists():
            with Image.open(d / 'old/end.png') as x, Image.open(d / 'new/end.png') as y:
                box = ImageChops.difference(x.convert('RGB'), y.convert('RGB')).getbbox()
            screen = f' 화면 차이 {box}' if box else ' 화면 같음'
        state = '' if last is None else f' $0725={last["0725"]:02X} nz={last["nz"]} vsbuf={last["vsbuf"]}'
        rows.append(f'{mp} {"통과" + bad_note if not bad else "실패: " + "; ".join(bad)}{state}{screen}')
    (out / 'report.txt').write_text('\n'.join(rows) + '\n')
    print('\n'.join(rows))
    print(f'{len(maps)}맵, 실패 {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
