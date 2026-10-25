"""NDS DQ4 이벤트 스크립트(data/data/SCRIPT/<맵>.bin)를 읽는다. 형식은 nds/dq4/docs/text-format.md 「이벤트 스크립트」.

모든 층이 같은 블록 꼴이다: 이름 16바이트, u32 칸 수 N, u32 머리 크기(0x20 + 표 크기),
u32 표 크기(N×8 을 16 의 배수로 올림), u32 0, 그 뒤 칸마다 (오프셋, 크기) u32 쌍. 오프셋은 블록 시작 + 머리 크기 기준.
  script → scriptgroup → scriptobject(칸 4개: 0x30바이트 머리, initialize, execute, terminate)
함수 블록(initialize·execute·terminate)은 칸 3개: 명령마다 1바이트(들여쓰기 깊이로 보임),
명령 시작 오프셋 u32 표(명령 수 + 1), 코드(u32 낱말). 명령은 u32 명령 번호 + 번호마다 정해진 수의 u32 인자.
명령 0x05 의 첫 인자는 메시지 번호다(MPT0 머리 +08 기준, ndstext.messages).

사용:
  python nds/dq4/tools/ndsscript.py tree FILE.bin                  블록 나무
  python nds/dq4/tools/ndsscript.py dump FILE.bin [JPROOT]         명령 목록(JPROOT 를 주면 메시지 명령 옆에 문장)
  python nds/dq4/tools/ndsscript.py stats SCRIPTDIR [JPROOT]       전체 파일 검사와 명령 번호별 개수·인자 수
"""
import collections
import os
import pathlib
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndstext  # noqa: E402

FUNCS = ('initialize', 'execute', 'terminate')
MSG_OPS = (0x05,)


def blocks(d, o=0, depth=0, out=None):
    """[(깊이, 이름, 위치, [(데이터 위치, 크기)])] — 이름이 있는 하위 칸은 다시 블록으로 읽는다."""
    out = [] if out is None else out
    name = d[o:o + 16].split(b'\0')[0].decode('ascii')
    n, head, tsize, zero = struct.unpack_from('<4I', d, o + 16)
    if tsize != (n * 8 + 15) // 16 * 16 or head != 0x20 + tsize or zero:
        raise ValueError(f'{o:#x}: 블록 머리가 아님')
    secs = [(o + head + a, s) for a, s in (struct.unpack_from('<2I', d, o + 0x20 + 8 * i) for i in range(n))]
    out.append((depth, name, o, secs))
    if name in FUNCS:
        return out
    for p, s in secs:
        if s >= 0x20 and d[p:p + 6] in (b'script', b'initia', b'execut', b'termin'):
            blocks(d, p, depth + 1, out)
    return out


def functions(d):
    """[(이름, 위치, [(깊이 바이트, (명령 번호, 인자…))])]"""
    out = []
    for _depth, name, o, secs in blocks(d):
        if name not in FUNCS:
            continue
        (p0, s0), (p1, s1), (p2, _s2) = secs
        offs = struct.unpack_from(f'<{s1 // 4}I', d, p1)
        ins = []
        for k in range(s0):
            ins.append((d[p0 + k], struct.unpack_from(f'<{(offs[k + 1] - offs[k]) // 4}I', d, p2 + offs[k])))
        out.append((name, o, ins))
    return out


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    if argv[0] == 'tree':
        d = pathlib.Path(argv[1]).read_bytes()
        for depth, name, o, secs in blocks(d):
            print(f'{"  " * depth}{name} {o:#x} 칸 {len(secs)}')
    elif argv[0] == 'dump':
        d = pathlib.Path(argv[1]).read_bytes()
        msgs = ndstext.messages(argv[2]) if len(argv) > 2 else {}
        for name, o, ins in functions(d):
            print(f'{name} {o:#x}')
            for depth, w in ins:
                args = ' '.join(f'{v:X}' for v in w[1:])
                text = msgs.get(w[1], '') if w[0] & 0xFFFF in MSG_OPS and len(w) > 1 else ''
                print(f'  {"  " * depth}{w[0]:05X} {args}' + (f'  ; {text[:40]}'.replace('\n', '/') if text else ''))
    elif argv[0] == 'stats':
        msgs = ndstext.messages(argv[2]) if len(argv) > 2 else {}
        files = sorted(f for f in os.listdir(argv[1]) if f.endswith('.bin'))
        ops, sizes = collections.Counter(), collections.defaultdict(set)
        nfunc = found = calls = 0
        for f in files:
            for _name, _o, ins in functions(pathlib.Path(argv[1], f).read_bytes()):
                nfunc += 1
                for _depth, w in ins:
                    ops[w[0] & 0xFFFF] += 1
                    sizes[w[0] & 0xFFFF].add(len(w) - 1)
                    if w[0] & 0xFFFF in MSG_OPS:
                        calls += 1
                        found += w[1] in msgs
        print(f'파일 {len(files)}, 함수 {nfunc}, 명령 {sum(ops.values())}')
        if msgs:
            print(f'메시지 명령 {calls}, 그중 대사 파일에 있는 번호 {found}')
        for op, c in sorted(ops.items()):
            print(f'{op:04X}\t{c}\t인자 {",".join(map(str, sorted(sizes[op])))}')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
