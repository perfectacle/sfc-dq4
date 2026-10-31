"""물건 k2 bit4(dq5tables.py 의 「그룹무작위」)를 슬라임 셋 무리에서 MesenCE 로 잰다.

전투에서 물건을 적에게 쓰면 `20:9531`·`956B` 가 그룹을 고른 뒤 `BRK #94 0E` 로 이 비트를 읽고, 켜져 있으면 `20:95F1`
(대상 바이트 $1037 bit3-6 에 그룹 번호), 꺼져 있으면 `20:95EE` → `20:A917` 로 그 그룹의 살아 있는 한 마리를 난수로
골라 그 번호를 넣는다(코드 읽기). 이름과 달리 켜진 쪽이 그룹을 그대로 대상으로 둔다(그룹을 치는 いかずちのつえ 등). やくそう(A1)를 적쪽(k2 bit5)으로 바꾸고 이 비트만 1·0 으로 둔 롬 둘로,
첫 필드 이벤트 전투를 スライム 3 으로 붙인 세이브스테이트에서 명령 앞 기다림을 바꿔 가며(난수가 달라짐) 쓰고
메시지마다 $1037 을 적는다(dq5battle.lua 의 PEEK).
같은 장면에서 물건 k4 하위 6비트(dq5tables.py 의 「k4하위」)도 본다. 전투에서 물건을 쓰면 20:B9F9 가 BRK #94 0F 로 이 값을
읽어, 06 이 아니면 27:81D0 + 값 × 2 의 두 바이트(전투 메시지 번호, 0 이면 없음)를 띄운다(코드 읽기). やくそう(A1)는 07
(「…を つかった！」 0D3)이고, 01 로 바꾼 롬은 0CC 「…を どうぐとして つかってみた！」 여야 한다.
  MESENCE=… python sfc/dq5/tools/dq5grouptargetcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5progresscheck import command, environment, require, run, save_json

HERE = Path(__file__).resolve().parent
WAITS = (0, 5, 11, 17, 23, 31)
# dq5tablecheck.py 의 BATTLE_ITEM 과 같은 입력: どうぐ → 첫 물건 → 쓰는 사람 → 대상 그룹.
PRESS = 'a:4,wait:30,down:4,wait:10,down:4,wait:10,a:4,wait:40,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'


def prepare(original, state, out, mesence, libdir):
    dest = out / 'battle-state'
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', BATTLE='00:3', SETTLE='300', SAVE='battle.mss', MAXF='1800')
    run(mesence, original, HERE / 'lua/dq5warp.lua', dest, env)
    require((dest / 'battle.mss').is_file(), '슬라임 셋 전투 상태가 저장되지 않음')
    return dest / 'battle.mss'


def build(original, out, name, fields):
    source = out / f'{name}.json'
    save_json(source, {'format': 'dq5tables/1', 'items': [{'id': 'A1', **fields}]})
    command('dq5tables.py', original, 'patch', source, '-o', out / f'{name}.patch.json')
    command('dq5build.py', original, 'build', out / f'{name}.patch.json', '-o', out / f'{name}.sfc')
    return out / f'{name}.sfc'


def use(rom, name, wait, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(DRIVER=str(HERE / 'lua/dq5battle.lua'), MAXF='320', POKE='7E2058=A1;7E2042=05', LOOP='wait:500',
               PEEK='7E1037:1', PRE=(f'wait:{wait},' if wait else '') + PRESS)
    run(mesence, rom, HERE / 'lua/dq5battle.lua', dest, env)
    rows = re.findall(r'msg ([0-9A-F]{3}) 7E1037=([0-9A-F]{2})', (dest / 'battle.txt').read_text(encoding='utf-8'))
    require(rows, f'{name}: 전투 메시지가 없음')
    return int(rows[0][1], 16), [m for m, _ in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/grouptargetcheck')
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
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        battle = prepare(original, state, out, mesence, libdir)
        roms = {bit: build(original, out, f'bit{bit}', {'적쪽': 1, '그룹무작위': bit}) for bit in (0, 1)}
        roms['k4'] = build(original, out, 'k4', {'k4하위': 1})
        roms['original'] = original
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {(bit, w): pool.submit(use, roms[bit], f'bit{bit}-wait{w}', w, battle, out, mesence, libdir)
                       for bit in (0, 1) for w in WAITS}
            words = {k: pool.submit(use, roms[k], k, 0, battle, out, mesence, libdir) for k in ('original', 'k4')}
            seen = {k: f.result()[0] for k, f in futures.items()}
            said = {k: f.result()[1] for k, f in words.items()}
        # $1037 bit3-6 = 대상 몬스터 번호(무리 안 0~2), bit7·bit0 = 적 한 마리.
        targets = {bit: [seen[(bit, w)] >> 3 & 0x0F for w in WAITS] for bit in (0, 1)}
        checks = {'bit1-fixed': set(targets[1]) == {0},
                  'bit0-random': len(set(targets[0])) > 1 and set(targets[0]) <= {0, 1, 2},
                  'k4-message': '0D3' in said['original'] and '0CC' not in said['original']
                  and '0CC' in said['k4'] and '0D3' not in said['k4']}
        save_json(out / 'results.json', {'1037': {f'{b}-{w}': f'{v:02X}' for (b, w), v in seen.items()},
                                         'targets': targets, 'messages': said, 'checks': checks})
        for k, rows in said.items():
            print(f'k4하위 {"원래(07)" if k == "original" else "01"}: 전투 메시지 {" ".join(rows)}')
        for bit in (1, 0):
            print(f'k2 bit4 = {bit}: 기다림 {list(WAITS)} → $1037 '
                  + ' '.join(f'{seen[(bit, w)]:02X}' for w in WAITS) + f' (대상 {targets[bit]})')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}건 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
