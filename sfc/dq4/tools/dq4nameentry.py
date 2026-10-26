"""모험의 서를 만들 때의 조합형 이름 입력(두벌식 자모 판). 루틴은 dq4nameentry.asm, 형식은 sfc/dq4/docs/dq4-menu-format.md.

DQ5 의 이름 입력 03:8B72 는 판(창 6C/6D)을 BRK 95 로 띄워 고른 칸($E8)마다 글자 바이트를 버퍼 $72~$79 에 쌓고 RTL 한다.
메뉴(7E:1BB0 = A5)에서는 이 루틴 대신 dq4nameentry.asm 의 NeKorean 이 돈다. 조합 규칙과 상태 스택은 같은 저자의
슈퍼 마리오 RPG 한글 패치 v1.3(kr-patches 저장소 sfc/super-mario-rpg/src/name_entry.asm)과 같다.

이름 글자 = 글리프 n. n < 51 은 호환 자모 U+3131~U+3163, n = 51 + k 는 KS X 1001 완성형 2,350자의 k 번째(코드 순).
저장은 글자마다 두 바이트 (85 + n // 111, 10 + n % 111). 첫 바이트 85~9A 는 원래 이름(가나 01~7E·탁점 접두 84/83)에
없는 값이라 한글 이름의 표시가 된다. 이름 끝 01·창 자리 표시 B0~·메뉴 창 접두 9F 와도 겹치지 않는다.
표시 없는 이름은 일본어로 읽는다. 첫 바이트가 10~25 였던 예전 한글 저장은 dq4namesave.py 로 바꾼다.
"""
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent

