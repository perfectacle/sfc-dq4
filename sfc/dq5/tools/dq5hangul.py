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


def glyph_bits(glyphs):
    """24:A631: 묶음 안 n 번째 글자는 n × 폭 × 높이 비트 뒤에서 시작하므로, 글자 사이에 채움 없이 비트를 잇는다."""
    w, h = len(glyphs[0][0]), len(glyphs[0])
    out = bytearray((w * h * len(glyphs) + 7) // 8)
    for n, rows in enumerate(glyphs):
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == '#':
                    i = n * w * h + y * w + w - 1 - x
                    out[i >> 3] |= 1 << (i & 7)
    return out


def retree(data, glyphs=None, overrides=None):
    """원본 롬 바이트 → 실험용 2MB 롬과 설명 줄. glyphs 는 새 글자(코드 3DB 부터 차례로)의 점 그림 목록,
    overrides 는 {메시지 번호: 코드 목록}. 없으면 「한」「글」 두 자와 메시지 129 = {1006}한글{1001}."""
    rom = Rom(data)
    msgs = [message(rom, m) for m in range(MESSAGES)]
    if glyphs is None:
        glyphs = list(NEW_GLYPHS.values())
    new_codes = list(range(GLYPHS, GLYPHS + len(glyphs)))
    if overrides is None:
        overrides = {0x129: [0x1006, *new_codes, 0x1001]}
    for m, c in overrides.items():
        msgs[m] = c
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
    g = glyph_bits(glyphs)
    w, h = len(glyphs[0][0]), len(glyphs[0])
    table += bytes((len(glyphs), w << 4, glyph_at & 0xFF, glyph_at >> 8 & 0xFF, (glyph_at >> 16) - 7 | h << 2))
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


# 시제품(proto): 메시지 한 줄, 이름, 명령 창을 한글로.
PROTO_LINE = ('이름은 ', '입니다')            # 메시지 129 = {1006}이름은 {1012}입니다。{1001}
PROTO_NAME = '용사'                           # 주인공 이름. 바이트는 아래 창 타일 번호와 같게 둔다
PROTO_MENU = (('대화', '주문'), ('강함', '도구'), ('장비', '작전'), ('문', '조사'))
PROTO_TILE0 = 0x50                            # 창 글자 BG3 타일(04:E528 의 1bpp)을 이 번호부터 한글 8×8 로 바꾼다
# --long: 원래 레코드(56바이트)에 들어가지 않는 긴 항목. 레코드를 뱅크 36 에 두고 창을 열 때 낮은 WRAM 으로 복사한다.
PROTO_MENU_LONG = (('이야기하기', '주문외우기'), ('강함', '도구'), ('장비', '작전'), ('문열기', '조사하기'))
PROTO_TILE0_LONG = 0x4B
# 창 레코드를 읽는 코드는 데이터 뱅크 04 의 16비트 주소로 읽으므로(04:9C4F 등) 레코드는 뱅크 04 안이나, 뱅크 00~3F 의
# $0000~$1FFF(낮은 WRAM 거울)에만 둘 수 있다. 7E:11A0~ 는 전투가 쓰고, 7E:1C30~1C52 에는 세이브스테이트마다 남은 자료가 있다.
# 7E:1ABC~1BB1(246바이트)은 세이브스테이트 셋에서 0 이고 전원부터 켠 새 게임·전투·필드 전투·가게·교회·이벤트 전투·일행 메뉴
# 실행에서 쓰기가 없던 자리다(증명은 아님, sfc/dq5/docs/dq5-hangul-format.md).
LOW_WRAM_RECORD = 0x1AC0
WINDOW_POINTER_LOAD = 0x049C46                # LDA $EB48,X / STA $DA (5바이트)
LONG_BANK = 0x36
# --twobyte: 이름 문자열(24:A7B6)에 접두 85 를 두어 「85 xx」 = 글자 코드 3DB + xx - 10 으로 읽게 한다. 이름 8바이트에 넉 자.
# xx 를 10 부터 쓰는 것은 01(이름 끝, 24:8A0F)·00 과 겹치지 않게 하려는 것이다.
NAME_PREFIX = 0x85
PROTO_NAME_2BYTE = '한글이름'
NAME_CODE_CALL = 0x24A7D5                     # JSR $A81E(보통 바이트 → 24:B270)
NAME_PREFIX_ROUTINE = 0x249E11                # retree 가 비운 디코더 자리(24:9E07~ 의 색인 루틴 뒤)
STRING_CODES = 0x24B270
COMMAND_WINDOW = 0x04ED0C
WINDOWS_TABLE = 0x04EB48
WINDOW_FONT = 0x04E528
PERIOD = 0x356                               # 「。」


def proto(data, long=False, twobyte=False):
    """retree 위에 한글 시제품을 얹은 2MB 롬과 설명 줄, 이름 바이트. long 이면 명령 창 항목을 PROTO_MENU_LONG 으로."""
    menu, tile0 = (PROTO_MENU_LONG, PROTO_TILE0_LONG) if long else (PROTO_MENU, PROTO_TILE0)
    from dq5hangulfont import render
    syll = []
    for ch in ''.join(PROTO_LINE) + PROTO_NAME + (PROTO_NAME_2BYTE if twobyte else ''):
        if ch != ' ' and ch not in syll:
            syll.append(ch)
    vwf = {ch: GLYPHS + i for i, ch in enumerate(syll)}

    def rows(ch, w, h):
        return [''.join('#' if v else '.' for v in r) for r in render(ch, w, h)]
    glyphs = [rows(ch, 11, 13) for ch in syll]

    def line(t):
        return [0x000 if ch == ' ' else vwf[ch] for ch in t]
    msg = [0x1006, *line(PROTO_LINE[0]), 0x1012, *line(PROTO_LINE[1]), PERIOD, 0x1001]
    d, info = retree(data, glyphs, {0x129: msg})
    # 창 글자: 메뉴·이름의 음절마다 BG3 타일 하나(8×8 1bpp).
    tiles = []
    for pair in menu:
        for word in pair:
            for ch in word:
                if ch not in tiles:
                    tiles.append(ch)
    for ch in PROTO_NAME:
        if ch not in tiles:
            tiles.append(ch)
    tile = {ch: tile0 + i for i, ch in enumerate(tiles)}
    for ch, t in tile.items():
        bits = bytes(int(''.join('1' if v else '0' for v in r), 2) for r in render(ch, 8, 8))
        o = lorom(WINDOW_FONT + (t - 1) * 8)
        d[o:o + 8] = bits
    # 이름 바이트 = 창 타일 번호. 보행 모드 메시지(1012)는 24:B270 으로 같은 바이트를 VWF 글자로 바꾼다.
    name = bytes(tile[ch] for ch in PROTO_NAME)
    for ch in PROTO_NAME:
        o = lorom(STRING_CODES + tile[ch] * 2)
        d[o:o + 2] = vwf[ch].to_bytes(2, 'little')
    # 명령 창: 항목을 한글 타일로 다시 쓰고 너비를 가장 긴 줄 + 테두리 2 로.
    o = lorom(COMMAND_WINDOW)
    old_len = len(bytes(d[o:o + 0x38]).split(b'\xff\x80')[0])
    body = bytearray()
    width = 0
    for a, b in menu:
        row = b'\xfe' + bytes(tile[c] for c in a) + b'\x01' * (max(len(x) for x, _ in menu) - len(a) + 1) \
            + b'\xfe' + bytes(tile[c] for c in b) + b'\xff'
        width = max(width, len(row) - 1)                         # FF 를 뺀 칸 수(FE 는 커서 칸)
        body += row
    head = bytearray(d[o:o + 6])
    head[2] = width + 2
    rec = bytes(head) + bytes(body) + b'\x80'                      # 80 = 레코드 끝. 빼면 남은 옛 바이트를 이어 읽어 엉뚱한 창이 뜬다
    if twobyte:
        # CMP #$85 / BNE 원래 / INX / DEC $00 / LDA $01,X / REP #$20 / AND #$00FF / CLC / ADC #$03CB / JSR $A832 / SEP #$20 / RTS
        r = bytes((0xC9, NAME_PREFIX, 0xD0, 0x14, 0xE8, 0xC6, 0x00, 0xB5, 0x01, 0xC2, 0x20, 0x29, 0xFF, 0x00, 0x18,
                   0x69, (GLYPHS - 0x10) & 0xFF, (GLYPHS - 0x10) >> 8, 0x20, 0x32, 0xA8, 0xE2, 0x20, 0x60, 0x4C, 0x1E, 0xA8))
        ro = lorom(NAME_PREFIX_ROUTINE)
        d[ro:ro + len(r)] = r
        co = lorom(NAME_CODE_CALL)
        d[co:co + 3] = bytes((0x20, NAME_PREFIX_ROUTINE & 0xFF, NAME_PREFIX_ROUTINE >> 8 & 0xFF))
        name = b''.join(bytes((NAME_PREFIX, vwf[ch] - GLYPHS + 0x10)) for ch in PROTO_NAME_2BYTE)
    if len(rec) <= old_len + 1:
        d[o:o + len(rec)] = rec
        where = '04:ED0C'
    else:
        # 레코드를 뱅크 36 에 두고, 창 표의 창 01 칸을 낮은 WRAM 주소로 바꾼 뒤 04:9C46 에 훅을 건다.
        # 훅은 원래 명령(LDA $EB48,X / STA $DA)을 하고, 주소가 LOW_WRAM_RECORD 이면 MVN 으로 레코드를 7E 에 복사한다.
        src = LONG_BANK << 16 | 0x8000
        hook = src + 0x100
        so = lorom(src)
        d[so:so + len(rec)] = rec
        n = len(rec) - 1
        code = bytes((0xBF, 0x48, 0xEB, 0x04, 0x85, 0xDA, 0xC9, LOW_WRAM_RECORD & 0xFF, LOW_WRAM_RECORD >> 8, 0xD0, 0x18,
                      0x08, 0x8B, 0xC2, 0x30, 0xDA, 0x5A, 0xA2, src & 0xFF, src >> 8 & 0xFF,
                      0xA0, LOW_WRAM_RECORD & 0xFF, LOW_WRAM_RECORD >> 8, 0xA9, n & 0xFF, n >> 8,
                      0x54, 0x7E, LONG_BANK, 0x7A, 0xFA, 0xAB, 0x28, 0xA5, 0xDA, 0x6B))
        ho = lorom(hook)
        d[ho:ho + len(code)] = code
        po = lorom(WINDOW_POINTER_LOAD)
        d[po:po + 5] = bytes((0x22, hook & 0xFF, hook >> 8 & 0xFF, hook >> 16, 0xEA))
        to = lorom(WINDOWS_TABLE + 1 * 2)
        d[to:to + 2] = LOW_WRAM_RECORD.to_bytes(2, 'little')
        where = f'{LONG_BANK:02X}:8000 → 7E:{LOW_WRAM_RECORD:04X}'
    d = checksum(d)
    info.append(f'한글 VWF {len(syll)}자 {GLYPHS:03X}~, 창 타일 {len(tiles)}개 {tile0:02X}~, 이름 바이트 {name.hex(" ")}, '
                f'명령 창 레코드 {len(rec)}바이트 {where}, 너비 {width + 2}(원래 12)')
    return d, info, name


# wintest: 창 문자열에 접두 9F 를 두어 「9F xx」 = 한글 8×8 글자 xx 를, 창을 그릴 때 VRAM 타일 83(창 글자 가운데 쓰이지 않는
# 단 하나의 칸)에 올려(전송 목록 7E:4000, 00:8CF9 가 NMI 에서 처리) 그 타일로 찍는다. 글자 하나짜리 시제품.
WIN_PREFIX = 0x9F
WIN_TILE = 0x83
WIN_DISPATCH = 0x04B11E                       # CMP #$01 / BEQ / JSR $B235 / BRA … / INY INY
WIN_HOOK = 0x368200
WIN_GLYPHS = 0x368300
WINTEST_TEXT = '한'


def wintest(data):
    """2MB 롬에 창 2바이트 접두 9F 시제품을 넣고, 명령 창 첫 항목 「はなす」 의 は 를 「9F 00」 으로 바꾼다."""
    from dq5hangulfont import render
    d = expand(data, 2)
    glyphs = b''.join(bytes(int(''.join('1' if v else '0' for v in r), 2) for r in render(ch, 8, 8))
                      for ch in WINTEST_TEXT)
    go = lorom(WIN_GLYPHS)
    d[go:go + len(glyphs)] = glyphs
    vram = 0x1000 + WIN_TILE * 8
    g = WIN_GLYPHS
    code = bytes((
        0xC9, 0x01, 0xD0, 0x04, 0xC8, 0xC8, 0x38, 0x6B,          # CMP #$01 / BNE / INY / INY / SEC / RTL
        0xC9, WIN_PREFIX, 0xF0, 0x02, 0x18, 0x6B,                # CMP #$9F / BEQ pre / CLC / RTL
        0xBD, 0x00, 0x00, 0xE8,                                  # pre: LDA $0000,X / INX (글자 번호)
        0xDA, 0x5A, 0x8B, 0x08,                                  # PHX / PHY / PHB / PHP
        0xC2, 0x30, 0x29, 0xFF, 0x00, 0x0A, 0x0A, 0x0A, 0xAA,    # REP #$30 / AND #$00FF / ASL×3 / TAX
        0xE2, 0x20, 0xA9, 0x7E, 0x48, 0xAB,                      # SEP #$20 / LDA #$7E / PHA / PLB
        0xAC, 0x59, 0x07,                                        # LDY $0759
        0xA9, 0x80, 0x99, 0x00, 0x40, 0xC8,                      # [80]
        0xA9, vram & 0xFF, 0x99, 0x00, 0x40, 0xC8,               # [VRAM 낮은]
        0xA9, vram >> 8, 0x99, 0x00, 0x40, 0xC8,                 # [VRAM 높은]
        0xA9, 0x08, 0x99, 0x00, 0x40, 0xC8,                      # [워드 수 8]
        0xA9, 0x00, 0x99, 0x00, 0x40, 0xC8,
        0xA9, 0x08, 0x85, 0x00,                                  # LDA #8 / STA $00 (줄 수)
        0xBF, g & 0xFF, g >> 8 & 0xFF, g >> 16,                  # loop: LDA glyphs,X
        0x99, 0x00, 0x40, 0xC8, 0xA9, 0xFF, 0x99, 0x00, 0x40, 0xC8, 0xE8,   # STA / INY / LDA #$FF / STA / INY / INX
        0xC6, 0x00, 0xD0, 0xED,                                  # DEC $00 / BNE loop(19바이트 뒤로)
        0x8C, 0x59, 0x07, 0xEE, 0x58, 0x07,                      # STY $0759 / INC $0758
        0xA9, 0x80, 0x04, 0x1A, 0x22, 0x8A, 0x95, 0x00,          # LDA #$80 / TSB $1A / JSL $00958A(NMI 에서 목록을 보낼 때까지 기다림, 04:E317 과 같음)
        0x28, 0xAB, 0x7A, 0xFA,                                  # PLP / PLB / PLY / PLX
        0xA9, WIN_TILE, 0x18, 0x6B))                             # LDA #$83 / CLC / RTL
    ho = lorom(WIN_HOOK)
    d[ho:ho + len(code)] = code
    # 04:B11E: JSL hook / BCS (처리 끝) / JSR $B235 / BRA $B0ED / BRA $B0ED(원래 B129)
    patch = bytes((0x22, WIN_HOOK & 0xFF, WIN_HOOK >> 8 & 0xFF, WIN_HOOK >> 16, 0xB0, 0x05, 0x20, 0x35, 0xB2, 0x80, 0xC4))
    po = lorom(WIN_DISPATCH)
    d[po:po + len(patch)] = patch
    co = lorom(COMMAND_WINDOW + 7)
    assert d[co] == 0x29
    d[co:co + 2] = bytes((WIN_PREFIX, 0x00))
    return checksum(d), [f'창 접두 {WIN_PREFIX:02X}: 훅 {WIN_HOOK:06X}, 글자 {len(WINTEST_TEXT)}개 {WIN_GLYPHS:06X}, VRAM 타일 {WIN_TILE:02X}']


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
    ap.add_argument('cmd', choices=('expand', 'retree', 'proto', 'wintest'))
    ap.add_argument('--size', type=int, default=2, choices=(2, 3, 4))
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--twobyte', action='store_true', help='proto: 이름 문자열 2바이트 접두 85(24:A7B6)')
    ap.add_argument('--long', action='store_true', help='proto: 레코드에 안 들어가는 긴 명령 창 항목(뱅크 36 → 낮은 WRAM)')
    a = ap.parse_args()
    data = open(a.rom, 'rb').read()
    if a.cmd == 'expand':
        out = expand(data, a.size)
        print(f'{len(out):#x} 바이트, 머리 크기 {out[HEADER + 0x17]:02X}')
    elif a.cmd == 'wintest':
        out, info = wintest(data)
        print('\n'.join(info))
    elif a.cmd == 'proto':
        out, info, name = proto(data, a.long, a.twobyte)
        print('\n'.join(info))
        poke = ';'.join(f'7E{0x2001 + i:04X}={b:02X}' for i, b in enumerate(name))
        print(f'이름을 넣으려면 POKE="{poke}' + (';7E{:04X}=01"'.format(0x2001 + len(name)) if len(name) < 8 else '"'))
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
