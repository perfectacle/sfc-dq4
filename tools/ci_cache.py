"""CI 캐시의 암호화 묶음과 출하 롬 빌드 단계 조각. GitHub 러너에서 composite action(.github/actions/enc-cache·
ship-cache)이 부른다. 형식: sfc/dq4/docs/dq4-release-check-format.md 「CI 캐시」.

퍼블릭 저장소라 포크 PR 워크플로도 기본 브랜치의 actions/cache 를 읽는다. 그래서 롬에서 나온 바이트(빌드 단계 결과·
사운드 변환·세이브스테이트·읽은 롬 바이트)는 폴더를 tar+zstd 로 묶어 CI_ROM_AGE_KEY 의 공개 키로 age 암호화한 파일 하나로만
캐시에 넣고, 되살릴 때 같은 키로 푼다. 묶음 키는 「접두어-내용 해시」 라 내용이 같으면 다시 저장하지 않는다.

  python tools/ci_cache.py unpack --name N --dir D --matched KEY
                                                           $RUNNER_TEMP/enc-cache/N.age 가 있으면 D 에 풀고 되살린 키를 적어 둠
  python tools/ci_cache.py pack --name N --dir D --prefix P [--max-mb M] [--exclude 이름,…]
                                                           D 를 묶어 암호화하고 save=true·key=P-<해시> 를 GITHUB_OUTPUT 에.
                                                           키가 이 잡에서 N 으로 되살린 키와 같거나 D 가 비었으면 save=false
  python tools/ci_cache.py prune --dir D --since FILE      D 바로 아래에서 FILE 보다 오래된 칸을 지움
  python tools/ci_cache.py ship-build --out work/ch1 --chunks DIR [dq4build 인자…]
                                                           dq4build.py 를 돌리고, 쓴 빌드 단계 캐시 칸을 단계 이름별로
                                                           DIR/<단계>/<칸> 에 복사(단계 하나가 바뀌어도 나머지 묶음은 그대로),
                                                           단계 시간([stage])을 찍고 미리 만든 빌드 표시를 남김
  python tools/ci_cache.py prebuilt --out DIR [dq4build 인자…]
                                                           DQ4_PREBUILT 의 같은 빌드를 복사, 없으면 dq4build.py
  python tools/ci_cache.py slots --file F --count N        guards.py --unit-slots 목록을 p0=…·d0=… 줄로(GITHUB_OUTPUT 용,
                                                           빈 자리는 빈 값). composite action unit-cache 가 부른다
  python tools/ci_cache.py digest --dir D --variant V --kind K --out FILE
                                                           빌드 폴더 D 의 파일마다 SHA-256(롬 바이트는 담지 않음)
  python tools/ci_cache.py verify-build DIR                DIR 아래 digest 들을 견줌: 변형마다 캐시 빌드(rom 잡)·조각이 받은 것이
                                                           무캐시 빌드(cold 잡)와 바이트가 같아야 0. 단계별 표(Markdown)
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types

ROOT = Path(__file__).resolve().parents[1]
DQ4_TOOLS = ROOT / 'sfc' / 'dq4' / 'tools'
# 출하 롬 빌드가 dq4buildcache 로 부르는 단계. .github/actions/ship-cache 가 이 이름마다 묶음 하나를 둔다
# (test_release_gate_workflow 가 맞춰 봄). 목록에 없는 새 단계는 'other' 묶음에 든다
SHIP_LABELS = ('titlelayers', 'chapter1-messages', 'titlelayerpatch', 'overture-build', 'menupatch-build',
               'chapter1-build', 'other')
KEY_LINE = re.compile(r'^AGE-SECRET-KEY-\S+$', re.M)


def store():
    temp = os.environ.get('RUNNER_TEMP')
    if not temp:
        raise SystemExit('RUNNER_TEMP 가 없음(GitHub Actions 러너에서 부른다)')
    path = Path(temp) / 'enc-cache'
    path.mkdir(parents=True, exist_ok=True)
    return path


def key_file():
    """CI_ROM_AGE_KEY 를 0600 임시 파일로. 부른 쪽이 지운다. 값은 찍지 않고 가린다."""
    text = os.environ.get('CI_ROM_AGE_KEY', '')
    lines = KEY_LINE.findall(text)
    if not lines:
        raise SystemExit('::error::CI_ROM_AGE_KEY 에 age 개인 키 줄(AGE-SECRET-KEY-…)이 없음')
    for line in lines:
        print(f'::add-mask::{line}', flush=True)
    fd, path = tempfile.mkstemp(prefix='age-', dir=store())
    with os.fdopen(fd, 'w') as f:
        f.write(text.strip() + '\n')
    return Path(path)


def files_of(folder, exclude=()):
    """폴더 안 파일. exclude 는 빼는 맨 위 이름."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob('*') if p.is_file() and p.relative_to(folder).parts[0] not in exclude)


