"""DQ4(FC) 인물 대화 → 메시지 번호. 형식은 docs/dq4-script-format.md.

사용:
  python tools/dq4talk.py rom/dq4.nes G K [--ram end.ram]   맵 (그룹, 순번) 의 인물마다 대화 번호·스크립트·대사
  python tools/dq4talk.py rom/dq4.nes id N                   대화 번호 N(16진) 하나
  python tools/dq4talk.py rom/dq4.nes all                    모든 맵 인물·스크립트를 풀어 못 읽은 명령 수를 셈
  python tools/dq4talk.py rom/dq4.nes compare DIR [--no]    lua/fc/talk.lua 기록(DIR/talk.txt)의 메시지 번호와 예측 비교
                                                            (--no: 예/아니오에서 「いいえ」 를 골랐을 때)

--ram 을 주면 RAM 덤프의 플래그($627B~)·장($615A)·시간($62ED)으로 조건을 풀어 실제로 나올 메시지만 낸다.

근거 루틴(뱅크 15): 대화 진입 $98F8, 대화 번호 → 갈래 $9962, 스크립트 표 $98F6 → $9642,
문장 실행 $9BA8, 조건 $99CE, 조건 결과 $9A4C, 건너뛰기 $9B1D·$9B38·$9B77, 예/아니오 대사 $9C92,
메시지 출력 $9914/$9919(16[04], X:A). 대화 번호는 1C[01]($96C7) 이 인물 레코드에서 꺼낸다.
"""
import sys
from pathlib import Path

from kr_patch.fc import ines

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import dq4map
import dq4text

BANK = 0x15
SCRIPTS = 0x9642          # $98F6 의 워드. 대화 번호 7~160 의 스크립트 포인터
SCRIPT_FIRST, YESNO_FIRST, MSG_FIRST = 0x007, 0x161, 0x179
MSG_BASE = 0x500          # 대화 번호 161 이상: 메시지 = 번호 - 161 + 500
SERVICE = 0x10000         # 예측 목록에서 메시지 번호 대신 서비스(15:$9CBF, A=n)를 나타내는 표시

# 서비스(대화 번호 0~6, 문장 12 의 인자) → 15:$9CBF 의 갈래 주소
SERVICES = {0: 0xB550, 1: 0xB84A, 2: 0xB858, 3: 0xB851, 4: 0xBBF0, 5: 0xB550, 6: 0xBF28}

# 조건 명령(아래 6비트) → (인자 바이트 수, 이름). bit7 이 켜져 있으면 결과를 뒤집는다.
CONDS = {
    0x02: (0, 'counter'),  # $E9(대화 진입 때 Y) 가 0: 카운터 너머에서 말 걸었다
    0x03: (1, 'party3'),   # BRK 63 63 40 → 10 함수 6, 인자 n
    0x05: (0, 'yes'),      # 예/아니오 창(16[00] A=48), 「はい」 면 참
    0x11: (1, 'item'),     # 15:$A794 → BRK 66 73
    0x13: (1, 'party13'),  # BRK 63 73 → 10 함수 7, 인자 n
    0x14: (0, 'day'),      # $62ED < 78
    0x16: (1, 'chapter'),  # $615A == n - 1
    0x1A: (2, 'flag!='),   # $627B+f != v
    0x1B: (2, 'flag&'),    # $627B+f & m != 0
    0x1C: (2, 'flag|'),    # ($627B+f | m) != 0
    0x1E: (0, 'call1E'),   # BRK 29 73 → 10 함수 7, X=0
}
STMT_ARGS = {0x17: 2, 0x18: 2, 0x19: 2, 0x12: 1, 0x00: 2, 0x01: 4}
STMT_NAMES = {0x17: 'flag&=', 0x18: 'flag|=', 0x19: 'flag=', 0x12: 'service', 0x00: 'call', 0x01: 'call+2'}
END_BLOCK = (0x3E, 0x3F)


def rd(prg, a):
    return prg[BANK * 0x4000 + (a & 0x3FFF)]


def talk_id(rec):
    """1C:$96C7: 대화 번호 = (머리 바이트 1 bit4-2) << 8 | 머리 바이트 4."""
    return (rec[1] >> 2 & 7) << 8 | rec[4]


def look(rec):
    """1C:$96C7 이 돌려주는 A($03): bit7 = 바이트 5 bit7 의 반대, bit6 = 바이트 0 bit7, bit5-0 = 바이트 3 >> 2."""
    return (0 if rec[5] & 0x80 else 0x80) | (rec[0] & 0x80) >> 1 | rec[3] >> 2


