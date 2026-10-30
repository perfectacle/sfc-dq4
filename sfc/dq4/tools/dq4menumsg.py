"""모험의 서 메뉴의 허프만 메시지(지우기 확인 1CE·1CF, 기록 깨짐 1D0)를 한글로 바꾼다.

새 글자를 메시지에 쓰려면 허프만 트리를 다시 만들어야 하고, 커진 트리와 메시지는 제자리에 들어가지 않는다.
DQ5 트랙 dq5hangul.py retree(2MB, 뱅크 30)와 같은 방법을 4MB 통합 롬의 빈 뱅크에 맞춘 것이다.

  65:8000~  보행 모드 디코더(24:9E02~9E46 사본, 표 피연산자와 끝 RTL 만 바꿈), 비트 마스크, 트리 1·0, 폰트 묶음 표,
            그 뒤 메시지 3,200개. 뱅크 69 끝까지. 3200 이상을 덧붙이면 색인 표를 트리 뒤(폰트 묶음 표 앞)에 둔다
  24:9E02   JSL 65:8000 / RTS
  24:9E07   JSR 8C8D / LDA $F2 / ORA #$60 / STA $F2 / RTS — 색인은 21비트라 뱅크를 60 아래로 적고 풀 때 OR 한다.
            24:8C8D 는 전투 메시지(24:8C60)도 부르므로 그 안은 고치지 않는다
  24:8BD7   JSR 8C8D → JSR 9E07
  24:AF1E   새 색인(3,200개일 때). 덧붙이면 24:8BC3 의 색인 읽기 뱅크·주소를 머리의 표로 바꾼다
  24:A63C·A660·A6C2·A673  폰트 묶음 표 피연산자 → 65 의 새 표
  07:D77C~  옮긴 메시지가 비운 자리. 한글 글자 그림(12×11 1bpp)

글자 코드는 3DB + 이름 입력 글리프 번호(dq4nameentry.GLYPHS: 호환 자모 51, 완성형 2,350, ＊, 전각 공백)이고,
그 뒤에 문장 부호가 이어진다. 글자 그림을 읽는 24:A6C1~ 은 묶음 주소에 비트 위치를 더한 뒤 뱅크 바이트만 따로 올려
데이터 뱅크로 삼으므로, 묶음 하나가 뱅크 경계를 넘으면 안 된다. 묶음 +4 의 뱅크는 07 + 2비트라 07~0A 에만 둔다.
형식은 sfc/dq4/docs/dq4-menu-format.md.
"""
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4nameentry as ne  # noqa: E402
from dq5hangul import (DECODER, DECODER_END, MASK_OPERAND, MESSAGES, NODES_0_OPERAND, NODES_1_OPERAND,  # noqa: E402
                       ROOT_OPERAND, WALK_INDEX_CALL, WALK_INDEX_STUB, build_tree, cpu_to_bytes, decode_check,
                       encode, glyph_bits)
from dq5map import Rom, lorom  # noqa: E402
from dq5text import FONT_GROUPS, FONT_TABLE_OPERANDS, GLYPHS, INDEX, font_groups, message  # noqa: E402
from dq5textwrite import INDEX_LOAD, INDEX_LOAD_CODE, MAX_MESSAGES  # noqa: E402

BASE = 0x658000
LIMIT = 0x6A0000            # 65~69 다섯 뱅크. 70 은 서곡 재배치 표, 6A~6F·72~7D 는 소리 이식이 쓴다
INDEX_BANK = 0x60
GLYPH_START = 0x07D77C     # 원래 보행 모드 메시지 3,200개의 시작(끝은 0C:8020). 그림은 뱅크 0A 까지만
GLYPH_BANKS = range(0x07, 0x0B)
READ_SLACK = 2              # 글자 한 줄을 3바이트로 읽으므로 묶음 끝 뒤 2바이트도 같은 뱅크 안이어야 한다
CELL_W, CELL_H = 12, 11     # 가나 ぼ(높이 11)와 같은 바닥. 묶음은 13줄 칸의 아래에 맞춰 그린다(24:A6DA)
PUNCT = ('.', '?', '!', ',')
# 부호 앞 빈 점. Galmuri11 부호는 앞 여백이 없어 「다.」처럼 앞 글자 ㅏ 곁줄기에 붙어 보였다(MesenCE 화면).
PUNCT_PAD = 1
# 1점짜리 마침표·쉼표는 SFC 화면에서 거의 보이지 않아 2점 굵기로 다시 그린다. 아래 줄이 기준선이다.
PUNCT_ROWS = {'.': ('##', '##'), ',': ('##', '.#', '#.')}
CHARS = ne.GLYPHS + list(PUNCT)

