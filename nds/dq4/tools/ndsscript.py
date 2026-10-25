"""NDS DQ4 이벤트 스크립트(data/data/SCRIPT/<맵>.bin)를 읽는다. 형식은 nds/dq4/docs/script-format.md.

모든 층이 같은 블록 꼴이다: 이름 16바이트, u32 칸 수 N, u32 머리 크기(0x20 + 표 크기),
u32 표 크기(N×8 을 16 의 배수로 올림), u32 0, 그 뒤 칸마다 (오프셋, 크기) u32 쌍. 오프셋은 블록 시작 + 머리 크기 기준.
  script → scriptgroup → scriptobject(칸 4개: 0x30바이트 머리, initialize, execute, terminate)
함수 블록(initialize·execute·terminate)은 칸 3개: 명령마다 깊이 1바이트, 명령 시작 오프셋 u32 표(명령 수 + 1),
코드(u32 낱말). 명령은 u32(아래 16비트 명령 번호, 위 16비트 상태 비트) + 번호마다 정해진 수의 u32 인자.
깊이가 하나 큰 뒤따르는 명령들이 자식이고, 명령이 참을 돌려줄 때만 자식을 실행한다.
명령 번호는 arm9.bin 0x0201FDC0 의 `addls pc, pc, r2, lsl #2` 분기표(0x0201FDC8 부터 0x178칸)로 처리 함수에 간다.

사용:
  python nds/dq4/tools/ndsscript.py tree FILE.bin                  블록 나무와 오브젝트 머리(모습, 방향, 자리)
  python nds/dq4/tools/ndsscript.py dump FILE.bin [JPROOT]         명령 목록. 이름을 아는 명령은 이름과 인자 풀이(JPROOT 를 주면 대사)
  python nds/dq4/tools/ndsscript.py stats SCRIPTDIR [JPROOT]       전체 파일 검사와 명령 번호별 개수·인자 수
  python nds/dq4/tools/ndsscript.py ops ARM9.bin [SCRIPTDIR]       명령 번호 → 처리 주소, 쓰인 수, 인자 수, 이름
"""
import collections
import os
import pathlib
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndstext  # noqa: E402

FUNCS = ('initialize', 'execute', 'terminate')
ARM9 = 0x02000000
DISPATCH = 0x0201FDC8  # 명령 0 의 분기 칸. 앞 칸(0x0201FDC4)은 범위 밖 번호가 가는 기본 분기
NOPS = 0x178
FLAG_KINDS = {0: '이야기', 1: '깃발1', 2: '맵'}

# 이름과 인자 꼴. 꼴 글자: m 메시지, c 개수, n 맵 이름(두 낱말), x 4.12 고정소수, d 10진, h 16진, k 깃발(종류·번호·값).
# 근거(실측·코드·인자)는 script-format.md 의 명령 표에 있다.
OPS = {
    0x03: ('대사 이어서', 'mc'), 0x04: ('대사 목록', 'mmmmmmmm'),
    0x05: ('대사 이어서(마을)', 'mc'), 0x06: ('대사 목록(마을)', 'mmmmmmmm'),
    0x07: ('인물 켜기', 'd'), 0x08: ('조작 잠금', 'd'), 0x09: ('기다리기', 'd'),
    0x0C: ('화면 어둡게', 'd'), 0x0D: ('화면 어둡게(끝)', 'dd'), 0x0E: ('화면 밝게', 'd'), 0x0F: ('검은 화면', 'dd'),
    0x11: ('카지노', 'dd'), 0x13: ('돈 더하기', 'dd'), 0x15: ('대사(시간 뒤 닫힘)', 'md'),
    0x17: ('깃발 쓰기', 'k'), 0x18: ('깃발이면', 'k'), 0x19: ('시간대이면', 'd'),
    0x1F: ('맵 이동(자리)', 'nhhxxxdd'), 0x20: ('맵 이동(입구)', 'nhhhd'),
    0x21: ('카메라 이동', 'xxxdhxd'), 0x22: ('카메라 이동', 'xxxd'), 0x23: ('카메라 돌리기', 'dhd'),
    0x48: ('필드 기호 행선지', 'nhhhd'), 0x4A: ('말을 걸면', ''), 0x4E: ('이 인물 방향', 'd'), 0x51: ('감정 표시', 'h'),
    0x4F: ('기다리기2', 'd'), 0x62: ('효과음', 'd'), 0x63: ('효과음2', 'd'), 0x78: ('전투', 'dh'),
    0x79: ('주인공 자리', 'xxx'), 0x7E: ('주인공 옮기기', 'xxxdd'), 0x7F: ('주인공 걷기', 'xxxxd'),
    0x92: ('주인공 자리', 'xxxdd'), 0x93: ('주인공 자리·방향', 'xxxdx'),
    0x98: ('가게 열기', 'h'), 0xB3: ('장 제목', 'dd'), 0xBE: ('필드로', 'dddd'), 0xC8: ('필드 자리 옮기기', 'd'), 0xC9: ('세피아 화면', ''),
    0xED: ('감정 표시', 'h'), 0x102: ('이민자 수 구간이면', 'dd'), 0x10C: ('돈 0', ''), 0x10E: ('전투', 'dhdddd'),
    0x11A: ('목소리 지정', 'cddddddd'), 0x12D: ('이민 마을 메뉴', 'hhhh'),
    0x12E: ('엇갈림 통신', ''), 0x145: ('필드 자리', 'hhd'), 0x130: ('마을 이름 입력', ''), 0x133: ('메시지 입력', ''),
    0x153: ('모험의 서 화면', ''), 0x164: ('전투', 'dhd'),
}


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


