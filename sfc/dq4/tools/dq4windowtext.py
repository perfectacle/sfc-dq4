"""창 글자 한글 표(dq4windowname.asm 의 WnText). dq4windowname.apply 가 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자」.

롬의 이름 표(21:955D, BRK 88 2B 가 읽는 표)를 일본어 이름으로 nds/dq4/tables/adopt.tsv 의 DS 일본어와 잇고, 맞는 이름만
Galmuri9 그림으로 바꾼다. 번호가 아니라 이름으로 잇는 것은 DQ4 데이터를 옮겨 번호가 바뀌어도 그대로 쓰기 위해서다.
맞지 않는 이름은 표에 넣지 않아 원래 가나로 찍힌다.

뱅크 TEXT_BANK:
  8000 + 종류 × 200  이름 번호 256개 × 16비트: 그림의 뱅크 안 주소, 0 = 없음
  9000~              [열 수][열마다 16바이트: 위 줄 8줄, 글자 줄 8줄](1bpp, bit7 = 왼쪽 점)
글자의 맨 윗줄이 위 줄 타일의 7줄째, 나머지 여덟 줄이 글자 줄에 온다(상태 창 이름과 같은 배치).
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
ADOPT = ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'

TEXT_BANK = 0x58
INDEX = 0x8000
DATA = 0x9000
# 이름 표 번호 → (adopt.tsv 의 표, 창 이름 칸의 최대 열 수)
KINDS = {5: ('아이템', 10)}
SHIFT = 6                       # render 의 띠(한글 윗줄 = 1줄)를 위 줄 7줄로 내림


def kana_key(text):
    """가타카나를 히라가나로, 빈칸을 빼서 표기 차이를 무시한다."""
    return ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in text if c not in ' 　')


def rom_names(data, table, count=256):
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    return [dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, table, n))) for n in range(count)]


def adopted(table):
    with open(ADOPT, encoding='utf-8') as f:
        return {kana_key(r['DS 일본어']): r['채택'] for r in csv.DictReader(f, delimiter='\t')
                if r['표'] == table and r['채택']}


def columns(font, text):
    """한글 문자열 → 열마다 16바이트(위 줄 8 + 글자 줄 8)."""
    import dq4menupatch
    out = []
    for col in dq4menupatch.render(font, text):
        if any(any(row) for row in col[16 - SHIFT:]):
            raise ValueError(f'{text!r}: 글자가 글자 줄 아래로 넘침')
        rows = [[0] * 8] * SHIFT + col[:16 - SHIFT]
        out.append(bytes(int(''.join(map(str, r)), 2) for r in rows))
    return out


def build(data, font):
    """뱅크 TEXT_BANK 의 8000~ 에 넣을 바이트와, 종류마다 (이름 수, 한글로 바꾼 수)."""
    index = bytearray(DATA - INDEX)
    body = bytearray()
    report = {}
    for kind, (table, limit) in KINDS.items():
        korean = adopted(table)
        names = rom_names(data, kind)
        done = 0
        for n, name in enumerate(names):
            ko = korean.get(kana_key(name))
            if not ko:
                continue
            cols = columns(font, ko)
            if len(cols) > limit:
                raise ValueError(f'{ko!r}: {len(cols)}열, 창은 {limit}열')
            at = DATA + len(body)
            index[kind * 0x200 + n * 2:kind * 0x200 + n * 2 + 2] = at.to_bytes(2, 'little')
            body += bytes((len(cols),)) + b''.join(cols)
            done += 1
        report[kind] = (len(names), done)
    if DATA + len(body) > 0x10000:
        raise ValueError('창 글자 그림이 뱅크 하나를 넘음')
    return bytes(index + body), report
