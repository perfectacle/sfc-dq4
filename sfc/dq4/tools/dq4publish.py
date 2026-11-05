"""1장 통합 롬을 만들어 원본 DQ5 와의 IPS 를 비공개 에셋 저장소(DQ4_ASSETS)에 둔다.

개발판(build)은 sfc/dq4/ips/ 에, 사람에게 내보내는 배포판(release)은 sfc/dq4/release/ 에 둔다. 배포판은 배포 관문
(tools/release_check.py)이 passed 로 판정한 보고서가 있어야만 만들고, 그 보고서의 커밋이 지금 HEAD 이고 다시 빌드한 롬의
SHA-1 이 보고서의 롬 SHA-1 과 같아야 한다. 판정은 보고서의 verdict 를 믿지 않고 단계 결과로 다시 센다. 이 검사는
실수(연습·실패·다른 롬의 보고서를 고름)를 막는 것이지 위조를 막지는 못한다: 보고서는 로컬 파일이라 단계 결과까지 고쳐
쓰면 통과한다.

SOURCE.txt 에 만든 sfc-dq4 커밋과 입력 해시를 적는다. 입력 해시는 dq4build.py 에서 닿는 도구 폴더 파일과
uv.lock 의 해시라 롬 없이 셀 수 있다. check 는 그 해시를 지금 소스로 다시 세어, 다르면 IPS 가 뒤처졌다고 알린다.

  python sfc/dq4/tools/dq4publish.py build [--commit]     # ASAR·DQ4_GALMURI·DQ4_ASSETS 필요, 롬은 rom/
  python sfc/dq4/tools/dq4publish.py stamp                # 입력 해시
  python sfc/dq4/tools/dq4publish.py check --assets DIR   # DIR 의 IPS 가 지금 소스로 만든 것인지
  python sfc/dq4/tools/dq4publish.py release --report work/release/<롬sha1>/report.json [--commit]   # 배포판

build 는 origin/main 에 들어간 커밋에서, 추적 파일을 고치지 않은 상태로만 돈다. 머지되지 않은 커밋으로 만든
IPS 는 SOURCE.txt 의 커밋으로 다시 만들 수 없기 때문이다.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import dq4buildcache  # noqa: E402

IPS_DIR = Path('sfc/dq4/ips')
RELEASE_DIR = Path('sfc/dq4/release')
IPS_NAME = 'dq4-ch1.ips'
STAMP_KEY = '입력 해시'
# tools/release_check.py 가 보고서를 두는 곳과 같아야 한다: work/release/<롬 SHA-1 앞 12자리>[-YYYYmmdd-HHMMSS]/
REPORT_DIR = Path('work/release')
# tools/release_check.py 의 STAGES 와 같아야 한다(tools/tests 의 시험이 본다)
GATE_STAGES = ('build', 'unit', 'guards', 'sweep', 'coverage')
ROW_STAGES = ('unit', 'guards', 'sweep')


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


def remote(assets, *args):
    # 토큰은 인자가 아니라 환경으로 넘긴다: 실패하면 CalledProcessError 가 인자를 그대로 찍는다
    env = dict(os.environ)
    if token := os.environ.get('GH_TOKEN'):
        basic = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.extraHeader',
                   GIT_CONFIG_VALUE_0=f'Authorization: Basic {basic}')
    subprocess.run(['git', *args], cwd=assets, check=True, env=env)


def make_ips(dq5, rom):
    """(원본, 결과, IPS). 원본에 IPS 를 다시 입혀 결과와 같은지 본다."""
    from kr_patch import ips
    base, out = dq5.read_bytes(), rom.read_bytes()
    patch = ips.make(base, out, rle=True)
    if ips.apply(base, patch) != out:
        raise SystemExit('IPS 를 원본에 다시 입혀도 빌드 롬과 같지 않다')
    return base, out, patch


def write_ips(assets, folder, patch, source_name, source_text, commit, message):
    target = assets / folder
    target.mkdir(parents=True, exist_ok=True)
    (target / IPS_NAME).write_bytes(patch)
    (target / source_name).write_text(source_text, encoding='utf-8')
    print(f'{target / IPS_NAME} {len(patch)} 바이트')
    if commit:
        git('add', str(folder), cwd=assets)
        if not git('status', '--porcelain', '--', str(folder), cwd=assets):
            print(f'IPS·{source_name} 그대로: 커밋하지 않음')
            return
        git('commit', '-q', '-m', message, cwd=assets)
        remote(assets, 'push', '-q', 'origin', 'HEAD')
        print(f'에셋 저장소에 커밋·push: {git("rev-parse", "--short", "HEAD", cwd=assets)}')


def build(assets, dq5, dq4, commit):
    import dq4build
    head = merged_commit()
    if commit:
        # 다른 세션이 먼저 넣었으면 그 위에 쌓아야 push 가 받아들여진다
        remote(assets, 'pull', '-q', '--ff-only')
    rom = dq4build.build(ROOT / 'work' / 'publish', dq5, dq4, assets=assets)
    base, out, patch = make_ips(dq5, rom)
    write_ips(assets, IPS_DIR, patch, 'SOURCE.txt',
              f'sfc-dq4 커밋: {head}\n'
              f'명령: uv run --locked python sfc/dq4/tools/dq4publish.py build\n'
              f'원본: dq5.sfc, SHA-1 {hashlib.sha1(base).hexdigest()}\n'
              f'결과 롬: SHA-1 {hashlib.sha1(out).hexdigest()}, {len(out)} 바이트\n'
              f'{STAMP_KEY}: {stamp()}\n', commit, f'sfc/dq4: 1장 IPS (sfc-dq4 {head[:8]})')


def check_report(report, head, path):
    """배포판을 만들어도 되는 보고서인가. 아니면 SystemExit. verdict 가 passed 여야 하고 단계 결과로도 다시 센다."""
    if report.get('rehearse'):
        raise SystemExit('보고서가 연습(--rehearse)이라 passed 가 아님: 배포 관문을 통과한 보고서로만 만든다')
    stages = report.get('stages') or {}
    if not isinstance(stages, dict):
        raise SystemExit(f'보고서의 stages 가 단계 표가 아님({type(stages).__name__}): 관문이 쓴 보고서로만 만든다')
    missing = [s for s in GATE_STAGES if s not in stages]
    extra = sorted(set(stages) - set(GATE_STAGES))
    if missing or extra:
        raise SystemExit(f'보고서의 단계가 관문 단계와 달라 passed 가 아님(빠짐 {", ".join(missing) or "-"}, '
                         f'모르는 단계 {", ".join(extra) or "-"}): 모든 단계를 돈 보고서로만 만든다')
    bad = []
    for name in GATE_STAGES:
        st = stages[name]
        rows = st.get('rows') if isinstance(st, dict) else None
        # 표가 있는 단계는 줄이 하나도 없으면 돌린 것이 없다는 뜻이라 통과로 치지 않는다
        if (not isinstance(st, dict) or st.get('status') != 'passed'
                or (name in ROW_STAGES and not rows)
                or any(not isinstance(r, dict) or r.get('status') != 'passed' for r in rows or [])):
            bad.append(name)
    if bad:
        raise SystemExit(f'보고서의 단계 {", ".join(bad)} 가 통과하지 않아 passed 가 아님')
    if report.get('verdict') != 'passed':
        raise SystemExit(f'보고서 판정이 passed 가 아님({report.get("verdict")})')
    if report.get('dirty'):
        raise SystemExit('보고서가 고친 것이 있는 트리에서 나왔다')
    if report.get('commit') != head:
        raise SystemExit(f'보고서 커밋 {str(report.get("commit"))[:8]} 이 지금 HEAD {head[:8]} 와 다르다')
    sha = report.get('rom_sha1') or ''
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise SystemExit('보고서에 롬 SHA-1 이 없다')
    folder = Path(path).resolve().parent
    if folder.parent != (ROOT / REPORT_DIR).resolve() or not re.fullmatch(rf'{sha[:12]}(-\d{{8}}-\d{{6}})?', folder.name):
        raise SystemExit(f'보고서가 {REPORT_DIR}/{sha[:12]}/ 에 있지 않다: 관문이 그 롬으로 쓴 보고서로만 만든다')


def release(assets, dq5, dq4, report_path, commit):
    import dq4build
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    head = merged_commit()
    check_report(report, head, report_path)
    if commit:
        remote(assets, 'pull', '-q', '--ff-only')
    rom = dq4build.build(ROOT / 'work' / 'publish-release', dq5, dq4, assets=assets)
    base, out, patch = make_ips(dq5, rom)
    if hashlib.sha1(out).hexdigest() != report['rom_sha1']:
        raise SystemExit(f'다시 빌드한 롬 SHA-1 {hashlib.sha1(out).hexdigest()[:12]} 이 보고서의 '
                         f'{report["rom_sha1"][:12]} 와 다르다')
    write_ips(assets, RELEASE_DIR, patch, 'RELEASE.txt',
              f'sfc-dq4 커밋: {head}\n'
              f'명령: uv run --locked python sfc/dq4/tools/dq4publish.py release\n'
              f'원본: dq5.sfc, SHA-1 {hashlib.sha1(base).hexdigest()}\n'
              f'결과 롬: SHA-1 {report["rom_sha1"]}, {len(out)} 바이트\n'
              f'배포 관문 보고서: {report.get("when")}, SHA-256 '
              f'{hashlib.sha256(Path(report_path).read_bytes()).hexdigest()}\n',
              commit, f'sfc/dq4: 1장 배포판 IPS (sfc-dq4 {head[:8]})')


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
    r = sub.add_parser('release', help='배포 관문 passed 보고서로 배포판 IPS 를 에셋 저장소 sfc/dq4/release/ 에 쓴다')
    r.add_argument('--report', required=True, type=Path, help='work/release/<롬sha1>/report.json')
    r.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'))
    r.add_argument('--dq5', default=ROOT / 'rom' / 'dq5.sfc', type=Path)
    r.add_argument('--dq4', default=ROOT / 'rom' / 'dq4.nes', type=Path)
    r.add_argument('--commit', action='store_true', help='에셋 저장소에 커밋하고 push')
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
    if args.cmd == 'release':
        release(args.assets, args.dq5, args.dq4, args.report, args.commit)
        return 0
    build(args.assets, args.dq5, args.dq4, args.commit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
