"""빌드 단계 캐시 키(dq4buildcache)가 그 단계가 실제로 읽는 것을 모두 담는지 맞춰 본다.

출하 롬 빌드(dq4build.build, 곡 묶음 앞까지)의 dq4buildcache.run 호출마다 도구를 캐시 없이 돌리며, 파이썬 감사 훅
(sitecustomize, 하위 파이썬 프로세스에도 PYTHONPATH 로 들어감)으로 연 파일·읽은 환경 변수·쓴 파일·띄운 다른 프로그램을
적는다. 단계 안에서 다시 dq4buildcache.run 으로 부르는 호출(1장 빌드의 그룹 빌드 등)도 저마다 따로 적는다. 호출마다 그
기록(하위 호출 것 포함)을 dq4buildcache.key_inputs 와 견줘 키에 없는 입력을 찾는다.

키에 없어도 되는 것:
- 파이썬 표준 라이브러리와 설치된 패키지(키에 파이썬 판·uv.lock 이 듦). 툴킷(kr_patch)은 .py 만 키에 들어 그 밖의 파일은 안 됨
- 같은 호출이 먼저 쓴 파일(임시 폴더·중간 결과)과 그 호출의 출력 자리, 폴더 열기(목록은 내용이 아님)
- /dev·/proc·/sys 아래(장치·커널)
- IGNORED_ENV 의 환경 변수(결과를 바꾸지 않는 까닭을 적음)

쓴 파일은 출력 자리(OUT_FLAGS 뒤 경로와 곁 파일)나 임시 폴더 안이어야 한다. 밖에 쓰면 캐시에서 되살아나지 않는다.
파이썬이 아닌 프로그램(asar 등)은 훅이 닿지 않으므로 EXTERNAL 에 적은 것만 받고, 그 인자로 넘긴 경로는 호출이 먼저
쓴 것이거나 키 입력이어야 한다.

  uv run --locked python sfc/dq4/tools/dq4buildkeys.py [--chapter2]   # 롬·ASAR·DQ4_GALMURI 필요, 빠진 입력이 있으면 1
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4buildcache  # noqa: E402

TRACE_ENV = 'DQ4_KEYTRACE'
SYSTEM = ('/dev/', '/proc/', '/sys/')
CALL = 'call.json'
# 호출이 읽지만 결과 바이트를 바꾸지 않는 환경 변수
IGNORED_ENV = {
    'DQ4_BUILD_CACHE': '캐시 자리·끄기만 정함',
    'DQ4_NATIVE': 'Go 도구 자리. 파이썬 경로와 같은 바이트(관문의 무캐시 빌드가 파이썬으로 돌아 견줌)',
    TRACE_ENV: '이 추적기',
    'PYTHONPATH': '이 추적기',
    'TMPDIR': '임시 폴더 자리', 'TEMP': '임시 폴더 자리', 'TMP': '임시 폴더 자리',
    'HOME': '사용자 폴더(파이썬 시작)',
    'PATH': '프로그램 찾기. 띄운 프로그램은 EXTERNAL 로 따로 봄',
    'LANG': 'argparse 메시지 번역(gettext)', 'LANGUAGE': 'argparse 메시지 번역', 'LC_ALL': 'argparse 메시지 번역',
    'LC_MESSAGES': 'argparse 메시지 번역',
    'COLUMNS': 'argparse 도움말 폭', 'LINES': 'argparse 도움말 폭',
    'NO_COLOR': '출력 색', 'FORCE_COLOR': '출력 색', 'TERM': '출력 색', 'PYTHON_COLORS': '출력 색',
    'PILLOW_ALIGNMENT': 'Pillow 메모리 할당', 'PILLOW_BLOCK_SIZE': 'Pillow 메모리 할당',
    'PILLOW_BLOCKS_MAX': 'Pillow 메모리 할당',
    'NPY_PROMOTION_STATE': 'numpy 시작 설정(판은 uv.lock)', 'NUMPY_MADVISE_HUGEPAGE': 'numpy 메모리 할당',
    'OPENBLAS_MAIN_FREE': 'OpenBLAS 스레드 메모리',
    '_PYTHON_SUBPROCESS_USE_POSIX_SPAWN': 'subprocess 띄우는 방식',
}
# 훅이 닿지 않는 프로그램: 실행 파일 이름 → 키에 드는 까닭
EXTERNAL = {
    'asar': 'ASAR 가 ENV_INPUTS 라 바이너리 내용이 키에 듦',
}


SITECUSTOMIZE = r'''
import os, sys, json
_dir = os.environ.get(%(env)r)
if _dir:
    import threading
    _state = {'pid': None, 'f': None}
    _busy = threading.local()

    def _emit(kind, value):
        if getattr(_busy, 'on', False):
            return
        _busy.on = True
        try:
            if _state['pid'] != os.getpid():
                _state['pid'] = os.getpid()
                _state['f'] = open(os.path.join(_dir, 'trace-%%d.jsonl' %% os.getpid()), 'a', buffering=1,
                                   encoding='utf-8')
            _state['f'].write(json.dumps([kind, value]) + '\n')
        finally:
            _busy.on = False

    def _path(p):
        try:
            return os.path.abspath(os.fsdecode(p))
        except (TypeError, ValueError):
            return None

    def _hook(event, args):
        if getattr(_busy, 'on', False):
            return
        if event == 'open':
            path, mode, flags = args
            if path is None or isinstance(path, int):
                return
            p = _path(path)
            if p is None:
                return
            write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            _emit('w' if write else 'r', p)
        elif event in ('os.rename', 'os.replace'):
            p = _path(args[1])
            if p:
                _emit('w', p)
        elif event == 'os.mkdir':
            p = _path(args[0])
            if p:
                _emit('w', p)
        elif event == 'subprocess.Popen':
            exe, argv = args[0], args[1]
            argv = argv if isinstance(argv, (list, tuple)) else [argv if argv is not None else exe]
            _emit('x', [os.fsdecode(a) if isinstance(a, (str, bytes, os.PathLike)) else str(a) for a in argv])

    sys.addaudithook(_hook)

    class _Env(type(os.environ)):
        def __getitem__(self, key):
            _emit('e', key)
            return super().__getitem__(key)

    os.environ.__class__ = _Env

    import importlib.abc, importlib.machinery

    def _wrap(module):
        original = module.run
        count = [0]
        lock = threading.Lock()

        def run(tool, *args, echo_stderr=False):
            import subprocess, tempfile
            if module.cache_dir() is not None:
                return original(tool, *args, echo_stderr=echo_stderr)
            with lock:
                count[0] += 1
                sub = os.path.join(_dir, 'call-%%d-%%d' %% (os.getpid(), count[0]))
            os.makedirs(sub)
            args = [str(a) for a in args]
            with open(os.path.join(sub, %(call)r), 'w', encoding='utf-8') as f:
                json.dump({'tool': os.path.abspath(str(tool)), 'args': args, 'cwd': os.getcwd()}, f)
            # 하위 호출에 넘기는 환경 복사는 읽기로 적지 않는다
            _busy.on = True
            try:
                env = dict(os.environ)
            finally:
                _busy.on = False
            env[%(env)r] = sub
            proc = subprocess.run([sys.executable, str(tool), *args], capture_output=True, text=True, env=env)
            if proc.returncode:
                raise RuntimeError('%%s %%s: %%s' %% (os.path.basename(str(tool)), ' '.join(args[:2]), proc.stderr[-1500:]))
            if echo_stderr:
                sys.stderr.write(proc.stderr)
            return proc.stdout
        module.run = run

    class _Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != 'dq4buildcache':
                return None
            spec = importlib.machinery.PathFinder.find_spec(name, path)
            if spec is None or spec.loader is None:
                return spec
            loader = spec.loader
            exec_module = loader.exec_module

            def exec_and_wrap(module):
                exec_module(module)
                _wrap(module)
            loader.exec_module = exec_and_wrap
            return spec

    sys.meta_path.insert(0, _Finder())
''' % {'env': TRACE_ENV, 'call': CALL}


def tracer(folder):
    """sitecustomize 를 둔 폴더(PYTHONPATH 에 넣음)."""
    site = Path(folder) / 'site'
    site.mkdir(parents=True, exist_ok=True)
    (site / 'sitecustomize.py').write_text(SITECUSTOMIZE, encoding='utf-8')
    return site


def read_trace(folder):
    """folder 아래(하위 호출 폴더 포함) 기록 모음 {'r','w','e','x'}."""
    got = {'r': set(), 'w': set(), 'e': set(), 'x': []}
    for f in sorted(Path(folder).rglob('trace-*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            try:
                kind, value = json.loads(line)
            except ValueError:
                continue
            if kind == 'x':
                got['x'].append(value)
            else:
                got[kind].add(value)
    return got


def traced_run(tool, args, log, site, env=None):
    """tool args 를 캐시 없이 추적하며 돌린다. 기록은 log 폴더에. 표준 출력을 돌려준다."""
    log.mkdir(parents=True)
    args = [str(a) for a in args]
    (log / CALL).write_text(json.dumps({'tool': str(Path(tool).resolve()), 'args': args, 'cwd': os.getcwd()}),
                            encoding='utf-8')
    run_env = dict(os.environ if env is None else env, DQ4_BUILD_CACHE='off', **{TRACE_ENV: str(log)})
    run_env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(site), run_env.get('PYTHONPATH', '')]))
    proc = subprocess.run([sys.executable, str(tool), *args], capture_output=True, text=True, env=run_env)
    if proc.returncode:
        raise RuntimeError(f'{Path(tool).name} {" ".join(args[:2])}: {proc.stderr[-1500:]}')
    return proc.stdout


def _real(p):
    return Path(os.path.realpath(p))


def _under(path, roots):
    return any(path == r or r in path.parents for r in roots)


def _python_dirs():
    dirs = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}
    dirs |= {v for v in sysconfig.get_paths().values() if v}
    return {_real(d) for d in dirs}


def _pyc_source(path):
    """__pycache__/이름.cpython-3xx.pyc 의 소스 경로."""
    if path.parent.name != '__pycache__' or path.suffix != '.pyc':
        return None
    return path.parent.parent / (path.name.split('.')[0] + '.py')


def check(tool, args, got, temp_roots=()):
    """키에 없는 입력·출력 밖에 쓴 파일·모르는 프로그램(문제 줄 목록). 상대 경로 인자는 지금 폴더 기준."""
    tool = Path(tool).resolve()
    args = [str(a) for a in args]
    inputs, toolkit, key_env = dq4buildcache.key_inputs(tool, args)
    _, outs = dq4buildcache._key(tool, args)
    inputs = {_real(p) for p in inputs}
    outs = [_real(o) for o in outs]
    sides = {_real(f) for o in outs if not o.is_dir() for f in dq4buildcache._siblings(o)}
    toolkit = _real(toolkit) if toolkit else None
    pydirs = _python_dirs()
    written = {_real(p) for p in got['w']}
    temps = {_real(tempfile.gettempdir()), *(_real(t) for t in temp_roots)}
    problems = []

    def covered(p):
        return p in inputs or any(d in p.parents for d in inputs)

    for raw in sorted(got['r']):
        p = _real(raw)
        # 폴더 열기(shutil 의 fd 기반 지우기 등, 이름이 dir_fd 기준이라 경로가 틀릴 수 있음)와 지워진 임시 파일
        if not p.is_file():
            continue
        if p in written or _under(p, outs) or p in sides or str(p).startswith(SYSTEM):
            continue
        src = _pyc_source(p)
        if src is not None:
            p = src
        if toolkit and _under(p, {toolkit}):
            if p.suffix != '.py':
                problems.append(f'키에 없는 툴킷 파일(.py 만 키에 듦): {p}')
            continue
        if _under(p, pydirs):
            continue
        if not covered(p):
            problems.append(f'키에 없는 입력 파일: {p}')
    for name in sorted(set(got['e']) - set(key_env) - set(IGNORED_ENV)):
        problems.append(f'키에 없는 환경 변수: {name}')
    for p in sorted(written):
        # 파이썬이 바이트코드를 __pycache__ 에 쓰는 것(임시 이름 .pyc.NNN 포함)은 결과가 아니다
        if _under(p, outs) or p in sides or _under(p, temps) or str(p).startswith(SYSTEM) or '__pycache__' in p.parts:
            continue
        problems.append(f'출력 자리 밖에 씀(캐시에서 되살아나지 않음): {p}')
    for argv in got['x']:
        exe = Path(argv[0]).name
        if _real(argv[0]) == _real(sys.executable) or exe.startswith('python'):
            continue
        if exe not in EXTERNAL:
            problems.append(f'추적하지 못하는 프로그램: {" ".join(argv[:3])}')
            continue
        for a in argv[1:]:
            if os.sep in a and Path(a).is_file():
                p = _real(a)
                if not (p in written or covered(p) or _under(p, outs) or _under(p, temps)):
                    problems.append(f'{exe} 에 넘긴 경로가 키에 없음: {p}')
    return [f'{tool.name} {" ".join(args[:1])}: {x}' for x in problems]


def check_calls(log_root, temp_roots=()):
    """log_root 아래 호출 폴더(call.json)마다 그 아래 기록 전부로 check. (호출 이름 목록, 문제 목록)."""
    names, problems = [], []
    here = os.getcwd()
    for call in sorted(Path(log_root).rglob(CALL)):
        meta = json.loads(call.read_text(encoding='utf-8'))
        got = read_trace(call.parent)
        names.append(f'{Path(meta["tool"]).name} {next(iter(meta["args"]), "")}'.strip())
        try:
            os.chdir(meta['cwd'])
            problems += check(meta['tool'], meta['args'], got, temp_roots)
        finally:
            os.chdir(here)
    return names, problems


def build_traced(out, dq5, dq4, chapter2, work):
    """dq4build.build 를 곡 묶음 앞까지 돌리며 dq4buildcache.run 호출을 추적하고 검사. (호출 이름 목록, 문제 목록)."""
    import dq4build
    site = tracer(work)
    logs = Path(work) / 'logs'
    count = [0]
    original = dq4buildcache.run

    def run(tool, *args, echo_stderr=False):
        count[0] += 1
        return traced_run(tool, args, logs / f'call-{count[0]}', site)

    dq4buildcache.run = run
    try:
        dq4build.build(Path(out), Path(dq5), Path(dq4), assets=None, chapter2=chapter2)
    finally:
        dq4buildcache.run = original
    return check_calls(logs, (work,))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dq5', default=str(ROOT / 'rom' / 'dq5.sfc'))
    ap.add_argument('--dq4', default=str(ROOT / 'rom' / 'dq4.nes'))
    ap.add_argument('--chapter2', action='store_true')
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix='dq4buildkeys-'))
    try:
        names, problems = build_traced(work / 'out', a.dq5, a.dq4, a.chapter2, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f'빌드 캐시 호출 {len(names)}개 추적: {", ".join(names)}')
    for p in problems:
        print(p)
    print('키에 빠진 입력 없음' if not problems else f'문제 {len(problems)}개')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
