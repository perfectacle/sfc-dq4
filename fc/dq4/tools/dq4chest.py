"""DQ4(FC) 보물상자와 발밑 숨은 아이템. 형식은 fc/dq4/docs/dq4-shop-format.md.

사용:
  python fc/dq4/tools/dq4chest.py rom/dq4.nes G K        맵(그룹 $63/순번 $64)의 상자와 발밑 아이템
  python fc/dq4/tools/dq4chest.py rom/dq4.nes all        상자 개수 표에 있는 맵 전부와 발밑 표 전부
  python fc/dq4/tools/dq4chest.py rom/dq4.nes check      맵마다 상자 블록 칸 수가 개수 표와 같은지 전수 검사
  python fc/dq4/tools/dq4chest.py rom/dq4.nes G K --compare end.sram   seq.lua 의 SRAM 덤프($6000~)로 열었음 플래그 비교

근거 루틴(코드 읽기와 실측):
  1E:$B3FE  しらべる. 발밑 블록 종류($6F40[블록])가 04 이면 상자(1E:$B447), 아니면 발밑 표(1E:$B4DB, 표 1E:$BF59).
  08:$B4E5  상자의 맵 안 순번 = 맵 버퍼 $7800 에서 지금 칸 앞(가로 순서)에 있는 종류 04 칸의 수.
  1E:$B72E  전체 순번 = 상자 개수 표(포인터 1E:$BDBE)에서 앞선 맵들의 개수 합 + 맵 안 순번 → $6278/$6279.
  1E:$B7B2  내용물 표(포인터 1E:$BDC0)[전체 순번]. 1E:$B791 열었음 플래그 $625D + 순번 >> 3, 비트 80 >> (순번 & 7).
  08:$8710  맵 종류가 00·1E 가 아니면 맵에 안 쓰인 첫 블록($0568)에 정의 18 11(종류 04, 타일 FC~FF)을 올린다.
            열린 상자 칸은 $7800 에서 이 블록으로 바뀐다(1E:$B7CA, 로드 때 1E:$A1F3).
  블록 종류  로드 뒤 $6F40 은 dq4block 의 블록 표(08:$84E9)와 장소별 고침(08:$8A2A)으로 계산한다(fc/dq4/docs/dq4-block-format.md).
"""
import sys

from kr_patch.fc import ines

import dq4block
import dq4data
import dq4map

CHEST_KIND = 0x04              # 08:$B67F 목록(04 00)
CHEST_BANK = 0x1E
COUNT_PTR, CONTENT_PTR = 0xBDBE, 0xBDC0
FEET_TABLE = 0xBF59            # 5바이트: 그룹, 순번, X, Y, 내용. FF 로 끝남
FLAG_ITEMS = 0xBDB3            # 발밑 내용 A0~AA 의 아이템(bit7 이면 금화)
SPECIAL_CHEST = 0xBC34         # 개수, 그 뒤 특수 내용 바이트(1E:$B462)
SPECIAL_FEET = 0xBC55          # 개수, 그 뒤 특수 내용 바이트(1E:$B539)
OPENED = 0x625D                # 상자 열었음 플래그
FEET_FLAGS = 0x6272            # 발밑 A0~AA 를 주웠음 플래그


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def rw(prg, bank, addr):
    return rd(prg, bank, addr) | rd(prg, bank, addr + 1) << 8


def block_props(prg, m, buf, g, k):
    """로드 뒤의 블록 속성 $6F40(dq4block: 08:$84E9 블록 표, 08:$8710 열린 상자 블록, 08:$8A2A 장소별 고침).
    m 은 all_maps 의 맵 레코드, buf 는 해제한 $7800. 올리지 않는 블록은 빠진다."""
    t = m[2] & 0x3F
    outside = dq4map.header(prg, m[3], m[4])[4]
    blocks = dq4block.load(prg, t, dq4block.used_blocks(buf, outside))
    dq4block.patch_props(prg, blocks['prop'], g, k)
    return blocks['prop']


def chest_counts(prg):
    """[(그룹, 순번, 상자 수)] — 1E:$B741 이 앞선 맵들의 수를 더해 전체 순번을 만든다."""
    a = rw(prg, CHEST_BANK, COUNT_PTR)
    out = []
    while rd(prg, CHEST_BANK, a) != 0xFF:
        out.append(tuple(rd(prg, CHEST_BANK, a + i) for i in range(3)))
        a += 3
    return out


def chest_base(prg, g, k):
    """1E:$B741: 표에서 (그룹, 순번)이 지금 맵 이상인 첫 줄 앞까지의 합. 표에 없는 맵은 다음 맵과 같은 순번을 쓴다."""
    n = 0
    for cg, ck, c in chest_counts(prg):
        if (cg, ck) >= (g, k):
            break
        n += c
    return n


