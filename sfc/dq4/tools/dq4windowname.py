"""게임 안 일행 열 창의 한글 이름(dq4windowname.asm). dq4menupatch.build 가 dq4bg3slot 다음에 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「상태 창 이름」.

이름 칸을 4칸에서 5칸으로 넓혀 Galmuri9 한글 넉 자(40점)를 담는다. 창 02(필드 상태 창)는 일행마다 열을 되풀이하므로
머리 너비 6 → 7 과 함께 열 간격 상수(04:A394·A3A4·B18E)를 5 → 6 으로 바꾼다(asm).
목록·つよさ 류의 공통 이름 출력 04:B79B 도 같은 렌더러로 그린다.
도구 이름 등 이름 표 문자열은 dq4windowtext 가 만든 그림을 칸 풀에서 빌린 칸에 올린다(04:B808).
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

CODE = 0x60C000
CODE_END = 0x60E000
STATUS_WINDOW = 0x02
LIST_HOOK = 0x04B79B
NMI_STUB = 0x00FFA1               # NMI 00:887C 가 들르는 받침(대기열이 있으면 JSL WqNmi, 이어서 JMP ($1944))
# 이름 하나를 04:B79B 로 찍는 「누구」 고르기 창(본문에 D0 자리 표시). 이름 칸 5칸을 담게 한 칸 왼쪽으로 옮겨 넓힌다.
# 오른쪽에는 이어서 열리는 창(도구·주문 목록 등)이 붙어 있어 오른쪽으로는 넓히지 않는다.
NAME_LISTS = (0x0C, 0x0E, 0x11, 0x13, 0x2C, 0x36, 0x38, 0x3D, 0x4A, 0x4F, 0x6F, 0x7A, 0x7F)
# 주문 목록 창(본문 00 81 FE D6 FF). 다섯 글자 칸을 한글 일곱 칸으로 오른쪽으로 넓힌다.
SPELL_WINDOW = 0x28
PREFIX_HOOK = 0x04B11E            # 창 바이트 갈래(메뉴 패치가 JSL 로 바꿔 둔 자리). 고정 문구 접두를 먼저 가른다


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def apply(data, font=None, asar=None):
    import dq4menupatch
    import dq4nameentry as ne
    import dq4windowtext
    asar = asar or os.environ.get('ASAR')
    if not asar:
        raise SystemExit('ASAR 에 asar 실행 파일을 주세요(sfc/dq4/docs/dq4-menu-format.md)')
    d = bytearray(data)
    if any(d[lorom(CODE):lorom(CODE_END)]):
        raise ValueError(f'{CODE:06X}~{CODE_END:06X} 가 비어 있지 않음')
    o = lorom(dq4menupatch.window_addr(d, STATUS_WINDOW))
    if d[o + 2] & 0x1F != 6:
        raise ValueError(f'창 {STATUS_WINDOW:02X} 머리 {d[o:o + 4].hex()}: 너비가 6 이 아님')
    d[o + 2] = (d[o + 2] & 0xE0) | 7
    for w in NAME_LISTS:
        o = lorom(dq4menupatch.window_addr(d, w))
        if d[o + 2] & 0x1F not in (8, 9) or d[o] & 0x1F == 0 or 0xD0 not in d[o + 4:o + 10]:
            raise ValueError(f'창 {w:02X} 머리 {d[o:o + 10].hex()}: 누구 고르기 창 모양이 아님')
        d[o] -= 1
        d[o + 2] += 1
    o = lorom(dq4menupatch.window_addr(d, SPELL_WINDOW))
    if d[o + 2] & 0x1F != 8 or d[o + 4:o + 9] != bytes((0x00, 0x81, 0xFE, 0xD6, 0xFF)):
        raise ValueError(f'창 {SPELL_WINDOW:02X} 머리 {d[o:o + 9].hex()}: 주문 목록 창 모양이 아님')
    d[o + 2] += 2
    hi_count = -(-len(ne.GLYPHS) // ne.CODE_RADIX)
    font = font or dq4menupatch.Font('galmuri9')
    text, _ = dq4windowtext.build(d, font)
    records, _ = dq4windowtext.fixed_records(d, font)
    for o, rec in records:
        d[o:o + len(rec)] = rec
    po = lorom(PREFIX_HOOK)
    if d[po] != 0x22:
        raise ValueError(f'{PREFIX_HOOK:06X} 가 JSL 이 아님: {d[po:po + 4].hex()}')
    t = lorom(dq4windowtext.TEXT_BANK << 16 | dq4windowtext.INDEX)
    if any(d[lorom(NMI_STUB):lorom(NMI_STUB) + 13]):
        raise ValueError(f'{NMI_STUB:06X} 가 비어 있지 않음')
    if any(d[t:t + len(text)]):
        raise ValueError(f'{dq4windowtext.TEXT_BANK:02X}:{dq4windowtext.INDEX:04X} 가 비어 있지 않음')
    d[t:t + len(text)] = text
    # 04:B79B 는 이름 입력이 먼저 NeListHook 으로 훅해 둔다. 메뉴 플래그가 켜져 있거나 한글이 아니면 그리로 넘긴다.
    o = lorom(LIST_HOOK)
    if d[o] != 0x5C:
        raise ValueError(f'{LIST_HOOK:06X} 가 JML 이 아님: {d[o:o + 4].hex()}')
    flag = re.search(r'^!flag\s*=\s*\$([0-9A-Fa-f]{6})', (HERE / 'dq4nameentry.asm').read_text(), re.M).group(1)
    defs = (f'!wn_code = ${CODE:06X}\n!wn_hi_base = ${ne.HI_BASE:02X}\n!wn_hi_count = {hi_count}\n'
            f'!wn_glyph_bank = ${ne.GLYPH_BANK:02X}\n!wn_list_prev = ${int.from_bytes(d[o + 1:o + 4], "little"):06X}\n'
            f'!wn_menu_flag = ${flag}\n!wt_bank = ${dq4windowtext.TEXT_BANK:02X}\n'
            f'!wt_prefix_prev = ${int.from_bytes(d[po + 1:po + 4], "little"):06X}\n'
            f'!wt_fixed = ${dq4windowtext.FIXED_PREFIX:02X}\n!wt_fixed_kind = {dq4windowtext.FIXED_KIND}\n!wt_safe = ${dq4windowtext.SAFE:04X}\n')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'main.asm').write_text(defs + (HERE / 'dq4windowname.asm').read_text())
        (tmp / 'rom.sfc').write_bytes(bytes(d))
        sym = os.environ.get('DQ4_WINDOWNAME_SYMBOLS')
        extra = ['--symbols=wla', f'--symbols-path={sym}'] if sym else []
        r = subprocess.run([asar, '--fix-checksum=off', *extra, str(tmp / 'main.asm'), str(tmp / 'rom.sfc')],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'asar: {r.stdout}{r.stderr}')
        out = (tmp / 'rom.sfc').read_bytes()
    if not any(out[lorom(CODE):lorom(CODE_END)]) or any(out[lorom(CODE_END):lorom(CODE_END) + 0x100]):
        raise ValueError('창 이름 코드가 정해 둔 자리를 벗어남')
    return out
