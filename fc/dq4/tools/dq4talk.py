"""DQ4(FC) 인물 대화 → 메시지 번호. 형식은 fc/dq4/docs/dq4-script-format.md.

사용:
  python fc/dq4/tools/dq4talk.py rom/dq4.nes G K [--ram end.ram] [--night]
                                                            맵 (그룹, 순번) 의 인물마다 대화 번호·스크립트·대사(--night: 밤 목록)
  python fc/dq4/tools/dq4talk.py rom/dq4.nes id N                   대화 번호 N(16진) 하나
  python fc/dq4/tools/dq4talk.py rom/dq4.nes all                    모든 맵 인물·스크립트를 풀어 못 읽은 명령 수를 셈
  python fc/dq4/tools/dq4talk.py rom/dq4.nes calls                  호출 문장(00·01)이 부르는 뱅크 15 루틴을 하는 일로 나눈 표
  python fc/dq4/tools/dq4talk.py rom/dq4.nes compare DIR [--no]    lua/talk.lua 기록(DIR/talk.txt)의 메시지 번호와 예측 비교
                                                            (--no: 예/아니오에서 「いいえ」 를 골랐을 때)
  python fc/dq4/tools/dq4talk.py rom/dq4.nes events [--compare DIR...]
                                                            이벤트 표 1C:$BF74 의 번호마다 전투·플래그·메시지·장소·부르는 곳
                                                            (--compare: EV 로 돌린 talk.lua 기록과 대조)
  python fc/dq4/tools/dq4talk.py rom/dq4.nes looks                  그림 번호마다 쓰는 인물 수·장소·첫 대사

--ram 을 주면 RAM 덤프의 플래그($627B~)·장($615A)·시간($62ED)·일행($616A~)·인물 레코드로 조건을 풀어
실제로 나올 메시지만 낸다. 덤프가 밤이면 밤 목록을 쓴다.

근거 루틴(뱅크 15): 대화 진입 $98F8, 대화 번호 → 갈래 $9962, 스크립트 표 $98F6 → $9642,
문장 실행 $9BA8, 조건 $99CE, 조건 결과 $9A4C, 건너뛰기 $9B1D·$9B38·$9B77, 예/아니오 대사 $9C92,
메시지 출력 $9914/$9919(16[04], X:A). 대화 번호는 1C[01]($96C7) 이 인물 레코드에서 꺼낸다.
"""
import sys
from pathlib import Path

from kr_patch.fc import ines
from kr_patch.fc.dis6502 import OPS, SIZE

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import dq4bank
import dq4map
import dq4text

BANK = 0x15
SCRIPTS = 0x9642          # $98F6 의 워드. 대화 번호 7~160 의 스크립트 포인터
SCRIPT_FIRST, YESNO_FIRST, MSG_FIRST = 0x007, 0x161, 0x179
MSG_BASE = 0x500          # 대화 번호 161 이상: 메시지 = 번호 - 161 + 500
SERVICE = 0x10000         # 예측 목록에서 메시지 번호 대신 서비스(15:$9CBF, A=n)를 나타내는 표시
NIGHT = dq4map.NIGHT     # $62ED 가 이 값 이상이면 밤(1C:$9BD9, 15:$9CE5)
WALK = range(0x616A, 0x616E)    # 걷는 일행 4자리
WAGON = range(0x6172, 0x6178)   # 마차 자리

# 서비스(대화 번호 0~6, 문장 12 의 인자) → 15:$9CBF 의 갈래 주소
SERVICES = {0: 0xB550, 1: 0xB84A, 2: 0xB858, 3: 0xB851, 4: 0xBBF0, 5: 0xB550, 6: 0xBF28}

