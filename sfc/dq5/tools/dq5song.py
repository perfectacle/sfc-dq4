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
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc 02          # 시퀀스 02 를 다시 쌀 수 있는 글로(--flow 는 트랙별 흐름 보기)
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc --check     # 0x47개 모두 풀어 모르는 바이트·범위 밖 점프 검사, 다시 싸서 바이트 비교
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc 03 --encode new.txt -o work/x.dq5patch.json
      # 글을 싸서 시퀀스 03 자리에 넣는 패치(제자리, 원래 길이 이하)
  python sfc/dq5/tools/dq5song.py rom/dq5.sfc 02 --kon dspw.txt --start 500
      # sfc/dq5/tools/lua/dq5dspw.lua 기록의 KON 시각·피치와 디코더 음표를 트랙(=목소리)마다 견줌
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5spc import SONG_SETS, body, sequences  # noqa: E402

# 명령 바이트: (이름, 인자 수). 처리기 주소는 SPC RAM 0795 표.
ARGS = {
    0xDB: ("if_loop2", 2), 0xDC: ("loop2", 2), 0xDD: ("release", 1), 0xDE: ("adsr_release", 3),
    0xDF: ("phase", 1), 0xE0: ("if_flag", 3), 0xE1: ("marker", 0), 0xE2: ("pitch_env", 1),
    0xE3: ("noise_on", 0), 0xE4: ("noise_off", 0), 0xE5: ("song_volume", 1), 0xE6: ("volume2_slide", 2),
    0xE7: ("fade", 1), 0xE8: ("pan_slide", 2), 0xE9: ("fine_tune", 1), 0xEA: ("jump", 2),
    0xEB: ("tempo", 1), 0xEC: ("gate", 1), 0xED: ("volume", 1), 0xEE: ("pan", 1),
    0xEF: ("adsr", 2), 0xF0: ("instrument", 1), 0xF1: ("follow1", 0), 0xF2: ("follow", 0),
    0xF3: ("follow_off", 0), 0xF4: ("loop2b", 2), 0xF5: ("loop", 3), 0xF6: ("volume2", 1),
    0xF7: ("nop", 0), 0xF8: ("call", 2), 0xF9: ("ret", 0), 0xFA: ("transpose", 1),
    0xFB: ("pitch_slide", 2), 0xFC: ("echo_on", 0), 0xFD: ("echo_off", 0), 0xFE: ("fe", 1),
}
GATES = bytes.fromhex("0d1a2633404d5a6673808c99a6b3bfccd9e6f2feff00")  # 17CD, A0~B5
JUMPS = {0xDB, 0xDC, 0xE0, 0xEA, 0xF4, 0xF5, 0xF8}
NAMES = {name: b for b, (name, _) in ARGS.items()}


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
        # 오프셋은 인자 바로 뒤 기준. F5 는 [횟수][오프셋], E0 은 [오프셋][값]
        off = arg[1] | arg[2] << 8 if b == 0xF5 else arg[0] | arg[1] << 8
        target = (nxt + off) & 0xFFFF
        arg = arg[:1] if b == 0xF5 else arg[2:]
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


def listing(seq):
    """다시 쌀 수 있는 글. 머리(tempo·track) 뒤에 본문을 처음부터 끝까지 차례로 풀고, 흐름으로 닿지 않는 바이트는 db 로 둔다.
    점프 대상과 트랙 시작에는 원래 자리로 이름(LXXXX)을 붙인다."""
    tempo, offs = header(seq)
    seen, targets = {}, set(offs)
    for off in offs:
        got, _ = walk(seq, off)
        seen.update(got)
    for pc in seen:
        target = step(seq, pc)[2]
        if target is not None:
            targets.add(target)
    lines = [f"tempo {tempo:02X}"] + [f"track L{o:04X}" for o in offs]
    pc = 2 + 2 * len(offs)
    while pc < len(seq):
        if pc in targets:
            lines.append(f"L{pc:04X}:")
        if pc in seen:
            nxt, text, target, _ = step(seq, pc)
            if target is not None:
                text = text.rsplit(" -> ", 1)[0] + f" -> L{target:04X}"
            lines.append(f"  {text}")
            pc = nxt
        else:
            lines.append(f"  db {seq[pc]:02X}")
            pc += 1
    return lines


