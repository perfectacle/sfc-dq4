"""DQ4(FC) 보물상자와 발밑 숨은 아이템. 형식은 docs/dq4-shop-format.md.

사용:
  python tools/dq4chest.py rom/dq4.nes G K        맵(그룹 $63/순번 $64)의 상자와 발밑 아이템
  python tools/dq4chest.py rom/dq4.nes all        상자 개수 표에 있는 맵 전부와 발밑 표 전부
  python tools/dq4chest.py rom/dq4.nes check      맵마다 상자 블록 칸 수가 개수 표와 같은지 전수 검사
  python tools/dq4chest.py rom/dq4.nes G K --compare end.sram   seq.lua 의 SRAM 덤프($6000~)로 열었음 플래그 비교
  python tools/dq4chest.py rom/dq4.nes loot [--json]   롬 전체의 「맵·자리 → 얻는 것·플래그」 표
                                                  (상자, 발밑, タンス·つぼ, 인물이 대화로 주는 것)

근거 루틴(코드 읽기와 실측):
  1E:$B3FE  しらべる. 발밑 블록 종류($6F40[블록])가 04 이면 상자(1E:$B447), 아니면 발밑 표(1E:$B4DB, 표 1E:$BF59).
  08:$B4E5  상자의 맵 안 순번 = 맵 버퍼 $7800 에서 지금 칸 앞(가로 순서)에 있는 종류 04 칸의 수.
  1E:$B72E  전체 순번 = 상자 개수 표(포인터 1E:$BDBE)에서 앞선 맵들의 개수 합 + 맵 안 순번 → $6278/$6279.
  1E:$B7B2  내용물 표(포인터 1E:$BDC0)[전체 순번]. 1E:$B791 열었음 플래그 $625D + 순번 >> 3, 비트 80 >> (순번 & 7).
  08:$8710  맵 종류가 00·1E 가 아니면 맵에 안 쓰인 첫 블록($0568)에 정의 18 11(종류 04, 타일 FC~FF)을 올린다.
            열린 상자 칸은 $7800 에서 이 블록으로 바뀐다(1E:$B7CA, 로드 때 1E:$A1F3).
  블록 종류  로드 뒤 $6F40 은 dq4block 의 블록 표(08:$84E9)와 장소별 고침(08:$8A2A)으로 계산한다(docs/dq4-block-format.md).
  15:$B0B1  대화 호출 루틴이 아이템 A 를 주는 곳(BRK 65 33 으로 빈 자리, BRK 2E 73 으로 넣음). 15:$B0C2 는 빼기
            (BRK 66 73 찾기 → BRK 30 73). BRK 4B 73 은 골드 더하기(A | $70 << 8 | $71 << 16).
  15:$A988  카지노 경품(대화 046)·メダル 왕(대화 15A): $07C5 = 1 로 그 장소의 무기 목록 줄(15:$B217)을 경품으로 쓴다.
"""
import sys

from kr_patch.fc import ines

import dq4block
import dq4data
import dq4map
import dq4talk

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
    """dq4map.maps 와 같다(마지막 그룹 48 포함)."""
    return dq4map.maps(prg)


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
    0xE4: '$628A bit1 일 때 탈옥 이벤트(메시지 03A9·03AA, $628A bit3, 주인공을 (0F,16) 으로, 1E:$B9B1)',
    0xE5: '위를 보면 50G, $6277 bit0 (1E:$B97D)',
    0xE6: '위를 보면 やくそう, $6277 bit1 (1E:$B964)',
    0xE7: '위를 보면 かわのよろい, $6277 bit2 (1E:$B94B)',
    0xE8: '$6286 bit1 이고 없으면 さえずりのみつ(1E:$B8DD)',
    0xE9: '위를 보면 すばやさのたね, $6277 bit3 (1E:$B917)',
    0xEA: '메시지 02A7(1E:$B8D5, 표에 쓰는 곳 없음)',
    0xEC: '오른쪽을 보면 アリーナ 가 벽을 걷어참(메시지 0308·0390, $627F bit1, 1E:$B8AD)',
    0xED: '위를 보고 $627D bit2 이면 벽 단추(메시지 0295, 「はい」 면 037A 벽이 열림, 1E:$B87C)',
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
    elif a[0] == 'loot':
        show_loot(prg, '--json' in a)
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


