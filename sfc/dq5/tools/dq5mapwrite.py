"""DQ5(SFC) 실내 맵 레코드 쓰기. 형식은 sfc/dq5/docs/dq5-map-format.md 의 「맵 레코드」, 패치 목록은
sfc/dq5/docs/dq5-build-format.md.

맵 레코드(머리 9바이트, 배치 비트스트림, 속성 패스 셋)를 명령 단위 JSON(dq5map/1)으로 풀고, 그 JSON 을 다시
레코드 바이트로 싼다. 읽는 쪽은 게임 루틴(01:A824 비트스트림, 01:B8A8·01:B8DD 니블 리더)을 그대로 따르고,
게임이 읽고 버리는 비트(패스 머리 바이트의 아래 7비트, 끝 바이트의 아래 6비트, 맞춤 니블, 비트스트림 끝의 남은 비트)도
JSON 에 담아 원래 레코드와 바이트까지 같게 싼다.

  dump    맵 하나 → JSON(-o, 빼면 표준 출력)
  check   맵 전부(실내 346, 그룹 50 이상 18)를 풀고 다시 싸서 원래 바이트와 견준다
  patch   JSON 여럿 → 패치 목록(-o). 새 레코드를 --at(늘린 롬의 자리, 기본 30:8000) 부터 차례로 놓고
          맵 포인터(0F:8ED7 그룹 목록, 그룹 50 이상은 1F:CEB6)를 그 자리로 바꾼다. --in-place 면 원래 자리에 덮되
          원래 레코드보다 길면 거부한다

JSON 의 commands 는 ["block", n] / ["put", x, y] / ["fill", x0, y0, x1, y1] / ["end"] 이다. 위치 비트 수는
머리 bits(+6)를 따르고, 위치 = y * 폭 + x 가 그 비트에 들어가야 한다. passes 셋은 각각
{"vertical": bool, "entries": [[x, y, 칸 수, 값, 꼴]…]} 이며 꼴은 one(1칸)·short(2~17칸)·long(2~257칸)이다.

사용:
  python sfc/dq5/tools/dq5mapwrite.py rom/dq5.sfc check
  python sfc/dq5/tools/dq5mapwrite.py rom/dq5.sfc dump 17 00 -o work/map/1700.json
  python sfc/dq5/tools/dq5mapwrite.py rom/dq5.sfc patch work/map/1700.json -o work/build/map.dq5patch.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import BLOCK_BITS, GROUP_TABLE, HIGH_GROUPS, Rom, lorom, map_pointer, next_addr  # noqa: E402

FORMAT = 'dq5map/1'
HEADER = ('kind', 'width', 'height', 'outside', 'zone', 'attr', 'bits', 'background_hi', 'background_lo')
GROUPS = 0x36
HIGH_FIRST = 0x50


def all_maps(rom):
    """(BC, BD) 전부. 그룹 목록은 이어져 있어서 다음 그룹 목록 시작까지가 그 그룹의 맵이다."""
    out = []
    g = [rom.u16(GROUP_TABLE + i * 2) for i in range(GROUPS)] + [GROUP_TABLE & 0xFFFF]
    for bc in range(GROUPS):
        out += [(bc, bd) for bd in range((g[bc + 1] - g[bc]) // 3)]
    h = [rom.u16(HIGH_GROUPS + i * 2) for i in range(5)] + [HIGH_GROUPS & 0xFFFF]
    for i in range(5):
        out += [(HIGH_FIRST + i, HIGH_FIRST + bd) for bd in range((h[i + 1] - h[i]) // 3)]
    return out


def pointer_addr(rom, bc, bd):
    """맵 포인터(24비트)가 놓인 CPU 주소."""
    if bc >= HIGH_FIRST:
        return HIGH_GROUPS & 0xFF0000 | rom.u16(HIGH_GROUPS + (bc - HIGH_FIRST) * 2) + (bd - HIGH_FIRST) * 3
    return 0x0F0000 | rom.u16(GROUP_TABLE + bc * 2) + bd * 3


class BitReader:
    """MSB 먼저. 01:AC66."""

    def __init__(self, rom, addr):
        self.rom, self.a, self.pos = rom, addr, 0

    def num(self, n):
        v = 0
        for _ in range(n):
            v = v << 1 | (self.rom.u8(self.a) >> (7 - self.pos)) & 1
            self.pos += 1
            if self.pos == 8:
                self.pos, self.a = 0, next_addr(self.a)
        return v


class Passes:
    """속성 패스 셋을 게임의 니블 리더(01:B8A8·01:B8DD)와 같은 위치 q 로 읽고 쓴다.

    게임 리더의 상태 (주소, half) 를 니블 위치 q = 2*주소 + half 로 보면
      nib()  는 N[q] 와 N[q+1] 을 한 바이트로 돌려주고 q += 1 (패스 머리는 이 값의 bit7 = N[q] 의 bit3)
      byte() 는 N[q+1] 과 N[q+2] 를 돌려주고 q += 2
      값·짧은 반복 니블은 nib() & 0F 라 N[q+1] 이고 q += 1
    이다. 그래서 패스 머리 니블은 앞 패스의 끝 바이트 아래 니블과 겹칠 수 있고, 머리 다음 니블은 아무도 읽지 않는다.
    레코드는 마지막으로 읽힌 니블 N[q] 가 든 바이트까지다.
    """

    ENTRY_TOP = {'one': 0x00, 'short': 0xC0, 'long': 0x80}

    def __init__(self, nibs=None):
        self.n = nibs if nibs is not None else {}
        self.q = 0
        self.used = set()

    def get(self, i):
        self.used.add(i)
        return self.n[i]

    def set(self, i, v):
        self.used.add(i)
        self.n[i] = v


def parse(rom, addr):
    """맵 레코드 → (JSON 문서, 레코드 길이)."""
    head = [rom.u8(addr + i) for i in range(9)]
    width, bits = head[1], head[6]
    s = BitReader(rom, addr + 9)
    cmds = []
    while True:
        if not s.num(1):
            p = s.num(bits)
            cmds.append(['put', p % width, p // width])
        elif not s.num(1):
            cmds.append(['block', s.num(BLOCK_BITS)])
        elif not s.num(1):
            a, b = s.num(bits), s.num(bits)
            cmds.append(['fill', a % width, a // width, b % width, b // width])
        else:
            cmds.append(['end'])
            break
    tail_bits = (8 - s.pos) % 8
    tail = s.num(tail_bits) if tail_bits else 0
    # 01:A7B3: 비트스트림이 바이트 중간에서 끝났으면 다음 바이트부터. 위에서 남은 비트를 읽어 이미 다음 바이트다.
    base = s.a

    def nibble(i):
        a = base
        for _ in range(i // 2):
            a = next_addr(a)
        b = rom.u8(a)
        return b >> 4 if i % 2 == 0 else b & 0x0F

    st = Passes(_Lazy(nibble))
    passes = []
    for kind in (1, 2, 3):
        fi = st.q
        fresh = fi not in st.used
        v = st.get(fi)
        st.q += 1
        p = {'vertical': bool(v & 8)}
        if fresh:
            p['flag_low'] = v & 7
        entries = []
        while True:
            b = st.get(st.q + 1) << 4 | st.get(st.q + 2)
            st.q += 2
            if b & 0xC0 == 0x40:
                p['end_low'] = b & 0x3F
                # 01:B83D·01:B938: 패스 1·2 는 반 바이트에서 끝났으면 니블 하나를 더 읽어 맞춘다.
                if kind != 3 and st.q % 2:
                    st.q += 1
                break
            lo = st.get(st.q + 1) << 4 | st.get(st.q + 2)
            st.q += 2
            x, y = ((b & 0x3F) << 1) | lo >> 7, lo & 0x7F
            if b & 0x80 and b & 0x40:
                cells, form = st.get(st.q + 1) + 2, 'short'
                st.q += 1
            elif b & 0x80:
                cells, form = (st.get(st.q + 1) << 4 | st.get(st.q + 2)) + 2, 'long'
                st.q += 2
            else:
                cells, form = 1, 'one'
            entries.append([x, y, cells, st.get(st.q + 1), form])
            st.q += 1
        p['entries'] = entries
        passes.append(p)
    count = st.q // 2 + 1
    junk = [nibble(i) for i in range(count * 2) if i not in st.used]
    end = base
    for _ in range(count):
        end = next_addr(end)

    doc = {'format': FORMAT, **dict(zip(HEADER, head)), 'commands': cmds, 'stream_tail': tail, 'passes': passes,
           'junk': ''.join(f'{v:X}' for v in junk)}
    length = lorom(end) - lorom(addr)
    return doc, length


class _Lazy(dict):
    """롬에서 니블을 필요할 때 읽는 dict."""

    def __init__(self, f):
        super().__init__()
        self.f = f

    def __missing__(self, i):
        self[i] = v = self.f(i)
        return v


class BitWriter:
    def __init__(self):
        self.out, self.cur, self.pos = bytearray(), 0, 0

    def put(self, v, n):
        for i in range(n - 1, -1, -1):
            self.cur = self.cur << 1 | (v >> i) & 1
            self.pos += 1
            if self.pos == 8:
                self.out.append(self.cur)
                self.cur, self.pos = 0, 0


def encode(doc):
    """JSON 문서 → 레코드 바이트. 틀린 값은 ValueError."""
    if doc.get('format') != FORMAT:
        raise ValueError(f'format 이 {FORMAT!r} 이 아님')
    head = [doc[k] for k in HEADER]
    if any(not 0 <= v <= 0xFF for v in head):
        raise ValueError('머리 값은 0~255')
    width, height, bits = head[1], head[2], head[6]

    def pos(x, y):
        p = y * width + x
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f'위치 ({x},{y}) 가 맵 {width}x{height} 밖')
        if p >> bits:
            raise ValueError(f'위치 ({x},{y}) = {p} 가 {bits}비트에 들어가지 않음')
        return p

    w = BitWriter()
    ended = False
    for c in doc['commands']:
        if ended:
            raise ValueError('end 뒤에 명령이 있음')
        op = c[0]
        if op == 'put':
            w.put(0, 1)
            w.put(pos(c[1], c[2]), bits)
        elif op == 'block':
            if not 0 <= c[1] < 1 << BLOCK_BITS:
                raise ValueError(f'블록 번호 {c[1]} 가 11비트 밖')
            w.put(0b10, 2)
            w.put(c[1], BLOCK_BITS)
        elif op == 'fill':
            w.put(0b110, 3)
            w.put(pos(c[1], c[2]), bits)
            w.put(pos(c[3], c[4]), bits)
        elif op == 'end':
            w.put(0b111, 3)
            ended = True
        else:
            raise ValueError(f'모르는 명령 {op!r}')
    if not ended:
        raise ValueError('commands 가 end 로 끝나지 않음')
    if w.pos:
        w.put(doc.get('stream_tail', 0), 8 - w.pos)
    out = bytearray(head) + w.out
    if len(doc['passes']) != 3:
        raise ValueError('passes 는 셋')
    st = Passes()
    for kind, p in enumerate(doc['passes'], 1):
        v = (8 if p['vertical'] else 0) | p.get('flag_low', 0)
        if st.q in st.n:
            # 앞 끝 바이트의 아래 니블과 겹친다. 게임이 보는 bit3 만 맞춘다.
            st.n[st.q] = st.n[st.q] & 7 | v & 8
        else:
            st.set(st.q, v)
        st.q += 1
        for x, y, cells, val, form in p['entries']:
            if not (0 <= x < 0x80 and 0 <= y < 0x80 and 0 <= val < 0x10):
                raise ValueError(f'패스 {kind} 엔트리 ({x},{y}) 값 {val} 이 범위 밖')
            b0, b1 = Passes.ENTRY_TOP[form] | x >> 1, (x & 1) << 7 | y
            for byte in (b0, b1):
                st.set(st.q + 1, byte >> 4)
                st.set(st.q + 2, byte & 0x0F)
                st.q += 2
            if form == 'one' and cells != 1:
                raise ValueError(f'패스 {kind} 엔트리 ({x},{y}): one 은 1칸')
            if form == 'short':
                if not 2 <= cells <= 17:
                    raise ValueError(f'패스 {kind} 엔트리 ({x},{y}): short 는 2~17칸')
                st.set(st.q + 1, cells - 2)
                st.q += 1
            elif form == 'long':
                if not 2 <= cells <= 257:
                    raise ValueError(f'패스 {kind} 엔트리 ({x},{y}): long 은 2~257칸')
                st.set(st.q + 1, (cells - 2) >> 4)
                st.set(st.q + 2, (cells - 2) & 0x0F)
                st.q += 2
            st.set(st.q + 1, val)
            st.q += 1
        e = 0x40 | p.get('end_low', 0)
        st.set(st.q + 1, e >> 4)
        st.set(st.q + 2, e & 0x0F)
        st.q += 2
        if kind != 3 and st.q % 2:
            st.q += 1
    count = st.q // 2 + 1
    junk = iter(int(c, 16) for c in doc.get('junk', ''))
    nib = [st.n[i] if i in st.n else next(junk, 0) for i in range(count * 2)]
    out += bytes(nib[i] << 4 | nib[i + 1] for i in range(0, len(nib), 2))
    return bytes(out)


def entries_for(doc):
    """속성 패스의 엔트리를 맵 안 칸 수로 검사(반복이 맵을 넘으면 게임은 버퍼 밖을 쓴다)."""
    bad = []
    width, height = doc['width'], doc['height']
    for kind, p in enumerate(doc['passes'], 1):
        for x, y, cells, _, _ in p['entries']:
            last = (y + cells - 1, x) if p['vertical'] else (y, x + cells - 1)
            if last[0] >= height or (not p['vertical'] and last[1] >= width):
                bad.append(f'패스 {kind} ({x},{y}) {cells}칸이 맵 밖까지')
    return bad


def dumps(doc):
    """명령·엔트리를 한 줄에 하나씩 둔 JSON."""
    j = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    lines = ['{']
    for k, v in doc.items():
        if k in ('commands', 'placements'):
            body = ',\n'.join(f'  {j(c)}' for c in v)
            lines.append(f' "{k}": [\n{body}\n ],')
        elif k == 'passes':
            ps = []
            for p in v:
                head = ', '.join(f'{j(a)}: {j(b)}' for a, b in p.items() if a != 'entries')
                ents = ',\n'.join(f'    {j(e)}' for e in p['entries'])
                ps.append(f'  {{{head}, "entries": [\n{ents}\n  ]}}' if ents else f'  {{{head}, "entries": []}}')
            lines.append(' "passes": [\n' + ',\n'.join(ps) + '\n ],')
        else:
            lines.append(f' {j(k)}: {j(v)},')
    lines[-1] = lines[-1].rstrip(',')
    return '\n'.join(lines) + '\n}'


def cpu(off):
    return f'{off // 0x8000:02X}:{0x8000 + off % 0x8000:04X}'


def to_cpu(off):
    return (off // 0x8000) << 16 | 0x8000 + off % 0x8000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'check', 'patch'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('-o', '--out')
    ap.add_argument('--at', default='30:8000')
    ap.add_argument('--in-place', action='store_true')
    ap.add_argument('--name', default='maps')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    rom = Rom(data)
    if a.cmd == 'check':
        bad = 0
        maps = all_maps(rom)
        total = 0
        for bc, bd in maps:
            addr = map_pointer(rom, bc, bd)
            doc, length = parse(rom, addr)
            o = lorom(addr)
            enc = encode(doc)
            total += length
            if enc != data[o:o + length]:
                bad += 1
                print(f'{bc:02X}/{bd:02X}: 다시 싼 {len(enc)}바이트가 원래 {length}바이트와 다름')
        print(f'맵 {len(maps)}개 {total}바이트, 다른 맵 {bad}개')
        return 1 if bad else 0
    if a.cmd == 'dump':
        bc, bd = int(a.args[0], 16), int(a.args[1], 16)
        doc, length = parse(rom, map_pointer(rom, bc, bd))
        doc = {'format': doc['format'], 'map': f'{bc:02X}/{bd:02X}', **{k: v for k, v in doc.items() if k != 'format'}}
        s = dumps(doc)
        if a.out:
            os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
            open(a.out, 'w', encoding='utf-8').write(s + '\n')
        else:
            print(s)
        return 0
    bank, _, low = a.at.partition(':')
    at = lorom(int(bank, 16) << 16 | int(low, 16))
    writes = []
    for path in a.args:
        doc = json.load(open(path, encoding='utf-8'))
        bc, bd = (int(v, 16) for v in doc['map'].split('/'))
        try:
            rec = encode(doc)
        except ValueError as e:
            print(f'오류: {path}: {e}', file=sys.stderr)
            return 1
        for line in entries_for(doc):
            print(f'경고: {path}: {line}', file=sys.stderr)
        old = lorom(map_pointer(rom, bc, bd))
        _, old_len = parse(rom, map_pointer(rom, bc, bd))
        label = f'map {bc:02X}/{bd:02X}'
        if a.in_place:
            if len(rec) > old_len:
                print(f'오류: {path}: 새 레코드 {len(rec)}바이트가 원래 {old_len}바이트보다 김', file=sys.stderr)
                return 1
            # 20/03·31/04·31/05 는 마지막 바이트가 다음 맵의 첫 바이트다.
            last = old + len(rec) - 1
            starts = {lorom(map_pointer(rom, *m)) for m in all_maps(rom)}
            if last in starts and rec[-1] != data[last]:
                print(f'오류: {path}: 마지막 바이트 {cpu(last)} 는 다음 맵의 머리라 바꿀 수 없음', file=sys.stderr)
                return 1
            if rec != data[old:old + len(rec)]:
                writes.append({'at': cpu(old), 'hex': rec.hex(' '), 'orig': data[old:old + len(rec)].hex(' '),
                               'note': label})
            continue
        # 레코드는 뱅크를 넘어 읽혀도 되지만(next_addr), 빌더의 CPU 주소 쓰기는 한 뱅크 안이라 파일 위치로 쓴다.
        writes.append({'at': f'0x{at:X}', 'hex': rec.hex(' '), 'note': label})
        p = lorom(pointer_addr(rom, bc, bd))
        new = to_cpu(at).to_bytes(3, 'little')
        writes.append({'at': cpu(p), 'hex': new.hex(' '), 'orig': data[p:p + 3].hex(' '), 'note': f'{label} 포인터'})
        at += len(rec)
    doc = {'format': 'dq5patch/1', 'name': a.name, 'writes': writes}
    if not a.in_place:
        doc['rom_size'] = 4 if at > 0x300000 else 3 if at > 0x200000 else 2
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'맵 {len(a.args)}개, 쓰기 {len(writes)}개 → {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
