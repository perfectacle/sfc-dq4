"""DQ5(SFC) 이야기 플래그(7E:2190 + 번호, 비트)를 켜고 끄고 보는 곳 목록. 형식은 sfc/dq5/docs/dq5-flags.md.

모으는 곳:
- 대화 스크립트(06:B065): 조건 1B·16(비트 시험)·1A(바이트 비교)·1C, 명령 17(끄기)·18(켜기)·19(바이트 쓰기).
  그 대화 번호를 쓰는 인물의 맵을 함께 적는다.
- 인물 인라인 스크립트(01:C800): 06(뛰기)·09(기다림) 시험, 10(켜기)·11(AND)·55(바이트 쓰기).
- 인물 목록 표: 12:839C(인물을 놓지 않음)·12:8449(목록 바꿈). 번호 bit7 이면 「꺼졌을 때」.
- 이벤트 스크립트(00:BEC3): 10 idx mask(켜기)·20 idx mask(AND)·B0 idx mask(켜질 때까지 기다림). 시작 주소와 해석은 dq5event.py.
- 맵별 루틴 표(15:F907) +2·+3, 맵 조건 표 01:9A12(35바이트 항목)·02:CAF6(6바이트 항목, 루틴 포인터).
- 네이티브 코드의 7E:2190~220F 롱 주소 읽기·쓰기(LDA·STA·CMP·AND·ORA 등 long). 바이트 변수로 쓰는 칸이 많다.
- 네이티브 코드의 BRK 0B(시험)·0C(켜기)·0D(끄기) mask idx(00:93BA). 롬 전체를 훑으므로 그림 뱅크 등 데이터를 빼려고
  코드 뱅크만 보고, 0B 는 바로 뒤가 BEQ·BNE 인 것, 0C·0D 는 바로 뒤가 흔한 명령인 것만 센다(놓치는 것이 있을 수 있음).

사용:
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc                 # 플래그 비트마다 켜는 곳·끄는 곳·보는 곳 개수와 첫 문맥
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc 2192.7          # 그 비트의 모든 참조
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc 2192            # 그 바이트의 모든 비트
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc --source talk   # 출처 하나만(talk·npc·list·hook·event·code·long)
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc --check flagtrace.txt ...
      # sfc/dq5/tools/lua/dq5flagtrace.lua 가 게임에서 잡은 BRK 0B·0C·0D 자리가 이 목록(코드 출처)에 있는지
"""
import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import dq5npc  # noqa: E402
import dq5talk  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5text import message, text  # noqa: E402

FLAG_BASE = 0x2190
NO_NPC = 0x12839C
OVERRIDES = 0x128449
HOOKS = 0x15F907
# 0B 뒤 BEQ·BNE 가 다섯 번 이상 나오는 뱅크와 게임에서 BRK 0B 실행을 본 29. 0C·0D·0E 는 그림 데이터라 우연히 같은 바이트가 많다.
CODE_BANKS = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F, 0x11, 0x12, 0x1E, 0x1F, 0x20, 0x21, 0x23, 0x24,
              0x25, 0x29, 0x2A}
# 코드와 그림 데이터가 섞인 뱅크(17·2B 는 코드 뱅크에서 JSL 로 들어감)에서 디스어셈블해 코드로 확인한 BRK 자리.
EXTRA_BRK = {0x179375, 0x179397, 0x2BBCCA, 0x2BBEBC}
# 롱 주소 참조만 받는 뱅크. 2B 의 BRK 0C 꼴 바이트는 그림 데이터였다.
LONG_BANKS = CODE_BANKS | {0x2B}
# BRK 0C·0D 바로 뒤에 오는 것으로 받아 주는 명령.
NEXT_OPS = {0x00, 0x08, 0x18, 0x20, 0x22, 0x28, 0x38, 0x4C, 0x5C, 0x60, 0x64, 0x6B, 0x80, 0x82, 0x85, 0x8B, 0x8D,
            0x8F, 0x9C, 0xA0, 0xA2, 0xA5, 0xA9, 0xAB, 0xAD, 0xAF, 0xC2, 0xE2, 0xEE, 0xF0, 0xD0,
            # 레지스터·색인 명령(06:C363 의 LDX abs, 06:B872 의 STX dp,Y 처럼 실제로 뒤에 오는 것)
            0xAE, 0xAC, 0xA6, 0xA4, 0x86, 0x84, 0x96, 0x94, 0x9D, 0x99, 0x9E, 0xC8, 0xE8, 0x88, 0xCA,
            0xAA, 0xA8, 0x8A, 0x98, 0x48, 0x68, 0xDA, 0xFA, 0x5A, 0x7A, 0x0B, 0x2B, 0x7B, 0x1A, 0x3A}
