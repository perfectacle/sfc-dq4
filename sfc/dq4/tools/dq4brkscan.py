"""뱅크 40 이상에 놓는 사건 코드가 부르는 BRK 스크립트 명령을 모은다(COMPAT-01).

BRK 핸들러(00:8F92)는 DB 를 BRK 를 부른 코드의 뱅크로 둔다. 핸들러가 DB 기준 절대 주소로 WRAM($0000~$1FFF)을
읽거나 쓰면, 뱅크 40~7D 에서는 WRAM 거울이 아니라 열린 버스·롬 거울에 닿는다(snes9x 에서 서장이 멈춘 원인).
그래서 높은 뱅크 코드는 열린 버스 프로브로 확인한 명령(ALLOWED)만 부른다.

진입점(PHP 로 시작하는 루틴과 장 상자의 입구)부터 흐름을 따라 역어셈블한다. M·X 폭은 REP·SEP·PHP/PLP 로
따라가고, 분기는 양쪽, JSR·JSL·JMP 는 같은 덩어리 안이면 따라간다. BRK 를 만나면 명령 번호를 적고 ALLOWED 의
피연산자 길이만큼 건너뛴다. 길이를 모르는 명령은 그 자리에서 문제로 적는다(새 명령은 확인 뒤 ALLOWED 에 더함).

  python sfc/dq4/tools/dq4brkscan.py      # 덩어리마다 찾은 BRK 명령과 문제
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from kr_patch.sfc.dis65816 import OPS, SIZE  # noqa: E402

# {BRK 명령: 피연산자 바이트 수}. 1장 걷기 검사(dq4ch1walkcheck) 전 구간에서 뱅크 5E 가 실제로 부르고(BRK 핸들러
# 00:8F80 입구 기록), 같은 걷기에 붙인 열린 버스 프로브가 뱅크 40~7D 아래 절반 접근을 보지 못한 명령만.
ALLOWED = {
    0x09: 1,    # n 프레임 기다리기
    0x88: 1,
    0x89: 2,
    0x8B: 2,
    0x8D: 2,
}
# 높은 뱅크에서 부르면 안 되는 명령과 까닭. ALLOWED 와 겹치지 않는다
FORBIDDEN = {
    0x16: '효과음을 넣고 24:FE44 로 기다림. FE44 가 대기열 $1D91·$1D93 을 DB 기준으로 읽음(dq4prologue._effect 로 대신)',
    0x95: '창 열기. 00:9085 가 창 번호를 STA $0A00(DB 기준)으로 씀(dq4ch1event 의 창 열기 네이티브로 대신)',
}
RETURNS = {0x60, 0x6B, 0x40}                    # RTS RTL RTI
JUMPS = {0x4C, 0x5C, 0x80, 0x82}                # JMP abs, JML long, BRA, BRL
CALLS = {0x20, 0x22}                            # JSR abs, JSL long
STOPS = {0x6C, 0x7C, 0xDC, 0xDB, 0xCB}          # 간접 점프·STP·WAI: 따라가지 않음
INDIRECT_CALL = 0xFC                            # JSR (abs,X): 대상은 모르고 다음 명령으로 이어 감
# native() 의 이름 가운데 자료(이벤트 스크립트·기록·빈 줄)인 것과, PHP 로 시작하지 않는 코드. 둘 다 아닌 이름이
# PHP 로 시작하지 않으면 문제로 친다(자료로 잘못 알고 건너뛰지 않게)
DATA_ENTRIES = {'blank2', 'end_event', 'talk_event', 'ev_back', 'ev_out', 'fly_event', 'record', 'event',
                'kick_walk', 'name', 'recruits'}
CODE_ENTRIES = {'hero_picture'}


def entries_of(name, base, blob, at):
    """(진입점 목록, 문제). PHP 로 시작하거나 CODE_ENTRIES 면 코드, DATA_ENTRIES 면 자료."""
    entries, problems = [], []
    for label, a in at.items():
        inside = 0 <= a - base < len(blob)
        if label in DATA_ENTRIES:
            continue
        if inside and (blob[a - base] == 0x08 or label in CODE_ENTRIES):
            entries.append(a)
        elif inside:
            problems.append(f'{name}.{label} {a:06X}: PHP 로 시작하지 않음(코드면 CODE_ENTRIES, 자료면 DATA_ENTRIES 에)')
    return entries, problems


def blobs():
    """[(이름, 시작 주소, 바이트, 진입점 목록)]. 롬 없이 만든다. 진입점을 못 가른 이름이 있으면 ValueError."""
    import dq4ch1event
    import dq4ch2event
    import dq4chapterbox as box
    import dq4prologue
    out = []
    for name, mod in (('prologue', dq4prologue), ('ch1event', dq4ch1event), ('ch2event', dq4ch2event)):
        blob, at = mod.native()
        entries, problems = entries_of(name, mod.CODE_AT, blob, at)
        if problems:
            raise ValueError('; '.join(problems))
        out.append((name, mod.CODE_AT, blob, entries))
    scenes = box.GAME_SCENES
    lay = box.Layout(box.CODE_AT, scenes, b'', [bytes(box.BOX_W * box.BOX_H * 2)] * len(scenes), box.palettes())
    out.append(('chapterbox', box.CODE_AT, lay.blob,
                [lay.start_at, lay.hook_at, *lay.box_at.values(), lay.reveal_at, lay.boot_at]))
    return out


def scan(base, blob, entries, others=()):
    """({BRK 명령: [주소]}, [문제], {덩어리 밖 대상}). others 는 따로 훑는 다른 덩어리의 (시작, 끝).
    뱅크 40 이상인데 어느 덩어리에도 없는 곳으로 나가면 훑지 못한 높은 뱅크 코드라 문제로 친다."""
    found, problems, seen, exits = {}, [], set(), set()
    work = [(e, True, True, ()) for e in entries]

    def inside(a):
        return base <= a < base + len(blob)

    def leave(a, how):
        exits.add(a)
        if a >> 16 >= 0x40 and not any(lo <= a < hi for lo, hi in others):
            problems.append(f'{how} {a:06X}: 훑지 않은 높은 뱅크 코드로 나감')

    while work:
        pc, m8, x8, pstack = work.pop()
        while inside(pc) and (pc, m8, x8) not in seen:
            seen.add((pc, m8, x8))
            op = blob[pc - base]
            if op == 0x00:
                if not inside(pc + 1):
                    problems.append(f'{pc:06X}: 덩어리 끝의 BRK')
                    break
                cmd = blob[pc - base + 1]
                found.setdefault(cmd, []).append(pc)
                if cmd in FORBIDDEN:
                    problems.append(f'{pc:06X}: BRK {cmd:02X} 금지 — {FORBIDDEN[cmd]}')
                    break
                if cmd not in ALLOWED:
                    problems.append(f'{pc:06X}: BRK {cmd:02X} 는 확인되지 않은 명령(열린 버스 프로브 뒤 ALLOWED 에 더함)')
                    break
                pc += 2 + ALLOWED[cmd]
                continue
            mn, md = OPS[op]
            n = (1 if m8 else 2) if md == 'immm' else (1 if x8 else 2) if md == 'immx' else SIZE[md]
            arg = int.from_bytes(blob[pc - base + 1:pc - base + 1 + n], 'little')
            nxt = pc + 1 + n
            if op == 0xC2:
                m8, x8 = m8 and not arg & 0x20, x8 and not arg & 0x10
            elif op == 0xE2:
                m8, x8 = m8 or bool(arg & 0x20), x8 or bool(arg & 0x10)
            elif op == 0x08:
                pstack = pstack + ((m8, x8),)
            elif op == 0x28 and pstack:
                (m8, x8), pstack = pstack[-1], pstack[:-1]
            if op in RETURNS or op in STOPS:
                break
            if op == INDIRECT_CALL:
                exits.add(f'JSR ({arg:04X},X) at {pc:06X}')
                pc = nxt
                continue
            if md == 'rel':
                target = (nxt + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF | (pc & 0xFF0000)
                if not inside(target):
                    leave(target, 'branch')
                elif op == 0x80:
                    pc = target
                    continue
                else:
                    work.append((target, m8, x8, pstack))
                if op == 0x80:
                    break
            elif op == 0x82:
                pc = (nxt + (arg - 65536 if arg & 0x8000 else arg)) & 0xFFFF | (pc & 0xFF0000)
                if not inside(pc):
                    leave(pc, 'BRL')
                    break
                continue
            elif op in (0x4C, 0x20):
                target = arg | (pc & 0xFF0000)
                if not inside(target):
                    leave(target, 'JMP' if op == 0x4C else 'JSR')
                    if op == 0x4C:
                        break
                elif op == 0x4C:
                    pc = target
                    continue
                else:
                    work.append((target, m8, x8, ()))
            elif op in (0x5C, 0x22):
                if not inside(arg):
                    leave(arg, 'JML' if op == 0x5C else 'JSL')
                    if op == 0x5C:
                        break
                elif op == 0x5C:
                    pc = arg
                    continue
                else:
                    work.append((arg, m8, x8, ()))
            pc = nxt
    return found, problems, exits


def main():
    bad = 0
    all_blobs = blobs()
    spans = [(b, b + len(blob)) for _, b, blob, _ in all_blobs]
    for name, base, blob, entries in all_blobs:
        found, problems, exits = scan(base, blob, entries, spans)
        cmds = ' '.join(f'{c:02X}×{len(v)}' for c, v in sorted(found.items(), key=lambda kv: kv[0] or 0))
        print(f'{name} {base:06X}+{len(blob)} 진입점 {len(entries)}: {cmds or "BRK 없음"}')
        outside = sorted(f'{e:06X}' if isinstance(e, int) else e for e in exits)
        print(f'  덩어리 밖: {" ".join(outside) or "없음"}')
        for p in problems:
            print(f'  문제: {p}')
        bad += len(problems)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
