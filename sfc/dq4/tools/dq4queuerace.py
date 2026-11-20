"""이름 대기열(WtQueue)을 짜는 동안 NMI 가 끼어들어도 대기열이 온전한지 본다.

WtQueue 는 항목을 짜는 동안 NMI 를 켜 둔다(항목 수를 늘리는 끝에서만 끔). 그래서 NMI 의 WqNmi 가 짜는 도중 아무
명령 경계에서나 대기열을 읽고 비울 수 있다. 장면을 돌려 그 경계에 NMI 가 우연히 왔는지에 기대면 운으로 통과하므로,
경계를 모두 훑는다.

1. MesenCE 헤드리스로 장면을 돌려 WtQueue 에 들어가는 순간의 레지스터와 WRAM 128KB 를 뜬다(lua/dq4queuesnap.lua).
2. 65816 해석기(sfc/dq5/tools/w65816.py)로 그 상태에서 WtQueue 를 돌린다. NMI 가 켜진 명령 경계마다 상태를 복제해
   거기서 WqNmi 를 끝까지 돌리고(NMI 가 대기열을 읽고 비움), 나머지 WtQueue 를 돌리고, 대기열이 빌 때까지 WqNmi 를 더 돌린다.
3. 끼어들기마다 VRAM 으로 나간 DMA(주소·방식·바이트)와 묶음 버퍼를 끼어들기 없는 실행과 견준다. 그리고 입구에 이미
   있던 항목이 모두 정확히 한 번씩 나갔는지, 묶음으로 뺀 이름이 대기열로 나가지 않았는지를 따로 본다(끼어들기 없는
   실행 자체가 틀리는 차례도 잡도록).

뜬 상태는 여섯 갈래(입구 항목 0·1·2개 이상 × 묶음으로 뺌·안 뺌)가 모두 있어야 한다. 하나라도 없으면 실패한다.
입구 대기열이 빈 상태에는 앞 항목 하나·둘을 끼워 넣은 변형도 만든다(앞 이름이 아직 나가지 않은 때와 같음).

  python sfc/dq4/tools/dq4queuerace.py --rom work/ch1/dq4-ch1.sfc --symbols work/wc/wn.sym --out work/race
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import w65816  # noqa: E402

LUA = HERE / 'lua' / 'dq4queuesnap.lua'
HEAD = 32
WQ_COUNT, WQ_RD, WQ_BUF = 0xA97E, 0xA978, 0x3EB0
WH_COUNT, WH_OFF, WH_BUF = 0x18302, 0x18304, 0x18320   # 7F:8302 등의 WRAM 오프셋
VBLANK_LINE = 0xE5          # WqNmi 가 읽는 주사선: 귀선 안
PER_CLASS = 2               # 갈래마다 견줄 상태 수
# (장면, 뜰 프레임 범위). 건네기는 앞 항목이 남은 채 이름을 바로 올리는 경우, sell-long-ch1(넘치는 팔기 목록)은 메시지 창이
# 보여 이름을 묶음으로 빼는 경우(WhStash, 311~328)가 이 범위에 있다. talk02-full 은 이름이 캔버스 밖 빌린 자리로 가 묶음
# 갈래가 생기지 않는다
WINDOWS = {'give-full': (440, 660), 'sell-long-ch1': (300, 340)}
WQ_OFF = 0xA980
# 입구 대기열이 빈 상태에 끼워 넣는 앞 항목: 방식 1(평면 0 + 평면 1 FF), 한 칸씩. 이름 슬롯이 쓰지 않는 VRAM 워드.
# 이름 하나는 항목 둘(글자 줄·위 줄)로 들어가므로 둘까지 넣는다. 항목 수에 따라 갈리는 검사(항목 수가 0 이 되나)가 있어서다
EXTRA = [(0x7F00, 1, 1, b'\x5a' * 8), (0x7F10, 1, 1, b'\xa5' * 8)]
# 갈래: (입구 항목 수 0·1·2 이상, 묶음으로 뺐나)
CLASSES = [(n, s) for n in (0, 1, 2) for s in (False, True)]


class RaceCpu(w65816.Cpu):
    """하드웨어 읽기 몇 개를 귀선 안처럼 돌려주고, NMI 켬($4200 bit7)과 VRAM DMA 를 적는 해석기."""

    def __init__(self, rom, wram):
        super().__init__(rom, wram, ppu=True)
        self.nmi_on = True
        self.dmas = []
        self._vhi = False
        self._vb = False

    def read(self, a):
        bank, addr = (a >> 16) & 0xFF, a & 0xFFFF
        if (bank & 0x7F) < 0x40:
            if addr == 0x213F or addr == 0x2137:
                self._vhi = False
                return 0
            if addr == 0x213D:
                v = 0 if self._vhi else VBLANK_LINE
                self._vhi = not self._vhi
                return v
            if addr == 0x4212:
                # 대기열이 찬 길은 귀선이 끝났다가 다시 오기를 기다린다: 읽을 때마다 귀선 밖·안을 번갈아
                self._vb = not self._vb
                return 0x80 if self._vb else 0
            if addr == 0x4210:
                return 0x80
        return super().read(a)

    def write(self, a, v):
        bank, addr = (a >> 16) & 0xFF, a & 0xFFFF
        if (bank & 0x7F) < 0x40 and addr == 0x4200:
            self.nmi_on = bool(v & 0x80)
        super().write(a, v)

    def _dma(self, ch):
        b = 0x4300 + ch * 16
        ctl, bb = self.reg[b], self.reg[b + 1]
        src = self.reg[b + 2] | self.reg[b + 3] << 8
        bank = self.reg[b + 4]
        n = self.reg[b + 5] | self.reg[b + 6] << 8 or 0x10000
        step = 0 if ctl & 0x08 else 1
        data = bytes(self.read((bank << 16) | ((src + i * step) & 0xFFFF)) for i in range(n))
        self.dmas.append((self.vaddr, ctl, bb, data))
        super()._dma(ch)


def load(path):
    raw = Path(path).read_bytes()
    h = raw[:HEAD]
    w = lambda i: h[i] | h[i + 1] << 8   # noqa: E731
    regs = {'frame': h[0] | h[1] << 8 | h[2] << 16, 'a': w(4), 'x': w(6), 'y': w(8), 's': w(10), 'd': w(12),
            'dbr': h[14], 'p': h[15], 'pbr': h[16], 'pc': w(17)}
    return regs, raw[HEAD:HEAD + 0x20000]


def pending(wram):
    """입구에 대기열에 있던 항목이 나가며 만들 DMA [(VRAM 워드, 방식, B 주소, 바이트)]."""
    out, y = [], wram[WQ_RD] | wram[WQ_RD + 1] << 8
    for _ in range(wram[WQ_COUNT]):
        at = WQ_BUF + y
        vram = (wram[at] | wram[at + 1] << 8) & 0x7FFF
        mode, cells = wram[at + 2], wram[at + 3]
        n = cells * 8 * (2 if mode == 0 else 1)
        data = bytes(wram[at + 4:at + 4 + n])
        if mode == 0:
            out.append((vram, 0x01, 0x18, data))
        else:
            out += [(vram, 0x00, 0x18, data), (vram, 0x08, 0x19, b'\xff' * n)]
        y += 4 + n
    return out


def with_pending(wram, n):
    """입구 대기열이 비었으면 앞 항목 n 개(EXTRA 앞에서부터)를 넣은 사본, 아니면 None. NMI 가 아직 보내지 않은 앞
    이름이 있는 때와 같은 상태다."""
    if wram[WQ_COUNT]:
        return None
    w = bytearray(wram)
    end = 0
    for vram, mode, cells, data in EXTRA[:n]:
        at = WQ_BUF + end
        w[at:at + 4] = (vram & 0xFF, vram >> 8, mode, cells)
        w[at + 4:at + 4 + len(data)] = data
        end += 4 + len(data)
    w[WQ_COUNT] = n
    w[WQ_RD:WQ_RD + 2] = (0, 0)
    w[WQ_OFF:WQ_OFF + 2] = (end & 0xFF, end >> 8)
    return bytes(w)


def stash(wram):
    count = wram[WH_COUNT] | wram[WH_COUNT + 1] << 8
    off = wram[WH_OFF] | wram[WH_OFF + 1] << 8
    return count, off, bytes(wram[WH_BUF:WH_BUF + min(off, 0x1EF0)])


def start(rom, regs, wram, entry):
    c = RaceCpu(rom, wram)
    c.a, c.x, c.y, c.s, c.d, c.dbr, c.p = regs['a'], regs['x'], regs['y'], regs['s'], regs['d'], regs['dbr'], regs['p']
    c.pbr, c.pc = entry >> 16, entry & 0xFFFF
    c.push16(0xFFFD)        # WtQueue 의 RTS 가 이 자리로 돌아오면 끝
    return c


def done(c):
    return c.pc == 0xFFFE


def nmi(c, wqnmi):
    keep = (c.a, c.x, c.y, c.s, c.d, c.dbr, c.p, c.pbr, c.pc)
    c.d, c.dbr = 0, 0
    c.jsl(wqnmi, max_steps=200_000)
    c.a, c.x, c.y, c.s, c.d, c.dbr, c.p, c.pbr, c.pc = keep


def finish(c, wqnmi, limit=400_000):
    """WtQueue 를 끝까지, 그다음 대기열이 빌 때까지 NMI. (DMA 목록, 묶음, 남은 항목 수)."""
    n = 0
    while not done(c):
        c.step()
        n += 1
        if n > limit:
            raise w65816.Stop('WtQueue 가 끝나지 않음')
    for _ in range(64):
        if not c.wram[WQ_COUNT]:
            break
        nmi(c, wqnmi)
    return c.dmas, stash(c.wram), c.wram[WQ_COUNT]


def judge(before, after_ref, runs, stashed):
    """before = 입구 항목의 DMA, after_ref = 끼어들기 없는 (DMA, 묶음, 남은 수), runs = [(경계, (DMA, 묶음, 남은 수))],
    stashed = 이 이름을 묶음으로 뺐나. [문제 글]."""
    problems = []
    want = Counter(before)
    ref_dmas, ref_stash, ref_left = after_ref
    ref_new = Counter(ref_dmas) - want
    lost = want - Counter(ref_dmas)
    if lost:
        problems.append(f'끼어들기 없이도 입구 항목 {sum(lost.values())}개 DMA 가 나가지 않음')
    if ref_left:
        problems.append(f'끼어들기 없이도 대기열이 비지 않음({ref_left})')
    if stashed and ref_new:
        problems.append(f'묶음으로 뺀 이름인데 대기열로도 DMA {sum(ref_new.values())}개가 나감')
    for k, (dmas, st, left) in runs:
        got = Counter(dmas)
        if want - got:
            problems.append(f'경계 {k}: 입구 항목 DMA {sum((want - got).values())}개가 나가지 않음(버려짐)')
        elif got - want != ref_new:
            extra = (got - want) - ref_new
            short = ref_new - (got - want)
            problems.append(f'경계 {k}: 새 항목 DMA 가 다름(더 나감 {sum(extra.values())}, 덜 나감 {sum(short.values())})')
        if st != ref_stash:
            problems.append(f'경계 {k}: 묶음 버퍼가 다름')
        if left:
            problems.append(f'경계 {k}: 대기열이 비지 않음({left})')
    return problems


def race(rom, regs, wram, entry, wqnmi):
    """(입구 항목 DMA, 끼어들기 없는 결과, [(경계, 결과)], 묶음으로 뺐나)."""
    before = pending(wram)
    st0 = stash(wram)
    ref = finish(start(rom, regs, wram, entry), wqnmi)
    runs, c, k = [], start(rom, regs, wram, entry), 0
    while True:
        if c.nmi_on:
            b = copy.deepcopy(c)
            nmi(b, wqnmi)
            runs.append((k, finish(b, wqnmi)))
        if done(c):
            break
        c.step()
        k += 1
    return before, ref, runs, ref[1] != st0


def snapshots(rom_path, symbols, out, mesence, libdir):
    import dq4windowcheck as wc
    import dq4vblankcheck as vb
    rom = Path(rom_path).read_bytes()
    states = wc.make_states(mesence, rom_path, rom, out / 'states')
    found = {s[0]: s for s in wc.scenes(states['shop'], states['shop'], states['shop'], states['battle'])}
    found.update({s[0]: s for s in vb.scenes(states)})
    paths = []
    for name, (a, b) in WINDOWS.items():
        scene = found[name]
        folder = out / name
        if not folder.exists():
            env_scene = scene[:5] + ((a, b),)
            os.environ.update(QSNAP=f'{symbols["WtQueue"]:06X}', QSNAPFROM=str(a), QSNAPTO=str(b), QSNAPMAX='120')
            saved = wc.PROBE
            wc.PROBE = LUA
            try:
                wc.run(mesence, libdir, rom_path, rom, folder, env_scene)
            finally:
                wc.PROBE = saved
        paths += sorted(folder.glob('q*.bin'))
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True, help='dq4menupatch 가 쓴 wn.sym')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    import dq4windowcheck as wc
    syms = wc.symbols(a.symbols)
    rom = a.rom.read_bytes()
    a.out.mkdir(parents=True, exist_ok=True)
    paths = snapshots(a.rom, syms, a.out.resolve(), os.environ['MESENCE'], os.environ['LIBDIR'])
    picked, classes = [], Counter()
    # 장면에서 뜬 그대로의 상태로 갈래를 먼저 채우고, 모자란 갈래만 끼워 넣은 변형으로
    loaded = [(p, *load(p)) for p in paths]
    variants = [(p, regs, wram, False) for p, regs, wram in loaded]
    variants += [(p, regs, with_pending(wram, n), True) for n in (1, 2) for p, regs, wram in loaded]
    for p, regs, w, added in variants:
        if w is None:
            continue
        ref = finish(start(rom, regs, w, syms['WtQueue']), syms['WqNmi'])
        key = (min(w[WQ_COUNT], 2), ref[1] != stash(w))
        if classes[key] < PER_CLASS:
            classes[key] += 1
            picked.append((p, regs, w, added, key))
    bad = 0
    for p, regs, wram, added, key in picked:
        before, ref, runs, stashed = race(rom, regs, wram, syms['WtQueue'], syms['WqNmi'])
        problems = judge(before, ref, runs, stashed)
        tag = (f'{p.parent.name}/{p.name} 프레임 {regs["frame"]} 입구 항목 {wram[WQ_COUNT]}{"(끼워 넣음)" if added else ""} '
               f'묶음 {"뺌" if key[1] else "안 뺌"}')
        if problems:
            bad += 1
            print(f'FAIL {tag}: 끼어들기 {len(runs)}곳, ' + '; '.join(problems[:4]))
        else:
            print(f'PASS {tag}: 끼어들기 {len(runs)}곳')
    for k in CLASSES:
        if not classes[k]:
            bad += 1
            print(f'FAIL 갈래 없음: 입구 항목 {k[0]}{"개 이상" if k[0] == 2 else "개"}, 묶음 {"뺌" if k[1] else "안 뺌"}')
    if bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
