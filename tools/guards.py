"""회귀 가드 목록 검사. 규칙은 .agents/skills/guards/SKILL.md (GUARD-01~03).

트랙마다 자기 폴더에 guards.toml 을 두고, 롬이 있어야 도는 실행 검사를 등록한다.

    [[check]]
    name = "dq4-compat-walk"            # PR 본문에 적는 이름(소문자·숫자·-)
    why = "무엇이 다시 깨지지 않게 하나"
    paths = ["sfc/dq4/tools/dq4prologue.py"]   # 이 파일을 바꾼 PR 은 이 검사를 돌린다(glob, ** 가능)
    run = "uv run --locked python ..."  # 돌리는 명령
    needs = ["rom", "MESENCE"]          # 돌리는 데 필요한 것. 대문자 이름은 환경 변수로 보고 --base 때 설정됐는지 알린다
    groups = ["ch1-build"]              # (골라 씀) 같은 파일의 [groups] 에 이름 붙인 paths 묶음을 더한다
    tier = "release"                    # (골라 씀) "pr"(기본) 또는 "release": 무거워 배포 관문에서만 돌리는 검사

    [groups]
    ch1-build = ["sfc/dq4/tools/dq4build.py", ...]   # 여러 검사가 함께 쓰는 paths 묶음

    [cache]
    key = "paths"                       # (골라 씀) 검사 결과 캐시 키에 넣을 추적 파일. "all"(기본) 또는 "paths"

PR 에서는 바뀐 파일이 그 검사의 paths 에 바로 맞을 때, 또는 guards.toml 에서 그 검사의 run·needs 가 바뀌었을 때(새 검사
포함) 걸린다. 묶음으로만 맞는 검사와 tier = "release" 인 검사는 빠지고 배포 관문(tools/release_check.py)이 돌린다.
PR 본문에 `가드: 전체` 줄이 있거나 --full 을 주면 묶음으로 맞는 것과 release 등급까지 모두 걸린다(빌드 순서·롬 배치·
공용 훅·에뮬레이터 교체처럼 큰 변경).

사용:
  python tools/guards.py                         목록 형식만 검사
  python tools/guards.py --base origin/main      바뀐 파일로 걸리는 검사와 명령을 찍음(PR 올리기 전)
  python tools/guards.py --base origin/main --run
                                                 걸린 검사를 포그라운드로 함께 돌리고 본문 결과 줄을 찍음
  python tools/guards.py --base origin/main --run --full
                                                 묶음으로 맞는 것·release 등급까지 돌림(본문에 `가드: 전체`)
  python tools/guards.py --base SHA --pr-body FILE
                                                 걸린 검사마다 본문에 결과 줄이 있는지 봄(CI)

--run 은 같은 입력(.md 를 뺀 추적 파일 내용, 명령, --rom 롬 SHA-1)으로 이미 통과한 검사를 건너뛴다. [cache] key = "paths"
인 트랙은 추적 파일 가운데 그 검사의 paths·묶음에 맞는 것, 그 트랙의 어느 검사도 paths 에 적지 않은 자료 파일
(.py·.lua·.asm 밖), 의존성 파일만 본다(key_scope).
입력이 달라도 롬을 빌드하는 검사는 빌드 단계를 먼저 돌려, 만든 파일과 .py 밖 입력이 같고 검사 단계가 지난번에 실행한
함수의 코드·연 파일이 모두 같으면 검사 단계를 건너뛴다(run_check, tools/guardtrace).
캐시는 원래 체크아웃의 work/cache/guards 에 있어 워크트리끼리 함께 쓴다. --no-cache 는 이 캐시와 검사 안의 캐시를
모두 끄고 전부 돌린다(no_cache_env(logs): 장면 캐시 DQ4_READSET=off, 빌드 단계 캐시 DQ4_BUILD_CACHE=off, 서장 끝·시작
상태 캐시는 로그 폴더 아래 빈 states/ 에서 그 실행 동안만).

결과 줄: `- [x] <이름>: 통과 (…)` 또는 `- [x] <이름>: 해당 없음 — <이유>`. 그 밖의 글(「통과하지 못함」 등)은 실패로 친다.
"""
import argparse
import concurrent.futures
import functools
import glob
import hashlib
import json
import os
import shutil
import signal
import stat
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesence_settings import settings_digest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
ENV = re.compile(r'^[A-Z][A-Z0-9_]*$')
FIELDS = {'name': str, 'why': str, 'paths': list, 'run': str, 'needs': list}
OPTIONAL = {'groups': list, 'tier': str}
TIERS = ('pr', 'release')
CACHE_KEYS = ('all', 'paths')
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
            if key not in ('check', 'groups', 'cache'):
                problems.append(f'{toml}: 모르는 키 {key}')
        cache = data.get('cache', {})
        if not isinstance(cache, dict) or set(cache) - {'key'} or cache.get('key', 'all') not in CACHE_KEYS:
            problems.append(f'{toml}: [cache] 는 key = {" 또는 ".join(map(repr, CACHE_KEYS))} 만')
            cache = {}
        mine = []
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
            if item.get('tier', 'pr') not in TIERS:
                problems.append(f'{where}: tier 는 {" 또는 ".join(map(repr, TIERS))}')
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
                mine.append({'file': toml, **item, 'own_paths': item['paths'], 'paths': [*item['paths'], *extra]})
        if cache.get('key') == 'paths':
            # 자료 파일의 주인은 낱낱이 적은 경로로만 친다(sfc/dq4/tools/** 같은 glob 은 읽는다는 뜻이 아니다)
            claimed = sorted({p for c in mine for p in c['paths'] if not glob.has_magic(p)})
            for c in mine:
                c['key_claimed'] = claimed
        checks += mine
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
    파일을 내용은 그대로 두고 mtime 만 되돌리면 옛 결과로 건너뛸 수 있다. 폴더 안 cache/ 아래는 내용으로 본다. 없으면 표시만."""
    path = Path(path)
    if path.is_file():
        if path.stat().st_size > BIG_FILE:
            h.update(b'big:' + stat_key(path))
        else:
            h.update(hashlib.sha1(path.read_bytes()).digest())
    elif path.is_dir():
        for f in sorted(p for p in path.rglob('*') if p.is_file()):
            rel = f.relative_to(path)
            # 폴더 안 cache/ 는 빌드가 같은 내용으로 다시 써 mtime 만 바뀌므로 내용으로 본다
            if 'cache' in rel.parts[:-1] and f.stat().st_size <= BIG_FILE:
                h.update(str(rel).encode() + b'\0' + hashlib.sha1(f.read_bytes()).digest())
                continue
            h.update(str(rel).encode() + b'\0' + stat_key(f))
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


# 어느 검사의 키에도 늘 넣는 추적 파일: 모든 검사가 도는 Python 과 의존성
ALWAYS_KEY = frozenset({'uv.lock', 'pyproject.toml', '.python-version'})
# dq4guardpaths 처럼 트랙 시험이 paths 가 덮는지 보는 종류(import·Lua·asm 으로 닿는 코드)
CODE_FILE = re.compile(r'\.(py|lua|asm)$')


@functools.lru_cache(maxsize=None)
def glob_regex(patterns):
    """paths glob 묶음(tuple)을 하나의 정규식으로. matches(PurePosixPath.full_match)와 같은 뜻이고 훨씬 빠르다."""
    return re.compile('|'.join(glob.translate(p, recursive=True, include_hidden=True) for p in patterns) or r'(?!)')


def key_scope(check):
    """검사 결과 캐시 키에 넣을 추적 파일을 고르는 함수. [cache] key = "paths" 인 트랙(key_claimed 가 있음)은 그 검사의
    paths·묶음에 맞는 것, 트랙의 어느 검사도 paths 에 낱낱이 적지 않은 자료 파일(.py·.lua·.asm 밖), ALWAYS_KEY.
    코드와 글자 상수로 이름을 적어 읽는 자료 파일은 트랙 시험(dq4guardpaths)이 paths 가 덮는다고 보장한다. 계산한
    이름으로 여는 자료 파일은 시험이 못 보므로, 주인이 적히지 않은 것은 누가 읽을지 몰라 모두의 키에 둔다.
    그 밖의 트랙은 모두."""
    claimed = check.get('key_claimed')
    if claimed is None:
        return lambda path: True
    own, anyone = glob_regex(tuple(check['paths'])), frozenset(claimed)
    return lambda path: (path in ALWAYS_KEY or bool(own.match(path))
                         or not (CODE_FILE.search(path) or path in anyone))


def input_key(check, root=ROOT, environ=os.environ, built=False):
    """같은 입력이면 같은 키. 추적 파일 가운데 결과에 닿는 것(is_input), 명령, needs 환경 변수가 가리키는 파일·폴더
    (hash_path), MESENCE 가 있으면 MesenCE 사용자 설정 파일, rom/ 원본, 명령이 읽는 파일(앞 단계가 만드는 것 빼고).
    MESENCE 가 있는데 설정 파일을 찾지 못하면 None: 결과에 닿는 입력을 모르므로 캐시를 읽지도 쓰지도 않는다.

    추적 파일은 key_scope 가 고른 것만 본다.

    built 면 빌드 단계를 돌린 뒤의 키(built_hit): 추적 .py 는 빼고(검사 단계가 연 .py 는 캐시 항목이 따로 본다),
    앞 단계가 만든 파일을 내용째 넣는다."""
    h = hashlib.sha256()
    run = check['run']
    h.update(run.encode())

    scope = key_scope(check)

    def counts(path):
        return is_input(path, run) and scope(path) and not (built and path.endswith('.py'))
    for line in git('ls-files', '-s').splitlines():
        if counts(line.split('\t', 1)[-1]):
            h.update(line.encode())
    for f in sorted(x for x in git('diff', '--name-only', 'HEAD').splitlines() if x and counts(x)):
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
    for tok in sorted(set(re.findall(r'(?<![\w/])(?:\$PWD/)?(work/\S+|rom/\S+)', run))):
        if not any(under(tok, d) for d in made):
            h.update(tok.encode())
            hash_path(h, root / tok)
    if built:
        for f in sorted(TRACER.glob('*.py')):
            h.update(f.name.encode() + b'\0' + f.read_bytes())
        # 새 .py 가 import 경로에서 다른 모듈을 가릴 수 있어 추적 .py 이름 목록은 넣는다(내용은 항목이 본다)
        h.update('\0'.join(sorted(x for x in tracked() if x.endswith('.py'))).encode())
        for d in made_paths(run):
            h.update(b'made:' + d.encode())
            hash_content(h, root / d)
    return h.hexdigest()


def hash_content(h, path):
    """파일은 내용, 폴더는 그 안 파일들의 (상대 경로, 내용). BIG_FILE 보다 큰 파일은 크기·mtime_ns 라 다시 만들면 빗나간다."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else []
    if not files:
        h.update(b'-')
    for f in files:
        h.update(str(f.relative_to(path) if f != path else '').encode() + b'\0')
        hash_path(h, f)


