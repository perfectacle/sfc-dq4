"""DQ5(SFC) 대화 스크립트(대화 번호 011~24E) 쓰기. 형식: sfc/dq5/docs/dq5-build-format.md 「대화 스크립트」,
읽기는 dq5-text-format.md 「대화 스크립트」 와 dq5talk.py.

스크립트 574개는 뱅크 06 의 18개 묶음이다. 06:AEF8 + g*2 가 묶음 g 첫 스크립트의 16비트 주소이고,
그 뒤 스크립트는 06:AFA9 가 앞 스크립트를 건너뛰어 찾는다. 06:AF93·06:B05D 가 데이터 뱅크를 06 으로 두고
06:B065 가 ($F9),Y(Y 8비트)로 읽으므로 스크립트는 뱅크 06 안, 하나에 256바이트까지다(코드 읽기).

  dump    스크립트를 JSON 으로(--talk 로 일부만)
  patch   고친 스크립트를 dq5patch/1 로. 묶음이 원래 자리보다 길면 --at(뱅크 06 빈 자리)으로 옮기고,
          --repack 이면 묶음 전부를 06:8129 부터 다시 채워 넘치는 묶음만 --at 에 둔다
  check   입력 없이: 원본 왕복이 쓰기 0개인지. 입력이 있으면 빌드한 롬을 다시 읽어 같은지, 다시 패치해 쓰기 0개인지

  python sfc/dq5/tools/dq5talkwrite.py rom/dq5.sfc dump -o work/talk.json
  python sfc/dq5/tools/dq5talkwrite.py rom/dq5.sfc dump --talk 012 -o work/papas.json
  python sfc/dq5/tools/dq5talkwrite.py rom/dq5.sfc patch work/papas.json -o work/talk.dq5patch.json --at 06:FE10
  python sfc/dq5/tools/dq5talkwrite.py rom/dq5.sfc check work/papas.json --at 06:FE10
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dq5build import cpu, free_ranges
from dq5map import Rom, lorom
from dq5talk import (EXTRA_BASE, FIRST_SCRIPT, FIRST_SPECIAL2, MESSAGE_BASE, SITES, THREE_BYTE, extra_address,
                     extra_config, extra_hooks, site_bytes)

FORMAT = 'dq5talk/1'
BANK = 0x06
TABLE = 0x06AEF8
COUNT = FIRST_SPECIAL2 - FIRST_SCRIPT
GROUPS = (COUNT + 31) // 32
# 원래 스크립트가 빈틈 없이 차지하는 자리. 06:8128 은 앞 코드의 RTL, 06:AEF8 은 묶음 표.
REGION = (0x068129, TABLE)
MAX_SCRIPT = 256
MESSAGES = 3200
# 조건 코드 → 인자 이름. 형식 문서에서 실측한 것만 받는다. 16 은 실행(06:B31F)이 3바이트, 건너뛰기(06:B27E)가 2바이트로
# 길이가 어긋나고, 1C 는 코드 읽기뿐이라 받지 않는다.
CONDS = {0x02: (), 0x03: ('member',), 0x05: (), 0x11: ('item',), 0x13: ('record',), 0x14: (),
         0x1A: ('index', 'value'), 0x1B: ('index', 'mask'), 0x1E: (), 0x1F: (), 0x20: ()}
FLAG_OPS = {0x17: ('flag-off', 'mask'), 0x18: ('flag-on', 'mask'), 0x19: ('flag-set', 'value')}
FLAG_CODES = {name: (code, arg) for code, (name, arg) in FLAG_OPS.items()}


def fields(value, required, optional=(), name='항목'):
    if not isinstance(value, dict):
        raise ValueError(f'{name}: 객체여야 함')
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f'{name}: 필드 {sorted(required)}(+{sorted(optional)})만 있어야 함, '
                         f'빠짐 {sorted(missing)}, 모름 {sorted(extra)}')


def byte(value, name):
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError(f'{name}: 0~255 정수여야 함')
    return value


def hexnum(value, lo, hi, width, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-F]{%d}' % width, value):
        raise ValueError(f'{name}: {width}자리 16진 대문자 문자열이어야 함')
    n = int(value, 16)
    if not lo <= n <= hi:
        raise ValueError(f'{name}: {lo:X}~{hi:X} 범위 밖')
    return n


def bank06(at):
    """'06:AAAA' 만 받는다(뱅크 06 고정)."""
    m = re.fullmatch(r'06:([0-9A-Fa-f]{4})', at or '')
    if not m or int(m[1], 16) < 0x8000:
        raise ValueError(f'--at {at!r}: 스크립트는 뱅크 06 안(06:8000~06:FFFF)에만 둘 수 있음')
    return 0x060000 | int(m[1], 16)


# ---------- 읽기 ----------

def read_cond(rom, a):
    c = rom.u8(a)
    code = c & 0x3F
    if code not in CONDS:
        raise ValueError(f'{a:06X}: 받지 않는 조건 코드 {code:02X}')
    if c & 0x40:
        raise ValueError(f'{a:06X}: 조건 바이트 bit6 이 켜짐')
    value = {'code': f'{code:02X}'}
    for i, key in enumerate(CONDS[code]):
        value[key] = rom.u8(a + 1 + i)
    if c & 0x80:
        value['not'] = True
    return value, a + 1 + len(CONDS[code])


def read_branch(rom, a):
    if rom.u8(a) != 0x06:
        op, a = read_op(rom, a)
        if op['op'] == 'if':
            raise ValueError(f'{a:06X}: 블록 없이 조건문을 분기로 씀(06:B23F 가 07 을 1바이트로 건너뜀)')
        return op, a
    a += 1
    ops = []
    while True:
        b = rom.u8(a)
        if b == 0x3E:
            if not ops:
                raise ValueError(f'{a:06X}: 빈 블록')
            return ops, a + 1
        if b == 0x3F:
            raise ValueError(f'{a:06X}: 블록이 3F 로 끝남')
        op, a = read_op(rom, a)
        ops.append(op)


def read_op(rom, a):
    b = rom.u8(a)
    if b & 0x40:
        v = (b & 0x3F) << 8 | rom.u8(a + 1)
        n = v & 0x1FFF if v & 0x2000 else v + MESSAGE_BASE
        if (n >= MESSAGE_BASE) == bool(v & 0x2000) or n >= MESSAGES:
            raise ValueError(f'{a:06X}: 메시지 {n:X} 의 부호가 원본 규칙과 다름')
        return {'op': 'msg', 'id': f'{n:03X}'}, a + 2
    if b == 0x07:
        cond, a = read_cond(rom, a + 1)
        then, a = read_branch(rom, a)
        op = {'op': 'if', 'cond': cond, 'then': then}
        if rom.u8(a) == 0x0B:
            op['else'], a = read_branch(rom, a + 1)
        return op, a
    if b in FLAG_OPS:
        name, arg = FLAG_OPS[b]
        return {'op': name, 'index': rom.u8(a + 1), arg: rom.u8(a + 2)}, a + 3
    if b == 0x00:
        return {'op': 'call', 'target': f'{rom.u16(a + 1):04X}'}, a + 3
    raise ValueError(f'{a:06X}: 받지 않는 명령 {b:02X}')


def read_script(rom, a):
    """스크립트 하나의 명령 목록과 끝(3F) 다음 주소."""
    body = []
    while rom.u8(a) != 0x3F:
        if rom.u8(a) == 0x3E:
            raise ValueError(f'{a:06X}: 블록 밖의 3E')
        op, a = read_op(rom, a)
        body.append(op)
    if not body:
        raise ValueError(f'{a:06X}: 빈 스크립트')
    return body, a + 1


def skip_length(code):
    """06:AFA9 가 스크립트 하나를 건너뛰는 길이. 3F 를 못 만나면 None."""
    i = 0
    while i < len(code):
        b = code[i]
        i += 1
        if b in THREE_BYTE:
            i += 2
        elif b & 0x40:
            i += 1
        elif b == 0x3F:
            return i
    return None


def layout(rom):
    """묶음마다 (시작 주소, [(대화 번호, 주소, 바이트, 명령 목록)]). 게임의 건너뛰기와 경계가 같은지도 본다."""
    groups = []
    for g in range(GROUPS):
        a = BANK << 16 | rom.u16(TABLE + g * 2)
        if a & 0xFFFF < 0x8000:
            raise ValueError(f'묶음 {g}: 포인터 {cpu(lorom(a))} 가 롬 밖')
        start, rows = a, []
        for n in range(g * 32, min(g * 32 + 32, COUNT)):
            body, end = read_script(rom, a)
            if end > 0x070000:
                raise ValueError(f'스크립트 {n:03X}: 뱅크 06 끝을 넘음')
            code = bytes(rom.d[lorom(a):lorom(a) + end - a])
            if skip_length(code) != len(code):
                raise ValueError(f'스크립트 {n:03X}: 06:AFA9 건너뛰기 경계가 명령 경계와 다름')
            rows.append((n + FIRST_SCRIPT, a, code, body))
            a = end
        groups.append((start, rows))
    return groups


def extra_layout(rom):
    """덧붙인 스크립트 [(대화 번호, 주소, 바이트, 명령 목록)]. 없으면 빈 목록."""
    cfg = extra_config(rom)
    if cfg is None:
        return cfg, []
    rows = []
    for n in range(cfg['end'] - EXTRA_BASE):
        a = extra_address(rom, n, cfg)
        body, end = read_script(rom, a)
        code = bytes(rom.d[lorom(a):lorom(a) + end - a])
        if end >> 16 != a >> 16 or skip_length(code) != len(code):
            raise ValueError(f'덧붙인 스크립트 {n + EXTRA_BASE:03X}: 뱅크를 넘거나 06:AFA9 건너뛰기 경계와 다름')
        rows.append((n + EXTRA_BASE, a, code, body))
    return cfg, rows


def dump(rom, talks=None):
    rows = [row for _, group in layout(rom) for row in group] + extra_layout(rom)[1]
    scripts = [{'talk': f'{t:03X}', 'body': body} for t, _, _, body in rows if talks is None or t in talks]
    return {'format': FORMAT, 'scripts': scripts}


# ---------- 쓰기 ----------

def encode_cond(value, where):
    fields(value, ('code',), ('not', *(k for c in CONDS.values() for k in c)), where)
    code = hexnum(value['code'], 0, 0x3F, 2, f'{where}.code')
    if code not in CONDS:
        raise ValueError(f'{where}: 조건 코드 {code:02X} 는 받지 않음(실측한 것: '
                         f'{", ".join(f"{c:02X}" for c in CONDS)})')
    fields(value, ('code', *CONDS[code]), ('not',), where)
    neg = value.get('not', False)
    if 'not' in value and neg is not True:
        raise ValueError(f'{where}.not: 뒤집을 때만 true 로 적음')
    return bytes([code | 0x80 * neg, *(byte(value[k], f'{where}.{k}') for k in CONDS[code])])


def encode_branch(value, where):
    if isinstance(value, list):
        if not value:
            raise ValueError(f'{where}: 빈 블록은 06:B065 가 3E 를 명령으로 읽으므로 받지 않음')
        return b'\x06' + b''.join(encode_op(op, f'{where}[{i}]') for i, op in enumerate(value)) + b'\x3e'
    if isinstance(value, dict) and value.get('op') == 'if':
        raise ValueError(f'{where}: 조건문을 분기로 쓰려면 블록(목록)에 넣어야 함')
    return encode_op(value, where)


def encode_op(value, where):
    if not isinstance(value, dict):
        raise ValueError(f'{where}: 명령은 객체여야 함')
    op = value.get('op')
    if op == 'msg':
        fields(value, ('op', 'id'), (), where)
        n = hexnum(value['id'], 0, MESSAGES - 1, 3, f'{where}.id')
        v = n - MESSAGE_BASE if n >= MESSAGE_BASE else n | 0x2000
        return bytes([0x40 | v >> 8, v & 0xFF])
    if op == 'if':
        fields(value, ('op', 'cond', 'then'), ('else',), where)
        out = b'\x07' + encode_cond(value['cond'], f'{where}.cond') + encode_branch(value['then'], f'{where}.then')
        if 'else' in value:
            out += b'\x0b' + encode_branch(value['else'], f'{where}.else')
        return out
    if op in FLAG_CODES:
        code, arg = FLAG_CODES[op]
        fields(value, ('op', 'index', arg), (), where)
        return bytes([code, byte(value['index'], f'{where}.index'), byte(value[arg], f'{where}.{arg}')])
    if op == 'call':
        fields(value, ('op', 'target'), (), where)
        t = hexnum(value['target'], 0x8000, 0xFFFF, 4, f'{where}.target')
        return bytes([0, t & 0xFF, t >> 8])
    raise ValueError(f'{where}: 모르는 명령 {op!r}(msg·if·flag-off·flag-on·flag-set·call)')


def encode_script(body, where):
    if not isinstance(body, list) or not body:
        raise ValueError(f'{where}: body 는 명령이 하나 이상인 목록이어야 함')
    code = b''.join(encode_op(op, f'{where}[{i}]') for i, op in enumerate(body)) + b'\x3f'
    if len(code) > MAX_SCRIPT:
        raise ValueError(f'{where}: {len(code)}바이트. 06:B065 는 Y(8비트)로 읽어 {MAX_SCRIPT}바이트까지')
    if skip_length(code) != len(code):
        raise ValueError(f'{where}: 06:AFA9 가 이 스크립트를 건너뛸 때 경계가 어긋남'
                         '(인자·메시지 바이트가 3F 로 읽히거나 길이 규칙이 다름). 인자를 바꾸거나 명령 순서를 바꿈')
    again, end = read_script(Rom(code), 0x8000)
    if end != 0x8000 + len(code) or again != body:
        raise ValueError(f'{where}: 부호화한 바이트를 다시 읽은 결과가 입력과 다름')
    return code


def scripts_from(doc):
    fields(doc, ('format', 'scripts'), (), '문서')
    if doc['format'] != FORMAT:
        raise ValueError(f'format={FORMAT} 이 필요함')
    if not isinstance(doc['scripts'], list):
        raise ValueError('scripts 는 목록이어야 함')
    out = {}
    for i, row in enumerate(doc['scripts']):
        fields(row, ('talk', 'body'), (), f'scripts[{i}]')
        t = hexnum(row['talk'], FIRST_SCRIPT, 0xFFF, 3, f'scripts[{i}].talk')
        if FIRST_SPECIAL2 <= t < EXTRA_BASE:
            raise ValueError(f'scripts[{i}].talk: 011~24E(원래 스크립트)나 900~FFF(덧붙인 스크립트)만 받음')
        if t in out:
            raise ValueError(f'대화 번호 {t:03X} 를 두 번 적음')
        out[t] = encode_script(row['body'], f'talk {t:03X}')
    return out


def place(rom, groups, codes, at=None, repack=False):
    """묶음마다 새 시작 주소. 원래 자리에 들어가면 그대로, 아니면 --at 부터 차례로(repack 이면 06:8129 부터 다시 채움)."""
    sizes = [sum(len(codes.get(t, c)) for t, _, c, _ in rows) for _, rows in groups]
    starts, overflow = [], []
    cursor = REGION[0]
    for g, (start, rows) in enumerate(groups):
        old = sum(len(c) for _, _, c, _ in rows)
        if repack:
            if cursor + sizes[g] <= REGION[1]:
                starts.append(cursor)
                cursor += sizes[g]
                continue
        elif sizes[g] <= old:
            starts.append(start)
            continue
        starts.append(None)
        overflow.append(g)
    if overflow:
        if at is None:
            need = ', '.join(f'묶음 {g}({sizes[g]}바이트)' for g in overflow)
            raise ValueError(f'원래 자리를 넘는 묶음: {need}. --at 06:XXXX(뱅크 06 빈 자리)이나 --repack 이 필요함')
        cursor = at
        for g in overflow:
            starts[g] = cursor
            cursor += sizes[g]
        if cursor > 0x070000:
            raise ValueError(f'--at {cpu(lorom(at))} 부터 {cursor - at}바이트가 뱅크 06 끝을 넘음')
        # 옮길 곳은 빈 자리 지도 안이거나, 이번에 다시 놓는 묶음이 원래 자리 밖에서 차지하던 곳이어야 한다.
        # 그대로 두는 묶음의 자리는 넣지 않는다(아래 겹침 검사와 함께 덮어쓰기를 막음).
        lo, hi = lorom(at), lorom(at) + cursor - at
        allowed = list(free_ranges(rom.d))
        for g, (start, rows) in enumerate(groups):
            if (g in overflow or starts[g] != start) and not REGION[0] <= start < REGION[1]:
                allowed.append((lorom(start), sum(len(c) for _, _, c, _ in rows)))
        allowed.sort()
        covered = lo
        for s, n in allowed:
            if s <= covered < s + n:
                covered = s + n
        if covered < hi:
            raise ValueError(f'--at {cpu(lo)}~{cpu(hi - 1)}: {cpu(covered)} 부터가 빈 자리 지도 밖')
    spans = sorted((starts[g], starts[g] + sizes[g], g) for g in range(len(groups)))
    for (_, e1, g1), (s2, _, g2) in zip(spans, spans[1:]):
        if s2 < e1:
            raise ValueError(f'묶음 {g1}·{g2} 의 새 자리가 {cpu(lorom(s2))} 에서 겹침')
    return starts


def runs(old, new, base):
    """old 와 new 가 다른 곳을 하나의 쓰기로(처음 다른 곳 ~ 마지막 다른 곳)."""
    diff = [i for i in range(len(new)) if old[i] != new[i]]
    if not diff:
        return []
    i, j = diff[0], diff[-1] + 1
    return [(base + i, new[i:j], old[i:j])]


def place_extra(rom, cfg, rows, codes, extra_at, hook_at):
    """덧붙인 스크립트의 바이트 쓰기 {파일 위치: 값}. 바뀐 것이 없으면 빈 사전.
    롬에 이미 있는 덧붙인 스크립트는 그대로 이어 받으므로 줄이거나 지울 수 없고, 옮기면 옛 자리는 남는다."""
    old = {t: code for t, _, code, _ in rows}
    merged = {**old, **{t: c for t, c in codes.items() if t >= EXTRA_BASE}}
    if merged == old and extra_at is None and hook_at is None:
        return {}
    count = len(merged)
    missing = [f'{t:03X}' for t in range(EXTRA_BASE, EXTRA_BASE + count) if t not in merged]
    if missing:
        raise ValueError(f'덧붙인 스크립트는 900 부터 빈 번호 없이 이어져야 함(빠짐 {missing[:4]})')
    groups = (count + 31) // 32
    blob_size = groups * 2 + sum(len(c) for c in merged.values())
    here = None
    if cfg is not None:
        here = (cfg['table'], (cfg['end'] - EXTRA_BASE + 31) // 32 * 2 + sum(len(c) for c in old.values()))
    if extra_at is None:
        if here is None or blob_size > here[1]:
            raise ValueError(f'덧붙인 스크립트 {blob_size}바이트를 둘 --extra-at(뱅크 30~3F)이 필요함')
        extra_at = here[0]
    if not 0x30 <= extra_at >> 16 <= 0x3F:
        # 06:B065 가 데이터 뱅크로 $0F1C·$0A01 같은 WRAM 거울 주소를 읽어(코드 읽기) 뱅크 00~3F 여야 하고,
        # 원래 롬(00~2F)에는 빈 자리가 거의 없으므로 늘린 뱅크 30~3F 만 받는다.
        raise ValueError('--extra-at: 뱅크 30~3F 만 받음(데이터 뱅크로 WRAM 거울을 읽는 늘린 뱅크)')
    if (extra_at & 0xFFFF) + blob_size > 0x10000:
        raise ValueError(f'--extra-at {cpu(lorom(extra_at))}: {blob_size}바이트가 뱅크를 넘음')
    # 이미 늘린 롬이면 옛 덧붙인 자리 밖의 바이트가 비어 있어야 한다(0, 또는 빌더가 뱅크 첫 8바이트에 쓰는 표지).
    old_span = range(lorom(here[0]), lorom(here[0]) + here[1]) if here else range(0)
    for off in range(lorom(extra_at), lorom(extra_at) + blob_size):
        if off < len(rom.d) and off not in old_span and rom.d[off] and off % 0x8000 >= 8:
            raise ValueError(f'--extra-at: {cpu(off)} 에 다른 자료가 있음(비어 있는 곳을 고름)')
    if hook_at is None:
        if cfg is None:
            raise ValueError('덧붙인 스크립트 루틴(84바이트)을 둘 --hook-at(뱅크 06 빈 자리)이 필요함')
        hook_at = cfg['hook']
    out = {}
    addresses, a = [], extra_at + groups * 2
    for n, t in enumerate(sorted(merged)):
        if n % 32 == 0:
            addresses.append(a)
        code = merged[t]
        out.update({lorom(a) + i: v for i, v in enumerate(code)})
        a += len(code)
    table = b''.join((x & 0xFFFF).to_bytes(2, 'little') for x in addresses)
    out.update({lorom(extra_at) + i: v for i, v in enumerate(table)})
    hooks, starts = extra_hooks(hook_at, EXTRA_BASE + count, extra_at, extra_at >> 16)
    if cfg is None or hook_at != cfg['hook']:
        if hook_at >> 16 != 0x06 or not any(st <= lorom(hook_at) and lorom(hook_at) + len(hooks) <= st + n
                                            for st, n in free_ranges(rom.d)):
            raise ValueError(f'--hook-at {cpu(lorom(hook_at))}: 뱅크 06 빈 자리 지도 안이어야 함({len(hooks)}바이트)')
    out.update({lorom(hook_at) + i: v for i, v in enumerate(hooks)})
    for name, raw in site_bytes(starts).items():
        out.update({lorom(SITES[name]) + i: v for i, v in enumerate(raw)})
    return out


def edits(rom, doc, at=None, repack=False, extra_at=None, hook_at=None):
    codes = scripts_from(doc)
    groups = layout(rom)
    starts = place(rom, groups, codes, at, repack)
    out = []
    for g, (start, rows) in enumerate(groups):
        new = b''.join(codes.get(t, c) for t, _, c, _ in rows)
        o = lorom(starts[g])
        # 옮긴 묶음은 통째로 쓴다. 차이만 쓰면 원래 바이트와 같은 곳이 다른 패치 목록에 빈 곳처럼 보인다.
        moved = [(o, new, bytes(rom.d[o:o + len(new)]))] if starts[g] != start else []
        for off, data, orig in moved or runs(rom.d[o:o + len(new)], new, o):
            out.append((off, data, orig, f'묶음 {g} 대화 {rows[0][0]:03X}~{rows[-1][0]:03X}'))
    table = b''.join((s & 0xFFFF).to_bytes(2, 'little') for s in starts)
    o = lorom(TABLE)
    for off, data, orig in runs(rom.d[o:o + len(table)], table, o):
        out.append((off, data, orig, '묶음 포인터 06:AEF8'))
    cfg, rows = extra_layout(rom)
    extra = place_extra(rom, cfg, rows, codes, extra_at, hook_at)
    taken = {off + i for off, data, _, _ in out for i in range(len(data))}
    if taken & set(extra):
        raise ValueError(f'덧붙인 스크립트 쓰기가 원래 스크립트 쓰기와 겹침: {cpu(min(taken & set(extra)))}')
    changed = sorted(off for off, v in extra.items() if off >= len(rom.d) or rom.d[off] != v)
    while changed:
        first = end = changed[0]
        while end in extra and (end - first) < 0x8000 and (end % 0x8000 or end == first) \
                and (end >= 0x180000) == (first >= 0x180000):
            end += 1
        data = bytes(extra[i] for i in range(first, end))
        orig = bytes(rom.d[first:end]) if first < 0x180000 else None
        if orig != data:
            out.append((first, data, orig, '덧붙인 스크립트'))
        changed = [c for c in changed if c >= end]
    return out, starts


def patch(rom, doc, at=None, repack=False, extra_at=None, hook_at=None):
    writes, _ = edits(rom, doc, at, repack, extra_at, hook_at)
    result = {'format': 'dq5patch/1', 'name': 'talk-scripts', 'writes': [
        {'at': cpu(off), 'hex': data.hex(' '), **({'orig': orig.hex(' ')} if orig is not None else {}), 'note': note}
        for off, data, orig, note in writes]}
    top = max((off + len(data) for off, data, _, _ in writes), default=0)
    if top > 0x180000:
        result['rom_size'] = 2 if top <= 0x200000 else 3 if top <= 0x300000 else 4
    return result


def check(rom, doc=None, at=None, repack=False, extra_at=None, hook_at=None):
    from dq5build import build
    import dq5talk
    original = dump(rom)
    writes, starts = edits(rom, original if doc is None else doc, at, repack, extra_at, hook_at)
    if dq5talk.check(rom):
        raise ValueError('dq5talk.py 의 경계 검사가 실패함')
    if doc is None:
        if writes:
            raise ValueError('원본 왕복 쓰기가 0개가 아님')
        total = sum(len(c) for _, rows in layout(rom) for _, _, c, _ in rows)
        print(f'스크립트 {len(original["scripts"])}개 {total}바이트, 묶음 {GROUPS}개 원본 왕복 쓰기 0개')
        return
    top = max((off + len(data) for off, data, _, _ in writes), default=0)
    size = 0 if top <= 0x180000 else 2 if top <= 0x200000 else 3 if top <= 0x300000 else 4
    built, _ = build(rom.d, [('talk-scripts', size, writes)], size)
    moved = Rom(built)
    want = {row['talk']: row['body'] for row in original['scripts']}
    want.update({row['talk'].upper(): row['body'] for row in doc['scripts']})
    got = {row['talk']: row['body'] for row in dump(moved)['scripts']}
    if got != want:
        bad = sorted(t for t in want if got.get(t) != want[t])
        raise ValueError(f'빌드한 롬을 다시 읽은 스크립트가 다름: {bad[:8]}')
    if dq5talk.check(moved):
        raise ValueError('빌드한 롬에서 dq5talk.py 의 경계 검사가 실패함')
    addresses = [a for _, rows in layout(moved) for _, a, _, _ in rows]
    for n in range(COUNT):
        if dq5talk.script_address(moved, n) != addresses[n]:
            raise ValueError(f'스크립트 {n:03X}: 게임의 찾기(06:AF85)와 다른 주소')
    if edits(moved, doc, at, repack, extra_at, hook_at)[0]:
        raise ValueError('빌드한 롬에 같은 입력을 다시 패치하면 쓰기가 남음')
    if edits(moved, dump(moved), at, repack)[0]:
        raise ValueError('빌드한 롬을 다시 읽고 인코딩한 결과가 다름')
    moved_groups = [g for g, s in enumerate(starts) if s != layout(rom)[g][0]]
    cfg, extras = extra_layout(moved)
    if extras:
        print(f'덧붙인 스크립트 {len(extras)}개(대화 900~{extras[-1][0]:03X}), 루틴 {cpu(lorom(cfg["hook"]))}, '
              f'표 {cpu(lorom(cfg["table"]))}')
    print(f'입력 스크립트 {len(doc["scripts"])}개, 쓰기 {len(writes)}개 '
          f'{sum(len(w[1]) for w in writes)}바이트, 옮긴 묶음 '
          + (', '.join(f'{g}→{cpu(lorom(starts[g]))}' for g in moved_groups) or '없음')
          + '; 다시 읽기·다시 패치 0개')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('dump')
    export.add_argument('-o', '--out', type=Path, required=True)
    export.add_argument('--talk', nargs='+', help='대화 번호(16진)')
    for name in ('patch', 'check'):
        p = sub.add_parser(name)
        p.add_argument('source', type=Path, nargs='?' if name == 'check' else None)
        if name == 'patch':
            p.add_argument('-o', '--out', type=Path, required=True)
        p.add_argument('--at', help='원래 자리를 넘는 묶음을 둘 뱅크 06 주소(빈 자리 지도 안, 예 06:FE10)')
        p.add_argument('--repack', action='store_true', help='묶음을 06:8129 부터 다시 채우고 넘치는 것만 --at 에')
        p.add_argument('--extra-at', help='대화 번호 900~ 의 덧붙인 스크립트(묶음 표 + 스크립트)를 둘 곳(뱅크 30~3F)')
        p.add_argument('--hook-at', help='덧붙인 스크립트 루틴 84바이트를 둘 뱅크 06 빈 자리(예 06:FE10)')
    args = parser.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        at = bank06(args.at) if getattr(args, 'at', None) else None
        extra_at = hook_at = None
        if getattr(args, 'extra_at', None):
            m = re.fullmatch(r'([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})', args.extra_at)
            if not m or int(m[2], 16) < 0x8000:
                raise ValueError('--extra-at 은 BB:AAAA')
            extra_at = int(m[1], 16) << 16 | int(m[2], 16)
        if getattr(args, 'hook_at', None):
            hook_at = bank06(args.hook_at)
        doc = json.loads(args.source.read_text(encoding='utf-8')) if getattr(args, 'source', None) else None
        if args.command == 'check':
            check(rom, doc, at, args.repack, extra_at, hook_at)
            return 0
        if args.command == 'dump':
            talks = None
            if args.talk:
                talks = {hexnum(t.upper().zfill(3), FIRST_SCRIPT, 0xFFF, 3, '--talk') for t in args.talk}
                if any(FIRST_SPECIAL2 <= t < EXTRA_BASE for t in talks):
                    raise ValueError('--talk: 011~24E 나 900~FFF 만 스크립트')
            result = dump(rom, talks)
        else:
            result = patch(rom, doc, at, args.repack, extra_at, hook_at)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return 0
    except (ValueError, OSError, IndexError, KeyError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
