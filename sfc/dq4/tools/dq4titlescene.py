"""타이틀 → 이름 입력 → 새 게임 → 서장 첫머리, 이어 하기 메뉴를 배포 롬(dq4-ch1-full.sfc) 그대로 libretro bsnes·snes9x
에서 기계적으로 본다. lua/dq4titleintegrationcheck.lua·dq4titlecheck.lua(관찰만)와 dq4nameentrycheck(MesenCE, 커서를
WRAM 으로 옮김)를 실제 패드 입력과 판정으로 잇는다. 형식은 sfc/dq4/docs/dq4-name-entry-format.md 「타이틀부터 새 게임까지」.

새 게임(저장 기록 없음):
  1. 전원 → 서곡: 지금 곡 $1D8B 가 OVERTURE 가 되고 DSP 목소리 0~5 가 울리고 소리(RMS)가 나며, 화면 평균 밝기가
     TITLE_BRIGHT 이상(하늘 그림)이 된다.
  2. Start → 메뉴(7E:1BB0 = A5) → A 로 「모험의 서를 만든다」. 기록이 없으면 칸 목록 없이 이름 입력(7F:F072 = 1).
  3. 이름 입력: KEYS 를 실제 방향·A·B 로 넣는다. 커서($0AD7)는 dq4nameentry.navigation 표로 길을 찾아 한 칸마다
     예상과 같은지, 글자를 넣을 때마다 확정 글자 수(7F:F000)·글리프(7F:F002~)·조합 칸 수(7F:F00A)가 NameModel 과 같은지
     본다. 네 글자가 찬 뒤 새 글자를 여는 자모는 받지 않고 대기열에 거절음(인자 33, X 02)이 들어간다.
  4. Y → 이름 확정 → A 로 서장 시작: 맵 3C/01, 곡 SILENT(서장 무음 곡), 7E:2001~2008 이 이름 부호, SRAM 첫 칸이
     기록되고 그 칸은 dq4savefixture 밑판(같은 입력, 이름 ㅂㅂㅂㅂ)과 이름 8바이트·체크섬만 다르다.
이어 하기(저장 기록 있음):
  5. 4 의 SRAM 을 넣고 전원 → Start → A·A 로 칸 목록을 거쳐 서장 저장 자리(25:8621 의 그룹 3C 항목)에 서고,
     7E:2001~ 이 저장한 이름이다.

  python sfc/dq4/tools/dq4cores.py && python sfc/dq4/tools/dq4titlescene.py --rom work/ch1/dq4-ch1-full.sfc --out work/titlescene
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4nameentry as ne  # noqa: E402

OVERTURE, MENU_SONG, SILENT = 0x10, 0x23, 0x4A
SONG_NOW = 0x7E1D8B
MENU_FLAG, MENU_ON = 0x7E1BB0, 0xA5
NE_ACTIVE, NE_N, NE_CH, NE_SP = 0x7FF072, 0x7FF000, 0x7FF002, 0x7FF00A
CURSOR = 0x7E0AD7
NAME = 0x7E2001
MAP = (0x7E00BC, 0x7E00BD)
PROLOGUE_MAP = (0x3C, 0x01)
TITLE_BRIGHT = 60                     # dq4compatcheck.TITLE_BRIGHT: 타이틀 하늘 그림은 밝다
Q_WRITE, Q_ARG, Q_X = 0x7E1D91, 0x7E1DA5, 0x7E1DB5
REJECT = (0x33, 0x02)                 # 이름 칸이 찼을 때의 거절음(서장 수련 검사의 새 게임 입력에서 실측)
HOLD, GAP = 4, 12                     # 누르는 프레임, 뗀 뒤 기다리는 프레임
# 라이안 → B 로 한 자모 지움 → ㄴ → 다·달 → ㅏ(다섯째 글자라 거절) → 「지우기」 칸 → Y 로 확정
BACK_KEY, ERASE_CELL = '<', '⌫'
KEYS = list('ㄹㅏㅇㅣㅇㅏㄴ') + [BACK_KEY] + list('ㄴㄷㅏㄹㅏ') + [ERASE_CELL]
DIRS = ('up', 'down', 'left', 'right')


class NameModel:
    """조합 규칙은 dq4nameentry.compose 와 같고, 지우기(B·「지우기」)는 조합 칸을 하나 되돌리거나 없으면 확정 글자를 지운다
    (dq4nameentry.asm NeBack, 형식 문서 「자모판과 이름 칸」)."""

    def __init__(self):
        self.chars, self.stack = [], []

    def text(self):
        out = list(self.chars) + ([self.code(self.stack[-1])] if self.stack else [])
        return ''.join(ne.GLYPHS[g] for g in out)

    @staticmethod
    def code(state):
        c, v, j = state
        if v is None:
            return ne.JAMO.index(ne.CHO[c])
        if c is None:
            return ne.JAMO.index(ne.JUNG[v])
        ch = chr(0xAC00 + (c * 21 + v) * 28 + j)
        return len(ne.JAMO) + ne.KS.index(ch) if ch in ne.KS else None

    def back(self):
        if self.stack:
            self.stack.pop()
        elif self.chars:
            self.chars.pop()

    def press(self, jamo):
        """자모 하나. 받으면 True(거절: 조합이 안 되거나 다섯째 글자를 열 때)."""
        saved = (list(self.chars), list(self.stack))
        ok = self._jamo(jamo) and len(self.chars) + (1 if self.stack else 0) <= ne.MAX_CHARS
        if not ok:
            self.chars[:], self.stack[:] = saved
        return ok

    def _push(self, state):
        if self.code(state) is None:
            return False
        self.stack.append(state)
        return True

    def _commit(self):
        if self.stack:
            self.chars.append(self.code(self.stack[-1]))
            self.stack.clear()

    def _start(self, jamo):
        return self._push((ne.CHO.index(jamo), None, 0) if jamo in ne.CHO else (None, ne.JUNG.index(jamo), 0))

    def _jamo(self, jamo):
        if not self.stack:
            return self._start(jamo)
        c, v, j = self.stack[-1]
        if jamo not in ne.JUNG:
            if v is None or c is None:
                self._commit()
                return self._start(jamo)
            if j:
                mix = ne.JONG_MIX.get((ne.JONG[j], jamo))
                if mix and self._push((c, v, ne.JONG.index(mix))):
                    return True
            elif jamo in ne.JONG and self._push((c, v, ne.JONG.index(jamo))):
                return True
            self._commit()
            return self._start(jamo)
        if v is None:
            return self._push((c, ne.JUNG.index(jamo), 0))
        if not j:
            mix = ne.JUNG_MIX.get((ne.JUNG[v], jamo))
            if mix:
                return self._push((c, ne.JUNG.index(mix), 0))
            self._commit()
            return self._start(jamo)
        pair = next((k for k, x in ne.JONG_MIX.items() if x == ne.JONG[j]), None)
        stay = ne.JONG.index(pair[0]) if pair else 0
        moved = ne.CHO.index(pair[1] if pair else ne.JONG[j])
        if self.code((c, v, stay)) is None or self.code((moved, ne.JUNG.index(jamo), 0)) is None:
            return False
        self.chars.append(self.code((c, v, stay)))
        self.stack.clear()
        self.stack.append((moved, None, 0))
        self.stack.append((moved, ne.JUNG.index(jamo), 0))
        return True


def board_keys():
    """자모판 칸마다 키(dq4nameentry.board_record 와 같은 차례: 줄마다 ROW_CELLS 칸, 빈 칸 NONE)."""
    out = []
    for row in ne.GRID:
        for cell in row + [None] * (ne.ROW_CELLS - len(row)):
            out.append(ne.NONE if cell is None else cell if cell in (ne.BACK, ne.DONE) else ne.JAMO.index(cell))
    return out


def route(nav, start, goal):
    """이웃 표(navigation: 위·아래·왼쪽·오른쪽 순으로 칸 수만큼씩)에서 start → goal 의 [(방향, 다음 칸)] 최단 길."""
    n = len(nav) // 4
    prev, todo = {start: None}, [start]
    while todo:
        here = todo.pop(0)
        if here == goal:
            break
        for k, d in enumerate(DIRS):
            nxt = nav[k * n + here]
            if nxt not in prev:
                prev[nxt] = (here, d)
                todo.append(nxt)
    if goal not in prev:
        raise ValueError(f'칸 {goal} 에 닿지 못함')
    path, at = [], goal
    while prev[at]:
        here, d = prev[at]
        path.append((d, at))
        at = here
    return path[::-1]


def name_bytes(text):
    return b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in text).ljust(8, b'\x01')


def slot_diff(a, b):
    """기록 칸 둘의 다른 오프셋(칸 안)."""
    return [i for i in range(min(len(a), len(b))) if a[i] != b[i]]


# ---- 실행 -----------------------------------------------------------------------------------------------------------

class Runner:
    """한 코어를 프레임마다 돌리며 소리·밝기·대기열 인자를 적는다."""

    def __init__(self, core, rom=None):
        self.c = core
        self.rom = rom
        self.rms, self.bright, self.events, self.notes = [], [], [], []
        self.voices = []
        self.last_q = None

    def rd(self, a, n=1):
        return self.c.rd(a, n)

    def step(self, buttons=()):
        self.c.run(set(buttons))
        q = self.rd(Q_WRITE)
        if self.last_q is not None and q != self.last_q:
            i = self.last_q
            while i != q:
                self.events.append((self.c.n, self.rd(Q_ARG + i), self.rd(Q_X + i)))
                i = (i + 1) % 16
        self.last_q = q
        if self.c.n % 10 == 0:
            self.bright.append((self.c.n, float(self.c.frame.mean()) if self.c.frame is not None else 0.0))
        if self.c.n % 30 == 0:
            a = self.c.take_audio()
            self.rms.append((self.c.n, float(np.sqrt((a.astype(float) ** 2).mean())) if a.size else 0.0))

    def wait(self, n):
        for _ in range(n):
            self.step()

    def until(self, pred, limit, press=None, every=40):
        """pred() 가 참이 될 때까지(limit 프레임). press 가 있으면 every 프레임마다 HOLD 프레임 누른다."""
        start = self.c.n
        while self.c.n - start < limit:
            if pred():
                return self.c.n
            held = press and (self.c.n - start) % every < HOLD
            self.step({press} if held else ())
        return self.c.n if pred() else None

    def tap(self, button):
        for _ in range(HOLD):
            self.step({button})
        self.wait(GAP)


def envx(r):
    from dq4sfxscene import spc_state
    got = spc_state(r.c)
    return tuple(got[0][v * 16 + 8] for v in range(8)) if got else (0,) * 8


NAME_VRAM = ((0x4F80, 0x5000), (0x5F80, 0x6000))   # 이름 칸 위·아래 타일(dq4nameentrycheck 와 같은 자리)


def name_tiles(r, rom, text):
    """화면 이름 칸 타일이 롬 글꼴로 그린 text 와 같은지. snes9x 는 VRAM 을 API 로 읽고, bsnes(VRAM API 없음)는
    직렬화 상태 안에서 위·아래 타일 줄을 찾는다. 돌려줌: (같은지, 다른 바이트 수 또는 None)."""
    import ctypes as C
    import dq4nameentrycheck as nec
    want = nec.field_tiles(rom, text)
    size = r.c.lib.retro_get_memory_size(3)
    if size:
        vram = bytes((C.c_ubyte * size).from_address(r.c.lib.retro_get_memory_data(3)))
        got = b''.join(vram[a:b] for a, b in NAME_VRAM)
        diff = sum(x != y for x, y in zip(got, want))
        return diff == 0, diff
    st = r.c.save()[0]
    return want[:128] in st and want[128:] in st, None


def name_state(r):
    n = r.rd(NE_N)
    return n, [r.rd(NE_CH + 2 * k, 2) for k in range(min(n, ne.MAX_CHARS))], r.rd(NE_SP)


def new_game(r, problems, info):
    """1~4. 이름 입력을 마치고 서장 첫머리에 서기까지."""
    from dq4sfxscene import spc_state
    at = r.until(lambda: r.rd(SONG_NOW) == OVERTURE, 600)
    info['overture_frame'] = at
    if at is None:
        problems.append(f'서곡(곡 {OVERTURE:02X})이 600프레임 안에 지금 곡이 되지 않음')
        return None
    # 곡이 바뀐 프레임의 ENVX 를 바탕으로, 그 뒤 목소리 0~5 가운데 하나가 앞 프레임보다 오르면 서곡이 울린 것
    voiced, prev = None, envx(r)
    for _ in range(120):
        r.step()
        now = envx(r)
        if any(now[v] > prev[v] for v in range(6)):
            voiced = r.c.n
            break
        prev = now
    info['overture_voiced'] = voiced
    if voiced is None:
        problems.append('서곡이 지금 곡이 된 뒤 120프레임 안에 목소리 0~5 가 새로 울리지 않음')
    lit = r.until(lambda: r.bright and r.bright[-1][1] >= TITLE_BRIGHT, 600)
    info['title_lit'] = lit
    if lit is None:
        problems.append(f'타이틀 화면 밝기가 {TITLE_BRIGHT} 에 닿지 않음')
    r.wait(60)
    loud = max((v for n, v in r.rms if n >= (at or 0)), default=0)
    info['overture_rms'] = round(loud, 1)
    if loud < 100:
        problems.append(f'서곡 동안 소리가 거의 없음(RMS {loud:.0f})')
    menu = r.until(lambda: r.rd(MENU_FLAG) == MENU_ON, 600, press='start', every=30)
    info['menu'] = menu
    if menu is None:
        problems.append('Start 로 메뉴(7E:1BB0 = A5)가 열리지 않음')
        return None
    entry = r.until(lambda: r.rd(NE_ACTIVE) == 1, 400, press='a')
    info['name_entry'] = entry
    if entry is None:
        problems.append('기록이 없는데 A 로 이름 입력에 들어가지 않음')
        return None
    r.wait(30)
    keys = board_keys()
    nav = ne.navigation(keys)
    start = keys.index(ne.JAMO.index(ne.CURSOR_START))
    if r.rd(CURSOR) != start:
        problems.append(f'이름 입력 첫 커서 {r.rd(CURSOR)}, 기대 {start}({ne.CURSOR_START})')
        return None
    model, steps, cur = NameModel(), [], start
    for key in KEYS:
        if key == BACK_KEY:
            r.tap('b')
            model.back()
            accepted = True
        else:
            goal = keys.index(ne.BACK) if key == ERASE_CELL else keys.index(ne.JAMO.index(key))
            for d, nxt in route(nav, cur, goal):
                r.tap(d)
                if r.rd(CURSOR) != nxt:
                    problems.append(f'{key}: {d} 뒤 커서 {r.rd(CURSOR)}, 기대 {nxt}')
                    return None
                cur = nxt
            before = len(r.events)
            r.tap('a')
            r.wait(20)
            if key == ERASE_CELL:
                model.back()
                accepted = True
            else:
                accepted = model.press(key)
                rejected = any((a, x) == REJECT for _, a, x in r.events[before:])
                if not accepted and not rejected:
                    problems.append(f'{key}: 받지 않아야 하는데 거절음(인자 {REJECT[0]:02X} X {REJECT[1]:02X})이 없음')
        n, chars, sp = name_state(r)
        want_n = len(model.chars)
        want_chars = model.chars[:ne.MAX_CHARS]
        ok = (n, chars, sp) == (want_n, want_chars, len(model.stack))
        steps.append({'key': key, 'accepted': accepted, 'text': model.text(), 'ok': ok,
                      'got': [n, [ne.GLYPHS[g] if g < len(ne.GLYPHS) else g for g in chars], sp]})
        if not ok:
            problems.append(f'{key}: 이름 상태 {steps[-1]["got"]}, 기대 {model.text()!r}(확정 {want_n}, 조합 칸 {len(model.stack)})')
            return None
    info['typed'] = steps
    text = model.text()
    info['name'] = text
    r.wait(10)
    shown, diff = name_tiles(r, Path(r.rom).read_bytes(), text)
    info['name_tiles'] = {'same': shown, 'diff_bytes': diff}
    if not shown:
        problems.append(f'이름 칸 화면 타일이 롬 글꼴로 그린 「{text}」 와 다름({diff} 바이트)')
    r.tap('y')
    r.wait(30)
    if r.rd(NE_ACTIVE) != 0:
        problems.append('Y 로 이름 입력이 끝나지 않음')
    got = bytes(r.rd(NAME + k) for k in range(8))
    if got != name_bytes(text):
        problems.append(f'확정한 이름 7E:2001 {got.hex()}, 기대 {name_bytes(text).hex()}({text})')
    ready = r.until(lambda: r.rd(MENU_FLAG) == 0 and (r.rd(MAP[0]), r.rd(MAP[1])) == PROLOGUE_MAP, 900, press='a')
    info['prologue'] = ready
    if ready is None:
        problems.append(f'이름 확정 뒤 서장 맵 {PROLOGUE_MAP[0]:02X}/{PROLOGUE_MAP[1]:02X} 에 들지 않음')
        return None
    silent = r.until(lambda: r.rd(SONG_NOW) == SILENT, 300)
    info['silent_song'] = silent
    if silent is None:
        problems.append(f'서장 첫머리 곡이 {SILENT:02X}(무음 곡) 이 되지 않음')
    got = bytes(r.rd(NAME + k) for k in range(8))
    if got != name_bytes(text):
        problems.append(f'서장 7E:2001 {got.hex()}, 기대 {name_bytes(text).hex()}')
    return text


def check_record(rom, sram, text, problems, info):
    """새 게임이 쓴 SRAM 칸이 밑판과 이름·체크섬만 다른지."""
    import dq4savefixture as fx
    from dq5sram import SLOTS, SLOT_SIZE, SUM_AT
    used = fx.saved_slots(sram)
    info['saved_slots'] = used
    if not used:
        problems.append('새 게임이 SRAM 에 기록을 쓰지 않음')
        return
    blk = sram[SLOTS[used[0]]:SLOTS[used[0]] + SLOT_SIZE]
    base = fx.SaveSlot.new_game(rom).to_block()
    diff = slot_diff(blk, base)
    allowed = set(range(1, 9)) | {SUM_AT, SUM_AT + 1}
    info['record_diff'] = [f'{fx.WRAM_BASE + i:04X}' for i in diff]
    if blk[1:9] != name_bytes(text):
        problems.append(f'기록 칸 이름 {bytes(blk[1:9]).hex()}, 기대 {name_bytes(text).hex()}')
    extra = [f'{fx.WRAM_BASE + i:04X}' for i in diff if i not in allowed]
    if extra:
        problems.append(f'기록 칸이 밑판(이름 ㅂㅂㅂㅂ 새 게임)과 이름·체크섬 밖에서 다름: {extra[:12]}')


def continue_game(core):
    """dq4savefixture.CONTINUE 입력(Start, A 연타)으로 이어 한다. 새 게임 첫 기록은 이어 할 자리 칸(7E:2033)이
    ルーラ 칸 표 밖이라 자리 표(25:8621)로 정하지 않고, 메뉴가 닫히고 서장 맵에 선 프레임을 본다."""
    import dq4savefixture as fx
    script = [b for b, f in fx.CONTINUE for _ in range(f)]
    arrived, entry = None, False
    while core.n < fx.ARRIVE_BY:
        b = script[core.n] if core.n < len(script) else 'wait'
        core.run(set() if b == 'wait' else {b})
        entry |= core.rd(NE_ACTIVE) == 1
        if core.n >= fx.ARRIVE_FROM and core.rd(MENU_FLAG) == 0 and (core.rd(MAP[0]), core.rd(MAP[1])) == PROLOGUE_MAP:
            arrived = core.n
            break
    return {'arrived': arrived, 'name': bytes(core.rd(NAME + k) for k in range(8)).hex(), 'name_entry': entry}


def check_core(name, rom, out):
    import dq4cores
    import dq4savefixture as fx
    out.mkdir(parents=True, exist_ok=True)
    path = dq4cores.core_path(name)
    res, problems, info = {'core': None}, [], {}
    t0 = time.time()
    with fx.closing(fx.open_core(path, rom, out / 'new')) as core:
        res['core'] = core.name
        r = Runner(core, rom)
        text = new_game(r, problems, info)
        r.wait(60)
        core.shot(out / 'prologue.png')
        sram = fx.read_sram(core)
    if text is not None:
        check_record(rom, sram, text, problems, info)
    cont = {}
    if text is not None and fx.saved_slots(sram):
        with fx.closing(fx.open_core(path, rom, out / 'continue', sram)) as core:
            cont = continue_game(core)
            core.shot(out / 'continue.png')
        if cont['arrived'] is None:
            problems.append(f'이어 하기로 서장 맵 {PROLOGUE_MAP[0]:02X}/{PROLOGUE_MAP[1]:02X} 에 서지 않음')
        elif cont['name'] != name_bytes(text).hex():
            problems.append(f'이어 한 뒤 이름 {cont["name"]}, 기대 {name_bytes(text).hex()}')
        if cont.get('name_entry'):
            problems.append('기록이 있는데 A·A 가 이름 입력으로 감(칸 목록이 아님)')
    res.update(status='failed' if problems else 'passed', problems=problems, info=info, continue_=cont,
               seconds=round(time.time() - t0, 1), core_sha256=dq4cores.sha256(path))
    return res


def main():
    import dq4compatcheck as cc
    import dq4cores
    import dq4savefixture as fx
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', nargs='?', choices=('check', '_core'), default='check')
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    args = ap.parse_args()
    rom = args.rom.resolve()
    out = args.out.resolve()
    if args.mode == '_core':
        res = check_core(args.core, rom, out)
        (out / 'core.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
        return 0 if res['status'] == 'passed' else 1
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    names = list(cc.CORES) if args.core == 'all' else [args.core]
    for n in names:
        if not dq4cores.core_path(n).exists():
            raise SystemExit(f'{dq4cores.core_path(n)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드')
    t0 = time.time()
    fx.SaveSlot.new_game(rom)            # 밑판을 먼저 한 번(코어 프로세스가 함께 만들지 않게)
    procs = {}
    for n in names:
        (out / n).mkdir(parents=True)
        with (out / n / 'log.txt').open('w') as log:
            procs[n] = subprocess.Popen([sys.executable, __file__, '_core', '--core', n, '--rom', str(rom),
                                         '--out', str(out / n)], stdout=log, stderr=subprocess.STDOUT)
    report = {'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(), 'cores': {}}
    for n, proc in procs.items():
        try:
            proc.wait(timeout=cc.UNIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        f = out / n / 'core.json'
        report['cores'][n] = (json.loads(f.read_text()) if f.exists() else
                              {'status': 'failed', 'problems': [f'코어 프로세스가 결과를 남기지 않음({out / n / "log.txt"})']})
    report['status'] = 'passed' if all(v['status'] == 'passed' for v in report['cores'].values()) else 'failed'
    report['seconds'] = round(time.time() - t0, 1)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds'],
                      **{k: {'status': v['status'], 'name': v.get('info', {}).get('name'),
                             'problems': v.get('problems')} for k, v in report['cores'].items()}},
                     ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