JAMO = [chr(c) for c in range(0x3131, 0x3164)]
CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
JONG = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'
JUNG_MIX = {('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ', ('ㅜ', 'ㅓ'): 'ㅝ',
            ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ', ('ㅡ', 'ㅣ'): 'ㅢ'}
JONG_MIX = {('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ', ('ㄹ', 'ㄱ'): 'ㄺ',
            ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ', ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ',
            ('ㄹ', 'ㅍ'): 'ㄿ', ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'}
KS = sorted((bytes([hi, lo]).decode('euc-kr') for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF)), key=ord)
GLYPHS = JAMO + KS + ['＊', '　']           # 이름 입력의 빈 칸 표시와 목록의 빈 글자
STAR = len(GLYPHS) - 2
MAX_CHARS = 4                         # 이름 8바이트(7E:2001~2008)
HI_BASE, LO_BASE, CODE_RADIX = 0x85, 0x10, 111
LEGACY_HI_BASE = 0x10                 # 표시 없던 예전 한글 저장의 첫 바이트
GLYPH_BANK = 0x62                     # 글리프 32바이트 × 2,403 = 뱅크 62~64(뱅크마다 1,024자)
FIELD_COL = 0xF8                      # 이름 칸 열 F8~FF(타일 2F8~2FF·3F8~3FF), 문구 열은 그 앞까지

BACK, DONE, NONE = 0xF1, 0xF2, 0xF0
ROW_CELLS = 11                        # 자모 10칸 + 오른쪽 명령 칸
LABELS = {BACK: '지우기', DONE: '끝'}
TITLE = '이름을 넣어 주세요'
# 닌텐도 한국어판(포켓몬스터 DS·3DS)과 같은 두벌식 배열. 쌍자음은 윗줄, ㅘ 같은 겹모음은 모음 둘로 넣는다.
GRID = [
    list('ㅃㅉㄸㄲㅆ') + [None, None, None] + list('ㅒㅖ'),
    list('ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ') + [BACK],
    list('ㅁㄴㅇㄹㅎㅗㅓㅏㅣ') + [None, DONE],
    list('ㅋㅌㅊㅍㅠㅜㅡ'),
]
CURSOR_START = 'ㅂ'


def code_bytes(n, hi_base=HI_BASE):
    return bytes((hi_base + n // CODE_RADIX, LO_BASE + n % CODE_RADIX))


def decode_name(data, hi_base=HI_BASE):
    """저장된 이름 8바이트 → 문자열(01 에서 끝). 한글 부호가 아닌 바이트가 있으면 ValueError."""
    out = []
    for i in range(0, 8, 2):
        if data[i] == 0x01:
            break
        hi, lo = data[i] - hi_base, data[i + 1] - LO_BASE
        n = hi * CODE_RADIX + lo
        if not (0 <= hi and 0 <= lo < CODE_RADIX and n < len(GLYPHS)):
            raise ValueError(f'한글 이름 부호가 아님: {bytes(data[:8]).hex()}')
        out.append(GLYPHS[n])
    return ''.join(out)


def board_record(atlas, old, jamo_font, prefix):
    """창 6C 자리의 판. 8점 줄 간격 창이라 글자 줄 아래에 빈 줄을 하나씩 둔다. 돌려줌: (레코드, 칸마다 키)."""
    rows, keys, width = [], [], 0
    n, k = atlas.run(TITLE)
    rows.append(b'\x01' * 6 + bytes((prefix, n, k)))
    rows.append(b'')
    width = 6 + n
    for grid in GRID:
        # 위아래 이동은 색인 ± 줄 칸 수($0AE3)라 줄마다 칸 수가 같아야 한다. 빈 칸은 FC(좌표 FF FF 인 빈 항목, 커서가
        # 건너뜀). 줄 칸 수는 04:C6E7 이 첫 항목 줄의 FE 바이트만 세므로, 첫 줄 끝에 그리지 않는 9F 00 FE 를 빈 칸만큼 둔다.
        row, cols = bytearray(), 0
        cells = grid + [None] * (ROW_CELLS - len(grid))
        for i, cell in enumerate(cells):
            if cell is None:
                row += b'\xfc\x01' if i < 10 else b'\xfc'
                cols += 2 if i < 10 else 1
                keys.append(NONE)
                continue
            if i < 10:
                n, k = atlas.run(cell, jamo_font)
                if n != 1:
                    raise ValueError(f'{cell}: 판 글자가 한 칸을 넘음')
                row += bytes((0xFE, prefix, n, k))
                cols += 2
                keys.append(JAMO.index(cell))
            else:
                n, k = atlas.run(LABELS[cell])
                row += bytes((0x01, 0xFE, prefix, n, k))
                cols += 2 + n
                keys.append(cell)
        if grid is GRID[0]:
            row += bytes((prefix, 0, 0xFE)) * cells.count(None)
        rows.append(bytes(row))
        rows.append(b'')
        width = max(width, cols)
    head = bytes((0x01, old[1], width + 2, (old[3] & 0xF0) | (len(rows) + 2), 0x00, len(rows)))
    return head + b''.join(r + b'\xff' for r in rows) + b'\x80', keys


def field_record(old, prefix):
    """창 6B(이름 칸). F3(가나 넉 자) 대신 열 F8 부터 여덟 칸. 아래 줄이 테두리가 되지 않게 높이 +1."""
    assert old[6:8] == b'\xf3\xff', old.hex()
    return bytes((old[0], old[1], 2 + 2 + 8, (old[3] & 0xF0) | ((old[3] & 0x0F) + 1), old[4], old[5],
                  prefix, 8, FIELD_COL, 0xFF))


def glyph_blob(font, render):
    """글리프마다 두 열 × 16줄 1bpp(열 0 의 16바이트, 이어서 열 1). render 는 dq4menupatch.render."""
    out = bytearray()
    for ch in GLYPHS:
        cols = render(font, ch, True)
        if len(cols) > 2:
            raise ValueError(f'{ch}: 이름 글자가 두 열을 넘음')
        cols += [[[0] * 8 for _ in range(16)]] * (2 - len(cols))
        for col in cols:
            out += bytes(int(''.join(map(str, r)), 2) for r in col)
    return bytes(out)


def navigation(keys):
    """위·아래는 같은 열에서 빈 칸을 건너뛰고 경계에서 멈춘다. 좌·우는 같은 줄 안에서 순환한다."""
    rows = len(keys) // ROW_CELLS
    tables = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        table = []
        for index, key in enumerate(keys):
            target = index
            if key != NONE:
                row, col = divmod(index, ROW_CELLS)
                for step in range(1, rows if dr else ROW_CELLS):
                    nr, nc = row + dr * step, (col + dc * step) % ROW_CELLS
                    if not 0 <= nr < rows:
                        break
                    candidate = nr * ROW_CELLS + nc
                    if keys[candidate] != NONE:
                        target = candidate
                        break
            table.append(target)
        tables.extend(table)
    return tables


def data_asm(keys, bridges):
    def db(label, values):
        values = list(values)
        return [f'{label}:'] + ['    db ' + ','.join(f'${v:02X}' for v in values[i:i + 16])
                                for i in range(0, len(values), 16)]

    def dw(label, values):
        values = list(values)
        return [f'{label}:'] + ['    dw ' + ','.join(f'${v:04X}' for v in values[i:i + 16])
                                for i in range(0, len(values), 16)]

    rest, move = [0], [0xFF]
    for j in JONG[1:]:
        pair = next((k for k, v in JONG_MIX.items() if v == j), None)
        rest.append(JONG.index(pair[0]) if pair else 0)
        move.append(CHO.index(pair[1] if pair else j))
    defs = ['; dq4nameentry.py 가 만든다', f'!ne_ks_count = {len(KS)}', f'!ne_jamo = {len(JAMO)}',
             f'!ne_star = {STAR}', f'!ne_hi_base = ${HI_BASE:02X}', f'!ne_blank_glyph = {STAR + 1}', f'!ne_glyph_bank = ${GLYPH_BANK:02X}', f'!ne_max = {MAX_CHARS}',
             f'!ne_cursor = {keys.index(JAMO.index(CURSOR_START))}', f'!ne_back = ${BACK:02X}',
             f'!ne_done = ${DONE:02X}', f'!ne_none = ${NONE:02X}', f'!ne_last = {keys.index(DONE)}']
    defs += [f'!ne_{name} = ${address:06X}' for name, address in bridges.items()]
    lines = db('NeNavigation', navigation(keys))
    lines += dw('NeKsSyl', [ord(ch) - 0xAC00 for ch in KS])
    lines += dw('NeCode', [int.from_bytes(code_bytes(n), 'little') for n in range(len(GLYPHS))])
    lines += db('NeGrid', keys)
    lines += db('NeJCho', [CHO.index(j) if j in CHO else 0xFF for j in JAMO])
    lines += db('NeJJung', [JUNG.index(j) if j in JUNG else 0xFF for j in JAMO])
    lines += db('NeJJong', [JONG.index(j) if j in JONG[1:] else 0 for j in JAMO])
    lines += db('NeChoJ', [JAMO.index(j) for j in CHO])
    lines += db('NeJungJ', [JAMO.index(j) for j in JUNG])
    lines += db('NeJongRest', rest) + db('NeJongMove', move)
    lines += db('NeJungMix', [x for (a, b), r in JUNG_MIX.items()
                              for x in (JUNG.index(a), JAMO.index(b), JUNG.index(r))] + [0xFF])
    lines += db('NeJongMix', [x for (a, b), r in JONG_MIX.items()
                              for x in (JONG.index(a), JAMO.index(b), JONG.index(r))] + [0xFF])
    return '\n'.join(defs) + '\n', '\n'.join(lines) + '\n'


def apply(rom, keys, blob, bridges, asar=None):
    """롬에 루틴·표·글리프를 asar 로 넣는다."""
    asar = asar or os.environ.get('ASAR')
    if not asar:
        raise SystemExit('ASAR 에 asar 실행 파일을 주세요(sfc/dq4/docs/dq4-menu-format.md)')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        defs, tables = data_asm(keys, bridges)
        (tmp / 'dq4nameentry-defs.asm').write_text(defs)
        (tmp / 'dq4nameentry-tables.asm').write_text(tables)
        for i in range(3):
            (tmp / f'glyphs{i}.bin').write_bytes(blob[i * 0x8000:(i + 1) * 0x8000])
        (tmp / 'main.asm').write_text((HERE / 'dq4nameentry.asm').read_text())
        (tmp / 'rom.sfc').write_bytes(rom)
        sym = os.environ.get('DQ4_NAMEENTRY_SYMBOLS')     # 실험할 때 심볼 파일(wla 꼴)을 남길 자리
        extra = ['--symbols=wla', f'--symbols-path={sym}'] if sym else []
        r = subprocess.run([asar, '--fix-checksum=off', *extra, str(tmp / 'main.asm'), str(tmp / 'rom.sfc')],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'asar: {r.stdout}{r.stderr}')
        return (tmp / 'rom.sfc').read_bytes()


def compose(keys):
    """두벌식 조합의 파이썬 기준(롬 루틴과 같은 규칙). keys = 자모 문자열. 돌려줌: 글자 목록(거절된 자모는 건너뜀)."""
    chars, stack = [], []

    def code(state):
        c, v, j = state
        if v is None:
            return JAMO.index(CHO[c])
        if c is None:
            return JAMO.index(JUNG[v])
        ch = chr(0xAC00 + (c * 21 + v) * 28 + j)
        return len(JAMO) + KS.index(ch) if ch in KS else None

    def push(state):
        if code(state) is None:
            return False
        stack.append(state)
        return True

    def commit():
        if stack:
            chars.append(code(stack[-1]))
            stack.clear()

    def start(jamo):
        state = (CHO.index(jamo), None, 0) if jamo in CHO else (None, JUNG.index(jamo), 0)
        return push(state)

    def jamo_in(jamo):
        if not stack:
            return start(jamo)
        c, v, j = stack[-1]
        if jamo not in JUNG:
            if v is None or c is None:
                commit()
                return start(jamo)
            if j:
                mix = JONG_MIX.get((JONG[j], jamo))
                if mix and push((c, v, JONG.index(mix))):
                    return True
            elif jamo in JONG and push((c, v, JONG.index(jamo))):
                return True
            commit()
            return start(jamo)
        if v is None:
            return push((c, JUNG.index(jamo), 0))
        if not j:
            mix = JUNG_MIX.get((JUNG[v], jamo))
            if mix:
                return push((c, JUNG.index(mix), 0))
            commit()
            return start(jamo)
        pair = next((k for k, x in JONG_MIX.items() if x == JONG[j]), None)
        stay = JONG.index(pair[0]) if pair else 0
        moved = CHO.index(pair[1] if pair else JONG[j])
        if code((c, v, stay)) is None or code((moved, JUNG.index(jamo), 0)) is None:
            return False
        chars.append(code((c, v, stay)))
        stack.clear()
        stack.append((moved, None, 0))
        stack.append((moved, JUNG.index(jamo), 0))
        return True

    for jamo in keys:
        saved = (list(chars), list(stack))
        if not jamo_in(jamo) or len(chars) + (1 if stack else 0) > MAX_CHARS:
            chars[:], stack[:] = saved
    return chars + ([code(stack[-1])] if stack else [])
