"""DQ5(SFC) 실내 맵 인물 목록. 형식은 sfc/dq5/docs/dq5-map-format.md 의 「인물」.

12:803F(맵 목록 찾기)·12:8093(엔트리 크기)·12:8161/8227(낮·밤 엔트리 해석)과
이벤트 플래그(7E:2190-)에 따른 덮어쓰기 표 둘(12:82FB 의 12:8449, 12:8357 의 12:839C),
엔트리 값을 인물 표에 넣는 1E:DB44, 인라인 스크립트 해석기 01:C800(명령 표 01:C827)을 옮겼다.

사용:
  python sfc/dq5/tools/dq5npc.py rom/dq5.sfc BC BD [--night] [--flags 21AD=10,...] [--compare wram.bin]
  python sfc/dq5/tools/dq5npc.py rom/dq5.sfc --list 108BBD      # 맵 대신 목록 주소(숨은 목록 등)
  python sfc/dq5/tools/dq5npc.py rom/dq5.sfc --check-scripts    # 모든 목록의 스크립트 길이 검사
--flags 는 7E:xxxx 이벤트 플래그 바이트 값. 주지 않으면 모두 0 으로 보고, 걸린 덮어쓰기 항목을 함께 보여 준다.
--compare 는 인물을 다 놓은 뒤(12:803C)의 WRAM 128KB 에서 인물 표(7E:3000-, 슬롯 08~) 22칸을 비교한다.
--flags 를 주지 않으면 덤프의 이벤트 플래그와 시간대로 목록을 고른다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

NPC_BANK = 0x05
NPC_GROUPS = 0x05D4B2
FIELDS = ('talk', 'misc', 'x', 'y', 'gfx', 'move')
# 두 벌짜리(C0) 엔트리에서 각 필드가 한 값뿐임을 나타내는 마스크 비트(12:81C6~8206 순서).
SHARED_BITS = (0x40, 0x04, 0x20, 0x10, 0x08, 0x02)


def entry_size(rom, a):
    """12:8093. 엔트리 길이(바이트)."""
    b0 = rom.u8(a)
    if b0 & 0xC0 != 0xC0:
        size = 7 if b0 & 0x10 else 8
        if b0 & 0x20:
            size += rom.u8(a + size) + 1
        return size
    mask = rom.u8(a + 1)
    x = 1
    if mask & 0x80:
        b3 = b0
    else:
        x += 1
        b3 = rom.u8(a + x)
    x += 2
    # 필드마다 「값이 둘이면 +1, 다음 필드 +1」. 마지막(이동)은 「둘이면 +1」만.
    for bit in (0x40, 0x04, 0x20, 0x10, 0x08):
        if not mask & bit:
            x += 1
        x += 1
    if not mask & 0x02:
        x += 1
    if not b0 & 0x10:
        x += 1
    if not b3 & 0x10:
        x += 1
    if b0 & 0x20:
        n = rom.u8(a + x)
        x += n + 1 if n else 2
    if b3 & 0x20 and not mask & 0x01:
        # 12:8143: 두 번째 스크립트.
        x += rom.u8(a + x) + 1
    return x


def parse(rom, a, night=False):
    """12:8161(낮)·12:8227(밤). 그 시간대에 놓이는 엔트리면 필드 dict, 아니면 None.

    첫 바이트 bit7-6: 80 낮만, 40 밤만, C0 둘 다(필드마다 값이 하나 또는 낮·밤 두 개), 00 놓지 않음.
    """
    b0 = rom.u8(a)
    kind = b0 & 0xC0
    if kind != 0xC0:
        if kind != (0x40 if night else 0x80):
            return None
        f = dict(zip(FIELDS, (rom.u8(a + i) for i in range(1, 7))))
        f['extra'] = 0xFF if b0 & 0x10 else rom.u8(a + 7)
        flags = b0
    else:
        mask = rom.u8(a + 1)
        b3 = b0 if mask & 0x80 else rom.u8(a + 2)
        y = 1 if mask & 0x80 else 2
        f = {}
        for name, bit in zip(FIELDS, SHARED_BITS):
            two = not mask & bit
            y += 1
            if night and two:
                y += 1
            f[name] = rom.u8(a + y)
            if not night and two:
                y += 1
        if night:
            if not b0 & 0x10:
                y += 1
            f['extra'] = 0xFF if b3 & 0x10 else rom.u8(a + y + 1)
            flags = b3
        else:
            f['extra'] = 0xFF if b0 & 0x10 else rom.u8(a + y + 1)
            flags = b0
    f['flags'] = flags
    f['talk'] |= (flags & 0x0F) << 8
    f['script'] = script_address(rom, a, night)
    return f


def _c0_head(rom, a):
    """두 벌 엔트리의 (b3, 마스크, 추가 값 다음 오프셋). entry_size 와 같은 셈."""
    b0, mask = rom.u8(a), rom.u8(a + 1)
    x = 1
    if mask & 0x80:
        b3 = b0
    else:
        x += 1
        b3 = rom.u8(a + x)
    x += 2
    for bit in (0x40, 0x04, 0x20, 0x10, 0x08):
        if not mask & bit:
            x += 1
        x += 1
    if not mask & 0x02:
        x += 1
    if not b0 & 0x10:
        x += 1
    if not b3 & 0x10:
        x += 1
    return b3, mask, x


def script_address(rom, a, night=False):
    """그 시간대 인라인 스크립트의 길이 바이트 주소, 없으면 None. 1E:DC0B 가 그 다음 주소를 7E:3480/34A0/34C0 에 둔다.

    두 벌 엔트리는 낮 스크립트(b0 bit5) 다음에 밤 스크립트(b3 bit5)가 온다. 마스크 bit0 이면 밤도 낮 자리를 쓴다(12:82BD).
    """
    b0 = rom.u8(a)
    if b0 & 0xC0 != 0xC0:
        return a + (7 if b0 & 0x10 else 8) if b0 & 0x20 else None
    b3, mask, x = _c0_head(rom, a)
    if not night:
        return a + x if b0 & 0x20 else None
    if not b3 & 0x20:
        return None
    if b0 & 0x20 and not mask & 0x01:
        x += rom.u8(a + x) + 1
    return a + x


# 1E:DB44 가 엔트리 값을 인물 표로 옮길 때 쓰는 표.
FACING = {0x88: '위', 0x11: '오른쪽', 0x44: '아래', 0x22: '왼쪽'}
FACING_BY_XY = (0x88, 0x11, 0x44, 0x22)     # 1E:DD9C. 색인 = X bit7 << 1 | Y bit7
LAYER_MASK = (0x01, 0x02, 0x04)             # 1E:DD98. 이동 bit0-1 = 3 이면 01 에 7E:33A0 bit7
SPEED = (0x00, 0x01, 0x02, 0x04)            # 1E:DD94. 이동 bit6-7
STEP = (0x01, 0x02, 0x04, 0x08, 0x10, 0x18, 0x20, 0x28)  # 1E:DDA0. 기타 bit0-2


def decode(f):
    """엔트리 값을 1E:DB44 가 인물 표에 넣는 값으로 푼다(인물 표 주소는 7E:xxxx + 슬롯)."""
    move, misc, extra = f['move'], f['misc'], f['extra']
    return {
        'x': f['x'] & 0x7F,
        'y': (f['y'] & 0x7F) - (misc >> 7),
        'facing': FACING_BY_XY[(f['x'] >> 7) << 1 | f['y'] >> 7],
        'layer': LAYER_MASK[move & 3] if move & 3 != 3 else 0x01,
        'interval': move >> 2 & 0x0F,
        'speed': SPEED[move >> 6],
        'step': STEP[misc & 7],
        'walk_anim': extra >> 4,
        'stand_anim': extra & 0x0F,
        'hidden': f['gfx'] == 0,
    }


# 01:C827 의 명령 표(00~58). (길이, 이름). 이름은 처리 루틴을 읽고 붙인 것이다.
# 길이는 처리 루틴이 $AE 를 늘리는 양이다(01:C8D9 는 1, 01:C8EA 는 A 만큼, 01:C937 은 명령 첫 바이트 기준 상대 점프).
# 「그 자리」는 $AE 를 늘리지 않고 끝나는 명령으로, 다음 차례에 같은 명령을 다시 실행한다(사실상 끝).
SCRIPT_OPS = {
    0x00: (1, '그 자리'),
    0x01: (1, '반복 끝'),
    0x02: (2, '반복 n'),
    0x03: (2, '상대 점프'),
    0x04: (3, '절대 점프'),
    0x05: (4, '네이티브가 0 을 돌려줄 때까지 대기'),
    0x06: (4, '플래그면 상대 점프'),
    0x07: (6, '주인공 자리로 상대 점프'),
    0x08: (5, '주인공 자리 대기 후 이벤트 시작'),
    0x09: (3, '플래그 대기'),
    0x0A: (1, '저장한 곳으로 복귀'),
    0x0B: (1, '19AE bit7'),
    0x0C: (1, '19AE bit7'),
    0x0D: (1, '그림 프레임 0'),
    0x0E: (1, '그림 프레임 0(걷기)'),
    0x0F: (1, '그림 프레임 0(종류별)'),
    0x10: (3, '플래그 켜기'),
    0x11: (3, '플래그 AND'),
    0x12: (1, '00:DF37'),
    0x13: (3, '걸어가기 X Y'),
    0x14: (1, '도착 대기'),
    0x15: (1, '걷기 멈춤'),
    0x16: (1, '멈춤(이동 간격 0)'),
    0x17: (1, '아무 방향 보기'),
    0x18: (1, '아무 방향으로 걷기(계속)'),
    0x19: (3, '범위 안 돌아다니기 W H(계속)'),
    0x1A: (1, '애니메이션 끄기'),
    0x1B: (1, '애니메이션 끄기(그 자리)'),
    0x1C: (1, '33A0 bit0 켜기'),
    0x1D: (2, '이동 간격'),
    0x1E: (2, '속도'),
    0x1F: (1, '31C0 bit1 켜기'),
    0x20: (3, '24:FEAC'),
    0x21: (3, '메시지(창 열고 닫음)'),
    0x22: (1, '33A0 bit0 끄기'),
    0x23: (2, '그림 프레임'),
    0x24: (2, '그림 프레임(걷기)'),
    0x25: (1, '그 자리'),
    0x26: (1, '그 자리'),
    0x27: (1, '3380 bit7 켜기'),
    0x28: (1, '숨기기'),
    0x29: (1, '03:AE3F'),
    0x2A: (1, '숨기기(03:AE3F)'),
    0x2B: (3, '순간이동 X Y'),
    0x2C: (1, '목표 자리로 순간이동'),
    0x2D: (1, '목표 자리로 순간이동'),
    0x2E: (2, '그림 프레임(종류별)'),
    0x2F: (2, '방향'),
    0x30: (3, '메시지(창 열기)'),
    0x31: (3, '메시지(이어서)'),
    0x32: (3, '메시지(창 닫음)'),
    0x33: (1, 'BRK 95'),
    0x34: (1, 'BRK 0E/95'),
    0x35: (2, '걷기 애니메이션 간격'),
    0x36: (2, '서기 애니메이션 간격'),
    0x37: (4, '네이티브 호출'),
    0x38: (1, '3180 = 0'),
    0x39: (2, '3180 = n'),
    0x3A: (2, '3180 = -n'),
    0x3B: (1, '33A0 = 80'),
    0x3C: (1, '33A0 = B0'),
    0x3D: (1, '33A0 = A0'),
    0x3E: (1, '그 자리'),
    0x3F: (1, '00:CF34'),
    0x40: (1, '00:CF38'),
    0x41: (4, '01:D915'),
    0x42: (1, '그 자리'),
    0x43: (4, '01:F117'),
    0x44: (1, '33A0 bit3 켜기'),
    0x45: (1, '33A0 bit3 끄기'),
    0x46: (1, '33A0 = 04'),
    0x47: (1, '33A0 = 06'),
    0x48: (1, '그 자리'), 0x49: (1, '그 자리'), 0x4A: (1, '그 자리'), 0x4B: (1, '그 자리'),
    0x4C: (1, '그 자리'), 0x4D: (1, '그 자리'), 0x4E: (1, '그 자리'),
    0x4F: (1, '3540 대기'),
    0x50: (3, '목표 자리 X Y'),
    0x51: (1, '3540 감소'),
    0x52: (1, '3540 감소(숨기기)'),
    0x53: (1, '3540 증가'),
    0x54: (1, '그 자리'),
    0x55: (3, '플래그 바이트 쓰기'),
    0x56: (1, '그 자리'),
}
# bit7 이 켜진 바이트는 01:C800 이 명령 57/58 로 보낸다: [X|80] [Y] 로 걸어가 도착할 때까지(2바이트).
SCRIPT_WALK = (2, '걸어가 도착 대기 X Y')
SCRIPT_STOPS = {k for k, (_, name) in SCRIPT_OPS.items() if name == '그 자리'} | {0x03, 0x04, 0x0A, 0x16, 0x18, 0x19, 0x1B}


def script_ops(code):
    """인라인 스크립트 바이트를 [(오프셋, 바이트, 이름)] 으로. 모르는 명령이면 ValueError."""
    out, i = [], 0
    while i < len(code):
        op = code[i]
        n, name = SCRIPT_WALK if op & 0x80 else SCRIPT_OPS.get(op, (None, None))
        if n is None:
            raise ValueError(f'+{i}: 모르는 명령 {op:02X}')
        out.append((i, code[i:i + n], name))
        i += n
    if i != len(code):
        raise ValueError(f'명령이 길이 {len(code)} 를 넘음({i})')
    return out


def script_bytes(rom, a):
    return bytes(rom.u8(a + 1 + i) for i in range(rom.u8(a)))


def s8(v):
    return v - 0x100 if v & 0x80 else v


def format_op(off, raw, name):
    op = raw[0]
    args = raw[1:]
    if op & 0x80:
        detail = f'({op & 0x7F},{args[0]})'
    elif op in (0x13, 0x2B, 0x50):
        detail = f'({args[0]},{args[1]})'
    elif op in (0x06, 0x09, 0x10, 0x11, 0x55):
        detail = f'7E:{0x2190 + (args[0] & 0x7F):04X} & {args[1]:02X}'
        # 09 는 bit7 이면 켜질 때까지, 아니면 꺼질 때까지 기다린다(01:CA5B). 06 은 거꾸로 bit7 이 0 일 때 켜져 있으면 뛴다(01:C998).
        if op == 0x09:
            detail += ' 켜짐' if args[0] & 0x80 else ' 꺼짐'
        if op == 0x06:
            detail += ' 꺼짐' if args[0] & 0x80 else ' 켜짐'
        if op == 0x06:
            detail += f' → +{off + s8(args[2]):02X}'
    elif op in (0x07, 0x08):
        # 07 은 x0 bit7 이 0 이면 사각형 안일 때 뛰고(01:C9BC), 08 은 bit7 이 0 이면 밖이 될 때까지 기다린다(01:C9FB).
        detail = f'({args[0] & 0x7F},{args[1]})-({args[2]},{args[3]})'
        if op == 0x08:
            detail += ' 안이 될 때까지' if args[0] & 0x80 else ' 밖이 될 때까지'
        if op == 0x07:
            detail += ' 밖이면' if args[0] & 0x80 else ' 안이면'
            detail += f' → +{off + s8(args[4]):02X}'
    elif op == 0x03:
        detail = f'→ +{off + 1 + s8(args[0]):02X}'
    elif op in (0x05, 0x37):
        detail = f'{args[2]:02X}:{args[1]:02X}{args[0]:02X}'
    elif op == 0x20:
        detail = f'{args[1]:02X}{args[0]:02X}'
    elif op in (0x21, 0x30, 0x31, 0x32):
        detail = f'{args[1]:02X}{args[0]:02X}'  # 메시지 번호(dq5text.py). 01:CEA9 가 24:8157 로 띄운다
    else:
        detail = ' '.join(f'{b:02X}' for b in args)
    return f'+{off:02X} {raw.hex(" "):12} {name} {detail}'.rstrip()


def all_lists(rom):
    """기본 목록(05:8651~D4B1, 맵 346개)과 대체 목록(10:8000~DDB1, 293개)의 시작 주소. [(주소, 이름)]."""
    out = []
    for bc in range(0x36):
        a = NPC_BANK << 16 | rom.u16(NPC_GROUPS + bc * 2)
        end = NPC_BANK << 16 | (rom.u16(NPC_GROUPS + bc * 2 + 2) if bc < 0x35 else NPC_GROUPS & 0xFFFF)
        bd = 0
        while a < end:
            out.append((a, f'{bc:02X}/{bd:02X}'))
            while rom.u8(a):
                a += entry_size(rom, a)
            a += 1
            bd += 1
    pointed = {}
    t = OVERRIDE_LISTS
    while rom.u8(t) != 0xFF:
        pointed.setdefault(0x100000 | rom.u16(t + 4), f'{rom.u8(t):02X}/{rom.u8(t + 1):02X} 대체')
        t += 6
    a = ALT_START
    while a < ALT_END:
        out.append((a, pointed.get(a, '숨은 목록')))
        while rom.u8(a):
            a += entry_size(rom, a)
        a += 1
    return out


def check_scripts(rom):
    """모든 목록의 인라인 스크립트를 명령 길이로 읽은 끝이 길이 바이트와 맞는지."""
    total = bad = 0
    for la, name in all_lists(rom):
        for a, _ in list_entries(rom, la):
            for night in (False, True):
                s = script_address(rom, a, night)
                if s is None or (night and s == script_address(rom, a, False)):
                    continue
                total += 1
                try:
                    script_ops(script_bytes(rom, s))
                except ValueError as e:
                    bad += 1
                    print(f'{name} {a:06X} script {s:06X}: {e}')
    print(f'scripts {total}, mismatch {bad}')
    return bad


OVERRIDE_LISTS = 0x128449
NO_NPC = 0x12839C
FLAGS = 0x7E2190
ALT_START, ALT_END = 0x108000, 0x10DDB2


def flag_on(flags, num, mask):
    """플래그 번호 bit7 이 0 이면 그 비트가 켜졌을 때, 1 이면 꺼졌을 때 참."""
    on = bool(flags.get(FLAGS + (num & 0x7F), 0) & mask)
    return on != bool(num & 0x80)


def overrides(rom, bc, bd):
    """12:8449 에서 이 맵에 걸린 (플래그 번호, 마스크, 목록 주소) 를 표 순서대로."""
    out, a = [], OVERRIDE_LISTS
    while rom.u8(a) != 0xFF:
        if (rom.u8(a), rom.u8(a + 1)) == (bc, bd):
            out.append((rom.u8(a + 2), rom.u8(a + 3), 0x100000 | rom.u16(a + 4)))
        a += 6
    return out


def no_npc_rules(rom, bc, bd):
    """12:839C 에서 이 맵에 걸린 (플래그 번호, 마스크). 하나라도 참이면 인물을 놓지 않는다."""
    out, a = [], NO_NPC
    while rom.u8(a) != 0xFF:
        if (rom.u8(a), rom.u8(a + 1)) == (bc, bd):
            out.append((rom.u8(a + 2), rom.u8(a + 3)))
        a += 4
    return out


def list_address(rom, bc, bd, flags):
    """12:8009 순서: 덮어쓰기 표 → (실내면) 기본 목록. 인물을 놓지 않으면 None."""
    if any(flag_on(flags, n, m) for n, m in no_npc_rules(rom, bc, bd)):
        return None
    for n, m, a in overrides(rom, bc, bd):
        if flag_on(flags, n, m):
            return a
    return map_list(rom, bc, bd)


def map_list(rom, bc, bd):
    a = NPC_BANK << 16 | rom.u16(NPC_GROUPS + bc * 2)
    for _ in range(bd):
        while rom.u8(a):
            a += entry_size(rom, a)
        a += 1
    return a


def list_entries(rom, a):
    out = []
    while rom.u8(a):
        n = entry_size(rom, a)
        out.append((a, n))
        a += n
    return out


def map_entries(rom, bc, bd):
    """(주소, 크기) 목록. 12:803F: 그룹 포인터에서 맵마다 00 으로 끝나는 목록을 bd 개 건너뛴다."""
    a = NPC_BANK << 16 | rom.u16(NPC_GROUPS + bc * 2)
    for _ in range(bd):
        while rom.u8(a):
            a += entry_size(rom, a)
        a += 1
    out = []
    while rom.u8(a):
        n = entry_size(rom, a)
        out.append((a, n))
        a += n
    return out


# 다른 루틴이 같은 바이트의 나머지 비트를 쓰는 칸. 1E:DB44 가 넣는 비트만 비교한다.
COMPARE_MASK = {0x32A0: 0x30, 0x33A0: 0xF0}


def table_values(rom, placed):
    """놓이는 엔트리들(놓는 순서)의 인물 표 값. 1E:DB44 를 옮겼다. [{7E 주소(슬롯 0 기준): 값}]."""
    counters = [0] * 8          # 12:800E 가 지우는 $85~$8C. 이동 간격 8 이상인 인물끼리 걸음 차례를 엇갈리게 한다(1E:DD1E)
    out = []
    for a, f in placed:
        d = decode(f)
        v = d['interval']
        if v < 8:
            t3300 = v << 4
        else:
            k, low = (v - 2) >> 1, v & 1
            c = counters[k] & 0x0F if low else counters[k] >> 4
            t3300 = v << 4 | (c + 1)
            c = c + 1 if c < v else 0
            counters[k] = (counters[k] & 0xF0 | c) if low else (counters[k] & 0x0F | c << 4)
        t = {0x3020: d['x'], 0x3080: d['y'], 0x3220: f['gfx'], 0x31E0: d['facing'], 0x31A0: d['layer'],
             0x3300: t3300, 0x3360: d['speed'], 0x3320: d['step'], 0x32C0: f['extra'] & 0xF0,
             0x32E0: (f['extra'] & 0x0F) << 4, 0x36E0: f['talk'] & 0xFF, 0x3700: f['talk'] >> 8,
             0x31C0: f['misc'] >> 7, 0x30E0: d['x'], 0x3140: d['y'], 0x3240: d['facing'] & 0x0F,
             0x3260: d['facing'] & 0x0F, 0x3340: d['step'], 0x32A0: f['misc'] & 0x30,
             0x33A0: (0x80 if f['move'] & 3 == 3 else 0) | 0x30 | (f['misc'] & 0x40) << 1}
        s = f['script']
        t[0x3480] = (s + 1) & 0xFF if s is not None else 0
        t[0x34A0] = (s + 1) >> 8 & 0xFF if s is not None else 0
        out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', type=lambda s: int(s, 16), nargs='?')
    ap.add_argument('bd', type=lambda s: int(s, 16), nargs='?')
    ap.add_argument('--compare')
    ap.add_argument('--night', action='store_true', help='7E:075E >= $F0 일 때의 목록')
    ap.add_argument('--flags', default='')
    ap.add_argument('--list', type=lambda s: int(s, 16), help='맵 대신 이 주소의 목록(예: 숨은 목록 108BBD)')
    ap.add_argument('--check-scripts', action='store_true', help='모든 목록의 인라인 스크립트 길이 검사')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.check_scripts:
        return 1 if check_scripts(rom) else 0
    flags = {0x7E0000 | int(k, 16): int(v, 16) for k, v in (t.split('=') for t in args.flags.split(',') if t)}
    w = open(args.compare, 'rb').read() if args.compare else None
    if w is not None and not args.flags:
        # 덤프의 이벤트 플래그·시간대로 목록을 고른다.
        flags = {FLAGS + i: w[(FLAGS & 0xFFFF) + i] for i in range(0x170)}
        args.night = args.night or w[0x075E] >= 0xF0
    if args.list is not None:
        base = args.list
    else:
        for n, m in no_npc_rules(rom, args.bc, args.bd):
            print(f'no-NPC rule: flag {n & 0x7F:02X} mask {m:02X}{" (꺼졌을 때)" if n & 0x80 else ""}')
        for n, m, a in overrides(rom, args.bc, args.bd):
            print(f'override: flag {n & 0x7F:02X} mask {m:02X}{" (꺼졌을 때)" if n & 0x80 else ""} -> {a:06X}')
        base = list_address(rom, args.bc, args.bd, flags)
        if base is None:
            print('인물을 놓지 않음')
            return 0
    print(f'list at {base:06X}')
    placed = []
    for a, n in list_entries(rom, base):
        f = parse(rom, a, args.night)
        raw = ' '.join(f'{rom.u8(a + i):02X}' for i in range(n))
        print(f'{a:06X} [{raw}]')
        if not f:
            print(f'  ({"밤" if args.night else "낮"}에는 없음)')
            continue
        placed.append((a, f))
        d = decode(f)
        print(f'  ({d["x"]},{d["y"]}) gfx={f["gfx"]:02X}{"(숨김)" if d["hidden"] else ""} talk={f["talk"]:03X}'
              f' 방향={FACING[d["facing"]]} 층={d["layer"]:02X} 이동간격={d["interval"]} 속도={d["speed"]}'
              f' 걸음={d["step"]:02X} 애니={d["walk_anim"]:X}/{d["stand_anim"]:X} 기타bit4-6={f["misc"] >> 4 & 7}')
        if f['script'] is not None:
            print(f'  스크립트 {f["script"] + 1:06X}')
            try:
                for op in script_ops(script_bytes(rom, f['script'])):
                    print('    ' + format_op(*op))
            except ValueError as e:
                print(f'    {e}')
    if w is not None:
        bad = 0
        for slot, t in enumerate(table_values(rom, placed), 8):
            diff = [f'{k:04X} ours {v:02X} game {w[k + slot]:02X}' for k, v in t.items()
                    if w[k + slot] & COMPARE_MASK.get(k, 0xFF) != v]
            bad += bool(diff)
            print(f'  slot {slot:02X}: {len(t)} 칸 ' + ('OK' if not diff else 'DIFF ' + '; '.join(diff)))
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
