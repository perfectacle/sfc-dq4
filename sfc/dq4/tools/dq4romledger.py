"""롬 쓰기 장부: 빌드 단계마다 바뀐 바이트 범위를 모은다. 형식은 sfc/dq4/docs/dq4-rom-ledger-format.md.

dq4build.py 가 단계 롬(title.sfc → … → dq4-ch1-full.sfc)을 만들 때마다 바로 앞 단계 롬과 견주어, 값이 바뀐 바이트를
범위로 적는다. 모듈마다 무엇을 썼는지 묻지 않고 단계 사이 차이로만 본다. 그래서 앞 단계와 같은 값을 다시 쓴 바이트는
장부에 없다.

첫 단계는 원래 롬을 타이틀 빌드와 같은 꼴로 늘린 것(뱅크 30~3F 는 원본 20~2F 의 거울, 그 뒤는 0)과 견준다.
거울 바이트는 빈 자리로 쓰므로(sfc/dq4/docs/dq4-chapter1-format.md) 거울 그대로인 바이트는 쓰지 않은 것으로 본다.
1장 빌드는 패치를 얹기 전에 거울 바이트를 0 으로 지운다. 거울 그대로이던 바이트가 0 으로 길게 이어지는 곳은 따로
cleared 로 적어, 검사가 그 자리를 뒤 단계가 쓸 빈 자리로 보게 한다.

  python sfc/dq4/tools/dq4romledger.py --dq5 rom/dq5.sfc --out work/ch1/ledger.json title=work/ch1/title.sfc …
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

FORMAT = 'dq4romledger/1'
BANK = 0x8000
ORIGINAL_SIZE = 0x180000
MIRROR_FROM = 0x100000          # 뱅크 20~2F
EXPANDED_SIZE = 0x400000
MIRROR_END = ORIGINAL_SIZE + ORIGINAL_SIZE - MIRROR_FROM   # 뱅크 30~3F 끝
BLOCK = 256
# 거울을 지운 자리로 볼 0 줄의 최소 길이. 1장 빌드의 새 자료 속 0 줄은 대부분 이보다 짧다
CLEAR_MIN = 32
# dq4build.py 가 적는 단계 이름. 자원 저장소 없이 빌드하면 sound 뒤가 빠진다
STAGES = ('title', 'overture', 'menu', 'chapter1', 'sound', 'sparfx', 'people')


def cpu(off):
    """파일 오프셋 → LoROM CPU 주소 문자열. 뱅크 7E·7F 자리(파일 3F0000~)는 FE·FF 로만 보인다."""
    b = off // BANK
    return f'{b | 0x80 if b >= 0x7E else b:02X}:{BANK + off % BANK:04X}'


def offset(text):
    """'BB:AAAA'(LoROM, 80~ 은 거울) 또는 '0x…'(파일 오프셋) → 파일 오프셋."""
    if text.lower().startswith('0x'):
        return int(text, 16)
    bank, sep, addr = text.partition(':')
    b, a = int(bank, 16), int(addr, 16) if sep else -1
    if not sep or not 0x8000 <= a <= 0xFFFF or b in (0x7E, 0x7F) or b > 0xFF:
        raise ValueError(f'주소 {text!r}: BB:AAAA(AAAA 8000~FFFF) 나 0x 파일 오프셋')
    return (b & 0x7F) * BANK + a - BANK


def expanded_original(dq5, size=EXPANDED_SIZE):
    """타이틀 빌드가 늘리는 꼴(dq4titlelayerpatch): 원래 롬 + 원본 20~2F 의 거울 + 0."""
    base = bytes(dq5) + bytes(dq5[MIRROR_FROM:ORIGINAL_SIZE])
    return base[:size] + bytes(max(0, size - len(base)))


def diff_ranges(before, after):
    """after 에서 before 와 값이 다른 바이트의 [시작, 끝) 목록. before 가 짧으면 모자란 자리는 0 으로 본다."""
    if len(after) < len(before):
        raise ValueError('뒤 단계 롬이 앞 단계보다 짧음')
    before = bytes(before) + bytes(len(after) - len(before))
    a, b = memoryview(before), memoryview(after)
    out = []
    start = None
    for blk in range(0, len(after), BLOCK):
        end = min(blk + BLOCK, len(after))
        if a[blk:end] == b[blk:end]:
            if start is not None:
                out.append((start, blk))
                start = None
            continue
        for i in range(blk, end):
            if before[i] != after[i]:
                if start is None:
                    start = i
            elif start is not None:
                out.append((start, i))
                start = None
    if start is not None:
        out.append((start, len(after)))
    return out


def merge(ranges, gap=0):
    """[시작, 끝) 목록을 gap 바이트 이하 틈은 이어 하나로."""
    out = []
    for s, e in sorted(ranges):
        if out and s - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def runs(mask):
    """참인 칸이 이어지는 [시작, 끝) 목록(numpy bool 배열)."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.view(np.int8), [0]))))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def intersect(a, b):
    """정렬된 [시작, 끝) 목록 둘의 교집합."""
    out, j = [], 0
    for s, e in a:
        while j < len(b) and b[j][1] <= s:
            j += 1
        k = j
        while k < len(b) and b[k][0] < e:
            lo, hi = max(s, b[k][0]), min(e, b[k][1])
            if lo < hi:
                out.append((lo, hi))
            k += 1
    return out


