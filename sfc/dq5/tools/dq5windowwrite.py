"""DQ5 창 레코드(04:EB48)의 자리·크기 쓰기. 전투 창도 같은 레코드를 쓴다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「창 자리·크기」. 레코드 머리 +0 아래 5비트 X, +1 아래 5비트 Y,
+2 아래 5비트 너비, +3 아래 4비트 높이(타일)만 바꾸고 나머지 비트와 내용은 그대로 둔다.
전투 메시지 창 둘(18 턴 메시지, 25 「…が あらわれた！」)은 글자·▼ 칸이 코드에 박혀 있어 두 레코드를 함께 옮기고 그 코드
피연산자도 고친다. X 만 바꾸면 피연산자만 고친다. 너비·높이를 바꾸면 글자 격자(원래 7E:1DD5, 26칸 × 6줄)를 GRID 로
옮기고 격자 루틴 넷(24:87AA·A4A4·A569·A5D9)과 24:813B 를 --message-at 에 두는 새 코드로 돌린다. 너비는 28~31(글자 칸
26~29), 높이는 7~13 의 홀수(글자 줄 3~6)이고 창 아래 끝은 원래처럼 27줄이라 Y = 28 - 높이다. 21줄보다 위로 올라가면
메시지 동안의 BG3 부분 전송(00:8E70)을 창 맨 위 줄부터로 넓히고, 공격·주문 효과 층(VRAM 1CE0, 00:FD75)은 창 위 줄까지만
올린다(00:FD92 → 새 코드). 글자는 줄을 저절로 바꾸지 않으므로 넓힌 칸·늘린 줄은 메시지 쪽이 채워야 한다.

  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc dump -o work/windows.json
  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc patch work/windows.json -o work/windows.dq5patch.json [--message-at BB:AAAA]
  python sfc/dq5/tools/dq5windowwrite.py rom/dq5.sfc check

JSON: {"format":"dq5windows/1", "windows":[{"index":"19","x":12,"y":14}]}. index 는 창 번호(16진 문자열),
x·y·w·h 가운데 바꿀 것만 적는다. 바꾼 창은 BG3 타일맵(32 × 32 타일) 안이어야 한다. +0 bit7 인 창(다른 창을 가리킴),
여러 번호가 함께 쓰는 레코드(89~8C), +0 bit6 창의 h(높이를 04:9FD3 이 일행에 맞춰 정함)는 받지 않는다.
18·25 는 한쪽만 적어도 둘 다 옮기고, 둘 다 적으면 값이 같아야 한다. h 만 적으면 Y 는 28 - h 로 둔다.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5build import BANK, parse_at  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5text import WINDOWS  # noqa: E402

FORMAT = 'dq5windows/1'
FIELDS = {'x': (0, 0x1F), 'y': (1, 0x1F), 'w': (2, 0x1F), 'h': (3, 0x0F)}
MAP_W = 32
# 전투 메시지 창. 18 은 턴 메시지(24:A5D9 가 글자 격자를 옮김), 25 는 나타난 무리(04:BCE7).
MESSAGES = (0x18, 0x25)
MESSAGE_W, MESSAGE_H, MESSAGE_Y = 28, 7, 21
# 창 아래 끝 줄(28줄부터 화면 밖). 무리 넷이면 창 25 는 한 줄 위·두 줄 더 높게 그려져(04:A070) 28줄까지 간다.
MESSAGE_BOTTOM = 27
# 높이 13 이면 무리 넷의 창 25 가 15 줄(4비트 끝)이다. Y 는 7줄(효과 층 첫 줄) 아래여야 무리 넷도 상태 창에 닿지 않는다.
MESSAGE_MAX_H = 13
EFFECT_TOP = 7
# 옮긴 글자 격자. 장면 770개에서 원래 코드의 접근이 없던 7E:A5F1~A91F 안(dq5-build-format.md).
GRID, GRID_SIZE = 0x7EA600, 0x200
# 격자 루틴 자리: (크기, 앞 바이트 sha1, 나머지 sha1). 앞 바이트(새 코드로 가는 JSL)와 원래 X 를 박은 24:A5ED·A5EE 는
# 0 으로 치고 셈한다. 원래 롬이거나 이 도구가 앞을 덮은 롬만 받는다(DQ4 메뉴 빌드의 24:A5E9 훅도 여기서 걸림).
ROUTINES = {0x24813B: (0x16, '3bf31616068a', '48d31b8b0594'), 0x2487AA: (0x4E, 'c7809863c450', '7b859cb4a4ce'),
            0x24A4A4: (0x4F, '2f39c80a4a96', 'bd40ea33e3b5'), 0x24A569: (0x6C, '86adbb1886bd', '85fb3c69ac50'),
            0x24A5D9: (0x30, 'c4f6527baaf6', '2b5ff696c127')}
MASKED = (0x24A5ED, 0x24A5EE)
# 원래 자리 → 새 코드 입구. 24:813B 는 그 자리에서 채우기만 부르고 원래 24:8151(JSR $811D)로 건너뛴다.
STUBS = {0x24813B: 'fill', 0x2487AA: 'line', 0x24A4A4: 'put', 0x24A569: 'scroll', 0x24A5D9: 'copylong'}
EFFECT_SITE, EFFECT_ORIG = 0x00FD92, bytes.fromhex('a9 80 03 8d 75 43')
# +0 bit6 창은 04:9FD3 이 높이를 다시 센다. bit5 가 켜지면 일행 수(4까지) × 2 + 3, 꺼지면 메뉴마다 달라 4비트 최대로 본다.
PARTY_HEIGHT = 4 * 2 + 3
MENU_HEIGHT = 0x0F


def integer(value, maximum, name, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}: {minimum}~{maximum} 정수여야 함')
    return value


def fields(value, allowed, name):
    if not isinstance(value, dict) or value.keys() - allowed:
        raise ValueError(f'{name}: 허용한 필드 {sorted(allowed)}만 있는 JSON 객체여야 함')


def read(rom, addr, size):
    off = lorom(addr)
    raw = bytes(rom.d[off:off + size])
    if len(raw) != size:
        raise ValueError(f'{addr:06X}: 롬에 {size}바이트가 없음')
    return raw


def records(rom):
    """창 번호 → 레코드 주소. 포인터는 첫 레코드 앞까지 놓일 수 있지만, 원본은 94 부터 0000·00FF·FFFF 같은
    창이 아닌 바이트라 8000 미만인 첫 포인터에서 센다."""
    first = rom.u16(WINDOWS)
    out = {}
    for n in range((first - (WINDOWS & 0xFFFF)) // 2):
        low = rom.u16(WINDOWS + n * 2)
        if low < 0x8000:
            break
        if low > 0x10000 - 4:
            raise ValueError(f'창 {n:02X}: 레코드 머리 04:{low:04X} 가 뱅크 04 끝을 넘음')
        out[n] = 0x040000 | low
    if not 0 < len(out) <= 0x100:
        raise ValueError('04:EB48 창 표가 원래 꼴이 아님')
    return out


def header(raw):
    return {k: raw[at] & mask for k, (at, mask) in FIELDS.items()}


def message_sites(x, y, w=MESSAGE_W, h=MESSAGE_H):
    """메시지 창 모양에 맞춘 코드 피연산자: (명령 주소, 여는 바이트, 피연산자 크기, 값, 설명). 원래 모양
    (2,21) 28 × 7 이면 원래 롬의 값이다. BG3 타일맵 버퍼(7E:5000) 안 바이트 위치는 at(줄, 칸). ▼ 는 오른쪽 테두리 바로 안
    칸이고, FD ▼ 는 글자 칸 가운데쯤(원래 26칸에서 12칸째). STA long(9F)은 아래 두 바이트만 고치고, 뱅크 바이트 7E 는
    원래 꼴인지 볼 때만 쓴다. 24:A5EC 는 모양을 바꾸면 새 코드가 대신하지만 X 쓰기와 같은 값을 둔다."""

    def at(row, col):
        return (row * 32 + col) * 2

    cols, rows = w - 2, h - 1
    lines = rows // 2
    return [(0x24A5EC, 0x9F, 2, 0x5000 + at(y, x + 1), '글자 격자 → BG3 버퍼'),
            (0x24883B, 0x9F, 2, 0x5000 + at(y + 1, x + 1), 'FD ▼(켜기)'),
            (0x24884F, 0x9F, 2, 0x5000 + at(y + 1, x + 1), 'FD ▼(끄기)'),
            (0x24881F, 0x69, 2, (cols // 2 - 1) * 2, 'FD ▼ 칸'),
            (0x24A51E, 0xA2, 2, at(y + rows - 1, x + cols), '마지막 줄 끝 ▼'),
            (0x24A528, 0xA2, 2, at(y + rows, x + cols), '무리 넷 마지막 줄 끝 ▼'),
            (0x04BCF0, 0xA9, 1, y, '무리 넷의 첫 무리 줄'),
            (0x04BCF4, 0xA9, 1, y + 1, '무리 줄'),
            (0x04BCF8, 0xA9, 1, x + 1, '무리 줄 첫 칸'),
            (0x2485FA, 0xC9, 1, lines, '줄 수(줄 바꾸기 FC)'),
            (0x248613, 0xA9, 1, lines - 1, '마지막 줄(모두 지우기)'),
            (0x24864C, 0xC9, 1, lines, '줄 수(둘째 줄부터 지우기)'),
            (0x248677, 0xC9, 1, lines, '줄 수(남은 줄 지우기)'),
            (0x24A4FA, 0xC9, 1, lines, '줄 수(줄 바꾸기)'),
            (0x008E72, 0xA9, 2, 0x1C00 + min(y, MESSAGE_Y) * 32, '부분 전송 VRAM'),
            (0x008E79, 0xA9, 2, (30 - min(y, MESSAGE_Y)) * 32, '부분 전송 워드 수'),
            (0x008E81, 0xA9, 2, 0x5000 + at(min(y, MESSAGE_Y), 0), '부분 전송 버퍼')]


def assemble(items, at):
    """[바이트 | ('label', 이름) | ('br', 옵코드, 이름) | ('jsr', 이름)] → (코드, 이름별 CPU 주소). at 은 첫 바이트의 CPU 주소."""
    labels, pos = {}, 0
    for item in items:
        if isinstance(item, bytes):
            pos += len(item)
        elif item[0] == 'label':
            labels[item[1]] = at + pos
        else:
            pos += 2 if item[0] == 'br' else 3
    code = bytearray()
    for item in items:
        if isinstance(item, bytes):
            code += item
        elif item[0] == 'br':
            delta = labels[item[2]] - (at + len(code) + 2)
            if not -128 <= delta < 128:
                raise ValueError(f'분기 {item[2]} 가 멂')
            code += bytes([item[1], delta & 0xFF])
        elif item[0] == 'jsr':
            code += b'\x20' + (labels[item[1]] & 0xFFFF).to_bytes(2, 'little')
    if (at & 0xFFFF) + len(code) > 0x10000:
        raise ValueError(f'{at >> 16:02X}:{at & 0xFFFF:04X}: 새 코드 {len(code)}바이트가 뱅크 끝을 넘음')
    return bytes(code), labels


def message_items(x, y, w, h):
    """격자 루틴을 옮긴 새 코드. 원래 루틴(24:8133·87AA·A4A4·A569·A5C5·A5D9)과 같은 일을 하되, 격자를 GRID 에 두고
    칸·줄 수를 w·h 에 맞춘다. 격자를 만지는 동안만 데이터 뱅크를 7E 로 두고, 바깥 루틴(04:991D 프레임 기다림·
    00:950E)은 부른 쪽의 데이터 뱅크로 부른다. 줄 0 은 창 위 테두리(8D)이고 그 줄의 탁점(84·83)은 테두리에 얹은
    92·93 으로 바꾼다(원래와 같음). y < 21 이면 끝에 효과 층 전송 크기를 고르는 eff 를 더한다."""
    b = bytes.fromhex
    cols, rows = w - 2, h - 1
    grid = GRID & 0xFFFF

    def w16(v):
        return v.to_bytes(2, 'little')

    db7e = b('8b f4 7e 7e ab ab')
    items = [
        # 24:813B 자리(PHP PHB 뒤, M 8 X 16)에서 JSL. 격자 전체를 01, 줄 0 을 8D 로.
        ('label', 'fill'), db7e, b('a9 01 a2') + w16(cols * rows - 1),
        ('label', 'f1'), b('9d') + w16(grid) + b('ca'), ('br', 0x10, 'f1'),
        b('a9 8d a2') + w16(cols - 1), ('label', 'f2'), b('9d') + w16(grid) + b('ca'), ('br', 0x10, 'f2'), b('ab 6b'),
        # 24:87AA: $0F0E 줄을 지움(줄 0 이면 테두리 줄을 8D 로).
        ('label', 'line'), b('08 5a da'), db7e, b('e2 20 c2 10 ad 0e 0f'), ('br', 0xF0, 'lzero'),
        b('85 00 64 01 c2 20 a9 00 00'), ('label', 'lmul'), b('18 69') + w16(cols * 2) + b('c6 00'), ('br', 0xD0, 'lmul'),
        b('aa da e2 20 a0') + w16(cols - 1) + b('a9 01'),
        ('label', 'l1'), b('9d') + w16(grid) + b('e8 88'), ('br', 0x10, 'l1'), b('fa'), ('br', 0x80, 'ltail'),
        ('label', 'lzero'), b('a9 8d a2') + w16(cols - 1), ('label', 'l2'), b('9d') + w16(grid) + b('ca'),
        ('br', 0x10, 'l2'), b('e8'),
        ('label', 'ltail'), b('a0') + w16(cols - 1) + b('a9 01'),
        ('label', 'l3'), b('9d') + w16(grid + cols) + b('e8 88'), ('br', 0x10, 'l3'), b('ab fa 7a 28 6b'),
        # 24:A4A4: 글자 A 를 ($0F0E 줄, $0F0D 칸)에. 탁점은 윗줄에, 아니면 칸을 하나 늘린다. 그 뒤 격자를 버퍼로.
        ('label', 'put'), b('08'), db7e, b('e2 30 48 7b ad 0d 0f c2 20 ae 0e 0f'), ('br', 0xF0, 'pcol'),
        ('label', 'pmul'), b('18 69') + w16(cols * 2) + b('ca'), ('br', 0xD0, 'pmul'),
        ('label', 'pcol'), b('c2 10 aa e2 20 68 c9 84'), ('br', 0xD0, 'p83'),
        b('da e2 10 ac 0e 0f'), ('br', 0xD0, 'pdak'), b('a9 92'), ('br', 0x80, 'pdak'),
        ('label', 'p83'), b('c9 83'), ('br', 0xD0, 'pchar'),
        b('da e2 10 ac 0e 0f'), ('br', 0xD0, 'pdak'), b('a9 93'), ('br', 0x80, 'pdak'),
        ('label', 'pchar'), b('9d') + w16(grid + cols) + b('ee 0d 0f'), ('br', 0x80, 'pcopy'),
        ('label', 'pdak'), b('c2 10 fa 9d') + w16(grid),
        ('label', 'pcopy'), ('jsr', 'copy'), b('ab 28 6b'),
        # 24:A569: 한 줄 올리기. 반 줄씩 두 번 밀며 그 사이에 한 프레임 낸다.
        ('label', 'scroll'), b('08 e2 20 c2 10'), db7e, b('a2') + w16(cols - 1) + b('a9 8d'),
        ('label', 's1'), b('9d') + w16(grid) + b('ca'), ('br', 0x10, 's1'), ('jsr', 'shift'),
        b('a2') + w16(cols - 1) + b('a9 01'),
        ('label', 's2'), b('9d') + w16(grid + cols * (rows - 1)) + b('ca'), ('br', 0x10, 's2'),
        ('jsr', 'copy'), b('ab 22 1d 99 04 a2 03 00 22 0e 95 00'), db7e, b('a2 00 00'),
        ('label', 's3'), b('bd') + w16(grid + cols) + b('c9 84'), ('br', 0xD0, 's4'), b('a9 92'), ('br', 0x80, 's5'),
        ('label', 's4'), b('c9 83'), ('br', 0xD0, 's6'), b('a9 93'), ('label', 's5'), b('9d') + w16(grid),
        ('label', 's6'), b('e8 e0') + w16(cols), ('br', 0x90, 's3'), ('jsr', 'shift'), ('jsr', 'copy'),
        b('ab 22 1d 99 04 a2 03 00 22 0e 95 00 28 6b'),
        # 24:A5C5: 줄 2~ 를 한 줄 위로(데이터 뱅크 7E 에서 부름).
        ('label', 'shift'), b('a2 00 00'),
        ('label', 'h1'), b('bd') + w16(grid + cols * 2) + b('9d') + w16(grid + cols) + b('e8 e0') + w16(cols * (rows - 2)),
        ('br', 0x90, 'h1'), b('60'),
        # 24:A5D9: 격자를 BG3 버퍼(창 맨 위 줄, X + 1 칸부터)로.
        ('label', 'copy'), b('08'), db7e, b('e2 20 c2 10 a2 00 00 9b'),
        ('label', 'c1'), b('a9') + bytes([cols]) + b('85 00'),
        ('label', 'c2'), b('b9') + w16(grid) + b('9f') + (0x7E5000 + (y * 32 + x + 1) * 2).to_bytes(3, 'little')
        + b('c8 e8 e8 c6 00'), ('br', 0xD0, 'c2'),
        b('c2 20 8a 18 69') + w16(0x40 - cols * 2) + b('aa e2 20 c0') + w16(cols * rows), ('br', 0x90, 'c1'),
        b('ab 28 60'),
        ('label', 'copylong'), ('jsr', 'copy'), b('6b')]
    if y < MESSAGE_Y:
        # 00:FD92(NMI, M 16, 데이터 뱅크 00). BG3 효과 층(1CE0)이면 창 위 줄까지만, 전투 배경(BG1·BG2)은 원래 0x380.
        items += [('label', 'eff'), b('ad 5e 0f c9 e0 1c'), ('br', 0xD0, 'e1'), b('a9') + w16((y - EFFECT_TOP) * 64),
                  ('br', 0x80, 'e2'), ('label', 'e1'), b('a9 80 03'), ('label', 'e2'), b('8d 75 43 6b')]
    return items


def stub(name, labels):
    target = labels[name].to_bytes(3, 'little')
    # 24:813B 는 JSL 뒤 BRA 로 24:8151(JSR $811D) 에 간다. 나머지는 JSL 뒤 RTS.
    return b'\x22' + target + (b'\x80\x10' if name == 'fill' else b'\x60')


def message_at(rom):
    """24:87AA 가 이 도구의 JSL 이면 새 코드 자리, 원래 꼴이면 None."""
    head = read(rom, 0x2487AA, 5)
    if head[0] != 0x22 or head[4] != 0x60:
        return None
    line = int.from_bytes(head[1:4], 'little')
    _, labels = assemble(message_items(2, MESSAGE_Y, MESSAGE_W, MESSAGE_H), 0)
    return line - labels['line']


def routine_state(rom, at):
    """격자 루틴 자리가 원래 꼴이면 'original', at 의 새 코드를 가리키면 'hooked'. 아니면 오류."""
    _, labels = assemble(message_items(2, MESSAGE_Y, MESSAGE_W, MESSAGE_H), at or 0)
    states = set()
    for addr, (size, head, tail) in ROUTINES.items():
        raw = bytearray(read(rom, addr, size))
        n = len(stub(STUBS[addr], labels))
        for m in MASKED:
            if addr <= m < addr + size:
                raw[m - addr] = 0
        if hashlib.sha1(bytes(raw[n:]).rjust(size, b'\0')).hexdigest()[:12] != tail:
            states.add(None)
        elif hashlib.sha1(bytes(raw[:n])).hexdigest()[:12] == head:
            states.add('original')
        elif at is not None and bytes(raw[:n]) == stub(STUBS[addr], labels):
            states.add('hooked')
        else:
            states.add(None)
    if len(states) != 1 or None in states:
        raise ValueError('격자 루틴(24:813B·87AA·A4A4·A569·A5D9)이 원래 꼴도, 이 도구가 고친 꼴도 아님')
    return states.pop()


def message_edits(rom, table, sharing, rows, at=None):
    """창 18·25 를 같은 자리·크기로 바꾸는 쓰기. rows 는 {창: 문서 줄}, at 은 새 코드 자리(--message-at)."""
    olds = {n: read(rom, table[n], 4) for n in MESSAGES}
    base = header(olds[MESSAGES[0]])
    for n, old in olds.items():
        if old[0] & 0x80 or len(sharing[table[n]]) > 1 or header(old) != base:
            raise ValueError('창 18·25 레코드가 원래 꼴(따로 쓰는 레코드, 같은 자리·크기)이 아님')
    want = dict(base)
    for key, (_, mask) in FIELDS.items():
        values = {integer(row[key], mask, f'창 {n:02X} {key}') for n, row in rows.items() if key in row}
        if len(values) > 1:
            raise ValueError(f'창 18·25 는 함께 옮겨 {key} 가 같아야 함')
        if values:
            want[key] = values.pop()
    if any('h' in row and 'y' not in row for row in rows.values()):
        want['y'] = MESSAGE_BOTTOM + 1 - want['h']
    current = message_at(rom)
    if current is not None and at is not None and at != current:
        raise ValueError(f'새 코드가 이미 {current >> 16:02X}:{current & 0xFFFF:04X} 에 있음(--message-at 을 같게 두거나 뺌)')
    at = current if current is not None else at
    if want == base:
        return []
    if want['w'] < MESSAGE_W:
        raise ValueError(f'창 18·25 너비는 {MESSAGE_W} 이상: 글자는 줄을 저절로 바꾸지 않아(24:A4A4 는 칸을 세기만 함) '
                         '좁히면 원래 메시지가 테두리를 넘음')
    if want['h'] % 2 == 0 or not MESSAGE_H <= want['h'] <= MESSAGE_MAX_H:
        raise ValueError(f'창 18·25 높이는 {MESSAGE_H}~{MESSAGE_MAX_H} 의 홀수(글자 줄 하나가 두 줄, 위 테두리 줄에 첫 줄 탁점): '
                         f'무리 넷이면 창 25 가 두 줄 더 높아져 4비트를 넘음')
    if want['y'] + want['h'] != MESSAGE_BOTTOM + 1:
        raise ValueError(f'창 18·25 아래 끝은 {MESSAGE_BOTTOM}줄(Y = 28 - 높이): 28줄부터는 화면 밖이고, 글자 격자는 '
                         '창 맨 위 줄부터 높이 - 1 줄을 채움')
    if want['x'] + want['w'] > MAP_W:
        raise ValueError('창 18·25: BG3 타일맵 32칸 밖')
    shaped = (want['w'], want['h']) != (MESSAGE_W, MESSAGE_H) or current is not None
    if shaped and at is None:
        raise ValueError('창 18·25 너비·높이를 바꾸려면 새 격자 루틴을 둘 자리(--message-at BB:AAAA)가 필요함')
    if (want['w'] - 2) * (want['h'] - 1) > GRID_SIZE:
        raise ValueError('글자 격자가 GRID 자리보다 큼')
    out = []
    for n in MESSAGES:
        new = bytearray(olds[n])
        for key, (pos, mask) in FIELDS.items():
            new[pos] = new[pos] & ~mask & 0xFF | want[key]
        out.append((table[n], bytes(new), olds[n], f'window {n:02X}'))
    for (addr, op, size, before, note), (_, _, _, after, _) in zip(message_sites(**base), message_sites(**want)):
        long = op == 0x9F
        old = read(rom, addr, 1 + size + long)
        if old[0] != op or int.from_bytes(old[1:1 + size], 'little') != before or long and old[-1] != 0x7E:
            raise ValueError(f'{addr >> 16:02X}:{addr & 0xFFFF:04X}: {note} 코드가 원래 꼴이 아님')
        if after != before:
            out.append((addr + 1, after.to_bytes(size, 'little'), old[1:1 + size], f'message window: {note}'))
    # 옮길 때만 본다. 18·25 를 그대로 두면 DQ4 메뉴 빌드처럼 격자 루틴에 다른 고리를 건 롬도 dump → patch·check 가 0 이어야
    # 한다. 피연산자 꼴을 먼저 봐, 24:A5E9 고리가 덮은 24:A5EC 는 X 만 옮길 때 원래 도구와 같은 오류로 멈춘다.
    routine_state(rom, current)
    if not shaped:
        return out
    code, labels = assemble(message_items(**want), at)
    out.append((at, code, None, 'message window: 옮긴 글자 격자 루틴'))
    for addr, name in STUBS.items():
        old = read(rom, addr, len(stub(name, labels)))
        out.append((addr, stub(name, labels), old, f'message window: 격자 루틴 → 새 코드({name})'))
    effect = read(rom, EFFECT_SITE, len(EFFECT_ORIG))
    hook = b'\x22' + labels['eff'].to_bytes(3, 'little') + b'\xea\xea' if 'eff' in labels else EFFECT_ORIG
    if effect != EFFECT_ORIG and not (effect[0] == 0x22 and effect[4:] == b'\xea\xea'):
        raise ValueError('00:FD92: 효과 층 전송 크기 코드가 원래 꼴이 아님')
    out.append((EFFECT_SITE, hook, effect, 'message window: 효과 층 전송 크기'))
    return out


def dump(rom):
    out = []
    for n, addr in records(rom).items():
        raw = read(rom, addr, 4)
        if not raw[0] & 0x80:
            out.append({'index': f'{n:02X}', **header(raw)})
    return {'format': FORMAT, 'windows': out}


def edits(rom, doc, at=None):
    fields(doc, {'format', 'windows'}, '문서')
    if doc.get('format') != FORMAT or not isinstance(doc.get('windows'), list):
        raise ValueError(f'format={FORMAT}과 windows 배열이 필요함')
    table = records(rom)
    sharing = {}
    for n, addr in table.items():
        sharing.setdefault(addr, []).append(n)
    out, seen, pair = [], set(), {}
    for row in doc['windows']:
        fields(row, {'index', *FIELDS}, '창')
        text = row.get('index')
        n = int(text, 16) if isinstance(text, str) and re.fullmatch(r'[0-9A-Fa-f]{2}', text) else None
        if n not in table or n in seen:
            raise ValueError(f'index {text!r}: 중복 없는 창 번호(16진 두 자리, 00~{len(table) - 1:02X})여야 함')
        seen.add(n)
        if n in MESSAGES:
            pair[n] = row
            continue
        addr = table[n]
        old = read(rom, addr, 4)
        if old[0] & 0x80:
            raise ValueError(f'창 {n:02X}: 다른 창을 가리키는 레코드라 고칠 수 없음')
        new = bytearray(old)
        for key, (pos, mask) in FIELDS.items():
            if key in row:
                new[pos] = new[pos] & ~mask & 0xFF | integer(row[key], mask, f'창 {n:02X} {key}')
        h = header(new)
        height = (PARTY_HEIGHT if new[0] & 0x20 else MENU_HEIGHT) if new[0] & 0x40 else h['h']
        # bit6 창이 원래 Y 보다 내려가지 않으면 원본 자리에서 그려지던 높이 그대로라 최악 높이로 막지 않는다.
        if new[0] & 0x40 and h['y'] <= header(old)['y']:
            height = 0
        # 원본에도 높이 1 인 창(28·8F)이 있어, 너비·높이 하한은 문서가 적은 필드에만 건다.
        if new != old and (h['x'] + h['w'] > MAP_W or h['y'] + height > MAP_W
                           or any(k in row and h[k] < 2 for k in ('w', 'h'))):
            raise ValueError(f'창 {n:02X}: BG3 타일맵 32 × 32 밖이거나 고친 너비·높이가 2 미만임')
        if new != old and len(sharing[addr]) > 1:
            names = '·'.join(f'{m:02X}' for m in sharing[addr])
            raise ValueError(f'창 {n:02X}: 레코드 {addr >> 16:02X}:{addr & 0xFFFF:04X} 를 {names} 가 함께 써 따로 고칠 수 없음')
        if old[0] & 0x40 and new[3] != old[3]:
            raise ValueError(f'창 {n:02X}: +0 bit6 창은 높이를 04:9FD3 이 일행에 맞춰 정해 h 를 받지 않음')
        out.append((addr, bytes(new), old, f'window {n:02X}'))
    if pair:
        out += message_edits(rom, table, sharing, pair, at)
    return out


def patch(rom, doc, name='windows', at=None):
    """새 코드(orig 없음)는 빌더가 원래 롬의 빈 자리나 늘린 자리인지 본다."""
    return {'format': 'dq5patch/1', 'name': name, 'writes': [
        {'at': f'{a >> 16:02X}:{a & 0xFFFF:04X}', 'hex': new.hex(' '), **({'orig': old.hex(' ')} if old is not None else {}),
         'note': note}
        for a, new, old, note in edits(rom, doc, at) if new != old]}


def check(rom):
    """다시 뽑은 자리·크기로 쓰기를 셈해 0 이어야 한다. 새 코드가 있는 롬이면 그 바이트도 지금 모양으로 다시 짠 것과 견준다."""
    doc = dump(rom)
    changed = 0
    for addr, new, old, _ in edits(rom, doc):
        changed += new != old
    at = message_at(rom)
    if at is not None:
        base = header(read(rom, records(rom)[MESSAGES[0]], 4))
        code, labels = assemble(message_items(**base), at)
        changed += read(rom, at, len(code)) != code
        changed += sum(read(rom, addr, len(stub(name, labels))) != stub(name, labels) for addr, name in STUBS.items())
        hook = b'\x22' + labels['eff'].to_bytes(3, 'little') + b'\xea\xea' if 'eff' in labels else EFFECT_ORIG
        changed += read(rom, EFFECT_SITE, len(hook)) != hook
    print(f'창 {len(doc["windows"])}개: 다른 쓰기 {changed}개' + (f', 격자 루틴 {at >> 16:02X}:{at & 0xFFFF:04X}' if at else ''))
    return bool(changed)


def address(text):
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', text):
        raise argparse.ArgumentTypeError('BB:AAAA 로 적어야 함')
    try:
        off, _ = parse_at(text)
    except Exception as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return (off // BANK) << 16 | 0x8000 | off % BANK


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom')
    sub = parser.add_subparsers(dest='command', required=True)
    out = sub.add_parser('dump')
    out.add_argument('-o', '--out', required=True)
    write = sub.add_parser('patch')
    write.add_argument('source')
    write.add_argument('-o', '--out', required=True)
    write.add_argument('--name', default='windows')
    write.add_argument('--message-at', type=address,
                       help='창 18·25 너비·높이를 바꿀 때 옮긴 글자 격자 루틴을 둘 자리(빈 롬 자리, 약 400바이트)')
    sub.add_parser('check')
    args = parser.parse_args()
    try:
        with open(args.rom, 'rb') as f:
            rom = Rom(f.read())
        if args.command == 'check':
            return int(check(rom))
        if args.command == 'dump':
            result = dump(rom)
        else:
            with open(args.source, encoding='utf-8') as f:
                result = patch(rom, json.load(f), args.name, args.message_at)
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(f'{args.command} → {args.out}')
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