TRACER = Path(__file__).resolve().parent / 'guardtrace'
sys.path.insert(0, str(TRACER))
from guardprint import module_prints  # noqa: E402
# 검사 단계 명령의 꼴: 환경 변수 대입 뒤 uv run 의 python 과 스크립트(인터프리터 플래그 없이). 그 밖의 프로그램은
# .py 를 몰래 읽을 수 있고, -I·-E·-S 는 PYTHONPATH 의 추적기를 싣지 않는다
CHECK_STAGE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*=\S*\s+)*uv run --(locked|frozen) python\s+(?P<script>[^\s-]\S*\.py)(\s|$)')
# 빌드 단계가 검사 단계에 남기는 셸 상태
SHELL_STATE = re.compile(r'(^|&&)\s*(cd|export|source|\.|set|unset|alias|pushd|popd|shopt|umask)\s')


def split_built(check):
    """빌드 결과 캐시를 쓸 수 있으면 (앞 단계들, 검사 단계) 명령, 아니면 None. 앞 단계가 무언가를 --out 으로 만들고,
    단위 테스트를 부르지 않으며, 셸 상태를 바꾸지 않고, && 말고 다른 연결(; || | & 줄바꿈)·따옴표·$( ) 가 없고,
    검사 단계가 CHECK_STAGE 꼴이어야 한다."""
    run = check['run']
    if not builds(run) or runs_tests(run) or SHELL_STATE.search(run) or re.search(r'[;\n`"\'\\]|\$\(|\|\||(?<![&|])[&|](?![&|])', run):
        return None
    stages = run.split('&&')
    if not CHECK_STAGE.match(stages[-1]):
        return None
    return '&&'.join(stages[:-1]), stages[-1]


