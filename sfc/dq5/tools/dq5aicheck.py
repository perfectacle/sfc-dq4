"""dq5aiwrite.py 로 고친 AI·작전·학습 배율·내성 배율·갑옷 원소 표를 MesenCE 에서 원래 롬과 견준다.

  ai      주인공·ホイミン(01)·マーリン(02) 과 슬라임 셋(HP 200)의 필드 전투. 동료 かしこさ 99, 전투 주문 칸 8~15 를 모두
          배움. 20:8846 에서 행동자·행동을 모아, 작전(7E:2034)·주인공 HP·가진 물건을 POKE 로 둔 같은 입력으로 견줌
  papas   파파스가 슬라임 셋에게 メラ. 내성 단계 0 배율 27:8055 FF → 80
  armor   슬라임이 まほうのよろい 를 입은 주인공에게 メラミ(3A). 갑옷 원소 표 まほうのよろい 항목 10 → 48

장면 준비용 ROMPATCH·SET·POKE(전투로 순간이동, 슬라임 HP·MP·행동, 동료 레코드, 작전, 주인공 HP·갑옷·물건·레벨)는
확인하는 표를 덮지 않는다. 원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5aicheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from dq5aiwrite import FORMAT, ODDS, dump
from dq5map import Rom
from dq5progresscheck import command, environment, require, run, save_json
from dq5spellfxcheck import casts
from dq5tablecheck import PAPAS

HERE = Path(__file__).resolve().parent
HOIMIN, MARLIN = '01', '02'


def zero_group0(table):
    """갈래 0(メラ·ギラ·イオ·ヒャド·バギ·デイン 내성)의 내성 단계 0 배율을 라운드마다 0 으로."""
    return [[[0 if g == 0 and s == 0 else v for s, v in enumerate(r)] for r in grp] for g, grp in enumerate(table)]


def cases(rom):
    odds = dump(rom)['odds']
    return {
        'value': {'actions': [{'action': a, 'value': 0} for a in ('01', '04', '06')]},
        'branch': {'actions': [{'action': '27', 'branch': '00'}]},
        'mp': {'actions': [{'action': a, 'mp': 0} for a in ('01', '04')]},
        'range': {'actions': [{'action': '04', 'range': '00'}]},
        'resist': {'actions': [{'action': '06', 'resist': '56'}]},
        'ivalue': {'items': [{'item': 'A1', 'value': 0}]},
        'ibranch': {'items': [{'item': 'A1', 'branch': '07'}]},
        'danger': {'tactics': [{'tactic': 0, 'danger': 0x4B}]},
        'per_mp': {'tactics': [{'tactic': 2, 'per_mp': 0x12}]},
        'flat': {'tactics': [{'tactic': 2, 'flat': 0xFF}]},
        'mp_ratio': {'tactics': [{'tactic': 2, 'mp_ratio': 0xFF}]},
        'mp_penalty': {'tactics': [{'tactic': 2, 'mp_penalty': 0}]},
        **{f'odds_{name}': {'odds': {name: zero_group0(odds[name])}} for name in ODDS},
        'rates': {'resist_rates': [0x80, 205, 84, 0]},
        'armor': {'armor': [{'index': 2, 'reduce': 48}]},
        # 대조용: 이 장면에서 아무도 갖지 않은 물건(00 ひのきのぼう)의 AI 기대 값만 바꾼다. 결정이 원본과 같아야 한다.
        'control': {'items': [{'item': '00', 'value': 1}]},
    }


HERO_HP = ',7E2042={:02X},7E2043=00'
ITEM = ',7E2080=A1'
# (이름, 고친 롬, 작전, 덧붙일 POKE, 기대: 행동자 → 행동 개수 사전을 받아 참/거짓)
AI_CASES = [
    ('value', 0, '', lambda o, m: all(o[MARLIN][a] for a in ('01', '04', '06'))
     and not any(m[MARLIN][a] for a in ('01', '04', '06')) and m[MARLIN]['02'] + m[MARLIN]['05'] > 0),
    ('branch', 0, HERO_HP.format(2), lambda o, m: o[HOIMIN]['27'] > 0 and m[HOIMIN]['27'] == 0 and m[HOIMIN]['28'] > 0),
    ('mp', 2, '', lambda o, m: o[MARLIN]['04'] == 0 and m[MARLIN]['04'] > 0),
    ('range', 0, '', lambda o, m: o[MARLIN]['04'] > 0 and m[MARLIN]['04'] == 0),
    ('resist', 0, '', lambda o, m: o[MARLIN]['06'] > 0 and m[MARLIN]['06'] == 0),
    ('ivalue', 3, HERO_HP.format(2) + ITEM, lambda o, m: o[HOIMIN]['A1'] > 0 and m[HOIMIN]['A1'] == 0),
    ('ibranch', 4, HERO_HP.format(2) + ITEM, lambda o, m: o[HOIMIN]['A1'] > 0 and m[HOIMIN]['A1'] == 0),
    ('danger', 0, HERO_HP.format(4), lambda o, m: o[HOIMIN]['27'] == 0 and m[HOIMIN]['27'] > 0),
    *((name, 2, '', lambda o, m: o[MARLIN]['04'] == 0 and m[MARLIN]['04'] > 0)
      for name in ('per_mp', 'flat', 'mp_ratio', 'mp_penalty')),
    ('odds_normal', 0, '', lambda o, m: sum(o[MARLIN][a] for a in ('01', '04', '06')) > 0
     and set(m[MARLIN]) <= {'73'}),
    ('odds_saving', 2, '', lambda o, m: o[MARLIN]['02'] > 0 and set(m[MARLIN]) <= {'73'}),
    # 주인공 레벨 30 이면 구역 레벨 + 10 이상인 「쉬운 전투」(21:C86D 의 $12D0)라 27:8284 를 쓴다.
    ('odds_easy', 0, ',7E2052=1E', lambda o, m: o[MARLIN]['04'] + o[MARLIN]['06'] > 0 and set(m[MARLIN]) <= {'73'}),
]
# 사다리 출구를 첫 필드 이벤트 자리로 덮고, 슬라임 MP 99·행동 여섯을 몬스터 メラミ(3A)로.
ARMOR_SCENE = dict(PAPAS, ROMPATCH='156FF5=E0253C0103;118004=63;118011=3A3A3A3A3A3A', POKE='7E2056=56',
                   READS='278104', EXECS='20AC54,20AC57', MAXF='2400')
PAPAS_SCENE = dict(PAPAS, READS='278055-278058')


def build(original, out):
    for name, edit in cases(Rom(original.read_bytes())).items():
        source, manifest = out / f'{name}.json', out / f'{name}.patch.json'
        save_json(source, {'format': FORMAT, **edit})
        command('dq5aiwrite.py', original, 'patch', source, '-o', manifest)
        command('dq5aiwrite.py', original, 'check', source)
        command('dq5build.py', original, 'build', manifest, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def prepare(original, state, out, mesence, libdir):
    dest = out / 'ai-state'
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', BATTLE='00:3', PARTY='05,04', SET='2073=63;209D=63;208E=FF;20B8=FF;2034=00',
               ROMPATCH='118003=C8', SETTLE='300', SAVE='battle.mss', MAXF='1800')
    run(mesence, original, HERE / 'lua/dq5warp.lua', dest, env)
    require((dest / 'battle.mss').is_file(), 'AI 전투 상태가 저장되지 않음')
    return dest / 'battle.mss'


def ai_run(name, rom, tactic, poke, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(DRIVER=str(HERE / 'lua/dq5battle.lua'), MAXF='4000', LOOP='a:4,wait:20',
               POKE=f'7E2034={tactic:02X}{poke}')
    run(mesence, rom, HERE / 'lua/dq5aicheck.lua', dest, env)
    rows = re.findall(r'actor (\w\w) action (\w\w)', (dest / 'decisions.txt').read_text())
    require(rows, f'{name}: 작전 AI 결정이 없음')
    seen = {}
    for actor, action in rows:
        seen.setdefault(actor, Counter())[action] += 1
    return {actor: Counter(c) for actor, c in seen.items()}


def scene_run(name, rom, options, state, out, mesence, libdir):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(options, DRIVER=str(HERE / 'lua/dq5battle.lua'))
    run(mesence, rom, HERE / 'lua/dq5tablecheck.lua', dest, env)
    return (dest / 'observed.txt').read_text()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/aicheck')
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
        jobs, controls = {}, {}
        for name, tactic, poke, _ in AI_CASES:
            # 같은 작전·POKE 의 원본 실행은 한 번만 돌린다.
            key = controls.setdefault((tactic, poke), f'ai-original-{len(controls)}')
            jobs[key] = (original, tactic, poke)
            jobs[f'ai-{name}'] = (out / f'{name}.sfc', tactic, poke)
        for (tactic, poke), key in controls.items():
            jobs[f'{key}-control'] = (out / 'control.sfc', tactic, poke)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {k: pool.submit(ai_run, k, *v, battle, out, mesence, libdir) for k, v in jobs.items()}
            texts = {k: pool.submit(scene_run, k, rom, opts, state, out, mesence, libdir) for k, rom, opts in (
                ('papas-original', original, PAPAS_SCENE), ('papas-rates', out / 'rates.sfc', PAPAS_SCENE),
                ('armor-original', original, ARMOR_SCENE), ('armor-armor', out / 'armor.sfc', ARMOR_SCENE))}
            seen = {k: f.result() for k, f in futures.items()}
            observed = {k: f.result() for k, f in texts.items()}
        results, failed = {}, []
        for name, tactic, poke, ok in AI_CASES:
            o = {a: Counter(c) for a, c in seen[controls[tactic, poke]].items()}
            m = {a: Counter(c) for a, c in seen[f'ai-{name}'].items()}
            for d in (o, m):
                for actor in (HOIMIN, MARLIN):
                    d.setdefault(actor, Counter())
            passed = ok(o, m)
            results[name] = {'tactic': tactic, 'original': {a: dict(c) for a, c in o.items()},
                             'patched': {a: dict(c) for a, c in m.items()}, 'passed': passed}
            if not passed:
                failed.append(name)
        same = [k for k in controls.values() if seen[k] != seen[f'{k}-control']]
        results['control'] = {'original': {k: {a: dict(c) for a, c in seen[k].items()} for k in controls.values()},
                              'patched': {k: {a: dict(c) for a, c in seen[f'{k}-control'].items()}
                                          for k in controls.values()}, 'passed': not same}
        if same:
            failed.append('control')
        damage = {c: casts(out, f'papas-{c}') for c in ('original', 'rates')}
        rates_ok = (len(damage['original']) >= 2 and len(damage['rates']) >= 2
                    and all(len(h) == 1 and 12 <= h[0][1] <= 15 for h in damage['original'])
                    and all(len(h) == 1 and 6 <= h[0][1] <= 7 for h in damage['rates'])
                    and 'read 278055=FF' in observed['papas-original'] and 'read 278055=80' in observed['papas-rates'])
        results['rates'] = {'original': damage['original'], 'patched': damage['rates'], 'passed': rates_ok}
        armor = {}
        for c in ('original', 'armor'):
            text = observed[f'armor-{c}']
            raw = [int(a, 16) for a in re.findall(r'pc=20AC54 A=([0-9A-F]{4})', text)]
            cut = [int(a, 16) for a in re.findall(r'pc=20AC57 A=([0-9A-F]{4})', text)]
            require(len(raw) == len(cut), f'armor-{c}: 빼기 앞뒤 기록 수가 다름')
            armor[c] = [(r, r - k) for r, k in zip(raw, cut)]
        armor_ok = (armor['original'] and armor['armor'] and all(d == 10 for _, d in armor['original'])
                    and all(d == 48 for _, d in armor['armor']))
        results['armor'] = {'original': armor['original'], 'patched': armor['armor'], 'passed': bool(armor_ok)}
        failed += [k for k in ('rates', 'armor') if not results[k]['passed']]
        save_json(out / 'results.json', results)
        for name, r in results.items():
            print(f'{name}: {"통과" if r["passed"] else "불일치"} 원본 {r["original"]} 변경 {r["patched"]}')
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
