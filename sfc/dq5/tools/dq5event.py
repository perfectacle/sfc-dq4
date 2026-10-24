"""DQ5(SFC) 이벤트(주인공을 조종하는 스크립트). 형식은 sfc/dq5/docs/dq5-event-format.md.

00:BEC3 이 $19B3~$19B5 가 가리키는 바이트를 한 명령씩 실행한다($19AE bit7 이 켜져 있는 동안 입력 대신).
시작 주소가 들어가는 길:
- 이벤트 표 23:E2C2([X][Y][스크립트 24비트] 10개, 23:E29A 가 A = 이벤트 번호로 고름. 02:B705 가 7E:1A0D 에
  (X, Y) 까지 걷는 명령과 C3 를 써 넣음)
- 스크립트 번호 표 23:E325(3바이트 포인터 83개, 23:E2F4 가 A = 번호로 고름)
- 코드 안의 LDA # / STA $19B3·$19B4·$19B5 묶음
- 스크립트 안의 C3(점프)

사용:
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc              # 이벤트 표 10개와 스크립트
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc 15F702       # 그 주소의 스크립트
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc --number 41  # 스크립트 번호 표 41 번
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc --starts     # 모든 시작 주소의 스크립트(번호 표·이벤트 표·코드·점프)
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc --list       # 시작 주소와 부르는 곳 한 줄씩
  python sfc/dq5/tools/dq5event.py rom/dq5.sfc --all        # 15:F150~F7CF 의 스크립트 전부(FF 로 나눔)
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5text import message, text  # noqa: E402

NUMBERED = 0x23E325        # 스크립트 번호 표, 3바이트씩
NUMBER_COUNT = 0x53        # 부르는 곳이 쓰는 가장 큰 번호가 52. 그 뒤는 코드
EMPTY = 0x23E41E           # 1A·1B·1C·3C 가 가리키는 곳. 스크립트가 아니라 코드라 빈 항목으로 본다
EVENTS = 0x23E2C2          # 이벤트 표, 5바이트씩
EVENT_COUNT = 10
# 15:F150~F7CF 에 스크립트가 FF 로 끝나며 이어져 있다(15:F7D0 부터는 맵별 루틴 코드).
SCRIPT_START, SCRIPT_END = 0x15F150, 0x15F7D0
CALL_EVENT = 0x23E2F4      # 스크립트 번호 표로 시작
CALL_WALK = 0x23E29A       # 이벤트 표로 시작
FLAG_BASE = 0x2190
DIRS = {0x01: '오른쪽', 0x02: '왼쪽', 0x04: '아래', 0x08: '위'}

# 명령: 길이, 이름. 길이는 처리기가 00:BFBB 로 넘기는 값. 00~0F 는 걷기(00:BEE3), FF 는 끝(00:BED4).
OPS = {
    0x10: (3, '플래그 켜기'),          # 00:BF9E  7E:2190+idx |= mask
    0x20: (3, '플래그 AND'),           # 00:BFD4  7E:2190+idx &= mask
    0x60: (3, '메시지'),               # 00:BF82  번호 16비트, 24:8157
    0x90: (7, '맵 이동'),              # 00:C00F  BC BD X Y 방향 $198E
    0x91: (1, '91'),                   # 00:C138  00:CC04, 00:D267
    0xA0: (4, '네이티브 호출'),        # 00:C046  JSL 주소
    0xB0: (3, '플래그 기다림'),        # 00:BFF1  켜질 때까지 다음 프레임에 다시
    0xC1: (2, '7E:31E0 쓰기'),         # 00:C104
    0xC2: (1, '한 프레임 쉬기'),       # 00:C11A
    0xC3: (4, '뛰기'),                 # 00:C122  주소 3바이트
    0xC4: (4, 'C4'),                   # 00:C092  7E:1E8C~1E8E, 01:D915
    0xC5: (4, 'C5'),                   # 00:C0D4  7E:1E8C~1E8E, 01:F117
    0xC6: (1, 'C6'),                   # 00:C15E  23:FE69
    0xC7: (2, 'C7'),                   # 00:C16E  23:FE77
    0xC8: (2, 'C8'),                   # 00:C182  23:FE80
    0xC9: (1, 'C9'),                   # 00:C18E  23:FE8F
}


def short_message(rom, n, width=40):
    s = text(message(rom, n)).replace('\n', ' ')
    return re.sub(r'\{[0-9A-F]{4}\}', '', s).strip()[:width]


def decode(rom, a, limit=600):
    """스크립트 하나를 FF·C3·모르는 명령까지. [(주소, 바이트, 설명)], 뛰는 곳 목록."""
    out, jumps = [], []
    for _ in range(limit):
        op = rom.u8(a)
        if op == 0xFF:
            out.append((a, b'\xff', '끝'))
            break
        if op < 0x10:
            raw = bytes((op, rom.u8(a + 1)))
            dirs = '+'.join(v for k, v in DIRS.items() if op & k) or '그대로'
            out.append((a, raw, f'걷기 {dirs} {raw[1]}칸'))
            a += 2
            continue
        if op not in OPS:
            out.append((a, bytes((op,)), f'모르는 명령 {op:02X}'))
            break
        n, name = OPS[op]
        raw = bytes(rom.u8(a + i) for i in range(n))
        desc = name
        if op in (0x10, 0x20, 0xB0):
            desc += f' 7E:{FLAG_BASE + raw[1]:04X} {raw[2]:02X}'
        elif op == 0x60:
            m = raw[1] | raw[2] << 8
            desc += f' {m:03X} 「{short_message(rom, m)}」'
        elif op == 0x90:
            desc += f' {raw[1]:02X}/{raw[2]:02X} ({raw[3]},{raw[4]}) 방향 {raw[5]}'
        elif op in (0xA0, 0xC3, 0xC4, 0xC5):
            t = raw[1] | raw[2] << 8 | raw[3] << 16
            desc += f' {t >> 16:02X}:{t & 0xFFFF:04X}'
            if op == 0xC3:
                jumps.append(t)
        elif n == 2:
            desc += f' {raw[1]:02X}'
        out.append((a, raw, desc))
        if op == 0xC3:
            break
        a += n
    return out, jumps


def numbered(rom):
    return [rom.u24(NUMBERED + k * 3) for k in range(NUMBER_COUNT)]


def events(rom):
    """이벤트 표 [(번호, X, Y, 스크립트 주소)]."""
    return [(k, rom.u8(EVENTS + k * 5), rom.u8(EVENTS + k * 5 + 1), rom.u24(EVENTS + k * 5 + 2))
            for k in range(EVENT_COUNT)]


def all_scripts(rom):
    """15:F150~F7CF 를 명령 길이로 읽어 FF 다음마다 나누는 스크립트 시작 주소."""
    a, starts = SCRIPT_START, [SCRIPT_START]
    while a < SCRIPT_END:
        op = rom.u8(a)
        a += 2 if op < 0x10 else (1 if op == 0xFF else OPS[op][0])
        if op == 0xFF and a < SCRIPT_END:
            starts.append(a)
    return starts


def callers(rom, target):
    """LDA #n / JSL target 을 찾는다. {n: [부르는 곳]}."""
    out = {}
    pat = re.compile(rb'\xa9(.)\x22' + bytes((target & 0xFF, target >> 8 & 0xFF, target >> 16)), re.S)
    for m in pat.finditer(rom.d):
        i = m.start()
        out.setdefault(m.group(1)[0], []).append(f'{i // 0x8000:02X}:{0x8000 + i % 0x8000:04X}')
    # TDC(A = 0) / JSL target
    for m in re.finditer(rb'\x7b\x22' + bytes((target & 0xFF, target >> 8 & 0xFF, target >> 16)), rom.d):
        i = m.start()
        out.setdefault(0, []).append(f'{i // 0x8000:02X}:{0x8000 + i % 0x8000:04X}')
    return out