def object_head(d, p):
    """scriptobject 첫 칸(0x30바이트): +04 인물 모습, +08 방향, +0C·+10·+14 x·y·z(4.12)."""
    model, facing, x, y, z = struct.unpack_from('<2I3i', d, p + 4)
    return model, facing, x / 4096, y / 4096, z / 4096


def branch(arm9, a):
    """ARM `b` 명령(주소 a)이 가는 곳."""
    off = struct.unpack_from('<I', arm9, a - ARM9)[0] & 0xFFFFFF
    return a + 8 + (off - (1 << 24) if off & 0x800000 else off) * 4


def handlers(arm9):
    """명령 번호마다 처리 주소. 기본 분기(범위 밖 번호)와 같은 곳이면 처리가 없는 번호다."""
    return [branch(arm9, DISPATCH + 4 * k) for k in range(NOPS)]


def word_name(v):
    s = v.to_bytes(4, 'little').rstrip(b'\0')
    return s.decode('ascii') if s and all(0x30 <= c < 0x7F for c in s) else None


def describe(w, msgs):
    """명령 한 줄을 사람이 읽을 꼴로."""
    op, flags, args = w[0] & 0xFFFF, w[0] >> 16, list(w[1:])
    name, form = OPS.get(op, (None, ''))
    head = f'{op:03X}' + (f'.{flags}' if flags else '')
    if not name:
        return f'{head} ' + ' '.join(f'{v:X}' for v in args)
    out, i = [], 0
    for ch in form:
        if i >= len(args):
            break
        v = args[i]
        if ch == 'k':
            out.append(f'{FLAG_KINDS.get(v, v)}[{args[i + 1]:X}]={args[i + 2]}')
            i += 3
            continue
        if ch == 'n':
            out.append(''.join(word_name(x) or '' for x in args[i:i + 2]) or f'{v:X}')
            i += 2
            continue
        if ch == 'm':
            if v:
                t = msgs.get(v)
                out.append(f'{v}' + (f'「{t[:24]}」'.replace('\n', '/') if t else ''))
        elif ch == 'x':
            out.append(f'{struct.unpack("<i", struct.pack("<I", v))[0] / 4096:g}')
        elif ch in 'dc':
            out.append(f'{v}')
        else:
            out.append(f'{v:X}')
        i += 1
    out += [f'{v:X}' for v in args[i:]]
    return f'{head} {name}: ' + ' '.join(out)


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    if argv[0] == 'tree':
        d = pathlib.Path(argv[1]).read_bytes()
        for depth, name, o, secs in blocks(d):
            extra = ''
            if name == 'scriptobject':
                model, facing, x, y, z = object_head(d, secs[0][0])
                extra = f'  모습 {model:#x} 방향 {facing} 자리 ({x:g}, {y:g}, {z:g})'
            print(f'{"  " * depth}{name} {o:#x} 칸 {len(secs)}{extra}')
    elif argv[0] == 'dump':
        d = pathlib.Path(argv[1]).read_bytes()
        msgs = ndstext.messages(argv[2]) if len(argv) > 2 else {}
        group = obj = -1
        func_at = {o: ins for _name, o, ins in functions(d)}
        for _depth, name, o, secs in blocks(d):
            if name == 'scriptgroup':
                group, obj = group + 1, -1
            elif name == 'scriptobject':
                obj += 1
                model, facing, x, y, z = object_head(d, secs[0][0])
                print(f'== 그룹 {group} 오브젝트 {obj}  모습 {model:#x} 방향 {facing} 자리 ({x:g}, {y:g}, {z:g})')
            elif name in FUNCS and func_at[o]:
                print(f'  {name}')
                for dep, w in func_at[o]:
                    print(f'    {"  " * dep}{describe(w, msgs)}')
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
                    if w[0] & 0xFFFF == 0x05:
                        calls += 1
                        found += w[1] in msgs
        print(f'파일 {len(files)}, 함수 {nfunc}, 명령 {sum(ops.values())}')
        if msgs:
            print(f'명령 0x05 {calls}, 그중 대사 파일에 있는 번호 {found}')
        for op, c in sorted(ops.items()):
            print(f'{op:04X}\t{c}\t인자 {",".join(map(str, sorted(sizes[op])))}')
    elif argv[0] == 'ops':
        arm9 = pathlib.Path(argv[1]).read_bytes()
        use, nargs = collections.Counter(), collections.defaultdict(set)
        if len(argv) > 2:
            for f in sorted(os.listdir(argv[2])):
                for _name, _o, ins in functions(pathlib.Path(argv[2], f).read_bytes()):
                    for _depth, w in ins:
                        use[w[0] & 0xFFFF] += 1
                        nargs[w[0] & 0xFFFF].add(len(w) - 1)
        default = branch(arm9, DISPATCH - 4)
        for op, a in enumerate(handlers(arm9)):
            name = '(처리 없음)' if a == default else OPS.get(op, ('', ''))[0]
            n = ','.join(map(str, sorted(nargs[op]))) or '-'
            print(f'{op:03X}\t{a:08X}\t{use[op]}\t{n}\t{name}')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
