"""배포 관문. 사람이 부를 때만 돈다(예약 실행 없음). 형식은 sfc/dq4/docs/dq4-release-check-format.md.

단계(차례대로, 앞 단계가 실패해도 나머지를 돌려 보고서에 모두 남긴다):

  build     출하 롬을 빌드한다(dq4build.py, 빌드 단계 캐시 켬). 관문 모드에서는 같은 때 모든 캐시를 끄고 파이썬 경로로
            한 번 더 빌드해 산출물 바이트가 모두 같아야 통과. 롬 SHA-1 이 보고서 폴더 이름이 된다
  unit      CI 와 같은 폴더마다 단위 테스트 전부(롬이 있으므로 롬 게이트 시험도 돈다)
  guards    모든 guards.toml 의 실행 검사 전부. 검사 결과 캐시와 장면 캐시를 쓰지 않는다(--rehearse 면 씀)
  sweep     트랙의 release.toml 시드 스윕(시드 0 부터 N 개와 seeds.json 의 실패 시드)
            --ci-report 면 guards·sweep 은 CI 결과만 받고 에뮬레이터를 돌리지 않는다(로컬 몫 LOCAL_NEEDS 만 예외)
  coverage  빌드 경로(dq4publish.inputs 의 .py) 커버리지. 로컬(단위 전부 + 빌드 캐시 끈 빌드 한 번, 하위 프로세스도
            잼) ≥ LOCAL_MIN, CI 와 같게(롬 링크 없는 임시 워크트리에서 롬·도구 환경 변수 없이 단위만) ≥ CI_MIN.
            unit 단계와 함께 돌면 unit 단계가 coverage 로 돌아 단위를 다시 돌지 않는다. --ci-report 면 빌드와 CI 와
            같게는 CI cold-build 잡의 기록(--ci-coverage)을 쓰고 로컬은 단위만 잰다

관문 모드(--rehearse 아님)에서는 build 의 캐시 빌드 밖의 모든 단계가 같은 환경(gate_env)으로 돈다: 장면 캐시(DQ4_READSET=off), 빌드 단계
캐시(DQ4_BUILD_CACHE=off), 서장 끝·시작 상태 캐시(DQ4_STATES_CACHE 를 이 실행 폴더의 빈 states/ 로, 처음 한 번 만들어 그
실행 안에서만 다시 씀). guards.py 의 검사 결과 캐시도 쓰지 않는다. 단계마다 같은 머신에서 돈 MesenCE 수(이 실행과 다른 워크트리)를
30초마다 세어 보고서에 적는다. 실패한 단계·검사는 다시 돌리지 않고 그대로 적는다.

보고서는 work/release/<롬 SHA-1 앞 12자리>/report.json·report.md 다. 모든 단계가 통과해야 통과다. --rehearse 로 돈
보고서는 캐시를 써 배포 근거가 되지 않으므로 통과로 적지 않는다.

  uv run --locked python tools/release_check.py                 # 전부(몇 시간)
  uv run --locked python tools/release_check.py --rehearse --stages build,unit
  uv run --locked python tools/release_check.py --ci-report DIR  # guards·sweep 은 CI 결과, 로컬은 build·unit·coverage
  uv run --locked python tools/release_check.py --ci-summary DIR # CI report 잡: 조각 결과 요약(Markdown), 실패면 1
  uv run --locked python tools/release_check.py --ci-coverage unit|build OUT [--build-out DIR]  # CI cold-build 잡

--ci-report 의 DIR 은 배포 관문 워크플로(release-gate.yml → guard-shards.yml)의 조각 결과(guards.py --all --json)를 받은 폴더다. 조각이 모두
있고 그 커밋이 지금 HEAD 여야 한다. CI 가 판정한 검사·스윕은 그 결과를 그대로 쓴다(실패를 로컬에서 다시 돌려 덮지 않는다).
CI 가 뺀 로컬 몫(needs 에 guard-shards.yml 의 LOCAL_NEEDS 가 든 것)만 로컬에서 돌린다. CI 에서 돌리지 않음(skipped)이거나
결과가 없는 검사·스윕은 다시 돌리지 않고 통과가 아닌 것으로 적는다.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_cache  # noqa: E402
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
    """모든 트랙의 release.toml 의 [[sweep]](guards.load_sweeps). 각 항목에 'file' 을 붙인다."""
    return guards.load_sweeps(files if files is not None else guards.tracked(), lambda f: (ROOT / f).read_text(
        encoding='utf-8'))[0]


seed_list = guards.seed_list


def failed_seeds(sweep):
    """그 트랙 폴더 seeds.json 에서 그 스윕 이름의 실패 시드. 없으면 빈 목록."""
    return guards.failed_seeds(sweep, ROOT)


def gate_env(run_dir, base=None):
    """관문 모드의 환경: 캐시를 모두 끈다(상태 캐시는 run_dir/states 에서 이 실행 동안만). build 단계만 빌드 단계 캐시를
    켜고(cached_env) 같은 때의 무캐시 빌드(cold_env)와 바이트를 견준다."""
    return dict(base if base is not None else os.environ, DQ4_READSET='off', DQ4_BUILD_CACHE='off',
                DQ4_STATES_CACHE=str(run_dir / 'states'))


def env_for(ctx, base=None):
    """단계가 쓸 환경. 연습이면 base(없으면 지금 환경 그대로 = None)."""
    if ctx['rehearse']:
        return base
    return gate_env(ctx['dir'], base)


def state_note(text):
    """검사 출력의 서장 끝 상태 캐시 표시("state_cache": "hit"|"miss"...)들."""
    return sorted(set(re.findall(r'"state_cache":\s*"([a-z]+)"', text)))


def cold_env(run_dir, base=None):
    """무캐시 빌드의 환경: 관문 환경에 곡 변환·검산 캐시도 끄고, Go 도구 대신 파이썬 경로로."""
    return dict(gate_env(run_dir, base), DQ4_SOUND_CACHE='off', DQ4_NATIVE='off')


def cached_env(run_dir, base=None):
    """관문 빌드의 환경: 관문 환경에서 빌드 단계 캐시만 기본(공유 칸)대로 켠다."""
    env = gate_env(run_dir, base)
    src = base if base is not None else os.environ
    if 'DQ4_BUILD_CACHE' in src:
        env['DQ4_BUILD_CACHE'] = src['DQ4_BUILD_CACHE']
    else:
        env.pop('DQ4_BUILD_CACHE')
    return env


def stage_build(ctx):
    """출하 롬을 빌드한다. 관문 모드에서는 빌드 단계 캐시로 빌드하고, 같은 때 모든 캐시를 끈 빌드(cold_env)를 따로 해
    산출물 바이트가 모두 같아야 통과다(캐시 키에 빠진 입력이 있으면 여기서 드러난다). 연습이면 캐시 빌드 하나만."""
    out = ctx['dir'] / 'build'
    jobs = {'cached': (out, cached_env(ctx['dir']) if not ctx['rehearse'] else None, 'build.log')}
    if not ctx['rehearse']:
        jobs['cold'] = (ctx['dir'] / 'build-cold', cold_env(ctx['dir']), 'build-cold.log')
    done = {}

    def one(kind):
        folder, env, log = jobs[kind]
        done[kind] = sh(BUILD.format(out=folder.relative_to(ROOT)), ctx['logs'] / log, env)
    threads = [threading.Thread(target=one, args=(k,)) for k in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    secs = max(s for _, s in done.values())
    rom = out / ROM_NAME
    failed = [f'{k} 종료 코드 {c}(로그 {jobs[k][2]})' for k, (c, _) in done.items() if c != 0]
    if failed or not rom.exists():
        return {'status': 'failed', 'seconds': secs, 'detail': ', '.join(failed) or f'{ROM_NAME} 없음'}
    ctx['rom'] = rom
    ctx['rom_sha1'] = hashlib.sha1(rom.read_bytes()).hexdigest()
    detail = f'롬 SHA-1 {ctx["rom_sha1"]}'
    if 'cold' not in jobs:
        return {'status': 'passed', 'seconds': secs, 'detail': detail}
    text, same = ci_cache.verify_build([ci_cache.digest(folder, 'ch1', kind) for kind, (folder, _, _) in jobs.items()],
                                       variants=('ch1',))
    (ctx['logs'] / 'build-verify.md').write_text(text, encoding='utf-8')
    if not same:
        return {'status': 'failed', 'seconds': secs,
                'detail': f'캐시 빌드가 무캐시 빌드와 다름 — 캐시 키에 빠진 입력(로그 build-verify.md), {detail}'}
    return {'status': 'passed', 'seconds': secs, 'detail': f'{detail}, 무캐시 빌드와 바이트 같음'}


def unit_counts(text):
    ran = re.findall(r'^Ran (\d+) tests?', text, re.M)
    skipped = re.findall(r'skipped=(\d+)', text)
    return int(ran[-1]) if ran else 0, int(skipped[-1]) if skipped else 0


def stage_unit(ctx):
    """coverage 단계도 돌면(ctx['cover']) 단위를 coverage 로 돌려, coverage 단계가 단위를 다시 돌지 않게 한다."""
    rows, secs_all = [], 0
    runner = 'python'
    if ctx.get('cover'):
        runner = f'coverage run --rcfile={coverage_paths(ctx["logs"], "local")[1]}'
    for d in UNIT_DIRS:
        if not (ROOT / d).is_dir():
            # CI 가 도는 폴더가 없어졌으면 그 시험이 빠진 것이라 통과로 치지 않는다
            rows.append({'dir': d, 'status': 'failed', 'tests': 0, 'skipped': 0, 'seconds': 0, 'detail': '폴더 없음'})
            continue
        log = ctx['logs'] / f'unit-{d.replace("/", "-")}.log'
        code, secs = sh(f"cd {d} && uv run --locked {runner} -m unittest discover -p 'test_*.py'", log, env_for(ctx))
        ran, skipped = unit_counts(log.read_text(encoding='utf-8', errors='replace'))
        rows.append({'dir': d, 'status': 'passed' if code == 0 else 'failed', 'tests': ran, 'skipped': skipped,
                     'seconds': secs})
        secs_all += secs
    ok = bool(rows) and all(r['status'] == 'passed' for r in rows)
    missing = [r['dir'] for r in rows if r.get('detail') == '폴더 없음']
    if ctx.get('cover'):
        ctx['unit_covered'] = True
        ctx['unit_failed'] = [r['dir'] + ('(폴더 없음)' if r.get('detail') else '') for r in rows if r['status'] != 'passed']
    return {'status': 'passed' if ok else 'failed', 'seconds': secs_all, 'rows': rows,
            'detail': (f'폴더 없음 {", ".join(missing)}; ' if missing else '') + f'{sum(r["tests"] for r in rows)}개, 건너뜀 {sum(r["skipped"] for r in rows)}개'}


def load_ci(folder):
    """CI 조각 결과(guards.py --all --json)를 모은다. {'commit', 'shards', 'rows', 'local'(이름 목록)}. 결과가 없거나,
    조각이 빠졌거나, 커밋이 서로 다르거나, 한 검사가 두 조각에 있으면 ValueError. 하위 조각 행은 검사 하나로
    합친다(guards.merge_parts)."""
    parts = []
    for f in sorted(Path(folder).rglob('*.json')):
        data = json.loads(f.read_text(encoding='utf-8'))
        if isinstance(data, dict) and {'commit', 'shard', 'rows', 'local'} <= set(data):
            parts.append(data)
    if not parts:
        raise ValueError(f'{folder}: CI 조각 결과가 없음')
    commits = {p['commit'] for p in parts}
    if len(commits) != 1:
        raise ValueError(f'조각마다 커밋이 다름: {sorted(commits)}')
    sizes = {p['shard'][1] if p['shard'] else 1 for p in parts}
    if len(sizes) != 1:
        raise ValueError(f'조각 수가 서로 다름: {sorted(sizes)}')
    n = sizes.pop()
    got = sorted(p['shard'][0] if p['shard'] else 1 for p in parts)
    if got != list(range(1, n + 1)):
        raise ValueError(f'조각 {n}개 가운데 받은 것 {got}')
    rows = guards.merge_parts([r for p in parts for r in p['rows']])
    sweep_rows = [r for r in rows if r.get('sweep')]
    rows = [r for r in rows if not r.get('sweep')]
    names = [r['name'] for r in rows + sweep_rows]
    twice = sorted({x for x in names if names.count(x) > 1})
    if twice:
        raise ValueError(f'두 조각에서 돈 검사: {twice}')
    local = sorted({x['name'] for p in parts for x in p['local']})
    # 표시가 없는 옛 조각 결과는 캐시를 쓰지 않던 때의 것이다
    cached = any(p.get('cached', False) for p in parts)
    commit = commits.pop()
    # 빌드 대조(ci_cache.verify_build): 무캐시 빌드 결과가 있을 때만. 조각이 받은 롬도 함께 견준다
    digests = ci_cache.load_digests(folder)
    build = None
    if any(d['kind'] == ci_cache.COLD for d in digests):
        text, ok = ci_cache.verify_build(digests)
        if any(d['commit'] != commit for d in digests):
            text, ok = text + '- **빌드 대조의 커밋이 조각 결과와 다름**\n', False
        build = {'ok': ok, 'text': text}
    return {'commit': commit, 'shards': n, 'rows': rows, 'sweeps': sweep_rows, 'local': local, 'cached': cached,
            'build': build, 'coverage': load_coverage(folder, commit)}


def ci_sweeps(ci, wanted):
    """CI 스윕 결과를 wanted(release.toml 스윕) 차례로. CI 에 없는 스윕은 「결과 없음」 으로 skipped."""
    got = {r['name']: r for r in ci.get('sweeps', [])}
    return [got.get(s['name']) or {'name': s['name'], 'file': s['file'], 'status': 'skipped',
                                   'detail': 'CI 결과 없음(release-gate 가 sweeps 를 돌리지 않음)'} for s in wanted]


def ci_summary(ci, require_build=False, wanted=None):
    """(Markdown, CI 결과가 모두 통과인가). 돌리지 않음(skipped)도 CI 환경이 모자란 것이라 통과로 치지 않는다. 캐시를
    쓴 실행(연습)은 모두 통과여도 판정을 연습으로 적는다. 빌드 대조(캐시 빌드 = 무캐시 빌드)가 있으면 그것도 같아야
    통과이고, require_build(배포 관문)면 없을 때도 실패다. wanted(release.toml 스윕)를 주면 그 스윕이 모두 CI 에서
    통과해야 통과다(시드 단위 실패는 그 시드를 적는다)."""
    words = {'passed': '통과', 'failed': '실패', 'skipped': '돌리지 않음'}
    build = ci.get('build')
    sw = ci_sweeps(ci, wanted) if wanted is not None else ci.get('sweeps', [])
    ok = (bool(ci['rows']) and all(r['status'] == 'passed' for r in ci['rows'])
          and all(r['status'] == 'passed' for r in sw))
    ok = ok and (build['ok'] if build else not require_build)
    word = ('연습 통과(캐시 씀, 배포 근거 아님)' if ci.get('cached') else '통과') if ok else '실패'
    lines = ['# 배포 관문 CI 결과', '', f'- 커밋: `{ci["commit"]}`', f'- 조각 {ci["shards"]}개, 검사 {len(ci["rows"])}개'
             f'({sum(r["status"] == "passed" for r in ci["rows"])}개 통과), 로컬 몫 {len(ci["local"])}개',
             f'- 판정: **{word}**', '', '| 검사 | 결과 | 내용 |', '| --- | --- | --- |']
    lines += [f'| {r["name"]} | {words.get(r["status"], r["status"])} | {r["detail"]} |'
              for r in sorted(ci['rows'], key=lambda r: (r['status'] == 'passed', r['name']))]
    if build:
        lines += ['', build['text'].rstrip('\n')]
    elif require_build:
        lines += ['', '## 캐시 빌드와 무캐시 빌드 대조', '', '- **무캐시 빌드 결과가 없음**(cold-build 잡을 본다)']
    if sw:
        lines += ['', '## 시드 스윕', '', f'스윕 {len(sw)}개({sum(r["status"] == "passed" for r in sw)}개 통과)', '',
                  '| 스윕 | 결과 | 시드 단위 | 내용 |', '| --- | --- | --- | --- |']
        lines += [f'| {r["name"]} | {words.get(r["status"], r["status"])} | {len(r.get("parts") or [])} | {r["detail"]} |'
                  for r in sorted(sw, key=lambda r: (r['status'] == 'passed', r['name']))]
    if ci['local']:
        lines += ['', '## 로컬 몫', '', '리눅스 CI 에서 돌리지 않아 `release_check.py --ci-report` 가 로컬에서 돌린다.', '',
                  ', '.join(ci['local'])]
    return '\n'.join(lines) + '\n', ok


def stage_guards(ctx):
    checks, problems = guards.load(guards.tracked())
    if problems:
        return {'status': 'failed', 'seconds': 0, 'detail': '; '.join(problems[:5]), 'rows': []}
    t0 = time.time()
    ci = ctx.get('ci')
    # CI 결과가 있으면 로컬 몫(LOCAL_NEEDS)만 여기서 돈다. CI 에서 돌리지 않음·결과 없음인 검사는 로컬 에뮬레이터로
    # 메우지 않고 그대로 통과가 아닌 것으로 남긴다
    judged = {r['name']: r for r in ci['rows']} if ci else {}
    mine = [c for c in checks if c['name'] in ci['local']] if ci else checks
    missing = [c for c in checks if ci and c['name'] not in judged and c['name'] not in ci['local']]
    done = guards.run_many(mine, ctx['parallel'], ctx['timeout'], no_cache=not ctx['rehearse'],
                           logs=ctx['logs'] / 'guards', env=env_for(ctx)) if mine else []
    done += [(c, 'skipped', 'CI 결과 없음') for c in missing]
    rows = [{'name': c['name'], 'file': c['file'], 'status': judged[c['name']]['status'],
             'detail': f'CI: {judged[c["name"]]["detail"]}'} for c in checks if c['name'] in judged]
    rows += [{'name': c['name'], 'file': c['file'], 'status': s, 'detail': d} for c, s, d in done]
    # 검사가 하나도 없으면 목록을 못 읽은 것이지 통과가 아니다
    ok = bool(rows) and all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': round(time.time() - t0), 'rows': rows,
            'detail': f'{sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'
                      + (f'(CI {len(judged)}개, 로컬 {len(done)}개)' if ci else '')}


def stage_sweep(ctx):
    if ctx.get('ci'):
        return stage_sweep_ci(ctx)
    if 'rom' not in ctx:
        return {'status': 'failed', 'seconds': 0, 'detail': '빌드한 롬이 없음', 'rows': []}
    rows, secs_all = [], 0
    for s in sweeps():
        seeds = seed_list(int(s.get('seeds', ctx['seeds_n'])), failed_seeds(s))
        out = ctx['dir'] / 'sweep' / s['name']
        cmd = s['run'].format(rom=ctx['rom'].relative_to(ROOT), out=out.relative_to(ROOT),
                              seeds=','.join(map(str, seeds)))
        log = ctx['logs'] / f'{s["name"]}.log'
        code, secs = sh(cmd, log, env_for(ctx), ctx['timeout'] * 4)
        rows.append({'name': s['name'], 'file': s['file'], 'seeds': seeds, 'seconds': secs,
                     'status': 'passed' if code == 0 else 'failed',
                     'state_cache': state_note(log.read_text(encoding='utf-8', errors='replace')) if log.exists() else [],
                     'detail': '시간 제한' if code is None else f'종료 코드 {code}'})
        secs_all += secs
    ok = bool(rows) and all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': secs_all, 'rows': rows,
            'detail': f'{sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'}


def stage_sweep_ci(ctx):
    """CI 조각이 돈 스윕 결과(시드 단위를 합친 것)를 받는다. 에뮬레이터를 돌리지 않는다."""
    rows = []
    for r in ci_sweeps(ctx['ci'], sweeps()):
        seeds = sorted({s for p in r.get('parts') or [] for s in p.get('seeds', [])})
        rows.append({'name': r['name'], 'file': r['file'], 'status': r['status'], 'seeds': seeds,
                     'seconds': int(m[1]) if (m := guards.SECONDS.match(r['detail'])) else 0, 'state_cache': [],
                     'detail': f'CI: {r["detail"]}'})
    ok = bool(rows) and all(r['status'] == 'passed' for r in rows)
    return {'status': 'passed' if ok else 'failed', 'seconds': 0, 'rows': rows,
            'detail': f'CI {sum(r["status"] == "passed" for r in rows)}/{len(rows)} 통과'}


def build_path_files(root=ROOT):
    """빌드 경로 파일: dq4publish.inputs()(dq4build.py 에서 닿는 도구 폴더 파일) 가운데 시험이 아닌 .py."""
    sys.path.insert(0, str(ROOT / 'sfc' / 'dq4' / 'tools'))
    import dq4publish
    return sorted(str(root / f) for f in dq4publish.inputs() if f.suffix == '.py' and not f.name.startswith('test_'))


COVERAGE_FORMAT = 'release-coverage-1'
COVERAGE_KINDS = ('unit', 'build')


def coverage_rc(path, data):
    path.write_text(f'[run]\nparallel = true\npatch = subprocess\ndata_file = {data}\n', encoding='utf-8')


def coverage_paths(logs, tag):
    """tag 몫 coverage 기록 파일과 설정 파일. 설정은 처음 부를 때 쓴다(같은 tag 의 단계들이 한 기록에 모인다)."""
    data = logs / f'coverage-{tag}' / '.coverage'
    rc = logs / f'coverage-{tag}.ini'
    if not rc.is_file():
        data.parent.mkdir(parents=True, exist_ok=True)
        coverage_rc(rc, data)
    return data, rc


def covered_units(root, logs, tag, env):
    """root 에서 UNIT_DIRS 단위 테스트 전부를 coverage 로. 실패한 폴더 목록."""
    _, rc = coverage_paths(logs, tag)
    failed = []
    for d in UNIT_DIRS:
        if not (root / d).is_dir():
            failed.append(f'{d}(폴더 없음)')
            continue
        code, _ = sh(f"cd {root / d} && uv run --locked coverage run --rcfile={rc} -m unittest discover -p 'test_*.py'",
                     logs / f'coverage-{tag}-{d.replace("/", "-")}.log', env)
        if code != 0:
            failed.append(d)
    return failed


def covered_build(root, logs, tag, env, build_out):
    """출하 롬 빌드 한 번을 coverage 로(단계 스크립트까지). 실패하면 ['build']."""
    _, rc = coverage_paths(logs, tag)
    # 빌드 단계 캐시가 맞으면 단계 스크립트가 돌지 않아 재지 못한다. 연습이어도 끈다
    code, _ = sh(f'cd {root} && uv run --locked coverage run --rcfile={rc} sfc/dq4/tools/dq4build.py --out {build_out}',
                 logs / f'coverage-{tag}-build.log', dict(env if env is not None else os.environ, DQ4_BUILD_CACHE='off'))
    return ['build'] if code != 0 else []


def coverage_result(root, logs, tag, extra=None):
    """tag 몫 기록을 모아 extra({저장소 상대 경로: 실행한 줄}, CI 가 잰 것)를 더하고 빌드 경로 파일로 보고서를 쓴다.
    (퍼센트, 빌드 경로 파일마다 실행한 줄 {저장소 상대 경로: [줄]})."""
    import coverage
    data, rc = coverage_paths(logs, tag)
    # combine 은 이미 모은 기록을 지우고 조각들로 새로 쓴다. 다시 불러도 앞서 모은 것이 남게 조각으로 돌린다
    if data.is_file():
        data.rename(data.with_name(f'{data.name}.combined'))
    cov = coverage.Coverage(data_file=str(data), config_file=str(rc))
    cov.combine(strict=False)
    files = build_path_files(root)
    if extra:
        # coverage 는 실제 경로(심볼릭 링크를 푼 것)로 적고 보고서도 그것으로 찾는다
        cov.get_data().add_lines({os.path.realpath(root / rel): lines for rel, lines in extra.items()
                                  if (root / rel).is_file()})
    cov.save()
    with open(logs / f'coverage-{tag}-report.txt', 'w', encoding='utf-8') as out:
        try:
            percent = cov.report(include=files, file=out, ignore_errors=True)
        except coverage.exceptions.NoDataError:
            percent = 0.0
    real = {os.path.realpath(f): f for f in files}
    got = cov.get_data()
    lines = {}
    for f in got.measured_files():
        if os.path.realpath(f) in real:
            rel = Path(real[os.path.realpath(f)]).relative_to(root).as_posix()
            lines[rel] = sorted(set(lines.get(rel, [])) | set(got.lines(f) or []))
    return round(percent, 1), lines


def measure(root, logs, tag, env, build_out=None, units=True):
    """root 에서 단위 테스트 전부(units 가 거짓이면 이미 같은 tag 로 돈 것을 씀)와 build_out 이 있으면 빌드 한 번을
    coverage 로 돌려 (퍼센트, 단계 실패 목록)."""
    failed = covered_units(root, logs, tag, env) if units else []
    if build_out is not None:
        failed += covered_build(root, logs, tag, env, build_out)
    return coverage_result(root, logs, tag)[0], failed


def ci_coverage(kind, out, build_out=None, root=ROOT):
    """CI cold-build 잡이 부른다. kind 'unit' 은 롬·도구 없는 지금 환경에서 단위 전부, 'build' 는 빌드 한 번을 coverage
    로 재 out 에 빌드 경로 파일마다 실행한 줄을 적는다(롬 바이트는 들지 않는다). 단위 실패는 기록만 하고 0, 빌드
    실패는 1(빌드 단계가 실패해야 한다)."""
    logs = root / 'work' / 'ci-coverage' / kind
    shutil.rmtree(logs, ignore_errors=True)
    logs.mkdir(parents=True)
    if kind == 'unit':
        failed = covered_units(root, logs, kind, None)
    else:
        failed = covered_build(root, logs, kind, None, build_out)
    percent, lines = coverage_result(root, logs, kind)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'format': COVERAGE_FORMAT, 'commit': guards.git('rev-parse', 'HEAD').strip(),
                               'kind': kind, 'percent': percent, 'failed': failed, 'lines': lines}) + '\n',
                   encoding='utf-8')
    print(f'[coverage] {kind}: 빌드 경로 {percent}%, 실패 {failed or "없음"}', flush=True)
    for log in sorted(logs.glob('coverage-*.log')):
        text = log.read_text(encoding='utf-8', errors='replace').splitlines()
        print(f'--- {log.name}', *text[-(60 if failed else 3):], sep='\n', flush=True)
    return 1 if kind == 'build' and failed else 0


def load_coverage(folder, commit):
    """folder 의 CI 커버리지 기록(ci_coverage) {kind: 기록}. 커밋이 다르면 ValueError."""
    out = {}
    for f in sorted(Path(folder).rglob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('format') == COVERAGE_FORMAT:
            if data['commit'] != commit:
                raise ValueError(f'{f.name}: CI 커버리지의 커밋 {data["commit"][:12]} 이 조각 결과와 다름')
            out[data['kind']] = data
    return out


def coverage_problems(local, ci, failed):
    problems = [f'{n} 시험이 실패함(커버리지 실행)' for n in failed]
    if local < LOCAL_MIN:
        problems.append(f'로컬 {local}% < {LOCAL_MIN}%')
    if ci < CI_MIN:
        problems.append(f'CI 와 같게 {ci}% < {CI_MIN}%')
    return problems


def stage_coverage(ctx):
    """--ci-report 면 빌드와 롬 없는 단위는 CI(cold-build 잡) 기록을 쓰고, 로컬은 단위만(unit 단계가 coverage 로
    돌았으면 그 기록). 아니면 둘 다 로컬에서 잰다."""
    t0 = time.time()
    logs = ctx['logs']
    units = not ctx.get('unit_covered')
    if ctx.get('ci') is not None:
        got = ctx['ci'].get('coverage') or {}
        missing = [k for k in COVERAGE_KINDS if k not in got]
        if missing:
            return {'status': 'failed', 'seconds': round(time.time() - t0),
                    'detail': f'CI 커버리지 기록 없음({", ".join(missing)}, build-digest-release-cold-ch1 artifact 를 받는다)'}
        failed = (covered_units(ROOT, logs, 'local', env_for(ctx)) if units else list(ctx.get('unit_failed', [])))
        failed += [f'CI {n}' for k in COVERAGE_KINDS for n in got[k]['failed']]
        local = coverage_result(ROOT, logs, 'local', extra=got['build']['lines'])[0]
        ci = coverage_result(ROOT, logs, 'ci', extra=got['unit']['lines'])[0]
    else:
        local, failed = measure(ROOT, logs, 'local', env_for(ctx), ctx['dir'] / 'coverage-build', units=units)
        failed = list(ctx.get('unit_failed', [])) + failed if not units else failed
        tmp = ctx['dir'] / 'ci-tree'
        guards.git('worktree', 'add', '--detach', str(tmp), 'HEAD')
        try:
            ci, cfail = measure(tmp, logs, 'ci', env_for(ctx, {k: v for k, v in os.environ.items() if k not in CI_UNSET}))
        finally:
            guards.git('worktree', 'remove', '--force', str(tmp))
        failed += cfail
    problems = coverage_problems(local, ci, failed)
    return {'status': 'failed' if problems else 'passed', 'seconds': round(time.time() - t0), 'local': local, 'ci': ci,
            'detail': f'로컬 {local}%, CI 와 같게 {ci}%' + (f' — {"; ".join(problems)}' if problems else '')}


RUN = {'build': stage_build, 'unit': stage_unit, 'guards': stage_guards, 'sweep': stage_sweep,
       'coverage': stage_coverage}


def run_stages(ctx, wanted):
    """wanted 단계를 차례로 돌린다. 단계가 예외로 멈추면 그 단계를 failed 로 적고 다음 단계로 간다."""
    stages = {}
    for name in STAGES:
        if name not in wanted:
            continue
        print(f'[release] {name}', flush=True)
        t0 = time.time()
        with Load(ROOT.name) as load:
            try:
                stages[name] = RUN[name](ctx)
            except Exception as e:
                # 단계 하나가 멈춰도 보고서는 남긴다
                stages[name] = {'status': 'failed', 'seconds': round(time.time() - t0),
                                'detail': f'단계가 멈춤: {type(e).__name__}: {e}'}
        stages[name]['load'] = load.summary()
        print(f'[release] {name}: {stages[name]["status"]} ({stages[name].get("detail", "")})', flush=True)
    return stages


def commit():
    """(HEAD, 고친 것·추적 안 된 파일이 있는가). 무시하는 파일(work/ 등)은 보지 않는다. 추적 안 된 빌드 입력도 결과에
    닿을 수 있어 센다."""
    head = guards.git('rev-parse', 'HEAD').strip()
    dirty = bool(guards.git('status', '--porcelain', '--untracked-files=normal').strip())
    return head, dirty


def verdict(stages, rehearse, wanted, dirty=False):
    """보고서 전체 판정: 고친 것 없는 커밋에서 모든 단계가 통과하고 연습(--rehearse)이 아닐 때만 passed. 캐시를 끄는
    것은 단계 환경이 하고, 여기서는 rehearse 만 본다."""
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
             f'- 시각: {report["when"]}']
    if report.get('ci'):
        ci = report['ci']
        lines.append(f'- CI: 조각 {ci["shards"]}개에서 검사 {ci["ran"]}개·스윕 {ci.get("sweeps", 0)}개, 로컬 몫 {ci["local"]}개')
    lines += ['', '| 단계 | 결과 | 시간 | 내용 |', '| --- | --- | --- | --- |']
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
            for r in rows:
                seeds = r.get('seeds') or []
                first = f'({seeds[0]}~)' if seeds else ''
                lines.append(f'| {r["name"]} | {words.get(r["status"], r["status"])} | {len(seeds)}개{first} | '
                             f'{r["seconds"]}초 | {",".join(r.get("state_cache") or []) or "-"} |')
    lines += ['', f'- 상태 캐시: {report.get("states", "-")}']
    load = {n: st['load'] for n, st in report['stages'].items() if st.get('load')}
    if load:
        lines += ['', '## 같은 머신의 MesenCE(30초마다 셈)', '', '| 단계 | 다른 워크트리 최대 | 평균 | 워크트리마다 최대 |',
                  '| --- | --- | --- | --- |']
        lines += [f'| {n} | {v["others_max"]} | {v["others_avg"]} | '
                  f'{", ".join(f"{k} {c}" for k, c in sorted(v["peak_by_tree"].items())) or "-"} |' for n, v in load.items()]
    return '\n'.join(lines) + '\n'


def write_report(dest, report):
    """report.json 을 먼저 쓰고 report.md 를 쓴다. 표를 만들다 멈춰도 판정 줄은 report.md 에 남긴다."""
    (dest / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    try:
        md = markdown(report)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
        md = (f'# 배포 관문 보고서\n\n- 판정: **{report.get("verdict")}**\n'
              f'- 표를 만들지 못함: {type(e).__name__}: {e}(report.json 을 본다)\n')
    (dest / 'report.md').write_text(md, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stages', default=','.join(STAGES), help='돌릴 단계(쉼표). 일부만 돌리면 판정은 partial')
    ap.add_argument('--rehearse', action='store_true', help='검사 결과·장면 캐시를 쓴다(빠름, 배포 근거 아님)')
    ap.add_argument('--seeds-n', type=int, default=SEEDS_N, help='release.toml 에 seeds 가 없는 스윕의 시드 수')
    ap.add_argument('--parallel', type=int, default=2)
    ap.add_argument('--timeout', type=int, default=1800, help='실행 검사 하나의 시간 제한(초). 스윕은 이것의 네 배')
    ap.add_argument('--ci-report', type=Path, metavar='DIR',
                    help='배포 관문 워크플로의 조각 결과 폴더. guards·sweep 단계는 CI 결과를 쓰고 로컬 몫만 돌린다')
    ap.add_argument('--ci-summary', type=Path, metavar='DIR',
                    help='조각 결과를 요약해 Markdown 으로 찍고 끝낸다(CI report 잡). 모두 통과가 아니면 1')
    ap.add_argument('--require-build', action='store_true',
                    help='--ci-summary: 캐시 빌드와 무캐시 빌드의 대조가 있고 같아야 통과(배포 관문)')
    ap.add_argument('--require-sweeps', action='store_true',
                    help='--ci-summary: release.toml 스윕이 모두 CI 에서 통과해야 통과(sweeps 를 돌린 관문). 없으면 스윕은 '
                         'CI 에 있는 것만 본다(PR·cache-warm)')
    ap.add_argument('--ci-coverage', nargs=2, metavar=('KIND', 'OUT'),
                    help='CI cold-build 잡: unit(단위 전부) 또는 build(--build-out 으로 빌드 한 번)를 coverage 로 재 OUT 에 적는다')
    ap.add_argument('--build-out', type=Path, help='--ci-coverage build 의 빌드 출력 폴더')
    a = ap.parse_args()
    if a.ci_coverage:
        kind, out = a.ci_coverage
        if kind not in COVERAGE_KINDS or (kind == 'build') != bool(a.build_out):
            ap.error('--ci-coverage KIND 는 unit 또는 build, --build-out 은 build 에만')
        return ci_coverage(kind, out, a.build_out)
    if a.ci_summary:
        try:
            text, ok = ci_summary(load_ci(a.ci_summary), a.require_build, sweeps() if a.require_sweeps else None)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f'# 배포 관문 CI 결과\n\n- 조각 결과를 읽지 못함: {type(e).__name__}: {e}')
            return 1
        print(text, end='')
        return 0 if ok else 1
    wanted = [s for s in a.stages.split(',') if s]
    bad = [s for s in wanted if s not in STAGES]
    if bad:
        ap.error(f'모르는 단계 {bad}')
    head, dirty = commit()
    ci = None
    if a.ci_report:
        try:
            ci = load_ci(a.ci_report)
        except (OSError, ValueError, KeyError, TypeError) as e:
            ap.error(f'--ci-report: {type(e).__name__}: {e}')
        if ci['commit'] != head:
            ap.error(f'--ci-report: CI 커밋 {ci["commit"][:12]} 이 HEAD {head[:12]} 와 다름')
        if ci['cached'] and not a.rehearse:
            ap.error('--ci-report: 캐시를 쓴 CI 실행(release-gate rehearse)이라 배포 근거가 아님. --rehearse 와 함께만 받는다')
        if not a.rehearse and not (ci['build'] and ci['build']['ok']):
            ap.error('--ci-report: CI 의 캐시 빌드가 같은 실행의 무캐시 빌드와 같다는 대조가 '
                     + ('어긋남' if ci['build'] else '없음(build-digest artifact 도 받는다)'))
    root = ROOT / 'work' / 'release'
    tmp = root / f'run-{os.getpid()}'
    (tmp / 'logs').mkdir(parents=True, exist_ok=True)
    ctx = {'dir': tmp, 'logs': tmp / 'logs', 'rehearse': a.rehearse, 'seeds_n': a.seeds_n, 'parallel': a.parallel,
           'timeout': a.timeout, 'ci': ci, 'cover': 'unit' in wanted and 'coverage' in wanted}
    states = '공유 캐시(연습)' if a.rehearse else '이 실행에서 새로 만듦(첫 생성 뒤 이 실행 안에서만 다시 씀)'
    stages = run_stages(ctx, wanted)
    end_head, end_dirty = commit()
    dirty = dirty or end_dirty or end_head != head
    report = {'verdict': verdict(stages, a.rehearse, wanted, dirty), 'commit': head, 'dirty': dirty,
              'rom_sha1': ctx.get('rom_sha1'), 'when': time.strftime('%Y-%m-%d %H:%M'), 'rehearse': a.rehearse,
              'states': states,
              'ci': {'shards': ci['shards'], 'ran': len(ci['rows']), 'sweeps': len(ci['sweeps']),
                     'local': len(ci['local'])} if ci else None,
              'stages': stages}
    # 이 폴더 이름 규칙을 바꾸면 dq4publish.check_report 도 함께 바꾼다(배포판은 이 자리의 보고서만 받는다)
    dest = root / (ctx['rom_sha1'][:12] if ctx.get('rom_sha1') else f'nobuild-{head[:12]}')
    if dest.exists():
        dest = dest.with_name(f'{dest.name}-{time.strftime("%Y%m%d-%H%M%S")}')
    tmp.rename(dest)
    write_report(dest, report)
    print(f'[release] 판정 {report["verdict"]}, 보고서 {dest.relative_to(ROOT)}/report.md', flush=True)
    return 0 if report['verdict'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
