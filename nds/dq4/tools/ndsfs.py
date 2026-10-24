"""NDS DQ4 파일 시스템 요약과 두 롬(일본판·한글 팬패치판)의 파일 비교. nds/dq4/docs/rom-map.md 의 표를 만든다.

사용:
  python nds/dq4/tools/ndsfs.py summary ROOT          data/data/ 아래 폴더별 파일 수·크기·확장자
  python nds/dq4/tools/ndsfs.py diff JPROOT KRROOT    내용이 다른 파일과 크기
ROOT 는 `krpatch nds unpack` 으로 푼 폴더.
"""
import collections
import os
import sys


def walk(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith('.')]
        for f in fn:
            p = os.path.join(dp, f)
            yield os.path.relpath(p, root), os.path.getsize(p)


def ext(name):
    base = os.path.basename(name)
    parts = base.split('.')
    return '.'.join(parts[-2:]) if len(parts) > 2 and parts[-1] == 'lz' else (parts[-1] if len(parts) > 1 else '-')


def cmd_summary(root):
    data = os.path.join(root, 'data', 'data')
    groups = collections.defaultdict(lambda: [0, 0, collections.Counter()])
    for rel, size in walk(data):
        top = rel.split(os.sep)[0] if os.sep in rel else '(최상위)'
        g = groups[top]
        g[0] += 1
        g[1] += size
        g[2][ext(rel)] += 1
    print('| 폴더 | 파일 | 크기(KB) | 확장자 |')
    print('| --- | --- | --- | --- |')
    for top, (n, size, exts) in sorted(groups.items()):
        print(f'| `{top}` | {n} | {size // 1024} | ' + ', '.join(f'`{e}` {c}' for e, c in exts.most_common(5)) + ' |')


def cmd_diff(jp, kr):
    a, b = dict(walk(jp)), dict(walk(kr))
    print('| 파일 | 일본판 | 한글판 |')
    print('| --- | --- | --- |')
    for rel in sorted(set(a) | set(b)):
        if rel not in a or rel not in b:
            print(f'| `{rel}` | {a.get(rel, "-")} | {b.get(rel, "-")} |')
        elif open(os.path.join(jp, rel), 'rb').read() != open(os.path.join(kr, rel), 'rb').read():
            print(f'| `{rel}` | {a[rel]} | {b[rel]} |')


def main(argv):
    if argv[:1] == ['summary']:
        cmd_summary(argv[1])
    elif argv[:1] == ['diff']:
        cmd_diff(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