def shadowed():
    """추적기를 가릴 수 있는 추적 sitecustomize.py(스크립트 폴더가 PYTHONPATH 보다 앞이다)가 있는가."""
    return any(PurePosixPath(f).name in ('sitecustomize.py', 'usercustomize.py') and not under(f, 'tools/guardtrace')
               for f in tracked())


def read_trace(reads, script=None):
    """검사 단계 기록을 {'files', 'dirs', 'stats': {경로: 값}, 'code': {경로: {qualname: [실행한 지문…]}}} 로.
    `?`, 기록 없음, 검사 단계 스크립트(script)의 S 줄이 없음(맨 위 Python 이 추적기를 싣지 않음), 같은 경로가 다른
    값으로 두 번(도는 중에 바뀜), 읽지 못한 파일(-)이면 None."""
    if not reads.is_file():
        return None
    out = {'files': {}, 'dirs': {}, 'stats': {}, 'links': {}, 'code': {}}
    starts = set()
    for line in reads.read_text(encoding='utf-8', errors='surrogateescape').splitlines():
        f = line.split('\t')
        kind = f[0]
        if kind == 'S' and len(f) == 2:
            starts.add(f[1])
        elif kind in ('F', 'D', 'E', 'L') and len(f) == 3:
            table = out[{'F': 'files', 'D': 'dirs', 'E': 'stats', 'L': 'links'}[kind]]
            if (kind == 'F' and f[2] == '-') or table.setdefault(f[1], f[2]) != f[2]:
                return None
        elif kind == 'C' and len(f) == 4:
            fps = out['code'].setdefault(f[1], {}).setdefault(f[2], [])
            if f[3] not in fps:
                fps.append(f[3])
        else:
            return None
    if script is not None and script not in starts:
        return None
    return out


