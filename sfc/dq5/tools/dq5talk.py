"""DQ5(SFC) 인물 대화 번호 → 대화 스크립트 → 메시지. 형식은 sfc/dq5/docs/dq5-text-format.md 의 「대화」.

말을 걸면 06:AF62 가 인물 표의 대화 번호(7E:36E0 하위, 7E:3700 상위)를 읽어 갈래를 고른다(06:AFF4).
  T < 011          06:DBD2 특수 기능. 06:DBDB 점프 표의 T 번째 처리기(000 은 메시지 1CC, 001~010 은 가게·여관·교회 등)
  011 <= T < 24F   대화 스크립트 T-011. 06:AEF8 표의 32개 묶음 포인터에서 3F 로 끝나는 스크립트를 건너뛰어 찾는다
  24F <= T < 26D   06:B34F. 메시지 T + 3C6 을 띄우고 はい/いいえ 창, はい 면 메시지 +1, いいえ 면 +2
  26D <= T         메시지 T + 3C6(06:AFFB, T - 24F + 615)
스크립트 명령은 06:B065 가 실행한다.

사용:
  python sfc/dq5/tools/dq5talk.py rom/dq5.sfc 012         # 대화 번호 012 의 스크립트와 메시지
  python sfc/dq5/tools/dq5talk.py rom/dq5.sfc 17 00       # 맵 17/00 인물(낮)의 대화
  python sfc/dq5/tools/dq5talk.py rom/dq5.sfc --check     # 스크립트 경계 검사
  python sfc/dq5/tools/dq5talk.py rom/dq5.sfc --calls     # 스크립트의 네이티브 호출 대상과 횟수
  python sfc/dq5/tools/dq5talk.py rom/dq5.sfc --field 3E 90 DB 45   # BRK 80~93 이 읽는 필드의 묶음·오프셋·후처리
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
# 「실측」 은 선실 파파스의 스크립트를 07 <조건> 61 6B 0B 61 29 3F 로 덮어 어느 메시지가 나오는지 본 것이고,
# 03·11·13·20 은 일행 레코드 둘째(7E:206A)와 일행 순서(7E:2020~, 수 7E:201D·201E)를 SET 으로 만들어 갈랐다.
COND_NAME = {
    0x02: '7E:0F1D != 0',
    0x03: '인물 번호 인자가 마차 밖 일행에 살아 있음(BRK 8B 48 DB). 인자 04 는 7E:2190 & 40 이면 03 으로 바꿈',
    0x05: 'はい/いいえ 창에서 はい',
    0x11: '일행 누군가가 물건 인자를 가짐(BRK 88 90)',
    0x13: '일행 레코드 인자 번째의 +1 bit7(살아 있음)이 켜짐(BRK 88 3E)',
    0x14: '낮: 시간대 7E:075E < F0(21:8000)',
    0x16: '7E:2190+idx & mask(1B 와 같은 처리기)',
    0x1A: '7E:2190+idx != 값',
    0x1B: '7E:2190+idx & mask',
    0x1C: '7E:2190+idx | mask != 0',
    0x1E: '신부가 ビアンカ(7E:21B3 & 08)',
    0x1F: '신부가 ビアンカ(7E:21B3 & 08)',
    0x20: '마차 밖 일행에 살아 있는 인물 번호 02 가 없음(BRK 89 4C 45)',
}
# 일행 레코드 +0 의 인물 번호와 이름(1008 로 띄워 본 것). 01·02 의 이름은 7E:2009·7E:2011, 80~ 은 동료 몬스터.
PARTY_IDS = {0x00: '주인공', 0x01: '아들', 0x02: '딸', 0x03: 'ビアンカ', 0x04: 'ビアンカ', 0x05: 'サンチョ',
             0x06: 'ピピン', 0x07: 'フローラ', 0x08: 'パパス', 0x09: 'ヘンリー', 0x0A: 'ベラ',
             0x0B: 'パパスのむすこ', 0x0C: 'やどやのむすめ', 0x80: 'ボロンゴ(1013)', 0x81: 'ボロンゴ',
             0x82: 'スラリン', 0x83: 'ドラきち'}
# 21:8AF8 필드 읽기. BRK 80~93 이 부른다(00:9197). 필드 f → 21:8D96[f] = 설명자 d → 21:8C86 + d*2.
FIELD_DESC = 0x218D96
FIELD_KIND = 0x218C86
FIELD_GROUPS = 0x218D6A
FIELD_SIZES = 0x218D8B
FIELD_POST = 0x218E8C


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


def field_info(rom, f):
    """21:8B31·8B82. 필드 f 의 (묶음, 묶음 기준 주소, 레코드 크기, 레코드 안 오프셋, 길이, 간접, 후처리 주소)."""
    d = rom.u8(FIELD_DESC + f)
    b0, b1 = rom.u8(FIELD_KIND + d * 2), rom.u8(FIELD_KIND + d * 2 + 1)
    k = (b0 >> 3) & 0xF
    return (k, rom.u24(FIELD_GROUPS + k * 3), rom.u8(FIELD_SIZES + k), b1, b0 & 7, b0 >> 7,
            0x210000 | rom.u16(FIELD_POST + f * 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('args', nargs='*', type=lambda s: int(s, 16))
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--night', action='store_true')
    ap.add_argument('--calls', action='store_true')
    ap.add_argument('--field', action='store_true', help='인자를 필드 번호로 보고 21:8AF8 설명자를 찍음')
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    if a.field:
        for f in a.args:
            k, base, size, off, n, ind, post = field_info(rom, f)
            print(f'field {f:02X}: 묶음 {k} ({base:06X}, {size}바이트) +{off} 길이 {n}{" 간접" if ind else ""} '
                  f'후처리 {post >> 16:02X}:{post & 0xFFFF:04X}')
        return 0
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