class Parser:
    """15:$9BA8(실행)·$9B38(건너뛰기) 와 같은 길이 규칙으로 스크립트를 나무로 푼다."""

    def __init__(self, prg):
        self.prg, self.unknown = prg, []

    def byte(self, a):
        return rd(self.prg, a)

    def block(self, a):
        """06 뒤 또는 스크립트 맨 처음: 문장을 3E/3F 가 나올 때까지(15:$9C2E)."""
        out = []
        while True:
            s, a = self.stmt(a)
            out.append(s)
            if s[0] in ('unknown', 'end'):
                return out, a
            if self.byte(a) in END_BLOCK:
                return out, a + 1

    def branch(self, a):
        """조건 뒤 갈래: 06 이면 블록, 아니면 문장 하나(15:$9A7B)."""
        if self.byte(a) == 0x06:
            return self.block(a + 1)
        s, a = self.stmt(a)
        return [s], a

    def stmt(self, a):
        b = self.byte(a)
        if b & 0x40:
            return ('msg', (b & 0x3F) << 8 | self.byte(a + 1)), a + 2
        if b == 0x3F:
            return ('end',), a + 1
        if b == 0x07:
            c = self.byte(a + 1)
            op = c & 0x3F
            if op not in CONDS:
                self.unknown.append(('cond', a + 1, c))
                return ('unknown', a + 1, c), a + 2
            n = CONDS[op][0]
            args = [self.byte(a + 2 + i) for i in range(n)]
            then, a = self.branch(a + 2 + n)
            other = None
            if self.byte(a) == 0x0B:
                other, a = self.branch(a + 1)
            return ('if', bool(c & 0x80), op, args, then, other), a
        if b in STMT_ARGS:
            n = STMT_ARGS[b]
            return (STMT_NAMES[b], [self.byte(a + 1 + i) for i in range(n)]), a + 1 + n
        self.unknown.append(('stmt', a, b))
        return ('unknown', a, b), a + 1


def script_addr(prg, tid):
    o = SCRIPTS + 2 * (tid - SCRIPT_FIRST)
    return rd(prg, o) | rd(prg, o + 1) << 8


def classify(prg, tid, parser=None):
    """15:$9962 의 갈래: ('service', n) / ('script', 주소, 나무, 끝) / ('yesno', 질문, 예, 아니오) / ('msg', 번호)."""
    if tid < SCRIPT_FIRST:
        return ('service', tid)
    if tid < YESNO_FIRST:
        a = script_addr(prg, tid)
        tree, end = (parser or Parser(prg)).block(a)
        return ('script', a, tree, end)
    m = tid - YESNO_FIRST + MSG_BASE
    if tid < MSG_FIRST:
        return ('yesno', m, m + 1, m + 2)   # 15:$9C92: 「はい」 면 +1, 「いいえ」 면 +2
    return ('msg', m)


class State:
    """RAM 덤프(CPU $0000-$7FFF)에서 조건을 푼다. 풀 수 없는 조건은 None."""

    def __init__(self, ram, yes=True, counter=False, oracle=None):
        self.ram, self.yes, self.counter = ram, yes, counter
        self.oracle, self.mismatch = oracle, 0   # oracle: talk.lua 가 기록한 조건마다 then 갈래를 탔는지

    def cond(self, op, args):
        r = self.ram
        if op == 0x14:
            return r[0x62ED] < 0x78
        if op == 0x16:
            return r[0x615A] == (args[0] - 1) & 0xFF
        if op == 0x1B:
            return r[0x627B + args[0]] & args[1] != 0
        if op == 0x1A:
            return r[0x627B + args[0]] != args[1]
        if op == 0x1C:
            return (r[0x627B + args[0]] | args[1]) != 0
        if op == 0x05:
            return self.yes
        if op == 0x02:
            return self.counter
        return None


