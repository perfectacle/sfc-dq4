"""전투 메시지 한글 검사(MesenCE 헤드리스). 1장 상태에서 탑 위 보스(39/04)와 싸우며, 메시지를 띄울 때마다(24:8C39) 번호를
검사할 번호로 바꿔 끼워 끝까지 찍히는지 보고 화면을 남긴다(lua/dq4battlemsgswap.lua).

  - 주인공 HP 999·이름 「라이언」을 SET 으로 두고 A 를 30프레임마다 눌러 싸운다. 이름·숫자 자리는 그때의 큐 값이 들어간다.
  - 한 번 실행에 BATCH 개씩 넣는다. 바꿔 넣은 번호 뒤로 다음 메시지가 오지 않고 실행이 끝나면 그 번호를 멈춤으로 보고,
    남은 번호는 다음 묶음으로 넘긴다.
  - 결과: OUT/report.json(보인 번호·멈춘 번호·못 닿은 번호), OUT/sheet-NN.png(메시지 창 모음).

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4battlemsgcheck.py --rom work/x/ch1.sfc --state work/state/ch1.mss --out work/battlemsgcheck
형식은 sfc/dq4/docs/dq4-battle-text-format.md 「검증」.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4battlemsg  # noqa: E402
import dq4battletexts  # noqa: E402
import dq4npccheck as nc  # noqa: E402

SWAP_LUA = HERE / 'lua' / 'dq4battlemsgswap.lua'
WARP_LUA = HERE.parents[1] / 'dq5' / 'tools' / 'lua' / 'dq5warp.lua'
BOSS_CELL = '39/04,46,22'
# 주인공 이름 「라이언」(이름 입력 표시 바이트), HP 999
HERO = '2001=8B;2002=2F;2003=93;2004=3C;2005=92;2006=13;2042=E7;2043=03;204E=E7;204F=03'
TAPS = 'up:20,idle:10,a:4,wait:40,' + ','.join(['a:4,wait:30'] * 220)
BATCH = 40
# 이 장면에서 원래 코드가 끝내지 못하는 번호. 원문 가나로 두어도 같다(검사의 바꿔 끼우기 탓)
SKIP = {0x004: '{EC}(합류하는 동료 이름)가 동료가 끼어드는 장면 밖에서는 멈춤'}
MAXF = 9000


def run(mesence, libdir, rom, state, out, ids):
    out.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ('POKE', 'ROMPATCH', 'BATTLE', 'FIELD')}
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(out), DRIVER=str(WARP_LUA),
               WARPEXIT=f'{nc.warp_exit(rom):X}', DP86OK=nc.dp86_allowed(rom), TO=BOSS_CELL, SET=HERO,
               SETTLE='120', TEST=TAPS, MAXF=str(MAXF), SWAP=','.join(f'{n:03X}' for n in ids),
               POOLCODES=','.join(f'{c:02X}' for c in dq4battlemsg.CODES))
    with (out / 'mesen.log').open('w') as log:
        try:
            subprocess.run([str(mesence), '--testrunner', str(rom), str(SWAP_LUA), '--Snes.DisableFrameSkipping=true'],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
        except subprocess.TimeoutExpired:
            pass
    path = out / 'swap.txt'
    rows = [line.split() for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return [(int(f), int(n, 16)) for f, n in rows]


def sheet(folder, ids, path):
    from PIL import Image
    shots = [(n, folder / f'm{n:03X}.png') for n in ids if (folder / f'm{n:03X}.png').exists()]
    if not shots:
        return
    w, h = 224, 62
    img = Image.new('RGB', (w * 2, h * ((len(shots) + 1) // 2)))
    for k, (_, p) in enumerate(shots):
        img.paste(Image.open(p).crop((16, 150, 16 + w, 150 + h)), ((k % 2) * w, (k // 2) * h))
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--state', required=True, type=Path, help='1장 맵에 선 세이브스테이트')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--ids', help='검사할 번호(16진, 쉼표). 없으면 dq4battletexts 의 모든 번호')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    args = ap.parse_args()
    if not args.mesence or not os.environ.get('LIBDIR'):
        raise SystemExit('MESENCE 와 LIBDIR 을 주세요')
    rom, state, out = args.rom.resolve(), args.state.resolve(), args.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    todo = [int(x, 16) for x in args.ids.split(',')] if args.ids else sorted(set(dq4battletexts.SOURCE) - set(SKIP))
    shown, stalled, rounds = [], [], 0
    while todo and rounds < 20:
        batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
        with ThreadPoolExecutor(args.jobs) as ex:
            results = list(ex.map(lambda kb: run(Path(args.mesence), Path(os.environ['LIBDIR']), rom, state,
                                                 out / f'r{rounds:02d}-{kb[0]:02d}', kb[1]), enumerate(batches)))
        todo = []
        for batch, swaps in zip(batches, results):
            done = [n for _, n in swaps]
            shown += done[:-1]
            if len(done) < len(batch):
                # 마지막으로 바꿔 넣은 번호 뒤로 메시지가 더 오지 않았다
                if done:
                    stalled.append(done[-1])
                todo += batch[len(done):]
            elif done:
                shown.append(done[-1])
        rounds += 1
    for d in sorted(out.glob('r*')):
        ids = [n for line in (d / 'swap.txt').read_text().splitlines() if line.strip()
               for n in [int(line.split()[1], 16)]] if (d / 'swap.txt').exists() else []
        sheet(d, ids, out / f'sheet-{d.name}.png')
    used = [int(line.split()[1]) for d in out.glob('r*') if (d / 'used.txt').exists()
            for line in (d / 'used.txt').read_text().splitlines() if line.strip()]
    report = {'status': 'passed' if not stalled and not todo else 'failed',
              'shown': len(shown), 'stalled': [f'{n:03X}' for n in stalled], 'unreached': [f'{n:03X}' for n in todo],
              'skipped': {f'{n:03X}': why for n, why in SKIP.items()},
              'pool': len(dq4battlemsg.CODES), 'pool_used_max': max(used, default=0)}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
