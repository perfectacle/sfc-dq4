"""빌드의 뜨거운 계산을 맡는 Go 작은 도구(sfc/dq4/tools/native/<이름>)를 찾고 만든다.

바이너리는 저장소에 두지 않는다. 소스 폴더 해시를 이름에 넣어 DQ4_NATIVE(없으면 원래 체크아웃의 work/native)에
<이름>-<해시 12자리> 로 만든다. 소스를 고치면 이름이 바뀌어 옛 바이너리를 쓰지 않는다. 부르는 쪽은 binary() 가
None 이면(만들지 않았거나 go 가 없음) 같은 결과를 내는 파이썬으로 돈다. 결과가 같은지는 각 도구의 대조 단위 테스트가 본다.
DQ4_NATIVE=off 면 늘 파이썬.

  python sfc/dq4/tools/dq4native.py build     # 없는 도구를 만듦(go 가 있어야 함)
  python sfc/dq4/tools/dq4native.py path      # 도구마다 쓰일 바이너리 경로(없으면 「파이썬」)
"""
import argparse
import functools
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCES = HERE / 'native'


def source_hash(name):
    h = hashlib.sha256()
    folder = SOURCES / name
    for f in sorted(p for p in folder.rglob('*') if p.is_file()):
        h.update(str(f.relative_to(folder)).encode() + b'\0' + f.read_bytes())
    return h.hexdigest()[:12]


def native_dir():
    if os.environ.get('DQ4_NATIVE'):
        return Path(os.environ['DQ4_NATIVE'])
    try:
        first = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()[0]
        return Path(first.removeprefix('worktree ')) / 'work' / 'native'
    except (OSError, subprocess.CalledProcessError, IndexError):
        return ROOT / 'work' / 'native'


def target(name):
    return native_dir() / f'{name}-{source_hash(name)}'


@functools.cache
def binary(name):
    """지금 소스로 만든 바이너리, 없으면 None."""
    if os.environ.get('DQ4_NATIVE', '').lower() == 'off':
        return None
    path = target(name)
    return path if path.is_file() and os.access(path, os.X_OK) else None


def build(name):
    """지금 소스의 바이너리를 만든다. 이미 있으면 그대로."""
    if target(name).is_file():
        return target(name)
    go = shutil.which('go')
    if go is None:
        raise SystemExit('go 가 없음')
    out = target(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f'.{out.name}.{os.getpid()}')
    env = dict(os.environ, CGO_ENABLED='0', GOTOOLCHAIN='local', GOFLAGS='-mod=mod')
    subprocess.run([go, 'build', '-trimpath', '-o', str(tmp), '.'], cwd=SOURCES / name, env=env, check=True)
    os.replace(tmp, out)
    return out


def names():
    return sorted(p.name for p in SOURCES.iterdir() if (p / 'go.mod').is_file())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('build', 'path'))
    a = ap.parse_args()
    for name in names():
        if a.cmd == 'build':
            print(f'{name}: {build(name)}')
        else:
            print(f'{name}: {binary(name) or "파이썬"}')


if __name__ == '__main__':
    sys.exit(main())
