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
NMI_STUB = 0x00FFA1               # NMI 00:887C 가 들르는 받침(JML WqNmiEntry, 이어서 JMP ($1944))
# 이름 하나를 04:B79B 로 찍는 「누구」 고르기 창(본문에 D0 자리 표시). 이름 칸 5칸을 담게 한 칸 왼쪽으로 옮겨 넓힌다.
# 오른쪽에는 이어서 열리는 창(도구·주문 목록 등)이 붙어 있어 오른쪽으로는 넓히지 않는다.
NAME_LISTS = (0x0C, 0x0E, 0x11, 0x13, 0x2C, 0x36, 0x38, 0x3D, 0x4A, 0x4F, 0x6F, 0x7A, 0x7F)
# 주문 목록 창(본문 00 81 FE D6 FF). 다섯 글자 칸을 한글 일곱 칸으로 오른쪽으로 넓힌다.
SPELL_WINDOW = 0x28
# 전투 작전 창(머리 17 82 06 05). 두 줄 한글(줄마다 다섯 칸까지)이 들어가게 한 칸 왼쪽으로 옮겨 넓힌다
TACTIC_WINDOW = 0x16
# 가게 동료 창(머리 02 0F 1C, 줄마다 이름 EF + 상태 CC). 이름 다섯째 칸 뒤로 상태를 미는 만큼 한 칸 왼쪽으로 옮겨 넓힌다
SHOP_MEMBERS = 0x3A
# 대열 바꾸기 창(46 왼쪽 DF 줄, 45 오른쪽 F1 줄). 줄마다 「번호 이름 Lv:」 라 이름 다섯째 칸 뒤로 미는 만큼 한 칸씩 넓힌다.
# 46 은 왼쪽으로 옮기고 45 는 오른쪽으로만 넓혀 둘이 겹치지 않게 한다
FORMATION = ((0x46, bytes((0x42, 0x04, 0x0E)), True), (0x45, bytes((0x10, 0x84, 0x0E)), False))
# 「HP와 MP」 창(03 은 앞 세 사람, 04 는 넷째부터). 너비가 한 사람 몫(6)이라 이름 다섯째 칸이 열 사이 빈칸에 걸치고,
# 맨 오른쪽 사람은 오른쪽 테두리를 덮었다. 상태 창처럼 한 사람 몫을 7 로
HP_WINDOWS = (0x03, 0x04)
# 가나 이름(몬스터 동료 등)의 바이트 → 글리프 번호 표(평 · 탁점 84 · 반탁점 83, 바이트마다 16비트, FFFF = 없음).
# 필드에서는 가나 칸을 슬롯으로 돌려 써 원래 가나 타일로 찍은 이름이 깨지므로, 한글 이름처럼 Galmuri9 가나로 그린다
KANA_TABLE = 0x60E800
EMPTY_SLOT_HOOK = 0x04B9EB        # 모험의 서 기록 목록의 빈 칸 「 しようしていません」 을 한 글자씩 찍는 고리
PREFIX_HOOK = 0x04B11E            # 창 바이트 갈래(메뉴 패치가 JSL 로 바꿔 둔 자리). 고정 문구 접두를 먼저 가른다


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def kana_glyphs(d, font, render):
    """가나 글자 글리프를 이름 글리프 뒤(dq4nameentry.GLYPHS 다음 번호)에 쓰고, 바이트 → 번호 표를 KANA_TABLE 에 쓴다."""
    import sys
    import dq4nameentry as ne
    tools = str(HERE.parents[1] / 'dq5' / 'tools')
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(d))
    table = bytearray(b'\xff' * 0x300)
    numbers = {}
    for k, prefix in enumerate(((), (0x84,), (0x83,))):
        for b in range(0x10, 0x80):
            try:
                ch = dq5text.text(dq5text.string_codes(rom, bytes(prefix + (b,))))
            except Exception:
                continue
            if len(ch) != 1 or not 0x3041 <= ord(ch) <= 0x30FC:
                continue
            n = numbers.setdefault(ch, len(ne.GLYPHS) + len(numbers))
            table[k * 0x100 + b * 2:k * 0x100 + b * 2 + 2] = n.to_bytes(2, 'little')
    for ch, n in numbers.items():
        cols = render(font, ch, True)
        if len(cols) > 2:
            raise ValueError(f'{ch}: 가나 글자가 두 열을 넘음')
        cols += [[[0] * 8 for _ in range(16)]] * (2 - len(cols))
        cell = b''.join(bytes(int(''.join(map(str, r)), 2) for r in col) for col in cols)
        o = lorom((ne.GLYPH_BANK + n // 1024) << 16 | 0x8000 + n % 1024 * 32)
        if any(d[o:o + 32]):
            raise ValueError(f'가나 글리프 {n} 자리가 비어 있지 않음')
        d[o:o + 32] = cell
    o = lorom(KANA_TABLE)
    if any(d[o:o + len(table)]):
        raise ValueError(f'{KANA_TABLE:06X} 가 비어 있지 않음')
    d[o:o + len(table)] = table
    return numbers


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
    for w in HP_WINDOWS:
        o = lorom(dq4menupatch.window_addr(d, w))
        if d[o + 2] & 0x1F != 6 or d[o + 4:o + 6] != bytes((0x00, 0x89 if w == 4 else 0x8B)):
            raise ValueError(f'창 {w:02X} 머리 {d[o:o + 8].hex()}: HP와 MP 창 모양이 아님')
        d[o + 2] += 1
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
    o = lorom(dq4menupatch.window_addr(d, SHOP_MEMBERS))
    if d[o:o + 3] != bytes((0x02, 0x0F, 0x1C)) or bytes((0xEF, 0xCC)) not in d[o:o + 12]:
        raise ValueError(f'창 {SHOP_MEMBERS:02X} 머리 {d[o:o + 12].hex()}: 가게 동료 창 모양이 아님')
    d[o] -= 1
    d[o + 2] += 1
    for w, head, left in FORMATION:
        o = lorom(dq4menupatch.window_addr(d, w))
        if d[o:o + 3] != head:
            raise ValueError(f'창 {w:02X} 머리 {d[o:o + 8].hex()}: 대열 바꾸기 창 모양이 아님')
        d[o] -= left
        d[o + 2] += 1
    o = lorom(dq4menupatch.window_addr(d, TACTIC_WINDOW))
    if d[o:o + 4] != bytes((0x17, 0x82, 0x06, 0x05)):
        raise ValueError(f'창 {TACTIC_WINDOW:02X} 머리 {d[o:o + 8].hex()}: 전투 작전 창 모양이 아님')
    d[o] -= 1
    d[o + 2] += 1
    hi_count = -(-len(ne.GLYPHS) // ne.CODE_RADIX)
    font = font or dq4menupatch.Font('galmuri9')
    text, _ = dq4windowtext.build(d, font)
    records, numbers = dq4windowtext.fixed_records(d, font)
    for o, rec in records:
        d[o:o + len(rec)] = rec
    eo = lorom(EMPTY_SLOT_HOOK)
    if d[eo:eo + 12] != bytes.fromhex('a20900bdfbb92035b2ca10f7'):
        raise ValueError(f'{EMPTY_SLOT_HOOK:06X}: 빈 기록 칸 고리가 아님')
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
    kana = kana_glyphs(d, font or dq4menupatch.Font('galmuri9'), dq4menupatch.render)
    flag = re.search(r'^!flag\s*=\s*\$([0-9A-Fa-f]{6})', (HERE / 'dq4nameentry.asm').read_text(), re.M).group(1)
    defs = (f'!wn_code = ${CODE:06X}\n!wn_hi_base = ${ne.HI_BASE:02X}\n!wn_hi_count = {hi_count}\n'
            f'!wn_glyph_bank = ${ne.GLYPH_BANK:02X}\n!wn_list_prev = ${int.from_bytes(d[o + 1:o + 4], "little"):06X}\n'
            f'!wn_menu_flag = ${flag}\n!wt_bank = ${dq4windowtext.TEXT_BANK:02X}\n'
            f'!wt_prefix_prev = ${int.from_bytes(d[po + 1:po + 4], "little"):06X}\n'
            f'!wt_fixed = ${dq4windowtext.FIXED_PREFIX:02X}\n!wt_fixed_kind = {dq4windowtext.FIXED_KIND}\n!wt_safe = ${dq4windowtext.SAFE:04X}\n'
            f'!wt_tactic = {dq4windowtext.tactic_first()}\n!wt_tactic_count = {len(dq4windowtext.TACTIC_LINES)}\n'
            f'!wn_kana_table = ${KANA_TABLE:06X}\n!wt_empty_slot = {numbers[dq4windowtext.EMPTY_SLOT]}\n')
    del kana
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