def run(tree, state, out, flags=None):
    """나무를 state 로 실행해 나오는 메시지 번호를 out 에. 풀 수 없는 조건을 만나면 False."""
    for s in tree:
        k = s[0]
        if k == 'msg':
            out.append(s[1])
        elif k == 'end':
            return 'end'
        elif k == 'if':
            _, neg, op, args, then, other = s
            v = state.cond(op, args)
            if state.oracle:
                taken = state.oracle.pop(0)
                if v is not None and (v != neg) != taken:
                    state.mismatch += 1
                v = taken != neg
            if v is None:
                out.append(None)
                return False
            body = then if v != neg else other
            if body:
                r = run(body, state, out)
                if r is not True:
                    return r if r is False else True   # 갈래 안 3F 는 그 조건만 빠져나온다(15:$9BC1)
        elif k in ('flag|=', 'flag&=', 'flag=') and state is not None:
            f, v = s[1]
            ram = state.ram
            ram[0x627B + f] = ram[0x627B + f] | v if k == 'flag|=' else ram[0x627B + f] & v if k == 'flag&=' else v
        elif k == 'service':
            out.append(SERVICE | s[1][0])
            return 'end'                # 15:$9CBF 로 가면 스크립트로 돌아오지 않는다
        elif k == 'unknown':
            out.append(None)
            return False
    return True


def messages(tree, acc=None):
    """나무에 나오는 모든 메시지 번호(차례대로, 중복 없이)."""
    acc = [] if acc is None else acc
    for s in tree:
        if s[0] == 'msg' and s[1] not in acc:
            acc.append(s[1])
        elif s[0] == 'if':
            messages(s[4], acc)
            if s[5]:
                messages(s[5], acc)
    return acc


def cond_text(neg, op, args):
    name = CONDS[op][1]
    a = ' '.join(f'{x:02X}' for x in args)
    return ('not ' if neg else '') + name + (f' {a}' if a else '')


def show(tree, rom, depth=1):
    pad = '  ' * depth
    for s in tree:
        k = s[0]
        if k == 'msg':
            print(f'{pad}msg {s[1]:04X}  {first_line(rom, s[1])}')
        elif k == 'if':
            _, neg, op, args, then, other = s
            print(f'{pad}if {cond_text(neg, op, args)}')
            show(then, rom, depth + 1)
            if other:
                print(f'{pad}else')
                show(other, rom, depth + 1)
        elif k == 'unknown':
            print(f'{pad}?? {s[2]:02X} @15:{s[1]:04X}')
        elif k == 'end':
            print(f'{pad}end')
        elif k in ('call', 'call+2'):
            print(f'{pad}{k} 15:{s[1][1] << 8 | s[1][0]:04X}' + ''.join(f' {x:02X}' for x in s[1][2:]))
        else:
            print(f'{pad}{k} ' + ' '.join(f'{x:02X}' for x in s[1]))


def first_line(rom, m):
    t = dq4text.text(dq4text.shown(dq4text.message_bytes(rom, m)))
    return t.replace('\n', ' ')[:60]


def npc_list(prg, g, k):
    """인물 표 순서(슬롯 6~) 의 레코드: dq4map.npcs 와 같은 거르기(F bit4)."""
    return [r for r in dq4map.npc_records(prg, g, k) if r[0] & 0x10]


def predict(prg, tid, state):
    """state 에서 처음 출력될 메시지들(None 은 풀 수 없는 조건)."""
    c = classify(prg, tid)
    if c[0] == 'msg':
        return [c[1]]
    if c[0] == 'yesno':
        return [c[1], c[2] if state.yes else c[3]]
    if c[0] == 'service':
        return [SERVICE | c[1]]
    out = []
    st = State(bytearray(state.ram), state.yes, state.counter, list(state.oracle or []))
    run(c[2], st, out)
    state.mismatch = st.mismatch
    return out


def describe(prg, rom, tid):
    c = classify(prg, tid)
    if c[0] == 'service':
        print(f'  서비스 {c[1]} (15:{SERVICES[c[1]]:04X})')
    elif c[0] == 'msg':
        print(f'  msg {c[1]:04X}  {first_line(rom, c[1])}')
    elif c[0] == 'yesno':
        print(f'  msg {c[1]:04X}  {first_line(rom, c[1])}')
        print(f'  if yes: msg {c[2]:04X}  {first_line(rom, c[2])}')
        print(f'  else:   msg {c[3]:04X}  {first_line(rom, c[3])}')
    else:
        print(f'  스크립트 15:{c[1]:04X}-{c[3] - 1:04X}')
        show(c[2], rom, 2)


