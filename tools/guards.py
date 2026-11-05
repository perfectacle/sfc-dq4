"""회귀 가드 목록 검사. 규칙은 .agents/skills/guards/SKILL.md (GUARD-01~03).

트랙마다 자기 폴더에 guards.toml 을 두고, 롬이 있어야 도는 실행 검사를 등록한다.

    [[check]]
    name = "dq4-compat-walk"            # PR 본문에 적는 이름(소문자·숫자·-)
    why = "무엇이 다시 깨지지 않게 하나"
    paths = ["sfc/dq4/tools/dq4prologue.py"]   # 이 파일을 바꾼 PR 은 이 검사를 돌린다(glob, ** 가능)
    run = "uv run --locked python ..."  # 돌리는 명령
    needs = ["rom", "MESENCE"]          # 돌리는 데 필요한 것. 대문자 이름은 환경 변수로 보고 --base 때 설정됐는지 알린다
    groups = ["ch1-build"]              # (골라 씀) 같은 파일의 [groups] 에 이름 붙인 paths 묶음을 더한다

    [groups]
    ch1-build = ["sfc/dq4/tools/dq4build.py", ...]   # 여러 검사가 함께 쓰는 paths 묶음

검사는 바뀐 파일이 paths(와 묶음)에 맞을 때, 또는 guards.toml 에서 그 검사의 run·needs 가 바뀌었을 때(새 검사 포함)
걸린다.

사용:
  python tools/guards.py                         목록 형식만 검사
  python tools/guards.py --base origin/main      바뀐 파일로 걸리는 검사와 명령을 찍음(PR 올리기 전)
  python tools/guards.py --base origin/main --run
                                                 걸린 검사를 포그라운드로 함께 돌리고 본문 결과 줄을 찍음
  python tools/guards.py --base SHA --pr-body FILE
                                                 걸린 검사마다 본문에 결과 줄이 있는지 봄(CI)

--run 은 같은 입력(.md 를 뺀 추적 파일 내용, 명령, --rom 롬 SHA-1)으로 이미 통과한 검사를 건너뛴다.
캐시는 원래 체크아웃의 work/cache/guards 에 있어 워크트리끼리 함께 쓴다. --no-cache 는 이 캐시와 검사 안의 캐시를
모두 끄고 전부 돌린다(NO_CACHE_ENV: 장면 캐시 DQ4_READSET=off, 빌드 단계 캐시 DQ4_BUILD_CACHE=off, 서장 끝·시작
상태 캐시는 로그 폴더 아래 빈 states/ 에서 그 실행 동안만).

결과 줄: `- [x] <이름>: 통과 (…)` 또는 `- [x] <이름>: 해당 없음 — <이유>`. 그 밖의 글(「통과하지 못함」 등)은 실패로 친다.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import signal
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesence_settings import settings_digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
ENV = re.compile(r'^[A-Z][A-Z0-9_]*$')
FIELDS = {'name': str, 'why': str, 'paths': list, 'run': str, 'needs': list}
OPTIONAL = {'groups': list}
# 이 값이 바뀌면 검사 결과가 바뀔 수 있다(why 는 설명, paths·groups 는 고르는 데만 씀)
RESULT_FIELDS = ('run', 'needs')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def tracked():
    return [line for line in git('ls-files').splitlines() if line]


def matches(path, pattern):
    return PurePosixPath(path).full_match(pattern)


def load(files, read=lambda f: (ROOT / f).read_text(encoding='utf-8')):
    """(검사 목록, 문제 목록). 검사는 {'file': guards.toml, **항목}. files 는 추적 파일 목록."""
    checks, problems = [], []
    for toml in sorted(f for f in files if PurePosixPath(f).name == 'guards.toml'):
        try:
            data = tomllib.loads(read(toml))
        except tomllib.TOMLDecodeError as e:
            problems.append(f'{toml}: TOML 오류 {e}')
            continue
        for key in data:
            if key not in ('check', 'groups'):
                problems.append(f'{toml}: 모르는 키 {key}')
        groups = data.get('groups', {})
        if not isinstance(groups, dict):
            problems.append(f'{toml}: groups 는 [groups] 표여야 함')
            groups = {}
        for gname, pats in groups.items():
            if not NAME.match(gname):
                problems.append(f'{toml} groups.{gname}: 이름은 소문자·숫자·- 만')
            if not isinstance(pats, list) or not pats:
                problems.append(f'{toml} groups.{gname}: 비어 있지 않은 목록이어야 함')
                continue
            for pattern in pats:
                if not isinstance(pattern, str) or not any(matches(f, pattern) for f in files):
                    problems.append(f'{toml} groups.{gname}: {pattern!r} 에 맞는 추적 파일이 없음')
        items = data.get('check', [])
        if not isinstance(items, list):
            problems.append(f'{toml}: check 는 [[check]] 배열이어야 함')
            continue
        for i, item in enumerate(items):
            where = f'{toml} check[{i}]'
            if not isinstance(item, dict):
                problems.append(f'{where}: 표가 아님')
                continue
            for key, kind in FIELDS.items():
                if not isinstance(item.get(key), kind):
                    problems.append(f'{where}: {key} 가 없거나 {kind.__name__} 가 아님')
            for key in item:
                if key not in FIELDS and key not in OPTIONAL:
                    problems.append(f'{where}: 모르는 키 {key}')
            used = item.get('groups', [])
            if not isinstance(used, list):
                problems.append(f'{where}: groups 가 list 가 아님')
                used = []
            for g in used:
                if g not in groups or not isinstance(groups.get(g), list):
                    problems.append(f'{where}: 묶음 {g!r} 이 {toml} 의 [groups] 에 없음')
            if isinstance(item.get('name'), str) and not NAME.match(item['name']):
                problems.append(f'{where}: 이름 {item["name"]!r} 은 소문자·숫자·- 만')
            if isinstance(item.get('paths'), list):
                if not item['paths'] and not used:
                    problems.append(f'{where}: paths 가 비어 있음')
                for pattern in item['paths']:
                    if not isinstance(pattern, str) or not any(matches(f, pattern) for f in files):
                        problems.append(f'{where}: paths {pattern!r} 에 맞는 추적 파일이 없음')
            if all(isinstance(item.get(k), kind) for k, kind in FIELDS.items()):
                extra = [p for g in used if isinstance(groups.get(g), list) for p in groups[g] if isinstance(p, str)]
                checks.append({'file': toml, **item, 'paths': [*item['paths'], *extra]})
    seen = {}
    for c in checks:
        name = c.get('name')
        if name in seen:
            problems.append(f'{c["file"]}: 이름 {name} 이 {seen[name]} 에도 있음')
        seen.setdefault(name, c['file'])
    return checks, problems


def unset_env(needs, environ=os.environ):
    """needs 가운데 환경 변수 이름인데 지금 비어 있는 것."""
    return [n for n in needs if ENV.match(n) and not environ.get(n)]


PLACEHOLDER = re.compile(r'<[^<>]+>')


def made_paths(run):
    """마지막 단계 앞의 단계들이 --out 으로 만드는 경로(파일 또는 폴더)."""
    return [m for st in run.split('&&')[:-1] for m in re.findall(r'--out\s+(\S+)', st)]


def under(path, base):
    p, b = PurePosixPath(path).parts, PurePosixPath(base).parts
    return p[:len(b)] == b


def rom_of(run):
    """마지막 단계(검사)가 읽는 --rom 경로. 앞 단계가 만드는 롬이면 None(돌리기 전엔 알 수 없음)."""
    m = re.search(r'--rom\s+(\S+)', run.split('&&')[-1])
    if not m:
        return None
    return None if any(under(m[1], d) for d in made_paths(run)) else m[1]


def builds(run):
    """마지막 단계 앞에 --out 으로 무언가를 만드는 단계가 있는지(롬 빌드)."""
    return bool(made_paths(run))


def out_dirs(run):
    """마지막 단계의 --out 가운데 work/<이름>… 폴더(검사 출력. 돌리기 전에 비운다). work 자체와 공유 캐시는 뺀다."""
    stage = run.split('&&')[-1]
    keep = []
    for d in re.findall(r'--out\s+(\S+)', stage):
        parts = PurePosixPath(d).parts
        if len(parts) >= 2 and parts[0] == 'work' and parts[1] != 'cache' and '..' not in parts:
            keep.append(d)
    return keep


# 이보다 큰 파일은 내용 대신 (크기, mtime_ns) 로 본다
BIG_FILE = 64 << 20


def stat_key(path):
    st = path.stat()
    return f'{st.st_size}:{st.st_mtime_ns}'.encode()


def hash_path(h, path):
    """파일은 내용(BIG_FILE 보다 크면 크기·mtime_ns), 폴더는 그 안 파일들의 (상대 경로, 크기, mtime_ns).
    폴더를 내용째 읽지 않는 것은 needs 의 자원 저장소(수 GB)처럼 큰 폴더도 키를 곧 만들게 하려는 것이다.
    파일을 내용은 그대로 두고 mtime 만 되돌리면 옛 결과로 건너뛸 수 있다. 없으면 표시만."""
    path = Path(path)
    if path.is_file():
        if path.stat().st_size > BIG_FILE:
            h.update(b'big:' + stat_key(path))
        else:
            h.update(hashlib.sha1(path.read_bytes()).digest())
    elif path.is_dir():
        for f in sorted(p for p in path.rglob('*') if p.is_file()):
            h.update(str(f.relative_to(path)).encode() + b'\0' + stat_key(f))
    else:
        h.update(b'-')


def env_names(needs):
    """needs 글에 나오는 환경 변수 이름(설명문 안의 LIBRETRO_BSNES 같은 것도)."""
    return sorted({n for item in needs for n in re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', item)})


# 검사 명령이 읽거나 실행하지 않는 추적 파일. 키에서 빼도 결과가 같다(뺀 것이 결과에 닿는다고 의심되면 넣어 둔다)
#   .md: 문서. guards.toml: 검사 목록(그 검사의 명령과 needs 는 따로 키에 든다). 에이전트·CI 설정, 해킹 일지
NOT_INPUT = re.compile(r'(\.md$|(^|/)guards\.toml$|^\.agents/|^\.github/|^\.claude/|(^|/)journal/)')
# 단위 테스트 파일
TEST_FILE = re.compile(r'((^|/)test_[^/]*\.py$|(^|/)tests/)')


def runs_tests(run):
    """명령이 단위 테스트를 부르는가: unittest·pytest 를 쓰거나 test_*.py·tests/ 의 파일을 바로 돌린다."""
    return bool(re.search(r'\b(unittest|pytest)\b|(^|[\s/])test_\w*\.py\b|(^|[\s/])tests/', run))


def is_input(path, run):
    """그 추적 파일이 이 검사 명령의 결과에 닿을 수 있는가. 단위 테스트를 부르는 명령은 테스트가 무엇을 읽을지 몰라
    .md 만 뺀다."""
    if path.endswith('.md'):
        return False
    if runs_tests(run):
        return True
    return not (NOT_INPUT.search(path) or TEST_FILE.search(path))


def input_key(check, root=ROOT, environ=os.environ):
    """같은 입력이면 같은 키. 추적 파일 가운데 결과에 닿는 것(is_input), 명령, needs 환경 변수가 가리키는 파일·폴더
    (hash_path), MESENCE 가 있으면 MesenCE 사용자 설정 파일, rom/ 원본, 명령이 읽는 파일(앞 단계가 만드는 것 빼고).
    MESENCE 가 있는데 설정 파일을 찾지 못하면 None: 결과에 닿는 입력을 모르므로 캐시를 읽지도 쓰지도 않는다."""
    h = hashlib.sha256()
    run = check['run']
    h.update(run.encode())
    for line in git('ls-files', '-s').splitlines():
        if is_input(line.split('\t', 1)[-1], run):
            h.update(line.encode())
    for f in sorted(x for x in git('diff', '--name-only', 'HEAD').splitlines() if x and is_input(x, run)):
        h.update(f.encode())
        hash_path(h, root / f)
    for n in env_names(check.get('needs', [])):
        v = environ.get(n, '')
        h.update(f'{n}={v}'.encode())
        if v:
            hash_path(h, v)
        if n == 'MESENCE' and v:
            digest = settings_digest(v)
            if digest is None:
                return None
            h.update(b'mesence-settings:' + digest.encode())
    hash_path(h, root / 'rom')
    made = made_paths(run) + out_dirs(run)
    for tok in sorted(set(re.findall(r'(?<![\w/])(work/\S+|rom/\S+)', run))):
        if not any(under(tok, d) for d in made):
            h.update(tok.encode())
            hash_path(h, root / tok)
    return h.hexdigest()


def cache_dir():
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    return common.parent / 'work' / 'cache' / 'guards'


RUNNING = set()


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def no_cache_env(logs):
    """캐시를 모두 끈 검사 환경. 상태 캐시는 logs/states(돌리기 전에 비움)에서 이 실행 동안만 쓴다."""
    return dict(os.environ, DQ4_READSET='off', DQ4_BUILD_CACHE='off', DQ4_STATES_CACHE=str(Path(logs) / 'states'))


def run_check(check, timeout, logs, no_cache=False, env=None):
    """검사 하나를 돌린다. (결과 'passed'|'failed'|'skipped', 본문 괄호 안 글). env 를 주면 그 환경으로 돈다(배포 관문이
    모든 단계에 같은 환경을 쓸 때)."""
    name, run = check['name'], check['run']
    if PLACEHOLDER.search(run):
        return 'skipped', '명령에 <…> 자리가 있어 직접 돌릴 것'
    unset = unset_env(check.get('needs', []))
    if unset:
        return 'skipped', f'설정 안 된 환경 변수 {", ".join(unset)}'
    key = input_key(check)
    hit = cache_dir() / f'{name}-{key[:24]}.json' if key else None
    if hit and hit.is_file() and not no_cache:
        old = json.loads(hit.read_text(encoding='utf-8'))
        return 'passed', f'캐시: 같은 입력으로 {old["when"]} 통과, {old["detail"]}'
    for d in out_dirs(run):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    log = logs / f'{name}.log'
    shown = log.relative_to(ROOT) if log.is_relative_to(ROOT) else log
    t0 = time.time()
    with log.open('w', encoding='utf-8') as out:
        env = env or (no_cache_env(logs) if no_cache else None)
        proc = subprocess.Popen(['bash', '-c', run], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        RUNNING.add(proc)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return 'failed', f'{timeout}초 안에 끝나지 않음, 로그 {shown}'
        finally:
            # 명령이 남긴 백그라운드 자식까지 그룹째 정리
            kill_group(proc)
            proc.wait()
            RUNNING.discard(proc)
    secs = round(time.time() - t0)
    if code:
        return 'failed', f'종료 코드 {code}, 로그 {shown}'
    m = re.search(r'--rom\s+(\S+)', run.split('&&')[-1])
    rom = m[1] if m else None
    detail = f'{secs}초' + (f', 롬 SHA-1 {hashlib.sha1((ROOT / rom).read_bytes()).hexdigest()[:8]}'
                           if rom and (ROOT / rom).is_file() else '')
    # 도는 동안 입력이 바뀌었으면 그 결과는 어느 입력의 것인지 모르므로 캐시하지 않는다
    if key is not None and input_key(check) == key:
        hit.parent.mkdir(parents=True, exist_ok=True)
        hit.write_text(json.dumps({'when': time.strftime('%Y-%m-%d %H:%M'), 'detail': detail}, ensure_ascii=False),
                       encoding='utf-8')
    return 'passed', detail


def run_all(hit, parallel, timeout, no_cache=False):
    """걸린 검사를 parallel 개씩 함께 돌리고 본문 결과 줄을 찍는다. 모두 통과하면 0."""
    done = run_many(hit, parallel, timeout, no_cache)
    print('\nPR 본문 결과 줄:')
    for c, status, detail in done:
        mark, word = ('x', '통과') if status == 'passed' else (' ', '실패' if status == 'failed' else '돌리지 않음')
        print(f'- [{mark}] {c["name"]}: {word} ({detail})')
    return 0 if all(s == 'passed' for _, s, _ in done) else 1


def run_many(hit, parallel, timeout, no_cache=False, logs=None, env=None):
    """검사를 parallel 개씩 함께 돌린다. [(검사, 'passed'|'failed'|'skipped', 글)]."""
    logs = logs or ROOT / 'work' / 'guards'
    logs.mkdir(parents=True, exist_ok=True)
    if no_cache and env is None:
        shutil.rmtree(logs / 'states', ignore_errors=True)
    shown = logs.relative_to(ROOT) if logs.is_relative_to(ROOT) else logs
    print(f'검사 {len(hit)}개를 {parallel}개씩 돌림(로그 {shown})', flush=True)

    def one(c):
        status, detail = run_check(c, timeout, logs, no_cache, env)
        print(f'  {c["name"]}: {status} ({detail})', flush=True)
        return c, status, detail
    # 롬을 스스로 빌드하는 검사는 다른 검사가 읽는 롬을 다시 쓸 수 있어 먼저 홀로 돌린다
    builders = [c for c in hit if builds(c['run'])]
    pool = concurrent.futures.ThreadPoolExecutor(max(1, parallel))
    try:
        done = [one(c) for c in builders]
        futures = [pool.submit(one, c) for c in hit if c not in builders]
        done += [f.result() for f in futures]
    except BaseException:
        # Ctrl-C 등: 도는 검사 그룹을 모두 끄고 남은 일을 버린다
        for proc in list(RUNNING):
            kill_group(proc)
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    return done


def triggered(checks, changed, edited=()):
    """paths(묶음 포함)에 맞는 파일이 바뀌었거나 이름이 edited 에 든 검사."""
    return [c for c in checks if c['name'] in edited or any(matches(f, p) for f in changed for p in c.get('paths', []))]


def edited_checks(base_text, head_text):
    """guards.toml 두 판에서 run·needs 가 다르거나 새로 생긴 검사 이름. 읽지 못하는 판은 빈 것으로 본다."""
    def blocks(text):
        try:
            data = tomllib.loads(text) if text else {}
        except tomllib.TOMLDecodeError:
            return {}
        items = data.get('check', [])
        return {c['name']: tuple(repr(c.get(k)) for k in RESULT_FIELDS)
                for c in (items if isinstance(items, list) else []) if isinstance(c, dict) and isinstance(c.get('name'), str)}
    old, new = blocks(base_text), blocks(head_text)
    return {name for name, v in new.items() if old.get(name) != v}


def edited_in(base, head, changed):
    """base…head 에서 바뀐 guards.toml 마다 run·needs 가 바뀐 검사(merge-base 의 판과 견줌)."""
    mb = git('merge-base', base, head).strip()
    names = set()
    for f in changed:
        if PurePosixPath(f).name != 'guards.toml':
            continue
        def show(rev):
            r = subprocess.run(['git', 'show', f'{rev}:{f}'], cwd=ROOT, capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else ''
        names |= edited_checks(show(mb), show(head))
    return names


# 「통과」 다음은 줄 끝·괄호·대시만(「통과하지 못함」「통과 못 함」을 통과로 읽지 않게)
PASSED = re.compile(r'^통과(?:[ \t]*$|[ \t]*[(（]|[ \t]+[—-])')
NOT_APPLICABLE = re.compile(r'^해당 없음[ \t]*[—-][ \t]*\S')


def body_problems(checks, body):
    """걸린 검사마다 `- [x] 이름: 통과 …` 또는 `- [x] 이름: 해당 없음 — 이유` 줄이 있어야 한다."""
    problems = []
    for c in checks:
        line = re.compile(rf'^[ \t]*[-*][ \t]*\[[xX]\][ \t]*`?{re.escape(c["name"])}`?[ \t]*:[ \t]*(\S.*)$', re.M)
        found = [m[1].strip() for m in line.finditer(body)]
        if not found:
            problems.append(f'{c["name"]}: PR 본문에 결과 줄이 없음 (`- [x] {c["name"]}: 통과 …`)')
        elif not all(PASSED.match(r) or NOT_APPLICABLE.match(r) for r in found):
            problems.append(f'{c["name"]}: 결과는 「통과 (…)」 또는 「해당 없음 — 이유」만: {found}')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', help='이 커밋과 HEAD 사이에 바뀐 파일로 걸리는 검사를 고른다')
    ap.add_argument('--head', default='HEAD', help='바뀐 파일을 볼 끝 커밋(CI 는 PR 의 head SHA: 머지 커밋이면 그 뒤 main 변경까지 걸림)')
    ap.add_argument('--pr-body', type=Path, help='PR 본문 파일. 걸린 검사의 결과 줄을 확인한다')
    ap.add_argument('--run', action='store_true', help='걸린 검사를 돌린다(--base 와 함께)')
    ap.add_argument('--parallel', type=int, default=2, help='--run 에서 함께 돌릴 검사 수(검사마다 안에서 다시 병렬)')
    ap.add_argument('--timeout', type=int, default=1800, help='--run 에서 검사 하나의 시간 제한(초)')
    ap.add_argument('--no-cache', action='store_true', help='--run 에서 검사 캐시·장면 캐시를 모두 끄고 전부 돌린다(배포 관문)')
    args = ap.parse_args()
    files = tracked()
    checks, problems = load(files)
    if args.base:
        changed = [f for f in git('diff', '--name-only', f'{args.base}...{args.head}').splitlines() if f]
        hit = triggered(checks, changed, edited_in(args.base, args.head, changed))
        if hit:
            print('이 변경이 건드리는 실행 검사(돌리고 PR 본문에 결과 줄):')
            for c in hit:
                print(f'- {c["name"]} ({c["file"]}): {c["why"]}\n    {c["run"]}')
                if c.get('needs'):
                    print(f'    필요: {", ".join(c["needs"])}')
                    unset = unset_env(c['needs'])
                    if unset:
                        print(f'    ⚠ 지금 설정 안 된 환경 변수: {", ".join(unset)} (export 한 뒤 돌릴 것)')
                print(f'    본문 줄: - [x] {c["name"]}: 통과 …')
        else:
            print('걸리는 실행 검사 없음')
        if args.pr_body:
            problems += body_problems(hit, args.pr_body.read_text(encoding='utf-8'))
        if args.run and hit and not problems:
            return run_all(hit, args.parallel, args.timeout, args.no_cache)
    elif args.pr_body or args.run:
        ap.error('--pr-body·--run 은 --base 와 함께')
    for p in problems:
        print(f'오류: {p}')
    print(f'가드 {len(checks)}개, 문제 {len(problems)}개')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