# 조건 명령(아래 6비트) → (인자 바이트 수, 이름). bit7 이 켜져 있으면 결과를 뒤집는다.
CONDS = {
    0x02: (0, 'counter'),  # $E9(대화 진입 때 Y) 가 0: 카운터 너머에서 말 걸었다
    0x03: (1, 'party'),    # 걷는 일행에 인물 n 이 있고 살아 있다(BRK 63 63 40, 42 63 40)
    0x05: (0, 'yes'),      # 예/아니오 창(16[00] A=48), 「はい」 면 참
    0x11: (1, 'item'),     # 일행 누군가가 아이템 n 을 가졌다(15:$A794 → BRK 66 73)
    0x13: (1, 'dead'),     # 일행(1~4장은 마차 포함)의 인물 n 이 죽어 있다(BRK 63 73, 42 73, 5장 6A 73)
    0x14: (0, 'day'),      # $62ED < 78
    0x16: (1, 'chapter'),  # $615A == n - 1
    0x1A: (2, 'flag!='),   # $627B+f != v
    0x1B: (2, 'flag&'),    # $627B+f & m != 0
    0x1C: (2, 'flag|'),    # ($627B+f | m) != 0
    0x1E: (0, 'male'),     # 선두가 남자(BRK 29 73, X=0)
}
STMT_ARGS = {0x17: 2, 0x18: 2, 0x19: 2, 0x12: 1, 0x00: 2, 0x01: 4}
STMT_NAMES = {0x17: 'flag&=', 0x18: 'flag|=', 0x19: 'flag=', 0x12: 'service', 0x00: 'call', 0x01: 'call+2'}
END_BLOCK = (0x3E, 0x3F)


def rd(prg, a):
    return prg[BANK * 0x4000 + (a & 0x3FFF)]


def talk_id(rec, night=False):
    """1C:$96C7: 대화 번호 = (머리 바이트 1 bit4-2) << 8 | 머리 바이트 4.
    밤($62ED ≥ 78)에 F bit1 이 꺼져 있으면 (바이트 1 bit1-0) << 8 | 덧붙은 바이트(F bit0 이 꺼져 있으면 8, 켜져 있으면 7)."""
    if night and not rec[0] & 2:
        return (rec[1] & 3) << 8 | rec[7 if rec[0] & 1 else 8]
    return (rec[1] >> 2 & 7) << 8 | rec[4]


def look(rec, night=False):
    """1C:$96C7 이 돌려주는 A($03): bit7 = 바이트 5 bit7 의 반대, bit6 = 바이트 0 bit7, bit5-0 = 바이트 3 >> 2.
    밤에는 bit7 = 바이트 6 bit7 의 반대, F bit0 이 꺼져 있으면 bit6 = 바이트 1 bit7, bit5-0 = 바이트 7 >> 2."""
    if not night:
        return (0 if rec[5] & 0x80 else 0x80) | (rec[0] & 0x80) >> 1 | rec[3] >> 2
    b6, b = (rec[0], rec[3]) if rec[0] & 1 else (rec[1], rec[7])
    return (0 if rec[6] & 0x80 else 0x80) | (b6 & 0x80) >> 1 | b >> 2


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
            return r[0x62ED] < NIGHT
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
        if op == 0x03:
            m = self.member(WALK, args[0])
            return m is not None and self.alive(m)
        if op == 0x13:
            m = self.member(WALK, args[0])
            if m is not None:
                return not self.alive(m)
            if r[0x615A] >= 4 or self.member(WAGON, args[0]) is None:
                return False     # 5장($615A ≥ 4)은 BRK 6A 73 이 마차 자리를 빼낸다
            return self.wagon() and not self.alive(self.member(WAGON, args[0]))
        if op == 0x11:
            if any(args[0] in self.items(e) for e in self.party(WALK)):
                return True
            if not any(args[0] in self.items(e) for e in self.party(WAGON)):
                return False
            return self.wagon()
        if op == 0x1E:
            lead = self.party(WALK)
            return bool(lead) and not self.female(lead[0])
        return None

    def wagon(self):
        """10:$8498: 마차 자리를 셀지. $618E bit5(마차 있음)가 꺼졌거나 bit7 이면 안 세고, 아래 3비트가 0 이면 센다.
        1·2 는 $41 bit7 이 켜져 있고 마차가 지금 그룹($63)에 있을 때만 센다: 1 은 $618F(그리고 $07BA 가 4·5 가 아닐 때),
        2 는 $6193 을 그룹과 견준다. 3 이상은 세지 않는다."""
        r = self.ram
        v = r[0x618E]
        if not v & 0x20 or v & 0x80:
            return False
        if not v & 7:
            return True
        if not r[0x41] & 0x80:
            return False
        if v & 7 == 1:
            return r[0x07BA] not in (4, 5) and r[0x618F] == r[0x63]
        return v & 7 == 2 and r[0x6193] == r[0x63]

    def party(self, slots):
        """일행 자리($616A~ 걷는 4, $6172~ 마차)에서 bit7 이 켜진 자리의 값(아래 5비트 = 레코드 번호)."""
        return [self.ram[a] & 0x1F for a in slots if self.ram[a] & 0x80]

    def record(self, e):
        """10:$9FBA: 레코드 번호 9 미만은 $6001 + 30×번호, 그 밖(손님)은 $610F + 6×(번호 − 9)."""
        return 0x6001 + 30 * e if e < 9 else 0x610F + 6 * (e - 9)

    def char_id(self, e):
        """10:$884C: 9 미만은 번호 & 7, 손님은 레코드 바이트 5 로 정한 인물 번호."""
        if e < 9:
            return e & 7
        b = self.ram[self.record(e) + 5]
        return (b - 0xBD if b >= 0xC5 else b + 0x20) & 0xFF

    def member(self, slots, n):
        return next((e for e in self.party(slots) if self.char_id(e) == n), None)

    def alive(self, e):
        """10:$964A 가 1(죽음)을 돌려주는 것은 레코드 바이트 0 의 bit7 이 꺼졌을 때."""
        return bool(self.ram[self.record(e)] & 0x80)

    def items(self, e):
        """10:$99A3: 소지품 8칸(+13~+1A)의 아래 7비트. 손님은 소지품이 없다."""
        a = self.record(e) + 0x13
        return {self.ram[a + i] & 0x7F for i in range(8)} if e < 9 else set()

    def female(self, e):
        """10:$881F: 주인공(번호 & 7 = 0)은 $615C bit0, 손님은 바이트 5 = CB, 그 밖은 46 의 비트(ミネア·マーニャ·アリーナ)."""
        if e >= 9:
            return self.ram[self.record(e) + 5] == 0xCB
        k = e & 7
        return bool(self.ram[0x615C] & 1) if k == 0 else bool(0x46 >> (k - 1) & 1)


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


