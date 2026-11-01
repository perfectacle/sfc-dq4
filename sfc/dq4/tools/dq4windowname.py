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
SPELL_BODY = bytes((0x00, 0x81, 0xFE, 0xD6, 0xFF))
# 전투 작전 창(머리 17 82 06 05). 두 줄 한글(줄마다 다섯 칸까지)이 들어가게 한 칸 왼쪽으로 옮겨 넓힌다
TACTIC_WINDOW = 0x16
TACTIC_HEAD = bytes((0x17, 0x82, 0x06, 0x05))
# 가게 동료 창(머리 02 0F 1C, 줄마다 이름 EF + 상태 CC). 이름 다섯째 칸 뒤로 상태를 미는 만큼 한 칸 왼쪽으로 옮겨 넓힌다
SHOP_MEMBERS = 0x3A
SHOP_MEMBERS_HEAD, SHOP_MEMBERS_ROW = bytes((0x02, 0x0F, 0x1C)), bytes((0xEF, 0xCC))
# 대열 바꾸기 창(46 왼쪽 DF 줄, 45 오른쪽 F1 줄). 줄마다 「번호 이름 Lv:」 라 이름 다섯째 칸 뒤로 미는 만큼 한 칸씩 넓힌다.
# 46 은 왼쪽으로 옮기고 45 는 오른쪽으로만 넓혀 둘이 겹치지 않게 한다
FORMATION = ((0x46, bytes((0x42, 0x04, 0x0E)), True), (0x45, bytes((0x10, 0x84, 0x0E)), False))
# 「HP와 MP」 창(03 은 앞 세 사람, 04 는 넷째부터). 너비가 한 사람 몫(6)이라 이름 다섯째 칸이 열 사이 빈칸에 걸치고,
# 맨 오른쪽 사람은 오른쪽 테두리를 덮었다. 상태 창처럼 한 사람 몫을 7 로
HP_WINDOWS = (0x03, 0x04)
HP_BODY = {0x03: bytes((0x00, 0x8B)), 0x04: bytes((0x00, 0x89))}
# 가나 이름(몬스터 동료 등)의 바이트 → 글리프 번호 표(평 · 탁점 84 · 반탁점 83, 바이트마다 16비트, FFFF = 없음).
# 필드에서는 가나 칸을 슬롯으로 돌려 써 원래 가나 타일로 찍은 이름이 깨지므로, 한글 이름처럼 Galmuri9 가나로 그린다
KANA_TABLE = 0x60E800
EMPTY_SLOT_HOOK = 0x04B9EB        # 모험의 서 기록 목록의 빈 칸 「 しようしていません」 을 한 글자씩 찍는 고리
EMPTY_SLOT_ORIG = bytes.fromhex('a20900bdfbb92035b2ca10f7')
PREFIX_HOOK = 0x04B11E            # 창 바이트 갈래(메뉴 패치가 JSL 로 바꿔 둔 자리). 고정 문구 접두를 먼저 가른다
# 가게 사기 목록(창 39). 줄마다 이름(EE) + 빈칸 셋 + 값 다섯 자리(CB). 빈칸 하나를 값 뒤 「G」(타일 0F, 골드 창 05 와 같은 글자)로
SHOP_BUY = 0x39
SHOP_BUY_ROW = (bytes.fromhex('feee010101cbff'), bytes.fromhex('feee0101cb0fff'))
# 가게 팔기 목록은 창 37(창 0F 의 별칭, 89 02 0F). 창 0F 는 필드 도구 창 등과 함께 쓰고 37 은 맡기는 곳도 열므로, 별칭을 푸는
# 세 자리(창 열기·그리기·크기 셈의 LDA $EB48,X)에서 가게일 때만 값 열이 붙은 레코드로 바꾼다(dq4windowname.asm ShopListRes)
SHOP_SELL_ALIAS = 0x37
SHOP_SELL_ITEMS = 0x0F
SHOP_SELL_ALIAS_RECORD = bytes((0x89, 0x02, SHOP_SELL_ITEMS))
SHOP_SELL_ITEMS_SHAPE = bytes.fromhex('4f03b90081fed3ff83')
SHOP_RESOLVE = (0x049C5C, 0x049FBB, 0x04A8C2)
SHOP_RESOLVE_ORIG = bytes.fromhex('bd48eb')
SHOP_SPOT, SHOP_SPOT_END = 0x04FF40, 0x050000
# 줄 물건의 파는 값 + G 를 찍는 자리 표시. 원래 DQ5 디버그 창 6C 만 쓰던 코드인데 메뉴 패치가 6C 를 다시 써 쓰는 창이 없어,
# 그 갈래(04:B3A2 표)를 빌린다. 값 다섯 자리 + G 여섯 칸에 「판매불가」 도 들어가야 한다
SHOP_PRICE_COLS = 6
SHOP_SELL_CODE = 0xD9
CODE_TABLE = 0x04B3A2
SHOP_SELL_CODE_ORIG = bytes.fromhex('46b9')
# 가게 동료 창(3A)의 「소지 중」 을 고르는 두 자리(장비류 04:C3B1, 도구 04:C508). LDY #$000A / BRL $C440 을 그 사람
# 소지품에서 고른 물건($0F22)의 개수를 센 「 N개 소지」 로(dq4windowname.asm ShopHeldCount)
HELD_SITES = (0x04C3B1, 0x04C508)
HELD_ORIG, HELD_PICKER = bytes.fromhex('a00a0082'), 0x04C440
# 가게 사기에서 값을 $0F28~ 에 두는 두 자리(도구·장비 갈래, STA $0F28 / LDA $47 / STA $0F29 / LDA $48 / STA $0F2A). 이어지는 06:F5E9 가
# 돈을 빼기 전에 확인을 묻는다. 확인 메시지는 원작에서 빈 묶음 064~067(dq4sysmsg)
BUY_SITES, BUY_ORIG = (0x06DCDF, 0x06DDFC), bytes.fromhex('8d280fa5478d290fa5488d2a0f')
BUY_CALL = bytes.fromhex('20e9f5')
# ShopBuyConfirm 이 부르는 원래 코드: 06:F602 돈 견주기, 06:DC2F 물건 목록(LDA #$01 / JSR $DFC4)
BUY_CONFIRM_ORIG = ((0x06F602, bytes.fromhex('008849')), (0x06DC2F, bytes.fromhex('a90120c4df')),
                    (0x06DFC4, bytes.fromhex('c904')))
