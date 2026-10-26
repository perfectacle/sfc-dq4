"""DQ5(SFC) 오프닝 타이틀을 롬 코드로 돌려 프레임마다 그린다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의
「롬 코드로 그린 타이틀」.

입력은 타이틀 고리가 처음 프레임 기다림(00:969A)에 닿은 때의 WRAM·VRAM·CGRAM·OAM·PPU/DMA/CPU 상태 한 벌이다
(lua/dq5titlesnap.lua 가 snap.* 으로 남김). 그 뒤는 w65816.py 가 타이틀 고리와 NMI 처리기(00:885D)를 롬 코드 그대로
돌리고, dq5ppu.py 가 레지스터 쓰기와 HDMA 표로 화면을 그린다.

게임은 프레임 처리가 길면 처리 도중에 NMI 가 들어온다(지연 프레임). 이것을 맞추려고 메모리 접근마다 마스터 주기를 센다:
ROM·WRAM 8, I/O 레지스터 6($4000~$41FF 는 12), 명령마다 메모리에 닿지 않는 내부 주기 6씩(IO 표), MVN·MVP 는 한 바이트에
내부 주기 둘. 보이는 줄마다 HDMA 가 CPU 를 멈추는 주기(18 + 채널마다 8 + 바이트마다 8)도 더한다. 한 프레임은
1364 × 262 에서 줄마다 리프레시 40 을 뺀 값이다.

  uv run --locked python sfc/dq5/tools/dq5titlevm.py rom/dq5.sfc work/title/snap --check work/title/pd
  uv run --locked python sfc/dq5/tools/dq5titlevm.py rom/dq5.sfc work/title/snap --frames 1300 --gif work/title/vm.gif
  uv run --locked python sfc/dq5/tools/dq5titlevm.py rom/dq5.sfc --out $OUT

--out 은 dq5titlegif.py 와 같은 입력으로 MesenCE 를 전원부터 돌려 스냅숏만 뜨고, 그 뒤는 롬 코드로 돌려
gfx/screens/anim/title-opening-rom.gif 를 dq5titlegif.py 의 title-opening.gif 와 같은 규칙(2프레임마다, 검은 화면 사이,
같은 장은 한 장으로)으로 쓴다. 입력(40프레임마다 A)도 같은 프레임에 $4218 로 넣는다.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import dq5ppu  # noqa: E402
from w65816 import Cpu as _Cpu, Stop  # noqa: E402

FRAME_WAIT = 0x00969A
FRAME = 1364 * 262 - 40 * 262

# 명령마다 메모리에 닿지 않는 내부 주기 수(65C816 주기 표에서 고른 것)
IO = [0] * 256
for _o in (0x18, 0x38, 0x58, 0x78, 0xB8, 0xD8, 0xF8, 0xE8, 0xC8, 0xCA, 0x88, 0xAA, 0xA8, 0x8A, 0x98, 0x9A, 0xBA, 0x5B,
           0x7B, 0x1B, 0x3B, 0x9B, 0xBB, 0xEA, 0x0A, 0x2A, 0x4A, 0x6A, 0x1A, 0x3A, 0xFB, 0xC2, 0xE2,
           0x48, 0xDA, 0x5A, 0x08, 0x8B, 0x0B, 0x4B, 0x62, 0x20, 0xFC, 0x22, 0x7C, 0x00, 0x02):
    IO[_o] = 1
for _o in (0xEB, 0x68, 0xFA, 0x7A, 0x28, 0xAB, 0x2B, 0x6B, 0x40):
    IO[_o] = 2
IO[0x60] = 3
for _o in (0x15, 0x16, 0x35, 0x36, 0x55, 0x56, 0x75, 0x76, 0x95, 0x96, 0xB5, 0xB6, 0xD5, 0xD6, 0xF5, 0xF6, 0x94, 0xB4,
           0x34, 0x74, 0x01, 0x21, 0x41, 0x61, 0x81, 0xA1, 0xC1, 0xE1,                       # dp,X·(dp,X)
           0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E, 0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x76, 0x7E,
           0xE6, 0xEE, 0xF6, 0xFE, 0xC6, 0xCE, 0xD6, 0xDE, 0x04, 0x0C, 0x14, 0x1C,           # 읽고 고쳐 쓰기
           0x9D, 0x99, 0x9E, 0x91):                                                         # 색인 쓰기
    IO[_o] += 1
for _o in range(0x03, 0x100, 0x20):     # d,S 는 내부 주기 1, (d,S),Y 는 2
    IO[_o] += 1
    IO[_o + 0x10] += 2
BRANCH = (0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0, 0x80, 0x82)
IDX_READ = (0x1D, 0x19, 0x3D, 0x39, 0x5D, 0x59, 0x7D, 0x79, 0xBD, 0xB9, 0xDD, 0xD9, 0xFD, 0xF9, 0xBC, 0xBE,
            0x11, 0x31, 0x51, 0x71, 0xB1, 0xD1, 0xF1)   # 16비트 색인이면 내부 주기 하나 더


class Cpu(_Cpu):
    """w65816 에 WRAM 포트($2180~$2183), 주기 세기와 처리 도중 NMI, 조이패드($4218)를 더한 것."""

    def __init__(self, rom, wram, pad=None):
        super().__init__(rom, wram, ppu=True)
        self.wport = 0
        self.cost = 0
        self.line = 0
        self.in_nmi = False
        self.nframe = 0
        self.pad = pad            # 함수(NMI 수) → $4218·$4219 16비트
        self.on_lag = None        # 처리 도중 NMI 를 넣기 직전에 부름
        self._br = 0

    def _ppu_write(self, addr, v):
        if addr == 0x2180:
            self.wram[self.wport] = v
            self.wport = (self.wport + 1) & 0x1FFFF
        elif 0x2181 <= addr <= 0x2183:
            sh = (addr - 0x2181) * 8
            self.wport = (self.wport & ~(0xFF << sh) | v << sh) & 0x1FFFF
        else:
            super()._ppu_write(addr, v)

    @staticmethod
    def speed(a):
        bank, addr = (a >> 16) & 0xFF, a & 0xFFFF
        if (bank & 0x7F) < 0x40 and 0x2000 <= addr < 0x6000:
            return 12 if 0x4000 <= addr < 0x4200 else 6
        return 8

    def read(self, a):
        self.cost += self.speed(a)
        if self.pad and (a & 0xFFFF) in (0x4218, 0x4219) and ((a >> 16) & 0x7F) < 0x40:
            v = self.pad(self.nframe)
            return v & 0xFF if (a & 0xFFFF) == 0x4218 else v >> 8
        return super().read(a)

    def write(self, a, v):
        self.cost += self.speed(a)
        super().write(a, v)

    def nmi(self):
        self.nframe += 1
        self.push(self.pbr)
        self.push16(self.pc)
        self.push(self.p)
        self.p = (self.p | 0x04) & ~0x08
        self.pbr, self.pc = 0, self.rom[0x7FEA] | self.rom[0x7FEB] << 8
        self.in_nmi = True

    def hdma_lines(self):
        """보이는 줄(NMI 가 240줄에서 들어오므로 그 뒤 22줄을 뺀 240줄)마다 HDMA 가 CPU 를 멈추는 주기를 더한다:
        18 + 켠 채널마다 8 + 옮기는 바이트마다 8."""
        while self.line < self.cost // 1364:
            self.line += 1
            if (240 + self.line) % 262 >= 240:
                continue
            en, h = self.reg[0x420C], 0
            for ch in range(8):
                if en >> ch & 1:
                    h += 8 + 8 * (1, 2, 2, 4, 4, 4, 2, 4)[self.reg[0x4300 + ch * 16] & 7]
            if h:
                self.cost += 18 + h

    def step(self):
        op = _Cpu.read(self, (self.pbr << 16) | self.pc)
        io = 2 if op in (0x44, 0x54) else IO[op] + (op in IDX_READ and not self.x8)
        self.cost += io * 6
        if op == 0x40 and self.in_nmi:
            self.in_nmi = False
        self.hdma_lines()
        if self.cost >= FRAME and not self.in_nmi and self.on_lag:
            self.cost -= FRAME
            self.line -= 262
            self.on_lag(self)
            self.nmi()
            return
        if op in BRANCH:
            self._br = (self.pbr << 16) | self.pc
        super().step()
        if op in BRANCH and ((self.pbr << 16) | self.pc) != (self._br + (3 if op == 0x82 else 2)) & 0xFFFFFF:
            self.cost += 6


BUTTONS = {'b': 0x8000, 'y': 0x4000, 'select': 0x2000, 'start': 0x1000, 'up': 0x0800, 'down': 0x0400, 'left': 0x0200,
           'right': 0x0100, 'a': 0x0080, 'x': 0x0040, 'l': 0x0020, 'r': 0x0010}


def seq_pad(seq, first):
    """boot.lua 의 SEQ 항목(「a@331:4」 = 331프레임부터 4프레임)을 NMI 수 → $4218·$4219 함수로. first 는 스냅숏 프레임."""
    presses = []
    for tok in seq:
        b, rest = tok.split('@')
        f, n = rest.split(':')
        presses.append((int(f), int(f) + int(n), BUTTONS[b]))

    def pad(j):
        f = first + j
        v = 0
        for a, e, bit in presses:
            if a <= f < e:
                v |= bit
        return v
    return pad


def load_snapshot(prefix):
    st = dq5ppu.load_state(prefix + '.state.txt')
    mem = {k: open(f'{prefix}.{k}', 'rb').read() for k in ('wram', 'vram', 'cgram', 'oam')}
    return st, mem


def run(rom, prefix, nframes, pad=None):
    """스냅숏부터 nframes 프레임을 돌려 프레임마다 (PPU 상태 dict, WRAM, VRAM, CGRAM, OAM) 을 돌려준다.
    한 장은 NMI 하나(기다림 끝이든 처리 도중이든) 직전의 상태로, MesenCE 의 그다음 프레임 끝 덤프와 같다."""
    st, mem = load_snapshot(prefix)
    c = Cpu(rom, mem['wram'], pad)
    c.vram[:], c.cgram[:], c.oam[:] = mem['vram'], mem['cgram'], mem['oam']
    c.reg[0x2115] = 0x80
    c.a, c.x, c.y, c.s, c.d, c.dbr = (int(st['cpu.' + k]) for k in ('a', 'x', 'y', 'sp', 'd', 'dbr'))
    c.setp(int(st['cpu.ps']))
    c.pbr, c.pc = int(st['cpu.k']), int(st['cpu.pc'])
    P = {k: v for k, v in st.items() if k.startswith(('ppu.', 'dmaController.'))}
    latch, seen, out = [0], [0], []
    first = [True]

    def snap(cpu):
        dq5ppu.apply(P, cpu.io_writes[seen[0]:], latch)
        seen[0] = len(cpu.io_writes)
        out.append((dict(P), bytes(cpu.wram), bytes(cpu.vram), bytes(cpu.cgram), bytes(cpu.oam)))
        if len(out) >= nframes:
            raise Stop('frames')

    def wait(cpu):
        if first[0]:
            first[0] = False
        else:
            snap(cpu)
        cpu.wram[0x1D93] = cpu.wram[0x1D91]   # 효과음 대기열은 소리 칩이 비운 것으로 둔다
        cpu.rts()
        cpu.cost = 0
        cpu.line = 0
        cpu.nmi()
        return True

    c.hooks[FRAME_WAIT] = wait
    c.on_lag = lambda cpu: None if first[0] else snap(cpu)
    try:
        while True:
            c.step()
    except Stop:
        pass
    return out


def render(frame):
    P, w, v, cg, o = frame
    return dq5ppu.render(dq5ppu.state_from(P, v, cg, o, w))


def images(rom, prefix, nframes, pad=None):
    """프레임마다 RGB 배열. 다른 도구가 import 해서 쓴다."""
    return [render(f) for f in run(rom, prefix, nframes, pad)]


def boot_snapshot(rom_path, mesen, folder):
    """dq5titlegif.py 의 입력으로 전원부터 돌려 SNAP_FROM 뒤 스냅숏을 folder/snap.* 로. SEQ 를 돌려준다."""
    import dq5titlegif as T
    # 롬 이름(=SRAM 파일 이름)을 임시 폴더마다 다르게 해, 다른 체크아웃의 실행과 SRAM 을 함께 쓰지 않는다
    name = 'dq5titlevm-' + os.path.basename(folder.rstrip('/'))
    test = os.path.join(folder, name + '.sfc')
    shutil.copy(rom_path, test)
    srm = os.path.join(T.SAVES, name + '.srm')
    if os.path.exists(srm):
        os.remove(srm)
    lib = subprocess.run(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                         check=True).stdout.strip()
    seq = T.MENU + T.TAPS
    env = dict(os.environ, LIBDIR=lib, PERIOD='40', TAP='a', TAPUNTIL='205', SEQ=','.join(seq), EVERY='0', BOOT='1',
               FROM=str(SNAP_FROM), MAXN='3', MAXF='9000', SHOT_DIR=folder)
    subprocess.run([mesen, '--testrunner', test, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lua',
                    'dq5titlesnap.lua'), '--Snes.RamPowerOnState=AllZeros', '--Snes.DisableFrameSkipping=true'],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800, check=False)
    if os.path.exists(srm):
        os.remove(srm)
    return seq


SNAP_FROM, GIF_FROM, GIF_TO = 5562, 4800, 6800   # GIF_FROM·GIF_TO 는 dq5titlegif.py 의 FROM·TO


def export(rom_path, out_root, mesen, step=2):
    """dq5assets 용: title-opening-rom.gif 를 쓰고 같은 폴더 index.json 의 그 항목만 바꾼다."""
    from PIL import Image
    rom = open(rom_path, 'rb').read()
    tmp = tempfile.mkdtemp(prefix='dq5titlevm-')
    seq = boot_snapshot(rom_path, mesen, tmp)
    prefix = os.path.join(tmp, 'snap')
    frames = [int(x) for x in open(prefix + '.frames.txt').read().split()]
    first = frames[1] + 1
    out = run(rom, prefix, GIF_TO - first + 1, seq_pad(seq, frames[0]))
    shots = [(f, render(out[f - first])) for f in range(GIF_FROM, GIF_TO + 1, step) if f >= first]
    from PIL import ImageStat
    dark = [sum(ImageStat.Stat(Image.fromarray(im).convert('L')).mean) < 1.5 for _, im in shots]   # dq5titlegif.dark 와 같게
    start = next(i for i in range(1, len(shots)) if dark[i - 1] and not dark[i])
    end = next(i for i in range(start, len(shots)) if dark[i])
    pics, durs = [], []
    for _, im in shots[start:end]:
        if pics and np.array_equal(im, pics[-1]):
            durs[-1] += step
            continue
        pics.append(im)
        durs.append(step)
    rel = 'title-opening-rom.gif'
    folder = os.path.join(out_root, 'gfx', 'screens', 'anim')
    os.makedirs(folder, exist_ok=True)
    ims = [Image.fromarray(p) for p in pics]
    ims[0].save(os.path.join(folder, rel), save_all=True, append_images=ims[1:],
                duration=[round(d * 1000 / 60) for d in durs], loop=0)
    index = os.path.join(folder, 'index.json')
    items = json.load(open(index)) if os.path.exists(index) else []
    items = [it for it in items if it.get('path') != rel]
    items.append({'cat': 'screens', 'group': '타이틀', 'title': '오프닝 타이틀 연출 (롬 코드로 그린 GIF)', 'path': rel,
                  'w': ims[0].width, 'h': ims[0].height, 'frames': len(ims), 'start': shots[start][0],
                  'end': shots[end - 1][0],
                  'note': f'{SNAP_FROM}프레임 뒤 스냅숏 한 벌에서 롬 코드로 돌려 {step}프레임마다 그림(같은 장은 한 장으로)'})
    with open(index, 'w') as f:
        json.dump(items, f, ensure_ascii=False, indent=0)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f'{len(ims)}장 {shots[start][0]}~{shots[end - 1][0]} -> {os.path.join(folder, rel)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('snap', nargs='?', help='lua/dq5titlesnap.lua 가 남긴 스냅숏 앞부분(예: work/title/snap)')
    ap.add_argument('--out', help='dq5assets 용 출력 뿌리(gfx/screens/anim/title-opening-rom.gif)')
    ap.add_argument('--mesen', default=os.path.expandvars('$MESENCE'))
    ap.add_argument('--taps', action='store_true', help='dq5titlegif.py 의 입력(SEQ)을 같은 프레임에 넣음(BOOT 스냅숏)')
    ap.add_argument('--frames', type=int, default=1300)
    ap.add_argument('--check', help='같은 실행의 프레임 덤프 폴더(fNNNNN.raw, lua/dq5titlesnap.lua 의 DUMPFROM·DUMPTO)')
    ap.add_argument('--gif', help='STEP 프레임마다 GIF 로(같은 장은 한 장으로)')
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--compare-gif', nargs=2, metavar=('GIF', 'FIRST'),
                    help='GIF(dq5titlegif.py 결과)의 장마다 같은 프레임과 견줌. FIRST 는 첫 장의 프레임 번호')
    a = ap.parse_args()
    if a.out:
        export(a.rom, a.out, a.mesen, a.step)
        return
    rom = open(a.rom, 'rb').read()
    frames = [int(x) for x in open(a.snap + '.frames.txt').read().split()]
    pad = None
    if a.taps:
        import dq5titlegif as T
        pad = seq_pad(T.MENU + T.TAPS, frames[0])
    out = run(rom, a.snap, a.frames, pad)
    first = frames[1] + 1     # out[0] 은 이 프레임 끝의 덤프와 같다
    print(f'{len(out)} 프레임, {first}~{first + len(out) - 1}')
    if a.check:
        bad, n = [], 0
        for k, fr in enumerate(out):
            p = os.path.join(a.check, f'f{first + k:05d}.raw')
            if not os.path.exists(p):
                continue
            raw = np.frombuffer(open(p, 'rb').read(), np.uint8).reshape(239, 256, 4)[:, :, [2, 1, 0]]
            d = int((render(fr) != raw).any(axis=2).sum())
            n += 1
            if d:
                bad.append((first + k, d))
        print(f'덤프와 견준 프레임 {n}, 다른 프레임 {len(bad)}', bad[:20])
    if a.compare_gif:
        from PIL import Image, ImageSequence
        t, bad, n = int(a.compare_gif[1]), [], 0
        for im in ImageSequence.Iterator(Image.open(a.compare_gif[0])):
            k = t - first
            if 0 <= k < len(out):
                n += 1
                d = int((render(out[k]) != np.array(im.convert('RGB'))).any(axis=2).sum())
                if d:
                    bad.append((t, d))
            t += round(im.info['duration'] * 60 / 1000)
        print(f'GIF 와 견준 장 {n}, 다른 장 {len(bad)}', bad[:20])
    if a.gif:
        from PIL import Image
        pics, durs = [], []
        for k in range(0, len(out), a.step):
            img = render(out[k])
            if pics and np.array_equal(img, pics[-1]):
                durs[-1] += a.step
                continue
            pics.append(img)
            durs.append(a.step)
        ims = [Image.fromarray(p) for p in pics]
        ims[0].save(a.gif, save_all=True, append_images=ims[1:], duration=[round(d * 1000 / 60) for d in durs], loop=0)
        print(f'{len(ims)}장 -> {a.gif}')


if __name__ == '__main__':
    main()