KIND_NAME = {'set': '켬', 'clear': '끔', 'write': '바이트 씀', 'test': '봄', 'compare': '바이트 비교', 'read': '바이트 읽음'}
BITS = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)


def bits_of(mask):
    return [7 - i for i, b in enumerate(BITS) if mask & b]


def short_message(rom, n, width=28):
    s = text(message(rom, n)).replace('\n', ' ')
    s = re.sub(r'\{[0-9A-F]{4}\}', '', s).strip()
    return s[:width]


def talk_users(rom):
    """대화 번호 → 그 번호를 쓰는 인물의 맵 이름들."""
    users = defaultdict(set)
    for la, name in dq5npc.all_lists(rom):
        for a, _ in dq5npc.list_entries(rom, la):
            for night in (False, True):
                f = dq5npc.parse(rom, a, night)
                if f:
                    users[f['talk']].add(name.split()[0])
    return users


def refs_talk(rom):
    users = talk_users(rom)
    out = []
    for n in range(dq5talk.FIRST_SPECIAL2 - dq5talk.FIRST_SCRIPT):
        t = n + dq5talk.FIRST_SCRIPT
        ops, _ = dq5talk.parse_script(rom, dq5talk.script_address(rom, n))
        maps = ','.join(sorted(users.get(t, ()))[:4]) or '인물 없음'
        last_msg = None
        for i, (addr, _, name, raw, msg) in enumerate(ops):
            if msg is not None:
                last_msg = msg
            ref = None
            if raw[0] == 0x07 and raw[1] & 0x3F in (0x1B, 0x16, 0x1C, 0x1A):
                c = raw[1] & 0x3F
                idx, val = raw[2], raw[3] if len(raw) > 3 else 0
                kind = 'compare' if c == 0x1A else 'test'
                # 참 분기의 첫 메시지를 문맥으로
                ctx = next((m for _, _, _, _, m in ops[i + 1:i + 6] if m is not None), None)
                ref = (idx, val, kind, ctx, ' (조건 뒤집음)' if raw[1] & 0x80 else '')
            elif raw[0] in (0x17, 0x18, 0x19):
                kind = {0x17: 'clear', 0x18: 'set', 0x19: 'write'}[raw[0]]
                idx, val = raw[1], raw[2]
                if kind == 'clear':
                    val ^= 0xFF
                ref = (idx, val, kind, last_msg, '')
            if ref:
                idx, val, kind, ctx, note = ref
                where = f'대화 {t:03X} ({maps}) {addr:06X}{note}'
                out.append(('talk', idx, val, kind, where, ctx))
    return out


def refs_npc(rom):
    out, seen = [], set()
    for la, name in dq5npc.all_lists(rom):
        for a, _ in dq5npc.list_entries(rom, la):
            for night in (False, True):
                s = dq5npc.script_address(rom, a, night)
                if s is None or s in seen:
                    continue
                seen.add(s)
                try:
                    ops = dq5npc.script_ops(dq5npc.script_bytes(rom, s))
                except ValueError:
                    continue
                for off, raw, _ in ops:
                    op = raw[0]
                    if op & 0x80 or op not in (0x06, 0x09, 0x10, 0x11, 0x55):
                        continue
                    idx, mask = raw[1] & 0x7F, raw[2]
                    kind = {0x06: 'test', 0x09: 'test', 0x10: 'set', 0x11: 'clear', 0x55: 'write'}[op]
                    if kind == 'clear':
                        mask ^= 0xFF
                    note = {0x06: '뛰기', 0x09: '기다림'}.get(op, '')
                    if op in (0x06, 0x09):
                        note += ' 켜짐' if (raw[1] & 0x80) == (0x80 if op == 0x09 else 0) else ' 꺼짐'
                    out.append(('npc', idx, mask, kind, f'인물 스크립트 {name} {s:06X}+{off} {note}'.rstrip(), None))
    return out


