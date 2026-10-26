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
  python nds/dq4/tools/ndsscript.py ops ARM9.bin [SCRIPTDIR]       명령 번호 → 처리 주소, 쓰인 수, 인자 수, 분류, 이름
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
    0x0A: ('주인공이 상자 안이면', 'xxxxxx'), 0x10: ('들어온 입구이면', 'h'), 0x12: ('도구 주기', 'hdd'),
    0x14: ('값 쓰기', 'dd'), 0x16: ('인물 표 비트이면', 'd'), 0x1B: ('상태 값', 'd'),
    0x1C: ('물체 애니메이션(기다림)', 'hd'), 0x1D: ('물체 애니메이션', 'hd'), 0x1E: ('물체 켜기·끄기', 'hd'),
    0x25: ('입구 설정', 'hd'), 0x28: ('시간대 정하기', 'd'), 0x2A: ('조사하면', 'h'), 0x2B: ('조사 자리', 'hxxx'),
    0x3E: ('조우 객체 값', 'd'), 0x3F: ('조우 켜기·끄기', 'd'), 0x41: ('전투 값 비교', 'dd'), 0x45: ('맵 깃발 무작위', 'hd'),
    0x49: ('도구를 가졌으면', 'h'), 0x4D: ('이 인물 자리', 'xxx'), 0x58: ('이 인물 보이기', 'd'), 0x5B: ('이 인물 배회 범위', 'xxxxxxx'),
    0x5D: ('이 인물 옮기기', 'xxxx'), 0x64: ('맵 인물을 일행으로', 'dd'), 0x66: ('일행에 넣기', 'd'), 0x67: ('일행에서 빼기', 'd'),
    0x68: ('물체 옮기기(프레임)', 'hxxxd'), 0x69: ('물체 옮기기(속도)', 'hxxxx'), 0x6A: ('일행 회복', 'd'),
    0x71: ('일행에 인물이 있으면', 'hhhddddd'), 0x72: ('일행에 인물이 없으면', 'hhhddddd'), 0x7A: ('주인공 방향', 'd'),
    0x80: ('인물 생사이면', 'dd'), 0x85: ('카메라를 이 인물로', 'd'), 0x86: ('곡 틀기', 'd'), 0x87: ('곡 멈추기', 'd'),
    0x96: ('기다리기3', 'd'), 0x99: ('예·아니오', 'dhd'), 0xA2: ('물체 자리', 'xxxh'), 0xA8: ('화면 색', 'dddd'),
    0xB1: ('이 인물 모습 바꾸기', 'h'), 0xC2: ('맵 비트', 'dd'), 0xD8: ('수 줄이기', ''), 0xD9: ('남은 수이면', 'd'),
    0xF2: ('조사 물건 상태이면', 'hd'), 0xFA: ('장 바꾸기', 'd'), 0x100: ('곡 자동 고르기 끄기', ''), 0x10F: ('일당 0', ''),
    0x110: ('일당 받기', ''), 0x111: ('일당 조건', 'dd'), 0x113: ('이 인물 동작', 'h'), 0x11B: ('대사 변수 X_WINS', 'd'),
    0x11C: ('상자 열기', 'h'), 0x11D: ('출입구 문', 'hhd'), 0x120: ('대사 변수 ACTOR', ''), 0x121: ('카메라를 다른 인물로', 'dd'),
    0x123: ('물체 옮기기', 'hxxxx'), 0x126: ('대사 상태이면', 'd'), 0x139: ('무작위 대사', 'cmmmmmmm'), 0x13A: ('ME', 'ddd'),
    0x13B: ('무작위 돈', ''), 0x146: ('곡 자동 고르기', ''), 0x147: ('곡 고정', 'd'), 0x14F: ('대사 변수 I_NAME', 'd'),
    0x160: ('대사 변수 TARGET', 'd'), 0x169: ('맵 비트', 'd'), 0x16A: ('탈것', 'd'), 0x16D: ('자리 저장', 'xxx'),
    0x175: ('자리 저장', 'xxx'),
}