BUY_ASK = 0x19                    # 메시지 묶음(06:DFC4 의 A, 메시지 = A × 4 + 가게 종류)
BUY_SPOT, BUY_SPOT_END = 0x06FFB0, 0x070000
# 도구 갈래의 개수 묻기와 나머지 개수 주기(06:FE10~ 대화 훅 뒤의 빈자리)
QTY_SPOT, QTY_SPOT_END = 0x06FE64, 0x06FF00
GIVE_SITE, GIVE_ORIG = 0x06DD39, bytes.fromhex('ad230f8542ad220f8543')
GIVE_TAIL = bytes.fromhex('00898030')
# 가게 BRK 를 부르는 도우미(가진 개수·최대 개수·합계). 뱅크 40 아래여야 BRK 가 WRAM 을 읽는다. 원래 롬도 빈 05 끝
LOW_SPOT, LOW_SPOT_END = 0x05FF00, 0x060000
# 가게 팔기 개수: 값 셈(06:DF06)과 물건 빼기 앞(06:DF35), 코드는 원래 롬도 빈 12 끝
SELL_QTY_SITE, SELL_QTY_ORIG = 0x06DF06, bytes.fromhex('ad220f8542225bdf06')
SELL_GIVE_SITE, SELL_GIVE_ORIG = 0x06DF35, bytes.fromhex('ad210f8542ad230f854300898032')
# 수 창 위·아래의 다음 숫자 셈(LDA $0AFE,X / INC·DEC / CMP / BCC·BCS / LDA). 가게 개수 창에서만 1~최대로 돌린다
QTY_UP_SITE, QTY_UP_ORIG = 0x04C970, bytes.fromhex('bdfe0a1ac90c9002a902')
QTY_DOWN_SITE, QTY_DOWN_ORIG = 0x04C995, bytes.fromhex('bdfe0a3ac902b002a90b')
# 팔기에서 고른 뒤 050 「{I} 말이죠. 잠깐만」(LDA #$14 / JSR $DFC4 / BRK 97 13). 건넌다
SELL_ASK_SITE, SELL_ASK_ORIG = 0x06DEFE, bytes.fromhex('a91420c4df009713')
# 팔기 「아니요」(BRK 95 00 / LDA #$18 / JSR $DFC4, 뒤는 06:DF50 사기/팔기 창)
SELL_NO_SITE, SELL_NO_ORIG = 0x06DF48, bytes.fromhex('009500a91820c4df')
SELL_SPOT, SELL_SPOT_END = 0x12FEB0, 0x130000
# 개수를 묻는 수 창(다섯 자리 입력, 맡기는 곳 등과 함께 씀)
QTY_WINDOW = 0x5C
QTY_RECORD = bytes.fromhex('16050823000101fdfdfdfdfdff52')


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
    import dq4battlemsg
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
        if d[o + 2] & 0x1F != 6 or d[o + 4:o + 6] != HP_BODY[w]:
            raise ValueError(f'창 {w:02X} 머리 {d[o:o + 8].hex()}: HP와 MP 창 모양이 아님')
        d[o + 2] += 1
    for w in NAME_LISTS:
        o = lorom(dq4menupatch.window_addr(d, w))
        if d[o + 2] & 0x1F not in (8, 9) or d[o] & 0x1F == 0 or 0xD0 not in d[o + 4:o + 10]:
            raise ValueError(f'창 {w:02X} 머리 {d[o:o + 10].hex()}: 누구 고르기 창 모양이 아님')
        d[o] -= 1
        d[o + 2] += 1
    o = lorom(dq4menupatch.window_addr(d, SPELL_WINDOW))
    if d[o + 2] & 0x1F != 8 or d[o + 4:o + 9] != SPELL_BODY:
        raise ValueError(f'창 {SPELL_WINDOW:02X} 머리 {d[o:o + 9].hex()}: 주문 목록 창 모양이 아님')
    d[o + 2] += 2
    o = lorom(dq4menupatch.window_addr(d, SHOP_MEMBERS))
    if d[o:o + 3] != SHOP_MEMBERS_HEAD or SHOP_MEMBERS_ROW not in d[o:o + 12]:
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
    if d[o:o + 4] != TACTIC_HEAD:
        raise ValueError(f'창 {TACTIC_WINDOW:02X} 머리 {d[o:o + 8].hex()}: 전투 작전 창 모양이 아님')
    d[o] -= 1
    d[o + 2] += 1
    o = lorom(dq4menupatch.window_addr(d, SHOP_BUY))
    shop_w = d[o + 2] & 0x1F
    if d[o + 6:o + 13] != SHOP_BUY_ROW[0]:
        raise ValueError(f'창 {SHOP_BUY:02X} 레코드 {d[o:o + 14].hex()}: 가게 사기 목록 모양이 아님')
    d[o + 6:o + 13] = SHOP_BUY_ROW[1]
    sell = dq4menupatch.window_addr(d, SHOP_SELL_ALIAS)
    if d[lorom(sell):lorom(sell) + 3] != SHOP_SELL_ALIAS_RECORD:
        raise ValueError(f'창 {SHOP_SELL_ALIAS:02X} 레코드 {d[lorom(sell):lorom(sell) + 3].hex()}: 창 0F 별칭이 아님')
    o = lorom(dq4menupatch.window_addr(d, SHOP_SELL_ITEMS))
    # 너비(셋째 바이트)는 다른 단계가 이름 칸에 맞춰 넓힌다
    if d[o:o + 2] + d[o + 3:o + 10] != SHOP_SELL_ITEMS_SHAPE:
        raise ValueError(f'창 {SHOP_SELL_ITEMS:02X} 레코드 {d[o:o + 10].hex()}: 물건 목록 모양이 아님')
    for a in SHOP_RESOLVE:
        if d[lorom(a):lorom(a) + 3] != SHOP_RESOLVE_ORIG:
            raise ValueError(f'{a:06X}: LDA $EB48,X 가 아님')
    o = lorom(CODE_TABLE) + (SHOP_SELL_CODE - 0xB0) * 2
    if d[o:o + 2] != SHOP_SELL_CODE_ORIG:
        raise ValueError(f'코드 {SHOP_SELL_CODE:02X} 갈래 {d[o:o + 2].hex()}: 04:B946 이 아님')
    for a in BUY_SITES:
        if d[lorom(a):lorom(a) + len(BUY_ORIG) + 3] != BUY_ORIG + BUY_CALL:
            raise ValueError(f'{a:06X}: 가게 사기 값 저장 + JSR $F5E9 가 아님')
    for a, want in BUY_CONFIRM_ORIG:
        if d[lorom(a):lorom(a) + len(want)] != want:
            raise ValueError(f'{a:06X}: 가게 사기 확인이 부르는 코드가 아님')
    if any(d[lorom(BUY_SPOT):lorom(BUY_SPOT_END - 1) + 1]):
        raise ValueError(f'{BUY_SPOT:06X}~ 가 비어 있지 않음')
    for a, orig in ((SELL_QTY_SITE, SELL_QTY_ORIG), (SELL_GIVE_SITE, SELL_GIVE_ORIG), (SELL_NO_SITE, SELL_NO_ORIG),
                    (SELL_ASK_SITE, SELL_ASK_ORIG),
                    (QTY_UP_SITE, QTY_UP_ORIG), (QTY_DOWN_SITE, QTY_DOWN_ORIG)):
        if d[lorom(a):lorom(a) + len(orig)] != orig:
            raise ValueError(f'{a:06X}: 가게 팔기 자리가 아님 {d[lorom(a):lorom(a) + len(orig)].hex()}')
    if any(d[lorom(SELL_SPOT):lorom(SELL_SPOT_END - 1) + 1]):
        raise ValueError(f'{SELL_SPOT:06X}~ 가 비어 있지 않음')
    if any(d[lorom(LOW_SPOT):lorom(LOW_SPOT_END - 1) + 1]):
        raise ValueError(f'{LOW_SPOT:06X}~ 가 비어 있지 않음')
    if any(d[lorom(QTY_SPOT):lorom(QTY_SPOT_END - 1) + 1]):
        raise ValueError(f'{QTY_SPOT:06X}~ 가 비어 있지 않음')
    if d[lorom(GIVE_SITE):lorom(GIVE_SITE) + 14] != GIVE_ORIG + GIVE_TAIL:
        raise ValueError(f'{GIVE_SITE:06X}: 도구 주기가 아님')
    o = lorom(dq4menupatch.window_addr(d, QTY_WINDOW))
    if d[o:o + 14] != QTY_RECORD:
        raise ValueError(f'창 {QTY_WINDOW:02X} {d[o:o + 14].hex()}: 다섯 자리 입력 창이 아님')
    for a in HELD_SITES:
        o = lorom(a)
        if d[o:o + 4] != HELD_ORIG or o + 6 + int.from_bytes(d[o + 4:o + 6], 'little', signed=True) != lorom(HELD_PICKER):
            raise ValueError(f'{a:06X} {d[o:o + 6].hex()}: 「소지 중」 고르기가 아님')
    if any(d[lorom(SHOP_SPOT):lorom(SHOP_SPOT_END - 1) + 1]):
        raise ValueError(f'{SHOP_SPOT:06X}~ 가 비어 있지 않음')
    hi_count = -(-len(ne.GLYPHS) // ne.CODE_RADIX)
    font = font or dq4menupatch.Font('galmuri9')
    cannot = dq4windowtext.FIXED[dq4windowtext.CANNOT_SELL]
    if len(dq4windowtext.columns(font, cannot)) > SHOP_PRICE_COLS:
        raise ValueError(f'「{cannot}」 이 값 칸 {SHOP_PRICE_COLS}열을 넘음')
    text, _ = dq4windowtext.build(d, font)
    records, numbers = dq4windowtext.fixed_records(d, font)
    for o, rec in records:
        d[o:o + len(rec)] = rec
    held = [numbers[k] for k in dq4windowtext.HELD_COUNT]
    if held != list(range(held[0], held[0] + len(held))):
        raise ValueError(f'「N개 소지」 문구 번호가 이어지지 않음: {held}')
    eo = lorom(EMPTY_SLOT_HOOK)
    if d[eo:eo + 12] != EMPTY_SLOT_ORIG:
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
            f'!wn_kana_table = ${KANA_TABLE:06X}\n!wt_empty_slot = {numbers[dq4windowtext.EMPTY_SLOT]}\n'
            f'!wt_cannot_sell = {numbers[dq4windowtext.CANNOT_SELL]}\n!shop_sell_alias = ${sell & 0xFFFF:04X}\n'
            f'!shop_sell_code = ${SHOP_SELL_CODE:02X}\n!shop_sell_slot = ${CODE_TABLE + (SHOP_SELL_CODE - 0xB0) * 2:06X}\n'
            f'!shop_spot = ${SHOP_SPOT:06X}\n!shop_sell_w = {shop_w}\n!wt_held_first = {held[0]}\n'
            f'!shop_buy_ask = ${BUY_ASK:02X}\n!shop_buy_spot = ${BUY_SPOT:06X}\n'
            f'!shop_qty_spot = ${QTY_SPOT:06X}\n!shop_qty_end = ${QTY_SPOT_END:06X}\n'
            f'!shop_low_spot = ${LOW_SPOT:06X}\n!shop_low_end = ${LOW_SPOT_END:06X}\n'
            f'!shop_sell_spot = ${SELL_SPOT:06X}\n!shop_sell_end = ${SELL_SPOT_END:06X}\n')
    defs += dq4battlemsg.apply(d, font or dq4menupatch.Font('galmuri9'), dq4menupatch.render,
                               len(ne.GLYPHS) + len(kana))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'main.asm').write_text(defs + (HERE / 'dq4windowname.asm').read_text()
                                      + (HERE / 'dq4battlemsg.asm').read_text())
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
    if not any(out[lorom(SHOP_SPOT):lorom(SHOP_SPOT_END - 1) + 1]):
        raise ValueError('가게 팔기 목록 코드가 들어가지 않음')
    # 도구 갈래는 개수 묻기(QTY_SPOT 첫머리 ShopBuyTool)
    for a in (SELL_QTY_SITE, SELL_GIVE_SITE):
        t = int.from_bytes(out[lorom(a) + 1:lorom(a) + 4], 'little')
        if out[lorom(a)] != 0x22 or not SELL_SPOT <= t < SELL_SPOT_END:
            raise ValueError(f'{a:06X}: JSL 가게 팔기 코드가 아님 {out[lorom(a):lorom(a) + 4].hex()}')
    # 팔기 「아니요」 는 JMP ShopSellNo(QTY_SPOT 안)로 같은 사람의 팔기 목록에
    t = int.from_bytes(out[lorom(SELL_NO_SITE) + 1:lorom(SELL_NO_SITE) + 3], 'little') | 0x060000
    if out[lorom(SELL_NO_SITE)] != 0x4C or not QTY_SPOT <= t < QTY_SPOT_END:
        raise ValueError(f'{SELL_NO_SITE:06X}: JMP 팔기 「아니요」 가 아님')
    # 장비 갈래는 개수 1 을 두는 ShopBuyEquip(BUY_SPOT 안)을 거쳐 확인으로
    for a, lo_, hi_ in ((BUY_SITES[0], QTY_SPOT, QTY_SPOT + 1), (BUY_SITES[1], BUY_SPOT + 1, BUY_SPOT_END),
                        (GIVE_SITE, QTY_SPOT, QTY_SPOT_END)):
        t = int.from_bytes(out[lorom(a) + 1:lorom(a) + 3], 'little')
        if out[lorom(a)] != 0x20 or not lo_ & 0xFFFF <= t < (hi_ - 1 & 0xFFFF) + 1:
            raise ValueError(f'{a:06X}: 가게 사기 훅 JSR 이 아님 {out[lorom(a):lorom(a) + 3].hex()}')

    for a in SHOP_RESOLVE:
        t = int.from_bytes(out[lorom(a) + 1:lorom(a) + 3], 'little')
        if out[lorom(a)] != 0x20 or not SHOP_SPOT & 0xFFFF <= t < 0x10000:
            raise ValueError(f'{a:06X}: JSR ShopListRes 가 아님 {out[lorom(a):lorom(a) + 3].hex()}')
    o = lorom(CODE_TABLE) + (SHOP_SELL_CODE - 0xB0) * 2
    if not SHOP_SPOT & 0xFFFF <= int.from_bytes(out[o:o + 2], 'little') < 0x10000:
        raise ValueError(f'코드 {SHOP_SELL_CODE:02X} 갈래가 ShopSellPrice 가 아님')
    return out