def code_starts(rom):
    """LDA #lo / STA $19B3 / LDA #hi / STA $19B4 / LDA #bank / STA $19B5. [(부르는 곳, 주소)]."""
    out = []
    pat = re.compile(rb'\xa9(.)\x8d\xb3\x19\xa9(.)\x8d\xb4\x19\xa9(.)\x8d\xb5\x19', re.S)
    for m in pat.finditer(rom.d):
        i = m.start()
        a = m.group(3)[0] << 16 | m.group(2)[0] << 8 | m.group(1)[0]
        out.append((f'{i // 0x8000:02X}:{0x8000 + i % 0x8000:04X}', a))
    return out


def all_starts(rom):
    """(이름, 주소, 부르는 곳) 목록. 같은 주소는 한 번만."""
    starts, seen = [], set()
    walk_callers = callers(rom, CALL_WALK)
    for k, x, y, a in events(rom):
        starts.append((f'이벤트 {k} ({x},{y})', a, ', '.join(walk_callers.get(k, [])) or '부르는 곳 못 찾음'))
    ev_callers = callers(rom, CALL_EVENT)
    for k, a in enumerate(numbered(rom)):
        if a == EMPTY:
            continue
        starts.append((f'번호 {k:02X}', a, ', '.join(ev_callers.get(k, [])) or '부르는 곳 못 찾음'))
    for caller, a in code_starts(rom):
        if a >> 16 != 0x00:      # 7E:1A0D 버퍼(02:B705)는 뺀다
            starts.append((f'코드 {caller}', a, caller))
    out = []
    todo = list(starts)
    while todo:
        name, a, by = todo.pop(0)
        if a in seen:
            continue
        seen.add(a)
        out.append((name, a, by))
        _, jumps = decode(rom, a)
        todo += [(f'뛰는 곳 ({name})', j, name) for j in jumps]
    return out