def check_all(prg):
    parser = Parser(prg)
    ids, recs = set(), 0
    for g, k, *_ in dq4map.maps(prg):
        for r in npc_list(prg, g, k):
            recs += 1
            ids.add(talk_id(r))
    kinds = {}
    for t in range(SCRIPT_FIRST, YESNO_FIRST):
        classify(prg, t, parser)
    for t in ids:
        kinds[classify(prg, t)[0]] = kinds.get(classify(prg, t)[0], 0) + 1
    print(f'인물 {recs}명, 대화 번호 {len(ids)}가지: ' + ', '.join(f'{k} {v}' for k, v in sorted(kinds.items())))
    print(f'스크립트 {YESNO_FIRST - SCRIPT_FIRST}개를 풀어 못 읽은 명령 {len(parser.unknown)}개')
    for kind, a, b in parser.unknown:
        print(f'  {kind} {b:02X} @15:{a:04X}')
    return not parser.unknown


def fmt(m):
    return '?' if m is None else f'서비스{m & 0xFF}' if m & SERVICE else f'{m:04X}'


def compare(prg, d, yes=True):
    """lua/fc/talk.lua 의 기록(d/talk.txt, d/talk_N.bin)과 비교. 맵은 덤프의 $63/$64, 조건은 그 덤프로 푼다."""
    talks = []
    for ln in Path(f'{d}/talk.txt').read_text().splitlines():
        p = ln.split()
        if len(p) < 3:
            continue
        if p[1] == 'talk':
            ram = bytearray(Path(f'{d}/talk_{p[3]}.bin').read_bytes())
            talks.append((int(p[2], 16), ram, int(p[4], 16) == 0 if len(p) > 4 else False, [], []))
        elif p[1] == 'msg' and talks:
            talks[-1][3].append(int(p[2], 16))
        elif p[1] == 'cond' and talks:
            talks[-1][4].append(p[2] == '1')
        elif p[1] == 'svc' and talks:
            talks[-1][3].append(SERVICE | int(p[2], 16))
    bad = 0
    guessed = 0
    for slot, ram, counter, got, conds in talks:
        g, k = ram[0x63], ram[0x64]
        recs = npc_list(prg, g, k)
        head = f'{g:02X}/{k:02X} 슬롯 {slot:02X}'
        if slot < 6 or slot - 6 >= len(recs):
            print(f'{head}: 인물 없음, 기록 {" ".join(f"{m:04X}" for m in got)}')
            continue
        tid = talk_id(recs[slot - 6])
        known = predict(prg, tid, State(ram, yes, counter))
        st = State(ram, yes, counter, conds)
        want = predict(prg, tid, st) if None in known else known
        guessed += None in known
        if want and want[-1] is not None and want[-1] & SERVICE:
            got = got[:got.index(want[-1]) + 1] if want[-1] in got else got   # 서비스 뒤 상점 대사는 비교하지 않음
        ok = bool(want) and None not in want and got[:len(want)] == want and not st.mismatch
        bad += not ok
        print(f'{head} 대화 {tid:03X}: 기록 {" ".join(map(fmt, got))}'
              f' / 예측 {" ".join(map(fmt, want))}{" (풀지 못한 조건은 기록대로)" if None in known else ""}'
              f' → {"같음" if ok else "다름"}')
    print(f'{len(talks)}번 중 {bad} 다름, 그중 {guessed}번은 풀지 못한 조건을 기록대로 따름')
    return bad == 0


def main():
    a = sys.argv
    data = Path(a[1]).read_bytes()
    prg, rom = ines.prg(data), dq4text.Rom(data)
    ram = bytearray(Path(a[a.index('--ram') + 1]).read_bytes()) if '--ram' in a else None
    if a[2] == 'all':
        sys.exit(0 if check_all(prg) else 1)
    if a[2] == 'id':
        describe(prg, rom, int(a[3], 16))
        return
    if a[2] == 'compare':
        sys.exit(0 if compare(prg, a[3], '--no' not in a) else 1)
    g, k = int(a[2], 16), int(a[3], 16)
    for i, r in enumerate(npc_list(prg, g, k)):
        tid = talk_id(r)
        print(f'{i:2d} 슬롯 {i + 6:02X} ({r[5] & 0x7F:02X},{r[6] & 0x7F:02X}) 겉모습 {look(r):02X} 대화 {tid:03X}')
        if ram:
            ms = predict(prg, tid, State(bytearray(ram)))
            print('  → ' + ' '.join('?' if m is None else f'{m:04X}' for m in ms))
        describe(prg, rom, tid)


if __name__ == '__main__':
    main()