def _encode_line(words, addr, labels):
    """글 한 줄을 바이트로. labels 가 None 이면 길이만 맞춘 자리 채움."""
    op = words[0]
    hexes = [int(w, 16) for w in words[1:] if not w.startswith("L") and w != "->" and w != "len"]
    target = next((w for w in words if w.startswith("L")), None)
    if op in ("note", "rest", "tie"):
        n = hexes[0] if op == "note" else 0 if op == "rest" else 0x4F
        if "len" in words:
            return bytes([n + 0x50, hexes[-1]])
        return bytes([n])
    if op == "gate_preset":
        return bytes([0xA0 + GATES.index(hexes[0])])
    if op in ("skip", "db"):
        return bytes(hexes)
    if op == "end":
        return b"\xff"
    b = NAMES[op]
    if b not in JUMPS:
        return bytes([b] + hexes)
    size = 1 + ARGS[b][1]
    off = 0 if labels is None else (labels[target] - (addr + size)) & 0xFFFF
    o = [off & 0xFF, off >> 8]
    return bytes([b] + (hexes + o if b == 0xF5 else o + hexes))


def assemble(lines):
    """listing() 꼴의 글을 시퀀스 바이트로 싼다. 이름은 두 번 훑어 자리를 정한다."""
    # 머리 줄(tempo·track)은 들여 쓰지 않고, 본문 명령은 들여 쓴다(명령 EB 도 이름이 tempo)
    lines = [ln.split("#")[0].rstrip() for ln in lines]
    head = [ln.split() for ln in lines if ln and not ln[0].isspace() and not ln.endswith(":")]
    body = [ln for ln in lines if ln.strip() and (ln[0].isspace() or ln.endswith(":"))]
    tempo = int(head[0][1], 16)
    tracks = [w[1] for w in head[1:]]
    labels, out = {}, None
    for final in (False, True):
        addr = 2 + 2 * len(tracks)
        data = bytearray()
        for ln in body:
            w = ln.split()
            if w[0].endswith(":"):
                labels[w[0][:-1]] = addr
                continue
            enc = _encode_line(w, addr, labels if final else None)
            data += enc
            addr += len(enc)
        if final:
            hdr = bytearray([tempo, len(tracks)])
            for t in tracks:
                hdr += bytes([labels[t] & 0xFF, labels[t] >> 8])
            out = bytes(hdr + data)
    return out


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


def patch(rom, n, new):
    """시퀀스 n 을 제자리에서 new 로 바꾸는 dq5patch/1. 시퀀스 묶음은 길이로 이어 걷기 때문에(2B:C3AB) 길이 바이트는 그대로 두고,
    new 가 짧으면 뒤를 FF 로 채운다. 원래보다 길면 거부한다."""
    _, a, ln = sequences(rom)[n]
    if len(new) > ln:
        raise SystemExit(f"sequence {n:02X}: {len(new)} bytes > {ln} (in-place only)")
    data = new + b"\xff" * (ln - len(new))
    o = lorom(a) + 2
    return {"format": "dq5patch/1", "name": f"song-{n:02X}", "writes": [
        {"at": f"0x{o:06X}", "hex": data.hex(" "), "orig": rom.d[o:o + ln].hex(" "),
         "note": f"시퀀스 {n:02X} 바꿔 넣기({len(new)} 바이트)"}]}


# 긴 시퀀스·새 샘플: 2B:C3AB(샘플·시퀀스 묶음을 길이로 걷기)를 늘린 뱅크의 고리로 돌린다. 시퀀스 묶음(2E:E2E4)이나
# 샘플 묶음(2B:EB00)을 걸을 때는 표의 3바이트 포인터([길이 2][자료] 의 자리)를 먼저 보고, 0 이면 원래대로 걷는다.
RELOC_BANK = 0x70
RELOC_CODE = 0x708010
RELOC_SEQ_TABLE = 0x708100  # 시퀀스 번호 x 3 (0x64 칸, SPC 04C7 표 크기)
RELOC_SMP_TABLE = 0x708300  # 샘플 번호 x 3 (0xC8 칸, SPC 03FF 표 크기)
RELOC_DATA = 0x708600


