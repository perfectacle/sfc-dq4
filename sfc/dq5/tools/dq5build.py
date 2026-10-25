"""DQ5(SFC) 패치 빌더. 원래 롬과 쓰기 도구들의 바이트 패치 목록(dq5patch/1 JSON)을 받아 겹침을 검사하고,
롬을 늘려 써 넣은 뒤 머리 체크섬을 고치고 IPS 를 낸다. 입력 형식과 빈 자리 지도는 sfc/dq5/docs/dq5-build-format.md.

결과 롬·IPS 는 work/ 아래에만 쓴다(커밋하지 않는다).

  build    패치 목록 여럿 → 롬(-o)과 IPS(--ips). --size 로 롬 크기(MB), 목록의 rom_size 중 큰 값이 우선.
           --fill-free XX 는 아무 목록도 쓰지 않은 빈 자리를 XX 로 채운다(빈 자리 지도를 시험할 때)
  check    패치 목록만 검사(겹침, orig, 범위)
  free     원래 롬의 빈 자리 지도와 늘린 뒤 새로 생기는 뱅크
  fromrom  다른 도구가 만든 롬 전체를 원래 롬(같은 크기로 늘린 것)과 견주어 패치 목록으로 바꾼다

사용:
  python sfc/dq5/tools/dq5build.py rom/dq5.sfc build a.dq5patch.json b.dq5patch.json --size 4 \\
      -o work/build/dq5kr.sfc --ips work/build/dq5kr.ips
  python sfc/dq5/tools/dq5build.py rom/dq5.sfc fromrom work/hangul/dq5-retree.sfc --name retree -o work/build/retree.dq5patch.json
"""
import argparse
import json
import os
import sys

from kr_patch import ips

sys.path.insert(0, os.path.dirname(__file__))
from dq5hangul import HEADER, checksum, expand  # noqa: E402

FORMAT = 'dq5patch/1'
BANK = 0x8000
ORIGINAL_SIZE = 0x180000
# 머리(7FB0~7FFF)는 빌더가 고친다. 패치 목록은 쓸 수 없다.
HEADER_RANGE = (0x7FB0, 0x8000)
# 뱅크 끝 0 의 첫 바이트를 읽는 곳이 있다(2B:C2C7 이 2F:FF86 을 소리 자료로 보냄). 그만큼 띄우고 16바이트로 맞춘다.
FREE_MARGIN = 16
FREE_MIN = 32
# 3MB 롬은 뱅크 60~ 이 40~ 을 되풀이한다. 4MB 롬의 파일 3F0000~ 은 뱅크 FE·FF 로만 보인다(7E·7F 는 WRAM).
REACHABLE = {2: 0x200000, 3: 0x300000, 4: 0x400000}


class PatchError(Exception):
    pass