LINE, END, PAUSE, SLOT = 0x1000, 0x1001, 0x1006, 0x1004
# 원문(FC DQ4 그룹 1 「なまえ のぼうけんのしょを けします。いいですか？」 와 SFC 문장)을 옮겼다. {1004} 는 칸 번호(1~3)라
# 받침이 바뀌므로 「번」 을 붙여 조사를 고정한다.
TEXTS = {
    0x1CE: [PAUSE, '모험의 서 ', SLOT, '번을 지웁니다.', LINE, '괜찮습니까?', END],
    0x1CF: [PAUSE, '모험의 서 ', SLOT, '번을 지웠습니다.', END],
    0x1D0: [PAUSE, '정말 안타깝지만', LINE, '모험의 서 ', SLOT, '번이', LINE, '지워지고 말았습니다.', END],
}


def code(ch):
    return 0 if ch == ' ' else GLYPHS + CHARS.index(ch)


def codes(parts):
    out = []
    for p in parts:
        if isinstance(p, str):
            out.extend(code(ch) for ch in p)
        else:
            out.append(p)
    return out


def glyph_rows(font, ch, w, h):
    """BDF 글자를 w×h 칸에 기준선을 맨 아래 줄로 둬 '#'/'.' 줄 목록으로."""
    g = font.glyphs[ch]
    gw, gh, bx, by = g['bbx']
    if bx < 0 or bx + gw > w or by < 0 or by + gh > h:
        raise ValueError(f'{ch!r}: {w}×{h} 칸을 넘음 {g["bbx"]}')
    rows = [['.'] * w for _ in range(h)]
    for i, row in enumerate(g['rows']):
        y = h - 1 - (by + gh - 1 - i)
        for x, v in enumerate(row):
            if v:
                rows[y][bx + x] = '#'
    return [''.join(r) for r in rows]