def flag_refs(rom):
    """dq5flags.py 가 쓰는 (번호, 마스크, 종류, 설명, 메시지)."""
    out = []
    for name, a, _ in all_starts(rom):
        ops, _ = decode(rom, a)
        last = None
        for addr, raw, _ in ops:
            if raw[0] == 0x60:
                last = raw[1] | raw[2] << 8
            if raw[0] in (0x10, 0x20, 0xB0):
                kind = {0x10: 'set', 0x20: 'clear', 0xB0: 'test'}[raw[0]]
                mask = raw[2] ^ 0xFF if kind == 'clear' else raw[2]
                note = ' 기다림' if kind == 'test' else ''
                out.append((raw[1], mask, kind, f'이벤트 스크립트 {addr:06X} ({name}){note}', last))
    return out


def show(rom, name, a, by):
    print(f'{name}: {a >> 16:02X}:{a & 0xFFFF:04X}  부르는 곳 {by}')
    ops, _ = decode(rom, a)
    for addr, raw, desc in ops:
        print(f'  {addr:06X} {raw.hex(" "):20} {desc}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('addr', nargs='?', type=lambda v: int(v, 16))
    ap.add_argument('--number', type=lambda v: int(v, 16))
    ap.add_argument('--starts', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.addr is not None:
        starts = [(f'{args.addr:06X}', args.addr, '-')]
    elif args.all:
        starts = [(f'{a:06X}', a, '-') for a in all_scripts(rom)]
    elif args.number is not None:
        starts = [s for s in all_starts(rom) if s[0] == f'번호 {args.number:02X}']
    elif args.starts or args.list:
        starts = all_starts(rom)
    else:
        starts = [s for s in all_starts(rom) if s[0].startswith('이벤트 ')]
    if args.list:
        for name, a, by in starts:
            ops, _ = decode(rom, a)
            first = next((d for _, r, d in ops if r[0] == 0x60), '')
            print(f'{a:06X} {name:22} {len(ops):3}개  {by}  {first[:50]}')
        print(f'스크립트 {len(starts)}개')
        return 0
    for s in starts:
        show(rom, *s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