def refs_lists(rom):
    out = []
    a = NO_NPC
    while rom.u8(a) != 0xFF:
        n, m = rom.u8(a + 2), rom.u8(a + 3)
        out.append(('list', n & 0x7F, m, 'test',
                    f'인물 없음 {rom.u8(a):02X}/{rom.u8(a + 1):02X} ({"꺼짐" if n & 0x80 else "켜짐"}일 때)', None))
        a += 4
    a = OVERRIDES
    while rom.u8(a) != 0xFF:
        n, m = rom.u8(a + 2), rom.u8(a + 3)
        out.append(('list', n & 0x7F, m, 'test',
                    f'인물 목록 {rom.u8(a):02X}/{rom.u8(a + 1):02X} → 10:{rom.u16(a + 4):04X} ({"꺼짐" if n & 0x80 else "켜짐"}일 때)',
                    None))
        a += 6
    return out


def refs_hooks(rom):
    out = []
    a = HOOKS
    while rom.u8(a) != 0xFF:
        bc, bd, n, m = (rom.u8(a + i) for i in range(4))
        if n != 0xFF:
            target = 'FE(필드)' if bc == 0xFE else f'{bc:02X}/' + ('**' if bd == 0xFF else f'{bd:02X}')
            out.append(('hook', n & 0x7F, m, 'test',
                        f'맵별 루틴 {target} → {rom.u24(a + 4):06X} ({"꺼짐" if n & 0x80 else "켜짐"}일 때)', None))
        a += 10
    return out


def refs_event(rom):
    import dq5event
    return [('event', idx, mask, kind, where, ctx) for idx, mask, kind, where, ctx in dq5event.flag_refs(rom)]


# [BC][BD][f][m] 로 시작하는 맵 조건 표: (주소, 항목 크기, 이름, BC 특수값). 주소 None 은 맵 팔레트 줄 표
# (dq5objpalette.py --at 이 옮기면 옮긴 자리, dq5sprite.map_palette_table).
COND_TABLES = ((None, 0x23, '01:9A12 표', {0xFE: '필드'}),
               (0x02CAF6, 6, '02:CAF6 표', {0xFE: '필드', 0xFD: '어디서나'}))


def refs_tables(rom):
    out = []
    for base, size, name, special in COND_TABLES:
        if base is None:
            import dq5sprite
            base = dq5sprite.map_palette_table(rom)
        a = base
        while rom.u8(a) != 0xFF:
            bc, bd, n, m = (rom.u8(a + i) for i in range(4))
            if n != 0xFF:
                where = special.get(bc) or f'{bc:02X}/' + ('**' if bd in (0xFF, 0xFC) else f'{bd:02X}')
                extra = f' → {base >> 16:02X}:{rom.u16(a + 4):04X}' if size == 6 else ''
                out.append(('hook', n & 0x7F, m, 'test',
                            f'{name} {where}{extra} ({"꺼짐" if n & 0x80 else "켜짐"}일 때)', None))
            a += size
    return out


def refs_code(rom):
    out = []
    data = rom.d
    for op, kind in ((0x0B, 'test'), (0x0C, 'set'), (0x0D, 'clear')):
        for m in re.finditer(bytes((0x00, op)), data):
            i = m.start()
            if i + 5 > len(data):
                continue
            if i // 0x8000 not in CODE_BANKS and (i // 0x8000) << 16 | (0x8000 + i % 0x8000) not in EXTRA_BRK:
                continue
            mask, idx, nxt = data[i + 2], data[i + 3], data[i + 4]
            if not mask or idx >= 0x80:
                continue
            if op == 0x0B and nxt not in (0xD0, 0xF0):
                continue
            if op != 0x0B and nxt not in NEXT_OPS:
                continue
            # 끄기 마스크는 끄는 비트가 한둘이다. 셋 이상이면 데이터 바이트로 본다(0F:8903·12:E08C·23:9059 등)
            if op == 0x0D and bin(mask ^ 0xFF).count('1') > 2:
                continue
            val = mask ^ 0xFF if kind == 'clear' else mask
            out.append(('code', idx, val, kind, f'코드 {i // 0x8000:02X}:{0x8000 + i % 0x8000:04X} BRK {op:02X}', None))
    return out


LONG_OPS = {0xAF: ('read', 'LDA'), 0xBF: ('read', 'LDA,X'), 0xCF: ('read', 'CMP'), 0xDF: ('read', 'CMP,X'),
            0x2F: ('read', 'AND'), 0x0F: ('read', 'ORA'), 0x4F: ('read', 'EOR'), 0x6F: ('read', 'ADC'),
            0xEF: ('read', 'SBC'), 0x8F: ('write', 'STA'), 0x9F: ('write', 'STA,X')}