def pos(rec, night=False):
    """인물 표에 들어가는 X·Y(1C:$98ED/$9907). 밤에 F bit4 와 bit2 가 켜져 있지 않으면 덧붙은 바이트 두 개."""
    i = 5
    if night and rec[0] & 0x10 and not rec[0] & 4:
        i = 7 + (0 if rec[0] & 1 else 1) + (0 if rec[0] & 2 else 1)
    return rec[i] & 0x7F, rec[i + 1] & 0x7F


def is_night(ram):
    return ram[0x62ED] >= NIGHT


def npc_list(prg, g, k, night=False, ram=None):
    """인물 표 순서(슬롯 6~) 의 레코드. 낮은 F bit4, 밤은 F bit3 인 레코드만 차례로(1C:$9798).
    ram 을 주면 진행 플래그로 고른 목록(dq4map.place_records)을 쓴다."""
    recs = dq4map.place_records(prg, g, k, dq4map.ram_flags(ram) if ram is not None else None)
    return [r for r in recs if r[0] & (0x08 if night else 0x10)]


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
    ids, recs, nights = set(), 0, 0
    for g, k, *_ in dq4map.maps(prg):
        for r in npc_list(prg, g, k):
            recs += 1
            ids.add(talk_id(r))
        for r in npc_list(prg, g, k, night=True):
            nights += 1
            ids.add(talk_id(r, night=True))
    alts = 0
    for *_, a in dq4map.event_entries(prg):
        for r in dq4map.records_at(prg, 0x1C, a)[0]:
            alts += 1
            for night in (False, True):
                if r[0] & (0x08 if night else 0x10):
                    ids.add(talk_id(r, night))
    kinds = {}
    for t in range(SCRIPT_FIRST, YESNO_FIRST):
        classify(prg, t, parser)
    for t in ids:
        kinds[classify(prg, t)[0]] = kinds.get(classify(prg, t)[0], 0) + 1
    print(f'인물 낮 {recs}명·밤 {nights}명, 이벤트 목록 {len(dq4map.event_entries(prg))}개 {alts}명, 대화 번호 {len(ids)}가지: ' + ', '.join(f'{k} {v}' for k, v in sorted(kinds.items())))
    print(f'스크립트 {YESNO_FIRST - SCRIPT_FIRST}개를 풀어 못 읽은 명령 {len(parser.unknown)}개')
    for kind, a, b in parser.unknown:
        print(f'  {kind} {b:02X} @15:{a:04X}')
    return not parser.unknown