def _asm(items):
    """(바이트열 | ('label', 이름) | ('b', 명령 바이트, 이름)) 목록을 2번 훑어 짧은 분기를 채운다."""
    for final in (False, True):
        out, labels_now = bytearray(), {}
        for it in items:
            if isinstance(it, bytes):
                out += it
            elif it[0] == "label":
                labels_now[it[1]] = len(out)
            else:
                rel = (labels[it[2]] - (len(out) + 2)) if final else 0
                out += bytes([it[1], rel & 0xFF])
        labels = labels_now
    return bytes(out)


def reloc_code():
    def tbl(a, k=0):
        return bytes([(a + k) & 0xFF, (a + k) >> 8 & 0xFF, RELOC_BANK])
    h = bytes.fromhex
    return _asm([
        h("48 DA 5A"),                          # PHA / PHX / PHY (16비트, 2B:C21E·C22C 문맥)
        h("A5 FD 29 FF 00 C9 2E 00"), ("b", 0xD0, "smp"),  # 뱅크 2E?
        h("A5 FB C9 E4 E2"), ("b", 0xD0, "walk"),         # 시퀀스 묶음 시작?
        h("A0 00 00"), ("b", 0x80, "look"),
        ("label", "smp"), h("C9 2B 00"), ("b", 0xD0, "walk"),
        h("A5 FB C9 00 EB"), ("b", 0xD0, "walk"),
        h("A0") + bytes([(RELOC_SMP_TABLE - RELOC_SEQ_TABLE) & 0xFF, (RELOC_SMP_TABLE - RELOC_SEQ_TABLE) >> 8]),
        ("label", "look"),
        h("A3 05 29 FF 00 48 0A 18 63 01 83 01 98 18 63 01 AA 68"),  # X = 표 위치 + 번호 x 3
        h("BF") + tbl(RELOC_SEQ_TABLE), ("b", 0xF0, "walk"),
        h("85 FB E2 20 BF") + tbl(RELOC_SEQ_TABLE, 2) + h("85 FD C2 20"),
        ("label", "done"), h("7A FA 68 6B"),       # PLY / PLX / PLA / RTL
        ("label", "walk"), h("A3 05 29 FF 00 AA"), ("b", 0xF0, "done"),
        ("label", "loop"), h("A7 FB 1A 1A 18 65 FB 85 FB"), ("b", 0x90, "same"),
        h("A9 00 80 04 FB E6 FD"),                 # LoROM 뱅크 넘김(원래 루틴과 같음)
        ("label", "same"), h("CA"), ("b", 0xD0, "loop"), ("b", 0x80, "done"),
    ])


