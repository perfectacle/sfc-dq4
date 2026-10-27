"""창 글자 한글 표(dq4windowname.asm 의 WnText). dq4windowname.apply 가 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자」.

롬의 이름 표(21:955D, BRK 88 2B 가 읽는 표)를 일본어 이름으로 nds/dq4/tables/adopt.tsv 의 DS 일본어와 잇고, 맞는 이름만
Galmuri9 그림으로 바꾼다. 번호가 아니라 이름으로 잇는 것은 DQ4 데이터를 옮겨 번호가 바뀌어도 그대로 쓰기 위해서다.
맞지 않는 이름은 표에 넣지 않아 원래 가나로 찍힌다.

뱅크 TEXT_BANK:
  8000 + 종류 × 200  이름 번호 256개 × 16비트: 그림의 뱅크 안 주소, 0 = 없음. 종류 FIXED_KIND 는 창 고정 문구
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
# 이름 표 번호 → (adopt.tsv 의 표, 창 이름 칸의 최대 열 수, 넘으면 멈출지). 주문 창(28)은 두 칸 넓혀 일곱 칸이고,
# 그보다 긴 이름(몬스터 특기 「얼어붙은 눈보라」)은 가나로 둔다.
KINDS = {5: ('아이템', 10, True), 3: ('주문·특기', 7, False)}
SHIFT = 6                       # render 의 띠(한글 윗줄 = 1줄)를 위 줄 7줄로 내림

# 창 레코드의 가나 항목을 접두 9E k(고정 문구 k)로 바꾼다. 이름 표가 쓰지 않는 종류 7 에 그림을 둔다.
FIXED_KIND = 7
FIXED_PREFIX = 0x9E
# 창 번호 → 오른쪽으로 넓힐 칸 수. 명령 창은 한 항목이 네 칸이라 adopt.tsv 의 긴 이름(「강한 정도」·「조사하다」)
# 대신 두 자 낱말로 줄였다. 「どうする」 창은 「건네기」 석 자가 들어가게 한 칸 넓힌다.
FIXED_WINDOWS = {0x01: 0, 0x10: 1}
FIXED = {
    'はなす': '대화', 'じゅもん': '주문', 'つよさ': '강함', 'どうぐ': '도구',
    'そうび': '장비', 'さくせん': '작전', 'とびら': '문', 'しらべる': '조사',
    'つかう': '쓰기', 'わたす': '건네기', 'すてる': '버리기',
}


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


def fixed_records(data, font):
    """FIXED_WINDOWS 의 창 레코드를 고쳐 쓴 [(파일 자리, 새 바이트)]와 문구 번호 {일본어: k}.
    항목 머리 FE 바로 뒤의 가나 n 칸과 그 뒤 빈칸 s 개를 9E k 와 빈칸 (n + s + 넓힘 − 한글 열 수) 개로 바꿔, 뒤 항목의 열 자리와
    04:B0F0 의 칸 셈($0ADE)을 원래와 같게 둔다."""
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    numbers = {jp: k for k, jp in enumerate(FIXED)}
    out = []
    for w, widen in FIXED_WINDOWS.items():
        addr, rec = dq5text.window(rom, w)
        start = rec.index(0xFE)
        new = bytearray(rec[:start])
        i = start
        while i < len(rec):
            b = rec[i]
            if not (0x02 <= b < 0xB0 and rec[i - 1] == 0xFE):
                new.append(b)
                i += 1
                continue
            j, n = i, 0
            while j < len(rec) and (0x02 <= rec[j] < 0xB0):
                j += 2 if rec[j] in (0x83, 0x84) else 1
                n += 1
            jp = dq5text.text(dq5text.string_codes(rom, rec[i:j]))
            if jp not in numbers:
                raise ValueError(f'창 {w:02X}: 「{jp}」 의 한글 문구가 없음')
            s = 0
            while j + s < len(rec) and rec[j + s] == 0x01:
                s += 1
            last = j + s >= len(rec) or rec[j + s] == 0xFF
            room = n + s + (widen if last else 0)
            m = len(columns(font, FIXED[jp]))
            if m > room:
                raise ValueError(f'창 {w:02X}: 「{FIXED[jp]}」 {m}열, 자리 {room}열')
            new += bytes((FIXED_PREFIX, numbers[jp])) + b'\x01' * (n + s - m)
            i = j + s
        if len(new) > len(rec):
            raise ValueError(f'창 {w:02X}: 고친 레코드가 원래보다 김')
        new[2] += widen
        o = ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)
        if bytes(data[o:o + len(rec)]) != rec:
            raise ValueError(f'창 {w:02X}: 레코드 자리가 어긋남')
        out.append((o, bytes(new) + b'\xff' * (len(rec) - len(new))))
    return out, numbers


def build(data, font):
    """뱅크 TEXT_BANK 의 8000~ 에 넣을 바이트와, 종류마다 (이름 수, 한글로 바꾼 수)."""
    index = bytearray(DATA - INDEX)
    body = bytearray()
    report = {}
    for jp, k in {jp: k for k, jp in enumerate(FIXED)}.items():
        cols = columns(font, FIXED[jp])
        at = DATA + len(body)
        index[FIXED_KIND * 0x200 + k * 2:FIXED_KIND * 0x200 + k * 2 + 2] = at.to_bytes(2, 'little')
        body += bytes((len(cols),)) + b''.join(cols)
    report[FIXED_KIND] = (len(FIXED), len(FIXED))
    for kind, (table, limit, strict) in KINDS.items():
        korean = adopted(table)
        names = rom_names(data, kind)
        done = 0
        for n, name in enumerate(names):
            ko = korean.get(kana_key(name))
            if not ko:
                continue
            cols = columns(font, ko)
            if len(cols) > limit:
                if strict:
                    raise ValueError(f'{ko!r}: {len(cols)}열, 창은 {limit}열')
                continue
            at = DATA + len(body)
            index[kind * 0x200 + n * 2:kind * 0x200 + n * 2 + 2] = at.to_bytes(2, 'little')
            body += bytes((len(cols),)) + b''.join(cols)
            done += 1
        report[kind] = (len(names), done)
    if DATA + len(body) > 0x10000:
        raise ValueError('창 글자 그림이 뱅크 하나를 넘음')
    return bytes(index + body), report