def content_hash(folder, exclude=()):
    """폴더 안 파일의 상대 경로·내용 해시. 없거나 비었으면 None."""
    folder = Path(folder)
    files = files_of(folder, exclude)
    if not files:
        return None
    h = hashlib.sha256()
    for f in files:
        with f.open('rb') as fh:
            h.update(str(f.relative_to(folder)).encode() + b'\0' + hashlib.file_digest(fh, 'sha256').digest())
    return h.hexdigest()[:40]


def folder_bytes(folder, exclude=()):
    return sum(p.stat().st_size for p in files_of(folder, exclude))


def output(**kv):
    target = os.environ.get('GITHUB_OUTPUT')
    lines = ''.join(f'{k}={v}\n' for k, v in kv.items())
    if target:
        with open(target, 'a', encoding='utf-8') as f:
            f.write(lines)
    print(lines, end='')


def pipe(cmd):
    subprocess.run(['bash', '-o', 'pipefail', '-c', cmd], check=True)


def unpack(name, folder, matched=''):
    blob = store() / f'{name}.age'
    (store() / f'{name}.matched').write_text(matched if blob.is_file() else '', encoding='utf-8')
    if not blob.is_file():
        print(f'{name}: 캐시 없음')
        return
    key = key_file()
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        pipe(f'age -d -i "{key}" "{blob}" | zstd -dc | tar -x --no-same-owner -C "{folder}" -f -')
    finally:
        key.unlink(missing_ok=True)
        blob.unlink(missing_ok=True)
    print(f'{name}: {folder} 에 풂({folder_bytes(folder) >> 20}MB)')


def pack(name, folder, prefix, max_mb=0, exclude=()):
    mark = store() / f'{name}.matched'
    matched = mark.read_text(encoding='utf-8') if mark.is_file() else ''
    digest = content_hash(folder, exclude)
    if digest is None:
        print(f'{name}: {folder} 가 비어 저장하지 않음')
        return output(save='false', key='')
    key = f'{prefix}-{digest}'
    if key == matched:
        print(f'{name}: 되살린 묶음과 내용이 같아 저장하지 않음')
        return output(save='false', key=key)
    size = folder_bytes(folder, exclude)
    if max_mb and size > max_mb << 20:
        print(f'::warning::{name}: {size >> 20}MB 가 한도 {max_mb}MB 를 넘어 저장하지 않음')
        return output(save='false', key=key)
    key_path = key_file()
    blob = store() / f'{name}.age'
    try:
        recipient = subprocess.run(['age-keygen', '-y', str(key_path)], capture_output=True, text=True,
                                   check=True).stdout.strip()
    finally:
        key_path.unlink(missing_ok=True)
    skip = ''.join(f' --exclude="./{x}"' for x in exclude)
    pipe(f'tar -C "{folder}"{skip} -cf - . | zstd -T0 -3 -q -c | age -r "{recipient}" -o "{blob}"')
    print(f'{name}: {size >> 20}MB → 암호화 {blob.stat().st_size >> 20}MB, 키 {key}')
    output(save='true', key=key)


def prune(folder, since):
    """folder 바로 아래 칸 가운데 since 파일보다 오래된 것(이 잡에서 쓰지 않은 것)을 지운다. 묶음이 실행마다 쌓이지 않게.
    dq4buildcache 는 칸을 쓸 때 mtime 을 새로 하고, tar 로 되살린 칸은 저장 때의 mtime 을 지닌다."""
    limit = Path(since).stat().st_mtime
    gone = 0
    for entry in Path(folder).iterdir() if Path(folder).is_dir() else []:
        if entry.stat().st_mtime < limit:
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
            gone += 1
    print(f'{folder}: 이 잡에서 쓰지 않은 칸 {gone}개 지움')