# 호출 문장이 부르는 루틴 안에서 알아보는 곳. 주소는 뱅크 15(와 $C000- 고정 뱅크 1F).
LEAF = {0xB0FF: 'event', 0xB0F6: 'event', 0x9919: 'msg', 0x9914: 'msg', 0xA695: 'msg', 0xB7DD: 'window',
        0xB84A: 'service', 0xB851: 'service', 0xB858: 'service', 0xBBF0: 'service', 0xBF28: 'service', 0xB550: 'service'}
CALL_TAGS = {   # 태그 → 표에 쓰는 이름. 앞에 있는 것이 그 루틴의 갈래(뜻은 fc/dq4/docs/dq4-script-format.md 「호출 문장」)
    'move': '잠·자리 옮김', 'service': '서비스', 'event': '이벤트(1C:$BF74 표)', 'mapevent': '맵 이벤트(1D:$B74D)',
    'item': '아이템', 'npc': '인물 움직임($7040)', 'window': '창', 'msg': '메시지'}
ITEM_CODES = {0x2E, 0x30, 0x66}   # 뱅크 10 일행 루틴(BRK n 73): 2E 주기, 30 빼기, 66 찾기


A_WRITERS = {'ADC', 'SBC', 'AND', 'ORA', 'EOR', 'ASL', 'LSR', 'ROL', 'ROR', 'PLA', 'TXA', 'TYA'}   # A 를 바꾸는 명령(LDA 빼고)


def brk_len(b1, b2):
    """BRK 문장 길이(복귀 = BRK + 길이). dq4-bank-format.md 의 x3 형식(10:$808A~)과 플래그 형식."""
    if b2 & 0x0F == 0x03:
        return 4 if b2 >> 4 in (2, 4, 6, 8) else 3
    return 4 if b2 & 0x0F == 0x0B and 0xCB <= b2 < 0xFB else 3