def all_maps(prg):
    """dq4map.maps 에 마지막 그룹을 더한 목록. maps 는 다음 그룹의 포인터로 맵 수를 세어 마지막 그룹(48)이 빠진다.
    마지막 그룹은 맵 번호 FF 앞까지(48/00~48/09, 뱅크 0B 에서 앞 맵의 끝에 이어짐)."""
    out = dq4map.maps(prg)
    bank, base = dq4map.GROUPS
    n = 0
    while rd(prg, bank, base + 2 * n) | rd(prg, bank, base + 2 * n + 1) << 8 != 0xFFFF:
        n += 1
    g = n - 1
    a = rw(prg, bank, base + 2 * g)
    k = 0
    while (mid := rd(prg, bank, a + 3 * k)) != 0xFF:
        out.append((g, k, mid, dq4map.data_bank(g, k), rw(prg, bank, a + 3 * k + 1)))
        k += 1
    return out


def load(prg, g, k):
    """dq4map.load 와 같되 all_maps 의 장소도 푼다. (맵 레코드, 폭, 높이, $7800 버퍼) 또는 None."""
    m = next((x for x in all_maps(prg) if x[:2] == (g, k)), None)
    if m is None:
        return None
    w, h, pb, tb, _ = dq4map.header(prg, m[3], m[4])
    return m, w, h, dq4map.decode(prg, m[3], m[4] + 3, w, h, pb, tb)