SLOT_PREFIX = re.compile(r'guard-unit-[\w.~-]+')


def slots(file, count):
    """unit-cache 의 자리 출력 줄. 접두어는 단위 이름 꼴(쉼표·공백 없음), 폴더는 줄바꿈 없는 경로만 받는다."""
    items = json.loads(Path(file).read_text(encoding='utf-8')) if Path(file).is_file() else []
    if len(items) > count:
        raise SystemExit(f'자리 {len(items)}개가 {count}개를 넘음')
    lines = []
    for i in range(count):
        s = items[i] if i < len(items) else {'prefix': '', 'dir': ''}
        if s['prefix'] and (not SLOT_PREFIX.fullmatch(s['prefix']) or not s['dir'] or re.search(r'[\r\n]', s['dir'])):
            raise SystemExit(f'자리 {i} 가 이상함: {s!r}')
        lines += [f'p{i}={s["prefix"]}', f'd{i}={s["dir"]}']
    return lines


def label(tool, args):
    stem = Path(tool).stem.removeprefix('dq4')
    sub = args[0] if args and not args[0].startswith('-') else ''
    name = f'{stem}-{sub}' if sub else stem
    return name if name in SHIP_LABELS else 'other'


FINAL_ROMS = ('dq4-ch1-full.sfc', 'dq4-ch1-sound.sfc', 'dq4-ch1.sfc')
MANIFEST = '.prebuilt.json'
# 빌드가 읽는 롬. 미리 만든 빌드는 이 롬들이 같을 때만 쓴다
BUILD_ROMS = ('dq5.sfc', 'dq4.nes')


def head_commit():
    return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                          check=True).stdout.strip()


def rom_digests():
    out = {}
    for name in BUILD_ROMS:
        f = ROOT / 'rom' / name
        if f.is_file():
            with f.open('rb') as fh:
                out[name] = hashlib.file_digest(fh, 'sha256').hexdigest()
    return out


def ship_build(out, chunks, extra):
    """dq4build.main 을 이 프로세스에서 돌리며 단계마다 걸린 시간을 찍고, dq4buildcache.run 이 쓴 칸을 단계별로
    복사하고, 미리 만든 빌드 표시(out/.prebuilt.json: 커밋·인자·롬 해시)를 남긴다."""
    sys.path.insert(0, str(DQ4_TOOLS))
    import dq4buildcache
    import dq4build
    used, lock = [], threading.Lock()
    original = dq4buildcache.run

    def run(tool, *args, **kw):
        strs = [str(a) for a in args]
        name = label(tool, strs)
        key = None
        if dq4buildcache.cache_dir() is not None:
            key, _ = dq4buildcache._key(Path(tool).resolve(), strs)
        hit = bool(key) and (dq4buildcache.cache_dir() / key).is_dir()
        t0 = time.monotonic()
        result = original(tool, *args, **kw)
        print(f'[stage] {Path(tool).stem} {strs[0] if strs and not strs[0].startswith("-") else ""} '
              f'{time.monotonic() - t0:.1f}s {"hit" if hit else "miss"}', flush=True)
        if key:
            with lock:
                used.append((name, key))
        return result

    def timed(cmd, *args, **kw):
        t0 = time.monotonic()
        try:
            return subprocess.run(cmd, *args, **kw)
        finally:
            print(f'[stage] {Path(str(cmd[1])).stem} {time.monotonic() - t0:.1f}s', flush=True)
    dq4buildcache.run = run
    dq4build.subprocess = types.SimpleNamespace(run=timed, DEVNULL=subprocess.DEVNULL)
    sys.argv = ['dq4build.py', '--out', str(out), *extra]
    t0 = time.monotonic()
    try:
        dq4build.main()
    finally:
        dq4buildcache.run = original
        dq4build.subprocess = subprocess
    print(f'[stage] total {time.monotonic() - t0:.1f}s', flush=True)
    rom = next(n for n in FINAL_ROMS if (Path(out) / n).is_file())
    (Path(out) / MANIFEST).write_text(json.dumps({'commit': head_commit(), 'args': list(extra), 'rom': rom,
                                                  'roms': rom_digests()}), encoding='utf-8')
    cache = dq4buildcache.cache_dir()
    if cache is None:
        return
    shutil.rmtree(chunks, ignore_errors=True)
    for name, key in used:
        if (cache / key).is_dir():
            shutil.copytree(cache / key, Path(chunks) / name / key, dirs_exist_ok=True)
    print('빌드 단계 칸: ' + ', '.join(f'{n}={k[:12]}' for n, k in used))


