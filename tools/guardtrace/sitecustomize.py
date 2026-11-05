"""guards.py 의 빌드 결과 캐시가 검사 단계를 돌릴 때 PYTHONPATH 앞에 이 폴더를 둔다. 그 단계와 자식 Python 이
GUARD_READS_ROOT 아래에서 쓴 것을 GUARD_READS 에 탭으로 가른 줄로 적는다.

  C <경로> <qualname> <지문>   실행한 코드 객체(guardprint.fingerprint). 실행하지 않은 함수는 적지 않는다
  F <경로> <SHA-1>              import 밖에서 읽으려고 연 파일(연 때의 내용. 못 읽으면 -)
  D <경로> <SHA-1>              목록을 본 폴더(이름 정렬)
  (GUARD_READS_SKIP 의 폴더, 검사가 돌기 전에 비우는 출력 폴더 아래는 적지 않는다)
  ?                             무엇을 읽었는지 모르는 일이 있었다. guards.py 는 이 기록을 캐시하지 않는다

`?` 는 이 파일을 싣지 못하게 뜨는 자식(python -I·-E·-S, env, PYTHONPATH·GUARD_READS 를 바꾸거나 뺀 환경),
Python 이 아니면서 .py 를 인자로 받는 자식(grep 등), __pycache__ 밖 .pyc, 감시 도구 번호를 얻지 못함에 적는다.
"""
import hashlib
import os
import re
import sys

_OUT = os.environ.get('GUARD_READS')
_ROOT = os.environ.get('GUARD_READS_ROOT')
# 검사가 돌기 전에 비우는 출력 폴더. 그 아래는 검사 자신이 만든 것이라 적지 않는다
_SKIP = [os.path.realpath(p) for p in os.environ.get('GUARD_READS_SKIP', '').split(os.pathsep) if p]
_HERE = os.path.dirname(os.path.realpath(__file__))
_BLIND = re.compile(r'(^|[\s/])python[0-9.]*(\s+-[A-Za-z]+)*\s+-[A-Za-z]*[IES][A-Za-z]*(\s|$)'
                    r'|(^|[\s/])env\s|PYTHONPATH|GUARD_READS|PYTHONPYCACHEPREFIX|PYTHONNOUSERSITE')
_PYTHON = re.compile(r'(^|/)(python[0-9.]*|uv)$')
_IMPORT = '<frozen importlib._bootstrap_external>'
_WRITE = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _emit(*fields):
    fd = os.open(_OUT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, ('\t'.join(fields) + '\n').encode('utf-8', 'surrogateescape'))
    finally:
        os.close(fd)


def _text(value):
    if isinstance(value, (list, tuple)):
        return ' '.join(_text(v) for v in value)
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


def _blind_env(env):
    env = os.environ if env is None else env
    try:
        reads = env.get('GUARD_READS') or env.get(b'GUARD_READS')
        paths = env.get('PYTHONPATH') or env.get(b'PYTHONPATH') or ''
    except AttributeError:
        return True
    reads = reads.decode() if isinstance(reads, bytes) else reads
    paths = paths.decode() if isinstance(paths, bytes) else paths
    return reads != _OUT or _HERE not in paths.split(os.pathsep)


def _inside(path):
    try:
        path = os.fsdecode(path)
    except (TypeError, ValueError):
        return None
    # <frozen …>·<string> 같은 이름은 파일이 아니다
    if path.startswith('<'):
        return None
    path = os.path.realpath(path)
    if not path.startswith(_ROOT + os.sep) or any(path == d or path.startswith(d + os.sep) for d in [_HERE, *_SKIP]):
        return None
    return path


def _sha1(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.file_digest(f, 'sha1').hexdigest()
    except OSError:
        return '-'


def _opened(args):
    path, mode, flags = args
    if isinstance(path, int):
        return
    if isinstance(mode, str):
        if any(c in mode for c in 'wax+'):
            return
    elif flags & _WRITE:
        return
    full = _inside(path)
    if full is None or full in _seen:
        return
    # 0 은 _opened, 1 은 _hook, 2 가 open 을 부른 곳
    if sys._getframe(2).f_code.co_filename == _IMPORT:
        if full.endswith('.pyc') and os.path.basename(os.path.dirname(full)) != '__pycache__':
            _emit('?')
        return
    _seen.add(full)
    _emit('F', os.path.relpath(full, _ROOT), _sha1(full))


def _listed(path):
    full = _inside('.' if path is None else path)
    if full is None or full in _seen or not os.path.isdir(full):
        return
    _seen.add(full)
    names = '\0'.join(sorted(os.listdir(full)))
    _emit('D', os.path.relpath(full, _ROOT), hashlib.sha1(names.encode('utf-8', 'surrogateescape')).hexdigest())


def _spawned(command, env):
    text = _text(command)
    words = text.split()
    program = os.path.basename(words[0]) if words else ''
    if _BLIND.search(text) or _blind_env(env) or (not _PYTHON.search(program) and '.py' in text):
        _emit('?')


def _hook(event, args):
    if _busy:
        return
    _busy.append(1)
    try:
        if event == 'open':
            _opened(args)
        elif event in ('os.listdir', 'os.scandir'):
            _listed(args[0])
        elif event == 'subprocess.Popen':
            _spawned(args[1], args[3])
        elif event == 'os.system':
            _spawned(args[0], None)
        elif event in ('os.exec', 'os.posix_spawn', 'os.spawn'):
            _spawned(args[-2], args[-1])
    finally:
        _busy.pop()


def _started(code, offset):
    full = _inside(code.co_filename)
    if full is not None:
        _emit('C', os.path.relpath(full, _ROOT), code.co_qualname, fingerprint(code))
    return sys.monitoring.DISABLE


if _OUT and _ROOT:
    from guardprint import fingerprint
    _ROOT = os.path.realpath(_ROOT)
    _seen = set()
    _busy = []
    sys.addaudithook(_hook)
    for _tool in (3, 4, 2):
        try:
            sys.monitoring.use_tool_id(_tool, 'guardtrace')
        except ValueError:
            continue
        sys.monitoring.register_callback(_tool, sys.monitoring.events.PY_START, _started)
        sys.monitoring.set_events(_tool, sys.monitoring.events.PY_START)
        break
    else:
        _emit('?')