# 얻는 물건 통합 표 ------------------------------------------------------------

GIVE_ITEM, TAKE_ITEM, PRIZE_LIST = 0xB0B1, 0xB0C2, 0xA988
# 가게 처리로 들어가면 거기서 산 물건을 주는 BRK 2E 73 이 잡히므로 더 따라가지 않는다
SHOP_ENTRIES = {0x9CBF, 0xB550, 0xB558, 0xB84A, 0xB847, 0xB84D, 0xB851, 0xB858, 0xBBF0, 0xBF28, 0xBF30}
# 호출 루틴 안의 검사. 스크립트 조건(dq4talk.CONDS)과 같은 루틴을 직접 부른다
ROUTINE_CHECKS = {0x9AC9: 'yes', 0xA794: 'item {:02X}', 0x9AF8: 'party {:02X}'}
# 카지노·メダル 왕 경품: 값을 무엇으로 치르는지(15:$A8CE·$AA2F)
PRIZE_COST = {0xA898: '카지노 코인 $62AD~$62AF', 0xA9C2: 'ちいさなメダル 맡긴 수 $62A2'}
# BRK 특수 형식 x3 의 복귀 자리(docs/dq4-bank-format.md). 표에 없는 x3 은 BRK+3
X3_LEN = {0x23: 4, 0x43: 4, 0x63: 4, 0x83: 5, 0x93: 4, 0xC3: 4, 0xD3: 4}


def brk_len(b1, b2):
    if b2 & 0x0F == 0x03:
        return X3_LEN.get(b2, 3)
    return 4 if b2 & 0x0F == 0x0B and 0xCB <= b2 < 0xFB else 3


