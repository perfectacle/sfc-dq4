"""빌드가 부르는 도구 하위 프로세스를 입력·도구 소스 해시를 키로 저장해 두고 다시 쓴다.

키는 도구 스크립트에서 import·도구 이름·데이터 파일 이름 문자열을 따라 닿는 도구 폴더의 파일, uv.lock, 파이썬 판,
인자로 만든다. 인자가 파일·폴더면 경로 대신 내용을 넣고, JSON 이면 그 안의 문자열 가운데 파일을 가리키는 것
(JSON 파일 기준 또는 현재 폴더 기준 경로)도 내용을 넣는다. 출력은 OUT_FLAGS 뒤의 경로와 표준 출력이다.
도구나 입력을 고치면 키가 바뀌어 저절로 다시 돌린다.

기본 자리는 원래 체크아웃의 work/cache/calls 라 워크트리끼리 함께 쓴다. DQ4_BUILD_CACHE 로 자리를 바꾸고,
DQ4_BUILD_CACHE=off 로 끈다. 칸은 KEEP_SECONDS 동안 쓰이지 않으면 지운다. 롬에서 나온 자료라 커밋하지 않는다. 통째로 지워도 된다.
도구는 OUT_FLAGS 뒤의 경로와 그 파일 곁의 같은 이름 파일(이름.*)에만 써야 한다. 그 밖에 쓰는 출력은 칸에 담기지 않는다.
"""
import ast
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOL_DIRS = (HERE, ROOT / 'sfc' / 'dq5' / 'tools', ROOT / 'fc' / 'dq4' / 'tools')
FILE_NAME = re.compile(r'[\w.-]+\.\w+')
DIR_NAME = re.compile(r'[A-Za-z]\w{2,}')
# 도구가 결과를 쓰는 인자. 이 뒤의 경로는 키에 넣지 않고(빌드마다 임시 폴더가 다름) 결과로 저장한다.
OUT_FLAGS = ('-o', '--out', '--ips', '--report')
# 도구가 읽는 환경 변수. 값이 가리키는 파일·폴더 내용을 키에 넣는다
ENV_INPUTS = ('ASAR', 'DQ4_GALMURI', 'NDS_FS')
# 켜면 도구가 출력 인자 밖에 파일을 쓰는 환경 변수. 켜져 있으면 캐시하지 않는다
ENV_OUTPUTS = ('DQ4_NAMEENTRY_SYMBOLS', 'DQ4_WINDOWNAME_SYMBOLS')
# 이만큼 쓰이지 않은 칸은 새 칸을 넣을 때 지운다
KEEP_SECONDS = 7 * 24 * 3600


@functools.cache
def _resolve(name):
    for d in TOOL_DIRS:
        if (d / name).is_file():
            return d / name
    return None


@functools.cache
def _resolve_dir(name):
    for d in TOOL_DIRS:
        if (d / name).is_dir():
            return d / name
    return None


@functools.cache
def _refs(path):
    """path 가 import 하거나 이름으로 부르는 도구 폴더 파일. 함수 안의 import 와 'dq5build.py' 같은 이름 문자열도 든다."""
    if path.suffix != '.py':
        return ()
    refs, dirs = [], []
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            refs += [a.name.split('.')[0] + '.py' for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            refs.append(node.module.split('.')[0] + '.py')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and FILE_NAME.fullmatch(node.value):
            refs.append(node.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and DIR_NAME.fullmatch(node.value):
            dirs.append(node.value)
    return (tuple(p for p in map(_resolve, dict.fromkeys(refs)) if p)
            + tuple(p for p in map(_resolve_dir, dict.fromkeys(dirs)) if p))


@functools.cache
def _digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def sources(*entries):
    """entries 에서 닿는 도구 폴더 파일."""
    seen, todo = set(), [Path(e).resolve() for e in entries]
    while todo:
        path = todo.pop()
        if path not in seen:
            seen.add(path)
            todo += _refs(path)
    return sorted(seen)


@functools.cache
def _toolkit_hash():
    """설치된 kr_patch 소스. 편집 설치나 워크트리마다 다른 .venv 도 키를 나누게 uv.lock 대신 실제 파일을 본다."""
    try:
        import kr_patch
    except ImportError:
        return b''
    h = hashlib.sha256()
    base = Path(kr_patch.__file__).parent
    for path in sorted(base.rglob('*.py')):
        h.update(str(path.relative_to(base)).encode() + b'\0' + _digest(path))
    return h.digest()


@functools.cache
def _tool_hash(tool):
    h = hashlib.sha256((ROOT / 'uv.lock').read_bytes() + sys.version.encode() + _toolkit_hash())
    for path in sources(tool):
        # 'dq4art' 처럼 이름으로 부르는 도구 폴더 안 자료 폴더는 안의 파일 전부
        for f in (sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]):
            h.update(str(f.relative_to(path.parent)).encode() + b'\0' + _digest(f))
    return h.hexdigest()


def _strings(doc):
    if isinstance(doc, str):
        yield doc
    elif isinstance(doc, dict):
        for v in doc.values():
            yield from _strings(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _strings(v)


def _content(path, h, seen):
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    if path.is_dir():
        for p in sorted(path.rglob('*')):
            if p.is_file():
                h.update(str(p.relative_to(path)).encode() + b'\0')
                _content(p, h, seen)
        return
    data = path.read_bytes()
    h.update(hashlib.sha256(data).digest())
    if path.suffix != '.json':
        return
    try:
        doc = json.loads(data)
    except ValueError:
        return
    for s in _strings(doc):
        if len(s) > 255 or '\n' in s:
            continue
        for ref in (path.parent / s, Path(s)):
            if ref.is_file():
                h.update(s.encode() + b'\0')
                _content(ref, h, seen)
                break


def _key(tool, args):
    """(키, 출력 경로). --out=경로·-o경로 처럼 붙여 쓴 출력은 알아보지 못하니 None(캐시하지 않음)."""
    if any(a.startswith(tuple(f + '=' for f in OUT_FLAGS)) or (a.startswith('-o') and a != '-o') for a in args):
        return None, []
    if any(os.environ.get(name) for name in ENV_OUTPUTS):
        return None, []
    h = hashlib.sha256(_tool_hash(tool).encode() + Path(tool).name.encode())
    for name in ENV_INPUTS:
        value = os.environ.get(name, '')
        h.update(f'\0env {name}={value}'.encode())
        if value and Path(value).exists():
            _content(Path(value), h, set())
    outs = []
    for i, a in enumerate(args):
        if i and args[i - 1] in OUT_FLAGS:
            outs.append(Path(a))
            h.update(f'\0out{len(outs)}'.encode())
        elif (os.sep in a or FILE_NAME.fullmatch(a)) and Path(a).exists():
            # 임시 폴더 경로는 빌드마다 달라 이름과 내용만 넣는다
            h.update(b'\0file' + Path(a).name.encode())
            _content(Path(a), h, set())
        else:
            h.update(b'\0arg' + a.encode())
    return h.hexdigest()[:40], outs


@functools.cache
def _main_checkout():
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'worktree', 'list', '--porcelain'],
                             capture_output=True, text=True, check=True).stdout
        return Path(out.splitlines()[0].removeprefix('worktree '))
    except (OSError, subprocess.CalledProcessError, IndexError):
        return ROOT