def sha1_of(path):
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else None


def content_sig(path):
    """추적기(sitecustomize.content_sig)와 같은 표지."""
    if not path.is_file():
        return None
    st = path.stat()
    return f'big:{st.st_size}:{st.st_mtime_ns}' if st.st_size > BIG_FILE else sha1_of(path)


def stat_state(path):
    try:
        st = os.stat(path)
    except OSError:
        return '-'
    return 'dir' if stat.S_ISDIR(st.st_mode) else str(st.st_size)


def link_of(path):
    try:
        return os.readlink(path)
    except OSError:
        return '-'


def listing_of(path):
    if not path.is_dir():
        return None
    return hashlib.sha1('\0'.join(sorted(os.listdir(path))).encode('utf-8', 'surrogateescape')).hexdigest()


def code_prints(path):
    return module_prints(path.read_bytes(), str(path)) if path.is_file() else None


def entry_holds(entry, root):
    """캐시 항목이 지금도 맞는가: 연 파일·본 폴더·stat 으로 본 것·거쳐 간 링크가 같고, 실행한 코드가 든 파일마다 원본이 같거나
    실행한 qualname 들의 지문 목록(차례 포함)이 같다."""
    if any(content_sig(root / p) != v for p, v in entry['files'].items()):
        return False
    if any(listing_of(root / p) != v for p, v in entry['dirs'].items()):
        return False
    if any(stat_state(root / p) != v for p, v in entry['stats'].items()):
        return False
    if 'links' not in entry or any(link_of(root / p) != v for p, v in entry['links'].items()):
        return False
    for p, (src, quals) in entry['code'].items():
        if sha1_of(root / p) == src:
            continue
        prints = code_prints(root / p)
        if prints is None or any(prints.get(q) != v for q, v in quals.items()):
            return False
    return True


def trace_entry(trace, root):
    """read_trace 결과를 캐시 항목으로. 실행한 qualname 마다 지금 파일의 같은 이름 지문 목록을 담는데, 실행한 지문이
    하나라도 그 목록에 없으면(도는 중에 고침) None."""
    code = {}
    for p, quals in trace['code'].items():
        prints = code_prints(root / p)
        if prints is None:
            return None
        kept = {}
        for q, fps in quals.items():
            if q not in prints or any(fp not in prints[q] for fp in fps):
                return None
            kept[q] = prints[q]
        code[p] = [sha1_of(root / p), kept]
    return {'files': trace['files'], 'dirs': trace['dirs'], 'stats': trace['stats'], 'links': trace['links'], 'code': code}


