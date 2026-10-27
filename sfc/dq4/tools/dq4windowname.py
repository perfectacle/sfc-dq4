"""게임 안 일행 열 창의 한글 이름(dq4windowname.asm). dq4menupatch.build 가 dq4bg3slot 다음에 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「상태 창 이름」.

이름 칸을 4칸에서 5칸으로 넓혀 Galmuri9 한글 넉 자(40점)를 담는다. 창 02(필드 상태 창)는 일행마다 열을 되풀이하므로
머리 너비 6 → 7 과 함께 열 간격 상수(04:A394·A3A4·B18E)를 5 → 6 으로 바꾼다(asm).
"""
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

CODE = 0x60C000
CODE_END = 0x60D000
STATUS_WINDOW = 0x02


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def apply(data, asar=None):
    import dq4menupatch
    import dq4nameentry as ne
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
    hi_count = -(-len(ne.GLYPHS) // ne.CODE_RADIX)
    defs = (f'!wn_code = ${CODE:06X}\n!wn_hi_base = ${ne.HI_BASE:02X}\n!wn_hi_count = {hi_count}\n'
            f'!wn_glyph_bank = ${ne.GLYPH_BANK:02X}\n')
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
