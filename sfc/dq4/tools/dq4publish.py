"""1장 통합 롬을 만들어 원본 DQ5 와의 IPS 를 비공개 에셋 저장소(DQ4_ASSETS)의 sfc/dq4/ips/ 에 둔다.

SOURCE.txt 에 만든 sfc-dq4 커밋과 입력 해시를 적는다. 입력 해시는 dq4build.py 에서 닿는 도구 폴더 파일과
uv.lock 의 해시라 롬 없이 셀 수 있다. check 는 그 해시를 지금 소스로 다시 세어, 다르면 IPS 가 뒤처졌다고 알린다.

  python sfc/dq4/tools/dq4publish.py build [--commit]     # ASAR·DQ4_GALMURI·DQ4_ASSETS 필요, 롬은 rom/
  python sfc/dq4/tools/dq4publish.py stamp                # 입력 해시
  python sfc/dq4/tools/dq4publish.py check --assets DIR   # DIR 의 IPS 가 지금 소스로 만든 것인지

build 는 origin/main 에 들어간 커밋에서, 추적 파일을 고치지 않은 상태로만 돈다. 머지되지 않은 커밋으로 만든
IPS 는 SOURCE.txt 의 커밋으로 다시 만들 수 없기 때문이다.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4buildcache  # noqa: E402

IPS_DIR = Path('sfc/dq4/ips')
IPS_NAME = 'dq4-ch1.ips'
STAMP_KEY = '입력 해시'


def inputs():
    """IPS 를 바꿀 수 있는 저장소 파일(ROOT 기준)."""
    files = []
    for path in dq4buildcache.sources(HERE / 'dq4build.py'):
        files += sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    return [f.relative_to(ROOT) for f in files if '__pycache__' not in f.parts] + [Path('uv.lock')]


def stamp():
    h = hashlib.sha256()
    for rel in inputs():
        h.update(rel.as_posix().encode() + b'\0' + hashlib.sha256((ROOT / rel).read_bytes()).digest())
    return h.hexdigest()


def read_source(text):
    return dict(line.split(': ', 1) for line in text.splitlines() if ': ' in line)


def git(*args, cwd=ROOT):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def merged_commit():
    if git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('추적 파일이 바뀌어 있다: 커밋하거나 되돌린 뒤에 만든다')
    git('fetch', '-q', 'origin', 'main')
    head = git('rev-parse', 'HEAD')
    if subprocess.run(['git', 'merge-base', '--is-ancestor', head, 'origin/main'], cwd=ROOT).returncode:
        raise SystemExit(f'{head[:8]} 이 origin/main 에 없다: 머지된 커밋에서 만든다')
    return head


def push(assets):
    token = os.environ.get('GH_TOKEN')
    auth = ['-c', f'http.extraHeader=Authorization: Bearer {token}'] if token else []
    subprocess.run(['git', *auth, 'push', '-q', 'origin', 'HEAD'], cwd=assets, check=True)


def build(assets, dq5, dq4, commit):
    from kr_patch import ips
    import dq4build
    head = merged_commit()
    rom = dq4build.build(ROOT / 'work' / 'publish', dq5, dq4)
    base, out = dq5.read_bytes(), rom.read_bytes()
    patch = ips.make(base, out, rle=True)
    if ips.apply(base, patch) != out:
        raise SystemExit('IPS 를 원본에 다시 입혀도 빌드 롬과 같지 않다')
    target = assets / IPS_DIR
    target.mkdir(parents=True, exist_ok=True)
    (target / IPS_NAME).write_bytes(patch)
    (target / 'SOURCE.txt').write_text(
        f'sfc-dq4 커밋: {head}\n'
        f'명령: uv run --locked python sfc/dq4/tools/dq4publish.py build\n'
        f'원본: dq5.sfc, SHA-1 {hashlib.sha1(base).hexdigest()}\n'
        f'결과 롬: SHA-1 {hashlib.sha1(out).hexdigest()}, {len(out)} 바이트\n'
        f'{STAMP_KEY}: {stamp()}\n', encoding='utf-8')
    print(f'{target / IPS_NAME} {len(patch)} 바이트, 결과 롬 sha1={hashlib.sha1(out).hexdigest()}')
    if commit:
        git('add', str(IPS_DIR), cwd=assets)
        if not git('status', '--porcelain', '--', str(IPS_DIR), cwd=assets):
            print('IPS·SOURCE.txt 그대로: 커밋하지 않음')
            return
        git('commit', '-q', '-m', f'sfc/dq4: 1장 IPS (sfc-dq4 {head[:8]})', cwd=assets)
        push(assets)
        print(f'에셋 저장소에 커밋·push: {git("rev-parse", "--short", "HEAD", cwd=assets)}')


def check(assets):
    source = assets / IPS_DIR / 'SOURCE.txt'
    if not source.is_file():
        raise SystemExit(f'{source} 이 없다: dq4publish.py build --commit 으로 처음 만든다')
    recorded = read_source(source.read_text(encoding='utf-8'))
    now = stamp()
    if recorded.get(STAMP_KEY) != now:
        print(f'IPS 가 뒤처졌다: sfc-dq4 {recorded.get("sfc-dq4 커밋", "?")[:8]} 로 만든 뒤 빌드 입력이 바뀜\n'
              f'  기록 {recorded.get(STAMP_KEY)}\n  지금 {now}\n'
              '  sfc-dq4 main 에서 dq4publish.py build --commit 으로 다시 만든다')
        return 1
    print(f'IPS 가 최신: sfc-dq4 {recorded["sfc-dq4 커밋"][:8]}, 입력 해시 {now[:12]}')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='1장 롬을 만들어 IPS 를 에셋 저장소에 쓴다')
    b.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'), help='비공개 에셋 저장소(DQ4_ASSETS)')
    b.add_argument('--dq5', default=ROOT / 'rom' / 'dq5.sfc', type=Path)
    b.add_argument('--dq4', default=ROOT / 'rom' / 'dq4.nes', type=Path)
    b.add_argument('--commit', action='store_true', help='에셋 저장소에 커밋하고 push(GH_TOKEN 이 있으면 그 토큰으로)')
    sub.add_parser('stamp', help='입력 해시')
    c = sub.add_parser('check', help='에셋의 IPS 가 지금 소스로 만든 것인지')
    c.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'), required=False)
    args = ap.parse_args()
    if args.cmd == 'stamp':
        print(stamp())
        return 0
    if args.assets is None:
        ap.error('--assets 또는 DQ4_ASSETS 가 필요하다')
    if args.cmd == 'check':
        return check(args.assets)
    build(args.assets, args.dq5, args.dq4, args.commit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