# 처리 함수가 부르는 함수·읽고 쓰는 RAM 으로 나눈 분류. 근거와 이름 없는 번호의 처리 요약은 script-format.md 의 명령 표에 있다.
GROUPS = {
    '흐름': (0x00, 0x02, 0x09, 0x4F, 0x90, 0x96, 0xEE, 0xF5, 0x107, 0x12F, 0x156),
    '깃발': (0x17, 0x18, 0x45, 0x46),
    '조건': (0x0A, 0x0B, 0x10, 0x16, 0x19, 0x41, 0x42, 0x43, 0x49, 0x4A, 0x6F, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75,
        0x76, 0x80, 0xD9, 0x111, 0x126),
    '대사': (0x03, 0x04, 0x05, 0x06, 0x15, 0xDB, 0x11A, 0x11B, 0x120, 0x128, 0x136, 0x139, 0x140, 0x142, 0x14F,
        0x150, 0x160, 0x16C),
    '창': (0x11, 0x3C, 0x3D, 0x8A, 0x8B, 0x8C, 0x98, 0x99, 0xB3, 0xB8, 0xC5, 0xCF, 0x12B, 0x12C, 0x12D, 0x12E,
        0x130, 0x133, 0x153),
    '인물': (0x07, 0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x44, 0x4B, 0x4C, 0x4D,
        0x4E, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60,
        0x61, 0x82, 0x83, 0x84, 0x8F, 0x9A, 0x9B, 0x9C, 0x9D, 0x9E, 0xA7, 0xB1, 0xE7, 0xE8, 0xEB, 0xF7, 0xF8, 0xF9,
        0x108, 0x112, 0x113, 0x11F, 0x124, 0x125, 0x129, 0x138, 0x13F, 0x148, 0x14A, 0x14D, 0x151, 0x161, 0x167,
        0x171),
    '주인공': (0x08, 0x38, 0x39, 0x3A, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F, 0x91, 0x92, 0x93, 0x94, 0x95, 0xA3,
        0xA5, 0xA6, 0xB0, 0xB7, 0xBA, 0xBB, 0xDC, 0xEC, 0xED, 0x109, 0x10A, 0x10B, 0x116, 0x117, 0x135, 0x143,
        0x159, 0x15A, 0x15B, 0x15C, 0x166, 0x173),
    '카메라': (0x21, 0x22, 0x23, 0x24, 0x29, 0x85, 0xA4, 0xB4, 0xB5, 0xB6, 0xB9, 0xBF, 0xC3, 0xC6, 0xCB, 0x121, 0x122,
        0x14C, 0x157),
    '화면': (0x0C, 0x0D, 0x0E, 0x0F, 0x40, 0x8D, 0x8E, 0xA8, 0xB2, 0xC9, 0xCA, 0x174, 0x176),
    '소리': (0x62, 0x63, 0x86, 0x87, 0xEF, 0x100, 0x13A, 0x146, 0x147),
    '소품': (0x1A, 0x1C, 0x1D, 0x1E, 0x68, 0x69, 0x97, 0xA2, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xC1, 0xC7, 0xCC,
        0xCD, 0xDD, 0xF3, 0xF4, 0xF6, 0xFD, 0x123, 0x141),
    '조사': (0x2A, 0x2B, 0xF2, 0x11C, 0x137),
    '맵 이동': (0x1F, 0x20, 0x25, 0x26, 0x27, 0x47, 0x48, 0xBE, 0x118, 0x119, 0x11D, 0x132),
    '맵 상태': (0x1B, 0x28, 0x3F, 0xC2, 0xD8, 0xFB, 0x13D, 0x14B, 0x15F, 0x169, 0x16A, 0x16D, 0x175),
    '일행': (0x12, 0x13, 0x14, 0x64, 0x65, 0x66, 0x67, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x77, 0x81, 0xAF, 0xC4, 0xEA,
        0xFC, 0xFF, 0x10C, 0x10F, 0x110, 0x114, 0x13B, 0x162, 0x163),
    '진행': (0xFA, 0x10D, 0x115, 0x144, 0x14E, 0x170),
    '전투': (0x3E, 0x78, 0x88, 0x10E, 0x164),
    '동료 대화': (0xD2, 0xD4, 0xD5, 0xD6, 0xD7, 0x11E, 0x13E, 0x152),
    '이민 마을': (0x101, 0x102, 0x103, 0x104, 0x105, 0x106, 0x12A, 0x131, 0x134, 0x16B),
    '필드': (0xBD, 0xC0, 0xC8, 0x145, 0x15D),
    '기타': (0xBC, 0xFE, 0x127, 0x154, 0x155, 0x168, 0x16E, 0x172, 0x177),
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
        group = {op: g for g, ops in GROUPS.items() for op in ops}
        for op, a in enumerate(handlers(arm9)):
            name = '(처리 없음)' if a == default else OPS.get(op, ('', ''))[0]
            n = ','.join(map(str, sorted(nargs[op]))) or '-'
            print(f'{op:03X}\t{a:08X}\t{use[op]}\t{n}\t{group.get(op, "")}\t{name}')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