def free_ranges(data):
    """원래 롬 뱅크 01~2F 끝의 0 줄(빈 자리)을 (파일 위치, 크기) 로."""
    out = []
    for b in range(1, ORIGINAL_SIZE // BANK):
        end = (b + 1) * BANK
        i = end
        while i > b * BANK and data[i - 1] == 0:
            i -= 1
        start = (i + FREE_MARGIN + 15) & ~15
        if end - start >= FREE_MIN:
            out.append((start, end - start))
    return out


def new_ranges(mb):
    """늘린 롬에서 새로 생겨 CPU 로 보이는 자리. 뱅크마다 첫 8바이트는 표지."""
    return [(o, BANK) for o in range(ORIGINAL_SIZE, REACHABLE[mb], BANK)]


def cpu(off):
    b = off // BANK
    return f'{b | 0x80 if b >= 0x7E else b:02X}:{0x8000 + off % BANK:04X}'


def parse_at(at):
    """'BB:AAAA'(LoROM CPU 주소, 뱅크 80~ 는 거울) 나 '0x…'(파일 위치) → (파일 위치, CPU 주소였는지)."""
    if at.lower().startswith('0x'):
        return int(at, 16), False
    bank, _, addr = at.partition(':')
    raw, a = int(bank, 16), int(addr, 16)
    b = raw & 0x7F
    if not addr or a < 0x8000 or a > 0xFFFF or raw in (0x7E, 0x7F) or raw > 0xFF:
        raise PatchError(f'주소 {at!r}: BB:AAAA(뱅크 00~7D·80~FF, AAAA 8000~FFFF) 나 0x 파일 위치만 씀')
    return b * BANK + (a - 0x8000), True


def unhex(s):
    return bytes.fromhex(s.replace(' ', ''))


def load(path):
    """패치 목록 하나 → (이름, 최소 크기 MB, [(파일 위치, 바이트, orig, 설명)])."""
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    if doc.get('format') != FORMAT:
        raise PatchError(f'{path}: format 이 {FORMAT!r} 이 아님')
    name = doc.get('name') or os.path.basename(path)
    writes = []
    for k, w in enumerate(doc.get('writes', [])):
        where = f'{name} writes[{k}]'
        try:
            off, is_cpu = parse_at(w['at'])
        except (KeyError, ValueError) as e:
            raise PatchError(f'{where}: at 이 없거나 틀림 ({e})') from None
        if ('hex' in w) == ('file' in w):
            raise PatchError(f'{where}: hex 와 file 가운데 하나만')
        if 'hex' in w:
            data = unhex(w['hex'])
        else:
            with open(os.path.join(os.path.dirname(path), w['file']), 'rb') as f:
                data = f.read()
        if not data:
            raise PatchError(f'{where}: 빈 쓰기')
        if is_cpu and off // BANK != (off + len(data) - 1) // BANK:
            raise PatchError(f'{where}: {w["at"]} 부터 {len(data)}바이트가 뱅크를 넘음(넘기려면 0x 파일 위치로)')
        orig = unhex(w['orig']) if 'orig' in w else None
        if orig is not None and len(orig) != len(data):
            raise PatchError(f'{where}: orig 길이 {len(orig)} 가 쓰는 길이 {len(data)} 와 다름')
        writes.append((off, data, orig, f'{where} {w["at"]} {w.get("note", "")}'.rstrip()))
    return name, int(doc.get('rom_size', 0)), writes


def inside(off, n, ranges):
    return any(s <= off and off + n <= s + size for s, size in ranges)


def check(original, lists, mb):
    """모든 쓰기를 모아 범위·orig·겹침을 검사한다. 고친 쓰기 목록(위치 순)을 돌려준다."""
    free = free_ranges(original)
    limit = REACHABLE[mb] if mb else ORIGINAL_SIZE
    allw = []
    for _, _, writes in lists:
        for off, data, orig, label in writes:
            end = off + len(data)
            if end > limit:
                raise PatchError(f'{label}: {cpu(off)} 이 롬 크기({mb or 1.5}MB)에서 CPU 로 보이는 자리를 넘음')
            if off < HEADER_RANGE[1] and end > HEADER_RANGE[0]:
                raise PatchError(f'{label}: 머리 00:FFB0~FFFF 는 빌더가 쓴다')
            if off < ORIGINAL_SIZE:
                if end > ORIGINAL_SIZE:
                    raise PatchError(f'{label}: 원래 롬과 늘린 자리에 걸침')
                if orig is not None and original[off:end] != orig:
                    raise PatchError(f'{label}: orig 가 원래 롬({original[off:end][:16].hex(" ")}…)과 다름')
                if orig is None and not inside(off, len(data), free):
                    raise PatchError(f'{label}: 원래 롬의 빈 자리 밖을 쓰려면 orig 가 있어야 함')
            allw.append((off, end, data, label))
    allw.sort()
    for (o1, e1, _, l1), (o2, e2, _, l2) in zip(allw, allw[1:]):
        if o2 < e1:
            raise PatchError(f'겹침 {cpu(o2)}~{cpu(min(e1, e2) - 1)}:\n  {l1}\n  {l2}')
    return allw


def build(original, lists, mb, fill=None):
    allw = check(original, lists, mb)
    d = bytearray(expand(original, mb)) if mb else bytearray(original)
    if fill is not None:
        for s, size in free_ranges(original):
            if not any(o < s + size and e > s for o, e, _, _ in allw):
                d[s:s + size] = bytes([fill]) * size
    for off, end, data, _ in allw:
        d[off:end] = data
    return bytes(checksum(d)), allw


def fromrom(original, patched, name, out):
    """patched 를 같은 크기로 늘린 원래 롬과 견주어 dq5patch/1 목록을 쓴다. 긴 쓰기는 옆 .bin 파일로."""
    mb = len(patched) // 0x100000 if len(patched) > ORIGINAL_SIZE else 0
    base = bytearray(expand(original, mb) if mb else original)
    # 머리(체크섬·크기)는 빌더가 다시 쓰므로 견주지 않는다.
    base[HEADER_RANGE[0]:HEADER_RANGE[1]] = patched[HEADER_RANGE[0]:HEADER_RANGE[1]]
    runs, i, n = [], 0, len(patched)
    while i < n:
        if base[i] == patched[i]:
            i += 1
            continue
        j = i
        # 4바이트 안쪽으로 떨어진 다른 곳은 한 쓰기로 묶는다.
        while j < n and (base[j] != patched[j] or any(base[k] != patched[k] for k in range(j, min(j + 4, n)))):
            j += 1
        while j > i and base[j - 1] == patched[j - 1]:
            j -= 1
        # 뱅크 경계에서 자른다.
        while i < j:
            k = min(j, (i // BANK + 1) * BANK)
            runs.append((i, k))
            i = k
        i = j
    stem = os.path.splitext(os.path.splitext(out)[0])[0]
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    writes = []
    for k, (s, e) in enumerate(runs):
        w = {'at': cpu(s)}
        if e - s > 1024:
            fn = f'{os.path.basename(stem)}.{k:03d}.bin'
            with open(os.path.join(os.path.dirname(out) or '.', fn), 'wb') as f:
                f.write(patched[s:e])
            w['file'] = fn
        else:
            w['hex'] = patched[s:e].hex(' ')
        if s < ORIGINAL_SIZE:
            w['orig'] = original[s:e].hex(' ')
        writes.append(w)
    doc = {'format': FORMAT, 'name': name, 'rom_size': mb, 'writes': writes}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('build', 'check', 'free', 'fromrom'))
    ap.add_argument('inputs', nargs='*')
    ap.add_argument('--size', type=int, default=0, choices=(0, 2, 3, 4))
    ap.add_argument('-o', '--out')
    ap.add_argument('--ips')
    ap.add_argument('--name')
    ap.add_argument('--fill-free', type=lambda s: int(s, 16))
    a = ap.parse_args()
    original = open(a.rom, 'rb').read()
    if len(original) != ORIGINAL_SIZE:
        print(f'원래 롬은 {ORIGINAL_SIZE:#x} 바이트여야 함(지금 {len(original):#x})', file=sys.stderr)
        return 1
    try:
        if a.cmd == 'free':
            fr = free_ranges(original)
            for s, size in fr:
                print(f'{cpu(s)}~{cpu(s + size - 1)}  {size:5d}')
            print(f'원래 롬 빈 자리 {len(fr)}곳 {sum(x for _, x in fr)}바이트')
            for mb in (2, 3, 4):
                nr = new_ranges(mb)
                where = {2: '30~3F', 3: '30~5F', 4: '30~7D, FE·FF'}[mb]
                print(f'{mb}MB: 새 뱅크 {len(nr)}개 {len(nr) * BANK // 1024}KB (뱅크 {where} 의 8000~FFFF)')
            return 0
        if a.cmd == 'fromrom':
            patched = open(a.inputs[0], 'rb').read()
            runs = fromrom(original, patched, a.name or os.path.basename(a.inputs[0]), a.out)
            print(f'쓰기 {len(runs)}개 {sum(e - s for s, e in runs)}바이트 → {a.out}')
            return 0
        lists = [load(p) for p in a.inputs]
        mb = max([a.size] + [m for _, m, _ in lists])
        if a.cmd == 'check':
            allw = check(original, lists, mb)
            print(f'목록 {len(lists)}개, 쓰기 {len(allw)}개 {sum(e - o for o, e, _, _ in allw)}바이트, 겹침 없음')
            return 0
        out, allw = build(original, lists, mb, a.fill_free)
    except PatchError as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1
    for name, _, writes in lists:
        print(f'{name}: 쓰기 {len(writes)}개 {sum(len(w[1]) for w in writes)}바이트')
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'wb') as f:
        f.write(out)
    print(f'{a.out}: {len(out):#x} 바이트, 머리 크기 {out[HEADER + 0x17]:02X}')
    if a.ips:
        p = ips.make(original, out)
        if ips.apply(original, p) != out:
            print('오류: IPS 를 다시 붙인 결과가 롬과 다름', file=sys.stderr)
            return 1
        with open(a.ips, 'wb') as f:
            f.write(p)
        print(f'{a.ips}: {len(p)} 바이트(원래 롬에 붙여 같은 롬이 됨을 확인)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
