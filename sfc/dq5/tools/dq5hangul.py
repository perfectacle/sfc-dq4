"""DQ5(SFC) 한글 넣기 실현성 실험용 롬 만들기. 결과는 sfc/dq5/docs/dq5-text-format.md 의 「한글 넣기 준비」.

원본 롬은 바꾸지 않고, 실험용 롬을 work/ 아래에 쓴다(커밋하지 않는다).

  expand      롬을 SIZE(2·3·4MB)로 늘리고 머리 체크섬을 고친다. 늘린 자리 뱅크마다 첫 16바이트에 표지(「DQ5X」+뱅크)를 쓴다
  retree      expand 한 2MB 롬에서 보행 모드 메시지 3,200개를 새로 만든 허프만 트리로 다시 부호화해 뱅크 30~ 에 두고,
              트리 표와 디코더(24:9E02 를 그대로 옮긴 것)도 뱅크 30 에 둔다. 폰트 묶음 표를 늘려 글자 3DB·3DC(「한」「글」)를
              더하고 메시지 129 를 {1006}한글{1001} 로 바꾼다

고친 곳(retree):
  24:9E02  JSL 30:8000 / RTS            디코더를 뱅크 30 의 사본으로(사본은 PHK/PLB 로 데이터 뱅크 30 을 쓰고 RTL 로 끝남)
  24:9E07  JSR 8C8D / LDA $F2 / ORA #$20 / STA $F2 / RTS
                                        비운 디코더 자리에 둔 보행 모드 전용 색인 풀기. 색인은 21비트라 뱅크 1F 까지만
                                        가리키므로 뱅크에 20 을 OR 한다. 24:8C8D 는 전투 메시지(24:8C60)도 부르므로 그 안은 고치지 않는다
  24:8BD7  JSR 8C8D → JSR 9E07
  24:AF1E  새 색인(16개마다 3바이트)
  24:A63C·A660·A6C2·A673  폰트 묶음 표 피연산자 → 새 표

사용:
  python sfc/dq5/tools/dq5hangul.py rom/dq5.sfc expand --size 2 -o work/hangul/dq5-2m.sfc
  python sfc/dq5/tools/dq5hangul.py rom/dq5.sfc retree -o work/hangul/dq5-retree.sfc
"""
import argparse
import heapq
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5text import ENDS, FONT_GROUPS, FONT_TABLE_OPERANDS, GLYPHS, INDEX, font_groups, message  # noqa: E402

HEADER = 0x7FC0
DECODER = 0x249E02
DECODER_END = 0x249E47
NODES_1_OPERAND, NODES_0_OPERAND, MASK_OPERAND, ROOT_OPERAND = 0x249E1D, 0x249E22, 0x249E16, 0x249E0D
WALK_INDEX_CALL = 0x248BD7
WALK_INDEX_STUB = 0x249E07
MESSAGES = 3200
NEW_BANK = 0x30
# 11×13 글자 그림. '#' 가 점.
NEW_GLYPHS = {
    '한': ('...#.....#.', '.#####...#.', '..###....#.', '.#...#...##', '.#...#...#.', '..###....#.', '.........#.',
           '..#......#.', '..#........', '..#........', '..#######..', '...........', '...........'),
    '글': ('.#######...', '.......#...', '.......#...', '.......#...', '...........', '###########', '...........',
           '.#######...', '.......#...', '.#######...', '.#.........', '.#######...', '...........'),
}


