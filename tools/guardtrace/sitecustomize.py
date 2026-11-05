"""guards.py 의 빌드 결과 캐시가 검사 단계를 돌릴 때 PYTHONPATH 앞에 이 폴더를 둔다. 그 단계와 자식 Python 이
GUARD_READS_ROOT 아래에서 연 .py(.pyc 는 그 원본)를 GUARD_READS 에 한 줄씩 적는다.

자식이 이 파일을 싣지 못하게 뜨면(python -I·-E·-S, env -i, PYTHONPATH·GUARD_READS 를 뺀 환경) 그 자식이 무엇을
읽었는지 모르므로 `?` 줄을 적는다. guards.py 는 `?` 가 있으면 결과를 캐시하지 않는다.
"""
import importlib.util
import os
import re
import sys

_OUT = os.environ.get('GUARD_READS')
_ROOT = os.environ.get('GUARD_READS_ROOT')
_HERE = os.path.dirname(os.path.abspath(__file__))
# 사이트 설정을 건너뛰는 Python 플래그(-I·-E·-S, 묶음 -IS 포함)와 환경을 비우는 env -i
_BLIND = re.compile(r'(^|[\s/])python[0-9.]*(\s+-[A-Za-z]+)*\s+-[A-Za-z]*[IES][A-Za-z]*(\s|$)|(^|[\s/])env\s+-i\b')


def _emit(line):
    fd = os.open(_OUT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (line + '\n').encode('utf-8', 'surrogateescape'))
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
    get = env.get if hasattr(env, 'get') else (lambda k: None)
    paths = (get('PYTHONPATH') or get(b'PYTHONPATH') or '')
    paths = paths.decode() if isinstance(paths, bytes) else paths
    return (get('GUARD_READS') or get(b'GUARD_READS')) is None or _HERE not in paths.split(os.pathsep)


def _hook(event, args):
    if event == 'open':
        path = args[0]
        if isinstance(path, bytes):
            path = path.decode('utf-8', 'surrogateescape')
        if not isinstance(path, str) or not path.endswith(('.py', '.pyc')):
            return
        path = os.path.realpath(path)
        if path.endswith('.pyc'):
            if os.path.basename(os.path.dirname(path)) != '__pycache__':
                return
            try:
                path = importlib.util.source_from_cache(path)
            except ValueError:
                return
        if path in _seen or not path.startswith(_ROOT + os.sep):
            return
        _seen.add(path)
        _emit(os.path.relpath(path, _ROOT))
    elif event in ('subprocess.Popen', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.system'):
        if event == 'subprocess.Popen':
            command, env = args[1], args[3]
        elif event == 'os.system':
            command, env = args[0], None
        else:
            command, env = args[-2], args[-1]
        if _BLIND.search(_text(command)) or _blind_env(env):
            _emit('?')


if _OUT and _ROOT:
    _ROOT = os.path.realpath(_ROOT)
    _seen = set()
    sys.addaudithook(_hook)