def call_tags(prg, start, seen=None, depth=0):
    """루틴 start 를 갈래까지 따라가며 (태그, 이벤트 번호) 를 모은다. JSR 은 뱅크 15 안이면 3단까지 들어간다."""
    seen = set() if seen is None else seen
    tags, todo = [], [(start, None)]
    while todo:
        a, imm = todo.pop()
        while (a, imm) not in seen and 0x8000 <= a < 0xC000:
            seen.add((a, imm))
            op = rd(prg, a)
            if op == 0x00:
                b1, b2 = rd(prg, a + 1), rd(prg, a + 2)
                if (b1, b2) == (0x07, 0xCF):
                    tags.append(('event', imm))
                elif (b1, b2) == (0x07, 0xDF):
                    tags.append(('mapevent', None))
                elif b2 == 0x73 and b1 in ITEM_CODES:
                    tags.append(('item', None))
                a += brk_len(b1, b2)
                continue
            if op not in OPS:
                break
            mn, md = OPS[op]
            n = 1 + SIZE[md]
            arg = rd(prg, a + 1) | (rd(prg, a + 2) << 8 if n == 3 else 0) if n > 1 else 0
            if mn == 'LDA':
                imm = arg if md == 'imm' else None
            elif mn in A_WRITERS:
                imm = None
            if mn in ('JSR', 'JMP') and md == 'abs':
                if arg in LEAF:
                    tags.append((LEAF[arg], imm))
                elif arg < 0xC000 and mn == 'JMP':
                    a = arg
                    continue
                elif arg < 0xC000 and depth < 3:
                    tags += call_tags(prg, arg, seen, depth + 1)
                if mn == 'JSR':
                    imm = None
                if mn == 'JMP':
                    break
            elif mn.startswith('ST') and md in ('zp', 'abs', 'abx'):
                if arg in (0x44, 0x45, 0x63, 0x64, 0x62ED):
                    tags.append(('move', None))
                elif 0x7040 <= arg < 0x7060:
                    tags.append(('npc', None))
            if mn in ('RTS', 'RTI') or (mn == 'JMP' and md == 'ind'):
                break
            if md == 'rel':
                to = (a + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF
                if imm is not None and (mn, imm == 0) in (('BNE', False), ('BEQ', True)):
                    a = to   # LDA #n 바로 뒤의 BNE/BEQ 는 늘 같은 쪽으로 간다
                    continue
                todo.append((to, imm))
            a += n
    return tags


def call_sites(prg):
    """대화 번호 7~160 의 스크립트에서 호출 문장마다 (대상 주소, 대화 번호, 인자)."""
    out = []

    def walk(tree, tid):
        for s in tree:
            if s[0] == 'if':
                walk(s[4], tid)
                walk(s[5] or [], tid)
            elif s[0] in ('call', 'call+2'):
                out.append((s[1][1] << 8 | s[1][0], tid, s[1][2:]))
    for t in range(SCRIPT_FIRST, YESNO_FIRST):
        walk(classify(prg, t)[2], t)
    return out


def show_calls(prg):
    sites = call_sites(prg)
    targets = sorted({a for a, *_ in sites})
    count = {}
    for a in targets:
        tags = call_tags(prg, a)
        kinds = list(dict.fromkeys(k for k, _ in tags))
        evs = sorted({v for k, v in tags if k == 'event' and v is not None})
        main = next((k for k in CALL_TAGS if k in kinds), None)
        count[main] = count.get(main, 0) + 1
        tids = ' '.join(f'{t:03X}' + ('+' + ''.join(f'{x:02X}' for x in arg) if arg else '') for b, t, arg in sites if b == a)
        names = ', '.join(CALL_TAGS[k] for k in CALL_TAGS if k in kinds) or '-'
        print(f'15:{a:04X}  {names}{" 이벤트 " + " ".join(f"{v:02X}" for v in evs) if evs else ""}  ← {tids}')
    print(f'호출 {len(sites)}곳, 루틴 {len(targets)}개: '
          + ', '.join(f'{CALL_TAGS[k] if k else "그 밖"} {v}' for k, v in count.items()))


EVENTS = (0x1C, 0xBF74, 0x32)   # 1C:$AD5F 가 A 번째 워드로 점프하는 표와 항목 수(그 뒤 $BFD8 부터는 다른 뱅크와 같은 조각)
EVENT_HELPERS = {0xBF4E: 'put', 0xBF5C: 'hide', 0xBF60: 'hide'}   # 슬롯 X+6 을 (A,Y)·(80,80)·(81,81) 자리에


def event_ops(prg, start):
    """이벤트 루틴을 갈래까지 따라가며 BRK·자리 쓰기를 모은다. 뱅크 1C 안의 JSR 은 2단까지 들어간다.
    돌려주는 것: [(종류, 값)] — battle(번호 또는 None), flag+/flag-/flag?(주소, 마스크), msg(번호), place(주소, 값), hide(슬롯)."""
    b = EVENTS[0]
    r1c = lambda a: prg[(0x1F if a >= 0xC000 else b) * 0x4000 + (a & 0x3FFF)]
    out, seen = [], set()

    def walk(a, depth):
        todo = [(a, None, None)]
        while todo:
            a, acc, x = todo.pop()
            while (a, acc, x) not in seen and 0x8000 <= a < 0xC000:
                seen.add((a, acc, x))
                op = r1c(a)
                if op == 0x00:
                    c = dq4bank.call(prg, a, b)
                    k = c['kind']
                    if (c['b1'], c['b2']) == (0x01, 0x8F):
                        out.append(('battle', acc))
                    elif k in ('flag-set', 'flag-clear', 'flag-test'):
                        out.append(({'flag-set': 'flag+', 'flag-clear': 'flag-', 'flag-test': 'flag?'}[k], (c['flag'], c['mask'])))
                    elif k == 'message':
                        out.append(('msg', c['msg']))
                    elif c.get('target') == 0x8028 and c.get('bank') == 0x16 and acc is not None:
                        out.append(('msg', acc))   # BRK 04 6F: X:A = 메시지 번호(X 를 모르면 A 만)
                    a += brk_len(c['b1'], c['b2'])
                    acc = None
                    continue
                if op not in OPS:
                    break
                mn, md = OPS[op]
                n = 1 + SIZE[md]
                arg = r1c(a + 1) | (r1c(a + 2) << 8 if n == 3 else 0) if n > 1 else 0
                if mn == 'LDA':
                    acc = arg if md == 'imm' else None
                elif mn == 'LDX':
                    x = arg if md == 'imm' else None
                elif mn in A_WRITERS:
                    acc = None
                if mn in ('JSR', 'JMP') and md == 'abs':
                    if arg in EVENT_HELPERS and EVENT_HELPERS[arg] == 'hide' and x is not None:
                        out.append(('hide', x + 6))
                    elif arg < 0xC000 and mn == 'JMP':
                        a = arg
                        continue
                    elif arg < 0xC000 and depth < 2 and arg not in EVENT_HELPERS:
                        walk(arg, depth + 1)
                    if mn == 'JMP':
                        break
                    acc = x = None
                elif mn == 'STA' and md in ('zp', 'abs') and arg in (0x63, 0x64, 0x65, 0x44, 0x45, 0x62ED):
                    out.append(('place', (arg, acc)))
                if mn in ('RTS', 'RTI') or (mn == 'JMP' and md == 'ind'):
                    break
                if md == 'rel':
                    to = (a + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF
                    if acc is not None and (mn, acc == 0) in (('BNE', False), ('BEQ', True)):
                        a = to
                        continue
                    todo.append((to, acc, x))
                a += n
    walk(start, 0)
    return out


def event_table(prg):
    b, t, n = EVENTS
    return [prg[b * 0x4000 + (t & 0x3FFF) + 2 * i] | prg[b * 0x4000 + (t & 0x3FFF) + 2 * i + 1] << 8 for i in range(n)]


def event_callers(prg):
    """이벤트 번호 → 부르는 곳. 대화 스크립트는 「대화 번호」, 다른 뱅크는 BRK 07 CF 앞의 LDA #n 으로 찾은 「뱅크:주소」."""
    out = {}
    sites = call_sites(prg)
    for a in sorted({a for a, *_ in sites}):
        for k, v in call_tags(prg, a):
            if k == 'event' and v is not None:
                out.setdefault(v, set()).update(f'{t:03X}' for b, t, _ in sites if b == a)
    for o in range(len(prg) - 3):
        bank = o // 0x4000
        if bank != BANK and prg[o:o + 3] == bytes([0, 0x07, 0xCF]) and prg[o - 2] == 0xA9:
            base = 0xC000 if bank in (0x0F, 0x1F) else 0x8000
            out.setdefault(prg[o - 1], set()).add(f'{bank:02X}:{base + (o & 0x3FFF):04X}')
    return out


PLACE_NAMES = {0x63: '$63', 0x64: '$64', 0x65: '$65', 0x44: '$44', 0x45: '$45', 0x62ED: '$62ED'}


def event_summary(ops):
    battles = [v for k, v in ops if k == 'battle']
    parts = []
    if battles:
        parts.append('전투 ' + ' '.join('?' if v is None else f'{v:02X}' for v in battles))
    for k, label in (('flag+', '켬'), ('flag-', '끔(&)'), ('flag?', '봄')):
        fs = [v for kk, v in ops if kk == k]
        if fs:
            parts.append(f'플래그 {label} ' + ' '.join(f'${a:04X}&{m:02X}' for a, m in fs))
    ms = [v for k, v in ops if k == 'msg']
    if ms:
        parts.append('메시지 ' + ' '.join(f'{m:04X}' for m in ms))
    pl = [v for k, v in ops if k == 'place']
    if pl:
        parts.append('자리 ' + ' '.join(f'{PLACE_NAMES[a]}={"?" if v is None else f"{v:02X}"}' for a, v in pl))
    hs = sorted({v for k, v in ops if k == 'hide'})
    if hs:
        parts.append('인물 숨김 ' + ' '.join(f'{v:02X}' for v in hs))
    return parts


def events_log(d):
    """talk.lua 기록에서 (이벤트 번호, 전투들, 바뀐 플래그 {주소: 값}, 메시지들, 바뀐 일행 자리 {주소: 값}).
    바뀐 것은 첫 말 걸기의 덤프(talk_1.bin)와 마지막으로 쓴 값이 다른 것."""
    before = (Path(d) / 'talk_1.bin').read_bytes()
    ev, battles, flags, msgs, party = None, [], [], [], []
    for line in (Path(d) / 'talk.txt').read_text().splitlines():
        p = line.split()
        if p[1] == 'ev1C':
            if ev is not None:
                break   # 그 뒤는 다음 이벤트(예: 2F 가 옮긴 맵에서 일어난 30)
            ev = int(p[2], 16)
        elif ev is None:
            continue
        elif p[1] == 'battle':
            battles.append(int(p[2], 16))
        elif p[1] == 'msg':
            msgs.append(int(p[2], 16))
        elif p[1] == 'w':
            a = int(p[2], 16)
            (party if 0x616A <= a < 0x617A else flags).append((a, int(p[3], 16)))
    changed = lambda ws: {a: v for a, v in dict(ws).items() if before[a] != v}
    return ev, battles, changed(flags), msgs, changed(party)


def show_events(prg, rom, dirs=()):
    table, callers = event_table(prg), event_callers(prg)
    logs = {}
    for d in dirs:
        lg = events_log(d)
        if lg[0] is not None:
            logs[lg[0]] = lg
    bad = 0
    for i, a in enumerate(table):
        ops = event_ops(prg, a)
        parts = event_summary(ops)
        who = ' '.join(sorted(callers.get(i, ()))) or '-'
        print(f'{i:02X} 1C:{a:04X}  ' + ('; '.join(parts) or '-') + f'  ← {who}')
        if i in logs:
            _, battles, flags, msgs, party = logs[i]
            want = [v for k, v in ops if k == 'battle' and v is not None]
            ok = not want or (battles and battles[0] == want[0])
            bad += not ok
            got = []
            if battles:
                got.append('전투 ' + ' '.join(f'{v:02X}' for v in battles))
            fl = {a: v for a, v in flags.items() if 0x627B <= a < 0x62B0}
            if fl:
                got.append('플래그 ' + ' '.join(f'${a:04X}={v:02X}' for a, v in sorted(fl.items())))
            pl = {a: v for a, v in flags.items() if a < 0x627B or a >= 0x62B0}
            if pl:
                got.append('자리 ' + ' '.join(f'${a:04X}={v:02X}' for a, v in sorted(pl.items())))
            if party:
                got.append('일행 ' + ' '.join(f'${a:04X}={v:02X}' for a, v in sorted(party.items())))
            if msgs:
                got.append('메시지 ' + ' '.join(f'{m:04X}' for m in dict.fromkeys(msgs)))
            print(f'   실행: ' + ('; '.join(got) or '바뀐 것 없음') + ('' if ok else '  (전투 번호 다름)'))
    if dirs:
        print(f'기록 {len(logs)}개, 전투 번호 다름 {bad}')
    return bad == 0


def sprite(rec, night=False):
    """맵에 들어갈 때 1C:$99B3 이 08[04] 에 넘기는 그림 번호: (look 의 아래 7비트) + 0F, 바이트 1 bit6(밤 bit5) 이면 | 80."""
    hi = rec[1] & (0x20 if night else 0x40)
    return ((look(rec, night) & 0x7F) + 0x0F) & 0xFF | (0x80 if hi else 0)


def show_looks(prg, rom):
    """롬의 모든 인물 레코드(보통 목록 낮·밤, 진행 목록)를 그림 번호로 모은다."""
    use = {}

    def add(rec, night, where):
        if rec[0] & (0x08 if night else 0x10):
            use.setdefault(sprite(rec, night), []).append((where, talk_id(rec, night)))
    for g, k, *_ in dq4map.maps(prg):
        for r in dq4map.npc_records(prg, g, k):
            add(r, False, f'{g:02X}/{k:02X}')
            add(r, True, f'{g:02X}/{k:02X}밤')
    for g, k, m, i, a in dq4map.event_entries(prg):
        for r in dq4map.records_at(prg, 0x1C, a)[0]:
            add(r, False, f'{g:02X}/{k:02X}*')
            add(r, True, f'{g:02X}/{k:02X}*밤')
    for n in sorted(use):
        places = list(dict.fromkeys(w for w, _ in use[n]))
        tid = next((t for _, t in use[n] if MSG_FIRST <= t), None)
        sample = ''
        if tid is not None:
            c = classify(prg, tid)
            sample = first_line(rom, c[1])[:30] if c[0] in ('msg', 'yesno') else ''
        print(f'그림 {n:02X}: 인물 {len(use[n]):3d}  장소 {len(places):2d} ({" ".join(places[:6])}{" …" if len(places) > 6 else ""})  {sample}')


def fmt(m):
    return '?' if m is None else f'서비스{m & 0xFF}' if m & SERVICE else f'{m:04X}'


def compare(prg, d, yes=True):
    """lua/talk.lua 의 기록(d/talk.txt, d/talk_N.bin)과 비교. 맵은 덤프의 $63/$64, 조건은 그 덤프로 푼다."""
    talks = []
    for ln in Path(f'{d}/talk.txt').read_text().splitlines():
        p = ln.split()
        if len(p) < 3:
            continue
        if p[1] == 'talk':
            ram = bytearray(Path(f'{d}/talk_{p[3]}.bin').read_bytes())
            talks.append([int(p[2], 16), ram, int(p[4], 16) == 0 if len(p) > 4 else False, [], [], None])
        elif p[1] == 'tid' and talks:
            talks[-1][5] = int(p[2], 16)
        elif p[1] == 'msg' and talks:
            talks[-1][3].append(int(p[2], 16))
        elif p[1] == 'cond' and talks:
            talks[-1][4].append(p[2] == '1')
        elif p[1] == 'svc' and talks:
            talks[-1][3].append(SERVICE | int(p[2], 16))
    bad = 0
    guessed = 0
    for slot, ram, counter, got, conds, logged in talks:
        g, k, night = ram[0x63], ram[0x64], is_night(ram)
        recs = npc_list(prg, g, k, night, ram)
        head = f'{g:02X}/{k:02X}{" 밤" if night else ""} 슬롯 {slot:02X}'
        if slot >= 6 and slot - 6 < len(recs):
            tid = talk_id(recs[slot - 6], night)
            if logged is not None and logged != tid:
                head += f' (대화 번호를 {logged:03X} 로 바꿈)'
        elif logged is None:
            print(f'{head}: 인물 없음, 기록 {" ".join(f"{m:04X}" for m in got)}')
            continue
        tid = tid if logged is None else logged
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
    if a[2] == 'calls':
        show_calls(prg)
        return
    if a[2] == 'id':
        describe(prg, rom, int(a[3], 16))
        return
    if a[2] == 'compare':
        sys.exit(0 if compare(prg, a[3], '--no' not in a) else 1)
    if a[2] == 'events':
        dirs = a[a.index('--compare') + 1:] if '--compare' in a else []
        sys.exit(0 if show_events(prg, rom, dirs) else 1)
    if a[2] == 'looks':
        show_looks(prg, rom)
        return
    g, k = int(a[2], 16), int(a[3], 16)
    night = '--night' in a or (ram is not None and is_night(ram))
    for i, r in enumerate(npc_list(prg, g, k, night, ram)):
        tid = talk_id(r, night)
        x, y = pos(r, night)
        print(f'{i:2d} 슬롯 {i + 6:02X} ({x:02X},{y:02X}) 겉모습 {look(r, night):02X} 대화 {tid:03X}')
        if ram:
            ms = predict(prg, tid, State(bytearray(ram)))
            print('  → ' + ' '.join('?' if m is None else f'{m:04X}' for m in ms))
        describe(prg, rom, tid)


if __name__ == '__main__':
    main()
