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
GUARD_READS 를 바꾸거나 뺀 환경), Python 밖이면서 .py 를 인자로 받는 자식(grep 등), 셸처럼 가를 수 없는 인자, __pycache__ 밖 .pyc, 감시 도구 번호를
얻지 못함에 적는다.
"""
import hashlib
import os
import re
import shlex
import stat as _stat
import sys
import threading

_OUT = os.environ.get('GUARD_READS')
_ROOT = os.environ.get('GUARD_READS_ROOT')
_SKIP = [os.path.realpath(p) for p in os.environ.get('GUARD_READS_SKIP', '').split(os.pathsep) if p]
_HERE = os.path.dirname(os.path.realpath(__file__))
_VENV = os.path.join(os.path.realpath(_ROOT), '.venv') if _ROOT else ''
_BLIND = re.compile(r'(^|[\s/])python[0-9.]*(\s+-[A-Za-z]+)*\s+-[A-Za-z]*[IES][A-Za-z]*(\s|$)'
                    r'|(^|[\s/])env\s|PYTHONPATH|GUARD_READS|PYTHONPYCACHEPREFIX|PYTHONNOUSERSITE')
_PYTHON = re.compile(r'(^|/)(python[0-9.]*|uv)$')
_IMPORT = '<frozen importlib._bootstrap_external>'
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


def _fail():
    """기록을 버리게 한다. 적지도 못하면 기록이 빠진 채 남지 않게 표지 파일을 둔다."""
    try:
        _emit('?')
    except Exception:
        try:
            _real_open(_OUT + '.broken', os.O_WRONLY | os.O_CREAT, 0o644)
        except Exception:
            pass


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
        prefix = env.get('PYTHONPYCACHEPREFIX') or env.get(b'PYTHONPYCACHEPREFIX')
    except AttributeError:
        return True
    reads, paths, prefix = (v.decode() if isinstance(v, bytes) else v for v in (reads, paths, prefix))
    # 빈 pycache 를 잃은 자식은 옛 .pyc 를 쓸 수 있다
    return reads != _OUT or _HERE not in paths.split(os.pathsep) or prefix != os.environ.get('PYTHONPYCACHEPREFIX')


def _inside(path):
    try:
        path = os.fsdecode(path)
    except (TypeError, ValueError):
        return None
    # <frozen …>·<string> 같은 이름은 파일이 아니다
    if not path or path.startswith('<'):
        return None
    path = os.path.realpath(path)
    # .venv 는 uv.lock(키에 듦)이 정한다
    if not path.startswith(_ROOT + os.sep) or any(path == d or path.startswith(d + os.sep) for d in [_HERE, _VENV, *_SKIP] if d):
        return None
    return path


def _rel(full):
    return os.path.relpath(full, _ROOT)


def _opened(args):
    path, mode, flags = args
    if isinstance(path, int):
        return
    # 쓰기만 하는 것은 빼고, 읽기·쓰기를 함께 하는 것(r+·w+·O_RDWR)은 읽기로 본다
    if isinstance(mode, str):
        if any(c in mode for c in 'wax') and '+' not in mode:
            return
    elif flags & os.O_ACCMODE == os.O_WRONLY:
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
        prefix = sys.pycache_prefix
        if full.endswith('.pyc') and os.path.basename(os.path.dirname(full)) != '__pycache__' and not (
                prefix and full.startswith(os.path.realpath(prefix) + os.sep)):
            _emit('?')
        return
    _emit('F', _rel(full), content_sig(full))


def _listed(path):
    full = _inside('.' if path is None else path)
    if full is None or not os.path.isdir(full):
        return
    names = '\0'.join(sorted(os.listdir(full)))
    _emit('D', _rel(full), hashlib.sha1(names.encode('utf-8', 'surrogateescape')).hexdigest())


def _words(command):
    """인자와, 셸 문자열(sh -c '…')이면 셸처럼 나눈 낱말까지. 따옴표가 겹치면 몇 겹 더 푼다.
    다 풀지 못하면 ValueError."""
    todo = [_text(w) for w in command] if isinstance(command, (list, tuple)) else [_text(command)]
    words = []
    for _ in range(4):
        words += todo
        todo = [part for w in todo if any(c in w for c in ' \t\n"\'\\') for part in shlex.split(w)]
        if not todo:
            return words
    raise ValueError(command)


def _spawned(command, env):
    text = _text(command)
    try:
        words = _words(command)
    except ValueError:
        # 무엇을 넘겼는지 가를 수 없다
        _emit('?')
        return
    program = os.path.basename(words[0].split()[0]) if words and words[0].split() else ''
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
            elif full and os.path.isdir(full):
                # 폴더를 받은 자식은 그 안 무엇을 읽을지 모른다
                _emit('?')


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
        elif event == 'import' and isinstance(args[1], str) and not args[1].endswith(('.py', '.pyc')):
            # 확장 모듈(.so)은 open 감사 없이 실리고 실행한 코드를 볼 수 없어 내용째 입력으로 본다
            full = _inside(args[1])
            if full is not None:
                _emit('F', _rel(full), content_sig(full))
        elif event in ('sqlite3.connect', 'ctypes.dlopen'):
            # C 쪽에서 파일을 읽어 open 감사에 걸리지 않는다
            _emit('?')
    except Exception:
        # 훅이 예외를 내면 그 open 이 실패한다. 무엇을 놓쳤는지 모르므로 기록을 버리게 한다
        _fail()
    finally:
        _local.busy = False


def _stat_seen(path, result):
    if getattr(_local, 'busy', False) or isinstance(path, int):
        return
    _local.busy = True
    try:
        full = _inside(path)
        if full is not None:
            # 경로를 realpath 로 적으므로 링크를 lstat 한 결과 대신 가리키는 것의 상태를 적는다(stat 과 같은 값)
            if result is not None and _stat.S_ISLNK(result.st_mode):
                try:
                    result = _real_stat(path)
                except OSError:
                    result = None
            state = '-' if result is None else 'dir' if _stat.S_ISDIR(result.st_mode) else str(result.st_size)
            _emit('E', _rel(full), state)
    except Exception:
        _fail()
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
    except Exception:
        _fail()
    finally:
        _local.busy = busy
    return sys.monitoring.DISABLE


if _OUT and _ROOT:
    from guardprint import fingerprint
    _ROOT = os.path.realpath(_ROOT)
    _real_open = os.open
    _lock = threading.Lock()

    def _new_lock():
        global _lock
        _lock = threading.Lock()
    # fork 때 다른 스레드가 잡고 있던 잠금을 자식이 물려받으면 첫 기록에서 멈춘다
    os.register_at_fork(after_in_child=_new_lock)
    _local = threading.local()
    _seen = set()
    _local.busy = True
    script = _inside(sys.argv[0]) if sys.argv and sys.argv[0] else None
    _emit('S', _rel(script) if script else '-')
    _local.busy = False
    sys.addaudithook(_hook)
    _real_stat = os.stat
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
