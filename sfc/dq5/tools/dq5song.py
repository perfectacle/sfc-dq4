"""DQ5(SFC) 곡 시퀀스 디코더. 형식은 sfc/dq5/docs/dq5-sound-format.md 「시퀀스 형식」.

시퀀스 n(2E:E2E4~, dq5spc.sequences)은 [템포][트랙 수 N][트랙 오프셋 2바이트 x N] 머리 뒤에 트랙 바이트가 온다.
오프셋은 시퀀스 첫 바이트 기준이다. 트랙 바이트는 SPC 드라이버 154E 가 읽는다:
  00~4F      음표(앞 길이). 00 = 쉼, 4F = 붙임, 그 밖은 음 번호 + 조옮김
  50~9F      음표(새 길이). 다음 바이트가 길이, 음 번호 = 바이트 - 50
  A0~B5      소리 길이 비율 미리 정한 값(17CD 표)
  B6~DA      건너뜀
  DB~FE      명령(표 0795, 인자 수는 ARGS)
  FF         트랙 끝

사용:
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc 02          # 시퀀스 02 를 글로
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc --check     # 0x47개 모두 끝까지 풀어 모르는 바이트·범위 밖 점프 검사
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc 02 --kon dspw.txt --start 500
      # sfc/dq5/tools/lua/dq5dspw.lua 기록의 KON 시각·피치와 디코더 음표를 트랙(=목소리)마다 견줌
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5spc import body, sequences  # noqa: E402

# 명령 바이트: (이름, 인자 수). 처리기 주소는 SPC RAM 0795 표.
ARGS = {
    0xDB: ("if_loop2", 2), 0xDC: ("loop2", 2), 0xDD: ("release", 1), 0xDE: ("adsr_release", 3),
    0xDF: ("phase", 1), 0xE0: ("if_flag", 3), 0xE1: ("marker", 0), 0xE2: ("e2", 1),
    0xE3: ("noise_on", 0), 0xE4: ("noise_off", 0), 0xE5: ("song_volume", 1), 0xE6: ("e6", 2),
    0xE7: ("e7", 1), 0xE8: ("pan_slide", 2), 0xE9: ("e9", 1), 0xEA: ("jump", 2),
    0xEB: ("tempo", 1), 0xEC: ("gate", 1), 0xED: ("volume", 1), 0xEE: ("pan", 1),
    0xEF: ("adsr", 2), 0xF0: ("instrument", 1), 0xF1: ("follow", 0), 0xF2: ("follow", 0),
    0xF3: ("follow_off", 0), 0xF4: ("loop2b", 2), 0xF5: ("loop", 3), 0xF6: ("volume2", 1),
    0xF7: ("nop", 0), 0xF8: ("call", 2), 0xF9: ("ret", 0), 0xFA: ("transpose", 1),
    0xFB: ("vibrato", 2), 0xFC: ("echo_on", 0), 0xFD: ("echo_off", 0), 0xFE: ("fe", 1),
}
GATES = bytes.fromhex("0d1a2633404d5a6673808c99a6b3bfccd9e6f2feff00")  # 17CD, A0~B5
JUMPS = {0xDB, 0xDC, 0xE0, 0xEA, 0xF4, 0xF5, 0xF8}


def header(seq):
    """(템포, [트랙 오프셋])."""
    return seq[0], [seq[2 + 2 * i] | seq[3 + 2 * i] << 8 for i in range(seq[1])]


def step(seq, pc):
    """pc 의 바이트 하나를 풀어 (다음 pc, 글, 점프 대상 또는 None, 흐름) 을 돌려준다.
    흐름은 'go'(계속)·'end'(FF)·'ret'(F9)·'jump'(EA)."""
    b = seq[pc]
    if b < 0x50:
        name = "rest" if b == 0 else "tie" if b == 0x4F else f"note {b:02X}"
        return pc + 1, name, None, "go"
    if b < 0xA0:
        n = b - 0x50
        name = "rest" if n == 0 else "tie" if n == 0x4F else f"note {n:02X}"
        return pc + 2, f"{name} len {seq[pc + 1]:02X}", None, "go"
    if b < 0xB6:
        return pc + 1, f"gate_preset {GATES[b - 0xA0]:02X}", None, "go"
    if b < 0xDB:
        return pc + 1, f"skip {b:02X}", None, "go"
    if b == 0xFF:
        return pc + 1, "end", None, "end"
    name, n = ARGS[b]
    arg = seq[pc + 1:pc + 1 + n]
    nxt = pc + 1 + n
    target = None
    if b in JUMPS:
        off = arg[1] | arg[2] << 8 if b == 0xF5 else arg[0] | arg[1] << 8  # F5 는 [횟수][오프셋]
        target = (nxt + off) & 0xFFFF
    text = f"{name} {' '.join(f'{a:02X}' for a in arg)}".rstrip()
    if target is not None:
        text += f" -> {target:04X}"
    flow = "jump" if b == 0xEA else "ret" if b == 0xF9 else "go"
    return nxt, text, target, flow


def walk(seq, start, limit=200000):
    """start 부터 흐름을 따라 닿는 바이트를 모두 푼다. {pc: (다음 pc, 글)}, [문제].
    F8 은 돌아올 자리를 쌓고, F9 는 쌓인 것이 없으면 아무것도 안 하고 다음 바이트로 간다(1970)."""
    seen, problems = {}, []
    todo, visited = [(start, ())], set()
    while todo and len(visited) < limit:
        pc, stack = todo.pop()
        while (pc, stack) not in visited:
            visited.add((pc, stack))
            if not 0 <= pc < len(seq):
                problems.append(f"pc {pc:04X} out of sequence")
                break
            nxt, text, target, flow = step(seq, pc)
            if nxt > len(seq):
                problems.append(f"{pc:04X} {text}: runs past end")
                break
            seen[pc] = (nxt, text)
            if target is not None and target >= len(seq):
                problems.append(f"{pc:04X} {text}: target out of sequence")
                break
            b = seq[pc]
            if flow == "end":
                break
            if b == 0xF8:
                if len(stack) >= 3:
                    problems.append(f"{pc:04X} call nested deeper than 3")
                    break
                stack, pc = stack + (nxt,), target
                continue
            if flow == "ret":
                if stack:
                    pc, stack = stack[-1], stack[:-1]
                else:
                    pc = nxt
                continue
            if flow == "jump":
                pc = target
                continue
            if target is not None:
                todo.append((target, stack))
            pc = nxt
    return seen, problems


class Track:
    def __init__(self, pc):
        self.pc, self.wait, self.dur, self.transpose, self.follow, self.instrument = pc, 1, 0, 0, False, None
        self.noise = False
        self.c1 = self.c2 = 0
        self.stack, self.events, self.done = [], [], False


def play(seq, max_ticks=4000, flag=0):
    """곡 전체를 틱 단위로 따라가며 트랙마다 [(틱, 음 번호 또는 None(쉼)·'tie', 악기, 잡음)] 를 낸다. 음 번호는 조옮김을 더한 값.
    드라이버처럼 틱마다 트랙 0 부터 차례로 기다림을 줄이고, 0 이 되면 다음 음표까지 읽는다.
    follow(F1·F2)인 트랙은 음표마다 바로 앞 트랙의 길이를 가져온다(1C64). if_flag 는 곡 변수(03E7)가 flag 인 것으로 보고,
    드라이버처럼 if_flag 를 읽은 틱이 끝나면 0 으로 돌린다(14BC). flag 는 명령 0C 의 X 가 고르는 스크립트(0801 표, 05 n)가 넣는다."""
    _, offs = header(seq)
    tracks = [Track(o) for o in offs]
    for tick in range(max_ticks):
        flag_read = False
        for i, t in enumerate(tracks):
            if t.done:
                continue
            t.wait -= 1
            steps = 0
            while t.wait == 0 and not t.done and steps < 5000:
                steps += 1
                if not 0 <= t.pc < len(seq):
                    t.done = True
                    break
                b = seq[t.pc]
                nxt, _, target, flow = step(seq, t.pc)
                if b < 0xA0:
                    if t.follow and i > 0:
                        t.dur = tracks[i - 1].dur
                    n = b - 0x50 if b >= 0x50 else b
                    if b >= 0x50:
                        t.dur = seq[t.pc + 1]
                    t.events.append((tick, None if n == 0 else "tie" if n == 0x4F else n + t.transpose, t.instrument, t.noise))
                    t.wait = t.dur or 0x100
                elif b == 0xFF:
                    t.done = True
                elif b == 0xF0:
                    t.instrument = seq[t.pc + 1]
                elif b in (0xE3, 0xE4):
                    t.noise = b == 0xE3
                elif b == 0xFA:
                    t.transpose = seq[t.pc + 1] - 256 if seq[t.pc + 1] >= 0x80 else seq[t.pc + 1]
                elif b in (0xF1, 0xF2):
                    t.follow = True
                elif b == 0xF3:
                    t.follow = False
                elif b == 0xDC:
                    t.c1 = (t.c1 or 2) - 1
                    nxt = target if t.c1 else nxt
                elif b == 0xDB:
                    nxt = target if t.c1 else nxt
                elif b in (0xF4, 0xF5):
                    t.c2 = (t.c2 or (2 if b == 0xF4 else seq[t.pc + 1])) - 1
                    nxt = target if t.c2 else nxt
                elif b == 0xE0:
                    nxt = target if seq[t.pc + 3] == flag else nxt
                    flag_read = True
                elif b == 0xEA:
                    nxt = target
                elif b == 0xF8:
                    t.stack.append(nxt)
                    nxt = target
                elif b == 0xF9 and t.stack:
                    nxt = t.stack.pop()
                t.pc = nxt
        if flag_read:
            flag = 0
    return [t.events for t in tracks]


def decode(seq):
    tempo, offs = header(seq)
    lines = [f"tempo {tempo:02X} tracks {len(offs)}"]
    problems = []
    for t, off in enumerate(offs):
        seen, p = walk(seq, off)
        problems += [f"track {t}: {x}" for x in p]
        lines.append(f"track {t} @ {off:04X}")
        lines += [f"  {pc:04X} {text}" for pc, (_, text) in sorted(seen.items())]
    return lines, problems


def read_kon(path):
    """dq5dspw.lua 기록에서 목소리마다 [(프레임, 피치, 잡음 주파수)] (KON 이 켜질 때의 피치 레지스터와 FLG 하위 5비트)."""
    pitch = [[0, 0] for _ in range(8)]
    kon = [[] for _ in range(8)]
    flg = 0
    for line in open(path):
        f, rv = line.split()
        r, v = (int(x, 16) for x in rv.split("="))
        if r < 0x80 and r & 0x0F in (2, 3):
            pitch[r >> 4][(r & 0x0F) - 2] = v
        elif r == 0x6C:
            flg = v
        elif r == 0x4C:
            for vo in range(8):
                if v >> vo & 1:
                    kon[vo].append((int(f), pitch[vo][0] | pitch[vo][1] << 8, flg & 0x1F))
    return kon


def compare(seq, kon, start, count=12, flag=0, voice=0):
    """트랙 i 를 목소리 voice + i 로 보고(효과음은 목소리 7), 음표 count 개의 시각과 음 차이를 KON 기록과 견준다.
    시각은 첫 음과 틱당 프레임(처음·끝 음으로 맞춤)으로 계산한다. 음 차이는 악기가 같은 이웃 음끼리만 본다(샘플마다 음높이가 다름). 잡음(E3) 음은 FLG 하위 5비트 = 음 번호 & 1F 를 본다(1B46).
    [(트랙, 틱당 프레임, 최대 프레임 차, 음 차이 틀린 수, 견준 음 수)]."""
    out = []
    for i, ev in enumerate(play(seq, 6000, flag)):
        notes = [e for e in ev if isinstance(e[1], int)]
        k = [x for x in kon[voice + i] if x[0] >= start][:count] if voice + i < 8 else []
        m = min(len(notes), len(k), count)
        if m < 2:
            out.append((i, None, None, None, m))
            continue
        fpt = (k[m - 1][0] - k[0][0]) / (notes[m - 1][0] - notes[0][0])
        err = max(abs(k[j][0] - (k[0][0] + (notes[j][0] - notes[0][0]) * fpt)) for j in range(m))
        bad = sum(k[j][2] != notes[j][1] & 0x1F for j in range(m) if notes[j][3])
        bad += sum(round(12 * math.log2(k[j][1] / k[j - 1][1])) != notes[j][1] - notes[j - 1][1]
                   for j in range(1, m) if notes[j][2] == notes[j - 1][2] and not notes[j][3] and not notes[j - 1][3])
        out.append((i, fpt, err, bad, m))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("seq", nargs="?", type=lambda s: int(s, 16))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--kon", metavar="DSPW", help="lua/dq5dspw.lua 의 dspw.txt 와 음표 시각·음 차이를 견줌")
    ap.add_argument("--start", type=int, default=0, help="--kon 에서 곡이 시작한 프레임(이 앞의 KON 은 뺌)")
    ap.add_argument("--voice", type=int, default=0, help="트랙 0 이 쓰는 목소리(효과음은 7)")
    ap.add_argument("--count", type=int, default=12, help="견줄 음 수")
    ap.add_argument("--flag", type=lambda v: int(v, 16), default=0, help="곡 변수(명령 0C 의 X 스크립트가 넣는 값)")
    args = ap.parse_args()
    rom = Rom(open(args.rom, "rb").read())
    seqs = [body(rom, a, n) for _, a, n in sequences(rom)]
    if args.check:
        bad = 0
        for i, seq in enumerate(seqs):
            if len(seq) < 2:
                print(f"{i:02X}: empty ({len(seq)} bytes)")
                continue
            tempo, offs = header(seq)
            covered = set()
            lines, problems = decode(seq)
            for off in offs:
                seen, _ = walk(seq, off)
                for pc, (nxt, _) in seen.items():
                    covered.update(range(pc, nxt))
            unread = len(seq) - (2 + 2 * len(offs)) - len(covered)
            bad += len(problems)
            print(f"{i:02X}: tempo {tempo:02X} tracks {len(offs)} bytes {len(seq):4d} unread {unread:3d}"
                  + (f" PROBLEMS {problems[:3]}" if problems else ""))
        print(f"{len(seqs)} sequences, {bad} problems")
        sys.exit(1 if bad else 0)
    if args.kon:
        for i, fpt, err, bad, m in compare(seqs[args.seq], read_kon(args.kon), args.start, args.count, args.flag, args.voice):
            if fpt is None:
                print(f"track {i}: {m} notes compared")
            else:
                print(f"track {i}: {m} notes, {fpt:.4f} frame/tick, max frame error {err:.1f}, pitch mismatches {bad}")
        return
    lines, problems = decode(seqs[args.seq])
    print("\n".join(lines + problems))


if __name__ == "__main__":
    main()