def refs_long(rom):
    out = []
    data = rom.d
    for m in re.finditer(rb'[\x21\x22]\x7e', data):
        i = m.start() - 2
        if i < 0 or i // 0x8000 not in LONG_BANKS or data[i] not in LONG_OPS:
            continue
        addr = data[i + 1] | data[i + 2] << 8
        if not FLAG_BASE <= addr < 0x2210:
            continue
        kind, name = LONG_OPS[data[i]]
        out.append(('long', addr - FLAG_BASE, 0, kind, f'코드 {i // 0x8000:02X}:{0x8000 + i % 0x8000:04X} {name} 7E:{addr:04X}', None))
    return out


def refs_short(rom):
    """LDA #m 뒤 TSB·TRB $21xx(데이터 뱅크 7E)와 짧은·롱 주소로 읽어 비트를 가르는 곳. 02:8B22 의 LDA #$80 / TSB $21A2 / TSB $21D7 처럼 TSB·TRB 가 이어지면
    앞의 LDA # 를 같이 쓴다."""
    out = []
    data = rom.d
    for m in re.finditer(rb'[\x0c\x1c][\x90-\xff]\x21|[\x0c\x1c][\x00-\x0f]\x22', data):
        i = m.start()
        if i // 0x8000 not in CODE_BANKS:
            continue
        k = i
        while k >= 3 and data[k - 3] in (0x0C, 0x1C) and data[k - 1] in (0x21, 0x22):
            k -= 3
        if k < 2 or data[k - 2] != 0xA9 or not data[k - 1]:
            continue
        addr = data[i + 1] | data[i + 2] << 8
        kind, name = ('set', 'TSB') if data[i] == 0x0C else ('clear', 'TRB')
        out.append(('short', addr - FLAG_BASE, data[k - 1], kind,
                    f'코드 {i // 0x8000:02X}:{0x8000 + i % 0x8000:04X} {name} ${addr:04X}', None))
    # 비트 시험: LDA $21xx(또는 롱 7E:21xx) 뒤 AND #m·BIT #m 은 m, BPL·BMI 는 bit7. BIT $21xx 뒤 BPL·BMI 는 bit7, BVC·BVS 는 bit6
    for m in re.finditer(rb'(?:\xad|\x2c)(?:[\x90-\xff]\x21|[\x00-\x0f]\x22)|\xaf(?:[\x90-\xff]\x21|[\x00-\x0f]\x22)\x7e', data):
        i = m.start()
        if i // 0x8000 not in CODE_BANKS | {0x2B}:
            continue
        op, j = data[i], m.end()
        nxt = data[j]
        if op == 0x2C:
            mask = {0x10: 0x80, 0x30: 0x80, 0x50: 0x40, 0x70: 0x40}.get(nxt)
        elif nxt in (0x29, 0x89):
            mask = data[j + 1]
        else:
            mask = 0x80 if nxt in (0x10, 0x30) else None
        if not mask:
            continue
        addr = data[i + 1] | data[i + 2] << 8
        name = {0xAD: 'LDA', 0xAF: 'LDA', 0x2C: 'BIT'}[op]
        out.append(('short', addr - FLAG_BASE, mask, 'test',
                    f'코드 {i // 0x8000:02X}:{0x8000 + i % 0x8000:04X} {name} ${addr:04X}', None))
    return out


# 번호를 X 로 받아 7E:2190,X 에 쓰는 공용 자리. 쓰기 기록의 PC 로 어느 길로 바뀌었는지 가른다.
GENERIC_WRITERS = {0x0093EF: 'BRK 0C', 0x009406: 'BRK 0D', 0x06B0C6: '대화 18', 0x06B0DB: '대화 17',
                   0x06B0EC: '대화 19', 0x01D2EE: '인물 55', 0x00BFAF: '이벤트 스크립트(00:BEC3) 켜기',
                   0x00BFE5: '이벤트 스크립트(00:BEC3) 끄기', 0x12F843: '상자 사건(12:F83C)',
                   0x01CB19: '인물 10', 0x01CB31: '인물 11'}   # 이 둘은 STA $2190,X(3바이트)