def prebuilt_dir(extra):
    """DQ4_PREBUILT(폴더 목록, os.pathsep) 가운데 이 커밋·롬으로 dq4build 인자 extra 의 ship-build 가 만든 폴더. 없으면 None."""
    want = {'commit': head_commit(), 'args': list(extra), 'roms': rom_digests()}
    for d in filter(None, os.environ.get('DQ4_PREBUILT', '').split(os.pathsep)):
        try:
            got = json.loads((Path(d) / MANIFEST).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if {k: got.get(k) for k in want} == want:
            return Path(d), got
    return None


def same_file(a, b):
    if not b.is_file() or b.is_symlink() or a.stat().st_size != b.stat().st_size:
        return False
    with a.open('rb') as fa, b.open('rb') as fb:
        return hashlib.file_digest(fa, 'sha256').digest() == hashlib.file_digest(fb, 'sha256').digest()


def sync_tree(src, out):
    """out 을 src(MANIFEST 뺌)와 같은 파일들로 맞춘다. 내용이 같은 파일은 건드리지 않고, 다른 파일은 임시 파일에 써서
    os.replace 로 바꾸며, src 에 없는 것은 지운다. 이미 같으면 아무것도 쓰지 않아, 같은 빌드를 읽는 다른 검사와 함께
    불러도 그 검사가 반쯤 쓴 파일이나 빈 폴더를 보지 않는다(guards.run_many 가 이것에 기대어 함께 돌린다)."""
    src, out = Path(src), Path(out)
    want = {f.relative_to(src) for f in files_of(src)} - {Path(MANIFEST)}
    for rel in sorted(want):
        dst = out / rel
        if same_file(src / rel, dst):
            continue
        for parent in [*reversed(rel.parents)][1:]:
            if (out / parent).exists() and not (out / parent).is_dir():
                (out / parent).unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        tmp = dst.with_name(f'.{dst.name}.prebuilt-tmp')
        shutil.copy2(src / rel, tmp)
        os.replace(tmp, dst)
    dirs = {d for w in want for d in w.parents}
    if out.is_dir():
        for p in sorted(out.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            rel = p.relative_to(out)
            if p.is_dir() and not p.is_symlink():
                if rel not in dirs:
                    shutil.rmtree(p)
            elif rel not in want:
                p.unlink()


def prebuilt(out, extra):
    """dq4build.py --out OUT [인자] 대신. DQ4_PREBUILT 가운데 같은 커밋·인자·롬으로 ship-build 가 만든 폴더가 있으면 OUT 을
    그것과 같게 맞추고(sync_tree) dq4build 와 같은 끝 줄을 찍는다. 없으면 dq4build.py 를 그대로 돌린다."""
    found = prebuilt_dir(extra)
    if found:
        d, got = found
        out = Path(out)
        if out.resolve() != d.resolve():
            sync_tree(d, out)
        rom = out / got['rom']
        print(f'[prebuilt] {d} → {out}', file=sys.stderr)
        print(f'{rom} sha1={hashlib.sha1(rom.read_bytes()).hexdigest()}')
        return 0
    print('[prebuilt] 맞는 미리 만든 빌드가 없어 dq4build.py 를 돌림', file=sys.stderr)
    return subprocess.run([sys.executable, str(DQ4_TOOLS / 'dq4build.py'), '--out', str(out), *extra]).returncode


DIGEST_FORMAT = 'dq4-build-digest/1'
# 빌드 폴더 맨 위 이름 → 그것을 쓰는 빌드 단계(dq4build.build 차례). 대조 표를 단계 차례로 찍는다
STAGE_OF = (('titlelayers', ('title',)), ('chapter1 messages', ('messages.json',)),
            ('titlelayerpatch', ('title.sfc', 'title.ips', 'title.json')),
            ('overture build', ('overture.sfc', 'overture.ips', 'overture.json', 'overture.txt')),
            ('menupatch build', ('menu.sfc', 'menu.ips')), ('chapter1 build', ('dq4-ch1.sfc', 'dq4-ch1.ips')),
            ('soundset·sparfx', ('dq4-ch1-sound.sfc', 'dq4-ch1-sound.ips', 'dq4-ch1-sound.json')),
            ('people', ('leader', 'dq4-ch1-full.sfc')), ('ledger', ('ledger.json',)))
# 견줄 때 「무캐시 빌드」 쪽 종류. 나머지(cached, shard-k)는 모두 이것과 같아야 한다
COLD = 'cold'


def digest(folder, variant, kind):
    """빌드 폴더의 파일마다 SHA-256. 미리 만든 빌드 표시(MANIFEST)는 뺀다(롬 잡과 무캐시 잡이 같은 커밋이라 같지만,
    빌드 결과가 아니다)."""
    folder = Path(folder)
    files = {}
    for f in files_of(folder):
        rel = f.relative_to(folder).as_posix()
        if rel == MANIFEST:
            continue
        with f.open('rb') as fh:
            files[rel] = hashlib.file_digest(fh, 'sha256').hexdigest()
    return {'format': DIGEST_FORMAT, 'variant': variant, 'kind': kind, 'commit': head_commit(), 'files': files}


def load_digests(folder):
    """folder 아래 digest JSON 들(DIGEST_FORMAT)."""
    out = []
    for f in sorted(Path(folder).rglob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('format') == DIGEST_FORMAT:
            out.append(data)
    return out


def stage_name(rel):
    top = rel.split('/')[0]
    return next((name for name, tops in STAGE_OF if top in tops), '기타')


def stage_hashes(files):
    """{단계: 그 단계 파일들(경로·해시)을 묶은 해시}."""
    groups = {}
    for rel in sorted(files):
        groups.setdefault(stage_name(rel), []).append(f'{rel}\0{files[rel]}')
    return {k: hashlib.sha256('\n'.join(v).encode()).hexdigest() for k, v in groups.items()}


def verify_build(digests, variants=('ch1', 'ch2', 'ch3'), need_cached=True):
    """(Markdown, 같은가). 변형마다 무캐시 빌드가 하나 있어야 하고, 캐시 빌드(need_cached 면 꼭)와 조각이 받은 것은 모두
    그것과 파일 목록·바이트가 같아야 한다. 커밋도 모두 같아야 한다."""
    lines, ok = ['## 캐시 빌드와 무캐시 빌드 대조', ''], True
    commits = {d['commit'] for d in digests}
    if len(commits) > 1:
        lines.append(f'- **커밋이 서로 다름**: {sorted(commits)}')
        ok = False
    for v in variants:
        mine = [d for d in digests if d['variant'] == v]
        cold = [d for d in mine if d['kind'] == COLD]
        others = [d for d in mine if d['kind'] != COLD]
        if len(cold) != 1:
            lines.append(f'- {v}: **무캐시 빌드 결과가 {len(cold)}개**(하나여야 함)')
            ok = False
            continue
        if need_cached and not any(d['kind'] == 'cached' for d in others):
            lines.append(f'- {v}: **캐시 빌드 결과가 없음**')
            ok = False
        ref = cold[0]['files']
        bad = [d for d in others if d['files'] != ref]
        kinds = sorted({d['kind'] for d in others})
        if not bad:
            rom = next((n for n in FINAL_ROMS if n in ref), None)
            lines.append(f'- {v}: 같음(파일 {len(ref)}개, {rom} SHA-256 `{ref.get(rom, "-")[:16]}`, '
                         f'견준 것 {", ".join(kinds) or "-"})')
            continue
        ok = False
        lines.append(f'- {v}: **캐시가 무캐시 빌드와 다른 롬을 냈다 — 캐시 키에 빠진 입력**(다른 것 '
                     f'{", ".join(sorted({d["kind"] for d in bad}))})')
        lines += ['', f'| 단계 | 무캐시 | ' + ' | '.join(d['kind'] for d in bad) + ' |',
                  '| --- | --- |' + ' --- |' * len(bad)]
        cold_st = stage_hashes(ref)
        bad_st = [stage_hashes(d['files']) for d in bad]
        order = [name for name, _ in STAGE_OF] + ['기타']
        for name in order:
            if name not in cold_st and not any(name in b for b in bad_st):
                continue
            cells = []
            for b in bad_st:
                got = b.get(name)
                cells.append('같음' if got == cold_st.get(name) else f'**{(got or "없음")[:12]}**')
            lines.append(f'| {name} | `{cold_st.get(name, "없음")[:12]}` | ' + ' | '.join(cells) + ' |')
        for d in bad:
            diff = sorted(k for k in set(ref) | set(d['files']) if ref.get(k) != d['files'].get(k))
            lines += ['', f'{d["kind"]} 에서 다른 파일({len(diff)}개): ' + ', '.join(f'`{k}`' for k in diff[:20])
                      + (' …' if len(diff) > 20 else '')]
        lines.append('')
    return '\n'.join(lines) + '\n', ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('unpack')
    p.add_argument('--name', required=True)
    p.add_argument('--dir', required=True)
    p.add_argument('--matched', default='')
    p = sub.add_parser('pack')
    p.add_argument('--name', required=True)
    p.add_argument('--dir', required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--max-mb', type=int, default=0)
    p.add_argument('--exclude', default='', help='묶지 않을 맨 위 이름(쉼표)')
    p = sub.add_parser('prune')
    p.add_argument('--dir', required=True)
    p.add_argument('--since', required=True)
    p = sub.add_parser('ship-build')
    p.add_argument('--out', required=True)
    p.add_argument('--chunks', required=True)
    p = sub.add_parser('prebuilt')
    p.add_argument('--out', required=True)
    p = sub.add_parser('slots')
    p.add_argument('--file', required=True)
    p.add_argument('--count', type=int, required=True)
    p = sub.add_parser('digest')
    p.add_argument('--dir', required=True)
    p.add_argument('--variant', required=True)
    p.add_argument('--kind', required=True, help=f'{COLD}(무캐시 빌드)·cached(rom 잡)·shard-k(조각이 받은 것)')
    p.add_argument('--out', required=True)
    p = sub.add_parser('verify-build')
    p.add_argument('folder')
    a, extra = ap.parse_known_args()
    if a.cmd not in ('ship-build', 'prebuilt') and extra:
        ap.error(f'모르는 인자 {extra}')
    if not re.fullmatch(r'[\w.-]+', getattr(a, 'name', 'x')):
        ap.error('--name 은 글자·숫자·.-_ 만')
    if a.cmd == 'unpack':
        unpack(a.name, a.dir, a.matched)
    elif a.cmd == 'pack':
        pack(a.name, a.dir, a.prefix, a.max_mb, tuple(x for x in a.exclude.split(',') if x))
    elif a.cmd == 'prune':
        prune(a.dir, a.since)
    elif a.cmd == 'prebuilt':
        sys.exit(prebuilt(a.out, extra))
    elif a.cmd == 'slots':
        print('\n'.join(slots(a.file, a.count)))
    elif a.cmd == 'digest':
        if not any(Path(a.dir, n).is_file() for n in FINAL_ROMS):
            raise SystemExit(f'::error::{a.dir} 에 빌드한 롬이 없음')
        doc = digest(a.dir, a.variant, a.kind)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        print(f'{a.dir}: 파일 {len(doc["files"])}개 → {a.out}')
    elif a.cmd == 'verify-build':
        text, ok = verify_build(load_digests(a.folder))
        print(text, end='')
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as f:
                f.write(text)
        sys.exit(0 if ok else 1)
    else:
        ship_build(a.out, a.chunks, extra)


if __name__ == '__main__':
    main()