def load_entries(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{time.monotonic_ns()}')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def built_hit(name, key, root):
    """같은 빌드 결과 키로 통과한 기록 가운데 지금도 맞는 것(entry_holds)."""
    for old in load_entries(cache_dir() / 'built' / f'{name}-{key[:24]}.json'):
        try:
            if entry_holds(old['trace'], root):
                return old
        except (KeyError, TypeError, ValueError):
            continue
    return None


def save_built(name, key, detail, trace):
    path = cache_dir() / 'built' / f'{name}-{key[:24]}.json'
    olds = [o for o in load_entries(path) if o.get('trace') != trace][-7:]
    olds.append({'when': time.strftime('%Y-%m-%d %H:%M'), 'detail': detail, 'trace': trace})
    write_atomic(path, json.dumps(olds, ensure_ascii=False))


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


def spawn(command, log, timeout, env):
    """bash 로 명령 하나를 돌려 로그에 덧붙인다. 종료 코드, 시간을 넘기면 None."""
    with log.open('a', encoding='utf-8') as out:
        proc = subprocess.Popen(['bash', '-c', command], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        RUNNING.add(proc)
        try:
            return proc.wait(timeout=max(1, timeout))
        except subprocess.TimeoutExpired:
            return None
        finally:
            # 명령이 남긴 백그라운드 자식까지 그룹째 정리
            kill_group(proc)
            proc.wait()
            RUNNING.discard(proc)


def run_check(check, timeout, logs, no_cache=False, env=None):
    """검사 하나를 돌린다. (결과 'passed'|'failed'|'skipped', 본문 괄호 안 글). env 를 주면 그 환경으로 돈다(배포 관문이
    모든 단계에 같은 환경을 쓸 때).

    입력 키가 빗나가도 롬을 빌드하는 검사(split_built)는 빌드 단계만 먼저 돌린다. 만든 파일·.py 밖 입력이 같고, 지난
    통과 때 검사 단계가 실행한 함수의 코드와 연 파일·본 폴더가 모두 같으면(entry_holds) 검사 단계를 건너뛴다. 검사
    단계는 tools/guardtrace 를 PYTHONPATH 앞에 두고 돌려 그것들을 적는다. 롬이 그대로이고 검사가 실행하지 않는
    함수만 고친 PR 이 실행 검사를 다시 돌지 않게 한다."""
    name, run = check['name'], check['run']
    if PLACEHOLDER.search(run):
        return 'skipped', '명령에 <…> 자리가 있어 직접 돌릴 것'
    unset = unset_env(check.get('needs', []))
    if unset:
        return 'skipped', f'설정 안 된 환경 변수 {", ".join(unset)}'
    key = input_key(check, ROOT)
    hit = cache_dir() / f'{name}-{key[:24]}.json' if key else None
    if hit and hit.is_file() and not no_cache:
        old = json.loads(hit.read_text(encoding='utf-8'))
        return 'passed', f'캐시: 같은 입력으로 {old["when"]} 통과, {old["detail"]}'
    # 같은 크기로 같은 초 안에 고친 원본은 옛 .pyc 를 그대로 쓰므로, 단계마다 빈 곳에서 새로 컴파일한다
    pycaches = []

    def fresh(e):
        pycaches.append(Path(tempfile.mkdtemp(prefix=f'guard-{name}-pyc-')))
        return dict(e, PYTHONPYCACHEPREFIX=str(pycaches[-1]))
    try:
        log = logs / f'{name}.log'
        shown = log.relative_to(ROOT) if log.is_relative_to(ROOT) else log
        log.write_text('', encoding='utf-8')
        env = dict(env or (no_cache_env(logs) if no_cache else os.environ))
        t0 = time.time()
        parts = None if no_cache or key is None or shadowed() else split_built(check)
        built = reads = None
        if parts:
            code = spawn(parts[0], log, timeout, fresh(env))
            if code is None:
                return 'failed', f'{timeout}초 안에 끝나지 않음, 로그 {shown}'
            if code:
                return 'failed', f'종료 코드 {code}, 로그 {shown}'
            built = input_key(check, ROOT, built=True)
            old = built and built_hit(name, built, ROOT)
            if old:
                return 'passed', f'캐시: 빌드 결과와 검사 코드가 같아 {old["when"]} 통과, {old["detail"]}'
            reads = logs / f'{name}.reads'
            reads.unlink(missing_ok=True)
            Path(f'{reads}.broken').unlink(missing_ok=True)
        # 검사 출력 폴더는 검사 단계를 돌릴 때만 비운다(건너뛰면 지난 출력이 남는다)
        for d in out_dirs(run):
            # 빌드 단계가 만든 폴더면(앞 단계 --out) 지우지 않는다
            if not any(under(d, m) or under(m, d) for m in made_paths(run)):
                shutil.rmtree(ROOT / d, ignore_errors=True)
        if parts:
            base = env
            env = dict(base, GUARD_READS=str(reads), GUARD_READS_ROOT=str(ROOT),
                       GUARD_READS_SKIP=os.pathsep.join(str(ROOT / d) for d in out_dirs(run)
                                                        if not any(under(d, m) or under(m, d) for m in made_paths(run))),
                       PYTHONPATH=os.pathsep.join(x for x in (str(TRACER), base.get('PYTHONPATH')) if x))
        code = spawn(parts[1] if parts else run, log, timeout - (time.time() - t0), fresh(env))
        if code is None:
            return 'failed', f'{timeout}초 안에 끝나지 않음, 로그 {shown}'
        secs = round(time.time() - t0)
        if code:
            return 'failed', f'종료 코드 {code}, 로그 {shown}'
        m = re.search(r'--rom\s+(\S+)', run.split('&&')[-1])
        rom = m[1] if m else None
        detail = f'{secs}초' + (f', 롬 SHA-1 {hashlib.sha1((ROOT / rom).read_bytes()).hexdigest()[:8]}'
                               if rom and (ROOT / rom).is_file() else '')
        # 도는 동안 입력이 바뀌었으면 그 결과는 어느 입력의 것인지 모르므로 캐시하지 않는다
        if key is not None and input_key(check, ROOT) == key:
            write_atomic(hit, json.dumps({'when': time.strftime('%Y-%m-%d %H:%M'), 'detail': detail}, ensure_ascii=False))
            trace = (read_trace(reads, CHECK_STAGE.match(parts[1])['script'])
                     if reads and not Path(f'{reads}.broken').exists() else None)
            entry = trace and trace_entry(trace, ROOT)
            # 검사 단계가 빌드 결과를 고쳐 썼으면 키가 달라져 남기지 않는다
            if built and entry and input_key(check, ROOT, built=True) == built:
                save_built(name, built, detail, entry)
        return 'passed', detail
    finally:
        for d in pycaches:
            shutil.rmtree(d, ignore_errors=True)


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


def triggered(checks, changed, edited=(), full=False):
    """바뀐 파일이 paths 에 맞거나 이름이 edited 에 든 검사. full 이 아니면(PR) 묶음은 빼고 검사 자신의 paths 만 보고,
    tier = "release" 인 검사도 뺀다. full 이면 묶음까지 보고 등급을 가리지 않는다."""
    def hits(c):
        pats = c.get('paths', []) if full else c.get('own_paths', c.get('paths', []))
        return c['name'] in edited or any(matches(f, p) for f in changed for p in pats)
    return [c for c in checks if (full or c.get('tier', 'pr') != 'release') and hits(c)]


# PR 본문에서 묶음·release 등급까지 모두 돌렸다고 밝히는 줄
FULL_LINE = re.compile(r'^[ \t]*가드[ \t]*:[ \t]*전체[ \t]*$', re.M)


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
    ap.add_argument('--full', action='store_true',
                    help='묶음으로 맞는 검사와 release 등급까지 고른다(PR 본문의 `가드: 전체` 와 같음)')
    args = ap.parse_args()
    files = tracked()
    checks, problems = load(files)
    if args.base:
        changed = [f for f in git('diff', '--name-only', f'{args.base}...{args.head}').splitlines() if f]
        edited = edited_in(args.base, args.head, changed)
        body = args.pr_body.read_text(encoding='utf-8') if args.pr_body else ''
        full = args.full or bool(FULL_LINE.search(body))
        hit = triggered(checks, changed, edited, full)
        if full:
            print('전체 모드: 묶음으로 맞는 검사와 release 등급까지 고름')
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
        later = [c for c in triggered(checks, changed, edited, full=True) if c not in hit]
        if later:
            print('배포 관문에서(이 PR 에서는 돌리지 않음. 큰 변경이면 본문에 `가드: 전체` 를 쓰고 --full 로 돌릴 것):')
            for c in later:
                why = 'release 등급' if c.get('tier', 'pr') == 'release' else '묶음으로만 맞음'
                print(f'- {c["name"]} ({why})')
        if args.pr_body:
            problems += body_problems(hit, body)
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