def cache_dir():
    env = os.environ.get('DQ4_BUILD_CACHE')
    if env == 'off':
        return None
    return Path(env) / 'calls' if env else _main_checkout() / 'work' / 'cache' / 'calls'


def _siblings(out):
    """파일 출력 곁에 같은 이름으로 쓰는 파일(dq5build fromrom 의 이름.NNN.bin 등)."""
    return [f for f in out.parent.glob(f'{out.stem}.*') if f != out and f.is_file()] if out.parent.is_dir() else []


def _stat(f):
    st = f.stat()
    return st.st_mtime_ns, st.st_size


def _snapshot(outs):
    """출력 자리에 먼저 있던 파일. 도구가 새로 쓰거나 바꾼 파일만 칸에 담으려고 찍어 둔다."""
    return {f: _stat(f) for out in outs
            for f in (out.rglob('*') if out.is_dir() else _siblings(out)) if f.is_file()}


def _store(cache, entry, outs, before, stdout, stderr):
    tmp = None
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=cache, prefix='.tmp-'))
        for k, out in enumerate(outs):
            if out.is_dir():
                for f in out.rglob('*'):
                    if f.is_file() and before.get(f) != _stat(f):
                        _copy(f, tmp / f'out{k}' / f.relative_to(out))
                (tmp / f'out{k}').mkdir(exist_ok=True)
            elif out.exists():
                _copy(out, tmp / f'out{k}')
                for f in _siblings(out):
                    if before.get(f) != _stat(f):
                        _copy(f, tmp / f'side{k}' / f.name)
        (tmp / 'stdout').write_text(stdout, encoding='utf-8')
        (tmp / 'stderr').write_text(stderr, encoding='utf-8')
        os.rename(tmp, entry)
        tmp = None
        _prune(cache)
    except OSError:  # 다른 세션이 먼저 넣었거나 저장을 못 했다. 결과는 이미 out 에 있다
        pass
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def _prune(cache):
    limit = time.time() - KEEP_SECONDS
    for entry in cache.iterdir():
        try:
            if entry.stat().st_mtime < limit:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            pass


def _restore(entry, outs):
    """칸의 (표준 출력, 표준 오류). 읽는 도중 칸이 지워지면 None(도구를 직접 돌린다)."""
    try:
        for k, out in enumerate(outs):
            if (entry / f'out{k}').exists():
                _copy(entry / f'out{k}', out)
            if (entry / f'side{k}').is_dir():
                _copy(entry / f'side{k}', out.parent)
        stdout = (entry / 'stdout').read_text(encoding='utf-8')
        stderr = (entry / 'stderr').read_text(encoding='utf-8') if (entry / 'stderr').exists() else ''
        os.utime(entry)
        return stdout, stderr
    except OSError:
        return None


def _copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def run(tool, *args, echo_stderr=False):
    """python tool args 의 표준 출력. 실패하면 RuntimeError(도구 이름·앞 인자 둘·표준 오류 끝).
    echo_stderr 면 성공한 호출의 표준 오류(경고)를 캐시에서 나왔을 때도 내보낸다."""
    tool = Path(tool).resolve()
    args = [str(a) for a in args]
    cache = cache_dir()
    key = None
    if cache is not None:
        key, outs = _key(tool, args)
    if key is not None:
        entry = cache / key
        if entry.is_dir():
            hit = _restore(entry, outs)
            if hit is not None:
                if echo_stderr:
                    sys.stderr.write(hit[1])
                return hit[0]
        before = _snapshot(outs)
    proc = subprocess.run([sys.executable, str(tool), *args], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"{tool.name} {' '.join(args[:2])}: {proc.stderr[-1500:]}")
    if echo_stderr:
        sys.stderr.write(proc.stderr)
    if key is not None:
        _store(cache, entry, outs, before, proc.stdout, proc.stderr)
    return proc.stdout