def checksum(data):
    """머리 7FDC~7FDF(보수·합)를 고친다. 2의 거듭제곱이 아닌 크기는 뒤쪽을 거울처럼 되풀이해 더한다(SNES 관례)."""
    d = bytearray(data)
    d[HEADER + 0x1C:HEADER + 0x20] = b'\xff\xff\x00\x00'
    n = len(d)
    p = 1
    while p * 2 <= n:
        p *= 2
    total = sum(d[:p])
    if n > p:
        rest = d[p:]
        total += sum(rest) * (p // len(rest))
    s = total & 0xFFFF
    d[HEADER + 0x1C:HEADER + 0x1E] = (s ^ 0xFFFF).to_bytes(2, 'little')
    d[HEADER + 0x1E:HEADER + 0x20] = s.to_bytes(2, 'little')
    return d


def expand(data, mb):
    size = mb * 0x100000
    d = bytearray(data) + bytes(size - len(data))
    for off in range(len(data), size, 0x8000):
        d[off:off + 8] = b'DQ5X' + (off // 0x8000).to_bytes(4, 'little')
    d[HEADER + 0x17] = {2: 0x0B, 3: 0x0C, 4: 0x0C}[mb]
    return checksum(d)


def build_tree(freq):
    """(잎 코드 → 비트 문자열, 노드 목록[(1쪽, 0쪽)], 뿌리 번호). 노드 값은 잎이면 8000|코드, 아니면 노드 번호."""
    heap = [(n, i, ('leaf', c)) for i, (c, n) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    k = len(heap)
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        heapq.heappush(heap, (a[0] + b[0], k, ('node', b[2], a[2])))
        k += 1
    nodes, codes = [], {}

    def place(t, path):
        if t[0] == 'leaf':
            codes[t[1]] = path
            return 0x8000 | t[1]
        i = len(nodes)
        nodes.append(None)
        nodes[i] = (place(t[1], path + '1'), place(t[2], path + '0'))
        return i
    root = place(heap[0][2], '')
    return codes, nodes, root


def encode(codes, msgs):
    """메시지 목록을 LSB 먼저 비트열로 잇는다. (바이트, 메시지마다 시작 비트)."""
    bits, starts = [], []
    for m in msgs:
        starts.append(len(bits))
        for c in m:
            bits.extend(int(b) for b in codes[c])
    out = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i >> 3] |= 1 << (i & 7)
    return out, starts


def cpu_to_bytes(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def glyph_bits(rows):
    w, h = len(rows[0]), len(rows)
    out = bytearray((w * h + 7) // 8)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c == '#':
                i = y * w + w - 1 - x
                out[i >> 3] |= 1 << (i & 7)
    return out


def retree(data):
    """원본 롬 바이트 → 실험용 2MB 롬과 설명 줄."""
    rom = Rom(data)
    msgs = [message(rom, m) for m in range(MESSAGES)]
    new_codes = list(range(GLYPHS, GLYPHS + len(NEW_GLYPHS)))
    msgs[0x129] = [0x1006, *new_codes, 0x1001]
    freq = {}
    for m in msgs:
        for c in m:
            freq[c] = freq.get(c, 0) + 1
    codes, nodes, root = build_tree(freq)
    d = expand(data, 2)
    base = NEW_BANK << 16 | 0x8000
    # 뱅크 30: 디코더 사본, 색인 뱅크 훅, 마스크 표, 트리 표 1·0, 폰트 묶음 표, 그 뒤 메시지.
    code = bytearray(data[lorom(DECODER):lorom(DECODER_END)])
    stub = bytes((0x20, 0x8D, 0x8C, 0xA5, 0xF2, 0x09, 0x20, 0x85, 0xF2, 0x60))
    mask_at = base + len(code)
    mask = bytes(1 << i for i in range(8))
    t1_at = mask_at + len(mask)
    t0_at = t1_at + len(nodes) * 2
    font_at = t0_at + len(nodes) * 2
    groups = font_groups(rom)
    table = bytearray(data[lorom(FONT_GROUPS):lorom(FONT_GROUPS) + len(groups) * 5])
    glyph_at = 0x07D77C                                              # 옮긴 메시지가 비운 자리(뱅크 07)
    g = bytearray()
    for name in NEW_GLYPHS:
        g += glyph_bits(NEW_GLYPHS[name])
    w, h = len(next(iter(NEW_GLYPHS.values()))[0]), len(next(iter(NEW_GLYPHS.values())))
    table += bytes((len(NEW_GLYPHS), w << 4, glyph_at & 0xFF, glyph_at >> 8 & 0xFF, (glyph_at >> 16) - 7 | h << 2))
    msg_at = font_at + len(table)
    blob, starts = encode(codes, msgs)
    assert (msg_at & 0xFFFF) + len(blob) < 0x10000 * 8, '메시지가 너무 김'

    for at, v in ((NODES_1_OPERAND, t1_at), (NODES_0_OPERAND, t0_at), (MASK_OPERAND, mask_at)):
        code[at - DECODER:at - DECODER + 2] = (v & 0xFFFF).to_bytes(2, 'little')
    code[ROOT_OPERAND - DECODER:ROOT_OPERAND - DECODER + 2] = (root * 2).to_bytes(2, 'little')
    assert code[-1] == 0x60
    code[-1] = 0x6B                                                  # RTS → RTL
    t1 = b''.join(n[0].to_bytes(2, 'little') for n in nodes)
    t0 = b''.join(n[1].to_bytes(2, 'little') for n in nodes)
    # 메시지는 LoROM 뱅크 경계($FFFF → 다음 뱅크 $8000)를 넘으며 이어지므로 뱅크마다 32KB 씩 나눠 쓴다.
    head = code + mask + t1 + t0 + table
    stream = bytes(head)
    pos = 0
    first = lorom(base)
    d[first:first + len(stream)] = stream
    o = first + len(stream)
    msg_off = o
    while pos < len(blob):
        room = 0x8000 - (o % 0x8000)
        d[o:o + min(room, len(blob) - pos)] = blob[pos:pos + room]
        pos += room
        o += room
    # 메시지 시작 비트 → CPU 주소. 앞 머리 뒤 첫 바이트가 msg_at.
    index = bytearray()
    for m in range(0, MESSAGES, 16):
        bit = starts[m]
        off = msg_off + (bit >> 3)
        cpu = (off // 0x8000) << 16 | 0x8000 | off % 0x8000
        rel_cpu = cpu - 0x200000                                     # 24:9E07 이 뱅크에 20 을 OR 한다
        index += cpu_to_bytes(rel_cpu << 3 | bit & 7)
    d[lorom(INDEX):lorom(INDEX) + len(index)] = index
    d[lorom(glyph_at):lorom(glyph_at) + len(g)] = g
    d[lorom(DECODER):lorom(DECODER) + 5] = bytes((0x22, *cpu_to_bytes(base), 0x60))
    d[lorom(WALK_INDEX_STUB):lorom(WALK_INDEX_STUB) + len(stub)] = stub
    d[lorom(WALK_INDEX_CALL):lorom(WALK_INDEX_CALL) + 2] = (WALK_INDEX_STUB & 0xFFFF).to_bytes(2, 'little')
    for a, k in FONT_TABLE_OPERANDS:
        d[lorom(a):lorom(a) + 3] = cpu_to_bytes(font_at + k)
    info = [f'잎 {len(codes)}, 노드 {len(nodes)}, 뿌리 X {root * 2:04X}, 최장 부호 {max(map(len, codes.values()))}비트',
            f'디코더 {base:06X}, 트리 1·0 {t1_at:06X}·{t0_at:06X}, 폰트 표 {font_at:06X}, 메시지 {len(blob)}바이트 ~{o:06X}(파일)',
            f'새 글자 {", ".join(f"{c:03X}" for c in new_codes)} 그림 {glyph_at:06X}']
    return checksum(d), info


def decode_check(data):
    """retree 롬을 롬만으로 다시 풀어 원본 메시지와 같은지(129 제외) 센다. 디코더 사본·새 색인·훅을 그대로 따른다."""
    rom = Rom(data)
    t1 = (NEW_BANK << 16) | rom.u16(NEW_BANK << 16 | 0x8000 | (NODES_1_OPERAND - DECODER))
    t0 = (NEW_BANK << 16) | rom.u16(NEW_BANK << 16 | 0x8000 | (NODES_0_OPERAND - DECODER))
    root = rom.u16(NEW_BANK << 16 | 0x8000 | (ROOT_OPERAND - DECODER))
    out = []
    for g in range(MESSAGES // 16):
        v = rom.u24(INDEX + g * 3)
        addr, bit = (v >> 3) | 0x200000, v & 7
        for _m in range(16):
            msg = []
            while True:
                x = root
                while True:
                    b = (rom.u8(addr) >> bit) & 1
                    bit += 1
                    if bit == 8:
                        bit = 0
                        addr += 1
                        if addr & 0xFFFF == 0:
                            addr |= 0x8000
                    val = rom.u16((t1 if b else t0) + x)
                    if val & 0x8000:
                        break
                    x = (val & 0x1FFF) * 2
                c = val & 0x1FFF
                msg.append(c)
                if c in ENDS:
                    break
            out.append(msg)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('expand', 'retree'))
    ap.add_argument('--size', type=int, default=2, choices=(2, 3, 4))
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    if a.cmd == 'expand':
        out = expand(data, a.size)
        print(f'{len(out):#x} 바이트, 머리 크기 {out[HEADER + 0x17]:02X}')
    else:
        out, info = retree(data)
        print('\n'.join(info))
        rom = Rom(data)
        again = decode_check(bytes(out))
        same = sum(again[m] == message(rom, m) for m in range(MESSAGES) if m != 0x129)
        print(f'롬만으로 다시 풀기: 메시지 {MESSAGES - 1}개 중 {same}개 같음, 129 = '
              + ' '.join(f'{c:04X}' for c in again[0x129]))
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'wb') as f:
        f.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
