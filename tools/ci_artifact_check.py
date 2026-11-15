"""CI 가 artifact 로 올리려는 폴더에 롬·세이브·패치가 섞이지 않았는지 본다. 가드 조각 워크플로(guard-shards.yml)가
업로드 바로 앞에서 부른다. 문제가 하나라도 있으면 1 로 끝나고, 워크플로는 올리지 않는다.

거르는 것:
- 확장자(어느 겹 확장자든) .sfc .smc .nes .nds .ml1 .sav .mss .ips .srm .state 와 그 대문자
- 심볼릭 링크(가리키는 곳이 롬일 수 있다)
- 내용의 SHA-256 이 --hashes 목록(sha256sum 출력 꼴, 워크플로가 롬을 푼 직후 rom/ 로 만든 것)에 든 파일
- --max-bytes 보다 큰 파일(판정 JSON·로그만 올리므로 큰 파일은 무엇이든 의심한다)

--hashes 목록이 비었거나 없으면 대조할 것이 없어 실패로 친다.

  python tools/ci_artifact_check.py work/ci-upload --hashes "$RUNNER_TEMP/rom-hashes.txt"
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

BANNED = frozenset({'.sfc', '.smc', '.nes', '.nds', '.ml1', '.sav', '.mss', '.ips', '.srm', '.state'})
MAX_BYTES = 8 << 20
HASH_LINE = re.compile(r'^([0-9a-fA-F]{64})\s')


def read_hashes(path):
    """sha256sum 출력에서 해시 집합(소문자)."""
    return {m[1].lower() for line in Path(path).read_text(encoding='utf-8').splitlines() if (m := HASH_LINE.match(line))}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def problems(folder, hashes, max_bytes=MAX_BYTES):
    folder = Path(folder)
    if not hashes:
        return ['롬 해시 목록이 비어 대조할 수 없음']
    if not folder.is_dir():
        return [f'{folder}: 폴더가 없음']
    out = []
    for p in sorted(folder.rglob('*')):
        rel = p.relative_to(folder)
        if p.is_symlink():
            out.append(f'{rel}: 심볼릭 링크')
            continue
        if not p.is_file():
            continue
        banned = sorted({s.lower() for s in p.suffixes} & BANNED)
        if banned:
            out.append(f'{rel}: 올리면 안 되는 확장자 {", ".join(banned)}')
            continue
        size = p.stat().st_size
        if size > max_bytes:
            out.append(f'{rel}: {size} 바이트, 한도 {max_bytes} 보다 큼')
            continue
        if sha256(p) in hashes:
            out.append(f'{rel}: 내용이 롬과 같음')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folder', type=Path, help='올리려는 폴더')
    ap.add_argument('--hashes', type=Path, required=True, help='롬 SHA-256 목록(sha256sum 출력)')
    ap.add_argument('--max-bytes', type=int, default=MAX_BYTES)
    a = ap.parse_args(argv)
    try:
        hashes = read_hashes(a.hashes)
    except OSError as e:
        hashes = set()
        print(f'오류: 롬 해시 목록을 읽지 못함: {e}')
    found = problems(a.folder, hashes, a.max_bytes)
    for p in found:
        print(f'오류: {p}')
    print(f'{a.folder}: 문제 {len(found)}개')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
