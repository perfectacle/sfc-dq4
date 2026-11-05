"""guards.py 의 빌드 결과 캐시가 검사 단계를 돌릴 때 PYTHONPATH 앞에 이 폴더를 둔다. 그 단계와 자식 Python 이
GUARD_READS_ROOT 아래에서 쓴 것을 GUARD_READS 에 탭으로 가른 줄로 적는다.

  S <경로>                     이 파일을 실은 프로세스의 스크립트(sys.argv[0], 저장소 밖이면 -)
  C <경로> <qualname> <지문>   실행한 코드 객체(guardprint.fingerprint). 실행하지 않은 함수는 적지 않는다
  F <경로> <내용>               import 밖에서 읽으려고 연 파일, MesenCE 에 인자·환경 변수로 넘긴 파일(content_sig)
  D <경로> <SHA-1>              목록을 본 폴더(이름 정렬)
  E <경로> <상태>               os.stat·os.access 로 본 것(크기, dir, 없으면 -). os.path.exists·isfile·getsize·Path.exists 가 쓴다
  L <경로> <가리키는 곳>        위 경로들을 풀다 거쳐 간 심볼릭 링크(os.readlink). 링크를 바꿔 달면 다른 파일을 읽게 된다
  ?                             무엇을 읽었는지 모르는 일이 있었다. guards.py 는 이 기록을 캐시하지 않는다

같은 경로가 다른 값으로 두 번 나오면(도는 중에 바뀜) guards.py 가 기록을 버린다. GUARD_READS_SKIP 의 폴더(검사가 돌기
전에 비우는 출력 폴더) 아래는 적지 않는다. 경로는 커널처럼 한 단계씩 풀어(`..` 포함) 실제 파일로 적는다. 자식은
아는 것만 받는다: 옵션이 -u·-B 뿐인 Python(자식 안에서 추적된다)과 $MESENCE(인자·환경 변수로 받은 저장소 안 파일을
F 로). `?` 는 그 밖 자식(셸·os.system·git·asar 등), PYTHONPATH·GUARD_READS·PYTHONPYCACHEPREFIX 를 바꾸거나 뺀 환경,
자식에게 넘긴 폴더, __pycache__ 밖 .pyc, 너무 깊은 링크, 감시 도구 번호를 얻지 못함에 적는다.
"""
import hashlib
import os
import re
import stat as _stat
import sys
import threading

_OUT = os.environ.get('GUARD_READS')
_ROOT = os.environ.get('GUARD_READS_ROOT')
_SKIP = [os.path.realpath(p) for p in os.environ.get('GUARD_READS_SKIP', '').split(os.pathsep) if p]
_HERE = os.path.dirname(os.path.realpath(__file__))
_VENV = os.path.join(os.path.realpath(_ROOT), '.venv') if _ROOT else ''
_PYTHON = re.compile(r'python[0-9.]*')
# 이 옵션만 단 Python 자식은 추적기를 그대로 싣는다
_PY_OK = {'-u', '-B'}
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


def _excluded(path):
    return not path.startswith(_ROOT + os.sep) or any(
        path == d or path.startswith(d + os.sep) for d in [_HERE, _VENV, *_SKIP] if d)


def _resolve(path):
    """커널처럼 앞에서부터 한 단계씩 풀어 실제 경로를 낸다(`..` 는 그때까지 푼 실제 폴더의 부모).
    거쳐 간 저장소 안 링크마다 L 줄을 적는다. 링크가 너무 깊으면 None."""
    todo = [c for c in path.split(os.sep) if c][::-1]
    cur = os.sep
    hops = 0
    while todo:
        c = todo.pop()
        if c == '.':
            continue
        if c == '..':
            cur = os.path.dirname(cur)
            continue
        step = os.path.join(cur, c)
        try:
            target = os.readlink(step)
        except OSError:
            cur = step
            continue
        hops += 1
        if hops > 40:
            return None
        if not _excluded(step):
            _emit('L', _rel(step), target)
        if target.startswith(os.sep):
            cur = os.sep
        todo += [t for t in target.split(os.sep) if t][::-1]
    return cur


def _inside(path, cwd=None):
    try:
        path = os.fsdecode(path)
        cwd = os.fsdecode(cwd) if cwd is not None else None
    except (TypeError, ValueError):
        return None
    # <frozen …>·<string> 같은 이름은 파일이 아니다
    if not path or path.startswith('<'):
        return None
    if not path.startswith(os.sep):
        # 상대 cwd 는 지금 폴더 기준이다
        path = os.path.join(os.getcwd(), cwd or '', path)
    full = _resolve(path)
    if full is None:
        _emit('?')
        return None
    # .venv 는 uv.lock(키에 듦)이 정한다
    if _excluded(full):
        return None
    return full


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


def _python_ok(words):
    """Python 자식이 추적기를 싣는 꼴(옵션이 _PY_OK 뿐)인가."""
    for w in words[1:]:
        if w in ('-c', '-m') or not w.startswith('-'):
            return True
        if w not in _PY_OK:
            return False
    return True


def _mesence():
    path = os.environ.get('MESENCE')
    return os.path.realpath(path) if path else None


def _spawned(program, command, env, cwd=None):
    """자식은 아는 것만 받는다. Python 은 자식 안에서 추적되고, MesenCE 는 인자·환경 변수로 받은 파일을 입력으로
    본다. 그 밖(셸·os.system·git·asar 등)은 무엇을 읽을지 모르므로 `?`."""
    if not isinstance(command, (list, tuple)) or not command or _blind_env(env):
        _emit('?')
        return
    words = [_text(w) for w in command]
    names = {os.path.basename(words[0])}
    if program is not None:
        names.add(os.path.basename(_text(program)))
    if all(_PYTHON.fullmatch(n) for n in names):
        if not _python_ok(words):
            _emit('?')
        return
    real = os.path.realpath(_text(program) if program is not None else words[0])
    if real != _mesence():
        _emit('?')
        return
    env = os.environ if env is None else env
    values = []
    for v in env.values():
        values += _text(v).split(os.pathsep)
    # 인자·환경 변수로 받은 저장소 안 파일은 그 내용을 입력으로 본다
    for word in words[1:] + values:
        for part in word.split('='):
            full = _inside(part, cwd) if part else None
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
            _spawned(args[0], args[1], args[3], args[2])
        elif event in ('os.system', 'os.fork', 'os.forkpty'):
            # 셸 문자열은 풀지 않는다. fork 뒤 exec 는 os.exec 로 따로 잡힌다
            if event == 'os.system':
                _emit('?')
        elif event in ('os.exec', 'os.posix_spawn'):
            _spawned(args[0], args[1], args[2])
        elif event == 'os.spawn':
            _spawned(args[1], args[2], args[3])
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


def _wrap_access(real):
    # os.access 는 감사 이벤트가 없다. 있음·크기를 stat 과 같은 E 줄로 적는다
    def access(path, mode, *args, **kwargs):
        if not args and not kwargs.get('dir_fd'):
            try:
                _stat_seen(path, _real_stat(path))
            except OSError:
                _stat_seen(path, None)
        return real(path, mode, *args, **kwargs)
    access.__wrapped__ = real
    return access


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
    os.access = _wrap_access(os.access)
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