def gift_scan(prg, start, seen=None, depth=0):
    """뱅크 15 루틴을 분기 양쪽·JMP·JSR(3단)까지 따라가 [(종류, 값)]. 종류: give·take(아이템 ID, 모르면 None),
    gold(금액, 모르면 None), flag((n, m): $627B+n |= m), prize(카지노·メダル 경품). 값은 바로 앞 LDA #n 로만 정한다."""
    from kr_patch.fc.dis6502 import OPS, SIZE
    seen = set() if seen is None else seen
    out, todo = [], [start]
    while todo:
        a, imm_at = todo.pop(), {}
        while a not in seen and 0x8000 <= a < 0xC000:
            seen.add(a)
            op = dq4talk.rd(prg, a)
            imm = dq4talk.rd(prg, a - 1) if dq4talk.rd(prg, a - 2) == 0xA9 else None
            if op == 0x00:
                b1, b2 = dq4talk.rd(prg, a + 1), dq4talk.rd(prg, a + 2)
                if b2 == 0x73 and b1 == 0x66:
                    imm_at['find'] = imm
                elif b2 == 0x73 and b1 == 0x2E:
                    out.append(('give', imm))
                elif b2 == 0x73 and b1 == 0x30:
                    out.append(('take', imm_at.get('find')))
                elif b2 == 0x73 and b1 == 0x4B:
                    hi = [imm_at.get(z) for z in (0x70, 0x71)]
                    out.append(('gold', None if imm is None or None in hi else imm | hi[0] << 8 | hi[1] << 16))
                elif b2 == 0xCB:
                    out.append(('flag', (b1, dq4talk.rd(prg, a + 3))))
                elif b2 == 0xEB:
                    out.append(('check', f'flag& {b1:02X} {dq4talk.rd(prg, a + 3):02X}'))
                a += brk_len(b1, b2)
                continue
            if op not in OPS:
                break
            mn, md = OPS[op]
            n = 1 + SIZE[md]
            arg = dq4talk.rd(prg, a + 1) | (dq4talk.rd(prg, a + 2) << 8 if n == 3 else 0) if n > 1 else 0
            if mn == 'STA' and md == 'zp' and arg in (0x70, 0x71):
                imm_at[arg] = imm
            if mn in ('JSR', 'JMP') and md == 'abs':
                if arg == GIVE_ITEM:
                    out.append(('give', imm))
                elif arg == TAKE_ITEM:
                    out.append(('take', imm))
                elif arg == PRIZE_LIST:
                    out.append(('prize', None))
                elif arg in ROUTINE_CHECKS:
                    out.append(('check', ROUTINE_CHECKS[arg].format(imm if imm is not None else 0)))
                elif arg in SHOP_ENTRIES:
                    pass
                elif arg < 0xC000 and mn == 'JMP':
                    a = arg
                    continue
                elif arg < 0xC000 and depth < 3:
                    out += gift_scan(prg, arg, seen, depth + 1)
                if mn == 'JMP':
                    break
            if mn in ('RTS', 'RTI') or (mn == 'JMP' and md == 'ind'):
                break
            if md == 'rel':
                todo.append((a + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF)
            a += n
    return out


def gift_routines(prg):
    """대화 호출 문장이 부르는 루틴 가운데 물건·골드를 주고받는 것: {주소: [(종류, 값)]}."""
    out = {}
    for a in sorted({a for a, *_ in dq4talk.call_sites(prg)}):
        ev = list(dict.fromkeys(gift_scan(prg, a)))
        if any(k in ('give', 'take', 'gold', 'prize') for k, _ in ev):
            out[a] = ev
    return out


def gift_paths(tree, routines, path=(), flags=()):
    """스크립트 나무에서 물건을 주고받는 호출: [(루틴 주소, 조건 목록, 같은 블록에서 켜는 플래그)]."""
    here = [*flags, *(tuple(s[1]) for s in tree if s[0] == 'flag|=')]
    out = []
    for s in tree:
        if s[0] in ('call', 'call+2'):
            a = s[1][1] << 8 | s[1][0]
            if a in routines:
                out.append((a, list(path), here))
        elif s[0] == 'if':
            _, neg, op, args, then, other = s
            c = dq4talk.cond_text(neg, op, args)
            out += gift_paths(then, routines, (*path, c), here)
            if other:
                out += gift_paths(other, routines, (*path, f'아님({c})'), here)
    return out


def talk_gifts(prg, g, k, routines):
    """인물이 대화로 주는 것: [(X, Y, 대화 번호, 루틴, 조건, 플래그)]. dq4shop.merchants 와 같이 낮·밤 모습과
    이벤트 플래그로 바뀌는 목록(1C:$9D0E)을 돈다."""
    import dq4shop
    out = []
    for src, recs in dq4shop.npc_lists(prg, g, k):
        for r in recs:
            got = {}
            for night in (False, True):
                if not r[0] & (0x08 if night else 0x10):
                    continue
                t, (x, y) = dq4talk.talk_id(r, night), dq4talk.pos(r, night)
                c = dq4talk.classify(prg, t)
                if c[0] != 'script':
                    continue
                got[night] = [(x, y, t, a, cond, fl) for a, cond, fl in gift_paths(c[2], routines)
                              if dq4shop.possible(cond, night)]
            if len(got) == 2 and got[False] == got[True]:
                del got[True]
                tags = {False: []}
            else:
                tags = {False: ['낮'], True: ['밤']}
            for night, rows in got.items():
                out += [(x, y, t, a, src + cond + tags[night], fl) for x, y, t, a, cond, fl in rows]
    return out


def flag_text(i, m):
    return f'${0x627B + i:04X}|={m:02X}'


def loot(prg):
    """롬 전체의 얻는 것: [dict(map, x, y, how, what, flag, cond)]. 맵 순서로 정렬."""
    import dq4block
    import dq4shop
    names = {i: n for i, n, *_ in dq4data.items(prg)}
    item = lambda v: '?' if v is None else names.get(v, f'{v:02X}')
    item_id = lambda v: '?' if v is None else f'{names.get(v, "?")}({v:02X})'   # てんくうのつるぎ 처럼 이름이 같은 ID 가 있다
    rows = []
    for g, k, _ in chest_counts(prg):
        for n, x, y, c, desc in chests(prg, g, k):
            rows.append({'map': (g, k), 'x': x, 'y': y, 'how': '상자', 'what': desc, 'code': c,
                         'flag': f'${OPENED + (n >> 3):04X}&{0x80 >> (n & 7):02X}', 'cond': [f'#{n}']})
    for g, k, x, y, c, desc, flag in feet_items(prg):
        rows.append({'map': (g, k), 'x': x, 'y': y, 'how': '발밑', 'what': desc, 'code': c,
                     'flag': None if flag is None else f'${flag[0]:04X}&{flag[1]:02X}', 'cond': []})
    for e in dq4block.pots(prg):
        rows.append({'map': (e['group'], e['index']), 'x': e['x'], 'y': e['y'], 'how': 'タンス·つぼ',
                     'what': item(e['item']), 'code': e['item'], 'flag': f'${e["flag"]:04X}&{e["bit"]:02X}', 'cond': []})
    routines = gift_routines(prg)
    for m in all_maps(prg):
        g, k = m[:2]
        for x, y, t, a, cond, fl in talk_gifts(prg, g, k, routines):
            got, checks = [], []
            ev = routines[a]
            prize = any(kind == 'prize' for kind, _ in ev)
            for kind, v in ev:
                if kind == 'give' and not (prize and v is None):
                    got.append(f'받음 {item_id(v)}')
                elif kind == 'take' and not (prize and v is None):
                    got.append(f'가져감 {item_id(v)}')
                elif kind == 'gold':
                    got.append(f'골드 {"변수" if v is None else v}')
                elif kind == 'prize':
                    got.append(f'경품({PRIZE_COST.get(a, "?")}) '
                               + ' '.join(f'{item(i)} {dq4shop.price(prg, g, k, i)}' for i in dq4shop.lookup(prg, 1, g, k)))
                elif kind == 'flag':
                    fl = [*fl, v]
                elif kind == 'check':
                    checks.append(v)
            rows.append({'map': (g, k), 'x': x, 'y': y, 'how': f'대화 {t:03X} 15:{a:04X}', 'what': ', '.join(got),
                         'code': None, 'flag': ' '.join(flag_text(*f) for f in dict.fromkeys(fl)) or None,
                         'cond': cond + ([f'루틴 안 {"·".join(dict.fromkeys(checks))}'] if checks else [])})
    merged = {}
    for r in rows:
        lists = [c for c in r['cond'] if c.startswith('목록 플래그')]
        rest = [c for c in r['cond'] if not c.startswith('목록 플래그')]
        key = (r['map'], r['x'], r['y'], r['how'], r['what'], r['flag'], tuple(rest))
        if key in merged:
            merged[key]['lists'] += lists or ['기본']
        else:
            merged[key] = {**r, 'cond': rest, 'lists': lists or ['기본']}
    rows = []
    for r in merged.values():
        if r['lists'] != ['기본']:
            r['cond'] = ['목록 ' + '·'.join(x.replace('목록 플래그 ', '') for x in r['lists'])] + r['cond']
        del r['lists']
        rows.append(r)
    rows.sort(key=lambda r: (r['map'], r['how'][0] != '상', r['y'] if r['y'] is not None else -1, r['x'] or 0))
    return rows


def show_loot(prg, as_json=False):
    rows = loot(prg)
    if as_json:
        import json
        print(json.dumps([{**r, 'map': f'{r["map"][0]:02X}/{r["map"][1]:02X}'} for r in rows], ensure_ascii=False, indent=1))
        return
    count = {}
    for r in rows:
        kind = r['how'].split()[0]
        count[kind] = count.get(kind, 0) + 1
        when = ' & '.join(r['cond'])
        print(f'{r["map"][0]:02X}/{r["map"][1]:02X} {cell(r["x"], r["y"])} {r["how"]}'
              f'{" [" + when + "]" if when else ""} → {r["what"]}{"  플래그 " + r["flag"] if r["flag"] else ""}')
    print(f'{len(rows)}줄: ' + ', '.join(f'{k} {v}' for k, v in count.items()))


if __name__ == '__main__':
    main()
