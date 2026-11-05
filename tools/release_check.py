"""배포 관문. 사람이 부를 때만 돈다(예약 실행 없음). 형식은 sfc/dq4/docs/dq4-release-check-format.md.

단계(차례대로, 앞 단계가 실패해도 나머지를 돌려 보고서에 모두 남긴다):

  build     출하 롬을 빌드한다(dq4build.py). 롬 SHA-1 이 보고서 폴더 이름이 된다
  unit      CI 와 같은 폴더마다 단위 테스트 전부(롬이 있으므로 롬 게이트 시험도 돈다)
  guards    모든 guards.toml 의 실행 검사 전부. 검사 결과 캐시와 장면 캐시를 쓰지 않는다(--rehearse 면 씀)
  sweep     트랙의 release.toml 시드 스윕(시드 0 부터 N 개와 seeds.json 의 실패 시드)
  coverage  빌드 경로(dq4publish.inputs 의 .py) 커버리지. 로컬(단위 전부 + 빌드 캐시 끈 빌드 한 번, 하위 프로세스도
            잼) ≥ LOCAL_MIN, CI 와 같게(롬 링크 없는 임시 워크트리에서 롬·도구 환경 변수 없이 단위만) ≥ CI_MIN

관문 모드(--rehearse 아님)에서는 서장 끝·시작 상태 캐시(DQ4_STATES_CACHE)를 이 실행 폴더의 빈 states/ 로 돌린다. 상태는 이
실행에서 처음 한 번 만들어 그 실행 안에서만 다시 쓴다. 단계마다 같은 머신에서 돈 MesenCE 수(이 실행과 다른 워크트리)를
30초마다 세어 보고서에 적는다. 실패한 단계·검사는 다시 돌리지 않고 그대로 적는다.

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
import threading
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
LOCAL_MIN, CI_MIN = 90.0, 80.0
# CI 에 없는 것: 롬(워크트리의 rom 링크)과 도구·에셋을 가리키는 환경 변수
CI_UNSET = ('ASAR', 'DQ4_ASSETS', 'DQ4_GALMURI', 'MESENCE', 'LIBDIR', 'LIBRETRO_BSNES', 'LIBRETRO_SNES9X', 'DQ4_CORES',
            'DQ4_SOUND_BASE')


class Load:
    """MesenCE 프로세스를 SAMPLE 초마다 세어, 워크트리(명령줄의 롬 경로가 든 저장소 형제 폴더)마다 최대 수를 모은다."""
    SAMPLE = 30

    def __init__(self, ours):
        self.ours, self.samples, self.peak, self.others = ours, 0, {}, []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def count(ps_text, parent):
        """ps 출력 → {워크트리 이름: MesenCE 수}."""
        out = {}
        for line in ps_text.splitlines():
            if '/MacOS/Mesen' not in line and not re.search(r'(^|/)Mesen(\.exe)?\s', line):
                continue
            m = re.search(re.escape(str(parent)) + r'/([^/\s]+)/', line)
            name = m.group(1) if m else '?'
            out[name] = out.get(name, 0) + 1
        return out

    def _run(self):
        while not self._stop.wait(self.SAMPLE):
            text = subprocess.run(['ps', '-axo', 'command='], capture_output=True, text=True).stdout
            got = self.count(text, ROOT.parent)
            self.samples += 1
            for k, v in got.items():
                self.peak[k] = max(self.peak.get(k, 0), v)
            self.others.append(sum(v for k, v in got.items() if k != self.ours))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()

    def summary(self):
        o = self.others
        return {'samples': self.samples, 'others_max': max(o, default=0),
                'others_avg': round(sum(o) / len(o), 1) if o else 0, 'peak_by_tree': self.peak}


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


def state_note(text):
    """검사 출력의 서장 끝 상태 캐시 표시("state_cache": "hit"|"miss"...)들."""
    return sorted(set(re.findall(r'"state_cache":\s*"([a-z]+)"', text)))


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
        log = ctx['logs'] / f'{s["name"]}.log'
        code, secs = sh(cmd, log, env_for(ctx['rehearse']), ctx['timeout'] * 4)
        rows.append({'name': s['name'], 'file': s['file'], 'seeds': seeds, 'seconds': secs,
                     'status': 'passed' if code == 0 else 'failed',
                     'state_cache': state_note(log.read_text(encoding='utf-8', errors='replace')) if log.exists() else [],
                     'detail': '시간 제한' if code is None else f'종료 코드 {code}'})
        secs_all += secs
    ok = all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': secs_all, 'rows': rows,
            'detail': f'{sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'}


def build_path_files(root=ROOT):
    """빌드 경로 파일: dq4publish.inputs()(dq4build.py 에서 닿는 도구 폴더 파일) 가운데 시험이 아닌 .py."""
    sys.path.insert(0, str(ROOT / 'sfc' / 'dq4' / 'tools'))
    import dq4publish
    return sorted(str(root / f) for f in dq4publish.inputs() if f.suffix == '.py' and not f.name.startswith('test_'))


def coverage_rc(path, data):
    path.write_text(f'[run]\nparallel = true\npatch = subprocess\ndata_file = {data}\n', encoding='utf-8')


def measure(root, logs, tag, env, build_out=None):
    """root 에서 단위 테스트 전부(와 build_out 이 있으면 빌드 한 번)를 coverage 로 돌려 (퍼센트, 단계 실패 목록)."""
    import coverage
    data = logs / f'coverage-{tag}' / '.coverage'
    data.parent.mkdir(parents=True, exist_ok=True)
    rc = logs / f'coverage-{tag}.ini'
    coverage_rc(rc, data)
    failed = []
    for d in UNIT_DIRS:
        if not (root / d).is_dir():
            continue
        code, _ = sh(f"cd {root / d} && uv run --locked coverage run --rcfile={rc} -m unittest discover -p 'test_*.py'",
                     logs / f'coverage-{tag}-{d.replace("/", "-")}.log', env)
        if code != 0:
            failed.append(d)
    if build_out is not None:
        code, _ = sh(f'cd {root} && uv run --locked coverage run --rcfile={rc} sfc/dq4/tools/dq4build.py --out {build_out}',
                     logs / f'coverage-{tag}-build.log', dict(env or os.environ, DQ4_BUILD_CACHE='off'))
        if code != 0:
            failed.append('build')
    cov = coverage.Coverage(data_file=str(data), config_file=str(rc))
    cov.combine(strict=False)
    cov.save()
    with open(logs / f'coverage-{tag}-report.txt', 'w', encoding='utf-8') as out:
        percent = cov.report(include=build_path_files(root), file=out, ignore_errors=True)
    return round(percent, 1), failed


def stage_coverage(ctx):
    t0 = time.time()
    logs = ctx['logs']
    local, lfail = measure(ROOT, logs, 'local', None, ctx['dir'] / 'coverage-build')
    tmp = ctx['dir'] / 'ci-tree'
    guards.git('worktree', 'add', '--detach', str(tmp), 'HEAD')
    try:
        env = {k: v for k, v in os.environ.items() if k not in CI_UNSET}
        ci, cfail = measure(tmp, logs, 'ci', env)
    finally:
        guards.git('worktree', 'remove', '--force', str(tmp))
    problems = [f'{n} 시험이 실패함(커버리지 실행)' for n in lfail + cfail]
    if local < LOCAL_MIN:
        problems.append(f'로컬 {local}% < {LOCAL_MIN}%')
    if ci < CI_MIN:
        problems.append(f'CI 와 같게 {ci}% < {CI_MIN}%')
    return {'status': 'failed' if problems else 'passed', 'seconds': round(time.time() - t0), 'local': local, 'ci': ci,
            'detail': f'로컬 {local}%, CI 와 같게 {ci}%' + (f' — {"; ".join(problems)}' if problems else '')}


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
            lines += ['| 스윕 | 결과 | 시드 | 시간 | 상태 캐시 |', '| --- | --- | --- | --- | --- |']
            lines += [f'| {r["name"]} | {words[r["status"]]} | {len(r["seeds"])}개({r["seeds"][0]}~) | {r["seconds"]}초 | '
                      f'{",".join(r.get("state_cache") or []) or "-"} |' for r in rows]
    lines += ['', f'- 상태 캐시: {report.get("states", "-")}']
    load = {n: st['load'] for n, st in report['stages'].items() if st.get('load')}
    if load:
        lines += ['', '## 같은 머신의 MesenCE(30초마다 셈)', '', '| 단계 | 다른 워크트리 최대 | 평균 | 워크트리마다 최대 |',
                  '| --- | --- | --- | --- |']
        lines += [f'| {n} | {v["others_max"]} | {v["others_avg"]} | '
                  f'{", ".join(f"{k} {c}" for k, c in sorted(v["peak_by_tree"].items())) or "-"} |' for n, v in load.items()]
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
    if a.rehearse:
        states = '공유 캐시(연습)'
    else:
        # 상태는 이 실행에서 처음 만든 것만 쓴다. 검사·스윕이 이 환경 변수를 물려받는다
        os.environ['DQ4_STATES_CACHE'] = str(tmp / 'states')
        states = '이 실행에서 새로 만듦(첫 생성 뒤 이 실행 안에서만 다시 씀)'
    stages = {}
    for name in STAGES:
        if name not in wanted:
            continue
        print(f'[release] {name}', flush=True)
        with Load(ROOT.name) as load:
            stages[name] = RUN[name](ctx)
        stages[name]['load'] = load.summary()
        print(f'[release] {name}: {stages[name]["status"]} ({stages[name].get("detail", "")})', flush=True)
    report = {'verdict': verdict(stages, a.rehearse, wanted, dirty), 'commit': head, 'dirty': dirty,
              'rom_sha1': ctx.get('rom_sha1'), 'when': time.strftime('%Y-%m-%d %H:%M'), 'rehearse': a.rehearse,
              'states': states,
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
