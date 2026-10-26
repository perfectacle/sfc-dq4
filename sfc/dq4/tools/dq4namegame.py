"""게임 안 보행 모드 메시지에 한글 이름을 찍는다. 형식은 sfc/dq4/docs/dq4-name-entry-format.md 「게임 안 이름」.

메시지의 이름 제어 코드(1011·1012 등)는 이름 바이트를 직접 페이지 $01~ 에 두고 24:A7B6 으로 글자 코드를 만든다.
24:A7D5 의 JSR $A81E(보통 바이트 → 24:B270 표)를 아래 루틴으로 돌려, 한글 표시 바이트(85~9A)면 다음 바이트와
묶어 글자 코드 3DB + n 으로 바꾼다. 글자 그림은 dq4menumsg.py 가 넣은 묶음이다.

루틴은 메시지 디코더를 옮긴 뒤 비는 24:9E11~9E46 에 둔다(dq4menumsg.py 가 9E02~9E10 을 씀).
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4menumsg as mm  # noqa: E402
import dq4nameentry as ne  # noqa: E402
from dq5map import lorom  # noqa: E402
from dq5text import GLYPHS  # noqa: E402

NAME_BYTE_CALL = 0x24A7D5          # JSR $A81E
ROUTINE = 0x249E11
ROUTINE_END = 0x249E47
STRING_CODE = 0xA81E
PUSH_CODE = 0xA832                 # A = 글자 코드(16비트)를 7E:0ECB,Y 에 쌓음


def routine():
    """A = 이름 바이트(8비트), X = $01 기준 자리(16비트), DB = 24. 한글이면 X·$00 을 한 바이트 더 넘긴다."""
    hi_end = ne.HI_BASE + (len(ne.GLYPHS) - 1) // ne.CODE_RADIX + 1
    add = GLYPHS - ne.LO_BASE
    body = bytes((
        0x38, 0xE9, ne.HI_BASE,                # SEC / SBC #$85
        0x8D, 0x02, 0x42,                      # STA $4202
        0xA9, ne.CODE_RADIX,                   # LDA #111
        0x8D, 0x03, 0x42,                      # STA $4203   곱은 8사이클 뒤 $4216
        0xE8, 0xC6, 0x00,                      # INX / DEC $00   둘째 바이트로
        0xB5, 0x01,                            # LDA $01,X
        0xC2, 0x20, 0x29, 0xFF, 0x00,          # REP #$20 / AND #$00FF
        0x18, 0x6D, 0x16, 0x42,                # CLC / ADC $4216
        0x18, 0x69, add & 0xFF, add >> 8,      # CLC / ADC #(3DB - 10)
        0x20, PUSH_CODE & 0xFF, PUSH_CODE >> 8,
        0xE2, 0x20, 0x60))                     # SEP #$20 / RTS
    head = bytes((0xC9, ne.HI_BASE, 0x90, 4 + len(body),   # CMP #$85 / BCC 원래
                  0xC9, hi_end, 0xB0, len(body)))          # CMP #$9B / BCS 원래
    return head + body + bytes((0x4C, STRING_CODE & 0xFF, STRING_CODE >> 8))


def apply(data):
    d = bytearray(data)
    code = routine()
    if ROUTINE + len(code) > ROUTINE_END:
        raise ValueError('이름 루틴이 비운 디코더 자리를 넘음')
    o = lorom(mm.DECODER)
    if bytes(d[o:o + 4]) != bytes((0x22, *mm.cpu_to_bytes(mm.BASE))):
        raise ValueError('메시지 디코더가 옮겨지지 않은 롬')
    o = lorom(ROUTINE)
    if bytes(d[o:o + 4]) != bytes.fromhex('a7f0a4f3'):
        raise ValueError(f'{ROUTINE:06X}: 예상한 원래 바이트가 아님')
    d[o:o + len(code)] = code
    o = lorom(NAME_BYTE_CALL)
    if bytes(d[o:o + 3]) != bytes((0x20, STRING_CODE & 0xFF, STRING_CODE >> 8)):
        raise ValueError(f'{NAME_BYTE_CALL:06X}: 예상한 원래 바이트가 아님')
    d[o + 1:o + 3] = (ROUTINE & 0xFFFF).to_bytes(2, 'little')
    return bytes(d)


def message_codes(name):
    """한글 이름 → 24:A7B6 이 쌓을 글자 코드 목록(파이썬 기준)."""
    return [GLYPHS + ne.GLYPHS.index(ch) for ch in name]
