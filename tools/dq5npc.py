"""DQ5(SFC) 실내 맵 인물 목록. 형식은 docs/dq5-map-format.md 의 「인물」.

12:803F(맵 목록 찾기)·12:8093(엔트리 크기)·12:8161/8227(낮·밤 엔트리 해석)과
이벤트 플래그(7E:2190-)에 따른 덮어쓰기 표 둘(12:82FB 의 12:8449, 12:8357 의 12:839C)을 옮겼다.

사용:
  python tools/dq5npc.py rom/dq5.sfc BC BD [--night] [--flags 21AD=10,...] [--compare wram.bin]
--flags 는 7E:xxxx 이벤트 플래그 바이트 값. 주지 않으면 모두 0 으로 보고, 걸린 덮어쓰기 항목을 함께 보여 준다.
--compare 는 인물을 다 놓은 뒤의 WRAM 128KB 에서 인물 표(7E:3000-, 슬롯 08~)와 X·Y·그림을 비교한다.
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
    return f


OVERRIDE_LISTS = 0x128449
NO_NPC = 0x12839C
FLAGS = 0x7E2190


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('bc', type=lambda s: int(s, 16))
    ap.add_argument('bd', type=lambda s: int(s, 16))
    ap.add_argument('--compare')
    ap.add_argument('--night', action='store_true', help='7E:075E >= $F0 일 때의 목록')
    ap.add_argument('--flags', default='')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    flags = {0x7E0000 | int(k, 16): int(v, 16) for k, v in (t.split('=') for t in args.flags.split(',') if t)}
    for n, m in no_npc_rules(rom, args.bc, args.bd):
        print(f'no-NPC rule: flag {n & 0x7F:02X} mask {m:02X}{" (꺼졌을 때)" if n & 0x80 else ""}')
    for n, m, a in overrides(rom, args.bc, args.bd):
        print(f'override: flag {n & 0x7F:02X} mask {m:02X}{" (꺼졌을 때)" if n & 0x80 else ""} -> {a:06X}')
    base = list_address(rom, args.bc, args.bd, flags)
    if base is None:
        print('인물을 놓지 않음')
        return 0
    print(f'list at {base:06X}')
    day = []
    for a, n in list_entries(rom, base):
        f = parse(rom, a, args.night)
        raw = ' '.join(f'{rom.u8(a + i):02X}' for i in range(n))
        if f:
            day.append(f)
            print(f'{a:06X} [{raw}]  x={f["x"] & 0x7F:2d} y={f["y"] & 0x7F:2d} gfx={f["gfx"]:02X} talk={f["talk"]:03X}')
        else:
            print(f'{a:06X} [{raw}]  ({"밤" if args.night else "낮"}에는 없음)')
    if args.compare:
        w = open(args.compare, 'rb').read()
        bad = 0
        for slot, f in enumerate(day, 8):
            game = (w[0x3020 + slot], w[0x3080 + slot], w[0x3220 + slot])
            # 12:8161 이 아닌 1E:DBD0 이 misc bit7 로 Y 를 1 줄인다.
            ours = (f['x'] & 0x7F, (f['y'] & 0x7F) - (1 if f['misc'] & 0x80 else 0), f['gfx'])
            ok = game == ours
            bad += not ok
            print(f'  slot {slot:02X}: ours {ours} game {game} {"OK" if ok else "DIFF"}')
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