def patch_reloc(rom, seqs=None, smps=None, sets=None):
    """시퀀스 {번호: 바이트}·샘플 {번호: [길이 2][자료] 바이트}를 뱅크 70 에 두고 포인터 표로 가리키는 dq5patch/1(롬 4MB).
    sets 는 {곡 번호: 곡 묶음 레코드 바이트} 로, 같은 길이로 제자리를 덮는다(2B:E67F, 드라이버 이미지 안이라 SPC 28EC 에도 감)."""
    seqs, smps, sets = seqs or {}, smps or {}, sets or {}
    seq_table = bytearray(0x64 * 3)
    smp_table = bytearray(0xC8 * 3)
    data, addr = bytearray(), RELOC_DATA
    for table, items, wrap in ((seq_table, seqs, True), (smp_table, smps, False)):
        for n, b in sorted(items.items()):
            rec = bytes([len(b) & 0xFF, len(b) >> 8]) + b if wrap else b
            table[n * 3:n * 3 + 3] = bytes([addr & 0xFF, addr >> 8 & 0xFF, RELOC_BANK])
            data += rec
            addr += len(rec)
    if (RELOC_DATA & 0xFFFF) + len(data) > 0x10000:
        raise SystemExit("relocated data does not fit in bank 70")

    def at(a):
        return f"{a >> 16:02X}:{a & 0xFFFF:04X}"
    hook = bytes([0x22, RELOC_CODE & 0xFF, RELOC_CODE >> 8 & 0xFF, RELOC_BANK, 0x60])  # JSL 고리 / RTS
    writes = [
        {"at": "2B:C3AB", "hex": hook.hex(" "), "orig": rom.d[lorom(0x2BC3AB):lorom(0x2BC3AB) + 5].hex(" "),
         "note": "샘플·시퀀스 묶음 걷기를 포인터 표 고리로"},
        {"at": at(RELOC_CODE), "hex": reloc_code().hex(" "), "note": "포인터 표 고리"},
        {"at": at(RELOC_SEQ_TABLE), "hex": seq_table.hex(" "), "note": "시퀀스 포인터 표(0 이면 원래 자리)"},
        {"at": at(RELOC_SMP_TABLE), "hex": smp_table.hex(" "), "note": "샘플 포인터 표(0 이면 원래 자리)"},
        {"at": at(RELOC_DATA), "hex": data.hex(" "),
         "note": f"시퀀스 {sorted(seqs)} 샘플 {sorted(smps)}"},
    ]
    for song, rec in sorted(sets.items()):
        a = SONG_SETS
        for _ in range(song):
            a += rom.u8(a) + 2
        if len(rec) != rom.u8(a) + 2:
            raise SystemExit(f"song set {song:02X}: length must stay {rom.u8(a) + 2}")
        writes.append({"at": at(a), "hex": rec.hex(" "), "orig": rom.d[lorom(a):lorom(a) + len(rec)].hex(" "),
                       "note": f"곡 묶음 {song:02X}"})
    return {"format": "dq5patch/1", "name": "dq5song-reloc", "rom_size": 4, "writes": writes}


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
    ap.add_argument("--flow", action="store_true", help="흐름대로 닿는 바이트만 트랙별로(다시 쌀 수 없는 보기)")
    ap.add_argument("--encode", metavar="TXT", help="listing 꼴 글을 싸서 시퀀스 seq 자리에 넣는 dq5patch/1 을 -o 로")
    ap.add_argument("--reloc", action="store_true", help="--encode 를 제자리 대신 뱅크 70 의 포인터 표로(길이 제한 없음)")
    ap.add_argument("--sample", action="append", default=[], metavar="ID=FILE",
                    help="--reloc 와 함께: dq5brrenc.py 가 만든 샘플 자료를 샘플 번호 ID 로 더함")
    ap.add_argument("--set", action="append", default=[], metavar="N=HEX",
                    help="--reloc 와 함께: 곡 묶음 레코드 N 을 같은 길이의 바이트로 덮음")
    ap.add_argument("--seqfile", metavar="TXT", help="--kon 에서 롬 대신 이 글을 싸서 견줌")
    ap.add_argument("-o", "--out")
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
            if assemble(listing(seq)) != seq:
                problems.append("re-encode differs")
            bad += len(problems)
            print(f"{i:02X}: tempo {tempo:02X} tracks {len(offs)} bytes {len(seq):4d} unread {unread:3d}"
                  + (f" PROBLEMS {problems[:3]}" if problems else ""))
        print(f"{len(seqs)} sequences (decoded and re-encoded), {bad} problems")
        sys.exit(1 if bad else 0)
    if args.encode:
        new = assemble(open(args.encode, encoding="utf-8").read().splitlines())
        if args.reloc:
            smps = {int(k, 16): open(v, "rb").read() for k, v in (x.split("=", 1) for x in args.sample)}
            sets = {int(k, 16): bytes.fromhex(v) for k, v in (x.split("=", 1) for x in args.set)}
            doc = patch_reloc(rom, {args.seq: new}, smps, sets)
        else:
            doc = patch(rom, args.seq, new)
        print(json.dumps(doc, ensure_ascii=False, indent=1), file=open(args.out, "w"))
        print(f"sequence {args.seq:02X}: {len(new)} bytes into {len(seqs[args.seq])}")
        return
    if args.kon:
        if args.seqfile:
            seqs[args.seq] = assemble(open(args.seqfile, encoding="utf-8").read().splitlines())
        for i, fpt, err, bad, m in compare(seqs[args.seq], read_kon(args.kon), args.start, args.count, args.flag, args.voice):
            if fpt is None:
                print(f"track {i}: {m} notes compared")
            else:
                print(f"track {i}: {m} notes, {fpt:.4f} frame/tick, max frame error {err:.1f}, pitch mismatches {bad}")
        return
    if args.flow:
        lines, problems = decode(seqs[args.seq])
        print("\n".join(lines + problems))
        return
    print("\n".join(listing(seqs[args.seq])))


if __name__ == "__main__":
    main()