def widen_tick(rows):
    """오른쪽 세로획 바로 옆 1점 곁줄기(ㅏ·ㅑ·ㅘ 등)를 빈 오른쪽 열로 1점 늘린다.

    Galmuri11 은 곁줄기가 1점이라 SFC 화면에서 「리」·「라」가 거의 같아 보였다. 글자 칸의 마지막 열은
    글자 사이 틈이라, 늘린 줄에서만 다음 글자와 틈이 없어진다.
    """
    w = len(rows[0])
    counts = [sum(r[x] == '#' for r in rows) for x in range(w)]
    v = max(range(w // 2, w), key=lambda x: counts[x])
    if counts[v] < 6 or v + 2 >= w:
        return rows
    out = list(rows)
    for y in range(1, len(rows) - 1):
        r = rows[y]
        tick = r[v - 1] == '.' and r[v] == '#' and r[v + 1] == '#' and r[v + 2] == '.'
        alone = rows[y - 1][v + 1] == '.' and rows[y + 1][v + 1] == '.'
        through = rows[y - 1][v] == '#' and rows[y + 1][v] == '#'
        if tick and alone and through:
            out[y] = r[:v + 2] + '#' + r[v + 3:]
    return out


def hangul_rows(font, ch):
    rows = glyph_rows(font, ch, CELL_W, CELL_H)
    return widen_tick(rows) if '가' <= ch <= '힣' else rows


def punct_rows(font, ch):
    """부호 하나의 (폭, 줄 목록). 앞에 PUNCT_PAD 점을 비운다."""
    if ch in PUNCT_ROWS:
        shape = PUNCT_ROWS[ch]
        w = PUNCT_PAD + len(shape[0]) + 1
        rows = ['.' * w] * (CELL_H - len(shape)) + ['.' * PUNCT_PAD + r + '.' for r in shape]
        return w, rows
    g = font.glyphs[ch]
    w = g['adv'] + PUNCT_PAD
    return w, ['.' * PUNCT_PAD + r for r in glyph_rows(font, ch, g['adv'], CELL_H)]


def plan_groups(sizes, start=GLYPH_START):
    """(글자 수, 폭, 높이) 목록 → 묶음마다 (글자 수, 폭, 높이, 주소). 뱅크를 넘는 묶음은 나눈다."""
    if start & 0xFFFF < 0x8000:
        raise ValueError(f'{start:06X}: 롬 자리가 아님')
    at, out = start, []
    for count, w, h in sizes:
        if not (0 < w < 16 and 0 < h < 16):
            raise ValueError(f'묶음 크기 {w}×{h} 는 4비트를 넘음')
        while count:
            room = ((at | 0xFFFF) + 1 - READ_SLACK - at) * 8 // (w * h)
            n = min(count, room, 0xFFF)
            if n <= 0:
                at = ((at >> 16) + 1) << 16 | 0x8000
                continue
            if at >> 16 not in GLYPH_BANKS:
                raise ValueError('글자 그림 자리가 모자람')
            out.append((n, w, h, at))
            at += (n * w * h + 7) // 8
            count -= n
    return out


def index_entry(stream, bit):
    """메시지 시작 비트 → 색인 3바이트. stream 은 메시지 첫 바이트의 파일 오프셋. 24:9E07 이 뱅크에 INDEX_BANK 를 OR 한다."""
    off = stream + (bit >> 3)
    cpu = (off // 0x8000) << 16 | 0x8000 | off % 0x8000
    return cpu_to_bytes((cpu - (INDEX_BANK << 16)) << 3 | bit & 7)


def message_count(ids):
    """메시지 수: 3200 이상 번호는 3200 부터 빈 번호 없이 이어야 하고, 색인이 16개마다 하나라 16의 배수로 올린다."""
    more = sorted(m for m in ids if m >= MESSAGES)
    if more != list(range(MESSAGES, MESSAGES + len(more))):
        raise ValueError(f'3200 이상 메시지는 {MESSAGES:X} 부터 빈 번호 없이 이어야 함')
    total = (MESSAGES + len(more) + 15) // 16 * 16
    if any(m < 0 for m in ids) or total > MAX_MESSAGES:
        raise ValueError(f'메시지 번호는 0~{MAX_MESSAGES - 1:X}')
    return total


def apply(data, font, extra=None):
    """메뉴 롬 바이트 → 메시지를 바꾼 롬 바이트와 설명 줄. extra 는 {메시지 번호: 부분 목록}(dq4chapter1.py 등).
    3200 이상 번호는 덧붙이고, 마지막 16개 묶음의 남는 자리는 끝 코드 하나로 채운다."""
    d = bytearray(data)
    rom = Rom(bytes(data))
    clash = set(TEXTS) & set(extra or {})
    if clash:
        raise ValueError(f'메뉴 메시지와 겹치는 번호: {sorted(f"{m:03X}" for m in clash)}')
    total = message_count(extra or {})
    grown = total > MESSAGES
    msgs = [message(rom, m) for m in range(MESSAGES)] + [[END]] * (total - MESSAGES)
    for m, parts in {**TEXTS, **(extra or {})}.items():
        msgs[m] = codes(parts)
    freq = {}
    for m in msgs:
        for c in m:
            freq[c] = freq.get(c, 0) + 1
    tree, nodes, root = build_tree(freq)
    blob, starts = encode(tree, msgs)

    hangul = [hangul_rows(font, ch) for ch in ne.GLYPHS]
    punct = [punct_rows(font, ch) for ch in PUNCT]
    sizes = [(len(hangul), CELL_W, CELL_H)] + [(1, w, CELL_H) for w, _ in punct]
    groups = plan_groups(sizes)
    pictures = list(hangul) + [rows for _, rows in punct]
    table = bytearray(rom.d[lorom(FONT_GROUPS):lorom(FONT_GROUPS) + len(font_groups(rom)) * 5])
    i = 0
    for n, w, h, at in groups:
        pic = glyph_bits(pictures[i:i + n])
        o = lorom(at)
        d[o:o + len(pic)] = pic
        table += bytes((n & 0xFF, w << 4 | n >> 8, at & 0xFF, at >> 8 & 0xFF, (at >> 16) - 7 | h << 2))
        i += n

    decoder = bytearray(rom.d[lorom(DECODER):lorom(DECODER_END)])
    mask = bytes(1 << b for b in range(8))
    mask_at = BASE + len(decoder)
    t1_at = mask_at + len(mask)
    t0_at = t1_at + len(nodes) * 2
    index_at = t0_at + len(nodes) * 2
    index_size = total // 16 * 3 if grown else 0
    font_at = index_at + index_size
    for at, v in ((NODES_1_OPERAND, t1_at), (NODES_0_OPERAND, t0_at), (MASK_OPERAND, mask_at)):
        decoder[at - DECODER:at - DECODER + 2] = (v & 0xFFFF).to_bytes(2, 'little')
    decoder[ROOT_OPERAND - DECODER:ROOT_OPERAND - DECODER + 2] = (root * 2).to_bytes(2, 'little')
    if decoder[-1] != 0x60:
        raise ValueError('디코더 끝이 RTS 가 아님')
    decoder[-1] = 0x6B
    t1 = b''.join(n[0].to_bytes(2, 'little') for n in nodes)
    t0 = b''.join(n[1].to_bytes(2, 'little') for n in nodes)
    head = bytes(decoder) + mask + t1 + t0 + bytes(index_size) + bytes(table)
    if (BASE & 0xFFFF) + len(head) > 0x10000:
        raise ValueError('디코더와 트리 표가 뱅크 65 를 넘음')
    stream = head + bytes(blob)
    o = lorom(BASE)
    if lorom(BASE) + len(stream) > lorom(LIMIT - 1) + 1:
        raise ValueError(f'메시지가 {LIMIT:06X} 을 넘음')
    if any(d[o:o + len(stream)]):
        raise ValueError(f'{BASE:06X}~ 가 비어 있지 않음')
    d[o:o + len(stream)] = stream

    index = b''.join(index_entry(o + len(head), starts[m]) for m in range(0, total, 16))
    index_table = index_at if grown else INDEX
    d[lorom(index_table):lorom(index_table) + len(index)] = index
    if grown:
        load = bytearray(INDEX_LOAD_CODE)
        load[1] = index_at >> 16
        for k, off in enumerate((5, 10, 15)):
            load[off:off + 2] = ((index_at & 0xFFFF) + k).to_bytes(2, 'little')
        p = lorom(INDEX_LOAD)
        if bytes(rom.d[p:p + len(load)]) != INDEX_LOAD_CODE:
            raise ValueError(f'{INDEX_LOAD:06X}: 예상한 원래 바이트가 아님')
        d[p:p + len(load)] = load

    stub = bytes((0x20, 0x8D, 0x8C, 0xA5, 0xF2, 0x09, INDEX_BANK, 0x85, 0xF2, 0x60))
    for addr, new, old in (
            (DECODER, bytes((0x22, *cpu_to_bytes(BASE), 0x60)), bytes.fromhex('088b4bab')),
            (WALK_INDEX_STUB, stub, bytes.fromhex('20c21064f4a2ba07e220')),
            (WALK_INDEX_CALL, (WALK_INDEX_STUB & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('8d8c'))):
        p = lorom(addr)
        if bytes(rom.d[p:p + len(old)]) != old:
            raise ValueError(f'{addr:06X}: 예상한 원래 바이트가 아님')
        d[p:p + len(new)] = new
    for a, k in FONT_TABLE_OPERANDS:
        if bytes(rom.d[lorom(a):lorom(a) + 3]) != cpu_to_bytes(FONT_GROUPS + k):
            raise ValueError(f'{a:06X}: 폰트 묶음 표 피연산자가 원래 값이 아님')
        d[lorom(a):lorom(a) + 3] = cpu_to_bytes(font_at + k)

    out = bytes(d)
    again = decode_check(out, BASE, INDEX_BANK, index=index_table, count=total)
    for m in range(total):
        if again[m] != msgs[m]:
            raise ValueError(f'메시지 {m:03X}: 다시 풀기가 다름')
    info = [(f'잎 {len(tree)}, 노드 {len(nodes)}, 최장 부호 {max(map(len, tree.values()))}비트, '
             f'메시지 {len(blob)}바이트 {BASE:06X}~(머리 {len(head)}바이트)'),
            '글자 묶음 ' + ', '.join(f'{n}자 {w}×{h} {at:06X}' for n, w, h, at in groups)]
    return out, info


def preview(font, path, scale=3):
    """세 메시지를 롬과 같은 칸(폭은 묶음 폭, 13줄 칸의 아래 맞춤)으로 그린 그림. 칸 번호와 공백은 8점."""
    from PIL import Image

    def cell(c):
        return None if c in ' 1' else (punct_rows(font, c)[0] if c in PUNCT else CELL_W)
    lines = [[]]
    for parts in TEXTS.values():
        for p in parts:
            if p == LINE:
                lines.append([])
            elif isinstance(p, str):
                lines[-1].extend(p)
            elif p == SLOT:
                lines[-1].append('1')
        lines += [[], []]
    width = 8 + max(sum(cell(c) or 8 for c in line) for line in lines)
    img = Image.new('RGB', (width, 13 * len(lines) + 8), (0, 0, 0))
    for y, line in enumerate(lines):
        x = 4
        for c in line:
            w = cell(c)
            if w:
                for ry, row in enumerate(punct_rows(font, c)[1] if c in PUNCT else hangul_rows(font, c)):
                    for rx, v in enumerate(row):
                        if v == '#':
                            img.putpixel((x + rx, 4 + y * 13 + 2 + ry), (255, 255, 255))
            x += w or 8
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(path)


if __name__ == '__main__':
    from dq4menupatch import Font
    preview(Font('galmuri11'), sys.argv[1] if len(sys.argv) > 1 else os.path.join('work', 'menu-msg-preview.png'))
