"""효과음 장면 검사: 1장에서 나는 효과음마다 게임 동작을 한 번 해 보고, 소리 대기열에 들어간 (명령, 효과음, 갈래)가
효과음 대응표(dq4sound-game.args)에서 나온 기대값과 같은지, 그 소리가 실제로 SPC 목소리에서 울렸는지 본다.
libretro bsnes·snes9x 둘 다, 장면마다 저장 기록(dq4savefixture)으로 그 자리 앞에서 시작한다. 형식은
sfc/dq4/docs/dq4-sound-port-format.md 「효과음 장면 검사」.

- 대기열: 24:FF83(과 같은 사본 34:FF83)이 칸 X 에 [명령 $1D95][인자 $1DA5][X $1DB5] 를 쓰고 $1D91 을 올린다. 2B 쪽이
  같은 프레임에 보내고 명령 칸을 FF 로 지우면 프레임마다 읽어서는 명령을 놓친다. 그래서 검사 롬 사본에만
  24:FFCC·34:FFCC 의 `STA $1D95,X / LDA #05` 를 같은 일에 그림자 칸 7E:1DD5+X 쓰기를 더한 루틴(7D:FF00)으로 바꾼다.
- 울림: 직렬화 상태의 DSP 레지스터에서 목소리 7(효과음)과 6(둘째 효과음 목소리)의 ENVX 가 대기열에 들어간 뒤
  WINDOW 프레임 안에 0 에서 오르는지. 곡(명령 01)은 $1D8B 가 그 곡이 되고 목소리 0~5 가 울리는지.
- 대응표: --sfx(DQ5 갈래 → NDS), --sfx-call(부르는 자리의 효과음 번호 바꿈), --sfx-remap(입구에서 돌려 부르기),
  --sfx-weapon(무기마다), --sfx-item, --sfx-pcm(빈 효과음 갈래), --inn-jingle. 장면이 없는 항목은 UNREACHED 에 까닭과
  함께 둔다(빠진 항목이 있으면 단위 테스트가 실패). --sfx-call 자리와 무기 표는 롬 바이트로도 본다.

  python sfc/dq4/tools/dq4cores.py && python sfc/dq4/tools/dq4sfxscene.py --rom work/ch1/dq4-ch1-full.sfc --out work/sfxscene
  (--only 장면,장면 · --core snes9x · --jobs 4)
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

ARGS = HERE / 'dq4sound-game.args'

# 대기열(7E 뱅크)
Q_WRITE, Q_READ, Q_CMD, Q_ARG, Q_X = 0x1D91, 0x1D93, 0x1D95, 0x1DA5, 0x1DB5
Q_LEN = 16
SONG_NOW = 0x1D8B
# 검사 롬 사본의 훅이 쓰는 명령 그림자(16칸)와 그 보수(16칸). 게임이 아무도 쓰지 않는 WRAM 은 찾지 못했다: 표지(A5)를
# 채워 보니 7F:FFF0 은 맵을 불러올 때, 7E:1DD5·1700·2B00 은 전투에서, 7E:9800 은 전투에서 돌아와 맵을 다시 그릴 때
# 덮였다. 그래서 칸마다 보수를 함께 써 두고, 둘이 맞는 칸만 훅이 쓴 것으로 읽는다. 덮이는 프레임에 들어온 명령은
# 놓칠 수 있다(전투에서 돌아오는 프레임 하나).
SHADOW, SHADOW_NOT = 0x9800, 0x9810
ENTRY_SITES = (0x24FFCC, 0x34FFCC)    # `STA $1D95,X` / `LDA #$05`
ENTRY_BYTES = bytes.fromhex('9D951DA905')
HOOK = 0x7DFF00
# STA $7E1D95,X / STA $7E:SHADOW,X / EOR #$FF / STA $7E:SHADOW_NOT,X / LDA #$05 / RTL. X 는 8비트(24:FF88 SEP #$30)
HOOK_CODE = (bytes.fromhex('9F951D7E') + bytes((0x9F, SHADOW & 0xFF, SHADOW >> 8, 0x7E)) + bytes.fromhex('49FF')
             + bytes((0x9F, SHADOW_NOT & 0xFF, SHADOW_NOT >> 8, 0x7E)) + bytes.fromhex('A9056B'))
SFX, SONG = 0x0C, 0x01
# 효과음 목소리를 울리는 대기열 명령: 효과음 0C, 글자 소리 05(대화·전투 메시지 글자마다 32-01), 배포 롬 장면의 모르는 명령
SOUND_CMDS = (SFX, 0x05, None)
WINDOW = 45
SFX_VOICES = (7, 6)
TOGETHER = 4                          # 한 효과음의 두 목소리가 함께 시작한다고 보는 프레임 차
DSP_DIR = 0x07                        # 드라이버가 두는 DIR(dq5spc.SPC_DIR >> 8)
BSNES_DSP = 289781                    # bsnes 115 직렬화 상태의 DSP 레지스터 128바이트(DIR·EDL 로 찾아 잼)
# SPC RAM 64KB 의 자리. DIR(7)의 칸이 가리키는 BRR 이 원본 DQ5 늘 두는 파형 1F 와 바이트까지 같아지는 자리로 맞춤
BSNES_SPC_RAM = 207853
SNES9X_SPC_RAM = 1                    # snes9x 상태 SND: 블록 안
SNES9X_DSP = 65701                    # snes9x 상태 SND: 블록 안의 DSP 레지스터


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


# ---- 대응표 ------------------------------------------------------------------------------------------------------

def key(text):
    """'37-0E' → (0x37, 0x0E)."""
    s, b = text.split('-')
    return int(s, 16), int(b, 16)


def name(k):
    return f'{k[0]:02X}-{k[1]:02X}'


@dataclass
class Table:
    """dq4sound-game.args 에서 효과음에 닿는 것만."""
    sfx: dict = field(default_factory=dict)       # (효과음, 갈래) → NDS 번호 문자열
    pcm: dict = field(default_factory=dict)       # 빈 효과음 (효과음, 갈래) → NDS 사양
    calls: dict = field(default_factory=dict)     # CPU 주소 → (원래 효과음, 새 효과음)
    remap: dict = field(default_factory=dict)     # (효과음, 갈래) → (효과음, 갈래)
    weapons: dict = field(default_factory=dict)   # 무기 번호($0DA7) → (효과음, 갈래)
    weapon_songs: list = field(default_factory=list)
    items: list = field(default_factory=list)     # 물건을 찾을 때 (효과음, 갈래)
    inn_jingle: bool = False
    songs: dict = field(default_factory=dict)     # DQ5 곡 자리 → NDS 곡

    def entries(self):
        """장면이 맡아야 할 항목 이름들(UNREACHED·장면의 covers 와 견줌)."""
        out = [f'sfx {name(k)}' for k in self.sfx] + [f'pcm {name(k)}' for k in self.pcm]
        out += [f'call {a:06X}' for a in self.calls] + [f'remap {name(k)}' for k in self.remap]
        out += [f'weapon {w:02X}' for w in self.weapons] + [f'item {name(k)}' for k in self.items]
        if self.inn_jingle:
            out.append('inn-jingle')
        return out


def parse_args_file(text):
    """[(옵션, 값 또는 None)]. 값은 옵션 다음 줄(-- 로 시작하지 않는 줄)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out, i = [], 0
    while i < len(lines):
        opt = lines[i]
        if not opt.startswith('--'):
            raise ValueError(f'옵션이 아님: {opt}')
        val = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith('--') else None
        out.append((opt, val))
        i += 2 if val is not None else 1
    return out