def check(rom, paths):
    """게임에서 잡은 BRK 0B·0C·0D 자리와 롱 주소 쓰기를 정적 목록과 맞춘다.
    쓰기는 PC - 4 가 공용 자리면 그 길로 세고, 아니면 그 STA long 이 목록에 있어야 한다."""
    static = {where.split()[1] for _, _, _, _, where, _ in refs_code(rom) + refs_long(rom)}
    sites, direct, via, other = {}, {}, {}, 0
    for p in paths:
        for line in open(p):
            f = line.split()
            if len(f) >= 6 and f[1] == 'brk':
                sites[f[2]] = f'BRK {f[3]} {f[4]} {f[5]}'
            elif len(f) >= 4 and f[1] == 'write':
                bank, pc = (int(x, 16) for x in f[3][3:].split(':'))
                a = bank << 16 | (pc - 4)
                g = GENERIC_WRITERS.get(a) or GENERIC_WRITERS.get(a + 1)
                if g:
                    via[g] = via.get(g, 0) + 1
                elif rom.u8(a) in (0x8F, 0x9F):
                    direct[f'{bank:02X}:{pc - 4:04X}'] = f'{f[2]} (STA long)'
                else:
                    other += 1
                    print(f'모르는 쓰기 {f[2]} pc={f[3][3:]}')
    found = {**sites, **direct}
    missing = sorted(k for k in found if k not in static)
    for k in missing:
        print(f'없음 {k} {found[k]}')
    print(f'BRK 자리 {len(sites)}개, 직접 롱 쓰기 {len(direct)}개 중 {len(found) - len(missing)}개가 목록에 있음')
    print('공용 자리로 쓴 것: ' + (', '.join(f'{k} {n}' for k, n in sorted(via.items())) or '없음') + f', 모르는 쓰기 {other}')
    return 1 if missing or other else 0


def collect(rom, sources):
    fns = {'talk': refs_talk, 'npc': refs_npc, 'list': refs_lists, 'hook': lambda r: refs_hooks(r) + refs_tables(r),
           'code': refs_code, 'event': refs_event,
           'long': refs_long, 'short': refs_short}
    refs = []
    for s in sources:
        refs += fns[s](rom)
    return refs


def by_bit(refs):
    """(바이트 주소, 비트) → 참조 목록. write·compare 는 바이트 단위라 비트 -1 로 둔다."""
    out = defaultdict(list)
    for src, idx, val, kind, where, ctx in refs:
        addr = FLAG_BASE + idx
        if kind in ('write', 'compare', 'read'):
            out[(addr, -1)].append((src, kind, val, where, ctx))
            continue
        # 끄기는 출처마다 AND 마스크를 뒤집어 「끄는 비트」로 넘긴다
        bits = bits_of(val)
        for b in bits:
            out[(addr, b)].append((src, kind, val, where, ctx))
    return out


def label(addr, bit):
    return f'{addr:04X}.{bit}' if bit >= 0 else f'{addr:04X}(바이트)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('flag', nargs='?')
    ap.add_argument('--source', action='append', choices=['talk', 'npc', 'list', 'hook', 'code', 'long', 'short', 'event'])
    ap.add_argument('--check', nargs='+')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        return check(rom, args.check)
    refs = by_bit(collect(rom, args.source or ['talk', 'npc', 'list', 'hook', 'event', 'code', 'long', 'short']))

    if args.flag:
        m = re.fullmatch(r'(?:7E:?)?([0-9A-Fa-f]{4})(?:\.([0-7]))?', args.flag)
        if not m:
            ap.error('플래그는 2192 또는 2192.7')
        addr, bit = int(m.group(1), 16), (int(m.group(2)) if m.group(2) else None)
        keys = sorted(k for k in refs if k[0] == addr and (bit is None or k[1] in (bit, -1)))
        for k in keys:
            print(label(*k))
            for src, kind, val, where, ctx in refs[k]:
                c = f'  「{short_message(rom, ctx)}」' if ctx is not None else ''
                extra = f' = {val:02X}' if kind in ('write', 'compare') and src != 'long' else ''
                print(f'  {KIND_NAME[kind] + extra:10} {where}{c}')
        return 0

    for k in sorted(refs):
        rows = refs[k]
        count = {kd: sum(1 for r in rows if r[1] == kd) for kd in KIND_NAME}
        summary = ' '.join(f'{KIND_NAME[kd]} {n}' for kd, n in count.items() if n)
        first = next((r for r in rows if r[1] in ('set', 'write')), rows[0])
        c = f' 「{short_message(rom, first[4], 20)}」' if first[4] is not None else ''
        print(f'{label(*k):12} {summary:28} {first[3]}{c}')
    print(f'플래그 {len(refs)}개, 참조 {sum(len(v) for v in refs.values())}개')
    return 0


if __name__ == '__main__':
    sys.exit(main())
