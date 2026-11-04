"""읽은 롬 바이트 캐시(dq4readset)를 켜고 서장을 만들 때 출력이 빠지지 않는지 본다.

서장 상태 캐시(StateCache) 없이 dq4ch1walkcheck.prologue(readset=True) 를 같은 빈 읽은 바이트 캐시로 세 번 돌린다.

  빈 캐시   처음은 캐시가 비어 모든 구간을 새로 돈다
  적중      둘째는 같은 롬·같은 입력이라 모든 구간이 캐시에서 펼쳐진다(새 항목이 늘지 않음)
  재검증    셋째는 DQ4_READSET_VERIFY=1 로 적중한 구간을 다시 돌려 캐시와 견준다

세 번 모두 서장이 통과하고, 시작 상태(start/start.mss)·서장 기록(prologue/walk.txt)·서장 끝 상태(prologue/end.mss)가
있어야 한다. 기록과 끝 상태는 세 번이 같아야 한다(롬 복사본 이름은 빼고 견줌).

  uv run --locked python sfc/dq4/tools/dq4readsetprologuecheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/rsprologue
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4ch1walkcheck as wc  # noqa: E402
import dq4readset as rs  # noqa: E402

FILES = ('start/start.mss', 'prologue/walk.txt', 'prologue/end.mss')
RUNS = (('empty', '0'), ('hit', '0'), ('verify', '1'))


def entries(cache):
    """캐시의 항목 수(키마다 여러 항목)."""
    store = rs.Store(cache)
    return sum(len(store.entries(p.stem)) for p in (cache / 'index').rglob('*.json')) if (cache / 'index').is_dir() else 0


def one(mesence, rom_path, out, cache, verify):
    out.mkdir(parents=True)
    rom = out / 'c.sfc'
    shutil.copyfile(rom_path, rom)
    env = {'DQ4_READSET': '', 'DQ4_READSET_CACHE': str(cache), 'DQ4_READSET_VERIFY': verify}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        _, r = wc.prologue(mesence, rom, rom.read_bytes(), out, wc.SEGMENTS, cache=None, readset=True)
    except SystemExit as e:
        r = {'status': 'failed', 'problems': [str(e)]}
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    files = {}
    for rel in FILES:
        p = out / rel
        if p.exists():
            files[rel] = rs.file_hash(p)
    return r, files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = a.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cache = out / 'cache'
    results, first, counts = [], None, []
    for name, verify in RUNS:
        r, files = one(mesence, a.rom.resolve(), out / name, cache, verify)
        counts.append(entries(cache))
        problems = [f'서장: {p}' for p in r.get('problems', [])] if r.get('status') != 'passed' else []
        problems += [f'{rel} 없음' for rel in FILES if rel not in files]
        if first is None:
            first = files
        else:
            problems += [f'{rel} 가 빈 캐시 실행과 다름' for rel in FILES if rel in files and rel in first
                         and files[rel] != first[rel]]
        if name == 'empty' and not counts[-1]:
            problems.append('캐시에 항목이 들지 않음')
        if name != 'empty' and counts[-1] != counts[0]:
            problems.append(f'적중해야 할 실행이 항목을 더함({counts[0]} → {counts[-1]})')
        res = {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems,
               'entries': counts[-1]}
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    ok = all(r['status'] == 'passed' for r in results)
    print(json.dumps({'status': 'passed' if ok else 'failed'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
