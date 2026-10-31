"""무리 값($1009~$100C → 7E:0C24)이 부르기(같은 몬스터 AB, 22:D1A9)에서 어떻게 세어지는지 MesenCE 에서 잰다.

첫 필드 이벤트 전투를 スライム 2 로 붙이고 그 무리 값을 00·01·02·80 으로 둔다(dq5warp.lua 의 BATTLE="00:2:값").
スライム 의 행동을 모두 AB(같은 몬스터 부르기)로 바꾸고(dq5scenes.actions, 주인공 HP 200 은 dq5scenes.HP200)
슬라임 둘의 HP(7E:07C2·07D2)를 붙잡아 둔다. 22:D1C0 은 무리 값이 0 이거나 음수일 때만 부르기를 받아들이므로(코드 읽기)
값 01·02 는 「たすけは こなかった」(04A)로 마릿수가 그대로이고, 00·80 은 「あらわれた」(04B)로 늘어야 한다.
메시지마다 7E:0C24(무리 값)·0C15(마릿수)를 dq5battle.lua 의 PEEK 로 적는다.
  MESENCE=… python sfc/dq5/tools/dq5groupvaluecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import dq5scenes as S
from dq5progresscheck import environment, require, run, save_json

HERE = Path(__file__).resolve().parent
VALUES = ('00', '01', '02', '80')
PATCH = S.HP200 + ';' + S.actions(0x00, 0xAB)


def scene(rom, value, state, out, mesence, libdir):
    dest = out / value
    env = environment(libdir, state, dest / 'state')
    env.update(FIELD='341,56', BATTLE=f'00:2:{value}', SETTLE='300', SAVE='battle.mss', MAXF='1800', ROMPATCH=PATCH)
    dest.mkdir()
    run(mesence, rom, HERE / 'lua/dq5warp.lua', dest / 'state', env)
    require((dest / 'state/battle.mss').is_file(), f'{value}: 전투 상태가 저장되지 않음')
    env = environment(libdir, dest / 'state/battle.mss', dest / 'battle')
    env.update(MAXF='1500', ROMPATCH=PATCH, POKE='7E07C2=FF;7E07C3=00;7E07D2=FF;7E07D3=00', PEEK='7E0C24:1,7E0C15:1')
    run(mesence, rom, HERE / 'lua/dq5battle.lua', dest / 'battle', env)
    text = (dest / 'battle/battle.txt').read_text(encoding='utf-8')
    return [(m, int(v, 16), int(c, 16)) for m, v, c in re.findall(r'msg ([0-9A-F]{3}) 7E0C24=(\w\w) 7E0C15=(\w\w)', text)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/groupvaluecheck')
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
            futures = {v: pool.submit(scene, rom, v, state, out, mesence, libdir) for v in VALUES}
            seen = {v: f.result() for v, f in futures.items()}
        checks = {}
        for v, rows in seen.items():
            calls = [m for m, _, _ in rows if m in ('04A', '04B')]
            counts = [c for _, _, c in rows]
            joins = int(v, 16) == 0 or int(v, 16) & 0x80
            checks[v] = bool(calls) and all(r[1] == int(v, 16) for r in rows) and (
                set(calls) == {'04B'} and max(counts) > 2 if joins else set(calls) == {'04A'} and set(counts) == {2})
            print(f'무리 값 {v}: 부르기 {" ".join(calls)}, 마릿수 {min(counts)}~{max(counts)}')
        save_json(out / 'results.json', {'messages': seen, 'checks': checks})
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
