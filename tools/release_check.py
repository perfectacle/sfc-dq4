"""배포 관문. 사람이 부를 때만 돈다(예약 실행 없음). 형식은 sfc/dq4/docs/dq4-release-check-format.md.

단계(차례대로, 앞 단계가 실패해도 나머지를 돌려 보고서에 모두 남긴다):

  build     출하 롬을 빌드한다(dq4build.py). 롬 SHA-1 이 보고서 폴더 이름이 된다
  unit      CI 와 같은 폴더마다 단위 테스트 전부(롬이 있으므로 롬 게이트 시험도 돈다)
  guards    모든 guards.toml 의 실행 검사 전부. 검사 결과 캐시와 장면 캐시를 쓰지 않는다(--rehearse 면 씀)
  sweep     트랙의 release.toml 시드 스윕(시드 0 부터 N 개와 seeds.json 의 실패 시드)
  coverage  빌드 경로 커버리지(아직 측정 수단이 없어 늘 실패, 형식 문서 「남은 것」)

보고서는 work/release/<롬 SHA-1 앞 12자리>/report.json·report.md 다. 모든 단계가 통과해야 통과다. --rehearse 로 돈
보고서는 캐시를 써 배포 근거가 되지 않으므로 통과로 적지 않는다.

  uv run --locked python tools/release_check.py                 # 전부(몇 시간)
  uv run --locked python tools/release_check.py --rehearse --stages build,unit
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guards  # noqa: E402

ROOT = guards.ROOT
STAGES = ('build', 'unit', 'guards', 'sweep', 'coverage')
# CI test 잡과 같은 폴더(.github/workflows/ci.yml 의 matrix)
UNIT_DIRS = ('sfc/dq4/tools', 'sfc/dq5/tools/tests', 'tools/tests', 'fc/dq4/tools', 'nds/dq4/tools')
BUILD = 'uv run --locked python sfc/dq4/tools/dq4build.py --out {out}'
ROM_NAME = 'dq4-ch1-full.sfc'
SEEDS_N = 16


def sh(cmd, log, env=None, timeout=None):
    """bash 로 돌려 (종료 코드, 초). 시간 제한을 넘기면 종료 코드 None."""
    t0 = time.time()
    with open(log, 'w', encoding='utf-8') as out:
        proc = subprocess.Popen(['bash', '-c', cmd], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            guards.kill_group(proc)
            proc.wait()
    return code, round(time.time() - t0)


def sweeps(files=None):
    """모든 트랙의 release.toml 의 [[sweep]]. 각 항목에 'file' 을 붙인다."""
    files = files if files is not None else guards.tracked()
    out = []
    for f in sorted(x for x in files if Path(x).name == 'release.toml'):
        for s in tomllib.loads((ROOT / f).read_text(encoding='utf-8')).get('sweep', []):
            out.append({'file': f, **s})
    return out


def seed_list(n, failed=()):
    """시드 0 부터 n 개, 이어서 실패 시드(겹침 없이 차례 유지)."""
    out = list(range(n))
    for s in failed:
        if s not in out:
            out.append(s)
    return out


def failed_seeds(sweep):
    """그 트랙 폴더 seeds.json 에서 그 스윕 이름의 실패 시드. 없으면 빈 목록."""
    path = ROOT / Path(sweep['file']).parent / 'seeds.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return [int(e['seed']) for e in data.get(sweep['name'], [])]


def env_for(rehearse):
    return None if rehearse else dict(os.environ, DQ4_READSET='off')


def stage_build(ctx):
    out = ctx['dir'] / 'build'
    code, secs = sh(BUILD.format(out=out.relative_to(ROOT)), ctx['logs'] / 'build.log', env_for(ctx['rehearse']))
    rom = out / ROM_NAME
    if code != 0 or not rom.exists():
        return {'status': 'failed', 'seconds': secs, 'detail': f'종료 코드 {code}, 로그 build.log'}
    ctx['rom'] = rom
    ctx['rom_sha1'] = hashlib.sha1(rom.read_bytes()).hexdigest()
    return {'status': 'passed', 'seconds': secs, 'detail': f'롬 SHA-1 {ctx["rom_sha1"]}'}


def unit_counts(text):
    ran = re.findall(r'^Ran (\d+) tests?', text, re.M)
    skipped = re.findall(r'skipped=(\d+)', text)
    return int(ran[-1]) if ran else 0, int(skipped[-1]) if skipped else 0


def stage_unit(ctx):
    rows, secs_all = [], 0
    for d in UNIT_DIRS:
        if not (ROOT / d).is_dir():
            continue
        log = ctx['logs'] / f'unit-{d.replace("/", "-")}.log'
        code, secs = sh(f"cd {d} && uv run --locked python -m unittest discover -p 'test_*.py'", log, env_for(ctx['rehearse']))
        ran, skipped = unit_counts(log.read_text(encoding='utf-8', errors='replace'))
        rows.append({'dir': d, 'status': 'passed' if code == 0 else 'failed', 'tests': ran, 'skipped': skipped,
                     'seconds': secs})
        secs_all += secs
    ok = rows and all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': secs_all, 'rows': rows,
            'detail': f'{sum(r["tests"] for r in rows)}개, 건너뜀 {sum(r["skipped"] for r in rows)}개'}


def stage_guards(ctx):
    checks, problems = guards.load(guards.tracked())
    if problems:
        return {'status': 'failed', 'seconds': 0, 'detail': '; '.join(problems[:5]), 'rows': []}
    t0 = time.time()
    done = guards.run_many(checks, ctx['parallel'], ctx['timeout'], no_cache=not ctx['rehearse'],
                           logs=ctx['logs'] / 'guards')
    rows = [{'name': c['name'], 'file': c['file'], 'status': s, 'detail': d} for c, s, d in done]
    ok = all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': round(time.time() - t0), 'rows': rows,
            'detail': f'{sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'}


def stage_sweep(ctx):
    if 'rom' not in ctx:
        return {'status': 'failed', 'seconds': 0, 'detail': '빌드한 롬이 없음', 'rows': []}
    rows, secs_all = [], 0
    for s in sweeps():
        seeds = seed_list(int(s.get('seeds', ctx['seeds_n'])), failed_seeds(s))
        out = ctx['dir'] / 'sweep' / s['name']
        cmd = s['run'].format(rom=ctx['rom'].relative_to(ROOT), out=out.relative_to(ROOT),
                              seeds=','.join(map(str, seeds)))
        code, secs = sh(cmd, ctx['logs'] / f'{s["name"]}.log', env_for(ctx['rehearse']), ctx['timeout'] * 4)
        rows.append({'name': s['name'], 'file': s['file'], 'seeds': seeds, 'seconds': secs,
                     'status': 'passed' if code == 0 else 'failed',
                     'detail': '시간 제한' if code is None else f'종료 코드 {code}'})
        secs_all += secs
    ok = all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': secs_all, 'rows': rows,
            'detail': f'{sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'}


def stage_coverage(ctx):
    return {'status': 'failed', 'seconds': 0, 'detail': '빌드 경로 커버리지 측정 수단이 아직 없음'}


RUN = {'build': stage_build, 'unit': stage_unit, 'guards': stage_guards, 'sweep': stage_sweep,
       'coverage': stage_coverage}


def commit():
    head = guards.git('rev-parse', 'HEAD').strip()
    dirty = bool(guards.git('status', '--porcelain', '--untracked-files=no').strip())
    return head, dirty


def verdict(stages, rehearse, wanted, dirty=False):
    """보고서 전체 판정: 고친 것 없는 커밋에서 모든 단계를 캐시 없이 돌려 모두 통과했을 때만 passed."""
    if rehearse:
        return 'rehearsal'
    if set(wanted) != set(STAGES):
        return 'partial'
    if dirty:
        return 'dirty'
    return 'passed' if all(stages[s]['status'] == 'passed' for s in STAGES) else 'failed'


def markdown(report):
    words = {'passed': '통과', 'failed': '실패', 'skipped': '돌리지 않음', 'rehearsal': '연습(캐시 씀, 배포 근거 아님)',
             'partial': '일부 단계만 돎(배포 근거 아님)', 'dirty': '커밋하지 않은 고친 것이 있음(배포 근거 아님)'}
    lines = ['# 배포 관문 보고서', '',
             f'- 판정: **{words.get(report["verdict"], report["verdict"])}**',
             f'- 커밋: `{report["commit"]}`' + (' (추적 파일에 고친 것이 있음)' if report['dirty'] else ''),
             f'- 롬 SHA-1: `{report.get("rom_sha1") or "-"}`',
             f'- 시각: {report["when"]}', '', '| 단계 | 결과 | 시간 | 내용 |', '| --- | --- | --- | --- |']
    for name, st in report['stages'].items():
        lines.append(f'| {name} | {words.get(st["status"], st["status"])} | {st["seconds"]}초 | {st.get("detail", "")} |')
    for name in ('unit', 'guards', 'sweep'):
        rows = report['stages'].get(name, {}).get('rows')
        if not rows:
            continue
        lines += ['', f'## {name}', '']
        if name == 'unit':
            lines += ['| 폴더 | 결과 | 시험 | 건너뜀 | 시간 |', '| --- | --- | --- | --- | --- |']
            lines += [f'| `{r["dir"]}` | {words[r["status"]]} | {r["tests"]} | {r["skipped"]} | {r["seconds"]}초 |' for r in rows]
        elif name == 'guards':
            lines += ['| 검사 | 결과 | 내용 |', '| --- | --- | --- |']
            lines += [f'| {r["name"]} | {words.get(r["status"], r["status"])} | {r["detail"]} |' for r in rows]
        else:
            lines += ['| 스윕 | 결과 | 시드 | 시간 |', '| --- | --- | --- | --- |']
            lines += [f'| {r["name"]} | {words[r["status"]]} | {len(r["seeds"])}개({r["seeds"][0]}~) | {r["seconds"]}초 |'
                      for r in rows]
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stages', default=','.join(STAGES), help='돌릴 단계(쉼표). 일부만 돌리면 판정은 partial')
    ap.add_argument('--rehearse', action='store_true', help='검사 결과·장면 캐시를 쓴다(빠름, 배포 근거 아님)')
    ap.add_argument('--seeds-n', type=int, default=SEEDS_N, help='release.toml 에 seeds 가 없는 스윕의 시드 수')
    ap.add_argument('--parallel', type=int, default=2)
    ap.add_argument('--timeout', type=int, default=1800, help='실행 검사 하나의 시간 제한(초). 스윕은 이것의 네 배')
    a = ap.parse_args()
    wanted = [s for s in a.stages.split(',') if s]
    bad = [s for s in wanted if s not in STAGES]
    if bad:
        ap.error(f'모르는 단계 {bad}')
    root = ROOT / 'work' / 'release'
    tmp = root / f'run-{os.getpid()}'
    (tmp / 'logs').mkdir(parents=True, exist_ok=True)
    head, dirty = commit()
    ctx = {'dir': tmp, 'logs': tmp / 'logs', 'rehearse': a.rehearse, 'seeds_n': a.seeds_n, 'parallel': a.parallel,
           'timeout': a.timeout}
    stages = {}
    for name in STAGES:
        if name not in wanted:
            continue
        print(f'[release] {name}', flush=True)
        stages[name] = RUN[name](ctx)
        print(f'[release] {name}: {stages[name]["status"]} ({stages[name].get("detail", "")})', flush=True)
    report = {'verdict': verdict(stages, a.rehearse, wanted, dirty), 'commit': head, 'dirty': dirty,
              'rom_sha1': ctx.get('rom_sha1'), 'when': time.strftime('%Y-%m-%d %H:%M'), 'rehearse': a.rehearse,
              'stages': stages}
    dest = root / (ctx['rom_sha1'][:12] if ctx.get('rom_sha1') else f'nobuild-{head[:12]}')
    if dest.exists():
        dest = dest.with_name(f'{dest.name}-{time.strftime("%Y%m%d-%H%M%S")}')
    tmp.rename(dest)
    (dest / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (dest / 'report.md').write_text(markdown(report), encoding='utf-8')
    print(f'[release] 판정 {report["verdict"]}, 보고서 {dest.relative_to(ROOT)}/report.md', flush=True)
    return 0 if report['verdict'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
