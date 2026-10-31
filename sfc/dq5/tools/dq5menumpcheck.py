"""dq5tables.py 로 주문 전투 MP 를 바꾸면 주문 목록 창의 MP 칸(21:9BB4)도 따라 써지는지 MesenCE 에서 본다.

시험 롬 mp: dq5tables.py 로 ホイミ(27) MP 3 → 9, メラ(01) MP 2 → 0.
      mpfx: mp 에 dq5spellfx.py 로 ホイミ 의 필드 처리기(11:84FA) MP 도 9 로.
장면
  field-*   배 선실에서 주인공에게 ホイミ 를 배우게 하고(LEARNED) じゅもん 창을 연 뒤 ホイミ 를 외운다. 창을 그리는
            21:9BAD 가 21:9BDB(ホイミ 칸)에서 읽은 값과 외운 뒤 남은 MP(100 에서 시작)를 원본 롬과 견준다. 120프레임 화면도 남긴다.
            mp 롬은 창이 9 를 보여도 필드에서 외우면 필드 처리기 즉값(3)만큼 빼고, mpfx 롬은 9 를 뺀다
  filter-*  dq5aicheck.py 의 AI 장면(주인공·ホイミン·マーリン 과 슬라임 셋)을 그 롬으로 시작해 작전 3(じゅもんつかうな)으로
            두고, マーリン 의 メラ 가 MP 거름(21:DA58) 뒤 후보 넣기 21:DA77 에 닿은 횟수를 원본 롬과 견준다

  MESENCE=… python sfc/dq5/tools/dq5menumpcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5aicheck import ai_run, prepare
from dq5progresscheck import command, environment, require, run, save_json
from dq5spellgrowcheck import FIELD_USE

HERE = Path(__file__).resolve().parent
EDIT = {'format': 'dq5tables/1', 'spells': [{'id': '01', 'MP': 0}, {'id': '27', 'MP': 9}]}
HOIMI_MENU = 0x219BB4 + 0x27


def field(name, rom, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(MODE='field', DRIVER=str(HERE / 'lua/dq5msg.lua'), LEARNED='010300', MAXF='650', PRE=FIELD_USE,
               SHOTS='120', READS=f'{HOIMI_MENU:06X}', EXECS='219BAD')
    run(mesence, rom, HERE / 'lua/dq5spellgrowcheck.lua', dest, env)
    text = (dest / 'observed.txt').read_text()
    ram = (dest / 'final.wram').read_bytes()
    reads = sorted({int(v, 16) for v in re.findall(rf'read {HOIMI_MENU:06X}=(\w\w) pc=219BB1', text)})
    return {'menu_read': reads, 'mp_after': int.from_bytes(ram[0x2044:0x2046], 'little')}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/menumpcheck')
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
        save_json(out / 'mp.json', EDIT)
        command('dq5tables.py', original, 'patch', out / 'mp.json', '-o', out / 'mp.dq5patch.json')
        command('dq5tables.py', original, 'check', out / 'mp.json')
        command('dq5build.py', original, 'build', out / 'mp.dq5patch.json', '-o', out / 'mp.sfc')
        save_json(out / 'fx.json', {'format': 'dq5spellfx/1', 'field_handlers': [{'handler': '84FA', 'mp': 9}]})
        command('dq5spellfx.py', original, 'patch', out / 'fx.json', '-o', out / 'fx.dq5patch.json')
        command('dq5build.py', original, 'build', out / 'mp.dq5patch.json', out / 'fx.dq5patch.json', '-o',
                out / 'mpfx.sfc')
        roms = {'original': original, 'mp': out / 'mp.sfc', 'mpfx': out / 'mpfx.sfc'}
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        battles = {k: prepare(roms[k], state, out, mesence, libdir, f'state-{k}') for k in ('original', 'mp')}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            fields = {k: pool.submit(field, f'field-{k}', rom, state, out, mesence, libdir) for k, rom in roms.items()}
            filters = {k: pool.submit(ai_run, f'filter-{k}', roms[k], 3, '', battles[k], out, mesence, libdir, '21DA77')
                       for k in ('original', 'mp')}
            seen = {k: f.result() for k, f in fields.items()}
            for f in filters.values():
                f.result()
        for k in ('original', 'mp'):
            text = (out / f'filter-{k}' / 'decisions.txt').read_text()
            seen[k]['mera_passes'] = len(re.findall(r'probe 21DA77 dp42=02 \w\w 00 00 01 ', text))
        checks = {
            'field-menu': seen['original']['menu_read'] == [3] and seen['mp']['menu_read'] == [9]
            and seen['mpfx']['menu_read'] == [9],
            'field-cast': seen['original']['mp_after'] == 97 and seen['mp']['mp_after'] == 97
            and seen['mpfx']['mp_after'] == 91,
            'filter': seen['original']['mera_passes'] == 0 and seen['mp']['mera_passes'] > 0,
        }
        save_json(out / 'results.json', {'seen': seen, 'checks': checks})
        print(json.dumps(seen, ensure_ascii=False))
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}건 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
