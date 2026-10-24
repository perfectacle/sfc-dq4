"""DQ5(SFC) 이야기 플래그(7E:2190 + 번호, 비트)를 켜고 끄고 보는 곳 목록. 형식은 sfc/dq5/docs/dq5-flags.md.

모으는 곳:
- 대화 스크립트(06:B065): 조건 1B·16(비트 시험)·1A(바이트 비교)·1C, 명령 17(끄기)·18(켜기)·19(바이트 쓰기).
  그 대화 번호를 쓰는 인물의 맵을 함께 적는다.
- 인물 인라인 스크립트(01:C800): 06(뛰기)·09(기다림) 시험, 10(켜기)·11(AND)·55(바이트 쓰기).
- 인물 목록 표: 12:839C(인물을 놓지 않음)·12:8449(목록 바꿈). 번호 bit7 이면 「꺼졌을 때」.
- 맵별 루틴 표(15:F907) +2·+3.
- 네이티브 코드의 7E:2190~220F 롱 주소 읽기·쓰기(LDA·STA·CMP·AND·ORA 등 long). 바이트 변수로 쓰는 칸이 많다.
- 네이티브 코드의 BRK 0B(시험)·0C(켜기)·0D(끄기) mask idx(00:93BA). 롬 전체를 훑으므로 그림 뱅크 등 데이터를 빼려고
  코드 뱅크만 보고, 0B 는 바로 뒤가 BEQ·BNE 인 것, 0C·0D 는 바로 뒤가 흔한 명령인 것만 센다(놓치는 것이 있을 수 있음).

사용:
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc                 # 플래그 비트마다 켜는 곳·끄는 곳·보는 곳 개수와 첫 문맥
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc 2192.7          # 그 비트의 모든 참조
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc 2192            # 그 바이트의 모든 비트
  python sfc/dq5/tools/dq5flags.py rom/dq5.sfc --source talk   # 출처 하나만(talk·npc·list·hook·code·long)
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
# BRK 0C·0D 바로 뒤에 오는 것으로 받아 주는 명령.
NEXT_OPS = {0x00, 0x08, 0x18, 0x20, 0x22, 0x28, 0x38, 0x4C, 0x5C, 0x60, 0x64, 0x6B, 0x80, 0x82, 0x85, 0x8B, 0x8D,
            0x8F, 0x9C, 0xA0, 0xA2, 0xA5, 0xA9, 0xAB, 0xAD, 0xAF, 0xC2, 0xE2, 0xEE, 0xF0, 0xD0}
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


def refs_code(rom):
    out = []
    data = rom.d
    for op, kind in ((0x0B, 'test'), (0x0C, 'set'), (0x0D, 'clear')):
        for m in re.finditer(bytes((0x00, op)), data):
            i = m.start()
            if i + 5 > len(data) or i // 0x8000 not in CODE_BANKS:
                continue
            mask, idx, nxt = data[i + 2], data[i + 3], data[i + 4]
            if not mask or idx >= 0x80:
                continue
            if op == 0x0B and nxt not in (0xD0, 0xF0):
                continue
            if op != 0x0B and nxt not in NEXT_OPS:
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
        if i < 0 or i // 0x8000 not in CODE_BANKS or data[i] not in LONG_OPS:
            continue
        addr = data[i + 1] | data[i + 2] << 8
        if not FLAG_BASE <= addr < 0x2210:
            continue
        kind, name = LONG_OPS[data[i]]
        out.append(('long', addr - FLAG_BASE, 0, kind, f'코드 {i // 0x8000:02X}:{0x8000 + i % 0x8000:04X} {name} 7E:{addr:04X}', None))
    return out


def check(rom, paths):
    """게임에서 잡은 BRK 0B·0C·0D 자리와 롱 주소 쓰기(쓴 뒤 PC - 4 가 STA long)가 정적 훑기에 있는지."""
    static = {where.split()[1] for _, _, _, _, where, _ in refs_code(rom) + refs_long(rom)}
    sites, writes, other = {}, {}, 0
    for p in paths:
        for line in open(p):
            f = line.split()
            if len(f) >= 6 and f[1] == 'brk':
                sites[f[2]] = f'BRK {f[3]} {f[4]} {f[5]}'
            elif len(f) >= 4 and f[1] == 'write':
                bank, pc = (int(x, 16) for x in f[3][3:].split(':'))
                a = bank << 16 | (pc - 4)
                if rom.u8(a) in (0x8F, 0x9F):
                    writes[f'{bank:02X}:{pc - 4:04X}'] = f'{f[2]} (STA long)'
                else:
                    other += 1
    found = {**sites, **writes}
    missing = sorted(k for k in found if k not in static)
    for k in missing:
        print(f'없음 {k} {found[k]}')
    print(f'BRK 자리 {len(sites)}개, 롱 쓰기 {len(writes)}개 중 {len(found) - len(missing)}개가 목록에 있음'
          f'(그 밖의 쓰기 {other}개는 BRK 처리기·스크립트 명령·간접 쓰기)')
    return 1 if missing else 0


def collect(rom, sources):
    fns = {'talk': refs_talk, 'npc': refs_npc, 'list': refs_lists, 'hook': refs_hooks, 'code': refs_code,
           'long': refs_long}
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
        bits = bits_of(val ^ 0xFF if kind == 'clear' else val)
        for b in bits:
            out[(addr, b)].append((src, kind, val, where, ctx))
    return out


def label(addr, bit):
    return f'{addr:04X}.{bit}' if bit >= 0 else f'{addr:04X}(바이트)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('flag', nargs='?')
    ap.add_argument('--source', action='append', choices=['talk', 'npc', 'list', 'hook', 'code', 'long'])
    ap.add_argument('--check', nargs='+')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check:
        return check(rom, args.check)
    refs = by_bit(collect(rom, args.source or ['talk', 'npc', 'list', 'hook', 'code', 'long']))

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
