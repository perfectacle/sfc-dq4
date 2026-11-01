"""호환성 검사(COMPAT-01·02): MesenCE 밖의 에뮬레이터에서도 1장을 끝까지 걸을 수 있는지 본다.

  walk  : dq4ch1walkcheck.SEGMENTS(서장 → 1장 끝 리셋)를 libretro 코어(bsnes·snes9x) 하나에서 끊지 않고 이어 걷는다.
          코어는 dq4cores.py 가 고정 커밋에서 빌드한 것(원래 체크아웃 work/cores/)을 쓰고, LIBRETRO_BSNES·LIBRETRO_SNES9X
          가 있으면 그 파일을 쓴다(코어 바이너리는 저장소에 두지 않음).
  probe : MesenCE 1장 걷기 검사에 lua/dq4openbus.lua 를 붙여, 뱅크 40~7D 아래 절반(열린 버스·롬 거울) 접근과
          뱅크 40 이상 코드가 부른 BRK 를 기록한다. SRAM(뱅크 70~7D)을 낮은 뱅크 코드가 쓰는 것 말고 접근이 있거나,
          dq4brkscan.ALLOWED 밖의 BRK 가 불리면 실패. MESENCE·LIBDIR 필요.

MesenCE 판(dq4ch1walkcheck)과 다른 점: 세이브스테이트 대신 한 실행에서 이어 걷고, 보스 패치를 보스 구간만이 아니라
처음부터 롬에 쓰고, 워프의 롬 쓰기는 cheat, 한 번 쓰는 WRAM 은 poke(bsnes 는 상태를 고쳐 다시 불러옴), 메시지 번호는
보지 않고, 끝(리셋)은 실행 추적 대신 어두운 끝 화면 뒤 타이틀이 다시 뜨는지(밝기)와 소리로 본다.

  python sfc/dq4/tools/dq4cores.py && python sfc/dq4/tools/dq4compatcheck.py walk --rom work/ch1/dq4-ch1-full.sfc --out work/compat
  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4compatcheck.py probe --rom work/ch1/dq4-ch1-full.sfc --out work/compat-probe
형식은 sfc/dq4/docs/dq4-compat-format.md.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4brkscan  # noqa: E402
import dq4cores  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402
from dq4libretro import Core, write_wav  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402

CORES = {'bsnes': 'LIBRETRO_BSNES', 'snes9x': 'LIBRETRO_SNES9X'}
TRIGGER_RECORD = 0x155812        # dq5warp.lua 가 덮는 트리거 레코드(파일 위치)
TRIGGER_LIST = 0x7E183A          # 지금 맵의 트리거 목록 포인터·개수
BIG_BD = 0x157769                # 맵 번호가 1F 를 넘을 때 덮는 자리
ENTRANCE, ARRIVALS = 0x27E83, 0x7EA97
TITLE_BRIGHT = 60                # 끝 상자·메뉴는 어둡고 타이틀(하늘 그림)은 밝다
DARK = 20                        # 끝맺음 서술·끝 상자의 검은 화면
WALK_HOLD, STUCK = 90, 90        # walk.lua 와 같음


def cpu(off):
    return (off // 0x8000) << 16 | 0x8000 | off % 0x8000


def rom_codes(off, data):
    return [f'{cpu(off + i):06X}{b:02X}' for i, b in enumerate(data)]


def sets(s):
    """dq5warp.lua SET 꼴(`075B=00;…`, 7E 뱅크 하위 16비트) → [(주소, 값)]."""
    return [(0x7E0000 | int(a, 16), int(v, 16)) for a, v in re.findall(r'(\w+)=(\w+)', s or '')]


def reset_seen(bright):
    """끝 구간 화면 밝기(30프레임마다)에서, 어두운 화면(서술·끝 상자) 뒤에 밝은 타이틀이 다시 떴는지.
    성 앞은 밝으므로 밝은 화면만으로는 리셋을 알 수 없다."""
    dark = next((i for i, b in enumerate(bright) if b < DARK), None)
    return dark is not None and any(b >= TITLE_BRIGHT for b in bright[dark:])


def tokens(s):
    out = []
    for tok in filter(None, (s or '').split(';')):
        m = re.fullmatch(r'(\d+),(\d+)', tok)
        out.append((int(m[1]), int(m[2])) if m else (tok.split(':')[0], int(tok.split(':')[1])))
    return out


class Walker:
    """한 코어에서 구간을 차례로 걷는다."""

    def __init__(self, core_path, rom_in, out):
        self.out = out
        data = bytearray(Path(rom_in).read_bytes())
        # 조우를 끄고 보스를 약하게(MesenCE 판은 보스 패치를 보스 구간에만 둠. 다른 구간에서 그 몬스터를 만나지 않음)
        for tok in (wc.NO_ENCOUNTERS + ';' + wc.boss_patch(bytes(data))).split(';'):
            off, hexs = tok.split('=')
            data[int(off, 16):int(off, 16) + len(hexs) // 2] = bytes.fromhex(hexs)
        self.rom = out / 'c.sfc'
        self.rom.write_bytes(bytes(data))
        self.warp_exit = warp_exit(self.rom)
        self.c = Core(str(core_path), str(self.rom), str(out))
        self.audio, self.rms = [], []
        self.pokes, self.rom_cheats, self.cheat_key = [], {}, None

    def rd(self, a):
        return self.c.rd(a)

    def apply(self):
        """구간 POKE 는 매 프레임(snes9x 는 직접, bsnes 는 cheat), 롬 쓰기는 cheat."""
        direct = self.c.direct
        if direct and self.pokes:
            self.c.poke(self.pokes)
        codes = [x for cs in self.rom_cheats.values() for x in cs]
        if not direct:
            codes += [f'{a:06X}{v:02X}' for a, v in self.pokes]
        if tuple(codes) != self.cheat_key:
            self.c.set_cheats(codes)
            self.cheat_key = tuple(codes)
            if not direct and self.pokes:
                # bsnes 는 cheat 를 다시 걸 때 앞 값을 되돌리므로 묶는 값을 바로 다시 쓴다
                self.c.poke(self.pokes)

    def step(self, buttons=()):
        self.c.run(buttons)
        if self.c.n % 60 == 0:
            a = self.c.take_audio()
            self.rms.append(int(np.sqrt((a.astype(float) ** 2).mean())) if a.size else 0)
            self.audio.append(a)
        self.apply()

    def boot(self):
        """서장 검사와 같은 부팅 입력으로 START_AT 프레임까지."""
        ys = [(f, 2) for f in range(900, 1600, 150)]
        held = set()
        for n in range(1, pc.START_AT + 1):
            self.step(held)
            held = ({'y'} if any(f <= n < f + ln for f, ln in ys) else
                    {'a'} if n < pc.TAP_UNTIL and n % 40 < 4 else set())

    def walk(self, arg, opt):
        pre, pts = tokens(pc.CLOSE), tokens(arg)
        maxf = opt.get('maxf', wc.frames(arg))
        want, after = opt.get('changes', 99), opt.get('after', 120)
        pi = wi = stuck = changes = n = 0
        left = press = cur = last = last_change = None
        maps, buttons = [], set()
        while True:
            self.step(buttons)
            n += 1
            buttons = set()
            here = (self.rd(0x7E00BC), self.rd(0x7E00BD))
            x, y = self.rd(0x7E3020), self.rd(0x7E3080)
            cur = cur or here
            if here != cur:
                changes, last_change, cur = changes + 1, n, here
                maps.append('%02X/%02X' % here)
            if pi < len(pre):
                b, f = pre[pi]
                left = f if left is None else left
                buttons = set() if b == 'wait' else {b}
                left -= 1
                if left <= 0:
                    pi, left = pi + 1, None
            elif last_change is not None and n < last_change + WALK_HOLD:
                pass
            elif wi < len(pts):
                p = pts[wi]
                if isinstance(p[0], str):
                    press = p[1] if press is None else press
                    buttons = set() if p[0] == 'wait' else {p[0]}
                    press -= 1
                    if press <= 0:
                        press, wi = None, wi + 1
                elif (x, y) == p:
                    wi, stuck = wi + 1, 0
                else:
                    stuck = stuck + 1 if (x, y) == last else 0
                    last = (x, y)
                    if stuck > STUCK:
                        wi, stuck = wi + 1, 0
                    buttons = {'right' if x < p[0] else 'left' if x > p[0] else 'down' if y < p[1] else 'up'}
            if (last_change is not None and changes >= want and n >= last_change + after) or n >= maxf:
                return maps or ['%02X/%02X' % here]

    def warp(self, arg, late=()):
        """dq5warp.lua 의 「어디서나」(ANYWHERE=1, SETTLE 120): 발밑에 트리거를 깔고 밟는다."""
        m = re.fullmatch(r'(\w+)/(\w+),(\d+),(\d+),?(\d*)', arg)
        bc, bd, tx, ty = int(m[1], 16), int(m[2], 16), int(m[3]), int(m[4])
        d = int(m[5]) if m[5] else 1
        self.rom_cheats = {'exit': rom_codes(self.warp_exit, (0xE0 | bd, tx, ty, d, bc))}
        if bd > 0x1F:
            self.rom_cheats['bd'] = rom_codes(BIG_BD, (0xA9, bd))

        def lay(x, y):
            if self.rd(0x7E00BE) & 0x80 == 0:
                world = self.rd(0x7E1949)
                fx = self.rd(0x7E00B6) | self.rd(0x7E00B7) << 8
                fy = (self.rd(0x7E00B8) | self.rd(0x7E00B9) << 8) + (y - self.rd(0x7E3080))
                self.rom_cheats['ent1'] = rom_codes(ENTRANCE, (bc, fx & 255, fx >> 8, fy & 255, fy >> 8))
                self.rom_cheats['ent2'] = rom_codes(ARRIVALS + bc * 5, (((world + 1) << 5) | (bd & 0x1F), tx, ty, d, 0))
            else:
                self.rom_cheats['trigger'] = rom_codes(TRIGGER_RECORD, (x, y, x + 1, y + 1, 0x01, 0xC0, bc, bd, tx, ty, d, 0x01))
                self.c.poke([(TRIGGER_LIST, 0x12), (TRIGGER_LIST + 1, 0xD8), (TRIGGER_LIST + 2, 0x2A), (TRIGGER_LIST + 3, 0x01)])
            self.apply()

        self.step()
        start, gmap = self.c.n, self.rd(0x7E00BC) << 8 | self.rd(0x7E00BD)
        laid = tried = arrived = None
        phase, buttons = 'any', set()
        for _ in range(1500):
            self.step(buttons)
            n, buttons = self.c.n, set()
            x, y = self.rd(0x7E3020), self.rd(0x7E3080)
            here = self.rd(0x7E00BC) << 8 | self.rd(0x7E00BD)
            indoor = self.rd(0x7E00BE) & 0x80
            if phase == 'any':
                if laid and here == bc << 8 | bd and indoor and (here != gmap or (x, y) == (tx, ty)):
                    phase, arrived = 'load', n
                elif n < start + 20 or (laid and here != gmap):
                    pass
                elif not laid:
                    lay(x, y + 1)
                    laid, tried = True, n
                elif n < tried + 40:
                    buttons = {'down'}
                elif n < tried + 41:
                    lay(x, y)
                elif n < tried + 50:
                    buttons = {'up'}
                elif n < tried + 100:
                    buttons = {'down'}
            elif phase == 'load' and n >= arrived + 90:
                # 걷기 검사와 같이 도착해 조작이 풀린 뒤 난수·시각을 다시 둔다(LATESET)
                self.c.poke(late)
                phase, arrived = 'settle', n
            elif phase == 'settle' and n >= arrived + 120:
                break
        # MesenCE 판은 구간마다 롬을 새로 읽으므로 워프 패치는 그 구간에만
        self.rom_cheats = {}
        self.apply()
        return ['%02X/%02X' % (self.rd(0x7E00BC), self.rd(0x7E00BD))]

    def check(self, name, opt, maps):
        flags = {k: bool(self.rd(a) & mask) for k, (a, mask) in wc.FLAGS.items()}
        items = [self.rd(wc.ITEMS + i) for i in range(12)]
        problems = []
        if 'map' in opt and maps[-1] != opt['map']:
            problems.append(f'끝 맵 {maps[-1]}, 기대 {opt["map"]}')
        problems += [f'깃발 {k} 꺼짐' for k in opt.get('want', []) if not flags[k]]
        problems += [f'깃발 {k} 켜짐' for k in opt.get('off', []) if flags[k]]
        if 'field' in opt and bool(self.rd(0x7E00BE) & 0x80) == opt['field']:
            problems.append('필드가 아님' if opt['field'] else '필드에 있음')
        problems += [f'물건 {w:02X} 없음' for w in opt.get('items', []) if w not in items]
        return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'maps': maps,
                'flags': [k for k, v in flags.items() if v], 'frame': self.c.n}

    def ending(self):
        """끝 서술 둘을 넘기고 끝 상자에서 누른 뒤(ENDING_PRE) 리셋되어 타이틀이 다시 뜨고 소리가 나는지."""
        self.c.poke(sets(wc.RNG))
        bright = []
        k = 0
        start = len(self.rms)
        for b, f in (tok.split(':') for tok in wc.ENDING_PRE.split(',')):
            for _ in range(int(f)):
                self.step(set() if b == 'wait' else {b})
                k += 1
                if k % 30 == 0:
                    bright.append(int(self.c.frame.mean()))
        for k in range(1500):
            self.step()
            if k % 30 == 29:
                bright.append(int(self.c.frame.mean()))
        self.c.shot(self.out / 'ending.png')
        problems = []
        if not reset_seen(bright):
            problems.append('어두운 끝 화면 뒤 타이틀이 다시 뜨지 않음')
        if max(self.rms[start:][-10:] or [0]) < 100:
            problems.append('리셋 뒤 소리가 없음')
        return {'name': 'ending', 'status': 'failed' if problems else 'passed', 'problems': problems,
                'bright': bright, 'frame': self.c.n}

    def run(self):
        t0 = time.time()
        self.boot()
        results = []
        for i, (name, how, arg, opt) in enumerate(wc.SEGMENTS):
            self.pokes = [(int(a, 16), int(v, 16)) for a, v in re.findall(r'(\w+)=(\w+)', opt.get('poke', ''))]
            if how == 'ending':
                r = self.ending()
            else:
                # 걷기 검사와 같이 구간을 시작할 때 난수·시각을 한 번 정한 값으로 둔다
                self.c.poke(sets(wc.pins(opt)))
                maps = self.warp(arg, sets(wc.pins(opt))) if how == 'warp' else self.walk(arg, opt)
                r = self.check(name, opt, maps)
            self.c.shot(self.out / f'{i:02d}-{name}.png')
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            if r['status'] != 'passed':
                break
        if self.audio:
            write_wav(self.out / 'audio.wav', np.concatenate(self.audio), self.c.rate)
        ok = len(results) == len(wc.SEGMENTS) and all(r['status'] == 'passed' for r in results)
        return {'core': self.c.name, 'status': 'passed' if ok else 'failed', 'segments': results,
                'frames': self.c.n, 'seconds': round(time.time() - t0, 1)}


def probe_problems(lines):
    """dq4openbus.lua 기록에서 문제를 고른다. 낮은 뱅크 코드의 SRAM(70~7D) 접근은 원래 DQ5 저장이라 괜찮다."""
    problems = []
    for line in lines:
        m = re.fullmatch(r'([RW]) pc=(\w\w):(\w{4}) bank=(\w\w)', line)
        if m:
            pc_bank, bank = int(m[2], 16), int(m[4], 16)
            if not (bank >= 0x70 and pc_bank < 0x40):
                problems.append(f'{m[2]}:{m[3]} 이 {m[4]}:0000~7FFF 를 {"읽음" if m[1] == "R" else "씀"}')
            continue
        m = re.fullmatch(r'BRK pc=(\w\w:\w{4}) op=(\w\w)', line)
        if m and int(m[2], 16) not in dq4brkscan.ALLOWED:
            problems.append(f'{m[1]} 이 BRK {m[2]} 를 부름(dq4brkscan.ALLOWED 밖)')
    return problems


def probe(rom, out):
    import dq4mesen
    lua = HERE / 'lua' / 'dq4openbus.lua'
    log = out / 'openbus.txt'
    orig = dq4mesen.run

    def wrapped(mesence, rom_, script, *a, **kw):
        env = dict(kw.get('env') or os.environ)
        env.update(PROBE_TARGET=str(script), OPENBUS_LOG=str(log))
        kw['env'] = env
        return orig(mesence, rom_, lua, *a, **kw)

    dq4mesen.run = wrapped
    old_argv = sys.argv
    sys.argv = ['dq4ch1walkcheck', '--rom', str(rom), '--out', str(out / 'walk')]
    try:
        walked = wc.main() == 0
    finally:
        sys.argv, dq4mesen.run = old_argv, orig
    lines = log.read_text(encoding='utf-8').splitlines() if log.exists() else []
    problems = ([] if walked else ['1장 걷기 검사 실패(walk/results.json)']) + probe_problems(lines)
    brks = sorted({line.split('op=')[1] for line in lines if line.startswith('BRK')})
    return {'status': 'failed' if problems else 'passed', 'problems': problems, 'high_bank_brk': brks,
            'records': len(lines)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('walk', 'probe'))
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--core', choices=('all', *CORES), default='all')
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom_sha = __import__('hashlib').sha1(args.rom.read_bytes()).hexdigest()
    if args.mode == 'probe':
        report = {'rom_sha1': rom_sha, **probe(args.rom.resolve(), out)}
    else:
        report = {'rom_sha1': rom_sha, 'cores': {}}
        for name in (CORES if args.core == 'all' else [args.core]):
            path = dq4cores.core_path(name)
            if not path.exists():
                raise SystemExit(f'{path} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드하거나 {CORES[name]} 로 코어 파일을 줌')
            (out / name).mkdir()
            report['cores'][name] = {**Walker(path, args.rom.resolve(), out / name).run(),
                                     'core_sha256': dq4cores.sha256(path),
                                     # 환경 변수로 다른 파일을 주면 빌드 기록은 그 파일의 것이 아니다
                                     'core_build': (dq4cores.stamp(name) if path == dq4cores.core_path(name, dq4cores.cores_dir())
                                                    and not os.environ.get(dq4cores.ENV[name]) else None)}
        report['status'] = 'passed' if all(r['status'] == 'passed' for r in report['cores'].values()) else 'failed'
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    summary = ({k: f'{v["status"]} {sum(s["status"] == "passed" for s in v["segments"])}/{len(wc.SEGMENTS)}'
                for k, v in report.get('cores', {}).items()} or {'problems': report.get('problems')})
    print(json.dumps({'status': report['status'], 'rom_sha1': rom_sha, **summary}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
