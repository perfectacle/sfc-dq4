"""DQ5(SFC) 인물 대화 번호 → 대화 스크립트 → 메시지. 형식은 docs/dq5-text-format.md 의 「대화」.

말을 걸면 06:AF62 가 인물 표의 대화 번호(7E:36E0 하위, 7E:3700 상위)를 읽어 갈래를 고른다(06:AFF4).
  T < 011          06:DBD2 특수 기능. 06:DBDB 점프 표의 T 번째 처리기(000 은 메시지 1CC, 001~010 은 가게·여관·교회 등)
  011 <= T < 24F   대화 스크립트 T-011. 06:AEF8 표의 32개 묶음 포인터에서 3F 로 끝나는 스크립트를 건너뛰어 찾는다
  24F <= T < 26D   06:B34F. 메시지 T + 3C6 을 띄우고 はい/いいえ 창, はい 면 메시지 +1, いいえ 면 +2
  26D <= T         메시지 T + 3C6(06:AFFB, T - 24F + 615)
스크립트 명령은 06:B065 가 실행한다.

사용:
  python tools/dq5talk.py rom/dq5.sfc 012         # 대화 번호 012 의 스크립트와 메시지
  python tools/dq5talk.py rom/dq5.sfc 17 00       # 맵 17/00 인물(낮)의 대화
  python tools/dq5talk.py rom/dq5.sfc --check     # 스크립트 경계 검사
  python tools/dq5talk.py rom/dq5.sfc --calls     # 스크립트의 네이티브 호출 대상과 횟수
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import dq5npc  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5text import message, text  # noqa: E402

BLOCKS = 0x06AEF8
SPECIALS = 0x06DBDB
SCRIPT_BANK = 0x06
FIRST_SCRIPT, FIRST_SPECIAL2, FIRST_DIRECT = 0x011, 0x24F, 0x26D
MESSAGE_BASE = 0x615
# 06:AFA9 가 스크립트를 건너뛸 때 3바이트로 보는 바이트(00 은 06:AFD8). 나머지는 bit6 이면 2바이트, 아니면 1바이트.
THREE_BYTE = (0x00, *range(0x17, 0x1D))


def talk_kind(t):
    if t < FIRST_SCRIPT:
        return 'special'
    if t < FIRST_SPECIAL2:
        return 'script'
    if t < FIRST_DIRECT:
        return 'special2'
    return 'message'


def script_address(rom, n):
    """06:AF85~AFE9. 스크립트 n(= 대화 번호 - 011)의 시작 주소. 게임과 같은 규칙으로 앞의 스크립트를 건너뛴다."""
    a = SCRIPT_BANK << 16 | rom.u16(BLOCKS + (n >> 5) * 2)
    for _ in range(n & 0x1F):
        while True:
            b = rom.u8(a)
            a += 1
            if b in THREE_BYTE:
                a += 2
            elif b & 0x40:
                a += 1
            elif b == 0x3F:
                break
    return a


def message_number(b0, b1):
    """06:B070~B086. 명령 바이트 bit6 이 메시지. bit5 면 번호 그대로, 아니면 615 를 더한다."""
    v = (b0 & 0x3F) << 8 | b1
    return v & 0x1FFF if v & 0x2000 else v + MESSAGE_BASE


# 06:B27E. 조건 바이트(bit7 = 뒤집기, 아래 6비트 = 조건 코드)를 포함한 길이. 1B 는 7E:2190+idx & mask 가 켜졌는지(06:B31F).
COND_SIZE = {0x02: 1, 0x05: 1, 0x14: 1, 0x1E: 1, 0x1F: 1, 0x20: 1,
             0x03: 2, 0x11: 2, 0x13: 2, 0x16: 2, 0x1A: 3, 0x1B: 3, 0x1C: 3}
# 06:B23F. 분기를 건너뛸 때 쓰는 명령 길이. bit6 이 켜진 바이트는 메시지(2).
OP_SIZE = {0x00: 3, 0x01: 5, 0x12: 2, 0x17: 3, 0x18: 3, 0x19: 3}
OP_NAME = {0x00: 'call', 0x01: 'call', 0x12: 'special', 0x17: 'flag-off', 0x18: 'flag-on', 0x19: 'flag-set'}
# 06:B15B 가 고르는 조건 처리기의 뜻. 처리기가 A = 0 을 돌려주면 참이다(조건 바이트 bit7 이 켜져 있으면 뒤집음).
# 「실측」 은 선실 파파스의 스크립트를 07 <조건> 61 6B 0B 61 29 3F 로 덮어 어느 메시지가 나오는지 본 것.
COND_NAME = {
    0x02: '7E:0F1D != 0',
    0x03: 'BRK 8B 의 $49 == 0(인자 04 는 7E:2190 & 40 이면 03 으로 바꿈)',
    0x05: 'はい/いいえ 창에서 はい',
    0x11: 'BRK 88 90 의 $46 bit7 이 꺼짐',
    0x13: 'BRK 88 3E 의 $46 bit7 이 꺼짐($42 = 인자)',
    0x14: '21:8000 이 C=0',
    0x16: '7E:2190+idx & mask(1B 와 같은 처리기)',
    0x1A: '7E:2190+idx != 값',
    0x1B: '7E:2190+idx & mask',
    0x1C: '7E:2190+idx | mask != 0',
    0x1E: '신부가 ビアンカ(7E:21B3 & 08)',
    0x1F: '신부가 ビアンカ(7E:21B3 & 08)',
    0x20: 'BRK 89 4C 45 의 $49 == 0',
}


def parse_branch(rom, a, depth, ops):
    """06:B214·B225. 06 으로 시작하면 3E·3F 까지 여러 명령, 아니면 명령 하나. (다음 주소, 3F 로 끝났는지)."""
    if rom.u8(a) == 0x06:
        a, end = parse_block(rom, a + 1, depth, ops, (0x3E, 0x3F))
        return a, end == 0x3F
    return parse_op(rom, a, depth, ops)


def parse_op(rom, a, depth, ops):
    """06:B065 의 명령 하나. (다음 주소, 3F 로 스크립트가 끝났는지)."""
    b = rom.u8(a)
    if b & 0x40:
        raw = bytes((b, rom.u8(a + 1)))
        ops.append((a, depth, 'msg', raw, message_number(*raw)))
        return a + 2, False
    if b == 0x07:
        # 07 <조건> <참 분기> [0B <거짓 분기>]. 06:B15B·B1E5.
        c = rom.u8(a + 1)
        n = 1 + COND_SIZE[c & 0x3F]
        raw = bytes(rom.u8(a + i) for i in range(n))
        name = COND_NAME.get(c & 0x3F, '')
        ops.append((a, depth, f'if{" not" if c & 0x80 else ""} cond{c & 0x3F:02X}' + (f' ({name})' if name else ''), raw, None))
        a, ended = parse_branch(rom, a + n, depth + 1, ops)
        if not ended and rom.u8(a) == 0x0B:
            ops.append((a, depth, 'else', b'\x0b', None))
            a, ended = parse_branch(rom, a + 1, depth + 1, ops)
        return a, ended
    if b in OP_SIZE:
        raw = bytes(rom.u8(a + i) for i in range(OP_SIZE[b]))
        ops.append((a, depth, OP_NAME[b], raw, None))
        return a + len(raw), False
    raise ValueError(f'{a:06X}: 모르는 명령 {b:02X}')


def parse_block(rom, a, depth, ops, stops):
    """06:B065·B11A. stops 의 바이트가 나올 때까지 명령을 읽고, 끝 바이트 다음 주소와 그 바이트를 돌려준다."""
    while True:
        b = rom.u8(a)
        if b in stops:
            ops.append((a, depth, {0x3E: 'end-block', 0x3F: 'end'}[b], bytes([b]), None))
            return a + 1, b
        a, ended = parse_op(rom, a, depth, ops)
        if ended:
            return a, 0x3F


def parse_script(rom, a):
    """스크립트 하나를 3F 까지 읽어 명령 목록과 끝 다음 주소를 돌려준다."""
    ops = []
    while True:
        a, end = parse_block(rom, a, 0, ops, (0x3E, 0x3F))
        if end == 0x3F:
            return ops, a


def talk(rom, t):
    """대화 번호 t 의 설명 줄들."""
    kind = talk_kind(t)
    if kind == 'message':
        m = t - FIRST_SPECIAL2 + MESSAGE_BASE
        return [f'talk {t:03X}: 메시지 {m:03X}', text(message(rom, m))]
    if kind == 'special':
        h = SCRIPT_BANK << 16 | rom.u16(SPECIALS + t * 2)
        return [f'talk {t:03X}: 06:DBD2 특수 기능 {t:02X} -> {h >> 16:02X}:{h & 0xFFFF:04X}']
    if kind == 'special2':
        m = t - FIRST_SPECIAL2 + MESSAGE_BASE
        return [f'talk {t:03X}: 06:B34F 묻기 {m:03X}, はい {m + 1:03X}, いいえ {m + 2:03X}',
                *(text(message(rom, n)) for n in (m, m + 1, m + 2))]
    a = script_address(rom, t - FIRST_SCRIPT)
    ops, _ = parse_script(rom, a)
    out = [f'talk {t:03X}: 스크립트 {t - FIRST_SCRIPT:03X} at {a:06X}']
    for addr, depth, name, raw, msg in ops:
        line = f'  {addr:06X} {raw.hex(" "):14} {"  " * depth}{name}'
        if msg is not None:
            line += f' {msg:03X} ' + text(message(rom, msg)).replace('\n', ' ')
        out.append(line)
    return out


def check(rom):
    """모든 스크립트를 06:B065 길이로 읽은 끝이 06:AFA9 건너뛰기로 찾은 다음 스크립트 시작과 같은지."""
    bad = 0
    total = FIRST_SPECIAL2 - FIRST_SCRIPT
    for n in range(total):
        try:
            _, end = parse_script(rom, script_address(rom, n))
        except (ValueError, KeyError) as e:
            bad += 1
            print(f'script {n:03X}: {e!r}')
            continue
        if (n + 1) & 0x1F and n + 1 < total and end != script_address(rom, n + 1):
            bad += 1
            print(f'script {n:03X}: 끝 {end:06X} != 다음 시작 {script_address(rom, n + 1):06X}')
    print(f'scripts {total}, mismatch {bad}')
    return bad


def native_calls(rom):
    """스크립트의 00 명령(06:B129)이 부르는 뱅크 06 주소별 횟수."""
    out = {}
    for n in range(FIRST_SPECIAL2 - FIRST_SCRIPT):
        ops, _ = parse_script(rom, script_address(rom, n))
        for _, _, _, raw, _ in ops:
            if raw[0] == 0x00:
                a = SCRIPT_BANK << 16 | raw[1] | raw[2] << 8
                out[a] = out.get(a, 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('args', nargs='*', type=lambda s: int(s, 16))
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--night', action='store_true')
    ap.add_argument('--calls', action='store_true')
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    if a.check:
        return 1 if check(rom) else 0
    if a.calls:
        calls = native_calls(rom)
        for addr in sorted(calls):
            print(f'{addr >> 16:02X}:{addr & 0xFFFF:04X} {calls[addr]}')
        print(f'targets {len(calls)}, calls {sum(calls.values())}')
        return 0
    if len(a.args) == 1:
        print('\n'.join(talk(rom, a.args[0])))
        return 0
    bc, bd = a.args
    for addr, _ in dq5npc.map_entries(rom, bc, bd):
        f = dq5npc.parse(rom, addr, a.night)
        if f is None:
            continue
        print(f'({f["x"] & 0x7F},{f["y"] & 0x7F}) gfx={f["gfx"]:02X}')
        print('\n'.join('  ' + s for s in talk(rom, f['talk'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
