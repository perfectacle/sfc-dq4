"""DQ5(SFC) 전투 연출 스크립트를 롬 코드 그대로 돌려 BG3 연출 층 프레임을 얻는다. 형식은
sfc/dq5/docs/dq5-graphics-format.md 의 「3E 루틴의 실측」·「롬 코드로 돌리기」.

해석기 22:D8FE 와 명령 3E 의 22 뱅크 루틴을 w65816.py 로 실행한다. 입력은 해석기를 부르기 직전(22:D790)의
WRAM 128KB 와 레지스터(lua/dq5fx3e.lua 의 VMDUMP=1 이 v<연출>.wram·.regs 로 남김)이고, 프레임 경계는
00:969A(NMI 기다림)다. 거기서 BG3 사본 7E:8A1D(14줄×32칸 워드)를 찍고 NMI 가 하던 일은 하지 않고 돌아온다.
결과를 같은 실행의 v<연출>.frames(게임이 00:969A 에서 찍은 사본)와 견준다.

--from-entry 는 연출 입구 22:D73C 부터 돈다. VMSCREENS=1 로 남긴 입구의 VRAM·CGRAM·OAM(v<연출>.vram0 등)을 넣으면
w65816 이 VRAM·CGRAM·OAM 쓰기와 일반 DMA 를 따라 해 프레임마다 연출 층 그림을 만든다(--screens 로 같은 실행의
e<연출>-<k>.* 와 견주고, --gif 로 저장). HDMA 는 흉내 내지 않으므로 줄마다 바뀌는 스크롤은 그림에 없다.

  uv run --locked python sfc/dq5/tools/dq5fxvm.py rom/dq5.sfc work/vm/h04 04        # 프레임마다 같음/다름
  uv run --locked python sfc/dq5/tools/dq5fxvm.py rom/dq5.sfc work/vm/h04 04 --inputs   # 해석기가 읽은 WRAM 중 쓰기 전에 읽은 곳
  uv run --locked python sfc/dq5/tools/dq5fxvm.py rom/dq5.sfc work/vm/h04 04 --from-entry --screens work/vm/h04 --gif work/vm/04.gif
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from w65816 import Cpu, Stop  # noqa: E402

BUF, BUF_LEN = 0x8A1D, 0x380
FRAME_WAIT = 0x00969A
INTERP = 0x22D8FE
ENTRY = 0x22D73C
INTERP_RET = 0x22D793
TRAILER = (0x19, 0x0F5E, 0x0F5F, 0x075B, 0x075C, 0x075D, 0x0DB0, 0x0DBC)  # 프레임 기록 뒤 8바이트
REC = BUF_LEN + len(TRAILER)


def load(folder, fx, entry=False):
    base = os.path.join(folder, f'v{fx:02X}')
    sfx = '0' if entry else ''
    wram = open(base + '.wram' + sfx, 'rb').read()
    a, x, y, s, d, dbr, p = open(base + '.regs' + sfx).read().split()
    frames = []
    if os.path.exists(base + '.frames'):
        raw = open(base + '.frames', 'rb').read()
        frames = [raw[i:i + REC] for i in range(0, len(raw), REC)]
    return wram, dict(a=int(a, 16), x=int(x, 16), y=int(y, 16), s=int(s, 16), d=int(d, 16), dbr=int(dbr, 16),
                      p=int(p, 16)), frames


def run(rom, wram, regs, max_frames=2000, track_inputs=False, nmi=True, entry=False, ppu=False, video=None,
        keep_wram=False, clock=False):
    """해석기를 끝(3F)까지 돌려 [00:969A 때의 BG3 사본 896바이트] 와 Cpu 를 돌려준다. video 는 시작 때의
    (VRAM, CGRAM, OAM). 없으면 0 에서 시작한다."""
    if clock:
        # 메모리 접근 주기를 세어 처리가 한 프레임을 넘기면 처리 도중 NMI 를 넣는다(dq5titlevm.Cpu, 연출도 240줄에서 NMI)
        import dq5titlevm
        c = dq5titlevm.Cpu(rom, wram)
        c.on_lag = lambda cpu: None
    else:
        c = Cpu(rom, wram, ppu=ppu)
    if ppu and video:
        c.vram[:], c.cgram[:], c.oam[:len(video[2])] = video[0], video[1], video[2]
        # VMAIN 은 전원을 켤 때 한 번 80(높은 바이트를 쓴 뒤 1 늘림)으로 두고 연출 안에서는 다시 쓰지 않는 곳이 있다
        c.reg[0x2115] = 0x80
    c.a, c.x, c.y, c.s, c.d, c.dbr = regs['a'], regs['x'], regs['y'], regs['s'], regs['d'], regs['dbr']
    c.setp(regs['p'])
    if track_inputs:
        c.wram_reads, c.wram_written = set(), set()
    frames = []

    c.screens = []

    def wait_nmi(cpu):
        # NMI 쪽 소리 처리가 효과음 대기열(7E:1D95, 머리 1D91·꼬리 1D93)을 비우는 것. 소리 칩과 주고받는 일이라
        # NMI 를 돌려도 흉내 나지 않는다. 24:FE44 가 대기열이 빌 때까지 기다리는 연출(イオ·ギガデイン)이 있다.
        cpu.wram[0x1D93] = cpu.wram[0x1D91]
        cpu.rts()
        if nmi and hasattr(cpu, 'nmi'):
            # 주기를 세는 해석기(dq5titlevm.Cpu): 기다림에서 셈을 0 으로 하고 NMI 를 넣는다
            cpu.cost = cpu.line = 0
            cpu.nmi()
        elif nmi:
            # 기다림이 끝나는 NMI 를 롬의 처리기 그대로 돌린다(RTI 로 부른 곳에 돌아옴). PPU 쪽은 w65816 이
            # 흉내 내는 CPU 쓰기와 일반 DMA 만 맞는다.
            cpu.push(cpu.pbr)
            cpu.push16(cpu.pc)
            cpu.push(cpu.p)
            cpu.p = (cpu.p | 0x04) & ~0x08
            cpu.pbr, cpu.pc = 0, rom[0x7FEA] | rom[0x7FEB] << 8
        else:
            # NMI 를 돌리지 않을 때: 난수 $075B 늘리기(00:8897)만
            cpu.wram[0x075B] = (cpu.wram[0x075B] + 1) & 0xFF
        return True

    c.wram_frames = []

    def frame_wait(cpu):
        frames.append(bytes(cpu.wram[BUF:BUF + BUF_LEN]) + bytes(cpu.wram[a] for a in TRAILER))
        if keep_wram:
            cpu.wram_frames.append(bytes(cpu.wram))
        if ppu:
            # 지금 화면은 앞 NMI 가 올린 VRAM·CGRAM·OAM 이다
            cpu.screens.append((bytes(cpu.vram), bytes(cpu.cgram), bytes(cpu.oam),
                                cpu.scroll.get(0x2111, 0), cpu.scroll.get(0x2112, 0)))
        if len(frames) >= max_frames:
            raise Stop('frame limit')
        return wait_nmi(cpu)

    c.hooks[FRAME_WAIT] = frame_wait
    if entry:
        # 22:D73C(A = 연출 번호)부터: 조각 목록·색을 롬에서 WRAM 으로 올리는 22:ABE8·BAFA 도 롬 코드로 돈다.
        # 프레임 기록은 해석기에 들어가서(22:D8FE) 돌아올 때(22:D793)까지만 센다.
        started = [False]

        def start(cpu):
            started[0] = True
            return False
        c.hooks[INTERP] = start

        def stop(cpu):
            started[0] = False
            return False
        c.hooks[INTERP_RET] = stop
        orig = frame_wait

        def gated(cpu):
            if not started[0]:
                return wait_nmi(cpu)
            return orig(cpu)
        c.hooks[FRAME_WAIT] = gated
        c.jsl(ENTRY, max_steps=20_000_000)
    else:
        c.jsr(INTERP, max_steps=20_000_000)
    return frames, c


def load_video(folder, fx):
    """lua/dq5fx3e.lua VMSCREENS=1 이 연출 입구에서 남긴 v<연출>.vram0·cgram0·oam0."""
    base = os.path.join(folder, f'v{fx:02X}')
    if not os.path.exists(base + '.vram0'):
        return None
    return tuple(open(base + s, 'rb').read() for s in ('.vram0', '.cgram0', '.oam0'))


def game_screens(folder, fx):
    """lua/dq5fxdump.lua 가 남긴 e<연출>-<k>.vram·cgram·oam·ppu 를 차례로."""
    out, k = [], 0
    while os.path.exists(os.path.join(folder, f'e{fx:02X}-{k:03d}.vram')):
        b = os.path.join(folder, f'e{fx:02X}-{k:03d}')
        h, v = (int(t) for t in open(b + '.ppu').read().split())
        out.append((open(b + '.vram', 'rb').read(), open(b + '.cgram', 'rb').read(), open(b + '.oam', 'rb').read(), h, v))
        k += 1
    return out


def vm_images(rom, folder, fx, clock=True):
    """연출 입구부터 롬 코드로 돌린 연출 층 그림(PIL RGBA) 목록. 다른 도구가 import 해서 쓴다."""
    from dq5fx import render_frame
    wram, regs, _ = load(folder, fx, entry=True)
    _, c = run(rom, wram, regs, entry=True, ppu=True, video=load_video(folder, fx), clock=clock)
    return [render_frame(*sc) for sc in c.screens]


def save_gif(images, path, ms=17):
    """연출 층 그림을 검은 바탕에 얹어 GIF 로(한 장 = 게임 한 프레임)."""
    from PIL import Image
    frames = []
    for im in images:
        bg = Image.new('RGBA', im.size, (0, 0, 0, 255))
        bg.alpha_composite(im)
        frames.append(bg.convert('RGB').convert('P', palette=Image.ADAPTIVE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0)


def compare_screens(vm, game):
    """연출 층 그림(dq5fx.render_frame)을 견준다. 게임 덤프는 프레임 끝마다라 VM 프레임 i 를 같은 차례 근처(±3)의
    게임 프레임과 맞춰 본다. (같은 그림 수, VM 프레임 수, 게임 덤프 수)."""
    from dq5fx import render_frame
    gi = [render_frame(*g).tobytes() for g in game]
    same = mem = 0
    for i, s in enumerate(vm):
        img = render_frame(*s).tobytes()
        if any(0 <= j < len(gi) and gi[j] == img for j in range(i - 3, i + 4)):
            same += 1
        if i < len(game) and s[:3] == game[i][:3]:
            mem += 1
    return same, len(vm), len(gi), mem


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('folder', help='lua/dq5fx3e.lua VMDUMP=1 의 SHOT_DIR')
    ap.add_argument('fx', help='연출 번호(16진)')
    ap.add_argument('--inputs', action='store_true', help='쓰기 전에 읽은 WRAM 주소 범위')
    ap.add_argument('--from-entry', action='store_true', help='22:D8FE 대신 연출 입구 22:D73C 부터(v<연출>.wram0)')
    ap.add_argument('--screens', help='lua/dq5fxdump.lua 덤프 폴더. --from-entry 로 VRAM·CGRAM·OAM 까지 흉내 내 연출 층 그림을 견줌')
    ap.add_argument('--png', help='VM 이 그린 연출 층을 이 폴더에 프레임마다 PNG 로')
    ap.add_argument('--gif', help='VM 이 그린 연출 층을 이 GIF 로(--from-entry 와 함께)')
    ap.add_argument('--clock', action='store_true', help='메모리 접근 주기를 세어 처리 도중 NMI 를 넣음(dq5titlevm.Cpu)')
    a = ap.parse_args()
    rom = open(a.rom, 'rb').read()
    fx = int(a.fx, 16)
    wram, regs, _ = load(a.folder, fx, entry=a.from_entry)
    game = load(a.folder, fx)[2]
    video = load_video(a.folder, fx) if a.from_entry else None
    frames, c = run(rom, wram, regs, track_inputs=a.inputs, entry=a.from_entry, ppu=bool(a.screens or a.png or a.gif),
                    video=video, clock=a.clock)
    same = sum(1 for i, f in enumerate(frames) if i < len(game) and f[:BUF_LEN] == game[i][:BUF_LEN])
    print(f'{fx:02X} frames vm {len(frames)} game {len(game)} same {same} steps {c.steps}')
    for i in range(max(len(frames), len(game))):
        f = frames[i][:BUF_LEN] if i < len(frames) else None
        g = game[i][:BUF_LEN] if i < len(game) else None
        if f != g:
            diff = sum(1 for k in range(0, BUF_LEN, 2) if f is None or g is None or f[k:k + 2] != g[k:k + 2])
            print(f'  first diff at frame {i}: {diff} cells')
            break
    if a.screens:
        same, nv, ng, mem = compare_screens(c.screens, game_screens(a.screens, fx))
        print(f'screens vm {nv} game {ng} same {same} vram-cgram-oam {mem}')
    if a.png:
        from dq5fx import render_frame
        os.makedirs(a.png, exist_ok=True)
        for i, sc in enumerate(c.screens):
            render_frame(*sc).save(os.path.join(a.png, f'{fx:02X}-{i:03d}.png'))
    if a.gif:
        from dq5fx import render_frame
        save_gif([render_frame(*sc) for sc in c.screens], a.gif)
    if a.inputs:
        ks = sorted(c.wram_reads)
        out, i = [], 0
        while i < len(ks):
            j = i
            while j + 1 < len(ks) and ks[j + 1] == ks[j] + 1:
                j += 1
            out.append(f'{ks[i]:05X}' if i == j else f'{ks[i]:05X}-{ks[j]:05X}')
            i = j + 1
        print('inputs', ','.join(out))


if __name__ == '__main__':
    main()
