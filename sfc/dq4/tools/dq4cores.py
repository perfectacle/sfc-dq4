"""호환성 검사(dq4compatcheck.py walk)가 쓰는 libretro 코어를 고정한 커밋에서 받아 빌드한다.

코어 바이너리는 저장소에 두지 않는다(bsnes 는 GPLv3, snes9x 는 비상업 라이선스라 재배포 의무가 따르고, 플랫폼마다
다르다). 대신 libretro 공식 저장소의 커밋을 여기에 고정해, 어느 세션이든 같은 소스로 같은 코어를 만든다. 커밋은
DEP-01 처럼 나온 지 7일이 넘은 것만 고른다.

출력은 원래 체크아웃의 work/cores/(워크트리끼리 함께 씀, DQ4_CORES 로 바꿈)에 <코어>_libretro.<확장자> 와
<코어>.json(커밋·출력 SHA-256)을 둔다. 이미 같은 커밋으로 만든 것이 있으면 다시 빌드하지 않는다.

  python sfc/dq4/tools/dq4cores.py            # 둘 다 받아 빌드(처음 약 1분)
  python sfc/dq4/tools/dq4cores.py --check    # 빌드 없이 상태만
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# 고친 날짜와 까닭은 형식 문서(sfc/dq4/docs/dq4-compat-format.md)의 「코어」 절
CORES = {
    'bsnes': {
        'repo': 'https://github.com/libretro/bsnes',
        'commit': '63ee22f7af8f5d1ada295c2c98fd7bf261fa62a7',   # 2026-09-04, 「bsnes 115」
        'make': [],
        'output': 'bsnes_libretro',
        # clang 21 은 nall/traits.hpp 의 표준 라이브러리 특수화를 오류로 본다(GCC·옛 clang 은 경고도 아님)
        'clang_cxx': '-Wno-error=invalid-specialization',
    },
    'snes9x': {
        'repo': 'https://github.com/libretro/snes9x',
        'commit': 'fae2fea08f74180759ef540ee94259213f503480',   # 2026-09-19, 「1.63 fae2fea」
        'make': ['-C', 'libretro'],
        'output': 'libretro/snes9x_libretro',
        'clang_cxx': '',
    },
}
ENV = {'bsnes': 'LIBRETRO_BSNES', 'snes9x': 'LIBRETRO_SNES9X'}


def suffix():
    return {'darwin': 'dylib', 'win32': 'dll', 'msys': 'dll', 'cygwin': 'dll'}.get(sys.platform, 'so')


def cores_dir():
    """DQ4_CORES, 없으면 원래 체크아웃(git worktree 목록의 첫째)의 work/cores."""
    if os.environ.get('DQ4_CORES'):
        return Path(os.environ['DQ4_CORES'])
    try:
        first = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()[0]
        return Path(first.removeprefix('worktree ')) / 'work' / 'cores'
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError):
        return ROOT / 'work' / 'cores'


def core_path(name, folder=None):
    """그 코어의 파일. 환경 변수가 있으면 그것, 없으면 cores_dir() 안."""
    if os.environ.get(ENV[name]):
        return Path(os.environ[ENV[name]])
    return (folder or cores_dir()) / f'{name}_libretro.{suffix()}'


def stamp(name, folder=None):
    f = (folder or cores_dir()) / f'{name}.json'
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_clang():
    try:
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        out = subprocess.run([*cxx, '--version'], capture_output=True, text=True).stdout
    except (OSError, ValueError):
        return False
    return 'clang' in out


def write_atomic(dst, data):
    """다른 워크트리가 동시에 읽어도 반쯤 쓴 파일을 보지 않게, 옆에 쓰고 바꿔 넣는다."""
    tmp = dst.with_name(f'.{dst.name}.{os.getpid()}')
    tmp.write_bytes(data)
    os.replace(tmp, dst)


def build(name, folder, jobs):
    """고정 커밋을 받아 빌드한다. 같은 폴더를 쓰는 워크트리끼리 겹치지 않게 잠근다."""
    import fcntl
    with (folder / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _build(name, folder, jobs)


def _build(name, folder, jobs):
    spec = CORES[name]
    out = folder / f'{name}_libretro.{suffix()}'
    have = stamp(name, folder)
    if have and have.get('commit') == spec['commit'] and out.exists() and have.get('sha256') == sha256(out):
        print(f'{name}: {spec["commit"][:12]} 이미 있음 {out}')
        return out
    src = folder / 'src' / f'{name}-{spec["commit"][:12]}-{os.getpid()}'
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    try:
        git = ['git', '-C', str(src)]
        subprocess.run(git + ['init', '-q'], check=True)
        subprocess.run(git + ['remote', 'add', 'origin', spec['repo']], check=True)
        subprocess.run(git + ['fetch', '-q', '--depth', '1', 'origin', spec['commit']], check=True)
        subprocess.run(git + ['-c', 'advice.detachedHead=false', 'checkout', '-q', 'FETCH_HEAD'], check=True)
        head = subprocess.run(git + ['rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        if head != spec['commit']:
            raise SystemExit(f'{name}: 받은 커밋 {head} 가 고정한 {spec["commit"]} 와 다름')
        cmd = ['make', f'-j{jobs}', *spec['make']]
        if spec['clang_cxx'] and is_clang():
            # 명령줄 CXXFLAGS 는 Makefile 의 플래그를 통째로 덮으므로 컴파일러에 붙인다
            cmd.append(f'CXX={os.environ.get("CXX", "c++")} {spec["clang_cxx"]}')
        print(f'{name}: {spec["commit"][:12]} 빌드: {" ".join(cmd)}', flush=True)
        with (folder / f'{name}-build.log').open('w', encoding='utf-8') as log:
            subprocess.run(cmd, cwd=src, stdout=log, stderr=subprocess.STDOUT, check=True)
        data = (src / f'{spec["output"]}.{suffix()}').read_bytes()
    finally:
        shutil.rmtree(src, ignore_errors=True)
    write_atomic(out, data)
    info = {'commit': spec['commit'], 'repo': spec['repo'], 'sha256': hashlib.sha256(data).hexdigest(),
            'platform': sys.platform}
    write_atomic(folder / f'{name}.json', (json.dumps(info, indent=1) + '\n').encode())
    print(f'{name}: {out} sha256 {info["sha256"][:16]}…')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='빌드하지 않고 상태만')
    ap.add_argument('--core', choices=('all', *CORES), default='all')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    args = ap.parse_args()
    folder = cores_dir()
    names = list(CORES) if args.core == 'all' else [args.core]
    bad = 0
    for name in names:
        if args.check:
            have, path = stamp(name, folder), core_path(name, folder)
            ok = bool(have and have.get('commit') == CORES[name]['commit'] and path.exists()
                      and have.get('sha256') == sha256(path))
            print(f'{name}: {"있음" if ok else "없음 또는 다른 커밋"} {path}')
            bad += not ok
        else:
            folder.mkdir(parents=True, exist_ok=True)
            build(name, folder, args.jobs)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