def load_table(text):
    t = Table()
    for opt, val in parse_args_file(text):
        if opt == '--sfx':
            k, v = val.split('=')
            t.sfx[key(k)] = v
        elif opt == '--sfx-pcm':
            k, v = val.split('=')
            t.pcm[key(k)] = v
        elif opt == '--sfx-call':
            a, v = val.split('=')
            old, new = v.split(':')
            t.calls[int(a, 16)] = (int(old, 16), int(new, 16))
        elif opt == '--sfx-remap':
            a, b = val.split('=')
            t.remap[key(a)] = key(b)
        elif opt == '--sfx-weapon':
            w, v = val.split('=')
            t.weapons[int(w, 16)] = key(v)
        elif opt == '--sfx-weapon-songs':
            t.weapon_songs.append(int(val, 16))
        elif opt == '--sfx-item':
            t.items.append(key(val))
        elif opt == '--inn-jingle':
            t.inn_jingle = True
        elif opt == '--song':
            a, b = val.split('=')
            t.songs[int(a, 16)] = int(b, 16)
    return t


def routed(table, sfx, branch, site=None):
    """게임이 (sfx, branch)를 부를 때 대기열에 들어갈 (효과음, 갈래). site 는 부르는 BRK 의 CPU 주소(--sfx-call)."""
    if site is not None and site in table.calls:
        old, new = table.calls[site]
        if old != sfx:
            raise ValueError(f'{site:06X} 은 {old:02X} 를 부르는 자리(장면은 {sfx:02X})')
        sfx = new
    return table.remap.get((sfx, branch), (sfx, branch))


def weapon_sound(table, weapon, song):
    """たたかう 소리: 지금 곡이 weapon_songs 이고 표에 있는 무기면 그 (효과음, 갈래), 아니면 None(DQ5 종류 표)."""
    if song in table.weapon_songs:
        return table.weapons.get(weapon)
    return None


def call_site_problems(rom, table):
    """--sfx-call 자리마다 롬이 `BRK 16|19 <새 효과음>` 인지."""
    out = []
    for addr, (old, new) in sorted(table.calls.items()):
        o = lorom(addr)
        got = rom[o:o + 3]
        if got[0] != 0x00 or got[1] not in (0x16, 0x19) or got[2] != new:
            out.append(f'{addr:06X}: {got.hex()} (기대 00 16|19 {new:02X}, 원래 {old:02X})')
    return out


WEAPON_SEQ_TABLE, WEAPON_BRANCH_TABLE = 0x718A00, 0x718B00
BARE_HANDS = 0x80                     # $0DA7 bit7 은 표를 보지 않고 맨손 갈래로 감(dq4soundpatch.BARE_HANDS)


def weapon_table_problems(rom, table):
    """무기 표 71:8A00(효과음)·71:8B00(갈래)이 --sfx-weapon 과 같은지(나머지는 FF)."""
    out = []
    for w in range(0x100):
        if w & BARE_HANDS:
            continue
        want = table.weapons.get(w, (0xFF, 0xFF))
        got = (rom[lorom(WEAPON_SEQ_TABLE) + w], rom[lorom(WEAPON_BRANCH_TABLE) + w])
        if got[0] != want[0] or (want[0] != 0xFF and got[1] != want[1]):
            out.append(f'무기 {w:02X}: 롬 {got[0]:02X}-{got[1]:02X}, 표 {want[0]:02X}-{want[1]:02X}')
    return out


# ---- 대기열·울림 판정(롬 없이 시험) --------------------------------------------------------------------------------

def drain(start, shadow, inverse, args, xs):
    """한 프레임 동안 훅이 쓴 칸들의 [(명령, 인자, X)]. 그림자와 보수가 맞는 칸(읽은 뒤 둘 다 FF 로 비워 맞지 않게
    둠)을 start(지난 프레임의 쓰기 칸)부터 차례로 읽는다. 쓰기 칸은 앞 칸이 FF 면 뒤로 물러나므로(24:FF94) 칸 번호
    차이로는 세지 않는다. 대기열의 명령 칸은 2B 도 고쳐 쓰므로(2B:BF89 등, 처리 중 위 두 비트) 견주지 않는다."""
    out = []
    for k in range(Q_LEN):
        i = (start + k) % Q_LEN
        if shadow[i] ^ inverse[i] == 0xFF:
            out.append((shadow[i], args[i], xs[i]))
    return out


def key_on(envx, start, window=WINDOW):
    """envx = 프레임마다 ENVX 목록(start 는 대기열에 들어간 프레임의 자리). 그 뒤 window 안에서 앞 프레임보다 올라
    0 이 아닌 첫 자리(없으면 None). 울리던 소리가 줄어들기만 하면 새로 울린 것이 아니다."""
    for i in range(max(start, 1), min(len(envx), start + window + 1)):
        if envx[i] and envx[i] > envx[i - 1]:
            return i
    return None


def match(events, want):
    """events = [(프레임, 명령, 효과음, 갈래)], want = (명령, 효과음, 갈래) → 첫 프레임 또는 None."""
    return next((f for f, *e in events if same(e, want)), None)


def same(event, want):
    """대기열 칸 (명령, 인자, X) 가 want 와 같은지. want 의 None 은 아무 값(곡의 X 는 부르는 곳마다 다름)."""
    return all(w is None or w == e for e, w in zip(event, want))


def fmt(want):
    return ' '.join('..' if v is None else f'{v:02X}' for v in want)


def match_seq(events, wants):
    """wants 를 차례로(같은 것이 두 번이면 두 번) 찾는다. 프레임 목록, 못 찾은 것부터는 None."""
    return [None if i is None else events[i][0] for i in match_index(events, wants)]


def match_index(events, wants):
    """match_seq 와 같되 events 의 자리(색인)."""
    out, i = [], 0
    for want in wants:
        while i < len(events) and not same(events[i][1:], want):
            i += 1
        if i >= len(events):
            out += [None] * (len(wants) - len(out))
            break
        out.append(i)
        i += 1
    return out


# ---- 장면 ----------------------------------------------------------------------------------------------------------

@dataclass
class Scene:
    """name: 이름. covers: 맡는 대응표 항목(Table.entries 이름). want: [(명령, 효과음, 갈래)] — 대응표에서 계산.
    forbid: 나오면 안 되는 것(원래 DQ5 번호). place: 저장 기록의 이어 할 자리. sets: SaveSlot.set 값.
    warp: 'BC/BD,x,y' 이어 한 뒤 순간이동. inputs: dq4compatcheck.Walker.walk 웨이포인트. battle: 걸음 전투 무리
    [(몬스터, 마릿수)]. pokes: 프레임마다 묶는 WRAM(CPU 주소, 값). patches: 검사 롬 사본에만 쓰는 [(파일 위치, 바이트 또는 원래 한 바이트 → 바이트 함수)].
    npc_talk: (x, y, 대화 번호) — 그 칸에 선 인물의 대화 번호를 바꾼다(7E:36E0·3700 + 슬롯, 여관 006·교회 005 등).
    seed: 순간이동 뒤 두는 난수(dq4ch1walkcheck.rng_for). {코어: 시드} 면 코어마다.
    maxf: 입력에 쓸 프레임(없으면 입력 길이로)."""
    name: str
    action: str
    want: list
    covers: list = field(default_factory=list)
    forbid: list = field(default_factory=list)
    place: str = 'imuru'
    sets: list = field(default_factory=lambda: ['flag=CHAPTER1'])
    warp: str = ''
    late: str = ''
    inputs: str = ''
    battle: list = None
    pokes: list = field(default_factory=list)
    patches: list = field(default_factory=list)
    npc_talk: tuple = None
    seed: int = 0
    critical: bool = False
    release: bool = False
    maxf: int = None


# ---- 실행 -----------------------------------------------------------------------------------------------------------

def hook_patches(rom):
    """대기열 그림자 훅(검사 롬 사본만). 자리 바이트가 예상과 다르면 ValueError."""
    out = []
    for site in ENTRY_SITES:
        o = lorom(site)
        if rom[o:o + 5] != ENTRY_BYTES:
            raise ValueError(f'{site:06X}: {rom[o:o + 5].hex()} — 대기열 입구가 바뀜')
        out.append((o, bytes((0x22, HOOK & 0xFF, HOOK >> 8 & 0xFF, HOOK >> 16, 0xEA))))
    h = lorom(HOOK)
    if any(rom[h:h + len(HOOK_CODE)]):
        raise ValueError(f'{HOOK:06X} 이 비어 있지 않음')
    out.append((h, HOOK_CODE))
    return out