def chest_cells(prg, g, k):
    """맵 버퍼를 가로 순서로 읽어 종류 04 칸의 (X, Y). 맵이 없는 장소는 None."""
    if (got := load(prg, g, k)) is None:
        return None
    m, w, h, buf = got
    props = block_props(prg, m, buf, g, k)
    return [(i % w, i // w) for i, b in enumerate(buf) if props.get(b & 0x1F, 0) & 0x7F == CHEST_KIND]


# 1E:$BC35 특수 내용과 처리 루틴(1E:$BC3D)이 주는 것. 아이템은 루틴이 A 에 싣는 ID. 모두 워프로 열어 확인.
CHEST_SPECIAL = {
    0xFF: '빈 상자(메시지 0297, 1E:$B4CE)',
    0xFE: 'ミミック(메시지 0299, 1E:$B868)',
    0xFD: 'ひとくいばこ(메시지 029A, 1E:$B86F)',
    0xEF: 'バロンのつのぶえ, 다음 순번 상자도 열었음으로(1E:$B807)',
    0xEE: 'てつのきんこ, $627D bit3, 칸을 블록 19 로(1E:$B81B)',
    0xE3: 'やみのランプ(1E:$B9ED)',
    0xE2: 'パデキアのたね(1E:$B8F7)',
    0xE0: 'しんじるこころ(1E:$B90A)',
}
# 1E:$BC55 발밑 특수 내용과 처리 루틴(1E:$BC62). 조건은 코드 읽기, 「확인」 은 1장 세이브스테이트에서 워프로 실측.
FEET_SPECIAL = {
    0xE1: 'かわきのいし, $6277 bit4 (1E:$B930)',
    0xE4: '$628A bit1 일 때 이벤트(1E:$B9B1)',
    0xE5: '위를 보면 50G, $6277 bit0 (1E:$B97D)',
    0xE6: '위를 보면 やくそう, $6277 bit1 (1E:$B964)',
    0xE7: '위를 보면 かわのよろい, $6277 bit2 (1E:$B94B)',
    0xE8: '$6286 bit1 일 때 さえずりのみつ(1E:$B8DD)',
    0xE9: '위를 보면 すばやさのたね, $6277 bit3 (1E:$B917)',
    0xEA: '메시지 02A7(1E:$B8D5, 표에 쓰는 곳 없음)',
    0xEC: '오른쪽을 보고 이벤트(1E:$B8AD)',
    0xED: '위를 보고 $627D bit2 일 때 이벤트(1E:$B87C)',
    0xEE: 'てつのきんこ 이벤트(예·아니오, $627D bit3 을 끄고 칸을 블록 03 으로, 1E:$B830)',
    0xF1: '5장이면 ふしぎなきのみ, $6277 bit5 (1E:$B9D1)',
}


def content_name(prg, c, special):
    """내용 바이트: bit7 0 이면 아이템 ID(1E:$B3EA), 특수 목록에 있으면 특수, 아니면 금화 (c & 7F) × 40(1E:$B47F)."""
    names = dq4data.items(prg)
    if c < 0x80:
        return names[c][1] if c < len(names) else f'아이템 {c:02X}'
    if c in special:
        return CHEST_SPECIAL.get(c, f'특수 {c:02X}')
    return f'{(c & 0x7F) * 40}G'


def special_codes(prg, at):
    n = rd(prg, CHEST_BANK, at)
    return {rd(prg, CHEST_BANK, at + 1 + i) for i in range(n)}


def chests(prg, g, k):
    """[(전체 순번, X, Y, 내용 바이트, 설명)]. 맵을 풀 수 없는 장소는 X·Y 가 None."""
    table = rw(prg, CHEST_BANK, CONTENT_PTR)
    base = chest_base(prg, g, k)
    special = special_codes(prg, SPECIAL_CHEST)
    cells = chest_cells(prg, g, k)
    if cells is None:
        cells = [(None, None)] * dict(((cg, ck), c) for cg, ck, c in chest_counts(prg)).get((g, k), 0)
    out = []
    for i, (x, y) in enumerate(cells):
        n = base + i
        c = rd(prg, CHEST_BANK, table + n)
        out.append((n, x, y, c, content_name(prg, c, special)))
    return out


def feet_items(prg):
    """발밑 표 1E:$BF59: [(그룹, 순번(아래 5비트), X, Y, 내용, 설명, 주웠음 플래그 (주소, 비트) 또는 None)]."""
    special = special_codes(prg, SPECIAL_FEET)
    names = dq4data.items(prg)
    out = []
    a = FEET_TABLE
    while rd(prg, CHEST_BANK, a) != 0xFF:
        g, kb, x, y, c = (rd(prg, CHEST_BANK, a + i) for i in range(5))
        flag = None
        if c < 0x80:
            desc = names[c][1]
        elif 0xA0 <= c < 0xAB:
            n = c & 0x0F
            it = rd(prg, CHEST_BANK, FLAG_ITEMS + n)
            desc = f'{(it & 0x7F) * 40}G' if it & 0x80 else names[it][1]
            flag = (FEET_FLAGS + (n >> 3), 0x80 >> (n & 7))
        elif c in special:
            desc = FEET_SPECIAL.get(c, f'특수 {c:02X}')
        else:
            desc = f'모름 {c:02X}'
        out.append((g, kb & 0x1F, x, y, c, desc, flag))
        a += 5
    return out


def opened(sram, n):
    """seq.lua 의 end.sram($6000~$7FFF)에서 상자 n 의 열었음 비트."""
    return bool(sram[OPENED - 0x6000 + (n >> 3)] & 0x80 >> (n & 7))


def check(prg):
    counts = {(g, k): c for g, k, c in chest_counts(prg)}
    bad = 0
    for m in all_maps(prg):
        g, k = m[:2]
        n = len(chest_cells(prg, g, k))
        if n != counts.get((g, k), 0):
            bad += 1
            nxt = next(((cg, ck) for cg, ck in counts if (cg, ck) > (g, k)), None)
            print(f'{g:02X}/{k:02X}: 상자 칸 {n}, 표 {counts.get((g, k), 0)}'
                  + (f' — 표에 없어 {nxt[0]:02X}/{nxt[1]:02X} 와 같은 순번' if (g, k) not in counts and nxt else ''))
    ms = {m[:2] for m in all_maps(prg)}
    missing = [f'{g:02X}/{k:02X}' for g, k in counts if (g, k) not in ms]
    print(f'맵 {len(ms)}개, 개수 표 {len(counts)}줄(상자 {sum(counts.values())}개), 다름 {bad}'
          + (f', 맵 목록에 없는 장소 {" ".join(missing)}' if missing else ''))


def cell(x, y):
    return '(?? ??)' if x is None else f'({x:02X},{y:02X})'


def show(prg, g, k, sram=None):
    for n, x, y, c, desc in chests(prg, g, k):
        tail = '' if sram is None else ('  열었음' if opened(sram, n) else '  닫힘')
        print(f'상자 #{n:3d} {cell(x, y)} {c:02X} {desc}  플래그 ${OPENED + (n >> 3):04X} 비트 {0x80 >> (n & 7):02X}{tail}')
    for fg, fk, x, y, c, desc, flag in feet_items(prg):
        if (fg, fk) == (g, k):
            f = '' if flag is None else f'  플래그 ${flag[0]:04X} 비트 {flag[1]:02X}'
            print(f'발밑 ({x:02X},{y:02X}) {c:02X} {desc}{f}')


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    a = sys.argv[2:]
    if a[0] == 'check':
        check(prg)
    elif a[0] == 'all':
        for g, k, _ in chest_counts(prg):
            print(f'# {g:02X}/{k:02X}')
            for n, x, y, c, desc in chests(prg, g, k):
                print(f'상자 #{n:3d} {cell(x, y)} {c:02X} {desc}')
        print('# 발밑')
        for g, k, x, y, c, desc, flag in feet_items(prg):
            f = '' if flag is None else f'  플래그 ${flag[0]:04X} 비트 {flag[1]:02X}'
            print(f'{g:02X}/{k:02X} ({x:02X},{y:02X}) {c:02X} {desc}{f}')
    else:
        g, k = int(a[0], 16), int(a[1], 16)
        sram = open(a[3], 'rb').read() if len(a) > 3 and a[2] == '--compare' else None
        show(prg, g, k, sram)


if __name__ == '__main__':
    main()