def cleared_ranges(ranges, mirror, before, after):
    """ranges 가운데 뱅크 30~3F 에서 거울을 0 으로 지운 곳의 [시작, 끝) 목록.
    지운 자리는 거울 그대로이던(before == mirror) 바이트가 뒤에 0 인 칸이 CLEAR_MIN 바이트 넘게 이어지는 곳이다.
    거울이 원래 0 인 칸도 잇는다. 새 자료 속의 0 은 짧게 끊기므로 빈 자리로 보지 않는다."""
    lo, hi = ORIGINAL_SIZE, min(MIRROR_END, len(after))
    if hi <= lo:
        return []
    b = np.frombuffer(bytes(before[lo:hi]), np.uint8)
    a = np.frombuffer(bytes(after[lo:hi]), np.uint8)
    m = np.frombuffer(bytes(mirror[lo:hi]), np.uint8)
    spans = [(lo + s, lo + e) for s, e in runs((a == 0) & (b == m)) if e - s >= CLEAR_MIN]
    return intersect(ranges, spans)


def crosses_bank(s, e):
    return s // BANK != (e - 1) // BANK


def range_doc(s, e):
    return {'off': f'{s:06X}', 'end': f'{e - 1:06X}', 'cpu': f'{cpu(s)}~{cpu(e - 1)}', 'bytes': e - s}


def range_of(doc):
    return int(doc['off'], 16), int(doc['end'], 16) + 1


def build(dq5, stages):
    """stages: [(이름, 롬 바이트)] 또는 [(이름, 롬 바이트, 파일 이름)] 단계 순서. 장부 dict.
    파일 이름은 장부와 같은 폴더의 그 단계 롬이다. 칼 효과처럼 같은 파일을 고쳐 쓰는 단계는 마지막 단계만 맞는다."""
    mirror = expanded_original(dq5, max((len(s[1]) for s in stages), default=EXPANDED_SIZE))
    before = mirror[:len(stages[0][1])] if stages else mirror
    doc = {'format': FORMAT, 'base': {'sha1': hashlib.sha1(dq5).hexdigest(), 'size': len(dq5)}, 'stages': []}
    for name, data, *file in stages:
        ranges = diff_ranges(before, data)
        padded = bytes(before) + bytes(len(data) - len(before))
        cleared = cleared_ranges(ranges, mirror, padded, data)
        doc['stages'].append({'name': name, **({'file': file[0]} if file else {}),
                              'sha1': hashlib.sha1(data).hexdigest(), 'size': len(data),
                              'bytes': sum(e - s for s, e in ranges), 'ranges': [range_doc(s, e) for s, e in ranges],
                              'cleared': [range_doc(s, e) for s, e in cleared]})
        before = data
    return doc


def write(path, doc):
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def load(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('format') != FORMAT:
        raise ValueError(f'{path}: format 이 {FORMAT!r} 이 아님')
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dq5', type=Path, default=Path('rom/dq5.sfc'))
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('stages', nargs='+', help='이름=롬 경로, 단계 순서대로')
    args = ap.parse_args()
    stages = []
    for s in args.stages:
        name, _, path = s.partition('=')
        stages.append((name, Path(path).read_bytes(), Path(path).name))
    doc = build(args.dq5.read_bytes(), stages)
    write(args.out, doc)
    for st in doc['stages']:
        print(f"{st['name']}: 범위 {len(st['ranges'])}개, {st['bytes']}바이트")


if __name__ == '__main__':
    main()