def scene_rom(rom, scene):
    """검사 롬 사본: 대기열 훅, 걸음 전투(scene.battle 이면 그 무리로 강제, 아니면 없앰), 장면 패치."""
    import dq4battlecheck as bc
    import dq4ch1walkcheck as wc
    if scene.release:
        return bytes(rom)
    data = bytearray(rom)
    patches = hook_patches(rom) + list(scene.patches)
    text = bc.force_patch(scene.battle) if scene.battle else wc.NO_ENCOUNTERS
    for tok in text.split(';'):
        off, hexs = tok.split('=')
        patches.append((int(off, 16), bytes.fromhex(hexs)))
    for off, b in patches:
        if callable(b):
            b = b(bytes(data[off:off + 1]))
        data[off:off + len(b)] = b
    return bytes(data)


def spc_state(core):
    """직렬화 상태의 (DSP 레지스터 128바이트, SPC RAM 64KB). 코어마다 자리가 다르고, DIR 이 드라이버가 두는 값인지로
    맞는지 본다. 드라이버가 DIR 을 두기 전(켠 직후)이면 None."""
    st = core.save()[0]
    if core.name.lower().startswith('snes9x'):
        base = st.find(b'SND:') + 10
        ram, regs = base + SNES9X_SPC_RAM, base + SNES9X_DSP
    else:
        ram, regs = BSNES_SPC_RAM, BSNES_DSP
    r = st[regs:regs + 128]
    if len(r) != 128:
        raise RuntimeError(f'{core.name}: 직렬화 상태가 짧음')
    if r[0x5D] != DSP_DIR:
        return None
    return r, st[ram:ram + 0x10000]


def dq5_samples(path=None):
    """원본 DQ5 롬(rom/dq5.sfc)의 샘플 번호 → BRR. 빌드 입력과 상관없는 기준이다."""
    import dq4soundcheck as sc
    from dq5map import Rom
    from dq5spc import samples
    data = Path(path or HERE.parents[2] / 'rom' / 'dq5.sfc').read_bytes()
    return {n: sc.sample_body(data, n)[7:] for n, *_ in samples(Rom(data))}


def source(regs, ram, voice, dq5):
    """목소리의 소리 바탕: 잡음(NON 비트)이면 'noise'. 아니면 SRCN 의 DIR 시작에서 원본 DQ5 샘플과 BRR 이 같으면
    'dq5 XX'(같은 파형이 여럿이면 '/' 로), 어느 것과도 다르면 'nds'(DQ5 에 없는 샘플: NDS 에서 옮긴 소리)."""
    if regs[0x3D] >> voice & 1:
        return 'noise'
    srcn = regs[voice * 16 + 4]
    start = ram[DSP_DIR * 0x100 + srcn * 4] | ram[DSP_DIR * 0x100 + srcn * 4 + 1] << 8
    same = [n for n, brr in dq5.items() if ram[start:start + len(brr)] == brr]
    return 'dq5 ' + '/'.join(f'{n:02X}' for n in same) if same else 'nds'


def make_walker():
    import dq4compatcheck as cc
    from dq4libretro import Core
    from dq5exitcheck import warp_exit

    class SceneWalker(cc.Walker):
        """dq4compatcheck.Walker 와 같게 걷되, 롬은 scene_rom 사본이고 프레임마다 대기열과 DSP 를 적는다."""

        def __init__(self, core_path, rom_bytes, out, release=False):
            self.out, self.seed = out, 0
            self.rom = out / 'c.sfc'
            self.rom.write_bytes(rom_bytes)
            self.warp_exit = warp_exit(self.rom)
            self.c = Core(str(core_path), str(self.rom), str(out))
            (out / cc.STARTED).write_text(f'{self.c.slot.waited:.3f}')
            self.audio, self.rms = [], []
            self.pokes, self.rom_cheats, self.cheat_key = [], {}, None
            self.events, self.envx, self.songs = [], [], []
            self.last = None
            self.watch = False
            self.release = release
            self.dsp_seen = False
            self.sources = {}
            self.dq5 = dq5_samples()

        def step(self, buttons=()):
            super().step(buttons)
            m = self.c.wram()
            if self.release:
                # 배포 롬(훅 없음): 쓰기 칸이 옮겨 간 칸의 인자·X 만 읽는다(명령은 이미 지워졌을 수 있음)
                now = m[Q_WRITE]
                if self.last is not None and now != self.last:
                    i = self.last
                    while i != now:
                        self.events.append((self.c.n, None, m[Q_ARG + i], m[Q_X + i]))
                        i = (i + 1) % Q_LEN
                self.last = now
            else:
                self.shadow_step(m)
            if self.watch:
                # 직렬화는 이어 하기·순간이동을 마친 뒤에만(bsnes 는 직렬화가 코어 동기 지점을 바꾼다)
                got = spc_state(self.c)
                env = tuple(got[0][v * 16 + 8] for v in range(8)) if got else (0,) * 8
                prev = self.envx[-1][1] if self.envx else (0,) * 8
                for v in SFX_VOICES:
                    if got and env[v] > prev[v]:
                        # 울리기 시작한 프레임의 바탕(다음 프레임이면 SRCN 이 다음 음으로 바뀔 수 있다)
                        self.sources[(len(self.envx), v)] = source(got[0], got[1], v, self.dq5)
                self.envx.append((self.c.n, env))
                self.dsp_seen |= got is not None
                self.songs.append(m[SONG_NOW])

        def shadow_step(self, m):
            clear = [(0x7E0000 + a + i, 0xFF) for a in (SHADOW, SHADOW_NOT) for i in range(Q_LEN)]
            if self.last is None:
                # 켤 때 그림자 칸은 아무 값이나 들어 있다
                self.c.poke(clear)
            else:
                new = drain(self.last, m[SHADOW:SHADOW + Q_LEN], m[SHADOW_NOT:SHADOW_NOT + Q_LEN],
                            m[Q_ARG:Q_ARG + Q_LEN], m[Q_X:Q_X + Q_LEN])
                self.events += [(self.c.n, *e) for e in new]
                if any(v != 0xFF for v in m[SHADOW:SHADOW + Q_LEN]) or any(v != 0xFF for v in m[SHADOW_NOT:SHADOW_NOT + Q_LEN]):
                    self.c.poke(clear)
            self.last = self.c.rd(0x7E0000 + Q_WRITE)

    return SceneWalker


POWER = 'power'                       # 저장 기록 없이 전원부터(새 게임)
NPC_X, NPC_Y, NPC_TALK_LO, NPC_TALK_HI, NPC_SLOTS = 0x3020, 0x3080, 0x36E0, 0x3700, 32


def npc_slot(core, x, y):
    """그 칸에 선 인물 슬롯(주인공 슬롯 0 은 빼고)."""
    return next((k for k in range(1, NPC_SLOTS) if (core.rd(0x7E0000 + NPC_X + k), core.rd(0x7E0000 + NPC_Y + k)) == (x, y)),
                None)


def slot_for(rom_path, scene):
    import dq4savefixture as fx
    slot = fx.SaveSlot.new_game(rom_path)
    slot.place = scene.place
    for kv in scene.sets:
        k, v = kv.split('=', 1)
        slot.set(k, v)
    return slot


