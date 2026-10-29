"""새 행동 번호(C6~)의 작전 AI 레코드와 갑옷 원소를 MesenCE 전투에서 원래 롬과 견준다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「행동 번호 늘리기」와 `dq5ai/1`. dq5spellgrow.py 로 새 번호 넷을 더한다.
  C6  メラ(01) 를 베낀 주문. マーリン(동료 몬스터 04) 의 전투 목록에서 メラ 칸을 C6 으로(dq5learnwrite.py --spells-from)
  C7  몬스터 メラミ(3A) 를 베끼고 element 01(メラ)
  C8  같은 것을 element 40(イオ, 갑옷 항목에 없음)
  C9  같은 것을 element 없이
이름은 dq5namewrite.py --append 로 붙인다. 롬은 셋이다.
  none    위 넷만(행동 AI 레코드 C6 은 원래 값 11 00 30 00 FF)
  copy    none + dq5aiwrite.py 로 C6 레코드를 メラ 에서 베낌
  strong  none + C6 레코드를 メラ 에서 베끼고 기대 값 255

  ai      dq5aicheck.py 와 같은 장면(주인공·ホイミン·マーリン 과 슬라임 셋, 작전 0). 20:8846 에서 고른 행동을 모아
          원본 롬의 차례에서 01 을 C6 으로 바꾼 것과 copy 롬의 차례가 같은지, none 롬이 C6 을 고르지 않는지 본다
  armor   슬라임이 まほうのよろい 를 입은 주인공에게 3A·C7·C8·C9. 20:AC27 의 원소, 20:AC54·AC57 의 빼기 앞뒤를 견준다

원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5battlegrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5aicheck import ARMOR_SCENE, MARLIN, ai_run, prepare, scene_run
from dq5learnwrite import FORMAT as LEARN_FORMAT, dump as learn_dump
from dq5map import Rom
from dq5namewrite import read_tables
from dq5progresscheck import command, require, save_json

AT = '6E:8000'
NAMES_AT = '6F:8000'
SPELLS = (('C6', '01', None), ('C7', '3A', '01'), ('C8', '3A', '40'), ('C9', '3A', None))
MARLIN_KIND, MERA = 4, 0x01
AI = {'copy': {'action': 'C6', 'copy': '01'}, 'strong': {'action': 'C6', 'copy': '01', 'value': 255}}
EXECS = '20ABF4,20AC27,20AC54,20AC57,20AC88'


def build(original, out):
    data = original.read_bytes()
    names = read_tables(data)[3]
    # 21:955D 는 n 번 건너뛰므로 C6 앞의 AB~C5 에도 (빈) 이름 칸이 있어야 한다.
    blank = [{'id': n, 'bytes': []} for n in range(0xAB, 0xC6)]
    save_json(out / 'names.json', {'format': 'dq5names/1', 'tables': [{'table': 3, 'names': blank + [
        {'id': int(n, 16), 'bytes': names[int(c, 16)] + names[int(c, 16)][-1:]} for n, c, _ in SPELLS]}]})
    command('dq5namewrite.py', original, 'patch', out / 'names.json', '--at', NAMES_AT, '--append', '-o', out / 'names.patch.json')
    spells = [{'id': n, 'copy': c, 'class': 'spell', **({'element': e} if e else {})} for n, c, e in SPELLS]
    save_json(out / 'grow.json', {'format': 'dq5spellgrow/1', 'spells': spells})
    command('dq5spellgrow.py', original, 'check', out / 'grow.json', '--at', AT)
    command('dq5spellgrow.py', original, 'patch', out / 'grow.json', '--at', AT, '-o', out / 'grow.patch.json')
    command('dq5build.py', original, 'build', out / 'grow.patch.json', '-o', out / 'spells.sfc')
    marlin = next(c for c in learn_dump(Rom(data))['characters'] if c['kind'] == 'monster' and c['index'] == MARLIN_KIND)
    require(marlin['battle'].count(MERA) == 1, 'マーリン 전투 목록에 メラ 가 한 칸이 아님')
    marlin['battle'][marlin['battle'].index(MERA)] = 0xC6
    save_json(out / 'learn.json', {'format': LEARN_FORMAT, 'characters': [marlin]})
    command('dq5learnwrite.py', original, 'check', out / 'learn.json', '--spells-from', out / 'spells.sfc')
    command('dq5learnwrite.py', original, 'patch', out / 'learn.json', '-o', out / 'learn.patch.json',
            '--spells-from', out / 'spells.sfc')
    base = [out / f'{p}.patch.json' for p in ('grow', 'names', 'learn')]
    command('dq5build.py', original, 'build', *base, '-o', out / 'none.sfc', '--ips', out / 'none.ips')
    for name, row in AI.items():
        save_json(out / f'ai-{name}.json', {'format': 'dq5ai/1', 'actions': [row]})
        command('dq5aiwrite.py', original, 'check', out / f'ai-{name}.json')
        command('dq5aiwrite.py', original, 'patch', out / f'ai-{name}.json', '-o', out / f'ai-{name}.patch.json')
        command('dq5build.py', original, 'build', *base, out / f'ai-{name}.patch.json', '-o', out / f'{name}.sfc',
                '--ips', out / f'{name}.ips')


def decisions(folder):
    return re.findall(r'actor (\w\w) action (\w\w)', (folder / 'decisions.txt').read_text())


def armor_rows(text):
    """(행동, 원소, 빼기 앞, 빼기 뒤, 끝 피해) — 20:ABF4 를 지날 때마다 한 줄. 지나지 않은 자리는 None."""
    rows, cur = [], None
    for pc, a in re.findall(r'pc=(20ABF4|20AC27|20AC54|20AC57|20AC88) A=([0-9A-F]{4})', text):
        v = int(a, 16)
        if pc == '20ABF4':
            cur = [v & 0xFF, None, None, None, None]
            rows.append(cur)
        elif cur is not None:
            cur[{'20AC27': 1, '20AC54': 2, '20AC57': 3, '20AC88': 4}[pc]] = v & 0xFF if pc == '20AC27' else v
    return [tuple(r) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/battlegrowcheck')
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
        build(original, out)
        battle = prepare(original, state, out, mesence, libdir)
        roms = {'original': original, **{k: out / f'{k}.sfc' for k in ('none', *AI)}}
        armor = {'3A': original, 'C7': roms['none'], 'C8': roms['none'], 'C9': roms['none']}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ai_jobs = {k: pool.submit(ai_run, f'ai-{k}', rom, 0, '', battle, out, mesence, libdir) for k, rom in roms.items()}
            armor_jobs = {
                k: pool.submit(scene_run, f'armor-{k}', rom, dict(
                    ARMOR_SCENE, ROMPATCH=ARMOR_SCENE['ROMPATCH'].replace('3A3A3A3A3A3A', k * 6), EXECS=EXECS),
                    state, out, mesence, libdir)
                for k, rom in armor.items()}
            for job in ai_jobs.values():
                job.result()
            texts = {k: f.result() for k, f in armor_jobs.items()}
        seen = {k: decisions(out / f'ai-{k}') for k in roms}
        results, failed = {}, []

        def verdict(name, ok, **detail):
            results[name] = {'passed': bool(ok), **detail}
            if not ok:
                failed.append(name)

        mapped = [(a, 'C6' if a == MARLIN and act == f'{MERA:02X}' else act) for a, act in seen['original']]
        marlin = {k: [act for a, act in v if a == MARLIN] for k, v in seen.items()}
        verdict('ai-copy', seen['copy'] == mapped and 'C6' in marlin['copy'],
                original=marlin['original'], patched=marlin['copy'])
        verdict('ai-none', 'C6' not in marlin['none'] and f'{MERA:02X}' not in marlin['none'] and marlin['none'],
                original=marlin['original'], patched=marlin['none'])
        verdict('ai-strong', marlin['strong'].count('C6') > marlin['copy'].count('C6'),
                copy=marlin['copy'], patched=marlin['strong'])
        rows = {k: [r for r in armor_rows(t) if r[0] == int(k, 16)] for k, t in texts.items()}
        # 3A·C7 은 メラ 원소로 まほうのよろい 가 10 을 빼고, C8(イオ)·C9(원소 0)는 빼기 없이 피해가 들어간다.
        expect = {'3A': (0x01, 10), 'C7': (0x01, 10), 'C8': (0x40, None), 'C9': (0x00, None)}
        for k, (element, cut) in expect.items():
            ok = rows[k] and all(r[1] == element and r[4] and (r[2] is None if cut is None else r[2] - r[3] == cut == r[2] - r[4])
                                 for r in rows[k])
            verdict(f'armor-{k}', ok, rows=rows[k])
        save_json(out / 'results.json', results)
        for name, r in results.items():
            print(f'{name}: {"통과" if r["passed"] else "불일치"} {({k: v for k, v in r.items() if k != "passed"})}')
        require(not failed, f'불일치: {", ".join(failed)}')
        print(f'{len(results)}건 게임 검사 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
