"""guards.py 의 빌드 결과 캐시가 검사 단계를 돌릴 때 PYTHONPATH 앞에 이 폴더를 둔다. 그 단계와 자식 Python 이
GUARD_READS_ROOT 아래에서 쓴 것을 GUARD_READS 에 탭으로 가른 줄로 적는다.

  S <경로>                     이 파일을 실은 프로세스의 스크립트(sys.argv[0], 저장소 밖이면 -)
  C <경로> <qualname> <지문>   실행한 코드 객체(guardprint.fingerprint). 실행하지 않은 함수는 적지 않는다
  F <경로> <내용>               import 밖에서 읽으려고 연 파일, Python 밖 자식의 인자로 넘긴 파일(content_sig)
  D <경로> <SHA-1>              목록을 본 폴더(이름 정렬)
  E <경로> <상태>               os.stat 으로 본 것(크기, dir, 없으면 -). os.path.exists·isfile·getsize·Path.exists 가 쓴다
  ?                             무엇을 읽었는지 모르는 일이 있었다. guards.py 는 이 기록을 캐시하지 않는다

같은 경로가 다른 값으로 두 번 나오면(도는 중에 바뀜) guards.py 가 기록을 버린다. GUARD_READS_SKIP 의 폴더(검사가 돌기
전에 비우는 출력 폴더) 아래는 적지 않는다. `?` 는 이 파일을 싣지 못하게 뜨는 자식(python -I·-E·-S, env, PYTHONPATH·
GUARD_READS 를 바꾸거나 뺀 환경), Python 밖이면서 .py 를 인자로 받는 자식(grep 등), __pycache__ 밖 .pyc, 감시 도구 번호를
얻지 못함에 적는다.
"""
import hashlib
import os
import re
import sys
import threading

_OUT = os.environ.get('GUARD_READS')
_ROOT = os.environ.get('GUARD_READS_ROOT')
_SKIP = [os.path.realpath(p) for p in os.environ.get('GUARD_READS_SKIP', '').split(os.pathsep) if p]
_HERE = os.path.dirname(os.path.realpath(__file__))
_BLIND = re.compile(r'(^|[\s/])python[0-9.]*(\s+-[A-Za-z]+)*\s+-[A-Za-z]*[IES][A-Za-z]*(\s|$)'
                    r'|(^|[\s/])env\s|PYTHONPATH|GUARD_READS|PYTHONPYCACHEPREFIX|PYTHONNOUSERSITE')
_PYTHON = re.compile(r'(^|/)(python[0-9.]*|uv)$')
_IMPORT = '<frozen importlib._bootstrap_external>'
_WRITE = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
# guards.BIG_FILE 와 같아야 한다. 이보다 큰 파일은 내용 대신 크기·mtime_ns
BIG_FILE = 64 << 20


def content_sig(path):
    """파일 내용 표지: SHA-1, BIG_FILE 보다 크면 big:크기:mtime_ns, 못 읽으면 -."""
    try:
        st = os.stat(path)
        if st.st_size > BIG_FILE:
            return f'big:{st.st_size}:{st.st_mtime_ns}'
        key = (path, st.st_size, st.st_mtime_ns, st.st_ino)
        if key not in _sigs:
            with open(path, 'rb') as f:
                _sigs[key] = hashlib.file_digest(f, 'sha1').hexdigest()
        return _sigs[key]
    except OSError:
        return '-'


_sigs = {}


def _emit(*fields):
    line = ('\t'.join(fields) + '\n').encode('utf-8', 'surrogateescape')
    with _lock:
        if line in _seen:
            return
        _seen.add(line)
        fd = _real_open(_OUT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
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
    if not path or path.startswith('<'):
        return None
    path = os.path.realpath(path)
    if not path.startswith(_ROOT + os.sep) or any(path == d or path.startswith(d + os.sep) for d in [_HERE, *_SKIP]):
        return None
    return path


def _rel(full):
    return os.path.relpath(full, _ROOT)


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
    if full is None:
        return
    # 0 은 _opened, 1 은 _hook, 2 가 open 을 부른 곳. 인터프리터가 스크립트를 열 때는 Python 프레임이 없다
    try:
        caller = sys._getframe(2).f_code.co_filename
    except ValueError:
        caller = None
    if caller == _IMPORT:
        if full.endswith('.pyc') and os.path.basename(os.path.dirname(full)) != '__pycache__':
            _emit('?')
        return
    _emit('F', _rel(full), content_sig(full))


def _listed(path):
    full = _inside('.' if path is None else path)
    if full is None or not os.path.isdir(full):
        return
    names = '\0'.join(sorted(os.listdir(full)))
    _emit('D', _rel(full), hashlib.sha1(names.encode('utf-8', 'surrogateescape')).hexdigest())


def _spawned(command, env):
    text = _text(command)
    words = text.split()
    program = os.path.basename(words[0]) if words else ''
    if _BLIND.search(text) or _blind_env(env):
        _emit('?')
        return
    if _PYTHON.search(program):
        return
    if '.py' in text:
        _emit('?')
        return
    # Python 밖 자식(에뮬레이터 등)이 인자로 받은 파일은 그 내용을 입력으로 본다
    for word in words[1:]:
        for part in word.split('='):
            full = _inside(part) if part else None
            if full and os.path.isfile(full):
                _emit('F', _rel(full), content_sig(full))


def _hook(event, args):
    if getattr(_local, 'busy', False):
        return
    _local.busy = True
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
    except Exception:
        # 훅이 예외를 내면 그 open 이 실패한다. 무엇을 놓쳤는지 모르므로 기록을 버리게 한다
        _emit('?')
    finally:
        _local.busy = False


def _stat_seen(path, result):
    if getattr(_local, 'busy', False) or isinstance(path, int):
        return
    _local.busy = True
    try:
        full = _inside(path)
        if full is not None:
            import stat as st
            state = '-' if result is None else 'dir' if st.S_ISDIR(result.st_mode) else str(result.st_size)
            _emit('E', _rel(full), state)
    finally:
        _local.busy = False


def _wrap_stat(real):
    def stat(path, *args, **kwargs):
        try:
            result = real(path, *args, **kwargs)
        except OSError:
            if not args and not kwargs.get('dir_fd'):
                _stat_seen(path, None)
            raise
        if not args and not kwargs.get('dir_fd'):
            _stat_seen(path, result)
        return result
    stat.__wrapped__ = real
    return stat


def _started(code, offset):
    # 추적기 자신의 realpath·stat 이 E 줄로 적히지 않게
    busy = getattr(_local, 'busy', False)
    _local.busy = True
    try:
        full = _inside(code.co_filename)
        if full is not None:
            _emit('C', _rel(full), code.co_qualname, fingerprint(code))
    finally:
        _local.busy = busy
    return sys.monitoring.DISABLE


if _OUT and _ROOT:
    from guardprint import fingerprint
    _ROOT = os.path.realpath(_ROOT)
    _real_open = os.open
    _lock = threading.Lock()
    _local = threading.local()
    _seen = set()
    _local.busy = True
    script = _inside(sys.argv[0]) if sys.argv and sys.argv[0] else None
    _emit('S', _rel(script) if script else '-')
    _local.busy = False
    sys.addaudithook(_hook)
    os.stat = _wrap_stat(os.stat)
    os.lstat = _wrap_stat(os.lstat)
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