def run_scene(core_name, rom_path, scene, out, dsp=True):
    """한 코어에서 장면 하나: 저장 기록으로 이어 하고(필요하면 순간이동), 입력을 넣고, 대기열·DSP 를 적는다."""
    import dq4compatcheck as cc
    import dq4cores
    import dq4ch1walkcheck as wc
    import dq4savefixture as fx
    out.mkdir(parents=True, exist_ok=True)
    rom = Path(rom_path).read_bytes()
    if scene.place == POWER:
        walker = make_walker()(dq4cores.core_path(core_name), scene_rom(rom, scene), out, scene.release)
        res = {'scene': scene.name, 'core': walker.c.name, 'problems': []}
        with fx.closing(walker.c):
            # 서장 검사와 같은 새 게임 입력(A 연타, 이름 입력에서 Y)으로 수련이 끝날 때까지
            walker.events, walker.watch = [], dsp
            walker.boot()
            cc.apply_sets(walker.c, wc.pins(wc.SEGMENTS[0][3]))
            walker.pokes = list(scene.pokes)
            walker.walk(scene.inputs, {'maxf': scene.maxf or wc.frames(scene.inputs)})
        return finish(walker, scene, res, out)
    slot = slot_for(rom_path, scene)
    sram = slot.to_sram()
    (out / 'c.srm').write_bytes(sram)
    walker = make_walker()(dq4cores.core_path(core_name), scene_rom(rom, scene), out, scene.release)
    res = {'scene': scene.name, 'core': walker.c.name, 'problems': []}
    with fx.closing(walker.c):
        fx.load_sram(walker.c, sram)
        at = fx.boot(walker.c, slot.goal, step=walker.step)
        if at is None:
            res['problems'].append(f'이어 할 자리 {slot.goal} 에 서지 않음')
            return finish(walker, scene, res, out)
        seed = scene.seed.get(core_name, 0) if isinstance(scene.seed, dict) else scene.seed
        pins = wc.pins({}, seed)
        if scene.warp:
            maps = walker.warp(scene.warp, ';'.join(v for v in (pins, scene.late) if v), cc.sets(pins))
            if maps[-1] != scene.warp[:5]:
                res['problems'].append(f'순간이동이 {maps[-1]} 에 섬(기대 {scene.warp[:5]})')
                return finish(walker, scene, res, out)
        else:
            cc.apply_sets(walker.c, ';'.join(v for v in (pins, scene.late) if v))
        if scene.npc_talk:
            slot_no = npc_slot(walker.c, *scene.npc_talk[:2])
            if slot_no is None:
                res['problems'].append(f'{scene.npc_talk[:2]} 에 선 인물이 없음')
                return finish(walker, scene, res, out)
            n = scene.npc_talk[2]
            walker.c.poke([(0x7E0000 + NPC_TALK_LO + slot_no, n & 0xFF), (0x7E0000 + NPC_TALK_HI + slot_no, n >> 8)])
        walker.events, walker.watch = [], dsp
        walker.pokes = list(scene.pokes)
        walker.walk(scene.inputs, {'maxf': scene.maxf or wc.frames(scene.inputs)})
    return finish(walker, scene, res, out)


def song_on(songs, envx, f, song, limit=600, window=120):
    """곡이 지금 곡으로 바뀐 프레임 자리(f 뒤 첫 전환)와, 그 뒤 window 안에 목소리 0~5 가운데 하나가 앞 프레임보다
    올라 울린 자리. 전환 앞부터 울리던 곡의 꼬리는 줄어들기만 하므로 치지 않는다."""
    j = next((k for k in range(max(f, 1), min(len(songs), f + limit)) if songs[k] == song and songs[k - 1] != song), None)
    if j is None:
        return None, None
    hits = [k for v in range(6) for k in [key_on([e[v] for _, e in envx], j, window)] if k is not None]
    return j, min(hits) if hits else None


def source_ok(got, want):
    """want: 'noise', 'nds'(원본 DQ5 에 없는 샘플), 'dq5'(원본 DQ5 샘플과 BRR 이 같거나 잡음: DQ5 효과음도 잡음을 씀),
    'not-dq5'(원본 DQ5 에 없는 샘플이거나 잡음: NDS 무기 소리는 샘플·잡음 둘 다로 옮겨짐)."""
    if got is None:
        return False
    if want == 'dq5':
        return got.startswith('dq5 ') or got == 'noise'
    if want == 'not-dq5':
        return got in ('nds', 'noise')
    return got == want


def assign_key_ons(events, wants, frames, envx, sources):
    """대기열 효과음 항목마다 울림 하나를 짝짓는다. 항목의 창은 다음 효과음 항목이 들어오기 전까지(최대 WINDOW).
    목소리 7·6 의 ENVX 가 오른 자리 가운데 아직 짝짓지 않은 가장 이른 자리를 고른다. 목소리 6 은 곡과 나눠 쓰고,
    대화 글자처럼 효과음이 6 에서만 울리기도 해서(7 은 앞 효과음 꼬리) 둘 다 본다. 바탕은 짝지은 울림과, 창 안의 다른
    목소리 첫 울림 가운데 TOGETHER 프레임 안에 시작한 것을 함께 돌려준다(6 의 울림이 곡 음일 수 있음).
    돌려줌: want 차례대로 (프레임, 목소리, [(목소리, 바탕)…]) 또는 None."""
    sfx_frames = sorted({n for n, c, *_ in events if c in SOUND_CMDS})
    used, out = set(), []
    for f in wants:
        if f is None:
            out.append(None)
            continue
        nxt = next((n for n in sfx_frames if n > f), None)
        end = min(f + WINDOW, nxt) if nxt is not None else f + WINDOW
        i = frames.index(f) if f in frames else None
        firsts = []
        for v in SFX_VOICES:
            series = [e[v] for _, e in envx]
            k = i
            while k is not None:
                k = key_on(series, k, end - frames[k] if k < len(frames) else 0)
                if k is None or frames[k] > end:
                    k = None
                    break
                if (k, v) not in used:
                    break
                k += 1
            if k is not None:
                firsts.append((k, v))
        if not firsts:
            out.append(None)
            continue
        best = min(firsts)
        used.add(best)
        k, v = best
        # 다른 목소리의 울림은 짝지은 울림과 거의 같이 시작할 때만(늦게 오른 것은 다음 소리일 수 있음)
        out.append((frames[k], v, [(v, sources.get(best))] +
                    [(x[1], sources.get(x)) for x in firsts if x != best and x[0] - k <= TOGETHER]))
    return out


def finish(walker, scene, res, out):
    """대기열·울림을 판정하고 결과를 쓴다."""
    events = walker.events
    frames = [n for n, _ in walker.envx]
    res['queue'] = [f"{n} {'..' if c is None else f'{c:02X}'} {a:02X} {x:02X}" for n, c, a, x in events]
    res['want'] = []
    if not walker.watch:
        # DSP 를 읽지 않은 대조 실행: 대기열 기록만 남긴다
        res['status'] = 'control'
        (out / 'scene.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
        return res
    idx = match_index(events, [w[:3] for w in scene.want])
    hits = [None if i is None else events[i][0] for i in idx]
    # 울림은 글자 소리까지 모든 효과음 항목에 차례로 짝지어, 원하는 항목이 앞 항목의 울림을 가져가지 않게 한다
    sound = [i for i, e in enumerate(events) if e[1] in SOUND_CMDS]
    paired = dict(zip(sound, assign_key_ons(events, [events[i][0] for i in sound], frames, walker.envx,
                                            walker.sources)))
    ons = {k: paired.get(i) for k, (w, i) in enumerate(zip(scene.want, idx))
           if w[0] in (SFX, None) and i is not None}
    for k, (want, f) in enumerate(zip(scene.want, hits)):
        row = {'want': fmt(want[:3]), 'frame': f, 'sounded': None}
        if len(want) > 3:
            row['source_want'] = want[3]
        if f is None:
            res['problems'].append(f'대기열에 {row["want"]} 없음')
            res['want'].append(row)
            continue
        if want[0] == SONG:
            switch, on = song_on(walker.songs, walker.envx, frames.index(f) if f in frames else 0, want[1])
            row['switch'] = frames[switch] if switch is not None else None
            row['sounded'] = frames[on] if on is not None else None
            if row['sounded'] is None:
                res['problems'].append(f'{row["want"]} 이 대기열에 들어갔지만 곡이 바뀐 뒤 목소리 0~5 가 새로 울리지 않음')
        else:
            got = ons.get(k)
            if got is None:
                res['problems'].append(f'{row["want"]}(프레임 {f}): 다음 효과음 항목 전까지 목소리 7·6 에 새 울림이 없음')
            else:
                row['sounded'], row['voice'], row['source'] = got[0], got[1], got[2][0][1]
                row['sources'] = [f'{v}:{x}' for v, x in got[2]]
                kind = want[3] if len(want) > 3 else None
                bad = None
                if kind and not any(source_ok(x, kind) for _, x in got[2]):
                    bad = f'{row["want"]}: 울린 바탕 {row["sources"]}, 결정 표의 바탕 {kind}'
                elif kind == 'dq5' and any(v == 7 and x == 'nds' for v, x in got[2]):
                    # 목소리 7 은 효과음만 쓴다: DQ5 로 고른 소리가 원본 DQ5 에 없는 샘플로 울림
                    bad = f'{row["want"]}: DQ5 로 고른 소리가 목소리 7 에서 원본 DQ5 에 없는 샘플로 울림({row["sources"]})'
                if bad:
                    res['problems'].append(bad)
        res['want'].append(row)
    for bad in scene.forbid:
        f = match(events, bad)
        if f is not None:
            res['problems'].append(f'대기열에 {fmt(bad)}(원래 번호)가 들어감(프레임 {f})')
    if scene.critical and not any(w.get('sounded') for w in res['want'] if w['want'] == fmt((SFX, 0x37, 0x0B))):
        res['problems'].insert(0, '회심 미발생(시드 다시 고르기: dq4sfxscene.py --pick-critical-seed)')
    if walker.envx and not walker.dsp_seen:
        res['problems'].append(f'DSP 레지스터를 찾지 못함(DIR {DSP_DIR:02X} 이 직렬화 상태의 그 자리에 없음)')
    res['status'] = 'failed' if res['problems'] else 'passed'
    res['frames'] = walker.c.n
    try:
        walker.c.shot(out / 'end.png')
    except Exception:  # noqa: BLE001 — 화면이 없어도 판정은 남긴다
        pass
    (out / 'scene.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
    return res


# ---- 장면 목록 --------------------------------------------------------------------------------------------------------

# 명령 창 → しらべる(dq4ch1walkcheck.SEARCH 와 같은 줄)
SEARCH = 'a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200'


HERO_HP = [(0x7E2042, 0xE7), (0x7E2043, 0x03)]     # 주인공 HP 999(dq4ch1walkcheck.HERO_HP)


MONSTERS = 0x118000                # 몬스터 표 23:8000(파일 위치), 25바이트씩(dq4ch1walkcheck.MONSTERS)


def strong(n):
    """몬스터 n 의 HP 를 2047 로(바이트3 + 바이트10 아래 3비트, dq4ch1walkcheck.boss_patch 와 같은 자리) 덮는 패치.
    여러 차례 주고받게 해 적의 공격·우리 편이 맞음·빗나감 소리를 듣는다."""
    base = MONSTERS + n * 25
    return [(base + 3, b'\xff'), (base + 10, lambda v: bytes((v[0] | 0x07,)))]


def talk(face, n=4, gap=50):
    """그 쪽을 보고 명령 창 → 「이야기하기」, 그 뒤 A 로 대사를 넘긴다."""
    return f'{face}:8;wait:30;a:8;wait:60;a:8;wait:60;' + ';'.join([f'a:8;wait:{gap}'] * n)


def sfx(k):
    return (SFX, *k)


def uncovered(table, every):
    """장면도 UNREACHED 도 맡지 않은 대응표 항목."""
    covered = {c for s in every for c in s.covers} | set(UNREACHED)
    return [e for e in table.entries() if e not in covered]


# 1장 장면으로 부르지 못하는 대응표 항목과 까닭. unreached_problems 가 롬에서 그 까닭을 다시 본다
UNREACHED = {
    'sfx 3C-00': '부르는 자리가 카지노 슬롯 루틴 11:B3B7 하나뿐이고 1장에 카지노가 없음',
    'pcm 40-03': '롬에 이 갈래를 넣는 코드(BRK 16|19 40 03, LDA #40 / LDX #03)가 없음',
}
# 장면은 없지만 1장에서 부를 수 있는 항목(런타임으로 확인하지 못한 것). 단위 테스트가 이 목록을 고정해, 새로 빠지는
# 항목이 생기면 드러나게 한다. --sfx-call 자리는 롬 바이트만 보고(call_site_problems), 게임 안에서 어느 자리를
# 지났는지는 가르지 못한다(문·상자 장면은 갈래 01·00 의 어느 한 자리를 지남)
RUNTIME_GAPS = {
    'pcm 45-02',    # 35-02 를 부르는 일곱 자리. 걸어서 여는 문·열쇠 문·문 명령은 모두 갈래 01 이었음
    'sfx 3B-01',    # 11:B673(카지노)과 20:D2E1(전투 쪽 코드, 어느 연출인지 모름)이 부름
}


def call_sites(rom, sfx, branch):
    """롬에서 `BRK 16|19 sfx branch` 와 `LDA #sfx / LDX #branch`(·거꾸로) 자리(CPU 주소)."""
    import re
    pats = [bytes((0, 0x16, sfx, branch)), bytes((0, 0x19, sfx, branch)), bytes((0xA9, sfx, 0xA2, branch)),
            bytes((0xA2, branch, 0xA9, sfx))]
    return sorted({(m.start() // 0x8000) << 16 | 0x8000 | m.start() % 0x8000
                   for p in pats for m in re.finditer(re.escape(p), rom)})


UNREACHED_SITES = {'sfx 3C-00': [0x11B3B7], 'pcm 40-03': []}


def unreached_problems(rom):
    """UNREACHED 의 까닭을 롬에서: 부르는 자리가 적어 둔 그대로인지."""
    out = []
    for k, want in UNREACHED_SITES.items():
        got = call_sites(rom, *key(k.split()[1]))
        if got != want:
            out.append(f'{k}: 부르는 자리 {[f"{a:06X}" for a in got]}, 기대 {[f"{a:06X}" for a in want]}')
    return out


def leftover_sites(rom, table):
    """대응표가 번호를 바꾼 원래 효과음(35-00·01·02)을 아직 부르는 자리 — 바뀌지 않은 사본 코드(결과에 적기만 함)."""
    olds = {old for old, _ in table.calls.values()}
    return [f'{a:06X} {o:02X}-{b:02X}' for o in sorted(olds) for b in range(4) for a in call_sites(rom, o, b)]


# ---- 효과음 결정 표(손으로 적음) --------------------------------------------------------------------------------------
# 빌드 입력(dq4sound-game.args)과 따로 둔 기준이다. 사용자가 청취로 고른 결정(DQ5 기본, 확실히 나은 것만 NDS:
# dq4-sound-port-format.md 「효과음 이식」 1~8 절)을 동작마다 적는다.
#   이름: (DQ5 원래 (효과음, 갈래), 부르는 자리 또는 None, 결정, 대기열에 들어갈 (효과음, 갈래), 울린 바탕)
# 바탕: 'dq5' = 원본 DQ5 롬(rom/dq5.sfc)의 어느 샘플과 BRR 이 같음, 'nds' = 원본 DQ5 에 없는 샘플, 'noise' = DSP 잡음.
# 결정이 NDS 인데 바탕이 dq5 이거나, DQ5 인데 nds 면 그 소리가 결정과 다르다.
DECISIONS = {
    'menu':        ((0x33, 0x00), None, 'NDS 12C 決定音', (0x33, 0x00), 'nds'),
    'yes-no':      ((0x33, 0x01), None, 'NDS 12C 決定音', (0x33, 0x01), 'nds'),
    'reject':      ((0x33, 0x02), None, 'NDS 12C 決定音', (0x33, 0x02), 'nds'),
    'talk':        ((0x32, 0x00), None, 'DQ5', (0x32, 0x00), 'dq5'),
    'stairs':      ((0x34, 0x02), None, 'NDS 131 階段', (0x34, 0x02), 'noise'),
    'bump':        ((0x34, 0x03), None, 'DQ5', (0x34, 0x03), 'dq5'),
    'door':        ((0x35, 0x01), 0x01E01B, 'NDS 134 扉（小）', (0x45, 0x01), 'nds'),
    'chest':       ((0x35, 0x00), 0x05E6A9, 'NDS 13A 宝箱', (0x3F, 0x00), 'nds'),
    'item':        (None, None, 'NDS 146 アイテム出現', (0x3F, 0x01), 'nds'),
    'attack':      ((0x37, 0x01), None, 'NDS 190 PC攻撃開始', (0x37, 0x01), 'nds'),
    'enemy-attack': ((0x37, 0x02), None, 'NDS 191 敵攻撃開始', (0x37, 0x02), 'nds'),
    'pc-hit':      ((0x37, 0x03), None, 'NDS 193 PCにダメージ', (0x37, 0x03), 'noise'),
    'enemy-hit':   ((0x37, 0x04), None, 'NDS 192 敵にダメージ', (0x37, 0x04), 'noise'),
    'miss':        ((0x37, 0x0D), None, 'NDS 194 敵のミス', (0x37, 0x0D), 'nds'),
    'spell':       ((0x37, 0x0E), None, 'NDS 132 呪文使用時', (0x37, 0x0E), 'nds'),
    'claw-kind':   ((0x37, 0x08), None, 'NDS 19D WEP_TETUTUME', (0x37, 0x08), 'noise'),
    'hoimi':       ((0x36, 0x00), None, 'DQ5', (0x36, 0x00), 'dq5'),
    'critical':    ((0x37, 0x0B), None, 'DQ5', (0x37, 0x0B), 'dq5'),
    'flee':        ((0x37, 0x00), None, 'DQ5', (0x37, 0x00), 'dq5'),
    'boss-hit':    ((0x37, 0x14), None, 'NDS 192 敵にダメージ', (0x45, 0x03), 'noise'),
    'scara':       ((0x46, 0x04), None, 'NDS 1F6 GAB_03', (0x45, 0x04), 'nds'),
    'spar-hero':   (None, None, 'NDS 19C 銅の剣', (0x40, 0x01), 'nds'),
    'spar-master': (None, None, 'NDS 1A0 鋼の剣', (0x40, 0x02), 'nds'),
    'frog-jump':   (None, None, 'NDS 47B EVE_JUMP', (0x45, 0x00), 'nds'),
}
# DQ5 효과음이 쓰는 늘 두는 파형(원본 DQ5 샘플 1F~22). --sfx-wave 가 이 자리에 NDS 파형을 넣으면 그 파형을 쓰는 DQ5
# 효과음(DQ5 로 고른 것 포함)의 소리도 바뀐다. 결과의 findings 에 적기만 한다
RESIDENT_WAVES = (0x1F, 0x20, 0x21, 0x22)


def resident_wave_diffs(rom, dq5=None):
    """롬의 늘 두는 파형 가운데 원본 DQ5 와 BRR 이 다른 번호."""
    import dq4soundcheck as sc
    dq5 = dq5 or dq5_samples()
    return [f'{n:02X}' for n in RESIDENT_WAVES if sc.sample_body(rom, n)[7:] != dq5[n]]


def d(key):
    """결정 표의 대기열 기대값과 바탕: (명령, 효과음, 갈래, 바탕)."""
    _, _, _, queue, kind = DECISIONS[key]
    return (SFX, *queue, kind)


def decision_problems(table):
    """빌드 입력이 결정 표와 어긋나는 곳: NDS 로 고른 DQ5 소리가 대응표를 거쳐 결정 표의 대기열 값으로 가는지, DQ5 로
    고른 소리는 대응표가 바꾸지 않는지(--sfx·--sfx-remap 에 없음)."""
    out = []
    for key, (orig, site, choice, queue, _) in DECISIONS.items():
        if orig is None:
            continue
        got = routed(table, *orig, site)
        if got != queue:
            out.append(f'{key}: 대응표로 {name(got)}, 결정 표 {name(queue)}')
        if choice == 'DQ5' and (orig in table.sfx or orig in table.remap):
            out.append(f'{key}: DQ5 로 고른 {name(orig)} 를 대응표가 바꿈')
        if choice.startswith('NDS ') and orig in table.sfx and table.sfx[orig] != choice.split()[1]:
            out.append(f'{key}: --sfx {name(orig)}={table.sfx[orig]}, 결정 표 {choice.split()[1]}')
    return out


TOWER = '39/01,20,16'                 # 탑 39/01: FC 던전 조우 구역(dq4battlecheck 의 tower 장면과 같은 자리)
FIGHT = 'down:8;wait:200;'            # 한 걸음 내디뎌 강제 조우
SLIME, BOSS = 0x00, 0xE2              # 슬라임, 탑 위 보스(dq4ch1event.BOSS_MONSTERS 첫째)
WEAPON = 0x7E0DA7                     # 공격하는 사람의 무기(28:8055 가 읽음). 프레임마다 묶어 무기를 고른다
NEXT_EXP = 'poke=2066=01;2067=00;2068=00'  # 주인공 다음 레벨 경험치(+26~+28)를 1 로: 한 번 이기면 레벨 업
# --pick-critical-seed 80 으로 고른 시드(A 15번 안에 회심). 두 코어는 전투에 드는 프레임이 하나 달라 난수가 갈린다.
# 전투 메시지 길이 같은 상관없는 변경에도 바뀌므로(snes9x 29 가 빠졌음), 두 롬에서 함께 난 시드를 골랐다
CRITICAL_SEED = {'snes9x': 48, 'bsnes': 19}
SCARA = 0x55                          # 몬스터 행동 スカラ(돌려 부르기 46-04 를 듣는 시험 롬)


CLAW, CLAW_KIND_SOUND = 0x2F, (0x37, 0x08)   # てつのツメ: 26:8A65 종류 4, 28:816E[4] = 37-08(롬 실측)


def boss_setup():
    """1장 걷기 검사가 탑 위 구간(tower_top)에 이르렀을 때의 flag·물건·동료(dq4ch1walkcheck.setup)를 저장 기록 값으로."""
    import dq4ch1walkcheck as wc
    first = next(k for k, seg in enumerate(wc.SEGMENTS) if seg[0] == 'tower_top')
    sets, party = wc.setup(wc.SEGMENTS, first)
    return [f'poke={sets}'] + ([f'party={party}'] if party else [])


def boss_inputs():
    import dq4ch1walkcheck as wc
    return next(seg[2] for seg in wc.SEGMENTS if seg[0] == 'boss')


def boss_patches():
    import dq4ch1event as ev
    out = []
    for n in ev.BOSS_MONSTERS:
        out += weak(n)
    return out


def taps(n, gap=40):
    return ';'.join([f'a:8;wait:{gap}'] * n)


def actions(n, act):
    """몬스터 n 의 행동 여섯(바이트 17~22)을 모두 act 로, MP(바이트4)를 255 로(주문은 MP 가 모자라면 때리기로 바뀜)."""
    return [(MONSTERS + n * 25 + 17, bytes([act] * 6)), (MONSTERS + n * 25 + 4, b'\xff')]


def harmless(n):
    """몬스터 n 의 공격력을 0 으로(바이트1, 바이트8 bit7): 맞혀도 피해가 0 이라 빗나감 소리가 난다."""
    base = MONSTERS + n * 25
    return [(base + 1, b'\x00'), (base + 8, lambda v: bytes((v[0] & 0x7F,)))]


def weak(n):
    """몬스터 n 을 HP 1·수비 0 으로(dq4ch1walkcheck.boss_patch 와 같은 바이트)."""
    base = MONSTERS + n * 25
    return [(base + 2, b'\x00'), (base + 3, b'\x01'), (base + 8, lambda v: bytes((v[0] & ~0x40 & 0xFF,))),
            (base + 10, lambda v: bytes((v[0] & ~0x07 & 0xFF,)))]


# 무기 소리는 모두 NDS 로 골랐다(효과음 이식 5). 효과음 번호는 빌드가 빈 효과음에 차례로 놓아 결정 표에 적지 않고,
# 바탕이 원본 DQ5 소리가 아닌지만 본다(not-dq5)
SPAR_KEYS = {(0x40, 0x01): 'spar-hero', (0x40, 0x02): 'spar-master', (0x37, 0x03): 'pc-hit'}


def scenes(table):
    """대응표에서 기대값을 계산한 장면 목록. 효과음마다 DQ5 원래 (효과음, 갈래)와 부르는 자리를 적고 routed 로 옮긴다."""
    import dq4prologue as pro
    import dq4prologuecheck as pc
    battle_song = table.weapon_songs[0]
    attack, enemy_hit = d('attack'), d('enemy-hit')
    out = [
        Scene('menu-open', '필드에서 명령 창 열기(DQ5 33-00)', [d('menu')],
              covers=['sfx 33-00'], inputs='a:8;wait:60'),
        Scene('menu-cursor', '명령 창 커서 움직이기(창 선택 고리 BRK 19 33 00)',
              [d('menu')] * 2, inputs='a:8;wait:60;down:6;wait:40'),
        # 배포 롬 그대로(대기열 훅·조우 패치 없음): 명령 칸은 이미 지워졌을 수 있어 인자·X 만 맞추고, 울림과 바탕은 같게 본다
        Scene('menu-open-release', '배포 롬: 필드에서 명령 창 열기', [(None, *d('menu')[1:])], release=True,
              inputs='a:8;wait:60'),
        Scene('stairs-release', '배포 롬: 왕좌의 방 아래 출구', [(None, *d('stairs')[1:])], release=True,
              warp='36/01,32,68', inputs='down:90;wait:120'),
        Scene('talk', '사람에게 말 걸기: 대화 글자(DQ5 32-00)', [d('talk')],
              warp='36/00,16,72', inputs=talk('up', 2)),
        Scene('stairs', '왕좌의 방 아래 출구로 나가기(DQ5 34-02)', [d('stairs')],
              covers=['sfx 34-02'], warp='36/01,32,68', inputs='down:90;wait:120'),
        Scene('door', '이무르 문 열기(DQ5 35-01, 01:E01B 등 문 15곳)', [d('door')],
              covers=['pcm 45-01'], forbid=[sfx((0x35, 0x01))], warp='37/00,38,45',
              inputs='up:100;wait:60'),
        Scene('locked-door', '잠긴 문에 부딪힘(DQ5 34-03)', [d('bump')],
              warp='36/01,6,27', inputs='up:60;wait:120'),
        Scene('chest', '우물 아래 상자 열기(DQ5 35-00, 05:E6A9 등 상자 7곳)', [d('chest')],
              covers=['pcm 3F-00'], forbid=[sfx((0x35, 0x00))], warp='3B/03,14,14',
              inputs='up:8;wait:30;' + SEARCH + ';a:8;wait:60'),
        Scene('pot', '항아리에서 물건 찾기(--sfx-item)', [d('item')],
              covers=[f'item {name(table.items[0])}', f'pcm {name(table.items[0])}'],
              warp='38/01,4,5', inputs='up:8;wait:30;' + SEARCH + ';a:8;wait:60'),
        Scene('inn', '여관에 묵기: 예·아니요 창(DQ5 33-01)과 징글(곡 1D)', [d('yes-no'), (SONG, 0x1D, None)],
              covers=['sfx 33-01', 'inn-jingle'], sets=['flag=CHAPTER1', 'gold=1000'], warp='36/00,16,72',
              npc_talk=(16, 71, 0x006), inputs=talk('up', 1) + ';a:8;wait:60;a:8;wait:60;a:8;wait:600'),
        Scene('church', '교회에서 기록하기: 예·아니요(DQ5 33-01)와 기록 징글(곡 20)',
              [d('yes-no'), (SONG, 0x20, None)], warp='36/00,10,43',
              inputs=talk('up', 1) + ';' + taps(4, 60) + ';a:8;wait:300;a:8;wait:400;' + taps(2, 200)),
        Scene('battle-win', '걸음 전투: 공격 시작(37-01)·무기(00)·적이 맞음(37-04)·승리(곡 1F)·레벨 업(곡 21)',
              [attack, (*sfx(weapon_sound(table, 0x00, battle_song)), 'not-dq5'), enemy_hit, (SONG, 0x1F, None), (SONG, 0x21, None)],
              covers=['sfx 37-01', 'sfx 37-04'], sets=['flag=CHAPTER1', NEXT_EXP], warp=TOWER, battle=[(SLIME, 1)],
              pokes=HERO_HP + [(WEAPON, 0x00)], patches=weak(SLIME), inputs=FIGHT + taps(30)),
        Scene('battle-trade', '주고받기: 적의 공격 시작(37-02)·우리 편이 맞음(37-03)',
              [attack, enemy_hit, d('enemy-attack'), d('pc-hit')],
              covers=['sfx 37-02', 'sfx 37-03'], warp=TOWER, battle=[(SLIME, 1)], pokes=HERO_HP,
              patches=strong(SLIME), inputs=FIGHT + taps(20)),
        Scene('battle-miss', '공격력 0 인 적이 때림: 빗나감(37-0D)', [d('enemy-attack'), d('miss')],
              covers=['sfx 37-0D'], warp=TOWER, battle=[(SLIME, 1)], pokes=HERO_HP,
              patches=strong(SLIME) + harmless(SLIME), inputs=FIGHT + taps(20)),
        Scene('battle-scara', '적의 スカラ: 돌려 부르기 46-04 → 45-04', [d('scara')],
              covers=['remap 46-04', 'pcm 45-04'], forbid=[sfx((0x46, 0x04))], warp=TOWER, battle=[(SLIME, 1)],
              pokes=HERO_HP, patches=strong(SLIME) + actions(SLIME, SCARA), inputs=FIGHT + taps(20)),
        Scene('battle-boss', '탑 위 보스 전투(사건 전투, 전투 곡이 무기 표 곡이 아님): 발톱 무기의 종류 소리(28:816E 종류 4 → '
              'DQ5 37-08)와 보스가 맞음(돌려 부르기 37-14 → 45-03)',
              [d('claw-kind'), d('boss-hit')],
              covers=['sfx 37-08', 'remap 37-14', 'pcm 45-03'], forbid=[sfx((0x37, 0x14))],
              sets=['flag=CHAPTER1'] + boss_setup(), warp='39/04,46,40', pokes=HERO_HP + [(WEAPON, CLAW)],
              patches=boss_patches(), inputs=boss_inputs()),
        Scene('battle-critical', '회심의 일격(DQ5 37-0B)', [attack, d('critical')], warp=TOWER, battle=[(SLIME, 1)],
              pokes=HERO_HP, seed=CRITICAL_SEED, critical=True, patches=strong(SLIME), inputs=FIGHT + taps(15)),
        Scene('battle-flee', '도망(DQ5 37-00)', [d('flee')], warp=TOWER, battle=[(SLIME, 1)],
              pokes=HERO_HP, patches=strong(SLIME), inputs=FIGHT + 'down:8;wait:30;' + taps(8)),
        Scene('training', '전원부터 새 게임: 이름 칸이 찬 뒤 A(33-02), 서장 칼 여섯 합(40-01·40-02·37-03)',
              [d('reject')] + [d(SPAR_KEYS[se]) for se, _, _ in pro.SPAR],
              covers=['sfx 33-02', 'pcm 40-01', 'pcm 40-02'], place='power'),
        Scene('frog', '서장 개구리가 연못에서 뛰어오름(45-00 두 번)', [d('frog-jump')] * 2,
              covers=['pcm 45-00'], place='power', inputs=';'.join(w for k, w in pc.ROUTE if k in ('train', 'frog'))),
        Scene('battle-heal', '호이민이 ホイミ: 주문 외움(37-0E)·ホイミ 효과(DQ5 36-00)',
              [d('spell'), d('hoimi')], covers=['sfx 37-0E'],
              sets=['flag=CHAPTER1', 'effect=hoimin', 'flag=HOIMIN'], warp=TOWER, battle=[(SLIME, 1)],
              pokes=[(0x7E2042, 0x02), (0x7E2043, 0x00)], patches=strong(SLIME) + harmless(SLIME), inputs=FIGHT + taps(30)),
    ]
    for w, se in sorted(table.weapons.items()):
        out.append(Scene(f'weapon-{w:02X}', f'たたかう: 무기 {w:02X} 소리(전투 곡 {battle_song:02X})',
                         [attack, (*sfx(weapon_sound(table, w, battle_song)), 'not-dq5')], covers=[f'weapon {w:02X}', f'pcm {name(se)}'],
                         warp=TOWER, battle=[(SLIME, 1)], pokes=HERO_HP + [(WEAPON, w)], patches=weak(SLIME),
                         inputs=FIGHT + taps(4)))
    return out


# ---- 명령 ------------------------------------------------------------------------------------------------------------

def unreached_problems(rom):
    return []


CRIT_PREFIX = 'crit-'
# bsnes 에서 직렬화(DSP 읽기)가 타이밍을 바꾸지 않는지: 이 장면들을 DSP 를 읽지 않고 한 번 더 돌려 대기열 기록이
# 프레임까지 같은지 본다
CONTROL = ('chest', 'battle-trade')
# 실측: DSP 를 읽으면 bsnes 대기열 시각이 많아야 1프레임 늦고(코어 동기 지점), 값·차례는 같았다
CONTROL_SHIFT = 2


def crit_scene(seed):
    """회심 시드 고르기용 장면(battle-critical 과 같은 입력, 시드만 다름)."""
    return Scene(f'{CRIT_PREFIX}{seed}', '회심 시드 찾기', [], warp=TOWER, battle=[(SLIME, 1)], pokes=HERO_HP, seed=seed,
                 patches=strong(SLIME), inputs=FIGHT + taps(15))


def find_scene(table, name):
    if name.startswith(CRIT_PREFIX):
        return crit_scene(int(name[len(CRIT_PREFIX):]))
    return next(s for s in scenes(table) if s.name == name)


def run_one(args):
    table = load_table(ARGS.read_text())
    scene = find_scene(table, args.only)
    res = run_scene(args.core, args.rom.resolve(), scene, args.out.resolve(), dsp=not args.no_dsp)
    return 0 if res['status'] == 'passed' else 1


def run_jobs(jobs, rom_path, out, n):
    """[(코어, 장면, DSP 읽기)] 를 장면마다 프로세스 하나로(같은 dylib 를 한 프로세스에서 둘 열지 않게)."""
    import dq4compatcheck as cc

    def one(job):
        core, scene, dsp = job
        dest = out / core / (scene.name if dsp else scene.name + '-nodsp')
        dest.mkdir(parents=True)
        with (dest / 'log.txt').open('w') as log:
            proc = subprocess.run([sys.executable, __file__, '--_one', '--core', core, '--only', scene.name,
                                   '--rom', str(rom_path), '--out', str(dest)] + ([] if dsp else ['--no-dsp']),
                                  stdout=log, stderr=subprocess.STDOUT, timeout=cc.UNIT_TIMEOUT, check=False)
        f = dest / 'scene.json'
        if f.exists():
            return json.loads(f.read_text())
        return {'scene': scene.name, 'core': core, 'status': 'failed',
                'problems': [f'장면 프로세스가 결과를 남기지 않음(종료 {proc.returncode}, {dest / "log.txt"})']}
    with concurrent.futures.ThreadPoolExecutor(max(1, n)) as pool:
        return list(pool.map(one, jobs))


def pick_seeds(rom_path, out, cores, last, n):
    """회심 시드 고르기: 시드 1~last 를 코어마다 돌려 회심(0C 37 0B)이 난 시드를 찍는다."""
    jobs = [(c, crit_scene(k), True) for k in range(1, last + 1) for c in cores]
    found = {c: [] for c in cores}
    for (c, sc, _), r in zip(jobs, run_jobs(jobs, rom_path, out, n)):
        if any(q.endswith(' 0C 37 0B') for q in r.get('queue', [])):
            found[c].append(int(sc.name[len(CRIT_PREFIX):]))
    print(json.dumps(found))
    return 0


def main():
    import dq4compatcheck as cc
    import dq4cores
    import dq4savefixture as fx
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--only', help='장면 이름(쉼표)')
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--pick-critical-seed', type=int, metavar='N', help='회심 장면 시드를 1~N 에서 코어마다 고름')
    ap.add_argument('--no-dsp', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--_one', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args._one:
        return run_one(args)
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom_path = args.rom.resolve()
    rom = rom_path.read_bytes()
    table = load_table(ARGS.read_text())
    every = scenes(table)
    cores = list(cc.CORES) if args.core == 'all' else [args.core]
    for c in cores:
        if not dq4cores.core_path(c).exists():
            raise SystemExit(f'{dq4cores.core_path(c)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드')
    fx.SaveSlot.new_game(rom_path)            # 밑판을 먼저 한 번(장면 프로세스끼리 함께 만들지 않게)
    if args.pick_critical_seed:
        return pick_seeds(rom_path, out, cores, args.pick_critical_seed, args.jobs)
    if args.only:
        names = args.only.split(',')
        unknown = set(names) - {s.name for s in every}
        if unknown:
            raise SystemExit(f'모르는 장면: {sorted(unknown)}')
        every = [s for s in every if s.name in names]
    t0 = time.time()
    all_scenes = scenes(table)
    static = {'call_sites': call_site_problems(rom, table), 'weapon_table': weapon_table_problems(rom, table),
              'decisions': decision_problems(table), 'unreached': unreached_problems(rom),
              'uncovered': [e for e in uncovered(table, all_scenes)
                            if e not in RUNTIME_GAPS and not e.startswith('call ')]}
    jobs = [(c, s, True) for s in every for c in cores]
    jobs += [('bsnes', s, False) for s in every if s.name in CONTROL and 'bsnes' in cores]
    done = run_jobs(jobs, rom_path, out, args.jobs)
    results = [r for (_, _, dsp), r in zip(jobs, done) if dsp]
    control = {}
    for (c, sc, dsp), r in zip(jobs, done):
        if not dsp:
            twin = next(x for (c2, s2, d2), x in zip(jobs, done) if d2 and c2 == c and s2.name == sc.name)
            a, b = r.get('queue', []), twin.get('queue', [])
            same = bool(a) and [x.split(None, 1)[1] for x in a] == [y.split(None, 1)[1] for y in b]
            shift = max((abs(int(x.split()[0]) - int(y.split()[0])) for x, y in zip(a, b)), default=None)
            control[sc.name] = {'same_values': same, 'max_frame_shift': shift, 'queue_len': len(a)}
            if not same or shift is None or shift > CONTROL_SHIFT:
                static.setdefault('control', []).append(
                    f'{sc.name}: DSP 를 읽지 않은 bsnes 실행과 대기열 기록이 다름(값 같음 {same}, 프레임 차 {shift})')
    problems = [f'{k}: {p}' for k, v in static.items() for p in v]
    ok = not problems and all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'rom_sha1': hashlib.sha1(rom).hexdigest(),
              'seconds': round(time.time() - t0, 1), 'static': static, 'control': control,
              'runtime_uncovered': sorted(RUNTIME_GAPS | {f'call {a:06X}' for a in table.calls}),
              'findings': {'leftover_sites': leftover_sites(rom, table), 'resident_waves_changed': resident_wave_diffs(rom),
                           'scenes': sorted({f for r in results for f in r.get('findings', [])})},
              'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for r in results:
        got = ', '.join(f"{w['want']}@{w['frame']}{'♪' + str(w.get('source') or '') if w.get('sounded') else '✕'}"
                        for w in r.get('want', []))
        print(f"{r['status']:6} {r.get('core', '?')[:6]:6} {r['scene']:18} {got} {'; '.join(r['problems'])}"
              + ''.join(f' [찾은 것] {x}' for x in r.get('findings', [])))
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds'],
                      'control': control, 'runtime_uncovered': report['runtime_uncovered'],
                      'findings': report['findings'], 'static_problems': problems},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
